"""Wassergeometrie aus OpenStreetMap über die Overpass-API.

Geladen werden Küstenlinien und Wasserflächen im Umkreis eines Spots. Das
Ergebnis wird auf Platte gelegt und nie wieder geholt — Küsten verschieben sich
selten, und die Overpass-Server sind ein Gemeinschaftsgut, das man nicht ohne
Not belastet.

Server: https://overpass-api.de/api/interpreter (Nutzungsregeln beachten:
wenige Abfragen, Pausen dazwischen, ehrlicher User-Agent).
"""
from __future__ import annotations
import gzip
import json
import math
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .. import CACHE
from ..i18n import T, TN, N_                                      # noqa: F401
from .netz import lies, cache_lesen, ablegen, ablegen_offen, USER_AGENT   # noqa: F401 — USER_AGENT gehört zur Schnittstelle

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
TIMEOUT = 330
# Frist für den ganzen Antwortkörper (netz.lies): große Auszüge brauchen auf
# einer langsamen Leitung Minuten, aber nicht Stunden.
FRIST_S = 600

# Die Abfrage läuft in zwei Stufen, und das aus einem gemessenen Grund: Ein
# einziger Spot in Friesland lieferte mit der naiven Fassung 134 MB, weil im
# Umkreis von 40 km tausende Gräben, Teiche und Kanäle liegen. Mit Größenfilter
# waren es 78 MB, bei 25 km Umkreis 15 MB.
#
# NAH (wenige Kilometer, ungefiltert) holt das Gewässer, auf dem der Spot
# liegt — auch wenn es ein Baggersee von 400 Metern ist, den jeder Größenfilter
# wegwerfen würde.
#
# FERN (voller Umkreis, nur große Flächen) holt, was für die Anlauflänge zählt:
# Küstenlinien, große Seen und Meeresarme. Kleingewässer zehn Kilometer weiter
# ändern an der Anlauflänge nichts.
#
# Absichtlich OHNE `out geom(bbox)`: das Zuschneiden spart zwar Daten, liefert
# aber Punktlisten mit Lücken, und aus einer zerschnittenen Küste lässt sich
# kein geschlossener Ring mehr bauen — genau der Ring, an dem hängt, ob ein
# Spot als Wasser erkannt wird.

QUERY_NEAR = """[out:json][timeout:180];
(
  way["natural"="coastline"]({bbox});
  way["natural"="water"]({bbox});
  relation["natural"="water"]({bbox});
  way["landuse"="reservoir"]({bbox});
  relation["landuse"="reservoir"]({bbox});
);
out geom qt;
"""

QUERY_FAR = """[out:json][timeout:180];
(
  way["natural"="coastline"]({bbox});
  way["natural"="water"]({bbox})(if:length()>{min_len});
  relation["natural"="water"]({bbox});
  way["landuse"="reservoir"]({bbox})(if:length()>{min_len});
  relation["landuse"="reservoir"]({bbox});
);
out geom qt;
"""

QUERY_FAR_SIMPLE = """[out:json][timeout:180];
(
  way["natural"="coastline"]({bbox});
  relation["natural"="water"]({bbox});
  relation["landuse"="reservoir"]({bbox});
);
out geom qt;
"""


MAX_BYTES = 300 * 1024 * 1024        # darüber ist die Abfrage falsch, nicht der Spot groß


class OverpassError(RuntimeError):
    pass


def safe_id(spot_id: str) -> str:
    """Eine Katalog-ID wird zum Dateinamen — also nur, was in einen Dateinamen darf.

    Die IDs stammen aus spots.yaml und aus der Spot-Aufnahme; beides ist eigene
    Eingabe, aber ein Tippfehler wie `../` soll trotzdem nie aus dem Cache-
    Ordner herausführen.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "-", str(spot_id))[:80]
    return cleaned or "spot"


def stempel(lat: float, lon: float) -> list[float]:
    """Die Koordinate, für die ein Auszug geholt wurde — vier Stellen, etwa 10 m."""
    return [round(float(lat), 4), round(float(lon), 4)]


def passt(gemerkt, lat: float, lon: float, toleranz: float = 0.0005) -> bool:
    """Gilt ein gemerkter Eintrag noch für diese Koordinate?

    Ein Cache, der nur an der Spot-ID hängt, überlebt jede Korrektur der
    Koordinate: nach dem Verschieben der Nadel rechnete der Geometrielauf
    aus dem Auszug für den alten Punkt weiter, Schutzgebiete, Regionalmodell
    und Fahrzeit blieben die der alten Stelle. Deshalb steht die Koordinate
    jetzt im Eintrag, und ein Eintrag, der zu einer anderen gehört, gilt
    nicht. Einträge ohne Stempel — aus der Zeit davor — gelten weiter; sie
    bekommen ihren Stempel beim nächsten Holen.
    """
    if not gemerkt:
        return True
    try:
        glat, glon = float(gemerkt[0]), float(gemerkt[1])
    except (TypeError, ValueError, IndexError):
        return True
    return abs(glat - float(lat)) <= toleranz and abs(glon - float(lon)) <= toleranz


def bbox_for(lat: float, lon: float, radius_km: float) -> str:
    dlat = radius_km / 110.574
    dlon = radius_km / (111.320 * max(math.cos(math.radians(lat)), 0.05))
    return f"{lat - dlat:.5f},{lon - dlon:.5f},{lat + dlat:.5f},{lon + dlon:.5f}"


def _ask(query: str, pause_s: float):
    """Eine Abfrage gegen die Endpunkte. Rückgabe: Daten oder OverpassError."""
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    last = None
    for endpoint in ENDPOINTS:
        req = urllib.request.Request(endpoint, data=body, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                try:
                    raw = lies(resp, MAX_BYTES, FRIST_S)
                except ValueError:
                    raise OverpassError(T("Antwort größer als 300 MB — Umkreis oder Filter prüfen"))
                data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError(T("unerwartete Antwort: {antwort}", antwort=type(data).__name__))
            time.sleep(pause_s)                      # den Servern Luft lassen
            return data
        # OSError deckt alles ab, was das Netz werfen kann: URLError und
        # HTTPError sind Unterklassen, ebenso ConnectionReset — und
        # socket.timeout, das unter Python 3.9 noch keine TimeoutError ist.
        # Bis 1.6.1 fiel genau dieser Lese-Timeout hier durch, und der zweite
        # Endpunkt wurde nie versucht. RecursionError: ein JSON, tiefer
        # verschachtelt, als json.loads lesen kann — bis 2.1.0 ließ auch das
        # den zweiten Endpunkt aus (C20).
        except (OSError, ValueError, RecursionError) as exc:
            last = exc
            time.sleep(pause_s)
    raise OverpassError(str(last))


def _merge(*responses) -> dict:
    """Antworten zusammenlegen, jedes OSM-Objekt nur einmal."""
    elements, seen = [], set()
    for response in responses:
        for el in (response or {}).get("elements", []):
            key = (el.get("type"), el.get("id"))
            if key in seen:
                continue
            seen.add(key)
            elements.append(el)
    return {"elements": elements}


def fetch_water(spot_id: str, lat: float, lon: float, radius_km: float,
                cache_dir: str | Path = CACHE / "geom", force: bool = False,
                pause_s: float = 3.0, near_km: float = 6.0,
                min_water_m: int = 1500, log=None) -> dict:
    """OSM-Wassergeometrie im Umkreis, zweistufig. Nutzt den Cache, wenn vorhanden.

    Scheitert die Fernabfrage — überlastete Server antworten gern mit 504 —,
    wird der Umkreis verkleinert und zuletzt auf Küste und große Relationen
    beschränkt. Eine Rose über 15 km ist brauchbar, gar keine nicht.
    """
    say = log or (lambda *a: None)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Gepackt abgelegt: die Rohantwort für einen Spot im Wasserland kann
    # zwanzig Megabyte haben, gezippt ist es ein Bruchteil, und gelesen wird
    # sie ohnehin nur beim Rechnen.
    path = cache_dir / f"{safe_id(spot_id)}_{radius_km:.0f}km.json.gz"
    plain = cache_dir / f"{safe_id(spot_id)}_{radius_km:.0f}km.json"
    if not force:
        gemerkt = None
        try:
            if path.exists():
                with gzip.open(path, "rt", encoding="utf-8") as fh:
                    gemerkt = json.load(fh)
            elif plain.exists():
                with plain.open(encoding="utf-8") as fh:
                    gemerkt = json.load(fh)
        except (OSError, ValueError, EOFError, RecursionError):
            gemerkt = None          # abgeschnittener Auszug: neu holen statt bei jedem Lauf scheitern
        if isinstance(gemerkt, dict):
            if passt(gemerkt.get("_spot"), lat, lon):
                return gemerkt
            say("    " + T("(Auszug gehörte zu einer anderen Koordinate — hole neu)"))

    near = _ask(QUERY_NEAR.format(bbox=bbox_for(lat, lon, min(near_km, radius_km))), pause_s)

    far, problem = None, None
    for radius in (radius_km, radius_km * 0.6):
        bbox = bbox_for(lat, lon, radius)
        for query in (QUERY_FAR.format(bbox=bbox, min_len=min_water_m),
                      QUERY_FAR_SIMPLE.format(bbox=bbox)):
            try:
                far = _ask(query, pause_s)
            except OverpassError as exc:
                problem = exc
                continue
            if radius < radius_km:
                say("    " + T("(Umkreis auf {km} km verkleinert)", km=f"{radius:.0f}"))
            break
        if far is not None:
            break

    if far is None:
        say("    " + T("(nur Nahbereich {km} km — Fernabfrage scheiterte: {fehler})",
                      km=f"{near_km:.0f}", fehler=problem))

    data = _merge(near, far)
    data["_spot"] = stempel(lat, lon)
    # Atomar: ein abgebrochener Lauf hinterlässt keinen halben Auszug.
    with ablegen_offen(path) as roh, gzip.open(roh, "wt", encoding="utf-8") as fh:
        json.dump(data, fh)
    return data


PROTECTED_QUERY = """[out:json][timeout:60];
(
  way["boundary"="protected_area"]({bbox});
  relation["boundary"="protected_area"]({bbox});
  way["leisure"="nature_reserve"]({bbox});
  relation["leisure"="nature_reserve"]({bbox});
);
out tags center;
"""

# Art und Ersatzname landen im Cache und in geometry.json („protected“) —
# deutsch gespeichert, übersetzt wird beim Anzeigen mit T().
PROTECT_CLASS = {
    "1": N_("Strenges Naturschutzgebiet"), "1a": N_("Strenges Naturschutzgebiet"), "1b": N_("Wildnisgebiet"),
    "2": N_("Nationalpark"), "3": N_("Naturdenkmal"), "4": N_("Habitat-/Artenschutzgebiet"),
    "5": N_("Landschaftsschutzgebiet"), "6": N_("Schutzgebiet mit Nutzung"), "7": N_("Naturschutz (lokal)"),
    "97": "Natura 2000", "98": N_("Ramsar-Feuchtgebiet"),
}


def fetch_protected(spot_id: str, lat: float, lon: float, radius_km: float = 1.5,
                    cache_dir: str | Path = CACHE / "geom", pause_s: float = 2.0,
                    force: bool = False) -> list[dict]:
    """Schutzgebiete im Umkreis — der häufigste Grund für Kite-/Wingverbote.

    Natura-2000-Vogelschutzgebiete (protect_class 97), Nationalparks (2) und
    Naturschutzgebiete (1, 4) sind an Nord- und Ostsee, im Wattenmeer und an
    vielen Seen die Stellen, an denen saisonale oder ganzjährige Verbote gelten.
    Das Tool kann die Regel nicht kennen — aber es kann sagen: hier nachsehen.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{safe_id(spot_id)}_protected.json"
    if not force:
        # Eine abgeschnittene Datei ist eine fehlende: bis 2.1.0 warf sie hier
        # bei jedem Lauf, und die Schutzgebietswarnung fehlte bis --force (C14).
        gemerkt = cache_lesen(path, (list, dict))
        if isinstance(gemerkt, list):                 # Ablage vor 1.7.0, ohne Stempel
            return gemerkt
        if isinstance(gemerkt, dict) and passt(gemerkt.get("_spot"), lat, lon):
            gebiete = gemerkt.get("gebiete")
            if isinstance(gebiete, list):
                return list(gebiete)
    body = urllib.parse.urlencode({"data": PROTECTED_QUERY.format(bbox=bbox_for(lat, lon, radius_km))}).encode()
    data = None
    for endpoint in ENDPOINTS:
        req = urllib.request.Request(endpoint, data=body, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(lies(resp).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError(type(data).__name__)
            break
        except (OSError, ValueError, RecursionError):
            data = None
            time.sleep(pause_s)
    if data is None:
        return []
    out, seen = [], set()
    elemente = data.get("elements")
    for el in elemente if isinstance(elemente, list) else []:
        tags = el.get("tags") if isinstance(el, dict) else None
        if not isinstance(tags, dict):
            tags = {} if isinstance(el, dict) else None
        if tags is None:
            continue
        name = tags.get("name") or tags.get("protection_title") or N_("Schutzgebiet ohne Namen")
        if name in seen:
            continue
        seen.add(name)
        pc = str(tags.get("protect_class", "")).strip()
        out.append({
            "name": name,
            "class": pc,
            "kind": PROTECT_CLASS.get(pc, tags.get("protection_title") or
                                      (N_("Naturschutzgebiet") if tags.get("leisure") == "nature_reserve"
                                       else N_("Schutzgebiet"))),
            "natura2000": pc == "97" or bool(tags.get("ref:natura2000")),
        })
    ablegen(path, json.dumps({"_spot": stempel(lat, lon), "gebiete": out}, ensure_ascii=False))
    time.sleep(pause_s)
    return out
