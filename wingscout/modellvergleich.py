"""Welches Wettermodell lag wo am besten? — der Modellvergleich im Rückblick.

Bis 1.13 stand im Rückblick eine Vorhersagelinie gegen die Messung: die
Wingfoilscout-Bewertung, in der ICON, GFS und ECMWF zu einer Reihe zusammengeführt
sind und das Regionalmodell die Stunden überschreibt, die es abdeckt. Ob ein
anderes Modell an diesem Spot besser gelegen hätte, sah man nicht.

Jetzt kommt jedes Modell einzeln an die Messung — roh, so wie Open-Meteo es
liefert, ohne `wind_factor` und ohne Thermik —, und die Wingfoilscout-Bewertung
steht als eigene Zeile dazwischen. Welche Modelle Open-Meteo rückwirkend führt,
wurde am 20.09.2026 an Brouwersdam und Torbole abgefragt (Archiv und laufende
Vorhersage, 17. bis 20.09.):

  global, überall  ICON, ECMWF IFS, ECMWF AIFS (das KI-Modell des EZMW), GFS,
                   Météo-France (ARPEGE/AROME), UKMO — dazu ICON-EU, GEM,
                   JMA, CMA; nichts lieferten BOM ACCESS und GraphCast
  regional         je nach Ort ICON-D2, AROME-HD, HARMONIE (KNMI, DMI), CH1,
                   ICON-2I, AROME-AT — „No data is available for this
                   location“ (HTTP 400) außerhalb ihres Gebiets

Verglichen werden die sechs globalen Modelle oben und bis zu drei
Regionalmodelle je Spot (die Kandidaten aus `highres.kandidaten`). Die Liste
der globalen lässt sich in `config.yaml` unter `rueckblick: modelle:` ändern.

Gedächtnis: Jede Prüfung legt ihre Summen je Spot, Tag und Modell in
`modellguete.json` ab (persönlich, nicht versioniert). Derselbe Tag wird bei
der nächsten Prüfung überschrieben, nicht doppelt gezählt — so entsteht über
Wochen eine Rangliste, die mehr sagt als drei Tage.

Die Maße sind dieselben wie in `pruefstand.masse` (MAE, Bias, Richtung, F1 für
„≥ 12 kn bei Tag“); gerechnet wird hier über Summen, damit sich Tage und Spots
zusammenzählen lassen. Ein Test hält fest, dass beide Wege dasselbe ergeben.
"""
from __future__ import annotations
import json
import math
from datetime import datetime
from pathlib import Path

from . import ROOT
from .i18n import T, TN, N_                                       # noqa: F401
from .pruefstand import SCHWELLE_KN, _winkel, _utc_stunde

VERGLEICH_GLOBAL = ["dwd_icon_seamless", "ecmwf_ifs", "ecmwf_aifs025_single", "ncep_gfs_seamless",
                    "meteofrance_seamless", "ukmo_seamless"]
# Anzeigenamen; die deutschen Bezeichnungen mit N_(), übersetzt in `name()`.
# Gemerkt (modellguete.json) und verglichen wird nur die Kennung links.
NAMEN = {"dwd_icon_seamless": "ICON", "ecmwf_ifs": "ECMWF", "ecmwf_aifs025_single": N_("ECMWF-KI"),
         "ncep_gfs_seamless": "GFS", "meteofrance_seamless": "Météo-France", "ukmo_seamless": "UKMO",
         "dwd_icon_eu": "ICON-EU", "gem_seamless": "GEM", "jma_seamless": "JMA", "metno_seamless": "MET Norway",
         "knmi_seamless": "KNMI", "dmi_seamless": "DMI", "wingscout": N_("Wingfoilscout-Bewertung")}
MAX_REGIONAL = 3
WINGSCOUT = "wingscout"
GUETE = ROOT / "modellguete.json"
MIN_STUNDEN_BESTES = 24           # darunter wird kein „bestes Modell“ benannt


def name(modell: str) -> str:
    if modell in NAMEN:
        return T(NAMEN[modell])
    from .sources.highres import kurzname
    kurz = kurzname(modell)
    return kurz if kurz != modell else modell.replace("_seamless", "").upper()


def _zahl(v) -> float | None:
    """Eine Zahl, mit der sich rechnen lässt — endlich und kein bool, sonst None.
    Pythons json nimmt NaN und Infinity an; bis 2.1.0 gingen sie von einer
    Station bis in `modellguete.json` und machten dort jede Rangliste zu NaN
    (Review 04.10.2026, C5)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return f if math.isfinite(f) else None


def _versatz(fc: dict) -> int:
    """utc_offset_seconds als ganze Sekunden — 0, wenn er fehlt oder Unsinn ist."""
    v = _zahl(fc.get("utc_offset_seconds"))
    return int(v) if v is not None and abs(v) <= 18 * 3600 else 0


# ── Reihen holen ─────────────────────────────────────────────────────────────

def _reihe_aus(hourly: dict, offset: int, schluessel_v: str, schluessel_d: str) -> dict:
    """{UTC-Stunde: (kn, Richtung|None)} aus einer Open-Meteo-Antwort."""
    aus = {}
    zeiten = hourly.get("time") or []
    v = hourly.get(schluessel_v) or []
    d = hourly.get(schluessel_d) or []
    for i, t in enumerate(zeiten):
        kn = _zahl(v[i]) if i < len(v) else None
        if kn is None:
            continue
        try:
            utc = _utc_stunde(datetime.fromisoformat(str(t)), offset)
        except (TypeError, ValueError, OverflowError):
            continue
        aus[utc] = (kn, _zahl(d[i]) if i < len(d) else None)
    return aus


def modellreihen(spot: dict, von: str, bis: str, tz: str, globale: list | None = None, log=None) -> list[dict]:
    """Jedes Vergleichsmodell als eigene Reihe — [{"id", "name", "art", "reihe"}].

    Eine Anfrage für alle globalen Modelle (nur Stärke und Richtung), eine je
    Regionalmodell. Was nicht antwortet, fehlt — der Vergleich lebt mit dem,
    was kommt."""
    from .sources import historisch
    from .sources.highres import kandidaten
    say = log or (lambda *a: None)
    globale = list(globale or VERGLEICH_GLOBAL)
    felder = ["wind_speed_10m", "wind_direction_10m"]
    aus = []
    try:
        fc = historisch.hole_bis_heute(spot, von, bis, globale, tz, hourly=felder)
        h = fc.get("hourly") or {}
        offset = _versatz(fc)
        einzeln = len(globale) == 1 and "wind_speed_10m" in h
        for m in globale:
            sv, sd = (("wind_speed_10m", "wind_direction_10m") if einzeln
                      else (f"wind_speed_10m_{m}", f"wind_direction_10m_{m}"))
            reihe = _reihe_aus(h, offset, sv, sd)
            if reihe:
                aus.append({"id": m, "name": name(m), "art": "global", "reihe": reihe})
    except Exception as exc:                            # noqa: BLE001 — dann ohne die globalen
        say("    " + T("Modellvergleich: globale Modelle nicht abrufbar ({fehler})", fehler=exc))
    for m in kandidaten(spot)[:MAX_REGIONAL]:
        try:
            fein = historisch.hole_regional_bis_heute(spot, m, von, bis, tz)
        except Exception as exc:                        # noqa: BLE001
            say("    " + T("Modellvergleich: {modell} nicht abrufbar ({fehler})", modell=name(m), fehler=exc))
            continue
        if not fein or not fein.get("hourly"):
            continue
        reihe = _reihe_aus(fein["hourly"], _versatz(fein), "wind_speed_10m", "wind_direction_10m")
        if reihe:
            aus.append({"id": m, "name": name(m), "art": "regional", "reihe": reihe})
    return aus


# ── Rechnen über Summen ──────────────────────────────────────────────────────

LEER = {"n": 0, "fehler": 0.0, "betrag": 0.0, "richtung_n": 0, "richtung_ok": 0,
        "tag_n": 0, "gesagt": 0, "gemessen": 0, "treffer": 0}


def summen(vorhersage: dict, messung: dict, tageslicht: set | None = None) -> dict:
    """Die Rohsummen, aus denen `masse` besteht — {UTC-Stunde: (kn, dir)} je Seite.
    Eine Stunde zählt nur, wenn beide Seiten eine endliche Zahl haben."""
    s = dict(LEER)
    for t, (v, vd) in vorhersage.items():
        if t not in messung:
            continue
        v, m = _zahl(v), _zahl(messung[t][0])
        if v is None or m is None:
            continue
        vd, md = _zahl(vd), _zahl(messung[t][1])
        s["n"] += 1
        s["fehler"] += v - m
        s["betrag"] += abs(v - m)
        if m >= 8 and vd is not None and md is not None:
            s["richtung_n"] += 1
            s["richtung_ok"] += 1 if _winkel(vd, md) <= 45 else 0
        if tageslicht is None or t in tageslicht:
            s["tag_n"] += 1
            ja_v, ja_m = v >= SCHWELLE_KN, m >= SCHWELLE_KN
            s["gesagt"] += ja_v
            s["gemessen"] += ja_m
            s["treffer"] += ja_v and ja_m
    s["fehler"], s["betrag"] = round(s["fehler"], 3), round(s["betrag"], 3)
    return s


def summen_je_tag(vorhersage: dict, messung: dict, tageslicht: set | None = None) -> dict:
    """Wie `summen`, aber je UTC-Tag getrennt — für das Gedächtnis."""
    tage: dict = {}
    for t in vorhersage:
        tage.setdefault(t[:10], {})[t] = vorhersage[t]
    return {tag: s for tag, reihe in sorted(tage.items())
            if (s := summen(reihe, messung, tageslicht))["n"]}


def addiere(*teile: dict) -> dict:
    s = dict(LEER)
    for t in teile:
        for k in LEER:
            s[k] += t.get(k, 0) or 0
    return s


def masse_aus(s: dict) -> dict:
    """Summen → dieselben Maße wie `pruefstand.masse`."""
    n = s.get("n") or 0
    if not n:
        return {"n": 0}
    aus = {"n": n, "bias": round(s["fehler"] / n, 2), "mae": round(s["betrag"] / n, 2),
           "richtung_n": s["richtung_n"],
           "richtung": round(s["richtung_ok"] / s["richtung_n"], 2) if s["richtung_n"] else None}
    p = s["treffer"] / s["gesagt"] if s["gesagt"] else None
    r = s["treffer"] / s["gemessen"] if s["gemessen"] else None
    f1 = 2 * p * r / (p + r) if p is not None and r is not None and (p + r) > 0 else None
    aus.update({"fahrbar_n": s["tag_n"], "gemessen_fahrbar": s["gemessen"], "gesagt_fahrbar": s["gesagt"],
                "precision": round(p, 2) if p is not None else None,
                "recall": round(r, 2) if r is not None else None,
                "f1": round(f1, 2) if f1 is not None else None})
    return aus


def _sortiert(zeilen: list) -> list:
    """Nach MAE, Reihen ohne gemeinsame Stunden ans Ende."""
    return sorted(zeilen, key=lambda z: (z["masse"].get("mae") is None, z["masse"].get("mae") or 0, z["name"]))


def vergleiche(reihen: list, wingscout: dict | None, messung: dict, tageslicht: set, jetzt_utc: str) -> dict:
    """Je Modell die Maße gegen die Messung, plus die Summen je Tag fürs Gedächtnis.

    Rückgabe {"modelle": [{"id", "name", "art", "masse"}], "tage": {id: {tag: summen}},
              "bestes": id|None}"""
    alle = list(reihen)
    if wingscout:
        alle.append({"id": WINGSCOUT, "name": T(NAMEN[WINGSCOUT]), "art": "bewertung", "reihe": wingscout})
    zeilen, tage = [], {}
    for r in alle:
        v = {t: w for t, w in r["reihe"].items() if t <= jetzt_utc}
        s = summen(v, messung, tageslicht)
        zeilen.append({"id": r["id"], "name": r["name"], "art": r["art"], "masse": masse_aus(s)})
        je_tag = summen_je_tag(v, messung, tageslicht)
        if je_tag:
            tage[r["id"]] = je_tag
    zeilen = _sortiert(zeilen)
    kandidat = next((z for z in zeilen if z["id"] != WINGSCOUT and (z["masse"].get("n") or 0) >= MIN_STUNDEN_BESTES), None)
    return {"modelle": zeilen, "tage": tage, "bestes": kandidat["id"] if kandidat else None}


def gesamt(spots: list) -> list:
    """Über alle Spots eines Rückblicks: je Modell die zusammengezählten Maße
    und an wie vielen Spots es das beste war."""
    je: dict = {}
    for z in spots:
        vg = z.get("vergleich") or {}
        for mid, tage in (vg.get("tage") or {}).items():
            e = je.setdefault(mid, {"id": mid, "name": name(mid), "summen": [], "spots": 0, "bestes": 0})
            e["summen"].extend(tage.values())
            e["spots"] += 1
        if vg.get("bestes") in je:
            je[vg["bestes"]]["bestes"] += 1
    zeilen = [{"id": e["id"], "name": e["name"], "spots": e["spots"], "bestes": e["bestes"],
               "masse": masse_aus(addiere(*e["summen"]))} for e in je.values()]
    return _sortiert(zeilen)


# ── Gedächtnis ───────────────────────────────────────────────────────────────

def _summen_ok(s) -> bool:
    """Tagessummen, mit denen sich rechnen lässt: jede vorhandene Summe endlich."""
    return isinstance(s, dict) and all(_zahl(s[k]) is not None for k in LEER if k in s)


def _ohne_nan(x):
    """NaN und Unendlich → None, überall in einer JSON-Struktur — die letzte
    Sicherung, bevor geschrieben wird."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _ohne_nan(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_ohne_nan(v) for v in x]
    return x


def _bereinigt(daten: dict) -> dict:
    """Was eine Datei von vor 2.1.1 an NaN mitbringen kann, fällt heraus:
    Tagessummen mit einem nicht endlichen Wert ganz (sie würden jede Summe
    vergiften, in die sie eingehen), sonst wird NaN zu None."""
    spots = {}
    for sid, e in daten["spots"].items():
        if not isinstance(e, dict):
            continue
        tage = {}
        alle = e.get("tage") if isinstance(e.get("tage"), dict) else {}
        for tag, t in alle.items():
            if not isinstance(t, dict):
                continue
            m = t.get("m") if isinstance(t.get("m"), dict) else {}
            tage[tag] = dict(t, m={mid: s for mid, s in m.items() if _summen_ok(s)})
        spots[sid] = dict(e, tage=tage)
    return _ohne_nan(dict(daten, spots=spots))


def gedaechtnis_laden(pfad: Path | None = None) -> dict:
    pfad = pfad or GUETE
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        if isinstance(daten, dict) and isinstance(daten.get("spots"), dict):
            return _bereinigt(daten)
    except (OSError, ValueError, RecursionError):
        pass
    return {"version": 1, "spots": {}}


def merken(ergebnis: dict, pfad: Path | None = None) -> dict:
    """Die Tagessummen eines Rückblicks ins Gedächtnis — ein Tag, der schon da
    ist, wird ersetzt (die Messung kann inzwischen vollständiger sein)."""
    from .spotedit import schreibe_atomar
    pfad = pfad or GUETE
    daten = gedaechtnis_laden(pfad)
    if not any((z.get("vergleich") or {}).get("tage") for z in ergebnis.get("spots") or []):
        return daten                                    # nichts zu merken — die Datei bleibt, wie sie ist
    for z in ergebnis.get("spots") or []:
        vg = z.get("vergleich") or {}
        if not vg.get("tage"):
            continue
        eintrag = daten["spots"].setdefault(z["id"], {"tage": {}})
        eintrag.update({"name": z.get("name"), "country": z.get("country")})
        st = z.get("station") or {}
        km = _zahl(st.get("km"))
        for mid, tage in vg["tage"].items():
            for tag, s in tage.items():
                if not _summen_ok(s):                        # NaN aus einer Antwort: dieser Tag nicht
                    continue
                t = eintrag["tage"].setdefault(tag, {"station": st.get("id"), "km": km, "m": {}})
                if t.get("station") != st.get("id"):         # andere Station: der Tag gilt neu
                    t.update({"station": st.get("id"), "km": km, "m": {}})
                t["m"][mid] = s
    daten["stand"] = datetime.now().isoformat(timespec="minutes")
    daten = _ohne_nan(daten)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    # allow_nan=False: was hier noch NaN wäre, ist ein Fehler im Code, kein
    # Wert — die Datei bliebe sonst für den Browser unlesbar.
    schreibe_atomar(pfad, json.dumps(daten, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    return daten


def auswerten(daten: dict) -> dict:
    """Die Rangliste über alles, was je geprüft wurde — gesamt und je Spot."""
    je_modell: dict = {}
    je_spot = []
    alle_tage = set()
    for sid, e in (daten.get("spots") or {}).items():
        je: dict = {}
        for tag, t in (e.get("tage") or {}).items():
            alle_tage.add(tag)
            for mid, s in (t.get("m") or {}).items():
                je.setdefault(mid, []).append(s)
                je_modell.setdefault(mid, {"summen": [], "spots": set(), "tage": set()})
                je_modell[mid]["summen"].append(s)
                je_modell[mid]["spots"].add(sid)
                je_modell[mid]["tage"].add(tag)
        zeilen = _sortiert([{"id": mid, "name": name(mid), "masse": masse_aus(addiere(*ss))} for mid, ss in je.items()])
        beste = [z for z in zeilen if z["id"] != WINGSCOUT and (z["masse"].get("n") or 0) >= MIN_STUNDEN_BESTES]
        ws = next((z for z in zeilen if z["id"] == WINGSCOUT), None)
        if beste:
            je_spot.append({"id": sid, "name": e.get("name") or sid, "tage": len(e.get("tage") or {}),
                            "bestes": beste[0]["name"], "bestes_id": beste[0]["id"], "mae": beste[0]["masse"].get("mae"),
                            "rangfolge": [(z["id"], z["masse"].get("mae")) for z in beste],
                            "zweites": beste[1]["name"] if len(beste) > 1 else None,
                            "zweites_mae": beste[1]["masse"].get("mae") if len(beste) > 1 else None,
                            "wingscout_mae": ws["masse"].get("mae") if ws else None})
    bestes_zaehler: dict = {}
    for z in je_spot:
        bestes_zaehler[z["bestes"]] = bestes_zaehler.get(z["bestes"], 0) + 1
    modelle = _sortiert([{"id": mid, "name": name(mid), "spots": len(e["spots"]), "tage": len(e["tage"]),
                          "bestes": bestes_zaehler.get(name(mid), 0), "masse": masse_aus(addiere(*e["summen"]))}
                         for mid, e in je_modell.items()])
    return {"seit": min(alle_tage) if alle_tage else None, "bis": max(alle_tage) if alle_tage else None,
            "rangfolge": [(z["id"], z["masse"].get("mae")) for z in modelle
                          if z["id"] != WINGSCOUT and (z["masse"].get("n") or 0) >= MIN_STUNDEN_BESTES],
            "tage": len(alle_tage), "spots": len(daten.get("spots") or {}), "modelle": modelle,
            "je_spot": sorted(je_spot, key=lambda z: z["name"].lower())}


def bisher_bestes(zeile: dict, auswertung: dict) -> dict | None:
    """Das Modell, das laut Gedächtnis bisher am besten lag — für die Option
    „Bisher bestes Modell“ im Rückblick.

    Zuerst das beste an diesem Spot (ab 24 gemeinsamen Stunden), sonst das
    beste über alle Spots. Genommen wird nur ein Modell, das an diesem Spot
    in diesem Rückblick eine Reihe hat — ein Regionalmodell, das den Spot
    nicht abdeckt, hilft dort nicht. Die Wingfoilscout-Bewertung zählt nicht:
    sie ist kein Modell."""
    da = {mid for mid in (zeile.get("modellnamen") or {})}
    if not da:
        return None
    spot = next((e for e in auswertung.get("je_spot") or [] if e.get("id") == zeile.get("id")), None)
    for quelle, liste, tage in (("spot", (spot or {}).get("rangfolge") or [], (spot or {}).get("tage")),
                                ("gesamt", auswertung.get("rangfolge") or [], auswertung.get("tage"))):
        for mid, mae in liste:
            if mid in da and mid != WINGSCOUT:
                return {"id": mid, "name": name(mid), "mae": mae, "quelle": quelle, "tage": tage or 0}
    return None
