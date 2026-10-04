"""Der Namensvergleich für unbestätigte Koordinaten.

Die eigentliche Arbeit macht hier nicht die Geometrie, sondern die Frage, wann
zwei Namen dasselbe Gewässer meinen. Der teuerste Fehler ist ein falscher
Widerspruch: die halbe importierte Liste heißt „Parkplatz" oder „beacharea",
und wenn das als Fehlalarm in der Liste landet, arbeitet man Fehlalarme ab
statt Fehler.
"""
from __future__ import annotations
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("kcheck", ROOT / "tools" / "koordinaten_check.py")
kcheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kcheck)


class Namensvergleich(unittest.TestCase):
    def test_gleicher_see_passt(self):
        for spot, osm in (
            ("Thunersee", "Thunersee"),
            ("Brombachsee", "Großer Brombachsee"),
            ("Lac du Der", "Lac du Der-Chantecoq"),          # nur über den Volltext
            ("Neusiedler See", "Neusiedler See / Fertő"),
            ("Bade- und Surferwiese Walchensee", "Walchensee"),
            ("Étang de Leucate (Lagune)", "Étang de Leucate"),
        ):
            self.assertEqual(kcheck.namen_vergleich(spot, osm), "passt", f"{spot} / {osm}")

    def test_anderer_see_widerspricht(self):
        for spot, osm in (
            ("Silbersee", "Baggersee Waldsee"),
            ("Plage de Savel", "Lac de Monteynard-Avignonet"),
            ("Playa de Poniente", "Río Piles"),
        ):
            self.assertEqual(kcheck.namen_vergleich(spot, osm), "widerspricht", f"{spot} / {osm}")

    def test_nichtssagender_spotname_ist_unklar(self):
        """Der wichtigste der drei Werte — sonst ist die halbe Liste Fehlalarm."""
        for spot in ("Parkplatz", "Parkplatz Strand", "Stellplatz Womo", "beacharea",
                     "Kitespot", "Surfspot", "Camping", "Slipstelle"):
            self.assertEqual(kcheck.namen_vergleich(spot, "Orrevatnet"), "unklar", spot)

    def test_leerer_osm_name_ist_unklar(self):
        self.assertEqual(kcheck.namen_vergleich("Thunersee", ""), "unklar")

    def test_umlaute_und_akzente_stoeren_nicht(self):
        self.assertEqual(kcheck.namen_vergleich("Grössee", "Groessee"), "passt")
        self.assertEqual(kcheck.namen_vergleich("Étang du Rosel", "Rosel"), "passt")


class PunktImGewaesser(unittest.TestCase):
    """Ein Quadrat als Wasserfläche, ein Punkt in der Mitte."""

    def _daten(self, name, lat0=49.0, lon0=8.0, d=0.01):
        ring = [{"lat": lat0 - d, "lon": lon0 - d}, {"lat": lat0 - d, "lon": lon0 + d},
                {"lat": lat0 + d, "lon": lon0 + d}, {"lat": lat0 + d, "lon": lon0 - d},
                {"lat": lat0 - d, "lon": lon0 - d}]
        tags = {"natural": "water"}
        if name:
            tags["name"] = name
        return {"elements": [{"type": "way", "tags": tags, "geometry": ring}]}

    def test_treffer_wird_zu_gruppe_a(self):
        spot = {"id": "x", "name": "Thunersee", "lat": 49.0, "lon": 8.0}
        fl = kcheck.flaechen(self._daten("Thunersee"), spot["lat"], spot["lon"])
        self.assertEqual(len(fl), 1)
        self.assertEqual(fl[0][0], "Thunersee")
        from wingscout.geometry import point_in_rings
        self.assertTrue(point_in_rings(0.0, 0.0, fl[0][1]))

    def test_unbenannte_flaeche_bleibt_ohne_namen(self):
        fl = kcheck.flaechen(self._daten(None), 49.0, 8.0)
        self.assertEqual(fl[0][0], None)

    def test_pin_ohne_wasser_in_drei_kilometern_ist_gruppe_d(self):
        """Der Prüfstand hat es an der Schwäbischen Alb gezeigt: ohne Wasser in
        Reichweite landete der Punkt in Gruppe B („Meer oder unbenannte
        Fläche“), weil die Rose irgendwo Wasser traf. Der Geometrieeintrag
        weiß es besser."""
        import gzip
        import json
        import tempfile
        spot = {"id": "alb", "name": "Münsinger Alb", "lat": 48.42, "lon": 9.55}
        with tempfile.TemporaryDirectory() as d:
            with gzip.open(Path(d) / "alb_25km.json.gz", "wt", encoding="utf-8") as fh:
                json.dump(self._daten("Fernsee", lat0=48.52, lon0=9.55), fh)      # 11 km nördlich
            urteil = kcheck.pruefe(spot, {"origin_offset_m": [0, 0], "wasser": False,
                                          "max_fetch_km": 14.0}, Path(d))
            self.assertEqual(urteil["gruppe"], "D", urteil)
            self.assertIn("an Land", urteil["grund"])
            # Ohne das Feld (alter Eintrag) bleibt das alte Urteil
            alt = kcheck.pruefe(spot, {"origin_offset_m": [0, 0], "max_fetch_km": 14.0}, Path(d))
            self.assertEqual(alt["gruppe"], "B")

    def test_land_wird_nicht_als_wasser_gelesen(self):
        daten = self._daten("Wald")
        daten["elements"][0]["tags"] = {"landuse": "forest", "name": "Wald"}
        self.assertEqual(kcheck.flaechen(daten, 49.0, 8.0), [])


if __name__ == "__main__":
    unittest.main()
