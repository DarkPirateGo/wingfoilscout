"""Die Startseite in docs/ (GitHub Pages, seit 2.1.0) und der neue Name.

Was hier festgehalten wird, ist leicht kaputtzumachen, ohne dass es jemand
merkt: ein Bild, das umbenannt wurde, eine Schrift von einem fremden Server,
ein Beispiel-Report, der versehentlich aus einem echten Lauf mit der eigenen
config.yaml stammt — oder ein „Wingscout“, das in die Oberfläche zurückrutscht.
"""
from __future__ import annotations
import re
import unittest

from tests.helpers import ROOT

DOCS = ROOT / "docs"


class Startseite(unittest.TestCase):
    def test_seiten_laden_nichts_von_fremden_servern(self):
        """Keine Schrift, kein Skript, kein Stil von außen — auch keine
        Google-Schriften: deren Abruf schickt die IP jedes Besuchers an Dritte."""
        for name in ("index.html", "bewertung.html"):
            text = (DOCS / name).read_text(encoding="utf-8")
            with self.subTest(name):
                self.assertEqual(re.findall(r'\ssrc=["\']https?://[^"\']+', text), [])
                self.assertEqual(re.findall(r'<link[^>]+href=["\']https?://[^"\']+', text), [])
                self.assertNotIn("@import", text)
                self.assertNotIn("fonts.googleapis", text)

    def test_alle_lokalen_verweise_gibt_es(self):
        text = (DOCS / "index.html").read_text(encoding="utf-8")
        ziele = set(re.findall(r'(?:src|href|srcset)=["\']([^"\'#?]+)["\']', text))
        lokal = {z for z in ziele if not z.startswith(("http://", "https://", "mailto:")) and z not in ("./", "")}
        self.assertTrue({"demo.html", "bewertung.html", "bilder/icon.png"} <= lokal, lokal)
        for z in sorted(lokal):
            with self.subTest(z):
                self.assertTrue((DOCS / z).is_file(), f"docs/{z} fehlt")
        self.assertTrue((DOCS / ".nojekyll").is_file(), "ohne .nojekyll baut GitHub die Seite mit Jekyll um")

    def test_bilder_gibt_es_hell_und_dunkel_und_sie_bleiben_klein(self):
        """Seit 2.1.0 zeigen Website und README die englische Oberfläche
        (docs/bilder/en/); die deutschen Bilder davor sind gelöscht."""
        for name in ("search", "destinations", "details", "grid"):
            for art in ("light", "dark"):
                pfad = DOCS / "bilder" / "en" / f"{name}-{art}.png"
                with self.subTest(str(pfad.relative_to(DOCS))):
                    self.assertTrue(pfad.is_file())
                    self.assertLess(pfad.stat().st_size, 150_000, "Bilder bleiben für immer in der Historie")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for pfad in re.findall(r'(?:src|srcset)="(docs/bilder/[^"]+)"', readme):
            with self.subTest(pfad):
                self.assertTrue((ROOT / pfad).is_file())

    def test_videos_bleiben_klein(self):
        """Auch ein Video bleibt für immer in der Historie — und jeder Besucher
        lädt es."""
        for name in ("wingfoilscout-promo-en.mp4", "wingfoilscout-desktop-en.mp4"):
            pfad = DOCS / "video" / name
            with self.subTest(name):
                self.assertTrue(pfad.is_file())
                self.assertLessEqual(pfad.stat().st_size, 8_000_000)
        for name in ("promo-poster.jpg", "desktop-poster.jpg"):
            pfad = DOCS / "video" / name
            with self.subTest(name):
                self.assertTrue(pfad.is_file())
                self.assertLess(pfad.stat().st_size, 200_000)

    def test_beispiel_report_ist_ein_demo_lauf(self):
        """Der veröffentlichte Report muss aus einem Demo-Lauf stammen — nie aus
        einem echten Lauf mit der eigenen config.yaml und ihrem Startpunkt.
        Gestartet wird am Demo-Punkt Hamburg, auf höchstens zwei Stellen."""
        text = (DOCS / "demo.html").read_text(encoding="utf-8")
        self.assertIn("Demo run with synthetic weather data", text)
        self.assertIn("Wingfoilscout", text)
        heim = re.search(r'"home": \{"name": "([^"]*)", "lat": (-?[\d.]+), "lon": (-?[\d.]+)\}', text)
        self.assertIsNotNone(heim, "Startpunkt der Karte nicht gefunden")
        self.assertEqual(heim.group(1), "Hamburg")
        self.assertEqual((float(heim.group(2)), float(heim.group(3))), (53.55, 9.99))
        for zahl in heim.group(2, 3):
            self.assertLessEqual(len(zahl.partition(".")[2]), 2, zahl)
        self.assertIn("<b>Start</b> Hamburg", text)
        self.assertIn("origin=53.55,9.99&", text)              # die Routen beginnen dort

    def test_eigener_startpunkt_steht_nirgends_in_docs(self):
        """Gegen die eigene config.yaml geprüft: ihr Startpunkt (`rider.home`)
        darf in keiner Datei der Website stehen. Ohne config.yaml — frischer
        Klon, Prüflauf auf GitHub — gibt es nichts zu vergleichen."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("persoenliche_daten",
                                                      ROOT / "tools" / "persoenliche_daten.py")
        waechter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(waechter)
        punkt = waechter.heimat()
        if punkt is None:
            self.skipTest("keine config.yaml mit rider.home")
        if punkt == ("53.55", "9.99"):
            self.skipTest("der eigene Startpunkt ist der Demo-Punkt")
        for pfad in sorted(DOCS.rglob("*")):
            if pfad.suffix.lower() not in (".html", ".htm", ".md", ".txt", ".json", ".js", ".css", ".svg", ".xml"):
                continue
            with self.subTest(str(pfad.relative_to(ROOT))):
                text = pfad.read_text(encoding="utf-8", errors="replace")
                self.assertEqual(waechter.fundstellen(text, *punkt), [],
                                 "Zeilen mit dem eigenen Startpunkt")


class NeuerName(unittest.TestCase):
    def test_oberflaeche_sagt_wingfoilscout(self):
        """Seit 2.1.0 heißt das Projekt Wingfoilscout. Im Code der Oberfläche
        und des Reports darf der alte Name nicht mehr auftauchen; das
        Python-Paket heißt intern weiter `wingscout` (klein, ein Bezeichner)."""
        for pfad in sorted((ROOT / "wingscout").rglob("*")):
            if pfad.suffix not in (".py", ".js", ".css", ".json") or "__pycache__" in pfad.parts:
                continue
            with self.subTest(str(pfad.relative_to(ROOT))):
                self.assertNotIn("Wingscout", pfad.read_text(encoding="utf-8"))

    def test_startdateien_tragen_den_neuen_namen(self):
        for name in ("Wingfoilscout starten.command", "Wingfoilscout fürs iPhone starten.command", "wingfoilscout.bat"):
            with self.subTest(name):
                self.assertTrue((ROOT / name).is_file())
        for name in ("Wingscout starten.command", "Wingscout fürs iPhone starten.command", "wingscout.bat"):
            with self.subTest(name):
                self.assertFalse((ROOT / name).exists(), f"{name} sollte umbenannt sein")

    def test_startskripte_erkennen_den_frischen_mac(self):
        """Ohne Befehlszeilenwerkzeuge ist /usr/bin/python3 nur ein Platzhalter.
        Dann soll das Skript das sagen, statt „Python ist zu alt“ zu melden."""
        for name in ("Wingfoilscout starten.command", "Wingfoilscout fürs iPhone starten.command"):
            text = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(name):
                self.assertIn("xcode-select -p", text)
                self.assertLess(text.index("xcode-select -p"), text.index("sys.version_info >= (3, 9)"))

    def test_windows_start_probiert_python_aus(self):
        """Seit 2.4.0 wird `python` ausprobiert statt nur gesucht: unter
        Windows kann es der Platzhalter des Microsoft Store sein, und dann
        scheiterte erst die Installation von PyYAML. Danach der Starter `py`
        von python.org, verlangt 3.9 wie auf dem Mac. Nur ASCII (cmd.exe),
        keine Sprungmarken: die Datei hat LF-Zeilenenden."""
        text = (ROOT / "wingfoilscout.bat").read_bytes().decode("ascii")
        self.assertNotIn("where python", text)
        for aufruf in ('python -c "import sys; sys.exit(sys.version_info < (3, 9))"',
                       'py -3 -c "import sys; sys.exit(sys.version_info < (3, 9))"',
                       "%PY% -m wingscout.webui"):
            self.assertIn(aufruf, text)
        befehle = [z.strip().lower() for z in text.splitlines()
                   if z.strip() and not z.strip().lower().startswith("rem")]
        self.assertEqual([z for z in befehle if z.startswith(":") or "goto" in z.split()], [])
        self.assertEqual(sum(1 for z in befehle if z.startswith("echo ")), 4, "eine Zeile je Sprache")


if __name__ == "__main__":
    unittest.main()
