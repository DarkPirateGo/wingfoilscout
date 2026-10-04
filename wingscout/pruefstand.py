"""Der Prüfstand — misst, ob Wingfoilscout noch rechnet, was es rechnen soll.

Die Tests in `tests/` prüfen ohne Netz, ob der Code tut, was er tun soll. Der
Prüfstand prüft mit Netz, ob das Ganze noch stimmt: ob die Wetterdienste noch
antworten, wie sie sollen, ob die Bewertung an Spots mit bekanntem Wind das
Bekannte zeigt, ob ein Pin an Land als Pin an Land erkannt wird — und ob die
Vorhersage an Tagen mit Messwerten so nah an der Messung liegt wie beim letzten
Mal. Das Letzte ist der eigentliche Zweck: eine Zahl je Spot, die sich nach
einer Änderung am Code nicht unbemerkt verschlechtern darf.

Vier Teile, jeder für sich abschaltbar (`tools/pruefstand.py --nur …`):

  referenz      Spots, an denen der Wind bekannt ist (Ora, Malojawind, Breva)
                — alle Modelle holen, Form der Antwort prüfen, Thermik-
                signatur je Modell zeigen, Regionalmodell-Abdeckung prüfen.
  land          Ein Punkt, der sicher an Land liegt (Schwäbische Alb): die
                Ufergeometrie muss ihn als unbrauchbar melden, der
                Koordinaten-Check als „an Land“, und die Bewertung darf seine
                Rose nicht benutzen. Dazu dieselbe Prüfung ohne Netz an einem
                synthetischen Auszug.
  vergangenheit Zehn Spots mit einer Wetterstation in Reichweite: die
                aufgehobene Vorhersage eines festen Zeitraums gegen die
                Messung. Fehler, Richtungstreffer und die Frage „fahrbar?“
                je Modell und für Wingfoilscout als Ganzes — und der Vergleich
                mit der gemerkten Grundlinie.
  grundlinie    `pruefstand/grundlinie.json` — die Zahlen des Laufs, der als
                Maßstab gilt. Wird nur auf Aufruf gesetzt.

Kein Test im Sinne von `unittest`: das Ergebnis ist ein Bericht mit drei
Stufen (ok, warnung, fehler) und einem Rückgabewert fürs Terminal.
"""
from __future__ import annotations
import json
import math
import statistics
from datetime import datetime, timedelta
from pathlib import Path

from . import CACHE, ROOT
from .models import CORE, DEFAULT_MODELS, normalize
from .spots import zeitzone
from . import thermik

Befund = tuple  # ("ok" | "warnung" | "fehler", Text)

# Spots mit bekanntem Wind und dem Regionalmodell, das dort antworten muss.
# Die Erwartung an den Wind selbst steht im Katalog (`thermal:`), nicht hier —
# eine Zahl an zwei Stellen wäre eine zu viel.
REFERENZ = [
    ("torbole", "italia_meteo_arpae_icon_2i"),        # Ora aus Süd, 13–20 Uhr
    ("silvaplana", "meteoswiss_icon_ch1"),           # Malojawind aus Südwest
    ("domaso", "italia_meteo_arpae_icon_2i"),         # Breva aus Süd
    ("brouwersdam", "knmi_harmonie_arome_netherlands"),
    ("walchensee", "dwd_icon_d2"),
    ("fehmarn-gruener-brink", "dwd_icon_d2"),
    ("naxos-agios-georgios", None),                   # Ortszeit: Athen, nicht Berlin
]

# Ein Punkt, der sicher an Land liegt: Münsinger Alb, Karst, kein Gewässer in
# drei Kilometern, die Donau fünfzehn Kilometer entfernt.
LAND_PUNKT = (48.42, 9.55)

SCHWELLE_KN = 12.0             # ab hier gilt eine Stunde als fahrbar (fest, nicht aus der config)
STATION_MAX_KM = 12.0          # weiter darf eine Station nicht vom Spot liegen
GRUNDLINIE = ROOT / "pruefstand" / "grundlinie.json"
LETZTER_LAUF = CACHE / "pruefstand" / "letzter_lauf.json"
ZEITRAUM = ("2026-08-01", "2026-08-31")     # fest: dieselben Tage bei jedem Lauf


# ── Hilfen ───────────────────────────────────────────────────────────────────

def _winkel(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def _mittel(werte) -> float | None:
    werte = list(werte)
    return round(statistics.fmean(werte), 2) if werte else None


def zusammenfassung(befunde: list) -> tuple[int, int, int]:
    """(ok, warnung, fehler)"""
    return (sum(1 for s, _ in befunde if s == "ok"), sum(1 for s, _ in befunde if s == "warnung"),
            sum(1 for s, _ in befunde if s == "fehler"))


# ── 1. Form der Antwort ──────────────────────────────────────────────────────

def pruefe_format(spot: dict, fc: dict, cfg) -> list:
    """Sieht die Antwort so aus, wie der Code sie liest?

    Hier steht alles, was bisher still schiefging: Felder mit Modellsuffix,
    Sonnenzeiten, Einstrahlung. Ein geändertes Namensschema bei Open-Meteo
    fällt hier auf, bevor es im Report auffällt.
    """
    aus = []
    models = cfg.get("wind", {}).get("models") or DEFAULT_MODELS
    primary = cfg.get("wind", {}).get("primary_model") or models[0]
    name = spot["name"]
    hourly = fc.get("hourly") or {}
    zeiten = hourly.get("time") or []
    if len(zeiten) < 24:
        aus.append(("fehler", f"{name}: nur {len(zeiten)} Stunden in der Antwort"))
        return aus
    h = normalize(hourly, models, primary)
    for feld in CORE:
        werte = [v for v in (h.get(feld) or []) if v is not None]
        if not werte:
            aus.append(("fehler", f"{name}: Feld `{feld}` fehlt oder ist leer — Namensschema geändert?"))
    if any(s == "fehler" for s, _ in aus):
        return aus
    aus.append(("ok", f"{name}: alle {len(CORE)} Felder da, {len(zeiten)} Stunden, "
                      f"Modelle {', '.join(sorted(h.get('wind_models') or {}))}"))

    winde = [v for v in h["wind_speed_10m"] if v is not None]
    richtungen = [v for v in h["wind_direction_10m"] if v is not None]
    if winde and not (0 <= min(winde) and max(winde) <= 80):
        aus.append(("fehler", f"{name}: Wind außerhalb 0–80 kn ({min(winde)}–{max(winde)}) — Einheit?"))
    if richtungen and not (0 <= min(richtungen) and max(richtungen) <= 360):
        aus.append(("fehler", f"{name}: Richtung außerhalb 0–360°"))
    paare = [(w, g) for w, g in zip(h["wind_speed_10m"], h["wind_gusts_10m"])
             if w is not None and g is not None]
    if paare:
        anteil = sum(1 for w, g in paare if g >= w - 0.5) / len(paare)
        if anteil < 0.95:
            aus.append(("warnung", f"{name}: Böe unter Mittelwind in {100 - anteil * 100:.0f} % der Stunden"))
    temps = [v for v in h["temperature_2m"] if v is not None]
    if temps and not (-40 <= min(temps) and max(temps) <= 50):
        aus.append(("fehler", f"{name}: Temperatur außerhalb −40–50 °C"))

    # Einstrahlung: nachts null, mittags nicht — sonst ist das Feld verschoben
    nachts, mittags = [], []
    for t, r in zip(zeiten, h["shortwave_radiation"]):
        if r is None:
            continue
        stunde = int(t[11:13])
        if 0 <= stunde <= 3:
            nachts.append(r)
        elif 11 <= stunde <= 14:
            mittags.append(r)
    if nachts and max(nachts) > 5:
        aus.append(("fehler", f"{name}: Einstrahlung nachts {max(nachts):.0f} W/m² — Zeitzone oder Feld verschoben?"))
    if mittags and max(mittags) < 20:
        aus.append(("warnung", f"{name}: Einstrahlung mittags nie über 20 W/m² — echt (Dauerregen) oder Feld leer?"))
    else:
        aus.append(("ok", f"{name}: Einstrahlung nachts {max(nachts or [0]):.0f}, mittags bis {max(mittags or [0]):.0f} W/m²"))

    # Sonnenzeiten: aus der Antwort, und die eigene Rechnung daneben
    from .score import _sonnenzeiten
    tage = sorted({t[:10] for t in zeiten})
    fenster = _sonnenzeiten(spot, fc, tage)
    if len(fenster) < len(tage):
        aus.append(("fehler", f"{name}: Sonnenzeiten für {len(tage) - len(fenster)} von {len(tage)} Tagen fehlen"))
    else:
        aus.append(("ok", f"{name}: Sonnenzeiten für alle {len(tage)} Tage"))
    daily = fc.get("daily") or {}
    auf = next((v for k, v in daily.items() if k.startswith("sunrise")), None)
    offset = fc.get("utc_offset_seconds")
    if auf and offset is not None:
        from . import sonne as sonnen_modul
        try:
            api = datetime.fromisoformat(auf[0])
            eigen = sonnen_modul.zeiten_lokal(float(spot["lat"]), float(spot["lon"]),
                                              datetime.fromisoformat(tage[0]).date(), int(offset))[0]
            ab = abs((api - eigen).total_seconds()) / 60.0
            aus.append(("ok" if ab <= 15 else "fehler",
                        f"{name}: Sonnenaufgang laut Antwort {api.strftime('%H:%M')}, eigene Rechnung "
                        f"{eigen.strftime('%H:%M')} ({ab:.0f} min)"))
        except (ValueError, TypeError, IndexError):
            aus.append(("warnung", f"{name}: Sonnenaufgang nicht vergleichbar"))

    # Zeitzone: die Antwort muss die Zone des Landes tragen
    erwartet = zeitzone(spot)
    try:
        from zoneinfo import ZoneInfo
        soll = int(datetime.fromisoformat(zeiten[12]).replace(tzinfo=ZoneInfo(erwartet)).utcoffset().total_seconds())
        if offset is None:
            aus.append(("warnung", f"{name}: kein utc_offset_seconds in der Antwort"))
        elif int(offset) != soll:
            aus.append(("fehler", f"{name}: Zeitversatz {offset} s, für {erwartet} wären es {soll} s"))
        else:
            aus.append(("ok", f"{name}: Ortszeit {erwartet} ({int(offset) // 3600:+d} h)"))
    except Exception:                                   # noqa: BLE001 — zoneinfo ohne Datenbank
        aus.append(("warnung", f"{name}: Zeitzone nicht prüfbar (keine Zonendatenbank)"))
    return aus


def pruefe_bewertung(spot: dict, rows: list, cfg) -> list:
    """Die Stundenbewertung auf einer echten Antwort: keine Nacht, alles 0–1."""
    aus = []
    name = spot["name"]
    if not rows:
        return [("fehler", f"{name}: score_hours liefert keine Stunden")]
    if any(not (0.0 <= r["score"] <= 1.0) for r in rows):
        aus.append(("fehler", f"{name}: Score außerhalb 0–1"))
    nacht = [r for r in rows if r["score"] > 0 and (r["t"].hour >= 23 or r["t"].hour <= 3)]
    if nacht:
        aus.append(("fehler", f"{name}: {len(nacht)} Nachtstunden (23–3 Uhr) mit Score > 0 — Tageslichtprüfung tot?"))
    else:
        aus.append(("ok", f"{name}: keine Nachtstunde fahrbar"))
    return aus


# ── 2. Thermiksignatur ───────────────────────────────────────────────────────

def thermik_signatur(spot: dict, fc: dict, rows: list, models: list) -> dict:
    """Sieht ein Modell die Thermik, die im Katalog steht?

    Je Modell: an wie vielen Tagen zeigt es im Thermikfenster die hinterlegte
    Richtung (±45°) mit mindestens 8 kn in der Mehrheit der Stunden? Dazu
    Wingfoilscout als Ganzes (Modell plus Annahme). Sonnige Tage zählen — die
    Thermik lebt von der Einstrahlung; ein Regentag beweist nichts.
    """
    th = spot.get("thermal") or {}
    if not th or th.get("dir") is None:
        return {}
    von, bis = float(th.get("from", 12)), float(th.get("to", 18))
    hourly = fc.get("hourly") or {}
    zeiten = hourly.get("time") or []
    tage = sorted({t[:10] for t in zeiten})

    def serie(feld, modell=None):
        key = f"{feld}_{modell}" if modell else feld
        werte = hourly.get(key)
        if werte is None and modell is None:
            werte = next((v for k, v in hourly.items() if k.startswith(feld + "_")), None)
        return werte or []

    # Ein Tag taugt für die Thermik, wenn die Sonne da ist (Energie bis 15 Uhr
    # über 70 % eines vollen Vormittags) UND der Gradientwind sie nicht
    # erstickt: im Fenster im Mittel unter 9 kn (thermik.BRICHT_AB), und nicht
    # aus einer Richtung, die der Katalog als tödlich führt. Sonst zählte ein
    # Nordföhntag als Fehlschlag der Ora — und der Ora fehlt an dem Tag nichts.
    strahlung = serie("shortwave_radiation")
    energie = {}
    for t, r in zip(zeiten, strahlung):
        if r is not None and int(t[11:13]) < 15:
            energie[t[:10]] = energie.get(t[:10], 0.0) + float(r)
    grob_speed, grob_dir = serie("wind_speed_10m", models[0]), serie("wind_direction_10m", models[0])
    erstickt_ab = th.get("suppressed_by") or []
    sonnig = []
    for tag in tage:
        if energie.get(tag, 0.0) < 0.7 * thermik.VOLLE_ENERGIE_WH:
            continue
        im_fenster = [(w, d) for t, w, d in zip(zeiten, grob_speed, grob_dir)
                      if t[:10] == tag and w is not None and von <= int(t[11:13]) < bis]
        if not im_fenster:
            continue
        mittel = sum(w for w, _ in im_fenster) / len(im_fenster)
        toedlich = any(w >= 6 and d is not None and any(_winkel(float(d), float(r)) <= 45 for r in erstickt_ab)
                       for w, d in im_fenster)
        if mittel < thermik.BRICHT_AB and not toedlich:
            sonnig.append(tag)

    from .models import short
    ergebnis = {"tage": len(tage), "sonnig": len(sonnig), "modelle": {}}
    kandidaten = {short(m): (serie("wind_speed_10m", m), serie("wind_direction_10m", m)) for m in models}
    fein = fc.get("_highres")
    if fein:
        from .sources.highres import kurzname
        kandidaten[kurzname(fein[0])] = (fein[1].get("wind_speed_10m") or [], fein[1].get("wind_direction_10m") or [])
        fein_zeiten = fein[1].get("time") or []
    for kurz, (speeds, dirs) in kandidaten.items():
        zt = fein_zeiten if (fein and kurz == kurzname(fein[0])) else zeiten
        treffer_tage = 0
        for tag in sonnig:
            drin, passt = 0, 0
            for t, w, d in zip(zt, speeds, dirs):
                if t[:10] != tag or w is None or d is None:
                    continue
                stunde = int(t[11:13])
                if von <= stunde < bis:
                    drin += 1
                    if w >= 8 and _winkel(float(d), float(th["dir"])) <= 45:
                        passt += 1
            if drin and passt / drin >= 0.5:
                treffer_tage += 1
        if any(v is not None for v in speeds):
            ergebnis["modelle"][kurz] = treffer_tage
    # Wingfoilscout als Ganzes: Modell plus Annahme
    treffer = 0
    for tag in sonnig:
        drin = [r for r in rows if r["day"] == tag and von <= r["t"].hour < bis]
        passt = [r for r in drin if r["wind"] >= 8 and r["dir"] is not None
                 and _winkel(float(r["dir"]), float(th["dir"])) <= 45]
        if drin and len(passt) / len(drin) >= 0.5:
            treffer += 1
    ergebnis["wingscout"] = treffer
    ergebnis["angenommen"] = sum(1 for r in rows if r.get("thermal"))
    return ergebnis


def pruefe_thermik(spot: dict, fc: dict, rows: list, models: list, monat: int) -> list:
    th = spot.get("thermal") or {}
    if not th or not th.get("typical_kn") or th.get("dir") is None:
        return []
    name, wind = spot["name"], th.get("name", "Thermik")
    sig = thermik_signatur(spot, fc, rows, models)
    if not sig:
        return []
    if not thermik.gilt_heute(th, monat):
        if sig["angenommen"]:
            return [("fehler", f"{name}: {wind} außerhalb der Saison angenommen ({sig['angenommen']} Stunden)")]
        return [("ok", f"{name}: {wind} hat im Monat {monat} keine Saison — nichts angenommen")]
    zeile = ", ".join(f"{k} {v}/{sig['sonnig']}" for k, v in sorted(sig["modelle"].items()))
    text = (f"{name}: {wind} an tauglichen Tagen (sonnig, schwacher Gradient) — Modelle: {zeile or 'keine'}; "
            f"Wingfoilscout {sig['wingscout']}/{sig['sonnig']} (Annahme in {sig['angenommen']} Stunden)")
    if not sig["sonnig"]:
        return [("ok", f"{name}: kein tauglicher Tag im Zeitraum (Sonne und schwacher Gradient) — {wind} nicht prüfbar")]
    if sig["wingscout"] < sig["sonnig"]:
        # Nicht jeder sonnige Tag hat Thermik — ein starker Gradient von der
        # falschen Seite erstickt sie. Ein Tag Abstand ist erlaubt.
        stufe = "warnung" if sig["wingscout"] >= sig["sonnig"] - 1 else "fehler"
        return [(stufe, text)]
    return [("ok", text)]


def referenz_lauf(cfg, spots: list, geometry: dict, tage: int = 3, log=None) -> tuple[list, list]:
    """Die Referenzspots mit der laufenden Vorhersage: Form, Bewertung, Thermik, Regionalmodell.

    Rückgabe: (Befunde, Tabellenzeilen zur Thermiksignatur).
    """
    from .sources.openmeteo import fetch, ForecastError
    from .sources.highres import hole as hole_fein, kurzname
    from .score import score_hours
    say = log or (lambda *a: None)
    by_id = {s["id"]: s for s in spots}
    refs = [(by_id[sid], modell) for sid, modell in REFERENZ if sid in by_id]
    fehlend = [sid for sid, _ in REFERENZ if sid not in by_id]
    befunde = [("warnung", f"Referenzspot {sid} nicht im Katalog") for sid in fehlend]
    if not refs:
        return befunde, []
    models = cfg.get("wind", {}).get("models") or DEFAULT_MODELS
    try:
        forecasts = fetch([s for s, _ in refs], tage, models=models, log=say)
    except ForecastError as exc:
        return befunde + [("warnung", f"Open-Meteo nicht erreichbar: {exc} — Referenz nicht prüfbar")], []
    try:
        fein, _stat = hole_fein([s for s, _ in refs if s["id"] in forecasts], tage, CACHE, log=say)
    except Exception as exc:                            # noqa: BLE001
        befunde.append(("warnung", f"Regionalmodelle nicht abrufbar ({exc})"))
        fein = {}
    monat = datetime.now().month
    tabelle = []
    for spot, erwartet in refs:
        fc = forecasts.get(spot["id"])
        if not fc:
            befunde.append(("fehler", f"{spot['name']}: keine Vorhersage in der Antwort"))
            continue
        if spot["id"] in fein:
            fc["_highres"] = fein[spot["id"]]
        befunde.extend(pruefe_format(spot, fc, cfg))
        if any(s == "fehler" and spot["name"] in t for s, t in befunde):
            continue
        rose = (geometry.get(spot["id"]) or {}).get("rose_m")
        rows = score_hours(spot, fc, cfg, rose=rose)
        befunde.extend(pruefe_bewertung(spot, rows, cfg))
        befunde.extend(pruefe_thermik(spot, fc, rows, models, monat))
        if erwartet:
            geliefert = fein.get(spot["id"], (None,))[0]
            if geliefert == erwartet:
                stunden = sum(1 for r in rows if r.get("modell"))
                befunde.append(("ok", f"{spot['name']}: Regionalmodell {kurzname(erwartet)} deckt {stunden} Stunden"))
            elif geliefert:
                befunde.append(("warnung", f"{spot['name']}: Regionalmodell {kurzname(geliefert)} statt "
                                           f"{kurzname(erwartet)} — Zuordnung geändert?"))
            else:
                befunde.append(("warnung", f"{spot['name']}: kein Regionalmodell geantwortet, erwartet {kurzname(erwartet)}"))
        sig = thermik_signatur(spot, fc, rows, models)
        if sig:
            tabelle.append({"spot": spot["name"], **sig})
    return befunde, tabelle


def tabelle_thermik(zeilen: list) -> str:
    if not zeilen:
        return ""
    modelle = sorted({m for z in zeilen for m in z["modelle"]})
    kopf = f"{'Thermikspot':28s} {'taugl./Tage':>11s} " + " ".join(f"{m:>8s}" for m in modelle) + f" {'Wingfoilscout':>9s}"
    out = [kopf, "-" * len(kopf)]
    for z in zeilen:
        out.append(f"{z['spot'][:28]:28s} {str(z['sonnig']) + '/' + str(z['tage']):>11s} "
                   + " ".join(f"{z['modelle'].get(m, '–'):>8}" for m in modelle)
                   + f" {z['wingscout']:>9}")
    out.append("(je Modell: an wie vielen tauglichen Tagen — sonnig, schwacher Gradient — es die "
               "hinterlegte Thermikrichtung im Fenster zeigt)")
    return "\n".join(out)


# ── 3. Land ──────────────────────────────────────────────────────────────────

def _synthetischer_auszug(lat: float, lon: float, abstand_m: float = 10000.0) -> dict:
    """Ein See von 4 × 4 km, `abstand_m` östlich des Punkts — sonst nichts."""
    m_lat = 111320.0
    m_lon = 111320.0 * math.cos(math.radians(lat))

    def pt(x, y):
        return {"lat": lat + y / m_lat, "lon": lon + x / m_lon}
    x0, x1 = abstand_m, abstand_m + 4000.0
    ring = [pt(x0, -2000), pt(x1, -2000), pt(x1, 2000), pt(x0, 2000), pt(x0, -2000)]
    return {"elements": [{"type": "way", "id": 1, "tags": {"natural": "water", "name": "Fernsee"},
                          "geometry": ring}]}


def land_pruefung(raw: dict, spot: dict, cfg) -> tuple[list, dict]:
    """Ein Auszug, ein Punkt an Land: Geometrie, Befund, Koordinaten-Check, Bewertung."""
    from .shoreline import rechne, befund
    aus = []
    gcfg = cfg.get("geometry", {})
    eintrag = rechne(raw, spot, float(gcfg.get("max_fetch_km", 25.0)), int(gcfg.get("ray_count", 36)))
    if eintrag.get("wasser") is False:
        aus.append(("ok", f"Geometrie: {eintrag['status']}"))
    else:
        aus.append(("fehler", f"Geometrie hält den Landpunkt für Wasser: {eintrag['status']} "
                              f"(Anlauf max {eintrag['max_fetch_km']} km)"))
    b = befund(eintrag)
    if b and b[0] == "unbrauchbar":
        aus.append(("ok", f"Prüfseite: unbrauchbar — {b[1]}"))
    else:
        aus.append(("fehler", f"Prüfseite würde den Landpunkt nicht melden ({b})"))
    # Bewertung: die Rose darf nicht benutzt werden
    from .score import score_hours
    n = 24
    fc = {"utc_offset_seconds": 7200,
          "hourly": {"time": [f"2026-07-15T{k:02d}:00" for k in range(n)],
                     "wind_speed_10m": [18.0] * n, "wind_gusts_10m": [21.0] * n,
                     "wind_direction_10m": [270.0] * n, "temperature_2m": [22.0] * n,
                     "precipitation": [0.0] * n, "cape": [0.0] * n, "weather_code": [1] * n,
                     "cloud_cover": [10.0] * n, "shortwave_radiation": [300.0] * n},
          "daily": {"time": ["2026-07-15"], "sunrise": ["2026-07-15T05:30"], "sunset": ["2026-07-15T21:15"]}}
    rose = None if eintrag.get("wasser") is False else eintrag["rose_m"]
    rows = score_hours(dict(spot, sectors=[]), fc, cfg, rose=rose)
    quellen = {r.get("source") for r in rows if r.get("source")}
    if "geometrie" in quellen:
        aus.append(("fehler", "Bewertung benutzt die Rose des Landpunkts"))
    else:
        aus.append(("ok", f"Bewertung ohne Rose ({', '.join(sorted(quellen)) or 'neutral'})"))
    return aus, eintrag


def land_offline(cfg) -> list:
    spot = {"id": "pruefstand-land", "name": "Prüfstand: Land", "lat": LAND_PUNKT[0], "lon": LAND_PUNKT[1]}
    aus, _ = land_pruefung(_synthetischer_auszug(*LAND_PUNKT), spot, cfg)
    return [(s, "ohne Netz · " + t) for s, t in aus]


def land_online(cfg, lat: float, lon: float, log=None) -> list:
    """Derselbe Weg mit einem echten OpenStreetMap-Auszug — und dem Koordinaten-Check."""
    from .sources.overpass import fetch_water
    spot = {"id": "pruefstand-land", "name": "Prüfstand: Land", "lat": lat, "lon": lon}
    cache = CACHE / "pruefstand" / "geom"
    try:
        gcfg = cfg.get("geometry", {})
        raw = fetch_water(spot["id"], lat, lon, float(gcfg.get("max_fetch_km", 25.0)),
                          cache_dir=cache, log=log)
    except Exception as exc:                            # noqa: BLE001
        return [("warnung", f"Overpass nicht erreichbar ({exc}) — Landprüfung nur ohne Netz")]
    aus, eintrag = land_pruefung(raw, spot, cfg)
    try:
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        from koordinaten_check import pruefe            # noqa: E402
        urteil = pruefe(spot, eintrag, cache)
        if urteil.get("gruppe") == "D":
            aus.append(("ok", f"Koordinaten-Check: Gruppe D — {urteil.get('grund')}"))
        else:
            aus.append(("fehler", f"Koordinaten-Check sagt Gruppe {urteil.get('gruppe')}: {urteil.get('grund')}"))
    except Exception as exc:                            # noqa: BLE001
        aus.append(("warnung", f"Koordinaten-Check nicht ausführbar ({exc})"))
    return [(s, f"{lat:.2f}, {lon:.2f} · " + t) for s, t in aus]


# ── 4. Vergangenheit ─────────────────────────────────────────────────────────

def masse(vorhersage: dict, messung: dict, tageslicht: set | None = None) -> dict:
    """Fehlermaße zwischen zwei Stundenreihen {UTC-Stunde: (kn, dir|None)}.

    bias      Vorhersage minus Messung im Mittel (kn) — negativ: zu wenig gesagt
    mae       mittlerer Betrag des Fehlers (kn)
    richtung  Anteil Stunden (Messung ≥ 8 kn) mit Richtungsfehler ≤ 45°
    fahrbar   die Frage, die zählt: Stunden über SCHWELLE_KN — Treffergenauigkeit
              (precision), Trefferquote (recall), F1; nur Stunden in `tageslicht`
    """
    gemeinsam = [t for t in vorhersage if t in messung and vorhersage[t][0] is not None
                 and messung[t][0] is not None]
    if not gemeinsam:
        return {"n": 0}
    diff = [vorhersage[t][0] - messung[t][0] for t in gemeinsam]
    aus = {"n": len(gemeinsam), "bias": _mittel(diff), "mae": _mittel(abs(d) for d in diff)}
    richt = [(vorhersage[t][1], messung[t][1]) for t in gemeinsam
             if messung[t][0] >= 8 and vorhersage[t][1] is not None and messung[t][1] is not None]
    aus["richtung_n"] = len(richt)
    aus["richtung"] = round(sum(1 for a, b in richt if _winkel(a, b) <= 45) / len(richt), 2) if richt else None
    tage = [t for t in gemeinsam if tageslicht is None or t in tageslicht]
    v_ja = {t for t in tage if vorhersage[t][0] >= SCHWELLE_KN}
    m_ja = {t for t in tage if messung[t][0] >= SCHWELLE_KN}
    tp = len(v_ja & m_ja)
    precision = tp / len(v_ja) if v_ja else None
    recall = tp / len(m_ja) if m_ja else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision is not None and recall is not None and (precision + recall) > 0 else None)
    aus.update({"fahrbar_n": len(tage), "gemessen_fahrbar": len(m_ja), "gesagt_fahrbar": len(v_ja),
                "precision": round(precision, 2) if precision is not None else None,
                "recall": round(recall, 2) if recall is not None else None,
                "f1": round(f1, 2) if f1 is not None else None})
    return aus


def _utc_stunde(t: datetime, offset_s: int) -> str:
    return (t - timedelta(seconds=offset_s)).strftime("%Y-%m-%dT%H:00")


def vergleich_paar(paar: dict, obs: dict, fc: dict, cfg, rose, models: list) -> dict:
    """Ein Spot gegen eine Station über den Zeitraum — alle Reihen."""
    from .score import score_hours
    spot = paar["spot"]
    rows = score_hours(spot, fc, cfg, rose=rose)
    offset = int(fc.get("utc_offset_seconds") or 0)
    messung = {t: (v["kn"], v.get("dir")) for t, v in obs["stunden"].items()}
    hourly = fc.get("hourly") or {}
    zeiten = hourly.get("time") or []

    def modell_reihe(modell):
        speeds = hourly.get(f"wind_speed_10m_{modell}") or hourly.get("wind_speed_10m") or []
        dirs = hourly.get(f"wind_direction_10m_{modell}") or hourly.get("wind_direction_10m") or []
        if len(dirs) < len(speeds):
            dirs = list(dirs) + [None] * (len(speeds) - len(dirs))
        out = {}
        for t, w, d in zip(zeiten, speeds, dirs):
            if w is None:
                continue
            out[_utc_stunde(datetime.fromisoformat(t), offset)] = (float(w), float(d) if d is not None else None)
        return out

    reihen = {}
    from .models import short
    for m in models:
        reihen[short(m)] = modell_reihe(m)
    fein = fc.get("_highres")
    if fein:
        from .sources.highres import kurzname
        fh = fein[1]
        out = {}
        for t, w, d in zip(fh.get("time") or [], fh.get("wind_speed_10m") or [], fh.get("wind_direction_10m") or []):
            if w is not None:
                out[_utc_stunde(datetime.fromisoformat(t), offset)] = (float(w), float(d) if d is not None else None)
        reihen[kurzname(fein[0])] = out
    reihen["Wingfoilscout"] = {_utc_stunde(r["t"], offset): (float(r["wind"]), (float(r["dir"]) if r["dir"] is not None else None))
                           for r in rows}
    tageslicht = {_utc_stunde(r["t"], offset) for r in rows if 8 <= r["t"].hour < 20}

    ergebnis = {"spot": spot["id"], "name": spot["name"], "quelle": obs["quelle"],
                "station": {"id": obs["station"]["id"], "name": obs["station"].get("name", "")},
                "km": paar["km"], "messstunden": len(messung), "reihen": {}}
    for kurz, reihe in reihen.items():
        ergebnis["reihen"][kurz] = masse(reihe, messung, tageslicht)
    # Sessions: sagt Wingfoilscout „fahrbar“ (Score über der Mindestgüte, kein Veto)?
    min_score = cfg["session"]["min_score"]
    v = {_utc_stunde(r["t"], offset): ((SCHWELLE_KN if (r["score"] >= min_score and not r["veto"]) else 0.0), None)
         for r in rows}
    ergebnis["sessions"] = masse(v, messung, tageslicht)
    return ergebnis


def paare_waehlen(paare: list, n: int) -> list:
    """Die nächsten n Paare, aber abwechselnd aus den Diensten — sonst stünde
    die Liste voller KNMI-Stationen, und Deutschland fehlte."""
    nach_quelle: dict[str, list] = {}
    for p in paare:
        nach_quelle.setdefault(p["quelle"], []).append(p)
    gesehen, aus = set(), []
    while len(aus) < n and any(nach_quelle.values()):
        for quelle in sorted(nach_quelle):
            liste = nach_quelle[quelle]
            while liste:
                p = liste.pop(0)
                if p["station"]["id"] in gesehen:
                    continue
                gesehen.add(p["station"]["id"])
                aus.append(p)
                break
            if len(aus) >= n:
                break
    return aus


def vergangenheit(cfg, spots: list, geometry: dict, von: str, bis: str, n_paare: int = 10,
                  paare_vorgabe: list | None = None, log=None, laender=None) -> dict:
    """Zehn Spots gegen ihre Stationen über den Zeitraum. Netz nötig, danach Cache."""
    from .sources import stationen, historisch
    from .sources.highres import kandidaten
    say = log or (lambda *a: None)
    models = cfg.get("wind", {}).get("models") or DEFAULT_MODELS
    by_id = {s["id"]: s for s in spots}
    if paare_vorgabe:
        paare = []
        for p in paare_vorgabe:
            spot = by_id.get(p["spot"])
            if spot:
                paare.append({"spot": spot, "quelle": p["quelle"], "station": p["station"], "km": p["km"]})
        say(f"    {len(paare)} Paare aus der Grundlinie")
    else:
        alle = stationen.paare_finden(spots, STATION_MAX_KM, log=say, laender=laender)
        paare = paare_waehlen(alle, n_paare)
        say(f"    {len(alle)} Spots mit Station in {STATION_MAX_KM:.0f} km, {len(paare)} gewählt")
    ergebnisse, befunde = [], []
    for paar in paare:
        spot = paar["spot"]
        kennung = f"{spot['name']} ↔ {paar['quelle']} {paar['station'].get('name', paar['station']['id'])}"
        obs, letzter_fehler = None, None
        for station in [paar["station"]] + list(paar.get("ersatz") or []):
            versuch = dict(paar, station=station)
            try:
                obs = stationen.stunden_fuer(versuch, von, bis)
                break
            except Exception as exc:                    # noqa: BLE001
                letzter_fehler = exc
                say(f"    {spot['name']}: {paar['quelle']} {station.get('name', station['id'])} liefert nichts ({exc}) — nächste Station")
        if obs is None:
            befunde.append(("warnung", f"{kennung}: Messwerte nicht abrufbar ({letzter_fehler})"))
            continue
        # Lage aus der Antwort: Abstand neu rechnen, zu weite Stationen verwerfen
        from .geo import haversine_km
        st = obs["station"]
        paar["km"] = round(haversine_km(spot["lat"], spot["lon"], st["lat"], st["lon"]), 1)
        paar["station"] = {"id": st["id"], "name": st.get("name", ""), "lat": st["lat"], "lon": st["lon"]}
        kennung = f"{spot['name']} ↔ {obs['quelle']} {paar['station'].get('name') or paar['station']['id']}"
        if paar["km"] > STATION_MAX_KM:
            befunde.append(("warnung", f"{kennung}: Station liegt {paar['km']} km entfernt — übersprungen"))
            continue
        if len(obs["stunden"]) < 24 * 10:
            befunde.append(("warnung", f"{kennung}: nur {len(obs['stunden'])} Messstunden"))
        tz = zeitzone(spot)
        try:
            fc = historisch.hole(spot, von, bis, models, tz)
        except Exception as exc:                        # noqa: BLE001
            befunde.append(("warnung", f"{kennung}: Vorhersage nicht abrufbar ({exc})"))
            continue
        liste = kandidaten(spot)
        if liste:
            try:
                fein = historisch.hole_regional(spot, liste[0], von, bis, tz)
                if fein and fein.get("hourly"):
                    fc["_highres"] = (liste[0], fein["hourly"])
            except Exception as exc:                    # noqa: BLE001
                befunde.append(("warnung", f"{kennung}: Regionalmodell nicht abrufbar ({exc})"))
        rose = (geometry.get(spot["id"]) or {}).get("rose_m")
        if (geometry.get(spot["id"]) or {}).get("wasser") is False:
            rose = None
        try:
            erg = vergleich_paar(paar, obs, fc, cfg, rose, models)
        except Exception as exc:                        # noqa: BLE001
            befunde.append(("fehler", f"{kennung}: Vergleich abgebrochen ({type(exc).__name__}: {exc})"))
            continue
        ergebnisse.append(erg)
        w = erg["reihen"].get("Wingfoilscout") or {}
        if w.get("n", 0) < 100:
            befunde.append(("warnung", f"{kennung}: nur {w.get('n', 0)} gemeinsame Stunden"))
            continue
        stufe = "ok"
        if w["mae"] is not None and w["mae"] > 8:
            stufe = "warnung"
        if w["bias"] is not None and abs(w["bias"]) > 6:
            stufe = "warnung"
        if w.get("richtung") is not None and w.get("richtung_n", 0) >= 20 and w["richtung"] < 0.5:
            stufe = "warnung"
        kennung = f"{spot['name']} ↔ {obs['quelle']} {paar['station'].get('name', paar['station']['id'])}"
        befunde.append((stufe, f"{kennung} ({paar['km']} km): Wingfoilscout MAE {w['mae']} kn, Bias {w['bias']:+} kn, "
                               f"Richtung {w['richtung'] if w['richtung'] is not None else '–'}, "
                               f"F1 Wind {w.get('f1')} / Urteil {erg['sessions'].get('f1')} "
                               f"bei {erg['sessions'].get('gemessen_fahrbar')} gemessenen Stunden ≥ {SCHWELLE_KN:.0f} kn"))
    geliefert = {e["spot"] for e in ergebnisse}
    return {"zeitraum": [von, bis], "schwelle_kn": SCHWELLE_KN,
            "paare": [{"spot": p["spot"]["id"], "quelle": p["quelle"], "station": p["station"], "km": p["km"]}
                      for p in paare if p["spot"]["id"] in geliefert],
            "ergebnisse": ergebnisse, "befunde": befunde}


# ── Grundlinie ───────────────────────────────────────────────────────────────

def grundlinie_lesen(pfad: Path = GRUNDLINIE) -> dict | None:
    if not pfad.exists():
        return None
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except ValueError:
        return None


def grundlinie_schreiben(vergangenheit_ergebnis: dict, version: str, pfad: Path = GRUNDLINIE) -> None:
    from .spotedit import schreibe_atomar
    pfad.parent.mkdir(parents=True, exist_ok=True)
    daten = {"version": version, "gesetzt": datetime.now().strftime("%Y-%m-%d %H:%M"),
             "zeitraum": vergangenheit_ergebnis["zeitraum"], "schwelle_kn": vergangenheit_ergebnis["schwelle_kn"],
             "paare": vergangenheit_ergebnis["paare"],
             "ergebnisse": {e["spot"]: {"reihen": e["reihen"], "sessions": e["sessions"],
                                       "station": e["station"], "quelle": e["quelle"], "km": e["km"]}
                            for e in vergangenheit_ergebnis["ergebnisse"]}}
    schreibe_atomar(pfad, json.dumps(daten, indent=1, ensure_ascii=False))


def vergleiche_grundlinie(grundlinie: dict, neu: dict, toleranz_mae: float = 1.0,
                          toleranz_f1: float = 0.10) -> list:
    """Schlechter als gemerkt? Je Spot die Wingfoilscout-Reihe und die Sessions."""
    aus = []
    if grundlinie.get("zeitraum") != neu.get("zeitraum"):
        aus.append(("warnung", f"Grundlinie gilt für {grundlinie.get('zeitraum')}, geprüft wurde {neu.get('zeitraum')} "
                               f"— nicht vergleichbar, Grundlinie neu setzen"))
        return aus
    alt = grundlinie.get("ergebnisse") or {}
    besser = 0
    for erg in neu.get("ergebnisse") or []:
        a = alt.get(erg["spot"])
        if not a:
            aus.append(("warnung", f"{erg['name']}: nicht in der Grundlinie"))
            continue
        w_alt, w_neu = (a.get("reihen") or {}).get("Wingfoilscout") or {}, erg["reihen"].get("Wingfoilscout") or {}
        s_alt, s_neu = a.get("sessions") or {}, erg.get("sessions") or {}
        if w_alt.get("mae") is None or w_neu.get("mae") is None:
            continue
        d_mae = round(w_neu["mae"] - w_alt["mae"], 2)
        # F1 auf dem Wind (≥ 12 kn beiderseits) — robust. Das Urteil-F1 zählt
        # nur, wo genug gemessene Stunden über der Schwelle liegen; sonst
        # entscheiden drei Stunden über eine ganze Kennzahl.
        d_f1 = (round(w_neu["f1"] - w_alt["f1"], 2)
                if w_alt.get("f1") is not None and w_neu.get("f1") is not None else 0.0)
        d_urteil = 0.0
        if (s_alt.get("f1") is not None and s_neu.get("f1") is not None
                and min(s_alt.get("gemessen_fahrbar", 0), s_neu.get("gemessen_fahrbar", 0)) >= 30):
            d_urteil = round(s_neu["f1"] - s_alt["f1"], 2)
        text = (f"MAE {w_alt['mae']} → {w_neu['mae']} kn, F1 Wind {w_alt.get('f1')} → {w_neu.get('f1')}, "
                f"F1 Urteil {s_alt.get('f1')} → {s_neu.get('f1')}")
        if d_mae > toleranz_mae or d_f1 < -toleranz_f1 or d_urteil < -toleranz_f1:
            aus.append(("fehler", f"{erg['name']}: schlechter als die Grundlinie — {text}"))
        elif d_mae < -toleranz_mae or d_f1 > toleranz_f1 or d_urteil > toleranz_f1:
            besser += 1
            aus.append(("ok", f"{erg['name']}: besser als die Grundlinie — {text}"))
        else:
            aus.append(("ok", f"{erg['name']}: wie die Grundlinie (MAE {w_neu['mae']} kn, F1 Wind {w_neu.get('f1')})"))
    fehlend = [sid for sid in alt if sid not in {e["spot"] for e in neu.get("ergebnisse") or []}]
    if fehlend:
        aus.append(("warnung", f"{len(fehlend)} Spots der Grundlinie ohne Ergebnis: {', '.join(fehlend[:5])}"))
    if besser:
        aus.append(("ok", f"{besser} Spots besser als gemerkt — wenn das gewollt war: --grundlinie-setzen"))
    return aus


# ── Bericht ──────────────────────────────────────────────────────────────────

ZEICHEN = {"ok": "✓", "warnung": "!", "fehler": "✗"}


def tabelle_vergangenheit(ergebnisse: list) -> str:
    if not ergebnisse:
        return ""
    reihen = sorted({k for e in ergebnisse for k in e["reihen"]} - {"Wingfoilscout"}) + ["Wingfoilscout"]
    kopf = (f"{'Spot':30s} {'Station':22s} {'km':>4s} " + " ".join(f"{r:>9s}" for r in reihen)
            + f" {'h≥12':>5s} {'F1 Wind':>7s} {'F1 Urteil':>9s}")
    zeilen = [kopf, "-" * len(kopf)]

    def z(v):
        return f"{v:.2f}" if isinstance(v, (int, float)) else "–"

    for e in ergebnisse:
        teile = []
        for r in reihen:
            m = e["reihen"].get(r) or {}
            teile.append(f"{m['mae']:>9.1f}" if m.get("mae") is not None else f"{'–':>9s}")
        w = e["reihen"].get("Wingfoilscout") or {}
        zeilen.append(f"{e['name'][:30]:30s} {e['station'].get('name', '')[:22]:22s} {e['km']:>4.1f} "
                      + " ".join(teile)
                      + f" {e['sessions'].get('gemessen_fahrbar', 0):>5d} {z(w.get('f1')):>7s} {z(e['sessions'].get('f1')):>9s}")
    zeilen.append("(Zahlen: mittlerer Fehler in kn je Reihe · h≥12: gemessene Tagesstunden über 12 kn · "
                  "F1 Wind: Wingfoilscout-Wind ≥ 12 gegen Messung ≥ 12 · F1 Urteil: Wingfoilscouts „fahrbar“ gegen "
                  "Messung ≥ 12 — bei wenigen h≥12 sagt F1 wenig)")
    return "\n".join(zeilen)


def bericht(abschnitte: list) -> str:
    """[(Titel, [Befunde], Zusatztext)] → Text fürs Terminal."""
    out = []
    gesamt = [0, 0, 0]
    for titel, befunde, zusatz in abschnitte:
        out.append(f"── {titel}")
        for stufe, text in befunde:
            out.append(f"  {ZEICHEN.get(stufe, '?')} {text}")
        if zusatz:
            out.append("")
            out.append("  " + zusatz.replace("\n", "\n  "))
        o, w, f = zusammenfassung(befunde)
        gesamt[0] += o; gesamt[1] += w; gesamt[2] += f
        out.append("")
    out.append(f"{gesamt[0]} ok · {gesamt[1]} Warnungen · {gesamt[2]} Fehler")
    return "\n".join(out)
