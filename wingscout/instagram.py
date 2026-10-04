"""Instagram je Spot: Absprünge und die Funde einer Suche.

Ob an einem Spot je etwas gepostet wurde, lässt sich nicht automatisch
prüfen: Instagram hat keine öffentliche Suche ohne Anmeldung und keine freie
Schnittstelle, die diese Frage beantwortet — und die Seiten abzugrasen
verbieten die Nutzungsbedingungen. Was geht, sind zwei Dinge:

* **Links, die die Frage mit einem Klick beantworten** — der Ort oder
  Hashtag auf Instagram selbst (im eigenen, angemeldeten Browser) und eine
  Google-Suche auf instagram.com mit Spotname und „wingfoil", die auch ohne
  Anmeldung zeigt, ob es Posts gibt.
* **Eine Momentaufnahme** solcher Suchen in `instagram.json`: je Spot die
  Instagram-Ortsseite (alle dort markierten Posts) und bis zu fünf Treffer.
  Titel und Adressen sind die Suchtreffer, unverändert — kein Beleg, dass
  dort gewingt wird, nur ein Hinweis, wo man nachsieht. Die Datei ist
  Daten, kein Katalog: löschen kostet nichts als die Funde.

Im Katalog darf `instagram:` stehen — ein Hashtag (mit oder ohne `#`) oder
eine ganze Adresse, etwa die Ortsseite oder ein Profil, das man selbst
gefunden hat. Der Katalog gewinnt gegen die Momentaufnahme.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from urllib.parse import quote

from . import ROOT
from .i18n import T, N_

DATEI = ROOT / "instagram.json"

_geladen: dict = {"pfad": None, "mtime": None, "daten": {}}


def lade(pfad: str | Path | None = None) -> dict:
    """Die Momentaufnahme — `{"stand": …, "spots": {id: {...}}}` oder leer.

    Wird bei jedem Aufruf gegen die Änderungszeit geprüft, damit die laufende
    Oberfläche eine neue Datei sieht, ohne dass man sie neu startet.
    """
    pfad = Path(pfad) if pfad else DATEI
    try:
        mtime = pfad.stat().st_mtime
    except OSError:
        return {}
    if _geladen["pfad"] == pfad and _geladen["mtime"] == mtime:
        return _geladen["daten"]
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        if not isinstance(daten, dict) or not isinstance(daten.get("spots"), dict):
            daten = {}
    except (OSError, ValueError):
        daten = {}
    _geladen.update(pfad=pfad, mtime=mtime, daten=daten)
    return daten


def _sicher(url) -> str:
    """Nur https-Adressen auf instagram.com — alles andere wird leer.

    Die Adressen stammen aus Suchtreffern und aus dem Katalog; stünde dort
    `javascript:` statt `https:`, würde ein Klick im Report Code ausführen.
    """
    url = str(url or "").strip()
    return url if re.match(r"^https://(www\.)?instagram\.com/", url) else ""


def tag(spot) -> str:
    """Der Hashtag, unter dem man den Spot auf Instagram sucht.

    Steht `instagram:` im Katalog, gilt der Eintrag (mit oder ohne `#`).
    Sonst wird der Name zum Tag: Kleinbuchstaben, Umlaute aufgelöst, alles
    andere weg — aus „Brouwersdam" wird `brouwersdam`, aus „St. Peter-Ording"
    `stpeterording`. Das trifft den gebräuchlichen Tag oft, nicht immer.
    """
    eigen = str(spot.get("instagram") or "").strip()
    if eigen and not eigen.startswith(("https://", "http://")):
        # Ein Hashtag besteht aus Buchstaben, Ziffern und Unterstrich — mehr
        # lässt Instagram nicht zu, und mehr soll auch nicht in die Adresse.
        return "".join(c for c in eigen.lstrip("#") if c.isalnum() or c == "_")[:60]
    name = str(spot.get("name") or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("é", "e"), ("è", "e"),
                 ("ê", "e"), ("à", "a"), ("â", "a"), ("ô", "o"), ("î", "i"), ("ç", "c"), ("ñ", "n"),
                 ("ø", "o"), ("å", "a"), ("æ", "ae")):
        name = name.replace(a, b)
    return "".join(c for c in name if c.isascii() and c.isalnum())[:30]


def funde(spot, daten: dict | None = None) -> dict:
    """Was die Momentaufnahme zu diesem Spot weiß — `{}` wenn nichts.

    `ort` ist die Ortsseite, `funde` die Treffer `[{"titel", "url"}]`,
    `urteil` eines von wing / kite_surf / treffer / keine / offen, `stand`
    das Datum der Suche.
    """
    daten = lade() if daten is None else daten
    eintrag = (daten.get("spots") or {}).get(spot.get("id"))
    if not isinstance(eintrag, dict):
        return {}
    aus = {"stand": str(daten.get("stand") or ""), "urteil": str(eintrag.get("urteil") or "")}
    ort = _sicher(eintrag.get("ort"))
    if ort:
        aus["ort"] = ort
        aus["ort_titel"] = str(eintrag.get("ort_titel") or "")
    aus["funde"] = [{"titel": str(f.get("titel") or ""), "url": _sicher(f.get("url"))}
                    for f in (eintrag.get("funde") or []) if isinstance(f, dict) and _sicher(f.get("url"))]
    return aus


def links(spot, daten: dict | None = None) -> list[tuple[str, str]]:
    """[(Beschriftung, Adresse)] — die Absprünge zu Instagram je Spot.

    Reihenfolge der ersten Adresse: eigene Adresse aus dem Katalog, sonst
    die Ortsseite aus der Momentaufnahme, sonst der Hashtag. Dazu immer die
    Google-Suche auf instagram.com, die auch ohne Anmeldung etwas zeigt.
    """
    eigen = str(spot.get("instagram") or "").strip()
    erster = ""
    if eigen.startswith(("https://", "http://")):
        erster = _sicher(eigen)
    if not erster:
        erster = funde(spot, daten).get("ort", "")
    if not erster:
        t = tag(spot)
        erster = f"https://www.instagram.com/explore/tags/{quote(t, safe='')}/" if t else ""
    suche = "https://www.google.com/search?q=" + quote(f'site:instagram.com "{spot.get("name", "")}" wingfoil', safe="")
    # Die Beschriftungen sind zugleich Schlüssel (webui → katalog.js liest
    # `ig["Insta-Suche"]`, die Karte `ig["Instagram"]`) und bleiben deutsch;
    # übersetzt wird beim Anzeigen mit T(text). „Instagram“ ist ein Name.
    aus = [("Instagram", erster)] if erster else []
    aus.append((N_("Insta-Suche"), suche))
    return aus


def beschriftung(url: str, titel: str = "") -> str:
    """Kurzer Name für einen Fund, aus der Adresse: `@konto`, `@konto (Reel)`,
    `Beitrag`, `#tag` — und für eine Ortsseite ihr Titel, weil drei Mal „Ort"
    nebeneinander nichts sagt. Der volle Titel steht als Tooltip.

    Reiner Anzeigetext (Report, Katalogseite) — deshalb gleich übersetzt."""
    pfad = re.sub(r"^https?://(www\.)?instagram\.com/", "", url).strip("/")
    teile = pfad.split("/")
    if not teile or not teile[0]:
        return "Instagram"
    if teile[0] == "explore":
        if len(teile) >= 2 and teile[1] == "locations":
            titel = str(titel or "").strip()
            return (T("Ort: {titel}", titel=f"{titel[:32]}{'…' if len(titel) > 32 else ''}")
                    if titel else T("Ort"))
        if len(teile) >= 3 and teile[1] == "tags":
            return "#" + teile[2]
        return "Instagram"
    if teile[0] in ("p", "reel", "reels"):
        return T("Reel") if teile[0] != "p" else T("Beitrag")
    konto = "@" + teile[0]
    if len(teile) >= 2 and teile[1] in ("reel", "reels"):
        return T("{konto} (Reel)", konto=konto)
    if len(teile) >= 2 and teile[1] == "p":
        return T("{konto} (Beitrag)", konto=konto)
    return konto


# Schlüssel sind die Urteile aus instagram.json; übersetzt wird beim
# Gebrauch: `T(URTEIL_TEXT.get(urteil, ""))` (report.py).
URTEIL_TEXT = {
    "wing": N_("Funde nennen Wing oder Foil"),
    "kite_surf": N_("Funde nennen Kite, Windsurf oder Surf — nichts zu Wing"),
    "treffer": N_("Funde ohne Sportbezug im Titel"),
    "keine": N_("keine brauchbaren Funde"),
    "offen": N_("noch nicht gesucht"),
}


def entferne(spot_id: str, pfad: str | Path | None = None) -> bool:
    """Den Eintrag eines gelöschten Spots aus der Momentaufnahme nehmen —
    sonst zeigt der Katalogtest auf eine Kennung, die es nicht mehr gibt."""
    pfad = Path(pfad) if pfad else DATEI
    daten = lade(pfad)
    if not daten or spot_id not in (daten.get("spots") or {}):
        return False
    neu = dict(daten)
    neu["spots"] = {k: v for k, v in daten["spots"].items() if k != spot_id}
    from .spotedit import schreibe_atomar
    schreibe_atomar(pfad, json.dumps(neu, ensure_ascii=False, indent=1))
    _geladen.update(pfad=None, mtime=None, daten={})     # die Änderungszeit kann in derselben Sekunde liegen
    return True

