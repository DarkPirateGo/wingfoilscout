"""Sonnenauf- und -untergang, selbst gerechnet.

Wingfoilscout fragt die Sonnenzeiten eigentlich bei Open-Meteo mit ab. Nur trägt
die Antwort einen Modellsuffix, sobald mehrere Modelle angefordert werden —
aus `sunrise` wird `sunrise_dwd_icon_seamless`. Der Zugriff auf `sunrise` ging
dann ins Leere, die Tageslichtprüfung lief leer mit, und der Report bot
Sessions um drei Uhr nachts an. Der Suffix wird jetzt mitgelesen; dieses Modul
ist die zweite Verteidigungslinie: Es rechnet die Zeiten aus Breite, Länge und
Datum, damit eine fehlende oder umbenannte Antwort nie wieder dazu führt, dass
die Nacht stillschweigend als fahrbar durchgeht.

Gerechnet wird mit der gängigen Sonnenstandsgleichung (Wikipedia, „Sunrise
equation"): mittlere Anomalie, Mittelpunktsgleichung, ekliptikale Länge,
Deklination, Stundenwinkel bei einer Sonnenhöhe von −0,833° (Refraktion plus
Sonnenradius). Das ist auf etwa eine Minute genau — für die Frage, ob eine
Stunde hell ist, mehr als ausreichend. Ich habe die Umsetzung gegen
Invarianten geprüft, nicht gegen eine Tabelle: Tagbogen zur Tagundnachtgleiche
zwölf Stunden, wahrer Mittag am Nullmeridian nahe 12 Uhr UTC, Polartag und
Polarnacht jenseits des Polarkreises. Dass sie mit den Zeiten von Open-Meteo
übereinstimmt, prüft das Programm bei jedem echten Lauf selbst nach.
"""
from __future__ import annotations
import math
from datetime import date, datetime, timedelta, timezone

HOEHE_GRAD = -0.833          # Sonnenmitte unter dem Horizont bei sichtbarem Aufgang
SCHIEFE_GRAD = 23.4397       # Schiefe der Ekliptik


class Polartag(Exception):
    """Die Sonne geht an diesem Tag nicht unter."""


class Polarnacht(Exception):
    """Die Sonne geht an diesem Tag nicht auf."""


def _julianischer_tag(tag: date) -> float:
    """Julianisches Datum um 00:00 UT."""
    a = (14 - tag.month) // 12
    y = tag.year + 4800 - a
    m = tag.month + 12 * a - 3
    jdn = (tag.day + (153 * m + 2) // 5 + 365 * y
           + y // 4 - y // 100 + y // 400 - 32045)
    return jdn - 0.5


def _zu_datum(jd: float) -> datetime:
    """Julianisches Datum → UTC-Zeitpunkt."""
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(days=jd - 2440587.5)


def zeiten_utc(lat: float, lon: float, tag: date) -> tuple[datetime, datetime]:
    """(Aufgang, Untergang) in UTC. Wirft Polartag/Polarnacht, wenn es keine gibt."""
    n = round(_julianischer_tag(tag) - 2451545.0 + 0.0008)
    # Die Formel rechnet mit westlicher Länge, hier ist Ost positiv — daher
    # minus. Mit Plus stimmt am Nullmeridian alles und sonst nichts: bei 8,7° Ost
    # lag der wahre Mittag damit 69 Minuten zu spät.
    j_stern = n - lon / 360.0
    m = math.radians((357.5291 + 0.98560028 * j_stern) % 360.0)
    c = (1.9148 * math.sin(m) + 0.0200 * math.sin(2 * m) + 0.0003 * math.sin(3 * m))
    lam = math.radians((math.degrees(m) + c + 180.0 + 102.9372) % 360.0)
    j_mittag = (2451545.0 + j_stern + 0.0053 * math.sin(m) - 0.0069 * math.sin(2 * lam))

    dek = math.asin(math.sin(lam) * math.sin(math.radians(SCHIEFE_GRAD)))
    phi = math.radians(lat)
    zaehler = math.sin(math.radians(HOEHE_GRAD)) - math.sin(phi) * math.sin(dek)
    nenner = math.cos(phi) * math.cos(dek)
    if nenner == 0:
        raise Polarnacht("Pol")
    cos_w = zaehler / nenner
    if cos_w > 1.0:
        raise Polarnacht(f"{lat:.1f}°, {tag}")
    if cos_w < -1.0:
        raise Polartag(f"{lat:.1f}°, {tag}")
    w = math.degrees(math.acos(cos_w))
    return _zu_datum(j_mittag - w / 360.0), _zu_datum(j_mittag + w / 360.0)


def mittag_utc(lat: float, lon: float, tag: date) -> datetime:
    """Wahrer Mittag — nur für die Prüfung der Rechnung interessant."""
    auf, unter = zeiten_utc(lat, lon, tag)
    return auf + (unter - auf) / 2


def zeiten_lokal(lat: float, lon: float, tag: date, offset_s: int) -> tuple[datetime, datetime]:
    """(Aufgang, Untergang) als zeitzonenlose lokale Zeit, wie sie Open-Meteo liefert.

    Bei Polartag gilt der ganze Tag als hell, bei Polarnacht keine Minute — so
    bleibt die Rückgabe an der Aufrufstelle ein schlichtes Zeitfenster.
    """
    versatz = timedelta(seconds=offset_s)
    beginn = datetime.combine(tag, datetime.min.time())
    try:
        auf, unter = zeiten_utc(lat, lon, tag)
    except Polartag:
        return beginn, beginn + timedelta(days=1)
    except Polarnacht:
        return beginn, beginn
    return (auf + versatz).replace(tzinfo=None), (unter + versatz).replace(tzinfo=None)
