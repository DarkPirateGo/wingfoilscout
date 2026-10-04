from __future__ import annotations
import re
import unittest
from datetime import date
from pathlib import Path

from tests.helpers import cfg as load_cfg, SPOTS
from wingscout import models, score
from wingscout.spots import load_spots, eligible
from wingscout.demo import build as demo_build


class Windbewertung(unittest.TestCase):
    def setUp(self):
        self.cfg = load_cfg()

    def test_kein_wing_unter_der_untergrenze(self):
        s, wing = score.score_wind(5, self.cfg)
        self.assertEqual(s, 0.0)
        self.assertIsNone(wing)

    def test_wohlfuehlband_voll_bewertet(self):
        lo, hi = self.cfg["wind"]["preferred_low"], self.cfg["wind"]["preferred_high"]
        mitte = (lo + hi) / 2
        s, wing = score.score_wind(mitte, self.cfg)
        self.assertGreaterEqual(s, 0.5)
        self.assertIsNotNone(wing)
        self.assertLessEqual(wing["low"], mitte)
        self.assertGreaterEqual(wing["high"], mitte)

    def test_boeen_druecken(self):
        ruhig, _ = score.score_gust(15, 16, self.cfg)
        wild, _ = score.score_gust(15, 30, self.cfg)
        self.assertEqual(ruhig, 1.0)
        self.assertLess(wild, 0.5)

    def test_richtung_ohne_sektoren_ist_neutral(self):
        s, label, water = score.score_direction({"sectors": []}, 270, self.cfg)
        self.assertEqual(s, self.cfg["wind"]["unknown_direction_score"])
        self.assertEqual(label, "unbekannt")

    def test_richtung_mit_sektor(self):
        spot = {"sectors": [{"from": 200, "to": 300, "quality": "best", "water": "flat"}]}
        s_in, *_ = score.score_direction(spot, 250, self.cfg)
        s_out, *_ = score.score_direction(spot, 90, self.cfg)
        self.assertGreater(s_in, s_out)

    def test_gewitter_ist_veto(self):
        s, warns, veto = score.score_weather(20, 0.0, 100, 95, self.cfg)
        self.assertIsNotNone(veto)

    def test_temperaturgrenzen(self):
        _, _, kalt = score.score_weather(self.cfg["weather"]["air_temp_min"] - 3, 0, 0, 1, self.cfg)
        _, _, heiss = score.score_weather(self.cfg["weather"]["air_temp_max"] + 3, 0, 0, 1, self.cfg)
        _, _, gut = score.score_weather(20, 0, 0, 1, self.cfg)
        self.assertIsNotNone(kalt)
        self.assertIsNotNone(heiss)
        self.assertIsNone(gut)

    def test_neopren(self):
        self.assertIsNone(score.wetsuit(None))
        self.assertIsInstance(score.wetsuit(19.5), str)


class Modelle(unittest.TestCase):
    def test_suffixe_werden_zusammengefuehrt(self):
        hourly = {"time": ["t0", "t1"],
                  "wind_speed_10m_dwd_icon_seamless": [10, None],
                  "wind_speed_10m_ncep_gfs_seamless": [12, 14],
                  "wind_speed_10m_ecmwf_ifs": [9, 11]}
        out = models.normalize(hourly, models.DEFAULT_MODELS, "dwd_icon_seamless")
        self.assertEqual(out["wind_speed_10m"], [10, 14])          # Lücke aus dem nächsten Modell
        self.assertEqual(set(out["wind_models"]), {"ICON", "GFS", "ECMWF"})
        self.assertEqual(out["wind_spread"][0], 3)
        self.assertGreater(out["wind_agree"][0], out["wind_agree"][1] - 1e-9)

    def test_einstrahlung_ueberlebt_das_zusammenfuehren(self):
        """Bei mehreren Modellen baut normalize() das hourly aus CORE neu —
        was dort fehlt, ist danach None. `shortwave_radiation` fehlte bis
        1.6.0; die Thermik lief deshalb immer im Bewölkungs-Rückfall."""
        hourly = {"time": ["t0"],
                  "wind_speed_10m_dwd_icon_seamless": [10],
                  "shortwave_radiation_dwd_icon_seamless": [612.0],
                  "cloud_cover_dwd_icon_seamless": [95]}
        out = models.normalize(hourly, models.DEFAULT_MODELS, "dwd_icon_seamless")
        self.assertEqual(out["shortwave_radiation"], [612.0])
        # Und rückwärts: alles, was score_hours liest, steht in CORE.
        quelle = (Path(score.__file__)).read_text(encoding="utf-8")
        gelesen = set(re.findall(r'val\("([a-z_0-9]+)"\)', quelle))
        self.assertTrue(gelesen <= set(models.CORE), gelesen - set(models.CORE))

    def test_einzelmodell_ohne_suffix(self):
        hourly = {"time": ["t0"], "wind_speed_10m": [15]}
        out = models.normalize(hourly, models.DEFAULT_MODELS, "dwd_icon_seamless")
        self.assertEqual(out["wind_speed_10m"], [15])
        self.assertEqual(out["wind_agree"], [1.0])

    def test_kurznamen(self):
        self.assertEqual(models.short("dwd_icon_seamless"), "ICON")


class Wellenmodell(unittest.TestCase):
    def _fc(self):
        n = 24
        return {"utc_offset_seconds": 7200,
                "hourly": {"time": [f"2026-07-15T{h:02d}:00" for h in range(n)],
                           "wind_speed_10m": [20.0] * n, "wind_gusts_10m": [23.0] * n,
                           "wind_direction_10m": [270.0] * n, "temperature_2m": [22.0] * n,
                           "precipitation": [0.0] * n, "cape": [0.0] * n, "weather_code": [1] * n,
                           "cloud_cover": [10.0] * n, "shortwave_radiation": [300.0] * n},
                "daily": {"time": ["2026-07-15"], "sunrise": ["2026-07-15T05:30"],
                          "sunset": ["2026-07-15T21:15"]}}

    def test_wellenhoehe_aus_dem_modell_schlaegt_die_faustformel(self):
        """Bis 1.6.1 wurde `wave_height` geholt und verworfen; für alle galt die
        SPM-Näherung. Am Meer liegt die bessere Zahl schon im Speicher."""
        spot = {"id": "m", "name": "Meer", "lat": 51.7, "lon": 3.8, "sectors": [], "water_body": "sea"}
        rose = [20000.0] * 36                       # offen in jede Richtung: Formel sagt Welle
        cfg = load_cfg()
        ohne = {r["t"].hour: r for r in score.score_hours(spot, self._fc(), cfg, rose=rose)}
        self.assertEqual(ohne[14]["water"], "wave")
        self.assertGreater(ohne[14]["wave_m"], 0.6)
        self.assertNotIn("wave_quelle", ohne[14])
        welle = {f"2026-07-15T{h:02d}:00": 0.15 for h in range(24)}
        mit = {r["t"].hour: r for r in score.score_hours(spot, self._fc(), cfg, rose=rose, wave=welle)}
        self.assertEqual(mit[14]["water"], "flat")
        self.assertEqual(mit[14]["wave_m"], 0.15)
        self.assertEqual(mit[14]["wave_quelle"], "Wellenmodell")
        self.assertEqual(mit[14]["fetch_up_km"], 20.0, "die Anlauflänge bleibt für die Windlage")
        sessions = score.build_sessions(spot, list(mit.values()), cfg)
        self.assertTrue(sessions and sessions[0]["wave_quelle"] == "Wellenmodell")


class Stundenbewertung(unittest.TestCase):
    """Die kleinen Befunde aus der Review — jeder mit dem Fall, der ihn zeigte."""

    def _fc(self, n=24, **ersatz):
        h = {"time": [f"2026-07-15T{k:02d}:00" for k in range(n)],
             "wind_speed_10m": [18.0] * n, "wind_gusts_10m": [21.0] * n,
             "wind_direction_10m": [270.0] * n, "temperature_2m": [22.0] * n,
             "precipitation": [0.0] * n, "cape": [0.0] * n, "weather_code": [1] * n,
             "cloud_cover": [10.0] * n, "shortwave_radiation": [300.0] * n}
        h.update(ersatz)
        return {"utc_offset_seconds": 7200, "hourly": h,
                "daily": {"time": ["2026-07-15"], "sunrise": ["2026-07-15T05:30"],
                          "sunset": ["2026-07-15T21:15"]}}

    def test_fehlende_richtung_wird_nicht_nord(self):
        """`or 0.0` machte aus None Nord — und Nord wurde gegen Sektoren und
        Rose geprüft, als wäre es gemessen."""
        spot = {"id": "s", "name": "S", "lat": 51.7, "lon": 3.8,
                "sectors": [{"from": 300, "to": 60, "quality": "bad", "water": "wave"}]}
        n = 24
        fc = self._fc(wind_direction_10m=[None] * n)
        rows = {r["t"].hour: r for r in score.score_hours(spot, fc, load_cfg())}
        r = rows[14]
        self.assertIsNone(r["dir"])
        self.assertEqual(r["dir_name"], "?")
        self.assertEqual(r["dir_quality"], "unbekannt")
        self.assertEqual(r["source"], "keine Richtung")
        self.assertGreater(r["score"], 0.5, "neutral bewertet, nicht als Nord = schlechter Sektor")
        sessions = score.build_sessions(spot, list(rows.values()), load_cfg())
        self.assertTrue(any("Windrichtung fehlt" in w for w in sessions[0]["warn"]))

    def test_einigkeit_schliesst_das_regionalmodell_ein(self):
        """Der Wind im Report kommt aus CH1 — dann muss auch die Einigkeit CH1 kennen."""
        n = 24
        suffix = "_dwd_icon_seamless"
        fc = self._fc()
        h = fc["hourly"]
        for k in list(h):
            if k != "time":
                h[k + suffix] = h.pop(k)
        h["wind_speed_10m_ncep_gfs_seamless"] = [18.5] * n
        h["wind_speed_10m_ecmwf_ifs"] = [17.5] * n
        fein = {"time": h["time"], "wind_speed_10m": [30.0] * n,
                "wind_gusts_10m": [34.0] * n, "wind_direction_10m": [270.0] * n}
        fc["_highres"] = ("meteoswiss_icon_ch1", fein)
        spot = {"id": "s", "name": "S", "lat": 46.5, "lon": 9.8, "sectors": []}
        rows = {r["t"].hour: r for r in score.score_hours(spot, fc, load_cfg())}
        r = rows[14]
        self.assertEqual(r["wind"], 30.0)
        self.assertEqual(r["modell"], "CH1")
        self.assertGreaterEqual(r["spread"], 12.0, "Spanne mit CH1: 30 gegen 17,5")
        self.assertLess(r["agree"], 0.5)
        sessions = score.build_sessions(spot, list(rows.values()), load_cfg())
        self.assertIn("CH1", sessions[0]["modelle"])
        self.assertNotIn("grob", sessions[0]["modelle"])

    def test_eine_stunde_knapp_unter_der_schwelle_wird_ueberbrueckt(self):
        spot = {"id": "s", "name": "S", "lat": 51.7, "lon": 3.8, "sectors": []}
        cfg = load_cfg()
        cfg["session"]["min_hours"] = 3
        rows = list(score.score_hours(spot, self._fc(), cfg))
        gut = [r for r in rows if r["score"] >= cfg["session"]["min_score"]]
        self.assertGreater(len(gut), 5)
        mitte = gut[len(gut) // 2]
        mitte["score"] = cfg["session"]["min_score"] - 0.05          # knapp darunter
        sessions = score.build_sessions(spot, rows, cfg)
        self.assertEqual(len(sessions), 1, "eine Session, nicht zwei kurze")
        self.assertTrue(any("knapp unter" in w for w in sessions[0]["warn"]))
        mitte["score"] = cfg["session"]["min_score"] - 0.2           # deutlich darunter
        for r in rows:
            r.pop("bruecke", None)
        self.assertEqual(len(score.build_sessions(spot, rows, cfg)), 2)

    def test_ablandig_veto_nur_auf_wunsch(self):
        """Ablandig mit viel Wasser in Lee: Warnung bleibt der Standard, das
        Veto ist eine Option."""
        spot = {"id": "s", "name": "S", "lat": 51.7, "lon": 3.8, "sectors": []}
        # Wind aus 270: in Luv (Westen) 200 m, in Lee (Osten) 20 km
        rose = [20000.0] * 36
        rose[27] = 200.0
        cfg = load_cfg()
        rows = {r["t"].hour: r for r in score.score_hours(spot, self._fc(), cfg, rose=rose)}
        self.assertEqual(rows[14]["dir_quality"], "ablandig")
        self.assertIsNone(rows[14]["veto"])
        cfg["geometry"]["offshore_veto_km"] = 10
        rows = {r["t"].hour: r for r in score.score_hours(spot, self._fc(), cfg, rose=rose)}
        self.assertIn("ablandig", rows[14]["veto"])
        self.assertEqual(rows[14]["score"], 0.0)

    def test_jetzt_mit_zone_wird_ortszeit(self):
        """Stundenstempel sind Ortszeit am Spot; „vorbei“ muss dieselbe Uhr lesen."""
        from datetime import datetime, timezone
        spot = {"id": "s", "name": "S", "lat": 51.7, "lon": 3.8, "sectors": []}
        fc = self._fc()                              # utc_offset 7200: 12:00 UTC = 14:00 Ortszeit
        jetzt = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        rows = {r["t"].hour: r for r in score.score_hours(spot, fc, load_cfg(), jetzt=jetzt)}
        self.assertEqual(rows[13]["veto"], "vorbei")
        self.assertNotEqual(rows[14]["veto"], "vorbei")
        fc["utc_offset_seconds"] = 10800              # Athen: 12:00 UTC = 15:00
        rows = {r["t"].hour: r for r in score.score_hours(spot, fc, load_cfg(), jetzt=jetzt)}
        self.assertEqual(rows[14]["veto"], "vorbei")
        self.assertNotEqual(rows[15]["veto"], "vorbei")


class SessionsUndTrips(unittest.TestCase):
    def setUp(self):
        self.cfg = load_cfg()
        spots = load_spots(SPOTS)
        keep, _ = eligible(spots, self.cfg, date.today().month, 500, None)
        self.keep = keep[:6]
        self.fcs = demo_build(self.keep, 3)

    def test_demo_liefert_sessions_und_trips(self):
        sessions = []
        for spot in self.keep:
            rows = score.score_hours(spot, self.fcs[spot["id"]], self.cfg)
            self.assertEqual(len(rows), 72)
            for r in rows:
                self.assertTrue(0.0 <= r["score"] <= 1.0)
            sessions.extend(score.build_sessions(spot, rows, self.cfg))
        self.assertTrue(sessions)
        for s in sessions:
            self.assertGreaterEqual(s["hours"], self.cfg["session"]["min_hours"])
            self.assertGreaterEqual(s["score"], self.cfg["session"]["min_score"])
            self.assertLess(s["start"], s["end"])
        trips = score.rank_trips(sessions, self.cfg)
        self.assertEqual([t["rank"] for t in trips], sorted((t["rank"] for t in trips), reverse=True))
        for t in trips:
            self.assertIn("drive_ok", t)
            self.assertEqual(t["drive_ok"], t["drive_h"] <= t["acceptable_drive_h"])

    def test_naechte_verlangen_tage_am_stueck(self):
        sessions = []
        for spot in self.keep:
            rows = score.score_hours(spot, self.fcs[spot["id"]], self.cfg)
            sessions.extend(score.build_sessions(spot, rows, self.cfg))
        alle = score.rank_trips(sessions, self.cfg, nights=0)
        zwei = score.rank_trips(sessions, self.cfg, nights=2)
        self.assertLessEqual(len(zwei), len(alle))
        for t in zwei:
            self.assertGreaterEqual(t["run_len"], 3)

    def test_zusammenhaengende_tage(self):
        runs = score.consecutive_runs(["2026-09-12", "2026-09-13", "2026-09-15"])
        self.assertEqual(runs, [["2026-09-12", "2026-09-13"], ["2026-09-15"]])


if __name__ == "__main__":
    unittest.main()
