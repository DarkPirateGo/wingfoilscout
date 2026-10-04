"""Spot-Katalog laden, filtern, Fahrzeit anhängen."""
from __future__ import annotations
import math
import re
from pathlib import Path

from .config import yaml_laden, yaml_meldung, YAML_FEHLER
from .geo import haversine_km, drive_estimate_h
from .i18n import T, TD, meldungswert

QUALITY_ORDER = {"best": 3, "good": 2, "ok": 1, "bad": 0}

# Zeitzone aus dem Landeskürzel. Bis 1.6.1 wurde alles in Europe/Berlin
# abgefragt — für Griechenland und Portugal standen die Uhrzeiten im Report
# damit eine Stunde neben der Ortszeit, und das Thermikfenster aus dem
# Katalog (gemeint als Ortszeit) griff versetzt. Alles, was hier nicht steht,
# ist Mitteleuropa. Die Kanaren und die Azoren liegen in ihrem Land eine
# Zone weiter westlich; das entscheidet die Länge.
ZEITZONE = {
    "GR": "Europe/Athens", "FI": "Europe/Helsinki", "RO": "Europe/Bucharest", "BG": "Europe/Sofia",
    "EE": "Europe/Tallinn", "LV": "Europe/Riga", "LT": "Europe/Vilnius", "CY": "Asia/Nicosia",
    "TR": "Europe/Istanbul",
    "PT": "Europe/Lisbon", "GB": "Europe/London", "IE": "Europe/Dublin", "IS": "Atlantic/Reykjavik",
    "MA": "Africa/Casablanca", "AG": "America/Antigua",
}


def zeitzone(spot: dict) -> str:
    land = (spot.get("country") or "").upper()
    lon = float(spot.get("lon") or 0.0)
    if land == "ES" and lon < -12:
        return "Atlantic/Canary"
    if land == "PT" and lon < -20:
        return "Atlantic/Azores"
    return ZEITZONE.get(land, "Europe/Berlin")


def nach_zeitzone(spots, vorgabe: str | None = None) -> list[tuple[str, list]]:
    """[(Zeitzone, Spots)] — eine Abfrage kann nur eine Zone tragen."""
    if vorgabe:
        return [(vorgabe, list(spots))]
    gruppen: dict[str, list] = {}
    for spot in spots:
        gruppen.setdefault(zeitzone(spot), []).append(spot)
    return list(gruppen.items())


class KatalogFehler(ValueError):
    """`spots.yaml` ist nicht lesbar oder widerspricht sich.

    Bis 1.6.0 warf `load_spots` hier `SystemExit`. Auf der Kommandozeile ist
    das dasselbe — Meldung, Ende. In der Oberfläche war es ein stiller Tod:
    `SystemExit` ist keine `Exception`, die Worker fingen sie nicht, der
    Thread verschwand, und `JOB` stand bis zum Neustart auf „läuft“. Ein
    Katalogfehler ist ein Wert-Fehler; was daraus wird, entscheidet der
    Aufrufer.
    """


SHOREBREAK_STATUS = ("yes", "possible", "no", "unknown")


def shorebreak_normieren(wert):
    """`shorebreak:` als Wort oder als Block — zurück kommt immer ein Block
    `{status, note, source}`, oder None, wenn nichts eingetragen ist.

    Das Feld ist reine Information: es filtert nicht und geht nicht in den
    Score. Es steht im Report, im Karten-Popup und im Katalog, damit man vor
    der Fahrt weiß, dass die Welle hier direkt am Ufer bricht und Ein- und
    Ausstieg Übung brauchen.

    YAML 1.1 liest ein nacktes `yes` als True und `no` als False — dieselbe
    Falle wie bei `dogs`. Wahrheitswerte werden hier zurückübersetzt, damit
    der Eintrag nicht stumm verschwindet; der Katalogtest mahnt trotzdem
    Anführungszeichen an. Ein unbekannter Status bleibt stehen, damit der
    Katalogtest ihn nennen kann; Report und Karte zeigen dann nichts.
    """
    if wert is None or wert == "":
        return None
    block = dict(wert) if isinstance(wert, dict) else {"status": wert}
    status = block.get("status")
    if status is True:
        status = "yes"
    elif status is False:
        status = "no"
    block["status"] = str(status if status is not None else "unknown").strip().lower()
    block["note"] = str(block.get("note") or "").strip()
    block["source"] = str(block.get("source") or "").strip()
    return block


TIDE_FAHRBAR = ("hochwasser", "niedrigwasser", "auflaufend", "ablaufend")


def tide_normieren(wert):
    """`tide:` — das Tidenfenster eines Spots — als Block `{fahrbar, stunden}`,
    oder None, wenn nichts eingetragen ist.

    `fahrbar` sagt, wann der Spot geht: `hochwasser` oder `niedrigwasser`
    (± `stunden` um den Scheitel, Standard 2) oder `auflaufend` / `ablaufend`
    (die ganze Halbtide). Stunden außerhalb fallen in der Bewertung mit Veto
    heraus. Ein unbekanntes Wort bleibt stehen, damit der Katalogtest es
    nennen kann; die Bewertung ignoriert das Fenster dann.

    Ob die Tide am Spot überhaupt gilt, entscheidet daneben `tidal:` —
    true, false oder weglassen für die Automatik (siehe wingscout/tide.py).
    """
    if wert is None or wert == "":
        return None
    block = dict(wert) if isinstance(wert, dict) else {"fahrbar": wert}
    block["fahrbar"] = str(block.get("fahrbar") or "").strip().lower()
    try:
        block["stunden"] = float(block.get("stunden") or 2)
    except (TypeError, ValueError):
        block["stunden"] = 2.0
    return block


SEKTOR_WASSER = ("flat", "chop", "wave")
SEKTOR_GUETE = ("best", "good", "ok", "bad")


def sektoren_normieren(spot_id: str, wert) -> list:
    """`sectors:` als Liste von Blöcken `{from, to, quality, water}` mit festem
    Wortschatz — oder `KatalogFehler`, der Spot und Feld nennt.

    Bis 1.18.3 kam `water` ungeprüft bis in den Report und stand dort in
    Klasse und Text (Review 25.09., S1): ein Wert wie `chop'><img …>` war
    echtes Markup. Der Report läuft unter der Herkunft der Oberfläche; der
    Katalog ist als geteilte Datei gedacht. Deshalb hier eine feste Liste,
    und `_esc` im Report obendrein.
    """
    if wert is None:
        return []
    if not isinstance(wert, list):
        raise KatalogFehler(T("{spot}: sectors muss eine Liste sein", spot=spot_id))
    aus = []
    for sec in wert:
        if not isinstance(sec, dict):
            raise KatalogFehler(T("{spot}: Sektor ist kein Block: {wert}", spot=spot_id, wert=repr(str(sec)[:40])))
        block = dict(sec)
        for key in ("from", "to"):
            v = block.get(key)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= float(v) <= 360:
                raise KatalogFehler(T("{spot}: Sektor {feld} muss eine Gradzahl 0–360 sein, nicht {wert}",
                                      spot=spot_id, feld=key, wert=repr(v)))
        block["quality"] = str(block.get("quality") or "ok").strip().lower()
        if block["quality"] not in SEKTOR_GUETE:
            raise KatalogFehler(T("{spot}: Sektor quality {wert} — erlaubt: {erlaubt}", spot=spot_id,
                                  wert=repr(block["quality"]), erlaubt=", ".join(SEKTOR_GUETE)))
        block["water"] = str(block.get("water") or "chop").strip().lower()
        if block["water"] not in SEKTOR_WASSER:
            raise KatalogFehler(T("{spot}: Sektor water {wert} — erlaubt: {erlaubt}", spot=spot_id,
                                  wert=repr(block["water"]), erlaubt=", ".join(SEKTOR_WASSER)))
        aus.append(block)
    return aus


def koordinate_pruefen(spot_id: str, entry: dict) -> None:
    """`lat`/`lon` müssen endliche Zahlen im Bereich sein. `nan` aus einer
    Importdatei blieb bis 1.18.3 im Katalog, überstand jeden Filter (jeder
    Vergleich mit NaN ist False) und ging als `latitude=nan` an Open-Meteo,
    das dann das ganze Paket von 20 Spots verwarf (Review 25.09., S7)."""
    for key, grenze in (("lat", 90.0), ("lon", 180.0)):
        v = entry.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise KatalogFehler(T("{spot}: {feld} muss eine Zahl sein, nicht {wert}",
                                  spot=spot_id, feld=key, wert=repr(v)))
        try:
            endlich = math.isfinite(float(v))
        except OverflowError:            # eine ganze Zahl mit Hunderten Stellen (Python 3.9.6 liest sie)
            endlich = False
        if not endlich or abs(float(v)) > grenze:
            try:
                wert = repr(v)
            except ValueError:           # ab Python 3.11: zu viele Stellen für einen Text
                wert = "…"
            raise KatalogFehler(T("{spot}: {feld} = {wert} liegt außerhalb von ±{grenze}",
                                  spot=spot_id, feld=key, wert=wert, grenze=f"{grenze:.0f}"))


# Felder, die als Text gelesen, gekürzt, verglichen oder angezeigt werden. Ein
# nacktes `no` (YAML 1.1: False) oder eine Zahl bleibt, was es bis 2.1.0 war;
# eine Liste oder ein Block dagegen ist kein Text — `str()` darauf schrieb
# ihn als „[…]“ ab oder lief bei einer Verweis-Bombe in den Speicher
# (Review 04.10.2026, C3).
TEXTFELDER = ("notes", "comment", "region", "country", "source", "source2", "access", "dogs",
              "popularity", "water_body", "seagrass", "shallow")


def textfelder_pruefen(spot_id: str, entry: dict) -> None:
    """Textfelder sind Text (oder ein einfacher Wert), und jeder Text im
    Eintrag lässt sich als UTF-8 schreiben.

    Ein einzelnes Surrogat (`"\\uD800"` in Anführungszeichen) liest YAML
    klaglos; bis 2.1.0 kam es so aus einer GeoJSON-Datei in den Katalog, und
    danach scheiterte jede Seite und jede Suche, die den Namen schreiben
    wollte, mit UnicodeEncodeError (Review 04.10.2026, C2). Hier fällt es
    beim Laden auf, mit Spot und Feld.
    """
    def einfach(wert) -> bool:
        return wert is None or isinstance(wert, (str, bool, int, float))

    pruefen = [(feld, entry.get(feld)) for feld in TEXTFELDER]
    # Die Blöcke, die load_spots selbst mit str() normiert
    for block, felder in (("shorebreak", ("status", "note", "source")), ("tide", ("fahrbar",))):
        wert = entry.get(block)
        if isinstance(wert, dict):
            pruefen += [(f"{block}.{feld}", wert.get(feld)) for feld in felder]
        else:
            pruefen.append((block, wert))
    for feld, wert in pruefen:
        if not einfach(wert):
            raise KatalogFehler(T("{spot}: {feld} muss ein Text sein, nicht {wert}",
                                  spot=spot_id, feld=feld, wert=repr(wert)[:60]))
    # Ohne Rekursion: die Tiefe kommt aus der Datei.
    offen = [(str(k), k) for k in entry] + [(str(k), v) for k, v in entry.items()]
    while offen:
        feld, wert = offen.pop()
        if isinstance(wert, str):
            try:
                wert.encode("utf-8")
            except UnicodeEncodeError:
                raise KatalogFehler(T("{spot}: {feld} enthält ungültige Zeichen", spot=spot_id,
                                      feld=feld.encode("utf-8", "replace").decode("utf-8"))) from None
        elif isinstance(wert, dict):
            offen.extend((feld, x) for paar in wert.items() for x in paar)
        elif isinstance(wert, (list, tuple)):
            offen.extend((feld, x) for x in wert)


class Spot(dict):
    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc


def load_spots(path: str | Path) -> list[Spot]:
    path = Path(path)
    if not path.exists():
        raise KatalogFehler(T("Spot-Katalog nicht gefunden: {pfad}", pfad=path))
    try:
        with path.open(encoding="utf-8") as fh:
            # Ohne Verweise (`*name`) — sonst wie safe_load (siehe config.py)
            raw = yaml_laden(fh) or []
    except YAML_FEHLER as exc:
        # ReaderError, ScannerError, ParserError sind kein ValueError — bis
        # 1.18.3 flogen sie roh durch jede Seite (Review 25.09., S4/U1).
        # Mit Zeile, damit man weiß, wo man hinschauen muss.
        raise KatalogFehler(yaml_meldung(exc, path.name)) from exc
    spots = []
    seen = set()
    if not isinstance(raw, list):
        raise KatalogFehler(T("Spot-Katalog muss eine Liste sein: {pfad}", pfad=path))
    for entry in raw:
        if not isinstance(entry, dict):
            raise KatalogFehler(T("Eintrag ist kein Spot: {eintrag}", eintrag=repr(str(entry)[:60])))
        for key in ("id", "name", "lat", "lon"):
            if key not in entry:
                # Name oder Eintrag kommen aus der Datei: auf einer Zeile, ohne
                # Steuerzeichen und Surrogate, gekürzt (meldungswert, C2)
                raise KatalogFehler(T("Spot ohne '{feld}': {spot}", feld=key,
                                      spot=meldungswert(entry.get("name", entry))))
        # Erst die Form, dann das Doppelte: eine ID wie `[a]` ist nicht
        # hashbar, und `in seen` warf bis 2.1.0 einen TypeError.
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", str(entry["id"])):
            raise KatalogFehler(T("Ungültige Spot-ID (nur Buchstaben, Ziffern, - und _): {id}",
                                  id=repr(entry["id"])))
        if entry["id"] in seen:
            raise KatalogFehler(T("Doppelte Spot-ID: {id}", id=entry["id"]))
        seen.add(entry["id"])
        if not isinstance(entry["name"], str) or not entry["name"].strip():
            raise KatalogFehler(T("{spot}: name muss ein Text sein, nicht {wert}",
                                  spot=entry["id"], wert=repr(entry["name"])))
        textfelder_pruefen(str(entry["id"]), entry)
        koordinate_pruefen(str(entry["id"]), entry)
        entry["sectors"] = sektoren_normieren(str(entry["id"]), entry.get("sectors"))
        entry.setdefault("seagrass", "none")
        entry.setdefault("shallow", "none")
        entry.setdefault("season", list(range(1, 13)))
        entry.setdefault("notes", "")
        entry.setdefault("verified", False)
        # geo_ok: „die Ufergeometrie sieht komisch aus, ich habe nachgesehen,
        # sie stimmt trotzdem" — setzt die Prüfseite, damit ein Spot nicht bei
        # jedem Lauf wieder in der Fundliste steht.
        entry.setdefault("geo_ok", False)
        # `comment`: der eigene Kommentar zum Spot — was man dort erlebt hat,
        # was man beim nächsten Mal wissen will. Frei, mehrzeilig, von jeder
        # Seite aus zu schreiben; `notes` bleibt die Beschreibung des Katalogs.
        entry["comment"] = str(entry.get("comment") or "").strip()
        shorebreak = shorebreak_normieren(entry.get("shorebreak"))
        if shorebreak:
            entry["shorebreak"] = shorebreak
        else:
            entry.pop("shorebreak", None)
        tide = tide_normieren(entry.get("tide"))
        if tide:
            entry["tide"] = tide
        else:
            entry.pop("tide", None)
        spots.append(Spot(entry))
    return spots


def eligible(spots: list[Spot], cfg, month, radius_km: float | None = None,
             max_drive_h: float | None = None) -> tuple[list[Spot], list[tuple[Spot, str]]]:
    """Trennt fahrbare Spots von ausgeschlossenen (mit Begründung).

    `month` ist ein Monat oder eine Menge von Monaten — der Zeitraum einer
    Suche kann über den Monatswechsel reichen, und ein Spot mit Saison im
    Oktober soll am 30. September nicht fehlen.
    """
    monate = {int(month)} if isinstance(month, int) else {int(m) for m in month}
    home = cfg["rider"]["home"]
    drive_cfg = cfg["drive"]
    water_cfg = cfg["water"]
    rules = cfg.get("rules") or {}
    keep, dropped = [], []

    allowed = water_cfg.get("include_types")
    grass_rank = {"none": 0, "some": 1, "heavy": 2}
    grass_limit = grass_rank.get(water_cfg.get("exclude_seagrass", "heavy"), 2)

    for spot in spots:
        spot["dist_km"] = haversine_km(home["lat"], home["lon"], spot["lat"], spot["lon"])
        spot["road_km"] = spot["dist_km"] * drive_cfg["detour_factor"]
        spot["drive_h"] = drive_estimate_h(
            spot["dist_km"], drive_cfg["avg_speed_kmh"], drive_cfg["detour_factor"]
        )
        # Die Gründe sind Anzeigetext (Report: „Nicht berücksichtigt“, Karte)
        # und werden nirgends verglichen — deshalb gleich übersetzt, als TD():
        # der Report setzt sie seit 2.3.0 für jede seiner vier Sprachen neu.
        if spot.get("reference_only"):
            dropped.append((spot, TD("nur Referenzspot, außerhalb des Suchradius")))
            continue
        if spot.get("disabled"):
            dropped.append((spot, TD("im Katalog deaktiviert")))
            continue
        wb = spot.get("water_body")
        # „unknown" kommt durch: wo die Gewässerart nicht feststeht, soll der
        # Spot nicht stillschweigend aus jeder Suche fallen. Die Ufergeometrie
        # sagt später, worin er liegt.
        if allowed and wb and wb != "unknown" and wb not in allowed:
            dropped.append((spot, TD("Gewässertyp {typ} ist in der Konfiguration ausgeschlossen", typ=wb)))
            continue
        if grass_rank.get(spot["seagrass"], 0) >= grass_limit:
            dropped.append((spot, TD("Seegras: {wert}", wert=spot["seagrass"])))
            continue
        if water_cfg.get("exclude_shallow") and spot["shallow"] == "widespread":
            dropped.append((spot, TD("durchgehender Stehbereich")))
            continue
        # Hunde- und Zugangsregeln filtern nur, wenn ausdrücklich gewünscht.
        # Sonst werden solche Spots angezeigt und im Report gekennzeichnet —
        # die Entscheidung, ob ein Platz mit Hundeverbot trotzdem taugt, trifft
        # niemand besser als der Fahrer selbst.
        if rules.get("require_dogs") and spot.get("dogs") == "no":
            dropped.append((spot, TD("Hunde am Spot verboten")))
            continue
        if rules.get("exclude_forbidden") and spot.get("access") == "verboten":
            dropped.append((spot, TD("Wingfoilen dort nicht erlaubt")))
            continue
        if not (monate & {int(m) for m in spot["season"]}):
            dropped.append((spot, TD("außerhalb der Saison")))
            continue
        # Dieselben zwei Sätze wie in cli.refine_drives.
        if radius_km is not None and spot["road_km"] > radius_km:
            dropped.append((spot, TD("{km} km — außerhalb des Radius von {radius} km",
                                    km=f"{spot['road_km']:.0f}", radius=f"{radius_km:.0f}")))
            continue
        limit = max_drive_h if max_drive_h is not None else drive_cfg["max_hours"]
        if spot["drive_h"] > limit:
            dropped.append((spot, TD("{h} h Fahrt über der Obergrenze von {grenze} h",
                                    h=f"{spot['drive_h']:.1f}", grenze=f"{limit:.1f}")))
            continue
        keep.append(spot)
    keep.sort(key=lambda s: s["drive_h"])
    return keep, dropped
