"""Open-Meteo Forecast API — kostenlos, kein Schlüssel, nicht-kommerziell.

Doku: https://open-meteo.com/en/docs  ·  https://open-meteo.com/en/docs/dwd-api
Free-Tier laut Anbieter: 10.000 Aufrufe/Tag, 5.000/h, 600/min.
"""
from __future__ import annotations
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from ..i18n import T, TN, N_                                      # noqa: F401
from .netz import lies, USER_AGENT

ENDPOINT = "https://api.open-meteo.com/v1/forecast"

HOURLY = [
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "temperature_2m",
    "precipitation",
    "cloud_cover",
    # Globalstrahlung für die Thermik: sie gewichtet hohe Cirren und tiefe
    # Stratusdecken richtig verschieden, was der Bedeckungsgrad nicht kann.
    "shortwave_radiation",
    "cape",
    "weather_code",
]
DAILY = ["sunrise", "sunset"]

CHUNK = 20          # Koordinaten pro Aufruf
TIMEOUT = 45
RETRY_WAIT = (2, 5, 12)      # Sekunden zwischen den Versuchen
RETRY_CODES = {429, 500, 502, 503, 504}
RETRY_AFTER_MAX = 60         # mehr als eine Minute wartet hier niemand auf einen Server

GRENZE = 1e6                 # kein abgefragtes Feld kommt auch nur in die Nähe
MAX_VERSATZ_S = 18 * 3600    # utc_offset_seconds: weiter liegt keine Zeitzone


class ForecastError(RuntimeError):
    pass


# ── Was aus der Antwort weitergeht ───────────────────────────────────────────
#
# Pythons json nimmt NaN, Infinity und 1e999 an, und eine Reihe kann statt
# Zahlen Text tragen. Bis 2.1.0 ging das ungeprüft in die Bewertung — und kippte
# dort die ganze Suche, nicht nur den einen Spot (Review 04.10.2026, C4). Jetzt
# prüft jede Open-Meteo-Quelle ihre Blöcke hier: was nicht passt, wird None
# (ein einzelner Wert) oder fällt mit einer Zeile im Protokoll weg (ein Block).

def zahl(v):
    """Ein Wert aus einer Reihe — eine endliche Zahl (kein bool), sonst None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    try:
        f = float(v)
    except OverflowError:                               # eine ganze Zahl mit 400 Stellen
        return None
    return v if math.isfinite(f) and abs(f) <= GRENZE else None


def zeit(t) -> bool:
    """Ein Zeitstempel, wie Open-Meteo ihn schreibt (2026-10-04T14:00)."""
    if not isinstance(t, str) or len(t) > 32:
        return False
    try:
        datetime.fromisoformat(t)
    except ValueError:
        return False
    return True


def reihen(roh, zeiten: bool = False) -> dict | None:
    """Ein `hourly`- oder `daily`-Objekt geprüft — oder None, wenn es keins ist.

    `time` muss eine Liste lesbarer Zeitstempel sein. Jede andere Reihe ist
    eine Liste (fehlt sie ganz, steht null da: lauter None) mit endlichen
    Zahlen — `zeiten=True` erlaubt auch Zeitstempel (Sonnenauf- und
    -untergang in `daily`); alles andere wird None, und die Reihe wird auf die
    Länge von `time` gekürzt oder mit None aufgefüllt."""
    if not isinstance(roh, dict):
        return None
    t = roh.get("time")
    if not isinstance(t, list) or not all(zeit(x) for x in t):
        return None
    n = len(t)
    aus = {"time": list(t)}
    for k, werte in roh.items():
        if k == "time" or not isinstance(k, str):
            continue
        if werte is None:
            werte = []
        if not isinstance(werte, list):
            return None
        sauber = []
        for v in werte[:n]:
            if zeiten and isinstance(v, str):
                sauber.append(v if zeit(v) else None)
            else:
                sauber.append(zahl(v))
        aus[k] = sauber + [None] * (n - len(sauber))
    return aus


def bereinigen(block) -> tuple[dict | None, str]:
    """Ein Block der Vorhersage → (bereinigter Block, "") oder (None, was nicht
    passte). `hourly` muss da und lesbar sein; ein unlesbares `daily` fällt
    allein weg (die Sonnenzeiten rechnet score.py dann selbst); ein
    `utc_offset_seconds` außerhalb von ±18 Stunden verwirft den Block — die
    Stunden ließen sich nicht mehr verorten. Der Grund ist ein Feldname,
    keine Übersetzung."""
    if not isinstance(block, dict):
        return None, type(block).__name__
    hourly = reihen(block.get("hourly"))
    if hourly is None:
        return None, "hourly"
    aus = dict(block, hourly=hourly)
    if "daily" in block:
        daily = reihen(block.get("daily"), zeiten=True)
        if daily is None:
            del aus["daily"]
        else:
            aus["daily"] = daily
    if block.get("utc_offset_seconds") is not None:     # fehlt er, rechnet score.py mit der Länge
        versatz = zahl(block["utc_offset_seconds"])
        if versatz is None or abs(versatz) > MAX_VERSATZ_S:
            return None, "utc_offset_seconds"
    return aus, ""


def _retry_after(exc) -> int:
    """`Retry-After` in Sekunden (die Datumsform wird nicht gelesen), höchstens
    eine Minute — 0, wenn der Server nichts sagt."""
    kopf = getattr(exc, "headers", None) or {}
    try:
        wert = str(kopf.get("Retry-After") or "").strip()
    except Exception:                                   # noqa: BLE001 — ein seltsamer Kopf ist keine Wartezeit
        return 0
    return min(int(wert), RETRY_AFTER_MAX) if wert.isdigit() else 0


def _get(url: str, log=None) -> object:
    """Abruf mit Wiederholung.

    Ein 503 von Open-Meteo ist meist ein Aussetzer von Sekunden — es wäre
    unsinnig, deswegen eine ganze Suche wegzuwerfen. Wiederholt wird nur bei
    Fehlern, die vorübergehen können; ein 400 wegen falscher Parameter kommt
    sofort zurück, sonst wartet man dreimal vergeblich.
    """
    say = log or (lambda *a: None)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last = None
    for attempt, wait in enumerate((*RETRY_WAIT, None), start=1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(lies(resp).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in RETRY_CODES or wait is None:
                break
            # Sagt der Server, wie lange er Ruhe braucht (429, 503), gilt das —
            # bis zu einer Minute; früher fragen verlängert nur die Sperre.
            wait = max(wait, _retry_after(exc))
            say("    " + T("Open-Meteo antwortet mit {code} — neuer Versuch in {s} s", code=exc.code, s=wait))
        except Exception as exc:                       # noqa: BLE001
            last = exc
            if wait is None:
                break
            say("    " + T("Open-Meteo nicht erreichbar ({fehler}) — neuer Versuch in {s} s", fehler=exc, s=wait))
        time.sleep(wait)
    raise ForecastError(T("Open-Meteo nicht erreichbar: {fehler}", fehler=last))


def fetch(spots, days: int, timezone: str | None = None, model: str | None = None,
          models: list[str] | None = None, log=None) -> dict:
    """Liefert {spot_id: forecast_dict}. Mehrere Koordinaten und Modelle pro Aufruf.

    `model`  erzwingt genau ein Modell (z. B. dwd_icon_d2).
    `models` fordert mehrere an — die Antwort trägt dann Suffixe wie
             wind_speed_10m_dwd_icon_seamless, siehe models.normalize().
    `timezone` None heißt: je Spot die Zone seines Landes (spots.zeitzone),
             die Stundenstempel sind dann Ortszeit am Spot.
    """
    from ..spots import nach_zeitzone
    out: dict[str, dict] = {}
    problems: list[str] = []
    stapel = [(tz, gruppe[i:i + CHUNK])
              for tz, gruppe in nach_zeitzone(spots, timezone)
              for i in range(0, len(gruppe), CHUNK)]
    for nr, (tz, batch) in enumerate(stapel):
        params = {
            "latitude": ",".join(f"{s['lat']:.4f}" for s in batch),
            "longitude": ",".join(f"{s['lon']:.4f}" for s in batch),
            "hourly": ",".join(HOURLY),
            "daily": ",".join(DAILY),
            "wind_speed_unit": "kn",
            "timezone": tz,
            "forecast_days": max(1, min(int(days), 16)),
            # Open-Meteo verschiebt eine Koordinate standardmäßig auf eine
            # Gitterzelle mit ähnlicher Höhe an LAND. Für einen Spot, der
            # naturgemäß auf dem Wasser liegt, ist das die falsche Zelle: über
            # Land ist der Wind wegen der Rauigkeit systematisch schwächer.
            # Bis 1.4.1 fragte diese Abfrage eine Landzelle ab, während die
            # hochauflösenden Modelle schon "nearest" nutzten — der Vergleich
            # der beiden maß damit zum Teil nur den Unterschied zwischen Land-
            # und Wasserzelle, nicht den zwischen den Modellen.
            "cell_selection": "nearest",
        }
        if model:
            params["models"] = model
        elif models:
            params["models"] = ",".join(models)
        try:
            data = _get(f"{ENDPOINT}?{urllib.parse.urlencode(params)}", log)
        except ForecastError as exc:
            # Eine gescheiterte Teilmenge ist kein Grund, die anderen
            # wegzuwerfen — lieber ein Report über 90 Spots als gar keiner.
            problems.append(T("{n} Spots ohne Vorhersage ({fehler})", n=len(batch), fehler=exc))
            continue

        # Eine Koordinate → Objekt, mehrere → Liste. Beides abfangen.
        if isinstance(data, dict) and "hourly" in data:
            blocks = [data]
        elif isinstance(data, list):
            blocks = data
        else:
            problems.append(T("Unerwartete Antwort von Open-Meteo: {antwort}", antwort=str(data)[:120]))
            continue
        if len(blocks) != len(batch):
            problems.append(T("Open-Meteo lieferte {n} Blöcke für {m} Spots", n=len(blocks), m=len(batch)))
            continue
        for spot, block in zip(batch, blocks):
            sauber, grund = bereinigen(block)
            if sauber is None:
                # Ein kaputter Block kostet seinen Spot, nicht die Suche.
                problems.append(T("Unerwartete Antwort von Open-Meteo: {antwort}",
                                  antwort=f"{spot.get('name') or spot['id']} ({grund})"))
                continue
            out[spot["id"]] = sauber
        if nr + 1 < len(stapel):
            time.sleep(0.4)

    if problems and log:
        for line in problems:
            log(f"    {line}")
    if not out:
        raise ForecastError(problems[0] if problems else T("keine Daten erhalten"))
    return out
