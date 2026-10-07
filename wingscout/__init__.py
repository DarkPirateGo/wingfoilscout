"""Wingfoilscout — findet Wingfoil-Sessions in Windmodellen und Spotwissen."""
from __future__ import annotations
__version__ = "2.4.0"

# Der Projektordner und der Zwischenspeicher darin — absolut, damit es nicht
# vom Arbeitsverzeichnis abhängt, wo Overpass-Auszüge und Warnfeeds landen.
# Bis 1.6.1 nahmen zwei Quellen "cache/…" relativ: wer die Oberfläche aus
# einem anderen Ordner startete, bekam einen zweiten Cache-Baum.
from pathlib import Path as _Path
ROOT = _Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
# Der Report, den die Oberfläche als Reiter „Ziele“ zeigt — nur zu ihm legt
# eine Suche seit 2.3.0 auch die Fassungen in allen vier Sprachen ab
# (cache/report/, siehe report.fassungen_schreiben).
REPORT = ROOT / "report.html"

# Das Repository — und das Formular, über das die Community Spots vorschlägt
# (seit 2.3.0, .github/ISSUE_TEMPLATE/spot.yml). Wingfoilscout öffnet es nur
# als Link im Browser; gesendet wird erst, wenn jemand es dort abschickt.
REPO = "https://github.com/DarkPirateGo/wingfoilscout"
SPOT_FORMULAR = REPO + "/issues/new"

# CSS und JavaScript von Oberfläche und Report liegen seit 1.16.0 als eigene
# Dateien in wingscout/web/ (Struktur-Review A1): ein Editor liest sie als das,
# was sie sind, `node --check` prüft das JavaScript (tools/check.sh), und
# geschweifte Klammern müssen nicht mehr für f-Vorlagen verdoppelt werden.
WEB = _Path(__file__).resolve().parent / "web"


def lies_web(name: str) -> str:
    """Eine Datei aus wingscout/web/ — gelesen einmal beim Start."""
    return (WEB / name).read_text(encoding="utf-8")
