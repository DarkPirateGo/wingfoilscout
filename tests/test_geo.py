from __future__ import annotations
import unittest
from tests.helpers import cfg  # noqa: F401  (setzt sys.path)
from wingscout.geo import parse_position, haversine_km, compass, in_sector, angle_diff, shore_relation


class ParsePosition(unittest.TestCase):
    def test_dezimal_varianten(self):
        erwartet = (51.7625, 3.854)
        for text in ("51.7625, 3.854", "51,7625 3,854", "51.7625;3.854",
                     "N 51.7625 O 3.854", "51.7625 3.854", "  51.7625 , 3.854  "):
            with self.subTest(text=text):
                self.assertEqual(parse_position(text), erwartet)
        self.assertEqual(parse_position("53.550/9.990"), (53.55, 9.99))

    def test_grad_minuten_sekunden(self):
        lat, lon = parse_position("51°45'45\"N 3°51'14\"E")
        self.assertAlmostEqual(lat, 51.7625, places=4)
        self.assertAlmostEqual(lon, 3.8539, places=3)

    def test_suedliche_und_westliche_halbkugel(self):
        self.assertEqual(parse_position("-33.9249, 18.4241"), (-33.9249, 18.4241))
        lat, lon = parse_position("33°55'S 18°25'E")
        self.assertLess(lat, 0)

    def test_maps_links(self):
        self.assertEqual(parse_position("https://www.google.com/maps/@51.7625,3.854,13z"), (51.7625, 3.854))
        self.assertEqual(parse_position("https://www.google.com/maps/place/X/@49.17008,8.61477,15z"), (49.17008, 8.61477))

    def test_link_ohne_koordinate_erfindet_nichts(self):
        # Vorher wurden aus ?cid=12345 die Ziffern 45 und 123 als Position gelesen.
        self.assertIsNone(parse_position("https://maps.google.com/?cid=12345"))
        self.assertIsNone(parse_position("https://www.google.com/maps/place/Hardtsee/data=!4m2!3m1"))

    def test_unsinn(self):
        for text in ("", "   ", "Quatsch", "200, 500", None):
            self.assertIsNone(parse_position(text))


class Winkel(unittest.TestCase):
    def test_haversine(self):
        self.assertAlmostEqual(haversine_km(53.55, 9.99, 53.55, 9.99), 0.0)
        self.assertAlmostEqual(haversine_km(51.7625, 3.854, 53.55, 9.99), 459, delta=6)

    def test_compass(self):
        self.assertEqual(compass(0), "N")
        self.assertEqual(compass(90), "O")
        self.assertEqual(compass(225), "SW")
        self.assertEqual(compass(359), "N")

    def test_sektor_ueber_nord(self):
        self.assertTrue(in_sector(10, 320, 40))
        self.assertTrue(in_sector(330, 320, 40))
        self.assertFalse(in_sector(180, 320, 40))

    def test_angle_diff_und_lage(self):
        self.assertEqual(angle_diff(350, 10), 20)
        self.assertEqual(shore_relation(90, 90), "auflandig")
        self.assertEqual(shore_relation(270, 90), "ablandig")
        self.assertEqual(shore_relation(180, 90), "sideshore")


if __name__ == "__main__":
    unittest.main()
