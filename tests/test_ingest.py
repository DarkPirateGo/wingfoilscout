from __future__ import annotations
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT  # noqa: F401
from wingscout import ingest

KML = '''<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>Brouwersdam Meerseite</name><Point><coordinates>3.854000,51.762500,0</coordinates></Point></Placemark>
<Placemark><name>Nur Linie</name><LineString><coordinates>1,2 3,4</coordinates></LineString></Placemark>
</Document></kml>'''

GEOJSON = '''{"type":"FeatureCollection","features":[
 {"type":"Feature","geometry":{"type":"Point","coordinates":[7.07964,49.56831]},
  "properties":{"location":{"name":"Bostalsee"}}},
 {"type":"Feature","geometry":{"type":"Point","coordinates":[10.8756,45.8695]},"properties":{"Title":"Torbole"}},
 {"type":"Feature","geometry":{"type":"LineString","coordinates":[[1,2],[3,4]]},"properties":{}}]}'''

GPX = '''<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
<wpt lat="52.9797" lon="5.4471"><name>Workum</name></wpt>
<wpt lat="53.0453" lon="5.3958"><name>Makkum</name></wpt></gpx>'''


class Zeilen(unittest.TestCase):
    def test_formen(self):
        faelle = {
            "Hardtsee; 49.17008, 8.61477": ("Hardtsee", 49.17008, 8.61477, None),
            "49.17008, 8.61477 Hardtsee": ("Hardtsee", 49.17008, 8.61477, None),
            "Bostalsee; 49.56831, 7.07964; reservoir": ("Bostalsee", 49.56831, 7.07964, "reservoir"),
            "Marina Julia | 45.77740, 13.53260 | meer": ("Marina Julia", 45.7774, 13.5326, "sea"),
            "https://www.google.com/maps/@51.7625,3.854,15z": ("", 51.7625, 3.854, None),
            "Spot 2; 49.17, 8.61": ("Spot 2", 49.17, 8.61, None),
        }
        for text, erwartet in faelle.items():
            with self.subTest(text=text):
                self.assertEqual(ingest.parse_line(text), erwartet)

    def test_unlesbares(self):
        for text in ("# Kommentar", "", "Unsinn ohne Zahlen", "https://maps.google.com/?cid=12345"):
            self.assertIsNone(ingest.parse_line(text))

    def test_freitext_mit_problemen(self):
        hits, problems = ingest.parse_text("Hardtsee; 49.17008, 8.61477\nQuatsch\n\n# x\n")
        self.assertEqual(len(hits), 1)
        self.assertEqual(problems, ["Quatsch"])


class Dateien(unittest.TestCase):
    def test_gpx(self):
        hits, problems = ingest.parse_text(GPX)
        self.assertEqual([h[0] for h in hits], ["Workum", "Makkum"])
        self.assertEqual(problems, [])

    def test_kml_nur_punkte_und_laenge_breite_vertauscht(self):
        hits, _ = ingest.parse_text(KML)
        self.assertEqual(hits, [("Brouwersdam Meerseite", 51.7625, 3.854, None)])

    def test_geojson(self):
        hits, _ = ingest.parse_text(GEOJSON)
        self.assertEqual([(h[0], h[1], h[2]) for h in hits],
                         [("Bostalsee", 49.56831, 7.07964), ("Torbole", 45.8695, 10.8756)])

    def test_csv_mit_koordinatenspalten(self):
        hits, _ = ingest.parse_text("Name,Latitude,Longitude\nWorkum,52.9797,5.4471\n")
        self.assertEqual(hits, [("Workum", 52.9797, 5.4471, None)])

    def test_takeout_csv_ohne_koordinate_wird_gezaehlt(self):
        text = ('Title,Note,URL\nA,,"https://www.google.com/maps/@51.7625,3.854,15z"\n'
                'B,,"https://maps.google.com/?cid=1"\n')
        hits, problems = ingest.parse_text(text)
        self.assertEqual([h[0] for h in hits], ["A"])
        self.assertEqual(len(problems), 1)
        self.assertIn("1 Zeilen ohne Koordinate", problems[0])

    def test_kmz_wird_erkannt(self):
        hits, problems = ingest.parse_text("PK\x03\x04xyz")
        self.assertEqual(hits, [])
        self.assertIn("KMZ", problems[0])


class Eintraege(unittest.TestCase):
    def test_land_raten(self):
        self.assertEqual(ingest.guess_country(49.17, 8.61), "DE")
        self.assertEqual(ingest.guess_country(51.76, 3.85), "NL")
        self.assertEqual(ingest.guess_country(45.87, 10.87), "IT")
        self.assertEqual(ingest.guess_country(0.0, 0.0), "")

    def test_slug(self):
        self.assertEqual(ingest.slug("Grüner Brink / Fehmarn"), "gruener-brink-fehmarn")
        self.assertEqual(ingest.slug("Grüner Brink / Fehmarn", {"gruener-brink-fehmarn"}), "gruener-brink-fehmarn-2")
        self.assertEqual(ingest.slug("???"), "spot")

    def test_build_entry_ist_vorsichtig(self):
        e = ingest.build_entry("Hardtsee", 49.17008, 8.61477, None, set())
        self.assertEqual(e["id"], "hardtsee")
        # Nicht „lake“ raten: der Katalog kennt `unknown`, die Vorfilter lassen
        # es durch, und die Ufergeometrie sagt später, worin der Spot liegt.
        self.assertEqual(e["water_body"], "unknown")
        self.assertEqual(ingest.build_entry("X", 49.1, 8.6, "sea", set())["water_body"], "sea")
        self.assertTrue(e["sectors_unknown"])
        self.assertEqual(e["sectors"], [])
        self.assertEqual(e["season"], list(range(1, 13)))
        self.assertIn("geraten", e["notes"])

    def test_dateiimport_ist_unbestaetigt_freitext_bestaetigt(self):
        """Hundert Wegpunkte aus einer fremden GPX hat niemand angesehen —
        bis 1.6.1 bekamen sie trotzdem `verified: true` und kamen nie auf
        die Prüfseite."""
        gpx = '<?xml version="1.0"?><gpx><wpt lat="51.7" lon="3.8"><name>A</name></wpt></gpx>'
        self.assertTrue(ingest.ist_datei(gpx))
        self.assertTrue(ingest.ist_datei('{"type":"FeatureCollection","features":[]}'))
        self.assertTrue(ingest.ist_datei("Name,Breite,Länge\nA,51.7,3.8\n"))
        self.assertFalse(ingest.ist_datei("Hardtsee; 49.17008, 8.61477"))
        self.assertFalse(ingest.ist_datei("https://www.google.com/maps/@51.7625,3.854,15z"))
        e = ingest.build_entry("A", 51.7, 3.8, None, set(), verified=False)
        self.assertFalse(e["verified"])
        self.assertEqual(e["source"], "importierte Datei")
        self.assertTrue(ingest.build_entry("A", 51.7, 3.8, None, set())["verified"])

    def test_xml_mit_doctype_wird_abgelehnt(self):
        """Entitäten, die sich tausendfach aufrufen, kosten Speicher — GPX und
        KML brauchen weder DOCTYPE noch ENTITY."""
        bombe = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
                 '<gpx><wpt lat="51.7" lon="3.8"><name>&b;</name></wpt></gpx>')
        self.assertEqual(ingest.parse_gpx(bombe), [])
        self.assertEqual(ingest.parse_kml(bombe.replace("gpx", "kml").replace("wpt", "Placemark")), [])
        sauber = '<gpx><wpt lat="51.7" lon="3.8"><name>A</name></wpt></gpx>'
        self.assertEqual(ingest.parse_gpx(sauber), [("A", 51.7, 3.8, None)])

    def test_dublette(self):
        vorhanden = [{"id": "x", "name": "X", "lat": 51.7559, "lon": 3.8491}]
        self.assertIsNotNone(ingest.too_close(51.7560, 3.8492, vorhanden))
        self.assertIsNone(ingest.too_close(51.80, 3.90, vorhanden))

    def test_append_haengt_gueltiges_yaml_an(self):
        import yaml
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spots.yaml"
            path.write_text("# Katalog\n- id: a\n  name: A\n  lat: 1\n  lon: 2\n", encoding="utf-8")
            ingest.append_to_yaml(path, [ingest.build_entry("Neu: mit Doppelpunkt", 49.1, 8.6, "sea", {"a"})])
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual([s["id"] for s in data], ["a", "neu-mit-doppelpunkt"])


if __name__ == "__main__":
    unittest.main()


class Ortsname(unittest.TestCase):
    """Neue Spots ohne Namen heißen nach dem nächsten Ort (OpenStreetMap) —
    bis 1.13 hießen 54 Spots „Pin 47.6143, 11.3394“."""

    # So hat Nominatim am 20.09.2026 geantwortet (gekürzt)
    FEIN = {"name": "Lütjenhof", "addresstype": "hamlet",
            "address": {"hamlet": "Lütjenhof", "village": "Lütjenbrode", "municipality": "Oldenburg-Land",
                        "county": "Kreis Ostholstein", "country": "Deutschland", "country_code": "de"}}
    GROB = {"name": "Großenbrode", "addresstype": "village",
            "address": {"village": "Großenbrode", "country_code": "de"}}
    MEER = {"name": "Albanien", "addresstype": "country", "address": {"country": "Albanien", "country_code": "al"}}

    def test_vorschlag_aus_der_antwort(self):
        from wingscout.sources import ortsname
        self.assertEqual(ortsname.vorschlag_aus(self.FEIN, self.GROB), {"name": "Lütjenbrode", "country": "DE"})
        # Auf dem Wasser nur das Land — dann bleibt der Koordinatenname
        self.assertEqual(ortsname.vorschlag_aus(self.MEER, self.MEER), {"name": "", "country": "AL"})
        self.assertIsNone(ortsname.vorschlag_aus({}, {"error": "Unable to geocode"}))

    def test_eintrag_mit_ort(self):
        e = ingest.build_entry("", 54.3538, 11.0666, None, set(), ort={"name": "Lütjenbrode", "country": "DE"})
        self.assertEqual((e["name"], e["id"], e["country"]), ("Lütjenbrode", "luetjenbrode", "DE"))
        self.assertIn("OpenStreetMap", e["notes"])
        # Ein mitgegebener Name bleibt, das Land kommt trotzdem aus OpenStreetMap
        e = ingest.build_entry("Mein Spot", 47.4, 9.7, None, set(), ort={"name": "Fußach", "country": "AT"})
        self.assertEqual((e["name"], e["country"]), ("Mein Spot", "AT"))
        # Ohne Antwort wie bisher
        e = ingest.build_entry("", 54.3538, 11.0666, None, set(), ort=None)
        self.assertEqual(e["name"], "Spot 54.3538, 11.0666")

    def test_abfrage_gemerkt_und_ausfall(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from wingscout.sources import ortsname
        antworten = {14: self.FEIN, 10: self.GROB}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(ortsname, "AKTIV", True), \
                mock.patch.object(ortsname, "CACHE_DATEI", Path(d) / "ortsnamen.json"), \
                mock.patch.object(ortsname, "_hole", side_effect=lambda lat, lon, z: antworten[z]) as hole:
            self.assertEqual(ortsname.vorschlag(54.3538, 11.0666)["name"], "Lütjenbrode")
            self.assertEqual(ortsname.vorschlag(54.35381, 11.06662)["name"], "Lütjenbrode")
            self.assertEqual(hole.call_count, 2, "dieselbe Stelle wird nicht noch einmal gefragt")
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(ortsname, "AKTIV", True), \
                mock.patch.object(ortsname, "CACHE_DATEI", Path(d) / "ortsnamen.json"), \
                mock.patch.object(ortsname, "_hole", side_effect=OSError("kein Netz")):
            self.assertIsNone(ortsname.vorschlag(1.0, 2.0))
        self.assertIsNone(ortsname.vorschlag(54.3538, 11.0666), "im Prüflauf abgeschaltet")
