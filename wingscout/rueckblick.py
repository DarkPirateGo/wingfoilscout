"""Rückblick — wie gut lag die Vorhersage an den besten Zielen der letzten Suche?

Der Prüfstand misst einen festen Monat an zehn festen Spots, damit sich
Änderungen am Code vergleichen lassen. Der Rückblick beantwortet die andere
Frage, die sich beim Lesen des Reports stellt: *Kann ich dem trauen?* Er nimmt
die besten Ziele der letzten Suche, holt für die letzten Tage die gemessenen
Winde der nächsten Wetterstation und die aufgehobene Vorhersage, rechnet die
Vorhersage durch die ganze Bewertung — Regionalmodell, `wind_factor`,
Thermik — und stellt beide nebeneinander, Stunde für Stunde.

Was man wissen muss, steht auch auf der Seite: Die aufgehobene Vorhersage ist
die mit dem kürzesten Vorlauf („heute für heute“), nicht die von vor drei
Tagen. Eine Station misst über Land, der Spot liegt über Wasser. Und eine
Station gibt es nur für Spots in Deutschland, den Niederlanden, Österreich,
Dänemark und Frankreich (und über die Grenze in deren Nähe) — die anderen
stehen mit dem Vermerk in der Liste.

Der Zeitraum reicht bis heute: die letzten `tage` Tage einschließlich des
laufenden, bis zur aktuellen Stunde. Wie weit die Messung an „jetzt“
heranreicht, hängt am Dienst, und sie hat Lücken — die Sonde vom 19.09.,
08 UTC: DWD geprüfte Stunden bis vorgestern, der laufende Tag aus den
Zehnminutenwerten, gestern fehlt (kommt mit der nächsten Tagesdatei); KNMI
bis vorgestern; GeoSphere bis zur aktuellen Stunde; Météo-France bis heute
03 UTC (die Tagesdatei erscheint morgens mit den Stunden bis kurz davor).
Je Spot steht deshalb, welche Stunden eine Messung haben (`abdeckung`).
"""
from __future__ import annotations
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from . import CACHE, modellvergleich
from . import i18n
from .i18n import T, TN, N_                                       # noqa: F401
from .models import DEFAULT_MODELS
from .spots import zeitzone
from .pruefstand import masse, _utc_stunde

LETZTER_LAUF = CACHE / "letzter_lauf.json"
ERGEBNIS = CACHE / "rueckblick.json"
MAX_TAGE = 14


def letzter_lauf() -> dict | None:
    if not LETZTER_LAUF.exists():
        return None
    try:
        return json.loads(LETZTER_LAUF.read_text(encoding="utf-8"))
    except ValueError:
        return None


def zeitraum(tage: int, heute: date | None = None) -> tuple[str, str]:
    """Die letzten `tage` Tage einschließlich heute — bis 1.8.1 endete der
    Zeitraum gestern, und der laufende Tag, den man gerade erlebt, fehlte."""
    heute = heute or date.today()
    tage = max(1, min(MAX_TAGE, int(tage)))
    return (heute - timedelta(days=tage - 1)).isoformat(), heute.isoformat()


def _stundenreihe(rows, fc: dict, obs_stunden: dict, jetzt_utc: str | None = None) -> list:
    """Je Vorhersagestunde: Ortszeit, Wingfoilscout-Wind, Messung, beide Richtungen.
    Stunden nach `jetzt_utc` fallen weg — Zukunft ist kein Rückblick."""
    offset = int(fc.get("utc_offset_seconds") or 0)
    aus = []
    for r in rows:
        utc = _utc_stunde(r["t"], offset)
        if jetzt_utc and utc > jetzt_utc:
            continue
        m = obs_stunden.get(utc)
        aus.append({"t": r["t"].strftime("%Y-%m-%dT%H:%M"), "v": round(float(r["wind"]), 1),
                    "vd": (round(float(r["dir"])) if r["dir"] is not None else None),
                    "m": (m["kn"] if m else None), "md": (m.get("dir") if m else None),
                    "modell": r.get("modell"), "thermik": bool(r.get("thermal"))})
    return aus


def abdeckung(stunden: list) -> str:
    """Welche Stunden eine Messung haben, als kurzer Text — „Do 17.09. 00–23 Uhr ·
    Sa 19.09. 00–09 Uhr“. Die Lücke dazwischen ist das, was man wissen muss:
    bei DWD und KNMI fehlt gestern, bis die nächste Tagesdatei kommt."""
    laeufe: list = []
    for h in stunden:
        if h.get("m") is None:
            continue
        t = datetime.fromisoformat(h["t"])
        if laeufe and laeufe[-1][1] + timedelta(hours=1) == t:
            laeufe[-1][1] = t
        else:
            laeufe.append([t, t])

    teile = []
    for a, b in laeufe:
        if a.date() == b.date():
            teile.append(T("{tag} {von}–{bis} Uhr", tag=i18n.tag(a), von=i18n.stunde(a), bis=i18n.stunde(b)))
        else:
            teile.append(T("{tag1} {von} Uhr bis {tag2} {bis} Uhr",
                           tag1=i18n.tag(a), von=i18n.stunde(a), tag2=i18n.tag(b), bis=i18n.stunde(b)))
    return " · ".join(teile)


MAX_KM_VORGABE = 30
MAX_KM_GRENZE = 100
GUT_GENUG = 0.9          # Anteil der Stunden bis jetzt, ab dem die nächste Station reicht
FAST_SO_VIELE = 0.8      # sonst: die nächste mit wenigstens 80 % der besten Abdeckung


def moegliche_stunden(von: str, jetzt_utc: str) -> int:
    """Wie viele UTC-Stunden vom Beginn des Zeitraums bis jetzt eine Messung
    haben könnten — so zählen auch die Dienste (UTC-Tag des Stempels)."""
    try:
        start = datetime.fromisoformat(f"{von}T00:00")
        ende = datetime.fromisoformat(jetzt_utc)
    except ValueError:
        return 0
    return max(0, int((ende - start).total_seconds() // 3600) + 1)


def gedeckt(stunden: dict, von: str, jetzt_utc: str) -> int:
    """Wie viele dieser Stunden die Station tatsächlich hat."""
    return sum(1 for t in stunden if f"{von}T00:00" <= t <= jetzt_utc)


def station_waehlen(versuche: list, moeglich: int) -> int | None:
    """Welcher Versuch zählt — Index in `versuche` [(station, obs, km, stunden)],
    die nach Entfernung sortiert sind.

    Bis 1.14.0 gewann die nächste Station, die *überhaupt* Werte hatte. Die
    Sonde vom 20.09. zeigte die Folge: IJmuiden Zone 1 bekam KNMI IJmuiden
    (0,8 km) mit 24 Stunden, alle von vorgestern — Rijkswaterstaat Buitenhaven,
    genauso weit weg, hatte Werte bis jetzt. Jetzt gilt:

      1. die nächste Station, die mindestens 90 % der Stunden bis jetzt hat;
      2. hat keine so viel: die nächste, die wenigstens 80 % dessen hat, was
         die beste hat — eine Station 25 km weiter mit einer Stunde mehr
         verdrängt die nahe nicht.
    """
    mit = [(i, n) for i, (_st, _obs, _km, n) in enumerate(versuche) if n > 0]
    if not mit:
        return None
    for i, n in mit:
        if moeglich and n >= GUT_GENUG * moeglich:
            return i
    beste = max(n for _, n in mit)
    return next(i for i, n in mit if n >= FAST_SO_VIELE * beste)


def rechne(cfg, spots_by_id: dict, top: list, tage: int, geometry: dict, log=None,
           heute: date | None = None, jetzt: datetime | None = None, max_km: float = MAX_KM_VORGABE) -> dict:
    """Die besten Ziele gegen die Messung der letzten `tage` Tage bis jetzt. Netz nötig.

    `max_km`: wie weit eine Station vom Spot liegen darf. Der Prüfstand nimmt
    12 km, weil er dieselben Paare über Monate vergleicht; hier zählt, dass
    überhaupt eine Messung da ist — und 30 km Küste sind meist derselbe Wind,
    30 km Binnenland nicht. Die Entfernung steht bei jedem Spot dabei.
    """
    from .sources import stationen
    say = log or (lambda *a: None)
    von, bis = zeitraum(tage, heute)
    max_km = max(1.0, min(float(MAX_KM_GRENZE), float(max_km or MAX_KM_VORGABE)))
    from datetime import timezone as _tz
    jetzt = jetzt or datetime.now(_tz.utc).replace(tzinfo=None)
    jetzt_utc = jetzt.strftime("%Y-%m-%dT%H:00")
    models = cfg.get("wind", {}).get("models") or DEFAULT_MODELS
    stationen.windguru_setzen((cfg.get("stationen") or {}).get("windguru"))
    spots = [spots_by_id[t["id"]] for t in top if t["id"] in spots_by_id]
    say(T("{n} Ziele, {von} bis {bis}, Stationen bis {km} km", n=len(spots), von=von, bis=bis, km=f"{max_km:.0f}"))
    paare = {p["spot"]["id"]: p for p in stationen.paare_finden(spots, max_km, log=say)}

    from . import __version__
    ergebnis = {"zeit": datetime.now().isoformat(timespec="minutes"), "von": von, "bis": bis,
                "bis_utc": jetzt_utc, "tage": int(tage), "max_km": max_km, "version": __version__,
                "suche": (letzter_lauf() or {}).get("zeit"), "spots": []}
    for eintrag in top:
        spot = spots_by_id.get(eintrag["id"])
        if not spot:
            continue
        zeile, _ = spot_zeile(cfg, spot, paare.get(spot["id"]), von, bis, jetzt_utc, geometry, max_km,
                              say, models, rang=eintrag.get("rang"))
        ergebnis["spots"].append(zeile)
    ergebnis["vergleich_gesamt"] = modellvergleich.gesamt(ergebnis["spots"])
    return ergebnis


def spot_zeile(cfg, spot: dict, paar: dict | None, von: str, bis: str, jetzt_utc: str, geometry: dict,
               max_km: float, say, models: list, rang=None) -> tuple[dict, list | None]:
    """Ein Spot gegen die Messung von `von` bis `bis` (bis `jetzt_utc`):
    Station wählen, aufgehobene Vorhersage durch die Bewertung rechnen, jedes
    Modell einzeln vergleichen. Rückgabe (Zeile für den Rückblick, Stunden der
    Bewertung) — die Stunden sind None, wenn es nichts zu vergleichen gab.
    Seit 1.16.0 eine eigene Funktion, weil das Session-Tagebuch dieselbe
    Rechnung für einen einzelnen Tag braucht."""
    from .sources import stationen, historisch
    from .sources.highres import kandidaten, kurzname
    from .score import score_hours
    zeile = {"id": spot["id"], "name": spot["name"], "rang": rang,
             "country": spot.get("country") or "", "station": None, "stunden": [], "masse": None}
    # `grund` und `abdeckung` sind Anzeigetext — in der Sprache des Laufs,
    # gemerkt bis zum nächsten „Prüfen“ (cache/rueckblick.json).
    if not paar:
        zeile["grund"] = T("keine Messstation in {km} km — die Dienste decken Deutschland, die "
                           "Niederlande, Österreich, Dänemark und Frankreich ab, dazu Windguru-Stationen aus der "
                           "Konfiguration; über Grenzen hinweg wird gesucht", km=f"{max_km:.0f}")
        return zeile, None
    say(f"{spot['name']}: {paar['quelle']} {paar['station'].get('name', paar['station']['id'])} ({paar['km']} km)")
    # Die Stationen im Umkreis der Entfernung nach; die nächste, die fast
    # alle Stunden bis jetzt hat, gewinnt (`station_waehlen`). Hat eine
    # für diese Tage nichts (KNMI kommt zwei Tage später) oder antwortet
    # sie nicht, kommt die nächste dran. Was die erste sagte, bleibt für
    # die Meldung.
    obs, erste, fehler = None, None, None
    from .geo import haversine_km
    moeglich = moegliche_stunden(von, jetzt_utc)
    versuche = []
    for station in [paar["station"]] + list(paar.get("ersatz") or []):
        try:
            versuch = stationen.stunden_fuer(dict(paar, station=station), von, bis)
        except Exception as exc:                    # noqa: BLE001
            fehler = exc
            continue
        if erste is None:
            erste = versuch
        st_v = versuch.get("station") or station
        km_v = round(haversine_km(spot["lat"], spot["lon"], st_v["lat"], st_v["lon"]), 1)
        n = gedeckt(versuch.get("stunden") or {}, von, jetzt_utc)
        versuche.append((st_v, versuch, km_v, n))
        if not n:
            if versuch.get("hinweis"):
                say("    " + T("{quelle} {station}: keine Werte für diese Tage ({hinweis})", quelle=versuch["quelle"],
                              station=station.get("name", station["id"]), hinweis=versuch["hinweis"]))
            else:
                say("    " + T("{quelle} {station}: keine Werte für diese Tage", quelle=versuch["quelle"],
                              station=station.get("name", station["id"])))
            continue
        if moeglich and n >= GUT_GENUG * moeglich:
            break                                   # näher geht es nicht, besser kaum
        say("    " + T("{quelle} {station}: {n} von {moeglich} Stunden bis jetzt — die nächste Station wird auch gefragt",
                      quelle=versuch["quelle"], station=station.get("name", station["id"]), n=n, moeglich=moeglich))
    wahl = station_waehlen(versuche, moeglich)
    statt = None
    if wahl is not None:
        obs = versuche[wahl][1]
        # Eine nähere Station mit Werten, die übergangen wurde, steht dabei
        vorher = next((v for v in versuche[:wahl] if v[3] > 0), None)
        if vorher:
            statt = {"name": vorher[0].get("name", vorher[0]["id"]), "quelle": vorher[1]["quelle"],
                     "km": vorher[2], "stunden": vorher[3]}
    if obs is None and erste is None:
        zeile["grund"] = T("Messwerte nicht abrufbar ({fehler})", fehler=fehler)
        return zeile, None
    if obs is None:
        st = erste["station"]
        km = round(haversine_km(spot["lat"], spot["lon"], st["lat"], st["lon"]), 1)
        zeile["station"] = {"id": st["id"], "name": st.get("name", ""), "quelle": erste["quelle"], "km": km}
        if erste.get("hinweis"):
            zeile["grund"] = T("die Station hat für diese Tage noch keine Werte veröffentlicht — {hinweis}; "
                               "auch keine andere in {km} km", hinweis=erste["hinweis"], km=f"{max_km:.0f}")
        else:
            zeile["grund"] = T("die Station hat für diese Tage noch keine Werte veröffentlicht; "
                               "auch keine andere in {km} km", km=f"{max_km:.0f}")
        return zeile, None
    st = obs["station"]
    km = round(haversine_km(spot["lat"], spot["lon"], st["lat"], st["lon"]), 1)
    zeile["station"] = {"id": st["id"], "name": st.get("name", ""), "quelle": obs["quelle"], "km": km,
                        "stunden": gedeckt(obs["stunden"], von, jetzt_utc), "moeglich": moeglich}
    if statt:
        zeile["station"]["statt"] = statt
        say("    " + T("genommen: {quelle} {station} ({km} km, {n} von {moeglich} Stunden) statt "
                      "{quelle2} {station2} ({km2} km, {n2} Stunden)",
                      quelle=obs["quelle"], station=st.get("name", st["id"]), km=km,
                      n=zeile["station"]["stunden"], moeglich=moeglich,
                      quelle2=statt["quelle"], station2=statt["name"], km2=statt["km"], n2=statt["stunden"]))
    zeile["messung_bis"] = max(obs["stunden"])          # UTC-Stunde des letzten Messwerts
    tz = zeitzone(spot)
    try:
        fc = historisch.hole_bis_heute(spot, von, bis, models, tz)
    except Exception as exc:                        # noqa: BLE001
        zeile["grund"] = T("aufgehobene Vorhersage nicht abrufbar ({fehler})", fehler=exc)
        return zeile, None
    liste = kandidaten(spot)
    if liste:
        try:
            fein = historisch.hole_regional_bis_heute(spot, liste[0], von, bis, tz)
            if fein and fein.get("hourly"):
                fc["_highres"] = (liste[0], fein["hourly"])
                zeile["modell"] = kurzname(liste[0])
        except Exception:                           # noqa: BLE001 — dann eben ohne
            pass
    eintrag_geo = geometry.get(spot["id"]) or {}
    rose = None if eintrag_geo.get("wasser") is False else eintrag_geo.get("rose_m")
    rows = score_hours(spot, fc, cfg, rose=rose)
    messung = {t: (v["kn"], v.get("dir")) for t, v in obs["stunden"].items()}
    offset = int(fc.get("utc_offset_seconds") or 0)
    vorhersage = {_utc_stunde(r["t"], offset): (float(r["wind"]), (float(r["dir"]) if r["dir"] is not None else None))
                  for r in rows if _utc_stunde(r["t"], offset) <= jetzt_utc}
    tageslicht = {_utc_stunde(r["t"], offset) for r in rows if 8 <= r["t"].hour < 20}
    zeile["masse"] = masse(vorhersage, messung, tageslicht)
    zeile["stunden"] = _stundenreihe(rows, fc, obs["stunden"], jetzt_utc)
    zeile["abdeckung"] = abdeckung(zeile["stunden"])
    # Jedes Modell einzeln gegen dieselbe Messung (seit 1.14.0)
    reihen = modellvergleich.modellreihen(spot, von, bis, tz, globale=(cfg.get("rueckblick") or {}).get("modelle"),
                                          log=say)
    zeile["vergleich"] = modellvergleich.vergleiche(reihen, vorhersage, messung, tageslicht, jetzt_utc)
    zeile["modellnamen"] = {r["id"]: r["name"] for r in reihen}
    for h in zeile["stunden"]:
        utc = _utc_stunde(datetime.fromisoformat(h["t"]), offset)
        h["mv"] = {r["id"]: round(r["reihe"][utc][0], 1) for r in reihen if utc in r["reihe"]}
    return zeile, rows


def mit_gedaechtnis(ergebnis: dict, pfad: Path | None = None) -> dict:
    """Die Tagessummen dieses Rückblicks ins Gedächtnis (`modellguete.json`)
    und die Rangliste über alle bisherigen Prüfungen ans Ergebnis."""
    try:
        daten = modellvergleich.merken(ergebnis, pfad)
        ergebnis["gedaechtnis"] = modellvergleich.auswerten(daten)
    except OSError as exc:
        ergebnis["gedaechtnis"] = {"fehler": T("Gedächtnis nicht schreibbar ({fehler})", fehler=exc)}
        return ergebnis
    # „Bisher bestes Modell“ je Spot — zum Zuschalten im Diagramm
    for zeile in ergebnis.get("spots") or []:
        bb = modellvergleich.bisher_bestes(zeile, ergebnis["gedaechtnis"])
        if bb:
            zeile["bisher_bestes"] = bb
    return ergebnis


def veraltet(ergebnis: dict | None, lauf: dict | None, version: str) -> str:
    """Warum ein gespeicherter Rückblick nicht mehr das ist, was man sieht —
    als Satz, oder leer. Am 20.09. stand auf der Seite noch „für FR ist kein
    Messdienst angebunden“: das Ergebnis war vom 18.09., gerechnet mit 1.9.0,
    während 1.10.0 längst Frankreich kannte — und nichts sagte es."""
    if not ergebnis:
        return ""
    gruende = []
    zeit = str(ergebnis.get("zeit") or "")
    suche = str((lauf or {}).get("zeit") or "")
    if suche and zeit and suche > zeit:
        gruende.append(T("die letzte Suche ({suche}) ist neuer als dieser Rückblick ({zeit}) — "
                         "die Ziele können andere sein", suche=suche.replace("T", " "), zeit=zeit.replace("T", " ")))
    alt = str(ergebnis.get("version") or T("vor 1.10.0"))
    if alt != version:
        gruende.append(T("er wurde mit Version {alt} gerechnet, das Programm ist jetzt {version}",
                         alt=alt, version=version))
    if not gruende:
        return ""
    return T("Dieses Ergebnis ist überholt: {gruende}. „Prüfen“ rechnet neu.", gruende="; ".join(gruende))


def speichern(ergebnis: dict, pfad: Path | None = None) -> None:
    from .spotedit import schreibe_atomar
    pfad = pfad or ERGEBNIS
    pfad.parent.mkdir(parents=True, exist_ok=True)
    schreibe_atomar(pfad, json.dumps(ergebnis, ensure_ascii=False))


def laden(pfad: Path | None = None) -> dict | None:
    pfad = pfad or ERGEBNIS
    if not pfad.exists():
        return None
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except ValueError:
        return None
