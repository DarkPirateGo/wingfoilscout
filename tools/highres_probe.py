#!/usr/bin/env python3
"""Einmal ausprobieren, welches hochauflösende Modell welchen Spot abdeckt.

Open-Meteo dokumentiert die Modellgrenzen nicht. Dieses Skript fragt sie ab und
schreibt das Ergebnis nach cache/highres.json — danach weiß Wingfoilscout Bescheid
und muss nicht bei jedem Lauf probieren.

    python3 tools/highres_probe.py            # alle Spots mit Thermikwissen
    python3 tools/highres_probe.py --alle     # der ganze Katalog
    python3 tools/highres_probe.py --neu      # gemerkte Zuordnung verwerfen
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wingscout.config import load_config, KonfigFehler        # noqa: E402
from wingscout.spots import load_spots, KatalogFehler         # noqa: E402
from wingscout.sources import highres                         # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--alle", action="store_true", help="ganzen Katalog prüfen")
    ap.add_argument("--neu", action="store_true", help="gemerkte Zuordnung verwerfen")
    ap.add_argument("--spots", default=str(ROOT / "spots.yaml"))
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    args = ap.parse_args(argv)

    load_config(args.config)                       # legt config.yaml an, falls sie fehlt
    spots = load_spots(args.spots)
    ziel = spots if args.alle else [s for s in spots if s.get("thermal")]
    cache_ordner = ROOT / "cache"
    if args.neu:
        (cache_ordner / highres.CACHE_NAME).unlink(missing_ok=True)

    print(f"{len(ziel)} Spots werden geprüft. Das dauert ein bis zwei Minuten.\n")
    ergebnis, stat = highres.hole(ziel, 2, cache_ordner, log=print)

    print(f"\n{stat.get('abgedeckt', 0)} von {len(ziel)} Spots haben ein hochauflösendes Modell.")
    for kurz, n in sorted(stat.get("modelle", {}).items(), key=lambda x: -x[1]):
        print(f"   {kurz}: {n}")
    ohne = [s for s in ziel if s["id"] not in ergebnis]
    if ohne:
        print(f"\nOhne feines Modell ({len(ohne)}) — dort bleiben die globalen:")
        for s in ohne[:20]:
            print(f"   {s['id']}  {s['name'][:40]}")
        if len(ohne) > 20:
            print(f"   … und {len(ohne) - 20} weitere")
    print(f"\nGemerkt in {cache_ordner / highres.CACHE_NAME}.")
    print("Läuft nicht alles durch? Noch einmal starten — der Cache macht dort weiter.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KatalogFehler, KonfigFehler) as exc:      # Meldung statt Traceback
        raise SystemExit(str(exc))
