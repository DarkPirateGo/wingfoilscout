#!/usr/bin/env python3
"""Git-Merge-Treiber für geometry.json — vereinigt statt zu streiten.

`geometry.json` ist eine Ablage: Spot-ID → berechnete Ufergeometrie. Zwei
Leute, die unabhängig fehlende Spots rechnen lassen, erzeugen damit einen
Konflikt, der inhaltlich keiner ist — die Einträge ergänzen sich, sie
widersprechen sich nicht. Dieser Treiber vereinigt beide Fassungen.

Bei einer Spot-ID, die beide geändert haben, gewinnt die eigene Fassung: der
Inhalt ist ohnehin abgeleitet, und wer zweifelt, lässt den Spot neu rechnen.

Eingehängt über .gitattributes und tools/install-hooks.sh. Aufruf durch Git:
    merge_geometry.py %A %O %B      (eigene, gemeinsame Basis, fremde)
"""
from __future__ import annotations
import json
import sys


def lies(pfad):
    try:
        with open(pfad, encoding="utf-8") as fh:
            daten = json.load(fh)
        return daten if isinstance(daten, dict) else None
    except (OSError, ValueError):
        return None


def main(argv):
    if len(argv) < 4:
        return 1
    eigen_pfad, _basis, fremd_pfad = argv[1], argv[2], argv[3]
    eigen, fremd = lies(eigen_pfad), lies(fremd_pfad)
    if eigen is None or fremd is None:
        return 1                      # kein JSON — Git soll normal melden

    vereint = dict(fremd)
    vereint.update(eigen)             # bei gleicher ID gewinnt die eigene Fassung
    with open(eigen_pfad, "w", encoding="utf-8") as fh:
        json.dump(vereint, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    nur_fremd = len(set(fremd) - set(eigen))
    print(f"geometry.json vereinigt: {len(vereint)} Spots, {nur_fremd} davon neu von der Gegenseite.",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
