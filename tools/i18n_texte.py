"""Sammelt alle übersetzbaren Texte ein und sagt, was in welcher Sprache fehlt.

    python3 tools/i18n_texte.py              # Übersicht: Zahl der Texte, Lücken je Sprache
    python3 tools/i18n_texte.py --fehlend en # die fehlenden Texte für Englisch als JSON
    python3 tools/i18n_texte.py --alle       # alle Texte mit Fundstellen als JSON

Eingesammelt wird jedes `T("…")`, `TN("…", "…", n)` und `N_("…")` — und ihre
Geschwister für Texte in Daten, `TD()` und `TND()` (seit 2.3.0) — mit einem
festen Text im Python-Code unter wingscout/ und jedes `t('…')`/`N_('…')` in
wingscout/web/*.js. Was übersetzt werden soll, muss so dastehen — ein Text,
der erst zur Laufzeit entsteht, lässt sich nicht einsammeln.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wingscout import i18n  # noqa: E402

FUNKTIONEN = {"T": 1, "N_": 1, "TN": 2, "TD": 1, "TND": 2}   # wie viele feste Texte vorne stehen


def python_texte(pfad: Path) -> list[tuple[str, int]]:
    baum = ast.parse(pfad.read_text(encoding="utf-8"), filename=str(pfad))
    funde = []
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Call):
            continue
        f = knoten.func
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
        if name not in FUNKTIONEN:
            continue
        for arg in knoten.args[:FUNKTIONEN[name]]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                funde.append((arg.value, knoten.lineno))
    return funde


def alle_texte() -> dict[str, list[str]]:
    """Text → Fundstellen („datei:zeile“)."""
    texte: dict[str, list[str]] = {}
    for pfad in sorted((ROOT / "wingscout").rglob("*.py")):
        if "__pycache__" in pfad.parts or pfad.name == "i18n.py":
            continue
        for text, zeile in python_texte(pfad):
            texte.setdefault(text, []).append(f"{pfad.relative_to(ROOT)}:{zeile}")
    for pfad in sorted((ROOT / "wingscout" / "web").glob("*.js")):
        code = pfad.read_text(encoding="utf-8")
        for text in i18n.js_texte(code):
            texte.setdefault(text, []).append(str(pfad.relative_to(ROOT)))
    return texte


def main(argv: list[str]) -> int:
    texte = alle_texte()
    if "--alle" in argv:
        print(json.dumps(texte, ensure_ascii=False, indent=1))
        return 0
    if "--fehlend" in argv:
        sprache = argv[argv.index("--fehlend") + 1]
        kat = i18n.katalog(sprache)
        print(json.dumps({k: v for k, v in texte.items() if k not in kat}, ensure_ascii=False, indent=1))
        return 0
    print(f"{len(texte)} Texte")
    for sprache in i18n.SPRACHEN:
        if sprache == i18n.QUELLE:
            continue
        kat = i18n.katalog(sprache)
        fehlend = [k for k in texte if k not in kat]
        uebrig = [k for k in kat if k not in texte]
        print(f"  {sprache}: {len(texte) - len(fehlend)} übersetzt, {len(fehlend)} fehlen, {len(uebrig)} übrig")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
