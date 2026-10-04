"""Neue Spots aus einer Texteingabe — Koordinaten rein, Katalogeintrag raus.

Gedacht für den Fall, der unterwegs passiert: Du siehst eine Stelle, nimmst die
Koordinate aus der Karte und willst sie beim nächsten Suchlauf dabeihaben, ohne
YAML von Hand zu schreiben.

Erlaubt ist alles, was unterwegs entsteht — eine Zeile je Spot:

    Hardtsee; 49.17008, 8.61477
    49.17008, 8.61477 Hardtsee
    Bostalsee; 49.56831, 7.07964; reservoir
    https://www.google.com/maps/@51.7625,3.854,15z
    51°45'45"N 3°51'14"E  Brouwersdam Innenseite

Dazu die üblichen Exportformate, jeweils als Datei über das Dateifeld:
GPX (Wegpunkte), KML aus Google My Maps (Ortsmarken), GeoJSON aus Google
Takeout (Punkte) und CSV mit Spalten für Breite und Länge.
"""
from __future__ import annotations
import csv
import math
import io
import json
import re
from pathlib import Path

from . import xmlsicher
from .geo import parse_position, haversine_km
from .i18n import T, TN, N_                                       # noqa: F401
from .spotedit import steuerzeichen_raus

WATER_WORDS = {
    "sea": "sea", "meer": "sea", "ozean": "sea", "kueste": "sea", "küste": "sea",
    "lagoon": "lagoon", "lagune": "lagoon", "haff": "lagoon", "bodden": "lagoon",
    "lake": "lake", "see": "lake", "baggersee": "lake",
    "reservoir": "reservoir", "stausee": "reservoir", "talsperre": "reservoir",
}

# Grobe Landesrahmen, nur um das Kürzel für die Wetterwarnungen zu raten.
# Überlappungen sind egal: es gewinnt der kleinste Rahmen, der den Punkt enthält.
COUNTRY_BOXES = [
    ("NL", 50.75, 3.35, 53.60, 7.23), ("BE", 49.49, 2.54, 51.51, 6.41),
    ("CH", 45.81, 5.95, 47.81, 10.50), ("AT", 46.37, 9.52, 49.02, 17.16),
    ("SI", 45.42, 13.37, 46.88, 16.61), ("HR", 42.38, 13.49, 46.55, 19.45),
    ("DK", 54.55, 8.07, 57.75, 12.69), ("DE", 47.27, 5.87, 55.06, 15.04),
    ("FR", 41.33, -5.14, 51.09, 9.56), ("IT", 36.62, 6.62, 47.09, 18.52),
    ("ES", 36.00, -9.30, 43.79, 3.32), ("PT", 36.96, -9.50, 42.15, -6.19),
    ("GR", 34.80, 19.37, 41.75, 29.65), ("PL", 49.00, 14.12, 54.84, 24.15),
    ("SE", 55.34, 11.11, 69.06, 24.16), ("NO", 57.96, 4.65, 71.19, 31.08),
]

# Zwischen den Zahlen ein Trenner aus `,;/` mit Leerraum drumherum, oder
# Leerraum mit mindestens einem Leerzeichen — dieselbe Sprache wie bis 2.1.0
# `\s*[,;/ ]\s*`, aber eindeutig zerlegt: dort konnte jedes Leerzeichen der
# Trenner sein, und eine lange Leerzeichenkette ohne zweite Zahl kostete
# quadratisch viel. Die erste Zeile eines Imports wird nicht gekappt; 8 KB
# brauchten eine Sekunde, die 4 MB, die ein Upload haben darf, Tage
# (Review 04.10.2026, C1).
COORD_PAIR = re.compile(
    r"(-?\d{1,3}[.,]\d+)(?:\s*[,;/]\s*|[^\S ]* \s*)(-?\d{1,3}[.,]\d+)")
# Die Lücken zwischen Minuten und Himmelsrichtung sind begrenzt: mit
# `[^NSEWO]*` lief die Suche quadratisch — 40 KB in einer Zeile kosteten
# vier Sekunden, 4 MB Stunden, und so lange antwortete jede Suche 409
# (Review 25.09.2026, S6). Eine Koordinatenzeile ist nie länger als ein paar
# hundert Zeichen; `parse_line` kappt sie zusätzlich.
DMS_PAIR = re.compile(
    r"\d{1,3}\s*[°d]\s*\d{1,2}[^NSEWO\n]{0,24}[NSEWO]\D{0,4}\d{1,3}\s*[°d]\s*\d{1,2}[^NSEWO\n]{0,24}[NSEWO]", re.I)
MAX_ZEILE = 500                 # Zeichen je Freitextzeile, die noch als Koordinate gelesen werden
MAX_TREFFER = 500               # Spots je Import — mehr hat niemand angesehen
MAX_NAME = 120                  # wie /katalog/neu
URL = re.compile(r"https?://\S+")


def name_putzen(name) -> str:
    """Ein Name aus fremder Hand — Importdatei, Nominatim — als Text, den jede
    Seite schreiben kann: gültiges UTF-8, keine Steuerzeichen, Leerraum zu je
    einem Leerzeichen, höchstens MAX_NAME Zeichen.

    Ein einzelnes Surrogat (`"\\ud800"` in einer GeoJSON-Datei von 169 Bytes)
    kam bis 2.1.0 so in den Katalog, und danach scheiterte jede Suche und
    jede Seite mit dem Namen an UnicodeEncodeError (Review 04.10.2026, C2).
    Es wird zu „?“. Eine Liste oder ein Block ist kein Name.
    """
    if not isinstance(name, (str, int, float)):
        return ""
    text = str(name or "").encode("utf-8", "replace").decode("utf-8")
    return " ".join(steuerzeichen_raus(text).split())[:MAX_NAME].strip()


def guess_country(lat: float, lon: float) -> str:
    hits = [(abs(n - s) * abs(e - w), code)
            for code, s, w, n, e in COUNTRY_BOXES if s <= lat <= n and w <= lon <= e]
    return min(hits)[1] if hits else ""


def slug(name: str, taken=()) -> str:
    base = name.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("é", "e"), ("è", "e")):
        base = base.replace(a, b)
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:40] or "spot"
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def parse_line(line: str):
    """Eine Zeile → (name, lat, lon, water_body|None) oder None."""
    text = line.strip().lstrip("-*•").strip()[:MAX_ZEILE]
    if not text or text.startswith("#"):
        return None

    rest, found = text, None
    url = URL.search(text)
    if url:
        found = parse_position(url.group(0))
        rest = text.replace(url.group(0), " ")
    if found is None:
        m = DMS_PAIR.search(text) or COORD_PAIR.search(text)
        if not m:
            return None
        found = parse_position(m.group(0))
        rest = text[:m.start()] + " " + text[m.end():]
    if found is None:
        return None

    water = None
    fields = [f.strip() for f in re.split(r"[;|]", rest) if f.strip()]
    if fields and fields[-1].lower() in WATER_WORDS:
        water = WATER_WORDS[fields.pop().lower()]
    name = " ".join(fields).strip(" ,;-–—\t")
    name = re.sub(r"\s{2,}", " ", name)
    return (name, found[0], found[1], water)


def _xml(text: str):
    """XML ohne DOCTYPE und Entitäten — die Prüfung steht in `xmlsicher`,
    weil MeteoAlarm dieselbe braucht."""
    return xmlsicher.lesen(text)


def parse_gpx(text: str):
    out = []
    root = _xml(text)
    if root is None:
        return out
    for el in root.iter():
        if el.tag.split("}")[-1] != "wpt":
            continue
        try:
            lat, lon = float(el.attrib["lat"]), float(el.attrib["lon"])
        except (KeyError, ValueError):
            continue
        name = ""
        for child in el:
            if child.tag.split("}")[-1] == "name" and child.text:
                name = child.text.strip()
        out.append((name, lat, lon, None))
    return out


LAT_KEYS = ("lat", "latitude", "breite", "breitengrad", "y")
LON_KEYS = ("lon", "lng", "long", "longitude", "laenge", "länge", "längengrad", "x")


def parse_kml(text: str):
    """Google My Maps und jedes andere KML: Ortsmarken mit Punktkoordinate.

    KML schreibt die Koordinate als „Länge,Breite,Höhe" — also andersherum als
    alles andere hier. Das ist die häufigste Fehlerquelle beim Einlesen.
    """
    out = []
    root = _xml(text)
    if root is None:
        return out
    for el in root.iter():
        if el.tag.split("}")[-1] != "Placemark":
            continue
        name, coords = "", ""
        for child in el.iter():
            tag = child.tag.split("}")[-1]
            if tag == "name" and child.text and not name:
                name = child.text.strip()
            elif tag == "Point":
                for sub in child.iter():
                    if sub.tag.split("}")[-1] == "coordinates" and sub.text and sub.text.split():
                        coords = sub.text.strip().split()[0]
        fields = coords.split(",")
        if len(fields) < 2:
            continue
        try:
            out.append((name, float(fields[1]), float(fields[0]), None))
        except (TypeError, ValueError):
            continue
    return out


def parse_geojson(text: str):
    """GeoJSON, wie Google Takeout „Gespeicherte Orte" es liefert.

    Auch hier steht die Länge zuerst. Der Name steckt je nach Export in
    `properties.name`, `properties.Title` oder unter `properties.location`.
    """
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        # Tausendfach verschachtelt ist kein GeoJSON — bis 2.1.0 flog der
        # RecursionError roh durch den Import (Review 04.10.2026, C20).
        return []
    out = []
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list):
        return out
    for feature in features:
        # Ein krummer Datensatz kostet den Datensatz, nicht die Datei
        # (Review 25.09.2026, S12).
        try:
            geometry = (feature or {}).get("geometry") or {}
            if geometry.get("type") != "Point":
                continue
            pair = geometry.get("coordinates") or []
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            props = feature.get("properties") or {}
            location = props.get("location") if isinstance(props.get("location"), dict) else {}
            name = (props.get("name") or props.get("Title") or props.get("title")
                    or location.get("name") or location.get("address") or "")
            out.append((name_putzen(name), float(pair[1]), float(pair[0]), None))
        except (AttributeError, TypeError, ValueError, KeyError, RecursionError):
            continue
    return out


def parse_csv(text: str):
    """CSV mit Spalten für Breite und Länge — sonst zeilenweise wie Freitext.

    Der Takeout-Export gespeicherter Google-Listen hat nur Titel, Notiz und
    eine Maps-Adresse. Steckt in der Adresse eine Koordinate, wird sie
    genommen; sonst bleibt der Eintrag ungelesen — ohne Koordinate lässt sich
    daraus nichts machen.
    """
    try:
        sample = text[:4000]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    try:
        rows = list(csv.DictReader(io.StringIO(text), dialect=dialect))
    except csv.Error:                       # ein Feld über 128 KB — keine Spotliste
        return [], []
    if not rows or not rows[0]:
        return [], []

    def column(candidates):
        for key in rows[0]:
            if key and key.strip().lower() in candidates:
                return key
        return None

    lat_key, lon_key = column(LAT_KEYS), column(LON_KEYS)
    name_key = column(("name", "title", "titel", "bezeichnung", "spot"))
    url_key = column(("url", "link", "adresse", "address"))

    out, missing = [], []
    for row in rows:
        name = (row.get(name_key) or "").strip() if name_key else ""
        if lat_key and lon_key:
            try:
                out.append((name, float(str(row[lat_key]).replace(",", ".")),
                            float(str(row[lon_key]).replace(",", ".")), None))
                continue
            except (TypeError, ValueError):
                pass
        found = parse_position(row[url_key]) if url_key and row.get(url_key) else None
        if found:
            out.append((name, found[0], found[1], None))
        else:
            missing.append(name or T("Zeile ohne Namen"))
    return out, missing


def koordinate_ok(lat, lon) -> bool:
    """Endlich und im Bereich. `nan` aus einer GPX-Datei kam bis 1.18.3 in den
    Katalog, überstand jeden Filter und ging als `latitude=nan` an Open-Meteo
    (Review 25.09.2026, S7)."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return math.isfinite(lat) and math.isfinite(lon) and abs(lat) <= 90 and abs(lon) <= 180


def _brauchbar(hits: list, problems: list) -> list:
    """Treffer mit unbrauchbarer Koordinate raus, Treffer und Namen gedeckelt —
    mit einer Zeile im Protokoll, damit nichts still verschwindet."""
    gut = [h for h in hits if koordinate_ok(h[1], h[2])]
    if len(gut) < len(hits):
        problems.append(T("{n} Punkte mit unbrauchbarer Koordinate übersprungen "
                          "(nan, inf oder außerhalb von ±90/±180).", n=len(hits) - len(gut)))
    if len(gut) > MAX_TREFFER:
        problems.append(T("Nur die ersten {max} von {n} Punkten übernommen — "
                          "mehr hat niemand angesehen; den Rest in einer zweiten Datei.", max=MAX_TREFFER, n=len(gut)))
        gut = gut[:MAX_TREFFER]
    return [(name_putzen(h[0]),) + tuple(h[1:]) for h in gut]


def parse_text(text: str):
    """Freitext oder Exportdatei → (Treffer, unlesbare Zeilen)."""
    hits, problems = _parse_text(text)
    return _brauchbar(hits, problems), problems


def _parse_text(text: str):
    head = text[:2000].lstrip()
    if head[:2] == "PK":
        return [], [T("KMZ ist eine gepackte Datei — bitte entpacken und die "
                      "enthaltene doc.kml laden.")]
    low = head.lower()
    if "<gpx" in low:
        return parse_gpx(text), []
    if "<kml" in low or "<placemark" in low:
        return parse_kml(text), []
    if head[:1] in "{[" and '"features"' in text[:4000]:
        return parse_geojson(text), []
    first = text.strip().splitlines()[0] if text.strip() else ""
    if first.count(",") + first.count(";") + first.count("\t") >= 2 and not COORD_PAIR.search(first):
        found, missing = parse_csv(text)
        if found or missing:
            note = ([T("{n} Zeilen ohne Koordinate übersprungen (z.B. {beispiele}) — Google-Listen aus Takeout "
                       "enthalten oft nur eine Orts-ID, keine Position.",
                       n=len(missing), beispiele=", ".join(missing[:3]))] if missing else [])
            return found, note
    hits, problems = [], []
    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#"):    # Leerzeilen und Kommentare sind kein Fehler
            continue
        parsed = parse_line(line)
        (hits if parsed else problems).append(parsed if parsed else line.strip()[:120])
    return hits, problems


def ist_datei(text: str) -> bool:
    """Kommt der Text aus einer Exportdatei (GPX, KML, GeoJSON, CSV)?

    Der Unterschied entscheidet über `verified`: eine Koordinate, die jemand
    selbst eintippt oder aus der Karte kopiert, hat er angesehen. Hundert
    Wegpunkte aus einer fremden GPX hat niemand angesehen — genau dafür gibt
    es die Prüfseite, und bis 1.6.1 kamen sie dort nie an, weil jeder Import
    `verified: true` bekam.
    """
    head = text[:2000].lstrip()
    low = head.lower()
    if "<gpx" in low or "<kml" in low or "<placemark" in low:
        return True
    if head[:1] in "{[" and '"features"' in text[:4000]:
        return True
    first = text.strip().splitlines()[0] if text.strip() else ""
    return first.count(",") + first.count(";") + first.count("\t") >= 2 and not COORD_PAIR.search(first)


def build_entry(name: str, lat: float, lon: float, water: str | None, taken,
                verified: bool = True, ort: dict | None = None) -> dict:
    """Ein Katalogeintrag mit vorsichtigen Voreinstellungen.

    `sectors_unknown` bleibt an, bis die Ufergeometrie gerechnet ist oder du
    Sektoren einträgst — bis dahin wird der Spot mit neutraler Richtungs-
    bewertung gerankt statt mit erfundenen Zahlen. Die Gewässerart ist
    `unknown`, wenn keine genannt wird: der Katalog kennt den Wert, die
    Vorfilter lassen ihn durch, und die Ufergeometrie sagt später, worin der
    Spot liegt. `lake` als Voreinstellung machte bis 1.6.1 aus einem
    Meeresspot einen See — der fiel bei abgewähltem „See“ heraus und wurde
    beim Versetzen ins Wasser in die falsche Fläche geschoben.
    """
    ort = ort or {}
    # Was hier ankommt, geht unverändert in spots.yaml und auf jede Seite:
    # der Name aus dem Import und der aus OpenStreetMap — auch aus dem
    # Zwischenspeicher, der ältere, ungekürzte Antworten halten kann.
    name, ort_name = name_putzen(name), name_putzen(ort.get("name"))
    # Name, Notiz und Quelle sind Katalogdaten in spots.yaml (wie die übrigen
    # Einträge auf Deutsch) — bewusst nicht übersetzt.
    label = name or ort_name or f"Spot {lat:.4f}, {lon:.4f}"
    land = ort.get("country") or guess_country(lat, lon)
    if ort.get("country"):
        notiz = ("Selbst eingetragen. Gewässerart und Untergrund sind geraten; Land"
                 + (" und Name" if not name and ort_name else "")
                 + " aus OpenStreetMap (nächster Ort).")
    else:
        notiz = ("Selbst eingetragen. Gewässerart, Untergrund und Land sind geraten — "
                 "das Landeskürzel stammt aus groben Rahmen und liegt in Grenznähe "
                 "gelegentlich daneben (es steuert nur die Wetterwarnungen).")
    return {
        "id": slug(label, taken),
        "name": label,
        "country": land,
        "region": "",
        "lat": round(float(lat), 6),
        "lon": round(float(lon), 6),
        "water_body": water or "unknown",
        "shallow": "none",
        "seagrass": "none",
        "season": list(range(1, 13)),
        "sectors": [],
        "sectors_unknown": True,
        "notes": notiz,
        "source": "eigene Eingabe" if verified else "importierte Datei",
        "verified": bool(verified),
        "wind_factor": 1.0,
    }


def too_close(lat: float, lon: float, spots, limit_km: float = 0.3):
    """Gibt den vorhandenen Spot zurück, wenn dieser Punkt schon im Katalog steht."""
    for spot in spots:
        if haversine_km(lat, lon, spot["lat"], spot["lon"]) <= limit_km:
            return spot
    return None


def append_to_yaml(path: str | Path, entries: list[dict]) -> None:
    """Hängt die Einträge an — ohne die kommentierte Datei neu zu schreiben.

    yaml.dump über die ganze Datei würde die Kopfzeilen und jede Erklärung
    darin verlieren. Darum wird nur angehängt, in derselben Form wie der Rest.
    """
    import yaml
    from .spotedit import schreibe_atomar

    def schreibbar(wert):
        # Ein einzelnes Surrogat schriebe YAML als "\uD800" — gültig für YAML,
        # aber danach von keiner Seite mehr auszugeben (Review 04.10.2026, C2).
        # Gilt für alles, was ein Aufrufer in den Eintrag legt, auch Notiz und
        # Kommentar aus /katalog/neu.
        if isinstance(wert, str):
            return wert.encode("utf-8", "replace").decode("utf-8")
        if isinstance(wert, list):
            return [schreibbar(x) for x in wert]
        if isinstance(wert, dict):
            return {schreibbar(k): schreibbar(v) for k, v in wert.items()}
        return wert

    text = "\n" + "\n".join(
        yaml.safe_dump([schreibbar(entry)], allow_unicode=True, sort_keys=False, width=100).rstrip()
        for entry in entries) + "\n"
    path = Path(path)
    alt = path.read_text(encoding="utf-8") if path.exists() else ""
    schreibe_atomar(path, alt + text)
