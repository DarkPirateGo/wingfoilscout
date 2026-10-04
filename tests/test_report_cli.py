from __future__ import annotations
import argparse
import json
import re
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from tests.helpers import cfg as load_cfg, SPOTS, CONFIG, ROOT
from wingscout import report
from wingscout.cli import main, hour_stamps, apply_start
from wingscout.spots import load_spots, eligible
from wingscout.demo import build as demo_build
from wingscout.score import score_hours, build_sessions, rank_trips


def demo_report(tmp: Path, start: str | None = None) -> str:
    args = ["--demo", "--days", "2", "--radius", "400", "--out", str(tmp / "r.html"), "--quiet",
            "--config", str(CONFIG), "--spots", str(SPOTS), "--geometry", str(tmp / "keine.json")]
    if start:
        args += ["--start", start, "--start-name", "Test"]
    code = main(args)
    assert code == 0, code
    return (tmp / "r.html").read_text(encoding="utf-8")


class Bausteine(unittest.TestCase):
    def test_links_zeigen_auf_den_punkt(self):
        spot = {"lat": 51.7625, "lon": 3.854}
        html = report._links(spot, {"lat": 53.55, "lon": 9.99})
        self.assertIn("park4night.com/en/search?lat=51.7625&lng=3.854&z=12", html)
        self.assertIn("windy.com/?51.7625,3.854,12", html)
        self.assertIn("origin=53.55,9.99&destination=51.7625,3.854", html)
        self.assertIn('rel="noopener"', html)

    def test_instagram_links_im_report(self):
        """Die Absprünge kommen aus wingscout/instagram.py — im Ziel unter den
        Links, im Karten-Popup, und als Zeile mit den Funden der Momentaufnahme."""
        html = report._links({"name": "Brouwersdam", "lat": 51.7625, "lon": 3.854}, {"lat": 53.55, "lon": 9.99})
        self.assertIn(' target="_blank" rel="noopener">Instagram</a>', html)
        self.assertIn(">Insta-Suche</a>", html)
        self.assertIn("instagram.com/", html)
        with tempfile.TemporaryDirectory() as d:
            karte = demo_report(Path(d)).split("<h2>Karte</h2>")[1].split("<h2>")[0]
        self.assertIn("(m.ig ? '<a target=\"_blank\" rel=\"noopener\" href=\"' + esc(m.ig) + '\">Instagram</a>' : '')", karte)
        self.assertIn('"ig": "https://www.instagram.com/', karte)

    def test_instagram_zeile(self):
        from unittest import mock
        from wingscout import instagram
        daten = {"stand": "2026-09-18", "spots": {"x": {
            "ort": "https://www.instagram.com/explore/locations/1/x/", "ort_titel": "X <Ort>", "urteil": "wing",
            "funde": [{"url": "https://www.instagram.com/konto/reel/abc/", "titel": "Reel <1>"},
                      {"url": "https://www.instagram.com/p/def/", "titel": "Beitrag"},
                      {"url": "https://www.instagram.com/konto2/", "titel": "K2"},
                      {"url": "https://www.instagram.com/konto3/", "titel": "K3"},
                      {"url": "javascript:alert(1)", "titel": "böse"}]}}}
        with mock.patch.object(instagram, "lade", return_value=daten):
            zeile = report._instagram_zeile({"id": "x", "name": "X"})
            self.assertEqual(report._instagram_zeile({"id": "y", "name": "Y"}), "")
        self.assertIn("title='X &lt;Ort&gt;'>Ort</a>", zeile)
        self.assertIn("title='Reel &lt;1&gt;'>@konto (Reel)</a>", zeile)
        self.assertIn(">Beitrag</a>", zeile)
        self.assertIn(">@konto2</a>", zeile)
        self.assertNotIn("konto3", zeile)                 # höchstens drei
        self.assertIn("1 weitere im Katalog", zeile)      # das vierte gültige — das fünfte war keine Adresse
        self.assertNotIn("javascript:", zeile)
        self.assertIn("Suchtreffer vom 18.09.2026, kein Beleg", zeile)

    def test_fremde_adresse_nur_http(self):
        self.assertEqual(report._safe_url("javascript:alert(1)"), "")
        self.assertEqual(report._safe_url("https://park4night.com/de/place/1"), "https://park4night.com/de/place/1")
        self.assertEqual(report._safe_url(None), "")

    def test_plaketten(self):
        self.assertIn("Hunde verboten", report._rule_pills({"dogs": "no"}))
        self.assertIn("Surfschein", report._rule_pills({"access": "schein"}))
        self.assertEqual(report._rule_pills({}), "")
        # Shorebreak: nur Information, mit der Notiz als Tooltip; „nein" bleibt stumm
        sb = {"shorebreak": {"status": "yes", "note": "bei Swell <steil>", "source": "Q"}}
        self.assertIn("'pill p-chop' title='bei Swell &lt;steil&gt;'>Shorebreak</span>", report._rule_pills(sb))
        self.assertIn(">Shorebreak möglich</span>", report._rule_pills({"shorebreak": {"status": "possible"}}))
        self.assertEqual(report._rule_pills({"shorebreak": {"status": "no"}}), "")
        self.assertEqual(report._rule_pills({"shorebreak": {"status": "unknown"}}), "")
        self.assertIn("bei Swell &lt;steil&gt; <i>(Q)</i>", report._shorebreak_zeile(sb))
        self.assertEqual(report._shorebreak_zeile({"shorebreak": {"status": "yes"}}), "")
        pill = report._ensemble_pill({"members": 40, "p_ride": 0.85, "p_good": 0.6, "p10": 12, "p50": 15, "p90": 19})
        self.assertIn("85 %", pill)
        self.assertIn("12–19 kn", pill)
        self.assertEqual(report._ensemble_pill(None), "")

    def test_thermiksession_zeigt_verlaesslichkeit_statt_ensemble(self):
        """An einer Thermiksession sagt die Plakette, was die Reihenfolge trägt:
        die Verlässlichkeit des Spots — nicht ein Ensemble, das die Thermik
        nicht sehen kann."""
        from datetime import datetime, timedelta
        start = datetime(2026, 7, 15, 13)
        spot = {"id": "ora", "name": "Torbole", "lat": 45.87, "lon": 10.87, "drive_h": 6.0,
                "road_km": 560, "notes": "", "thermal": {"name": "Ora", "reliability": 0.8}}
        session = {"spot": spot, "day": "2026-07-15", "start": start, "end": start + timedelta(hours=4),
                   "hours": 4, "score": 0.7, "peak": 0.8, "wind_min": 14, "wind_max": 17, "gust_max": 20,
                   "dirs": ["S"], "wings": [5.0], "water": "flat", "quality": "good", "temp": 26,
                   "warn": ["Thermik angenommen — Erfahrungswert, kein Modellwind"], "thermal": True,
                   "sicherheit": {"quelle": "thermik", "p": 0.8},
                   "ens": {"members": 40, "p_ride": 0.0, "p_good": 0.0, "p10": 3, "p50": 5, "p90": 7}}
        trip = {"spot": spot, "sessions": [session], "days": ["2026-07-15"], "total_hours": 4,
                "drive_h": 6.0, "acceptable_drive_h": 8.0, "drive_ok": True, "run_len": 1}
        html = report._trip_article(1, trip, load_cfg(), argparse.Namespace(), {"lat": 49.4, "lon": 8.7})
        self.assertIn("Thermik angenommen · 80 % verlässlich", html)
        self.assertNotIn("0 % sicher", html)

    def test_shorebreak_steht_im_ziel_und_im_popup(self):
        """Die Angabe ist Information, keine Regel: sie filtert nicht und
        ändert keinen Score — sie steht als Plakette am Ziel, als Zeile mit
        der Notiz darunter und im Karten-Popup."""
        from datetime import timedelta
        start = datetime(2026, 7, 15, 13)
        spot = {"id": "x", "name": "Strand", "lat": 47.6, "lon": -3.2, "drive_h": 9.0, "road_km": 900,
                "notes": "", "shorebreak": {"status": "yes", "note": "Atlantik, bei Swell", "source": "Q"}}
        session = {"spot": spot, "day": "2026-07-15", "start": start, "end": start + timedelta(hours=3),
                   "hours": 3, "score": 0.6, "peak": 0.7, "wind_min": 15, "wind_max": 18, "gust_max": 22,
                   "dirs": ["W"], "wings": [5.0], "water": "chop", "quality": "ok", "temp": 20,
                   "warn": [], "sicherheit": {"quelle": "ensemble", "p": 0.6}}
        trip = {"spot": spot, "sessions": [session], "days": ["2026-07-15"], "total_hours": 3,
                "drive_h": 9.0, "acceptable_drive_h": 8.0, "drive_ok": False, "run_len": 1}
        html = report._trip_article(1, trip, load_cfg(), argparse.Namespace(), {"lat": 49.4, "lon": 8.7})
        self.assertIn("title='Atlantik, bei Swell'>Shorebreak</span>", html)
        self.assertIn("<span class='pill p-chop'>Shorebreak</span> Atlantik, bei Swell <i>(Q)</i>", html)
        # Im Popup: die Karte bekommt Status und Notiz mit
        with tempfile.TemporaryDirectory() as d:
            args = ["--demo", "--days", "1", "--radius", "900", "--out", str(Path(d) / "r.html"), "--quiet",
                    "--config", str(CONFIG), "--spots", str(SPOTS), "--geometry", str(Path(d) / "keine.json")]
            self.assertEqual(main(args), 0)
            html = (Path(d) / "r.html").read_text(encoding="utf-8")
        karte = html.split("<h2>Karte</h2>")[1].split("<h2>")[0]
        daten = json.loads(re.search(r"var KARTE = (\{.*?\});\n", karte, re.S).group(1)
                           .replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&"))
        mit = [m for m in daten["markers"] if m.get("sb") in ("yes", "possible")]
        self.assertTrue(mit, "im Umkreis von 900 km liegt mindestens ein Spot mit Shorebreak-Angabe")
        self.assertTrue(all(m["sb_note"] for m in mit))
        self.assertIn("m.sb === 'yes' ? 'Shorebreak' : 'Shorebreak möglich'", karte)

    def test_kommentar_im_ziel_und_im_popup(self):
        """Der eigene Kommentar steht am Ziel und im Karten-Popup — als Kasten,
        den das Skript zum Editor macht. Escaped, mit Umbruch als Text."""
        from datetime import timedelta
        start = datetime(2026, 7, 15, 13)
        spot = {"id": "x", "name": "Strand", "lat": 47.6, "lon": -3.2, "drive_h": 9.0, "road_km": 900,
                "notes": "", "comment": "Parken am Ende\n<b>der</b> Straße"}
        session = {"spot": spot, "day": "2026-07-15", "start": start, "end": start + timedelta(hours=3),
                   "hours": 3, "score": 0.6, "peak": 0.7, "wind_min": 15, "wind_max": 18, "gust_max": 22,
                   "dirs": ["W"], "wings": [5.0], "water": "chop", "quality": "ok", "temp": 20,
                   "warn": [], "sicherheit": {"quelle": "ensemble", "p": 0.6}}
        trip = {"spot": spot, "sessions": [session], "days": ["2026-07-15"], "total_hours": 3,
                "drive_h": 9.0, "acceptable_drive_h": 8.0, "drive_ok": False, "run_len": 1}
        html = report._trip_article(1, trip, load_cfg(), argparse.Namespace(), {"lat": 49.4, "lon": 8.7})
        self.assertIn("<div class='kmt' data-id='x' data-text='Parken am Ende\n&lt;b&gt;der&lt;/b&gt; Straße'></div>", html)
        with tempfile.TemporaryDirectory() as d:
            voll = demo_report(Path(d))
        self.assertIn("window.WSKommentar", voll)
        self.assertIn("window.WSKommentar.alle();", voll)
        self.assertIn("fetch('/katalog/kommentar'", voll)
        karte = voll.split("<h2>Karte</h2>")[1].split("<h2>")[0]
        self.assertIn('data-id="\' + esc(m.id) + \'" data-text="\' + esc(m.kmt) + \'"', karte)
        daten = json.loads(re.search(r"var KARTE = (\{.*?\});\n", karte, re.S).group(1)
                           .replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&"))
        self.assertTrue(all("id" in m and "kmt" in m for m in daten["markers"]))
        self.assertIn("WSKommentar.alle(e.popup.getElement())", karte)

    def test_sessionstabelle_sortierbar(self):
        """Alle Sessions in der Tabelle, jede Zelle mit Sortierwert, die
        Spalten anklickbar; gezeigt werden die ersten 40 der Reihenfolge."""
        from datetime import timedelta
        start = datetime(2026, 7, 15, 13)

        def session(name, hours, wmin, wmax, quality, water, score):
            spot = {"id": name.lower(), "name": name, "lat": 47.6, "lon": -3.2, "drive_h": 1.0, "road_km": 10, "notes": ""}
            return {"spot": spot, "day": "2026-07-15", "start": start, "end": start + timedelta(hours=hours),
                    "hours": hours, "score": score, "peak": score, "wind_min": wmin, "wind_max": wmax, "gust_max": wmax + 3,
                    "dirs": ["W", "WNW"], "wings": [4.2, 5.0, 6.5], "water": water, "quality": quality, "temp": 20,
                    "warn": [], "geo": True}
        sessions = [session("Alpha", 3, 12, 18, "sideshore", "flat", 0.9), session("Beta", 6, 20, 28, "auflandig", "wave", 0.7),
                    session("Gamma", 2, 10, 14, "ablandig", "chop", 0.5), session("Delta <x>", 4, 15, 16, "best", "flat", 0.8)]
        html = report._sessions_tabelle(sorted(sessions, key=lambda x: -x["score"]))
        self.assertIn("<details class='abschnitt' id='sessions'><summary><h2>Alle Sessions</h2>", html)
        for k in ("spot", "wann", "dauer", "wind", "lage", "richtung", "wing", "wasser", "score"):
            self.assertIn(f"<th data-k='{k}'", html)
        self.assertIn("<th data-k='score' title='Bewertung, beste zuerst' class='sort'>Score</th>", html)
        # Sortierwerte: Wind = Maximum vor Minimum, Lage und Wasser als Rang
        self.assertIn("<td class='n' data-v='2820'>20–28 kn</td>", html)
        self.assertIn("<td data-v='0'><span class='pill p-flat'>sideshore</span></td>", html)
        self.assertIn("<td data-v='3'><span class='pill p-wave'>auflandig</span></td>", html)
        self.assertIn("<td data-v='4'><span class='pill p-chop'>ablandig</span></td>", html)
        self.assertIn("<td data-v='1'><span class='pill p-flat'>Top-Richtung</span></td>", html)
        self.assertIn("<td data-v='2'><span class='pill p-wave'>Welle</span></td>", html)
        self.assertIn("<td data-v='delta &lt;x&gt;'>Delta &lt;x&gt;</td>", html)
        self.assertIn("data-v='4.2'>4.2–6.5 m²", html)
        self.assertIn("getElementById('sesstab')", html)
        # Mehr als 40: alle in der Tabelle, ab der 41. versteckt
        viele = [session(f"S{i}", 2, 10, 15, "sideshore", "flat", 1 - i / 100) for i in range(45)]
        html = report._sessions_tabelle(viele)
        self.assertEqual(html.count("<tr>"), 40 + 1)             # 40 Zeilen + Kopfzeile
        self.assertEqual(html.count("<tr class='mehr'>"), 5)
        self.assertIn("alle 45 zeigen", html)
        # Im Demo-Report ist die Tabelle drin, die alte Überschrift nicht mehr
        with tempfile.TemporaryDirectory() as d:
            voll = demo_report(Path(d))
        self.assertIn("id='sesstab'", voll)
        self.assertNotIn("Alle Sessions nach Qualität", voll)

    def test_stellplatzblock_escaped(self):
        camping = {"places": [{"km": 1.0, "name": "<b>x</b>", "kind_label": "C", "rating": 4.0, "reviews": 2,
                               "services": ["animaux"], "lat": 51.7, "lon": 3.8,
                               "url": "javascript:alert(1)"}], "ohne_hundeangabe": 3}
        html = report._camping_block(camping, {"lat": 51.7, "lon": 3.8})
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)
        self.assertNotIn("javascript:", html)
        self.assertIn("3 weitere", html)

    def test_windy_statt_maps_im_raster(self):
        """Im Stundenraster fragt man nach Wind, nicht nach dem Weg.

        Der Name führt auf Windy, die Kilometerangabe daneben auf die Route —
        zwei Fragen, zwei Ziele, eine Zeile.
        """
        spot = {"lat": 51.7625, "lon": 3.854}
        self.assertEqual(report._windy(spot), "https://www.windy.com/?51.7625,3.854,12")
        self.assertEqual(report._windy(spot, 9), "https://www.windy.com/?51.7625,3.854,9")
        with tempfile.TemporaryDirectory() as d:
            html = demo_report(Path(d))
        raster = html.split("<h2>Stundenraster</h2>")[1].split("<h2>")[0]
        self.assertIn("windy.com/?", raster)
        self.assertIn("Wind und Vorhersage auf Windy", raster)
        self.assertIn("class='hmkm' href='https://www.google.com/maps/dir/", raster)
        self.assertNotIn("title='Route in Google Maps'>", raster.split("class='hmkm'")[0])

    def test_deutsche_wochentage(self):
        """strftime('%a') liefert unter der C-Locale englische Kürzel."""
        self.assertEqual(report._tag(datetime(2026, 9, 15, 14)), "Di 15.09.")
        self.assertEqual(report._tag(datetime(2026, 9, 13), lang=False), "So")
        with tempfile.TemporaryDirectory() as d:
            html = demo_report(Path(d))
        for englisch in ("Mon ", "Tue ", "Wed ", "Thu ", "Fri ", "Sat ", "Sun "):
            self.assertNotIn(englisch, html, f"englischer Wochentag {englisch!r} im Report")

    def test_karte_hat_ebenen_und_stundenband(self):
        """Die Karte soll eine Ansicht sein, keine Illustration."""
        with tempfile.TemporaryDirectory() as d:
            html = demo_report(Path(d))
        karte = html.split("<h2>Karte</h2>")[1].split("<h2>")[0]
        for schalter in ("id=\"l_top\"", "id=\"l_hit\"", "id=\"l_quiet\"", "id=\"l_out\"",
                         "id=\"l_names\"", "id=\"l_ring\"", "id=\"l_windy\"",
                         "id=\"b_top\"", "id=\"b_all\"", "id=\"b_full\""):
            self.assertIn(schalter, karte)
        # Ein Klick zeigt die Details — der Schalter für den Sprung zu Windy
        # ist da, aber aus. Der Name im Popup führt trotzdem zu Windy.
        self.assertIn('id="l_windy"', karte)
        self.assertNotIn('id="l_windy" checked', karte)
        self.assertIn("window.open('https://www.windy.com/?'", karte)
        self.assertIn("var windyUrl = 'https://www.windy.com/?'", karte)
        self.assertIn('class="titel"', karte)
        daten = json.loads(re.search(r"var KARTE = (\{.*?\});\n", karte, re.S).group(1)
                           .replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&"))
        self.assertEqual(len(daten["stunden"]), sum(t[1] for t in daten["tage"]))
        mit_band = [m for m in daten["markers"] if m["sc"]]
        self.assertTrue(mit_band)
        for m in mit_band:
            self.assertEqual(len(m["sc"]), len(daten["stunden"]))
            self.assertEqual(len(m["wd"]), 2 * len(daten["stunden"]))
            self.assertTrue(m["sc"].isdigit() and m["wd"].isdigit())
        # Ausgeschlossene Spots liegen in einer eigenen Ebene und sind aus
        self.assertTrue(any(m["kind"] == "out" for m in daten["markers"]))

    def test_flaechen_auf_der_karte_fangen_keine_klicks(self):
        """Der Radiuskreis lag als zuletzt gezeichnete, gefüllte Fläche über
        allen Punkten und schluckte innerhalb des Suchradius jeden Klick —
        seit 1.0.0, unbemerkt hinter dem Thermikring-Fehler von 1.5.3. Jede
        `L.circle`-Fläche ist Dekoration: nicht interaktiv, eigene Ebene unter
        den Punkten, und die Ebene ohne pointer-events."""
        # Das Kartenskript steht seit 1.16.0 in wingscout/web/karte.js — ohne
        # die verdoppelten Klammern der f-Vorlage
        text = (ROOT / "wingscout" / "web" / "karte.js").read_text(encoding="utf-8")
        stellen = [m.start() for m in re.finditer(r"pane: 'dekor'", text)]
        self.assertGreaterEqual(len(stellen), 2, "Radiuskreis und Thermikring liegen auf der Dekor-Ebene")
        for pos in stellen:
            self.assertIn("interactive: false", text[pos - 400:pos + 40], text[pos - 120:pos])
        # Der Radiuskreis selbst — die Fläche, die alles verdeckte
        ring = text[text.index("var ring = L.circle("):]
        ring = ring[:ring.index("});") + 3]
        self.assertIn("interactive: false", ring)
        self.assertIn("pane: 'dekor'", ring)
        self.assertIn("map.getPane('dekor').style.pointerEvents = 'none'", text)
        self.assertLess(text.index("createPane('dekor')"), text.index("L.circleMarker("),
                        "die Ebene muss vor dem ersten Punkt angelegt sein")

    def test_stellplaetze_als_eigene_ebene(self):
        """Park4Night-Plätze gehören auf die Karte, nicht nur in die Liste.

        Ohne Netz gibt es im Demo-Lauf keine Plätze, deshalb hier von Hand
        eingesetzt — mitsamt einem bösartigen Namen, denn diese Namen kommen
        von einem fremden Server.
        """
        cfg = load_cfg()
        spots = load_spots(SPOTS)
        keep, dropped = eligible(spots, cfg, date.today().month, 300, None)
        keep = keep[:3]
        fcs = demo_build(keep, 2)
        all_rows, sessions = {}, []
        for sp in keep:
            rows = score_hours(sp, fcs[sp["id"]], cfg)
            all_rows[sp["id"]] = (sp, rows)
            sessions.extend(build_sessions(sp, rows, cfg))
        trips = rank_trips(sessions, cfg)
        self.assertTrue(trips)
        trips[0]["camping"] = {"ohne_hundeangabe": 2, "places": [{
            "name": "</script><b>Platz</b>", "lat": trips[0]["spot"]["lat"] + 0.02,
            "lon": trips[0]["spot"]["lon"], "km": 2.4, "rating": 4.2, "reviews": 11,
            "url": "javascript:alert(1)", "kind_label": "Stellplatz", "services": ["animaux"],
        }]}
        args = argparse.Namespace(days=2, radius=300, nights=0, _n_spots=3, _n_verified=0, _n_geo=0,
                                  _alerts={}, _protected={}, _n_sessions=len(sessions), _n_trips=len(trips))
        html = report.render(trips, all_rows, dropped, cfg, args, demo=True)
        karte = html.split("<h2>Karte</h2>")[1].split("<h2>")[0]
        self.assertIn('id="l_camp"', karte)
        daten = json.loads(re.search(r"var KARTE = (\{.*?\});\n", karte, re.S).group(1)
                           .replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&"))
        self.assertEqual(len(daten["camps"]), 1)
        self.assertEqual(daten["camps"][0]["url"], "")          # javascript: fliegt raus
        self.assertNotIn("</script><b>Platz</b>", karte)        # Name nie als Markup

    def test_knotenskala_folgt_dem_wohlfuehlband(self):
        """Grün ist das Band aus der Oberfläche, die roten Enden weichen aus."""
        g = report.knoten_grenzen({"wind": {"preferred_low": 14, "preferred_high": 24}})
        self.assertEqual((g["rot_unter"], g["gruen_von"], g["gruen_bis"],
                          g["rot_ueber"], g["dunkel_ueber"]), (11, 14, 24, 26, 30))
        for kn, farbe in ((8, report.ROT), (11, report.ORANGE), (13, report.ORANGE),
                          (14, report.GRUEN), (24, report.GRUEN), (25, report.ORANGE),
                          (26, report.ORANGE), (27, report.ROT), (30, report.ROT),
                          (31, report.DUNKELROT), (45, report.DUNKELROT)):
            self.assertEqual(report.knoten_farbe(kn, g), farbe, f"{kn} kn")

        # Band 14–28 gegen rot ab 26: das rote Ende weicht aus, statt das
        # Band zu zerschneiden — sonst wäre eine Stunde grün und rot zugleich.
        g2 = report.knoten_grenzen({"wind": {"preferred_low": 14, "preferred_high": 28}})
        self.assertEqual(g2["rot_ueber"], 30)
        self.assertEqual(report.knoten_farbe(27, g2), report.GRUEN)
        # Dunkelrot rutscht nie unter das rote Ende: sonst gäbe es eine Stunde,
        # die gleichzeitig hellrot und dunkelrot wäre.
        self.assertEqual(g2["dunkel_ueber"], 30)
        self.assertEqual(report.knoten_farbe(31, g2), report.DUNKELROT)
        g4 = report.knoten_grenzen({"wind": {"preferred_low": 16, "preferred_high": 34}})
        self.assertEqual(g4["dunkel_ueber"], 36)

        # Ein Band, das unter das untere rote Ende reicht, schiebt es mit.
        g3 = report.knoten_grenzen({"wind": {"preferred_low": 9, "preferred_high": 20}})
        self.assertEqual(g3["rot_unter"], 9)
        self.assertEqual(report.knoten_farbe(9, g3), report.GRUEN)

    def test_raster_hat_beide_faerbungen(self):
        with tempfile.TemporaryDirectory() as d:
            html = demo_report(Path(d))
        raster = html.split("<h2>Stundenraster</h2>")[1]
        self.assertIn("id='f_guete'", raster)
        self.assertIn("id='f_knoten'", raster)
        self.assertIn("id='leg_knoten'", raster)
        self.assertIn("Wohlfühlband", raster)
        # Jede Zelle trägt ihre Knoten mit, sonst kann der Umschalter nichts tun
        zellen = re.findall(r"<div class='cell[^']*' style='background:[^']*' data-kn='(-?\d+)'", raster)
        self.assertGreater(len(zellen), 100)
        self.assertTrue(all(z.lstrip("-").isdigit() for z in zellen))
        self.assertIn("data-aus='1'", raster)              # Nachtstunden sind markiert

    def test_reihenfolge_drei_dann_raster_dann_rest(self):
        """Die besten drei, die Karte, das Raster — der Rest hinter einer Klappe.
        Seit 2.3.0 stehen die besten drei vor der Karte."""
        with tempfile.TemporaryDirectory() as d:
            html = demo_report(Path(d))
        folge = [m for m in re.findall(r"<h2>([^<]+)</h2>", html)]
        # "Thermikziele" und "Wann die Thermik läuft" erscheinen nur, wenn im
        # Zeitraum überhaupt Thermikspots in Frage kommen.
        erwartet = ["Die besten drei", "Karte", "Thermikziele",
                    "Wann die Thermik läuft", "Stundenraster"]
        self.assertEqual([x for x in folge[:5] if x in erwartet],
                         [x for x in erwartet if x in folge])
        vor = html.split("<h2>Stundenraster</h2>")[0]
        self.assertEqual(vor.count("<details class='trip'"), 3)
        nach = html.split("<h2>Stundenraster</h2>")[1]
        self.assertIn("<details class='abschnitt' id='weitere'>", nach)
        self.assertIn("<h2>Weitere Ziele</h2>", nach)
        # Die Nummerierung läuft über beide Blöcke hinweg durch
        raenge = [int(x) for x in re.findall(r"<span class='rank'>(\d+)</span>", html)]
        self.assertEqual(raenge[:4], [1, 2, 3, 4])
        self.assertEqual(raenge, list(range(1, len(raenge) + 1)))
        # Die Klappe steht vor den Einzelartikeln, nicht dahinter
        self.assertLess(nach.index("<details class='abschnitt' id='weitere'>"), nach.index("<details class='trip'"))

    def test_fahrtnotiz_ist_markup_kein_text(self):
        """Das <span> mit der Herkunft der Fahrzeit stand wörtlich im Report."""
        with tempfile.TemporaryDirectory() as d:
            html = demo_report(Path(d))
        self.assertNotIn("&lt;span title=", html)
        self.assertIn("title='Luftlinie mal Umwegfaktor", html)

    def test_version_steht_im_report(self):
        """Damit man später weiß, mit welchem Stand ein Report entstanden ist."""
        from wingscout import __version__
        with tempfile.TemporaryDirectory() as d:
            html = demo_report(Path(d))
        self.assertIn(f"Wingfoilscout {__version__}", html)
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_stundenachse(self):
        rows = [{"t": datetime(2026, 9, 12) + __import__("datetime").timedelta(hours=i)} for i in range(72)]
        days, ticks = report._hour_axis(rows)
        self.assertEqual(days.count("hmaxis"), 3)
        self.assertEqual(len(re.findall(r"<span[^>]*>0[0369]|1[258]|2[1]</span>", ticks)) > 0, True)
        self.assertEqual(report._hour_axis([]), ("", ""))


class Gestaffelt(unittest.TestCase):
    """Der Report in zwei Stufen (1.20.0, nach der Rückmeldung eines Mitlesers:
    „zu überfrachtet — einfache Ansicht mit Basisinfo, dann aufklappen“).
    Zugeklappt je Ziel zwei Zeilen und je Abschnitt eine Überschrift;
    aufgeklappt alles, was bis 1.19.2 immer dastand."""

    def _trip(self, sessions=2, drive_ok=True, thermal=False, alerts=0, protected=0):
        from datetime import timedelta
        spot = {"id": "x", "name": "Strand <b>", "lat": 51.7, "lon": 3.8, "drive_h": 5.0, "road_km": 400,
                "notes": "eigene Notiz", "water_body": "sea"}
        if thermal:
            spot["thermal"] = {"name": "Ora", "note": "nachmittags"}
        sess = []
        for k in range(sessions):
            start = datetime(2026, 9, 24 + k, 13)
            sess.append({"spot": spot, "day": start.strftime("%Y-%m-%d"), "start": start,
                         "end": start + timedelta(hours=3 + k), "hours": 3 + k, "score": 0.5 + 0.2 * k,
                         "peak": 0.7, "wind_min": 15 + k, "wind_max": 18 + k, "gust_max": 22, "dirs": ["W"],
                         "wings": [4.2, 5.0, 6.5], "water": "chop", "quality": "sideshore", "geo": True,
                         "temp": 20, "warn": [], "sicherheit": {"quelle": "ensemble", "p": 0.6}})
        trip = {"spot": spot, "sessions": sess, "days": [s["day"] for s in sess], "total_hours": sum(s["hours"] for s in sess),
                "drive_h": 5.0, "acceptable_drive_h": 8.0, "drive_ok": drive_ok, "run_len": 1}
        args = argparse.Namespace(
            _alerts={"x": [{"level": 3, "level_name": "Orange", "event": "Sturm", "area": "Küste"}] * alerts},
            _protected={"x": [{"kind": "Schutzgebiet", "name": f"Gebiet {i}"} for i in range(protected)]})
        return trip, args

    def test_anlauf_und_welle_mit_trennpunkt(self):
        """Hinter „Welle 0.17 m“ folgte der Hinweis ohne Trennzeichen — am
        Handy las es sich als „0.17 metwas Regen“ (2.1.0)."""
        trip, args = self._trip(sessions=1)
        trip["sessions"][0].update(fetch_km=1.0, wave_m=0.17, warn=["etwas Regen"])
        html = report._trip_article(1, trip, load_cfg(), args, {"lat": 49.4, "lon": 8.7})
        self.assertIn("Welle 0.17 m</span> · etwas Regen", html)
        trip["sessions"][0].update(warn=[], quality="")
        html = report._trip_article(1, trip, load_cfg(), args, {"lat": 49.4, "lon": 8.7})
        self.assertNotIn("</span> ·  ·", html)

    def test_zugeklappt_zwei_zeilen(self):
        trip, args = self._trip()
        html = report._trip_article(4, trip, load_cfg(), args, {"lat": 49.4, "lon": 8.7})
        self.assertTrue(html.startswith("<details class='trip' id='ziel-4'><summary>"))
        self.assertNotIn("<details class='trip' id='ziel-4' open", html)         # zu, bis jemand klickt
        kopf = html.split("</summary>")[0]
        self.assertIn("<span class='rank'>4</span>", kopf)
        self.assertIn("<span class='name'>Strand &lt;b&gt;</span>", kopf)
        # Die beste Session (höchster Score, hier die zweite) als eine Zeile — und
        # die andere nur als Zahl
        self.assertIn("Fr 25.09. 13–17 Uhr · 16–19 kn · 4.2–6.5 m² · sideshore", re.sub(r"<[^>]+>", "", kopf))
        # Teile bleiben beisammen — am Handy kein Umbruch zwischen Zahl und Einheit
        self.assertIn("<span class='nw'>4.2–6.5 m²</span>", kopf)
        self.assertIn("<span class='mehrsess'>+1 weitere Session</span>", kopf)
        self.assertIn("5.0 h Fahrt (geschätzt)</span> · 7 h Wasser an 2 Tagen", kopf)
        self.assertIn("<span class='pill p-flat'>Fahrt lohnt</span>", kopf)
        # Was nur aufgeklappt zu sehen ist
        rumpf = html.split("</summary>")[1]
        self.assertTrue(rumpf.startswith("<div class='ausfuehrlich'>"))
        self.assertIn("<div class='metazeile'>Regel erlaubt 8.0 h</div>", rumpf)
        self.assertIn("<div class='sess'>", rumpf)
        self.assertEqual(rumpf.count("<div class='srow'"), 2)
        self.assertIn("eigene Notiz", rumpf)
        self.assertTrue(html.endswith("</div></details>"))

    def test_plaketten_im_kopf_nur_das_entscheidende(self):
        trip, args = self._trip(sessions=1, drive_ok=False, thermal=True, alerts=2, protected=3)
        html = report._trip_article(1, trip, load_cfg(), args, {"lat": 49.4, "lon": 8.7})
        kopf = html.split("</summary>")[0]
        for pill in ("<span class='pill p-chop'>Fahrt grenzwertig</span>", "<span class='pill p-alert'>2 Warnungen</span>",
                     "<span class='pill p-ok'>Thermik</span>", "<span class='pill p-info'>3 Hinweise</span>"):
            self.assertIn(pill, kopf)
        self.assertNotIn("weitere Session", kopf)
        self.assertNotIn("Gebiet 0", kopf)                 # der Wortlaut steht erst aufgeklappt
        self.assertIn("Gebiet 0", html)
        self.assertIn("deine Regel gibt nur 8.0 h her", html.split("</summary>")[1])

    def test_abschnitte_sind_klappen_und_die_ansicht_hat_einen_schalter(self):
        with tempfile.TemporaryDirectory() as d:
            html = demo_report(Path(d))
        for kennung, titel in (("raster", "Stundenraster"), ("sessions", "Alle Sessions"), ("weitere", "Weitere Ziele"),
                               ("ausgeschlossen", "Nicht berücksichtigt"), ("bewertung", "Wie das Wetter bewertet wird")):
            self.assertIn(f"<details class='abschnitt' id='{kennung}'><summary><h2>{titel}</h2><span class='hint'>", html)
        self.assertNotIn("<details class='abschnitt' id='raster' open", html)
        self.assertIn("<div class='ansicht' role='group' aria-label='Ansicht'>", html)
        self.assertIn("<button type='button' data-ansicht='ausfuehrlich'>Ausführlich</button>", html)
        # Das Skript dazu trägt die Nonce der Seite wie jedes andere
        nonce = re.search(r"'nonce-([A-Za-z0-9_-]+)'", html).group(1)
        self.assertIn(f"<script nonce='{nonce}'>\n" + report.ANSICHT_JS[:40], html)
        self.assertIn("localStorage", report.ANSICHT_JS)
        self.assertIn("details.abschnitt:not(#weitere)", report.ANSICHT_JS)    # 40 Karten auf einmal will niemand
        # Ein Ziel je Klappe, keine Karte mehr ohne Klappe
        self.assertNotIn("<article", html)
        self.assertEqual(html.count("<details class='trip'"), html.count("<span class='rank'>"))


class GanzerReport(unittest.TestCase):
    def test_demo_lauf_schreibt_report(self):
        with tempfile.TemporaryDirectory() as d:
            html = demo_report(Path(d))
        for teil in ("<h2>Die besten drei</h2>", "<h2>Stundenraster</h2>", "Demo-Lauf", "leaflet",
                     "integrity=", "Uhrzeit", "class='hmkm'"):
            self.assertIn(teil, html)
        self.assertNotIn("{{", html.split("<script")[0])       # keine unaufgelösten Vorlagen

    def test_startpunkt_veraendert_ergebnis(self):
        with tempfile.TemporaryDirectory() as d:
            a = demo_report(Path(d))
            b = demo_report(Path(d), start="51.7369, 3.8285")
        self.assertIn("<b>Start</b> Hamburg", a)
        self.assertIn("<b>Start</b> Test", b)
        self.assertNotEqual(a, b)

    def test_boese_spotnamen_werden_escaped(self):
        cfg = load_cfg()
        spots = load_spots(SPOTS)
        keep, dropped = eligible(spots, cfg, date.today().month, 300, None)
        keep = keep[:3]
        keep[0]["name"] = "<script>alert(1)</script>"
        keep[0]["notes"] = "\"><img src=x onerror=alert(1)>"
        fcs = demo_build(keep, 2)
        all_rows, sessions = {}, []
        for s in keep:
            rows = score_hours(s, fcs[s["id"]], cfg)
            all_rows[s["id"]] = (s, rows)
            sessions.extend(build_sessions(s, rows, cfg))
        trips = rank_trips(sessions, cfg)
        args = argparse.Namespace(days=2, radius=300, nights=0, _n_spots=3, _n_verified=0, _n_geo=0,
                                  _alerts={}, _protected={}, _n_sessions=len(sessions), _n_trips=len(trips))
        html = report.render(trips, all_rows, dropped, cfg, args, demo=True)
        # Der Text darf nur noch entschärft vorkommen: als &lt;…&gt; im HTML oder
        # als \u003c…\u003e im JSON der Karte — nie als echtes Tag.
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<img src=x onerror", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("\\u003cscript\\u003e", html)


class Kommandozeile(unittest.TestCase):
    def test_stundenstempel(self):
        # `end` ist exklusiv wie bei einer Session (letzte Stunde plus eins):
        # 12–14 Uhr sind die Stunden 12 und 13, nicht auch noch 14.
        stamps = hour_stamps(datetime(2026, 9, 13, 12), datetime(2026, 9, 13, 14))
        self.assertEqual(stamps, ["2026-09-13T12:00", "2026-09-13T13:00"])
        self.assertEqual(hour_stamps(datetime(2026, 9, 13, 12), datetime(2026, 9, 13, 12)),
                         ["2026-09-13T12:00"])

    def test_startpunkt_uebernehmen(self):
        cfg = load_cfg()
        lines = []
        self.assertTrue(apply_start(cfg, "51.7625, 3.854", "Dam", lines.append))
        self.assertEqual(cfg["rider"]["home"]["name"], "Dam")
        self.assertFalse(apply_start(cfg, "Quatsch", None, lines.append))
        self.assertEqual(cfg["rider"]["home"]["name"], "Dam")       # unlesbar ändert nichts
        self.assertTrue(any("nicht lesbar" in l for l in lines))

    def test_kein_spot_im_radius_ist_kein_absturz(self):
        with tempfile.TemporaryDirectory() as d:
            code = main(["--demo", "--days", "1", "--radius", "10", "--start", "0.0, 0.0",
                         "--out", str(Path(d) / "r.html"), "--quiet", "--config", str(CONFIG),
                         "--spots", str(SPOTS), "--geometry", str(Path(d) / "keine.json")])
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
