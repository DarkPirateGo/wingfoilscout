#!/usr/bin/env python3
"""Etappe 03 · Ufergeometrie für alle Spots berechnen.

Holt einmalig die OSM-Wassergeometrie um jeden Spot, misst die Anlauflänge in
36 Richtungen und legt das Ergebnis in `geometry.json` ab. Danach braucht
`wingscout` kein Netz mehr dafür — die Rose ändert sich nicht.

    python3 build_geometry.py                 # alles, was noch fehlt
    python3 build_geometry.py --only brouwersdam workum
    python3 build_geometry.py --recompute      # neu rechnen, Cache behalten
    python3 build_geometry.py --force         # alles neu holen (belastet Overpass)
    python3 build_geometry.py --radius 25     # kleinerer Umkreis, schnellere Abfrage

Erster Lauf über 55 Spots dauert je nach Overpass-Auslastung 10–30 Minuten,
größtenteils Wartezeit. Alles wird zwischengespeichert; ein Abbruch ist harmlos,
beim nächsten Start geht es weiter.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wingscout.config import load_config, KonfigFehler        # noqa: E402
from wingscout.spots import load_spots, KatalogFehler         # noqa: E402
from wingscout.shoreline import (auffaellig, load_store, missing,   # noqa: E402
                                 run_batch)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Ufergeometrie je Spot aus OpenStreetMap.")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--spots", default="spots.yaml")
    ap.add_argument("--out", default="geometry.json")
    ap.add_argument("--radius", type=float, default=None, help="Umkreis in km (Standard aus config)")
    ap.add_argument("--dirs", type=int, default=None, help="Anzahl Richtungen (Standard aus config)")
    ap.add_argument("--only", nargs="*", help="nur diese Spot-IDs")
    ap.add_argument("--force", action="store_true",
                    help="die gewählten Spots (mit --only) oder alle neu holen UND neu rechnen "
                         "(belastet Overpass); andere Einträge bleiben erhalten")
    ap.add_argument("--recompute", action="store_true",
                    help="neu rechnen aus dem vorhandenen Cache, ohne neue Abfragen")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    gcfg = cfg.get("geometry", {})
    radius = args.radius or gcfg.get("max_fetch_km", 40.0)
    n_dirs = args.dirs or gcfg.get("ray_count", 36)

    spots = load_spots(args.spots)
    if args.only:
        wanted = set(args.only)
        spots = [s for s in spots if s["id"] in wanted]

    out_path = Path(args.out)
    # Immer vom vorhandenen Bestand aus. `--force` begann bis 1.7.0 mit einem
    # leeren Speicher — zusammen mit `--only` blieben von 275 Einträgen sechs
    # übrig, und der Rest war weg, bis Git ihn zurückbrachte. Neu holen heißt
    # jetzt: die gewählten Spots werden überschrieben, alle anderen bleiben.
    store = load_store(out_path)

    todo = spots if (args.force or args.recompute) else missing(spots, store)
    print(f"{len(spots)} Spots · {len(store)} schon berechnet · {len(todo)} offen "
          f"· Umkreis {radius:.0f} km · {n_dirs} Richtungen\n")

    done, failed = run_batch(todo, store, out_path, radius, n_dirs,
                             print, force=args.force)

    print(f"\n{done} berechnet, {failed} fehlgeschlagen → {out_path}")
    schlecht, pruefen = auffaellig(store)
    if schlecht:
        print(f"\nUnbrauchbar — hier stimmt die Koordinate fast sicher nicht ({len(schlecht)}):")
        for sid, grund, _ in schlecht:
            print(f"  · {sid}: {grund}")
    if pruefen:
        print(f"\nWeit vom Pin ins Wasser versetzt — Koordinate nachsehen ({len(pruefen)}):")
        for sid, grund, _ in pruefen:
            print(f"  · {sid}: {grund}")
    if failed:
        print(f"\n{failed} Spots sind nicht durchgelaufen (meist Overpass überlastet).")
        print("Einfach noch einmal starten — der Lauf macht bei den offenen weiter.")
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KatalogFehler, KonfigFehler) as exc:      # Meldung statt Traceback
        raise SystemExit(str(exc))
