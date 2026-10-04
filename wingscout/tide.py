"""Gezeiten am Spot: Hoch- und Niedrigwasser, Lage je Stunde, Tidenfenster.

Die Quelle ist `sea_level_height_msl` aus der Open-Meteo-Marine-API: der
modellierte Wasserstand über dem mittleren Meeresspiegel, stündlich, auf einem
0,08°-Raster (≈ 8 km), Gezeit und Windstau zusammen. Das ist kein amtlicher
Gezeitenkalender: gegenüber der Tafel des nächsten Pegels weichen die Zeiten
ab — wie weit, ist nicht gegen eine Tafel geprüft; in Buchten und
Flussmündungen ist mit mehr zu rechnen als an offener Küste. Für „auflaufend
bis 15 Uhr“ sollte es reichen, für den Fußweg übers Watt nicht.

Drei Stufen im Katalog (`tidal:`):
  true      Tiden gelten hier — auch wenn das Modell wenig Hub zeigt
  false     nie, auch am Meer (Ostsee, Mittelmeer, eine Lagune hinter Schleusen)
  (fehlt)   automatisch: Meer oder Lagune mit modelliertem Hub ab AUTO_HUB_MIN

Ein Tidenfenster (`tide:`) ist freiwillig und macht die Gezeit zur Regel:
    tide:
      fahrbar: hochwasser   # hochwasser | niedrigwasser | auflaufend | ablaufend
      stunden: 2            # ± Stunden um den Scheitel (nur bei hoch-/niedrigwasser)
Stunden außerhalb des Fensters fallen mit Veto heraus — wie die Nacht oder zu
kaltes Wasser. Ohne Fenster ist die Tide reine Anzeige und ändert keinen Score.
"""
from __future__ import annotations
import calendar
from datetime import datetime, timedelta
from statistics import median

from .i18n import T, TD, N_, uebersetzt

AUTO_HUB_MIN = 0.5            # m — darunter gilt ein Spot ohne Angabe als tidenfrei
STAUWASSER_MIN = 30           # ± Minuten um den Scheitel heißt „Hochwasser“ / „Niedrigwasser“
FENSTER_ARTEN = ("hochwasser", "niedrigwasser", "auflaufend", "ablaufend")
FENSTER_STUNDEN = 2.0
# Die Schlüssel sind Daten („HW“, „auflaufend“ stehen so in Ereignissen,
# Stunden und Katalog); die Werte sind Anzeigetext und werden erst beim
# Gebrauch übersetzt — `T(LAGE_TEXT[k])`, auch in report.py. Ebenso QUELLE.
ART_TEXT = {"HW": N_("Hochwasser"), "NW": N_("Niedrigwasser")}
LAGE_TEXT = {"hochwasser": N_("Hochwasser"), "niedrigwasser": N_("Niedrigwasser"),
             "auflaufend": N_("auflaufend"), "ablaufend": N_("ablaufend")}
QUELLE = N_("Open-Meteo Marine, modellierter Wasserstand auf 8-km-Raster — keine amtliche Gezeitentafel")


def extrema(series: dict) -> list[dict]:
    """Hoch- und Niedrigwasser über den ganzen Verlauf.

    [{"art": "HW"|"NW", "zeit": datetime, "hoehe": m}], zeitlich sortiert.
    Der Scheitel fällt selten auf die volle Stunde; die Zeit wird deshalb aus
    der Parabel durch die drei Stunden um das Extremum bestimmt — auf die
    Minute, mit einer Genauigkeit, die das Modell selbst nicht hat, aber
    ohne den Sprung, den „14:00“ statt „14:25“ macht.
    """
    pts = []
    for k, v in (series or {}).items():
        # Eine unlesbare Zeit oder ein Text statt Zahl aus der Antwort kostet
        # den Punkt, nicht die Suche (Review 25.09., S10).
        try:
            if v is not None:
                pts.append((datetime.fromisoformat(str(k)), float(v)))
        except (TypeError, ValueError):
            continue
    pts.sort()
    out = []
    for i in range(1, len(pts) - 1):
        (t0, y0), (t1, y1), (t2, y2) = pts[i - 1], pts[i], pts[i + 1]
        if y1 > y0 and y1 >= y2:
            art = "HW"
        elif y1 < y0 and y1 <= y2:
            art = "NW"
        else:
            continue
        zeit, hoehe = t1, y1
        if t1 - t0 == timedelta(hours=1) and t2 - t1 == timedelta(hours=1):
            nenner = y0 - 2 * y1 + y2
            if abs(nenner) > 1e-9:
                dx = max(-0.5, min(0.5, (y0 - y2) / (2 * nenner)))
                zeit = t1 + timedelta(minutes=round(dx * 60))
                hoehe = y1 - (y2 - y0) ** 2 / (8 * nenner)
        out.append({"art": art, "zeit": zeit, "hoehe": round(hoehe, 2)})
    return out


def hub(ereignisse: list[dict]) -> float | None:
    """Mittlerer Tidenhub: Median der Höhenunterschiede aufeinanderfolgender
    Scheitel. Der Median, weil ein Windstau einzelne Paare verzerrt."""
    diffs = [abs(a["hoehe"] - b["hoehe"]) for a, b in zip(ereignisse, ereignisse[1:])
             if a["art"] != b["art"]]
    return round(median(diffs), 2) if diffs else None


def lage(t: datetime, ereignisse: list[dict]) -> dict | None:
    """Wo im Tidenzyklus der Zeitpunkt liegt.

    {"art": hochwasser|niedrigwasser|auflaufend|ablaufend, "vor": Ereignis|None,
     "nach": Ereignis|None}. Stauwasser (± STAUWASSER_MIN um den Scheitel) heißt
    „Hochwasser“ bzw. „Niedrigwasser“, dazwischen läuft es auf oder ab.
    """
    if not ereignisse:
        return None
    vor = nach = None
    for ev in ereignisse:
        if ev["zeit"] <= t:
            vor = ev
        else:
            nach = ev
            break
    stau = timedelta(minutes=STAUWASSER_MIN)
    if nach is not None and nach["zeit"] - t <= stau:
        art = "hochwasser" if nach["art"] == "HW" else "niedrigwasser"
    elif vor is not None and t - vor["zeit"] <= stau:
        art = "hochwasser" if vor["art"] == "HW" else "niedrigwasser"
    elif nach is not None:
        art = "auflaufend" if nach["art"] == "HW" else "ablaufend"
    else:
        art = "ablaufend" if vor["art"] == "HW" else "auflaufend"
    return {"art": art, "vor": vor, "nach": nach}


def fenster_lesen(spot: dict) -> dict | None:
    """Das Tidenfenster aus dem Katalog — oder None, wenn keines (oder ein
    unbekanntes) eingetragen ist. `load_spots` hat den Block normiert."""
    block = spot.get("tide")
    if not isinstance(block, dict):
        return None
    art = str(block.get("fahrbar") or "").strip().lower()
    if art not in FENSTER_ARTEN:
        return None
    try:
        stunden = float(block.get("stunden") or FENSTER_STUNDEN)
    except (TypeError, ValueError):
        stunden = FENSTER_STUNDEN
    return {"fahrbar": art, "stunden": max(0.5, min(6.0, stunden))}


def fenster_text(fenster: dict | None) -> str:
    """Anzeigetext, nirgends verglichen — deshalb gleich übersetzt, als TD():
    er steht im Veto der Stunden und in der Übersicht, und der Report setzt
    ihn seit 2.3.0 für jede seiner vier Sprachen neu."""
    if not fenster:
        return ""
    if fenster["fahrbar"] in ("hochwasser", "niedrigwasser"):
        stunden = f"{fenster['stunden']:g}"
        if fenster["fahrbar"] == "hochwasser":
            return TD("HW ± {h} h", h=stunden)
        return TD("NW ± {h} h", h=stunden)
    return TD("nur {lage}", lage=TD(LAGE_TEXT.get(fenster["fahrbar"], fenster["fahrbar"])))


def im_fenster(t: datetime, ereignisse: list[dict], fenster: dict | None) -> bool | None:
    """Liegt der Zeitpunkt im Tidenfenster? None, wenn es nicht zu entscheiden
    ist — kein Fenster, keine Ereignisse. Für die Stundenbewertung wird die
    Stundenmitte übergeben, damit 13–14 Uhr bei „HW 14:25 ± 2 h“ dabei ist."""
    if not fenster or not ereignisse:
        return None
    art = fenster["fahrbar"]
    if art in ("hochwasser", "niedrigwasser"):
        such = "HW" if art == "hochwasser" else "NW"
        breite = timedelta(hours=fenster["stunden"])
        return any(ev["art"] == such and abs(ev["zeit"] - t) <= breite for ev in ereignisse)
    # Halbtiden nach der Richtung, nicht nach dem Stauwasser-Etikett: „nur
    # auflaufend“ ist die Zeit von Niedrig- bis Hochwasser, Scheitel inklusive
    # des Beginns — dieselben Abschnitte, die `fenster_zeiten` anzeigt.
    lg = lage(t, ereignisse)
    if lg is None:
        return None
    if lg["nach"] is not None:
        steigt = lg["nach"]["art"] == "HW"
    else:
        steigt = lg["vor"]["art"] == "NW"
    return steigt if art == "auflaufend" else not steigt


def fenster_zeiten(ereignisse: list[dict], fenster: dict | None, tag: str) -> list[tuple[str, str]]:
    """Die Fenster eines Tages als („12:25“, „16:25“) — für die Anzeige."""
    if not fenster or not ereignisse:
        return []
    aus = []
    if fenster["fahrbar"] in ("hochwasser", "niedrigwasser"):
        such = "HW" if fenster["fahrbar"] == "hochwasser" else "NW"
        breite = timedelta(hours=fenster["stunden"])
        for ev in ereignisse:
            if ev["art"] != such:
                continue
            von, bis = ev["zeit"] - breite, ev["zeit"] + breite
            if von.date().isoformat() <= tag <= bis.date().isoformat():
                aus.append((von.strftime("%H:%M") if von.date().isoformat() == tag else "00:00",
                            bis.strftime("%H:%M") if bis.date().isoformat() == tag else "24:00"))
    else:
        # Halbtiden von Scheitel zu Scheitel. Vor dem ersten und nach dem
        # letzten Ereignis liegt eine halbe Periode (≈ 6 h 12 min), die der
        # Verlauf nur angeschnitten zeigt — sie wird ergänzt, damit der erste
        # Morgen kein Loch hat; die Grenze ist dann eine Näherung.
        such_ende = "HW" if fenster["fahrbar"] == "auflaufend" else "NW"
        halb = timedelta(hours=6, minutes=12)
        kette = list(ereignisse)
        if kette[0]["art"] == such_ende:
            kette.insert(0, {"art": "", "zeit": kette[0]["zeit"] - halb})
        if kette[-1]["art"] != such_ende:
            kette.append({"art": such_ende, "zeit": kette[-1]["zeit"] + halb})
        for a, b in zip(kette, kette[1:]):
            if b["art"] != such_ende:
                continue
            von, bis = a["zeit"], b["zeit"]
            if von.date().isoformat() <= tag <= bis.date().isoformat():
                aus.append((von.strftime("%H:%M") if von.date().isoformat() == tag else "00:00",
                            bis.strftime("%H:%M") if bis.date().isoformat() == tag else "24:00"))
    return aus


def uebersicht(spot: dict, series: dict | None, versatz_s: int | None, cfg=None) -> dict:
    """Was Report, Karte und Bewertung über die Tide an diesem Spot wissen müssen.

    {"modus": "ja"|"nein"|"auto", "aktiv": bool, "grund": str, "daten": bool,
     "hub": m|None, "ereignisse": [...], "fenster": {...}|None,
     "fenster_text": str, "versatz": s, "quelle": str}
    `aktiv` sagt, ob die Tide hier gezeigt und — mit Fenster — bewertet wird.
    """
    tidal = spot.get("tidal")
    modus = "ja" if tidal is True else ("nein" if tidal is False else "auto")
    grenze = float(((cfg or {}).get("tide") or {}).get("auto_hub_min", AUTO_HUB_MIN))
    ereignisse = extrema(series) if series else []
    h = hub(ereignisse)
    meer = spot.get("water_body") in ("sea", "lagoon")
    # `grund` und `quelle` sind Anzeigetext — übersetzt, wenn die Übersicht entsteht
    # (TD: in einer anderen Sprache neu zu setzen, siehe i18n „Texte in Daten“).
    aus = {"modus": modus, "aktiv": False, "grund": "", "daten": bool(series),
           "hub": h, "ereignisse": ereignisse, "fenster": None, "fenster_text": "",
           "versatz": int(versatz_s or 0), "quelle": TD(QUELLE)}
    if modus == "nein":
        aus["grund"] = TD("im Katalog ausgeschaltet")
        return aus
    if modus == "ja":
        aus["aktiv"] = True
        aus["grund"] = (TD("im Katalog eingeschaltet") if series
                        else TD("im Katalog eingeschaltet — aber keine Tidendaten vom Modell"))
    elif not meer:
        aus["grund"] = TD("kein Meer- oder Lagunenspot")
        return aus
    elif not series:
        aus["grund"] = TD("keine Tidendaten vom Modell")
        return aus
    elif h is None or h < grenze:
        aus["grund"] = (TD("modellierter Hub {hub} m unter {grenze} m", hub=f"{h:.1f}", grenze=f"{grenze:g}")
                        if h is not None else TD("kein Tidenverlauf im Modell"))
        return aus
    else:
        aus["aktiv"] = True
        aus["grund"] = TD("automatisch: Meer mit {hub} m Hub", hub=f"{h:.1f}")
    aus["fenster"] = fenster_lesen(spot)
    aus["fenster_text"] = fenster_text(aus["fenster"])
    return aus


def lage_text(t: datetime, ereignisse: list[dict]) -> str:
    """„auflaufend, Hochwasser um 14:25“ — für Sessionzeile und Raster."""
    lg = lage(t, ereignisse)
    if lg is None:
        return ""
    if lg["art"] in ("hochwasser", "niedrigwasser"):
        return T(LAGE_TEXT[lg["art"]])
    ziel = lg["nach"] or lg["vor"]
    if lg["nach"] is None:
        return T(LAGE_TEXT[lg["art"]])
    return T("{lage}, {art} um {zeit}", lage=T(LAGE_TEXT[lg["art"]]), art=T(ART_TEXT[ziel["art"]]),
             zeit=ziel["zeit"].strftime("%H:%M"))


def als_json(info: dict) -> dict:
    """Die Übersicht ohne datetime-Objekte — für das Skript im Report, das die
    Lage zur Anzeigezeit neu berechnet. `epoch` ist der Zeitpunkt als
    Unix-Sekunden (die Ereigniszeiten sind Ortszeit am Spot; `versatz` macht
    daraus UTC), damit der Browser nicht in seiner eigenen Zeitzone rechnet."""
    versatz = int(info.get("versatz") or 0)
    ereignisse = []
    for ev in info.get("ereignisse") or []:
        utc = ev["zeit"] - timedelta(seconds=versatz)
        ereignisse.append({"art": ev["art"], "hoehe": ev["hoehe"],
                           "zeit": ev["zeit"].strftime("%H:%M"),
                           "tag": ev["zeit"].strftime("%Y-%m-%d"),
                           "epoch": calendar.timegm(utc.timetuple())})
    return {"aktiv": bool(info.get("aktiv")), "modus": info.get("modus"), "hub": info.get("hub"),
            # in der Sprache des Reports, der gerade geschrieben wird (2.3.0)
            "fenster": info.get("fenster"), "fenster_text": uebersetzt(info.get("fenster_text")) or "",
            "ereignisse": ereignisse, "versatz": versatz}
