"""Spots aus der Community (seit 2.3.0): das Formular „Suggest a spot“ auf
GitHub und die Links, mit denen Wingfoilscout es öffnet.

Gewünscht am 04.10.2026: eine einfache Möglichkeit, dass die Community Spots
hinzufügt. Der Weg führt über ein Formular auf GitHub
(`.github/ISSUE_TEMPLATE/spot.yml`) — ohne Git, mit einem kostenlosen Konto —,
übernommen wird von Hand. Wingfoilscout öffnet das Formular nur als Link,
vorausgefüllt über die Adresse; die Namen in der Adresse sind die `id`s der
Felder und müssen zum Formular passen.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
import urllib.parse
from pathlib import Path

import yaml

from wingscout import REPO, SPOT_FORMULAR
from wingscout import webui as w
from wingscout.config import load_config

ROOT = Path(__file__).resolve().parent.parent
FORMULAR = ROOT / ".github" / "ISSUE_TEMPLATE" / "spot.yml"
CONFIG = ROOT / "config.example.yaml"
KATALOG_JS = ROOT / "wingscout" / "web" / "katalog.js"
NODE = shutil.which("node")


def formular() -> dict:
    return yaml.safe_load(FORMULAR.read_text(encoding="utf-8"))


class Formular(unittest.TestCase):
    """Das Formular selbst — wie GitHub es verlangt (Schlüssel, `id`s)."""

    def test_aufbau(self):
        f = formular()
        for schluessel in ("name", "description", "body"):
            self.assertIn(schluessel, f)
        self.assertTrue(f["title"].startswith("Spot"))
        arten = {"markdown", "input", "textarea", "dropdown", "checkboxes"}
        for feld in f["body"]:
            self.assertIn(feld["type"], arten)
            self.assertIn("attributes", feld)

    def test_ids_eindeutig_und_erlaubt(self):
        ids = [feld["id"] for feld in formular()["body"] if "id" in feld]
        self.assertEqual(len(ids), len(set(ids)))
        for i in ids:
            self.assertRegex(i, r"^[A-Za-z0-9_-]+$")

    def test_die_vorausgefuellten_felder_gibt_es(self):
        """Was Wingfoilscout in die Adresse schreibt, muss ein Textfeld des
        Formulars sein — sonst kommt der Wert nicht an."""
        textfelder = {feld["id"] for feld in formular()["body"] if feld["type"] in ("input", "textarea")}
        code = KATALOG_JS.read_text(encoding="utf-8")
        for name in ("name", "koordinate", "hinweise"):
            with self.subTest(feld=name):
                self.assertIn(name, textfelder)
                self.assertRegex(code, rf"\b{name}:")

    def test_zustimmung_ist_pflicht(self):
        zustimmung = next(feld for feld in formular()["body"] if feld.get("id") == "zustimmung")
        optionen = zustimmung["attributes"]["options"]
        self.assertTrue(all(o.get("required") for o in optionen))
        self.assertIn("PolyForm Noncommercial 1.0.0", optionen[0]["label"])

    def test_gewaesser_wie_im_katalog(self):
        """Die Auswahl deckt die Gewässerarten des Katalogs ab (plus „weiß nicht“)."""
        gewaesser = next(feld for feld in formular()["body"] if feld.get("id") == "gewaesser")
        self.assertEqual(len(gewaesser["attributes"]["options"]), len(w.WATER_TYPES) + 1)


class Adresse(unittest.TestCase):

    def test_formularadresse(self):
        self.assertEqual(SPOT_FORMULAR, REPO + "/issues/new")
        self.assertTrue(REPO.startswith("https://github.com/"))

    def test_vorausgefuellt_und_kodiert(self):
        adresse = w.spot_vorschlag({"name": "A & B <x>", "koordinate": "51.7625, 3.854", "leer": "",
                                    "hinweise": "x" * 1000})
        basis, _, abfrage = adresse.partition("?")
        self.assertEqual(basis, SPOT_FORMULAR)
        werte = urllib.parse.parse_qs(abfrage)
        self.assertEqual(werte["template"], ["spot.yml"])
        self.assertEqual(werte["name"], ["A & B <x>"])
        self.assertEqual(werte["koordinate"], ["51.7625, 3.854"])
        self.assertNotIn("leer", werte)
        self.assertEqual(len(werte["hinweise"][0]), 300)
        self.assertNotIn("<", adresse)

    @unittest.skipUnless(NODE, "node fehlt")
    def test_im_browser_dieselbe_adresse(self):
        """`vorschlagUrl()` aus katalog.js baut dieselbe Adresse wie Python."""
        code = KATALOG_JS.read_text(encoding="utf-8")
        teile = re.findall(r"^function (?:vorschlagUrl|korrekturUrl)\(.*?^}", code, re.M | re.S)
        self.assertEqual(len(teile), 2)
        prog = ("var VORSCHLAG = " + repr(SPOT_FORMULAR) + "; function t(s) { return s; }\n" + "\n".join(teile)
                + "\nconsole.log(vorschlagUrl({name: 'A & B <x>', koordinate: '51.7625, 3.854', leer: ''}));"
                  "\nconsole.log(korrekturUrl({name: 'Brouwersdam', lat: 51.76251234, lon: 3.85412345}));")
        aus = subprocess.run([NODE, "-"], input=prog, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(aus.returncode, 0, aus.stderr)
        js, korrektur = aus.stdout.strip().split("\n")
        self.assertEqual(urllib.parse.parse_qs(js.partition("?")[2]),
                         urllib.parse.parse_qs(w.spot_vorschlag({"name": "A & B <x>", "koordinate": "51.7625, 3.854"})
                                               .partition("?")[2]))
        werte = urllib.parse.parse_qs(korrektur.partition("?")[2])
        self.assertEqual(werte["koordinate"], ["51.76251, 3.85412"])
        self.assertEqual(werte["title"], ["Spot: Brouwersdam – Korrektur"])


class Seiten(unittest.TestCase):

    def test_katalog(self):
        from wingscout.spots import load_spots
        seite = w.katalog_page(load_spots(str(ROOT / "spots.yaml"))[:3], {"lat": 53.55, "lon": 9.99})
        self.assertRegex(seite, r"<a id='kvorschlag' href='https://github\.com/DarkPirateGo/wingfoilscout/issues/new\?"
                                r"template=spot\.yml' target='_blank' rel='noopener noreferrer'>")
        self.assertIn('var VORSCHLAG = "https://github.com/DarkPirateGo/wingfoilscout/issues/new";', seite)

    def test_suchseite(self):
        cfg = load_config(str(CONFIG))
        seite = w.page(cfg, w.form_defaults(cfg))
        self.assertIn("Für alle in den Katalog:", seite)
        self.assertIn("href='" + w.spot_vorschlag().replace("&", "&amp;") + "' target='_blank' "
                      "rel='noopener noreferrer'", seite)

    def test_korrekturlink_wird_nicht_abgefangen(self):
        """Die Aktionen einer Zeile (umbenennen, verschieben …) halten den Klick
        an; der Link zu GitHub muss durchgehen — die Klickbehandlung gilt nur
        für Links mit `data-akt`."""
        code = KATALOG_JS.read_text(encoding="utf-8")
        self.assertIn("querySelectorAll('.kakt a[data-akt]')", code)
        self.assertNotIn("querySelectorAll('.kakt a')", code)
        self.assertIn('class="vorschlag"', code)
        self.assertIn('rel="noopener noreferrer"', code)


if __name__ == "__main__":
    unittest.main()
