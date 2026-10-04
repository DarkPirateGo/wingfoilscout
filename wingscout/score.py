"""Bewertung einzelner Stunden und Bildung von Sessions.

Jede Stunde bekommt Teilscores (0..1) für Wind, Richtung, Wasser, Wetter und
Böigkeit. Der Gesamtscore ist die gewichtete Summe; harte Ausschlüsse (Gewitter,
Temperatur außerhalb, kein passender Wing) setzen ihn auf 0 und tragen einen
Grund ein. Nichts davon ist Blackbox — jede Stunde weiß, warum sie ist, was sie ist.
"""
from __future__ import annotations
import math
from datetime import date, datetime, timedelta, timezone
from statistics import median

from . import sonne
from .geo import in_sector, compass
from .geometry import rose_at, classify, wave_height_m, water_label
from . import thermik
from . import tide as gezeiten
from .models import normalize, einigkeit, DEFAULT_MODELS
from .geo import haversine_km
from .i18n import T, TD, N_

# Übersetzt: was nur angezeigt wird — Veto, Warnungen, Neoprenwahl (beim
# Entstehen; der Lauf hat seine Sprache schon). Deutsch bleiben, was auch
# Schlüssel ist: `quality`/`dir_quality`, `source`, `wave_quelle`, `water`.

QUALITY_SCORE = {"best": 1.0, "good": 0.85, "ok": 0.6, "bad": 0.15}
WATER_BASE = {"flat": 1.0, "chop": 0.72, "wave": 0.42}
DAYLIGHT_MARGIN_MIN = 30

# Woher die Sonnenzeiten des letzten Laufs kamen und wie weit die eigene
# Rechnung von der Vorhersage abwich. Der Aufrufer schreibt das ins Log: damit
# prüft jeder echte Lauf die Formel in sonne.py gegen die Zeiten von
# Open-Meteo, ohne dass irgendwo eine Tabelle gepflegt werden muss.
SONNE_STATISTIK = {"vorhersage": 0, "gerechnet": 0, "abweichung_min": 0.0}


# ── Werte aus fremden Antworten ──────────────────────────────────────────────
# Was Open-Meteo, das Wellenmodell oder ein Spiegel liefern, kommt hier an,
# bevor jemand damit rechnet. Bis 2.1.0 brach ein einziger Unsinnswert die
# ganze Suche ab: `utc_offset_seconds: 1e999` als OverflowError, ein Text als
# Temperatur als TypeError im Vergleich, `nan` als Windrichtung in compass()
# (Review 04.10.2026, C4). Die Quellen putzen selbst; das hier ist die zweite
# Linie: was keine endliche Zahl ist, gilt als fehlend.

def _zahl(wert):
    """Endliche Zahl, sonst None — der Wert selbst bleibt, wie er kam."""
    if isinstance(wert, bool) or not isinstance(wert, (int, float)):
        return None
    try:
        return wert if math.isfinite(wert) and abs(wert) < 1e9 else None
    except OverflowError:                # eine ganze Zahl mit 400 Stellen
        return None


def _zeitversatz(fc: dict) -> int | None:
    """`utc_offset_seconds` als ganze Sekunden — oder None wie ohne Angabe,
    wenn es keine Zahl ist oder mehr als einen Tag ausmacht."""
    versatz = _zahl(fc.get("utc_offset_seconds"))
    return int(versatz) if versatz is not None and abs(versatz) <= 86400 else None


def _sonnenzeiten(spot, fc: dict, tage: list[str]) -> dict:
    """{Tag: (erste helle Minute, letzte helle Minute)} als lokale Zeit.

    Erst die Vorhersage, dann die eigene Rechnung. Der Suffix ist der Grund für
    das Herumsuchen: fordert man mehrere Modelle an, heißt das Feld nicht mehr
    `sunrise`, sondern `sunrise_dwd_icon_seamless`. Bis 1.4.3 griff der Zugriff
    daneben, die Prüfung lief leer, und 30 Prozent aller Sessionstunden lagen
    zwischen 20 und 7 Uhr.
    """
    daily = fc.get("daily") if isinstance(fc.get("daily"), dict) else {}

    def feld(name):
        if name in daily:
            return daily[name]
        for key, wert in daily.items():
            if key.startswith(name + "_"):
                return wert
        return None

    def liste(name):
        wert = feld(name)
        return wert if isinstance(wert, list) else []

    tage_api = liste("time")
    auf_api, unter_api = liste("sunrise"), liste("sunset")
    offset = _zeitversatz(fc)
    # Ohne Zeitversatz in der Antwort bleibt nur die Länge durch 15 Grad. Das
    # reicht, um die Nacht auszuschließen, aber nicht für einen Abgleich auf
    # Minuten — der wird dann übersprungen, statt eine Abweichung zu melden,
    # die nur die eigene Schätzung misst.
    offset_bekannt = offset is not None
    if not offset_bekannt:
        offset = int(round(float(spot.get("lon") or 0.0) / 15.0)) * 3600
    rand = timedelta(minutes=DAYLIGHT_MARGIN_MIN)
    fenster = {}
    for tag in tage:
        aus_api = None
        if auf_api and unter_api and tag in tage_api:
            i = tage_api.index(tag)
            try:
                aus_api = (datetime.fromisoformat(auf_api[i]), datetime.fromisoformat(unter_api[i]))
            except (IndexError, ValueError, TypeError):
                aus_api = None
            if aus_api and (aus_api[0].tzinfo or aus_api[1].tzinfo):
                aus_api = None           # Ortszeit ohne Zone erwartet; mit Zone ließe sie sich nicht vergleichen
        gerechnet = None
        if spot.get("lat") is not None and spot.get("lon") is not None:
            try:
                gerechnet = sonne.zeiten_lokal(
                    float(spot["lat"]), float(spot["lon"]), date.fromisoformat(tag), int(offset))
            except (ValueError, TypeError):
                gerechnet = None
        if aus_api and gerechnet and offset_bekannt:
            ab = max(abs((aus_api[0] - gerechnet[0]).total_seconds()),
                     abs((aus_api[1] - gerechnet[1]).total_seconds())) / 60.0
            SONNE_STATISTIK["abweichung_min"] = max(SONNE_STATISTIK["abweichung_min"], round(ab, 1))
        quelle = aus_api or gerechnet
        if not quelle:
            continue
        SONNE_STATISTIK["vorhersage" if aus_api else "gerechnet"] += 1
        fenster[tag] = (quelle[0] + rand, quelle[1] - rand)
    return fenster



# ── Teilscores ───────────────────────────────────────────────────────────────

def pick_wing(wind_kn: float, wings: list[dict]) -> dict | None:
    """Passendster Wing: der, in dessen Bereich der Wind am zentralsten liegt."""
    best, best_c = None, -1.0
    for w in wings:
        if w["low"] <= wind_kn <= w["high"]:
            mid = (w["low"] + w["high"]) / 2
            half = (w["high"] - w["low"]) / 2
            c = 1.0 - abs(wind_kn - mid) / half
            if c > best_c:
                best, best_c = w, c
    return best


def score_wind(wind_kn: float, cfg) -> tuple[float, dict | None]:
    wings = cfg["quiver"]["wings"]
    wing = pick_wing(wind_kn, wings)
    if wing is None:
        return 0.0, None
    mid = (wing["low"] + wing["high"]) / 2
    half = (wing["high"] - wing["low"]) / 2
    r = abs(wind_kn - mid) / half                      # 0 = Mitte, 1 = Rand
    centrality = 1.0 if r <= 0.5 else 1.0 - (r - 0.5)  # Rand → 0.5

    lo, hi = cfg["wind"]["preferred_low"], cfg["wind"]["preferred_high"]
    if lo <= wind_kn <= hi:
        band = 1.0
    else:
        gap = lo - wind_kn if wind_kn < lo else wind_kn - hi
        band = max(0.6, 1.0 - gap / 8.0 * 0.4)
    return round(centrality * band, 3), wing


def score_gust(wind_kn: float, gust_kn: float, cfg) -> tuple[float, float]:
    gf = gust_kn / max(wind_kn, 1.0)
    ok, bad = cfg["wind"]["gust_ok"], cfg["wind"]["gust_bad"]
    if gf <= ok:
        s = 1.0
    elif gf >= bad:
        s = 0.3
    else:
        s = 1.0 - (gf - ok) / (bad - ok) * 0.7
    top = max(w["high"] for w in cfg["quiver"]["wings"])
    if gust_kn > top + 6:
        s = min(s, 0.25)
    return round(s, 3), round(gf, 2)


def match_sector(spot, wind_from: float) -> dict | None:
    for sec in spot.get("sectors", []):
        if in_sector(wind_from, sec["from"], sec["to"]):
            return sec
    return None


def score_direction(spot, wind_from: float, cfg=None) -> tuple[float, str, str]:
    """Zwei verschiedene Arten von „keine Angabe" — die dürfen nicht gleich zählen.

    Hat der Spot Sektoren, aber keiner passt, ist das eine Aussage: diese
    Richtung geht hier nicht. Hat er gar keine Sektoren, ist es schlicht eine
    Lücke im Katalog, und ein harter Malus würde jeden importierten Spot
    unsichtbar machen.
    """
    if not spot.get("sectors"):
        neutral = 0.6
        if cfg is not None:
            neutral = cfg["wind"].get("unknown_direction_score", 0.6)
        return neutral, "unbekannt", "chop"
    sec = match_sector(spot, wind_from)
    if sec is None:
        # Ein Wert für `quality` wie „unbekannt“ — Schlüssel und Anzeige
        # zugleich; report.py übersetzt beim Anzeigen: T(QUAL_LABEL.get(q, q)).
        return 0.2, N_("Richtung nicht im Katalog"), "chop"
    return QUALITY_SCORE.get(sec.get("quality", "ok"), 0.6), sec.get("quality", "ok"), sec.get("water", "chop")


def score_water(water_label: str, wind_kn: float, cfg) -> float:
    base = WATER_BASE.get(water_label, 0.6)
    aversion = cfg["water"]["chop_aversion"]
    s = 1.0 - aversion * (1.0 - base)
    if water_label != "flat" and wind_kn > 22:
        s *= 0.9
    return round(max(0.0, min(1.0, s)), 3)


def score_weather(temp, rain, cape, code, cfg) -> tuple[float, list[str], str | None]:
    w = cfg["weather"]
    warn: list[str] = []
    if code in w["thunder_codes"]:
        return 0.0, warn, TD("Gewitter gemeldet")
    if temp is None or temp < w["air_temp_min"] or temp > w["air_temp_max"]:
        return 0.0, warn, TD("Lufttemperatur {temp} °C außerhalb {min}–{max} °C",
                            temp=temp, min=w["air_temp_min"], max=w["air_temp_max"])

    s = 1.0
    edge = min(temp - w["air_temp_min"], w["air_temp_max"] - temp)
    if edge < 3:
        s *= 0.8
        warn.append(TD("{temp} °C nah an deiner Grenze", temp=f"{temp:.0f}"))

    rain = rain or 0.0
    if rain >= w["rain_hard_mm"]:
        s *= 0.2
        warn.append(TD("Regen {mm} mm/h", mm=f"{rain:.1f}"))
    elif rain >= w["rain_soft_mm"]:
        s *= 1.0 - 0.5 * (rain - w["rain_soft_mm"]) / max(w["rain_hard_mm"] - w["rain_soft_mm"], 0.1)
        warn.append(TD("Regen {mm} mm/h", mm=f"{rain:.1f}"))

    cape = cape or 0.0
    if cape >= w["cape_bad"]:
        s *= 0.35
        warn.append(TD("CAPE {cape} J/kg — Gewitterneigung hoch", cape=f"{cape:.0f}"))
    elif cape >= w["cape_warn"]:
        s *= 0.7
        warn.append(TD("CAPE {cape} J/kg — Gewitter möglich", cape=f"{cape:.0f}"))
    return round(max(0.0, s), 3), warn, None


def wetsuit(sst: float | None) -> str | None:
    """Faustregel für die Neoprenwahl aus der Wassertemperatur."""
    if sst is None:
        return None
    if sst < 10:
        return T("6/5 mit Haube, Handschuhe, Schuhe")
    if sst < 13:
        return T("5/4 mit Haube")
    if sst < 16:
        return T("5/4 oder dicker 4/3")
    if sst < 19:
        return "4/3"
    if sst < 22:
        return "3/2"
    return T("Shorty oder Lycra")


def thermal_adjust(spot, t, wind, wdir, cfg):
    """Alter Aufruf ohne Wetterbezug — bleibt für die Tests und die Kommandozeile.

    Die Rechnung liegt jetzt in `thermik.annahme()` und berücksichtigt
    Einstrahlung und Gegenwind. Ohne diese Angaben verhält sie sich wie früher:
    das Kalenderblatt ohne Blick aus dem Fenster.
    """
    wind, wdir, angenommen, _ = thermik.annahme(spot, t, wind, wdir, cfg)
    return wind, wdir, angenommen


def _ortszeit(zeitpunkt: datetime | None, spot, fc) -> datetime | None:
    """Ein Zeitpunkt mit Zone als Ortszeit des Spots (ohne Zone), wie seine
    Stundenstempel; einer ohne Zone bleibt, wie er ist."""
    if zeitpunkt is None or zeitpunkt.tzinfo is None:
        return zeitpunkt
    versatz = _zeitversatz(fc)
    if versatz is None:
        versatz = int(round(float(spot.get("lon") or 0.0) / 15.0)) * 3600
    return (zeitpunkt.astimezone(timezone.utc) + timedelta(seconds=int(versatz))).replace(tzinfo=None)


def tide_events(series: dict, day: str) -> list[tuple[str, str]]:
    """Hoch- und Niedrigwasser eines Tages als („HW“, „14:25“) — die Scheitel
    rechnet `tide.extrema` auf die Minute; bis 1.17.0 stand hier die volle
    Stunde des höchsten Werts."""
    return [(ev["art"], ev["zeit"].strftime("%H:%M")) for ev in gezeiten.extrema(series)
            if ev["zeit"].date().isoformat() == day]


# ── Stundenbewertung ─────────────────────────────────────────────────────────

def score_from_geometry(spot, wind_from: float, wind_kn: float, rose, cfg):
    """Richtung und Wasserzustand aus der Fetch-Rose statt aus Handarbeit.

    Luv-Fetch sagt, wie weit der Wind über Wasser angelaufen ist — daraus die
    Wellenhöhe. Lee-Platz sagt, wie viel Wasser vor dir liegt. Beides zusammen
    ergibt die Windlage.
    """
    up = rose_at(rose, wind_from)
    down = rose_at(rose, wind_from + 180)
    label, quality = classify(up, down, cfg)
    hs = wave_height_m(wind_kn, up)
    return quality, label, water_label(hs), up, down, hs


def score_hours(spot, fc: dict, cfg, marine: dict | None = None,
                rose: list | None = None, tide: dict | None = None,
                jetzt: datetime | None = None, wave: dict | None = None,
                tide_info: dict | None = None, ab: datetime | None = None,
                tage: tuple[str, str] | None = None) -> list[dict]:
    """`jetzt` schneidet vergangene Stunden ab.

    Seit 2.3.0 kann eine Suche später beginnen (zeitraum.py): `tage` ist dann
    (erster Tag, Tag nach dem letzten) als „JJJJ-MM-TT“ — Stunden an anderen
    Tagen gibt es für diese Suche nicht —, und `ab` (mit Zone) schneidet am
    ersten Tag die Stunden davor ab wie `jetzt` die vergangenen.

    `wave` ist die Wellenhöhe aus dem Wellenmodell (Open-Meteo Marine, nur mit
    --marine und nur am Meer), {Zeit: m}. Wo sie vorliegt, ersetzt sie die
    Faustformel aus Anlauflänge und Wind: die rechnet mit U10 und ohne Dauer-
    und Tiefenbegrenzung, das Modell mit Dünung, Tide und Bodenprofil. Bis
    1.6.1 wurde die Zahl geholt und weggeworfen. Die Anlauflänge bleibt für
    die Windlage — ablandig oder auflandig sagt kein Wellenmodell.

    `tide` ist der Wasserstand {Zeit: m}, `tide_info` die Übersicht aus
    `tide.uebersicht()`. Ist die Tide am Spot aktiv, trägt jede Stunde ihre
    Lage im Zyklus (`tide_lage`); steht im Katalog ein Tidenfenster, fallen
    Stunden außerhalb mit Veto heraus. Ohne Fenster ändert die Tide keinen
    Score — sie steht dann nur im Report.

    Die Vorhersage beginnt um 00:00 des laufenden Tages. Wer den Report um elf
    startet, bekam bis 1.4.3 als erstes eine „Session" von 0 bis 10 Uhr
    angeboten — und die Stunden zählten in „10 h Wasser an 2 Tagen" mit. Ohne
    Angabe bleibt alles stehen; nur der echte Lauf setzt die Grenze.
    """
    tiden_aktiv = bool(tide_info and tide_info.get("aktiv"))
    ereignisse = (tide_info or {}).get("ereignisse") or [] if tiden_aktiv else []
    fenster = (tide_info or {}).get("fenster") if tiden_aktiv else None
    models = cfg.get("wind", {}).get("models") or DEFAULT_MODELS
    primary = cfg.get("wind", {}).get("primary_model") or models[0]
    h = normalize(fc["hourly"], models, primary)
    # Gibt es für diesen Spot ein hochauflösendes Regionalmodell, überschreibt
    # es den Wind für die Stunden, die es abdeckt. Es reicht kürzer als die
    # globalen, deshalb erst nach dem Zusammenführen und nur stundenweise.
    fein = fc.get("_highres")
    if fein:
        from .sources.highres import einsetzen, kurzname
        h["_highres_stunden"] = einsetzen(h, fein[1], kurzname(fein[0]))
        h["_highres_modell"] = fein[0]
        if h["_highres_stunden"]:
            # Die Einigkeit muss das Modell einschließen, dessen Wind im
            # Report steht — sonst beschreibt sie drei Reihen, die niemand
            # mehr sieht.
            h["wind_spread"], h["wind_agree"] = einigkeit(h.get("wind_models") or {},
                                                          len(h.get("time") or []))
    wind_factor = float(spot.get("wind_factor", 1.0) or 1.0)
    zeiten = h.get("time") if isinstance(h.get("time"), list) else []
    sun = _sonnenzeiten(spot, fc, sorted({t[:10] for t in zeiten if isinstance(t, str)}))
    # Die Stundenstempel sind Ortszeit des Spots; ein Zeitpunkt mit Zone
    # wird in dieselbe Ortszeit gebracht, sonst gilt „vorbei“ in Athen
    # eine Stunde zu früh und in Lissabon eine zu spät. Ebenso der Start.
    jetzt, ab = _ortszeit(jetzt, spot, fc), _ortszeit(ab, spot, fc)
    # Reihen je Zeitstempel ({Zeit: Wert}) aus den Zusatzquellen
    marine, wave, tide = ({} if not isinstance(x, dict) else x for x in (marine, wave, tide))

    weights = cfg["weights"]
    rows = []
    energie: dict[str, float] = {}       # Wh/m² je Tag, seit Tagesbeginn summiert
    th_stunden: dict[str, list] = {}     # (Stunde, Stundenpotenzial) je Tag
    for i, tstr in enumerate(zeiten):
        try:
            t = datetime.fromisoformat(tstr)
        except (TypeError, ValueError):
            continue                     # ein unlesbarer Stempel kostet die Stunde, nicht die Suche
        if t.tzinfo is not None:
            continue                     # Ortszeit ohne Zone — mit Zone ließe sie sich nicht vergleichen
        day = t.date().isoformat()
        if tage is not None and not (tage[0] <= day < tage[1]):
            continue                     # vor oder nach dem Zeitraum der Suche (seit 2.3.0)

        def reihe(key, standard=None):
            series = h.get(key)
            wert = _zahl(series[i]) if isinstance(series, list) and i < len(series) else None
            return standard if wert is None else wert

        def val(key):                    # eine Vorhersagegröße — steht in models.CORE
            return reihe(key)

        wind = val("wind_speed_10m")
        if wind is None:
            continue
        sst = _zahl(marine.get(tstr))
        gust = (val("wind_gusts_10m") or wind)
        # Eine fehlende Richtung bleibt None. `or 0.0` machte daraus Nord, und
        # Nord wurde dann gegen Sektoren und Rose geprüft, als wäre es gemessen.
        wdir = val("wind_direction_10m")
        wind, gust = wind * wind_factor, gust * wind_factor
        # Eingestrahlte Energie seit Sonnenaufgang dieses Tages. Die Thermik
        # lebt nicht von der Sonne dieser Stunde, sondern davon, wie viel
        # Wärme der Vormittag schon in den Boden gebracht hat.
        strahlung = val("shortwave_radiation")
        if strahlung is not None:
            energie[day] = energie.get(day, 0.0) + float(strahlung)
        energie_bisher = energie.get(day) if strahlung is not None else None
        wind, wdir, thermal_assumed, thermik_p = thermik.annahme(
            spot, t, wind, wdir, cfg, energie_bisher, val("cloud_cover"))
        if thermal_assumed:
            gust = max(gust, wind * 1.2)
        if spot.get("thermal"):
            th_stunden.setdefault(day, []).append((t.hour, thermik_p))

        row = {
            "t": t, "day": day, "wind": round(wind, 1), "gust": round(gust, 1), "dir": wdir,
            "dir_name": compass(wdir) if wdir is not None else "?", "temp": val("temperature_2m"),
            "rain": val("precipitation"), "cape": val("cape"),
            "code": val("weather_code"), "sst": sst, "warn": [], "veto": None,
            "spread": reihe("wind_spread", 0.0),
            "agree": reihe("wind_agree", 1.0),
            "models": {m: (_zahl(ser[i]) if isinstance(ser, list) and i < len(ser) else None)
                       for m, ser in (h.get("wind_models") or {}).items()},
            "thermal": thermal_assumed,
            "thermik_p": round(thermik_p, 2),
            "modell": (h.get("wind_herkunft") or [None] * (i + 1))[i]
                      if i < len(h.get("wind_herkunft") or []) else None,
            "modell_delta": reihe("wind_unterschied"),
            "tide": _zahl(tide.get(tstr)),
        }
        if thermal_assumed:
            row["warn"].append(TD("Thermik angenommen"))
        if ereignisse:
            # Die Stundenmitte, nicht der Stundenbeginn: „13 Uhr“ steht für
            # 13:00–14:00, und bei Hochwasser um 14:25 ist diese Stunde
            # auflaufend, nicht schon Stauwasser.
            lg = gezeiten.lage(t + timedelta(minutes=30), ereignisse)
            row["tide_lage"] = lg["art"] if lg else None

        # Ein Veto zählt nur als „ja oder nein“; der Text steht im Raster.
        if jetzt is not None and t + timedelta(hours=1) <= jetzt:
            row["veto"] = TD("vorbei")
            row["score"] = 0.0
            rows.append(row)
            continue

        if ab is not None and t + timedelta(hours=1) <= ab:
            row["veto"] = TD("vor dem gewählten Start")
            row["score"] = 0.0
            rows.append(row)
            continue

        if sst is not None and sst < cfg["weather"]["water_temp_min"]:
            row["veto"] = TD("Wasser {sst} °C unter deiner Grenze von {grenze} °C",
                            sst=f"{sst:.0f}", grenze=cfg["weather"]["water_temp_min"])
            row["score"] = 0.0
            rows.append(row)
            continue

        rise_set = sun.get(day)
        if rise_set and not (rise_set[0] <= t <= rise_set[1]):
            row["veto"] = TD("außerhalb der Tageslichtzeit")
            row["score"] = 0.0
            rows.append(row)
            continue

        if fenster and gezeiten.im_fenster(t + timedelta(minutes=30), ereignisse, fenster) is False:
            row["veto"] = TD("außerhalb des Tidenfensters ({fenster})", fenster=gezeiten.fenster_text(fenster))
            row["score"] = 0.0
            rows.append(row)
            continue

        s_wind, wing = score_wind(wind, cfg)
        if wing is None:
            row["veto"] = TD("{kn} kn — kein passender Wing im Quiver", kn=f"{wind:.0f}")
            row["score"] = 0.0
            rows.append(row)
            continue
        row["wing"] = wing["size"]

        s_gust, gf = score_gust(wind, gust, cfg)
        row["gust_factor"] = gf
        if gf >= cfg["wind"]["gust_bad"]:
            row["warn"].append(TD("böig ({faktor})", faktor=f"{gf:.2f}"))

        use_geo = rose is not None and not (
            spot.get("sectors") and cfg["geometry"].get("prefer_manual_sectors", True))
        hs_modell = _zahl(wave.get(tstr))
        if wdir is None:
            # Ohne Richtung keine Windlage: neutral wie ein Spot ohne Sektoren.
            s_dir = cfg["wind"].get("unknown_direction_score", 0.6)
            quality, wlabel = "unbekannt", "chop"
            row["source"] = "keine Richtung"
            if hs_modell is not None:
                wlabel = water_label(float(hs_modell))
                row["wave_m"] = round(float(hs_modell), 2)
                row["wave_quelle"] = "Wellenmodell"
        elif use_geo:
            s_dir, quality, wlabel, up, down, hs = score_from_geometry(spot, wdir, wind, rose, cfg)
            if hs_modell is not None:
                hs = float(hs_modell)
                wlabel = water_label(hs)
                row["wave_quelle"] = "Wellenmodell"
            row["fetch_up_km"] = round(up / 1000, 1)
            row["fetch_down_km"] = round(down / 1000, 1)
            row["wave_m"] = round(hs, 2)
            row["source"] = "geometrie"
            # B12: ablandig mit viel Wasser in Lee ist keine Komfortfrage, sondern
            # die Frage nach dem Rückweg. Nur, wenn in der Konfiguration eine
            # Grenze steht; 0 heißt aus, dann bleibt es bei der Warnung.
            veto_km = float(cfg["geometry"].get("offshore_veto_km", 0) or 0)
            if veto_km and quality == "ablandig" and down / 1000.0 >= veto_km:
                row["dir_quality"], row["water"] = quality, wlabel
                row["veto"] = TD("ablandig mit {km} km freiem Wasser in Lee (Grenze {grenze} km)",
                                km=f"{down / 1000:.0f}", grenze=f"{veto_km:.0f}")
                row["score"] = 0.0
                rows.append(row)
                continue
        else:
            s_dir, quality, wlabel = score_direction(spot, wdir, cfg)
            row["source"] = "katalog"
            if hs_modell is not None:            # nur zur Anzeige — das Katalogurteil bleibt
                row["wave_m"] = round(float(hs_modell), 2)
                row["wave_quelle"] = "Wellenmodell"
        row["dir_quality"] = quality
        row["water"] = wlabel
        s_water = score_water(wlabel, wind, cfg)

        s_weather, warns, veto = score_weather(row["temp"], row["rain"], row["cape"], row["code"], cfg)
        row["warn"].extend(warns)
        if veto:
            row["veto"] = veto
            row["score"] = 0.0
            rows.append(row)
            continue

        total = (
            weights["wind"] * s_wind
            + weights["direction"] * s_dir
            + weights["water"] * s_water
            + weights["weather"] * s_weather
            + weights["gust"] * s_gust
        ) / sum(weights.values())
        # Uneinige Modelle drücken den Score — eine Fahrt plant man nicht auf einen Ausreißer.
        agree_w = cfg.get("wind", {}).get("agreement_weight", 0.3)
        total *= (1.0 - agree_w) + agree_w * row["agree"]
        row["parts"] = {"wind": s_wind, "richtung": s_dir, "wasser": s_water,
                        "wetter": s_weather, "böen": s_gust}
        row["score"] = round(total, 3)
        rows.append(row)

    # Das Thermikpotenzial des Tages, nicht der besten Stunde. Es hängt an
    # jeder Zeile des Tages, damit die Session es ohne Umweg mitnimmt.
    th = spot.get("thermal")
    if th and th_stunden:
        tag_p = {tag: thermik.tagespotenzial(th, werte) for tag, werte in th_stunden.items()}
        for row in rows:
            row["thermik_tag"] = round(tag_p.get(row["day"], 0.0), 3)

    apply_thunder_shadow(rows, cfg)
    return rows


def apply_thunder_shadow(rows: list[dict], cfg) -> None:
    """Ein Gewitter um 17 Uhr macht auch 15 Uhr fragwürdig.

    Das Modell markiert nur die Stunde, in der es an diesem Gitterpunkt rechnet.
    Draußen auf dem Wasser interessiert dich das Zeitfenster drumherum genauso.
    """
    shadow = cfg["weather"].get("thunder_shadow_h", 0)
    if not shadow:
        return
    codes = set(cfg["weather"]["thunder_codes"])
    hits = [i for i, r in enumerate(rows) if r.get("code") in codes]
    if not hits:
        return
    for i, row in enumerate(rows):
        if row["veto"] or i in hits:
            continue
        near = min((abs(i - h) for h in hits), default=99)
        if near <= shadow:
            row["score"] = round(row["score"] * 0.4, 3)
            row["warn"].append(TD("Gewitter {h} h entfernt im Modell", h=near))
            row["thunder_shadow"] = near
    return


# ── Sessions ─────────────────────────────────────────────────────────────────

def build_sessions(spot, rows: list[dict], cfg) -> list[dict]:
    min_score = cfg["session"]["min_score"]
    min_hours = cfg["session"]["min_hours"]
    sessions, block = [], []

    def flush():
        if len(block) >= min_hours:
            # Der Unterschied zum groben Modell als Median, nicht als Maximum.
            # Bis 1.5.0 stand dort das Maximum über den Block — eine Zahl, die
            # mit der Länge der Session wächst statt mit der Güte des Modells:
            # im Lauf vom 16.09.2026 lag der Median bei Sessions bis 8 h bei
            # 0 kn, bei Sessions über 16 h bei 6 kn. Gezählt werden nur die
            # Stunden, die das feine Modell wirklich abdeckt; es reicht kürzer
            # als die globalen, und eine fehlende Stunde ist kein Nullwert.
            deltas = [r["modell_delta"] for r in block if r.get("modell_delta") is not None]
            winds = [r["wind"] for r in block]
            wings = sorted({r["wing"] for r in block if r.get("wing")})
            warns = summarize_warnings(block, cfg)
            quals = [r.get("dir_quality", "ok") for r in block]
            sessions.append({
                "spot": spot,
                "day": block[0]["day"],
                "start": block[0]["t"],
                "end": block[-1]["t"] + timedelta(hours=1),
                "hours": len(block),
                "score": round(sum(r["score"] for r in block) / len(block), 3),
                "peak": round(max(r["score"] for r in block), 3),
                "wind_min": round(min(winds)), "wind_max": round(max(winds)),
                "gust_max": round(max(r["gust"] for r in block)),
                "dirs": sorted({r["dir_name"] for r in block}),
                "wings": wings,
                "water": max({r.get("water", "chop") for r in block},
                             key=lambda w: {"wave": 2, "chop": 1, "flat": 0}.get(w, 1)),
                "quality": max(quals, key=lambda q: {"best": 3, "good": 2, "ok": 1, "bad": 0}.get(q, 1)),
                "temp": round(sum(r["temp"] for r in block if r["temp"] is not None) / len(block)),
                "fetch_km": (round(max(r["fetch_up_km"] for r in block if r.get("fetch_up_km") is not None), 1)
                             if any(r.get("fetch_up_km") is not None for r in block) else None),
                "wave_m": (round(max(r["wave_m"] for r in block if r.get("wave_m") is not None), 2)
                           if any(r.get("wave_m") is not None for r in block) else None),
                "geo": any(r.get("source") == "geometrie" for r in block),
                "wave_quelle": ("Wellenmodell" if any(r.get("wave_quelle") == "Wellenmodell" for r in block)
                                else None),
                "agree": round(sum(r.get("agree", 1.0) for r in block) / len(block), 2),
                "modelle": sorted({m for r in block for m, v in (r.get("models") or {}).items()
                                   if v is not None and m != "grob"}),
                "spread_max": round(max(r.get("spread") or 0.0 for r in block), 1),
                "thermal": any(r.get("thermal") for r in block),
                "thermik_p": max((r.get("thermik_tag") or 0.0) for r in block),
                "thermik_spitze": max((r.get("thermik_p") or 0.0) for r in block),
                "modell": next((r.get("modell") for r in block if r.get("modell")), None),
                "modell_delta": round(median(deltas), 1) if deltas else None,
                "modell_delta_max": round(max(deltas, key=abs), 1) if deltas else None,
                "modell_stunden": len(deltas),
                "sst": (round(sum(r["sst"] for r in block if r.get("sst") is not None) /
                              max(1, sum(1 for r in block if r.get("sst") is not None)), 1)
                        if any(r.get("sst") is not None for r in block) else None),
                "tides": [(ev["art"], ev["zeit"].strftime("%H:%M")) for ev in tiden
                          if ev["zeit"].date().isoformat() == block[0]["day"]],
                "tide_lage": block[0].get("tide_lage"),
                "warn": warns,
            })
        block.clear()

    # Hoch- und Niedrigwasser einmal je Spot, nicht je Session — und nur, wo
    # die Tide aktiv ist: `tide_lage` steht an den Stunden genau dann, wenn
    # `tide.uebersicht()` sie für diesen Spot eingeschaltet hat.
    tiden = (gezeiten.extrema({r["t"].strftime("%Y-%m-%dT%H:%M"): r["tide"] for r in rows
                               if r.get("tide") is not None})
             if any(r.get("tide_lage") for r in rows) else [])

    # Eine einzelne Stunde knapp unter der Schwelle zwischen zwei tragenden
    # Stunden zerschnitt bis 1.6.1 die Session: 0,54 mitten im Nachmittag
    # machte aus fünf Stunden zwei mal zwei, mit `min_hours: 3` gar nichts.
    # Sie wird überbrückt — mit Vermerk, und nur eine, nur ohne Veto, nur bis
    # 0,1 unter der Schwelle.
    traegt = [r["score"] >= min_score and not r["veto"] for r in rows]
    for i in range(1, len(rows) - 1):
        if (not traegt[i] and not rows[i]["veto"] and rows[i]["score"] >= min_score - 0.1
                and traegt[i - 1] and traegt[i + 1]
                and rows[i]["t"] - rows[i - 1]["t"] == timedelta(hours=1)
                and rows[i + 1]["t"] - rows[i]["t"] == timedelta(hours=1)
                and rows[i]["day"] == rows[i - 1]["day"] == rows[i + 1]["day"]):
            rows[i]["bruecke"] = True

    prev_t = None
    for row in rows:
        good = (row["score"] >= min_score or row.get("bruecke")) and not row["veto"]
        # Eine Session endet spätestens mit dem Tag. Seit die Nacht wieder
        # ausgeschlossen wird, greift das kaum noch — aber ohne diese Zeile
        # stand im Report „Do 17.09. 00–00 Uhr · 48 h", und die Überschrift
        # log, weil sie nur den ersten Tag und zwei Uhrzeiten zeigt.
        contiguous = (prev_t is not None and (row["t"] - prev_t) == timedelta(hours=1)
                      and bool(block) and row["day"] == block[-1]["day"])
        if good and (contiguous or not block):
            block.append(row)
        elif good:
            flush()
            block.append(row)
        else:
            flush()
        prev_t = row["t"]
    flush()
    return sessions


def summarize_warnings(block: list[dict], cfg) -> list[str]:
    """Aus 12 Stundenwarnungen werden vier Sätze statt vierzig."""
    w = cfg["weather"]
    out = []
    cape = max((r.get("cape") or 0) for r in block)
    rain = max((r.get("rain") or 0) for r in block)
    gf = max((r.get("gust_factor") or 0) for r in block)
    shadow = [r["thunder_shadow"] for r in block if r.get("thunder_shadow") is not None]
    temps = [r["temp"] for r in block if r["temp"] is not None]
    # Nur Anzeige (report.py fügt sie mit Komma zusammen) — gleich übersetzt, als
    # TD(): der Report setzt sie seit 2.3.0 für jede seiner vier Sprachen neu.
    if cape >= w["cape_bad"]:
        out.append(TD("Gewitterneigung hoch (CAPE bis {cape})", cape=f"{cape:.0f}"))
    elif cape >= w["cape_warn"]:
        out.append(TD("Gewitter möglich (CAPE bis {cape})", cape=f"{cape:.0f}"))
    if rain >= w["rain_hard_mm"]:
        out.append(TD("kräftiger Regen (bis {mm} mm/h)", mm=f"{rain:.1f}"))
    elif rain >= w["rain_soft_mm"]:
        out.append(TD("etwas Regen (bis {mm} mm/h)", mm=f"{rain:.1f}"))
    if any(r.get("dir_quality") == "unbekannt" for r in block):
        out.append(TD("Windrichtungen für diesen Spot nicht hinterlegt"))
    spreads = [r.get("spread") or 0.0 for r in block]
    if spreads and max(spreads) >= 6:
        worst = max(block, key=lambda r: r.get("spread") or 0.0)
        parts = ", ".join(f"{m} {v:.0f}" for m, v in (worst.get("models") or {}).items() if v is not None)
        out.append(TD("Modelle uneinig (bis {kn} kn Abstand: {modelle})", kn=f"{max(spreads):.0f}", modelle=parts))
    if any(r.get("thermal") for r in block):
        out.append(TD("Thermik angenommen — Erfahrungswert, kein Modellwind"))
    if any(r.get("bruecke") for r in block):
        out.append(TD("eine Stunde knapp unter der Mindestgüte mitgenommen"))
    if any(r.get("source") == "keine Richtung" for r in block):
        out.append(TD("Windrichtung fehlt im Modell — Lage neutral bewertet"))
    if cfg["geometry"].get("offshore_warn", True) and \
            any(r.get("dir_quality") == "ablandig" for r in block):
        out.append(TD("ablandiger Wind — glattes Wasser, aber du treibst raus"))
    if shadow:
        out.append(TD("Gewitter im Modell {h} h neben dieser Session", h=min(shadow)))
    if gf >= cfg["wind"]["gust_bad"]:
        out.append(TD("böig (Faktor bis {faktor})", faktor=f"{gf:.2f}"))
    if temps:
        edge = min(min(t - w["air_temp_min"] for t in temps),
                   min(w["air_temp_max"] - t for t in temps))
        if edge < 3:
            out.append(TD("Temperatur nah an deiner Grenze ({von}–{bis} °C)",
                         von=f"{min(temps):.0f}", bis=f"{max(temps):.0f}"))
    return out


def consecutive_runs(days: list[str]) -> list[list[str]]:
    """Zusammenhängende Kalendertage — für „ich will zwei Nächte bleiben"."""
    runs, cur = [], []
    for d in sorted(days):
        cur_date = datetime.fromisoformat(d).date()
        if cur and (cur_date - datetime.fromisoformat(cur[-1]).date()).days == 1:
            cur.append(d)
        else:
            if cur:
                runs.append(cur)
            cur = [d]
    if cur:
        runs.append(cur)
    return runs


def apply_reliability(sessions: list[dict], cfg) -> int:
    """Thermiksessions: die Verlässlichkeit aus dem Katalog als Wahrscheinlichkeit.

    Das Ensemble beantwortet „wie sicher ist die Lage?“ für Modellwind. An
    einer Thermiksession kommt der Wind aber nicht aus dem Modell — das
    Ensemble sieht dort 5 kn und meldet 0 % Sicherheit, und bis 1.6.1 halbierte
    das genau die Sessions, die das Tool eigens korrigiert hatte. Die passende
    Wahrscheinlichkeit ist die Verlässlichkeit des Spots („quasi täglich“ oder
    „wenn alles passt“), und sie geht mit demselben gedämpften Faktor ein wie
    das Ensemble: `(1 − g) + g · p`, g aus `ensemble.weight`. Rückgabe:
    betroffene Sessions.
    """
    gewicht = float((cfg.get("ensemble") or {}).get("weight", 0.5) or 0.0)
    if gewicht <= 0:
        return 0
    n = 0
    for s in sessions:
        if not s.get("thermal"):
            continue
        verl = _zahl((s["spot"].get("thermal") or {}).get("reliability", 0.6))
        verl = 0.6 if verl is None else float(verl)          # kein Wert: wie ohne Angabe
        s.setdefault("score_roh", s["score"])
        s["score"] = round(s["score_roh"] * ((1.0 - gewicht) + gewicht * verl), 3)
        s["sicherheit"] = {"quelle": "thermik", "p": round(verl, 2)}
        n += 1
    return n


def ensemble_schwelle(kn: float, spot: dict, session: dict) -> float:
    """Was das rohe Ensemble zeigen muss, damit die Session fährt.

    Der Wind im Report ist nicht der rohe Modellwind: das Regionalmodell
    ersetzt ihn (Unterschied `modell_delta`), `wind_factor` skaliert ihn. Das
    Ensemble kennt beides nicht. Gefragt wird deshalb nach der rohen Zahl, aus
    der nach beiden Korrekturen `kn` würde: (grob + delta) · faktor ≥ kn.
    """
    faktor = float(spot.get("wind_factor", 1.0) or 1.0)
    delta = float(session.get("modell_delta") or 0.0)
    return max(0.0, kn / max(faktor, 0.05) - delta)


def rank_trips(sessions: list[dict], cfg, nights: int = 0) -> list[dict]:
    """Fasst Sessions pro Spot zu Trips zusammen und prüft die Fahrzeit-Regel."""
    apply_reliability(sessions, cfg)
    by_spot: dict[str, list[dict]] = {}
    for s in sessions:
        by_spot.setdefault(s["spot"]["id"], []).append(s)

    cap = cfg["session"]["useful_hours_cap"]
    per_water = cfg["drive"]["hours_per_water_hour"]
    trips = []
    for sid, group in by_spot.items():
        spot = group[0]["spot"]
        days = sorted({s["day"] for s in group})
        runs = consecutive_runs(days)
        best_run = max(runs, key=len) if runs else []
        if nights and len(best_run) < nights + 1:
            continue
        hours_per_day = {d: min(cap, sum(s["hours"] for s in group if s["day"] == d)) for d in days}
        total_hours = sum(hours_per_day.values())
        n_days = len(days)
        avg = total_hours / n_days
        drive = spot["drive_h"]
        acceptable = min(per_water * avg * (1 + 0.5 * nights), cfg["drive"]["max_hours"])
        if drive <= acceptable:
            drive_score = 1.0
        else:
            drive_score = max(0.0, 1.0 - (drive - acceptable) / max(acceptable, 0.5) * 0.8)
        quality = sum(s["score"] * s["hours"] for s in group) / max(sum(s["hours"] for s in group), 1)
        trips.append({
            "spot": spot,
            "sessions": sorted(group, key=lambda s: s["start"]),
            "days": days,
            "run_days": best_run,
            "run_len": len(best_run),
            "hours_per_day": hours_per_day,
            "total_hours": total_hours,
            "avg_hours": round(avg, 1),
            "drive_h": drive,
            "acceptable_drive_h": round(acceptable, 1),
            "drive_ok": drive <= acceptable,
            "quality": round(quality, 3),
            "drive_score": round(drive_score, 4),
            "rank": _rang(quality, drive_score, total_hours),
        })
    trips.sort(key=lambda t: -t["rank"])
    plan_b(trips, cfg)
    return trips


def _rang(quality: float, drive_score: float, total_hours: float) -> float:
    return round(quality * drive_score * min(1.0, 0.55 + 0.15 * total_hours), 4)


def apply_ensemble(trips: list[dict], cfg) -> int:
    """Die Ensemble-Wahrscheinlichkeit als Faktor im Score. Rückgabe: Sessions.

    Bis 1.4.3 stand die Zahl im Report und sonst nirgends: `ensemble` kam in
    diesem Modul kein einziges Mal vor. Deshalb konnte eine Session mit „0 %
    sicher" auf Platz 2 stehen — die Zahl, die vor einer sechsstündigen
    Anfahrt am meisten zählt, hatte auf die Reihenfolge keinen Einfluss.

    Der Faktor ist gedämpft, nicht roh: `(1 − g) + g · p`. Mit dem Standard
    g = 0,5 behält eine Session ohne jede Rückendeckung die Hälfte ihres
    Scores. Roh zu multiplizieren würde sie auf null setzen und den Report bei
    einer unsicheren Wetterlage leeren — dann steht dort nichts, obwohl es
    etwas zu entscheiden gibt.

    Eine Grenze, die man kennen muss: die Wahrscheinlichkeit wird nur für die
    vordersten Ziele geholt. Wer weiter hinten liegt, wird weder belohnt noch
    bestraft und kann dadurch an einem gedämpften Ziel vorbeiziehen.
    """
    gewicht = float((cfg.get("ensemble") or {}).get("weight", 0.5) or 0.0)
    if gewicht <= 0:
        return 0
    n = 0
    for t in trips:
        betroffen = False
        for s in t["sessions"]:
            ens = s.get("ens")
            if not isinstance(ens, dict) or _zahl(ens.get("p_ride")) is None:
                continue                 # keine Wahrscheinlichkeit — oder keine Zahl: wie nicht abgefragt
            if s.get("thermal"):
                # Hier gilt die Verlässlichkeit des Spots (apply_reliability);
                # das Ensemble kann die Thermik nicht sehen und würde sie nur
                # bestrafen.
                continue
            s.setdefault("score_roh", s["score"])
            s["score"] = round(s["score_roh"] * ((1.0 - gewicht) + gewicht * float(ens["p_ride"])), 3)
            betroffen = True
            n += 1
        if betroffen:
            grp = t["sessions"]
            stunden = max(sum(x["hours"] for x in grp), 1)
            t["quality"] = round(sum(x["score"] * x["hours"] for x in grp) / stunden, 3)
            t["rank"] = _rang(t["quality"], t["drive_score"], t["total_hours"])
    if n:
        trips.sort(key=lambda t: -t["rank"])
        plan_b(trips, cfg)
    return n


def plan_b(trips: list[dict], cfg) -> None:
    """Die beste Alternative in Reichweite — wer Gruppen führt, hat immer eine."""
    plan_b_km = cfg.get("drive", {}).get("plan_b_km", 120)
    for t in trips:
        best = None
        for o in trips:
            if o is t:
                continue
            d = haversine_km(t["spot"]["lat"], t["spot"]["lon"], o["spot"]["lat"], o["spot"]["lon"])
            if d * 1.22 <= plan_b_km and set(o["days"]) & set(t["days"]):
                if best is None or o["rank"] > best[1]["rank"]:
                    best = (round(d * 1.22), o)
        t["plan_b"] = {"name": best[1]["spot"]["name"], "km": best[0],
                       "hours": best[1]["total_hours"]} if best else None
