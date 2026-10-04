#!/usr/bin/env python3
"""Was sich an einer Koordinate ohne Karte und ohne Netz nachprüfen lässt.

Der Katalog trägt bei rund hundert Spots `verified: false`: die Koordinate
stammt aus einer importierten Liste, bei der Takeout-Liste aus einer gerundeten
Spalte, und niemand hat je hingeschaut. Der Geometrielauf beantwortet davon
schon eine Frage — *liegt der Punkt im Wasser?* —, und er beantwortet sie für
fast alle mit Ja.

Er beantwortet aber nicht die zweite: *liegt er im richtigen Wasser?* Genau
das ist der Fehler, den eine gerundete Koordinate erzeugt. Dieses Werkzeug
vergleicht deshalb den Namen des Spots mit dem Namen der Wasserfläche, in der
der Punkt laut OpenStreetMap liegt. Die Daten dafür liegen schon da: der
Geometrielauf hat den Overpass-Auszug je Spot in `cache/geom` abgelegt, samt
`name`-Tags. Das Werkzeug braucht also kein Netz.

Was es NICHT kann, und zwar grundsätzlich:

  · Am Meer gibt es keine benannte Fläche. Die Küstenlinie trennt nur Land von
    Wasser; ob der Punkt am gemeinten Strand liegt oder drei Kilometer weiter,
    steht in keinem Tag.
  · Ein unbenannter Baggersee bleibt unbenannt. Kein Name, kein Vergleich.
  · Ob man dort fahren darf, parken kann oder der Einstieg taugt, sagt kein
    Polygon. Das bleibt Sache dessen, der hinfährt.

Deshalb bestätigt es nichts von selbst, sondern sortiert in vier Gruppen und
überlässt die Entscheidung dem Menschen. Mit `--setze-bestaetigt` schreibt es
für die eindeutige Gruppe A `verified: true` in den Katalog.
"""
from __future__ import annotations
import argparse
import gzip
import json
import math
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wingscout.geometry import point_in_rings, projector          # noqa: E402
from wingscout.spots import load_spots, KatalogFehler             # noqa: E402

WASSER_NATURAL = {"water", "bay", "strait"}
WASSER_LANDUSE = {"reservoir", "basin"}

# Wörter, die in Spot- und Gewässernamen vorkommen, ohne etwas zu unterscheiden.
GENERISCH = {
    "see", "lake", "lac", "etang", "lago", "laguna", "lagune", "meer", "mare",
    "stausee", "baggersee", "badesee", "weiher", "teich", "bucht", "baie",
    "bay", "golfe", "golf", "strand", "plage", "playa", "spiaggia", "praia",
    "beach", "strandbad", "ufer", "nordufer", "sudufer", "ostufer", "westufer",
    "nord", "sud", "ost", "west", "nordwest", "nordost", "sudwest", "sudost",
    "kite", "kitespot", "kitesurf", "surf", "surfspot", "windsurf", "wingfoil",
    "spot", "beim", "bei", "der", "die", "das", "dem", "den", "des", "du",
    "de", "la", "le", "les", "el", "il", "lo", "di", "da", "van", "het",
    "the", "of", "and", "und", "et", "am", "an", "auf", "in", "im", "zum",
    "zur", "club", "camping", "campingplatz", "parkplatz", "parking", "port",
    "hafen", "marina", "insel", "ile", "isola", "isla", "reservoir",
    # Aus der Takeout- und der Jens-Dee-Liste: Namen, die den Stellplatz oder
    # die Schule meinen, nicht das Gewässer.
    "stellplatz", "womo", "wohnmobil", "campground", "area", "beacharea",
    "badestelle", "liegewiese", "surferwiese", "schule", "ecole",
    "escuela", "scuola", "vela", "nautique", "surfing", "kitesurfing",
    "kiteboarding", "association", "verein", "center", "centre", "station",
    "zugang", "einstieg", "slipstelle", "rampe", "steg",
}


UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
                         "Ä": "ae", "Ö": "oe", "Ü": "ue"})


def _glatt(text: str) -> str:
    """Kleinschreibung, deutsche Umlaute ausgeschrieben, sonstige Akzente weg.

    Die Reihenfolge ist wichtig: erst ä→ae, dann die restlichen Zeichen über
    NFKD entkleiden. Umgekehrt würde aus „Müritz" ein „muritz" und der
    Vergleich mit einer Liste, die „Mueritz" schreibt, ginge daneben.
    """
    roh = unicodedata.normalize("NFKD", text.lower().translate(UMLAUTE))
    return "".join(c for c in roh if not unicodedata.combining(c))


def normalisiere(text: str) -> list[str]:
    """Kleinschreibung, Akzente weg, nur unterscheidende Wörter."""
    roh = _glatt(text)
    worte = []
    for w in "".join(c if c.isalnum() else " " for c in roh).split():
        if len(w) >= 4 and w not in GENERISCH:
            worte.append(w)
    return worte


def _flach(text: str) -> str:
    roh = _glatt(text)
    return " ".join("".join(c if c.isalnum() else " " for c in roh).split())


def namen_vergleich(spot_name: str, osm_name: str) -> str:
    """"passt" · "widerspricht" · "unklar".

    Der dritte Wert ist der wichtigste. „Parkplatz", „beacharea",
    „Stellplatz Womo" — die halbe Takeout-Liste trägt Namen, die über das
    Gewässer nichts aussagen. Ohne diesen Wert landet jeder davon als
    Widerspruch in der Liste, und der Mensch arbeitet lauter Fehlalarme ab.

    „Lac du Der" gegen „Lac du Der-Chantecoq" soll passen, obwohl nach dem
    Streichen der Füllwörter kein Wort übrig bleibt — deshalb zusätzlich der
    Vergleich der ganzen, geglätteten Zeichenketten.
    """
    ganz_a, ganz_b = _flach(spot_name), _flach(osm_name)
    if ganz_a and ganz_b and (ganz_a in ganz_b or ganz_b in ganz_a):
        return "passt"
    a, b = set(normalisiere(spot_name)), set(normalisiere(osm_name))
    if not a or not b:
        return "unklar"
    if a & b:
        return "passt"
    # Teilwörter: „Brombachsee" in „Kleiner Brombachsee"
    if any(x in y or y in x for x in a for y in b if min(len(x), len(y)) >= 5):
        return "passt"
    return "widerspricht"


def flaechen(data: dict, lat0: float, lon0: float):
    """[(name|None, [ring, …]), …] — Wasserflächen in lokalen Metern."""
    to_xy, _ = projector(lat0, lon0)
    raus = []
    for e in data.get("elements", []):
        t = e.get("tags") or {}
        if t.get("natural") not in WASSER_NATURAL and t.get("landuse") not in WASSER_LANDUSE:
            continue
        name = t.get("name")
        if e.get("type") == "way" and e.get("geometry"):
            pts = [to_xy(p["lat"], p["lon"]) for p in e["geometry"]]
            if len(pts) > 3:
                raus.append((name, [pts]))
        elif e.get("type") == "relation":
            ringe = [[to_xy(p["lat"], p["lon"]) for p in m["geometry"]]
                     for m in e.get("members", [])
                     if m.get("geometry") and m.get("role") in ("outer", "", None)
                     and len(m["geometry"]) > 3]
            if ringe:
                raus.append((name, ringe))
    return raus


def pruefe(spot: dict, eintrag: dict | None, cache_ordner: Path) -> dict:
    """Ein Urteil je Spot: gruppe, Begründung, gefundener Gewässername."""
    pfad = cache_ordner / f"{spot['id']}_25km.json.gz"
    if not pfad.exists():
        return {"gruppe": "D", "grund": "kein Overpass-Auszug im Zwischenspeicher",
                "gewaesser": None}
    # Der Geometrielauf hat kein Wasser in drei Kilometern gefunden: dann ist
    # der Pin an Land, und ob die Strahlen der Rose irgendwo Wasser trafen,
    # spielt keine Rolle. Bis 1.8.0 landete so ein Punkt in Gruppe B („Meer
    # oder unbenannte Fläche“) — der Prüfstand hat es an der Schwäbischen Alb
    # gezeigt.
    if eintrag and eintrag.get("wasser") is False:
        return {"gruppe": "D", "gewaesser": None,
                "grund": "kein Wasser innerhalb von 3 km um den Pin — liegt an Land"}

    versatz = 0.0
    if eintrag:
        dx, dy = (eintrag.get("origin_offset_m") or [0, 0])[:2]
        versatz = math.hypot(float(dx), float(dy))

    try:
        data = json.loads(gzip.open(pfad).read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        return {"gruppe": "D", "grund": f"Auszug nicht lesbar ({exc})", "gewaesser": None}

    fl = flaechen(data, spot["lat"], spot["lon"])
    # Erst den Pin selbst prüfen, dann die Stelle, auf die der Geometrielauf
    # ihn geschoben hat — die liegt per Definition im Wasser.
    for x, y, woher in ((0.0, 0.0, "Pin"), (float(versatz and (eintrag["origin_offset_m"][0])),
                                            float(versatz and (eintrag["origin_offset_m"][1])),
                                            "versetzter Punkt")):
        drin = [n for n, ringe in fl if point_in_rings(x, y, ringe)]
        if not drin:
            continue
        benannt = [n for n in drin if n]
        if not benannt:
            return {"gruppe": "B", "gewaesser": None,
                    "grund": f"{woher} liegt in einer unbenannten Wasserfläche"}
        urteile = [(namen_vergleich(spot["name"], n), n) for n in benannt]
        if any(u == "passt" for u, _ in urteile):
            name = next(n for u, n in urteile if u == "passt")
            return {"gruppe": "A", "gewaesser": name,
                    "grund": f"{woher} liegt in „{name}“ — Name passt zum Spot"}
        if all(u == "unklar" for u, _ in urteile):
            return {"gruppe": "B", "gewaesser": benannt[0],
                    "grund": f"{woher} liegt in „{benannt[0]}“ — der Spotname sagt nichts dazu"}
        name = next(n for u, n in urteile if u == "widerspricht")
        return {"gruppe": "C", "gewaesser": name,
                "grund": f"{woher} liegt in „{name}“ — der Name widerspricht"}

    if versatz > 300:
        return {"gruppe": "D", "gewaesser": None,
                "grund": f"der Pin liegt an Land, {versatz:.0f} m bis zum Wasser"}
    return {"gruppe": "B", "gewaesser": None,
            "grund": "Meer oder unbenannte Fläche — kein Name zum Vergleichen"}


TITEL = {
    "A": "Name bestätigt — der Punkt liegt im richtigen, benannten Gewässer",
    "B": "Im Wasser, aber nichts zu vergleichen — plausibel, nicht belegt",
    "C": "Widerspruch — der Punkt liegt in einem anders benannten Gewässer",
    "D": "Der Pin liegt an Land (bei Strandspots oft der Parkplatz)",
}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--spots", default=str(ROOT / "spots.yaml"))
    p.add_argument("--geometry", default=str(ROOT / "geometry.json"))
    p.add_argument("--cache", default=str(ROOT / "cache" / "geom"))
    p.add_argument("--alle", action="store_true",
                   help="auch schon bestätigte Spots prüfen")
    p.add_argument("--setze-bestaetigt", action="store_true",
                   help="für Gruppe A `verified: true` in den Katalog schreiben")
    args = p.parse_args()

    spots = load_spots(args.spots)
    if not args.alle:
        spots = [s for s in spots if not s.get("verified")]
    store = json.loads(Path(args.geometry).read_text(encoding="utf-8"))
    cache = Path(args.cache)

    gruppen: dict[str, list] = {"A": [], "B": [], "C": [], "D": []}
    for spot in spots:
        urteil = pruefe(spot, store.get(spot["id"]), cache)
        gruppen[urteil["gruppe"]].append((spot, urteil))

    print(f"{len(spots)} Spots geprüft, ohne Netz, aus dem Overpass-Zwischenspeicher.\n")
    for schluessel in ("C", "D", "A", "B"):
        eintraege = gruppen[schluessel]
        if not eintraege:
            continue
        print(f"── {schluessel}: {TITEL[schluessel]} ({len(eintraege)})")
        for spot, urteil in eintraege:
            print(f"   {spot['name'][:40]:42s} {urteil['grund']}")
        print()

    if args.setze_bestaetigt and gruppen["A"]:
        from wingscout import spotedit
        for spot, _ in gruppen["A"]:
            spotedit.set_flag(args.spots, spot["id"], "verified", True)
        print(f"{len(gruppen['A'])} Spots der Gruppe A auf `verified: true` gesetzt.")
    elif gruppen["A"]:
        print(f"Mit --setze-bestaetigt werden die {len(gruppen['A'])} Spots der Gruppe A "
              f"im Katalog bestätigt.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KatalogFehler as exc:                      # Meldung statt Traceback
        raise SystemExit(str(exc))
