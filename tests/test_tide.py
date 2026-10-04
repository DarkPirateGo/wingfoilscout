"""Gezeiten (1.18.0): Scheitel auf die Minute, Lage je Stunde, Tidenfenster,
die drei Stufen im Katalog, die Anzeige im Report und der Schalter im Katalog."""
from __future__ import annotations
import argparse
import calendar
import json
import math
import re
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

import yaml

from tests.helpers import cfg as load_cfg, CONFIG, SPOTS
from wingscout import tide, score, report, spotedit
from wingscout.spots import load_spots, tide_normieren
import wingscout.webui as w


def kurve(hw: datetime, stunden: int = 72, hub_m: float = 2.0, start: datetime | None = None) -> dict:
    """Ein sauberer Tidenverlauf: Hochwasser um `hw`, Periode 12,42 h, {Zeit: m}."""
    start = start or hw.replace(hour=0, minute=0)
    aus = {}
    for i in range(stunden):
        t = start + timedelta(hours=i)
        dt = (t - hw).total_seconds() / 3600
        aus[t.strftime("%Y-%m-%dT%H:%M")] = round(hub_m / 2 * math.cos(2 * math.pi * dt / 12.42), 4)
    return aus


class Scheitel(unittest.TestCase):
    def test_hochwasser_auf_die_minute_aus_stundenwerten(self):
        """Das Modell liefert volle Stunden; der Scheitel liegt dazwischen. Die
        Parabel durch die drei Stunden trifft ihn — bis 1.17.0 stand „14:00“."""
        ev = tide.extrema(kurve(datetime(2026, 9, 24, 2, 25)))
        self.assertEqual([e["art"] for e in ev[:4]], ["HW", "NW", "HW", "NW"])
        self.assertEqual(ev[0]["zeit"].strftime("%H:%M"), "02:25")
        self.assertEqual(ev[2]["zeit"].strftime("%H:%M"), "14:50")        # + 12 h 25 min
        self.assertAlmostEqual(ev[0]["hoehe"], 1.0, places=2)
        self.assertAlmostEqual(ev[1]["hoehe"], -1.0, places=2)
        self.assertAlmostEqual(tide.hub(ev), 2.0, places=1)
        alt = score.tide_events(kurve(datetime(2026, 9, 24, 2, 25)), "2026-09-24")
        self.assertEqual(alt[:2], [("HW", "02:25"), ("NW", "08:38")])

    def test_ohne_stundenraster_keine_interpolation(self):
        """Lücken im Verlauf: dann bleibt es beim gemessenen Punkt."""
        series = {"2026-09-24T00:00": 0.0, "2026-09-24T02:00": 1.0, "2026-09-24T03:00": 0.9,
                  "2026-09-24T04:00": 0.5}
        ev = tide.extrema(series)
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["zeit"], datetime(2026, 9, 24, 2, 0))
        self.assertEqual(tide.extrema({}), [])
        self.assertIsNone(tide.hub([]))

    def test_lage_und_stauwasser(self):
        ev = tide.extrema(kurve(datetime(2026, 9, 24, 2, 25)))
        def art(h, m=30):
            return tide.lage(datetime(2026, 9, 24, h, m), ev)["art"]
        self.assertEqual(art(1), "auflaufend")
        self.assertEqual(art(2), "hochwasser")            # 02:30 liegt 5 min nach dem Scheitel
        self.assertEqual(art(2, 56), "ablaufend")         # 31 min danach nicht mehr
        self.assertEqual(art(5), "ablaufend")
        self.assertEqual(art(8, 40), "niedrigwasser")
        self.assertEqual(art(13), "auflaufend")
        self.assertEqual(tide.lage_text(datetime(2026, 9, 24, 13, 30), ev), "auflaufend, Hochwasser um 14:50")
        self.assertEqual(tide.lage_text(datetime(2026, 9, 24, 14, 40), ev), "Hochwasser")
        self.assertIsNone(tide.lage(datetime(2026, 9, 24), []))
        self.assertEqual(tide.lage_text(datetime(2026, 9, 24), []), "")


class Fenster(unittest.TestCase):
    def setUp(self):
        self.ev = tide.extrema(kurve(datetime(2026, 9, 24, 2, 25)))

    def test_lesen_aus_dem_katalog(self):
        self.assertIsNone(tide.fenster_lesen({}))
        self.assertIsNone(tide.fenster_lesen({"tide": {"fahrbar": "quatsch"}}))
        f = tide.fenster_lesen({"tide": tide_normieren({"fahrbar": "Hochwasser", "stunden": "1.5"})})
        self.assertEqual(f, {"fahrbar": "hochwasser", "stunden": 1.5})
        self.assertEqual(tide.fenster_lesen({"tide": tide_normieren("auflaufend")}),
                         {"fahrbar": "auflaufend", "stunden": 2.0})
        self.assertEqual(tide.fenster_lesen({"tide": {"fahrbar": "niedrigwasser", "stunden": 99}})["stunden"], 6.0)
        self.assertEqual(tide.fenster_text({"fahrbar": "hochwasser", "stunden": 2.0}), "HW ± 2 h")
        self.assertEqual(tide.fenster_text({"fahrbar": "ablaufend", "stunden": 2.0}), "nur ablaufend")
        self.assertEqual(tide.fenster_text(None), "")

    def test_um_hochwasser(self):
        f = {"fahrbar": "hochwasser", "stunden": 2.0}
        drin = [h for h in range(24) if tide.im_fenster(datetime(2026, 9, 24, h, 30), self.ev, f)]
        # HW 02:25 → 00:25–04:25 (Stundenmitten 0:30 … 3:30); HW 14:50 → 12:50–16:50
        self.assertEqual(drin, [0, 1, 2, 3, 13, 14, 15, 16])
        self.assertEqual(tide.fenster_zeiten(self.ev, f, "2026-09-24"), [("00:25", "04:25"), ("12:50", "16:50")])

    def test_um_niedrigwasser_und_halbtiden(self):
        nw = {"fahrbar": "niedrigwasser", "stunden": 1.0}
        drin = [h for h in range(24) if tide.im_fenster(datetime(2026, 9, 24, h, 30), self.ev, nw)]
        self.assertEqual(drin, [8, 9, 20, 21])                              # NW 08:38 und 21:03
        auf = {"fahrbar": "auflaufend", "stunden": 2.0}
        drin = [h for h in range(24) if tide.im_fenster(datetime(2026, 9, 24, h, 30), self.ev, auf)]
        # Von NW bis HW — 02:30 liegt fünf Minuten nach dem Scheitel, da läuft es schon ab
        self.assertEqual(drin, [0, 1, 9, 10, 11, 12, 13, 14, 21, 22, 23])
        ab = {"fahrbar": "ablaufend", "stunden": 2.0}
        drin = [h for h in range(24) if tide.im_fenster(datetime(2026, 9, 24, h, 30), self.ev, ab)]
        self.assertEqual(drin, [2, 3, 4, 5, 6, 7, 8, 15, 16, 17, 18, 19, 20])
        self.assertEqual(tide.fenster_zeiten(self.ev, ab, "2026-09-24"), [("02:25", "08:38"), ("14:50", "21:03")])
        # Vor dem ersten Scheitel wird die halbe Periode ergänzt; über Mitternacht zeigt der Tag seinen Anteil
        self.assertEqual(tide.fenster_zeiten(self.ev, auf, "2026-09-24"), [("00:00", "02:25"), ("08:38", "14:50"), ("21:03", "24:00")])
        self.assertEqual(tide.fenster_zeiten(self.ev, auf, "2026-09-25")[0], ("00:00", "03:15"))

    def test_nicht_entscheidbar(self):
        self.assertIsNone(tide.im_fenster(datetime(2026, 9, 24, 12), self.ev, None))
        self.assertIsNone(tide.im_fenster(datetime(2026, 9, 24, 12), [], {"fahrbar": "hochwasser", "stunden": 2}))


class DreiStufen(unittest.TestCase):
    """`tidal: true` / `false` / nichts — und was die Automatik daraus macht."""

    def test_automatik_am_meer_mit_hub(self):
        u = tide.uebersicht({"water_body": "sea"}, kurve(datetime(2026, 9, 24, 2, 25)), 7200, load_cfg())
        self.assertEqual((u["modus"], u["aktiv"]), ("auto", True))
        self.assertIn("2.0 m Hub", u["grund"])
        self.assertEqual(u["versatz"], 7200)
        self.assertIsNone(u["fenster"])

    def test_automatik_ohne_hub_oder_am_see(self):
        ostsee = tide.uebersicht({"water_body": "sea"}, kurve(datetime(2026, 9, 24, 2, 25), hub_m=0.3), 0, {})
        self.assertFalse(ostsee["aktiv"])
        self.assertIn("unter 0.5 m", ostsee["grund"])
        see = tide.uebersicht({"water_body": "lake"}, kurve(datetime(2026, 9, 24, 2, 25)), 0, {})
        self.assertFalse(see["aktiv"])
        self.assertEqual(see["grund"], "kein Meer- oder Lagunenspot")
        ohne = tide.uebersicht({"water_body": "sea"}, None, 0, {})
        self.assertFalse(ohne["aktiv"])
        self.assertFalse(ohne["daten"])
        # Die Schwelle ist einstellbar
        u = tide.uebersicht({"water_body": "sea"}, kurve(datetime(2026, 9, 24, 2, 25), hub_m=0.3), 0,
                            {"tide": {"auto_hub_min": 0.2}})
        self.assertTrue(u["aktiv"])

    def test_ja_und_nein_schlagen_die_automatik(self):
        ja = tide.uebersicht({"water_body": "sea", "tidal": True}, kurve(datetime(2026, 9, 24, 2, 25), hub_m=0.3), 0, {})
        self.assertEqual((ja["modus"], ja["aktiv"]), ("ja", True))
        ja_ohne = tide.uebersicht({"water_body": "lake", "tidal": True}, None, 0, {})
        self.assertTrue(ja_ohne["aktiv"])                  # eingeschaltet, aber ohne Daten
        self.assertIn("keine Tidendaten", ja_ohne["grund"])
        nein = tide.uebersicht({"water_body": "sea", "tidal": False}, kurve(datetime(2026, 9, 24, 2, 25)), 0, {})
        self.assertEqual((nein["modus"], nein["aktiv"]), ("nein", False))
        mit = tide.uebersicht({"water_body": "sea", "tide": {"fahrbar": "hochwasser", "stunden": 2.0}},
                              kurve(datetime(2026, 9, 24, 2, 25)), 0, {})
        self.assertEqual(mit["fenster_text"], "HW ± 2 h")

    def test_json_fuer_das_skript_rechnet_in_utc(self):
        """Der Browser rechnet in Unix-Sekunden: 02:25 Ortszeit bei UTC+2 ist 00:25 UTC."""
        u = tide.uebersicht({"water_body": "sea"}, kurve(datetime(2026, 9, 24, 2, 25)), 7200, {})
        j = tide.als_json(u)
        self.assertEqual(j["ereignisse"][0]["zeit"], "02:25")
        self.assertEqual(j["ereignisse"][0]["tag"], "2026-09-24")
        self.assertEqual(j["ereignisse"][0]["epoch"], calendar.timegm((2026, 9, 24, 0, 25, 0)))
        json.dumps(j)                                       # nichts darin, was JSON nicht kann


class Katalog(unittest.TestCase):
    def test_tide_block_wird_normiert(self):
        self.assertIsNone(tide_normieren(None))
        self.assertIsNone(tide_normieren(""))
        self.assertEqual(tide_normieren("Ablaufend"), {"fahrbar": "ablaufend", "stunden": 2.0})
        self.assertEqual(tide_normieren({"fahrbar": "hochwasser", "stunden": "x"}), {"fahrbar": "hochwasser", "stunden": 2.0})

    def test_katalog_kennt_nur_bekannte_fenster(self):
        for s in load_spots(str(SPOTS)):
            if "tide" in s:
                self.assertIn(s["tide"]["fahrbar"], tide.FENSTER_ARTEN, s["id"])
            if "tidal" in s:
                self.assertIsInstance(s["tidal"], bool, f"{s['id']}: tidal ist true, false oder weg")

    def test_feld_und_block_entfernen(self):
        text = ("- id: a\n  name: \"Alpha\"\n  tidal: true\n  tide:\n    fahrbar: hochwasser\n"
                "    stunden: 2\n  lat: 1\n  lon: 2\n\n- id: b\n  name: \"Beta\"\n  tide:\n    fahrbar: ablaufend\n")
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "s.yaml"
            pfad.write_text(text, encoding="utf-8")
            self.assertTrue(spotedit.entferne_feld(pfad, "a", "tide"))
            self.assertTrue(spotedit.entferne_feld(pfad, "a", "tidal"))
            self.assertFalse(spotedit.entferne_feld(pfad, "a", "tidal"))
            self.assertTrue(spotedit.entferne_feld(pfad, "b", "tide"))
            daten = yaml.safe_load(pfad.read_text(encoding="utf-8"))
            self.assertEqual(daten, [{"id": "a", "name": "Alpha", "lat": 1, "lon": 2}, {"id": "b", "name": "Beta"}])
            self.assertIn("\n\n- id: b", pfad.read_text(encoding="utf-8"))     # die Leerzeile bleibt
            with self.assertRaises(ValueError):
                spotedit.entferne_feld(pfad, "a", "Tide!")


class Bewertung(unittest.TestCase):
    def _fc(self):
        n = 48
        t0 = datetime(2026, 9, 24)
        return {"utc_offset_seconds": 7200,
                "hourly": {"time": [(t0 + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(n)],
                           "wind_speed_10m": [18.0] * n, "wind_gusts_10m": [21.0] * n,
                           "wind_direction_10m": [270.0] * n, "temperature_2m": [20.0] * n,
                           "precipitation": [0.0] * n, "cape": [0.0] * n, "weather_code": [1] * n,
                           "cloud_cover": [10.0] * n, "shortwave_radiation": [300.0] * n},
                "daily": {"time": ["2026-09-24", "2026-09-25"], "sunrise": ["2026-09-24T07:20", "2026-09-25T07:22"],
                          "sunset": ["2026-09-24T19:30", "2026-09-25T19:28"]}}

    def _spot(self, **extra):
        s = {"id": "m", "name": "Meer", "lat": 51.7, "lon": 3.8, "sectors": [], "water_body": "sea"}
        s.update(extra)
        return s

    def test_ohne_fenster_nur_anzeige(self):
        """Die Lage steht an jeder Stunde, der Score bleibt, wie er ohne Tide wäre."""
        cfg = load_cfg()
        series = kurve(datetime(2026, 9, 24, 2, 25), stunden=48)
        info = tide.uebersicht(self._spot(), series, 7200, cfg)
        mit = score.score_hours(self._spot(), self._fc(), cfg, tide=series, tide_info=info)
        ohne = score.score_hours(self._spot(), self._fc(), cfg)
        self.assertEqual([r["score"] for r in mit], [r["score"] for r in ohne])
        self.assertEqual([r["veto"] for r in mit], [r["veto"] for r in ohne])
        lagen = {r["t"].hour: r.get("tide_lage") for r in mit if r["day"] == "2026-09-24"}
        self.assertEqual(lagen[13], "auflaufend")
        self.assertEqual(lagen[14], "hochwasser")
        self.assertEqual(lagen[16], "ablaufend")
        self.assertTrue(all(r.get("tide_lage") is None for r in ohne))
        sessions = score.build_sessions(self._spot(), mit, cfg)
        self.assertTrue(sessions)
        self.assertEqual(sessions[0]["tide_lage"], lagen[sessions[0]["start"].hour])
        self.assertIn(("HW", "14:50"), sessions[0]["tides"])
        self.assertNotIn(("HW", "03:15"), sessions[0]["tides"], "nur die Scheitel des Sessiontages")

    def test_fenster_ist_ein_veto(self):
        cfg = load_cfg()
        series = kurve(datetime(2026, 9, 24, 2, 25), stunden=48)
        spot = self._spot(tide={"fahrbar": "hochwasser", "stunden": 2.0})
        info = tide.uebersicht(spot, series, 7200, cfg)
        rows = {(r["day"], r["t"].hour): r for r in score.score_hours(spot, self._fc(), cfg, tide=series, tide_info=info)}
        self.assertIsNone(rows[("2026-09-24", 14)]["veto"])
        self.assertGreater(rows[("2026-09-24", 14)]["score"], 0)
        self.assertEqual(rows[("2026-09-24", 10)]["veto"], "außerhalb des Tidenfensters (HW ± 2 h)")
        self.assertEqual(rows[("2026-09-24", 10)]["score"], 0.0)
        # Nacht bleibt Nacht — das Tageslicht-Veto kommt vor dem Fenster
        self.assertEqual(rows[("2026-09-24", 2)]["veto"], "außerhalb der Tageslichtzeit")
        sessions = score.build_sessions(spot, list(rows.values()), cfg)
        # HW 14:50 → 12:50–16:50 → Stunden 13 bis 16; am Folgetag HW 15:41 → 14 bis 17
        self.assertEqual([(s["day"], s["start"].hour, s["end"].hour) for s in sessions],
                         [("2026-09-24", 13, 17), ("2026-09-25", 14, 18)])
        self.assertEqual(sessions[0]["tide_lage"], "auflaufend")

    def test_aus_oder_ohne_daten_bleibt_alles_wie_es_war(self):
        cfg = load_cfg()
        series = kurve(datetime(2026, 9, 24, 2, 25), stunden=48)
        aus = self._spot(tidal=False, tide={"fahrbar": "hochwasser", "stunden": 2.0})
        info = tide.uebersicht(aus, series, 7200, cfg)
        rows = score.score_hours(aus, self._fc(), cfg, tide=series, tide_info=info)
        self.assertTrue(all(r.get("tide_lage") is None and r["veto"] != "außerhalb des Tidenfensters (HW ± 2 h)"
                            for r in rows))
        an_ohne = self._spot(tidal=True, tide={"fahrbar": "hochwasser", "stunden": 2.0})
        info = tide.uebersicht(an_ohne, None, 7200, cfg)
        rows = score.score_hours(an_ohne, self._fc(), cfg, tide_info=info)
        self.assertTrue(all("Tidenfenster" not in (r["veto"] or "") for r in rows))


class Anzeige(unittest.TestCase):
    def _trip(self, spot):
        start = datetime(2026, 9, 24, 13)
        session = {"spot": spot, "day": "2026-09-24", "start": start, "end": start + timedelta(hours=3),
                   "hours": 3, "score": 0.6, "peak": 0.7, "wind_min": 15, "wind_max": 18, "gust_max": 22,
                   "dirs": ["W"], "wings": [5.0], "water": "chop", "quality": "ok", "temp": 20,
                   "warn": [], "sicherheit": {"quelle": "ensemble", "p": 0.6},
                   "tide_lage": "auflaufend", "tides": [("HW", "02:25"), ("NW", "08:38"), ("HW", "14:50"), ("NW", "21:03")]}
        return {"spot": spot, "sessions": [session], "days": ["2026-09-24"], "total_hours": 3,
                "drive_h": 5.0, "acceptable_drive_h": 8.0, "drive_ok": True, "run_len": 1}

    def test_tidenzeile_am_ziel(self):
        spot = {"id": "x", "name": "Strand", "lat": 51.7, "lon": 3.8, "drive_h": 5.0, "road_km": 400,
                "notes": "", "water_body": "sea", "tide": {"fahrbar": "hochwasser", "stunden": 2.0}}
        spot["_tide"] = tide.uebersicht(spot, kurve(datetime(2026, 9, 24, 2, 25)), 7200, load_cfg())
        html = report._trip_article(1, self._trip(spot), load_cfg(), argparse.Namespace(), {"lat": 49.4, "lon": 8.7})
        self.assertIn("<div class='tide'><span class='pill p-info'>Tide</span>", html)
        self.assertIn("data-tide='{\"aktiv\":true,", html)
        self.assertIn("<b>Do 24.09.</b> <span class='ev'>HW 02:25</span> · <span class='ev'>NW 08:38</span>", html)
        self.assertIn("(Fenster 00:25–04:25, 12:50–16:50)", html)
        self.assertIn("Hub ≈ 2,0 m · fahrbar HW ± 2 h — Stunden außerhalb sind ausgeschlossen", html)
        self.assertIn("Modell, keine amtliche Tafel", html)
        self.assertIn("· 20 °C · Tide auflaufend · HW 14:50</span>", html)       # Sessionzeile
        # Der Stand beim Erstellen steht drin — das Skript ersetzt ihn beim Öffnen
        self.assertRegex(html, r"<span class='tide-jetzt' data-tide='[^']*'>Stand \d\d:\d\d Uhr: ")
        # Ohne Fenster: nur Information
        spot2 = dict(spot)
        spot2.pop("tide")
        spot2["_tide"] = tide.uebersicht(spot2, kurve(datetime(2026, 9, 24, 2, 25)), 7200, load_cfg())
        html = report._trip_article(1, self._trip(spot2), load_cfg(), argparse.Namespace(), {"lat": 49.4, "lon": 8.7})
        self.assertIn("nur zur Information, kein Einfluss auf die Bewertung", html)
        self.assertNotIn("Fenster", html)

    def test_eingeschaltet_ohne_daten_und_ausgeschaltet(self):
        spot = {"id": "x", "name": "Strand", "lat": 51.7, "lon": 3.8, "drive_h": 5.0, "road_km": 400,
                "notes": "", "water_body": "sea", "tidal": True}
        spot["_tide"] = tide.uebersicht(spot, None, 7200, load_cfg())
        html = report._trip_article(1, self._trip(spot), load_cfg(), argparse.Namespace(), {"lat": 49.4, "lon": 8.7})
        self.assertIn("keine Tidendaten vom Modell", html)
        self.assertNotIn("data-tide", html)
        spot["tidal"] = False
        spot["_tide"] = tide.uebersicht(spot, kurve(datetime(2026, 9, 24, 2, 25)), 7200, load_cfg())
        html = report._trip_article(1, self._trip(spot), load_cfg(), argparse.Namespace(), {"lat": 49.4, "lon": 8.7})
        self.assertNotIn("class='tide'", html)
        ohne = {k: v for k, v in spot.items() if k != "_tide"}          # ein Spot ohne Übersicht (alte Aufrufer)
        html = report._trip_article(1, self._trip(ohne), load_cfg(), argparse.Namespace(), {"lat": 49.4, "lon": 8.7})
        self.assertNotIn("class='tide'", html)

    def test_demo_report_traegt_skript_und_karte(self):
        from wingscout.cli import main
        with tempfile.TemporaryDirectory() as d:
            args = ["--demo", "--days", "2", "--radius", "700", "--out", str(Path(d) / "r.html"), "--quiet",
                    "--config", str(CONFIG), "--spots", str(SPOTS), "--geometry", str(Path(d) / "keine.json")]
            self.assertEqual(main(args), 0)
            html = (Path(d) / "r.html").read_text(encoding="utf-8")
        self.assertIn("window.WSTide.start()", html)
        self.assertIn("<div class='tide'>", html)
        self.assertIn("<td>Tide</td><td class='n'>sea_level_height_msl</td>", html)
        # Raster-Tooltip nennt die Lage
        self.assertRegex(html, r"title=\"[^\"]*· Tide (auflaufend|ablaufend|Hochwasser|Niedrigwasser)")
        karte = html.split("<h2>Karte</h2>")[1].split("<h2>")[0]
        daten = json.loads(re.search(r"var KARTE = (\{.*?\});\n", karte, re.S).group(1)
                           .replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&"))
        mit = [m for m in daten["markers"] if m.get("tide")]
        self.assertTrue(mit, "im Demo-Lauf hat mindestens ein Meer-Spot Tiden")
        self.assertTrue(all(m["tide"]["ereignisse"] and m["tide_text"].startswith("Stand ") for m in mit))
        self.assertIn("window.WSTide.alle(e.popup.getElement())", karte)

    def test_skript_rechnet_die_lage_zur_anzeigezeit(self):
        """tide.js ohne Browser: Node führt die Funktion mit festem „jetzt“ aus."""
        import shutil as _sh
        import subprocess
        node = _sh.which("node")
        if not node:
            self.skipTest("node fehlt")
        u = tide.uebersicht({"water_body": "sea", "tide": {"fahrbar": "hochwasser", "stunden": 2.0}},
                            kurve(datetime(2026, 9, 24, 2, 25)), 7200, {})
        daten = json.dumps(tide.als_json(u))
        jetzt = calendar.timegm((2026, 9, 24, 8, 10, 0))              # 10:10 Ortszeit: ablaufend, NW 08:38? nein — nach NW
        skript = (Path(__file__).resolve().parent.parent / "wingscout" / "web" / "tide.js").read_text(encoding="utf-8")
        js = ("var window = {}; var document = {addEventListener: function () {}};\n" + skript +
              f"\nvar d = {daten};\n"
              f"console.log(window.WSTide.text(d, {jetzt}));\n"
              f"console.log(window.WSTide.text(d, {calendar.timegm((2026, 9, 24, 11, 0, 0))}));\n"
              f"console.log(window.WSTide.text(d, {calendar.timegm((2026, 9, 24, 12, 35, 0))}));\n"
              f"console.log(window.WSTide.text(d, {calendar.timegm((2026, 9, 30, 12, 0, 0))}));\n")
        out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        zeilen = out.stdout.strip().splitlines()
        # 10:10 Ortszeit: ablaufend nach HW 02:25 → nein: NW war 08:38, also auflaufend Richtung HW 14:50
        self.assertEqual(zeilen[0], "Jetzt auflaufend · Hochwasser um 14:50 (in 4 h 40 min) · nächstes Tidenfenster 12:50–16:50 (in 2 h 40 min)")
        self.assertEqual(zeilen[1], "Jetzt auflaufend · Hochwasser um 14:50 (in 1 h 50 min) · im Tidenfenster bis 16:50 (noch 3 h 50 min)")
        self.assertEqual(zeilen[2], "Jetzt Hochwasser (14:50) · im Tidenfenster bis 16:50 (noch 2 h 15 min)")
        self.assertEqual(zeilen[3], "Der Report ist älter als sein Tidenverlauf — neu suchen.")


class Oberflaeche(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        w.Handler.cfg_path = str(CONFIG)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), w.Handler)
        w.SERVER["instance"] = cls.server
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _post(self, path, daten):
        kopf = {"Origin": f"http://127.0.0.1:{self.port}", "Content-Type": "application/json"}
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(daten).encode(),
                                     method="POST", headers=kopf)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_schalter_im_katalog(self):
        with tempfile.TemporaryDirectory() as d:
            kopie = Path(d) / "spots.yaml"
            shutil.copy(SPOTS, kopie)
            orig = w.SPOTS_FILE
            w.SPOTS_FILE = kopie
            try:
                def spot(sid):
                    return {x["id"]: x for x in yaml.safe_load(kopie.read_text(encoding="utf-8"))}[sid]
                self.assertTrue(spot("brouwersdam").get("tidal"))
                code, j = self._post("/katalog/tide", {"id": "brouwersdam", "tidal": "auto", "fahrbar": "hochwasser", "stunden": "1,5"})
                self.assertEqual(code, 200, j)
                self.assertEqual(j["tide"], {"fahrbar": "hochwasser", "stunden": 1.5})
                self.assertIn("HW ± 1.5 h", j["message"])
                self.assertNotIn("tidal", spot("brouwersdam"))
                self.assertEqual(spot("brouwersdam")["tide"], {"fahrbar": "hochwasser", "stunden": 1.5})
                code, j = self._post("/katalog/tide", {"id": "brouwersdam", "tidal": "ja", "fahrbar": "auflaufend"})
                self.assertEqual(code, 200, j)
                self.assertIs(spot("brouwersdam")["tidal"], True)
                self.assertEqual(spot("brouwersdam")["tide"], {"fahrbar": "auflaufend"})   # ohne Stunden
                code, j = self._post("/katalog/tide", {"id": "brouwersdam", "tidal": "nein", "fahrbar": ""})
                self.assertEqual(code, 200, j)
                self.assertIs(spot("brouwersdam")["tidal"], False)
                self.assertNotIn("tide", spot("brouwersdam"))
                # Der Katalog liest sich noch, Kommentare bleiben
                self.assertTrue(load_spots(str(kopie)))
                self.assertIn("Wingfoilscout · Spot catalogue", kopie.read_text(encoding="utf-8"))
                # Unsinn wird abgewiesen
                for daten in ({"id": "brouwersdam", "tidal": "vielleicht"},
                              {"id": "brouwersdam", "tidal": "ja", "fahrbar": "immer"},
                              {"id": "brouwersdam", "tidal": "ja", "fahrbar": "hochwasser", "stunden": "9"},
                              {"id": "brouwersdam", "tidal": "nein", "fahrbar": "hochwasser"},
                              {"id": "gibt-es-nicht", "tidal": "ja"}):
                    code, j = self._post("/katalog/tide", daten)
                    self.assertEqual(code, 400, daten)
            finally:
                w.SPOTS_FILE = orig

    def test_katalogseite_traegt_die_felder(self):
        spots = load_spots(str(SPOTS))
        daten = {d["id"]: d for d in w.katalog_daten(spots)}
        self.assertIs(daten["brouwersdam"]["tidal"], True)
        self.assertIn("tide", daten["brouwersdam"])
        see = next(d for d in daten.values() if d["water"] == "lake")
        self.assertIsNone(see["tidal"])
        html = w.katalog_page(spots, {"lat": 49.4, "lon": 8.7})
        self.assertIn("<option value='tide'>mit Tidenregel</option>", html)
        self.assertIn("data-akt=\"tide\"", html)
        self.assertIn("/katalog/tide", html)
        self.assertIn("kp-tide", html)

    def test_marine_haken_erklaert_die_tide(self):
        cfg = load_cfg()
        html = w.page(cfg, w.form_defaults(cfg))
        self.assertIn("Wassertemperatur und Wellenmodell", html)
        self.assertNotIn("Wassertemperatur und Tiden", html)
        self.assertIn("marine", w.ERKLAERUNG)
        self.assertIn("Tidenzeiten kommen seit 1.18.0 immer mit", html)


class Datenquelle(unittest.TestCase):
    def test_marine_bricht_nach_netzfehler_ab(self):
        """Acht Pakete à 45 s Timeout wären sechs Minuten für nichts."""
        from wingscout.sources import marine
        aufrufe = []

        def kaputt(req, timeout=0):
            aufrufe.append(req.full_url)
            raise urllib.error.URLError("kein Netz")
        orig = marine.urllib.request.urlopen
        marine.urllib.request.urlopen = kaputt
        try:
            spots = [{"id": f"s{i}", "lat": 51.0 + i * 0.01, "lon": 3.0, "water_body": "sea"} for i in range(45)]
            self.assertEqual(marine.fetch(spots, 3, timezone="Europe/Amsterdam"), {})
        finally:
            marine.urllib.request.urlopen = orig
        self.assertEqual(len(aufrufe), 1)

    def test_suche_holt_die_tide_auch_ohne_marine_haken(self):
        """Ohne --marine kommen Tiden, aber weder Wassertemperatur noch Welle in
        die Bewertung; `tidal: false` wird ohne den Haken gar nicht erst angefragt."""
        from wingscout import cli
        keep = [{"id": "a", "name": "A", "lat": 51.7, "lon": 3.8, "water_body": "sea"},
                {"id": "b", "name": "B", "lat": 51.8, "lon": 3.9, "water_body": "sea", "tidal": False},
                {"id": "c", "name": "C", "lat": 47.0, "lon": 9.0, "water_body": "lake"},
                {"id": "d", "name": "D", "lat": 45.0, "lon": 12.4, "water_body": "lagoon", "tidal": True}]
        ohne = argparse.Namespace(marine=False, demo=False)
        mit = argparse.Namespace(marine=True, demo=False)
        self.assertEqual([s["id"] for s in cli.marine_ziele(keep, ohne)], ["a", "d"])
        self.assertEqual([s["id"] for s in cli.marine_ziele(keep, mit)], ["a", "b", "d"])
        m = {"sst": {"x": 12.0}, "wave": {"x": 0.4}, "tide": {"x": 0.1}}
        self.assertEqual(cli.marine_fuer_bewertung(m, ohne), (None, None))
        self.assertEqual(cli.marine_fuer_bewertung(m, mit), ({"x": 12.0}, {"x": 0.4}))
        self.assertEqual(cli.marine_fuer_bewertung(m, argparse.Namespace(marine=False, demo=True)),
                         ({"x": 12.0}, {"x": 0.4}))
        self.assertEqual(cli.marine_fuer_bewertung({}, mit), (None, None))

if __name__ == "__main__":
    unittest.main()
