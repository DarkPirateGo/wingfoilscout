"""Session-Tagebuch — was auf dem Wasser wirklich war, gegen das, was Wingfoilscout sagte.

Bis 1.15 wusste Wingfoilscout nur aus Spotguides und Modellen, wie gut ein Tag
wird. Ob das Windfenster eines Wings stimmt oder ein Spot mehr Wind hat, als
die Modelle sagen, weiß nur, wer dort war. Das Tagebuch hält je Session fest:

    Spot, Datum, Zeit von–bis, Wing, Leistung (untermotorisiert / passt /
    übermotorisiert), Wasser (flach / kabbelig / Welle), Note 1–5

und legt daneben, was Wingfoilscout für genau diese Stunden gesagt hätte
(Bewertung mit Spotwissen), was die Modelle sagten und was die nächste
Messstation gemessen hat — dieselbe Rechnung wie im Rückblick
(`rueckblick.spot_zeile`).

Aus mehreren Sessions werden Vorschläge:

  Windfenster je Wing  „untermotorisiert“ bei einem Wind, den der Quiver für
                       diesen Wing schon als passend führt, heißt: die
                       Untergrenze liegt zu tief; „übermotorisiert“ im Fenster
                       heißt: die Obergrenze liegt zu hoch; „passt“ außerhalb
                       heißt: das Fenster ist zu eng. Als Wind der Session gilt
                       die Messung, wenn eine Station höchstens 15 km weg liegt,
                       sonst die Wingfoilscout-Vorhersage — was genommen wurde,
                       steht an jedem Beleg.
  Windfaktor je Spot   Jede Session grenzt den Faktor ein: „passt“ heißt,
                       roher Modellwind der Session-Stunden mal Faktor lag im
                       Fenster des gefahrenen Wings; untermotorisiert: darunter;
                       übermotorisiert: darüber. Verlangen mindestens zwei
                       Sessions einen anderen Faktor, wird der nächstliegende
                       vorgeschlagen, zu dem alle Sessions des Spots passen.

Ein Vorschlag braucht mindestens zwei Sessions, die in dieselbe Richtung
zeigen, und wird nur übernommen, wenn du ihn bestätigst — in `config.yaml`
(Windfenster) oder `spots.yaml` (Windfaktor).

Gespeichert wird in `tagebuch.json` im Projektordner: persönlich, nicht
versioniert (wie `config.yaml`), gesichert nur über das Backup des Macs.
"""
from __future__ import annotations
import json
import math
import re
import statistics
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from . import ROOT, i18n
from .i18n import T, TN, N_                                       # noqa: F401

TAGEBUCH = ROOT / "tagebuch.json"
# Schlüssel sind Daten (stehen so in tagebuch.json), die Werte Beschriftungen —
# übersetzt wird beim Anzeigen: T(LEISTUNG[k]).
LEISTUNG = {"unter": N_("untermotorisiert"), "passt": N_("passt"), "ueber": N_("übermotorisiert")}
WASSER = {"flach": N_("flach"), "kabbelig": N_("kabbelig"), "welle": N_("Welle")}
WASSER_AUS_BEWERTUNG = {"flat": "flach", "chop": "kabbelig", "wave": "welle"}
MIN_BELEGE = 2                 # so viele Sessions braucht ein Vorschlag
STATION_NAH_KM = 15.0          # näher: die Messung gilt als Wind der Session
FAKTOR_GRENZEN = (0.6, 1.5)
FAKTOR_SCHRITT = 0.05
VERGLEICH_KM = 30.0            # Umkreis für die Messstation, wie im Rückblick


class TagebuchFehler(ValueError):
    pass


# Die Oberfläche trägt ein, löscht und schreibt Vergleiche aus dem
# Hintergrundlauf zurück — jeweils lesen, ändern, schreiben. Ohne Sperre
# verlöre eine Session, die während eines Vergleichs eingetragen wird, gegen
# das Zurückschreiben des Vergleichs.
_SPERRE = threading.Lock()


# ── Datei ────────────────────────────────────────────────────────────────────

def laden(pfad: Path | None = None) -> dict:
    pfad = pfad or TAGEBUCH
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        if isinstance(daten, dict) and isinstance(daten.get("sessions"), list):
            return daten
    except (OSError, ValueError):
        pass
    return {"version": 1, "sessions": []}


def speichern(daten: dict, pfad: Path | None = None) -> None:
    from .spotedit import schreibe_atomar
    pfad = pfad or TAGEBUCH
    pfad.parent.mkdir(parents=True, exist_ok=True)
    schreibe_atomar(pfad, json.dumps(daten, ensure_ascii=False, indent=1))


# ── Eintragen ────────────────────────────────────────────────────────────────

def _uhrzeit(text) -> str:
    t = str(text or "").strip()
    if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", t):
        raise TagebuchFehler(T("Uhrzeit nicht lesbar: „{eingabe}“ — erwartet HH:MM", eingabe=t))
    h, m = t.split(":")
    return f"{int(h):02d}:{m}"


def pruefe(roh: dict, spots_by_id: dict, wings: list, jetzt: datetime | None = None) -> dict:
    """Eine Eingabe aus der Oberfläche → ein sauberer Eintrag, oder TagebuchFehler.
    `jetzt`: Ortszeit des Rechners — eine Session kann nicht erst beginnen."""
    jetzt = jetzt or datetime.now()
    heute = jetzt.date()
    spot = str(roh.get("spot") or "")
    if spot not in spots_by_id:
        raise TagebuchFehler(T("Unbekannter Spot — bitte aus der Liste wählen."))
    try:
        tag = date.fromisoformat(str(roh.get("datum") or ""))
    except ValueError:
        raise TagebuchFehler(T("Datum nicht lesbar — erwartet JJJJ-MM-TT.")) from None
    if tag > heute:
        raise TagebuchFehler(T("Das Datum liegt in der Zukunft."))
    von, bis = _uhrzeit(roh.get("von")), _uhrzeit(roh.get("bis"))
    if bis <= von:
        raise TagebuchFehler(T("„Bis“ muss nach „von“ liegen."))
    if tag == heute and von > jetzt.strftime("%H:%M"):
        raise TagebuchFehler(T("Die Session beginnt erst — eintragen, wenn sie begonnen hat."))
    try:
        wing = roh.get("wing")
        wing = float(wing.replace(",", ".") if isinstance(wing, str) else wing)   # „4,2“ wie „4.2“
    except (TypeError, ValueError):
        raise TagebuchFehler(T("Wing fehlt.")) from None
    groessen = [float(w["size"]) for w in wings]
    if not any(abs(wing - g) < 1e-6 for g in groessen):
        raise TagebuchFehler(T("Wing {wing} m² steht nicht im Quiver ({quiver}).",
                               wing=i18n.zahl(wing, 1), quiver=", ".join(i18n.zahl(g, 1) for g in groessen)))
    leistung = str(roh.get("leistung") or "")
    if leistung not in LEISTUNG:
        raise TagebuchFehler(T("Leistung fehlt: untermotorisiert, passt oder übermotorisiert."))
    wasser = str(roh.get("wasser") or "")
    if wasser not in WASSER:
        raise TagebuchFehler(T("Wasser fehlt: flach, kabbelig oder Welle."))
    try:
        note = int(roh.get("note"))
    except (TypeError, ValueError):
        raise TagebuchFehler(T("Note fehlt (1 bis 5).")) from None
    if not 1 <= note <= 5:
        raise TagebuchFehler(T("Die Note geht von 1 bis 5."))
    return {"spot": spot, "datum": tag.isoformat(), "von": von, "bis": bis, "wing": wing,
            "leistung": leistung, "wasser": wasser, "note": note}


def eintragen(eintrag: dict, pfad: Path | None = None) -> dict:
    with _SPERRE:
        daten = laden(pfad)
        session = dict(eintrag, id=uuid.uuid4().hex[:12], angelegt=datetime.now().isoformat(timespec="minutes"))
        daten["sessions"].append(session)
        speichern(daten, pfad)
    return session


def loeschen(sid: str, pfad: Path | None = None) -> bool:
    with _SPERRE:
        daten = laden(pfad)
        vorher = len(daten["sessions"])
        daten["sessions"] = [s for s in daten["sessions"] if s.get("id") != sid]
        if len(daten["sessions"]) == vorher:
            return False
        speichern(daten, pfad)
    return True


def _gehalt(vg: dict | None) -> int:
    """Wie viel ein Vergleich weiß: 2 mit Messung, 1 nur Vorhersage, 0 nichts."""
    vg = vg or {}
    return 2 if vg.get("gemessen_kn") is not None else 1 if vg.get("wingscout_kn") is not None else 0


def vergleich_eintragen(ergebnisse: dict, pfad: Path | None = None) -> dict:
    """Die Vergleiche aus einem Hintergrundlauf (Session-ID → Vergleich) in die
    Datei, wie sie *jetzt* ist — eine inzwischen gelöschte Session bleibt
    gelöscht, eine inzwischen eingetragene bleibt da.

    Weiß der neue Vergleich weniger als der alte (das Netz war weg, die
    Station antwortete nicht), bleibt der alte stehen und bekommt den
    Fehlschlag als `letzter_versuch` dazu — ein „Neu vergleichen“ im Funkloch
    soll keine Messung von gestern löschen. Rückgabe: {"neu": n, "behalten": k}."""
    zahl = {"neu": 0, "behalten": 0}
    with _SPERRE:
        daten = laden(pfad)
        for s in daten["sessions"]:
            if s.get("id") not in ergebnisse:
                continue
            neu, alt = ergebnisse[s["id"]], s.get("vergleich")
            if _gehalt(neu) < _gehalt(alt):
                alt["letzter_versuch"] = {"gerechnet": neu.get("gerechnet"),
                                          "grund": neu.get("grund") or T("weniger gefunden")}
                zahl["behalten"] += 1
            else:
                s["vergleich"] = neu
                zahl["neu"] += 1
        if zahl["neu"] or zahl["behalten"]:
            speichern(daten, pfad)
    return zahl


# ── Vergleich mit Vorhersage und Messung ─────────────────────────────────────

def stunden_der_session(session: dict) -> list[int]:
    """Die vollen Stunden (Ortszeit), die die Session berührt: 14:30–16:10 → 14, 15, 16."""
    h0 = int(session["von"][:2])
    h1, m1 = int(session["bis"][:2]), int(session["bis"][3:])
    ende = h1 if m1 == 0 else h1 + 1
    return list(range(h0, max(ende, h0 + 1)))


def _mittel(werte) -> float | None:
    """Das Mittel der Zahlen darin. None, Text, NaN und Unendlich zählen nicht:
    bis 2.1.0 machte ein NaN aus der Messung das ganze Mittel zu NaN, und das
    stand dann in tagebuch.json (Review 04.10.2026, C5)."""
    zahlen = []
    for v in werte:
        if v is None or isinstance(v, bool):
            continue
        try:
            f = float(v)
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(f):
            zahlen.append(f)
    return round(statistics.fmean(zahlen), 1) if zahlen else None


def auswerten(session: dict, zeile: dict, rows: list | None, wind_factor: float) -> dict:
    """Aus der Rückblick-Zeile eines Tages die Stunden der Session herausziehen."""
    tag, stunden = session["datum"], set(stunden_der_session(session))
    aus = {"station": zeile.get("station"), "grund": zeile.get("grund")}
    auswahl = [h for h in zeile.get("stunden") or []
               if h["t"][:10] == tag and int(h["t"][11:13]) in stunden]
    rows_s = [r for r in rows or [] if r["t"].date().isoformat() == tag and r["t"].hour in stunden]
    if not auswahl and not rows_s:
        aus["grund"] = aus.get("grund") or T("keine Stunden dieser Session in Vorhersage oder Messung")
        return aus
    aus["wingscout_kn"] = _mittel(h.get("v") for h in auswahl)
    aus["gemessen_kn"] = _mittel(h.get("m") for h in auswahl)
    aus["gemessen_h"] = sum(1 for h in auswahl if h.get("m") is not None)
    modelle = {}
    for h in auswahl:
        for mid, v in (h.get("mv") or {}).items():
            modelle.setdefault(mid, []).append(v)
    aus["modelle"] = {mid: _mittel(v) for mid, v in modelle.items()}
    werte = [v for v in aus["modelle"].values() if v is not None]
    aus["spanne"] = [min(werte), max(werte)] if len(werte) >= 2 else None
    aus["thermik"] = any(h.get("thermik") for h in auswahl) or any(r.get("thermal") for r in rows_s)
    # Roher Modellwind am Spot — ohne Windfaktor. Stunden mit Thermikannahme
    # zählen nicht: dort ersetzt die Annahme den Modellwind.
    roh = [float(r["wind"]) / wind_factor for r in rows_s if not r.get("thermal") and r.get("wind") is not None]
    aus["roh_kn"] = _mittel(roh) if wind_factor else None
    wings = [r.get("wing") for r in rows_s if r.get("wing") is not None]
    aus["wing_vorschlag"] = max(set(wings), key=wings.count) if wings else None
    wasser = [WASSER_AUS_BEWERTUNG.get(r.get("water")) for r in rows_s if r.get("water")]
    aus["wasser_vorhersage"] = max(set(wasser), key=wasser.count) if wasser else None
    scores = [r.get("score") for r in rows_s if r.get("score") is not None]
    aus["score"] = round(statistics.fmean(scores) * 100) if scores else None
    return aus


def vergleichen(cfg, spots_by_id: dict, geometry: dict, sessions: list, log=None,
                jetzt: datetime | None = None) -> None:
    """Für jede übergebene Session Vorhersage und Messung ihrer Stunden holen —
    schreibt `vergleich` in die übergebenen Sessions (Kopien; zurück in die
    Datei mit `vergleich_eintragen`). Netz nötig.

    `grund` ist nur Anzeigetext (nie verglichen) und steht in der Sprache des
    Laufs in der Datei — er trägt Fehlertexte und Stationshinweise, die sich
    beim Anzeigen nicht mehr übersetzen ließen; „Neu vergleichen“ schreibt ihn neu."""
    from . import rueckblick, __version__
    from .models import DEFAULT_MODELS
    from .sources import stationen
    say = log or (lambda *a: None)
    jetzt = jetzt or datetime.now(timezone.utc).replace(tzinfo=None)
    models = cfg.get("wind", {}).get("models") or DEFAULT_MODELS
    stationen.windguru_setzen((cfg.get("stationen") or {}).get("windguru"))
    for session in sessions:
        spot = spots_by_id.get(session.get("spot"))
        if not spot:
            session["vergleich"] = {"grund": T("Spot nicht mehr im Katalog"),
                                    "gerechnet": jetzt.isoformat(timespec="minutes")}
            continue
        tag = session["datum"]
        tagesende = f"{tag}T23:00"
        jetzt_utc = min(jetzt.strftime("%Y-%m-%dT%H:00"), tagesende)
        say(f"{tag} {spot['name']} {session['von']}–{session['bis']}")
        try:
            stationsfehler = ""
            try:
                paare = stationen.paare_finden([spot], VERGLEICH_KM, log=say)
            except Exception as exc:                    # noqa: BLE001 — dann ohne Messung
                paare, stationsfehler = [], T("Stationen nicht abrufbar ({fehler})", fehler=exc)
                say(f"    {stationsfehler}")
            zeile, rows = rueckblick.spot_zeile(cfg, spot, paare[0] if paare else None, tag, tag, jetzt_utc,
                                                geometry, VERGLEICH_KM, say, models)
            if rows is None:
                # Keine Station, oder sie hat für diesen Tag (noch) nichts —
                # DWD liefert gestern erst mit der nächsten Tagesdatei. Die
                # Vorhersage steht trotzdem neben der Session; „Neu
                # vergleichen“ holt die Messung später nach.
                ohne = _nur_vorhersage(cfg, spot, tag, geometry, models, say)
                ohne[0]["station"] = zeile.get("station")
                ohne[0]["grund"] = T("{grund} — nur die Vorhersage",
                                     grund=stationsfehler or zeile.get("grund") or T("keine Messung"))
                zeile, rows = ohne
            vg = auswerten(session, zeile, rows, float(spot.get("wind_factor") or 1.0))
        except Exception as exc:                        # noqa: BLE001 — eine Session kostet nicht alle
            vg = {"grund": T("nicht abrufbar ({fehler})", fehler=exc)}
        vg["gerechnet"] = datetime.now().isoformat(timespec="minutes")
        vg["version"] = __version__
        session["vergleich"] = vg


def _nur_vorhersage(cfg, spot: dict, tag: str, geometry: dict, models: list, say) -> tuple[dict, list | None]:
    """Keine Messung für diesen Tag: die Bewertung der Stunden und die
    einzelnen Modelle trotzdem, damit wenigstens die Vorhersage neben der
    Session steht. Dieselben Schritte wie in `rueckblick.spot_zeile`."""
    from . import modellvergleich
    from .pruefstand import _utc_stunde
    from .sources import historisch
    from .sources.highres import kandidaten, kurzname
    from .score import score_hours
    from .spots import zeitzone
    tz = zeitzone(spot)
    zeile = {"id": spot["id"], "name": spot["name"], "station": None, "stunden": []}
    fc = historisch.hole_bis_heute(spot, tag, tag, models, tz)
    liste = kandidaten(spot)
    if liste:
        try:
            fein = historisch.hole_regional_bis_heute(spot, liste[0], tag, tag, tz)
            if fein and fein.get("hourly"):
                fc["_highres"] = (liste[0], fein["hourly"])
                zeile["modell"] = kurzname(liste[0])
        except Exception:                               # noqa: BLE001 — dann eben ohne
            pass
    eintrag_geo = geometry.get(spot["id"]) or {}
    rose = None if eintrag_geo.get("wasser") is False else eintrag_geo.get("rose_m")
    rows = score_hours(spot, fc, cfg, rose=rose)
    offset = int(fc.get("utc_offset_seconds") or 0)
    try:
        reihen = modellvergleich.modellreihen(spot, tag, tag, tz,
                                              globale=(cfg.get("rueckblick") or {}).get("modelle"), log=say)
    except Exception:                                   # noqa: BLE001 — die Spanne ist Beiwerk
        reihen = []
    for r in rows:
        utc = _utc_stunde(r["t"], offset)
        zeile["stunden"].append({
            "t": r["t"].strftime("%Y-%m-%dT%H:%M"), "v": round(float(r["wind"]), 1), "m": None,
            "thermik": bool(r.get("thermal")),
            "mv": {x["id"]: round(x["reihe"][utc][0], 1) for x in reihen if utc in x["reihe"]}})
    zeile["modellnamen"] = {x["id"]: x["name"] for x in reihen}
    return zeile, rows


# ── Vorschläge ───────────────────────────────────────────────────────────────

def wind_der_session(session: dict) -> tuple[float | None, str]:
    """Welcher Wind gilt für die Session: die Messung, wenn die Station nah
    ist, sonst die Wingfoilscout-Vorhersage."""
    vg = session.get("vergleich") or {}
    st = vg.get("station") or {}
    # Die Basis ist Anzeigetext: `vorschlaege` rechnet sie bei jedem Aufruf der
    # Seite neu, gespeichert wird sie nicht.
    if vg.get("gemessen_kn") is not None and (st.get("km") or 999) <= STATION_NAH_KM:
        return float(vg["gemessen_kn"]), T("gemessen ({quelle} {name}, {km} km)", quelle=st.get("quelle", ""),
                                           name=st.get("name", ""), km=i18n.zahl(st.get("km") or 0))
    if vg.get("wingscout_kn") is not None:
        return float(vg["wingscout_kn"]), T("Wingfoilscout-Vorhersage")
    return None, ""


def _beleg(session: dict, wind: float | None, basis: str) -> dict:
    return {"id": session.get("id"), "datum": session.get("datum"), "spot": session.get("spot"),
            "leistung": session.get("leistung"), "wind": wind, "basis": basis}


def vorschlaege_windfenster(sessions: list, wings: list) -> list[dict]:
    aus = []
    for w in sorted(wings, key=lambda w: -float(w["size"])):
        groesse, low, high = float(w["size"]), float(w["low"]), float(w["high"])
        eigene = [(s, *wind_der_session(s)) for s in sessions if abs(float(s.get("wing") or 0) - groesse) < 1e-6]
        eigene = [(s, wind, basis) for s, wind, basis in eigene if wind is not None]
        if not eigene:
            continue
        unter = [(s, v, b) for s, v, b in eigene if s["leistung"] == "unter"]
        passt = [(s, v, b) for s, v, b in eigene if s["leistung"] == "passt"]
        ueber = [(s, v, b) for s, v, b in eigene if s["leistung"] == "ueber"]
        passt_min = min((v for _, v, _ in passt), default=None)
        passt_max = max((v for _, v, _ in passt), default=None)
        low_neu = high_neu = None
        gruende, belege = [], []
        # Untergrenze
        zu_tief = [(s, v, b) for s, v, b in unter if v >= low]
        if len(zu_tief) >= MIN_BELEGE:
            kandidat = math.floor(max(v for _, v, _ in zu_tief)) + 1      # knapp darüber
            if passt_min is not None and kandidat > passt_min:
                gruende.append(T("Untergrenze: widersprüchlich — untermotorisiert bis {bis} kn, "
                                 "aber „passt“ schon ab {ab} kn",
                                 bis=f"{max(v for _, v, _ in zu_tief):.0f}", ab=f"{passt_min:.0f}"))
            else:
                low_neu = kandidat
                gruende.append(T("{n}× untermotorisiert bei {werte} kn — im Fenster ab {low} kn",
                                 n=len(zu_tief), werte=", ".join(f"{v:.0f}" for _, v, _ in zu_tief),
                                 low=f"{low:.0f}"))
                belege += [_beleg(s, v, b) for s, v, b in zu_tief]
        else:
            zu_eng_unten = [(s, v, b) for s, v, b in passt if v < low]
            if len(zu_eng_unten) >= MIN_BELEGE:
                kandidat = math.floor(min(v for _, v, _ in zu_eng_unten))
                unter_max = max((v for _, v, _ in unter), default=None)
                if unter_max is not None and unter_max >= kandidat:
                    gruende.append(T("Untergrenze: widersprüchlich — „passt“ schon ab {ab} kn, "
                                     "aber untermotorisiert noch bei {bei} kn",
                                     ab=kandidat, bei=f"{unter_max:.0f}"))
                else:
                    low_neu = kandidat
                    gruende.append(T("{n}× „passt“ unter der Untergrenze ({werte} kn)",
                                     n=len(zu_eng_unten), werte=", ".join(f"{v:.0f}" for _, v, _ in zu_eng_unten)))
                    belege += [_beleg(s, v, b) for s, v, b in zu_eng_unten]
        # Obergrenze
        zu_hoch = [(s, v, b) for s, v, b in ueber if v <= high]
        if len(zu_hoch) >= MIN_BELEGE:
            kandidat = math.ceil(min(v for _, v, _ in zu_hoch)) - 1       # knapp darunter
            if passt_max is not None and kandidat < passt_max:
                gruende.append(T("Obergrenze: widersprüchlich — übermotorisiert ab {ab} kn, "
                                 "aber „passt“ noch bei {bei} kn",
                                 ab=f"{min(v for _, v, _ in zu_hoch):.0f}", bei=f"{passt_max:.0f}"))
            else:
                high_neu = kandidat
                gruende.append(T("{n}× übermotorisiert bei {werte} kn — im Fenster bis {high} kn",
                                 n=len(zu_hoch), werte=", ".join(f"{v:.0f}" for _, v, _ in zu_hoch),
                                 high=f"{high:.0f}"))
                belege += [_beleg(s, v, b) for s, v, b in zu_hoch]
        else:
            zu_eng_oben = [(s, v, b) for s, v, b in passt if v > high]
            if len(zu_eng_oben) >= MIN_BELEGE:
                kandidat = math.ceil(max(v for _, v, _ in zu_eng_oben))
                ueber_min = min((v for _, v, _ in ueber), default=None)
                if ueber_min is not None and ueber_min <= kandidat:
                    gruende.append(T("Obergrenze: widersprüchlich — „passt“ noch bei {bei} kn, "
                                     "aber übermotorisiert schon bei {ab} kn",
                                     bei=kandidat, ab=f"{ueber_min:.0f}"))
                else:
                    high_neu = kandidat
                    gruende.append(T("{n}× „passt“ über der Obergrenze ({werte} kn)",
                                     n=len(zu_eng_oben), werte=", ".join(f"{v:.0f}" for _, v, _ in zu_eng_oben)))
                    belege += [_beleg(s, v, b) for s, v, b in zu_eng_oben]
        neu_low = low_neu if low_neu is not None else low
        neu_high = high_neu if high_neu is not None else high
        if (low_neu is not None or high_neu is not None) and neu_low >= neu_high:
            gruende.append(T("der Vorschlag ergäbe kein Fenster mehr (unten ≥ oben) — nichts übernommen"))
            low_neu = high_neu = None
        aus.append({"size": groesse, "low": low, "high": high, "low_neu": low_neu, "high_neu": high_neu,
                    "sessions": len(eigene), "gruende": gruende, "belege": belege})
    return aus


def _runde_faktor(f: float, richtung: int = 0) -> float:
    """Auf 0,05 — nach oben (richtung 1), nach unten (-1) oder zum nächsten."""
    schritte = f / FAKTOR_SCHRITT
    n = math.ceil(schritte - 1e-9) if richtung > 0 else math.floor(schritte + 1e-9) if richtung < 0 else round(schritte)
    return round(n * FAKTOR_SCHRITT, 2)


def vorschlaege_windfaktor(sessions: list, wings: list, spots_by_id: dict) -> list[dict]:
    """Jede Session grenzt den Windfaktor des Spots ein. Mit dem rohen
    Modellwind `roh` der Session-Stunden und dem Fenster (low, high) des
    gefahrenen Wings heißt

        passt              low ≤ Faktor · roh ≤ high
        untermotorisiert   Faktor · roh < low
        übermotorisiert    Faktor · roh > high

    Liegt der jetzige Faktor außerhalb dessen, was mindestens zwei Sessions
    erlauben — in dieselbe Richtung —, wird der nächstliegende Faktor
    vorgeschlagen, zu dem *alle* Sessions des Spots passen: die kleinste
    Änderung, die die Sessions erklärt. Widersprechen sich die Sessions (kein
    Faktor passt zu allen), gibt es keinen Vorschlag."""
    fenster = {float(w["size"]): (float(w["low"]), float(w["high"])) for w in wings}
    je_spot: dict = {}
    for s in sessions:
        roh = (s.get("vergleich") or {}).get("roh_kn")
        f = fenster.get(float(s.get("wing") or 0))
        if roh and roh > 0.5 and f and s.get("spot") in spots_by_id and s.get("leistung") in LEISTUNG:
            je_spot.setdefault(s["spot"], []).append((s, float(roh), f))
    aus = []
    for sid, liste in sorted(je_spot.items()):
        spot = spots_by_id[sid]
        aktuell = float(spot.get("wind_factor") or 1.0)
        eintrag = {"id": sid, "name": spot.get("name", sid), "wind_factor": aktuell, "neu": None,
                   "sessions": len(liste), "grund": "", "belege": []}
        unten, oben = 0.0, math.inf              # der Bereich, in dem der Faktor liegen muss
        hoeher, tiefer = [], []                  # Sessions, denen der jetzige Faktor zu tief / zu hoch ist
        for s, roh, (low, high) in liste:
            if s["leistung"] == "passt":
                u, o = low / roh, high / roh
            elif s["leistung"] == "unter":
                u, o = 0.0, low / roh
            else:
                u, o = high / roh, math.inf
            unten, oben = max(unten, u), min(oben, o)
            beleg = _beleg(s, roh, T("roher Modellwind; {wing} m²: {low}–{high} kn",
                                     wing=i18n.zahl(s["wing"], 1), low=f"{low:g}", high=f"{high:g}"))
            if aktuell < u:
                hoeher.append(beleg)
            elif aktuell > o:
                tiefer.append(beleg)
        if unten > oben:
            eintrag["grund"] = T("widersprüchlich — kein Faktor passt zu allen Sessions (verlangt wären "
                                 "mindestens {unten} und höchstens {oben}); kein Vorschlag",
                                 unten=i18n.zahl(unten, 2), oben=i18n.zahl(oben, 2))
            aus.append(eintrag)
            continue
        if oben == math.inf:
            bereich = T("ab {faktor}", faktor=i18n.zahl(unten, 2))
        elif unten <= 0:
            bereich = T("bis {faktor}", faktor=i18n.zahl(oben, 2))
        else:
            bereich = f"{i18n.zahl(unten, 2)}–{i18n.zahl(oben, 2)}"
        if not hoeher and not tiefer:
            eintrag["grund"] = T("die Sessions passen zum Faktor {faktor} (möglich: {bereich})",
                                 faktor=i18n.zahl(aktuell), bereich=bereich)
            aus.append(eintrag)
            continue
        richtung, belege = (1, hoeher) if hoeher else (-1, tiefer)
        # „höheren“/„niedrigeren“ als eigene Sätze — ein eingesetztes Adjektiv
        # ließe sich nicht übersetzen.
        if len(belege) < MIN_BELEGE:
            eintrag["grund"] = (T("{n} Session spricht für einen höheren Faktor — mindestens {min} nötig",
                                  n=len(belege), min=MIN_BELEGE) if richtung > 0 else
                                T("{n} Session spricht für einen niedrigeren Faktor — mindestens {min} nötig",
                                  n=len(belege), min=MIN_BELEGE))
            eintrag["belege"] = belege
            aus.append(eintrag)
            continue
        neu = _runde_faktor(unten if richtung > 0 else oben, richtung)
        if not unten <= neu <= oben:                      # Bereich schmaler als ein Schritt
            neu = _runde_faktor((unten + oben) / 2)
        grenze = ""
        if not FAKTOR_GRENZEN[0] <= neu <= FAKTOR_GRENZEN[1]:
            neu = min(max(neu, FAKTOR_GRENZEN[0]), FAKTOR_GRENZEN[1])
            grenze = "; " + T("begrenzt auf {faktor} (erlaubt {von}–{bis}) — so weit weg von den Modellen "
                              "stimmt vermutlich etwas anderes, bitte den Spot prüfen",
                              faktor=i18n.zahl(neu), von=i18n.zahl(FAKTOR_GRENZEN[0]), bis=i18n.zahl(FAKTOR_GRENZEN[1]))
        if abs(neu - aktuell) < 1e-6:
            eintrag["grund"] = (T("die Sessions verlangen {bereich}, der Faktor steht schon an der Grenze {faktor}",
                                  bereich=bereich, faktor=i18n.zahl(neu)) if grenze else
                                T("die Sessions verlangen {bereich}, das ist gerundet der jetzige Faktor",
                                  bereich=bereich))
            aus.append(eintrag)
            continue
        eintrag["neu"] = neu
        eintrag["belege"] = belege
        eintrag["grund"] = (T("{n} Sessions verlangen einen höheren Faktor; zu allen {m} Sessions passt {bereich}{grenze}",
                              n=len(belege), m=len(liste), bereich=bereich, grenze=grenze) if richtung > 0 else
                            T("{n} Sessions verlangen einen niedrigeren Faktor; zu allen {m} Sessions passt {bereich}{grenze}",
                              n=len(belege), m=len(liste), bereich=bereich, grenze=grenze))
        aus.append(eintrag)
    return aus


def vorschlaege(daten: dict, cfg, spots_by_id: dict) -> dict:
    sessions = [s for s in daten.get("sessions") or [] if s.get("vergleich")]
    wings = cfg["quiver"]["wings"]
    fenster = vorschlaege_windfenster(sessions, wings)
    faktor = vorschlaege_windfaktor(sessions, wings, spots_by_id)
    # Dieselbe Session kann beide Vorschläge tragen: untermotorisiert passt zu
    # einem zu tief angesetzten Windfenster ebenso wie zu Modellen, die am
    # Spot zu viel Wind sagen. Beide zu übernehmen, korrigierte denselben
    # Befund doppelt — die Seite sagt es dazu.
    def ids(eintraege, aktiv):
        return {b["id"] for e in eintraege if aktiv(e) for b in e.get("belege") or []}
    im_fenster = ids(fenster, lambda w: w["low_neu"] is not None or w["high_neu"] is not None)
    im_faktor = ids(faktor, lambda f: f["neu"] is not None)
    for w in fenster:
        w["ueberschneidung"] = ((w["low_neu"] is not None or w["high_neu"] is not None)
                                and bool(im_faktor & {b["id"] for b in w["belege"]}))
    for f in faktor:
        f["ueberschneidung"] = f["neu"] is not None and bool(im_fenster & {b["id"] for b in f["belege"]})
    return {"windfenster": fenster, "windfaktor": faktor,
            "min_belege": MIN_BELEGE, "station_nah_km": STATION_NAH_KM}


# ── Übernehmen ───────────────────────────────────────────────────────────────

def passender_vorschlag(vs: dict, eingabe: dict) -> dict:
    """Übernommen wird nur, was gerade vorgeschlagen ist — die Seite schickt
    mit, was sie gezeigt hat, und das muss zum frisch gerechneten Vorschlag
    passen. Sonst (eine Session kam dazu, die Seite ist alt) TagebuchFehler."""
    art = eingabe.get("art")
    try:
        if art == "windfenster":
            groesse = float(eingabe.get("size"))
            v = next((w for w in vs["windfenster"] if abs(w["size"] - groesse) < 1e-6), None)
            if not v or (v["low_neu"] is None and v["high_neu"] is None):
                raise TagebuchFehler(T("Für Wing {wing} m² gibt es gerade keinen Vorschlag — Seite neu laden.",
                                       wing=i18n.zahl(groesse, 1)))
            low = v["low_neu"] if v["low_neu"] is not None else v["low"]
            high = v["high_neu"] if v["high_neu"] is not None else v["high"]
            if float(eingabe.get("low")) != float(low) or float(eingabe.get("high")) != float(high):
                raise TagebuchFehler(T("Der Vorschlag hat sich inzwischen geändert — Seite neu laden."))
            return {"art": art, "size": groesse, "low": float(low), "high": float(high)}
        if art == "windfaktor":
            sid = str(eingabe.get("id") or "")
            v = next((f for f in vs["windfaktor"] if f["id"] == sid), None)
            if not v or v["neu"] is None:
                raise TagebuchFehler(T("Für diesen Spot gibt es gerade keinen Vorschlag — Seite neu laden."))
            if abs(float(eingabe.get("wert")) - float(v["neu"])) > 1e-6:
                raise TagebuchFehler(T("Der Vorschlag hat sich inzwischen geändert — Seite neu laden."))
            return {"art": art, "id": sid, "wert": float(v["neu"])}
    except (TypeError, ValueError) as exc:
        if isinstance(exc, TagebuchFehler):
            raise
        raise TagebuchFehler(T("Unvollständige Angaben zum Vorschlag.")) from None
    raise TagebuchFehler(T("Unbekannte Art von Vorschlag."))


def wing_setzen(pfad: str | Path, groesse: float, low: float, high: float) -> None:
    """Das Windfenster eines Wings in `config.yaml` ändern — nur diese Zeile,
    Kommentare und alles andere bleiben. Erwartet die Form der Vorlage:
    `- {size: 5.0, low: 13, high: 22}`."""
    from .spotedit import schreibe_atomar
    if not (0 <= low < high <= 80):
        raise TagebuchFehler(T("Ungültiges Fenster: {low}–{high} kn", low=low, high=high))
    pfad = Path(pfad)
    zeilen = pfad.read_text(encoding="utf-8").splitlines(keepends=True)
    muster = re.compile(r"^(\s*-\s*\{\s*size:\s*)([\d.]+)(\s*,\s*low:\s*)([\d.]+)(\s*,\s*high:\s*)([\d.]+)(\s*\}.*)$", re.S)
    treffer = 0
    for i, z in enumerate(zeilen):
        m = muster.match(z)
        if m and abs(float(m.group(2)) - float(groesse)) < 1e-6:
            zeilen[i] = f"{m.group(1)}{m.group(2)}{m.group(3)}{low:g}{m.group(5)}{high:g}{m.group(7)}"
            treffer += 1
    if treffer != 1:
        # Die YAML-Form als Platzhalter: geschweifte Klammern im Text selbst
        # vertrügen sich nicht mit den Platzhaltern.
        raise TagebuchFehler(T("Wing {wing} m² nicht (eindeutig) in der Form „{form}“ gefunden — "
                               "bitte in config.yaml von Hand ändern.",
                               wing=i18n.zahl(groesse, 1), form="- {size: …, low: …, high: …}"))
    schreibe_atomar(pfad, "".join(zeilen))
