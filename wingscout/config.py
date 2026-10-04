"""Konfiguration laden und plausibilisieren."""
from __future__ import annotations
import os
import sys
from pathlib import Path
import yaml

from .i18n import T, meldungswert


class KonfigFehler(ValueError):
    """`config.yaml` fehlt oder ist unbrauchbar — siehe `KatalogFehler` in spots.py."""


class _OhneVerweise(yaml.SafeLoader):
    """`SafeLoader` ohne Verweise (`*name`), sonst in allem wie `safe_load`.

    Ein Verweis setzt einen Knoten an anderer Stelle noch einmal ein. Neun
    Ebenen aus je neun Verweisen sind fast 400 Millionen Einträge aus gut
    500 Bytes; `safe_load` teilt die Knoten nur, aber der erste, der den Wert
    liest — `str()` eines Kommentars, der Katalog —, lief in einen
    `MemoryError`, und das bei jedem Seitenaufruf (Review 04.10.2026, C3).
    Weder spots.yaml noch config.yaml brauchen Verweise; ein Anker (`&name`)
    allein schadet nicht und bleibt erlaubt.
    """

    def compose_node(self, parent, index):
        if self.check_event(yaml.events.AliasEvent):
            raise yaml.composer.ComposerError(
                None, None, "found an alias — aliases (*name) are not supported", self.peek_event().start_mark)
        return super().compose_node(parent, index)


def yaml_laden(fh):
    """Wie `yaml.safe_load`, nur ohne Verweise — für alles, was von Hand oder
    über die Oberfläche geschrieben wird."""
    lader = _OhneVerweise(fh)
    try:
        return lader.get_single_data()
    finally:
        lader.dispose()


# Was beim Lesen einer YAML-Datei außer `yaml.YAMLError` noch fliegen kann:
# ungültiges UTF-8 und Zahlen mit mehr als 4300 Stellen oder ein 13. Monat
# als ValueError, eine Verschachtelung ab etwa 500 Ebenen als RecursionError.
# Bis 2.1.0 kamen sie roh durch jede Seite.
YAML_FEHLER = (yaml.YAMLError, ValueError, RecursionError)


def yaml_meldung(exc, datei: str) -> str:
    """Ein ganzer Satz mit Datei und, wo bekannt, Zeile — derselbe für
    spots.yaml und config.yaml."""
    marke = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
    grund = getattr(exc, "problem", None) or (str(exc).splitlines() or [type(exc).__name__])[0]
    if marke is not None:
        return T("{datei} nicht lesbar, Zeile {zeile}: {grund}", datei=datei, zeile=marke.line + 1, grund=grund)
    return T("{datei} nicht lesbar: {grund}", datei=datei, grund=grund)


class Config(dict):
    """Dict mit Punktzugriff für die oberste Ebene."""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc


VORLAGE = "config.example.yaml"


def ensure_config(path: str | Path) -> Path:
    """Fehlt die persönliche Konfiguration, aus der Vorlage anlegen.

    `config.yaml` enthält Startpunkt, Gewicht und Material — das ist bei jedem
    anders und gehört deshalb niemandem gemeinsam. Versioniert ist nur
    `config.example.yaml`; die persönliche Fassung entsteht beim ersten Start
    daraus und wird von Git ignoriert. So kollidiert sie nie beim Aktualisieren.
    """
    path = Path(path)
    if path.exists():
        return path
    vorlage = path.parent / VORLAGE
    if not vorlage.exists():
        raise KonfigFehler(T("Weder {datei} noch {vorlage} gefunden in {ordner}",
                             datei=path.name, vorlage=VORLAGE, ordner=path.parent))
    # Nur für den Besitzer lesbar: hier stehen Heimatkoordinate und, wenn
    # eingetragen, das Windguru-Passwort (Review 25.09., S13).
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(vorlage.read_text(encoding="utf-8"))
    hinweis = T("{datei} aus {vorlage} angelegt — Startpunkt und Quiver dort eintragen.",
                datei=path.name, vorlage=VORLAGE)
    print(hinweis, file=sys.stderr)
    return path


def load_config(path: str | Path) -> Config:
    path = ensure_config(path)
    if not path.exists():
        raise KonfigFehler(T("Konfiguration nicht gefunden: {pfad}", pfad=path))
    try:
        with path.open(encoding="utf-8") as fh:
            raw = yaml_laden(fh)
    except YAML_FEHLER as exc:
        # Wie bei spots.yaml: mit Zeile, als KonfigFehler — sonst bricht die
        # Oberfläche wortlos ab (Review 25.09., U1).
        raise KonfigFehler(yaml_meldung(exc, path.name)) from exc
    if not isinstance(raw, dict):
        raise KonfigFehler(T("Konfiguration ist kein YAML-Mapping: {pfad}", pfad=path))
    cfg = Config(raw)

    try:
        wings = cfg["quiver"]["wings"]
    except (KeyError, TypeError):
        raise KonfigFehler(T("Kein Abschnitt quiver.wings in {pfad}", pfad=path))
    if not wings:
        raise KonfigFehler(T("Kein Wing in der Konfiguration — ohne Quiver kein Windfenster."))
    for w in wings:
        if w["low"] >= w["high"]:
            # Die Größe kommt aus der Datei — ein `"x\uD800"` darin ließ bis
            # 2.1.0 die Fehlerseite scheitern (meldungswert, C2)
            raise KonfigFehler(T("Wing {groesse}: low muss kleiner als high sein.",
                                 groesse=meldungswert(w["size"])))
    cfg["quiver"]["wings"] = sorted(wings, key=lambda w: -w["size"])
    return cfg


def quiver_range(cfg: Config) -> tuple[float, float]:
    wings = cfg["quiver"]["wings"]
    return min(w["low"] for w in wings), max(w["high"] for w in wings)
