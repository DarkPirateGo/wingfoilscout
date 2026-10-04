"""Geometrie: Distanzen, Fahrzeitschätzung, Windrichtungs-Sektoren."""
from __future__ import annotations
import functools
import math

from . import i18n
from .i18n import T, N_

EARTH_R_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(math.sqrt(a))


def drive_estimate_h(dist_km: float, avg_speed_kmh: float, detour_factor: float) -> float:
    """Grobe Fahrzeit aus Luftlinie. Ersetzt kein Routing — Etappe 03."""
    return (dist_km * detour_factor) / max(avg_speed_kmh, 1.0)


def in_sector(deg: float, start: float, end: float) -> bool:
    """Liegt deg im Sektor start..end (im Uhrzeigersinn, darf über Nord laufen)?"""
    deg %= 360
    start %= 360
    end %= 360
    if start <= end:
        return start <= deg <= end
    return deg >= start or deg <= end


# Die 16 Kürzel als ein Text: so sieht die Übersetzung die ganze Rose („O“ ist
# Ost), und kein Kürzel fällt mit einem gleichlautenden Schlüssel zusammen —
# „NW“ heißt in report.py Niedrigwasser. Die Übersetzung muss 16 durch
# Leerzeichen getrennte Kürzel behalten, sonst bleibt es bei der deutschen Rose.
KOMPASS = N_("N NNO NO ONO O OSO SO SSO S SSW SW WSW W WNW NW NNW")


def richtung(i: int) -> str:
    """Kürzel Nummer `i` (0 = Nord, im Uhrzeigersinn) in der geltenden Sprache."""
    names = T(KOMPASS).split()
    if len(names) != 16:
        names = KOMPASS.split()
    return names[i % 16]


# Je Sprache, Rose und Richtung ein Text — statt eines neuen an jeder Stunde.
_RICHTUNGEN: dict[tuple[str, str, int], i18n.Text] = {}


def compass(deg: float) -> str:
    """Das Kürzel der Himmelsrichtung — Anzeigetext, nirgends verglichen,
    deshalb gleich übersetzt. Seit 2.3.0 ein `i18n.Text`: der Report schreibt
    dieselbe Suche in allen vier Sprachen und setzt das Kürzel dort neu."""
    i = int((deg % 360) / 22.5 + 0.5) % 16
    schluessel = (i18n.aktuell(), T(KOMPASS), i)
    text = _RICHTUNGEN.get(schluessel)
    if text is None:
        text = _RICHTUNGEN[schluessel] = i18n.Text(richtung(i), functools.partial(richtung, i), schluessel[0])
    return text


def angle_diff(a: float, b: float) -> float:
    """Kleinster Winkel zwischen zwei Richtungen, 0..180."""
    d = abs((a - b) % 360)
    return min(d, 360 - d)


def shore_relation(wind_from: float, shore_bearing: float) -> str:
    """Windrichtung relativ zum Ufer. shore_bearing = Blick vom Ufer aufs Wasser."""
    rel = angle_diff(wind_from, shore_bearing)
    if rel <= 25:
        return "auflandig"
    if rel <= 65:
        return "side-on"
    if rel <= 115:
        return "sideshore"
    if rel <= 155:
        return "side-off"
    return "ablandig"


# ── Startpunkt aus einer Texteingabe ─────────────────────────────────────────
# Damit man unterwegs einfach hineinkopieren kann, was das Telefon gerade
# hergibt: Dezimalgrad, Grad/Minuten/Sekunden oder ein Google-Maps-Link.

import re                                                        # noqa: E402

# Leerraum zwischen den Teilen ist begrenzt. Mit `\s*` vor und hinter jedem
# optionalen Teil lief die Suche kubisch: ein CSV-Feld aus `1°1`, 2000
# Leerzeichen und einem `x` kostete 21 Sekunden, 100 KB rund einen Monat —
# so lange lief der Import, und jede Suche bekam 409 (Review 04.10.2026, C1).
# `parse_position` fasst Leerraum vorher zu einem Zeichen zusammen; die
# Grenze im Muster ist die zweite Sicherung.
_DMS = re.compile(
    r"(\d{1,3})\s{0,3}[°d:]\s{0,3}(\d{1,2}(?:[.,]\d+)?)\s{0,3}['′m:]?\s{0,3}"
    r"(?:(\d{1,2}(?:[.,]\d+)?)\s{0,3}[\"″s]?)?\s{0,3}([NSEWO])", re.I)
# Dieselbe Form mit der Himmelsrichtung vorn, wie GPS-Geräte sie schreiben:
# „N 51°45.750 E 3°51.233“. Bis 2.1.0 fand `_DMS` darin nur einen Treffer
# (die Zahlen der Breite mit dem E der Länge), und die Zahlensuche machte aus
# allem (51.0, 45.75).
_DMS_VORN = re.compile(
    r"\b([NSEWO])\s{0,3}(\d{1,3})\s{0,3}[°d:]\s{0,3}(\d{1,2}(?:[.,]\d+)?)\s{0,3}['′m:]?"
    r"(?:\s{0,3}(\d{1,2}(?:[.,]\d+)?)\s{0,3}[\"″s]?)?", re.I)
_NUM = re.compile(r"(?:([NSEWO])\s*)?(-?\d{1,3}(?:[.,]\d+)?)\s*°?\s*(?:([NSEWO])\b)?", re.I)
# Eine Koordinate, ein Link oder eine Zeile mit Namen ist nie länger; ein
# CSV-Feld darf 128 KB haben.
MAX_EINGABE = 2000


def _f(x: str) -> float:
    return float(x.replace(",", "."))


def _dms_paar(treffer) -> tuple[float, float] | None:
    """[(Grad, Minuten, Sekunden, Himmelsrichtung)] → (lat, lon), wenn unter
    den ersten beiden eine Breite und eine Länge sind."""
    vals = {}
    for deg, minutes, sec, hemi in treffer[:2]:
        v = int(deg) + _f(minutes) / 60 + (_f(sec) / 3600 if sec else 0.0)
        h = hemi.upper()
        if h in ("S", "W"):
            v = -v
        vals["lat" if h in ("N", "S") else "lon"] = v
    if "lat" in vals and "lon" in vals:
        return vals["lat"], vals["lon"]
    return None


def _plausible(lat: float, lon: float):
    if abs(lat) > 90 and abs(lon) <= 90:            # vertauscht eingegeben
        lat, lon = lon, lat
    if abs(lat) > 90 or abs(lon) > 180:
        return None
    return round(lat, 6), round(lon, 6)


def parse_position(text: str):
    """'51.7625, 3.854' · '51°45'45"N 3°51'14"E' · Maps-Link → (lat, lon) oder None.

    Bewusst tolerant: Komma oder Punkt als Dezimaltrenner, N/S/E/W/O in beiden
    Schreibrichtungen, Vorzeichen. Was nicht plausibel ist, kommt als None
    zurück — der Aufrufer bleibt dann beim Startpunkt aus der Konfiguration.
    """
    if not text or not str(text).strip():
        return None
    # Leerraum zu je einem Leerzeichen: die Muster unten sehen dasselbe wie
    # vorher, aber keine langen Läufe mehr, an denen sie sich festbeißen.
    s = " ".join(str(text).split())
    if len(s) > MAX_EINGABE:
        return None

    if "://" in s or "maps." in s.lower():           # Google-/OSM-Link
        m = re.search(r"(?:@|[?&](?:q|mlat|ll)=|/)(-?\d{1,3}\.\d+)[,/](-?\d{1,3}\.\d+)", s)
        # Steht keine Koordinate drin, dann gibt es keine. Weiterzusuchen hieße,
        # aus einer Orts-ID wie ?cid=12345 Zahlen zu klauben und als Position
        # auszugeben — eine erfundene Koordinate ist schlimmer als keine.
        return _plausible(float(m.group(1)), float(m.group(2))) if m else None

    dms = _DMS.findall(s)
    if len(dms) >= 2:
        paar = _dms_paar(dms)
        if paar:
            return _plausible(*paar)
    # Erst wenn die Richtung hinten nichts ergibt: sonst läse „…45"N 3°51'…“
    # das N als Richtung der Länge.
    vorn = [(deg, minutes, sec, hemi) for hemi, deg, minutes, sec in _DMS_VORN.findall(s)]
    if len(vorn) >= 2:
        paar = _dms_paar(vorn)
        if paar:
            return _plausible(*paar)

    found = []
    for m in _NUM.finditer(s):
        if not m.group(2):
            continue
        hemi = (m.group(1) or m.group(3) or "").upper()
        v = _f(m.group(2))
        if hemi in ("S", "W"):
            v = -abs(v)
        found.append((hemi, v))
        if len(found) == 2:
            break
    if len(found) == 2:
        by_axis = {}
        for hemi, v in found:
            if hemi in ("N", "S"):
                by_axis["lat"] = v
            elif hemi in ("E", "W", "O"):
                by_axis["lon"] = v
        if "lat" in by_axis and "lon" in by_axis:
            return _plausible(by_axis["lat"], by_axis["lon"])
        return _plausible(found[0][1], found[1][1])
    return None
