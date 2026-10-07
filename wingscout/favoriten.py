"""Favoriten: eigene Lieblingsspots, im Report ganz oben (seit 2.4.0).

Gewünscht am 06.10.2026: in der ersten Eingabemaske Spots per Eintippen
(Autovervollständigen) zu einer Liste hinzufügen und mit „Favoriten zuerst
zeigen“ dafür sorgen, dass der Report so beginnt: Favoriten → die besten drei →
Karte. Favoriten werden immer gerechnet, auch außerhalb des Umkreises und
trotz der Filter; die besten drei, die Karte und das Raster bleiben bei der
normalen Suche (siehe cli.run_search).

Die Liste ist persönlich wie das Tagebuch: `favoriten.json` im Projektordner,
nicht versioniert (.gitignore, tools/persoenliche_daten.py). Gespeichert wird
nur, was nach einer Spot-ID aussieht — die Namen kommen beim Anzeigen aus dem
Katalog.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import ROOT
from .spots import ID_MUSTER          # dieselbe Regel wie im Katalog (spots.yaml)

DATEI = ROOT / "favoriten.json"
# Jeder Favorit kostet eine Vorhersage mehr, und der Abschnitt steht vor den
# besten drei — zehn sind eine Hand voll Hausspots, keine zweite Suche.
MAX = 10


def bereinigen(ids, bekannte=None) -> list[str]:
    """Nur gültige IDs, jede einmal, in der gegebenen Reihenfolge, höchstens
    MAX — und mit `bekannte` nur die, die es im Katalog gibt."""
    if isinstance(ids, str):
        ids = ids.split(",")
    if not isinstance(ids, (list, tuple)):
        return []
    rein: list[str] = []
    for roh in ids:
        if not isinstance(roh, str):
            continue
        sid = roh.strip()
        if not ID_MUSTER.fullmatch(sid) or sid in rein:
            continue
        if bekannte is not None and sid not in bekannte:
            continue
        rein.append(sid)
        if len(rein) >= MAX:
            break
    return rein


def laden(pfad: Path | str | None = None) -> dict:
    """{"ids": [...], "zuerst": bool} — fehlt die Datei oder ist sie kaputt,
    eine leere Liste. `zuerst` ist an, solange nichts anderes gemerkt ist."""
    pfad = Path(pfad) if pfad else DATEI
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        daten = None
    if not isinstance(daten, dict):
        daten = {}
    zuerst = daten.get("zuerst", True)
    return {"ids": bereinigen(daten.get("ids") or []), "zuerst": zuerst if isinstance(zuerst, bool) else True}


def speichern(ids, zuerst: bool, bekannte=None, pfad: Path | str | None = None) -> dict:
    """Die Liste ablegen — atomar und nur für den Besitzer lesbar wie
    config.yaml (spotedit.schreibe_atomar). Rückgabe: was gespeichert ist."""
    from .spotedit import schreibe_atomar
    pfad = Path(pfad) if pfad else DATEI
    daten = {"ids": bereinigen(ids, bekannte), "zuerst": bool(zuerst)}
    schreibe_atomar(pfad, json.dumps(daten, ensure_ascii=False, indent=1) + "\n")
    return daten


def aus_args(args) -> list[str]:
    """Welche Favoriten ein Lauf rechnet: die Oberfläche gibt eine Liste,
    die Kommandozeile `--favoriten` (die gemerkten) oder `--favoriten a,b`."""
    wert = getattr(args, "favoriten", None)
    if wert is True or wert == GEMERKT:
        return laden()["ids"]
    return bereinigen(wert or [])


# Was `--favoriten` ohne Wert bedeutet (argparse `const`)
GEMERKT = "gemerkt"
