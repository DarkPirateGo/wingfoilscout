#!/usr/bin/env python3
"""Google-Takeout-Liste in den Katalog übernehmen — einmalig, nachvollziehbar.

Die Datei hat zwei Sorten Koordinaten, und der Unterschied ist wichtig:

  · Zeilen mit `/maps/search/<lat>,<lon>` in der Adresse tragen einen selbst
    gesetzten Pin — exakt, `verified: true`.
  · Zeilen mit einer Orts-ID haben nur die nachträglich ergänzten Spalten
    Breitengrad/Längengrad. Die sind auf drei bis vier Stellen gerundet und
    teilweise mehrfach vergeben (Tomtom Kite Leucate und Franqui beach haben
    denselben Wert, liegen aber Kilometer auseinander). Also `verified: false`.

Aufruf:  python3 import/import_takeout.py [--trocken] [--mit-notizen]

Die eigenen Notizen aus der Liste bleiben ohne `--mit-notizen` draußen — auch
als Name: der Katalog ist öffentlich, und in einer eigenen Liste steht, was
man sich selbst aufschreibt (Review 04.10.2026, D5). Gelesen werden sie
trotzdem, aber nur für die grobe Gewässerart, die als ein Wort im Katalog
landet.

Die Takeout-Datei selbst liegt nicht im Repository (`.gitignore`,
`import/*.csv`): ein Google-Export ist eine persönliche Liste mit
eigenen Notizen. Wer das Skript nutzt, legt seinen Export unter dem Namen in
`QUELLE` ab.
"""
from __future__ import annotations
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wingscout import ingest                                    # noqa: E402
from wingscout.geo import haversine_km                          # noqa: E402
from wingscout.spots import load_spots, KatalogFehler           # noqa: E402

QUELLE = ROOT / "import" / "takeout-2026-09-13.csv"
PIN = re.compile(r"/maps/search/(-?\d+\.\d+),(-?\d+\.\d+)")
DMS_NAME = re.compile(r"^\d{1,3}°\d{1,2}'")
UNBRAUCHBAR = "Koordinate unbrauchbar (nan, inf oder außerhalb von ±90/±180)"

# Einträge, die keine Spots sind — Adressen und Gebäude aus derselben Liste.
# Als Muster, nicht als Namen: eine Google-Liste enthält auch Privatadressen,
# und die gehören nicht in ein Skript, das im Repository liegt.
NICHT_SPOT = re.compile(r"(straße|strasse|str\.|weg|platz|gasse|allee|ring)\s*\d+[a-z]?\b|sporthalle|turnhalle", re.I)

SEE = ("see", "lac ", "lac d", "lago", "etang", "étang", "lagoa", "stausee", "weiher")
MEER = ("strand", "beach", "plage", "playa", "praia", "spiaggia", "plaža", "paralia",
        "havn", "fyr", "bucht", "mare", "bad", "dam", "vig", "mer", "marina", "baia",
        "kitespot", "surfspot", "tarifa", "médano")


def gewaesser(name: str, notiz: str) -> str:
    """Grobe Einordnung aus dem Namen. Im Zweifel „unknown" — die Ufergeometrie
    klärt es später, und eine falsche Angabe wäre schlimmer als keine."""
    text = f"{name} {notiz}".lower()
    if any(w in text for w in SEE):
        return "lake"
    if any(w in text for w in MEER):
        return "sea"
    return "unknown"


# Wörter, die eine Zeile als Beschreibung ausweisen und nicht als Namen.
KEIN_NAME = ("wind", "richtung", "welle", "parken", "tief", "spot von", "spot vanberlos",
             "checken", "erkunden", "potentiell", "keine ahnung", "hier ", "bei ", "http",
             "könnte", "nicht bei", "am besten", "super", "stehen am")


def lesbarer_name(titel: str, notiz: str, lat: float, lon: float) -> str:
    """Ein Name, der auch in einem Ranking noch etwas sagt.

    „Gesetzte Markierung" und reine Gradangaben taugen nicht. Die erste
    Notizzeile schon — aber nur, wenn sie wie ein Name aussieht und nicht wie
    eine Beschreibung; sonst hieße ein Spot am Ende „Beste Windrichtung N-NO".
    """
    titel = (titel or "").strip()
    if titel and titel != "Gesetzte Markierung" and not DMS_NAME.match(titel):
        return titel
    erste = next((z.strip() for z in (notiz or "").splitlines()
                  if z.strip() and not z.strip().startswith("http")), "")
    if erste and len(erste) <= 25 and not any(w in erste.lower() for w in KEIN_NAME):
        return erste.rstrip(" .,!")
    return f"Pin {lat:.4f}, {lon:.4f}"


def auswerten(rows, vorhanden, mit_notizen: bool = False) -> tuple[list[dict], list[tuple[str, str]]]:
    """Zeilen der Takeout-Datei → (neue Katalogeinträge, übersprungene als (Name, Grund))."""
    belegt = {s["id"] for s in vorhanden}
    neu, uebersprungen = [], []
    for r in rows:
        titel = (r.get("Titel") or "").strip()
        notiz = (r.get("Notiz") or "").strip()
        url = (r.get("URL") or "").strip()

        pin = PIN.search(url)
        if pin:
            lat, lon, genau = float(pin.group(1)), float(pin.group(2)), True
        else:
            try:
                lat = float((r.get("Breitengrad") or "").strip())
                lon = float((r.get("Längengrad") or "").strip())
            except ValueError:
                uebersprungen.append((titel or "(ohne Titel)", "keine Koordinate"))
                continue
            genau = False
        # Endlich und im Bereich, wie beim Import in der Oberfläche (Review
        # 25.09.2026, S7): `nan` schrieb bis 2.1.0 ein `.nan` in den Katalog und
        # machte ihn unlesbar, `inf` brach den Import mittendrin ab.
        if not ingest.koordinate_ok(lat, lon):
            uebersprungen.append((titel or "(ohne Titel)", UNBRAUCHBAR))
            continue

        if NICHT_SPOT.search(titel):
            uebersprungen.append((titel, "kein Wasserspot"))
            continue
        if not titel and not notiz:
            uebersprungen.append((f"{lat:.4f}, {lon:.4f}", "weder Name noch Notiz"))
            continue

        # Auch ein Name aus der ersten Notizzeile ist eigener Text
        name = lesbarer_name(titel, notiz if mit_notizen else "", lat, lon)

        doppelt = ingest.too_close(lat, lon, vorhanden, limit_km=0.3)
        if doppelt:
            uebersprungen.append((name, f"schon im Katalog: {doppelt['name']}"))
            continue
        gleich = next((e for e in neu if haversine_km(lat, lon, e["lat"], e["lon"]) <= 0.05), None)
        if gleich:
            gleich.setdefault("_auch", []).append(name)
            uebersprungen.append((name, f"gleiche Näherung wie {gleich['name']}"))
            continue

        eintrag = ingest.build_entry(name, lat, lon, None, belegt)
        belegt.add(eintrag["id"])
        eintrag["water_body"] = gewaesser(titel, notiz)
        eintrag["verified"] = genau
        eintrag["source"] = url or "Google-Takeout-Liste"
        # Nur die eigene Notiz aus der Liste, und nur auf Wunsch. Herkunft und
        # Genauigkeit stehen in `source` und `verified`, die Gewässerart in
        # `water_body` — bis 1.19.2 wiederholte die Notiz das als Fließtext,
        # und der stand dann in jedem Report (163-mal derselbe Satz).
        eintrag["notes"] = " ".join(notiz.split()) if mit_notizen else ""
        neu.append(eintrag)

    for e in neu:
        auch = e.pop("_auch", None)
        if auch:
            e["notes"] = ((e["notes"].rstrip(".") + ". ") if e["notes"] else "") + \
                "Dieselbe Näherungskoordinate tragen außerdem: " + ", ".join(auch) + "."
    return neu, uebersprungen


def main(trocken: bool = False, mit_notizen: bool = False) -> int:
    rows = list(csv.DictReader(QUELLE.open(encoding="utf-8")))
    neu, uebersprungen = auswerten(rows, load_spots(ROOT / "spots.yaml"), mit_notizen)

    print(f"{len(rows)} Zeilen gelesen → {len(neu)} neue Spots, {len(uebersprungen)} übersprungen")
    print(f"   davon exakte Pins: {sum(1 for e in neu if e['verified'])}, "
          f"gerundete Spaltenwerte: {sum(1 for e in neu if not e['verified'])}")
    print("   eigene Notizen: " + ("übernommen (--mit-notizen)" if mit_notizen
                                  else "nicht übernommen (mit --mit-notizen schon)"))
    for name, grund in uebersprungen:
        print(f"   übersprungen · {name[:42]:42s} {grund}")

    if trocken:
        print("\nTrockenlauf — nichts geschrieben.")
        return 0

    kopf = ("\n# ─────────────────────────────────────────────────────────────────────────────\n"
            "#  Addendum · own Google Takeout list\n"
            "#\n"
            "#  `verified: true`  = the coordinate is a pin placed by hand.\n"
            "#  `verified: false` = the coordinate comes from the column added later,\n"
            "#                      rounded and in places assigned more than once.\n"
            "#  `water_body: unknown` = can't be derived from the name; once computed, the\n"
            "#                      shoreline geometry tells what kind of water the point is in.\n"
            + ("#  The notes are the list's own, imported unchanged.\n" if mit_notizen
               else "#  The list's own notes were not imported.\n")
            + "# ─────────────────────────────────────────────────────────────────────────────\n")
    with (ROOT / "spots.yaml").open("a", encoding="utf-8") as fh:
        fh.write(kopf)
    ingest.append_to_yaml(ROOT / "spots.yaml", neu)
    print(f"\n{len(neu)} Spots an spots.yaml angehängt.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main("--trocken" in sys.argv, "--mit-notizen" in sys.argv))
    except KatalogFehler as exc:                      # Meldung statt Traceback
        raise SystemExit(str(exc))
