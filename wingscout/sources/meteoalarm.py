"""Amtliche Wetterwarnungen für ganz Europa — MeteoAlarm (EUMETNET), CC BY 4.0.

Ein Feed je Land, Atom-Format mit CAP-Feldern:
    https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-{land}

Warum das in ein Spot-Tool gehört: Das Modell kann 30 kn zeigen und der Tag
trotzdem keiner sein — Sturmwarnung, Gewitterlinie, Starkregen. Wer Gruppen
führt, prüft die amtliche Warnlage, bevor er den Bus belädt. Hier wird sie
je Land geholt, eine Stunde zwischengespeichert und den Spots nach Gebiet
zugeordnet.

Das Parsen ist bewusst tolerant: Feeds ändern sich, und lieber eine Warnung
ohne Detail als ein Absturz beim Planen.
"""
from __future__ import annotations
import json
import re
import time
import urllib.request
from pathlib import Path

from .. import xmlsicher
from ..i18n import T, TN, N_                                      # noqa: F401
from .netz import lies, cache_lesen, ablegen, USER_AGENT          # noqa: F401 — USER_AGENT gehört zur Schnittstelle

from .. import CACHE

FEED = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-{country}"
COUNTRY_SLUG = {
    "DE": "germany", "NL": "netherlands", "FR": "france", "IT": "italy", "DK": "denmark",
    "CH": "switzerland", "AT": "austria", "BE": "belgium", "ES": "spain", "PT": "portugal",
    "HR": "croatia", "GR": "greece", "PL": "poland", "SE": "sweden", "NO": "norway",
}
# Die Warnungen liegen eine Stunde im Cache (cache/alerts/*.json): Stufenname
# und Ersatz-Ereignis bleiben deutsch, übersetzt wird beim Anzeigen mit T().
LEVEL_NAME = {2: N_("gelb"), 3: N_("orange"), 4: N_("rot")}
CACHE_TTL_S = 3600
EINTRAG_FELDER = ("title", "areaDesc", "event", "severity", "effective", "onset", "expires")


def _name(el) -> str:
    """Der Name ohne Namensraum."""
    return el.tag.split("}")[-1] if isinstance(el.tag, str) else ""


def _gang(wurzel, stopp: str):
    """Die Elemente unter `wurzel` in Dokumentreihenfolge, wie `iter()` —
    nur ohne in Elemente namens `stopp` hinabzusteigen (sie selbst kommen
    noch vor)."""
    stapel = [iter(wurzel)]
    while stapel:
        kind = next(stapel[-1], None)
        if kind is None:
            stapel.pop()
            continue
        yield kind
        if _name(kind) != stopp:
            stapel.append(iter(kind))


def _texte(wurzel, namen, stopp: str) -> tuple[dict, list]:
    """Ein Gang durch den Teilbaum: je Name der erste Text (unabhängig vom
    Namensraum, in Dokumentreihenfolge), dazu die `parameter`-Elemente darin.

    Bis 2.1.0 suchte jedes Feld und jeder Parameter mit `iter()` im ganzen
    Teilbaum — bei ineinander geschachtelten Einträgen wuchs die Arbeit mit
    der Tiefe mal der Größe; selbst unter der Tiefengrenze von `xmlsicher`
    kostete ein Feed von 236 KB sechs Sekunden (C10). Jetzt ist jedes Element
    einmal dran: im Eintrag, in dem es steht, und im Parameter, in dem es
    steht."""
    texte, parameter = {}, []
    for el in _gang(wurzel, stopp):
        n = _name(el)
        if n == "parameter":
            parameter.append(el)
        if n in namen and n not in texte and el.text:
            texte[n] = el.text.strip()
    return texte, parameter


def parse_feed(xml_text: str) -> list[dict]:
    """Atom-Einträge → Liste von Warnungen mit Level, Ereignis, Gebiet, Zeitraum."""
    out = []
    # Ohne DOCTYPE und Entitäten — derselbe Schutz wie im Dateiimport
    # (Review 25.09.2026, S5); ein manipulierter Feed darf nicht mehr kosten
    # als eine leere Warnliste.
    root = xmlsicher.lesen(xml_text)
    if root is None:
        return out
    for entry in root.iter():
        if _name(entry) != "entry":
            continue
        felder, parameter = _texte(entry, EINTRAG_FELDER, "entry")
        title = felder.get("title", "")
        area = felder.get("areaDesc", "") or title
        event = felder.get("event", "")
        level, kind = 0, ""
        # CAP-Parameter: valueName awareness_level → "3; orange; Severe"
        for param in parameter:
            werte, _ = _texte(param, ("valueName", "value"), "parameter")
            name = werte.get("valueName", "").lower()
            value = werte.get("value", "")
            if name == "awareness_level":
                m = re.match(r"\s*(\d)", value)
                level = int(m.group(1)) if m else 0
            elif name == "awareness_type":
                kind = re.sub(r"^\d+;\s*", "", value)
        if not level:                      # aktuelle Feeds: Farbe im Titel, Stufe in cap:severity
            colour = {"yellow": 2, "orange": 3, "red": 4, "gelb": 2}
            sev = {"moderate": 2, "severe": 3, "extreme": 4}
            low = title.lower()
            level = next((v for k, v in colour.items() if k in low), 0) or \
                    sev.get(felder.get("severity", "").lower(), 0)
            m = re.search(r"(?:level|stufe)\s*:?\s*(\d)", title, re.I)
            level = int(m.group(1)) if m else level
        out.append({
            "title": title, "event": event or kind or N_("Warnung"), "area": area,
            "level": level, "level_name": LEVEL_NAME.get(level, "info"),
            "from": felder.get("effective", "") or felder.get("onset", ""),
            "until": felder.get("expires", ""),
        })
    return out


def fetch_country(country: str, cache_dir: str | Path = CACHE / "alerts") -> list[dict]:
    slug = COUNTRY_SLUG.get(country.upper())
    if not slug:
        return []
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"{slug}.json"
    try:
        frisch = time.time() - cache.stat().st_mtime < CACHE_TTL_S
    except OSError:
        frisch = False
    gemerkt = _gemerkt(cache)
    if frisch and gemerkt is not None:
        return gemerkt
    req = urllib.request.Request(FEED.format(country=slug), headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            alerts = parse_feed(lies(resp).decode("utf-8", "replace"))
    except Exception:                                  # noqa: BLE001 — Warnungen sind Zusatz, kein Muss
        # Der alte Stand, wenn er lesbar ist — bis 2.1.0 warf eine kaputte
        # Datei hier, mitten in der Ausnahmebehandlung (C14).
        return gemerkt or []
    ablegen(cache, json.dumps(alerts, ensure_ascii=False))
    return alerts


def _gemerkt(pfad: Path) -> list | None:
    """Die gemerkten Warnungen — nur, was `alerts_for` lesen kann."""
    daten = cache_lesen(pfad, list)
    if daten is None:
        return None
    return [a for a in daten if isinstance(a, dict) and isinstance(a.get("level"), int)
            and isinstance(a.get("area"), str)]


def alerts_for(spots, min_level: int = 2, cache_dir=CACHE / "alerts",
               landesweit: dict | None = None) -> dict:
    """{spot_id: [warnungen]} — nach Land geholt, nach Gebiet zugeordnet.

    Nur Spots mit `region` bekommen Warnungen, und nur die, deren Gebiet den
    Regionsnamen enthält. Bis 1.6.1 bekam ein Spot ohne `region` alle
    Warnungen seines Landes — im Lauf vom 16.09. stand „Gewitter · Bornholm“
    an dreizehn dänischen Spots an der Nordsee und „Kreis Plön“ an neun
    deutschen. Das war Rauschen, in dem die echte Warnung unterging. Was ohne
    Gebiet bleibt, wird in `landesweit` je Land gesammelt, damit der Report es
    einmal sagen kann statt an jedem Spot.
    """
    by_country: dict[str, list[dict]] = {}
    for spot in spots:
        c = (spot.get("country") or "").upper()
        if c and c not in by_country and c in COUNTRY_SLUG:
            by_country[c] = [a for a in fetch_country(c, cache_dir) if a["level"] >= min_level]
    out = {}
    ohne_gebiet: set[str] = set()
    for spot in spots:
        land = (spot.get("country") or "").upper()
        alerts = by_country.get(land, [])
        region = (spot.get("region") or "").lower()
        if not region:
            if alerts:
                ohne_gebiet.add(land)
            continue
        hits = [a for a in alerts if region in (a["area"] or "").lower()]
        if hits:
            out[spot["id"]] = hits[:6]
    if landesweit is not None:
        for land in sorted(ohne_gebiet):
            landesweit[land] = by_country[land]
    return out
