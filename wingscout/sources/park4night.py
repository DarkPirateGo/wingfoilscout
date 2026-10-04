"""Stellplätze und Campingplätze rund um einen Spot — Park4Night.

Inoffizielle Schnittstelle, im September 2026 im Browser mitgelesen:

    GET https://park4night.com/api/places/around
        ?lat=..&lng=..&radius=<km>&filter=<json>&lang=de

Die Antwort ist JSON, aber base64-verpackt. Sie kann sich jederzeit ändern oder
verschwinden — deshalb ist ein Ausfall hier nie ein Grund, den Report platzen
zu lassen; dann fehlt eben dieser Abschnitt.

Zwei Dinge, die beim Mitlesen aufgefallen sind und die das Filtern bestimmen:

Erstens greift der serverseitige Filter `{"services":["animaux"]}` nicht sauber
durch — in der Antwort standen auch Plätze ganz ohne Serviceangaben. Für die
Regel „Hund muss erlaubt sein" ist das zu wenig, also wird hier selbst
gefiltert.

Zweitens heißt eine fehlende Angabe zu Tieren NICHT, dass Hunde verboten sind;
meistens hat sie nur niemand eingetragen. Solche Plätze fliegen trotzdem raus,
werden aber gezählt und im Report genannt — sonst wundert man sich, warum an
einem offensichtlich hundefreundlichen Küstenabschnitt nur zwei Plätze stehen.
"""
from __future__ import annotations
import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from ..i18n import T, TD, TN, N_                                  # noqa: F401
from .netz import lies

ENDPOINT = "https://park4night.com/api/places/around"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
TIMEOUT = 30
DOG_SERVICE = "animaux"

# Plätze, an denen man stehen kann. Tagesparkplätze, Picknickplätze und reine
# Ver-/Entsorgungsstellen nützen für eine Übernachtung nichts. Die
# Beschriftung wird in `_tidy` übersetzt.
OVERNIGHT = {
    "PN": (N_("Umgeben von Natur"), 0),
    "F": (N_("Bauernhof / Winzer"), 0),
    "ACC_PR": (N_("Privater Stellplatz"), 0),
    "ACC_G": (N_("Stellplatz, kostenlos"), 1),
    "ACC_P": (N_("Stellplatz, kostenpflichtig"), 1),
    "PSS": (N_("Stellplatz ohne Ver-/Entsorgung"), 1),
    "P": (N_("Parkplatz Tag und Nacht"), 2),
    "EP": (N_("Bei Privatpersonen"), 2),
    "AR": (N_("Rastplatz"), 3),
    "C": (N_("Campingplatz"), 3),
}


class Park4NightError(RuntimeError):
    pass


def _decode(raw: bytes):
    text = raw.decode("utf-8", "replace").strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        return json.loads(base64.b64decode(text).decode("utf-8", "replace"))
    except Exception as exc:                          # noqa: BLE001
        raise Park4NightError(T("Antwort nicht lesbar: {fehler}", fehler=str(exc)[:80])) from exc


def _around(lat: float, lon: float, radius_km: float, lang: str = "de") -> list:
    params = {"lat": f"{lat:.5f}", "lng": f"{lon:.5f}",
              "radius": int(max(1, radius_km)), "filter": "{}", "lang": lang}
    url = f"{ENDPOINT}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://park4night.com/de/search",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = _decode(lies(resp))
    except urllib.error.HTTPError as exc:
        raise Park4NightError(f"HTTP {exc.code}") from exc
    except Exception as exc:                          # noqa: BLE001
        raise Park4NightError(str(exc)) from exc
    if isinstance(data, dict):
        data = data.get("places") or data.get("data") or []
    return data if isinstance(data, list) else []


def _num(value, default: float = 0.0) -> float:
    """Was aus der Fremdantwort in den Report wandert, muss eine Zahl sein."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _tidy(place: dict) -> dict:
    address = place.get("address") or {}
    kind = (place.get("type") or {}).get("code") or ""
    label, rank = OVERNIGHT.get(kind, ("", 9))
    ort = " ".join(x for x in (address.get("zipcode"), address.get("city")) if x)
    name = (place.get("name") or "").strip() or (place.get("title_short") or "").strip()
    # Nicht gespeichert: das Ergebnis geht im selben Lauf in den Report — in
    # alle vier Sprachen (2.3.0), deshalb die eigenen Texte als TD().
    return {
        "id": place.get("id"),
        "name": name or ort or TD("ohne Namen"),
        "ort": ort,
        "land": address.get("country") or "",
        "kind": kind,
        "kind_label": (TD(label) if label else "") or (place.get("type") or {}).get("label") or kind,
        "rank": rank,
        "lat": _num(place.get("lat")),
        "lon": _num(place.get("lng")),
        "km": round(_num(place.get("distance")), 1),
        "rating": _num(place.get("rating")),
        "reviews": int(_num(place.get("review"))),
        "services": [str(x) for x in (place.get("services") or []) if isinstance(x, (str, int))]
                    if isinstance(place.get("services"), list) else [],
        "pro": bool(place.get("isPro")),
        "nature_protect": bool(place.get("nature_protect")),
        # Nur ein Pfad darf an die Domain: `.evil.example/x` ergäbe sonst
        # `https://park4night.com.evil.example/x`, und _safe_url() im Report
        # sieht nur den Anfang.
        "url": ("https://park4night.com" + str(place.get("url"))
                if isinstance(place.get("url"), str) and place["url"].startswith("/") else ""),
    }


def places_for(lat: float, lon: float, cfg_camping: dict, lang: str = "de") -> dict:
    """Passende Plätze um einen Punkt. Rückgabe mit Zählern, was wegfiel."""
    radius = float(cfg_camping.get("max_distance_km", 15))
    min_rating = float(cfg_camping.get("min_rating", 0) or 0)
    dog_required = bool(cfg_camping.get("dog_required", True))
    prefer_small = bool(cfg_camping.get("prefer_small", True))

    raw = _around(lat, lon, radius, lang)
    ohne_hund = zu_weit = falscher_typ = schlecht = 0
    keep = []
    for entry in raw:
        place = _tidy(entry)
        if place["km"] > radius:
            zu_weit += 1
            continue
        if place["rank"] > 3:
            falscher_typ += 1
            continue
        if dog_required and DOG_SERVICE not in place["services"]:
            ohne_hund += 1
            continue
        if min_rating and place["reviews"] >= 2 and place["rating"] < min_rating:
            schlecht += 1
            continue
        keep.append(place)

    def score(p):
        """Alles in „gefühlte Kilometer" umgerechnet, damit sich die Kriterien
        gegeneinander abwägen lassen statt streng nacheinander.

        Ein Bauernhof darf weiter weg liegen als ein großer Campingplatz — aber
        nicht beliebig weit. Ein Rang kostet anderthalb Kilometer, eine gute
        Bewertung bringt bis zu einem Kilometer Vorsprung. Unbewertete Plätze
        gelten als mittelmäßig, nicht als schlecht.
        """
        weit = p["km"]
        if prefer_small:
            weit += 1.5 * p["rank"]
        bewertung = p["rating"] if p["reviews"] else 3.0
        weit -= max(-1.0, min(1.0, (bewertung - 3.5) * 0.7))
        return weit

    keep.sort(key=score)
    for place in keep:
        place["gewichtet_km"] = round(score(place), 1)
    return {
        "places": keep,
        "gesamt": len(raw),
        "ohne_hundeangabe": ohne_hund,
        "zu_weit": zu_weit,
        "falscher_typ": falscher_typ,
        "schlecht_bewertet": schlecht,
    }


def fetch(spots, cfg_camping: dict, lang: str = "de", pause_s: float = 1.0,
          log=None) -> dict:
    """{spot_id: Ergebnis} — ein Aufruf je Spot, mit Pause dazwischen."""
    say = log or (lambda *a: None)
    out = {}
    for i, spot in enumerate(spots):
        try:
            out[spot["id"]] = places_for(spot["lat"], spot["lon"], cfg_camping, lang)
        except Park4NightError as exc:
            say("    " + T("Park4Night für {spot}: {fehler}", spot=spot["name"], fehler=exc))
        except Exception as exc:                      # noqa: BLE001 — inoffizielle Schnittstelle
            # Ein Feld, das anders aussieht als beim Mitlesen, darf nicht den
            # ganzen Lauf beenden: dann fehlt eben dieser Stellplatzblock.
            say("    " + T("Park4Night für {spot}: Antwort nicht lesbar ({art}: {fehler})",
                          spot=spot["name"], art=type(exc).__name__, fehler=exc))
        if i + 1 < len(spots):
            time.sleep(pause_s)
    return out
