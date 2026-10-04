"""Ufergeometrie je Spot — einmal holen, danach rechnet das Tool ohne Netz.

Hier liegt der eigentliche Vorgang, damit ihn beide Wege nutzen können: das
Skript `build_geometry.py` und der Knopf in der Oberfläche. Vorher steckte er
im Skript, was den Import aus der Oberfläche davon abhängig machte, aus welchem
Verzeichnis gestartet wurde.
"""
from __future__ import annotations
import json
import math
from pathlib import Path

from . import geometry as geo
from .i18n import T, TN, N_                                       # noqa: F401
from .sources.overpass import fetch_water, fetch_protected, OverpassError   # noqa: F401


def rechne(raw: dict, spot: dict, radius_km: float, n_dirs: int) -> dict:
    """Aus einem OSM-Auszug die Ufergeometrie rechnen — ohne Netz.

    Getrennt vom Holen, damit der Prüfstand und die Tests denselben Weg
    nehmen wie der Geometrielauf.

    `wasser` sagt, ob der Ursprung der Rose im Wasser liegt (oder dorthin
    versetzt wurde). Bis 1.7.0 galt bei gescheitertem Versetzen „Rose gilt“,
    sobald die Rose im Mittel 300 m maß — ein Punkt auf der Schwäbischen Alb
    bekam damit eine Rose aus Strahlen, die zehn Kilometer über Land bis zur
    Donau liefen, und sah aus wie ein See. Ohne Wasser innerhalb von drei
    Kilometern ist der Pin an Land, und die Rose beschreibt nichts.
    """
    parts = geo.segments_from_osm(raw, spot["lat"], spot["lon"])
    index = geo.SegmentIndex(parts["segments"])
    ox, oy, moved, status = geo.snap_into_water(parts, index, n_dirs, radius_km,
                                                prefer=spot.get("water_body"))
    rose = geo.fetch_rose(index, ox, oy, n_dirs, radius_km)
    wasser = "kein Wasser gefunden" not in status
    out = {
        "n_dirs": n_dirs,
        "radius_km": radius_km,
        "rose_m": rose,
        "origin_offset_m": [round(ox), round(oy)],
        "snapped": moved,
        "wasser": wasser,
        # gespeichert in geometry.json: deutsch, übersetzt wird beim Anzeigen
        "status": status if wasser else N_("kein Wasser innerhalb von 3 km — liegt der Pin an Land?"),
        "segments": len(parts["segments"]),
        "rings": len(parts["rings"]),
        "coastline_segments": len(parts["coastline"]),
    }
    out.update(geo.summarize(rose))
    return out


def build_one(spot: dict, radius_km: float, n_dirs: int,
              force: bool = False, log=None) -> dict:
    """Wassergeometrie holen, Anlauflänge in `n_dirs` Richtungen messen."""
    raw = fetch_water(spot["id"], spot["lat"], spot["lon"], radius_km,
                      force=force, log=log)
    out = rechne(raw, spot, radius_km, n_dirs)
    try:
        out["protected"] = fetch_protected(spot["id"], spot["lat"], spot["lon"], force=force)
    except Exception:                                   # noqa: BLE001 — Zusatzinfo, kein Abbruchgrund
        out["protected"] = []
    return out


# Ab wann ist eine Ufergeometrie unbrauchbar? Nicht die Statusmeldung
# entscheidet das, sondern die gemessene Rose: 300 m Wasser in der besten
# Richtung sind keine Session, egal wie sauber der Punkt gesetzt wurde.
MIN_FETCH_KM = 0.3
WEIT_VERSETZT_M = 1000.0


def befund(entry: dict) -> tuple[str, str] | None:
    """Was an einem Eintrag auffällt — oder None, wenn nichts.

    Rückgabe ist ("unbrauchbar" | "pruefen", Begründung).

    Die frühere Warnliste nahm `open_share < 0.15` und nannte alles davon
    „Koordinate prüfen". Das traf 67 Spots, von denen 39 schlicht kleine
    Baggerseen waren — auf 800 m Wasser ist keine Richtung „offen", das ist
    kein Fehler, sondern ein kleiner See. Gleichzeitig fehlten 25 Spots, deren
    Pin kilometerweit danebenlag, die aber viel offenes Wasser hatten. Eine
    Liste, die das Falsche meldet und das Richtige übersieht, liest man nach
    dem zweiten Mal nicht mehr.
    """
    if entry.get("wasser") is False:
        return ("unbrauchbar", T("kein Wasser innerhalb von 3 km — liegt der Pin an Land?"))
    fetch = entry.get("max_fetch_km") or 0.0
    if fetch < MIN_FETCH_KM:
        return ("unbrauchbar", T("höchstens {m} m Wasser in jeder Richtung", m=f"{fetch * 1000:.0f}"))
    versatz = math.hypot(*(entry.get("origin_offset_m") or [0.0, 0.0]))
    if versatz > WEIT_VERSETZT_M:
        return ("pruefen", T("{m} m vom Pin ins Wasser versetzt", m=f"{versatz:.0f}"))
    return None


def auffaellig(store: dict, ignorieren=()) -> tuple[list, list]:
    """(unbrauchbar, zu prüfen) — beide nach Schwere sortiert.

    `ignorieren` sind Spot-IDs, die jemand angesehen und für richtig befunden
    hat (`geo_ok: true` im Katalog). Ohne das stünden sie bei jedem Lauf wieder
    in der Liste, und eine Liste, die man nicht abarbeiten kann, liest man
    irgendwann gar nicht mehr.
    """
    ignorieren = set(ignorieren)
    schlecht, pruefen = [], []
    for sid, entry in store.items():
        if sid in ignorieren:
            continue
        b = befund(entry)
        if not b:
            continue
        (schlecht if b[0] == "unbrauchbar" else pruefen).append((sid, b[1], entry))
    schlecht.sort(key=lambda x: x[2].get("max_fetch_km") or 0.0)
    pruefen.sort(key=lambda x: -math.hypot(*(x[2].get("origin_offset_m") or [0, 0])))
    return schlecht, pruefen


def load_store(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def save_store(path: str | Path, store: dict) -> None:
    from .spotedit import schreibe_atomar
    schreibe_atomar(path, json.dumps(store, indent=1))


def missing(spots, store: dict) -> list:
    """Spots ohne Geometrie — die Reihenfolge des Katalogs bleibt erhalten."""
    return [s for s in spots if s["id"] not in store]


def run_batch(spots, store: dict, store_path, radius_km: float, n_dirs: int,
              log, force: bool = False) -> tuple[int, int]:
    """Reihe von Spots rechnen, nach jedem sichern. Rückgabe: (fertig, Fehler).

    Nach jedem Spot zu speichern ist Absicht: der Lauf dauert Minuten, und ein
    Abbruch mittendrin darf nicht die ganze Arbeit kosten.
    """
    done = failed = 0
    for i, spot in enumerate(spots, 1):
        log(f"[{i}/{len(spots)}] {spot['name']}")
        try:
            entry = build_one(spot, radius_km, n_dirs, force, log)
        except OverpassError as exc:
            log("    " + T("Overpass nicht erreichbar: {fehler}", fehler=exc))
            failed += 1
            continue
        except Exception as exc:                        # noqa: BLE001
            import traceback
            where = traceback.extract_tb(exc.__traceback__)[-1]
            log("    " + T("Fehler beim Rechnen: {fehler} ({datei} Zeile {zeile})",
                          fehler=exc, datei=Path(where.filename).name, zeile=where.lineno))
            failed += 1
            continue
        store[spot["id"]] = entry
        save_store(store_path, store)
        done += 1
        warn = "  ⚠ " if entry["open_share"] < 0.15 else "    "
        # Status und Namen sind gespeicherte Daten (deutsch): die festen Texte
        # darunter — „im Wasser“, „Schutzgebiet ohne Namen“ — übersetzt T().
        protected = ", ".join(T(p["name"]) for p in entry.get("protected", [])[:2])
        log(warn + T("{status} · offenste Richtung {richtung}° · Anlauf max {max} km, Median {median} km",
                     status=T(entry["status"]), richtung=entry["open_bearing"],
                     max=entry["max_fetch_km"], median=entry["median_fetch_km"])
            + ("\n    " + T("Schutzgebiet: {namen}", namen=protected) if protected else ""))
    return done, failed
