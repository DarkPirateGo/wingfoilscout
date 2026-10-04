"""Content-Security-Policy — die zweite Verteidigungslinie (seit 1.19.1).

Die erste ist das Escaping: kein Katalogtext, keine Fremdantwort kommt roh in
eine Seite. Die zweite greift, wenn die erste einmal versagt — wie beim
Sektorfeld `water` bis 1.18.3 (Review 25.09., S1): Skript, das nicht von
Wingfoilscout stammt, läuft dann trotzdem nicht. Dafür trägt jede Antwort eine
frisch gewürfelte Nonce, und nur `<script>`-Blöcke mit genau dieser Nonce
werden ausgeführt; Ereignisattribute (`onerror=`) und `javascript:`-Adressen
sind damit ohnehin tot. Fremde Skripte gibt es nur eines, Leaflet von cdnjs,
mit Prüfsumme.

Die Report-Datei bekommt dieselbe Richtlinie als `<meta http-equiv>` mit
einer Nonce je Erzeugung: ein Katalogtext kennt sie nicht, sein Skript
bleibt stumm — auch als `file://` auf dem iPhone. Liefert der Server die
Datei aus, nimmt er die Nonce aus ihrem Kopf, damit Kopfzeile und Datei
dasselbe sagen.

Was die Richtlinie zulässt, ist genau das, was die Seiten brauchen: Styles
inline (Rasterzellen und Popups tragen `style=`), Leaflet-Stil und -Skript
von cdnjs, Kacheln von OpenStreetMap, Marker-Bilder von cdnjs, Anfragen nur
an den eigenen Server, Rahmen nur vom eigenen Server (die Startseite bettet
den Report ein). Kein `object`, keine fremde `base`, kein Formular nach
draußen.
"""
from __future__ import annotations
import re
import secrets

CDNJS = "https://cdnjs.cloudflare.com"
KACHELN = "https://tile.openstreetmap.org https://*.tile.openstreetmap.org"
# Das Attribut steht in doppelten Anführungszeichen: die Richtlinie selbst ist
# voller einfacher ('self', 'nonce-…') und enthält nie ein doppeltes.
_NONCE_IM_KOPF = re.compile(rb'<meta http-equiv="Content-Security-Policy" content="[^"]*\'nonce-([A-Za-z0-9_-]{16,})\'')


def neue_nonce() -> str:
    return secrets.token_urlsafe(16)


def richtlinie(nonce: str, kopfzeile: bool = True) -> str:
    """Die Richtlinie als Text. `kopfzeile=False` für das `<meta>` im Report:
    `frame-ancestors` gilt dort nicht (Browser ignorieren es im Meta-Element
    mit einer Warnung) und bleibt deshalb weg."""
    teile = [
        "default-src 'self'",
        f"script-src 'nonce-{nonce}' {CDNJS}",
        f"style-src 'self' 'unsafe-inline' {CDNJS}",
        f"img-src 'self' data: {KACHELN} {CDNJS}",
        "connect-src 'self'",
        "font-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-src 'self'",
    ]
    if kopfzeile:
        teile.append("frame-ancestors 'self'")
    return "; ".join(teile)


def meta(nonce: str) -> str:
    """Das Meta-Element für eine Datei, die ohne Server geöffnet wird."""
    return f'<meta http-equiv="Content-Security-Policy" content="{richtlinie(nonce, kopfzeile=False)}">'


def skript(nonce: str, code: str) -> str:
    return f"<script nonce='{nonce}'>{code}</script>"


def nonce_aus_datei(roh: bytes) -> str | None:
    """Die Nonce aus dem Kopf einer gespeicherten Report-Datei — oder None bei
    einem Report von vor 1.19.1. Gesucht wird nur im Kopf: was ein Katalogtext
    in den Rumpf brächte, steht escaped da und kommt hier nie an."""
    m = _NONCE_IM_KOPF.search(roh[:6000])
    return m.group(1).decode("ascii") if m else None
