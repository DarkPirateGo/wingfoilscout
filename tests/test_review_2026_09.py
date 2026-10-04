"""Die Befunde des Reviews vom 25.09.2026 (REVIEW.md, Stand 1.18.3) — jeder
als Test, der den alten Fehler nachstellt und den neuen Stand festhält.
Sicherheit S1–S14 und die Bedienungsbefunde, die sich ohne Browser prüfen
lassen."""
from __future__ import annotations
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import yaml

from tests.helpers import CONFIG, SPOTS
from wingscout import report, spotedit, tide
from wingscout.spots import load_spots, KatalogFehler, sektoren_normieren, koordinate_pruefen
import wingscout.webui as w


def _katalog(tmp: Path, spots: list) -> Path:
    pfad = tmp / "spots.yaml"
    pfad.write_text(yaml.safe_dump(spots, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return pfad


MEER = {"id": "poc", "name": "PoC Strand", "country": "NL", "lat": 51.75, "lon": 3.85,
        "water_body": "sea", "verified": True}


class S1_ReportEscaping(unittest.TestCase):
    """S1: `sectors[].water` stand roh in Klasse und Text der Wasser-Plakette."""

    def test_wasserplakette_escaped_und_whitelist(self):
        boese = "chop'><img src=x onerror=alert(1)>"
        html = report._wasser_pill(boese)
        self.assertNotIn("<img", html)
        self.assertIn("class='pill p-chop'", html)                 # Klasse nur aus der Liste
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)
        self.assertEqual(report._wasser_pill("flat"), "<span class='pill p-flat'>flach</span>")

    def test_katalog_lehnt_fremde_werte_ab(self):
        with self.assertRaises(KatalogFehler) as cm:
            sektoren_normieren("x", [{"from": 200, "to": 320, "quality": "good", "water": "chop'><b>"}])
        self.assertIn("water", str(cm.exception))
        with self.assertRaises(KatalogFehler):
            sektoren_normieren("x", [{"from": 200, "to": 320, "quality": "super"}])
        with self.assertRaises(KatalogFehler):
            sektoren_normieren("x", [{"from": "200", "to": 320}])
        with self.assertRaises(KatalogFehler):
            sektoren_normieren("x", "N-W")
        self.assertEqual(sektoren_normieren("x", None), [])
        norm = sektoren_normieren("x", [{"from": 200, "to": 320, "quality": " Good ", "water": "FLAT"}])
        self.assertEqual((norm[0]["quality"], norm[0]["water"]), ("good", "flat"))

    def test_boeser_sektor_kommt_nicht_in_den_report(self):
        """Der ganze Weg: Katalog → Demo-Lauf → Report. Ein Sektor mit Markup
        im Wasserfeld wird schon beim Laden abgewiesen; ein Report, der dennoch
        einen Fremdwert bekäme, escaped ihn."""
        from wingscout.cli import main
        with tempfile.TemporaryDirectory() as d:
            spot = dict(MEER, sectors=[{"from": 200, "to": 320, "quality": "good",
                                        "water": "chop'><img src=x onerror=alert(1)>"}])
            pfad = _katalog(Path(d), [spot])
            with self.assertRaises(SystemExit) as cm:
                main(["--demo", "--days", "1", "--radius", "900", "--no-geo", "--spots", str(pfad),
                      "--config", str(CONFIG), "--out", str(Path(d) / "r.html"), "--quiet",
                      "--geometry", str(Path(d) / "keine.json")])
            self.assertIn("Sektor water", str(cm.exception))
            self.assertFalse((Path(d) / "r.html").exists())


class S2_HostAufGET(unittest.TestCase):
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

    def _get(self, pfad, host=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{pfad}")
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_fremder_host_liest_nichts(self):
        """DNS-Rebinding: ein fremder Name, der auf 127.0.0.1 zeigt, bekam bis
        1.18.3 Katalog, Tagebuch und Heimatkoordinate — POST war zu, GET nicht."""
        for pfad in ("/status", "/", "/katalog", "/tagebuch/daten", "/rueckblick/daten", "/report"):
            code, body = self._get(pfad, host=f"evil.example:{self.port}")
            self.assertEqual(code, 403, pfad)
            self.assertNotIn(b"lat", body)
        code, body = self._get("/status")
        self.assertEqual(code, 200)
        self.assertIn(b"state", body)

    def test_antwort_header(self):
        """S8: kein MIME-Raten, kein Referer nach draußen."""
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/status")
        with urllib.request.urlopen(req, timeout=5) as r:
            self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(r.headers.get("Referrer-Policy"), "no-referrer")
            self.assertEqual(r.headers.get("Cache-Control"), "no-store")
            self.assertEqual(r.headers.get("X-Frame-Options"), "SAMEORIGIN")

    def test_kaputter_katalog_gibt_eine_seite(self):
        """U1: bis 1.18.3 brach die Verbindung wortlos ab; jetzt 500 mit Grund."""
        with tempfile.TemporaryDirectory() as d:
            kopie = Path(d) / "spots.yaml"
            shutil.copy(SPOTS, kopie)
            with kopie.open("a", encoding="utf-8") as fh:
                fh.write('\n- id: kaputt\n  name: "x\n')
            orig = w.SPOTS_FILE
            w.SPOTS_FILE = kopie
            try:
                for pfad in ("/katalog", "/tagebuch", "/tagebuch/daten"):
                    code, body = self._get(pfad)
                    self.assertEqual(code, 500, pfad)
                    text = body.decode("utf-8")
                    self.assertIn("nicht lesbar", text)
                    self.assertIn("Zeile", text)
                    self.assertNotIn(str(Path(d)), text, "kein Dateipfad im Browser")
                    self.assertIn("<nav class='reiter'>", text)
                    self.assertIn("git checkout spots.yaml", text)
            finally:
                w.SPOTS_FILE = orig


class S3_Schluessel(unittest.TestCase):
    def test_nicht_ascii_wird_abgewiesen_statt_zu_werfen(self):
        orig = dict(w.LAN)
        w.LAN.update(aktiv=True, schluessel="abcDEF123", adressen=("192.168.1.5",))
        try:
            self.assertEqual(w.zugang_pruefen("192.168.1.9", "ü", ""), "abweisen")
            self.assertEqual(w.zugang_pruefen("192.168.1.9", "", f"{w.COOKIE}=ü"), "abweisen")
            self.assertEqual(w.zugang_pruefen("192.168.1.9", "abcDEF123", ""), "setzen")
            self.assertEqual(w.zugang_pruefen("192.168.1.9", "", f"{w.COOKIE}=abcDEF123"), "frei")
            self.assertEqual(w.zugang_pruefen("192.168.1.9", "abcDEF12", ""), "abweisen")
        finally:
            w.LAN.update(orig)


class S4_Steuerzeichen(unittest.TestCase):
    def test_set_text_haelt_den_katalog_lesbar(self):
        with tempfile.TemporaryDirectory() as d:
            pfad = _katalog(Path(d), [dict(MEER)])
            for code in list(range(0, 32)) + [127, 0x85, 0x9F]:
                spotedit.set_text(pfad, "poc", "name", f"Spot{chr(code)}X")
                spots = load_spots(str(pfad))
                soll = "Spot\nX" if code in (10, 13) else ("Spot\tX" if code == 9 else "SpotX")   # \r wird zu \n
                self.assertEqual(spots[0]["name"], soll, code)
            self.assertEqual(spotedit.steuerzeichen_raus("a\x01b c"), "ab c")

    def test_yaml_fehler_ist_ein_katalogfehler_mit_zeile(self):
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "spots.yaml"
            pfad.write_text('- id: a\n  name: "Alpha"\n  lat: 51.7\n  lon: 3.8\n- id: b\n  name: "x\n', encoding="utf-8")
            with self.assertRaises(KatalogFehler) as cm:
                load_spots(str(pfad))
            self.assertIn("Zeile", str(cm.exception))
            self.assertIsInstance(cm.exception, ValueError)


class S7_Koordinaten(unittest.TestCase):
    def test_katalog_verlangt_endliche_koordinaten(self):
        for lat, lon in ((float("nan"), 3.8), (float("inf"), 3.8), (95, 3.8), (51.7, 200), ("51.7", 3.8), (True, 3.8)):
            with self.assertRaises(KatalogFehler, msg=(lat, lon)):
                koordinate_pruefen("x", {"lat": lat, "lon": lon})
        koordinate_pruefen("x", {"lat": 51.7, "lon": 3.8})
        koordinate_pruefen("x", {"lat": -90, "lon": 180})


class S11_Spotedit(unittest.TestCase):
    def test_blockskalar_und_einrueckung(self):
        text = ('- id: a\n  name: "Alpha"\n  lat: 51.7\n  lon: 3.8\n  comment: |\n    erste Zeile\n    zweite Zeile\n'
                '\n-   id: b\n    name: "Beta"\n    lat: 52.0\n    lon: 4.0\n')
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "s.yaml"
            pfad.write_text(text, encoding="utf-8")
            spotedit.set_text(pfad, "a", "comment", "neu")
            daten = {x["id"]: x for x in yaml.safe_load(pfad.read_text(encoding="utf-8"))}
            self.assertEqual(daten["a"]["comment"], "neu")
            self.assertEqual(daten["a"]["name"], "Alpha")
            spotedit.set_text(pfad, "a", "comment", "")
            self.assertNotIn("comment", {x["id"]: x for x in yaml.safe_load(pfad.read_text(encoding="utf-8"))}["a"])
            # Vier Leerzeichen Einrückung: der Block landet auf der Ebene des Spots
            spotedit.set_block(pfad, "b", "tide", ["fahrbar: hochwasser", "stunden: 2"])
            daten = {x["id"]: x for x in yaml.safe_load(pfad.read_text(encoding="utf-8"))}
            self.assertEqual(daten["b"]["tide"], {"fahrbar": "hochwasser", "stunden": 2})
            self.assertEqual(daten["b"]["name"], "Beta")
            self.assertTrue(load_spots(str(pfad)))


class S10_Zusatzquellen(unittest.TestCase):
    def test_tide_und_ensemble_vertragen_unlesbares(self):
        ev = tide.extrema({"2026-09-24T00:00": 0.1, "quatsch": 0.5, "2026-09-24T01:00": "x",
                           "2026-09-24T02:00": 0.9, "2026-09-24T03:00": 0.4, "2026-09-24T04:00": None})
        self.assertEqual([e["art"] for e in ev], ["HW"])
        from wingscout.sources.ensemble import window_stats
        self.assertIsNone(window_stats({"time": "x", "members": []}, ["2026-09-24T12:00"], 12, 15))
        stats = window_stats({"time": ["2026-09-24T12:00", "2026-09-24T13:00"],
                              "members": [[14, "x"], "kaputt", [16, 17], [None, None]]},
                             ["2026-09-24T12:00", "2026-09-24T13:00"], 12, 15)
        self.assertEqual(stats["members"], 2)


class S13_Haertung(unittest.TestCase):
    def test_report_wird_atomar_geschrieben(self):
        with tempfile.TemporaryDirectory() as d:
            ziel = Path(d) / "r.html"
            report.write(ziel, "<html>x</html>")
            self.assertEqual(ziel.read_text(encoding="utf-8"), "<html>x</html>")
            self.assertFalse((Path(d) / "r.html.neu").exists())

    def test_config_wird_nur_fuer_den_besitzer_angelegt(self):
        import os
        import stat
        from wingscout.config import ensure_config
        with tempfile.TemporaryDirectory() as d:
            shutil.copy(CONFIG, Path(d) / "config.example.yaml")
            pfad = ensure_config(Path(d) / "config.yaml")
            self.assertTrue(pfad.exists())
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(pfad.stat().st_mode), 0o600)

    def test_instagram_nur_https(self):
        from wingscout.instagram import _sicher
        self.assertEqual(_sicher("http://instagram.com/x"), "")
        self.assertEqual(_sicher("https://www.instagram.com/x"), "https://www.instagram.com/x")

    def test_gitignore_deckt_persoenliches_ab(self):
        from tests.helpers import ROOT
        regeln = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        for datei in ("config.yaml", "tagebuch.json", "modellguete.json", "ui_defaults.json", "report.html"):
            self.assertTrue(any(r.strip().lstrip("/") == datei for r in regeln), datei)

    def test_schluesselkasten_nicht_am_handy(self):
        self.assertIn(".gruppe.nurgross{display:none}", w.REITER_CSS)

    def test_cache_namen_aus_netzantworten_bleiben_im_ordner(self):
        from wingscout.sources import stationen
        for roh, erwartet in (("rws2_../../x_W_a_b.json", "rws2_.._.._x_W_a_b.json"),
                              ("../etc/passwd", "_etc_passwd"), (".versteckt", "versteckt"),
                              ("dwd_01234_now.zip", "dwd_01234_now.zip"),
                              ("knmi_240_2026-09-20_2026-09-22.csv", "knmi_240_2026-09-20_2026-09-22.csv")):
            pfad = stationen._cache_pfad(roh)
            self.assertEqual(pfad.name, erwartet, roh)
            self.assertEqual(pfad.parent, stationen.CACHE_DIR)

    def test_zip_mitglied_wird_vor_dem_entpacken_gemessen(self):
        import zipfile
        from wingscout.sources import stationen
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "t.zip"
            with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("produkt_zehn_x.txt", "STATIONS_ID;MESS_DATUM\n")
            self.assertIn("STATIONS_ID", stationen._zip_text(pfad, "produkt_zehn", "DWD"))
            with self.assertRaises(stationen.StationError):
                stationen._zip_text(pfad, "gibt_es_nicht", "DWD")
            alt = stationen.ZIP_MITGLIED_MAX
            stationen.ZIP_MITGLIED_MAX = 4
            try:
                with self.assertRaises(stationen.StationError):
                    stationen._zip_text(pfad, "produkt_zehn", "DWD")
            finally:
                stationen.ZIP_MITGLIED_MAX = alt

    def test_weiterleitung_nur_auf_https(self):
        from wingscout.sources.netz import _NurHttps
        h = _NurHttps()
        req = urllib.request.Request("https://api.example/x")
        with self.assertRaises(urllib.error.HTTPError):
            h.redirect_request(req, None, 302, "Found", {}, "http://api.example/klartext")
        neu = h.redirect_request(req, None, 302, "Found", {}, "https://api.example/y")
        self.assertEqual(neu.full_url, "https://api.example/y")
        # Zum eigenen Rechner nur, wenn die Anfrage schon dort war (seit 2.1.1,
        # Review 04.10.2026, C8) — ein fremder Dienst leitet nicht dorthin um.
        with self.assertRaises(urllib.error.HTTPError):
            h.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1:8765/katalog")
        lokal_req = urllib.request.Request("http://127.0.0.1:8765/x")
        lokal = h.redirect_request(lokal_req, None, 302, "Found", {}, "http://127.0.0.1:8765/katalog")
        self.assertEqual(lokal.full_url, "http://127.0.0.1:8765/katalog")

    def test_kaputte_konfiguration_ist_ein_konfigfehler(self):
        from wingscout.config import load_config, KonfigFehler
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "config.yaml"
            pfad.write_text('rider:\n  name: "x\n', encoding="utf-8")
            with self.assertRaises(KonfigFehler) as cm:
                load_config(pfad)
            self.assertIn("Zeile", str(cm.exception))


class U3_RasterTipp(unittest.TestCase):
    def test_report_traegt_den_kasten(self):
        """Am Handy gibt es keinen Tooltip — ein Tipp auf die Zelle zeigt den
        Text unter dem Raster (mobil.js), am Rechner der Klick genauso."""
        from wingscout.report import MOBIL_JS, CSS
        self.assertIn("zellinfo", MOBIL_JS)
        self.assertIn("getElementById('hmraster')", MOBIL_JS)
        self.assertIn(".zellinfo{", CSS)
        self.assertIn(".cell.gewaehlt{", CSS)


class S5_XML(unittest.TestCase):
    def test_doctype_hinter_einem_kommentar(self):
        """Die Sperre sah bis 1.18.3 nur die ersten 4000 Zeichen."""
        from wingscout import ingest, xmlsicher
        fill = "<!-- <gpx> " + "x" * 4200 + " -->"
        xml = ('<?xml version="1.0"?>' + fill + '<!DOCTYPE gpx [<!ENTITY a "AAAAAAAAAA">'
               '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]><gpx><wpt lat="51.7" lon="3.8"><name>&b;&b;</name></wpt></gpx>')
        self.assertIsNone(xmlsicher.lesen(xml))
        hits, probleme = ingest.parse_text(xml)
        self.assertEqual(hits, [])
        # Ohne DOCTYPE: unbekannte Entität ist ein Parserfehler, keine Expansion
        self.assertIsNone(xmlsicher.lesen('<gpx><wpt lat="1" lon="2"><name>&b;</name></wpt></gpx>'))
        # Sauberes GPX liest weiter
        gut = '<?xml version="1.0"?><gpx><wpt lat="51.7" lon="3.8"><name>Strand &amp; Meer</name></wpt></gpx>'
        self.assertEqual(ingest.parse_text(gut)[0], [("Strand & Meer", 51.7, 3.8, None)])
        self.assertIsNone(xmlsicher.lesen("<a>" * 10 + "x" * (xmlsicher.MAX_ZEICHEN + 1)))

    def test_meteoalarm_feed_ohne_entitaeten(self):
        from wingscout.sources.meteoalarm import parse_feed
        feed = ('<?xml version="1.0"?><!DOCTYPE feed [<!ENTITY a "AAAA">]>'
                '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>&a;</title></entry></feed>')
        self.assertEqual(parse_feed(feed), [])


class S6_Regex(unittest.TestCase):
    def test_lange_zeile_kostet_keine_sekunden(self):
        import time
        from wingscout import ingest
        zeile = "1°1x" * 20000                       # 80 KB — bis 1.18.3 rund 16 s
        t0 = time.time()
        ingest.DMS_PAIR.search(zeile)
        ingest.parse_line(zeile)
        self.assertLess(time.time() - t0, 0.5)
        # Echte DMS-Zeilen lesen sich weiter
        hits, _ = ingest.parse_text("Strand 51°45'45\"N 3°51'14\"E")
        self.assertEqual(len(hits), 1)
        self.assertAlmostEqual(hits[0][1], 51.7625, places=3)


class S7_ImportKoordinaten(unittest.TestCase):
    def test_nan_und_bereich_fliegen_raus(self):
        from wingscout import ingest
        gpx = ('<?xml version="1.0"?><gpx><wpt lat="nan" lon="3.8"><name>N</name></wpt>'
               '<wpt lat="95" lon="200"><name>R</name></wpt><wpt lat="inf" lon="3.8"><name>I</name></wpt>'
               '<wpt lat="51.7" lon="3.8"><name>OK</name></wpt></gpx>')
        hits, probleme = ingest.parse_text(gpx)
        self.assertEqual([h[0] for h in hits], ["OK"])
        self.assertTrue(any("unbrauchbarer Koordinate" in p for p in probleme), probleme)
        geojson = ('{"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Point",'
                   '"coordinates":{"x":1}},"properties":{"name":"krumm"}},{"type":"Feature","geometry":'
                   '{"type":"Point","coordinates":[3.8,51.7]},"properties":{"name":"gut"}}]}')
        hits, _ = ingest.parse_text(geojson)
        self.assertEqual([h[0] for h in hits], ["gut"])
        kml = ('<kml><Placemark><name>leer</name><Point><coordinates> </coordinates></Point></Placemark>'
               '<Placemark><name>gut</name><Point><coordinates>3.8,51.7,0</coordinates></Point></Placemark></kml>')
        hits, _ = ingest.parse_text(kml)
        self.assertEqual([h[0] for h in hits], ["gut"])
        self.assertFalse(ingest.koordinate_ok("x", 1))
        self.assertTrue(ingest.koordinate_ok(-90, 180))


class S12_Mengen(unittest.TestCase):
    def test_treffer_und_namen_sind_gedeckelt(self):
        from wingscout import ingest
        viele = "\n".join(f"{'N' * 300} {51 + i / 10000:.5f}, {3 + i / 10000:.5f}" for i in range(600))
        hits, probleme = ingest.parse_text(viele)
        self.assertEqual(len(hits), ingest.MAX_TREFFER)
        self.assertTrue(all(len(h[0]) <= ingest.MAX_NAME for h in hits))
        self.assertTrue(any("ersten 500" in p for p in probleme), probleme)
        # Ein Feld über 128 KB in einer CSV: leer statt Absturz
        csv_text = "name,lat,lon\n" + "x" * 200000 + ",51.7,3.8\n"
        self.assertIsInstance(ingest.parse_csv(csv_text), tuple)


if __name__ == "__main__":
    unittest.main()
