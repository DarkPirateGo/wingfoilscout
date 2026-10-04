"""Gemeinsames für alle Tests.

Die Tests brauchen kein Netz — und seit 1.14.0 bekommen sie keines. Bis dahin
stand das nur in ENTWICKLUNG.md; am 20.09.2026 fragte ein Test der Sonde
tatsächlich Rijkswaterstaat an, weil eine neue Abfrage nicht untergeschoben
war, und fiel nur zufällig auf (die Prüfumgebung hatte kein Netz). Jetzt
scheitert jeder Aufruf nach draußen laut, bevor er rausgeht; nur der lokale
Testserver (127.0.0.1) ist erreichbar.
"""
from __future__ import annotations
import os
import urllib.parse
import urllib.request

# Kein Netz im Prüflauf: der Ortsname für neue Spots (Nominatim) bleibt aus.
# Die Tests, die ihn brauchen, schieben die Antwort unter.
from wingscout.sources import ortsname as _ortsname
_ortsname.AKTIV = False

_urlopen = urllib.request.urlopen

# Die Tests prüfen die deutschen Texte — unabhängig davon, welche Sprache auf
# diesem Rechner im Umschalter gewählt ist (sprache.txt) oder im System gilt.
os.environ["WINGSCOUT_SPRACHE"] = "de"


class NetzImTest(RuntimeError):
    """Ein Test wollte ins Netz — die Antwort gehört untergeschoben."""


def _nur_lokal(url, *args, **kwargs):
    ziel = url.full_url if isinstance(url, urllib.request.Request) else str(url)
    host = urllib.parse.urlsplit(ziel).hostname or ""
    if host not in ("127.0.0.1", "localhost"):
        raise NetzImTest(f"Netzaufruf im Test: {ziel[:120]}")
    return _urlopen(url, *args, **kwargs)


urllib.request.urlopen = _nur_lokal
