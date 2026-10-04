"""Open-Meteo Marine API — Wassertemperatur, Wellenhöhe und Wasserstand (Tide).

Doku: https://open-meteo.com/en/docs/marine-weather-api
Modelle u.a. DWD EWAM (0,05° ≈ 5 km, Europa), MFWAM, ECMWF WAM.

Achtung, drei echte Einschränkungen:
  · Binnenseen und Stauseen liegen außerhalb jedes Wellenmodells — dort kommt
    nichts zurück, und das ist richtig so.
  · Der Anbieter weist selbst darauf hin, dass die Genauigkeit direkt an der
    Küste begrenzt ist. Werte hier sind ein Trend, keine Zusage.
  · sea_level_height_msl enthält die Gezeiten (0,08° ≈ 8 km Raster). Für
    „Hochwasser gegen 14 Uhr" reicht das, für Wattwanderungen nicht. Was
    Wingfoilscout daraus macht, steht in wingscout/tide.py.

Seit 1.18.0 wird für jeden Meer- und Lagunenspot angefragt, nicht nur mit
--marine — die Tide gehört zur Anzeige. Antwortet der Dienst nicht, bricht
die Schleife nach dem ersten Fehler ab statt jedes Paket in den Timeout zu
laufen: acht Pakete mal 45 s wären sechs Minuten für nichts.
"""
from __future__ import annotations
import json
import urllib.error
import urllib.parse
import urllib.request

from ..i18n import T, TN, N_                                      # noqa: F401
from .netz import lies, USER_AGENT
from .openmeteo import reihen

ENDPOINT = "https://marine-api.open-meteo.com/v1/marine"
HOURLY = ["sea_surface_temperature", "wave_height", "sea_level_height_msl"]
CHUNK = 20
TIMEOUT = 45

SEA_LIKE = {"sea", "lagoon"}


def fetch(spots, days: int, timezone: str | None = None, log=None) -> dict:
    """{spot_id: {"sst": {zeit: °C}, "wave": {zeit: m}, "tide": {zeit: m}}} — Fehler sind nicht fatal.

    Jeder Block wird geprüft wie die Vorhersage (`openmeteo.reihen`): ein
    unlesbarer fällt mit einer Zeile in `log` weg, ein einzelner Unsinnswert
    (Text, NaN, 1e999) wird übergangen."""
    from ..spots import nach_zeitzone
    say = log or (lambda *a: None)
    targets = [s for s in spots if s.get("water_body") in SEA_LIKE]
    out: dict[str, dict] = {}
    stapel = [(tz, gruppe[i:i + CHUNK])
              for tz, gruppe in nach_zeitzone(targets, timezone)
              for i in range(0, len(gruppe), CHUNK)]
    for tz, batch in stapel:
        params = {
            "latitude": ",".join(f"{s['lat']:.4f}" for s in batch),
            "longitude": ",".join(f"{s['lon']:.4f}" for s in batch),
            "hourly": ",".join(HOURLY),
            "timezone": tz,
            "forecast_days": max(1, min(int(days), 16)),
        }
        url = f"{ENDPOINT}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(lies(resp).decode("utf-8"))
        except (urllib.error.URLError, OSError):           # Netz weg, Timeout, HTTP-Fehler
            break                                          # die weiteren Pakete scheitern genauso
        except Exception:                                  # noqa: BLE001
            continue                                       # ohne Marine-Daten weiterrechnen
        blocks = [data] if isinstance(data, dict) and "hourly" in data else data
        if not isinstance(blocks, list) or len(blocks) != len(batch):
            continue
        for spot, block in zip(batch, blocks):
            h = reihen(block.get("hourly")) if isinstance(block, dict) else None
            if h is None:
                say("    " + T("Unerwartete Antwort von Open-Meteo: {antwort}",
                              antwort=f"Marine, {spot.get('name') or spot['id']} (hourly)"))
                continue
            times = h["time"]
            sst = h.get("sea_surface_temperature") or []
            wave = h.get("wave_height") or []
            level = h.get("sea_level_height_msl") or []
            out[spot["id"]] = {
                "sst": {t: v for t, v in zip(times, sst) if v is not None},
                "wave": {t: v for t, v in zip(times, wave) if v is not None},
                "tide": {t: v for t, v in zip(times, level) if v is not None},
            }
    return out
