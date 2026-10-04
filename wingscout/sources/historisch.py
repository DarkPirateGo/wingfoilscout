"""Vorhersagen aus der Vergangenheit — Open-Meteo Historical Forecast API.

Für den Prüfstand: Wie gut lag die Vorhersage an Tagen, für die es Messwerte
gibt? Dafür braucht es die Vorhersage, wie sie damals war. Open-Meteo hebt sie
auf, in derselben Form wie die laufende Vorhersage, nur mit `start_date` und
`end_date` statt `forecast_days`:

    https://historical-forecast-api.open-meteo.com/v1/forecast

Was man wissen muss: Aufgehoben wird je Stunde der Lauf mit dem kürzesten
Vorlauf — also die Vorhersage von „heute für heute“, nicht die von vor drei
Tagen. Für die Frage „rechnet die Bewertung richtig, wenn das Modell richtig
liegt“ ist das genau richtig; für die Frage „wie gut war die Prognose drei
Tage vorher“ bräuchte es die Previous-Runs-API — noch nicht gebaut.

Alles, was hier geholt wird, landet in `cache/pruefstand/` und wird nie wieder
geholt: ein fester Zeitraum in der Vergangenheit ändert sich nicht, und der
Prüfstand soll bei jedem Lauf dieselben Zahlen vergleichen.

Der laufende Tag ist der Sonderfall: ob das Archiv ihn schon führt, sagt die
Beschreibung nicht. `hole_bis_heute` holt deshalb die Vergangenheit aus dem
Archiv und den heutigen Tag (und was das Archiv von gestern noch nicht hat)
aus der laufenden Vorhersage mit `past_days` — das ist derselbe kürzeste
Vorlauf, nur noch nicht archiviert. Beides wird Stunde für Stunde zu einer
Antwort zusammengesetzt.
"""
from __future__ import annotations
import hashlib
import json
import urllib.parse
import urllib.request

from .. import CACHE
from ..i18n import T, TN, N_                                      # noqa: F401
from .netz import lies, cache_lesen, ablegen, USER_AGENT
from .openmeteo import HOURLY, DAILY, TIMEOUT, bereinigen

ENDPOINT = "https://historical-forecast-api.open-meteo.com/v1/forecast"
ENDPOINT_LIVE = "https://api.open-meteo.com/v1/forecast"
CACHE_DIR = CACHE / "pruefstand"


class HistorischError(RuntimeError):
    pass


def _schluessel(*teile) -> str:
    roh = "|".join(str(t) for t in teile)
    return hashlib.sha1(roh.encode("utf-8")).hexdigest()[:16]


def _aus_cache(name: str, bis: str | None = None):
    """Die gemerkte Antwort — geprüft wie eine frische (`openmeteo.bereinigen`);
    eine kaputte Datei oder eine aus der Zeit vor 2.1.1 mit NaN darin heißt:
    neu holen. `{}` ist die gemerkte Absage eines Regionalmodells."""
    pfad = CACHE_DIR / f"{name}.json"
    if bis:
        # Für die letzten Tage liefert die Archiv-API nach und nach mehr —
        # nach sechs Stunden noch einmal fragen (siehe stationen._brauchbar).
        from .stationen import _brauchbar
        if not _brauchbar(pfad, bis):
            return None
    daten = cache_lesen(pfad, dict)
    if not daten:
        return daten
    return bereinigen(daten)[0]


def _in_cache(name: str, daten) -> None:
    ablegen(CACHE_DIR / f"{name}.json", json.dumps(daten))


def _sauber(daten: dict) -> dict:
    """Eine Antwort mit `hourly`, geprüft — oder HistorischError."""
    sauber, grund = bereinigen(daten)
    if sauber is None:
        raise HistorischError(T("unerwartete Antwort: {antwort}", antwort=grund))
    return sauber


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(lies(resp).decode("utf-8"))
    except Exception as exc:                            # noqa: BLE001
        raise HistorischError(str(exc)) from exc


def hole(spot: dict, von: str, bis: str, models: list[str], timezone: str,
         hourly: list[str] | None = None) -> dict:
    """Die aufgehobene Vorhersage für einen Spot und einen Zeitraum.

    Rückgabe in der Form der laufenden Vorhersage (`hourly` mit Modellsuffixen,
    `daily`, `utc_offset_seconds`), damit `score_hours` sie unverändert nimmt.
    """
    felder = hourly or HOURLY
    name = "hist_" + _schluessel(spot["id"], f"{spot['lat']:.4f}", f"{spot['lon']:.4f}",
                                 von, bis, ",".join(models), timezone, ",".join(felder))
    gemerkt = _aus_cache(name, bis)
    if gemerkt is not None:
        return gemerkt
    params = {
        "latitude": f"{spot['lat']:.4f}", "longitude": f"{spot['lon']:.4f}",
        "hourly": ",".join(felder), "daily": ",".join(DAILY),
        "wind_speed_unit": "kn", "timezone": timezone,
        "start_date": von, "end_date": bis, "cell_selection": "nearest",
        "models": ",".join(models),
    }
    daten = _get(f"{ENDPOINT}?{urllib.parse.urlencode(params)}")
    if not isinstance(daten, dict) or "hourly" not in daten:
        raise HistorischError(T("unerwartete Antwort: {antwort}", antwort=str(daten)[:120]))
    daten = _sauber(daten)
    _in_cache(name, daten)
    return daten


def hole_regional(spot: dict, modell: str, von: str, bis: str, timezone: str) -> dict | None:
    """Das Regionalmodell für denselben Zeitraum — None, wenn es den Punkt nicht deckt."""
    name = "hist_" + _schluessel(spot["id"], f"{spot['lat']:.4f}", f"{spot['lon']:.4f}",
                                 von, bis, modell, timezone, "regional")
    gemerkt = _aus_cache(name, bis)
    if gemerkt is not None:
        return gemerkt or None
    params = {
        "latitude": f"{spot['lat']:.4f}", "longitude": f"{spot['lon']:.4f}",
        "hourly": "wind_speed_10m,wind_gusts_10m,wind_direction_10m",
        "wind_speed_unit": "kn", "timezone": timezone,
        "start_date": von, "end_date": bis, "cell_selection": "nearest",
        "models": modell,
    }
    try:
        daten = _get(f"{ENDPOINT}?{urllib.parse.urlencode(params)}")
    except HistorischError as exc:
        if "400" in str(exc):                        # außerhalb der Modelldomain
            _in_cache(name, {})
            return None
        raise
    if not isinstance(daten, dict) or "hourly" not in daten:
        _in_cache(name, {})
        return None
    daten = _sauber(daten)                              # unlesbar: nicht als Absage merken
    _in_cache(name, daten)
    return daten


# ── Bis heute: Archiv plus laufende Vorhersage ───────────────────────────────

def _heute():
    from datetime import date
    return date.today()


def _live(spot: dict, past_days: int, models: str, timezone: str, felder: list[str],
          mit_daily: bool = True) -> dict:
    """Die laufende Vorhersage mit `past_days` — gemerkt für eine Stunde."""
    heute = _heute().isoformat()
    name = "live_" + _schluessel(spot["id"], f"{spot['lat']:.4f}", f"{spot['lon']:.4f}",
                                 past_days, models, timezone, ",".join(felder), mit_daily)
    gemerkt = _aus_cache(name, heute)
    if gemerkt is not None:
        return gemerkt
    params = {
        "latitude": f"{spot['lat']:.4f}", "longitude": f"{spot['lon']:.4f}",
        "hourly": ",".join(felder), "wind_speed_unit": "kn", "timezone": timezone,
        "past_days": max(0, min(int(past_days), 92)), "forecast_days": 1,
        "cell_selection": "nearest", "models": models,
    }
    if mit_daily:
        params["daily"] = ",".join(DAILY)
    daten = _get(f"{ENDPOINT_LIVE}?{urllib.parse.urlencode(params)}")
    if not isinstance(daten, dict) or "hourly" not in daten:
        raise HistorischError(T("unerwartete Antwort: {antwort}", antwort=str(daten)[:120]))
    daten = _sauber(daten)
    _in_cache(name, daten)
    return daten


def zusammensetzen(archiv: dict | None, live: dict | None, von: str, bis: str) -> dict:
    """Zwei Antworten derselben Form zu einer für [von, bis]: je Stunde der
    Archivwert, wo er fehlt der aus der laufenden Vorhersage. Stunden außerhalb
    des Zeitraums fallen weg, `daily` wird ebenso zusammengelegt."""
    teile = [t for t in (archiv, live) if t and t.get("hourly")]
    if not teile:
        raise HistorischError(T("weder Archiv noch laufende Vorhersage haben Stunden"))
    aus = dict(teile[0])
    aus["hourly"] = {}
    aus["daily"] = {}
    felder = []
    for t in teile:
        for k in t["hourly"]:
            if k != "time" and k not in felder:
                felder.append(k)
    zeiten: dict = {}
    for t in teile:
        h = t["hourly"]
        for i, stempel in enumerate(h.get("time") or []):
            if not (von <= str(stempel)[:10] <= bis):
                continue
            werte = zeiten.setdefault(stempel, {})
            for k in felder:
                reihe = h.get(k) or []
                wert = reihe[i] if i < len(reihe) else None
                if werte.get(k) is None and wert is not None:
                    werte[k] = wert
    stempel_sortiert = sorted(zeiten)
    aus["hourly"]["time"] = stempel_sortiert
    for k in felder:
        aus["hourly"][k] = [zeiten[t].get(k) for t in stempel_sortiert]
    tage: dict = {}
    tagesfelder = []
    for t in teile:
        d = t.get("daily") or {}
        for k in d:
            if k != "time" and k not in tagesfelder:
                tagesfelder.append(k)
        for i, tag in enumerate(d.get("time") or []):
            if not (von <= str(tag)[:10] <= bis):
                continue
            werte = tage.setdefault(tag, {})
            for k in tagesfelder:
                reihe = d.get(k) or []
                wert = reihe[i] if i < len(reihe) else None
                if werte.get(k) is None and wert is not None:
                    werte[k] = wert
    tage_sortiert = sorted(tage)
    aus["daily"]["time"] = tage_sortiert
    for k in tagesfelder:
        aus["daily"][k] = [tage[t].get(k) for t in tage_sortiert]
    return aus


def hole_bis_heute(spot: dict, von: str, bis: str, models: list[str], timezone: str,
                   hourly: list[str] | None = None) -> dict:
    """Wie `hole`, aber der Zeitraum darf bis heute reichen."""
    from datetime import date, timedelta
    heute = _heute()
    gestern = (heute - timedelta(days=1)).isoformat()
    felder = hourly or HOURLY
    if bis < heute.isoformat():
        return hole(spot, von, bis, models, timezone, hourly)
    archiv = None
    if von <= gestern:
        try:
            archiv = hole(spot, von, gestern, models, timezone, hourly)
        except HistorischError:
            archiv = None                             # dann trägt die laufende Vorhersage alles
    past = (heute - date.fromisoformat(von)).days
    live = _live(spot, past, ",".join(models), timezone, felder)
    return zusammensetzen(archiv, live, von, bis)


def hole_regional_bis_heute(spot: dict, modell: str, von: str, bis: str, timezone: str) -> dict | None:
    """Wie `hole_regional`, aber bis heute — None, wenn das Modell den Punkt nicht deckt."""
    from datetime import date, timedelta
    heute = _heute()
    gestern = (heute - timedelta(days=1)).isoformat()
    if bis < heute.isoformat():
        return hole_regional(spot, modell, von, bis, timezone)
    archiv = hole_regional(spot, modell, von, gestern, timezone) if von <= gestern else None
    felder = ["wind_speed_10m", "wind_gusts_10m", "wind_direction_10m"]
    past = (heute - date.fromisoformat(von)).days
    try:
        live = _live(spot, past, modell, timezone, felder, mit_daily=False)
    except HistorischError as exc:
        if "400" in str(exc):
            return archiv
        raise
    try:
        return zusammensetzen(archiv, live, von, bis)
    except HistorischError:
        return None

