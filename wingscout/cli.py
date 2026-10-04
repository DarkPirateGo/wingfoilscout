"""Wingfoilscout · Kommandozeile."""
from __future__ import annotations
import argparse
import os
import sys
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import load_config, quiver_range, KonfigFehler
from .spots import load_spots, eligible, KatalogFehler
from .geo import parse_position
from .score import score_hours, build_sessions, rank_trips
from .tide import uebersicht as tide_uebersicht
from . import report as report_mod
from . import i18n, zeitraum
from .i18n import T, TD, TN, N_                                   # noqa: F401

ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv=None):
    # Die Hilfe entsteht vor main()s Sprachwahl: sie folgt WINGSCOUT_SPRACHE
    # oder der gespeicherten Wahl, nicht --sprache.
    p = argparse.ArgumentParser(
        prog="wingscout",
        description=T("Findet Wingfoil-Sessions im Umkreis und schreibt einen HTML-Report."),
    )
    p.add_argument("--days", type=int, default=3, help=T("Vorhersagetage (1–16, Standard 3)"))
    p.add_argument("--ab", default=None,
                   help=T("Startzeitpunkt statt jetzt: \"2026-10-10 09:00\", \"10.10.2026 09:00\" oder nur das "
                          "Datum; die Tage zählen ab ihm"))
    p.add_argument("--radius", type=float, default=500, help=T("Suchradius in km Straße (Standard 500)"))
    p.add_argument("--max-drive", type=float, default=None, help=T("Obergrenze einfache Fahrt in Stunden"))
    p.add_argument("--min-hours", type=float, default=None, help=T("Mindestlänge einer Session in Stunden"))
    p.add_argument("--start", default=None,
                   help=T("Startpunkt statt Zuhause: \"51.7625, 3.854\", Grad/Minuten oder Maps-Link"))
    p.add_argument("--start-name", default=None, help=T("Anzeigename für den Startpunkt"))
    p.add_argument("--nights", type=int, default=0,
                   help=T("Geplante Übernachtungen — verlangt entsprechend viele Tage am Stück"))
    p.add_argument("--config", default=str(ROOT / "config.yaml"))
    p.add_argument("--spots", default=str(ROOT / "spots.yaml"))
    p.add_argument("--out", default=str(ROOT / "report.html"))
    p.add_argument("--model", default=None, help=T("Open-Meteo-Modell erzwingen, z.B. icon_d2"))
    p.add_argument("--geometry", default=str(ROOT / "geometry.json"),
                   help=T("Datei mit der Ufergeometrie aus build_geometry.py"))
    p.add_argument("--no-geo", action="store_true",
                   help=T("Ufergeometrie ignorieren, nur Katalog-Sektoren nutzen"))
    p.add_argument("--marine", action="store_true",
                   help=T("Wassertemperatur und Wellenmodell mit bewerten (nur Meer- und Lagunenspots); "
                          "die Tidenzeiten kommen seit 1.18.0 auch ohne diesen Schalter"))
    p.add_argument("--no-routing", action="store_true",
                   help=T("Fahrzeiten schätzen statt routen (kein OSRM-Aufruf)"))
    p.add_argument("--no-camping", action="store_true",
                   help=T("Keine Stellplätze von Park4Night holen"))
    p.add_argument("--no-ensemble", action="store_true",
                   help=T("Keine Ensemble-Wahrscheinlichkeit für die besten Ziele holen"))
    p.add_argument("--no-highres", action="store_true",
                   help=T("Keine hochauflösenden Regionalmodelle abfragen"))
    p.add_argument("--no-alerts", action="store_true",
                   help=T("Keine amtlichen Wetterwarnungen (MeteoAlarm) holen"))
    p.add_argument("--demo", action="store_true", help=T("Synthetische Daten statt echter Vorhersage"))
    p.add_argument("--open", action="store_true", help=T("Report danach im Browser öffnen"))
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--sprache", choices=sorted(i18n.SPRACHEN), default=None,
                   help=T("Sprache von Meldungen und Report: de, en, fr, es (sonst die in der Oberfläche "
                          "gewählte oder die des Systems)"))
    return p.parse_args(argv)


def main(argv=None, log_fn=None) -> int:
    args = parse_args(argv)
    # Aus der Oberfläche kommt ein Lauf mit der Sprache seiner Anfrage schon
    # gesetzt (webui._starte); nur die Kommandozeile entscheidet hier selbst.
    if log_fn is None:
        i18n.fuer_kommandozeile(getattr(args, "sprache", None))
    if log_fn is not None:
        log = log_fn
    else:
        log = (lambda *a: None) if args.quiet else (lambda *a: print(*a, file=sys.stderr))

    # Der Startzeitpunkt als Zeitpunkt (seit 2.3.0); die Oberfläche übergibt
    # ihn schon gelesen.
    try:
        args.ab = zeitraum.lesen(args.ab)
    except ValueError:
        raise SystemExit(T("Startzeitpunkt „{ab}“ nicht lesbar — etwa 2026-10-10 09:00 oder 10.10.2026, "
                           "ohne Angabe gilt jetzt.", ab=str(args.ab)[:40]))

    # Nur hier wird aus einem kaputten Katalog ein Programmende: die Oberfläche
    # nutzt run_search() direkt und meldet den Fehler im Protokoll.
    try:
        cfg = load_config(args.config)
        if args.min_hours is not None:
            cfg["session"]["min_hours"] = args.min_hours
        return run_search(cfg, args, log)
    except (KatalogFehler, KonfigFehler) as exc:
        raise SystemExit(str(exc))


def apply_start(cfg, start, start_name, log) -> bool:
    """Startpunkt aus der Eingabe übernehmen — unterwegs zählt, wo man steht.

    Alle Entfernungen, Fahrzeiten und der Radius beziehen sich danach auf diesen
    Punkt statt auf Zuhause. Unlesbare Eingaben ändern nichts und sagen es.
    """
    if not start:
        return False
    pos = parse_position(start) if isinstance(start, str) else tuple(start)
    if not pos:
        log(T("Startpunkt \"{start}\" nicht lesbar — bleibe bei {name}.",
              start=start, name=cfg["rider"]["home"]["name"]))
        return False
    lat, lon = pos
    name = (start_name or "").strip() or f"{lat:.4f}, {lon:.4f}"
    cfg["rider"]["home"] = {"name": name, "lat": lat, "lon": lon}
    log(T("Startpunkt: {name} ({lat}, {lon})", name=name, lat=f"{lat:.4f}", lon=f"{lon:.4f}"))
    return True


def add_ensemble(trips, cfg, args, log, top: int | None = None) -> None:
    """Wahrscheinlichkeit für die besten Ziele nachladen.

    Bewusst erst nach dem Ranking und nur für die vordersten Ziele: das
    Ensemble beantwortet die Frage „lohnt die Anfahrt", und die stellt sich
    nur dort, wo das Tool ohnehin hinschickt. Fünfzig Spots durchzurechnen
    wäre Datenverkehr ohne Erkenntnis.

    Scheitert der Abruf, bleibt der Report ohne diese Angabe — sie ist eine
    Ergänzung, kein Fundament.
    """
    if getattr(args, "no_ensemble", False) or getattr(args, "demo", False) or not trips:
        return
    # Seit die Wahrscheinlichkeit in den Score eingeht, entscheidet dieser
    # Wert mit über die Reihenfolge — deshalb reicht die alte Handvoll nicht
    # mehr: wer nicht abgefragt wird, wird weder belohnt noch bestraft.
    if top is None:
        top = int((cfg.get("ensemble") or {}).get("top", 20) or 20)
    from .sources.ensemble import fetch as fetch_ensemble, window_stats, EnsembleError

    wanted, seen = [], set()
    for trip in trips[:top]:
        spot = trip["spot"]
        if spot["id"] not in seen:
            seen.add(spot["id"])
            wanted.append(spot)
    try:
        data = fetch_ensemble(wanted, getattr(args, "_abruf_tage", args.days))
    except EnsembleError as exc:
        log(T("Ensemble nicht abrufbar ({fehler}) — weiter ohne Wahrscheinlichkeit", fehler=exc))
        return
    except Exception as exc:                       # noqa: BLE001 — Zusatz, kein Muss
        log(T("Ensemble nicht lesbar ({art}: {fehler}) — weiter ohne Wahrscheinlichkeit",
              art=type(exc).__name__, fehler=exc))
        return

    ride_kn, _ = quiver_range(cfg)
    good_kn = cfg.get("wind", {}).get("preferred_low", ride_kn)
    counted = 0
    from .score import apply_ensemble, ensemble_schwelle
    for trip in trips[:top]:
        entry = data.get(trip["spot"]["id"])
        if not entry:
            continue
        for session in trip["sessions"]:
            if session.get("thermal"):
                continue          # dort zählt die Verlässlichkeit des Spots, nicht das Ensemble
            hours = hour_stamps(session["start"], session["end"])
            # Eine krumme Antwort kostet die Wahrscheinlichkeit dieses Ziels,
            # nicht die Suche — bis 2.1.0 stand die Auswertung außerhalb jedes
            # try (Review 04.10.2026, C4).
            try:
                stats = window_stats(entry, hours,
                                     ensemble_schwelle(ride_kn, trip["spot"], session),
                                     ensemble_schwelle(good_kn, trip["spot"], session))
            except Exception as exc:               # noqa: BLE001 — Zusatz, kein Muss
                log(T("Ensemble für {name} nicht lesbar ({art}: {fehler}) — weiter ohne Wahrscheinlichkeit",
                      name=trip["spot"]["name"], art=type(exc).__name__, fehler=str(exc)[:120]))
                break
            if stats:
                session["ens"] = stats
                counted += 1
    gewichtet = apply_ensemble(trips, cfg)
    if gewichtet:
        log(T("Ensemble: {n} Sessions an {ziele} Zielen mit Wahrscheinlichkeit versehen, "
              "{gewichtet} davon im Ranking gewichtet", n=counted, ziele=len(data), gewichtet=gewichtet))
    else:
        log(T("Ensemble: {n} Sessions an {ziele} Zielen mit Wahrscheinlichkeit versehen",
              n=counted, ziele=len(data)))


def hour_stamps(start, end) -> list[str]:
    """Stundenstempel im Format der API, von start bis vor end.

    `end` einer Session ist exklusiv (letzte Stunde plus eins) — bis 1.6.1
    zählte hier die Stunde nach der Session mit.
    """
    stamps, t = [], start
    while t < end:
        stamps.append(t.strftime("%Y-%m-%dT%H:00"))
        t += timedelta(hours=1)
    return stamps or [start.strftime("%Y-%m-%dT%H:00")]


def add_camping(trips, cfg, args, log, top: int = 8) -> None:
    """Stellplätze für die besten Ziele nachladen — Hund zwingend erlaubt.

    Wie beim Ensemble nur für die vordersten Ziele: fünfzig Abfragen an einen
    fremden Server, von denen zweiundvierzig niemand liest, wären schlechtes
    Benehmen.
    """
    if getattr(args, "no_camping", False) or getattr(args, "demo", False) or not trips:
        return
    from .sources.park4night import fetch as fetch_places

    camping = cfg.get("camping", {})
    wanted, seen = [], set()
    for trip in trips[:top]:
        spot = trip["spot"]
        if spot["id"] not in seen:
            seen.add(spot["id"])
            wanted.append(spot)

    try:
        data = fetch_places(wanted, camping, log=log)
    except Exception as exc:                       # noqa: BLE001 — Zusatz, kein Muss
        log(T("Park4Night nicht lesbar ({art}: {fehler}) — weiter ohne Stellplätze",
              art=type(exc).__name__, fehler=exc))
        return
    if not data:
        log(T("Park4Night nicht erreichbar — weiter ohne Stellplätze"))
        return
    for trip in trips[:top]:
        result = data.get(trip["spot"]["id"])
        if result:
            trip["camping"] = result
    gefunden = sum(len(v["places"]) for v in data.values())
    ohne = sum(v["ohne_hundeangabe"] for v in data.values())
    if ohne:
        log(T("Park4Night: {n} hundefreundliche Plätze an {ziele} Zielen · {ohne} Plätze ohne Angabe "
              "zu Tieren übergangen", n=gefunden, ziele=len(data), ohne=ohne))
    else:
        log(T("Park4Night: {n} hundefreundliche Plätze an {ziele} Zielen", n=gefunden, ziele=len(data)))


def refine_drives(keep, cfg, args, limit_h: float, log):
    """Echte Fahrzeiten holen und den Vorfilter damit nachziehen.

    Rückgabe: (bleibende Spots, zusätzlich aussortierte mit Begründung).
    """
    if keep and not getattr(args, "no_routing", False) and not getattr(args, "demo", False):
        try:
            from .sources.routing import drive_times, apply_to
            home = cfg["rider"]["home"]
            times = drive_times(home, keep, ROOT / "cache" / "routes.json", log=log)
            apply_to(keep, times)
        except Exception as exc:                       # noqa: BLE001 — Zusatz, kein Muss
            log(T("Fahrzeiten nicht routbar ({fehler}) — es bleibt bei der Schätzung", fehler=exc))

    # Dieselben zwei Sätze wie in spots.eligible — Anzeigetext für den Report,
    # als TD(): der Report setzt sie für jede seiner vier Sprachen neu.
    bleiben, raus = [], []
    for spot in keep:
        if args.radius is not None and spot["road_km"] > args.radius:
            raus.append((spot, TD("{km} km — außerhalb des Radius von {radius} km",
                                  km=f"{spot['road_km']:.0f}", radius=f"{args.radius:.0f}")))
        elif spot["drive_h"] > limit_h:
            raus.append((spot, TD("{h} h Fahrt über der Obergrenze von {grenze} h",
                                  h=f"{spot['drive_h']:.1f}", grenze=f"{limit_h:.1f}")))
        else:
            bleiben.append(spot)
    bleiben.sort(key=lambda s: s["drive_h"])
    return bleiben, raus


def marine_ziele(keep, args) -> list:
    """Für welche Spots die Marine-API gefragt wird: Meer und Lagune — mit
    --marine alle, sonst alle außer denen mit `tidal: false` (die brauchen
    ohne den Haken nichts von dort)."""
    from .sources.marine import SEA_LIKE
    return [s for s in keep if s.get("water_body") in SEA_LIKE
            and (getattr(args, "marine", False) or s.get("tidal") is not False)]


def marine_fuer_bewertung(m: dict, args) -> tuple:
    """(Wassertemperatur, Welle) für score_hours — nur mit --marine oder im
    Demo-Lauf; ohne den Haken bleibt beides draußen wie bis 1.17.0. Die Tide
    hängt nicht am Haken, sie wird daneben immer weitergereicht."""
    if getattr(args, "marine", False) or getattr(args, "demo", False):
        return m.get("sst"), m.get("wave")
    return None, None


def run_search(cfg, args, log) -> int:
    """Der eigentliche Durchlauf — von der Kommandozeile und von der Oberfläche genutzt."""
    args._n_geo = getattr(args, "_n_geo", 0)
    apply_start(cfg, getattr(args, "start", None), getattr(args, "start_name", None), log)
    spots_all = load_spots(args.spots)
    args._n_spots = len(spots_all)
    args._n_verified = sum(1 for s in spots_all if s.get("verified"))

    lo, hi = quiver_range(cfg)
    log(T("Quiver deckt {lo}–{hi} kn ab · {n} Spots im Katalog", lo=f"{lo:.0f}", hi=f"{hi:.0f}", n=len(spots_all)))

    # Ab wann und wie lange (seit 2.3.0): die Tage zählen ab dem Startzeitpunkt,
    # geholt wird ab heute bis zu seinem Ende — höchstens 16 Tage.
    gewollt = getattr(args, "ab", None)
    try:
        fenster = zeitraum.fenster(gewollt, args.days)
    except zeitraum.ZuWeit:
        log(T("FEHLER: Startzeitpunkt {ab} liegt hinter dem letzten Vorhersagetag ({bis}) — "
              "die Vorhersage reicht 16 Tage.", ab=gewollt.strftime("%Y-%m-%d %H:%M"),
              bis=zeitraum.letzter_tag().isoformat()))
        return 1
    if gewollt is not None and fenster.ab is None:
        log(T("Startzeitpunkt {ab} ist schon vorbei — die Suche beginnt jetzt.",
              ab=gewollt.strftime("%Y-%m-%d %H:%M")))
    elif fenster.ab is not None:
        log(T("Zeitraum: {n} Tage ab {ab}", n=fenster.tage, ab=fenster.ab.strftime("%Y-%m-%d %H:%M")))
    if fenster.gekuerzt:
        log(T("Die Vorhersage reicht nur bis {bis} — Zeitraum auf {n} Tage gekürzt.",
              bis=zeitraum.letzter_tag().isoformat(), n=fenster.tage))
    args.days = fenster.tage
    args._fenster = fenster
    args._abruf_tage = fenster.abruf_tage

    # Mit Zuschlag vorfiltern und erst danach echte Fahrzeiten holen: die
    # Schätzung irrt in beide Richtungen, und ein Ziel wegen einer zu
    # pessimistischen Faustformel gar nicht erst zu prüfen wäre der teurere
    # Fehler. Der Zuschlag kostet nichts — geroutet wird ohnehin in einem Aufruf.
    margin = 1.0 if getattr(args, "no_routing", False) else 1.35
    limit_h = args.max_drive if args.max_drive is not None else cfg["drive"]["max_hours"]
    # Saison: jeder Monat, den der Zeitraum berührt — ein Lauf am 30.09. über
    # sechzehn Tage soll Oktoberspots nach der Oktobersaison beurteilen; seit
    # 2.3.0 ab dem Startzeitpunkt.
    monate = fenster.monate()
    keep, dropped = eligible(spots_all, cfg, monate,
                             args.radius * margin, limit_h * margin)
    keep, spaeter = refine_drives(keep, cfg, args, limit_h, log)
    dropped.extend(spaeter)
    log(T("{n} Spots im Radius von {r} km, {m} aussortiert", n=len(keep), r=f"{args.radius:.0f}", m=len(dropped)))
    if not keep:
        log(T("Kein Spot übrig — Radius erhöhen oder Filter lockern."))
        return 2

    if args.demo:
        from .demo import build as demo_build
        forecasts = demo_build(keep, fenster.abruf_tage)
        log(T("DEMO-Modus: synthetische Wetterdaten, keine echte Vorhersage."))
    else:
        from .sources.openmeteo import fetch, ForecastError
        try:
            forecasts = fetch(keep, fenster.abruf_tage, model=args.model,
                              models=None if args.model else cfg.get("wind", {}).get("models"),
                              log=log)
        except ForecastError as exc:
            log(T("FEHLER: {fehler}", fehler=exc))
            log(T("Tipp: --demo zeigt den Report mit synthetischen Daten."))
            return 1
        fehlend = len(keep) - len(forecasts)
        if fehlend > 0:
            log(T("Vorhersage für {n} Spots geladen ({tage} Tage) — {fehlend} ohne Daten",
                  n=len(forecasts), tage=args.days, fehlend=fehlend))
        else:
            log(T("Vorhersage für {n} Spots geladen ({tage} Tage)", n=len(forecasts), tage=args.days))

        # Hochauflösende Regionalmodelle: 1 bis 2,5 km statt 7 bis 25. Sie
        # lösen Talwinde und Seebrisen auf, die im groben Gitter verschwinden.
        if not getattr(args, "no_highres", False) and cfg.get("wind", {}).get("highres", True):
            from .sources.highres import hole as hole_fein
            try:
                fein, stat = hole_fein([s for s in keep if s["id"] in forecasts],
                                       fenster.abruf_tage, Path(args.geometry).parent / "cache",
                                       log=log)
            except Exception as exc:                          # noqa: BLE001
                log("    " + T("Hochauflösende Modelle übersprungen ({fehler})", fehler=exc))
                fein, stat = {}, {}
            for sid, paar in fein.items():
                forecasts[sid]["_highres"] = paar
            if stat.get("abgedeckt"):
                welche = ", ".join(f"{k} {v}" for k, v in sorted(stat["modelle"].items()))
                log(T("Hochauflösend gerechnet: {n} von {gesamt} Spots ({welche})",
                      n=stat["abgedeckt"], gesamt=len(forecasts), welche=welche))
            args._n_highres = stat.get("abgedeckt", 0)

    geometry = {}
    if not args.no_geo:
        gpath = Path(args.geometry)
        if gpath.exists():
            import json
            geometry = json.loads(gpath.read_text(encoding="utf-8"))
            hit = sum(1 for s in keep if s["id"] in geometry)
            log(T("Ufergeometrie für {n} von {gesamt} Spots vorhanden", n=hit, gesamt=len(keep)))
            args._n_geo = hit
        else:
            log(T("Keine Ufergeometrie gefunden — einmal `python3 build_geometry.py` laufen lassen."))

    # Seit 1.18.0 kommen die Marine-Daten für jeden Meer- und Lagunenspot,
    # nicht nur mit --marine: der Wasserstand (Tide) gehört zur Anzeige, und
    # die Anfrage kostet dasselbe, ob sie eine oder drei Reihen holt. Der
    # Haken entscheidet nur noch, ob Wassertemperatur und Wellenmodell in die
    # Bewertung eingehen. Spots mit `tidal: false` werden ohne --marine gar
    # nicht erst angefragt.
    marine = {}
    if not args.demo:
        from .sources.marine import fetch as fetch_marine
        wollen = marine_ziele(keep, args)
        if wollen:
            try:
                marine = fetch_marine(wollen, fenster.abruf_tage)
                if args.marine:
                    log(T("Marine-Daten (Tide, Wassertemperatur, Welle) für {n} von {gesamt} Meer-Spots",
                          n=len(marine), gesamt=len(wollen)))
                else:
                    log(T("Marine-Daten (Tide) für {n} von {gesamt} Meer-Spots", n=len(marine), gesamt=len(wollen)))
            except Exception as exc:                      # noqa: BLE001 — Zusatzdaten, kein Muss
                if args.marine:
                    log(T("Marine-Daten nicht abrufbar ({fehler}) — weiter ohne Tiden, Wassertemperatur und Welle",
                          fehler=exc))
                else:
                    log(T("Marine-Daten nicht abrufbar ({fehler}) — weiter ohne Tiden", fehler=exc))

    alerts, landesweit = {}, {}
    if not args.demo and not getattr(args, "no_alerts", False):
        try:
            from .sources.meteoalarm import alerts_for
            alerts = alerts_for(keep, min_level=2, landesweit=landesweit)
            treffer = sum(len(v) for v in alerts.values())
            if landesweit:
                log(T("Wetterwarnungen: {n} Treffer für {spots} Spots · ohne Gebietszuordnung: {laender}",
                      n=treffer, spots=len(alerts),
                      laender=", ".join(f"{land} {len(w)}" for land, w in landesweit.items())))
            else:
                log(T("Wetterwarnungen: {n} Treffer für {spots} Spots", n=treffer, spots=len(alerts)))
        except Exception as exc:                      # noqa: BLE001
            log(T("Wetterwarnungen nicht abrufbar ({fehler}) — weiter ohne", fehler=exc))
    elif args.demo:
        # `event` steht im Report und wird dort übersetzt (`T(event)`, wie die
        # Ereignisse aus dem Feed) — hier also der deutsche Quelltext, sonst
        # fände eine andere Sprache des Reports keinen Schlüssel (2.3.0);
        # `level_name` ist der Schlüssel aus meteoalarm.LEVEL_NAME, `title`
        # zeigt niemand.
        alerts = {keep[0]["id"]: [{"event": N_("Wind"), "level": 3, "level_name": "orange",
                                   "area": keep[0].get("region") or keep[0]["name"],
                                   "from": "", "until": "", "title": "Demo-Warnung"}]} if keep else {}
    args._alerts = alerts
    args._alerts_landesweit = landesweit
    args._protected = {sid: (geometry.get(sid) or {}).get("protected") or [] for sid in geometry}
    # Eine Rose von einem Pin an Land beschreibt nichts — sie wird nicht
    # benutzt, und der Report sagt, dass die Koordinate zu prüfen ist.
    args._an_land = {sid for sid, e in geometry.items() if (e or {}).get("wasser") is False}

    from .score import SONNE_STATISTIK as _sonne
    # Je Lauf von vorn: die Oberfläche hält das Modul über viele Läufe, und
    # eine Abweichung vom Vormittag hat im Abendlauf nichts verloren.
    _sonne.update(vorhersage=0, gerechnet=0, abweichung_min=0.0)

    all_rows, sessions = {}, []
    # `jetzt` mit Zone: die Stundenstempel sind Ortszeit am Spot, und
    # score_hours rechnet den Zeitpunkt je Spot dorthin um.
    jetzt = None if args.demo else datetime.now(timezone.utc)
    for spot in keep:
        fc = forecasts.get(spot["id"])
        if not fc:
            continue
        # Ein Unsinnswert in der Antwort für einen Spot kostet diesen Spot,
        # nicht die Suche: bis 2.1.0 brach ein `utc_offset_seconds: 1e999`
        # oder ein Text als Temperatur den ganzen Lauf ab (Review 04.10.2026, C4).
        try:
            rose = None if spot["id"] in args._an_land else (geometry.get(spot["id"]) or {}).get("rose_m")
            m = marine.get(spot["id"]) or fc.get("_marine_demo") or {}
            sst, welle = marine_fuer_bewertung(m, args)
            try:
                tide_info = tide_uebersicht(spot, m.get("tide"), fc.get("utc_offset_seconds"), cfg)
            except Exception as exc:                  # noqa: BLE001 — Zusatzdaten, kein Muss
                log("    " + T("Tide für {name} nicht verwertbar ({fehler}) — weiter ohne",
                              name=spot["name"], fehler=exc))
                tide_info = None
            spot["_tide"] = tide_info                 # Report und Karte lesen es vom Spot
            rows = score_hours(spot, fc, cfg, sst, rose, m.get("tide"),
                               jetzt=jetzt, wave=welle, tide_info=tide_info,
                               ab=fenster.ab_mit_zone(), tage=fenster.tage_iso)
            neue = build_sessions(spot, rows, cfg)
        except Exception as exc:                      # noqa: BLE001 — ein Spot, nicht die Suche
            log("    " + T("Vorhersage für {name} nicht verwertbar ({art}: {fehler}) — Spot übersprungen",
                          name=spot["name"], art=type(exc).__name__, fehler=str(exc)[:120]))
            continue
        all_rows[spot["id"]] = (spot, rows)
        sessions.extend(neue)
    n_tide = sum(1 for spot in keep if (spot.get("_tide") or {}).get("aktiv"))
    if n_tide:
        mit_fenster = sum(1 for spot in keep if (spot.get("_tide") or {}).get("fenster"))
        if mit_fenster:
            log(T("Tiden an {n} Spots, davon {fenster} mit Tidenfenster", n=n_tide, fenster=mit_fenster))
        else:
            log(T("Tiden an {n} Spots", n=n_tide))

    if _sonne["gerechnet"]:
        log(T("Sonnenzeiten: {vorhersage} Tage aus der Vorhersage, {gerechnet} selbst gerechnet",
              vorhersage=_sonne["vorhersage"], gerechnet=_sonne["gerechnet"]))
    if _sonne["vorhersage"] and _sonne["abweichung_min"]:
        log("    " + T("eigene Rechnung weicht um höchstens {min} min ab", min=f"{_sonne['abweichung_min']:.0f}"))

    trips = rank_trips(sessions, cfg, getattr(args, "nights", 0) or 0)
    add_ensemble(trips, cfg, args, log)
    add_camping(trips, cfg, args, log)
    nights = getattr(args, "nights", 0) or 0
    if nights:
        log(T("{n} Sessions · {ziele} Ziele mit {tage} brauchbaren Tagen am Stück",
              n=len(sessions), ziele=len(trips), tage=nights + 1))
    else:
        log(T("{n} Sessions in {ziele} Zielen gefunden", n=len(sessions), ziele=len(trips)))
    args._n_sessions, args._n_trips = len(sessions), len(trips)

    def rendern() -> str:
        return report_mod.render(trips, all_rows, dropped, cfg, args, demo=args.demo)

    out = report_mod.write(args.out, rendern())
    log(T("Report: {pfad}", pfad=out))
    # Derselbe Report in allen vier Sprachen, damit der Reiter „Ziele“ dem
    # Sprachumschalter folgt, ohne neue Suche (seit 2.3.0). Nur für den Report,
    # den die Oberfläche zeigt; scheitert es, bleibt „Ziele“ in dieser Sprache.
    if report_mod.ist_standard(out):
        try:
            report_mod.fassungen_schreiben(out, rendern)
        except Exception as exc:                      # noqa: BLE001 — Zusatz, kein Muss
            log("    " + T("(Report in den anderen Sprachen nicht abgelegt: {fehler})", fehler=exc))
    # Was dieser Lauf oben hatte — für den Rückblick in der Oberfläche, der
    # die besten Ziele gegen gemessene Winde der letzten Tage hält.
    try:
        from . import CACHE
        from .spotedit import schreibe_atomar
        import json as _json
        CACHE.mkdir(parents=True, exist_ok=True)
        schreibe_atomar(CACHE / "letzter_lauf.json", _json.dumps({
            "zeit": datetime.now().isoformat(timespec="minutes"), "demo": bool(args.demo),
            "days": int(args.days), "home": cfg["rider"]["home"],
            "ab": args._fenster.ab.isoformat(timespec="minutes") if getattr(args, "_fenster", None)
                  and args._fenster.ab else None,
            "top": [{"rang": i, "id": t["spot"]["id"], "name": t["spot"]["name"]}
                    for i, t in enumerate(trips, 1)]}, ensure_ascii=False, indent=1))
    except Exception as exc:                          # noqa: BLE001 — Zusatz, kein Muss
        log("    " + T("(letzter_lauf.json nicht geschrieben: {fehler})", fehler=exc))
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


def programm(argv=None) -> int:
    """`main()` als eigenes Programm — `run.py` und `python3 -m wingscout.cli`.

    Was ein Lauf schreibt, gehört nur dem Benutzer: report.html und die
    Dateien in cache/ tragen den Startpunkt, und mit der üblichen Maske 022
    konnte bis 2.1.0 jeder Benutzer des Rechners sie lesen (Review 04.10.2026,
    A3). Die Maske gilt nur hier, nicht in `main()`: die Tests und die
    Oberfläche rufen `main()` mit ihrer eigenen auf. Danach gilt wieder die
    alte."""
    alte_maske = os.umask(0o077)
    try:
        return main(argv)
    finally:
        os.umask(alte_maske)


if __name__ == "__main__":
    raise SystemExit(programm())
