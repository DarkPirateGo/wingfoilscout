"""Synthetische Wetterdaten, damit sich der Report ohne Netz ansehen lässt.

Erfundene Zahlen mit plausibler Tagesstruktur — ausschließlich zum Prüfen der
Pipeline und des Layouts. Der Report markiert Demo-Läufe deutlich.
"""
from __future__ import annotations
import math
import random
from datetime import datetime, timedelta

from . import sonne


def build(spots, days: int, seed: int = 7) -> dict:
    rnd = random.Random(seed)
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    out = {}
    for spot in spots:
        base = rnd.uniform(9, 24)                     # Grundwind des Spots
        main_dir = rnd.choice([sec["from"] for sec in spot.get("sectors", [])] or [270])
        times, wind, gust, wdir, temp, rain, cape, code = [], [], [], [], [], [], [], []
        d_time, sunrise, sunset = [], [], []
        for d in range(days):
            day0 = start + timedelta(days=d)
            trend = rnd.uniform(-5, 6)
            d_time.append(day0.date().isoformat())
            # Feste Zeiten für alle Spots wären bequem, aber dann meldet der
            # Abgleich im Log eine Abweichung von zwei Stunden und man sucht
            # den Fehler in der Rechnung statt in den Demodaten.
            auf, unter = sonne.zeiten_lokal(spot["lat"], spot["lon"], day0.date(), 7200)
            sunrise.append(auf.strftime("%Y-%m-%dT%H:%M"))
            sunset.append(unter.strftime("%Y-%m-%dT%H:%M"))
            stormy = rnd.random() < 0.12
            for h in range(24):
                t = day0 + timedelta(hours=h)
                thermal = 5.5 * math.sin(max(0.0, (h - 8) / 11 * math.pi))
                v = max(0.5, base + trend + thermal + rnd.uniform(-2.2, 2.2))
                times.append(t.strftime("%Y-%m-%dT%H:%M"))
                wind.append(round(v, 1))
                gust.append(round(v * rnd.uniform(1.12, 1.45), 1))
                wdir.append(round((main_dir + rnd.uniform(-22, 22)) % 360, 1))
                temp.append(round(13 + 9 * math.sin(max(0.0, (h - 6) / 13 * math.pi)) + rnd.uniform(-2, 3), 1))
                r = round(max(0.0, rnd.gauss(0.05, 0.5)), 2) if not stormy else round(abs(rnd.gauss(1.6, 1.4)), 2)
                rain.append(r)
                cape.append(round(abs(rnd.gauss(1500 if stormy else 220, 500)), 0))
                code.append(95 if (stormy and 13 <= h <= 18 and rnd.random() < 0.5) else (61 if r > 0.5 else 3))
        hourly = {"time": times}
        base_series = {"wind_speed_10m": wind, "wind_gusts_10m": gust, "wind_direction_10m": wdir,
                       "temperature_2m": temp, "precipitation": rain, "cape": cape,
                       "weather_code": code, "cloud_cover": [50] * len(times)}
        # Drei Modelle wie bei Open-Meteo suffigiert; GFS und ECMWF weichen zufällig ab,
        # an manchen Tagen deutlich — damit die Einigkeitslogik etwas zu tun hat.
        for m, jitter in (("dwd_icon_seamless", 0.0), ("ncep_gfs_seamless", 2.4), ("ecmwf_ifs", 1.6)):
            day_bias = {d: rnd.uniform(-jitter * 1.6, jitter * 1.6) for d in range(days)}
            for k, series in base_series.items():
                if k == "wind_speed_10m":
                    hourly[f"{k}_{m}"] = [round(max(0.5, v + day_bias[i // 24] + rnd.uniform(-jitter, jitter)), 1)
                                          for i, v in enumerate(series)]
                elif k == "wind_gusts_10m":
                    hourly[f"{k}_{m}"] = [round(max(0.5, v + day_bias[i // 24]), 1) for i, v in enumerate(series)]
                else:
                    hourly[f"{k}_{m}"] = list(series)
        out[spot["id"]] = {
            "hourly": hourly,
            "utc_offset_seconds": 7200,
            "daily": {"time": d_time, "sunrise": sunrise, "sunset": sunset},
        }
        marine_demo = {}
        if spot.get("water_body") in ("sea", "lagoon"):
            sst_base = rnd.uniform(9, 22)
            # Tidenhub: an Spots mit `tidal: true` immer deutlich, sonst
            # zwischen Ostsee und Atlantik verteilt — so zeigt der Demo-Lauf
            # auch die Automatik (ab 0,5 m Hub gilt der Spot als Tidenspot).
            hub = 1.2 if spot.get("tidal") else rnd.choice([0.15, 0.3, 0.9, 1.6])
            phase = rnd.random() * 2 * math.pi
            marine_demo = {
                "sst": {t: round(sst_base + rnd.uniform(-0.4, 0.4), 1) for t in times},
                "tide": {t: round(hub * math.sin(2 * math.pi * (i / 12.42) + phase), 2)
                         for i, t in enumerate(times)},
            }
        out[spot["id"]]["_marine_demo"] = marine_demo
    return out
