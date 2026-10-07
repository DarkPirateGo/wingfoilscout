"""HTML-Report. Eine Datei, keine externen Abhängigkeiten, öffnet im Browser."""
from __future__ import annotations
import base64
import functools
import hashlib
import html
import json
import math
from datetime import datetime, timedelta, timezone as _tz
from pathlib import Path

from . import __version__, instagram
from . import csp
from . import i18n
from .i18n import T, TN, N_                                       # noqa: F401
from . import tide as gezeiten
from .score import wetsuit as wetsuit_label
from .config import quiver_range

WATER_LABEL = {"flat": N_("flach"), "chop": N_("kabbelig"), "wave": N_("Welle")}
QUAL_LABEL = {"best": N_("Top-Richtung"), "good": N_("gute Richtung"), "ok": N_("brauchbar"), "bad": N_("schlecht"),
              "sideshore": N_("sideshore"), "side-on": N_("side-on"), "ablandig": N_("ablandig"),
              "auflandig": N_("auflandig"), "unbekannt": N_("Richtung unbekannt"),
              "kein Wasser": N_("kein offenes Wasser")}
LAGE_PILL = {"sideshore": "flat", "side-on": "flat", "ablandig": "chop",
             "auflandig": "wave", "kein Wasser": "wave"}
# Hoch- und Niedrigwasser kurz: „HW“/„NW“ sind Kennungen aus tide.py (dort
# verglichen); übersetzt wird erst hier bei der Anzeige.
TIDE_KURZ = {"HW": N_("HW"), "NW": N_("NW")}


def _wasser_pill(wasser) -> str:
    """Die Plakette für den Wasserzustand — Klasse nur aus der festen Liste,
    Text escaped. Bis 1.18.3 stand `s['water']` roh in Klasse und Text, und
    der Wert kam ungeprüft aus dem Katalogfeld `sectors[].water` (Review
    25.09., S1). `load_spots` prüft das Feld seit 1.19.0 zusätzlich."""
    klasse = wasser if wasser in WATER_LABEL else "chop"
    return f"<span class='pill p-{klasse}'>{html.escape(str(T(WATER_LABEL.get(wasser, wasser))))}</span>"

# Stylesheet und Skripte des Reports stehen seit 1.16.0 in wingscout/web/ —
# eingelesen beim Start und in den Report geschrieben wie vorher.
from . import WEB, lies_web                                      # noqa: E402
KARTE_JS = lies_web("karte.js")

CSS = lies_web("report.css")
# Das Logo des Erstellers im Fuß des Reports (seit 1.19.1) — eingebettet, weil
# die Datei ohne Server geöffnet wird (AirDrop, `file://`): 33 kB PNG, als
# Base64 44 kB. Die Richtlinie (`img-src … data:`) lässt es zu.
LOGO_DATA = "data:image/png;base64," + base64.b64encode((WEB / "logo.png").read_bytes()).decode("ascii")


def _hour_axis(rows):
    """Tages- und Stundenleiste über dem Raster — damit man die Uhrzeit sieht,
    statt sie aus der Hilfeblase eines 8 Pixel breiten Kästchens zu holen.

    Der Abstand der Stundenzahlen richtet sich nach der Rasterbreite: bei drei
    Tagen ist jede dritte Stunde beschriftet, bei sechzehn nur noch der Tag.
    """
    n = len(rows)
    if not n:
        return "", ""

    col_px = 810 / n                       # grobe Annahme für die Spaltenbreite
    step = next((k for k in (1, 2, 3, 6, 12) if col_px * k >= 26), 24)

    days = []
    i = 0
    while i < n:
        day = rows[i]["t"].date()
        j = i
        while j < n and rows[j]["t"].date() == day:
            j += 1
        days.append(f"<div class='hmaxis' style='grid-column:{i + 1}/span {j - i}'>"
                    f"{_tag(rows[i]['t'])}</div>")
        i = j

    ticks = []
    for k, r in enumerate(rows):
        hour = r["t"].hour
        label = f"{hour:02d}" if hour % step == 0 else ""
        # die erste Zahl linksbündig, sonst rutscht sie unter die Zeilenbeschriftung
        pos = " style='left:0;transform:none'" if k == 0 and label else ""
        ticks.append(f"<div class='tick{' dstart' if hour == 0 else ''}'>"
                     f"<span{pos}>{label}</span></div>")

    grid = f"grid-template-columns:repeat({n},1fr)"
    day_row = (f"<div class='hm'><div class='hmname'></div>"
               f"<div class='hmcells' style='{grid}'>{''.join(days)}</div></div>")
    tick_row = (f"<div class='hm'><div class='hmname hmunit'>{T('Uhrzeit')}</div>"
                f"<div class='hmcells' style='{grid}'>{''.join(ticks)}</div></div>")
    return day_row, tick_row


def _ensemble_pill(ens) -> str:
    """Wie viele der vierzig Ensemble-Rechnungen tragen diese Session?

    Der Anteil ist die ehrlichere Zahl als jeder Einzelwert: er sagt, wie
    stabil die Wetterlage ist. Unter der Hälfte heißt, dass die Session
    genauso gut ausfallen kann — das ist die Information, die vor einer
    sechsstündigen Anfahrt zählt.
    """
    if not ens:
        return ""
    share = ens["p_ride"]
    klass = "ok" if share >= 0.75 else ("info" if share >= 0.5 else "chop")
    title = T("{n} Ensemble-Rechnungen · Spitzenwind "
              "P10 {p10} / Median {p50} / P90 {p90} kn · "
              "im Wohlfühlband bei {gut} % · "
              "geht gedämpft in die Reihenfolge ein; das Stundenraster zeigt "
              "weiter den ungedämpften Wert",
              n=ens['members'], p10=f"{ens['p10']:.0f}", p50=f"{ens['p50']:.0f}", p90=f"{ens['p90']:.0f}",
              gut=f"{ens['p_good'] * 100:.0f}")
    sicher = T("{p} % sicher ({von}–{bis} kn)", p=f"{share * 100:.0f}",
               von=f"{ens['p10']:.0f}", bis=f"{ens['p90']:.0f}")
    return (f"<span class='pill p-{klass}' title=\"{_esc(title)}\">"
            f"{sicher}</span> ")


def _modell_pill(s) -> str:
    """Was das feine Modell an dieser Session ändert — typisch, nicht bestenfalls.

    Die Zahl auf der Plakette ist der Median über die abgedeckten Stunden. Das
    Maximum, das bis 1.5.0 dort stand, misst bei einer langen Session vor allem
    ihre Länge: je mehr Stunden gezogen werden, desto größer fällt die
    günstigste aus. Die Spitze steht weiter im Tooltip, wo sie niemanden in die
    Irre führt.
    """
    d, spitze = s.get("modell_delta"), s.get("modell_delta_max")
    mehr = f" {d:+.0f} kn" if d is not None and abs(d) >= 2 else ""
    title = T("Regionalmodell mit 1 bis 2,5 km Gitter statt 7 bis 25. Die Zahl ist der "
              "typische Unterschied zum groben Modell (Median über die abgedeckten Stunden)")
    if spitze is not None and abs(spitze) >= 2:
        title += ", " + T("Spitze {kn} kn", kn=f"{spitze:+.0f}")
    if s.get("modell_stunden") and s.get("hours") and s["modell_stunden"] < s["hours"]:
        title += "; " + T("abgedeckt sind {n} von {m} Stunden, die feinen Modelle reichen kürzer",
                          n=s['modell_stunden'], m=s['hours'])
    return f"<span class='pill p-ok' title='{_esc(title)}'>{_esc(s['modell'])}{mehr}</span> "


SERVICE_LABEL = {
    "animaux": N_("Hunde"), "point_eau": N_("Wasser"), "eau_noire": N_("Schwarzwasser"),
    "eau_usee": N_("Grauwasser"), "poubelle": N_("Müll"), "wc_public": N_("WC"),
    "douche": N_("Dusche"), "electricite": N_("Strom"), "wifi": N_("WLAN"),
    "laverie": N_("Waschmaschine"), "boulangerie": N_("Bäcker"), "gaz": N_("Gas"),
    "donnees_mobile": N_("Mobilfunk"), "piscine": N_("Pool"), "lavage": N_("Waschplatz"),
}


DOG_PILL = {
    "no": ("chop", N_("Hunde verboten")),
    "leash": ("info", N_("Hunde nur an der Leine")),
    "yes": ("ok", N_("Hunde erlaubt")),
}
ACCESS_PILL = {
    "verboten": ("chop", N_("Wingfoilen verboten")),
    "unklar": ("chop", N_("Erlaubnis unklar")),
    "schein": ("info", N_("Surfschein nötig")),
    "verein": ("info", N_("Vereinsmitgliedschaft nötig")),
    "zone": ("info", N_("nur in der Zone")),
    "gebuehr": ("info", N_("Eintritt oder Gebühr")),
    "frei": ("ok", N_("ausdrücklich erlaubt")),
}


SHOREBREAK_PILL = {
    "yes": ("chop", N_("Shorebreak")),
    "possible": ("info", N_("Shorebreak möglich")),
}


def _rule_pills(spot) -> str:
    """Hunde- und Zugangsregeln als Plakette, seit 1.9.0 auch der Shorebreak.

    Nichts davon filtert — es steht nur sichtbar da. Ein Hundeverbot heißt
    nicht, dass der Spot nicht taugt; es heißt, dass man vorher weiß, worauf
    man sich einlässt. Fehlt die Angabe, steht nichts da: „unbekannt" wäre eine
    Aussage, die die Quellen nicht hergeben. Auch „kein Shorebreak" bleibt
    stumm — an einem See wäre die Plakette Rauschen.
    """
    out = []
    for wert, tabelle, titel in ((spot.get("dogs"), DOG_PILL, N_("Hunde am Spot — siehe Notiz")),
                                 (spot.get("access"), ACCESS_PILL, N_("Zugang und Erlaubnis — siehe Notiz"))):
        eintrag = tabelle.get(wert)
        if eintrag:
            klasse, text = eintrag
            out.append(f"<span class='pill p-{klasse}' title='{_esc(T(titel))}'>"
                       f"{_esc(T(text))}</span> ")
    sb = spot.get("shorebreak") or {}
    eintrag = SHOREBREAK_PILL.get(sb.get("status")) if isinstance(sb, dict) else None
    if eintrag:
        klasse, text = eintrag
        titel = sb.get("note") or T("Die Welle bricht direkt am Ufer — Ein- und Ausstieg mit Bedacht")
        out.append(f"<span class='pill p-{klasse}' title='{_esc(titel)}'>{_esc(T(text))}</span> ")
    return "".join(out)


def _instagram_zeile(spot) -> str:
    """Die Funde der Instagram-Momentaufnahme als Zeile unter dem Ziel.

    Höchstens drei Links, beschriftet nach Konto oder Art, der volle Titel
    des Treffers als Tooltip. Die Zeile sagt dazu, was sie ist — Suchtreffer
    mit Datum, kein Beleg. Ohne Funde und ohne Ortsseite steht nichts da.
    """
    f = instagram.funde(spot)
    if not f or (not f.get("funde") and not f.get("ort")):
        return ""
    teile = []
    if f.get("ort"):
        teile.append(f"<a href='{_esc(f['ort'])}' target='_blank' rel='noopener' "
                     f"title='{_esc(f.get('ort_titel') or T('Ortsseite auf Instagram'))}'>{T('Ort')}</a>")
    for fund in f["funde"][:3]:
        teile.append(f"<a href='{_esc(fund['url'])}' target='_blank' rel='noopener' "
                     f"title='{_esc(fund['titel'])}'>{_esc(instagram.beschriftung(fund['url'], fund['titel']))}</a>")
    mehr = len(f["funde"]) - 3
    rest = " · " + T("{n} weitere im Katalog", n=mehr) if mehr > 0 else ""
    stand = " " + T("(Suchtreffer vom {datum}, kein Beleg)", datum=_datum(f['stand'])) if f.get("stand") else ""
    # URTEIL_TEXT ist eine Tabelle aus instagram.py — übersetzt wird beim Gebrauch
    return (f"<span><span class='pill p-info' title='{_esc(T(instagram.URTEIL_TEXT.get(f.get('urteil'), '')))}'>"
            f"Instagram</span> " + " · ".join(teile) + f"{rest}{stand}</span>")


def _datum(iso: str) -> str:
    """„2026-09-18“ → 18.09.2026 · 18 Sep 2026 · 18 sept. 2026 · 18 sep 2026"""
    try:
        return i18n.datum_jahr(datetime.strptime(iso, "%Y-%m-%d"))
    except ValueError:
        return iso


def _tide_json(info: dict) -> str:
    """Die Übersicht für das Skript — als Wert eines einfach angeführten
    Attributs: nur &, <, > und das einfache Anführungszeichen werden
    ersetzt, die doppelten des JSON bleiben lesbar (23 Spots × 4 Tage
    Scheitel sind sonst ein Drittel größer)."""
    # NaN als null (i18n.json_endlich): JSON.parse im Skript verwürfe sonst die
    # ganze Übersicht
    roh = i18n.json_endlich(gezeiten.als_json(info), ensure_ascii=False, separators=(",", ":"))
    return roh.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&#39;")


def _tide_stand(info: dict, jetzt=None) -> str:
    """Die Lage beim Erstellen des Reports, in Ortszeit des Spots. Das Skript
    ersetzt den Text beim Öffnen durch die Lage zur Anzeigezeit; ohne Skript
    (oder in einer Vorschau) bleibt dieser Satz stehen."""
    ereignisse = info.get("ereignisse") or []
    if not ereignisse:
        return ""
    if jetzt is None:
        jetzt = datetime.now(tz=_tz.utc).replace(tzinfo=None) + timedelta(seconds=int(info.get("versatz") or 0))
    lage = gezeiten.lage_text(jetzt, ereignisse)
    return T("Stand {zeit} Uhr: {lage}", zeit=jetzt.strftime('%H:%M'), lage=lage) if lage else ""


def _zeitraum_text(args) -> str:
    """„3 Tage“ — mit Startzeitpunkt (seit 2.3.0) „3 Tage ab Sa 10.10. 09:00“."""
    fenster = getattr(args, "_fenster", None)
    if fenster is None or fenster.ab is None:
        return T("{n} Tage", n=args.days)
    return T("{n} Tage ab {start}", n=args.days, start=_tag(fenster.ab) + " " + fenster.ab.strftime("%H:%M"))


def _tage_der_suche(args) -> tuple[str, str] | None:
    """(erster Tag, Tag nach dem letzten) einer Suche mit Startzeitpunkt."""
    fenster = getattr(args, "_fenster", None)
    return fenster.tage_iso if fenster is not None else None


def _tide_zeile(spot, jetzt=None, tage: tuple[str, str] | None = None) -> str:
    """Die Tide am Ziel: Lage jetzt (per Skript aktuell gehalten), Hoch- und
    Niedrigwasser je Tag, Hub und — wenn im Katalog gesetzt — das Tidenfenster.
    Mit `tage` (einer Suche mit Startzeitpunkt, seit 2.3.0) nur die Tage darin."""
    info = spot.get("_tide") or {}
    if not info.get("aktiv"):
        return ""
    ereignisse = info.get("ereignisse") or []
    fenster = info.get("fenster")
    teile = [f"<div class='tide'><span class='pill p-info'>{T('Tide')}</span>"]
    if not ereignisse:
        teile.append("<span class='tide-jetzt'>" + T("keine Tidendaten vom Modell — die Küste liegt wohl "
                                                     "außerhalb des 8-km-Rasters") + "</span>")
        if fenster:
            teile.append("<span class='tide-meta'>"
                         + T("Tidenfenster {fenster} gesetzt, ohne Daten nicht angewendet",
                             fenster=_esc(info.get('fenster_text', '')))
                         + "</span>")
        return "".join(teile) + "</div>"
    teile.append(f"<span class='tide-jetzt' data-tide='{_tide_json(info)}'>"
                 f"{_esc(_tide_stand(info, jetzt))}</span>")
    zeitraum_tage, tage_ev = tage, {}
    for ev in ereignisse:
        tag = ev["zeit"].date().isoformat()
        if zeitraum_tage is None or zeitraum_tage[0] <= tag < zeitraum_tage[1]:
            tage_ev.setdefault(tag, []).append(ev)
    zeilen = []
    for tag, evs in sorted(tage_ev.items())[:7]:
        liste = " · ".join(f"<span class='ev'>{T(TIDE_KURZ.get(ev['art'], ev['art']))} {ev['zeit'].strftime('%H:%M')}</span>"
                           for ev in evs)
        fz = gezeiten.fenster_zeiten(ereignisse, fenster, tag)
        if fz:
            liste += " <i>" + T("(Fenster {zeiten})", zeiten=", ".join(f"{a}–{b}" for a, b in fz)) + "</i>"
        zeilen.append(f"<span><b>{_tag(evs[0]['zeit'])}</b> {liste}</span>")
    teile.append("<span class='tide-tage'>" + "".join(zeilen) + "</span>")
    meta = []
    if info.get("hub") is not None:
        meta.append(T("Hub ≈ {hub} m", hub=i18n.zahl(info['hub'], 1)))
    if fenster:
        meta.append(T("fahrbar {fenster} — Stunden außerhalb sind ausgeschlossen",
                      fenster=_esc(info.get('fenster_text', ''))))
    else:
        meta.append(T("nur zur Information, kein Einfluss auf die Bewertung"))
    # QUELLE ist eine Konstante aus tide.py — übersetzt wird beim Gebrauch
    meta.append("<span title='" + _esc(T(gezeiten.QUELLE)) + "'>" + T("Modell, keine amtliche Tafel") + "</span>")
    teile.append("<span class='tide-meta'>" + " · ".join(meta) + "</span>")
    return "".join(teile) + "</div>"


def _shorebreak_zeile(spot) -> str:
    """Die Notiz zum Shorebreak als eigene Zeile unter dem Kopf — die Plakette
    allein sagt nicht, wann und warum. Ohne Notiz reicht die Plakette."""
    sb = spot.get("shorebreak") or {}
    if not isinstance(sb, dict) or sb.get("status") not in SHOREBREAK_PILL or not sb.get("note"):
        return ""
    klasse, text = SHOREBREAK_PILL[sb["status"]]
    quelle = f" <i>({_esc(sb['source'])})</i>" if sb.get("source") else ""
    return (f"<span><span class='pill p-{klasse}'>{_esc(T(text))}</span> "
            f"{_esc(sb['note'])}{quelle}</span>")


def _safe_url(url) -> str:
    """Nur http(s)-Adressen dürfen in einen Link — alles andere wird leer.

    Die Adresse eines Stellplatzes stammt aus einer fremden Antwort. Stünde
    dort `javascript:` statt `https:`, würde ein Klick im Report Code ausführen.
    """
    url = str(url or "")
    return url if url.startswith(("https://", "http://")) else ""


def _camping_block(camping, spot, home=None) -> str:
    """Stellplätze unter einem Ziel — nur solche, an denen der Hund mitdarf.

    Die Zahl der übergangenen Plätze steht bewusst dabei: „keine Angabe zu
    Tieren" heißt bei Park4Night meistens, dass es niemand eingetragen hat,
    nicht dass Hunde verboten sind. Ohne diesen Hinweis wundert man sich, warum
    an einer Küste voller Campingplätze nur zwei in der Liste stehen.
    """
    if not camping:
        return ""
    places = camping.get("places") or []
    ohne = camping.get("ohne_hundeangabe", 0)
    if not places:
        hinweis = (T("Kein Platz im Umkreis mit Angabe „Hunde erlaubt\".")
                   + (" " + T("{n} Plätze ohne diese Angabe wurden übergangen — "
                              "bei Park4Night direkt nachsehen.", n=ohne) if ohne else ""))
        return f"<div class='camp'><h4>{T('Stellplätze')}</h4><p class='note'>{_esc(hinweis)}</p></div>"

    rows = []
    for place in places[:4]:
        dienste = " · ".join(T(SERVICE_LABEL.get(x, x)) for x in place["services"]
                             if x in SERVICE_LABEL and x != "animaux")
        bewertung = (TN("{wert} bei {n} Bewertung", "{wert} bei {n} Bewertungen", place['reviews'], wert=f"{place['rating']:.1f}")
                     if place["reviews"] else T("noch nicht bewertet"))
        route = (f"https://www.google.com/maps/dir/?api=1"
                 f"&origin={spot['lat']},{spot['lon']}"
                 f"&destination={place['lat']},{place['lon']}&travelmode=driving")
        rows.append(
            f"<div class='camprow'>"
            f"<span class='num'>{place['km']:.1f} km</span>"
            f"<span><a href='{_esc(_safe_url(place['url']))}' target='_blank' rel='noopener'>"
            f"{_esc(place['name'])}</a>"
            f"<span class='pill p-ok'>{T('Hunde')}</span> "
            f"<span class='note'>{_esc(place['kind_label'])} · {_esc(bewertung)}"
            f"{' · ' + _esc(dienste) if dienste else ''}</span></span>"
            f"<a class='camproute' href='{route}' target='_blank' rel='noopener'>{T('Weg zum Wasser')}</a>"
            f"</div>")

    fuss = T("{n} weitere Plätze ohne Angabe zu Tieren übergangen.", n=ohne) if ohne else ""
    return (f"<div class='camp'><h4>{T('Stellplätze mit Hund')}</h4>{''.join(rows)}"
            + (f"<p class='note'>{_esc(fuss)}</p>" if fuss else "") + "</div>")


def knoten_grenzen(cfg) -> dict:
    """Die vier Grenzen der Knotenskala, immer widerspruchsfrei.

    Grün ist das Wohlfühlband aus der Oberfläche — änderst du es dort, wandert
    die grüne Zone mit. Die beiden roten Enden stehen in der Konfiguration
    (`wind.red_below` / `wind.red_above`) und bedeuten „zu wenig für den
    größten Wing" und „zu viel, um Spaß zu haben".

    Liegt ein rotes Ende im Wohlfühlband — bei Band 14–28 und rot ab 26 wäre
    das so —, weicht es aus, statt die grüne Zone zu zerschneiden: das untere
    auf die Bandgrenze, das obere zwei Knoten darüber. Damit bleibt die Skala
    immer lesbar, egal was in der Oberfläche steht.
    """
    w = cfg["wind"]
    lo, hi = float(w["preferred_low"]), float(w["preferred_high"])
    unten = min(float(w.get("red_below", 11)), lo)
    oben = float(w.get("red_above", 26))
    if oben <= hi:
        oben = hi + 2
    dunkel = max(float(w.get("dark_above", 30)), oben)
    return {"rot_unter": unten, "gruen_von": lo, "gruen_bis": hi,
            "rot_ueber": oben, "dunkel_ueber": dunkel}


ROT, ORANGE, GRUEN, DUNKELROT = "#C24A38", "#D98A2B", "#3B8F63", "#7A1F14"
AUS = " data-aus='1'"      # Nacht oder ausgeschlossen — in der Knotenansicht blass


def knoten_farbe(kn: float, g: dict) -> str:
    """Rot – orange – grün – orange – rot – dunkelrot, nach Knoten.

    Das dunkelrote Ende (Standard ab 30 kn) ist keine Geschmacksfrage mehr,
    sondern eine andere Kategorie: da geht es nicht um Spaß, sondern um die
    Frage, ob man überhaupt aufs Wasser sollte.
    """
    if kn > g["dunkel_ueber"]:
        return DUNKELROT
    if kn < g["rot_unter"] or kn > g["rot_ueber"]:
        return ROT
    if kn < g["gruen_von"] or kn > g["gruen_bis"]:
        return ORANGE
    return GRUEN


def _cell_color(score: float) -> str:
    if score <= 0:
        return "var(--surface-2)"
    a = 0.12 + 0.88 * min(score, 1.0) ** 1.5
    return f"rgba(174,31,104,{a:.2f})"


def _esc(x) -> str:
    """Escaped für HTML — und ein Text aus der Suche (`i18n.TD`) zuvor in der
    Sprache des Reports, der gerade entsteht (seit 2.3.0 alle vier aus einer
    Suche; siehe i18n „Texte in Daten“)."""
    return html.escape(str(i18n.uebersetzt(x)))


def _richtungen(dirs, n: int = 3) -> str:
    """Die Himmelsrichtungen einer Session („W/WNW“): in der Sprache des
    Reports, nach deren Kürzeln sortiert, die ersten `n` — so, wie eine Suche
    in dieser Sprache sie gelistet hätte („O“ ist auf Englisch „E“ und
    sortiert anders)."""
    return "/".join(sorted({str(i18n.uebersetzt(d)) for d in dirs})[:n])


def _ohne_null(x) -> str:
    """Eine ganze Zahl ohne „.0“: 500.0 → „500“ (bis 2.1.0 stand im Kopf des
    Reports „Radius 500.0 km“); alles andere, wie es ist."""
    try:
        ganz = float(x).is_integer()
    except (TypeError, ValueError, OverflowError):
        return str(x)
    return str(int(float(x))) if ganz else str(x)


def _tag(t, lang: bool = True) -> str:
    """Datum mit Wochentag in der Sprache des Reports („Sa 03.10.“, „Sat 3 Oct“),
    mit `lang=False` nur der Wochentag.

    `strftime("%a")` richtet sich nach der Locale des Prozesses, und die ist
    bei einem doppelgeklickten Python unter macOS „C" — der Report stand
    deshalb auf Englisch da („Tue 15.09."). Feste Kürzel je Sprache (seit
    2.1.0 in i18n.py) sind zuverlässiger als jeder Locale-Aufruf.
    """
    return i18n.tag(t) if lang else i18n.wochentag(t)


def _stunde(t) -> str:
    """Tag und volle Stunde („Sa 03.10. 14 Uhr“) — für Popup und Zellen der Raster."""
    return _tag(t) + " " + T("{stunde} Uhr", stunde=i18n.stunde(t))


def _maps_route(spot, home=None) -> str:
    """Google-Maps-Route zum Spot — mit Startpunkt, wenn einer bekannt ist.

    Mit `origin` zeigt Maps die Entfernung ab dem tatsächlichen Standort statt
    ab dem, wo das Telefon gerade meint zu sein.
    """
    ziel = f"{spot['lat']},{spot['lon']}"
    start = f"&origin={home['lat']},{home['lon']}" if home else ""
    return (f"https://www.google.com/maps/dir/?api=1{start}"
            f"&destination={ziel}&travelmode=driving")


def _windy(spot, zoom: int = 12) -> str:
    """Windy auf die Spotkoordinate.

    Windy kennt keinen Deep-Link auf einen benannten Ort, nimmt aber die
    Kartenmitte als `?lat,lon,zoom`. Zoom 12 zeigt die Bucht, 11 die Küste.
    """
    return f"https://www.windy.com/?{spot['lat']},{spot['lon']},{zoom}"


def _links(spot, home=None) -> str:
    """Die Absprünge unter einem Ziel — alle auf die Spotkoordinate, seit
    1.9.0 auch zu Instagram.

    Park4Night nimmt `lat`, `lng` und `z` entgegen und zeigt die Stellplätze
    genau dort; die frühere Fassung führte auf die Suchstartseite, wo man von
    Hand hinnavigieren musste. Windy kennt keinen Deep-Link auf einen Punkt,
    nimmt aber die Kartenmitte — Zoom 12 reicht, um den Spot zu erkennen.
    """
    lat, lon = spot["lat"], spot["lon"]
    # Die Beschriftungen („Instagram“, „Insta-Suche“) kommen aus instagram.py —
    # übersetzt wird hier bei der Anzeige.
    insta = "".join(f'<a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(T(text))}</a>'
                    for text, url in instagram.links(spot))
    return (
        f'<a href="{_windy(spot)}" target="_blank" rel="noopener">Windy</a>'
        f'<a href="{_maps_route(spot, home)}" target="_blank" rel="noopener">{T("Route")}</a>'
        f'<a href="https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=14/{lat}/{lon}" target="_blank" rel="noopener">{T("Karte prüfen")}</a>'
        f'<a href="https://park4night.com/en/search?lat={lat}&lng={lon}&z=12" target="_blank" rel="noopener">Park4Night</a>'
        + insta
    )


def _band_labels(rows):
    """Stundenbeschriftung und Tagesblöcke für das Band im Popup.

    Beides ist für alle Spots gleich — dieselbe Vorhersagestunde bedeutet
    überall dieselbe Uhrzeit. Deshalb steht es einmal im Kopf der Daten und
    nicht bei jedem der bis zu 277 Marker.
    """
    if not rows:
        return [], []
    stunden = [_stunde(r["t"]) for r in rows]
    tage, letzte = [], None
    for r in rows:
        tag = _tag(r["t"])
        if tag != letzte:
            tage.append([_tag(r["t"], lang=False), 0])
            letzte = tag
        tage[-1][1] += 1
    return stunden, tage


def _marker_band(rows):
    """Score und Wind als kompakte Zeichenketten.

    Ausgeschrieben als JSON-Listen wären das bei 16 Tagen und 277 Spots
    mehrere Megabyte. Ein Zeichen je Stunde für den Score (0–9) und zwei für
    den Wind (auf 99 kn gedeckelt) sind rund 1 kB je Spot.

    Eine Stunde ohne endlichen Wert (`nan`/`inf` aus einer kaputten Quelle)
    steht als 0 da — die Bänder bleiben gleich lang, und `int(round(nan))`
    bricht nicht mehr den ganzen Report ab.
    """
    def ganz(x, hoch: int, faktor: float = 1.0) -> int:
        try:
            x = float(x) * faktor
        except (TypeError, ValueError):
            return 0
        return min(hoch, max(0, int(round(x)))) if math.isfinite(x) else 0

    sc = "".join(str(ganz(r["score"], 9, 9)) for r in rows)
    wd = "".join(f"{ganz(r['wind'], 99):02d}" for r in rows)
    return sc, wd


def _kurz(text: str, n: int = 110) -> str:
    """Notiz fürs Popup kürzen — der volle Text steht unten beim Ziel.

    Manche Katalognotizen sind drei Zeilen lang (Herkunft der Koordinate,
    Genauigkeit). Im Popup verdrängen sie das, wofür man geklickt hat.
    """
    text = (text or "").strip()
    return text if len(text) <= n else text[:n - 1].rstrip(" ,;.") + "…"


def _camp_marker(place, spot):
    return {
        "name": i18n.uebersetzt(place["name"]), "lat": place["lat"], "lon": place["lon"],
        "km": round(place.get("km", 0.0), 1),
        "kind": i18n.uebersetzt(place.get("kind_label", "")),
        "rating": place.get("rating"), "reviews": place.get("reviews", 0),
        "url": _safe_url(place.get("url", "")),
        "spot": spot["name"],
    }


def _map_block(trips, all_rows, dropped, cfg, args, nonce: str = "") -> str:
    """Die Karte als eigenständige Ansicht, nicht als Illustration.

    Der Report hat unten alles in Tabellen. Wer aber „wo denn?" fragt, denkt
    räumlich und will die Antwort dort haben, wo er hinschaut: Name am Punkt,
    Stundenband im Popup, Stellplätze als eigene Ebene, und alles einzeln
    abschaltbar, weil 277 Punkte sonst ein Farbteppich sind.
    """
    home = cfg["rider"]["home"]
    ranked = {t["spot"]["id"]: (i + 1, t) for i, t in enumerate(trips)}
    markers, camps = [], []

    ref = next(iter(all_rows.values()))[1] if all_rows else []
    stunden, tage = _band_labels(ref)

    for spot_id, (spot, rows) in all_rows.items():
        sc, wd = _marker_band(rows)
        rank_trip = ranked.get(spot_id)
        th = spot.get("thermal") or {}
        sb = spot.get("shorebreak") or {}
        eintrag = {
            "id": spot["id"], "name": spot["name"], "lat": spot["lat"], "lon": spot["lon"],
            "kmt": str(spot.get("comment") or ""),
            "thermik": th.get("name") or (T("Thermik") if th else ""),
            "drive": T("{h} h Fahrt · {km} km", h=f"{spot['drive_h']:.1f}", km=f"{spot['road_km']:.0f}"),
            "notes": _kurz(spot.get("notes", "")),
            "sb": sb.get("status", "") if isinstance(sb, dict) else "",
            "sb_note": _kurz(sb.get("note", "")) if isinstance(sb, dict) else "",
            "ig": dict(instagram.links(spot)).get("Instagram", ""),
            "sc": sc, "wd": wd,
        }
        tide_info = spot.get("_tide") or {}
        if tide_info.get("aktiv") and tide_info.get("ereignisse"):
            eintrag["tide"] = gezeiten.als_json(tide_info)
            eintrag["tide_text"] = _tide_stand(tide_info)
        if rank_trip:
            rank, t = rank_trip
            best = max(t["sessions"], key=lambda x: x["score"])
            eintrag.update({
                "kind": "top" if rank <= 3 else "hit", "rank": rank,
                "line": (T("{h} h Wasser an {n} Tag(en)", h=f"{t['total_hours']:.0f}", n=len(t['days']))
                         + " · "
                         + T("beste Session {tag} {von}–{bis} Uhr, {wmin}–{wmax} kn", tag=_tag(best['start']),
                             von=i18n.stunde(best['start']), bis=i18n.stunde(best['end']),
                             wmin=best['wind_min'], wmax=best['wind_max'])),
                "dirs": _richtungen(best["dirs"]),
                "wings": " / ".join(f"{w:g}" for w in best["wings"][:3]),
            })
            for place in ((t.get("camping") or {}).get("places") or [])[:6]:
                camps.append(_camp_marker(place, spot))
        else:
            eintrag.update({"kind": "quiet", "rank": None,
                            "line": T("im Radius, aber keine Session im Zeitraum")})
        markers.append(eintrag)

    for spot, reason in dropped:
        markers.append({
            "id": spot["id"], "name": spot["name"], "lat": spot["lat"], "lon": spot["lon"],
            "kmt": str(spot.get("comment") or ""),
            "kind": "out", "rank": None, "line": i18n.uebersetzt(reason),
            "drive": T("{h} h Fahrt · {km} km", h=f"{spot['drive_h']:.1f}", km=f"{spot['road_km']:.0f}"),
            "notes": _kurz(spot.get("notes", "")), "sc": "", "wd": "",
        })

    # Daten in einem <script>: ein Spotname „</script><script>…" würde sonst das
    # Skript beenden und eigenes ausführen. Als Unicode-Escapes bleibt es JSON
    # und kann nie als Markup gelesen werden — derselbe Weg wie für alle Daten
    # in Skripten (i18n.json_im_skript), mit U+2028/U+2029 und NaN als null.
    payload = i18n.json_im_skript({
        "home": {"name": home["name"], "lat": home["lat"], "lon": home["lon"]},
        "radius_km": args.radius,
        "umweg": _umweg(cfg),
        "stunden": stunden, "tage": tage,
        "markers": markers, "camps": camps,
    })

    camp_schalter = ("" if not camps else
                     '<label><input type="checkbox" id="l_camp" checked>'
                     '<i style="background:#276B4F"></i>' + T("Stellplätze mit Hund") + '</label>')
    # Die Beschriftungen der Vorlage vorab: T() mit Platzhaltern in einer
    # dreifach angeführten f-Vorlage wäre kaum lesbar.
    legende = T("Punkt anklicken: Stundenband, Fahrt und Luftlinie zum Start · der Name\n"
                "  im Popup führt zu Windy · überfahren zeigt den Namen")
    # Der Kreis ist eine Luftlinie und nur Orientierung: gesucht wird nach
    # der gerouteten Fahrstrecke (seit 2.4.0 so gesagt; bis dahin „= … km
    # Straße“, als wäre der Kreis die Grenze).
    kreis = T("gestrichelter Kreis ≈ {luft} km Luftlinie, nur zur Orientierung — die Suche nimmt Spots "
              "bis {strasse} km Fahrstrecke",
              strasse=f"{args.radius:.0f}", luft=f"{args.radius / _umweg(cfg):.0f}")

    return f"""<details class="zu-am-handy" id="kartebox" open><summary><h2>{T("Karte")}</h2></summary>
<div id="map"><div class="nomap">{T("Karte lädt … (braucht kurz Internet für die Kacheln)")}</div></div>
<div class="maptools" id="maptools">
  <label><input type="checkbox" id="l_top" checked><i style="background:#AE1F68"></i>{T("Top 3")}</label>
  <label><input type="checkbox" id="l_hit" checked><i style="background:rgba(174,31,104,.55)"></i>{T("Session gefunden")}</label>
  <label><input type="checkbox" id="l_quiet" checked><i style="background:#8FA9B3"></i>{T("windstill")}</label>
  <label><input type="checkbox" id="l_out"><i style="border:1.5px solid #8FA9B3"></i>{T("aussortiert")}</label>
  {camp_schalter}
  <span class="trenner"></span>
  <label><input type="checkbox" id="l_thermik"><i style="background:#D98A2B"></i>{T("Thermische Winde")}</label>
  <label><input type="checkbox" id="l_windy">{T("Klick öffnet Windy statt der Details")}</label>
  <label><input type="checkbox" id="l_names">{T("Namen der Treffer")}</label>
  <label><input type="checkbox" id="l_ring" checked>{T("Radius")}</label>
  <button type="button" id="b_top">{T("Auf Top 3")}</button>
  <button type="button" id="b_all">{T("Alles zeigen")}</button>
  <button type="button" id="b_full">{T("Vollbild")}</button>
</div>
<div class="maplegend">
  <span>{legende}</span>
  <span>{kreis}</span>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"
        integrity="sha384-NElt3Op+9NBMCYaef5HxeJmU4Xeard/Lku8ek6hoPTvYkQPh3zLIrJP7KiRocsxO"
        crossorigin="anonymous"></script>
<script nonce='{nonce or csp.neue_nonce()}'>
var KARTE = {payload};
{KARTE_JS}</script>
</details>"""


# ── Kommentar je Spot ────────────────────────────────────────────────────────
#
# Ein Kasten `.kmt` mit `data-id` (und `data-text`) wird zum Kommentar mit
# „bearbeiten“; der Editor schickt an `/katalog/kommentar` der laufenden
# Oberfläche. Der Report ist eine Datei — geöffnet aus der Oberfläche (im
# Rahmen unter der Suche) trifft der Aufruf den Server, geöffnet als Datei
# nicht; dann sagt der Kasten das, statt still zu scheitern. Nach dem
# Speichern erfährt es jeder Kasten desselben Spots auf der Seite
# (Ereignis `kommentar`), im Report also Ziel und Karten-Popup zugleich.
# Dieselbe Fassung nutzen Katalog-, Prüf- und Rückblickseite (webui).

KOMMENTAR_CSS = lies_web("kommentar.css")

KOMMENTAR_JS = lies_web("kommentar.js")
TIDE_JS = lies_web("tide.js")


def kommentar_kasten(spot_id: str, text: str) -> str:
    """Der Kasten, den `WSKommentar.alle()` zum Kommentar macht."""
    return f"<div class='kmt' data-id='{_esc(spot_id)}' data-text='{_esc(text or '')}'></div>"


# ── Alle Sessions: sortierbar ────────────────────────────────────────────────
#
# Die Tabelle stand nach Score sortiert da, auf 40 Zeilen gekappt. Wer aber
# „wo ist es am längsten fahrbar" oder „wo ist es flach" fragt, sortiert
# anders — und die Kappung nach Score würde ihm dann genau die Zeilen
# nehmen, die er sucht. Deshalb stehen alle Sessions in der Tabelle, jede
# Zelle trägt ihren Sortierwert (`data-v`), ein Klick auf die Spalte sortiert
# im Browser, und gezeigt werden die ersten 40 der aktuellen Reihenfolge —
# „alle zeigen" hebt das auf.

# Windlage: was man am liebsten hat, zuerst. Sideshore ist die Lage zum
# Wingen, side-on fast so gut, auflandig bringt Welle und Rückweg umsonst,
# ablandig ist die Rückwegfrage. Die Sektorenurteile des Katalogs
# (best…bad) reihen sich dazwischen ein — sie sagen „gute Richtung", nicht
# welche Lage.
LAGE_RANG = {"sideshore": 0, "side-on": 1, "best": 1, "good": 2, "auflandig": 3, "ok": 3,
             "ablandig": 4, "bad": 5, "unbekannt": 6, "kein Wasser": 7}
WASSER_RANG = {"flat": 0, "chop": 1, "wave": 2}


def _sessions_tabelle(sessions: list, nonce: str = "") -> str:
    kopf = (("spot", T("Spot"), T("Name, A bis Z")), ("wann", T("Wann"), T("Beginn")),
            ("dauer", T("Dauer"), T("Stunden am Stück")),
            ("wind", T("Wind"), T("Windmaximum, dann Minimum")),
            ("lage", T("Lage"), T("sideshore zuerst, dann side-on, auflandig, ablandig")),
            ("richtung", T("Richtung"), T("Himmelsrichtung, aus der der Wind kommt")),
            ("wing", T("Wing"), T("kleinster Wing")),
            ("wasser", T("Wasser"), T("flach zuerst, dann kabbelig, dann Welle")),
            ("score", T("Score"), T("Bewertung, beste zuerst")))
    aus = ["<p class='sub' style='margin:0 0 10px'>"
           + T("Spalte anklicken sortiert, noch einmal dreht um. Gezeigt werden die ersten 40 der "
               "Reihenfolge — <a href='#' id='sess_alle'>alle {n} zeigen</a>.", n=len(sessions))
           + "</p>"
           "<p class='wischen'>" + T("Seitlich wischen — rechts stehen Wind, Windlage, Wing und Wasser.") + "</p>",
           "<div class='scroll'><table id='sesstab'><thead><tr>"]
    for k, titel, tip in kopf:
        aus.append(f"<th data-k='{k}' title='{_esc(tip)}'{' class=' + chr(39) + 'sort' + chr(39) if k == 'score' else ''}>{titel}</th>")
    aus.append("</tr></thead><tbody>")
    for i, s in enumerate(sessions):
        ws = s["wings"]
        wl = f"{ws[0]:g}\u2013{ws[-1]:g}" if len(ws) > 2 else " / ".join(f"{w:g}" for w in ws)
        lage = s.get("quality") or "unbekannt"
        lage_text = T(QUAL_LABEL.get(lage, lage))
        lage_pill = LAGE_PILL.get(lage, {"best": "flat", "good": "flat", "ok": "chop", "bad": "wave"}.get(lage, "chop"))
        richtung = _richtungen(s["dirs"])
        aus.append(
            f"<tr{' class=' + chr(39) + 'mehr' + chr(39) if i >= 40 else ''}>"
            f"<td data-v='{_esc(s['spot']['name'].lower())}'>{_esc(s['spot']['name'])}</td>"
            f"<td class='n' data-v='{s['start'].strftime('%Y-%m-%dT%H')}'>{_tag(s['start'])} {i18n.stunde(s['start'])}–{i18n.stunde(s['end'])}</td>"
            f"<td class='n' data-v='{int(s['hours'])}'>{s['hours']} h</td>"
            f"<td class='n' data-v='{int(s['wind_max']) * 100 + int(s['wind_min'])}'>{s['wind_min']}–{s['wind_max']} kn</td>"
            f"<td data-v='{LAGE_RANG.get(lage, 6)}'><span class='pill p-{lage_pill}'>{_esc(lage_text)}</span></td>"
            f"<td class='n' data-v='{_esc(richtung)}'>{_esc(richtung)}</td>"
            f"<td class='n' data-v='{ws[0] if ws else 0:g}'>{wl} m²</td>"
            f"<td data-v='{WASSER_RANG.get(s['water'], 1)}'>{_wasser_pill(s['water'])}</td>"
            f"<td class='n' data-v='{s['score']:.3f}'>{s['score']:.2f}</td></tr>")
    aus.append("</tbody></table></div>")
    aus.append(csp.skript(nonce or csp.neue_nonce(), "\n" + SESSIONS_JS))
    return _abschnitt(T("Alle Sessions"), T("{n} Sessions, sortierbar", n=len(sessions)), "".join(aus), "sessions")


SESSIONS_JS = lies_web("sessions.js")
MOBIL_JS = lies_web("mobil.js")           # Rohtext; ins <script> kommt er mit der Nonce der Seite
ANSICHT_JS = lies_web("ansicht.js")       # Einfach/Ausführlich (seit 1.20.0)


def _raster_schalter(g: dict, nonce: str = "") -> str:
    """Umschalter Güte/Knoten — färbt die vorhandenen Zellen im Browser um.

    Die Zellen tragen ihre Knoten als `data-kn`, die Güte-Farbe steht als
    Hintergrund schon drin. Beim ersten Umschalten wird sie in `data-guete`
    gesichert, danach kostet Hin und Her nichts mehr.
    """
    grenzen = i18n.json_im_skript(g)             # wie alle Daten in Skripten
    return """<script nonce='%s'>
(function () {
  var G = %s, ROT = '%s', ORANGE = '%s', GRUEN = '%s', DUNKEL = '%s';
  var raster = document.getElementById('hmraster');
  var bGuete = document.getElementById('f_guete'), bKnoten = document.getElementById('f_knoten');
  if (!raster || !bGuete) return;
  var zellen = raster.querySelectorAll('.cell');

  function knotenFarbe(kn) {
    if (kn > G.dunkel_ueber) return DUNKEL;
    if (kn < G.rot_unter || kn > G.rot_ueber) return ROT;
    if (kn < G.gruen_von || kn > G.gruen_bis) return ORANGE;
    return GRUEN;
  }
  function setze(modus) {
    for (var i = 0; i < zellen.length; i++) {
      var z = zellen[i];
      if (!z.dataset.guete) z.dataset.guete = z.style.background;
      if (modus === 'knoten') {
        z.style.background = knotenFarbe(Number(z.dataset.kn));
        z.style.opacity = z.dataset.aus ? '.3' : '1';
      } else {
        z.style.background = z.dataset.guete;
        z.style.opacity = '1';
      }
    }
    bGuete.className = modus === 'knoten' ? '' : 'an';
    bKnoten.className = modus === 'knoten' ? 'an' : '';
    document.getElementById('leg_guete').style.display = modus === 'knoten' ? 'none' : '';
    document.getElementById('leg_knoten').style.display = modus === 'knoten' ? '' : 'none';
  }
  bGuete.addEventListener('click', function () { setze('guete'); });
  bKnoten.addEventListener('click', function () { setze('knoten'); });
})();
</script>""" % (nonce or csp.neue_nonce(), grenzen, ROT, ORANGE, GRUEN, DUNKELROT)


def _abschnitt(titel: str, hinweis: str, inhalt: str, kennung: str = "") -> str:
    """Ein Abschnitt als Klappe (seit 1.20.0): Überschrift und ein kurzer
    Hinweis, was drin ist, bleiben sichtbar; der Inhalt kommt auf Klick oder
    mit der Ansicht „Ausführlich“."""
    kennung = f" id='{kennung}'" if kennung else ""
    return (f"<details class='abschnitt'{kennung}><summary><h2>{titel}</h2>"
            f"<span class='hint'>{hinweis}</span></summary><div class='inhalt'>{inhalt}</div></details>")


def _beste_session(t: dict) -> dict | None:
    """Die Session mit dem höchsten Score — die eine Zeile, die im zugeklappten
    Ziel steht."""
    return max(t["sessions"], key=lambda s: s.get("score", 0)) if t.get("sessions") else None


def _kern(t: dict) -> str:
    """Die Antwort in einer Zeile: wann, wie viel Wind, welcher Wing, welche
    Lage — aus der besten Session. Weitere Sessions nur als Zahl; sie stehen
    aufgeklappt einzeln da."""
    s = _beste_session(t)
    if not s:
        return ""
    ws = s["wings"]
    wings = f"{ws[0]:g}–{ws[-1]:g}" if len(ws) > 2 else " / ".join(f"{w:g}" for w in ws)
    teile = [_tag(s['start']) + " " + T("{von}–{bis} Uhr", von=i18n.stunde(s['start']), bis=i18n.stunde(s['end'])),
             f"{s['wind_min']}–{s['wind_max']} kn", f"{wings} m²"]
    if s.get("geo"):
        teile.append(T(QUAL_LABEL.get(s["quality"], s["quality"])))
    # Jeder Teil bleibt beisammen (2.1.0): am Handy brach „5 / 6.5 m²“ sonst
    # zwischen Zahl und Einheit um. Umgebrochen wird nur an den Punkten.
    text = " · ".join(f"<span class='nw'>{_esc(x)}</span>" for x in teile)
    weitere = len(t["sessions"]) - 1
    if weitere:
        text += (" <span class='mehrsess'>"
                 + TN("+{n} weitere Session", "+{n} weitere Sessions", weitere) + "</span>")
    return text


def _kopf_pills(t: dict, args) -> str:
    """Die Plaketten im zugeklappten Ziel — nur, was über Fahren oder
    Nichtfahren entscheidet: Fahrt, amtliche Warnungen, Thermik, Tide, und die
    Zahl der Hinweise (Schutzgebiete, Shorebreak, Pin an Land), die
    aufgeklappt im Wortlaut stehen."""
    spot = t["spot"]
    pills = [f"<span class='pill p-{'flat' if t['drive_ok'] else 'chop'}'>"
             f"{T('Fahrt lohnt') if t['drive_ok'] else T('Fahrt grenzwertig')}</span>"]
    alerts = (getattr(args, "_alerts", {}) or {}).get(spot["id"], [])
    if alerts:
        lvl = "p-alert" if any(a.get("level", 0) >= 3 for a in alerts) else "p-chop"
        pills.append(f"<span class='pill {lvl}'>{TN('{n} Warnung', '{n} Warnungen', len(alerts))}</span>")
    if spot.get("thermal"):
        pills.append(f"<span class='pill p-ok'>{T('Thermik')}</span>")
    if (spot.get("_tide") or {}).get("aktiv"):
        pills.append(f"<span class='pill p-info'>{T('Tide')}</span>")
    hinweise = (len((getattr(args, "_protected", {}) or {}).get(spot["id"], []))
                + (1 if _shorebreak_zeile(spot) else 0)
                + (1 if spot["id"] in (getattr(args, "_an_land", None) or ()) else 0))
    if hinweise:
        pills.append(f"<span class='pill p-info'>{TN('{n} Hinweis', '{n} Hinweise', hinweise)}</span>")
    return "".join(pills)


def _fahrt(spot, drive_h: float) -> str:
    """„3.4 h Fahrt“ mit der Herkunft als Tooltip — geroutet oder geschätzt.

    Fertiges Markup: der Text darunter wird nicht mehr escaped. Alles darin
    ist entweder eine Zahl aus der Berechnung oder ein fester Satz von hier —
    nichts davon kommt aus Katalog, Netz oder Eingabe. Vorher stand das
    <span> wörtlich im Report, weil es zweimal durch _esc lief."""
    woher = (T("Luftlinie mal Umwegfaktor — nicht geroutet")
             if spot.get("drive_source") != "Routing" else
             T("{km} km Straße, über OSRM geroutet", km=f"{spot.get('road_km', 0):.0f}"))
    # Mit und ohne „(geschätzt)“ als zwei ganze Texte statt eines angehängten Stücks
    fahrt_text = (T("{h} h Fahrt", h=f"{drive_h:.1f}") if spot.get("drive_source") == "Routing" else
                  T("{h} h Fahrt (geschätzt)", h=f"{drive_h:.1f}"))
    return f"<span title='{_esc(woher)}'>{fahrt_text}</span>"


def _umweg(cfg) -> float:
    """Der Umwegfaktor der Schätzung (Straße zu Luftlinie) aus der config."""
    try:
        f = float((cfg.get("drive") or {}).get("detour_factor") or 1.22)
    except (TypeError, ValueError):
        return 1.22
    return f if math.isfinite(f) and f > 0 else 1.22


def _strecke(spot, cfg) -> str:
    """Die Fahrstrecke eines Spots als Zelle: geroutet „1026 km“, sonst
    „≈ 561 km“ mit der Luftlinie im Tooltip (seit 2.4.0)."""
    km = spot.get("road_km", spot.get("dist_km", 0)) or 0
    if spot.get("drive_source") == "Routing":
        return f"<span title='{_esc(T('über OSRM geroutet'))}'>{km:.0f} km</span>"
    titel = T("geschätzt: {luft} km Luftlinie × {faktor}, nicht geroutet",
              luft=f"{spot.get('dist_km', 0):.0f}", faktor=i18n.zahl(_umweg(cfg), 2))
    return f"<span title='{_esc(titel)}'>≈&#8239;{km:.0f} km</span>"


def _trip_article(i: int, t: dict, cfg, args, home, favorit: dict | None = None) -> str:
    """Ein Ziel als Klappe (seit 1.20.0): zugeklappt die Antwort in zwei Zeilen
    — Name, Fahrt, beste Session, die entscheidenden Plaketten —, aufgeklappt
    alles, was bis 1.19.2 immer dastand: Kommentar, Warnungen im Wortlaut,
    Tide, jede Session, Stellplätze, Links, Katalognotiz.

    Steht als eigene Funktion da, weil der Report die Ziele an mehreren
    Stellen zeigt: die besten drei ganz oben (seit 2.3.0 vor der Karte), alle
    weiteren hinter einer Klappe unter dem Stundenraster — und seit 2.4.0 die
    Favoriten vor allem anderen. Dort steht statt des Rangs ein Stern
    (`favorit` ist der Eintrag aus cli.favoriten_liste), daneben der Platz
    unter den Zielen der Suche oder, dass der Spot außerhalb lag.
    """
    teile: list[str] = []
    spot = t["spot"]
    if favorit is not None:
        kennung = f"fav-{i}"
        rang = f"<span class='rank fav' title='{_esc(T('Favorit'))}'>★</span>"
        stern = ""
        if favorit.get("rang"):
            zusatz = (f"<span class='pill p-info' title='{_esc(T('Platz {n} unter den Zielen der Suche', n=favorit['rang']))}'>"
                      f"{T('Platz {n}', n=favorit['rang'])}</span>")
        elif favorit.get("grund"):
            zusatz = (f"<span class='pill p-info' title='{_esc(favorit['grund'])}'>"
                      f"{T('außerhalb der Suche')}</span>")
        else:
            zusatz = ""
    else:
        kennung, rang, zusatz = f"ziel-{i}", f"<span class='rank'>{i}</span>", ""
        stern = (f"<span class='favstern' title='{_esc(T('Favorit'))}'>★</span>"
                 if spot["id"] in (getattr(args, "_fav_ids", None) or ()) else "")
    fahrt = _fahrt(spot, t["drive_h"])
    regel = (T("Regel erlaubt {h} h", h=f"{t['acceptable_drive_h']:.1f}") if t["drive_ok"] else
             T("deine Regel gibt nur {h} h her", h=f"{t['acceptable_drive_h']:.1f}"))
    pb = t.get("plan_b")
    plan_b_html = (" · " + T("Plan B: {name} ({km} km, {h} h Wasser)", name=_esc(pb['name']), km=pb['km'],
                             h=f"{pb['hours']:.0f}")
                   if pb else "")
    tage = len(t["days"])
    teile.append(f"<details class='trip' id='{kennung}'><summary>"
                 f"{rang}"
                 f"<span class='name'>{stern}{_esc(spot['name'])}</span>"
                 f"<span class='pills'>{zusatz}{_rule_pills(spot)}{_kopf_pills(t, args)}</span>"
                 f"<span class='meta'>{fahrt} · "          # enthält bewusst Markup, siehe oben
                 f"{TN('{h} h Wasser an {n} Tag', '{h} h Wasser an {n} Tagen', tage, h=format(t['total_hours'], '.0f'))}</span>"
                 f"<span class='kern'>{_kern(t)}</span>"
                 f"</summary><div class='ausfuehrlich'>")
    # Aufgeklappt zuerst das, was der Kopf weglässt: die Fahrzeitregel, Tage
    # am Stück, Plan B.
    am_stueck = " · " + T("{n} am Stück", n=t['run_len']) if t.get('run_len', 0) > 1 else ""
    teile.append(f"<div class='metazeile'>{regel}{am_stueck}{plan_b_html}</div>")
    if favorit is not None and favorit.get("grund") and not favorit.get("rang"):
        teile.append("<div class='metazeile'>"
                     + T("Nicht in der Suche: {grund} — als Favorit trotzdem gerechnet.", grund=_esc(favorit["grund"]))
                     + "</div>")
    teile.append(f"<div class='kommentar'>{kommentar_kasten(spot['id'], spot.get('comment', ''))}</div>")
    flags = []
    for a in (getattr(args, '_alerts', {}) or {}).get(spot['id'], [])[:3]:
        lvl = 'p-alert' if a.get('level', 0) >= 3 else 'p-chop'
        flags.append(f"<span><span class='pill {lvl}'>{T('Warnung {stufe}', stufe=_esc(T(a.get('level_name', ''))))}</span> "
                     f"{_esc(T(a.get('event', '')))} · {_esc(a.get('area', ''))}</span>")
    for pa in (getattr(args, '_protected', {}) or {}).get(spot['id'], [])[:3]:
        flags.append(f"<span><span class='pill p-info'>{_esc(T(pa.get('kind', 'Schutzgebiet')))}</span> "
                     f"{T('{name} — Regeln vor Ort prüfen', name=_esc(T(pa.get('name', ''))))}</span>")
    if spot.get('thermal'):
        flags.append(f"<span><span class='pill p-ok'>{T('Thermikspot')}</span> {_esc(spot['thermal'].get('note', ''))}</span>")
    if _shorebreak_zeile(spot):
        flags.append(_shorebreak_zeile(spot))
    if _instagram_zeile(spot):
        flags.append(_instagram_zeile(spot))
    if spot['id'] in (getattr(args, '_an_land', None) or ()):
        flags.append(f"<span><span class='pill p-chop'>{T('Pin an Land?')}</span> "
                     + T("kein Wasser innerhalb von 3 km um die Koordinate — auf der Prüfseite nachsehen; "
                         "die Windlage ist ohne Ufergeometrie bewertet")
                     + "</span>")
    if flags:
        teile.append("<div class='flags'>" + "".join(flags) + "</div>")
    teile.append(_tide_zeile(spot, tage=_tage_der_suche(args)))
    teile.append("<div class='sess'>")
    for s in t["sessions"]:
        ws = s["wings"]
        wings = f"{ws[0]:g}–{ws[-1]:g}" if len(ws) > 2 else " / ".join(f"{w:g}" for w in ws)
        note = ", ".join(i18n.uebersetzt(w) for w in s["warn"]) or T(QUAL_LABEL.get(s["quality"], ""))
        lage = ""
        if s.get("geo"):
            pill = LAGE_PILL.get(s["quality"], "chop")
            lage = (f"<span class='pill p-{pill}'>{_esc(T(QUAL_LABEL.get(s['quality'], s['quality'])))}</span> ")
        geo_num = ""
        if s.get("fetch_km") is not None:
            # Mit und ohne Wellenmodell je ein ganzer Text statt angehängter Stücke
            aus_modell = s.get("wave_quelle") == "Wellenmodell"
            geo_titel = (T("Anlauflänge aus der Ufergeometrie; Welle aus dem Wellenmodell") if aus_modell else
                         T("Anlauflänge aus der Ufergeometrie; Welle aus Anlauf und Wind geschätzt"))
            km, m = f"{s['fetch_km']:.0f}", f"{s['wave_m']:.2f}"
            geo_text = (T("Anlauf {km} km · Welle {m} m (Wellenmodell)", km=km, m=m) if aus_modell else
                        T("Anlauf {km} km · Welle {m} m", km=km, m=m))
            geo_num = (f"<span class='geo' title='{_esc(geo_titel)}'>{geo_text}</span>"
                       f"{' · ' if note else ' '}")
        agree, spread_max = s.get("agree", 1.0), s.get("spread_max", 0.0)
        namen = ", ".join(s.get("modelle") or []) or T("die Modelle")
        if agree < 0.75 or spread_max >= 8:
            uneinig = T("{namen} liegen deutlich auseinander (bis {kn} kn)", namen=namen, kn=f"{spread_max:.0f}")
            lage += f"<span class='pill p-chop' title='{_esc(uneinig)}'>{T('Modelle uneinig')}</span> "
        elif agree >= 0.95 and spread_max < 5:
            einig = T("{namen} liegen nah beieinander", namen=namen)
            lage += f"<span class='pill p-ok' title='{_esc(einig)}'>{T('Modelle einig')}</span> "
        if s.get("modell"):
            lage += _modell_pill(s)
        if s.get("thermal"):
            sicher = s.get("sicherheit") or {}
            verl = (" · " + T("{p} % verlässlich", p=f"{sicher['p'] * 100:.0f}") if sicher.get("p") is not None else "")
            erfahrung = T("Erfahrungswert aus dem Katalog, kein Modellwind. Die Verlässlichkeit des Spots "
                          "geht statt des Ensembles gedämpft in die Reihenfolge ein")
            lage += (f"<span class='pill p-info' title='{_esc(erfahrung)}'>{T('Thermik angenommen')}{verl}</span> ")
        else:
            lage += _ensemble_pill(s.get("ens"))
        extra = ""
        if s.get("tide_lage"):
            # Lage zu Beginn der Session und die Scheitel, die in sie fallen.
            von, bis = s["start"].strftime("%H:%M"), s["end"].strftime("%H:%M")
            drin = [f"{T(TIDE_KURZ.get(k, k))} {v}" for k, v in s.get("tides") or [] if von <= v <= bis]
            # LAGE_TEXT ist eine Tabelle aus tide.py — übersetzt wird beim Gebrauch
            extra += " · " + T("Tide {lage}", lage=T(gezeiten.LAGE_TEXT.get(s["tide_lage"], s["tide_lage"])))
            if drin:
                extra += " · " + " → ".join(drin[:3])
        elif s.get("tides"):
            extra += " · " + " ".join(f"{T(TIDE_KURZ.get(k, k))} {v}" for k, v in s["tides"][:4])
        if s.get("sst") is not None:
            extra += " · " + T("Wasser {grad} °C, {anzug}", grad=f"{s['sst']:.0f}", anzug=wetsuit_label(s['sst']))
        teile.append(
            f"<div class='srow' style='grid-column:1/-1'>"
            f"<span class='when'>{_tag(s['start'])} "
            f"{T('{von}–{bis} Uhr', von=i18n.stunde(s['start']), bis=i18n.stunde(s['end']))}</span>"
            f"<span class='num'>{s['hours']} h</span>"
            f"<span class='num'>{s['wind_min']}–{s['wind_max']} kn ({s['gust_max']})</span>"
            f"<span class='num'>{_esc(_richtungen(s['dirs']))} · {wings} m²</span>"
            f"<span class='note'>{lage}"
            f"{_wasser_pill(s['water'])} "
            f"{geo_num}{_esc(note)} · {s['temp']} °C{_esc(extra)}</span></div>")
    teile.append(_camping_block(t.get("camping"), spot, home))
    teile.append(f"</div><div class='links'>{_links(spot, home)}"
                 f"<span style='color:var(--muted)'>{_esc(spot.get('notes', ''))}</span></div>"
                 "</div></details>")
    return "".join(teile)


# ── Favoriten (seit 2.4.0) ──────────────────────────────────────────────────
# Wann eine Stunde gar nicht zählen kann, egal wie der Wind ist: vorbei, vor dem
# gewählten Start, nachts (`veto_art` aus score.score_hours).
OHNE_CHANCE = ("vorbei", "vor_start", "nacht")


def _warum_nichts(e: dict, cfg, args) -> str:
    """Ein Satz, warum ein Favorit im Zeitraum keine Session hat — als Text,
    escaped wird beim Einsetzen. Der Grund einer gesperrten Stunde ist ihr
    eigener (`veto`, ein Text aus TD()), also in jeder Sprache des Reports."""
    rows = e.get("rows")
    if not rows:
        return T("Keine Vorhersage für diesen Spot.")
    nights = getattr(args, "nights", 0) or 0
    if e.get("n_sessions") and nights:
        return T("Sessions gibt es, aber keine {n} Tage am Stück.", n=nights + 1)
    tag = [r for r in rows if r.get("veto_art") not in OHNE_CHANCE]
    if not tag:
        return T("Im Zeitraum keine Stunde bei Tageslicht.")
    beste = max(tag, key=lambda r: r.get("wind") or 0)
    lo, _hi = quiver_range(cfg)
    kn, wann = f"{beste.get('wind') or 0:.0f}", _stunde(beste["t"])
    if (beste.get("wind") or 0) < lo:
        return T("Höchstens {kn} kn ({wann}) — dein Quiver fängt bei {lo} kn an.", kn=kn, wann=wann, lo=f"{lo:.0f}")
    # Wo Wind wäre: der häufigste Grund, der die Stunden sperrt — in den Worten
    # der stärksten so gesperrten Stunde („31 kn — kein passender Wing im
    # Quiver“, „außerhalb des Tidenfensters (…)“, „Gewitter gemeldet“ …)
    gesperrt = [r for r in tag if (r.get("wind") or 0) >= lo and r.get("veto")]
    if gesperrt:
        zahl: dict[str, int] = {}
        for r in gesperrt:
            zahl[r.get("veto_art") or ""] = zahl.get(r.get("veto_art") or "", 0) + 1
        art = max(zahl, key=lambda k: zahl[k])
        beleg = max((r for r in gesperrt if (r.get("veto_art") or "") == art), key=lambda r: r.get("wind") or 0)
        # Wind und Uhrzeit dieser Stunde, nicht der windigsten überhaupt —
        # sonst stünde der Grund einer Stunde neben den Zahlen einer anderen.
        return T("Wind reicht zeitweise ({kn} kn, {wann}), aber: {grund}.",
                 kn=f"{beleg.get('wind') or 0:.0f}", wann=_stunde(beleg["t"]),
                 grund=str(i18n.uebersetzt(beleg["veto"])))
    return T("Wind reicht zeitweise ({kn} kn, {wann}), aber nicht lange oder gut genug für eine Session.",
             kn=kn, wann=wann)


def _fav_leer(n: int, e: dict, cfg, args, home) -> str:
    """Ein Favorit ohne Session: Stern, Name, Fahrt, warum nicht — und die
    Absprünge (Windy, Route …), um selbst nachzusehen. Keine Klappe: es gibt
    nichts aufzuklappen."""
    spot = e["spot"]
    zusatz = (f"<span class='pill p-info' title='{_esc(e['grund'])}'>{T('außerhalb der Suche')}</span>"
              if e.get("grund") else "")
    fahrt = _fahrt(spot, spot["drive_h"]) if spot.get("drive_h") is not None else ""
    return (f"<div class='trip favleer' id='fav-{n}'><div class='kopf'>"
            f"<span class='rank fav' title='{_esc(T('Favorit'))}'>★</span>"
            f"<span class='name'>{_esc(spot['name'])}</span>"
            f"<span class='pills'>{zusatz}{_rule_pills(spot)}</span>"
            f"<span class='meta'>{fahrt}</span>"
            f"<span class='kern'>{_esc(_warum_nichts(e, cfg, args))}</span>"
            f"</div><div class='links'>{_links(spot, home)}</div></div>")


def _favoriten_block(cfg, args, home) -> str:
    """Der Abschnitt „Favoriten“ vor den besten drei (seit 2.4.0): je Favorit
    in der Reihenfolge der Liste sein Ziel wie unter den besten drei — oder,
    warum es im Zeitraum nichts wird."""
    liste = getattr(args, "_favoriten", None) or []
    if not liste:
        return ""
    teile = [f"<h2>{T('Favoriten')}</h2>",
             "<p class='sub favhinweis'>"
             + T("Immer gerechnet, auch außerhalb des Radius — in der Reihenfolge deiner Liste.") + "</p>"]
    for n, e in enumerate(liste, 1):
        teile.append(_trip_article(n, e["trip"], cfg, args, home, favorit=e) if e.get("trip")
                     else _fav_leer(n, e, cfg, args, home))
    return "".join(teile)


THERMIK_ORANGE = (217, 138, 43)
THERMIK_ERSTICKT = "rgba(92,116,128,.42)"


def _thermik_zelle(p: float, im_fenster: bool) -> str:
    """Drei Zustände, drei Farben — die mittlere ist die interessante.

    Außerhalb des Fensters ist die Zelle blass wie im Hauptraster. Innerhalb
    zeigt ein Orangeton das Potenzial. Und eine Zelle, deren Fenster offen ist,
    deren Potenzial aber auf null steht, bekommt ein eigenes Grau: dort wäre
    heute Thermik fällig, und der Gradientwind oder die Grundströmung erstickt
    sie. Das steht in keiner anderen Darstellung des Reports.
    """
    if not im_fenster:
        return "var(--surface-2)"
    if p <= 0.02:
        return THERMIK_ERSTICKT
    r, g, b = THERMIK_ORANGE
    a = 0.16 + 0.84 * min(p / 1.15, 1.0) ** 1.1
    return f"rgba({r},{g},{b},{a:.2f})"


def _thermik_raster(all_rows, cfg, home) -> str:
    """Eigenes Stundenraster nur für die Thermikspots.

    Das Hauptraster färbt nach Güte oder Knoten und zeigt damit, was die
    Modelle sagen. Genau dort liegen die Thermikspots aber daneben. Dieses
    Raster färbt nach dem Thermikpotenzial und beantwortet die andere Frage:
    wann läuft es wo, und wo ist das Fenster heute tot?

    Anders als die Liste darüber hängt es nicht an den Zielen, sondern an den
    Stunden — ein Spot, an dem die Modelle keine einzige fahrbare Stunde sehen,
    steht hier trotzdem. Das ist der Sinn der Sache.
    """
    from . import thermik

    zeilen = []
    for spot, rows in all_rows.values():
        th = spot.get("thermal")
        if not th or not rows:
            continue
        if not thermik.gilt_heute(th, rows[0]["t"].month):
            continue
        beste = max((r.get("thermik_tag") or 0.0) for r in rows)
        zeilen.append((beste, spot, th, rows))
    if not zeilen:
        return ""
    zeilen.sort(key=lambda z: (-z[0], z[1]["name"]))

    ref = zeilen[0][3]
    axis_days, axis_ticks = _hour_axis(ref)
    teile = ["<p class='sub'>" + T("Dieselben Stunden wie im großen Raster, aber nach dem "
                                   "Thermikpotenzial eingefärbt statt nach dem Modellwind. Nur Spots mit "
                                   "hinterlegtem Thermikwissen, die in diesem Monat Saison haben — sortiert "
                                   "nach dem besten Tag.") + "</p>",
             "<p class='wischen'>" + T("Seitlich wischen — die Spalten sind die Stunden.") + "</p>",
             "<div class='scroll' style='padding:12px' id='thraster'>"]
    if axis_days:
        teile.append(axis_days)
        teile.append(axis_ticks)

    # Die festen Teile der Tooltips je Raster einmal übersetzt, nicht je Zelle
    stunde_titel = functools.lru_cache(maxsize=None)(_stunde)
    ausserhalb = T("außerhalb des Thermikfensters")
    erstickt = T("Fenster offen, heute erstickt — Gegenwind oder Grundströmung")
    angenommen = 0
    for pos, (_beste, spot, th, rows) in enumerate(zeilen):
        if pos and pos % 12 == 0 and axis_ticks and len(rows) == len(ref):
            teile.append(axis_ticks)
        von, bis = float(th.get("from", 12)), float(th.get("to", 18))
        zellen = []
        for r in rows:
            stunde = r["t"].hour
            drin = von <= stunde < bis
            p = float(r.get("thermik_p") or 0.0)
            an = bool(r.get("thermal"))
            angenommen += 1 if an else 0
            titel = stunde_titel(r["t"]) + " · "
            if not drin:
                titel += ausserhalb
            elif p <= 0.02:
                titel += erstickt
            else:
                titel += T("Potenzial {p}", p=f"{p:.0%}") + " · "
                titel += (T("angenommen {kn} kn", kn=f"{r['wind']:.0f}") if an
                          else T("Modell {kn} kn, keine Annahme", kn=f"{r['wind']:.0f}"))
            klassen = "cell" + (" tan" if an else "") + (" dstart" if stunde == 0 else "")
            zellen.append(f"<div class='{klassen}' style='background:{_thermik_zelle(p, drin)}' "
                          f"title=\"{_esc(titel)}\"></div>")
        teile.append(
            f"<div class='hm'><div class='hmname'>"
            f"<a href='{_windy(spot)}' target='_blank' rel='noopener' "
            f"title='{_esc(T('Wind und Vorhersage auf Windy'))}'>{_esc(spot['name'])}</a>"
            f"<span class='thermname'>{_esc(th.get('name', T('Thermik')))}</span></div>"
            f"<div class='hmcells' style='grid-template-columns:repeat({len(rows)},1fr)'>"
            f"{''.join(zellen)}</div></div>")
    teile.append("</div>")

    teile.append(
        "<div class='hmlegend'>"
        f"<span><span class='swatch' style='background:{_thermik_zelle(0.25, True)}'></span>{T('schwach')}</span>"
        f"<span><span class='swatch' style='background:{_thermik_zelle(0.7, True)}'></span>{T('ordentlich')}</span>"
        f"<span><span class='swatch' style='background:{_thermik_zelle(1.15, True)}'></span>{T('voll')}</span>"
        f"<span><span class='swatch' style='background:{THERMIK_ERSTICKT}'></span>"
        f"{T('Fenster offen, heute erstickt')}</span>"
        "<span><span class='swatch' style='background:var(--surface-2)'></span>"
        f"{T('außerhalb des Fensters')}</span>"
        "<span><span class='swatch' style='outline:1.5px solid rgba(122,66,10,.85);"
        "outline-offset:-1.5px'></span>"
        + T("Annahme greift — der Wind im Report kommt aus der Thermik, nicht aus dem Modell")
        + "</span></div>")
    ohne = sum(1 for _b, _s, th, _r in zeilen if not th.get("typical_kn"))
    if ohne:
        teile.append("<p class='note' style='margin:6px 0 0'>"
                     + T("Bei {n} dieser Spots ist belegt, dass es dort Thermik gibt, aber keine Quelle "
                         "nennt eine Stärke. Ihre Zeilen zeigen das Potenzial, tragen aber nie einen "
                         "Rahmen — dort wird nichts angenommen.", n=ohne)
                     + "</p>")
    return _abschnitt(T("Wann die Thermik läuft"), T("{n} Thermikspots, Stunde für Stunde", n=len(zeilen)),
                      "".join(teile), "thermikraster")


def _thermik_block(trips, cfg, args, home) -> str:
    """Thermikziele als eigene Liste — sie folgen anderen Regeln als der Rest.

    An der Ora, am Malojawind oder am Maestral entscheidet nicht die
    Großwetterlage, sondern ob die Sonne scheint und ob ein Gegenwind bläst.
    Solche Spots gehen im allgemeinen Ranking unter: das Modell sieht dort oft
    5 kn, wo tatsächlich 18 stehen. Deshalb eine eigene Liste, nach dem
    Thermikpotenzial des besten Tages sortiert statt nach dem Gesamtscore.

    Aufgenommen wird nur, wofür im Katalog Thermikwissen hinterlegt ist, und
    was im laufenden Monat überhaupt Saison hat.
    """
    kandidaten = []
    for platz, t in enumerate(trips, 1):
        spot = t["spot"]
        th = spot.get("thermal")
        if not th:
            continue
        # Die Schwelle liegt tief, weil der Balken die Schwäche selbst zeigt:
        # seit 1.5.2 ist das Potenzial ein Tagesmittel mal Verlässlichkeit und
        # liegt damit selten über 0,9, wo vorher fast jeder sonnige Tag auf 1,0
        # kam. Die Liste ist ohnehin auf zehn begrenzt und absteigend sortiert
        # — ein schwacher Kandidat erscheint nur, wenn es keinen besseren gibt.
        sessions = [x for x in t["sessions"] if x.get("thermal") or x.get("thermik_p", 0) > 0.15]
        if not sessions:
            continue
        beste = max(sessions, key=lambda x: (x.get("thermik_p", 0), x["score"]))
        kandidaten.append((beste.get("thermik_p", 0.0), platz, t, beste, th))
    if not kandidaten:
        return ""
    kandidaten.sort(key=lambda x: (-x[0], x[1]))

    zeilen = []
    for p, platz, t, beste, th in kandidaten[:10]:
        spot = t["spot"]
        angenommen = beste.get("thermal")
        staerke = (T("{kn} kn erwartet", kn=f"{th['typical_kn']:.0f}") if th.get("typical_kn")
                   else T("keine belegte Stärke"))
        balken = int(round(min(1.0, p) * 10))
        verl = float(th.get("reliability", 0.6))
        von, bis = i18n.stunde(th.get('from', 12)), i18n.stunde(th.get('to', 18))
        titel = T("Thermikpotenzial {p} am {tag} — Mittel über das "
                  "Fenster {von}–{bis} Uhr aus Einstrahlung "
                  "und Gegenwind, mal der Verlässlichkeit des Spots ({verl}). "
                  "Die beste einzelne Stunde käme auf {spitze}",
                  p=f"{p:.0%}", tag=_tag(beste['start']), von=von, bis=bis, verl=f"{verl:.0%}",
                  spitze=f"{beste.get('thermik_spitze', 0.0):.0%}")
        zeilen.append(
            f"<div class='throw'>"
            f"<span class='thname'><a href='{_windy(spot)}' target='_blank' rel='noopener'>"
            f"{_esc(spot['name'])}</a>"
            f"<span class='thwind'>{_esc(th.get('name', T('Thermik')))}</span></span>"
            f"<span class='thbar' title=\"{_esc(titel)}\">"
            f"{'█' * balken}{'·' * (10 - balken)}</span>"
            # Nicht die Session zeigen, sondern das Thermikfenster: die Session
            # läuft oft von morgens bis abends, die Ora erst ab 13 Uhr.
            f"<span class='num'>{_tag(beste['start'])} · "
            f"{T('{von}–{bis} Uhr', von=von, bis=bis)}</span>"
            f"<span class='num'>{staerke}</span>"
            f"<span class='num'>{t['drive_h']:.1f} h</span>"
            f"<span class='note'>"
            + ("<span class='pill p-info'>" + T("Thermik angenommen") + "</span> " if angenommen else "")
            + T("Platz {n} im Gesamtranking", n=platz) + f" · {_esc(th.get('note', ''))}</span></div>")

    ohne_zahl = sum(1 for _, _, _, _, th in kandidaten if not th.get("typical_kn"))
    fuss = ("" if not ohne_zahl else
            "<p class='note' style='margin:8px 0 0'>"
            + T("Bei {n} dieser Spots ist zwar "
                "belegt, dass es dort Thermik gibt, aber keine Quelle nennt eine Stärke. "
                "Dort wird nichts angenommen — der Spot steht nur als Kandidat in der Liste.", n=ohne_zahl)
            + "</p>")

    return _abschnitt(
        T("Thermikziele"), T("{n} Spots mit Thermikwissen", n=len(zeilen)),
        "<p class='sub'>"
        + T("Spots, an denen die Modelle regelmäßig danebenliegen, weil die "
            "Zirkulation kleiner ist als das Rechengitter. Sortiert nach dem Thermikpotenzial "
            "des besten Tages: Einstrahlung und Gegenwind über das ganze Thermikfenster "
            "gemittelt, mal der Verlässlichkeit des Spots.")
        + f"</p><div class='thliste'>{''.join(zeilen)}</div>{fuss}", "thermikziele")


def render(trips, all_rows, dropped, cfg, args, demo: bool = False) -> str:
    now = i18n.datum_zeit(datetime.now())
    # Eine Nonce je Erzeugung: nur Skripte mit ihr laufen — ein Katalogtext,
    # der doch einmal roh in die Seite käme, kennt sie nicht (siehe csp.py).
    nonce = csp.neue_nonce()
    home = cfg["rider"]["home"]            # Startpunkt als Ganzes, für die Routenlinks
    home_name = home["name"]
    parts = []
    parts.append(f"<!doctype html><html lang='{i18n.aktuell()}'><head><meta charset='utf-8'>"
                 f"{csp.meta(nonce)}"
                 f"<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>"
                 f"<title>{T('Wingfoilscout · {now}', now=now)}</title>"
                 f"<link rel='stylesheet' href='https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css' "
                 f"integrity='sha384-c6Rcwz4e4CITMbu/NBmnNS8yN2sC3cUElMEMfP3vqqKFp7GOYaaBBCqmaWBjmkjb' crossorigin='anonymous'>"
                 f"<style>{CSS}{KOMMENTAR_CSS}</style>{csp.skript(nonce, i18n.js_vorspann())}</head><body><div class='wrap'>")
    # Datum und Uhrzeit bleiben beisammen: am Handy brach die Zeile sonst
    # zwischen „3 Oct 2026,“ und „22:32“ um (2.1.0).
    zeitstempel = f"<span class='nw'>{_esc(now)}</span>"
    parts.append(f"<p class='sub'>{T('Wingfoilscout {version} · erstellt {now}', version=__version__, now=zeitstempel)}</p>"
                 f"<h1>{T('Wo lohnt es sich?')}</h1>")
    # Zwei Ansichten (seit 1.20.0): „Einfach“ zeigt je Ziel zwei Zeilen und
    # die Abschnitte nur als Überschrift; „Ausführlich“ klappt alles auf, wie
    # der Report bis 1.19.2 immer aussah. Die Wahl merkt sich der Browser
    # (web/ansicht.js); ohne Skript gilt Einfach, und jede Klappe geht einzeln.
    parts.append(f"<div class='ansicht' role='group' aria-label='{_esc(T('Ansicht'))}'><span>{T('Ansicht')}</span>"
                 f"<button type='button' data-ansicht='einfach' class='an'>{T('Einfach')}</button>"
                 f"<button type='button' data-ansicht='ausfuehrlich'>{T('Ausführlich')}</button></div>")
    parts.append(f"<details class='zu-am-handy' open><summary>{T('Wonach gesucht wurde')}</summary>"
                 "<div class='params'>"
                 f"<span><b>{T('Start')}</b> {_esc(home_name)}</span>"
                 f"<span><b>{T('Radius')}</b> {T('{km} km Fahrstrecke', km=_ohne_null(args.radius))}</span>"
                 f"<span><b>{T('Zeitraum')}</b> {_zeitraum_text(args)}</span>"
                 f"<span><b>{T('Mindestsession')}</b> {cfg['session']['min_hours']:.0f} h</span>"
                 f"<span><b>{T('Quiver')}</b> {'/'.join(str(w['size']) for w in cfg['quiver']['wings'])}</span>"
                 f"<span><b>{T('Wind')}</b> {T('alle Angaben in Knoten')}</span>"
                 f"<span><b>{T('Uhrzeiten')}</b> {T('Ortszeit am Spot')}</span>"
                 + (f"<span><b>{T('Favoriten')}</b> {len(getattr(args, '_favoriten', None) or [])}</span>"
                    if getattr(args, "_favoriten", None) else "")
                 + "</div></details>")

    landesweit = getattr(args, "_alerts_landesweit", None) or {}
    if landesweit:
        # Einmal im Kopf statt an jedem Spot: Warnungen, die keinem Gebiet
        # zuzuordnen sind, weil der Spot kein `region` trägt.
        teile = []
        for land, warnungen in sorted(landesweit.items()):
            ereignisse = sorted({w.get("event") or T("Warnung") for w in warnungen})
            teile.append(f"{_esc(land)}: {len(warnungen)} ({_esc(', '.join(ereignisse[:3]))}"
                         f"{'…' if len(ereignisse) > 3 else ''})")
        parts.append("<div class='banner'>"
                     + T("<b>Amtliche Warnungen ohne Gebietszuordnung</b> — {liste}. Spots ohne "
                         "<code>region</code> im Katalog zeigen sie nicht; wo eine Warnung gilt, "
                         "bei MeteoAlarm nachsehen.", liste=" · ".join(teile))
                     + "</div>")
    # Der Radius ist eine Fahrstrecke (seit 2.4.0 ausdrücklich, gewünscht am
    # 07.10.2026). Wo OSRM keine Route geliefert hat, gilt sie nur nach
    # Schätzung — dann hier einmal, für wie viele Spots der Suche.
    geschaetzt = sum(1 for spot, _ in all_rows.values() if spot.get("drive_source") != "Routing")
    if geschaetzt and not demo:
        parts.append("<div class='banner'>"
                     + T("<b>Fahrstrecke für {n} von {gesamt} Spots nur geschätzt</b> — für sie kam keine Route "
                         "von OSRM (oder „Fahrzeiten routen“ ist aus). Geschätzt wird Luftlinie × {faktor}; die "
                         "echte Strecke kann länger sein als der Radius. Diese Ziele tragen „(geschätzt)“ an der "
                         "Fahrzeit.", n=geschaetzt, gesamt=len(all_rows), faktor=i18n.zahl(_umweg(cfg), 2))
                     + "</div>")
    if demo:
        parts.append("<div class='banner'>"
                     + T("<b>Demo-Lauf mit synthetischen Wetterdaten.</b> "
                         "Diese Zahlen sind erfunden und zeigen nur, wie der Report aussieht. "
                         "Für echte Vorhersagen ohne <code>--demo</code> starten.")
                     + "</div>")

    # ── Trips ────────────────────────────────────────────────────────────────
    # Reihenfolge: die besten drei, die Karte, das Raster, dann der Rest
    # hinter einer Klappe. Die drei Ziele und das Raster sind das, wofür man
    # den Report öffnet; Platz 12 schaut man sich nur an, wenn die ersten drei
    # nichts hergeben. Bis 2.1 stand die Karte vor den besten drei — seit
    # 2.3.0 steht gleich oben, wo es am besten ist, und die Karte zeigt danach,
    # wo das liegt (gewünscht am 04.10.2026).
    # Seit 2.4.0 davor, wenn gewünscht, die Favoriten: Favoriten → die besten
    # drei → Karte (gewünscht am 06.10.2026).
    parts.append(_favoriten_block(cfg, args, home))
    parts.append(f"<h2>{T('Die besten drei') if len(trips) > 3 else T('Beste Ziele')}</h2>")
    if not trips:
        parts.append("<p class='sub'>"
                     + T("Kein Spot im Radius erfüllt deine Kriterien in diesem Zeitraum. "
                         "Radius erhöhen, Zeitraum verlängern oder die Schwellen in der config lockern.")
                     + "</p>")
    for i, t in enumerate(trips[:3], 1):
        parts.append(_trip_article(i, t, cfg, args, home))

    parts.append(_map_block(trips, all_rows, dropped, cfg, args, nonce))
    parts.append(_thermik_block(trips, cfg, args, home))
    parts.append(_thermik_raster(all_rows, cfg, home))
    # ── Heatmap ──────────────────────────────────────────────────────────────
    # Zwei Lesarten derselben Stunden: die Güte beantwortet „lohnt sich das?",
    # die Knoten „welcher Wing?". Ein Umschalter statt zweier Raster
    # untereinander — dieselben Zellen, andere Farbe.
    g = knoten_grenzen(cfg)
    raster: list[str] = []
    raster.append("<div class='hmschalter'>"
                 f"<button type='button' id='f_guete' class='an'>{T('Güte')}</button>"
                 f"<button type='button' id='f_knoten'>{T('Knoten')}</button></div>")
    raster.append("<div class='hmlegend' id='leg_guete'>"
                 f"<span><span class='swatch' style='background:var(--surface-2)'></span>{T('nicht fahrbar')}</span>"
                 f"<span><span class='swatch' style='background:rgba(174,31,104,.35)'></span>{T('geht')}</span>"
                 f"<span><span class='swatch' style='background:rgba(174,31,104,1)'></span>{T('Top')}</span>"
                 f"<span>{T('je Spalte eine Stunde, Tageslicht wie Nacht')}</span></div>")
    raster.append(
        f"<div class='hmlegend' id='leg_knoten' style='display:none'>"
        f"<span><span class='swatch' style='background:{ROT}'></span>{T('unter {kn} kn', kn=format(g['rot_unter'], '.0f'))}</span>"
        f"<span><span class='swatch' style='background:{ORANGE}'></span>{g['rot_unter']:.0f}–{g['gruen_von'] - 1:.0f} kn</span>"
        f"<span><span class='swatch' style='background:{GRUEN}'></span>"
        + T("Wohlfühlband {von}–{bis} kn", von=f"{g['gruen_von']:.0f}", bis=f"{g['gruen_bis']:.0f}") + "</span>"
        f"<span><span class='swatch' style='background:{ORANGE}'></span>"
        f"{g['gruen_bis'] + 1:.0f}–{g['rot_ueber']:.0f} kn</span>"
        + (f"<span><span class='swatch' style='background:{ROT}'></span>"
           f"{g['rot_ueber'] + 1:.0f}–{g['dunkel_ueber']:.0f} kn</span>"
           if g["dunkel_ueber"] > g["rot_ueber"] else "")
        + f"<span><span class='swatch' style='background:{DUNKELROT}'></span>"
          f"{T('über {kn} kn', kn=format(g['dunkel_ueber'], '.0f'))}</span>"
          f"<span>{T('blass = Nacht oder ausgeschlossen')}</span></div>")
    raster.append("<p class='wischen'>" + T("Seitlich wischen — die Spalten sind die Stunden.") + "</p>")
    raster.append("<div class='scroll' style='padding:12px' id='hmraster'>")

    ref = next(iter(all_rows.values()))[1] if all_rows else []
    axis_days, axis_ticks = _hour_axis(ref)
    if axis_days:
        raster.append(axis_days)
        raster.append(axis_ticks)

    # Uhrzeit, Richtung, Score und Tide wiederholen sich Zeile für Zeile: je
    # Wert einmal übersetzt und escaped statt in jeder der bis zu 100 000
    # Zellen. Escaped, weil sie in title="…" stehen: bis 2.1.0 standen sie dort
    # roh, und ein `"` in einer Übersetzung (oder in den Kürzeln der
    # Kompassrose) setzte jeder Zelle eigene Attribute — im Test 552 Zellen mit
    # `onmouseover`, nur die Richtlinie (csp.py) hielt sie still.
    @functools.lru_cache(maxsize=None)
    def stunde_titel(t) -> str:
        return _esc(_stunde(t))

    @functools.lru_cache(maxsize=None)
    def richtung_titel(name) -> str:
        return _esc(name)

    @functools.lru_cache(maxsize=None)
    def score_titel(wert: str) -> str:
        return _esc(T("Score {score}", score=wert))

    @functools.lru_cache(maxsize=None)
    def tide_titel(lage: str) -> str:
        return _esc(" · " + T("Tide {lage}", lage=T(gezeiten.LAGE_TEXT.get(lage, ""))))

    for pos, (spot_id, (spot, rows)) in enumerate(all_rows.items()):
        if pos and pos % 12 == 0 and axis_ticks and len(rows) == len(ref):
            raster.append(axis_ticks)                      # bei langen Listen wiederholen
        n = len(rows)
        # data-kn und data-aus reisen mit, damit der Umschalter die Farben im
        # Browser neu setzen kann, ohne dass der Report zweimal alles enthält.
        cells = "".join(f"<div class='cell{' dstart' if r['t'].hour == 0 else ''}' "
                        f"style='background:{_cell_color(r['score'])}' "
                        f"data-kn='{r['wind']:.0f}'{AUS if r['score'] <= 0 else ''} "
                        f"title=\"{stunde_titel(r['t'])} · {r['wind']:.0f} kn "
                        f"{richtung_titel(r['dir_name'])} · {score_titel(format(r['score'], '.2f'))}"
                        f"{tide_titel(r['tide_lage']) if r.get('tide_lage') else ''}"
                        f"{' · ' + _esc(r['veto']) if r['veto'] else ''}\"></div>" for r in rows)
        # Name führt auf Windy, die Kilometerangabe auf die Route: beide
        # Fragen („wie wird der Wind?" und „wie weit ist das?") haben damit je
        # ein eigenes Ziel, ohne dass die Zeile eine zweite Zeile braucht.
        weit = (f"<a class='hmkm' href='{_maps_route(spot, home)}' target='_blank' "
                f"rel='noopener' title='{_esc(T('Route in Google Maps'))}'>{spot['road_km']:.0f} km</a>"
                if spot.get("road_km") else "")
        raster.append(f"<div class='hm'>"
                     f"<div class='hmname'>"
                     f"<a href='{_windy(spot)}' target='_blank' rel='noopener' "
                     f"title='{_esc(T('Wind und Vorhersage auf Windy'))}'>{_esc(spot['name'])}</a>{weit}</div>"
                     f"<div class='hmcells' style='grid-template-columns:repeat({n},1fr)'>{cells}</div></div>")
    raster.append("</div>")
    raster.append(_raster_schalter(g, nonce))
    parts.append(_abschnitt(T("Stundenraster"),
                            T("{n} Spots, Stunde für Stunde — Güte oder Knoten", n=len(all_rows)),
                            "".join(raster), "raster"))

    weitere = trips[3:]
    if weitere:
        parts.append(_abschnitt(T("Weitere Ziele"), T("Platz 4 bis {n}", n=len(trips)),
                                "".join(_trip_article(i, t, cfg, args, home) for i, t in enumerate(weitere, 4)),
                                "weitere"))

    # ── Alle Sessions ────────────────────────────────────────────────────────
    sessions = [s for t in trips for s in t["sessions"]]
    sessions.sort(key=lambda s: -s["score"])
    if sessions:
        parts.append(_sessions_tabelle(sessions, nonce))

    # ── Ausgeschlossen ───────────────────────────────────────────────────────
    if dropped:
        # Seit 2.4.0 die Fahrstrecke wie überall sonst — bis 2.3.0 stand hier
        # die Luftlinie, im Grund daneben die Strecke: zwei Zahlen für einen
        # Spot („682 km“ und „1026 km — außerhalb des Radius“, gemeldet am
        # 07.10.2026). Geschätzt (nicht geroutet) mit „≈“ und Tooltip.
        zeilen = [f"<p class='wischen'>{T('Seitlich wischen.')}</p><div class='scroll'><table><thead><tr>"
                  f"<th>{T('Spot')}</th><th>{T('Fahrstrecke')}</th><th>{T('Grund')}</th></tr></thead><tbody>"]
        for spot, reason in sorted(dropped, key=lambda x: x[0].get("road_km", x[0]["dist_km"])):
            zeilen.append(f"<tr><td>{_esc(spot['name'])}</td>"
                          f"<td class='n'>{_strecke(spot, cfg)}</td><td>{_esc(reason)}</td></tr>")
        zeilen.append("</tbody></table></div>")
        parts.append(_abschnitt(T("Nicht berücksichtigt"), T("{n} Spots, jeweils mit Grund", n=len(dropped)),
                                "".join(zeilen), "ausgeschlossen"))

    wx = cfg["weather"]
    regeln = (
        (T("Gewitter"), "weather_code",
         T("Code {codes} (Gewitter, mit und ohne Hagel) — die Stunde fällt komplett raus. Stunden bis "
           "{h} h davor und danach werden auf 40 % abgewertet und in der Session vermerkt.",
           codes=", ".join(str(c) for c in wx['thunder_codes']), h=wx.get('thunder_shadow_h', 0))),
        (T("Gewitterneigung"), "cape",
         T("Ab {warn} J/kg Abwertung auf 70 % und Hinweis, ab {schlecht} J/kg auf 35 %. "
           "CAPE warnt dort, wo das Modell noch keine Gewitterstunde ausgibt.",
           warn=wx['cape_warn'], schlecht=wx['cape_bad'])),
        (T("Regen"), "precipitation",
         T("Unter {weich} mm/h ohne Abzug, dann linear fallend bis {hart} mm/h, darüber auf 20 %.",
           weich=wx['rain_soft_mm'], hart=wx['rain_hard_mm'])),
        (T("Lufttemperatur"), "temperature_2m",
         T("Außerhalb {min}–{max} °C fällt die Stunde raus. Innerhalb von 3 °C zur Grenze Abwertung auf 80 %.",
           min=wx['air_temp_min'], max=wx['air_temp_max'])),
        (T("Wassertemperatur"), "sea_surface_temperature",
         T("Unter {min} °C fällt die Stunde raus — aber nur mit <code>--marine</code> und nur an Meer- und "
           "Lagunenspots. Für Binnenseen gibt es keine Quelle.", min=wx['water_temp_min'])),
        (T("Tide"), "sea_level_height_msl",
         T("Wasserstand aus dem Marine-Modell (8-km-Raster, keine amtliche Tafel) — an Meer- und "
           "Lagunenspots mit Tidenhub, oder wo <code>tidal: true</code> im Katalog steht. Ohne "
           "Tidenfenster reine Anzeige; mit <code>tide: fahrbar</code> fallen Stunden außerhalb "
           "des Fensters raus.")),
        (T("Tageslicht"), "sunrise / sunset",
         T("30 min nach Sonnenaufgang bis 30 min vor Sonnenuntergang.")),
        (T("Bewölkung"), "cloud_cover",
         T("Wird geholt, aber nicht bewertet — für die Session ist sie egal.")),
    )
    parts.append(_abschnitt(T("Wie das Wetter bewertet wird"), T("die Regeln hinter der Güte"),
                 f"<p class='wischen'>{T('Seitlich wischen.')}</p><div class='scroll'><table class='wx'><thead><tr>"
                 f"<th>{T('Größe')}</th><th>{T('Quelle')}</th><th>{T('Regel')}</th></tr></thead><tbody>"
                 + "".join(f"<tr><td>{groesse}</td><td class='n'>{quelle}</td><td>{regel}</td></tr>"
                           for groesse, quelle, regel in regeln)
                 + "</tbody></table></div>", "bewertung"))

    # Der Fuß Satz für Satz — ein Schlüssel je Satz, verbunden mit Leerzeichen
    fuss = " ".join((
        T("Windlage und Wellenhöhe stammen, wo eine Fetch-Rose vorliegt, aus der "
          "OpenStreetMap-Ufergeometrie: Anlauflänge über Wasser in 36 Richtungen, daraus "
          "ablandig / sideshore / auflandig und die Wellenhöhe nach der fetch-begrenzten "
          "SPM-Beziehung."),
        T("Das ist eine Näherung — sie unterstellt gleichbleibenden Wind und rechnet mit U10."),
        T("Von Hand gepflegte Sektoren in <code>spots.yaml</code> haben Vorrang."),
        T("Wind, Böen, Temperatur, Regen, CAPE und Wettercode von "
          "<a href='https://open-meteo.com'>Open-Meteo</a> (freier, nicht-kommerzieller Tarif)."),
        T("Windrichtungssektoren, Wasserzustand, Seegras und Stehbereich stammen aus "
          "<code>spots.yaml</code> — von Hand gepflegt und noch unverifiziert."),
        T("Fahrzeit ist geroutet, wo OSRM antwortet, sonst aus der Luftlinie geschätzt — "
          "welches von beidem, steht bei jedem Ziel im Tooltip der Fahrzeit."),
        T("Alle Windangaben in Knoten, alle Uhrzeiten in der Ortszeit des jeweiligen Spots."),
    ))
    parts.append(
        f"<footer>{fuss}</footer>"
        f"<p class='marke'><img src='{LOGO_DATA}' alt='DARK' height='26'>Wingfoilscout {__version__}</p></div>"
        + csp.skript(nonce, f"{KOMMENTAR_JS}\nwindow.WSKommentar.alle();\n{TIDE_JS}\nwindow.WSTide.start();")
        + csp.skript(nonce, "\n" + MOBIL_JS) + csp.skript(nonce, "\n" + ANSICHT_JS) + "</body></html>")
    return "".join(parts)


def write(path: str | Path, content: str) -> Path:
    """Erst daneben, dann umbenennen: die Oberfläche liefert `report.html`
    jederzeit aus, und ein Leser soll den alten oder den neuen Report sehen,
    nie einen halben (Review 25.09., S13)."""
    from .spotedit import schreibe_atomar
    path = Path(path)
    schreibe_atomar(path, content)
    return path


# ── Der Report in allen vier Sprachen (seit 2.3.0) ───────────────────────────
#
# `report.html` ist der Report in der Sprache, in der die Suche lief — die
# Datei, die per AirDrop aufs iPhone wandert und dort ohne Server aufgeht.
# Schreibt eine Suche diesen Report (wingscout.REPORT: jede Suche aus der
# Oberfläche, die Kommandozeile ohne `--out`), legt sie dieselbe Suche
# zusätzlich in allen vier Sprachen in cache/report/ ab, und der Reiter
# „Ziele“ zeigt die Fassung, die zur Spracheinstellung passt. Bis 2.1.0 blieb
# „Ziele“ nach dem Umschalten in der alten Sprache, bis zur nächsten Suche
# (gemeldet am 04.10.2026). Gerechnet wird einmal; die Texte aus der Rechnung
# setzt `i18n.uebersetzt()` je Sprache neu (i18n „Texte in Daten“).
#
# `index.json` nennt die Prüfsumme des report.html, zu dem die Fassungen
# gehören, und die jeder Fassung. Passt etwas nicht — ein Lauf einer älteren
# Version, ein von Hand ersetzter Report, ein abgebrochenes Schreiben —, zeigt
# „Ziele“ report.html, wie es ist.

def fassungen_ordner() -> Path:
    from . import CACHE                    # zur Laufzeit: die Tests legen CACHE um
    return CACHE / "report"


def ist_standard(pfad: str | Path) -> bool:
    """Ist `pfad` der Report, den die Oberfläche zeigt?"""
    from . import REPORT
    try:
        return Path(pfad).resolve() == Path(REPORT).resolve()
    except (OSError, RuntimeError):
        return False


def _pruefsumme(roh: bytes) -> str:
    return hashlib.sha256(roh).hexdigest()


def fassungen_schreiben(haupt: str | Path, rendern) -> list[str]:
    """Den eben geschriebenen Report `haupt` in allen vier Sprachen ablegen.

    `rendern()` liefert den Report in der gerade geltenden Sprache (dieselbe
    Suche, dieselben Daten); die Sprache des Laufs ist `haupt` selbst.
    Rückgabe: die abgelegten Sprachen."""
    from .spotedit import schreibe_atomar
    ordner = fassungen_ordner()
    ordner.mkdir(parents=True, exist_ok=True)
    index = ordner / "index.json"
    # Zuerst den alten Index weg: er nennt den alten Report, und bis der neue
    # dasteht, soll „Ziele“ report.html zeigen, keine halbe Mischung.
    try:
        index.unlink()
    except FileNotFoundError:
        pass
    haupt_roh = Path(haupt).read_bytes()
    eigene = i18n.aktuell()
    pruefsummen = {}
    for sprache in i18n.SPRACHEN:
        datei = ordner / f"report.{sprache}.html"
        if sprache == eigene:
            roh = haupt_roh
            schreibe_atomar(datei, roh.decode("utf-8"))
        else:
            with i18n.in_sprache(sprache):
                schreibe_atomar(datei, rendern())
        pruefsummen[sprache] = _pruefsumme(datei.read_bytes())
    schreibe_atomar(index, json.dumps({"report": _pruefsumme(haupt_roh), "sprachen": pruefsummen},
                                      ensure_ascii=True, indent=1))
    return list(pruefsummen)


def fassung(haupt_roh: bytes, sprache: str) -> bytes | None:
    """Die abgelegte Fassung des Reports `haupt_roh` in `sprache` — None, wenn
    es keine gibt oder sie nicht zu genau diesem Report gehört."""
    if sprache not in i18n.SPRACHEN:
        return None
    ordner = fassungen_ordner()
    try:
        index = json.loads((ordner / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(index, dict) or index.get("report") != _pruefsumme(haupt_roh):
        return None
    erwartet = (index.get("sprachen") or {}).get(sprache) if isinstance(index.get("sprachen"), dict) else None
    if not isinstance(erwartet, str):
        return None
    try:
        roh = (ordner / f"report.{sprache}.html").read_bytes()
    except OSError:
        return None
    return roh if _pruefsumme(roh) == erwartet else None
