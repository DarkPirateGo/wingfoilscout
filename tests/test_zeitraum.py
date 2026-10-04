"""Ab wann gesucht wird (seit 2.3.0): Startzeitpunkt statt „jetzt“.

Bis 2.1 begann jede Suche jetzt, die Tage zählten ab heute. Gewünscht am
04.10.2026: in der Oberfläche neben „Von wo aus?“ und den Tagen auch „Ab
wann?“. Die Tage zählen ab dem Startzeitpunkt, Stunden davor fallen heraus,
und weiter als 16 Tage ab heute reicht keine Vorhersage.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import wingscout
from wingscout import cli, i18n, zeitraum
from wingscout import webui as w
from wingscout.demo import build as demo_build
from wingscout.score import score_hours

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.example.yaml"
SPOTS = ROOT / "spots.yaml"


class Lesen(unittest.TestCase):

    def test_formen(self):
        erwartet = datetime(2026, 10, 10, 9, 30)
        for text in ("2026-10-10T09:30", "2026-10-10 09:30", "2026-10-10T09:30:00", "10.10.2026 09:30",
                     "10.10.2026, 09:30", " 2026-10-10T09:30 "):
            with self.subTest(text=text):
                self.assertEqual(zeitraum.lesen(text), erwartet)
        self.assertEqual(zeitraum.lesen("2026-10-10"), datetime(2026, 10, 10))
        self.assertEqual(zeitraum.lesen("10.10.2026"), datetime(2026, 10, 10))

    def test_leer_heisst_jetzt(self):
        for text in (None, "", "   "):
            self.assertIsNone(zeitraum.lesen(text))

    def test_unlesbar(self):
        for text in ("morgen", "2026-13-01", "31.02.2026", "2026-10-10T25:00", "x" * 500, "1e999"):
            with self.subTest(text=text[:20]), self.assertRaises(ValueError):
                zeitraum.lesen(text)


class Fenster(unittest.TestCase):
    JETZT = datetime(2026, 10, 4, 11, 40)

    def test_ohne_startzeitpunkt_wie_bisher(self):
        f = zeitraum.fenster(None, 3, jetzt=self.JETZT)
        self.assertIsNone(f.ab)
        self.assertEqual((f.erster_tag, f.tage, f.vorlauf, f.abruf_tage), (date(2026, 10, 4), 3, 0, 3))
        self.assertIsNone(f.tage_iso)                  # kein Filter: die Quellen liefern genau den Zeitraum
        self.assertFalse(f.gekuerzt)

    def test_spaeter(self):
        f = zeitraum.fenster(datetime(2026, 10, 10, 9, 0), 3, jetzt=self.JETZT)
        self.assertEqual((f.erster_tag, f.tage, f.vorlauf, f.abruf_tage), (date(2026, 10, 10), 3, 6, 9))
        self.assertEqual(f.tage_iso, ("2026-10-10", "2026-10-13"))
        self.assertEqual(f.ab_mit_zone().replace(tzinfo=None), datetime(2026, 10, 10, 9, 0))
        self.assertIsNotNone(f.ab_mit_zone().tzinfo)

    def test_schon_vorbei_heisst_jetzt(self):
        for ab in (datetime(2026, 10, 1, 9, 0), datetime(2026, 10, 4, 11, 39), self.JETZT):
            with self.subTest(ab=ab):
                f = zeitraum.fenster(ab, 3, jetzt=self.JETZT)
                self.assertIsNone(f.ab)
                self.assertEqual((f.erster_tag, f.vorlauf), (date(2026, 10, 4), 0))

    def test_heute_spaeter(self):
        f = zeitraum.fenster(datetime(2026, 10, 4, 15, 0), 2, jetzt=self.JETZT)
        self.assertEqual((f.erster_tag, f.vorlauf, f.abruf_tage), (date(2026, 10, 4), 0, 2))
        self.assertEqual(f.tage_iso, ("2026-10-04", "2026-10-06"))

    def test_gekuerzt_an_der_grenze_der_vorhersage(self):
        f = zeitraum.fenster(datetime(2026, 10, 15, 8, 0), 7, jetzt=self.JETZT)
        self.assertEqual((f.vorlauf, f.tage, f.gewuenscht, f.abruf_tage), (11, 5, 7, 16))
        self.assertTrue(f.gekuerzt)
        letzter = zeitraum.fenster(datetime(2026, 10, 19, 8, 0), 3, jetzt=self.JETZT)
        self.assertEqual((letzter.vorlauf, letzter.tage, letzter.abruf_tage), (15, 1, 16))

    def test_zu_weit(self):
        for ab in (datetime(2026, 10, 20, 0, 0), datetime(2027, 1, 1)):
            with self.subTest(ab=ab), self.assertRaises(zeitraum.ZuWeit):
                zeitraum.fenster(ab, 1, jetzt=self.JETZT)
        self.assertEqual(zeitraum.letzter_tag(date(2026, 10, 4)), date(2026, 10, 19))

    def test_monate_ab_dem_start(self):
        f = zeitraum.fenster(datetime(2026, 10, 30, 9, 0), 4, jetzt=datetime(2026, 10, 20, 8, 0))
        self.assertEqual(f.monate(), {10, 11})
        self.assertEqual(zeitraum.fenster(None, 2, jetzt=datetime(2026, 10, 20, 8, 0)).monate(), {10})

    def test_tage_bleiben_zwischen_1_und_16(self):
        self.assertEqual(zeitraum.fenster(None, 0, jetzt=self.JETZT).tage, 1)
        self.assertEqual(zeitraum.fenster(None, 40, jetzt=self.JETZT).tage, 16)


class Stunden(unittest.TestCase):
    """score_hours mit Zeitraum und Startzeitpunkt."""

    def setUp(self):
        from wingscout.config import load_config
        from wingscout.spots import load_spots
        self.cfg = load_config(str(CONFIG))
        self.spot = next(s for s in load_spots(str(SPOTS)) if s.get("sectors"))
        self.fc = demo_build([self.spot], 4)[self.spot["id"]]
        self.heute = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    def test_nur_die_tage_im_zeitraum(self):
        von = (self.heute + timedelta(days=1)).date().isoformat()
        bis = (self.heute + timedelta(days=3)).date().isoformat()
        rows = score_hours(self.spot, self.fc, self.cfg, tage=(von, bis))
        self.assertEqual(len(rows), 48)
        self.assertEqual({r["day"] for r in rows}, {von, (self.heute + timedelta(days=2)).date().isoformat()})

    def test_stunden_vor_dem_start_fallen_heraus(self):
        # Ortszeit des Spots: `utc_offset_seconds` der Demo ist die des Spots — der
        # Start hier in UTC, so dass er in Spotzeit genau auf 10 Uhr fällt.
        versatz = timedelta(seconds=int(self.fc.get("utc_offset_seconds") or 0))
        start_lokal = self.heute + timedelta(days=1, hours=10)
        ab = (start_lokal - versatz).replace(tzinfo=timezone.utc)
        tag = start_lokal.date().isoformat()
        rows = score_hours(self.spot, self.fc, self.cfg, ab=ab,
                           tage=(tag, (start_lokal + timedelta(days=1)).date().isoformat()))
        self.assertEqual(len(rows), 24)
        mit_veto = [r["t"].hour for r in rows if r["veto"] == "vor dem gewählten Start"]
        self.assertEqual(mit_veto, list(range(10)))
        self.assertTrue(all(r["score"] == 0.0 for r in rows if r["t"].hour < 10))

    def test_ohne_angabe_alles_wie_bisher(self):
        self.assertEqual(len(score_hours(self.spot, self.fc, self.cfg)), 96)


def suche(out: Path, *extra: str) -> tuple[int, str]:
    protokoll = io.StringIO()
    with contextlib.redirect_stderr(protokoll):
        code = cli.main(["--demo", "--days", "2", "--radius", "400", "--out", str(out),
                         "--config", str(CONFIG), "--spots", str(SPOTS), "--geometry", str(ROOT / "geometry.json"),
                         "--sprache", "de", *extra])
    return code, protokoll.getvalue()


class Kommandozeile(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        for p in (mock.patch.object(wingscout, "CACHE", self.tmp / "cache"), mock.patch.dict(os.environ)):
            p.start()
            self.addCleanup(p.stop)
        os.environ.pop("WINGSCOUT_SPRACHE", None)
        self.addCleanup(i18n.setze, i18n.QUELLE)

    def test_ab_in_drei_tagen(self):
        start = (datetime.now() + timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)
        out = self.tmp / "r.html"
        code, protokoll = suche(out, "--ab", start.strftime("%Y-%m-%d %H:%M"))
        self.assertEqual(code, 0, protokoll)
        self.assertIn("Zeitraum: 2 Tage ab " + start.strftime("%Y-%m-%d %H:%M"), protokoll)
        text = out.read_text(encoding="utf-8")
        self.assertIn("2 Tage ab " + i18n.tag(start) + " 10:00", text)
        tage = re.findall(r"class='hmaxis'[^>]*>([^<]*)<", text)
        self.assertEqual(tage[:2], [i18n.tag(start), i18n.tag(start + timedelta(days=1))])
        self.assertNotIn(i18n.tag(datetime.now()), tage)
        self.assertIn("vor dem gewählten Start", text)
        lauf = json.loads((self.tmp / "cache" / "letzter_lauf.json").read_text(encoding="utf-8"))
        self.assertEqual(lauf["ab"], start.strftime("%Y-%m-%dT%H:%M"))

    def test_zu_weit_und_unlesbar(self):
        weit = (date.today() + timedelta(days=20)).isoformat()
        code, protokoll = suche(self.tmp / "r.html", "--ab", weit)
        self.assertEqual(code, 1)
        self.assertIn("hinter dem letzten Vorhersagetag", protokoll)
        self.assertFalse((self.tmp / "r.html").exists())
        with self.assertRaises(SystemExit) as cm:
            suche(self.tmp / "r.html", "--ab", "nächsten Samstag")
        self.assertIn("nicht lesbar", str(cm.exception))

    def test_gekuerzt(self):
        start = (date.today() + timedelta(days=14)).isoformat()
        code, protokoll = suche(self.tmp / "r.html", "--ab", start, "--days", "5")
        self.assertEqual(code, 0, protokoll)
        self.assertIn("Zeitraum auf 2 Tage gekürzt", protokoll)

    def test_schon_vorbei(self):
        code, protokoll = suche(self.tmp / "r.html", "--ab", "2020-01-01 10:00")
        self.assertEqual(code, 0, protokoll)
        self.assertIn("schon vorbei — die Suche beginnt jetzt", protokoll)
        self.assertNotIn("vor dem gewählten Start", (self.tmp / "r.html").read_text(encoding="utf-8"))

    def test_in_jeder_sprache_des_reports(self):
        """Das Veto „vor dem gewählten Start“ kommt aus der Rechnung — auch
        in den abgelegten Fassungen (2.3.0) in deren Sprache."""
        from wingscout import report
        start = (datetime.now() + timedelta(days=2)).replace(hour=12, minute=0, second=0, microsecond=0)
        standard = self.tmp / "report.html"
        with mock.patch.object(wingscout, "REPORT", standard):
            code, protokoll = suche(standard, "--ab", start.strftime("%Y-%m-%d %H:%M"))
        self.assertEqual(code, 0, protokoll)
        for sprache in i18n.SPRACHEN:
            with self.subTest(sprache=sprache), i18n.in_sprache(sprache):
                text = report.fassung(standard.read_bytes(), sprache).decode("utf-8")
                self.assertIn(i18n.T("vor dem gewählten Start"), text)
                self.assertIn(i18n.T("{n} Tage ab {start}", n=2, start=i18n.tag(start) + " 12:00"), text)


class Oberflaeche(unittest.TestCase):
    """Das Feld „Ab wann?“ und was `/run` und `/save` damit tun."""

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.tmp = Path(tmp.name)
        for p in (mock.patch.object(w, "DEFAULTS_FILE", cls.tmp / "ui_defaults.json"),
                  mock.patch.object(w, "REPORT_FILE", cls.tmp / "report.html"),
                  mock.patch.object(w.Handler, "cfg_path", str(CONFIG))):
            p.start()
            cls.addClassCleanup(p.stop)
        server = w.BegrenzterServer(("127.0.0.1", 0), w.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        cls.addClassCleanup(server.server_close)
        cls.addClassCleanup(server.shutdown)
        cls.basis = f"http://127.0.0.1:{server.server_address[1]}"

    def post(self, pfad: str, felder: dict) -> tuple[int, dict]:
        daten = urllib.parse.urlencode(felder).encode()
        anfrage = urllib.request.Request(self.basis + pfad, data=daten, method="POST",
                                         headers={"Origin": self.basis, "Sec-Fetch-Site": "same-origin"})
        try:
            with urllib.request.urlopen(anfrage, timeout=30) as antwort:
                return antwort.status, json.loads(antwort.read() or b"{}")
        except urllib.error.HTTPError as fehler:
            return fehler.code, json.loads(fehler.read() or b"{}")

    def test_feld_auf_der_seite(self):
        from wingscout.config import load_config
        cfg = load_config(str(CONFIG))
        seite = w.page(cfg, w.form_defaults(cfg))
        self.assertIn('type="datetime-local" id="ab" name="ab"', seite)
        self.assertIn(f'max="{zeitraum.letzter_tag().isoformat()}T23:59"', seite)
        self.assertIn('id="abjetzt"', seite)
        self.assertIn("Ab wann?", seite)

    def test_formular(self):
        from wingscout.config import load_config
        werte = w.parse_form({"ab": ["2026-10-10T09:00"]}, w.form_defaults(load_config(str(CONFIG))))
        self.assertEqual(werte["ab"], "2026-10-10T09:00")
        self.assertEqual(w.make_args(werte).ab, datetime(2026, 10, 10, 9, 0))
        werte["ab"] = "Unsinn"
        self.assertIsNone(w.make_args(werte).ab)
        werte["ab"] = ""
        self.assertIsNone(w.make_args(werte).ab)

    def test_run_lehnt_ab_mit_einem_satz(self):
        weit = zeitraum.fuer_feld(datetime.combine(zeitraum.letzter_tag() + timedelta(days=2), datetime.min.time()))
        for ab, teil in ((weit, "letzten Vorhersagetag"), ("2026-99-99T10:00", "nicht lesbar")):
            with self.subTest(ab=ab), mock.patch.object(w, "start_run") as start:
                code, antwort = self.post("/run", {"ab": ab, "demo": "on"})
                self.assertEqual(code, 400)
                self.assertIn(teil, antwort.get("error", ""))
                start.assert_not_called()

    def test_run_mit_startzeitpunkt(self):
        ab = zeitraum.fuer_feld((datetime.now() + timedelta(days=2)).replace(hour=9, minute=0))
        with mock.patch.object(w, "start_run", return_value=True) as start:
            code, _ = self.post("/run", {"ab": ab, "demo": "on"})
        self.assertEqual(code, 200)
        self.assertEqual(start.call_args[0][1]["ab"], ab)

    def test_save_merkt_den_startzeitpunkt_nicht(self):
        code, _ = self.post("/save", {"ab": "2026-10-10T09:00", "start": "51.7, 3.8", "days": "4"})
        self.assertEqual(code, 200)
        gemerkt = json.loads((self.tmp / "ui_defaults.json").read_text(encoding="utf-8"))
        self.assertNotIn("ab", gemerkt)
        self.assertNotIn("start", gemerkt)
        self.assertEqual(gemerkt["days"], 4)


if __name__ == "__main__":
    unittest.main()
