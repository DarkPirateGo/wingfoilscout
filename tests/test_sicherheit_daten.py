"""Befunde des Reviews vom 04.10.2026 im Kern: fremde Daten, die Suche,
Import oder Katalog lahmlegten — jeder Fall nachgestellt, dazu der Stand, der
mit gültigen Daten unverändert bleiben muss.

C1 kubische Koordinatenmuster · C2 einzelne Surrogate · C3 YAML-Verweise ·
C4 Unsinnswerte in der Bewertung · C10 Ringe aus vielen Teilstücken ·
C20 tief verschachteltes GeoJSON · C25 Ortsnamen aus Nominatim ·
A3/C13 Dateirechte beim atomaren Schreiben.
"""
from __future__ import annotations
import copy
import json
import os
import shutil
import stat
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import yaml

from tests.helpers import CONFIG, ROOT, SPOTS, cfg as load_cfg
from wingscout import cli, geo, geometry, ingest, score, spotedit
from wingscout.config import KonfigFehler, load_config, yaml_laden
from wingscout.spots import KatalogFehler, load_spots

POSIX = os.name == "posix"


def _katalog(ordner: Path, text: str) -> Path:
    pfad = Path(ordner) / "spots.yaml"
    pfad.write_text(text, encoding="utf-8")
    return pfad


EIN_SPOT = "- id: a\n  name: A\n  lat: 51.7\n  lon: 3.8\n"


class C1_Koordinatenmuster(unittest.TestCase):
    """`\\s*` vor und hinter jedem optionalen Teil: 2000 Leerzeichen in einem
    CSV-Feld kosteten 21 Sekunden, 100 KB rund einen Monat."""

    def test_leerraum_im_feld_kostet_keine_sekunden(self):
        t0 = time.perf_counter()
        self.assertEqual(geo.parse_position("1°1" + " " * 100_000 + "x"), (1.0, 1.0))
        # Der Weg aus dem Review: Takeout-CSV, Koordinate in der Adressspalte
        text = 'Title,Note,URL\nA,,"1°1' + " " * 120_000 + 'x"\n'
        ingest.parse_text(text)
        # Die Muster selbst sind begrenzt, auch ohne das Zusammenfassen davor
        geo._DMS.findall("1°1" + " " * 100_000 + "x")
        geo._DMS_VORN.findall("N 1°1" + " " * 100_000 + "x")
        self.assertLess(time.perf_counter() - t0, 1.0)

    def test_erste_zeile_eines_imports_ist_linear(self):
        """`COORD_PAIR` lief auf der ersten Zeile quadratisch — die wird nicht
        gekappt: 8 KB eine Sekunde, die 4 MB eines Uploads Tage."""
        zeile = "a,,1.1" + " " * 200_000 + "x\n"
        t0 = time.perf_counter()
        ingest.ist_datei(zeile)
        ingest.parse_text(zeile)
        self.assertLess(time.perf_counter() - t0, 1.0)

    def test_koordinatenpaar_wie_bisher(self):
        """Dieselbe Sprache wie `\\s*[,;/ ]\\s*`: ein Trenner aus `,;/` mit
        Leerraum, oder Leerraum mit mindestens einem Leerzeichen."""
        for text, paar in (("51.7625, 3.854", ("51.7625", "3.854")), ("51,7625 3,854", ("51,7625", "3,854")),
                           ("51.7625 ;\t3.854", ("51.7625", "3.854")), ("51.7625\t 3.854", ("51.7625", "3.854")),
                           ("53.550/9.990", ("53.550", "9.990")), ("x 1.5  ,  -2.5 y", ("1.5", "-2.5"))):
            with self.subTest(text=text):
                self.assertEqual(ingest.COORD_PAIR.search(text).groups(), paar)
        for text in ("51.7625\t3.854", "51.7625,,3.854", "51.7625 x 3.854"):
            with self.subTest(text=text):
                self.assertIsNone(ingest.COORD_PAIR.search(text))

    def test_richtung_vorn(self):
        """„N 51°45.750 E 3°51.233“ wurde bis 2.1.0 zu (51.0, 45.75)."""
        lat, lon = geo.parse_position("N 51°45.750 E 3°51.233")
        self.assertAlmostEqual(lat, 51.7625, places=5)
        self.assertAlmostEqual(lon, 3.853883, places=5)
        lat, lon = geo.parse_position("N51°45'45\" E3°51'14\"")
        self.assertAlmostEqual(lat, 51.7625, places=4)
        self.assertAlmostEqual(lon, 3.8539, places=3)
        self.assertEqual(geo.parse_position("S 33°55.000' E 018°25.000'"), (-33.916667, 18.416667))
        self.assertEqual(geo.parse_position("N 43°30' W 008°15'"), (43.5, -8.25))
        # Richtung hinten bleibt, wie sie war — auch wenn danach ein N folgt
        lat, lon = geo.parse_position("51°45'45\"N 3°51'14\"E")
        self.assertAlmostEqual(lat, 51.7625, places=4)
        # Ein Buchstabe mitten im Wort ist keine Richtung
        self.assertEqual(geo._DMS_VORN.findall("Seen 51°45.750"), [])

    def test_zu_lang_ist_keine_koordinate(self):
        self.assertIsNone(geo.parse_position("51.7625, 3.854" + "x" * geo.MAX_EINGABE))
        self.assertEqual(geo.parse_position(" " * 10_000 + "51.7625, 3.854"), (51.7625, 3.854))


class C2_Surrogate(unittest.TestCase):
    """Ein Name mit `\\ud800` aus 169 Bytes GeoJSON: Import, Katalog, dann
    UnicodeEncodeError in der Suche und auf jeder Seite mit dem Namen."""

    GEOJSON = json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [8.61, 49.17]},
         "properties": {"name": "Baggersee \ud800"}}]})

    def test_import_putzt_den_namen(self):
        self.assertTrue(self.GEOJSON.isascii())
        hits, _ = ingest.parse_text(self.GEOJSON)
        self.assertEqual(hits[0][0], "Baggersee ?")
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "spots.yaml"
            shutil.copy(SPOTS, pfad)
            vorhanden = {s["id"] for s in load_spots(pfad)}
            eintrag = ingest.build_entry(*hits[0], vorhanden, verified=False)
            ingest.append_to_yaml(pfad, [eintrag])
            neu = [s for s in load_spots(pfad) if s["id"] == eintrag["id"]][0]
            self.assertEqual(neu["name"], "Baggersee ?")
            neu["name"].encode("utf-8")
            # Notiz und Kommentar legt /katalog/neu selbst in den Eintrag —
            # auch sie gehen nur als gültiges UTF-8 in die Datei
            zweiter = ingest.build_entry("Zweiter", 53.9, 10.9, None, vorhanden | {eintrag["id"]})
            zweiter.update(notes="Notiz \udc80", comment="Kommentar\ud800")
            ingest.append_to_yaml(pfad, [zweiter])
            neu = {s["id"]: s for s in load_spots(pfad)}[zweiter["id"]]
            self.assertEqual((neu["notes"], neu["comment"]), ("Notiz ?", "Kommentar?"))

    def test_name_putzen(self):
        self.assertEqual(ingest.name_putzen(" Grüner\tBrink\n\x01 / Fehmarn\u0085 "), "Grüner Brink / Fehmarn")
        self.assertEqual(ingest.name_putzen("A\udc80B"), "A?B")
        self.assertEqual(len(ingest.name_putzen("x" * 1000)), ingest.MAX_NAME)
        self.assertEqual(ingest.name_putzen(None), "")
        self.assertEqual(ingest.name_putzen(["a", "b"]), "")
        self.assertEqual(ingest.name_putzen({"a": 1}), "")
        self.assertEqual(ingest.name_putzen(42), "42")
        # Ein Name nur aus Steuerzeichen ist keiner — dann der Ort oder die Koordinate
        e = ingest.build_entry("\x01\x02", 49.17, 8.61, None, set())
        self.assertEqual(e["name"], "Spot 49.1700, 8.6100")
        e = ingest.build_entry("", 49.17, 8.61, None, set(), ort={"name": "Ort\ud800\x07", "country": "DE"})
        self.assertEqual(e["name"], "Ort?")

    def test_steuerzeichen_raus_nimmt_surrogate(self):
        self.assertEqual(spotedit.steuerzeichen_raus("a\ud800b\udfffc\U0001F600"), "abc\U0001F600")
        self.assertEqual(spotedit.steuerzeichen_raus("zwei\nZeilen\tTab"), "zwei\nZeilen\tTab")

    def test_katalog_mit_surrogat_ist_ein_katalogfehler(self):
        with tempfile.TemporaryDirectory() as d:
            for text, feld in ((EIN_SPOT.replace("name: A", 'name: "Baggersee \\uD800"'), "name"),
                               (EIN_SPOT + '  notes: "x\\uDC00"\n', "notes"),
                               (EIN_SPOT + '  thermal: {name: "x\\uD800"}\n', "thermal")):
                with self.subTest(feld=feld):
                    with self.assertRaises(KatalogFehler) as cm:
                        load_spots(_katalog(d, text))
                    self.assertIn(f"a: {feld}", str(cm.exception))
            # Ein Emoji ist ein ganzes Zeichen, kein Surrogat
            self.assertEqual(load_spots(_katalog(d, EIN_SPOT + '  notes: "\U0001F600"\n'))[0]["notes"], "\U0001F600")


class C3_YamlVerweise(unittest.TestCase):
    """559 Bytes mit verschachtelten Ankern: MemoryError bei jedem Seitenaufruf."""

    BOMBE = EIN_SPOT + "  c0: &a0 [x,x,x,x,x,x,x,x,x]\n" + "".join(
        f"  c{i}: &a{i} [{','.join([f'*a{i - 1}'] * 9)}]\n" for i in range(1, 9)) + "  comment: *a8\n"

    def test_verweise_werden_abgelehnt(self):
        with tempfile.TemporaryDirectory() as d:
            t0 = time.perf_counter()
            with self.assertRaises(KatalogFehler) as cm:
                load_spots(_katalog(d, self.BOMBE))
            self.assertLess(time.perf_counter() - t0, 1.0)
            self.assertIn("Zeile", str(cm.exception))
            self.assertIn("alias", str(cm.exception))
            # Ein Anker allein schadet nicht
            self.assertEqual(load_spots(_katalog(d, EIN_SPOT.replace("name: A", "name: &n A")))[0]["name"], "A")
            konfig = Path(d) / "config.yaml"
            konfig.write_text(CONFIG.read_text(encoding="utf-8") + "\nx: &a [1, 1]\ny: [*a, *a]\n", encoding="utf-8")
            with self.assertRaises(KonfigFehler):
                load_config(konfig)

    def test_katalog_und_vorlage_lesen_sich_wie_mit_safe_load(self):
        for pfad in (SPOTS, CONFIG):
            with self.subTest(datei=pfad.name):
                with pfad.open(encoding="utf-8") as fh:
                    erwartet = yaml.safe_load(fh)
                with pfad.open(encoding="utf-8") as fh:
                    self.assertEqual(yaml_laden(fh), erwartet)

    def test_was_yaml_sonst_noch_wirft_ist_ein_katalogfehler(self):
        """RecursionError, ValueError und UnicodeDecodeError sind kein
        `yaml.YAMLError` — sie kamen roh durch jede Seite."""
        faelle = {
            "verschachtelt": EIN_SPOT + "  notes: " + "[" * 3000 + "]" * 3000 + "\n",
            "riesenzahl": EIN_SPOT.replace("lat: 51.7", "lat: 1" + "0" * 5000),
            "monat 13": EIN_SPOT + "  region: 2026-13-45\n",
            "id als liste": EIN_SPOT.replace("id: a", "id: [a]"),
        }
        with tempfile.TemporaryDirectory() as d:
            for name, text in faelle.items():
                with self.subTest(fall=name):
                    with self.assertRaises(KatalogFehler):
                        load_spots(_katalog(d, text))
            pfad = Path(d) / "spots.yaml"
            pfad.write_bytes(b"- id: a\n  name: \xed\xa0\x80\n  lat: 1\n  lon: 2\n")
            with self.assertRaises(KatalogFehler):
                load_spots(pfad)

    def test_textfelder_sind_text(self):
        with tempfile.TemporaryDirectory() as d:
            for zusatz, feld in (("  notes: [a, b]\n", "notes"), ("  comment: {x: 1}\n", "comment"),
                                 ("  region: [1]\n", "region"),
                                 ("  shorebreak: {status: 'yes', note: [x]}\n", "shorebreak.note"),
                                 ("  tide: [hochwasser]\n", "tide")):
                with self.subTest(feld=feld):
                    with self.assertRaises(KatalogFehler) as cm:
                        load_spots(_katalog(d, EIN_SPOT + zusatz))
                    self.assertIn(f"a: {feld} muss ein Text sein", str(cm.exception))
            # YAML 1.1: nacktes `no` ist False — bleibt, wie es bis 2.1.0 war
            spot = load_spots(_katalog(d, EIN_SPOT + "  dogs: no\n  country: NO\n  comment: 42\n"))[0]
            self.assertEqual((spot["dogs"], spot["country"], spot["comment"]), (False, False, "42"))


def _vorhersage(stunden=24) -> dict:
    tag = datetime(2026, 10, 4)
    zeiten = [(tag + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(stunden)]
    return {"utc_offset_seconds": 7200,
            "hourly": {"time": zeiten, "wind_speed_10m": [16.0] * stunden, "wind_gusts_10m": [20.0] * stunden,
                       "wind_direction_10m": [250.0] * stunden, "temperature_2m": [18.0] * stunden,
                       "precipitation": [0.0] * stunden, "cape": [0.0] * stunden, "weather_code": [3] * stunden,
                       "cloud_cover": [20] * stunden, "shortwave_radiation": [300.0] * stunden},
            "daily": {"time": ["2026-10-04"], "sunrise": ["2026-10-04T07:30"], "sunset": ["2026-10-04T18:55"]}}


SPOT = {"id": "a", "name": "A", "lat": 51.75, "lon": 3.85, "country": "NL", "water_body": "sea",
        "sectors": [{"from": 200, "to": 320, "quality": "good", "water": "chop"}], "season": list(range(1, 13))}


class C4_Unsinnswerte(unittest.TestCase):
    """Ein einziger Unsinnswert aus einer Quelle brach bis 2.1.0 die ganze Suche ab."""

    def setUp(self):
        self.cfg = load_cfg()

    def test_bewertung_haelt_unsinn_aus(self):
        gut = score.score_hours(dict(SPOT), _vorhersage(), self.cfg)
        self.assertTrue(any(r["score"] > 0 for r in gut))
        faelle = {
            "utc_offset 1e999": lambda fc: fc.update(utc_offset_seconds=float("inf")),
            "utc_offset riesig": lambda fc: fc.update(utc_offset_seconds=10 ** 400),
            "utc_offset Text": lambda fc: fc.update(utc_offset_seconds="2h"),
            "Temperatur Text": lambda fc: fc["hourly"]["temperature_2m"].__setitem__(12, "warm"),
            "Temperatur nan": lambda fc: fc["hourly"]["temperature_2m"].__setitem__(12, float("nan")),
            "Richtung nan": lambda fc: fc["hourly"]["wind_direction_10m"].__setitem__(12, float("nan")),
            "Richtung inf": lambda fc: fc["hourly"]["wind_direction_10m"].__setitem__(12, float("inf")),
            "Wind Text": lambda fc: fc["hourly"]["wind_speed_10m"].__setitem__(12, "stark"),
            "Code Liste": lambda fc: fc["hourly"]["weather_code"].__setitem__(12, [95]),
            "Regen Text": lambda fc: fc["hourly"]["precipitation"].__setitem__(12, "viel"),
            "Strahlung Text": lambda fc: fc["hourly"]["shortwave_radiation"].__setitem__(12, "hell"),
            "Zeit kaputt": lambda fc: fc["hourly"]["time"].__setitem__(5, "quatsch"),
            "Zeit Zahl": lambda fc: fc["hourly"]["time"].__setitem__(6, 5),
            "Zeit mit Zone": lambda fc: fc["hourly"]["time"].__setitem__(7, "2026-10-04T07:00+02:00"),
            "Sonnenaufgang mit Zone": lambda fc: fc["daily"].update(sunrise=["2026-10-04T07:30+02:00"]),
            "daily Liste": lambda fc: fc.update(daily=["x"]),
            "Sonnenzeiten Block": lambda fc: fc["daily"].update(sunrise={"a": 1}, time="2026-10-04"),
        }
        jetzt = datetime(2026, 10, 4, 6, tzinfo=timezone.utc)
        for name, kaputt in faelle.items():
            with self.subTest(fall=name):
                fc = _vorhersage()
                kaputt(fc)
                for wann in (None, jetzt):
                    rows = score.score_hours(dict(SPOT), copy.deepcopy(fc), self.cfg, jetzt=wann)
                    score.build_sessions(dict(SPOT), rows, self.cfg)
        # Zusatzreihen: Wassertemperatur, Welle, Wasserstand
        t = _vorhersage()["hourly"]["time"][12]
        rows = score.score_hours(dict(SPOT), _vorhersage(), self.cfg, {t: "kalt"}, tide={t: "hoch"},
                                 wave={t: float("nan")})
        self.assertIsNone([r for r in rows if r["t"].hour == 12][0]["sst"])
        score.score_hours(dict(SPOT), _vorhersage(), self.cfg, ["x"], tide="x", wave=5)

    def test_gueltige_werte_bleiben_wie_sie_sind(self):
        self.assertEqual([score._zahl(x) for x in (0, 3, 2.5, -7.0)], [0, 3, 2.5, -7.0])
        self.assertEqual([score._zahl(x) for x in (None, True, "1", float("nan"), float("inf"), [1], 10 ** 400)],
                         [None] * 7)
        self.assertEqual(score._zeitversatz({"utc_offset_seconds": 7200}), 7200)
        self.assertIsNone(score._zeitversatz({"utc_offset_seconds": 1e999}))
        self.assertIsNone(score._zeitversatz({}))

    def test_ensemble_und_verlaesslichkeit_ohne_zahl(self):
        spot = dict(SPOT, drive_h=1.0)
        sessions = [{"spot": spot, "day": "2026-10-04", "start": datetime(2026, 10, 4, 12),
                     "end": datetime(2026, 10, 4, 15), "hours": 3, "score": 0.8, "thermal": False,
                     "ens": {"p_ride": p}} for p in ("x", float("nan"), None, 0.5)]
        trips = score.rank_trips(sessions, self.cfg)
        self.assertEqual(score.apply_ensemble(trips, self.cfg), 1)
        thermik = [{"spot": dict(spot, thermal={"reliability": "hoch"}), "score": 0.8, "thermal": True}]
        self.assertEqual(score.apply_reliability(thermik, self.cfg), 1)
        self.assertEqual(thermik[0]["sicherheit"]["p"], 0.6)

    def test_ein_kaputter_spot_kostet_den_spot_nicht_die_suche(self):
        echt = cli.score_hours
        getroffen = []

        def wirft_beim_ersten(spot, *a, **k):
            if not getroffen:
                getroffen.append(spot["name"])
                raise OverflowError("cannot convert float infinity to integer")
            return echt(spot, *a, **k)

        zeilen = []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(cli, "score_hours", wirft_beim_ersten):
            args = ["--demo", "--days", "1", "--radius", "400", "--out", str(Path(d) / "r.html"),
                    "--config", str(CONFIG), "--spots", str(SPOTS), "--geometry", str(Path(d) / "keine.json")]
            self.assertEqual(cli.main(args, log_fn=zeilen.append), 0)
            self.assertTrue((Path(d) / "r.html").exists())
        self.assertIn(f"    Vorhersage für {getroffen[0]} nicht verwertbar (OverflowError: cannot convert float "
                      "infinity to integer) — Spot übersprungen", zeilen)
        self.assertTrue(any("Sessions in" in z for z in zeilen), "die übrigen Spots wurden bewertet")

    def test_ensemble_auswertung_im_try(self):
        """window_stats stand außerhalb jedes try — eine unhashbare Zeit warf."""
        import argparse
        trips = [{"spot": dict(SPOT, wind_factor=1.0), "days": ["2026-10-04"], "quality": 0.8, "drive_score": 1.0,
                  "total_hours": 3, "rank": 0.5,
                  "sessions": [{"start": datetime(2026, 10, 4, 12), "end": datetime(2026, 10, 4, 15),
                                "thermal": False, "score": 0.8, "hours": 3, "modell_delta": None}]}]
        zeilen = []
        args = argparse.Namespace(no_ensemble=False, demo=False, days=1)
        with mock.patch("wingscout.sources.ensemble.fetch", return_value={"a": {"time": [[1]], "members": [[9]]}}), \
                mock.patch("wingscout.sources.ensemble.window_stats", side_effect=TypeError("unhashable type: 'list'")):
            cli.add_ensemble(trips, self.cfg, args, zeilen.append)
        self.assertIn("Ensemble für A nicht lesbar (TypeError: unhashable type: 'list') — weiter ohne "
                      "Wahrscheinlichkeit", zeilen)
        self.assertNotIn("ens", trips[0]["sessions"][0])


class C10_Ringe(unittest.TestCase):
    def test_viele_teilstuecke_in_linearer_zeit(self):
        """20 000 Stücke eines fremden Overpass-Spiegels: bis 2.1.0 eine Viertelstunde."""
        rel = {"members": [{"role": "outer", "geometry": [{"lat": i * 1e-3, "lon": 0.0}, {"lat": i * 1e-3, "lon": 1e-3}]}
                           for i in range(20_000)]}
        t0 = time.perf_counter()
        self.assertEqual(geometry.stitch_rings(rel), [])
        kette = [{"lat": i * 1e-4, "lon": 0.0} for i in range(20_001)] + [{"lat": 0.0, "lon": 0.0}]
        teile = [kette[i:i + 2] for i in range(20_001)]
        teile = teile[::2] + [list(reversed(t)) for t in teile[1::2]]
        ringe = geometry.stitch_rings({"members": [{"role": "outer", "geometry": t} for t in teile]})
        self.assertLess(time.perf_counter() - t0, 5.0)
        self.assertEqual(len(ringe), 1)
        self.assertTrue(ringe[0][1])
        self.assertEqual(len(ringe[0][0]), len(kette))

    def test_wahl_wie_bisher(self):
        """An einem Knoten mit drei Stücken gewinnt das erste in der Liste, und
        vorn anhängen geht wie hinten — dieselben Ringe wie bis 2.1.0."""
        p = [{"lat": 0.0, "lon": float(i)} for i in range(6)]
        rel = {"members": [{"role": "outer", "geometry": [p[0], p[1]]},
                           {"role": "outer", "geometry": [p[2], p[1]]},       # endet, wo die Kette endet
                           {"role": "outer", "geometry": [p[1], p[3]]},       # fängt dort an — später in der Liste
                           {"role": "outer", "geometry": [p[4], p[0]]},       # vorn anhängen
                           {"role": "outer", "geometry": [p[2], p[4]]}]}
        ringe = geometry.stitch_rings(rel)
        # 0→1, dann Stück 1 (umgedreht, vor Stück 2), dann Stück 3 vorn (vor Stück 4), dann Stück 4
        self.assertEqual([[q["lon"] for q in kette] for kette, _ in ringe], [[4.0, 0.0, 1.0, 2.0, 4.0]])
        self.assertTrue(ringe[0][1])

    def test_unsinn_in_der_relation(self):
        rel = {"members": ["x", None, {"role": "outer", "geometry": [{"lat": "a", "lon": 1}, {"lon": 2},
                                                                        {"lat": 0, "lon": 0}, {"lat": 1, "lon": 1},
                                                                        {"lat": 1, "lon": 0}, {"lat": 0, "lon": 0}]}]}
        self.assertEqual(len(geometry.stitch_rings(rel)), 1)
        self.assertEqual(geometry.stitch_rings({"members": None}), [])


class C20_TiefesGeoJSON(unittest.TestCase):
    def test_verschachtelung_ist_ein_lesefehler(self):
        text = '{"features": ' + "[" * 100_000 + "]" * 100_000 + "}"
        self.assertEqual(ingest.parse_geojson(text), [])
        self.assertEqual(ingest.parse_text(text)[0], [])
        # Ein tief verschachtelter Name kostet den Namen, nicht den Punkt
        name = json.loads("[" * 500 + "]" * 500)
        daten = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [3.8, 51.7]}, "properties": {"name": name}}]}
        self.assertEqual(ingest.parse_geojson(json.dumps(daten)), [("", 51.7, 3.8, None)])


class C25_Ortsname(unittest.TestCase):
    def test_nominatim_name_wird_geputzt_und_gekuerzt(self):
        from wingscout.sources import ortsname
        riesig = {"addresstype": "village", "address": {"village": "Dorf\x07" + "x" * 500_000, "country_code": "de"}}
        aus = ortsname.vorschlag_aus(riesig, {})
        self.assertEqual(len(aus["name"]), ingest.MAX_NAME)
        self.assertNotIn("\x07", aus["name"])
        aus = ortsname.vorschlag_aus({"address": {"village": "Ort\ud800", "country_code": "ÄÖ"}}, {})
        self.assertEqual(aus, {"name": "Ort?", "country": ""})

    def test_surrogat_im_zwischenspeicher_ist_kein_absturz(self):
        from wingscout.sources import ortsname
        with tempfile.TemporaryDirectory() as d:
            datei = Path(d) / "ortsnamen.json"
            # Ein alter Eintrag mit Surrogat — er lässt sich nicht als UTF-8 schreiben
            datei.write_text('{"1.0000,1.0000": {"name": "X\\ud800", "country": ""}}', encoding="utf-8")
            antwort = {"addresstype": "village", "address": {"village": "Neu\ud800", "country_code": "nl"}}
            with mock.patch.object(ortsname, "AKTIV", True), mock.patch.object(ortsname, "CACHE_DATEI", datei), \
                    mock.patch.object(ortsname, "_hole", return_value=antwort):
                self.assertEqual(ortsname.vorschlag(51.7, 3.8), {"name": "Neu?", "country": "NL"})
            datei.write_text("[1, 2]", encoding="utf-8")
            with mock.patch.object(ortsname, "AKTIV", True), mock.patch.object(ortsname, "CACHE_DATEI", datei), \
                    mock.patch.object(ortsname, "_hole", return_value=antwort):
                self.assertEqual(ortsname.vorschlag(51.7, 3.8)["name"], "Neu?")


@unittest.skipUnless(POSIX, "Dateirechte gibt es so nur auf POSIX")
class A3_Dateirechte(unittest.TestCase):
    """`schreibe_atomar` legte die Nachbardatei mit den Standardrechten an —
    nach „Übernehmen“ im Tagebuch war config.yaml nicht mehr 0600 (S13)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ordner = Path(self.tmp.name)
        self.maske = os.umask(0o022)           # die übliche — wie im Terminal

    def tearDown(self):
        os.umask(self.maske)
        self.tmp.cleanup()

    @staticmethod
    def modus(pfad: Path) -> int:
        return stat.S_IMODE(pfad.stat().st_mode)

    def test_config_bleibt_0600_nach_wing_setzen(self):
        from wingscout import tagebuch
        from wingscout.config import ensure_config
        shutil.copy(CONFIG, self.ordner / "config.example.yaml")
        pfad = ensure_config(self.ordner / "config.yaml")
        self.assertEqual(self.modus(pfad), 0o600)
        wing = load_config(pfad)["quiver"]["wings"][0]
        tagebuch.wing_setzen(pfad, wing["size"], wing["low"] + 1, wing["high"])
        self.assertEqual(self.modus(pfad), 0o600)
        self.assertEqual(sorted(x.name for x in self.ordner.iterdir()), ["config.example.yaml", "config.yaml"])

    def test_rechte_der_alten_datei_neue_nur_fuer_den_besitzer(self):
        alt = self.ordner / "katalog.yaml"
        alt.write_text("- id: a\n", encoding="utf-8")
        os.chmod(alt, 0o640)
        spotedit.schreibe_atomar(alt, "- id: b\n")
        self.assertEqual((self.modus(alt), alt.read_text(encoding="utf-8")), (0o640, "- id: b\n"))
        neu = self.ordner / "neu.json"
        spotedit.schreibe_atomar(neu, "{}")
        self.assertEqual(self.modus(neu), 0o600)

    def test_rest_eines_abgebrochenen_laufs_vererbt_nichts(self):
        ziel = self.ordner / "config.yaml"
        ziel.write_text("a: 1\n", encoding="utf-8")
        os.chmod(ziel, 0o600)
        rest = self.ordner / "config.yaml.neu"
        rest.write_text("halb", encoding="utf-8")
        os.chmod(rest, 0o644)
        spotedit.schreibe_atomar(ziel, "a: 2\n")
        self.assertEqual((self.modus(ziel), ziel.read_text(encoding="utf-8")), (0o600, "a: 2\n"))
        self.assertFalse(rest.exists())

    def test_fehler_beim_schreiben_laesst_nichts_liegen(self):
        ziel = self.ordner / "spots.yaml"
        ziel.write_text("- id: a\n", encoding="utf-8")
        with self.assertRaises(UnicodeEncodeError):
            spotedit.schreibe_atomar(ziel, "- id: \ud800\n")
        self.assertEqual(ziel.read_text(encoding="utf-8"), "- id: a\n")
        self.assertEqual([x.name for x in self.ordner.iterdir()], ["spots.yaml"])

    def test_programm_setzt_die_maske_main_nicht(self):
        gesehen = []
        with mock.patch.object(cli, "main", side_effect=lambda argv=None: gesehen.append(os.umask(0o077)) or 0):
            self.assertEqual(cli.programm(["--demo"]), 0)
        self.assertEqual(gesehen, [0o077])
        self.assertEqual(os.umask(0o022), 0o022, "danach gilt wieder die alte Maske")
        # main() selbst — Tests, Oberfläche — lässt die Maske, wie sie ist
        with mock.patch.object(cli, "run_search", side_effect=lambda *a: gesehen.append(os.umask(0o022)) or 0):
            cli.main(["--demo", "--config", str(CONFIG), "--quiet"])
        self.assertEqual(gesehen[-1], 0o022)
        self.assertIn("from wingscout.cli import programm", (ROOT / "run.py").read_text(encoding="utf-8"))
        self.assertIn("raise SystemExit(programm())", (ROOT / "wingscout" / "cli.py").read_text(encoding="utf-8"))

    def test_alter_report_wird_nur_fuer_den_besitzer(self):
        """Ein Report aus einem früheren Lauf mit 0644: der nächste Lauf als
        Programm lässt ihn nur noch für den Besitzer lesbar."""
        ziel = self.ordner / "r.html"
        ziel.write_text("alt", encoding="utf-8")
        os.chmod(ziel, 0o644)
        code = cli.programm(["--demo", "--days", "1", "--radius", "300", "--out", str(ziel), "--quiet",
                             "--config", str(CONFIG), "--spots", str(SPOTS),
                             "--geometry", str(self.ordner / "keine.json")])
        self.assertEqual(code, 0)
        self.assertEqual(self.modus(ziel), 0o600)
        self.assertEqual(os.umask(0o022), 0o022)


if __name__ == "__main__":
    unittest.main()
