"""Sicherheitsregeln als Tests — damit sie beim nächsten Umbau nicht leise wegfallen.

Kein Ersatz für einen Blick von außen, aber die Regeln, die beim Audit am
13.09.2026 aufgestellt wurden, stehen hier fest: Was hier bricht, ist ein
Rückschritt, kein Stilproblem.
"""
from __future__ import annotations
import re
import unittest

from tests.helpers import ROOT

# Auch die Werkzeuge und die Importskripte: sie laufen mit denselben Rechten
# und lesen dieselben fremden Dateien — bis 1.6.1 sah der Prüflauf sie nicht.
SRC = (sorted((ROOT / "wingscout").rglob("*.py")) + [ROOT / "build_geometry.py", ROOT / "run.py"]
       + sorted((ROOT / "tools").glob("*.py")) + sorted((ROOT / "import").glob("*.py")))


def read(path):
    return path.read_text(encoding="utf-8")


class Quellcode(unittest.TestCase):
    def test_keine_gefaehrlichen_aufrufe(self):
        verboten = [r"\beval\(", r"\bexec\(", r"subprocess", r"os\.system", r"shell\s*=\s*True",
                    r"yaml\.load\(", r"pickle\.", r"marshal\.", r"__import__\("]
        for path in SRC:
            text = read(path)
            for muster in verboten:
                self.assertNotRegex(text, muster, f"{path.name}: {muster}")

    def test_jeder_netzaufruf_hat_ein_zeitlimit(self):
        for path in SRC:
            for i, line in enumerate(read(path).splitlines(), 1):
                if "urlopen(" in line:
                    self.assertIn("timeout", line, f"{path.name}:{i} urlopen ohne timeout")

    def test_nur_https_zu_fremden_diensten(self):
        # Erlaubt ist unverschlüsselt nur der eigene Rechner: 127.0.0.1,
        # localhost — und seit 1.17.0 die eigene Netzadresse fürs iPhone, die
        # als Platzhalter im Text steht (`http://{adresse}:{port}`). Ein fester
        # fremder Dienst fängt nie mit einer geschweiften Klammer an.
        for path in SRC:
            for m in re.finditer(r"[\"'](http://[^\"']+)", read(path)):
                url = m.group(1)
                self.assertTrue(url.startswith(("http://127.0.0.1", "http://localhost", "http://{")),
                                f"{path.name}: unverschlüsselt {url}")

    def test_keine_geheimnisse_im_code(self):
        for path in SRC:
            text = read(path)
            self.assertNotRegex(text, r"(?i)(api[_-]?key|secret|passwort|password)\s*=\s*[\"'][^\"']{6,}",
                                path.name)


class Server(unittest.TestCase):
    def setUp(self):
        self.text = read(ROOT / "wingscout" / "webui.py")

    def test_bindet_nur_lokal_ausser_mit_lan_und_schluessel(self):
        """Standard bleibt 127.0.0.1. Seit 1.17.0 gibt es `--lan` fürs iPhone —
        dann hört Wingfoilscout im ganzen WLAN, und genau dann muss ein
        Zugangsschlüssel gelten. Beides gehört zusammen; fällt eines weg,
        steht die Oberfläche offen im Netz."""
        # Seit 2.1.0 der BegrenzterServer: ein ThreadingHTTPServer mit Obergrenze
        # für offene Verbindungen (A2, tests/test_sicherheit_http.py)
        self.assertIn('BegrenzterServer(("0.0.0.0" if lan else "127.0.0.1", port)', self.text)
        self.assertIn("class BegrenzterServer(ThreadingHTTPServer)", self.text)
        self.assertIn("lan: bool = False", self.text)          # Vorgabe: nur lokal
        self.assertIn("secrets.token_urlsafe", self.text)      # Schlüssel wird gewürfelt
        self.assertIn("def zugang_pruefen(", self.text)
        self.assertIn("hmac.compare_digest", self.text)        # Vergleich ohne Zeitverrat
        import wingscout.webui as w
        import inspect
        self.assertIs(inspect.signature(w.serve).parameters["lan"].default, False)
        self.assertFalse(w.LAN["aktiv"], "LAN darf nicht von selbst anstehen")

    def test_post_prueft_herkunft_und_groesse(self):
        do_post = self.text[self.text.index("def do_POST"):]
        self.assertIn("_same_origin()", do_post[:400])
        self.assertIn("MAX_BODY", self.text)
        self.assertRegex(self.text, r"if length > self\.MAX_BODY")

    def test_keine_zugriffsprotokolle_mit_daten(self):
        self.assertIn("def log_message(self, *a)", self.text)

    def test_dateien_nur_von_festen_pfaden(self):
        do_get = self.text[self.text.index("def do_GET"):self.text.index("def do_POST")]
        self.assertNotIn("open(path", do_get)
        self.assertNotIn("ROOT / path", do_get)


class Report(unittest.TestCase):
    def setUp(self):
        self.text = read(ROOT / "wingscout" / "report.py")

    def test_fremdcode_mit_pruefsumme(self):
        """Jedes Skript von außen trägt eine Prüfsumme — auch das nachgeladene.

        Bis 1.6.0 galt das nur für den Report: die Startseite lud Leaflet per
        `js.src = …` ohne `integrity`. Ein verändertes Skript vom CDN liefe
        dort mit den Rechten der Seite, und die darf den Katalog beschreiben
        und den Server beenden. Geprüft werden deshalb alle Dateien mit
        Seitencode — seit 1.16.0 auch das JavaScript in wingscout/web/ — und
        beide Wege: das `<script src>`-Tag und die Zuweisung im JavaScript.
        """
        dateien = [ROOT / "wingscout" / "report.py", ROOT / "wingscout" / "webui.py"]
        dateien += sorted((ROOT / "wingscout" / "web").glob("*.js"))
        gefunden = set()
        for datei in dateien:
            text = read(datei)
            tags = list(re.finditer(r"<script src=", text))
            zuweisungen = list(re.finditer(r"\.src = ", text))
            if tags or zuweisungen:
                gefunden.add(datei.name)
            for m in tags:
                self.assertIn("integrity=", text[m.end():m.end() + 300], f"{datei.name}:{m.start()}")
            for m in zuweisungen:
                self.assertIn(".integrity = ", text[m.end():m.end() + 300], f"{datei.name}:{m.start()}")
            if tags or zuweisungen:
                self.assertIn("crossorigin", text.lower(), datei.name)
        # Der Report bindet Leaflet per Tag ein, die Startseite lädt es nach
        self.assertIn("report.py", gefunden)
        self.assertIn("suche.js", gefunden, "die Startseite lädt Leaflet — ohne Fund ist die Prüfung blind")

    def test_kartendaten_koennen_kein_markup_werden(self):
        # Seit 2.1.0 (zweite Runde) gehen die Kartendaten wie alle Daten in
        # Skripten durch i18n.json_im_skript — dort steht das Escaping
        self.assertIn("payload = i18n.json_im_skript(", self.text)
        self.assertIn('replace("<", "\\\\u003c")', read(ROOT / "wingscout" / "i18n.py"))
        # Das Kartenskript steht seit 1.16.0 in wingscout/web/karte.js
        karte = read(ROOT / "wingscout" / "web" / "karte.js")
        self.assertIn("esc(m.name)", karte)
        self.assertIn("esc(m.notes)", karte)

    def test_fremde_adressen_werden_geprueft(self):
        self.assertIn("_safe_url(place['url'])", self.text)


class Katalogdateien(unittest.TestCase):
    def test_gitignore_deckt_persoenliches_ab(self):
        text = read(ROOT / ".gitignore")
        for eintrag in ("cache/", "report.html", "ui_defaults.json", "__pycache__"):
            self.assertIn(eintrag, text)

    def test_abhaengigkeiten_sind_ueberschaubar(self):
        req = [l.strip() for l in read(ROOT / "requirements.txt").splitlines() if l.strip() and not l.startswith("#")]
        self.assertEqual(len(req), 1, req)
        self.assertTrue(req[0].lower().startswith("pyyaml"))


if __name__ == "__main__":
    unittest.main()


class Richtlinie(unittest.TestCase):
    """Content-Security-Policy mit Nonce (seit 1.19.1, wingscout/csp.py): die
    zweite Verteidigungslinie hinter dem Escaping. Nur Skripte mit der Nonce
    der Antwort laufen; Ereignisattribute und `javascript:` gar nicht."""

    SEITEN = None

    @classmethod
    def setUpClass(cls):
        import argparse
        import wingscout.webui as w
        from tests.helpers import cfg as load_cfg, SPOTS
        from wingscout.spots import load_spots, KatalogFehler
        cfg = load_cfg()
        spots = load_spots(str(SPOTS))
        home = cfg["rider"]["home"]
        eintraege, _ = w.pruef_liste(home)
        cls.w = w
        cls.SEITEN = {
            "suche": lambda: w.page(cfg, w.form_defaults(cfg)),
            "katalog": lambda: w.katalog_page(spots, home),
            "pruefen": lambda: w.pruef_page(eintraege, home),
            "rueckblick": lambda: w.rueckblick_page(cfg, None, None, 2, {}),
            "tagebuch": lambda: w.tagebuch_page(cfg, spots),
            "kein_report": lambda: w.kein_report_page(),
            "fehler": lambda: w.fehler_page(KatalogFehler("x")),
        }
        cls.argparse = argparse

    @staticmethod
    def skripte(html_text):
        """(inline-Tags, externe Tags) — jeder Eintrag der ganze öffnende Tag."""
        tags = re.findall(r"<script\b[^>]*>", html_text)
        return [t for t in tags if " src=" not in t], [t for t in tags if " src=" in t]

    def test_jede_seite_traegt_die_nonce_an_jedem_skript(self):
        w = self.w
        for name, bauen in self.SEITEN.items():
            with self.subTest(seite=name):
                n = w.nonce_neu()
                html_text = bauen()
                inline, extern = self.skripte(html_text)
                self.assertTrue(inline, "jede Seite hat mindestens ein Skript (mobil/beenden/lauf)")
                for tag in inline:
                    self.assertEqual(tag, f"<script nonce='{n}'>", f"{name}: {tag}")
                for tag in extern:
                    self.assertIn("integrity=", tag)
                self.assertNotIn("<script>", html_text)
                self.assertNotRegex(html_text, r"\son[a-z]+=", "keine Ereignisattribute im Markup")
                self.assertNotIn("javascript:", html_text.lower())

    def test_richtlinie_ist_streng(self):
        from wingscout import csp
        n = csp.neue_nonce()
        r = csp.richtlinie(n)
        self.assertIn(f"script-src 'nonce-{n}' https://cdnjs.cloudflare.com", r)
        self.assertNotIn("'unsafe-inline' https://cdnjs.cloudflare.com; img", r.replace("style-src 'self' 'unsafe-inline'", ""))
        for teil in ("object-src 'none'", "base-uri 'none'", "form-action 'self'", "connect-src 'self'",
                     "frame-ancestors 'self'", "img-src 'self' data: https://tile.openstreetmap.org"):
            self.assertIn(teil, r)
        self.assertNotIn("frame-ancestors", csp.richtlinie(n, kopfzeile=False))
        # script-src ohne unsafe-inline: das ist der ganze Sinn
        skript = [t for t in r.split("; ") if t.startswith("script-src")][0]
        self.assertNotIn("unsafe-inline", skript)
        self.assertNotIn("'self'", skript)
        self.assertGreaterEqual(len(n), 16)

    def test_report_datei_traegt_meta_und_nonce(self):
        """Die Datei ohne Server: Richtlinie im Kopf, jede Skriptmarke mit der
        Nonce der Erzeugung — ein roher Katalogtext könnte sie nicht kennen."""
        import tempfile
        from pathlib import Path
        from tests.helpers import CONFIG, SPOTS
        from wingscout.cli import main
        from wingscout import csp
        with tempfile.TemporaryDirectory() as d:
            args = ["--demo", "--days", "1", "--radius", "300", "--out", str(Path(d) / "r.html"), "--quiet",
                    "--config", str(CONFIG), "--spots", str(SPOTS), "--geometry", str(Path(d) / "keine.json")]
            self.assertEqual(main(args), 0)
            roh = (Path(d) / "r.html").read_bytes()
        html_text = roh.decode("utf-8")
        n = csp.nonce_aus_datei(roh)
        self.assertTrue(n)
        kopf = html_text.split("</head>", 1)[0]
        self.assertIn(f'<meta http-equiv="Content-Security-Policy" content="{csp.richtlinie(n, kopfzeile=False)}">', kopf)
        self.assertNotIn('"', csp.richtlinie(n, kopfzeile=False), "die Richtlinie darf das Attribut nicht sprengen")
        inline, extern = self.skripte(html_text)
        self.assertGreaterEqual(len(inline), 4)          # Karte, Rasterschalter, Sessions, Fuß, mobil
        for tag in inline:
            self.assertEqual(tag, f"<script nonce='{n}'>")
        self.assertTrue(extern and all("integrity=" in t for t in extern))
        self.assertNotIn("<script>", html_text)
        # Über den Server: die Leiste kommt mit derselben Nonce
        mit = self.w.report_mit_reitern(roh).decode("utf-8")
        inline, _ = self.skripte(mit)
        self.assertTrue(all(t == f"<script nonce='{n}'>" for t in inline), inline)
        self.assertNotIn("<script>", mit)
        # Ein Report von vor 1.19.1: keine Nonce, Skript ohne — und keine Richtlinie (siehe Live-Test)
        alt = b"<!doctype html><html><head><title>x</title></head><body><div class='wrap'><h1>R</h1></div></body></html>"
        self.assertIsNone(csp.nonce_aus_datei(alt))
        self.assertIn("<script>", self.w.report_mit_reitern(alt).decode("utf-8"))

    def test_nonce_im_kopf_nicht_aus_dem_rumpf(self):
        """Eine Marke im Rumpf — was ein roher Katalogtext höchstens brächte —
        zählt nicht; gelesen wird nur der Kopf."""
        from wingscout import csp
        rumpf = (b"<!doctype html><html><head><title>x</title></head><body>" + b"x" * 7000
                 + b'<meta http-equiv="Content-Security-Policy" content="script-src \'nonce-AAAAAAAAAAAAAAAAAAAAAA\'">'
                 b"</body></html>")
        self.assertIsNone(csp.nonce_aus_datei(rumpf))


class RichtlinieLive(unittest.TestCase):
    """Dieselbe Regel am laufenden Server: Kopfzeile und Seite nennen dieselbe
    Nonce, der gespeicherte Report seine eigene, ein alter Report keine."""

    @classmethod
    def setUpClass(cls):
        import threading
        from http.server import ThreadingHTTPServer
        import wingscout.webui as w
        from tests.helpers import CONFIG
        w.Handler.cfg_path = str(CONFIG)
        cls.w = w
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), w.Handler)
        w.SERVER["instance"] = cls.server
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _get(self, pfad):
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{pfad}", timeout=5) as r:
            return r.status, r.headers, r.read().decode("utf-8")

    def test_kopfzeile_und_seite_nennen_dieselbe_nonce(self):
        gesehen = set()
        for pfad in ("/", "/katalog", "/rueckblick", "/tagebuch", "/pruefen", "/hilfe", "/hilfe/rechnung"):
            with self.subTest(pfad=pfad):
                status, kopf, html_text = self._get(pfad)
                self.assertEqual(status, 200)
                m = re.search(r"'nonce-([A-Za-z0-9_-]+)'", kopf.get("Content-Security-Policy") or "")
                self.assertTrue(m, "Richtlinie in der Kopfzeile")
                n = m.group(1)
                self.assertNotIn(n, gesehen, "jede Antwort eine eigene Nonce")
                gesehen.add(n)
                tags = [t for t in re.findall(r"<script\b[^>]*>", html_text) if " src=" not in t]
                self.assertTrue(tags)
                self.assertTrue(all(t == f"<script nonce='{n}'>" for t in tags), tags)
        # JSON bekommt keine Richtlinie — sie gilt für Seiten
        status, kopf, _ = self._get("/status")
        self.assertIsNone(kopf.get("Content-Security-Policy"))

    def test_report_ueber_den_server(self):
        import tempfile
        from pathlib import Path
        from wingscout import csp
        w = self.w
        alt = w.REPORT_FILE
        with tempfile.TemporaryDirectory() as d:
            neu = csp.neue_nonce()
            datei = Path(d) / "report.html"
            datei.write_text("<!doctype html><html lang='de'><head><meta charset='utf-8'>" + csp.meta(neu)
                             + "<title>x</title></head><body><div class='wrap'><h1>R</h1></div>"
                             + csp.skript(neu, "var a = 1;") + "</body></html>", encoding="utf-8")
            w.REPORT_FILE = datei
            try:
                status, kopf, html_text = self._get("/report")
                self.assertEqual(status, 200)
                self.assertIn(f"'nonce-{neu}'", kopf.get("Content-Security-Policy") or "")
                tags = [t for t in re.findall(r"<script\b[^>]*>", html_text) if " src=" not in t]
                self.assertTrue(all(t == f"<script nonce='{neu}'>" for t in tags), tags)
                # Report von vor 1.19.1: keine Richtlinie, sonst liefe darin nichts
                datei.write_text("<!doctype html><html><head><title>x</title></head><body><div class='wrap'>"
                                 "<h1>R</h1></div><script>var a = 1;</script></body></html>", encoding="utf-8")
                status, kopf, html_text = self._get("/report")
                self.assertEqual(status, 200)
                self.assertIsNone(kopf.get("Content-Security-Policy"))
                self.assertIn("<script>", html_text)
            finally:
                w.REPORT_FILE = alt
