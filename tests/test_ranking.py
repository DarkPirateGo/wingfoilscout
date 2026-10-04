"""Das Ensemble entscheidet mit — vorher stand die Zahl nur im Report.

Der Befund aus dem Lauf vom 16.09.2026: Platz 2 trug eine Session mit „0 %
sicher", beim Spitzenreiter waren zwei von drei Sessions bei 3 und 10 Prozent.
Ursache war, dass `ensemble` in score.py nicht vorkam.
"""
from __future__ import annotations
import unittest
from datetime import datetime, timedelta

from wingscout.score import rank_trips, apply_ensemble
from tests.helpers import cfg as basis_config


def _spot(sid, drive_h, lat=50.0, lon=8.0):
    return {"id": sid, "name": sid, "lat": lat, "lon": lon, "drive_h": drive_h}


def _sessions(spot, tage=2, score=0.8, stunden=5):
    out = []
    for d in range(tage):
        start = datetime(2026, 9, 16 + d, 11, 0)
        out.append({"spot": spot, "day": start.date().isoformat(), "start": start,
                    "end": start + timedelta(hours=stunden), "hours": stunden,
                    "score": score, "warn": []})
    return out


class EnsembleImRanking(unittest.TestCase):
    def setUp(self):
        self.cfg = basis_config()
        self.cfg["ensemble"] = {"weight": 0.5, "top": 20}
        self.sicher = _spot("sicher", 3.0, lon=8.0)
        self.wackelig = _spot("wackelig", 3.0, lon=12.0)

    def _trips(self, p_sicher, p_wackelig, score_wackelig=0.82):
        sessions = _sessions(self.sicher, score=0.80) + _sessions(self.wackelig, score=score_wackelig)
        trips = rank_trips(sessions, self.cfg)
        for t in trips:
            p = p_sicher if t["spot"]["id"] == "sicher" else p_wackelig
            for s in t["sessions"]:
                s["ens"] = {"p_ride": p, "p_good": p, "p10": 10, "p50": 14, "p90": 18, "members": 40}
        return trips

    def test_wackeliges_ziel_faellt_zurueck(self):
        trips = self._trips(0.95, 0.05)
        self.assertEqual(trips[0]["spot"]["id"], "wackelig")   # vorher vorn: besserer Rohscore
        n = apply_ensemble(trips, self.cfg)
        self.assertEqual(n, 4)
        self.assertEqual(trips[0]["spot"]["id"], "sicher")

    def test_gedaempft_statt_ausgeloescht(self):
        trips = self._trips(0.95, 0.0)
        apply_ensemble(trips, self.cfg)
        wackelig = next(t for t in trips if t["spot"]["id"] == "wackelig")
        # Halbes Gewicht: 0,82 → 0,41, nicht 0.
        self.assertAlmostEqual(wackelig["sessions"][0]["score"], 0.41, places=2)
        self.assertGreater(wackelig["rank"], 0.0)
        self.assertEqual(wackelig["sessions"][0]["score_roh"], 0.82)

    def test_gewicht_null_laesst_alles_wie_es_war(self):
        self.cfg["ensemble"]["weight"] = 0.0
        trips = self._trips(0.95, 0.0)
        vorher = [t["spot"]["id"] for t in trips], [t["rank"] for t in trips]
        self.assertEqual(apply_ensemble(trips, self.cfg), 0)
        self.assertEqual(([t["spot"]["id"] for t in trips], [t["rank"] for t in trips]), vorher)

    def test_ohne_ensemble_bleibt_der_score_unberuehrt(self):
        sessions = _sessions(self.sicher, score=0.80)
        trips = rank_trips(sessions, self.cfg)
        self.assertEqual(apply_ensemble(trips, self.cfg), 0)
        self.assertNotIn("score_roh", trips[0]["sessions"][0])

    def test_thermiksession_traegt_die_verlaesslichkeit_statt_des_ensembles(self):
        """Das Ensemble sieht an der Ora 5 kn und meldet 0 % — bis 1.6.1 halbierte
        das genau die Session, die das Tool korrigiert hatte. Jetzt zählt die
        Verlässlichkeit des Spots, und das Ensemble lässt die Session in Ruhe."""
        from wingscout.score import apply_reliability
        ora = _spot("ora", 3.0, lon=10.0)
        ora["thermal"] = {"name": "Ora", "typical_kn": 16, "reliability": 0.8, "from": 13, "to": 20}
        sessions = _sessions(ora, score=0.80)
        for s in sessions:
            s["thermal"] = True
        trips = rank_trips(sessions, self.cfg)
        s0 = trips[0]["sessions"][0]
        self.assertEqual(s0["score_roh"], 0.80)
        self.assertAlmostEqual(s0["score"], 0.80 * (0.5 + 0.5 * 0.8), places=3)   # 0,72
        self.assertEqual(s0["sicherheit"], {"quelle": "thermik", "p": 0.8})
        for s in trips[0]["sessions"]:
            s["ens"] = {"p_ride": 0.0, "p_good": 0.0, "p10": 3, "p50": 5, "p90": 7, "members": 40}
        self.assertEqual(apply_ensemble(trips, self.cfg), 0)
        self.assertAlmostEqual(trips[0]["sessions"][0]["score"], 0.72, places=3)
        self.assertEqual(apply_reliability(sessions, dict(self.cfg, ensemble={"weight": 0.0})), 0)

    def test_ensemble_schwelle_kennt_faktor_und_regionalmodell(self):
        """Der Report-Wind ist (grob + delta) · faktor; gefragt wird das Ensemble
        nach der rohen Zahl, aus der das würde."""
        from wingscout.score import ensemble_schwelle
        self.assertEqual(ensemble_schwelle(12.0, {}, {}), 12.0)
        self.assertEqual(ensemble_schwelle(12.0, {"wind_factor": 1.2}, {}), 10.0)
        self.assertEqual(ensemble_schwelle(12.0, {}, {"modell_delta": 5.0}), 7.0)
        self.assertEqual(ensemble_schwelle(12.0, {}, {"modell_delta": -3.0}), 15.0)
        self.assertEqual(ensemble_schwelle(12.0, {"wind_factor": 1.2}, {"modell_delta": 4.0}), 6.0)
        self.assertEqual(ensemble_schwelle(3.0, {}, {"modell_delta": 9.0}), 0.0)

    def test_plan_b_wird_nach_der_umsortierung_neu_gesetzt(self):
        nah = _spot("nah", 3.0, lat=50.0, lon=8.0)
        sessions = _sessions(self.sicher) + _sessions(nah, score=0.7)
        trips = rank_trips(sessions, self.cfg)
        self.assertTrue(all("plan_b" in t for t in trips))
        for t in trips:
            for s in t["sessions"]:
                s["ens"] = {"p_ride": 0.9, "p_good": 0.9, "p10": 10, "p50": 14, "p90": 18, "members": 40}
        apply_ensemble(trips, self.cfg)
        self.assertTrue(all("plan_b" in t for t in trips))


if __name__ == "__main__":
    unittest.main()


class ModellPlakette(unittest.TestCase):
    """Befund 3: die Zahl wuchs mit der Länge der Session, nicht mit der Modellgüte."""

    def setUp(self):
        from tests.helpers import cfg as load_cfg
        self.cfg = load_cfg()
        self.cfg["session"]["min_score"] = 0.0
        self.spot = {"id": "t", "name": "T", "lat": 45.87, "lon": 10.87, "drive_h": 5.0,
                     "sectors": [{"from": 200, "to": 340, "quality": "good"}], "water": "flat"}

    def _block(self, deltas):
        start = datetime(2026, 9, 17, 11, 0)
        return [{"t": start + timedelta(hours=i), "day": "2026-09-17", "score": 0.8,
                 "veto": None, "wind": 18.0, "gust": 22.0, "temp": 18.0, "dir_name": "W",
                 "wing": 6.5, "warn": [], "modell": "CH1", "modell_delta": d,
                 "water": "flat", "dir_quality": "good"}
                for i, d in enumerate(deltas)]

    def _session(self, deltas):
        from wingscout.score import build_sessions
        return build_sessions(self.spot, self._block(deltas), self.cfg)[0]

    def test_median_statt_maximum(self):
        # Eine einzige gute Stunde macht aus einer wirkungslosen Session keine gute.
        s = self._session([0.0, 0.0, 0.0, 0.0, 0.0, 12.0])
        self.assertEqual(s["modell_delta"], 0.0)
        self.assertEqual(s["modell_delta_max"], 12.0)

    def test_durchgehender_zugewinn_bleibt_sichtbar(self):
        s = self._session([5.0, 6.0, 5.0, 7.0, 6.0])
        self.assertEqual(s["modell_delta"], 6.0)

    def test_laenge_allein_hebt_den_wert_nicht(self):
        kurz = self._session([0.0, 4.0, 0.0])
        lang = self._session([0.0, 4.0, 0.0] + [0.0] * 9)
        self.assertEqual(kurz["modell_delta"], lang["modell_delta"])

    def test_fehlende_stunden_zaehlen_nicht_als_null(self):
        # Das feine Modell reicht kürzer als die globalen: die unbedeckten
        # Stunden dürfen den Median nicht nach unten ziehen.
        s = self._session([6.0, 6.0, 6.0, None, None, None, None])
        self.assertEqual(s["modell_delta"], 6.0)
        self.assertEqual(s["modell_stunden"], 3)
        self.assertEqual(s["hours"], 7)

    def test_negativer_unterschied_bleibt_negativ(self):
        s = self._session([-4.0, -5.0, -4.0])
        self.assertEqual(s["modell_delta"], -4.0)
        self.assertEqual(s["modell_delta_max"], -5.0)

    def test_ohne_feines_modell_keine_zahl(self):
        s = self._session([None, None, None])
        self.assertIsNone(s["modell_delta"])
        self.assertEqual(s["modell_stunden"], 0)

    def test_plakette_zeigt_median_und_nennt_die_spitze_im_tooltip(self):
        from wingscout.report import _modell_pill
        s = self._session([0.0, 0.0, 0.0, 0.0, 0.0, 12.0])
        html = _modell_pill(s)
        self.assertIn(">CH1<", html)
        self.assertNotIn("+12 kn<", html)            # die Spitze steht nicht auf der Plakette
        self.assertIn("Spitze +12 kn", html)
        self.assertIn("Median", html)
        s2 = self._session([6.0, 6.0, 6.0, None, None])
        html2 = _modell_pill(s2)
        self.assertIn("CH1 +6 kn<", html2)
        self.assertIn("abgedeckt sind 3 von 5 Stunden", html2)
        # Attribut bleibt heil: einfache Anführungszeichen umschließen den Titel
        self.assertNotIn("'", html2.split("title='", 1)[1].split("'>", 1)[0])
