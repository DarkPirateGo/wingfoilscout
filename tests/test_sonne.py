"""Sonnenzeiten und die Folgen: Tageslicht, Vergangenheit, Tagesgrenze.

Geprüft wird die Rechnung gegen Invarianten, nicht gegen eine abgeschriebene
Tabelle — die könnte ich weder belegen noch pflegen. Der wahre Mittag am
15. Längengrad muss auf 11:00 UTC fallen, weil 15 Grad genau einer Stunde
entsprechen; am Nullmeridian auf 12:00. Das ist der Test, der den Vorzeichen-
fehler bei der Länge gefunden hat: mit falschem Vorzeichen stimmt Greenwich
weiterhin und sonst nichts.
"""
from __future__ import annotations
import unittest
from datetime import date, datetime, timedelta

from wingscout import sonne
from wingscout.score import score_hours, build_sessions, _sonnenzeiten
from tests.helpers import cfg as demo_config


class Rechnung(unittest.TestCase):
    def test_wahrer_mittag_folgt_der_laenge(self):
        for lon, erwartet in ((0.0, 12), (15.0, 11), (-15.0, 13), (30.0, 10)):
            mittag = sonne.mittag_utc(48.0, lon, date(2026, 9, 1))
            # Anfang September ist die Zeitgleichung nahe null, deshalb ist die
            # Länge hier der einzige Beitrag.
            ab = abs((mittag - datetime(2026, 9, 1, erwartet, tzinfo=mittag.tzinfo)).total_seconds())
            self.assertLess(ab, 12 * 60, f"{lon}° → {mittag}")

    def test_tagundnachtgleiche_ergibt_zwoelf_stunden(self):
        for lat in (0.0, 30.0, 50.0, 60.0):
            auf, unter = sonne.zeiten_utc(lat, 0.0, date(2026, 9, 22))
            stunden = (unter - auf).total_seconds() / 3600.0
            # Etwas über zwölf: Refraktion und Sonnenradius verlängern den Tag,
            # und zwar mit der Breite zunehmend.
            self.assertGreater(stunden, 12.0)
            self.assertLess(stunden, 12.5)

    def test_sommertag_ist_laenger_als_wintertag(self):
        lang = sonne.zeiten_utc(50.0, 8.0, date(2026, 6, 21))
        kurz = sonne.zeiten_utc(50.0, 8.0, date(2026, 12, 21))
        self.assertGreater((lang[1] - lang[0]).total_seconds(),
                           (kurz[1] - kurz[0]).total_seconds() + 6 * 3600)

    def test_polartag_und_polarnacht(self):
        with self.assertRaises(sonne.Polartag):
            sonne.zeiten_utc(70.0, 20.0, date(2026, 6, 21))
        with self.assertRaises(sonne.Polarnacht):
            sonne.zeiten_utc(70.0, 20.0, date(2026, 12, 21))
        # Nach außen bleibt es ein Zeitfenster: ganzer Tag oder gar keiner.
        auf, unter = sonne.zeiten_lokal(70.0, 20.0, date(2026, 6, 21), 7200)
        self.assertEqual((unter - auf), timedelta(days=1))
        auf, unter = sonne.zeiten_lokal(70.0, 20.0, date(2026, 12, 21), 7200)
        self.assertEqual(auf, unter)

    def test_mitteleuropa_liegt_im_plausiblen_fenster(self):
        auf, unter = sonne.zeiten_lokal(53.55, 9.99, date(2026, 9, 16), 7200)
        self.assertEqual(auf.date(), date(2026, 9, 16))
        self.assertTrue(6 <= auf.hour <= 8, auf)
        self.assertTrue(19 <= unter.hour <= 21, unter)


def _forecast(tag: str, suffix: str = "", *, mit_sonne=True, stunden=24) -> dict:
    zeiten = [f"{tag}T{h:02d}:00" for h in range(stunden)]
    fc = {
        "utc_offset_seconds": 7200,
        "hourly": {
            "time": zeiten,
            "wind_speed_10m": [18.0] * stunden,
            "wind_gusts_10m": [22.0] * stunden,
            "wind_direction_10m": [270.0] * stunden,
            "temperature_2m": [18.0] * stunden,
            "precipitation": [0.0] * stunden,
            "cape": [0.0] * stunden,
            "weather_code": [1] * stunden,
            "cloud_cover": [20.0] * stunden,
            "shortwave_radiation": [300.0] * stunden,
        },
    }
    if mit_sonne:
        fc["daily"] = {"time": [tag],
                       f"sunrise{suffix}": [f"{tag}T07:00"],
                       f"sunset{suffix}": [f"{tag}T19:00"]}
    return fc


SPOT = {"id": "x", "name": "X", "lat": 53.55, "lon": 9.99,
        "sectors": [{"from": 200, "to": 340, "quality": "good"}], "water": "flat"}


class Tageslicht(unittest.TestCase):
    def setUp(self):
        self.cfg = demo_config()

    def test_suffix_der_modelle_wird_mitgelesen(self):
        """Mehrere Modelle → `sunrise_dwd_icon_seamless`. Genau das ging verloren."""
        fenster = _sonnenzeiten(SPOT, _forecast("2026-09-16", "_dwd_icon_seamless"), ["2026-09-16"])
        self.assertIn("2026-09-16", fenster)
        auf, unter = fenster["2026-09-16"]
        self.assertEqual(auf.hour, 7)          # 07:00 plus 30 min Rand
        self.assertEqual(unter.hour, 18)       # 19:00 minus 30 min Rand

    def test_ohne_sonnenfeld_wird_gerechnet(self):
        fenster = _sonnenzeiten(SPOT, _forecast("2026-09-16", mit_sonne=False), ["2026-09-16"])
        auf, unter = fenster["2026-09-16"]
        self.assertTrue(7 <= auf.hour <= 8, auf)
        self.assertTrue(18 <= unter.hour <= 20, unter)

    def test_nacht_wird_ausgeschlossen(self):
        rows = score_hours(SPOT, _forecast("2026-09-16", "_dwd_icon_seamless"), self.cfg)
        nachts = [r for r in rows if r["t"].hour in (2, 3, 4, 23)]
        self.assertTrue(nachts)
        for r in nachts:
            self.assertEqual(r["score"], 0.0)
            self.assertEqual(r["veto"], "außerhalb der Tageslichtzeit")
        mittags = [r for r in rows if r["t"].hour == 13][0]
        self.assertIsNone(mittags["veto"])

    def test_session_bleibt_im_tag(self):
        rows = score_hours(SPOT, _forecast("2026-09-16", "_dwd_icon_seamless"), self.cfg)
        for s in build_sessions(SPOT, rows, self.cfg):
            self.assertEqual(s["start"].date(), s["end"].date() if s["end"].hour else s["start"].date())
            self.assertLessEqual(s["hours"], 14)


class Vergangenheit(unittest.TestCase):
    def test_vergangene_stunden_fallen_weg(self):
        cfg = demo_config()
        fc = _forecast("2026-09-16", "_dwd_icon_seamless")
        jetzt = datetime(2026, 9, 16, 11, 0)
        rows = score_hours(SPOT, fc, cfg, jetzt=jetzt)
        for r in rows:
            if r["t"].hour < 10:
                self.assertEqual(r["veto"], "vorbei", r["t"])
        self.assertNotEqual(rows[14]["veto"], "vorbei")
        sessions = build_sessions(SPOT, rows, cfg)
        for s in sessions:
            self.assertGreaterEqual(s["end"], jetzt)

    def test_ohne_angabe_bleibt_alles_stehen(self):
        rows = score_hours(SPOT, _forecast("2026-09-16", "_dwd_icon_seamless"), demo_config())
        self.assertFalse([r for r in rows if r["veto"] == "vorbei"])


if __name__ == "__main__":
    unittest.main()
