"""Logo des Erstellers und Versionsnummer (1.19.1): rechts in der
Reiterleiste am Rechner, im Fuß jeder Seite am Handy, unter dem Fuß des
Reports — und die Bilddatei kommt vom Server, ohne dass web/ freigegeben wäre.

Bis 1.19.0 stand die Nummer nur klein in der Unterzeile der Suchseite und im
Fuß des Reports; auf Katalog, Rückblick und Tagebuch gar nicht."""
from __future__ import annotations
import base64
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from tests.helpers import cfg as load_cfg, CONFIG, SPOTS
from wingscout import __version__, WEB
import wingscout.webui as w

LOGO = WEB / "logo.png"


class Leiste(unittest.TestCase):
    def test_marke_in_der_leiste_vor_beenden(self):
        leiste = w.reiter_leiste("/")
        self.assertIn("<span class='marke' title='Wingfoilscout " + __version__, leiste)
        self.assertIn("<img src='/logo.png' alt='DARK' height='26'>", leiste)
        self.assertIn(f"<span class='version'>v{__version__}</span>", leiste)
        # Ganz rechts bleibt „Beenden“ (1.18.2); die Marke steht davor
        self.assertLess(leiste.index("class='marke'"), leiste.index("id='quit'"))
        self.assertEqual(leiste.count("class='marke'"), 1)

    def test_die_datei_liegt_in_web(self):
        self.assertTrue(LOGO.exists())
        self.assertEqual(LOGO.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertLess(LOGO.stat().st_size, 60_000, "klein genug, um in jedem Report zu stecken")
        self.assertIn("/logo.png", w.BILD_DATEIEN)

    def test_nummer_unter_dem_logo_sprache_daneben(self):
        """Seit der Hilfe in der App (das „?“ in der Leiste): Logo und Nummer
        bilden die Marke, die Sprache steht daneben — in der Leiste stellt das
        CSS die Nummer klein unter das Logo, damit die Leiste in allen vier
        Sprachen eine Zeile bleibt; im Fuß am Handy stehen alle drei in einer
        Reihe."""
        self.assertNotIn("sprachwahl", w.marke())
        leiste = w.reiter_leiste("/")
        self.assertLess(leiste.index("class='marke'"), leiste.index("class='sprachwahl'"))
        self.assertLess(leiste.index("class='sprachwahl'"), leiste.index("class='hilfeknopf'"))
        self.assertLess(leiste.index("class='hilfeknopf'"), leiste.index("id='quit'"))
        fuss = w.seitenende()
        self.assertLess(fuss.index("class='marke'"), fuss.index("class='sprachwahl'"))
        reiter = (WEB / "reiter.css").read_text(encoding="utf-8")
        regel = re.search(r"\.reiter \.marke\{([^}]*)\}", reiter).group(1)
        self.assertIn("flex-direction:column", regel)

    def test_marke_nennt_die_laufende_version(self):
        """Die Nummer in der Marke ist die des Prozesses; liegt auf der Platte
        eine neuere, sagt das der Neustart-Hinweis — nicht die Marke."""
        self.assertRegex(w.marke(), r">v\d+\.\d+\.\d+</span>")
        alt = w.__version__
        w.__version__ = "9.9.9"
        try:
            self.assertIn(">v9.9.9</span>", w.marke())
            self.assertIn("title='Wingfoilscout 9.9.9 ", w.marke())
            self.assertIn("läuft noch mit Version 9.9.9", w.neustart_hinweis())
        finally:
            w.__version__ = alt
        self.assertEqual(w.neustart_hinweis(), "")


class Fuss(unittest.TestCase):
    """Jede Seite der Oberfläche endet mit dem Fuß (`seitenende()`), innerhalb
    des `.wrap` — am Handy die einzige Stelle für Logo und Version."""

    @classmethod
    def setUpClass(cls):
        from wingscout.spots import load_spots, KatalogFehler
        cfg = load_cfg()
        spots = load_spots(str(SPOTS))
        home = cfg["rider"]["home"]
        eintraege, _ = w.pruef_liste(home)
        cls.SEITEN = {
            "suche": lambda: w.page(cfg, w.form_defaults(cfg)),
            "katalog": lambda: w.katalog_page(spots, home),
            "pruefen": lambda: w.pruef_page(eintraege, home),
            "rueckblick": lambda: w.rueckblick_page(cfg, None, None, 2, {}),
            "tagebuch": lambda: w.tagebuch_page(cfg, spots),
            "kein_report": lambda: w.kein_report_page(),
            "fehler": lambda: w.fehler_page(KatalogFehler("x")),
            "hilfe": lambda: w.hilfe_page(),
            "rechnung": lambda: w.rechnung_page(),
        }

    def test_fuss_auf_jeder_seite(self):
        for name, bauen in self.SEITEN.items():
            with self.subTest(seite=name):
                seite = bauen()
                self.assertEqual(seite.count("<footer class='seitenfuss'>"), 1)
                fuss = seite.index("<footer class='seitenfuss'>")
                # Leiste oben, Fuß unten — beide mit der Marke, sonst nirgends
                self.assertEqual(seite.count("class='marke'"), 2, name)
                self.assertLess(seite.index("<nav class='reiter'>"), fuss)
                # Der Fuß steht noch im .wrap: nach ihm schließt das div, dann
                # kommen die Skripte, dann ist Schluss
                rest = seite[fuss:]
                self.assertRegex(rest, r"</footer></div><script nonce='[A-Za-z0-9_-]+'>")
                self.assertTrue(seite.rstrip().endswith("</body></html>"))
                self.assertIn(f"v{__version__}", seite)

    def test_unterzeile_der_suchseite_ohne_nummer(self):
        """Bis 1.19.0 stand „v1.x“ in der Unterzeile; jetzt steht die Nummer in
        der Leiste direkt darüber — zweimal auf einem Bildschirm wäre doppelt."""
        cfg = load_cfg()
        seite = w.page(cfg, w.form_defaults(cfg))
        sub = re.search(r'<p class="sub">(.*?)</p>', seite).group(1)
        self.assertNotIn("v" + __version__, sub)
        self.assertIn("Spots im Katalog", sub)

    def test_report_ueber_den_server_hat_die_marke_in_der_leiste(self):
        aus = w.report_mit_reitern(
            b"<html><head></head><body><div class='wrap'><h1>R</h1></div></body></html>").decode("utf-8")
        self.assertEqual(aus.count("class='marke'"), 1)
        self.assertIn("src='/logo.png'", aus)


class Auslieferung(unittest.TestCase):
    """Das Bild kommt vom eigenen Server (`img-src 'self'`); die Liste der
    Bilddateien ist fest — web/ ist kein freigegebenes Verzeichnis."""

    @classmethod
    def setUpClass(cls):
        w.Handler.cfg_path = str(CONFIG)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), w.Handler)
        w.SERVER["instance"] = cls.server
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _get(self, pfad):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{pfad}", timeout=5) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def test_logo_kommt_als_png(self):
        status, kopf, body = self._get("/logo.png")
        self.assertEqual(status, 200)
        self.assertEqual(kopf.get("Content-Type"), "image/png")
        self.assertEqual(kopf.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(body, LOGO.read_bytes())

    def test_nur_die_genannten_dateien(self):
        for pfad in ("/logo.PNG", "/Logo.png", "/basis.css", "/mobil.js", "/web/logo.png", "/logo.png/"):
            with self.subTest(pfad=pfad):
                self.assertEqual(self._get(pfad)[0], 404)

    def test_richtlinie_laesst_das_bild_zu(self):
        """Vom Server (`'self'`) und eingebettet im Report (`data:`)."""
        from wingscout import csp
        img = [t for t in csp.richtlinie("n" * 22).split("; ") if t.startswith("img-src ")][0]
        self.assertIn("'self'", img)
        self.assertIn("data:", img)
        status, kopf, _ = self._get("/")
        self.assertIn("img-src 'self' data:", kopf.get("Content-Security-Policy"))


class Report(unittest.TestCase):
    """Die Report-Datei wird ohne Server geöffnet (AirDrop, `file://`) — das
    Logo steckt deshalb als Data-URI darin, unter dem Fuß, mit der Nummer."""

    def test_logo_eingebettet(self):
        from wingscout import report
        self.assertTrue(report.LOGO_DATA.startswith("data:image/png;base64,"))
        self.assertEqual(base64.b64decode(report.LOGO_DATA.split(",", 1)[1]), LOGO.read_bytes())

    def test_marke_unter_dem_fuss(self):
        from tests.test_report_cli import demo_report
        from wingscout import report
        with tempfile.TemporaryDirectory() as d:
            html_text = demo_report(Path(d))
        marke = f"<p class='marke'><img src='{report.LOGO_DATA}' alt='DARK' height='26'>Wingfoilscout {__version__}</p>"
        self.assertEqual(html_text.count(marke), 1)
        self.assertLess(html_text.index("</footer>"), html_text.index(marke))
        # Kein zweites Logo (die Leiste des Servers kommt erst bei der Auslieferung dazu)
        self.assertNotIn("/logo.png", html_text)


class Stil(unittest.TestCase):
    """Wo die Marke zu sehen ist, entscheidet das CSS: am Rechner in der
    Leiste, am Handy im Fuß — nie an beiden Stellen."""

    def test_regeln(self):
        reiter = (WEB / "reiter.css").read_text(encoding="utf-8")
        basis = (WEB / "basis.css").read_text(encoding="utf-8")
        report = (WEB / "report.css").read_text(encoding="utf-8")
        self.assertIn(".reiter .marke{margin-left:auto", reiter)
        handy = reiter[reiter.index("@media (max-width:700px)"):]
        self.assertIn(".reiter .marke{display:none}", handy)
        self.assertIn(".seitenfuss{display:none}", basis)
        handy = basis[basis.index("@media (max-width:700px)"):]
        self.assertIn(".seitenfuss{display:flex", handy)
        # Im Report: p.marke, nicht .marke — über den Server trägt er auch die Leiste
        self.assertIn("p.marke{", report)
        self.assertNotRegex(report, r"(?<![.\w])\.marke\{")
        # Ein Maß überall
        for css in (reiter, basis, report):
            self.assertIn("height:26px;width:auto", css)


if __name__ == "__main__":
    unittest.main()
