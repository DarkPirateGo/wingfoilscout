"""Mehrere Wettermodelle in einer Antwort — und was sie voneinander halten.

Ein einzelner Modelllauf ist keine Entscheidungsgrundlage für eine Fahrt,
die man drei Tage vorher festlegt. Wer Gruppen durch Europa führt, schaut
immer auf zwei, drei Modelle und fährt nur, wenn sie sich einig sind.
Open-Meteo liefert mehrere Modelle in einem Aufruf; hier werden sie auf eine
Hauptreihe zusammengeführt und die Einigkeit je Stunde berechnet.

Namensschema der Antwort bei mehreren Modellen: `wind_speed_10m_<modell>`.
Falls Open-Meteo doch ohne Suffix antwortet, greift der Rückfall auf die
unsuffigierten Schlüssel — der Code läuft in beiden Fällen.
"""
from __future__ import annotations

DEFAULT_MODELS = ["dwd_icon_seamless", "ncep_gfs_seamless", "ecmwf_ifs"]
SHORT = {"dwd_icon_seamless": "ICON", "ncep_gfs_seamless": "GFS", "ecmwf_ifs": "ECMWF",
         "meteofrance_seamless": "AROME", "ukmo_seamless": "UKMO"}

# Alles, was `score_hours` aus der Antwort liest, muss hier stehen: bei mehreren
# Modellen wird das `hourly` nur aus dieser Liste neu gebaut, und was fehlt,
# ist danach stillschweigend `None`. `shortwave_radiation` fehlte bis 1.6.0 —
# die Thermik rechnete deshalb immer mit dem Bewölkungs-Rückfall statt mit
# der Einstrahlung, für die sie gebaut war. Derselbe Fehler wie bei den
# Sonnenzeiten in 1.5.0, nur eine Zeile tiefer.
CORE = ["wind_speed_10m", "wind_gusts_10m", "wind_direction_10m", "temperature_2m",
        "precipitation", "cloud_cover", "shortwave_radiation", "cape", "weather_code"]


def short(model: str) -> str:
    return SHORT.get(model, model.replace("_seamless", "").upper())


def normalize(hourly: dict, models: list[str], primary: str) -> dict:
    """Macht aus einer Mehrmodell-Antwort eine Hauptreihe plus Einigkeitsmaß.

    Rückgabe: neues hourly-Dict mit den Kernvariablen unter ihrem normalen Namen
    (Hauptmodell, Lücken aus den anderen gefüllt) sowie
      wind_models  {kurzname: [kn, …]}   alle Modelle nebeneinander
      wind_spread  [kn, …]               max − min je Stunde
      wind_agree   [0..1, …]             1 = einig, 0.4 = weit auseinander
    """
    n = len(hourly.get("time") or [])
    out = {"time": hourly.get("time", [])}
    suffixed = any(f"wind_speed_10m_{m}" in hourly for m in models)

    if not suffixed:                                   # nur ein Modell geliefert
        for k in CORE:
            out[k] = hourly.get(k) or [None] * n
        out["wind_models"] = {short(primary): out["wind_speed_10m"]}
        out["wind_spread"] = [0.0] * n
        out["wind_agree"] = [1.0] * n
        return out

    order = [primary] + [m for m in models if m != primary]
    for k in CORE:
        merged = []
        for i in range(n):
            v = None
            for m in order:
                series = hourly.get(f"{k}_{m}")
                if series and i < len(series) and series[i] is not None:
                    v = series[i]
                    break
            merged.append(v)
        out[k] = merged

    wind_models = {}
    for m in models:
        series = hourly.get(f"wind_speed_10m_{m}")
        if series:
            wind_models[short(m)] = series
    out["wind_models"] = wind_models
    out["wind_spread"], out["wind_agree"] = einigkeit(wind_models, n)
    return out


def einigkeit(wind_models: dict, n: int) -> tuple[list[float], list[float]]:
    """(Spanne, Einigkeit) je Stunde über alle Reihen in `wind_models`.

    Eigene Funktion, weil sie zweimal gebraucht wird: einmal nach dem
    Zusammenführen der globalen Modelle, und noch einmal, nachdem ein
    Regionalmodell den Wind ersetzt hat. Bis 1.6.1 stand „Modelle einig“ dann
    neben einem Wind aus CH1, der von allen dreien fünf Knoten abwich — die
    Einigkeit bezog sich auf Modelle, die gar nicht mehr angezeigt wurden.
    `grob` (die Kopie der groben Hauptreihe) zählt nicht mit: sie ist ICON.
    """
    reihen = [v for k, v in wind_models.items() if k != "grob"]
    spread, agree = [], []
    for i in range(n):
        vals = [s[i] for s in reihen if i < len(s) and s[i] is not None]
        if len(vals) < 2:
            spread.append(0.0)
            agree.append(1.0)
            continue
        d = max(vals) - min(vals)
        spread.append(round(d, 1))
        agree.append(1.0 if d <= 3 else (0.4 if d >= 9 else round(1.0 - (d - 3) / 6 * 0.6, 3)))
    return spread, agree
