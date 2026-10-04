"""Etappe 03 — Ufergeometrie aus OpenStreetMap.

Die Idee in einem Satz: **Anlauflänge über Wasser in jede Himmelsrichtung**.

Von jedem Spot aus werden Strahlen in alle Richtungen geschossen. Der erste
Schnittpunkt mit einer Wassergrenze — Küstenlinie oder Seeufer — ist die
Anlauflänge (Fetch) in dieser Richtung. Aus dieser einen Größe folgt alles,
was du bisher im Kopf gemacht hast:

  · Fetch in Luv klein, Platz in Lee groß   → ablandig
  · Fetch in Luv groß, Platz in Lee klein   → auflandig, Welle steht rein
  · beides groß                             → sideshore, das Beste
  · beides klein                            → falscher Punkt, kein Wasser

Und die Wellenhöhe folgt aus Fetch und Windstärke, statt geraten zu werden.

Kein Zusatzpaket nötig: Projektion, Gitterindex und Strahlenschnitt sind hier
ausgeschrieben. Das kostet ein paar Zeilen mehr und spart dir eine Abhängigkeit,
die auf jedem Rechner anders zickt.
"""
from __future__ import annotations
import math
from collections import deque

from .i18n import T, TN, N_                                       # noqa: F401

# ── Projektion ───────────────────────────────────────────────────────────────
# Äquidistant um den Spot. Über 80 km Kantenlänge liegt der Fehler unter 0,1 % —
# für Anlauflängen völlig ausreichend.

M_PER_DEG_LAT = 110574.0


def projector(lat0: float, lon0: float):
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat0))

    def to_xy(lat: float, lon: float) -> tuple[float, float]:
        return ((lon - lon0) * m_per_deg_lon, (lat - lat0) * M_PER_DEG_LAT)

    def to_latlon(x: float, y: float) -> tuple[float, float]:
        return (lat0 + y / M_PER_DEG_LAT, lon0 + x / m_per_deg_lon)

    return to_xy, to_latlon


# ── Segmente aus OSM-Daten ───────────────────────────────────────────────────

def segments_from_osm(data: dict, lat0: float, lon0: float,
                      min_water_m: float = 150.0) -> dict:
    """Zerlegt die OSM-Antwort in drei Dinge.

    `segments`  Wassergrenzen als Strecken — daran endet ein Strahl
    `coastline` nur die Küstenlinien, in Original-Richtung. OSM zeichnet sie so,
                dass LAND LINKS und WASSER RECHTS liegt; daraus folgt, auf
                welcher Seite ein Punkt liegt
    `rings`     geschlossene Wasserflächen für den Test, ob der Spot im Wasser
                liegt

    `min_water_m` wirft Kleinstgewässer weg: Gräben, Teiche, Hafenbecken,
    Löschwasserweiher. Für die Anlauflänge sind sie bedeutungslos, als
    Strahlenblocker aber fatal — ein Dorfweiher drei Kilometer im Landesinneren
    würde sonst die Anlauflänge über den offenen See begrenzen. Gemessen wird
    die größere Seite des umgebenden Rechtecks.
    """
    to_xy, _ = projector(lat0, lon0)

    segments: list[tuple[float, float, float, float]] = []
    coastline: list[tuple[float, float, float, float]] = []
    rings: list[list[tuple[float, float]]] = []

    def as_points(points):
        out = []
        for point in points or ():
            try:
                out.append(to_xy(point["lat"], point["lon"]))
            except (KeyError, TypeError):
                continue
        return out

    def big_enough(pts) -> bool:
        if len(pts) < 3:
            return False
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return max(max(xs) - min(xs), max(ys) - min(ys)) >= min_water_m

    def as_segments(pts, is_coast=False):
        for a, b in zip(pts, pts[1:]):
            if a != b:
                segments.append((a[0], a[1], b[0], b[1]))
                if is_coast:
                    coastline.append((a[0], a[1], b[0], b[1]))

    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        kind = el.get("type")

        if tags.get("natural") == "coastline":
            if kind == "way":
                as_segments(as_points(el.get("geometry")), is_coast=True)
            else:
                for member in el.get("members", []):
                    as_segments(as_points(member.get("geometry")), is_coast=True)
            continue

        if kind == "way":
            pts = as_points(el.get("geometry"))
            if not big_enough(pts):
                continue
            as_segments(pts)
            if len(pts) > 3 and pts[0] == pts[-1]:
                rings.append(pts)
        elif kind == "relation":
            for chain, closed in stitch_rings(el):
                pts = as_points(chain)
                if not big_enough(pts):
                    continue
                as_segments(pts)                    # nur die echten Uferstücke
                if len(pts) > 3:
                    rings.append(pts if closed else pts + [pts[0]])

    return {"segments": segments, "coastline": coastline, "rings": rings}


def stitch_rings(relation: dict, min_open_points: int = 60):
    """Zerlegt ein Multipolygon in Ringe. Rückgabe: [(Punkte, war_geschlossen)].

    Große Gewässer — Grevelingenmeer, Oosterschelde, IJsselmeer — sind in
    OpenStreetMap Relationen: das Ufer ist in Dutzende Einzelwege zerlegt, von
    denen keiner für sich geschlossen ist. Wer nur die Einzelwege ansieht,
    findet keine Fläche und hält den Spot für Land. Hier werden die Stücke an
    ihren gemeinsamen Endpunkten aneinandergehängt, bis ein Ring zu ist.

    Manche Gewässer sind größer als der abgefragte Ausschnitt — die
    Oosterschelde ist fünfzig Kilometer lang. Dann fehlen die Teilstücke
    außerhalb, und der Ring schließt nie. Ein langer offener Zug wird deshalb
    trotzdem als Fläche geführt und beim Aufrufer künstlich geschlossen; die
    gedachte Verbindungslinie darf aber kein Strahlenblocker werden, sonst
    stünde mitten im Wasser eine Wand. Darum die zweite Rückgabe.

    Gesucht wird über ein Verzeichnis der Endpunkte, nicht über alle Stücke:
    bis 2.1.0 lief jeder Schritt durch die ganze Liste, und eine Relation mit
    20 000 Stücken von einem fremden Overpass-Spiegel kostete eine
    Viertelstunde (Review 04.10.2026, C10). Gewählt wird dasselbe Stück wie
    vorher — das erste in der Liste, das an einem der beiden Enden passt,
    mit derselben Reihenfolge der vier Fälle —, die Ringe sind also gleich.
    """
    parts = []
    mitglieder = relation.get("members")
    for member in mitglieder if isinstance(mitglieder, list) else []:
        if not isinstance(member, dict) or member.get("role") not in (None, "", "outer", "inner"):
            continue
        # Punkte ohne Koordinate kommen vor; sie hier stehen zu lassen, kostete
        # einen Abbruch mitten im Lauf.
        geometry = [p for p in (member.get("geometry") or []) if isinstance(p, dict)
                    and all(isinstance(p.get(k), (int, float)) and not isinstance(p.get(k), bool)
                            for k in ("lat", "lon"))]
        if len(geometry) < 2:
            continue
        parts.append(geometry)

    def key(point):
        return (round(point["lat"], 7), round(point["lon"], 7))

    # Endpunkt → Stücke, die dort anfangen bzw. enden, aufsteigend. Benutzte
    # Stücke bleiben stehen und werden beim Nachsehen vorn abgeräumt.
    anfang: dict = {}
    ende: dict = {}
    for i, part in enumerate(parts):
        anfang.setdefault(key(part[0]), deque()).append(i)
        ende.setdefault(key(part[-1]), deque()).append(i)
    used = [False] * len(parts)

    def erstes(verzeichnis, k):
        liste = verzeichnis.get(k)
        while liste and used[liste[0]]:
            liste.popleft()
        return liste[0] if liste else None

    rings = []
    for start in range(len(parts)):
        if used[start]:
            continue
        used[start] = True
        chain = deque(parts[start])
        while True:
            vorn, hinten = key(chain[0]), key(chain[-1])
            if vorn == hinten:
                break
            kandidaten = [i for i in (erstes(anfang, hinten), erstes(ende, hinten),
                                      erstes(ende, vorn), erstes(anfang, vorn)) if i is not None]
            if not kandidaten:
                break
            i = min(kandidaten)
            part = parts[i]
            if key(part[0]) == hinten:
                chain.extend(part[1:])
            elif key(part[-1]) == hinten:
                chain.extend(reversed(part[:-1]))
            elif key(part[-1]) == vorn:
                chain.extendleft(reversed(part[:-1]))
            else:
                chain.extendleft(part[1:])
            used[i] = True
        chain = list(chain)
        closed = key(chain[0]) == key(chain[-1])
        if len(chain) > 3:
            rings.append((chain, closed))
    return rings


# ── Liegt der Punkt überhaupt im Wasser? ─────────────────────────────────────

def point_in_rings(x: float, y: float, rings) -> bool:
    """Even-odd-Test gegen geschlossene Wasserflächen."""
    inside = False
    for ring in rings:
        c = False
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            if (y1 > y) != (y2 > y):
                xin = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
                if x < xin:
                    c = not c
        if c:
            inside = not inside
    return inside


def coastline_side(x: float, y: float, coastline, max_m: float = 20000.0):
    """Wasser oder Land? Über die Zeichenrichtung der nächsten Küstenlinie.

    OSM-Konvention: Küstenlinien laufen so, dass Land links und Wasser rechts
    liegt. Das Kreuzprodukt der nächsten Strecke mit dem Punkt sagt die Seite.
    Rückgabe: "water", "land" oder None, wenn keine Küste in Reichweite ist.
    """
    best_d2, best = max_m * max_m, None
    for (x1, y1, x2, y2) in coastline:
        ex, ey = x2 - x1, y2 - y1
        L2 = ex * ex + ey * ey
        if L2 == 0:
            continue
        t = max(0.0, min(1.0, ((x - x1) * ex + (y - y1) * ey) / L2))
        px, py = x1 + t * ex, y1 + t * ey
        d2 = (x - px) ** 2 + (y - py) ** 2
        if d2 < best_d2:
            best_d2, best = d2, (x1, y1, ex, ey)
    if best is None:
        return None
    x1, y1, ex, ey = best
    cross = ex * (y - y1) - ey * (x - x1)
    return "land" if cross > 0 else "water"


# ── Gitterindex + Strahlenschnitt ────────────────────────────────────────────

class SegmentIndex:
    """Gleichmäßiges Gitter über die Strecken, damit ein Strahl nicht alles testen muss."""

    def __init__(self, segments, cell_m: float = 2000.0):
        self.cell = cell_m
        self.segments = segments
        self.grid: dict[tuple[int, int], list[int]] = {}
        for i, (x1, y1, x2, y2) in enumerate(segments):
            cx0, cx1 = sorted((int(x1 // cell_m), int(x2 // cell_m)))
            cy0, cy1 = sorted((int(y1 // cell_m), int(y2 // cell_m)))
            for cx in range(cx0, cx1 + 1):
                for cy in range(cy0, cy1 + 1):
                    self.grid.setdefault((cx, cy), []).append(i)

    def first_hit(self, ox: float, oy: float, bearing_deg: float, max_m: float) -> float:
        """Entfernung zum ersten Schnittpunkt, sonst max_m."""
        rad = math.radians(bearing_deg)
        dx, dy = math.sin(rad), math.cos(rad)          # Kompass: 0° = Nord = +y
        best = max_m
        step = self.cell * 0.5
        seen: set[tuple[int, int]] = set()
        checked: set[int] = set()
        t = 0.0
        while t <= max_m:
            px, py = ox + dx * t, oy + dy * t
            for ddx in (-1, 0, 1):
                for ddy in (-1, 0, 1):
                    key = (int(px // self.cell) + ddx, int(py // self.cell) + ddy)
                    if key in seen:
                        continue
                    seen.add(key)
                    for i in self.grid.get(key, ()):
                        if i in checked:
                            continue
                        checked.add(i)
                        hit = _ray_segment(ox, oy, dx, dy, *self.segments[i])
                        if hit is not None and 1.0 < hit < best:
                            best = hit
            if best <= t + self.cell * 1.5:            # näher kommt nichts mehr
                break
            t += step
        return best


def _ray_segment(ox, oy, dx, dy, x1, y1, x2, y2):
    """Strahl (Ursprung, Richtung) gegen Strecke A→B. Rückgabe: Entfernung oder None."""
    ex, ey = x2 - x1, y2 - y1
    denom = dx * ey - dy * ex
    if abs(denom) < 1e-12:
        return None
    fx, fy = x1 - ox, y1 - oy
    t = (fx * ey - fy * ex) / denom
    if t <= 0:
        return None
    u = (fx * dy - fy * dx) / denom
    if u < 0.0 or u > 1.0:
        return None
    return t


# ── Fetch-Rose ───────────────────────────────────────────────────────────────

def fetch_rose(index: SegmentIndex, ox: float = 0.0, oy: float = 0.0,
               n_dirs: int = 36, max_km: float = 40.0) -> list[float]:
    """Anlauflänge in Metern für n_dirs gleichverteilte Richtungen, beginnend bei Nord."""
    max_m = max_km * 1000.0
    stepd = 360.0 / n_dirs
    return [round(index.first_hit(ox, oy, i * stepd, max_m), 1) for i in range(n_dirs)]


def on_water(x: float, y: float, geom: dict) -> bool | None:
    """Liegt der Punkt im Wasser? Erst Seen, dann Küstenlinie. None = keine Aussage."""
    if point_in_rings(x, y, geom.get("rings") or []):
        return True
    side = coastline_side(x, y, geom.get("coastline") or [])
    if side is not None:
        return side == "water"
    return None


def ring_extent_km2(ring) -> float:
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return (max(xs) - min(xs)) * (max(ys) - min(ys)) / 1e6


def _nearest_on_segments(segments, max_m: float):
    """Kürzester Abstand vom Ursprung zu einer Strecke und der Fußpunkt dazu.

    Der Fußpunkt liegt AUF der Strecke, nicht auf einem ihrer Endpunkte. Das
    ist kein Detail: ein gerader Damm ist in OpenStreetMap oft ein einziger
    Weg mit zwei Punkten in 500 m Abstand — wer nur die Endpunkte ansieht,
    hält einen Spot in der Mitte des Damms für 250 m vom Wasser entfernt und
    versetzt ihn in die falsche Richtung.
    """
    best = (max_m, None)
    for (x1, y1, x2, y2) in segments:
        ex, ey = x2 - x1, y2 - y1
        L2 = ex * ex + ey * ey
        if L2 == 0:
            continue
        t = max(0.0, min(1.0, (-x1 * ex - y1 * ey) / L2))
        px, py = x1 + t * ex, y1 + t * ey
        d = math.hypot(px, py)
        if d < best[0]:
            best = (d, (px, py))
    return best


def _nearest_on_coastline(coastline, max_m: float):
    return _nearest_on_segments(coastline, max_m)


def _nearest_on_ring(ring, max_m: float):
    return _nearest_on_segments([(a[0], a[1], b[0], b[1]) for a, b in zip(ring, ring[1:])], max_m)


SEA_AREA_KM2 = 5000.0          # das offene Meer als Fläche, größer als jeder See hier


def snap_into_water(geom: dict, index: SegmentIndex, n_dirs: int = 36,
                    max_km: float = 40.0, snap_m: float = 3000.0,
                    prefer: str | None = None):
    """Spots liegen auf dem Parkplatz, nicht im Wasser — den Ursprung versetzen.

    Entscheidend ist, in WELCHES Wasser versetzt wird. Die nächste Wasserkante
    ist oft ein Entwässerungsgraben hinterm Deich; wer dorthin springt, misst
    die Anlauflänge über einen drei Meter breiten Graben. Andererseits taugt
    „immer die größte Fläche" auch nicht: ein Ostseespot darf nicht in die
    Nordsee zwanzig Kilometer weiter versetzt werden.

    Darum zwei Stufen. Erstens `prefer` aus dem Katalog — steht dort `sea`,
    wird zuerst die Küstenlinie versucht, bei `lake`, `lagoon`, `reservoir`
    zuerst die Flächen. Zweitens innerhalb einer Art eine Abwägung aus Größe
    und Entfernung: eine große Fläche darf weiter weg liegen, eine winzige
    muss praktisch unter den Füßen sein.

    Rückgabe: (x, y, verschoben, status).

    Der Status ist Datum, nicht Anzeige: er steht deutsch in geometry.json, und
    `shoreline.rechne` sucht darin „kein Wasser gefunden“. Die festen Texte,
    die angezeigt werden, sind mit N_() markiert und werden beim Anzeigen
    übersetzt (T(status)); der Versatz mit seinen Zahlen bleibt deutsch.
    """
    rings = geom.get("rings") or []
    coastline = geom.get("coastline") or []

    if point_in_rings(0.0, 0.0, rings):
        return 0.0, 0.0, False, N_("im Wasser")
    if coastline_side(0.0, 0.0, coastline) == "water":
        return 0.0, 0.0, False, N_("im Wasser (Seeseite der Küstenlinie)")

    def score(area_km2, distance_m):
        return area_km2 / (1.0 + (distance_m / 200.0) ** 2)

    area_cands = []
    for ring in rings:
        near, point = _nearest_on_ring(ring, snap_m)
        if point is not None:
            area = ring_extent_km2(ring)
            area_cands.append((-score(area, near), near, area, ring, point))
    area_cands.sort(key=lambda c: c[0])

    sea_cands = []
    if coastline:
        near, point = _nearest_on_coastline(coastline, snap_m)
        if point is not None:
            sea_cands.append((-score(SEA_AREA_KM2, near), near, SEA_AREA_KM2, None, point))

    order = (sea_cands + area_cands) if prefer == "sea" else (area_cands + sea_cands)

    for _, near, area, ring, (px, py) in order[:12]:
        length = math.hypot(px, py) or 1.0
        ux, uy = px / length, py / length
        for extra in (30.0, 80.0, 160.0, 320.0, 640.0):
            d = near + extra
            nx, ny = ux * d, uy * d
            ok = (point_in_rings(nx, ny, [ring]) if ring is not None
                  else coastline_side(nx, ny, coastline) == "water")
            if ok:
                bearing = math.degrees(math.atan2(ux, uy)) % 360
                size = "offenes Meer" if ring is None else f"{area:.0f} km² Fläche"
                note = " — Koordinate prüfen" if d > 500 else ""
                return nx, ny, True, f"{d:.0f} m nach {bearing:.0f}° ins Wasser versetzt ({size}){note}"
    return 0.0, 0.0, False, "kein Wasser gefunden"          # nur verglichen, nie angezeigt


def rose_at(rose: list[float], bearing_deg: float) -> float:
    n = len(rose)
    return rose[int(round((bearing_deg % 360) / (360.0 / n))) % n]


# ── Ableitungen ──────────────────────────────────────────────────────────────

G = 9.81
KN_TO_MS = 0.514444


def wave_height_m(wind_kn: float, fetch_m: float) -> float:
    """Signifikante Wellenhöhe nach der fetch-begrenzten SPM-Beziehung.

        H_s = 0.0016 · U · sqrt(F / g)      (U in m/s, F in m)

    Das ist eine Ingenieursnäherung: sie unterstellt, dass der Wind lange genug
    aus derselben Richtung weht, und rechnet mit U10 statt dem Windstressfaktor.
    Für „ist das hier glatt oder kabbelig" reicht sie; eine Wellenvorhersage
    ersetzt sie nicht.
    """
    u = max(wind_kn, 0.0) * KN_TO_MS
    return 0.0016 * u * math.sqrt(max(fetch_m, 0.0) / G)


def water_label(h_s: float) -> str:
    if h_s < 0.25:
        return "flat"
    if h_s < 0.60:
        return "chop"
    return "wave"


def classify(fetch_up_m: float, fetch_down_m: float, cfg=None) -> tuple[str, float]:
    """Windlage aus Anlauflänge in Luv und Platz nach Lee."""
    offshore_max = 400.0
    lee_min = 500.0
    if cfg is not None:
        g = cfg.get("geometry", {})
        offshore_max = g.get("offshore_max_m", offshore_max)
        lee_min = g.get("lee_room_min_m", lee_min)

    up_open = fetch_up_m > offshore_max
    down_open = fetch_down_m > lee_min
    if not up_open and not down_open:
        return "kein Wasser", 0.10

    ratio = fetch_up_m / max(fetch_down_m, 1.0)
    if not up_open or ratio < 0.15:
        return "ablandig", 0.50           # glatt, aber du treibst raus
    if not down_open or ratio > 6.7:
        return "auflandig", 0.55          # Welle und Shorebreak vor der Nase
    return ("sideshore", 1.0) if 0.35 < ratio < 2.9 else ("side-on", 0.88)


def summarize(rose: list[float]) -> dict:
    """Kennzahlen für den Report: offenste Richtung, Median, Anteil offener Sektoren."""
    n = len(rose)
    best = max(range(n), key=lambda i: rose[i])
    ordered = sorted(rose)
    return {
        "open_bearing": round(best * 360.0 / n),
        "max_fetch_km": round(max(rose) / 1000.0, 1),
        "median_fetch_km": round(ordered[n // 2] / 1000.0, 1),
        "open_share": round(sum(1 for f in rose if f > 1000.0) / n, 2),
    }
