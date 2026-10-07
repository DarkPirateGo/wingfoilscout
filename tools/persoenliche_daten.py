#!/usr/bin/env python3
"""Was nie ins öffentliche Repository darf — eine Liste für alle Wächter.

Drei Stellen fragen hier nach, damit niemand drei Listen pflegt:
`tools/veroeffentlichen.sh` vor dem Commit, `tools/check.sh` (also auch der
Pre-Commit-Hook) und der Prüflauf auf GitHub (`.github/workflows/tests.yml`).
Dieselben Pfade stehen in `.gitignore`; `tests/test_sicherheit_repo.py` prüft,
dass beide zusammenpassen. Anlass: Review 04.10.2026, D1 — `git add -A` nahm
alles mit, was `.gitignore` nicht kannte: „config Kopie.yaml“, die
`.neu`-Zwischendateien der App, einen Takeout-Ordner, Bildschirmfotos.

Aufruf:
  git ls-files | python3 tools/persoenliche_daten.py dateien [--mit-grund]
      nennt jeden Pfad, der nie ins Repository gehört (Exit 1, wenn einer dabei ist)
  git diff --cached -U0 | python3 tools/persoenliche_daten.py heimat
      sucht in den neuen Zeilen des Diffs die Heimatkoordinate aus der eigenen
      config.yaml oder einen Punkt keinen Kilometer daneben — Exit 1 bei einem
      Fund, 2 wenn sie sich nicht prüfen lässt; ohne config.yaml gibt es nichts
      zu prüfen

Git ruft das Skript nicht selbst auf, es bekommt dessen Ausgabe: die
Werkzeuge starten keine anderen Programme (Sicherheitsregel seit dem Audit
vom 13.09.2026, tests/test_security.py).
"""
from __future__ import annotations

import math
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (Muster für den Pfad relativ zum Projektordner, Grund). Groß und klein zählen
# gleich — auf dem Mac liest Git auch .gitignore so (core.ignorecase).
VERBOTEN = [
    (r"^config(?!\.example\.yaml$)[^/]*\.yaml$|(^|/)config\.yaml$",
     "persönliche Konfiguration oder eine Kopie davon"),
    (r"(^|/)tagebuch\.json$|^tagebuch[^/]*\.json$", "Logbuch"),
    (r"(^|/)favoriten\.json$|^favoriten[^/]*\.json$", "eigene Favoriten"),
    (r"(^|/)modellguete\.json$|^modellguete[^/]*\.json$", "eigener Modellvergleich"),
    (r"(^|/)ui_defaults\.json$|^ui_defaults[^/]*\.json$", "gespeicherte Voreinstellungen"),
    (r"(^|/)sprache\.txt$", "eigene Sprachwahl"),
    (r"(^|/)report\.html$|^report[^/]*\.html$|(^|/)vorschau\.html$|_tmp\.html$"
     r"|(^|/)live_[^/]*\.(json|html)$", "Report oder Zwischenstand eines echten Laufs"),
    (r"(^|/)cache/", "Zwischenspeicher, kennt den Startpunkt"),
    (r"\.neu$", "halb geschriebene Zwischendatei der App"),
    (r"^import/[^/]*\.(csv|json)$|(^|/)takeout/", "Export einer eigenen Liste"),
    (r"\.(gpx|kml|kmz|geojson|zip)$", "Track, Kartenexport oder Archiv"),
    (r"(^|/)(bildschirmfoto|bildschirmaufnahme|screenshot|screen recording)[^/]*(/|$)",
     "Bildschirmfoto oder Bildschirmaufnahme"),
    (r"\.bak$|~$|(^|/)\.[^/]*\.sw[^/]$", "Sicherungs- oder Editordatei"),
    (r"^\.claude/settings\.local\.json$|(^|/)claude\.local\.md$", "lokale Einstellungen für Claude"),
    (r"(^|/)\.ds_store$", "Finder-Datei, verrät Dateinamen"),
    (r"(^|/)claude outputs/", "Ablage der Claude-App"),
]
_VERBOTEN = [(re.compile(muster, re.IGNORECASE), grund) for muster, grund in VERBOTEN]


def grund(pfad: str) -> str | None:
    """Warum `pfad` nie ins Repository gehört — None, wenn er darf."""
    pfad = pfad.strip().replace("\\", "/")
    for muster, warum in _VERBOTEN:
        if muster.search(pfad):
            return warum
    return None


def verbotene(pfade) -> list[tuple[str, str]]:
    """[(Pfad, Grund)] für jeden Pfad, der nie ins Repository gehört."""
    return [(p, g) for p in pfade if p.strip() for g in [grund(p)] if g]


# ── Heimatkoordinate ─────────────────────────────────────────────────────────
# Gesucht wird nicht nur der Wert aus config.yaml, sondern jeder Punkt in
# seiner Nähe: das Beispiel, das bis 2.1.0 in Vorlage und Tests stand, war
# auf zwei Stellen gerundet und lag damit wenige hundert Meter neben dem
# eigenen Viertel (Review 04.10.2026, D2). Gröber als zwei Nachkommastellen
# (~1 km) ist eine Stadt, kein Wohnort — solche Zahlen zählen nicht.
ZAHL = re.compile(r"(?<![\d.])-?\d{1,3}[.,]\d{2,}")
UMKREIS_KM = 1.0
# So nah stehen Breite und Länge, wenn sie zusammengehören:
# `"lat": 1.23, "lon": 4.56`, `origin=1.23,4.56`, `lat: 1.23⏎    lon: 4.56`.
NAEHE = 80
HUNK = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _als_text(wert) -> str:
    """Eine Koordinate aus der YAML-Datei als Dezimaltext, ohne Exponent."""
    return format(Decimal(repr(float(str(wert).replace(",", ".")))), "f")


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    x = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(x)))


def fundstellen(text: str, lat, lon, umkreis_km: float = UMKREIS_KM) -> list[int]:
    """Zeilen (ab 1), in denen eine Breite und eine Länge dicht beieinander
    stehen, die zusammen höchstens `umkreis_km` vom Punkt (lat, lon) entfernt
    sind — gleich, ob genauer, gröber oder etwas daneben geschrieben."""
    lat, lon = float(lat), float(lon)
    breiten, laengen = [], []
    for m in ZAHL.finditer(text):
        try:
            wert = float(m.group(0).replace(",", "."))
        except ValueError:
            continue
        if abs(wert - lat) <= 0.1:
            breiten.append((m.start(), wert))
        if abs(wert - lon) <= 0.2:
            laengen.append((m.start(), wert))
    zeilen = {text.count("\n", 0, min(pb, pl)) + 1
              for pb, b in breiten for pl, la in laengen
              if pb != pl and abs(pb - pl) <= NAEHE and _km(b, la, lat, lon) <= umkreis_km}
    return sorted(zeilen)


def heimat(config: Path | None = None) -> tuple[str, str] | None:
    """(Breite, Länge) aus `rider.home` der eigenen config.yaml, als Text.

    None, wenn es die Datei oder den Punkt nicht gibt; ValueError, wenn die
    Datei da ist, sich aber nicht lesen lässt — dann lässt sich auch nicht
    prüfen, ob der Punkt irgendwo steht."""
    config = ROOT / "config.yaml" if config is None else Path(config)
    if not config.is_file():
        return None
    import yaml
    try:
        daten = yaml.safe_load(config.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"{config.name}: {exc}") from exc
    fahrer = daten.get("rider") if isinstance(daten, dict) else None
    home = fahrer.get("home") if isinstance(fahrer, dict) else None
    if not isinstance(home, dict):
        return None
    try:
        return _als_text(home["lat"]), _als_text(home["lon"])
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None


def neue_bloecke(diff: str) -> list[tuple[str, int, str]]:
    """(Datei, erste Zeile, Text) je Block hinzugefügter Zeilen eines Diffs
    (`git diff --cached -U0`); entfernte Zeilen zählen nicht."""
    bloecke: list[tuple[str, int, str]] = []
    datei, nr, start, zeilen, im_kopf = None, 0, 0, [], False

    def abschliessen():
        if datei and zeilen:
            bloecke.append((datei, start, "\n".join(zeilen)))
        zeilen.clear()

    for zeile in diff.split("\n"):
        if zeile.startswith("diff --git "):
            abschliessen()
            datei, im_kopf = None, True
            continue
        if im_kopf and zeile.startswith("+++ "):
            ziel = zeile[4:].rstrip("\t").strip('"')
            datei = ziel[2:] if ziel.startswith("b/") else None     # /dev/null: gelöscht
            continue
        m = HUNK.match(zeile)
        if m:
            abschliessen()
            im_kopf, nr = False, int(m.group(1))
            continue
        if not im_kopf and zeile.startswith("+"):
            if not zeilen:
                start = nr
            zeilen.append(zeile[1:])
            nr += 1
    abschliessen()
    return bloecke


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["dateien"]:
        treffer = verbotene(sys.stdin.read().splitlines())
        for pfad, warum in treffer:
            print(f"{pfad}   ({warum})" if "--mit-grund" in argv else pfad)
        return 1 if treffer else 0
    if argv[:1] == ["heimat"]:
        # Immer ganz lesen, auch wenn es nichts zu prüfen gibt: wer vorn in die
        # Leitung schreibt (git diff), bräche sonst mit SIGPIPE ab.
        diff = sys.stdin.buffer.read().decode("utf-8", "replace")
        try:
            punkt = heimat()
        except ValueError as exc:
            print(f"   config.yaml lässt sich nicht lesen ({exc}) — ob die Heimatkoordinate "
                  "im Commit steht, ist so nicht prüfbar.")
            return 2
        if punkt is None:
            return 0
        funde = [(datei, start + zeile - 1) for datei, start, text in neue_bloecke(diff)
                 for zeile in fundstellen(text, *punkt)]
        if funde:
            print("   Die Heimatkoordinate aus config.yaml (rider.home) — oder ein Punkt keinen")
            print("   Kilometer daneben — steht im Commit:")
            for datei, zeile in funde:
                print(f"     {datei}, Zeile {zeile}")
        return 1 if funde else 0
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
