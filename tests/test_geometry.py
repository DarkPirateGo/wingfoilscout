from __future__ import annotations
import unittest

from tests.helpers import square_lake
from wingscout import geometry as geo
from wingscout import shoreline

LAT, LON = 52.0, 5.0


class SyntheticLake(unittest.TestCase):
    """Ein 2 × 2 km großer See, der Spot steht 60 m westlich am Ufer."""

    def setUp(self):
        self.data = square_lake(LAT, LON, x0=60, x1=2060, y0=-1000, y1=1000)
        self.parts = geo.segments_from_osm(self.data, LAT, LON)
        self.index = geo.SegmentIndex(self.parts["segments"])

    def test_zerlegung(self):
        self.assertEqual(len(self.parts["rings"]), 1)
        self.assertEqual(len(self.parts["segments"]), 4)
        self.assertEqual(self.parts["coastline"], [])

    def test_spot_liegt_an_land_und_wird_ins_wasser_versetzt(self):
        self.assertFalse(geo.point_in_rings(0.0, 0.0, self.parts["rings"]))
        ox, oy, moved, status = geo.snap_into_water(self.parts, self.index, 36, 5.0, prefer="lake")
        self.assertTrue(moved)
        self.assertTrue(geo.point_in_rings(ox, oy, self.parts["rings"]))
        self.assertGreater(ox, 60)                 # nach Osten, in den See
        self.assertLess(abs(oy), 1)
        self.assertIn("ins Wasser versetzt", status)
        self.assertNotIn("Koordinate prüfen", status)   # 90 m sind kein Grund zur Sorge

    def test_anlauf_nach_osten_lang_nach_westen_kurz(self):
        ox, oy, *_ = geo.snap_into_water(self.parts, self.index, 36, 5.0, prefer="lake")
        rose = geo.fetch_rose(self.index, ox, oy, 36, 5.0)
        self.assertEqual(len(rose), 36)
        ost, west = geo.rose_at(rose, 90), geo.rose_at(rose, 270)
        self.assertAlmostEqual(ost, 2060 - ox, delta=15)
        self.assertLess(west, 120)
        summary = geo.summarize(rose)
        self.assertTrue(40 <= summary["open_bearing"] <= 140, summary)   # offen nach Osten
        self.assertAlmostEqual(summary["max_fetch_km"], 2.1, delta=0.2)  # bis in die ferne Ecke

    def test_weit_entfernte_koordinate_wird_markiert(self):
        data = square_lake(LAT, LON, x0=1200, x1=3200, y0=-1000, y1=1000)
        parts = geo.segments_from_osm(data, LAT, LON)
        *_, status = geo.snap_into_water(parts, geo.SegmentIndex(parts["segments"]), 36, 5.0, prefer="lake")
        self.assertIn("Koordinate prüfen", status)

    def test_kleingewaesser_fliegen_raus(self):
        data = square_lake(LAT, LON, x0=60, x1=160, y0=-50, y1=50)    # 100 m Teich
        parts = geo.segments_from_osm(data, LAT, LON, min_water_m=150)
        self.assertEqual(parts["rings"], [])
        self.assertEqual(parts["segments"], [])


class Relationen(unittest.TestCase):
    def _rel(self, members):
        return {"type": "relation", "tags": {"natural": "water"}, "members": members}

    def test_ring_aus_offenen_teilstuecken(self):
        a = [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 0.01}]
        b = [{"lat": 0, "lon": 0.01}, {"lat": 0.01, "lon": 0.01}, {"lat": 0.01, "lon": 0}]
        c = [{"lat": 0.01, "lon": 0}, {"lat": 0, "lon": 0}]
        rings = geo.stitch_rings(self._rel([{"role": "outer", "geometry": b},
                                            {"role": "outer", "geometry": c},
                                            {"role": "outer", "geometry": a}]))
        self.assertEqual(len(rings), 1)
        chain, closed = rings[0]
        self.assertTrue(closed)
        self.assertEqual(chain[0], chain[-1])

    def test_luecken_in_punktlisten(self):
        a = [{"lat": 0, "lon": 0}, None, {"lat": 0, "lon": 0.01}]
        b = [{"lat": 0, "lon": 0.01}, {"lat": 0.01, "lon": 0.01}, {"lat": 0, "lon": 0}]
        rings = geo.stitch_rings(self._rel([{"role": "outer", "geometry": a}, {"role": "outer", "geometry": b}]))
        self.assertEqual(len(rings), 1)

    def test_offener_zug_wird_als_flaeche_gefuehrt_aber_nicht_zum_blocker(self):
        # Ein großes Gewässer, dessen Ufer über den Ausschnitt hinausläuft
        a = [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 0.05}, {"lat": 0.05, "lon": 0.05}, {"lat": 0.05, "lon": 0.0}]
        rings = geo.stitch_rings(self._rel([{"role": "outer", "geometry": a}]))
        self.assertEqual(len(rings), 1)
        self.assertFalse(rings[0][1])
        parts = geo.segments_from_osm({"elements": [self._rel([{"role": "outer", "geometry": a}])]}, 0.025, 0.025)
        self.assertEqual(len(parts["rings"]), 1)
        self.assertEqual(parts["rings"][0][0], parts["rings"][0][-1])   # künstlich geschlossen
        self.assertEqual(len(parts["segments"]), 3)                     # aber nur echte Ufer als Strecken

    def test_rollen_ohne_outer_inner_ignoriert(self):
        rings = geo.stitch_rings(self._rel([{"role": "label", "geometry": [{"lat": 0, "lon": 0}, {"lat": 1, "lon": 1}]}]))
        self.assertEqual(rings, [])


class Formeln(unittest.TestCase):
    def test_wellenhoehe_waechst_mit_anlauf_und_wind(self):
        self.assertLess(geo.wave_height_m(15, 1000), geo.wave_height_m(15, 20000))
        self.assertLess(geo.wave_height_m(10, 10000), geo.wave_height_m(25, 10000))
        self.assertEqual(geo.wave_height_m(15, 0), 0.0)

    def test_wasserlabel(self):
        self.assertEqual(geo.water_label(0.1), "flat")
        self.assertEqual(geo.water_label(0.4), "chop")
        self.assertEqual(geo.water_label(1.0), "wave")

    def test_klassifikation(self):
        lage, _ = geo.classify(fetch_up_m=20000, fetch_down_m=100)
        self.assertEqual(lage, "auflandig")
        lage, _ = geo.classify(fetch_up_m=100, fetch_down_m=20000)
        self.assertEqual(lage, "ablandig")


if __name__ == "__main__":
    unittest.main()


class Befund(unittest.TestCase):
    """Wann eine Ufergeometrie auffällt — und wann eben nicht.

    Die erste Fassung nahm `open_share < 0.15` und nannte alles davon
    „Koordinate prüfen". Auf 800 m Wasser ist keine Richtung offen, also
    landeten 39 völlig korrekte Baggerseen in der Liste, während 25 Spots mit
    kilometerweit danebenliegendem Pin fehlten. Diese Tests halten die
    Unterscheidung fest.
    """

    @staticmethod
    def eintrag(**werte):
        basis = {"max_fetch_km": 5.0, "median_fetch_km": 2.0, "open_share": 0.8,
                 "origin_offset_m": [0, 0], "status": "im Wasser"}
        basis.update(werte)
        return basis

    def test_kleiner_see_ist_kein_befund(self):
        # Hardtsee: 800 m Wasser, Pin sitzt richtig, keine Richtung „offen"
        see = self.eintrag(max_fetch_km=0.8, median_fetch_km=0.2, open_share=0.0)
        self.assertIsNone(shoreline.befund(see))

    def test_zu_wenig_wasser_ist_unbrauchbar(self):
        stufe, grund = shoreline.befund(self.eintrag(max_fetch_km=0.1))
        self.assertEqual(stufe, "unbrauchbar")
        self.assertIn("100 m", grund)

    def test_weit_versetzter_pin_faellt_auf_auch_bei_viel_wasser(self):
        weit = self.eintrag(max_fetch_km=25.0, origin_offset_m=[2000, 1500])
        stufe, grund = shoreline.befund(weit)
        self.assertEqual(stufe, "pruefen")
        self.assertIn("2500 m", grund)

    def test_kurzer_versatz_ist_kein_befund(self):
        self.assertIsNone(shoreline.befund(self.eintrag(origin_offset_m=[40, 30])))

    def test_auffaellig_sortiert_nach_schwere(self):
        store = {
            "knapp": self.eintrag(max_fetch_km=0.2),
            "ganz_wenig": self.eintrag(max_fetch_km=0.05),
            "weit": self.eintrag(origin_offset_m=[3000, 0]),
            "weniger_weit": self.eintrag(origin_offset_m=[1200, 0]),
            "heil": self.eintrag(),
        }
        schlecht, pruefen = shoreline.auffaellig(store)
        self.assertEqual([s[0] for s in schlecht], ["ganz_wenig", "knapp"])
        self.assertEqual([p[0] for p in pruefen], ["weit", "weniger_weit"])


class BuildGeometrySkript(unittest.TestCase):
    def test_force_mit_only_laesst_den_rest_stehen(self):
        """`--force` begann bis 1.7.0 mit einem leeren Speicher: zusammen mit
        `--only` blieben von 275 Einträgen sechs übrig. Der Bestand muss
        stehen bleiben, nur die gewählten Spots werden ersetzt."""
        import json
        import sys
        import tempfile
        from pathlib import Path
        from unittest import mock
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import build_geometry
        with tempfile.TemporaryDirectory() as d:
            spots = Path(d) / "spots.yaml"
            spots.write_text("- id: a\n  name: A\n  lat: 52.0\n  lon: 5.0\n"
                             "- id: b\n  name: B\n  lat: 52.1\n  lon: 5.1\n", encoding="utf-8")
            out = Path(d) / "geometry.json"
            out.write_text(json.dumps({"a": {"max_fetch_km": 9.0, "rose_m": [9000.0] * 36},
                                       "b": {"max_fetch_km": 8.0, "rose_m": [8000.0] * 36}}),
                           encoding="utf-8")
            neu = {"n_dirs": 36, "radius_km": 25, "rose_m": [1000.0] * 36, "max_fetch_km": 1.0,
                   "open_share": 0.0, "status": "im Wasser", "open_bearing": 0,
                   "median_fetch_km": 1.0, "origin_offset_m": [0, 0], "protected": []}
            import contextlib
            import io
            with mock.patch.object(build_geometry, "run_batch",
                                   side_effect=lambda todo, store, path, *a, **k: (
                                       [store.__setitem__(s["id"], dict(neu)) for s in todo],
                                       shoreline.save_store(path, store), (len(todo), 0))[-1]), \
                    contextlib.redirect_stdout(io.StringIO()):          # das Skript druckt — nicht im Prüflauf
                code = build_geometry.main(["--force", "--only", "b", "--spots", str(spots),
                                            "--out", str(out), "--config",
                                            str(Path(__file__).resolve().parent.parent / "config.example.yaml")])
            self.assertEqual(code, 0)
            danach = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(danach["a"]["max_fetch_km"], 9.0, "a war nicht gewählt und bleibt")
            self.assertEqual(danach["b"]["max_fetch_km"], 1.0, "b wurde neu gerechnet")
