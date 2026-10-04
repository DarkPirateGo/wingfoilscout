"""Ortsname zu einer Koordinate — für neue Spots, die ohne Namen kommen.

Bis 1.13 bekam ein Spot ohne Namen „Spot 47.6143, 11.3394“ (aus der
Google-Liste „Pin 47.6143, 11.3394“) und hieß so, bis jemand ihn von Hand
umbenannte — am 20.09.2026 waren es 54. Jetzt fragt Wingfoilscout beim Eintragen
Nominatim, den Geocoder von OpenStreetMap, nach dem nächsten Ort und dem Land.

Nominatim (nominatim.openstreetmap.org/reverse) ist frei und ohne Schlüssel,
verlangt aber laut Nutzungsrichtlinie höchstens eine Anfrage je Sekunde und
einen Absender, der sich zu erkennen gibt — beides hält dieses Modul ein.
Gefragt wird zweimal: auf Stufe 14 (Dorf, Ortsteil) für den Namen und auf
Stufe 10 (Gemeinde) als Rückfall. Die Antwortform ist am 20.09.2026 an 278
Spots des Katalogs gelesen worden (`name`, `addresstype`, `address.village`,
`address.town`, `address.city`, `address.hamlet`, `address.country_code` …).

Fällt der Dienst aus, bleibt alles wie vorher: der Spot heißt nach seiner
Koordinate, das Land kommt aus den groben Rahmen in `ingest.py`.
"""
from __future__ import annotations
import json
import threading
import time
import urllib.parse
import urllib.request

from .. import CACHE
from ..ingest import name_putzen
from .netz import lies, USER_AGENT

ENDPOINT = "https://nominatim.openstreetmap.org/reverse"
TIMEOUT = 10
CACHE_DATEI = CACHE / "ortsnamen.json"
AKTIV = True                 # die Tests schalten das ab — kein Netz im Prüflauf
_SPERRE = threading.Lock()
_LETZTE = [0.0]
ORT_FELDER = ("village", "town", "city", "hamlet", "suburb", "quarter", "locality", "municipality")


def _hole(lat: float, lon: float, zoom: int) -> dict:
    params = {"format": "jsonv2", "lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "zoom": zoom,
              "addressdetails": 1, "accept-language": "de"}
    req = urllib.request.Request(f"{ENDPOINT}?{urllib.parse.urlencode(params)}",
                                 headers={"User-Agent": USER_AGENT})
    with _SPERRE:                                        # höchstens eine Anfrage je Sekunde
        warten = 1.1 - (time.monotonic() - _LETZTE[0])
        if warten > 0:
            time.sleep(warten)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                daten = json.loads(lies(resp, 1024 * 1024).decode("utf-8"))
        finally:
            _LETZTE[0] = time.monotonic()
    return daten if isinstance(daten, dict) else {}


def ort_aus(antwort: dict) -> str:
    """Der Ort aus einer Nominatim-Antwort — Dorf vor Stadt vor Weiler; der
    Name der Antwort selbst nur, wenn sie ein Ort ist.

    Geputzt wie ein Name aus einer Importdatei (`ingest.name_putzen`): bis
    2.1.0 kam ein Name von 500 000 Zeichen samt Steuerzeichen ungekürzt in
    den Eintrag, und ein einzelnes Surrogat ließ das Schreiben des
    Zwischenspeichers scheitern (Review 04.10.2026, C25)."""
    adresse = antwort.get("address") if isinstance(antwort.get("address"), dict) else {}
    for feld in ORT_FELDER:
        wert = name_putzen(adresse.get(feld))
        if wert:
            return wert
    if antwort.get("addresstype") in ORT_FELDER:
        return name_putzen(antwort.get("name"))
    return ""


def vorschlag_aus(fein: dict, grob: dict) -> dict | None:
    """(Antwort Stufe 14, Antwort Stufe 10) → {"name", "country"} oder None."""
    name = ort_aus(fein) or ort_aus(grob)
    land = str(((fein.get("address") or {}) if isinstance(fein.get("address"), dict) else {}).get("country_code")
               or ((grob.get("address") or {}) if isinstance(grob.get("address"), dict) else {}).get("country_code")
               or "").upper()
    if not name and not land:
        return None
    return {"name": name, "country": land if len(land) == 2 and land.isascii() and land.isalpha() else ""}


def vorschlag(lat: float, lon: float) -> dict | None:
    """Nächster Ort und Land für eine Koordinate — gemerkt, None bei Ausfall."""
    if not AKTIV:
        return None
    schluessel = f"{lat:.4f},{lon:.4f}"
    try:
        gemerkt = json.loads(CACHE_DATEI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        gemerkt = {}
    if not isinstance(gemerkt, dict):
        gemerkt = {}
    if schluessel in gemerkt:
        return gemerkt[schluessel]
    try:
        aus = vorschlag_aus(_hole(lat, lon, 14), _hole(lat, lon, 10))
    except Exception:                                    # noqa: BLE001 — Ausfall: dann ohne
        return None
    gemerkt[schluessel] = aus
    try:
        from ..spotedit import schreibe_atomar
        CACHE_DATEI.parent.mkdir(parents=True, exist_ok=True)
        schreibe_atomar(CACHE_DATEI, json.dumps(gemerkt, ensure_ascii=False))
    except (OSError, UnicodeError):     # ein Surrogat aus einem alten Eintrag: dann ohne Merken
        pass
    return aus
