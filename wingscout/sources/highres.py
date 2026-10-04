"""Hochauflösende Regionalmodelle — dort, wo das grobe Gitter blind ist.

Die globalen Modelle rechnen auf 7 bis 25 km. Die Ora am Gardasee entsteht in
einem Tal, das an der engsten Stelle 2 km breit ist; der Maestral lebt von
einer Küstenlinie, die auf 25 km zu einer geraden Kante wird. Solche
Zirkulationen fallen durch das Gitter. Regionalmodelle rechnen auf 1 bis 2,5 km
und lösen sie auf.

Open-Meteo bietet mehrere davon kostenlos an. Zwei Dinge machen die Sache
unbequem:

Erstens dokumentiert Open-Meteo nirgends, welches Modell welchen Punkt
abdeckt — in der Doku steht nur „Central Europe" oder „Italy & Southern
Europe". Ob `dwd_icon_d2` den Gardasee einschließt, steht in keiner Tabelle.
Es hilft nur Ausprobieren. Die Rahmen in MODELLE unten sind deshalb bewusst
großzügige Vorauswahlen, keine Wahrheit: sie ersparen sinnlose Versuche, aber
entschieden wird durch die Antwort des Servers.

Zweitens beantwortet Open-Meteo eine Anfrage für einen Punkt außerhalb der
Modelldomain mit HTTP 400 statt mit leeren Werten. Bei einer Sammelanfrage über
zwanzig Koordinaten reißt ein einziger unpassender Punkt alle anderen mit.
Deshalb wird eine abgelehnte Gruppe halbiert und erneut versucht, bis die
Ausreißer feststehen — und das Ergebnis je Spot gemerkt, damit dieser Tanz
einmal und nicht bei jedem Lauf stattfindet.

Was hier NICHT passiert: die Modelle ersetzen die globalen nicht. Sie reichen
zwei bis fünf Tage, die globalen bis sechzehn. Die hochauflösende Reihe
überschreibt nur die Stunden, die sie abdeckt, und der Report sagt, woher der
Wind kommt.
"""
from __future__ import annotations
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from ..i18n import T, TN, N_                                      # noqa: F401
from .netz import lies, cache_lesen, ablegen, USER_AGENT

from .openmeteo import ENDPOINT, TIMEOUT, reihen
from .overpass import passt, stempel

# (Bezeichner, Auflösung km, Kurzname, Reichweite, Heimat)
#
# Reichweite = wie weit das Modell überhaupt antwortet (großzügig geschätzt).
# Heimat     = das Land, für das der Anbieter es baut und gegen dessen
#              Messnetz er es prüft.
#
# Beide Rahmen sind von Hand gesetzt, keine dokumentierten Domains — Open-Meteo
# veröffentlicht keine. Die Reichweite dient nur dazu, sinnlose Anfragen zu
# sparen; entschieden wird durch die Antwort des Servers.
#
# Warum überhaupt zwei Rahmen: der erste Probelauf über Philipps Katalog gab
# dem Gardasee das Schweizer Modell (1 km) und Zeeland das französische
# (1,5 km) — beide antworten dort, weil ihre Domains weit über die Landesgrenze
# reichen. Nur ist ein Modell am Rand seines Gebiets am schwächsten: dort
# fehlen dem Anbieter die Stationen, gegen die er rechnet, und Randartefakte
# sind ein bekanntes Problem (MeteoSwiss beschneidet die eigene Domain aus
# genau dem Grund um 20 km). Deshalb gewinnt jetzt das Modell des Landes, und
# erst danach zählt die feinere Auflösung.
#
# Ein Rechteck kann keiner Landesgrenze folgen. Die Südkante der Schweiz ist
# deshalb bei 46,3° gezogen statt bei den tatsächlichen 45,8°: sonst fiele der
# Nordzipfel des Comer Sees in die Schweizer Heimat, obwohl er in Italien liegt
# und das italienische Modell dort die bessere Auskunft ist. Wer einen Spot im
# Tessin einträgt, bekommt dadurch ICON-2I statt ICON-CH1 — 2 km statt 1, aber
# vom richtigen Anbieter. Aus demselben Grund endet Frankreichs Heimat bei
# 8,3° statt bei den 9,6° Korsikas — sonst hätte das französische Modell den
# Comer See beansprucht. Italiens Nordkante liegt aus demselben Grund bei
# 46,6° und nicht bei den 47,1° des Brenners.
#
# Dass sich Heimatrahmen überlappen, ist unschädlich: wo zwei Modelle daheim
# sind, entscheidet unter ihnen wieder die Auflösung.
MODELLE = [
    # Bezeichner                          km   kurz        Reichweite                  Heimat                    Land
    ("meteoswiss_icon_ch1",              1.0, "CH1",      (45.0, 48.5, 5.0, 11.5),   (46.3, 47.9, 5.9, 10.6),  "CH"),
    ("meteofrance_arome_france_hd",      1.5, "AROME-HD", (41.0, 52.0, -6.0, 10.5),  (41.3, 51.2, -5.2, 8.3),  "FR"),
    ("italia_meteo_arpae_icon_2i",       2.0, "ICON-2I",  (35.0, 48.5, 5.0, 20.0),   (36.0, 46.6, 6.5, 18.6),  "IT"),
    ("dwd_icon_d2",                      2.0, "ICON-D2",  (43.0, 58.0, 0.0, 20.5),   (47.2, 55.1, 5.8, 15.1),  "DE"),
    ("knmi_harmonie_arome_netherlands",  2.0, "HARMONIE", (49.0, 55.5, 1.0, 9.0),    (49.4, 53.6, 2.5, 7.3),   "NL"),
    ("geosphere_arome_austria",          2.5, "AROME-AT", (44.5, 50.0, 8.0, 18.0),   (46.3, 49.1, 9.5, 17.2),  "AT"),
    ("dmi_harmonie_arome_europe",        2.0, "DMI",      (47.0, 65.0, -8.0, 25.0),  (54.5, 57.8, 8.0, 15.2),  "DK"),
]

# Wird die Auswahlregel geändert, ist die gemerkte Zuordnung überholt.
# 3: die Zuordnung trägt die Koordinate, für die sie gilt (1.7.0).
# 4: das Landeskürzel des Spots entscheidet vor dem Heimatrahmen (1.8.1).
#    Fehmarn liegt in beiden Rahmen, dem deutschen und dem dänischen, beide
#    Modelle haben 2 km — und der Prüfstand fand DMI, weil bei Gleichstand
#    das Alphabet entschied. Ein Spot in Deutschland bekommt das deutsche
#    Modell; die Rahmen bleiben für Spots ohne Landeskürzel.
REGEL = 4

# Bewusst wenige Variablen: Open-Meteo zählt eine Anfrage mit mehr als zehn
# Variablen als mehrere Aufrufe. Hier zählt nur der Wind — alles andere kommt
# weiter aus der Hauptabfrage.
HOURLY = ["wind_speed_10m", "wind_gusts_10m", "wind_direction_10m"]
CACHE_NAME = "highres.json"
MAX_TAGE = 3            # weiter reicht keines dieser Modelle verlässlich
GRUPPE = 10             # Koordinaten je Anfrage
# Wie lange „kein Modell deckt diesen Spot“ gilt. Bis 2.1.0 für immer — und
# dafür genügte ein einziges HTTP 400, auch ein vorübergehendes (C26). Danach
# wird neu gefragt; das kostet je Kandidat einen Aufruf, keinen Wind.
ABSAGE_TAGE = 7


class HighresError(RuntimeError):
    pass


def _drin(lat, lon, rahmen) -> bool:
    la0, la1, lo0, lo1 = rahmen
    return la0 <= lat <= la1 and lo0 <= lon <= lo1


def kandidaten(spot: dict) -> list[str]:
    """Modelle für diesen Punkt: erst das des Landes, dann die Nachbarn.

    Drei Gruppen: das Modell des Landes, in dem der Spot laut Katalog liegt;
    dann Modelle, in deren Heimatrahmen er liegt; dann alle anderen in
    Reichweite. Innerhalb jeder Gruppe entscheidet die Auflösung. Ein Modell
    am Rand seines Gebiets ist auch bei feinerem Gitter nicht die bessere
    Auskunft.
    """
    lat, lon = spot["lat"], spot["lon"]
    land = (spot.get("country") or "").upper()
    eigenes, daheim, fremd = [], [], []
    for name, aufl, _kurz, reichweite, heimat, modell_land in MODELLE:
        if not _drin(lat, lon, reichweite):
            continue
        if land and modell_land == land:
            eigenes.append((aufl, name))
        elif _drin(lat, lon, heimat):
            daheim.append((aufl, name))
        else:
            fremd.append((aufl, name))
    return [n for _a, n in sorted(eigenes)] + [n for _a, n in sorted(daheim)] + [n for _a, n in sorted(fremd)]


def kurzname(modell: str) -> str:
    for m, _aufl, kurz, *_ in MODELLE:
        if m == modell:
            return kurz
    return modell


def aufloesung(modell: str) -> float:
    for m, aufl, *_ in MODELLE:
        if m == modell:
            return aufl
    return 0.0


def lade_cache(ordner: str | Path) -> dict:
    return cache_lesen(Path(ordner) / CACHE_NAME, dict) or {}


def sichere_cache(ordner: str | Path, cache: dict) -> None:
    cache = dict(cache, _regel=REGEL)     # damit niemand den Stempel vergisst
    ablegen(Path(ordner) / CACHE_NAME, json.dumps(cache, indent=1, sort_keys=True))


def _absage_gilt(eintrag: dict, heute: str) -> bool:
    """Gilt „kein Modell“ noch? Ein Eintrag ohne Datum (vor 2.1.1) bekommt
    heute seins und gilt ab jetzt `ABSAGE_TAGE` Tage."""
    seit = eintrag.get("seit")
    if not isinstance(seit, str):
        eintrag["seit"] = heute
        return True
    try:
        return (date.fromisoformat(heute) - date.fromisoformat(seit)).days < ABSAGE_TAGE
    except ValueError:
        return False


def _anfrage(modell: str, batch: list[dict], tage: int, timezone: str):
    params = {
        "latitude": ",".join(f"{s['lat']:.4f}" for s in batch),
        "longitude": ",".join(f"{s['lon']:.4f}" for s in batch),
        "hourly": ",".join(HOURLY),
        "models": modell,
        "wind_speed_unit": "kn",
        "timezone": timezone,
        "forecast_days": tage,
        # Im Gebirge verschiebt die Voreinstellung „land" den Punkt auf eine
        # Gitterzelle ähnlicher Höhe — am Seeufer landet man damit leicht am
        # Hang statt auf dem Wasser. Für Talwinde ist die nächste Zelle besser.
        "cell_selection": "nearest",
    }
    url = f"{ENDPOINT}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(lies(resp).decode("utf-8"))
    if isinstance(data, dict) and "hourly" in data:
        return [data]
    if isinstance(data, list):
        return data
    raise HighresError(T("unerwartete Antwort: {antwort}", antwort=str(data)[:100]))


def _teile_und_frage(modell, batch, tage, timezone, log) -> dict:
    """Gruppe abfragen; bei Ablehnung halbieren, bis die Ausreißer feststehen.

    Open-Meteo lehnt eine ganze Sammelanfrage ab, sobald ein Punkt außerhalb
    der Domain liegt. Ohne Halbieren verlöre man neunzehn brauchbare Punkte
    wegen eines unbrauchbaren.
    """
    if not batch:
        return {}
    try:
        blocks = _anfrage(modell, batch, tage, timezone)
    except urllib.error.HTTPError as exc:
        if exc.code != 400:
            raise HighresError(f"{modell}: HTTP {exc.code}") from exc
        if len(batch) == 1:
            return {batch[0]["id"]: None}              # deckt diesen Punkt nicht ab
        mitte = len(batch) // 2
        links = _teile_und_frage(modell, batch[:mitte], tage, timezone, log)
        time.sleep(0.3)
        rechts = _teile_und_frage(modell, batch[mitte:], tage, timezone, log)
        return {**links, **rechts}
    except Exception as exc:                            # noqa: BLE001
        raise HighresError(f"{modell}: {exc}") from exc
    if len(blocks) != len(batch):
        raise HighresError(T("{modell}: {n} Blöcke für {m} Punkte", modell=modell, n=len(blocks), m=len(batch)))
    return {s["id"]: b for s, b in zip(batch, blocks)}


def hole(spots, tage: int, cache_ordner: str | Path, timezone: str | None = None,
         log=None) -> tuple[dict, dict]:
    """({spot_id: (modell, hourly)}, Statistik) — beste verfügbare Auflösung je Spot.

    Der Cache merkt sich je Spot, welches Modell ihn abdeckt (oder dass keines
    es tut). Damit kostet die Suche nach dem ersten Lauf keine zusätzlichen
    Anfragen mehr — nur noch eine je Modell und Gruppe.
    """
    from ..spots import zeitzone
    say = log or (lambda *a: None)
    cache = lade_cache(cache_ordner)
    if cache.get("_regel") != REGEL:
        # Auswahlregel geändert: was gemerkt war, gilt nicht mehr.
        cache = {"_regel": REGEL}
    heute = date.today().isoformat()
    tage = max(1, min(int(tage), MAX_TAGE))
    ergebnis: dict[str, tuple[str, dict]] = {}
    statistik = {"geprueft": 0, "abgedeckt": 0, "modelle": {}}

    # Je Spot das feinste Modell, das laut Cache passt — sonst alle Kandidaten.
    # Gruppiert nach Modell und Zeitzone: eine Abfrage trägt nur eine Zone.
    offen: dict[tuple[str, str], list[dict]] = {}
    for spot in spots:
        eintrag = cache.get(spot["id"])
        eintrag = eintrag if isinstance(eintrag, dict) else {}
        # Eine Zuordnung gilt für die Koordinate, für die sie gefunden wurde.
        # Nach einer Korrektur der Nadel wird neu geprüft, statt mit dem Modell
        # des alten Punkts weiterzurechnen — ohne Stempel ebenfalls.
        if not eintrag.get("bei") or not passt(eintrag["bei"], spot["lat"], spot["lon"]):
            eintrag = {}
        gemerkt = eintrag.get("modell", "unbekannt")
        if gemerkt is None and _absage_gilt(eintrag, heute):
            continue                                    # nichts deckt ihn ab — fürs Erste
        if not isinstance(gemerkt, str) or gemerkt not in {m[0] for m in MODELLE}:
            gemerkt = "unbekannt"                       # abgelaufen, oder Unsinn in der Datei
        liste = [gemerkt] if gemerkt != "unbekannt" else kandidaten(spot)
        if not liste:
            cache[spot["id"]] = {"modell": None, "bei": stempel(spot["lat"], spot["lon"]), "seit": heute}
            continue
        offen.setdefault((liste[0], timezone or zeitzone(spot)), []).append(spot)

    versuche_spaeter: list[dict] = []
    for (modell, tz), gruppe in list(offen.items()):
        for i in range(0, len(gruppe), GRUPPE):
            teil = gruppe[i:i + GRUPPE]
            statistik["geprueft"] += len(teil)
            try:
                antwort = _teile_und_frage(modell, teil, tage, tz, say)
            except HighresError as exc:
                say("    " + T("{modell} nicht abrufbar ({fehler}) — die globalen Modelle bleiben",
                              modell=kurzname(modell), fehler=exc))
                continue
            for spot in teil:
                if spot["id"] not in antwort:
                    continue
                block = antwort[spot["id"]]                 # None: HTTP 400, das Modell deckt ihn nicht
                fein = None
                if block is not None:
                    fein = reihen(block.get("hourly")) if isinstance(block, dict) else None
                    if fein is None:
                        # Eine unlesbare Antwort sagt nichts über die Abdeckung:
                        # nichts gemerkt, beim nächsten Lauf dasselbe Modell.
                        say("    " + T("{modell} nicht abrufbar ({fehler}) — die globalen Modelle bleiben",
                                      modell=kurzname(modell), fehler=T("unerwartete Antwort: {antwort}",
                                                                        antwort=spot.get("name") or spot["id"])))
                        continue
                if fein is not None:
                    ergebnis[spot["id"]] = (modell, fein)
                    cache[spot["id"]] = {"modell": modell, "bei": stempel(spot["lat"], spot["lon"])}
                    statistik["abgedeckt"] += 1
                    statistik["modelle"][kurzname(modell)] = \
                        statistik["modelle"].get(kurzname(modell), 0) + 1
                else:
                    # Dieses Modell nicht — beim nächsten Lauf das nächstgröbere.
                    # Die nach ihm in der Reihe, nicht „alle außer ihm“: so
                    # pendelte ein Spot, den die ersten beiden ablehnen, bis
                    # 2.1.0 ewig zwischen diesen beiden.
                    liste = kandidaten(spot)
                    rest = liste[liste.index(modell) + 1:] if modell in liste else liste
                    bei = stempel(spot["lat"], spot["lon"])
                    if rest:
                        versuche_spaeter.append(spot)
                        cache[spot["id"]] = {"modell": rest[0], "bei": bei}
                    else:
                        cache[spot["id"]] = {"modell": None, "bei": bei, "seit": heute}
            time.sleep(0.3)

    sichere_cache(cache_ordner, cache)
    if versuche_spaeter:
        say("    " + T("{n} Spots: nächstgröberes Modell beim nächsten Lauf", n=len(versuche_spaeter)))
    return ergebnis, statistik


def einsetzen(hourly: dict, fein: dict, kurz: str) -> int:
    """Die feine Windreihe über die grobe legen, Stunde für Stunde.

    Nur dort, wo das feine Modell tatsächlich einen Wert hat — es reicht
    kürzer als die globalen. Rückgabe: wie viele Stunden ersetzt wurden.
    Die grobe Reihe bleibt als eigenes Modell im Vergleich stehen, damit die
    Anzeige „Modelle uneinig" ehrlich bleibt.
    """
    zeiten = {t: i for i, t in enumerate(fein.get("time") or [])}
    ersetzt = 0
    grob_wind = list(hourly.get("wind_speed_10m") or [])
    herkunft = [None] * len(hourly.get("time") or [])
    unterschied = [None] * len(hourly.get("time") or [])
    for i, t in enumerate(hourly.get("time") or []):
        j = zeiten.get(t)
        if j is None:
            continue
        neu = (fein.get("wind_speed_10m") or [None] * (j + 1))[j]
        if neu is None:
            continue
        for feld in ("wind_speed_10m", "wind_gusts_10m", "wind_direction_10m"):
            reihe = fein.get(feld) or []
            if j < len(reihe) and reihe[j] is not None and hourly.get(feld) is not None:
                hourly[feld][i] = reihe[j]
        herkunft[i] = kurz
        # Wie viel das feine Modell gegenüber dem groben ändert. Das ist die
        # eigentliche Auskunft: deckt ein Modell den Punkt nur ab, oder trifft
        # es die Zirkulation auch? Bei der Ora steht hier ein zweistelliges
        # Plus, bei einem flachen Küstenstreifen nahe null.
        alt_wert = grob_wind[i] if i < len(grob_wind) else None
        if alt_wert is not None:
            unterschied[i] = round(neu - alt_wert, 1)
        ersetzt += 1
    if ersetzt:
        hourly.setdefault("wind_models", {})[kurz] = [
            (fein.get("wind_speed_10m") or [None] * len(zeiten))[zeiten[t]]
            if t in zeiten else None for t in hourly.get("time") or []]
        hourly["wind_models"].setdefault("grob", grob_wind)
        hourly["wind_herkunft"] = herkunft
        hourly["wind_unterschied"] = unterschied
    return ersetzt
