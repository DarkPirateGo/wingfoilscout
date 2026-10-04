"""Datenquellen — alles ohne Netz, mit untergeschobenen Antworten."""
from __future__ import annotations
import base64
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

from tests.helpers import cfg as load_cfg
from wingscout.sources import meteoalarm, openmeteo, ensemble, park4night, routing, overpass

FEED_NEU = '''<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">
<entry><title>Yellow Wind Warning for Texel</title>
<cap:areaDesc>Texel</cap:areaDesc><cap:event>Wind</cap:event><cap:severity>Moderate</cap:severity>
<cap:effective>2026-09-11T00:00:00Z</cap:effective><cap:expires>2026-09-11T14:22:00Z</cap:expires></entry>
<entry><title>Orange Thunderstorm Warning for Zeeland</title>
<cap:areaDesc>Zeeland</cap:areaDesc><cap:event>Thunderstorm</cap:event><cap:severity>Severe</cap:severity></entry>
</feed>'''

FEED_ALT = '''<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">
<entry><title>Warnung</title><cap:areaDesc>Bayern</cap:areaDesc>
<cap:parameter><cap:valueName>awareness_level</cap:valueName><cap:value>3; orange; Severe</cap:value></cap:parameter>
<cap:parameter><cap:valueName>awareness_type</cap:valueName><cap:value>1; Wind</cap:value></cap:parameter>
</entry></feed>'''


class Gitterzelle(unittest.TestCase):
    """Beide Abfragen müssen dieselbe Art Gitterzelle nehmen.

    Open-Meteo verschiebt eine Koordinate standardmäßig auf eine Landzelle
    ähnlicher Höhe. Fragte die Hauptabfrage eine Landzelle ab, während die
    hochauflösenden Modelle "nearest" nutzen, dann maß der ausgewiesene
    Unterschied zwischen beiden zum Teil nur Land gegen Wasser — über Land ist
    der Wind wegen der Rauigkeit systematisch schwächer. Der Vergleich hätte
    die feinen Modelle besser aussehen lassen, als sie sind.
    """

    def test_beide_quellen_nehmen_die_naechste_zelle(self):
        from wingscout.sources import openmeteo, highres
        import inspect
        for modul in (openmeteo, highres):
            quelltext = inspect.getsource(modul)
            self.assertIn('"cell_selection": "nearest"', quelltext,
                          f"{modul.__name__} fragt nicht die nächste Gitterzelle ab")


class MeteoAlarm(unittest.TestCase):
    def test_neues_feedformat(self):
        alerts = meteoalarm.parse_feed(FEED_NEU)
        self.assertEqual([a["level"] for a in alerts], [2, 3])
        self.assertEqual(alerts[0]["area"], "Texel")
        self.assertEqual(alerts[1]["event"], "Thunderstorm")

    def test_altes_feedformat(self):
        alerts = meteoalarm.parse_feed(FEED_ALT)
        self.assertEqual(alerts[0]["level"], 3)
        self.assertEqual(alerts[0]["event"], "Wind")

    def test_kaputtes_xml_ergibt_leer(self):
        self.assertEqual(meteoalarm.parse_feed("<feed><entry>"), [])

    def test_zuordnung_nach_region(self):
        alerts = meteoalarm.parse_feed(FEED_NEU)
        meteoalarm.fetch_country = lambda c, cache_dir=None: alerts
        spots = [{"id": "z", "country": "NL", "region": "Zeeland"},
                 {"id": "f", "country": "NL", "region": "Friesland"}]
        out = meteoalarm.alerts_for(spots, min_level=2)
        self.assertIn("z", out)
        self.assertNotIn("f", out)

    def test_ohne_region_keine_warnung_am_spot_sondern_einmal_im_kopf(self):
        """„Gewitter · Bornholm“ an dreizehn Nordseespots war Rauschen. Ein Spot
        ohne `region` bekommt nichts; das Land wird einmal gesammelt."""
        alerts = meteoalarm.parse_feed(FEED_NEU)
        meteoalarm.fetch_country = lambda c, cache_dir=None: alerts
        spots = [{"id": "z", "country": "NL", "region": "Zeeland"},
                 {"id": "o", "country": "NL", "region": ""},
                 {"id": "p", "country": "NL"}]
        landesweit = {}
        out = meteoalarm.alerts_for(spots, min_level=2, landesweit=landesweit)
        self.assertIn("z", out)
        self.assertNotIn("o", out)
        self.assertNotIn("p", out)
        self.assertEqual(list(landesweit), ["NL"])
        self.assertEqual(len(landesweit["NL"]), len([a for a in alerts if a["level"] >= 2]))


class Antwortgroesse(unittest.TestCase):
    def test_zu_grosse_antwort_ist_ein_fehler(self):
        from wingscout.sources.netz import lies
        class Resp:
            def __init__(self, n): self.n = n
            def read(self, k=-1): return b"x" * (self.n if k < 0 else min(k, self.n))
        self.assertEqual(len(lies(Resp(10), limit=10)), 10)
        with self.assertRaises(ValueError):
            lies(Resp(11), limit=10)

    def test_jede_quelle_liest_begrenzt(self):
        from tests.helpers import ROOT
        for datei in sorted((ROOT / "wingscout" / "sources").glob("*.py")):
            text = datei.read_text(encoding="utf-8")
            self.assertNotIn("resp.read()", text, f"{datei.name}: unbegrenztes read()")


class OpenMeteoRetry(unittest.TestCase):
    def setUp(self):
        self._urlopen = openmeteo.urllib.request.urlopen
        self._wait = openmeteo.RETRY_WAIT
        openmeteo.RETRY_WAIT = (0, 0, 0)

    def tearDown(self):
        openmeteo.urllib.request.urlopen = self._urlopen
        openmeteo.RETRY_WAIT = self._wait

    def _fake(self, codes):
        calls = {"n": 0}

        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n=-1): return b'{"hourly": {"time": []}}'

        def urlopen(req, timeout=None):
            calls["n"] += 1
            code = codes[min(calls["n"] - 1, len(codes) - 1)]
            if code == 200:
                return Resp()
            raise urllib.error.HTTPError(req.full_url, code, "x", {}, None)
        openmeteo.urllib.request.urlopen = urlopen
        return calls

    def test_503_wird_wiederholt(self):
        calls = self._fake([503, 503, 200])
        self.assertEqual(openmeteo._get("https://x"), {"hourly": {"time": []}})
        self.assertEqual(calls["n"], 3)

    def test_400_wird_nicht_wiederholt(self):
        calls = self._fake([400])
        with self.assertRaises(openmeteo.ForecastError):
            openmeteo._get("https://x")
        self.assertEqual(calls["n"], 1)

    def test_teilausfall_liefert_rest(self):
        spots = [{"id": f"s{i}", "lat": 50 + i * 0.1, "lon": 8} for i in range(30)]
        calls = {"n": 0}

        def fake_get(url, log=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise openmeteo.ForecastError("503")
            n = len(url.split("latitude=")[1].split("&")[0].split("%2C"))
            return [{"hourly": {"time": []}} for _ in range(n)]
        orig = openmeteo._get
        openmeteo._get = fake_get
        try:
            lines = []
            got = openmeteo.fetch(spots, 3, log=lines.append)
        finally:
            openmeteo._get = orig
        self.assertEqual(len(got), 10)
        self.assertTrue(any("ohne Vorhersage" in l for l in lines))


class Ensemble(unittest.TestCase):
    def test_fensterstatistik(self):
        entry = {"time": ["2026-09-13T12:00", "2026-09-13T13:00", "2026-09-13T14:00"],
                 "members": [[10, 12, 14], [8, 9, 9], [16, 18, 20], [11, 13, 12]]}
        st = ensemble.window_stats(entry, entry["time"], ride_kn=10, good_kn=14)
        self.assertEqual(st["members"], 4)
        self.assertEqual(st["p_ride"], 0.75)
        self.assertEqual(st["p_good"], 0.25)
        self.assertLessEqual(st["p10"], st["p50"])
        self.assertLessEqual(st["p50"], st["p90"])
        self.assertIsNone(ensemble.window_stats(entry, ["2026-09-14T12:00"], 10, 14))
        self.assertIsNone(ensemble.window_stats(None, entry["time"], 10, 14))


class Park4Night(unittest.TestCase):
    PROBE = [
        {"id": 1, "url": "/de/place/1", "type": {"code": "PJ"}, "name": "", "title_short": "Tagesparkplatz",
         "address": {"zipcode": "4323", "city": "Ellemeet"}, "lat": 51.7, "lng": 3.8, "services": ["animaux"],
         "review": 12, "rating": 4.7, "distance": 0.8},
        {"id": 2, "url": "/de/place/2", "type": {"code": "C"}, "name": "Camping Gut", "address": {},
         "lat": 51.7, "lng": 3.8, "services": ["animaux", "douche"], "review": 19, "rating": 5, "distance": 1.1},
        {"id": 3, "url": "/de/place/3", "type": {"code": "C"}, "name": "Camping Ohne Hund", "address": {},
         "lat": 51.7, "lng": 3.8, "services": ["douche"], "review": 9, "rating": 4.8, "distance": 0.5},
        {"id": 4, "url": "/de/place/4", "type": {"code": "ACC_G"}, "name": "Stellplatz Deich", "address": {},
         "lat": 51.7, "lng": 3.8, "services": ["animaux"], "review": 6, "rating": 4.2, "distance": 3.1},
        {"id": 5, "url": "/de/place/5", "type": {"code": "C"}, "name": "Schlecht", "address": {},
         "lat": 51.7, "lng": 3.8, "services": ["animaux"], "review": 40, "rating": 2.5, "distance": 0.9},
        {"id": 6, "url": "/de/place/6", "type": {"code": "C"}, "name": "Zu weit", "address": {},
         "lat": 51.9, "lng": 3.9, "services": ["animaux"], "review": 5, "rating": 5, "distance": 19.2},
        {"id": 7, "url": "javascript:alert(1)", "type": {"code": "F"}, "name": "Böse", "address": {},
         "lat": "abc", "lng": None, "services": ["animaux"], "review": 1, "rating": 5, "distance": 2.0},
    ]

    def setUp(self):
        self._around = park4night._around
        park4night._around = lambda lat, lon, radius, lang="de": self.PROBE

    def tearDown(self):
        park4night._around = self._around

    def test_dekodierung(self):
        plain = json.dumps([{"id": 1}]).encode()
        self.assertEqual(park4night._decode(plain), [{"id": 1}])
        self.assertEqual(park4night._decode(base64.b64encode(plain)), [{"id": 1}])
        with self.assertRaises(park4night.Park4NightError):
            park4night._decode(b"@@@ kein json, kein base64 @@@")

    def test_filter_und_zaehler(self):
        camping = load_cfg()["camping"]
        res = park4night.places_for(51.7369, 3.8285, camping)
        namen = [p["name"] for p in res["places"]]
        self.assertNotIn("Tagesparkplatz", namen)          # falscher Typ
        self.assertNotIn("Camping Ohne Hund", namen)       # Hund zwingend
        self.assertNotIn("Schlecht", namen)                # unter min_rating
        self.assertNotIn("Zu weit", namen)
        self.assertEqual(res["ohne_hundeangabe"], 1)
        self.assertEqual(res["zu_weit"], 1)
        self.assertEqual(res["schlecht_bewertet"], 1)
        # klein und 3 km weit schlägt den großen Campingplatz in 1 km
        self.assertLess(namen.index("Stellplatz Deich"), namen.index("Camping Gut"))

    def test_fremde_werte_werden_zahlen(self):
        camping = load_cfg()["camping"]
        boese = [p for p in park4night.places_for(51.7, 3.8, camping)["places"] if p["name"] == "Böse"]
        self.assertEqual(len(boese), 1)
        self.assertEqual(boese[0]["lat"], 0.0)
        self.assertEqual(boese[0]["lon"], 0.0)


class CacheAnDerKoordinate(unittest.TestCase):
    """Ein Auszug gilt für den Punkt, für den er geholt wurde.

    Bis 1.6.1 hingen alle Zwischenspeicher nur an der Spot-ID. Wer die Nadel
    auf der Prüfseite verschob, bekam Geometrie, Schutzgebiete und Fahrzeit
    des alten Punkts — ohne dass irgendetwas das gesagt hätte.
    """

    def test_passt(self):
        from wingscout.sources.overpass import passt, stempel
        self.assertEqual(stempel(51.736912, 3.828512), [51.7369, 3.8285])
        self.assertTrue(passt([51.7369, 3.8285], 51.73691, 3.82851))
        self.assertFalse(passt([51.7369, 3.8285], 51.7420, 3.8285))     # 570 m weiter
        self.assertTrue(passt(None, 51.7, 3.8))                        # ohne Stempel: gilt
        self.assertTrue(passt("kaputt", 51.7, 3.8))

    def test_overpass_auszug_wird_bei_anderer_koordinate_neu_geholt(self):
        from wingscout.sources import overpass
        antworten = []
        orig = overpass._ask
        overpass._ask = lambda query, pause_s: antworten.append(query) or {"elements": []}
        try:
            with tempfile.TemporaryDirectory() as d:
                overpass.fetch_water("x", 51.7369, 3.8285, 25, cache_dir=d, pause_s=0)
                erste = len(antworten)
                self.assertGreater(erste, 0)
                overpass.fetch_water("x", 51.7369, 3.8285, 25, cache_dir=d, pause_s=0)
                self.assertEqual(len(antworten), erste, "gleicher Punkt: aus dem Cache")
                overpass.fetch_water("x", 51.7500, 3.8285, 25, cache_dir=d, pause_s=0)
                self.assertGreater(len(antworten), erste, "anderer Punkt: neu geholt")
                # Ein alter Auszug ohne Stempel gilt weiter — das Holen ist teuer.
                pfad = Path(d) / "y_25km.json"
                pfad.write_text('{"elements": []}', encoding="utf-8")
                vorher = len(antworten)
                overpass.fetch_water("y", 51.0, 3.0, 25, cache_dir=d, pause_s=0)
                self.assertEqual(len(antworten), vorher)
        finally:
            overpass._ask = orig

    def test_schutzgebiete_mit_stempel_und_altem_format(self):
        from wingscout.sources import overpass
        with tempfile.TemporaryDirectory() as d:
            alt = Path(d) / "a_protected.json"
            alt.write_text('[{"name": "Altes Format"}]', encoding="utf-8")
            self.assertEqual(overpass.fetch_protected("a", 51.7, 3.8, cache_dir=d)[0]["name"],
                             "Altes Format")
            neu = Path(d) / "b_protected.json"
            neu.write_text(json.dumps({"_spot": [51.7, 3.8], "gebiete": [{"name": "Neu"}]}),
                           encoding="utf-8")
            self.assertEqual(overpass.fetch_protected("b", 51.7, 3.8, cache_dir=d)[0]["name"], "Neu")
            # Anderer Punkt: der Eintrag gilt nicht; ohne Netz kommt eine leere Liste
            orig = overpass.urllib.request.urlopen
            overpass.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError("kein Netz"))
            try:
                self.assertEqual(overpass.fetch_protected("b", 51.9, 3.8, cache_dir=d, pause_s=0), [])
            finally:
                overpass.urllib.request.urlopen = orig


class Park4NightRobust(unittest.TestCase):
    def test_kaputte_felder_beenden_nicht_den_lauf(self):
        """Inoffizielle Schnittstelle: ein Feld, das anders aussieht als beim
        Mitlesen, kostet den Stellplatzblock — nicht den Report."""
        kaputt = [{"id": 1, "url": ".evil.example/x", "type": {"code": "C"}, "name": "A", "address": None,
                   "lat": 51.7, "lng": 3.8, "services": "animaux", "review": "viele", "rating": "n/a",
                   "distance": "nah"},
                  {"id": 2, "url": "/de/place/2", "type": {"code": "C"}, "name": "B", "address": {},
                   "lat": 51.7, "lng": 3.8, "services": ["animaux", {"x": 1}], "review": 3, "rating": 4.5,
                   "distance": 1.0}]
        orig = park4night._around
        park4night._around = lambda lat, lon, radius, lang="de": kaputt
        try:
            res = park4night.places_for(51.7, 3.8, {"dog_required": True, "min_rating": 0})
        finally:
            park4night._around = orig
        b = next(p for p in res["places"] if p["name"] == "B")
        self.assertEqual(b["url"], "https://park4night.com/de/place/2")
        self.assertEqual(b["services"], ["animaux"])
        # A: `services` war eine Zeichenkette → als „ohne Hundeangabe“ gezählt, nicht abgestürzt
        self.assertEqual(res["ohne_hundeangabe"], 1)
        a = park4night._tidy(kaputt[0])
        self.assertEqual(a["url"], "", "kein Pfad → keine Adresse, auch nicht park4night.com.evil…")
        self.assertEqual((a["rating"], a["reviews"], a["km"]), (0.0, 0, 0.0))

    def test_fetch_faengt_alles(self):
        orig = park4night.places_for
        park4night.places_for = lambda *a, **k: (_ for _ in ()).throw(TypeError("ganz anders"))
        try:
            lines = []
            out = park4night.fetch([{"id": "s", "name": "S", "lat": 51.7, "lon": 3.8}], {}, log=lines.append)
        finally:
            park4night.places_for = orig
        self.assertEqual(out, {})
        self.assertTrue(any("nicht lesbar" in l for l in lines))


class Routing(unittest.TestCase):
    def test_fahrzeit_gilt_nur_fuer_die_koordinate(self):
        """Gemerkt mit Stempel: gleicher Punkt aus dem Cache, anderer Punkt neu;
        ohne Stempel (vor 1.7.0) ebenfalls neu — ein Aufruf je neunzig Ziele."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "routes.json"
            json.dump({"51.74,3.83": {"a": {"h": 1.02, "km": 63.0, "bei": [51.44, 4.21]},
                                      "b": {"h": 2.0, "km": 150.0, "bei": [52.98, 5.45]},
                                      "c": {"h": 3.0, "km": 200.0}}}, open(path, "w"))
            spots = [{"id": "a", "lat": 51.44, "lon": 4.21},        # passt
                     {"id": "b", "lat": 52.60, "lon": 5.45},        # 40 km verschoben
                     {"id": "c", "lat": 53.00, "lon": 6.00}]        # ohne Stempel
            gefragt = []
            orig = routing._ask
            routing._ask = lambda coords: gefragt.append(coords) or {
                "code": "Ok", "durations": [[0, 7200, 10800]], "distances": [[0, 160000, 210000]]}
            try:
                times = routing.drive_times({"lat": 51.7369, "lon": 3.8285}, spots, path)
            finally:
                routing._ask = orig
            self.assertEqual(len(gefragt), 1)
            self.assertNotIn("51.44000,4.21000", gefragt[0])            # a kam aus dem Cache
            self.assertEqual(times["a"], {"h": 1.02, "km": 63.0})
            self.assertEqual(times["b"], {"h": 2.0, "km": 160.0})
            self.assertEqual(json.load(open(path))["51.74,3.83"]["b"]["bei"], [52.6, 5.45])

    def test_cache_und_ausfall(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "routes.json"
            json.dump({"51.74,3.83": {"a": {"h": 1.02, "km": 63.0, "bei": [51.44, 4.21]}}}, open(path, "w"))
            spots = [{"id": "a", "lat": 51.44, "lon": 4.21}, {"id": "b", "lat": 52.98, "lon": 5.45}]
            orig = routing._ask
            routing._ask = lambda coords: (_ for _ in ()).throw(routing.RoutingError("aus"))
            try:
                lines = []
                times = routing.drive_times({"lat": 51.7369, "lon": 3.8285}, spots, path, log=lines.append)
            finally:
                routing._ask = orig
            self.assertEqual(times, {"a": {"h": 1.02, "km": 63.0}})
            self.assertTrue(any("Schätzung" in l for l in lines))
            n = routing.apply_to(spots, times)
            self.assertEqual(n, 1)
            self.assertEqual(spots[0]["drive_source"], "Routing")
            self.assertEqual(spots[1]["drive_source"], "Schätzung")

    def test_antwort_wird_uebernommen_und_gespeichert(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "routes.json"
            spots = [{"id": "a", "lat": 51.44, "lon": 4.21}]
            orig = routing._ask
            routing._ask = lambda coords: {"code": "Ok", "durations": [[0, 3660]], "distances": [[0, 63000]]}
            try:
                times = routing.drive_times({"lat": 51.7369, "lon": 3.8285}, spots, path)
            finally:
                routing._ask = orig
            self.assertEqual(times["a"], {"h": 1.02, "km": 63.0})
            self.assertTrue(path.exists())

    def test_veraltetes_tls_wird_benannt(self):
        """Der Handschlagfehler soll sagen, woran es liegt — sonst sucht man am Server."""
        import ssl
        orig = ssl.OPENSSL_VERSION
        handschlag = "[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] sslv3 alert handshake failure"
        try:
            ssl.OPENSSL_VERSION = "LibreSSL 2.8.3"
            rat = routing._rat(handschlag)
            self.assertIn("LibreSSL 2.8.3", rat)
            self.assertIn("brew install python", rat)
            # Ein Fehler ohne TLS-Bezug bleibt unkommentiert.
            self.assertEqual(routing._rat("timed out"), "")
            ssl.OPENSSL_VERSION = "OpenSSL 3.0.2 15 Mar 2022"
            self.assertEqual(routing.tls_veraltet(), "")
            self.assertEqual(routing._rat(handschlag), "")
        finally:
            ssl.OPENSSL_VERSION = orig


class Overpass(unittest.TestCase):
    def test_ids_werden_dateitauglich(self):
        self.assertEqual(overpass.safe_id("../../etc/passwd"), "------etc-passwd")
        self.assertEqual(overpass.safe_id("brouwersdam"), "brouwersdam")
        self.assertEqual(overpass.safe_id(""), "spot")

    def test_merge_entdoppelt(self):
        out = overpass._merge({"elements": [{"type": "way", "id": 1}]},
                              {"elements": [{"type": "way", "id": 1}, {"type": "way", "id": 2}]}, None)
        self.assertEqual(len(out["elements"]), 2)


if __name__ == "__main__":
    unittest.main()
