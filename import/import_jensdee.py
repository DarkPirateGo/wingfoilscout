#!/usr/bin/env python3
"""Importiert die Google-Maps-Liste „Wingfoil Spots" von Jens Dee.

Quelle: https://maps.app.goo.gl/5QM64ZbUbmcit8rf6 (213 Orte, freigegebene Liste)
Aus dem Browser extrahiert wurden 206 Einträge. Ein Teil davon sind gesetzte
Pins, deren Beschriftung die Koordinate selbst ist — die lassen sich exakt
übernehmen. Der Rest sind benannte Orte ohne Koordinate im DOM.
"""
from __future__ import annotations
import math
import re
import sys

import yaml

# Mittelpunkt für den Umkreis — der Beispielpunkt aus config.example.yaml
# (Hamburg, Stadtmitte). Wer die Liste neu einliest, setzt hier den eigenen
# Startpunkt ein, aber nur lokal: ein Wohnort gehört nicht ins Repository.
HOME = (53.55, 9.99)

# ── Pins, deren Name die Koordinate ist ──────────────────────────────────────
DMS_PINS = [
    "41°11'33.8\"N 9°19'11.9\"E",
    "54°05'44.9\"N 8°56'58.0\"E",
    "56°53'06.4\"N 8°37'33.7\"E",
    "36°59'26.8\"N 25°23'30.7\"E",
    "36°04'00.6\"N 5°41'08.0\"W",
    "47°27'15.8\"N 11°42'50.1\"E",
    "54°27'08.1\"N 11°00'17.2\"E",
    "54°28'46.4\"N 11°14'50.5\"E",
    "54°29'06.9\"N 11°00'43.5\"E",
    "54°25'31.9\"N 11°05'51.8\"E",
    "42°58'44.1\"N 17°06'13.0\"E",
    "44°14'51.1\"N 15°11'06.8\"E",
    "43°15'23.7\"N 16°38'03.0\"E",
    "43°15'46.1\"N 16°36'35.5\"E",
    "41°46'06.8\"N 19°35'33.5\"E",
    "42°11'32.5\"N 18°58'00.3\"E",
    "40°57'27.3\"N 19°27'57.7\"E",
    "41°04'12.0\"N 19°27'23.8\"E",
    "41°52'39.2\"N 19°19'27.0\"E",
    "37°01'38.8\"N 25°22'15.3\"E",
    "37°05'45.8\"N 25°22'29.9\"E",
    "56°59'43.2\"N 8°51'51.1\"E",
    "42°34'40.4\"N 9°03'29.7\"W",
    "41°51'12.9\"N 8°52'00.4\"W",
    "57°38'41.8\"N 10°28'08.0\"E",
    "51°55'29.2\"N 3°59'01.6\"E",
    "47°25'59.5\"N 11°43'52.1\"E",
    "49°07'57.9\"N 10°57'27.1\"E",
    "49°07'12.9\"N 10°56'30.2\"E",
    "55°32'18.4\"N 8°09'08.4\"E",
    "57°00'18.0\"N 8°56'15.6\"E",
    "41°11'30.5\"N 9°17'46.3\"E",
    "51°40'42.0\"N 4°07'55.3\"E",
    "46°20'34.4\"N 1°25'48.3\"W",
    "55°53'19.3\"N 8°21'08.8\"E",
    "47°34'22.6\"N 10°11'31.3\"E",
    "47°55'57.3\"N 12°27'44.3\"E",
    "47°50'34.5\"N 12°28'33.7\"E",
    "47°53'08.5\"N 12°32'01.0\"E",
]

# Grobe Gebietszuordnung: (lat_min, lat_max, lon_min, lon_max, Name, Gewässertyp)
REGIONS = [
    (54.35, 54.60, 10.95, 11.10, "Fehmarn West", "sea"),
    (54.35, 54.60, 11.10, 11.35, "Fehmarn Ost", "sea"),
    (53.90, 54.35,  8.60,  9.20, "Nordseeküste Dithmarschen", "sea"),
    (47.80, 48.00, 12.35, 12.60, "Chiemsee", "lake"),
    (49.00, 49.25, 10.80, 11.10, "Fränkisches Seenland", "lake"),
    (47.45, 47.70, 10.05, 10.35, "Allgäu / Forggensee", "lake"),
    (47.35, 47.55, 11.60, 11.85, "Achensee", "lake"),
    (51.80, 52.10,  3.85,  4.20, "Zuid-Holland", "sea"),
    (51.55, 51.80,  4.00,  4.30, "Zeeland / Volkerak", "lagoon"),
    (46.20, 46.50, -1.60, -1.30, "Vendée", "sea"),
    (55.30, 58.00,  8.00, 11.00, "Dänemark", "sea"),
    (40.50, 42.30, 19.00, 20.00, "Albanien / Montenegro", "sea"),
    (42.80, 44.50, 15.00, 17.50, "Kroatien", "sea"),
    (40.80, 41.40,  9.10,  9.50, "Sardinien Nordost", "sea"),
    (36.80, 37.20, 25.20, 25.50, "Naxos", "sea"),
    (35.80, 36.30, -6.00, -5.50, "Tarifa", "sea"),
    (41.70, 43.00, -9.20, -8.60, "Galicien / Nordportugal", "sea"),
]


def dms_to_dec(text: str) -> tuple[float, float]:
    parts = re.findall(r"(\d+)°(\d+)'([\d.]+)\"([NSEW])", text)
    if len(parts) != 2:
        raise ValueError(f"nicht parsebar: {text}")
    out = []
    for d, m, s, hemi in parts:
        val = int(d) + int(m) / 60 + float(s) / 3600
        if hemi in ("S", "W"):
            val = -val
        out.append(round(val, 5))
    return out[0], out[1]


def haversine_km(a, b) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(x))


def region_of(lat, lon):
    for la0, la1, lo0, lo1, name, wb in REGIONS:
        if la0 <= lat <= la1 and lo0 <= lon <= lo1:
            return name, wb
    return None, "sea"


def main(max_km: float = 1100.0) -> None:
    rows, skipped = [], []
    counters: dict[str, int] = {}
    for pin in DMS_PINS:
        lat, lon = dms_to_dec(pin)
        dist = haversine_km(HOME, (lat, lon))
        region, wb = region_of(lat, lon)
        if dist > max_km:
            skipped.append((pin, region or "unbekannt", dist))
            continue
        base = region or f"Pin {lat:.2f}/{lon:.2f}"
        counters[base] = counters.get(base, 0) + 1
        label = f"{base} {counters[base]}"
        umlaut = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
                                "Ä": "ae", "Ö": "oe", "Ü": "ue", "é": "e", "è": "e"})
        slug = re.sub(r"[^a-z0-9]+", "-", label.translate(umlaut).lower()).strip("-")
        rows.append({
            "id": f"jd-{slug}", "name": f"{label} (Jens-Dee-Pin)",
            "lat": lat, "lon": lon, "water_body": wb, "dist": dist, "pin": pin,
        })

    print(f"{len(rows)} Pins im Radius von {max_km:.0f} km, {len(skipped)} zu weit weg\n")
    for r in sorted(rows, key=lambda r: r["dist"]):
        print(f"  {r['dist']:6.0f} km  {r['lat']:.5f}, {r['lon']:.5f}  {r['name']}")
    print("\nzu weit:")
    for pin, region, dist in sorted(skipped, key=lambda s: s[2]):
        print(f"  {dist:6.0f} km  {region:28s} {pin}")

    entries = []
    for r in sorted(rows, key=lambda r: r["dist"]):
        entries.append({
            "id": r["id"], "name": r["name"], "lat": r["lat"], "lon": r["lon"],
            "water_body": r["water_body"], "shallow": "none", "seagrass": "none",
            "season": [3, 4, 5, 6, 7, 8, 9, 10, 11], "sectors": [],
            "notes": (f"Gesetzter Pin aus Jens Dees Liste, Originalbeschriftung {r['pin']}. "
                      "Koordinate exakt, Name und nutzbare Windrichtungen unbekannt — bitte ergänzen."),
            "source": "https://maps.app.goo.gl/5QM64ZbUbmcit8rf6",
            "verified": True, "sectors_unknown": True,
        })
    with open("jensdee_pins.yaml", "w", encoding="utf-8") as fh:
        fh.write("# Automatisch erzeugt aus der Google-Maps-Liste 'Wingfoil Spots' von Jens Dee\n"
                 "# https://maps.app.goo.gl/5QM64ZbUbmcit8rf6\n"
                 "# Koordinaten exakt (die Pins tragen sie als Namen), Windsektoren unbekannt.\n\n")
        yaml.safe_dump(entries, fh, allow_unicode=True, sort_keys=False, width=100)
    print(f"\n→ jensdee_pins.yaml geschrieben ({len(rows)} Einträge)")


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 1100.0)
