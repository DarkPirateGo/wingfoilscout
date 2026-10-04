"""Wie sicher ist die Vorhersage? — Open-Meteo-Ensemble (ICON-EPS).

Das deterministische Modell sagt eine Zahl. Das Ensemble rechnet dieselbe Lage
vierzigmal mit leicht gestörten Anfangsbedingungen durch und zeigt damit, wie
stabil diese Zahl ist. Für die Frage „lohnt die Anfahrt" ist das oft wichtiger
als der Wert selbst: 15 kn, bei denen 35 von 40 Rechnungen über der Fahrgrenze
liegen, sind eine Fahrt wert; 15 kn, bei denen es 12 von 40 sind, nicht.

Kostenlos und ohne Schlüssel, im September 2026 geprüft:
    https://ensemble-api.open-meteo.com/v1/ensemble

Eine Einschränkung, die man kennen muss: das Ensemble liegt auf einem gröberen
Gitter als die deterministischen Modelle. Am Brouwersdam landet die Abfrage
15 km vom Spot, das deterministische ICON auf 3 km. Für die Stabilität der
Wetterlage ist das unerheblich, als Windwert taugt es nicht — deshalb wird hier
nur Wahrscheinlichkeit berechnet, nie ein Wert überschrieben.
"""
from __future__ import annotations
import json
import urllib.parse
import urllib.request

from ..i18n import T, TN, N_                                      # noqa: F401
from .netz import lies, USER_AGENT
from .openmeteo import reihen

URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
MODEL = "icon_seamless_eps"
CHUNK = 10                      # Orte je Abfrage; die Antwort wird sonst groß
TIMEOUT = 90


class EnsembleError(RuntimeError):
    pass


def fetch(spots, days: int, timezone: str | None = None, log=None) -> dict:
    """{spot_id: {"time": [...], "members": [[kn, ...], ...]}} — Zeiten in der Zone des Spots.

    Jeder Eintrag ist geprüft (`openmeteo.reihen`): Zeiten lesbar, Werte
    endliche Zahlen oder None. Passt die Zahl der Einträge nicht zur Zahl der
    Orte, fällt das Paket weg — bis 2.1.0 landeten die Reihen dann beim
    falschen Spot (C19). Kommt gar nichts Brauchbares, ist das ein
    EnsembleError mit dem Grund."""
    from ..spots import nach_zeitzone
    say = log or (lambda *a: None)
    out: dict[str, dict] = {}
    probleme: list[str] = []
    stapel = [(tz, gruppe[i:i + CHUNK])
              for tz, gruppe in nach_zeitzone(list(spots), timezone)
              for i in range(0, len(gruppe), CHUNK)]
    for tz, batch in stapel:
        params = {
            "latitude": ",".join(f"{s['lat']:.4f}" for s in batch),
            "longitude": ",".join(f"{s['lon']:.4f}" for s in batch),
            "hourly": "wind_speed_10m",
            "models": MODEL,
            "wind_speed_unit": "kn",
            "timezone": tz,
            "forecast_days": str(min(max(days, 1), 16)),
        }
        url = f"{URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(lies(resp).decode("utf-8"))
        except Exception as exc:                       # noqa: BLE001
            raise EnsembleError(str(exc)) from exc
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise EnsembleError(T("unerwartete Antwort: {antwort}", antwort=str(data)[:80]))
        if len(data) != len(batch):
            probleme.append(T("Open-Meteo lieferte {n} Blöcke für {m} Spots", n=len(data), m=len(batch)))
            say("    " + probleme[-1])
            continue
        for spot, entry in zip(batch, data):
            hourly = reihen(entry.get("hourly")) if isinstance(entry, dict) else None
            if hourly is None:
                probleme.append(T("unerwartete Antwort: {antwort}", antwort=spot.get("name") or spot["id"]))
                say("    " + probleme[-1])
                continue
            series = [v for k, v in hourly.items() if k.startswith("wind_speed_10m")]
            if hourly["time"] and series:
                out[spot["id"]] = {"time": hourly["time"], "members": series}
    if not out and probleme:
        raise EnsembleError(probleme[0])
    return out


def _quantile(values, q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1)))]


def window_stats(entry: dict, hours: list[str], ride_kn: float, good_kn: float) -> dict | None:
    """Statistik über ein Zeitfenster: Anteil brauchbarer Rechnungen und Spanne.

    Eine Rechnung zählt als brauchbar, wenn sie im Fenster mindestens zwei
    Stunden über der Grenze liegt — ein einzelner Ausreißer nach oben ist keine
    Session. `hours` sind Zeitstempel im Format der API (2026-09-13T14:00).
    """
    if not entry:
        return None
    if not isinstance(entry.get("time"), list) or not isinstance(entry.get("members"), list):
        return None
    index = {t: i for i, t in enumerate(entry["time"])}
    slots = [index[h] for h in hours if h in index]
    if not slots:
        return None

    ride = good = 0
    peaks = []
    for series in entry["members"]:
        if not isinstance(series, list):
            continue
        # Nur Zahlen: ein String in einer Reihe warf bis 1.18.3 einen
        # TypeError mitten in der Suche (Review 25.09., S10).
        values = [series[i] for i in slots
                  if i < len(series) and isinstance(series[i], (int, float)) and not isinstance(series[i], bool)]
        if not values:
            continue
        peaks.append(max(values))
        need = min(2, len(values))
        if sum(1 for v in values if v >= ride_kn) >= need:
            ride += 1
        if sum(1 for v in values if v >= good_kn) >= need:
            good += 1
    if not peaks:
        return None
    return {
        "members": len(peaks),
        "p_ride": round(ride / len(peaks), 2),
        "p_good": round(good / len(peaks), 2),
        "p10": round(_quantile(peaks, 0.10), 1),
        "p50": round(_quantile(peaks, 0.50), 1),
        "p90": round(_quantile(peaks, 0.90), 1),
    }
