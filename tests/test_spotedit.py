"""Koordinaten in spots.yaml ändern, ohne die Datei zu verlieren.

Der Katalog ist das eigentliche Asset und besteht zu einem guten Teil aus
Kommentaren. Diese Tests halten fest, dass eine Korrektur genau eine Zeile
ändert und sonst nichts.
"""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path

import yaml

from wingscout import spotedit

BEISPIEL = """\
# Kopfkommentar, der bleiben muss
- id: erster-spot
  name: Erster
  # Notiz mitten im Block
  lat: 49.1
  lon: 8.6
  water_body: lake
  dogs: "no"
- id: zweiter-spot
  name: Zweiter
  lat: 50.0
  lon: 9.0
  notes: enthält - einen Bindestrich
# Fußkommentar
"""


class Bearbeiten(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.pfad = Path(self.ordner.name) / "spots.yaml"
        self.pfad.write_text(BEISPIEL, encoding="utf-8")

    def tearDown(self):
        self.ordner.cleanup()

    def text(self):
        return self.pfad.read_text(encoding="utf-8")

    def test_textfeld_setzen(self):
        """`country: AL` für einen Spot, dessen Land geraten war — in
        Anführungszeichen, und ein vorhandenes Feld wird ersetzt, nicht verdoppelt."""
        spotedit.set_text(self.pfad, "zweiter-spot", "country", "AL")
        spotedit.set_text(self.pfad, "erster-spot", "dogs", "no")
        text = self.text()
        self.assertIn('  country: "AL"\n', text)
        self.assertEqual(text.count("dogs:"), 1)
        self.assertIn('  dogs: "no"\n', text)
        daten = yaml.safe_load(text)
        self.assertEqual(daten[1]["country"], "AL")
        self.assertEqual(daten[0]["dogs"], "no")
        self.assertIn("# Notiz mitten im Block", text)
        spotedit.set_text(self.pfad, "erster-spot", "notes", 'sagt "hallo"')
        self.assertEqual(yaml.safe_load(self.text())[0]["notes"], 'sagt "hallo"')
        # Mehrzeilig: als \n in Anführungszeichen — YAML liest den Umbruch zurück
        vorher = self.text().count("\n")
        spotedit.set_text(self.pfad, "erster-spot", "comment", "zwei\nZeilen\tmit Tab")
        self.assertEqual(yaml.safe_load(self.text())[0]["comment"], "zwei\nZeilen\tmit Tab")
        self.assertEqual(self.text().count("\n"), vorher + 1)   # eine Zeile mehr, kein Umbruch im Wert
        # Leer nimmt das Feld heraus
        spotedit.set_text(self.pfad, "erster-spot", "comment", "")
        self.assertNotIn("comment", yaml.safe_load(self.text())[0])
        self.assertNotIn("comment:", self.text())
        with self.assertRaises(spotedit.SpotNichtGefunden):
            spotedit.set_text(self.pfad, "gibt-es-nicht", "country", "DE")

    def test_umgebrochener_wert_wird_ganz_ersetzt(self):
        """`notes:` steht im Katalog oft über mehrere Zeilen (YAML faltet einen
        eingerückten Fließtext zu einem Wert). Bis 1.19.2 ersetzte `set_text`
        nur die Kopfzeile und ließ die Fortsetzung als Waisen stehen — die
        Datei war danach nicht mehr lesbar (gefunden am 29.09.2026 beim Kürzen
        von 163 Notizen). Dasselbe beim Leeren und bei Werten in Anführungszeichen."""
        self.pfad.write_text(BEISPIEL.replace(
            "  notes: enthält - einen Bindestrich\n",
            "  notes: erste Zeile, die\n    weitergeht und noch\n    eine dritte hat\n"
            "  comment: 'in Anführungszeichen\n    über zwei Zeilen'\n"
            "  wind_factor: 1.0\n"), encoding="utf-8")
        self.assertEqual(yaml.safe_load(self.text())[1]["notes"], "erste Zeile, die weitergeht und noch eine dritte hat")
        spotedit.set_text(self.pfad, "zweiter-spot", "notes", "kurz")
        daten = yaml.safe_load(self.text())                      # liest sich noch
        self.assertEqual(daten[1]["notes"], "kurz")
        self.assertEqual(daten[1]["comment"], "in Anführungszeichen über zwei Zeilen")
        self.assertEqual(daten[1]["wind_factor"], 1.0)
        self.assertNotIn("weitergeht", self.text())
        spotedit.set_text(self.pfad, "zweiter-spot", "comment", "")
        daten = yaml.safe_load(self.text())
        self.assertNotIn("comment", daten[1])
        self.assertNotIn("Anführungszeichen", self.text())
        self.assertEqual(daten[1]["wind_factor"], 1.0)
        # Auch eine Zahl hinter einem umgebrochenen Feld: der Nachbar bleibt heil
        spotedit.set_zahl(self.pfad, "zweiter-spot", "wind_factor", 1.1)
        self.assertEqual(yaml.safe_load(self.text())[1]["notes"], "kurz")

    def test_zahl_setzen(self):
        """`wind_factor` aus dem Tagebuch: neu anlegen, dann ersetzen — als Zahl, nicht als Text."""
        spotedit.set_zahl(self.pfad, "erster-spot", "wind_factor", 1.15)
        self.assertIn("  wind_factor: 1.15\n", self.text())
        spotedit.set_zahl(self.pfad, "erster-spot", "wind_factor", 1)
        text = self.text()
        self.assertEqual(text.count("wind_factor:"), 1)
        self.assertEqual(yaml.safe_load(text)[0]["wind_factor"], 1.0)
        self.assertIn("# Notiz mitten im Block", text)
        for falsch in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                spotedit.set_zahl(self.pfad, "erster-spot", "wind_factor", falsch)
        with self.assertRaises(ValueError):
            spotedit.set_zahl(self.pfad, "erster-spot", "Wind-Faktor", 1.0)

    def test_unterblock_bleibt_unberuehrt(self):
        """Ein Spot mit Thermikblock hat zwei `name:` — der eigene und der des
        Windes. Umbenannt wird der Spot, nicht der Wind (20.09.: aus
        „Nordwind“ wurde „Achensee – Pertisau“, der Spot hieß weiter „Achensee 1“)."""
        self.pfad.write_text("""\
- id: mit-thermik
  thermal:
    name: "Nordwind"
    comment: "Wind-Kommentar"
  name: Achensee 1 (Jens-Dee-Pin)
  lat: 47.45
  lon: 11.71
""", encoding="utf-8")
        spotedit.set_text(self.pfad, "mit-thermik", "name", "Achensee – Pertisau")
        spotedit.set_text(self.pfad, "mit-thermik", "comment", "")
        d = yaml.safe_load(self.text())[0]
        self.assertEqual(d["name"], "Achensee – Pertisau")
        self.assertEqual(d["thermal"], {"name": "Nordwind", "comment": "Wind-Kommentar"})
        # Ein neues Feld kommt auf die Ebene des Spots, nicht in den Unterblock
        spotedit.set_text(self.pfad, "mit-thermik", "country", "AT")
        d = yaml.safe_load(self.text())[0]
        self.assertEqual(d["country"], "AT")
        self.assertNotIn("country", d["thermal"])

    def test_spot_entfernen(self):
        """Der Block verschwindet, der Rest der Datei bleibt Zeichen für Zeichen."""
        weg = spotedit.entferne(self.pfad, "erster-spot")
        text = self.text()
        self.assertIn("- id: erster-spot", weg)
        self.assertIn("# Notiz mitten im Block", weg)
        self.assertNotIn("erster-spot", text)
        self.assertIn("# Kopfkommentar, der bleiben muss", text)
        self.assertIn("- id: zweiter-spot", text)
        self.assertIn("# Fußkommentar", text)
        self.assertEqual([e["id"] for e in yaml.safe_load(text)], ["zweiter-spot"])
        spotedit.entferne(self.pfad, "zweiter-spot")
        self.assertEqual(yaml.safe_load(self.text()), None)          # nur noch Kommentare
        with self.assertRaises(spotedit.SpotNichtGefunden):
            spotedit.entferne(self.pfad, "erster-spot")

    def test_schreiben_ist_atomar(self):
        """Nachbardatei plus Umbenennen: keine halbe Datei, kein Rest daneben."""
        spotedit.set_flag(self.pfad, "erster-spot", "verified", True)
        self.assertEqual(sorted(x.name for x in Path(self.ordner.name).iterdir()), ["spots.yaml"])
        self.assertIn("verified: true", self.text())
        spotedit.schreibe_atomar(self.pfad, "- id: a\n")
        self.assertEqual(self.text(), "- id: a\n")
        self.assertFalse((self.pfad.with_name("spots.yaml.neu")).exists())

    def test_koordinate_aendern_laesst_alles_andere_stehen(self):
        spotedit.set_coords(self.pfad, "erster-spot", 49.123456, 8.654321)
        neu = self.text()
        self.assertIn("# Kopfkommentar, der bleiben muss", neu)
        self.assertIn("# Notiz mitten im Block", neu)
        self.assertIn("# Fußkommentar", neu)
        self.assertIn("  lat: 49.123456\n", neu)
        self.assertIn("  lon: 8.654321\n", neu)
        # Der zweite Spot ist unberührt
        self.assertIn("  lat: 50.0\n", neu)
        daten = yaml.safe_load(neu)
        self.assertEqual(len(daten), 2)
        self.assertEqual(daten[0]["lat"], 49.123456)
        self.assertEqual(daten[0]["dogs"], "no")          # bleibt Text, nicht False
        self.assertTrue(daten[0]["verified"])             # Korrektur gilt als geprüft

    def test_zweiter_spot_trotz_bindestrich_im_text(self):
        spotedit.set_coords(self.pfad, "zweiter-spot", 51.0, 4.0)
        daten = yaml.safe_load(self.text())
        self.assertEqual((daten[1]["lat"], daten[1]["lon"]), (51.0, 4.0))
        self.assertEqual(daten[0]["lat"], 49.1)
        self.assertIn("enthält - einen Bindestrich", self.text())

    def test_flag_setzen_und_neu_anlegen(self):
        spotedit.set_flag(self.pfad, "erster-spot", "geo_ok", True)
        daten = yaml.safe_load(self.text())
        self.assertTrue(daten[0]["geo_ok"])
        spotedit.set_flag(self.pfad, "erster-spot", "geo_ok", False)
        self.assertFalse(yaml.safe_load(self.text())[0]["geo_ok"])

    def test_unbekannter_spot_meldet_sich(self):
        with self.assertRaises(spotedit.SpotNichtGefunden):
            spotedit.set_coords(self.pfad, "gibt-es-nicht", 1.0, 2.0)
        self.assertEqual(self.text(), BEISPIEL)          # Datei unverändert

    def test_unsinnige_koordinate_wird_abgelehnt(self):
        for lat, lon in ((91.0, 0.0), (0.0, 181.0), (-100.0, 0.0)):
            with self.assertRaises(ValueError):
                spotedit.set_coords(self.pfad, "erster-spot", lat, lon)
        self.assertEqual(self.text(), BEISPIEL)

    def test_feldname_wird_geprueft(self):
        with self.assertRaises(ValueError):
            spotedit.set_flag(self.pfad, "erster-spot", "lat: 0\n  boese", True)
