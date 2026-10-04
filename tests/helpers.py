"""Gemeinsames für alle Tests: Pfade, Konfiguration, Hilfen ohne Netz."""
from __future__ import annotations
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wingscout.config import load_config          # noqa: E402

CONFIG = ROOT / "config.example.yaml"     # die persönliche config.yaml ist nicht versioniert
SPOTS = ROOT / "spots.yaml"


def cfg():
    return load_config(CONFIG)


def square_lake(lat0: float, lon0: float, x0: float, x1: float, y0: float, y1: float) -> dict:
    """OSM-artige Antwort: eine geschlossene Wasserfläche als Rechteck in Metern
    um (lat0, lon0). Damit lassen sich Ufergeometrie und Anlauflänge ohne
    Overpass prüfen."""
    m_lat = 111320.0
    m_lon = 111320.0 * math.cos(math.radians(lat0))

    def pt(x, y):
        return {"lat": lat0 + y / m_lat, "lon": lon0 + x / m_lon}

    ring = [pt(x0, y0), pt(x1, y0), pt(x1, y1), pt(x0, y1), pt(x0, y0)]
    return {"elements": [{"type": "way", "id": 1, "tags": {"natural": "water"}, "geometry": ring}]}
