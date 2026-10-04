"""Oberfläche: Formular, Seite und ein echter Server auf einem freien Port."""
from __future__ import annotations
import json
import re
import threading
import unittest
import urllib.error
import urllib.request

import yaml
from http.server import ThreadingHTTPServer
from pathlib import Path

from tests.helpers import cfg as load_cfg, CONFIG
import wingscout.webui as w


class Formular(unittest.TestCase):
    def setUp(self):
        self.cfg = load_cfg()
        self.base = w.form_defaults(self.cfg)

    def test_startwerte_aus_konfiguration(self):
        self.assertEqual(self.base["air_min"], self.cfg["weather"]["air_temp_min"])
        self.assertEqual(self.base["start"], "")
        self.assertTrue(self.base["routing"] and self.base["camping"] and self.base["ensemble"])

    def test_unlesbares_faellt_auf_startwert(self):
        v = w.parse_form({"days": ["abc"], "radius": ["-5"], "min_score": ["7"]}, self.base)
        self.assertEqual(v["days"], self.base["days"])
        self.assertEqual(v["radius"], 10.0)                  # Untergrenze
        self.assertEqual(v["min_score"], 0.95)               # Obergrenze

    def test_nan_und_inf_fallen_auf_den_startwert(self):
        """`nan` als Temperaturgrenze schaltete die Prüfung stumm ab: jeder
        Vergleich mit nan ist falsch. `inf` als Radius hob ihn auf."""
        v = w.parse_form({"air_min": ["nan"], "radius": ["inf"], "pref_low": ["-inf"],
                          "gust_bad": ["NaN"]}, self.base)
        self.assertEqual(v["air_min"], self.base["air_min"])
        self.assertEqual(v["radius"], self.base["radius"])
        self.assertEqual(v["pref_low"], self.base["pref_low"])
        self.assertEqual(v["gust_bad"], self.base["gust_bad"])

    def test_gemerkte_startwerte_werden_geprueft(self):
        """ui_defaults.json geht durch dieselbe Prüfung wie das Formular:
        unbekannte Schlüssel fallen weg, Zeichenketten werden Zahlen oder
        Startwert, fehlende Haken behalten ihren Startwert."""
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            datei = Path(d) / "ui_defaults.json"
            datei.write_text(json.dumps({"days": "7", "radius": "\" onmouseover=\"x", "fremd": 1,
                                         "routing": False, "types": ["sea", "quatsch"]}),
                             encoding="utf-8")
            orig = w.DEFAULTS_FILE
            w.DEFAULTS_FILE = datei
            try:
                v = w.form_defaults(self.cfg)
            finally:
                w.DEFAULTS_FILE = orig
        self.assertEqual(v["days"], 7)
        self.assertEqual(v["radius"], self.base["radius"])        # unlesbar → Startwert
        self.assertNotIn("fremd", v)
        self.assertFalse(v["routing"])
        self.assertTrue(v["highres"], "nicht gemerkt → Startwert bleibt")
        self.assertEqual(v["types"], ["sea"])
        html = w.page(self.cfg, v)
        self.assertNotIn("onmouseover", html)

    def test_haken_und_text(self):
        v = w.parse_form({"start": ["  51.7625, 3.854  "], "start_name": ["Dam"], "req_dogs": ["on"],
                          "grass": ["none"], "types": ["sea", "quatsch"]}, self.base)
        self.assertEqual(v["start"], "51.7625, 3.854")
        self.assertTrue(v["req_dogs"])
        self.assertFalse(v["shallow"])                        # nicht gesendet = aus
        self.assertEqual(v["types"], ["sea"])
        self.assertEqual(v["grass"], "none")

    def test_anwendung_auf_konfiguration(self):
        v = dict(self.base, air_min=9, req_dogs=True, min_hours=3.0)
        c = w.apply_to_config(self.cfg, v)
        self.assertEqual(c["weather"]["air_temp_min"], 9)
        self.assertTrue(c["rules"]["require_dogs"])
        self.assertEqual(c["session"]["min_hours"], 3.0)
        self.assertNotEqual(self.cfg["weather"]["air_temp_min"], 9)   # Original unberührt

    def test_argumente(self):
        a = w.make_args(dict(self.base, start="51.7, 3.8", routing=False, camping=False))
        self.assertEqual(a.start, "51.7, 3.8")
        self.assertTrue(a.no_routing and a.no_camping)
        self.assertFalse(a.no_ensemble)


def ohne_sprachteile(html: str) -> str:
    """Die Seite ohne den Vorspann für Übersetzungen (erstes Skript im Kopf,
    seit 2.1.0) und ohne den Sprachumschalter — die Tests hier prüfen den
    Aufbau der Seite, nicht die Sprachmechanik (die prüft tests/test_i18n.py)."""
    html = re.sub(r"<script[^>]*>window\.T=.*?</script>", "", html, count=1, flags=re.S)
    return re.sub(r"<select class='sprachwahl'.*?</select>", "", html, flags=re.S)


class Seite(unittest.TestCase):
    def test_baut_und_ist_sauber(self):
        cfg = load_cfg()
        html = ohne_sprachteile(w.page(cfg, w.form_defaults(cfg)))
        for teil in ('id="start"', 'id="gps"', 'id="pick"', 'id="spots_text"', 'id="addspots"',
                     'id="rungeo"', "id='quit'", 'name="ensemble"', 'name="camping"', 'name="routing"'):
            self.assertIn(teil, html)
        js = re.split(r"<script[^>]*>", html)[1].split("</script>")[0]
        self.assertNotRegex(js, r"\{\{|\}\}")                # keine unaufgelösten Vorlagenklammern
        self.assertNotIn("innerHTML = j.", js)                # Serverdaten nie als HTML einsetzen

    def test_vordergrund_bleibt_schmal(self):
        """Vor den Klappen darf nur die eine Entscheidung stehen: woher, ab wann
        und wie weit.

        Die erste Fassung zeigte vierzig Bedienelemente gleichzeitig. Dieser Test
        hält den Rückbau fest — wer künftig ein Feld nach vorn zieht, muss hier
        vorbeikommen und sich dabei etwas denken. Seit 2.3.0 steht „Ab wann?“
        vorn (Feld und „Jetzt“), ausdrücklich gewünscht am 04.10.2026: der
        Startzeitpunkt gehört zur Entscheidung wie der Startort.
        """
        cfg = load_cfg()
        html = ohne_sprachteile(w.page(cfg, w.form_defaults(cfg)))
        rumpf = re.split(r"<script[^>]*>", html)[0]
        vorn = re.sub(r"<details.*?</details>", "", rumpf, flags=re.S)
        felder = len(re.findall(r"<(?:input|select|textarea)\b", vorn))
        self.assertLessEqual(felder, 3, "zu viele Eingabefelder vor den Klappen")
        self.assertEqual(len(re.findall(r"<button\b", vorn)), 9)
        for klappe in ('id="mehr"', 'id="quellen"', 'id="spots"', 'id="protokoll"'):
            self.assertIn(klappe, rumpf)

    def test_voreinstellungen(self):
        cfg = load_cfg()
        html = w.page(cfg, w.form_defaults(cfg))
        self.assertEqual(len(w.PRESETS), 3)
        for _schluessel, beschriftung, _zeile, tage, naechte, km in w.PRESETS:
            self.assertIn(beschriftung, html)
            self.assertIn(f'data-tage="{tage}" data-naechte="{naechte}" data-radius="{km}"', html)
        # Jede Voreinstellung muss auch abgeglichen werden koennen
        self.assertIn("presetAbgleich", html)

    def test_keine_zeilenumbrueche_in_js_zeichenketten(self):
        """Ein '\\n' in der Vorlage wird zum echten Umbruch und zerreißt das Skript.

        Der Fehler ist zweimal passiert und im Browser nur als weiße Seite
        sichtbar. Ungerade Anzahl nicht entwerteter Anführungszeichen je Zeile
        ist sein Fingerabdruck.
        """
        cfg = load_cfg()
        js = re.split(r"<script[^>]*>", w.page(cfg, w.form_defaults(cfg)))[1].split("</script>")[0]
        for nr, zeile in enumerate(js.splitlines(), 1):
            for zeichen in ("'", '"'):
                offen = len(re.findall(r"(?<!\\)" + zeichen, zeile)) % 2
                self.assertFalse(offen, f"Zeile {nr} lässt {zeichen} offen: {zeile.strip()}")

    def test_erklaerungen_an_den_erklaerungsbeduerftigen_feldern(self):
        """Mindestgüte, Böigkeit und Kabbel-Aversion sagen als Wort nichts."""
        cfg = load_cfg()
        html = w.page(cfg, w.form_defaults(cfg))
        for name in ("min_score", "gust_bad", "chop"):
            self.assertIn(name, w.ERKLAERUNG)
            block = html.split(f'for="{name}"')[1].split("</label>")[0]
            self.assertIn('class="info"', block)
            self.assertIn("infobox", block)
        # Felder ohne Erklärung bekommen kein leeres Symbol
        self.assertNotIn('class="info"', html.split('for="days"')[1].split("</label>")[0])
        self.assertEqual(w.hinweis("days"), "")
        # Der Text wird escaped, nicht roh eingesetzt
        self.assertNotIn("<", w.ERKLAERUNG["chop"])

    def test_version_steht_im_kopf(self):
        from wingscout import __version__
        cfg = load_cfg()
        self.assertIn(f"v{__version__}", w.page(cfg, w.form_defaults(cfg)))

    def test_heimatname_wird_escaped(self):
        cfg = load_cfg()
        cfg["rider"]["home"]["name"] = "<b>x</b>"
        html = w.page(cfg, w.form_defaults(cfg))
        self.assertNotIn("<b>x</b>", html)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)


class Hintergrund(unittest.TestCase):
    """Die drei Hintergrundläufe müssen `running` in jedem Fall verlassen."""

    def _warte(self, sekunden=5.0):
        import time
        ende = time.time() + sekunden
        while time.time() < ende:
            with w.LOCK:
                if w.JOB["state"] != "running":
                    return dict(w.JOB)
            time.sleep(0.05)
        self.fail("JOB steht nach 5 s noch auf „running“")

    def tearDown(self):
        with w.LOCK:
            w.JOB.update(state="idle", error=None, log=[])

    def test_kaputter_katalog_laesst_die_oberflaeche_nicht_haengen(self):
        """Bis 1.6.0 warf load_spots SystemExit; der Worker fing nur Exception,
        der Thread starb still, und jeder Knopf antwortete 409 bis zum Neustart."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            kaputt = Path(d) / "spots.yaml"
            kaputt.write_text("- id: a\n  name: A\n  lat: 1\n  lon: 1\n"
                              "- id: a\n  name: B\n  lat: 2\n  lon: 2\n", encoding="utf-8")
            original = w.SPOTS_FILE
            w.SPOTS_FILE = kaputt
            try:
                w.start_ingest(str(CONFIG), "Test; 49.17, 8.61", False)
                job = self._warte()
            finally:
                w.SPOTS_FILE = original
        self.assertEqual(job["state"], "error")
        self.assertIn("Doppelte Spot-ID", job["error"])

    def test_auch_systemexit_endet_im_fehlerzustand(self):
        """Der zweite Fang: was keine Exception ist, kommt trotzdem an."""
        def arbeit():
            raise SystemExit(3)
        w._starte("run", arbeit)
        job = self._warte()
        self.assertEqual(job["state"], "error")
        self.assertIn("Abbruch", job["error"])

    def test_zwei_starts_zugleich_nur_einer_laeuft(self):
        """Prüfen und Setzen unter einem LOCK — zwei gleichzeitige Anfragen
        sahen bis 1.6.1 beide „frei“ und schrieben beide report.html."""
        import threading
        tor = threading.Event()
        def arbeit():
            tor.wait(3)
            with w.LOCK:
                w.JOB["state"] = "done"
        self.assertTrue(w._starte("run", arbeit))
        self.assertFalse(w._starte("run", arbeit))
        tor.set()
        self._warte()

    def test_kein_start_waehrend_die_pruefseite_schreibt(self):
        with w.LOCK:
            w.PRUEFEN_AKTIV["n"] = 1
        try:
            self.assertFalse(w._starte("ingest", lambda: None))
            with w.LOCK:
                self.assertNotEqual(w.JOB["state"], "running")
        finally:
            with w.LOCK:
                w.PRUEFEN_AKTIV["n"] = 0

    def test_arbeit_ohne_ende_ist_ein_fehler_kein_dauerlauf(self):
        w._starte("ingest", lambda: None)
        job = self._warte()
        self.assertEqual(job["state"], "error")
        self.assertIn("ohne Ergebnis", job["error"])


class LiveServer(unittest.TestCase):
    """Ein echter Server auf einem freien Port, nur für die Sicherheitsregeln."""

    @classmethod
    def setUpClass(cls):
        w.Handler.cfg_path = str(CONFIG)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), w.Handler)
        w.SERVER["instance"] = cls.server
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _post(self, path, body=b"", headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body, method="POST",
                                     headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_seite_und_status(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=5) as r:
            self.assertEqual(r.status, 200)
            self.assertIn(b"Wingfoilscout", r.read())
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/status", timeout=5) as r:
            self.assertIn("state", json.loads(r.read()))

    def test_nicht_von_fremden_seiten_einbettbar(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=5) as r:
            self.assertEqual(r.headers.get("X-Frame-Options"), "SAMEORIGIN")

    def test_unbekannter_pfad(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/../etc/passwd", timeout=5)
        self.assertEqual(cm.exception.code, 404)

    def test_fremde_herkunft_wird_abgewiesen(self):
        code, body = self._post("/shutdown", headers={"Origin": "https://boese-seite.example"})
        self.assertEqual(code, 403)
        code, _ = self._post("/run", headers={"Origin": "http://evil.test"})
        self.assertEqual(code, 403)
        self.assertTrue(self.thread.is_alive())               # Server lebt noch

    def test_falscher_host_wird_abgewiesen(self):
        code, _ = self._post("/run", headers={"Host": "wingscout.attacker.example"})
        self.assertEqual(code, 403)

    def test_eigene_herkunft_ist_erlaubt(self):
        # Ein leerer /save-Aufruf mit passendem Origin geht durch (schreibt nur Standardwerte);
        # hier reicht: kein 403.
        code, _ = self._post("/status", headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertNotEqual(code, 403)

    def test_pruefen_braucht_eigene_herkunft(self):
        """Die Endpunkte schreiben in spots.yaml — CSRF gilt hier erst recht."""
        for pfad in ("/pruefen/setzen", "/pruefen/ok"):
            code, _ = self._post(pfad, body=b'{"id":"x"}',
                                 headers={"Origin": "https://boese-seite.example",
                                          "Content-Type": "application/json"})
            self.assertEqual(code, 403, pfad)

    def test_pruefen_weist_unsinn_ab(self):
        eigen = {"Origin": f"http://127.0.0.1:{self.port}", "Content-Type": "application/json"}
        code, body = self._post("/pruefen/setzen", body=b"kein json", headers=eigen)
        self.assertEqual(code, 400)
        code, body = self._post("/pruefen/setzen", body=b'{"koordinate":"51,3"}', headers=eigen)
        self.assertEqual(code, 400)
        self.assertIn("Kein Spot", json.loads(body)["error"])
        code, body = self._post("/pruefen/setzen",
                                body=b'{"id":"gibt-es-nicht","koordinate":"Buchstaben"}',
                                headers=eigen)
        self.assertEqual(code, 400)
        self.assertIn("nicht lesbar", json.loads(body)["error"])

    def test_pruefseite_wird_ausgeliefert(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/pruefen", timeout=10) as r:
            text = r.read().decode("utf-8")
        self.assertEqual(r.status, 200)
        self.assertIn("Koordinaten prüfen", text)

    def test_passt_so_schreibt_wirklich_in_den_katalog(self):
        """Der Knopf muss die Datei ändern, sonst ist er Dekoration.

        Geprüft wird gegen eine Kopie in einem Temporärordner — der echte
        Katalog bleibt unberührt.
        """
        import shutil
        import tempfile
        from tests.helpers import SPOTS
        with tempfile.TemporaryDirectory() as d:
            kopie = Path(d) / "spots.yaml"
            shutil.copy(SPOTS, kopie)
            original = w.SPOTS_FILE
            w.SPOTS_FILE = kopie
            try:
                erster = yaml.safe_load(kopie.read_text(encoding="utf-8"))[0]
                self.assertNotIn("geo_ok", erster)
                code, body = self._post(
                    "/pruefen/ok",
                    body=json.dumps({"id": erster["id"]}).encode(),
                    headers={"Origin": f"http://127.0.0.1:{self.port}",
                             "Content-Type": "application/json"})
                self.assertEqual(code, 200, body)
                self.assertTrue(json.loads(body)["erledigt"])
                danach = yaml.safe_load(kopie.read_text(encoding="utf-8"))
                # „Passt so" bestätigt die Koordinate. `geo_ok` kommt nur dazu,
                # wenn für diesen Spot auch wirklich eine Geometriewarnung
                # vorliegt — sonst stünde der Vermerk bei hundert Spots ohne
                # Anlass in der Datei.
                self.assertTrue(danach[0]["verified"])
                self.assertEqual(len(danach), len(yaml.safe_load(SPOTS.read_text(encoding="utf-8"))))
                # Der Kopfkommentar der Datei überlebt das Schreiben
                self.assertIn("Wingfoilscout · Spot catalogue", kopie.read_text(encoding="utf-8"))
            finally:
                w.SPOTS_FILE = original

    def test_korrigierte_koordinate_gilt_als_bestaetigt(self):
        """Wer die Nadel selbst setzt, hat hingeschaut — das ist `verified`."""
        import shutil
        import tempfile
        import wingscout.shoreline as sl
        from tests.helpers import SPOTS
        with tempfile.TemporaryDirectory() as d:
            kopie = Path(d) / "spots.yaml"
            shutil.copy(SPOTS, kopie)
            geo = Path(d) / "geometry.json"
            geo.write_text("{}", encoding="utf-8")
            orig_s, orig_g, orig_b = w.SPOTS_FILE, w.GEOMETRY_FILE, sl.build_one
            w.SPOTS_FILE, w.GEOMETRY_FILE = kopie, geo
            # Ohne Netz gäbe es hier sechs Sekunden Wartezeit für nichts.
            sl.build_one = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("kein Netz"))
            try:
                spots = yaml.safe_load(kopie.read_text(encoding="utf-8"))
                # Irgendein Spot — seit alle Koordinaten bestätigt sind (20.09.),
                # gibt es keinen unbestätigten mehr, und der Test darf davon
                # nicht abhängen. Die Kopie bekommt ihn erst einmal unbestätigt.
                ziel = next((x for x in spots if not x.get("verified")), spots[0])
                from wingscout import spotedit
                spotedit.set_flag(kopie, ziel["id"], "verified", False)
                code, body = self._post(
                    "/pruefen/setzen",
                    body=json.dumps({"id": ziel["id"], "koordinate": "51.7369, 3.8285"}).encode(),
                    headers={"Origin": f"http://127.0.0.1:{self.port}",
                             "Content-Type": "application/json"})
                self.assertEqual(code, 200, body)
                danach = {x["id"]: x for x in yaml.safe_load(kopie.read_text(encoding="utf-8"))}
                self.assertTrue(danach[ziel["id"]]["verified"])
                self.assertAlmostEqual(danach[ziel["id"]]["lat"], 51.7369, places=4)
            finally:
                w.SPOTS_FILE, w.GEOMETRY_FILE, sl.build_one = orig_s, orig_g, orig_b

    def test_katalog_pflegen(self):
        """Anlegen, umbenennen, verschieben, löschen — auf Textebene in einer
        Kopie des Katalogs; die Kennung bleibt, Kommentare bleiben, und was
        gelöscht wird, verschwindet auch aus Geometrie und Instagram-Datei."""
        import shutil
        import tempfile
        import wingscout.shoreline as sl
        from wingscout import instagram
        from tests.helpers import SPOTS
        kopf = {"Origin": f"http://127.0.0.1:{self.port}", "Content-Type": "application/json"}
        with tempfile.TemporaryDirectory() as d:
            kopie = Path(d) / "spots.yaml"
            shutil.copy(SPOTS, kopie)
            geo = Path(d) / "geometry.json"
            ig = Path(d) / "instagram.json"
            orig = (w.SPOTS_FILE, w.GEOMETRY_FILE, sl.build_one, instagram.DATEI)
            w.SPOTS_FILE, w.GEOMETRY_FILE, instagram.DATEI = kopie, geo, ig
            sl.build_one = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("kein Netz"))
            try:
                vorher = len(yaml.safe_load(kopie.read_text(encoding="utf-8")))
                # Anlegen — 300 m neben Brouwersdam: erst die Warnung, dann trotzdem
                code, body = self._post("/katalog/neu", body=json.dumps(
                    {"name": "Testspot <b>", "koordinate": "51.7625, 3.8541", "water": "sea", "notes": "Notiz"}).encode(), headers=kopf)
                self.assertEqual(code, 409, body)
                self.assertEqual(json.loads(body)["doppelt"], "brouwersdam")
                code, body = self._post("/katalog/neu", body=json.dumps(
                    {"name": "Testspot <b>", "koordinate": "51.7625, 3.8541", "water": "sea", "notes": "Notiz",
                     "country": "nl", "trotzdem": True, "geometrie": True, "comment": "erster Eindruck"}).encode(), headers=kopf)
                self.assertEqual(code, 200, body)
                neu = json.loads(body)
                self.assertEqual(neu["name"], "Testspot <b>")
                self.assertEqual(neu["country"], "NL")
                self.assertEqual(neu["comment"], "erster Eindruck")
                self.assertIn("ließ sich gerade nicht rechnen", neu["message"])
                spots = {x["id"]: x for x in yaml.safe_load(kopie.read_text(encoding="utf-8"))}
                self.assertEqual(len(spots), vorher + 1)
                self.assertEqual(spots[neu["id"]]["notes"], "Notiz")
                self.assertEqual(spots[neu["id"]]["comment"], "erster Eindruck")
                self.assertTrue(spots[neu["id"]]["verified"])
                # Unlesbare Koordinate, falsches Land
                code, body = self._post("/katalog/neu", body=json.dumps({"name": "x", "koordinate": "nix"}).encode(), headers=kopf)
                self.assertEqual(code, 400)
                code, body = self._post("/katalog/neu", body=json.dumps({"koordinate": "50.0, 8.0", "country": "Deutschland"}).encode(), headers=kopf)
                self.assertEqual(code, 400)
                # Umbenennen: Kennung bleibt, Name in Anführungszeichen, Kommentare bleiben
                code, body = self._post("/katalog/umbenennen", body=json.dumps({"id": neu["id"], "name": "  Neuer  Name "}).encode(), headers=kopf)
                self.assertEqual(code, 200, body)
                spots = {x["id"]: x for x in yaml.safe_load(kopie.read_text(encoding="utf-8"))}
                self.assertEqual(spots[neu["id"]]["name"], "Neuer Name")
                self.assertIn("Wingfoilscout · Spot catalogue", kopie.read_text(encoding="utf-8"))
                code, body = self._post("/katalog/umbenennen", body=json.dumps({"id": neu["id"], "name": ""}).encode(), headers=kopf)
                self.assertEqual(code, 400)
                code, body = self._post("/katalog/umbenennen", body=json.dumps({"id": "gibt-es-nicht", "name": "x"}).encode(), headers=kopf)
                self.assertEqual(code, 400)
                # Verschieben = Übernehmen auf der Prüfseite
                code, body = self._post("/katalog/verschieben", body=json.dumps({"id": neu["id"], "koordinate": "51.7369, 3.8285"}).encode(), headers=kopf)
                self.assertEqual(code, 200, body)
                spots = {x["id"]: x for x in yaml.safe_load(kopie.read_text(encoding="utf-8"))}
                self.assertAlmostEqual(spots[neu["id"]]["lat"], 51.7369, places=4)
                # Kommentar: mehrzeilig, Steuerzeichen raus, leer nimmt ihn weg
                code, body = self._post("/katalog/kommentar", body=json.dumps(
                    {"id": neu["id"], "comment": "  Parken am Ende der Straße.\r\nBei SW super. \x07 <b>x</b>  "}).encode(), headers=kopf)
                self.assertEqual(code, 200, body)
                self.assertEqual(json.loads(body)["comment"], "Parken am Ende der Straße.\nBei SW super.  <b>x</b>")
                spots = {x["id"]: x for x in yaml.safe_load(kopie.read_text(encoding="utf-8"))}
                self.assertEqual(spots[neu["id"]]["comment"], "Parken am Ende der Straße.\nBei SW super.  <b>x</b>")
                code, body = self._post("/katalog/kommentar", body=json.dumps({"id": neu["id"], "comment": "x" * 2001}).encode(), headers=kopf)
                self.assertEqual(code, 400)
                code, body = self._post("/katalog/kommentar", body=json.dumps({"id": neu["id"], "comment": ""}).encode(), headers=kopf)
                self.assertEqual(code, 200, body)
                self.assertNotIn("comment", {x["id"]: x for x in yaml.safe_load(kopie.read_text(encoding="utf-8"))}[neu["id"]])
                code, body = self._post("/katalog/kommentar", body=json.dumps({"id": "gibt-es-nicht", "comment": "x"}).encode(), headers=kopf)
                self.assertEqual(code, 400)
                # Löschen: aus Katalog, Geometrie und Instagram-Datei
                geo.write_text(json.dumps({neu["id"]: {"x": 1}, "brouwersdam": {"x": 2}}), encoding="utf-8")
                ig.write_text(json.dumps({"stand": "2026-09-18", "spots": {neu["id"]: {"funde": [], "urteil": "keine"}}}), encoding="utf-8")
                code, body = self._post("/katalog/loeschen", body=json.dumps({"id": neu["id"]}).encode(), headers=kopf)
                self.assertEqual(code, 200, body)
                spots = {x["id"]: x for x in yaml.safe_load(kopie.read_text(encoding="utf-8"))}
                self.assertNotIn(neu["id"], spots)
                self.assertEqual(len(spots), vorher)
                self.assertEqual(list(json.loads(geo.read_text(encoding="utf-8"))), ["brouwersdam"])
                self.assertEqual(json.loads(ig.read_text(encoding="utf-8"))["spots"], {})
                self.assertIn("Wingfoilscout · Spot catalogue", kopie.read_text(encoding="utf-8"))
                code, body = self._post("/katalog/loeschen", body=json.dumps({"id": neu["id"]}).encode(), headers=kopf)
                self.assertEqual(code, 400)
                # Ohne Herkunft: abgelehnt
                code, body = self._post("/katalog/loeschen", body=json.dumps({"id": "brouwersdam"}).encode(),
                                        headers={"Origin": "http://boese.example", "Content-Type": "application/json"})
                self.assertEqual(code, 403)
                self.assertIn("brouwersdam", {x["id"] for x in yaml.safe_load(kopie.read_text(encoding="utf-8"))})
            finally:
                w.SPOTS_FILE, w.GEOMETRY_FILE, sl.build_one, instagram.DATEI = orig
                instagram._geladen.update(pfad=None, mtime=None, daten={})

    def test_zu_grosse_anfrage(self):
        code, body = self._post("/addspots", headers={"Content-Length": str(50 * 1024 * 1024)})
        self.assertEqual(code, 413)

    def test_negative_laenge_haelt_keinen_thread_fest(self):
        """`Content-Length: -1` hieß bis 1.6.0 `rfile.read(-1)`: lesen bis zum
        Verbindungsende, und das bestimmt der Absender. Der Bearbeitungs-Thread
        hing so lange. Jetzt kommt sofort ein 400 — für Formular und JSON."""
        import socket
        for pfad in ("/status", "/pruefen/ok"):      # /status schreibt nichts, auch wenn es hängt
            s = socket.create_connection(("127.0.0.1", self.port))
            s.settimeout(3)
            try:
                s.sendall(f"POST {pfad} HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                          f"Content-Length: -1\r\n\r\n".encode())
                antwort = s.recv(200).decode(errors="replace")
            except socket.timeout:
                self.fail(f"{pfad}: keine Antwort — der Thread hängt an read(-1)")
            finally:
                s.close()
            self.assertIn(" 400 ", antwort.splitlines()[0], pfad)

    def test_beschaeftigt(self):
        with w.LOCK:
            vorher = w.JOB["state"]
            w.JOB["state"] = "running"
        try:
            code, _ = self._post("/run", body=b"days=1")
            self.assertEqual(code, 409)
            # Die Prüfseite schreibt in dieselben Dateien wie der Lauf — sie
            # wartet, statt dazwischenzuschreiben.
            code, body = self._post("/pruefen/ok", body=b'{"id":"x"}',
                                    headers={"Origin": f"http://127.0.0.1:{self.port}",
                                             "Content-Type": "application/json"})
            self.assertEqual(code, 409)
            self.assertIn("abwarten", json.loads(body)["error"])
        finally:
            with w.LOCK:
                w.JOB["state"] = vorher


class Shutdown(unittest.TestCase):
    def test_belegter_port(self):
        """Ein anderes Programm auf 8765 ließ Wingfoilscout bis 1.18.3 mit „Address
        already in use“ sterben. Jetzt: fremder Server → nächster freier Port;
        laufendes Wingfoilscout → kein zweites, nur die Adresse; frei → wie gehabt."""
        from http.server import BaseHTTPRequestHandler as _BH

        class Fremd(_BH):
            def do_GET(self):
                body = b"<html>ein anderes Programm</html>"
                self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        fremd = ThreadingHTTPServer(("127.0.0.1", 0), Fremd)
        f_port = fremd.server_address[1]
        threading.Thread(target=fremd.serve_forever, daemon=True).start()
        w.Handler.cfg_path = str(CONFIG)
        eigen = ThreadingHTTPServer(("127.0.0.1", 0), w.Handler)
        e_port = eigen.server_address[1]
        threading.Thread(target=eigen.serve_forever, daemon=True).start()
        try:
            self.assertEqual(w.port_belegt_von(f_port), "fremd")
            self.assertEqual(w.port_belegt_von(e_port), "wingscout")
            wahl = w.port_klaeren(f_port)
            self.assertIsNotNone(wahl["port"])
            self.assertNotEqual(wahl["port"], f_port)
            self.assertIn("anderen Programm belegt", wahl["hinweis"])
            self.assertIsNone(w.port_belegt_von(wahl["port"]))
            wahl = w.port_klaeren(e_port)
            self.assertIsNone(wahl["port"])
            self.assertEqual(wahl["laeuft"], f"http://127.0.0.1:{e_port}/")
            self.assertIn("läuft schon", wahl["hinweis"])
        finally:
            fremd.shutdown(); fremd.server_close()
            eigen.shutdown(); eigen.server_close()
        # Danach ist der Port frei — und `serve` würde ihn nehmen
        self.assertIsNone(w.port_belegt_von(f_port))
        self.assertEqual(w.port_klaeren(f_port), {"port": f_port, "hinweis": "", "laeuft": ""})

    def test_beenden_stoppt_den_server(self):
        w.Handler.cfg_path = str(CONFIG)
        server = ThreadingHTTPServer(("127.0.0.1", 0), w.Handler)
        w.SERVER["instance"] = server
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        req = urllib.request.Request(f"http://127.0.0.1:{port}/shutdown", data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            self.assertEqual(r.status, 200)
        t.join(timeout=5)
        self.assertFalse(t.is_alive())
        server.server_close()


if __name__ == "__main__":
    unittest.main()


class Pruefseite(unittest.TestCase):
    """Die Seite, auf der zweifelhafte Koordinaten korrigiert werden.

    Der eigentliche Nutzen steckt im Schreiben nach `spots.yaml` — das wird in
    `test_spotedit.py` geprüft. Hier geht es um die Seite selbst und darum,
    dass ein böser Spotname nicht als Markup durchkommt: die Namen stammen aus
    importierten Listen, also von außen.
    """

    def test_leere_seite_zeigt_nur_den_hinweis(self):
        """Nichts zu prüfen: keine Erklärung von drei Stufen, keine leere Karte,
        kein Leaflet — nur der Satz, dass nichts offen ist."""
        seite = w.pruef_page([], {"lat": 53.55, "lon": 9.99, "name": "Hamburg"})
        self.assertIn("Nichts zu prüfen", seite)
        self.assertNotIn("Unbrauchbar", seite)
        self.assertNotIn("leaflet.min.js", seite)
        self.assertNotIn("id='pmap'", seite)
        self.assertIn("href='/pruefen' class='an'", seite)       # der Reiter bleibt hier stehen
        self.assertIn("viewport-fit=cover", seite)               # Safe Area am iPhone

    def test_ein_einzelner_eintrag_steht_im_singular(self):
        eintrag = [{"id": "a", "name": "A", "lat": 50.0, "lon": 8.0, "stufe": "unbestaetigt",
                    "grund": "Koordinate nie bestätigt", "comment": "", "fetch_km": None}]
        seite = w.pruef_page(eintrag, {"lat": 53.55, "lon": 9.99, "name": "Hamburg"})
        self.assertIn("Ein Spot, der auf der Karte nachgesehen gehört.", seite)
        self.assertIn("id='pmap'", seite)

    def test_seite_baut_und_escaped(self):
        eintraege = [
            {"id": "boese", "name": "<script>alert(1)</script>", "lat": 51.7, "lon": 3.8,
             "stufe": "unbrauchbar", "grund": "höchstens 100 m Wasser", "fetch_km": 0.1},
            {"id": "weit", "name": "Weit weg", "lat": 49.0, "lon": 8.0,
             "stufe": "pruefen", "grund": "2500 m vom Pin versetzt", "fetch_km": 5.0},
        ]
        html_text = w.pruef_page(eintraege, {"lat": 53.55, "lon": 9.99})
        self.assertIn("Koordinaten prüfen", html_text)
        self.assertIn("data-id=\"boese\"", html_text.replace("'", '"'))
        self.assertIn("Weit weg", html_text)
        self.assertNotIn("<script>alert(1)</script>", html_text)
        self.assertIn("&lt;script&gt;", html_text)
        self.assertIn("\\u003cscript\\u003e", html_text)       # auch im JSON entschärft
        js = re.split(r"<script[^>]*>", html_text)[-1].split("</script>")[0]
        for nr, zeile in enumerate(js.splitlines(), 1):
            for zeichen in ("'", '"'):
                self.assertFalse(len(re.findall(r"(?<!\\)" + zeichen, zeile)) % 2,
                                 f"Zeile {nr} lässt {zeichen} offen")

    def test_leere_liste_sagt_das(self):
        html_text = w.pruef_page([], {"lat": 53.55, "lon": 9.99})
        self.assertIn("Nichts zu prüfen", html_text)


class PruefListeUnbestaetigt(unittest.TestCase):
    """Die 103 Spots mit `verified: false` standen nirgends als eine Liste.

    Sie sind kein Fehler, nur eine offene Frage: Die Koordinate stammt aus
    einer importierten Liste, und niemand hat je hingeschaut. Ohne Liste
    arbeitet man so etwas nicht ab.
    """

    HOME = {"lat": 53.55, "lon": 9.99}

    def _mit_katalog(self, spots, geometrie=None):
        import tempfile
        from pathlib import Path as P
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        sp = P(d.name) / "spots.yaml"
        sp.write_text(yaml.safe_dump(spots, allow_unicode=True, sort_keys=False), encoding="utf-8")
        geo = P(d.name) / "geometry.json"
        geo.write_text(json.dumps(geometrie or {}), encoding="utf-8")
        alt_s, alt_g = w.SPOTS_FILE, w.GEOMETRY_FILE
        w.SPOTS_FILE, w.GEOMETRY_FILE = sp, geo
        self.addCleanup(lambda: setattr(w, "SPOTS_FILE", alt_s))
        self.addCleanup(lambda: setattr(w, "GEOMETRY_FILE", alt_g))
        return sp

    def _spot(self, sid, name, lat, lon, verified):
        return {"id": sid, "name": name, "country": "DE", "lat": lat, "lon": lon,
                "water_body": "lake", "shallow": "none", "seagrass": "none",
                "season": list(range(1, 13)), "sectors": [], "verified": verified}

    def test_unbestaetigte_erscheinen_und_zwar_nach_entfernung(self):
        self._mit_katalog([
            self._spot("nah", "Nah", 53.6, 10.1, False),       # ~10 km
            self._spot("fern", "Fern", 45.9, 10.9, False),     # ~850 km
            self._spot("fertig", "Fertig", 53.7, 10.1, True),
        ])
        eintraege, _ = w.pruef_liste(self.HOME)
        ids = [e["id"] for e in eintraege]
        self.assertEqual(ids, ["nah", "fern"], "bestätigte Spots gehören nicht in die Liste")
        self.assertTrue(all(e["stufe"] == "unbestaetigt" for e in eintraege))
        self.assertIn("km Luftlinie", eintraege[0]["grund"])

    def test_ein_spot_steht_nur_einmal_drin(self):
        """Auffällig UND unbestätigt: die Geometriewarnung ist die dringendere."""
        geo = {"kaputt": {"rose_m": [0.0] * 36, "n_dirs": 36, "radius_km": 25,
                          "max_fetch_km": 0.0, "median_fetch_km": 0.0, "open_share": 0.0,
                          "status": "0 km² Fläche", "snapped": True}}
        self._mit_katalog([self._spot("kaputt", "Kaputt", 49.5, 8.7, False)], geo)
        eintraege, _ = w.pruef_liste(self.HOME)
        self.assertEqual(len(eintraege), 1)
        self.assertNotEqual(eintraege[0]["stufe"], "unbestaetigt")

    def test_seite_trennt_die_stufen_und_bietet_einen_filter(self):
        self._mit_katalog([self._spot("a", "Alpha", 49.5, 8.7, False),
                           self._spot("b", "Beta", 49.6, 8.8, False)])
        eintraege, _ = w.pruef_liste(self.HOME)
        html_text = w.pruef_page(eintraege, self.HOME)
        self.assertIn("data-stufe='unbestaetigt'", html_text)
        self.assertIn("class='pfilter'", html_text)
        self.assertIn("Unbestätigt 2", html_text)
        self.assertIn("Alle 2", html_text)
        # Keine Zeile des eingebetteten Skripts lässt eine Zeichenkette offen
        skript = re.split(r"<script[^>]*>", html_text)[-1].split("</script>", 1)[0]
        for zeile in skript.splitlines():
            self.assertEqual(zeile.count("'") % 2, 0, zeile)

    def test_karte_bleibt_stehen_waehrend_die_liste_scrollt(self):
        """Bei 104 Karten muss man sonst jedes Mal hochscrollen.

        Der Haken lag nicht am fehlenden `sticky`, sondern daran, dass es auf
        der Karte selbst stand: ein klebendes Element braucht Platz zum Wandern
        innerhalb seines Elternelements, und das war genauso hoch wie die Karte.
        """
        self._mit_katalog([self._spot("a", "Alpha", 49.5, 8.7, False)])
        eintraege, _ = w.pruef_liste(self.HOME)
        seite = w.pruef_page(eintraege, self.HOME)
        self.assertIn("<div class='pmapsp'>", seite)
        self.assertIn(".pmapsp{position:sticky", seite)
        # Auf der Karte selbst darf es gerade nicht mehr stehen
        regel = seite.split("#pmap{", 1)[1].split("}", 1)[0]
        self.assertNotIn("sticky", regel)
        # Das Raster darf die Spalte nicht auf volle Höhe strecken
        self.assertIn("align-items:start", seite.split(".pspalten{", 1)[1].split("}", 1)[0])


class ReportAlsReiter(unittest.TestCase):
    """Über den Server ist der Report der Reiter „Ziele“ und bekommt die Leiste
    eingesetzt; die Datei selbst bleibt unverändert, weil sie per AirDrop aufs
    iPhone wandert und dort ohne Server geöffnet wird."""

    def test_leiste_wird_eingesetzt(self):
        roh = b"<!doctype html><html><body><h1>Report</h1></body></html>"
        aus = w.report_mit_reitern(roh).decode("utf-8")
        self.assertIn("<nav class='reiter'>", aus)
        self.assertIn("href='/rueckblick'", aus)
        self.assertIn("window.top !== window.self", aus)      # im Rahmen keine Leiste
        self.assertTrue(aus.endswith("</body></html>"))

    def test_beenden_auf_jedem_reiter(self):
        """Der Knopf „Beenden“ sitzt in der Leiste — also auf jeder Seite, auch
        im Report über den Server — und bringt sein Skript mit. Im Suchformular
        steht er nicht mehr (bis 1.18.1 unten, auf keinem anderen Reiter zu sehen)."""
        cfg = load_cfg()
        seiten = [w.page(cfg, w.form_defaults(cfg)), w.kein_report_page(),
                  w.report_mit_reitern(b"<html><head></head><body><div class='wrap'><h1>R</h1></div></body></html>").decode("utf-8")]
        for seite in seiten:
            leiste = seite.split("<nav class='reiter'>", 1)[1].split("</nav>", 1)[0]
            self.assertIn("id='quit'", leiste)
            self.assertIn("getElementById('quit')", seite)
            self.assertIn("fetch('/shutdown', {method: 'POST'})", seite)
            self.assertEqual(seite.count("id='quit'"), 1)
            self.assertEqual(seite.count("getElementById('quit')"), 1)
        self.assertNotIn('id="quit"', seiten[0])
        self.assertIn(".reiter .aus{", w.REITER_CSS)
        # Im Rahmen nimmt das Skript die ganze Leiste samt Knopf heraus — es steht nach dem Knopf
        self.assertLess(seiten[2].index("id='quit'"), seiten[2].index("window.top !== window.self"))

    def test_leiste_steht_oben_wie_auf_jeder_seite(self):
        """Bis 1.18.0 kam sie vor `</body>` — am Handy unten festgeheftet und
        deshalb egal, am Rechner aber am Ende von 40 Bildschirmen Report und
        damit unsichtbar. Jetzt: Format in den Kopf, Leiste an den Anfang von
        `.wrap`, vor die erste Überschrift."""
        roh = (b"<!doctype html><html><head><style>.x{}</style></head>"
               b"<body><div class='wrap'><p class='sub'>Wingfoilscout</p><h1>Report</h1></div></body></html>")
        aus = w.report_mit_reitern(roh).decode("utf-8")
        self.assertLess(aus.index("<nav class='reiter'>"), aus.index("<h1>"))
        self.assertLess(aus.index("<div class='wrap'>"), aus.index("<nav class='reiter'>"))
        self.assertLess(aus.index(".reiter{"), aus.index("</head>"))
        self.assertEqual(aus.count("<nav class='reiter'>"), 1)
        # Das Skript, das die Leiste im Rahmen entfernt, folgt direkt auf sie
        self.assertLess(aus.index("<nav class='reiter'>"), aus.index("window.top !== window.self"))
        # Ein echter Report aus dem Demo-Lauf: dieselbe Stelle
        from tests.helpers import CONFIG, SPOTS
        from wingscout.cli import main
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(main(["--demo", "--days", "1", "--radius", "300", "--out", str(Path(d) / "r.html"),
                                   "--quiet", "--config", str(CONFIG), "--spots", str(SPOTS),
                                   "--geometry", str(Path(d) / "keine.json")]), 0)
            aus = w.report_mit_reitern((Path(d) / "r.html").read_bytes()).decode("utf-8")
        self.assertLess(aus.index("<nav class='reiter'>"), aus.index("<h1>Wo lohnt es sich?</h1>"))

    def test_ohne_body_bleibt_alles_wie_es_ist(self):
        roh = b"kein HTML"
        self.assertEqual(w.report_mit_reitern(roh), roh)

    def test_rueckblick_und_tagebuch_finden_ihren_lauf_wieder(self):
        """Dieselbe Lücke wie bei der Suchseite bis 1.18.2, nur zwei Reiter
        weiter (gefunden am 30.09.2026): Rückblick starten, Reiter wechseln,
        zurück — kein Spinner, „Prüfen“ frei, das alte Ergebnis stand da, und
        das neue kam erst nach einem Neuladen. Jetzt fragen beide Seiten beim
        Laden nach dem Stand; läuft etwas anderes, warten sie, statt beim Klick
        409 zu kassieren."""
        cfg = load_cfg()
        for name, skript in (("rueckblick", w.RUECKBLICK_JS), ("tagebuch", w.TAGEBUCH_JS)):
            with self.subTest(seite=name):
                self.assertIn("function uhrzeit(", skript)
                self.assertRegex(skript, r"fetch\('/status'\)[^\n]*\n\s*if \(j\.state === 'running'\) \{ \w+\(j\.kind !== '" + name + r"'\); poll\(\); \}")
                self.assertIn(f"j.kind === '{name}' && (j.state === 'done' || j.state === 'error')", skript)
                self.assertIn("uhrzeit(j.ende)", skript)
        self.assertIn("Es läuft gerade etwas anderes — der Rückblick wartet.", w.RUECKBLICK_JS)
        self.assertIn("Es läuft gerade etwas anderes — das Tagebuch wartet.", w.TAGEBUCH_JS)
        # Beide Seiten liefern das Skript mit Nonce aus
        for html_text in (w.rueckblick_page(cfg, None, None, 2, {}), w.tagebuch_page(cfg, [])):
            self.assertIn("fetch('/status')", html_text)

    def test_lauf_ueberlebt_den_reiterwechsel(self):
        """Ein Lauf gehört zum Programm, nicht zum Fenster. Bis 1.18.2 sah die
        Suchseite beim Wiederkommen aus wie abgebrochen (kein Spinner, Knopf
        frei, 409 beim Klick). Jetzt: `JOB` trägt Start und Ende, die Suchseite
        fragt beim Laden nach dem Stand, und jede Seite zeigt am Reiter, dass
        etwas läuft (lauf.js) — auch der Report über den Server."""
        import time
        cfg = load_cfg()
        seite = w.page(cfg, w.form_defaults(cfg))
        skript = re.split(r"<script[^>]*>", seite, 1)[1]
        self.assertIn("function zeigeLauf(", skript)
        self.assertIn("function zeigeErgebnis(", skript)
        self.assertRegex(skript, r"fetch\('/status'\)[^\n]*\n\s*if \(j\.state === 'running'\) \{ zeigeLauf\(j\); poll\(\); \}")
        for html_text in (seite, w.kein_report_page(),
                          w.report_mit_reitern(b"<html><head></head><body><div class='wrap'><h1>R</h1></div></body></html>").decode("utf-8")):
            self.assertIn("classList.add(klasse); a.title = text;", html_text)      # lauf.js
            self.assertEqual(html_text.count("var WOHER = {run: '/', ingest: '/'"), 1)
        self.assertIn(".reiter a.laeuft span::after", w.REITER_CSS)
        self.assertIn(".reiter a.neu span::after", w.REITER_CSS)
        # Start und Ende im Stand: davor keine, danach beide
        w.JOB.update(state="idle", seit=None, ende=None)
        vorher = time.time()
        self.assertTrue(w._starte("ingest", lambda: w.JOB.update(state="done", summary="x")))
        for _ in range(50):
            with w.LOCK:
                fertig = w.JOB["state"] != "running" and w.JOB["ende"] is not None
            if fertig:
                break
            time.sleep(0.05)
        self.assertTrue(fertig)
        self.assertGreaterEqual(w.JOB["seit"], vorher)
        self.assertGreaterEqual(w.JOB["ende"], w.JOB["seit"])
        self.assertIn("ende", json.loads(json.dumps(w.JOB)))
        w.JOB.update(state="idle", seit=None, ende=None, summary="", log=[])

    def test_ohne_report_eine_freundliche_seite(self):
        seite = w.kein_report_page()
        self.assertIn("Noch kein Report", seite)
        self.assertIn("href='/'", seite)
        self.assertIn("class='reiter'", seite)


class ZugangVomHandy(unittest.TestCase):
    """Mit `--lan` hört Wingfoilscout im WLAN — dann entscheidet der Schlüssel.

    Ohne ihn käme jedes Gerät im selben Netz an Katalog, Tagebuch und den
    Beenden-Knopf; der Server hört sonst nur auf 127.0.0.1.
    """

    def setUp(self):
        self.alt = dict(w.LAN)
        self.addCleanup(lambda: w.LAN.update(self.alt))
        w.LAN.update(aktiv=True, schluessel="geheim-123", adressen=("192.168.178.25",))

    def test_ohne_lan_ist_alles_frei(self):
        w.LAN.update(aktiv=False)
        self.assertEqual(w.zugang_pruefen("192.168.178.9", "", ""), "frei")

    def test_der_mac_selbst_braucht_keinen_schluessel(self):
        self.assertEqual(w.zugang_pruefen("127.0.0.1", "", ""), "frei")
        self.assertEqual(w.zugang_pruefen("::1", "", ""), "frei")

    def test_fremdes_geraet_ohne_schluessel_wird_abgewiesen(self):
        self.assertEqual(w.zugang_pruefen("192.168.178.9", "", ""), "abweisen")
        self.assertEqual(w.zugang_pruefen("192.168.178.9", "falsch", ""), "abweisen")
        self.assertEqual(w.zugang_pruefen("192.168.178.9", "", "wingscout_schluessel=falsch"), "abweisen")
        self.assertEqual(w.zugang_pruefen("192.168.178.9", "", "anderes=geheim-123"), "abweisen")

    def test_schluessel_in_der_adresse_setzt_das_cookie(self):
        self.assertEqual(w.zugang_pruefen("192.168.178.9", "geheim-123", ""), "setzen")

    def test_cookie_reicht_danach(self):
        self.assertEqual(w.zugang_pruefen("192.168.178.9", "", "a=1; wingscout_schluessel=geheim-123"), "frei")

    def test_handler_leitet_um_und_setzt_das_cookie(self):
        """Der Weg durch den Handler: 302 auf dieselbe Seite ohne Schlüssel,
        Cookie dabei — und ohne Schlüssel 401 statt einer Seite."""
        class Probe(w.Handler):
            def __init__(self, ip, pfad, cookie=""):
                self.client_address = (ip, 4711)
                self.path = pfad
                self.headers = {"Cookie": cookie}
                self.code = None
                self.kopf = {}
                self.gesendet = b""

            def send_response(self, code):
                self.code = code

            def send_header(self, name, wert):
                self.kopf[name] = wert

            def end_headers(self):
                pass

            def _send(self, code, body, ctype="text/html; charset=utf-8"):
                self.code, self.gesendet = code, body

        mit = Probe("192.168.178.9", "/tagebuch?k=geheim-123&x=1")
        self.assertFalse(mit._zugang())
        self.assertEqual(mit.code, 302)
        self.assertEqual(mit.kopf["Location"], "/tagebuch?x=1")
        self.assertIn("wingscout_schluessel=geheim-123", mit.kopf["Set-Cookie"])
        self.assertIn("HttpOnly", mit.kopf["Set-Cookie"])

        ohne = Probe("192.168.178.9", "/tagebuch")
        self.assertFalse(ohne._zugang())
        self.assertEqual(ohne.code, 401)
        self.assertIn(b"Kein Zugang", ohne.gesendet)

        daheim = Probe("127.0.0.1", "/tagebuch")
        self.assertTrue(daheim._zugang())

    def test_eigene_adressen_sind_keine_loopback(self):
        for adresse in w.eigene_adressen():
            self.assertFalse(adresse.startswith("127."), adresse)


class PruefReiter(unittest.TestCase):
    """Der Reiter „Koordinaten prüfen“ steht nur da, wenn es etwas zu prüfen
    gibt — sonst führt er auf eine leere Seite und verwirrt (1.16.1)."""

    def setUp(self):
        import os
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.sp, self.geo = d / "spots.yaml", d / "geometry.json"
        self.sp.write_text("- id: a\n", encoding="utf-8")
        self.geo.write_text("{}", encoding="utf-8")
        self.os = os
        alt = (w.SPOTS_FILE, w.GEOMETRY_FILE, w.pruef_liste, dict(w._PRUEF_ZAHL))
        self.aufrufe, self.eintraege = [], []

        def liste(home=None):
            self.aufrufe.append(home)
            return list(self.eintraege), {}

        w.SPOTS_FILE, w.GEOMETRY_FILE, w.pruef_liste = self.sp, self.geo, liste
        w._PRUEF_ZAHL.update(stand=None, n=0)

        def zurueck():
            w.SPOTS_FILE, w.GEOMETRY_FILE, w.pruef_liste = alt[0], alt[1], alt[2]
            w._PRUEF_ZAHL.clear()
            w._PRUEF_ZAHL.update(alt[3])
            self.tmp.cleanup()

        self.addCleanup(zurueck)

    def test_leere_liste_versteckt_den_reiter(self):
        self.assertNotIn("/pruefen", w.reiter("/"))
        self.assertIn("Katalog", w.reiter("/"))
        # Auf der Prüfseite selbst bleibt er stehen — sonst zieht sich die
        # Seite unter den Füßen weg, wenn der letzte Eintrag abgehakt ist.
        self.assertIn("href='/pruefen' class='an'", w.reiter("/pruefen"))  # aktiv, also sichtbar

    def test_mit_eintrag_ist_er_wieder_da(self):
        self.eintraege = [{"stufe": "unbestaetigt"}]
        self.assertIn("href='/pruefen'", w.reiter("/"))

    def test_zahl_wird_gemerkt_bis_sich_eine_datei_aendert(self):
        w.reiter("/")
        w.reiter("/katalog")
        self.assertEqual(len(self.aufrufe), 1, "jede Seite darf den Katalog nicht neu einlesen")
        self.eintraege = [{"stufe": "pruefen"}]
        self.assertNotIn("/pruefen", w.reiter("/"))          # noch der gemerkte Stand
        stat = self.sp.stat()
        self.os.utime(self.sp, (stat.st_atime + 5, stat.st_mtime + 5))
        self.assertIn("href='/pruefen'", w.reiter("/"))
        self.assertEqual(len(self.aufrufe), 2)

    def test_kaputter_katalog_kostet_nur_den_reiter(self):
        def kaputt(home=None):
            raise ValueError("Doppelte Spot-ID")

        w.pruef_liste = kaputt
        self.assertNotIn("/pruefen", w.reiter("/"))


class Neustarthinweis(unittest.TestCase):
    def test_hinweis_nur_wenn_die_platte_neuer_ist(self):
        """Nach „Neuen Stand holen“ läuft der alte Prozess weiter — jede Seite
        sagt dann, dass ein Neustart fällig ist. Sonst steht nichts da."""
        from unittest import mock
        self.assertEqual(w.version_auf_platte(), w.__version__)
        self.assertEqual(w.neustart_hinweis(), "")
        self.assertNotIn("b-warn", w.reiter("/"))
        with mock.patch.object(w, "version_auf_platte", return_value="9.9.9"):
            hinweis = w.neustart_hinweis()
            self.assertIn("läuft noch mit Version " + w.__version__, hinweis)
            self.assertIn("auf der Platte liegt schon 9.9.9", hinweis)
            self.assertIn("class='banner b-warn'", w.reiter("/katalog"))


class Katalogseite(unittest.TestCase):
    def test_seite_zeigt_alle_spots_und_escaped(self):
        from wingscout.spots import Spot
        spots = [Spot({"id": "a", "name": "<b>Böse</b>", "lat": 51.7, "lon": 3.8, "country": "NL",
                       "water_body": "sea", "verified": True, "notes": "x & y", "sectors": [],
                       "thermal": {"name": "Zeewind"}}),
                 Spot({"id": "b", "name": "Zwei", "lat": 49.4, "lon": 8.7, "country": "DE",
                       "water_body": "lake", "verified": False, "notes": "", "sectors": [],
                       "shorebreak": {"status": "possible"}, "instagram": "#zweisee", "comment": "war am 12.9. da"})]
        html = w.katalog_page(spots, {"lat": 53.55, "lon": 9.99})
        self.assertIn("class='reiter'", html)
        self.assertIn("id='ksuch'", html)
        self.assertIn("id='kneu'", html)                       # Schon drin?
        self.assertNotIn("<b>Böse</b>", html)
        self.assertIn("\\u003cb\\u003e", html)
        self.assertIn("integrity=", html)
        daten = w.katalog_daten(spots)
        self.assertEqual([d["id"] for d in daten], ["a", "b"])       # nach Name sortiert: Böse, Zwei
        self.assertEqual(daten[0]["thermik"], "Zeewind")
        self.assertEqual(daten[1]["shorebreak"], "possible")
        self.assertEqual(daten[1]["instagram"], "#zweisee")
        # Instagram-Adressen kommen aus wingscout/instagram.py — dieselben wie im Report
        self.assertEqual(daten[1]["ig"]["Instagram"], "https://www.instagram.com/explore/tags/zweisee/")
        self.assertIn("site%3Ainstagram.com%20%22Zwei%22%20wingfoil", daten[1]["ig"]["Insta-Suche"])
        self.assertEqual(daten[0]["ig"]["Instagram"], "https://www.instagram.com/explore/tags/bboeseb/")
        self.assertEqual(daten[0]["ig_funde"], [])
        self.assertIn("<option value='insta_offen'>", html)
        # Kommentar: je Zeile ein Kasten, das gemeinsame Skript, das Feld im Formular
        self.assertEqual(daten[1]["comment"], "war am 12.9. da")
        self.assertIn("window.WSKommentar", html)
        self.assertIn("id='kkommentar'", html)
        self.assertIn("'<div class=\"kmt\" data-id=\"' + esc(s.id)", html)
        self.assertIn("<option value='NL'>", html)
        js = re.split(r"<script[^>]*>", html)[1].split("</script>")[0]
        self.assertNotRegex(js, r"\{\{|\}\}")

    def test_katalog_wird_ausgeliefert(self):
        w.Handler.cfg_path = str(CONFIG)
        server = ThreadingHTTPServer(("127.0.0.1", 0), w.Handler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/katalog", timeout=10) as r:
                text = r.read().decode("utf-8")
            self.assertEqual(r.status, 200)
            self.assertIn("<h1>Katalog</h1>", text)
            self.assertIn("var SPOTS = ", text)
        finally:
            server.shutdown()
            server.server_close()


class WebDateien(unittest.TestCase):
    """CSS und JavaScript liegen seit 1.16.0 in wingscout/web/ (Struktur-Review
    A1). Was hier fest steht: jede Datei ist da und wird gelesen, und keine
    trägt verdoppelte Klammern — ein Überbleibsel der f-Vorlagen, das im
    Browser als Syntaxfehler endet."""

    def test_dateien_da_und_ohne_verdoppelte_klammern(self):
        from wingscout import webui
        dateien = sorted(webui.WEB.glob("*"))
        # .png seit 1.17.0: die Symbole für den Home-Bildschirm
        self.assertEqual({d.suffix for d in dateien}, {".css", ".js", ".png"})
        for d in dateien:
            if d.suffix == ".png":
                self.assertTrue(d.stat().st_size > 200, d.name)
                self.assertEqual(d.read_bytes()[:8], b"\x89PNG\r\n\x1a\n", d.name)
                continue
            text = d.read_text(encoding="utf-8")
            self.assertTrue(text.strip(), d.name)
            if d.suffix == ".js":
                # „{{“ kommt in diesem JavaScript nicht vor; „}}“ schon (ein
                # Objekt im Objekt) und wird deshalb nicht geprüft
                self.assertNotIn("{{", text, d.name)
        self.assertEqual(webui.RUECKBLICK_JS, (webui.WEB / "rueckblick.js").read_text(encoding="utf-8"))

    def test_symbole_und_manifest_werden_ausgeliefert(self):
        """Fürs „Zum Home-Bildschirm“ braucht Safari das Manifest und ein
        apple-touch-icon; fehlen sie, startet die Web-App namenlos und grau."""
        from wingscout import webui
        import json as _json
        daten = _json.loads(webui.MANIFEST)
        self.assertEqual(daten["display"], "standalone")
        self.assertEqual(daten["start_url"], "/")
        quellen = {i["src"] for i in daten["icons"]}
        self.assertIn("/icon-512-maskable.png", quellen)
        for pfad in quellen | {"/icon-180.png"}:
            datei = webui.WEB / pfad.lstrip("/")
            self.assertTrue(datei.exists(), pfad)
        from tests.helpers import cfg as load_cfg
        seite = webui.page(load_cfg(), webui.form_defaults(load_cfg()))
        self.assertIn("rel='manifest'", seite)
        self.assertIn("apple-touch-icon", seite)

    def test_startseite_bekommt_heimat_und_kartenbibliothek(self):
        from wingscout import webui
        from tests.helpers import cfg as load_cfg
        cfg = load_cfg()
        seite = webui.page(cfg, webui.form_defaults(cfg))
        self.assertIn("var LEAFLET = {", seite)
        self.assertIn(webui.LEAFLET_JS_SRI, seite)
        self.assertIn(f"var HOME = {{lat: {float(cfg['rider']['home']['lat'])}", seite)
        self.assertIn(webui.SUCHE_JS, seite)
