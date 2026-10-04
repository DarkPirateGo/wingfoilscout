"""Echte Fahrzeiten statt Luftlinie mal Faktor — OSRM.

Bisher schätzte das Tool die Anfahrt als Luftlinie mal 1,22 bei 85 km/h. Für
die Frage, die das ganze Ranking trägt — lohnt die Fahrt —, ist das zu grob.
In Zeeland liegen Dämme und Fähren dazwischen, in den Alpen Pässe. Gemessen am
Brouwersdam: zum Oesterdam schätzt die Faustformel 57 km und 40 Minuten, in
Wirklichkeit sind es 63 km und 61 Minuten.

Der offene Demo-Server von OSRM beantwortet das ohne Schlüssel:

    https://router.project-osrm.org/table/v1/driving/{lon,lat;...}
        ?sources=0&annotations=duration,distance

Ein Aufruf liefert die Fahrzeit von einem Start zu allen Zielen gleichzeitig —
der komplette Katalog geht in eine Abfrage. Das ist auch der Grund, warum hier
die Tabellen- und nicht die Routenschnittstelle genutzt wird: ein Aufruf statt
hundert ist der Unterschied zwischen Nutzung und Belästigung.

Der Server ist ein Demo-Dienst ohne Zusage. Fällt er aus, bleibt es bei der
Schätzung; das Tool merkt sich je Spot, woher die Zahl stammt.
"""
from __future__ import annotations
import json
import math
import time
import urllib.error
import urllib.request
from pathlib import Path

from ..i18n import T, TN, N_                                      # noqa: F401
from .netz import lies, cache_lesen, ablegen, USER_AGENT          # noqa: F401 — USER_AGENT gehört zur Schnittstelle

from .overpass import passt, stempel

ENDPOINT = "https://router.project-osrm.org/table/v1/driving/"
CHUNK = 90                # Ziele je Aufruf; der Demo-Server nimmt mehr, aber die URL wird lang
TIMEOUT = 40
MAX_DAUER_S = 48 * 3600   # länger fährt niemand zu einem Spot; was darüber liegt, ist Unsinn
MAX_STRECKE_M = 10_000_000


class RoutingError(RuntimeError):
    pass


def tls_veraltet() -> str:
    """Nennt die TLS-Bibliothek, wenn sie zu alt für heutige Server ist, sonst "".

    Das mitgelieferte Python von macOS (3.9.6) ist gegen LibreSSL 2.8.3 gebaut.
    Diese Fassung ist von 2018 und scheitert beim Handschlag mit Servern, die
    nur noch moderne Verfahren anbieten — darunter router.project-osrm.org. Der
    Fehler, den urllib dann durchreicht, lautet "SSLV3_ALERT_HANDSHAKE_FAILURE"
    und klingt nach einem kaputten Server. Der Server ist in Ordnung.
    """
    try:
        import ssl
    except ImportError:                                 # pragma: no cover
        return ""
    version = getattr(ssl, "OPENSSL_VERSION", "")
    if version.startswith("LibreSSL"):
        return version
    return ""


def _rat(fehler: str) -> str:
    """Hängt an eine Fehlermeldung den Grund, wenn er bekannt ist."""
    text = str(fehler)
    if "handshake" not in text.lower() and "SSL" not in text:
        return ""
    alt = tls_veraltet()
    if not alt:
        return ""
    return " — " + T("Ursache ist {tls} in diesem Python, nicht der Server; "
                     "ein aktuelles Python (brew install python) behebt es", tls=alt)


def _key(lat: float, lon: float) -> str:
    """Startpunkt auf gut einen Kilometer gerundet — feiner lohnt kein Cache."""
    return f"{lat:.2f},{lon:.2f}"


def _start(lat: float, lon: float) -> str:
    """Der Startpunkt für OSRM — so grob wie der Cacheschlüssel. Der offene
    Demo-Server muss nicht auf fünf Stellen (gut ein Meter) wissen, wo jemand
    wohnt; bis 2.1.0 bekam er genau das (Review 04.10.2026, C12). Ein
    Kilometer ändert an einer Fahrzeit nichts, und die Antwort gilt ohnehin
    für alle Starts in diesem Kilometer."""
    return f"{lon:.2f},{lat:.2f}"


def _zahl(v, hoechstens: float) -> float | None:
    """Eine endliche Zahl in [0, hoechstens) — sonst None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    try:
        f = float(v)
    except OverflowError:
        return None
    return f if math.isfinite(f) and 0 <= f < hoechstens else None


def _eintrag_ok(e) -> bool:
    """Ein gemerkter Eintrag, mit dem sich rechnen lässt (NaN aus einer alten
    Datei, ein Text statt einer Zahl: nein — dann wird neu geroutet)."""
    return (isinstance(e, dict) and _zahl(e.get("h"), MAX_DAUER_S / 3600.0 + 0.01) is not None
            and _zahl(e.get("km"), MAX_STRECKE_M / 1000.0 + 0.1) is not None)


def load_cache(path: str | Path) -> dict:
    """{Startschlüssel: {spot_id: Eintrag}} — was nicht lesbar ist, fehlt.
    Eine kaputte Datei ist ein leerer Cache, ein Eintrag mit NaN (bis 2.1.0
    möglich) einer, der neu geroutet wird."""
    daten = cache_lesen(path, dict) or {}
    return {k: {sid: e for sid, e in slot.items() if _eintrag_ok(e)}
            for k, slot in daten.items() if isinstance(slot, dict)}


def _ask(coords: str) -> dict:
    url = f"{ENDPOINT}{coords}?sources=0&annotations=duration,distance"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(lies(resp).decode("utf-8"))
    except Exception as exc:                            # noqa: BLE001
        raise RoutingError(str(exc)) from exc
    if not isinstance(data, dict):
        raise RoutingError(T("unbekannter Fehler"))
    if data.get("code") != "Ok":
        raise RoutingError(data.get("message") or data.get("code") or T("unbekannter Fehler"))
    return data


def drive_times(home: dict, spots, cache_path: str | Path = "cache/routes.json",
                pause_s: float = 1.0, log=None) -> dict:
    """{spot_id: {"km": float, "h": float}} — aus dem Cache, sonst frisch geholt."""
    say = log or (lambda *a: None)
    cache = load_cache(cache_path)
    schluessel = _key(home["lat"], home["lon"])
    if not isinstance(cache.get(schluessel), dict):
        cache[schluessel] = {}
    slot = cache[schluessel]

    # Ein Eintrag gilt für die Koordinate, für die geroutet wurde. Nach einer
    # Korrektur der Nadel — oder ohne Stempel aus der Zeit davor — wird neu
    # gefragt; das ist ein Aufruf je neunzig Ziele, kein Preis.
    def gilt(s) -> bool:
        e = slot.get(s["id"])
        return e is not None and bool(e.get("bei")) and passt(e["bei"], s["lat"], s["lon"])

    offen = [s for s in spots if not gilt(s)]
    if offen:
        start = _start(home["lat"], home["lon"])
        geholt = 0
        for i in range(0, len(offen), CHUNK):
            batch = offen[i:i + CHUNK]
            coords = ";".join([start] + [f"{s['lon']:.5f},{s['lat']:.5f}" for s in batch])
            try:
                data = _ask(coords)
            except RoutingError as exc:
                # {hinweis}: leer oder „ — Ursache ist …“ (`_rat`)
                say("    " + T("Routing nicht erreichbar ({fehler}){hinweis} — es bleibt bei der Schätzung",
                              fehler=exc, hinweis=_rat(exc)))
                break
            dauer, strecke = _zeile(data.get("durations")), _zeile(data.get("distances"))
            for n, spot in enumerate(batch, start=1):
                # Nur, was eine Fahrzeit sein kann: endlich, nicht negativ,
                # unter 48 Stunden. NaN oder 1e999 hätte sonst im Cache gestanden
                # und jede weitere Suche mitgenommen (C4).
                h = _zahl(dauer[n], MAX_DAUER_S) if n < len(dauer) else None
                if h is None:
                    continue
                m = strecke[n] if n < len(strecke) else None
                if m is None or m == 0:
                    m = 0                               # keine Strecke gesagt: wie bisher 0 km
                else:
                    m = _zahl(m, MAX_STRECKE_M)
                    if m is None:
                        continue
                slot[spot["id"]] = {
                    "h": round(h / 3600.0, 2),
                    "km": round(m / 1000.0, 1),
                    "bei": stempel(spot["lat"], spot["lon"]),
                }
                geholt += 1
            if i + CHUNK < len(offen):
                time.sleep(pause_s)
        if geholt:
            ablegen(cache_path, json.dumps(cache))
            if len(spots) > len(offen):
                say(T("Fahrzeiten: {n} Ziele über OSRM geroutet, {m} aus dem Zwischenspeicher",
                      n=geholt, m=len(spots) - len(offen)))
            else:
                say(T("Fahrzeiten: {n} Ziele über OSRM geroutet", n=geholt))
    return {s["id"]: {"h": slot[s["id"]]["h"], "km": slot[s["id"]]["km"]}
            for s in spots if s["id"] in slot and passt(slot[s["id"]].get("bei"), s["lat"], s["lon"])}


def _zeile(matrix) -> list:
    """Die erste Zeile einer OSRM-Matrix (Start → alle Ziele) — [] wenn die
    Antwort keine Matrix ist."""
    if isinstance(matrix, list) and matrix and isinstance(matrix[0], list):
        return matrix[0]
    return []


def apply_to(spots, times: dict) -> int:
    """Trägt echte Werte in die Spots ein. Rückgabe: wie viele ersetzt wurden."""
    n = 0
    for spot in spots:
        entry = times.get(spot["id"])
        if not entry:
            spot.setdefault("drive_source", "Schätzung")
            continue
        spot["road_km"] = entry["km"]
        spot["drive_h"] = entry["h"]
        spot["drive_source"] = "Routing"
        n += 1
    return n
