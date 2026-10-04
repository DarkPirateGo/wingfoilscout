"""XML aus fremder Hand einlesen — ohne DOCTYPE, ohne Entitäten.

GPX, KML und der MeteoAlarm-Feed brauchen beides nie. Eine Datei, die es
trotzdem mitbringt, ist entweder kaputt oder böse gemeint: Entitäten, die
sich gegenseitig tausendfach aufrufen, kosten Speicher, bis das Programm
kippt („billion laughs“). Neuere expat-Fassungen bremsen das, Apples Python
3.9 je nach macOS-Stand nicht — deshalb die Prüfung hier, vor dem Parser.

Bis 1.18.3 sah `ingest._xml` nur die ersten 4000 Zeichen an; ein Kommentar
davor reichte, um daran vorbeizukommen (Review 25.09.2026, S5). Jetzt gilt
der ganze Text — und das genügt: ohne `<!DOCTYPE` kann kein XML-Dokument
eigene Entitäten erklären, expat lehnt jede unbekannte Entität dann als
Fehler ab. Ein `<!DOCTYPE` innerhalb eines Kommentars ist für expat
Kommentartext; die Suche ist also strenger als nötig, nie zu lasch.

Seit 2.1.1 auch nicht tiefer als `MAX_TIEFE` Ebenen (Review 04.10.2026,
C10). Wer einen Baum mit `iter()` je Element durchsucht — MeteoAlarm je
Eintrag und Parameter, der KML-Import je Placemark —, zahlt bei tausendfach
ineinander geschachtelten Elementen quadratisch: 4000 Ebenen in 50 KB
kosteten Sekunden. Ein GPX hat sechs, sieben Ebenen, ein KML mit Ordnern
selten mehr als zwölf, der Warnfeed vier.
"""
from __future__ import annotations
import re
import xml.etree.ElementTree as ET

VERBOTEN = re.compile(r"<!\s*(?:doctype|entity)", re.I)
MAX_ZEICHEN = 8 * 1024 * 1024        # mehr XML hat kein Wegpunkt-Export und kein Warnfeed
MAX_TIEFE = 64


class _ZuTief(ValueError):
    pass


class _Baumbauer(ET.TreeBuilder):
    """Der übliche TreeBuilder, der mitzählt, wie tief er gerade ist."""

    def __init__(self, grenze: int):
        super().__init__()
        self._tiefe = 0
        self._grenze = grenze

    def start(self, tag, attrs):
        self._tiefe += 1
        if self._tiefe > self._grenze:
            raise _ZuTief(self._tiefe)
        return super().start(tag, attrs)

    def end(self, tag):
        self._tiefe -= 1
        return super().end(tag)


def lesen(text: str):
    """Der Wurzelknoten — oder None, wenn das Dokument nicht sein darf oder
    nicht lesbar ist (dazu zählt: tiefer als `MAX_TIEFE` verschachtelt)."""
    if not text or len(text) > MAX_ZEICHEN or VERBOTEN.search(text):
        return None
    try:
        parser = ET.XMLParser(target=_Baumbauer(MAX_TIEFE))
        parser.feed(text)
        return parser.close()
    except (ET.ParseError, ValueError):
        return None
