#!/usr/bin/env python3
"""Prüfstand: stimmt Wingfoilscout noch? — mit Netz, gegen Wetterdienste und Messwerte.

    python3 tools/pruefstand.py                    # alles: Referenz, Land, Vergangenheit
    python3 tools/pruefstand.py --nur referenz     # nur ein Teil (referenz | land | vergangenheit)
    python3 tools/pruefstand.py --sonde            # antwortet jeder Dienst? zeigt, was kommt
    python3 tools/pruefstand.py --grundlinie-setzen   # diesen Lauf als Maßstab merken

Rückgabewert: 0 alles in Ordnung, 1 mindestens ein Fehler (oder schlechter
als die Grundlinie), 2 nichts prüfbar (kein Netz).

Was hier geprüft wird und warum, steht in BENCHMARK.md.
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wingscout import __version__, CACHE                          # noqa: E402
from wingscout.config import load_config, KonfigFehler           # noqa: E402
from wingscout.spots import load_spots, KatalogFehler             # noqa: E402
from wingscout.shoreline import load_store                        # noqa: E402
from wingscout import pruefstand as ps                            # noqa: E402


def sonde(cfg, spots) -> int:
    """Jeden Dienst einmal anfragen und zeigen, was er wirklich antwortet —
    für den festen Prüfstandsmonat und für die letzten zwei Tage bis jetzt.
    Je Dienst das nächste Spot-Station-Paar; wo sich zwei Dienste eine Liste
    teilen (KNMI und Rijkswaterstaat), je Dienst eines."""
    from datetime import date, timedelta
    from wingscout.sources import stationen, historisch
    von, bis = ps.ZEITRAUM
    heute = date.today().isoformat()
    vorgestern = (date.today() - timedelta(days=2)).isoformat()
    stationen.windguru_setzen((cfg.get("stationen") or {}).get("windguru"))
    print(f"Sonde · Prüfstandsmonat {von} bis {bis} · Rückblick {vorgestern} bis {heute}\n")
    fehler = 0

    def beispiele(liste):
        return "; ".join(f"{s['id']} {s['name']} ({s['lat']:.2f}, {s['lon']:.2f})" for s in liste[:3])

    for land, (name, lade, hole) in stationen.QUELLEN.items():
        kandidaten = [s for s in spots if (s.get("country") or "").upper() == land]
        umkreis = ps.STATION_MAX_KM
        try:
            if land in stationen.JE_SPOT:
                if not kandidaten:
                    print(f"  {name}: kein {land}-Spot im Katalog")
                    continue
                # Frankreich: die Stationen kommen je Spot aus der Département-Datei
                liste = lade(kandidaten[0])
                print(f"✓ {name}: {len(liste)} Stationen um {kandidaten[0]['name']}, z. B. {beispiele(liste)}")
            elif land == "WG":
                liste = lade()
                if not liste:
                    print(f"  {name}: keine Station in der Konfiguration — Windguru gibt Messwerte nur mit "
                          f"dem API-Passwort der Station heraus; Stationen mit Passwort stehen unter "
                          f"stationen: windguru: in config.yaml (Vorlage in config.example.yaml). "
                          f"Die Sonde liest die Vorlage, also: --config config.yaml")
                    continue
                print(f"✓ {name}: {len(liste)} Stationen aus der Konfiguration, z. B. {beispiele(liste)}")
                kandidaten, umkreis = spots, 50.0        # ein Windguru-Standort kann überall liegen
            else:
                liste = lade()
                print(f"✓ {name}: {len(liste)} Stationen, z. B. {beispiele(liste)}")
                dienste = sorted({str(s.get("dienst") or name) for s in liste})
                if len(dienste) > 1:
                    print("  davon " + ", ".join(f"{sum(1 for s in liste if (s.get('dienst') or name) == d)} {d}"
                                                for d in dienste))
                if land == "NL" and "RWS" not in dienste:
                    # nl_stationen verschluckt den Fehler (dann eben nur KNMI) —
                    # die Sonde soll ihn zeigen: am 20.09. stand hier nur „49
                    # Stationen“, und dass Rijkswaterstaat fehlte, sah man nicht.
                    try:
                        stationen.rws_stationen()
                    except Exception as exc:            # noqa: BLE001
                        print(f"✗ Rijkswaterstaat: Stationsliste — {exc}")
                        fehler += 1
        except Exception as exc:                        # noqa: BLE001
            print(f"✗ {name}: Stationsliste — {exc}")
            fehler += 1
            continue
        if land in stationen.JE_SPOT:
            # Frankreich lädt je Spot die Département-Datei — für eine Sonde
            # reichen die Spots aus dem Département des ersten, nicht alle 55.
            erste = kandidaten[0]
            depts = set(stationen.fr_departements(float(erste["lat"]), float(erste["lon"])))
            kandidaten = [s for s in kandidaten
                          if depts & set(stationen.fr_departements(float(s["lat"]), float(s["lon"])))]
        paare = stationen.paare_finden(kandidaten, umkreis, dienste=[land])
        if not paare:
            wo = "einen Spot" if land == "WG" else f"einen {land}-Spot"
            print(f"  keine Station in {umkreis:.0f} km um {wo}")
            continue
        gesehen = set()
        for p in paare:
            # je Dienst das nächste Paar — KNMI und Rijkswaterstaat teilen sich NL
            if p["quelle"] in gesehen:
                continue
            gesehen.add(p["quelle"])
            for zeitraum in ((von, bis), (vorgestern, heute)):
                try:
                    obs = stationen.stunden_fuer_station(p["station"], *zeitraum)
                    st = sorted(obs["stunden"].items())
                    if st:
                        print(f"  {p['spot']['name']} ↔ {obs['quelle']} {obs['station'].get('name')} ({p['km']} km), "
                              f"{zeitraum[0]}–{zeitraum[1]}: {len(st)} Stunden, erste {st[0][0]} {st[0][1]}, "
                              f"letzte {st[-1][0]} {st[-1][1]}")
                    else:
                        print(f"  {p['spot']['name']} ↔ {obs['quelle']} {obs['station'].get('name')} ({p['km']} km): "
                              f"keine Stunden für {zeitraum[0]}–{zeitraum[1]}"
                              + (f" — {obs['hinweis']}" if obs.get("hinweis") else ""))
                except Exception as exc:                # noqa: BLE001
                    print(f"✗ {p['quelle']}: Stundenwerte {zeitraum[0]}–{zeitraum[1]} — {exc}")
                    fehler += 1
    # Was heute schon da ist, sagt „letzte“ oben: DWD und GeoSphere sollten bis
    # zur laufenden Stunde reichen, KNMI und Météo-France bis gestern.
    try:
        spot = next(s for s in spots if s["id"] == "brouwersdam")
        fc = historisch.hole(spot, von, von, ["dwd_icon_seamless", "ncep_gfs_seamless", "ecmwf_ifs"], "Europe/Berlin")
        felder = sorted(k for k in fc["hourly"] if k != "time")
        print(f"✓ Open-Meteo Vergangenheit: {len(fc['hourly']['time'])} Stunden, Felder z. B. {felder[:3]} … ({len(felder)})")
        fc2 = historisch.hole_bis_heute(spot, vorgestern, heute, ["dwd_icon_seamless", "ncep_gfs_seamless", "ecmwf_ifs"], "Europe/Berlin")
        zeiten = fc2["hourly"]["time"]
        wind = next((fc2["hourly"][k] for k in fc2["hourly"] if k.startswith("wind_speed_10m")), [])
        letzte = next((zeiten[i] for i in range(len(zeiten) - 1, -1, -1) if i < len(wind) and wind[i] is not None), None)
        print(f"✓ Open-Meteo bis heute: {len(zeiten)} Stunden {zeiten[0]} … {zeiten[-1]}, letzter Windwert {letzte}")
    except Exception as exc:                            # noqa: BLE001
        print(f"✗ Open-Meteo Vergangenheit: {exc}")
        fehler += 1
    return 1 if fehler else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Prüfstand — stimmt Wingfoilscout noch?")
    ap.add_argument("--nur", choices=["referenz", "land", "vergangenheit"], help="nur diesen Teil")
    ap.add_argument("--sonde", action="store_true", help="nur prüfen, ob die Dienste antworten")
    ap.add_argument("--grundlinie-setzen", action="store_true", help="diesen Lauf als Maßstab merken")
    ap.add_argument("--von", default=ps.ZEITRAUM[0])
    ap.add_argument("--bis", default=ps.ZEITRAUM[1])
    ap.add_argument("--paare", type=int, default=10, help="wie viele Spot-Station-Paare (Standard 10)")
    ap.add_argument("--dienste", default="DE,NL,AT,FR",
                    help="Länder der Spots, aus denen die Paare gebildet werden (Standard DE,NL,AT,FR); "
                         "die Station darf von jedem Dienst kommen, auch über die Grenze. "
                         "Frankreich lädt je Département 5–15 MB — ohne FR bleibt der erste Lauf klein")
    ap.add_argument("--land", default=f"{ps.LAND_PUNKT[0]},{ps.LAND_PUNKT[1]}",
                    help="Landpunkt als lat,lon (Standard: Münsinger Alb)")
    ap.add_argument("--ohne-netz", action="store_true",
                    help="nur, was ohne Netz geht (der synthetische Landpunkt) — für die Tests")
    ap.add_argument("--config", default=str(ROOT / "config.example.yaml"),
                    help="Konfiguration; Standard ist die Vorlage, damit die Zahlen bei allen gleich sind")
    ap.add_argument("--spots", default=str(ROOT / "spots.yaml"))
    ap.add_argument("--geometry", default=str(ROOT / "geometry.json"))
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    spots = load_spots(args.spots)
    geometry = load_store(args.geometry)
    from wingscout.sources import stationen
    stationen.windguru_setzen((cfg.get("stationen") or {}).get("windguru"))   # Windguru nur aus der Konfiguration
    print(f"Wingfoilscout {__version__} · Prüfstand · {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
    if args.sonde:
        return sonde(cfg, spots)

    abschnitte = []
    teile = [args.nur] if args.nur else ["referenz", "land", "vergangenheit"]
    netz_fehlte = 0

    if args.ohne_netz:
        teile = [t for t in teile if t == "land"]

    if "referenz" in teile:
        print("Referenzspots … (holt die laufende Vorhersage)")
        befunde, tabelle = ps.referenz_lauf(cfg, spots, geometry, log=lambda *a: None)
        if any("nicht erreichbar" in t for _, t in befunde):
            netz_fehlte += 1
        abschnitte.append(("Referenzspots — Form der Antwort, Bewertung, Thermik, Regionalmodell",
                           befunde, ps.tabelle_thermik(tabelle)))

    if "land" in teile:
        print("Landpunkt …")
        try:
            lat, lon = (float(x) for x in args.land.split(","))
        except ValueError:
            print(f"--land braucht lat,lon — nicht {args.land!r}")
            return 1
        befunde = ps.land_offline(cfg)
        if not args.ohne_netz:
            befunde += ps.land_online(cfg, lat, lon, log=lambda *a: None)
        abschnitte.append(("Ein Punkt an Land", befunde, ""))

    ergebnis = None
    if "vergangenheit" in teile:
        print(f"Vergangenheit {args.von} bis {args.bis} … (Messwerte und aufgehobene Vorhersagen, beim ersten Mal ein paar Minuten)")
        grundlinie = ps.grundlinie_lesen()
        vorgabe = (grundlinie or {}).get("paare") if grundlinie and not args.grundlinie_setzen else None
        ergebnis = ps.vergangenheit(cfg, spots, geometry, args.von, args.bis, args.paare,
                                    paare_vorgabe=vorgabe, log=print,
                                    laender=[l.strip() for l in args.dienste.split(",") if l.strip()])
        befunde = list(ergebnis["befunde"])
        if not ergebnis["ergebnisse"]:
            netz_fehlte += 1
        zusatz = ps.tabelle_vergangenheit(ergebnis["ergebnisse"])
        if grundlinie and not args.grundlinie_setzen and ergebnis["ergebnisse"]:
            befunde.append(("ok", f"Grundlinie vom {grundlinie.get('gesetzt')} (Version {grundlinie.get('version')})"))
            befunde.extend(ps.vergleiche_grundlinie(grundlinie, ergebnis))
        elif not grundlinie and ergebnis["ergebnisse"]:
            befunde.append(("warnung", "Noch keine Grundlinie — mit --grundlinie-setzen wird dieser Lauf der Maßstab"))
        abschnitte.append((f"Vergangenheit {args.von} bis {args.bis} — Vorhersage gegen Messung", befunde, zusatz))

    print()
    print(ps.bericht(abschnitte))

    CACHE.joinpath("pruefstand").mkdir(parents=True, exist_ok=True)
    ps.LETZTER_LAUF.write_text(json.dumps({
        "version": __version__, "zeit": datetime.now().isoformat(timespec="minutes"),
        "abschnitte": [{"titel": t, "befunde": b} for t, b, _ in abschnitte],
        "vergangenheit": ergebnis}, indent=1, ensure_ascii=False, default=str), encoding="utf-8")

    if args.grundlinie_setzen and ergebnis and ergebnis["ergebnisse"]:
        ps.grundlinie_schreiben(ergebnis, __version__)
        print(f"\nGrundlinie gesetzt: {ps.GRUNDLINIE.relative_to(ROOT)} ({len(ergebnis['ergebnisse'])} Spots)")

    alle = [b for _, bs, _ in abschnitte for b in bs]
    _, _, fehler = ps.zusammenfassung(alle)
    if fehler:
        return 1
    return 2 if netz_fehlte else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KatalogFehler, KonfigFehler) as exc:      # Meldung statt Traceback
        raise SystemExit(str(exc))
