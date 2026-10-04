"""Die Datenquellen gegen kaputte, böse oder bloß seltsame Antworten — Review
vom 04.10.2026, Befunde C4 bis C26, jeder als Test, der den alten Fehler
nachstellt und den neuen Stand festhält. Alles ohne Netz: die Antworten sind
untergeschoben, der Testserver ist höchstens 127.0.0.1."""
from __future__ import annotations
import gzip
import json
import math
import os
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from wingscout import modellvergleich, tagebuch, xmlsicher
from wingscout.sources import (ensemble, highres, historisch, marine, meteoalarm, netz, openmeteo,
                               overpass, routing, stationen)

# tests/test_sources.py ersetzt meteoalarm.fetch_country für seine Tests und
# stellt es nicht zurück — hier zählt die echte Funktion.
FETCH_COUNTRY = meteoalarm.fetch_country


class Antwort:
    """Ein Ersatz für die Antwort von `urlopen`: liest in Stücken wie
    `HTTPResponse.read1`, mit `length` (Rest laut Content-Length)."""

    def __init__(self, daten: bytes = b"", length=None, pause_s: float = 0.0, status: int = 200):
        self._daten, self._pos = daten, 0
        self.length = length                    # größer als die Daten: die Verbindung reißt vorher ab
        self.pause_s = pause_s
        self.status = status
        self.gewuenscht: list[int] = []

    def read1(self, n=-1):
        self.gewuenscht.append(n)
        if self.pause_s:
            time.sleep(self.pause_s)
        stueck = self._daten[self._pos:self._pos + (n if n >= 0 else len(self._daten))]
        self._pos += len(stueck)
        if self.length is not None:
            self.length -= len(stueck)
        return stueck

    def read(self, n=-1):                       # wer read() mit Grenze ruft, bekommt den Fehler zu sehen
        raise AssertionError("lies() muss stückweise lesen")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def json_antwort(objekt) -> Antwort:
    roh = json.dumps(objekt).encode("utf-8")
    return Antwort(roh, length=len(roh))


ZEITEN = [f"2026-10-04T{h:02d}:00" for h in range(6)]


def block(**hourly):
    h = {"time": list(ZEITEN), "wind_speed_10m": [16.0] * 6, "wind_gusts_10m": [19.0] * 6,
         "wind_direction_10m": [250.0] * 6}
    h.update(hourly)
    return {"utc_offset_seconds": 7200, "hourly": h,
            "daily": {"time": ["2026-10-04"], "sunrise": ["2026-10-04T07:30"], "sunset": ["2026-10-04T19:00"]}}


def spot(sid, lat=51.76, lon=3.85, **mehr):
    return dict({"id": sid, "name": sid.upper(), "lat": lat, "lon": lon, "country": "NL", "water_body": "sea"},
                **mehr)


# ── C4: Open-Meteo ───────────────────────────────────────────────────────────

class OpenMeteoBereinigen(unittest.TestCase):
    """C4: NaN, Infinity, 1e999 und Text kamen bis in die Bewertung und
    kippten dort die ganze Suche."""

    def test_unsinnswerte_werden_none_und_reihen_passen_zur_zeit(self):
        b = block(wind_speed_10m=[float("nan"), float("inf"), -float("inf"), "warm", True, 12],
                  wind_gusts_10m=[1.0, 2.0],                        # zu kurz
                  wind_direction_10m=[1.0] * 9,                     # zu lang
                  cape=None)                                        # ganz ohne Werte
        sauber, grund = openmeteo.bereinigen(b)
        self.assertEqual(grund, "")
        h = sauber["hourly"]
        self.assertEqual(h["wind_speed_10m"], [None, None, None, None, None, 12])
        self.assertEqual(h["wind_gusts_10m"], [1.0, 2.0, None, None, None, None])
        self.assertEqual(len(h["wind_direction_10m"]), 6)
        self.assertEqual(h["cape"], [None] * 6)
        self.assertEqual(sauber["daily"]["sunrise"], ["2026-10-04T07:30"])

    def test_1e999_aus_dem_json(self):
        roh = json.dumps([block()]).replace("16.0", "1e999", 1)
        sauber, _ = openmeteo.bereinigen(json.loads(roh)[0])
        self.assertIsNone(sauber["hourly"]["wind_speed_10m"][0])
        self.assertEqual(sauber["hourly"]["wind_speed_10m"][1], 16.0)

    def test_gueltige_daten_bleiben_wie_sie_sind(self):
        b = block(weather_code=[1, 2, 3, 61, 0, 95])
        sauber, grund = openmeteo.bereinigen(json.loads(json.dumps(b)))
        self.assertEqual((sauber, grund), (b, ""))

    def test_kaputter_block_faellt_weg(self):
        for kaputt, grund in (([], "list"), ({"hourly": []}, "hourly"),
                              (block(time=ZEITEN[:3] + ["kaputt"] + ZEITEN[4:]), "hourly"),
                              (block(time=[[1]] + ZEITEN[1:]), "hourly"),
                              (block(wind_speed_10m="x"), "hourly"),
                              (dict(block(), utc_offset_seconds=1e300), "utc_offset_seconds"),
                              (dict(block(), utc_offset_seconds=99 * 3600), "utc_offset_seconds"),
                              (dict(block(), utc_offset_seconds="7200"), "utc_offset_seconds")):
            with self.subTest(kaputt=str(kaputt)[:60]):
                self.assertEqual(openmeteo.bereinigen(kaputt), (None, grund))
        # Ohne Versatz (null): score.py rechnet mit der Länge — kein Grund zum Verwerfen
        self.assertIsNotNone(openmeteo.bereinigen(dict(block(), utc_offset_seconds=None))[0])
        # Unlesbares daily fällt allein weg
        sauber, _ = openmeteo.bereinigen(dict(block(), daily="kaputt"))
        self.assertNotIn("daily", sauber)

    def test_fetch_verwirft_den_block_mit_protokoll_und_behaelt_den_anderen(self):
        gut, boese = block(), block(time=["kaputt"] * 6)
        zeilen = []
        with mock.patch.object(urllib.request, "urlopen", return_value=json_antwort([boese, gut])):
            out = openmeteo.fetch([spot("a"), spot("b")], 1, timezone="Europe/Berlin", log=zeilen.append)
        self.assertEqual(list(out), ["b"])
        self.assertTrue(any("Unerwartete Antwort von Open-Meteo" in z and "A (hourly)" in z for z in zeilen), zeilen)

    def test_retry_after_wird_beachtet(self):
        """C18: ein 429 mit Retry-After wartet so lange wie verlangt — höchstens eine Minute."""
        aufrufe, gewartet = [], []

        def urlopen(req, timeout=None):
            aufrufe.append(req.headers.get("User-agent"))
            if len(aufrufe) == 1:
                raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {"Retry-After": "7"}, None)
            if len(aufrufe) == 2:
                raise urllib.error.HTTPError(req.full_url, 503, "Busy", {"Retry-After": "86400"}, None)
            return json_antwort({"hourly": {"time": []}})
        with mock.patch.object(urllib.request, "urlopen", urlopen), \
                mock.patch.object(openmeteo, "RETRY_WAIT", (0, 0, 0)), \
                mock.patch.object(openmeteo.time, "sleep", gewartet.append):
            openmeteo._get("https://api.open-meteo.com/v1/forecast?x=1")
        self.assertEqual(gewartet, [7, openmeteo.RETRY_AFTER_MAX])
        self.assertEqual(aufrufe[0], netz.USER_AGENT)


class MarineHighresEnsemble(unittest.TestCase):
    def test_marine_kaputter_block_und_unsinnswerte(self):
        h = {"time": ZEITEN, "sea_surface_temperature": [14.0, "kalt", float("nan"), 15.0, None, 1e999],
             "wave_height": [0.5] * 6, "sea_level_height_msl": [0.1] * 6}
        zeilen = []
        with mock.patch.object(urllib.request, "urlopen", return_value=json_antwort([{"hourly": h}, 1])):
            out = marine.fetch([spot("a"), spot("b")], 1, timezone="Europe/Berlin", log=zeilen.append)
        self.assertEqual(list(out), ["a"])
        self.assertEqual(out["a"]["sst"], {ZEITEN[0]: 14.0, ZEITEN[3]: 15.0})
        self.assertTrue(any("Marine, B" in z for z in zeilen), zeilen)

    def test_highres_kaputte_antwort_wird_nicht_als_absage_gemerkt(self):
        """H1/H2: ein Block, der kein Objekt ist, oder Wind als Text — weder
        Absturz noch „Modell deckt den Spot nicht“."""
        ort = spot("torbole", 45.87, 10.87, country="IT")
        for kaputt in (1, {"hourly": {"time": ZEITEN, "wind_speed_10m": "x"}}):
            with self.subTest(kaputt=kaputt), tempfile.TemporaryDirectory() as d, \
                    mock.patch.object(highres, "_anfrage", return_value=[kaputt]):
                zeilen = []
                ergebnis, _ = highres.hole([ort], 2, d, log=zeilen.append)
                self.assertEqual(ergebnis, {})
                self.assertNotIn("torbole", highres.lade_cache(d), "nichts gemerkt — nächster Lauf fragt neu")
                self.assertTrue(any("unerwartete Antwort" in z for z in zeilen), zeilen)
        # Text in einer sonst guten Reihe wird None, der Rest kommt durch
        gut = {"hourly": {"time": ZEITEN, "wind_speed_10m": [18.0, "x", float("nan"), 18.0, 18.0, 18.0]}}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(highres, "_anfrage", return_value=[gut]):
            ergebnis, _ = highres.hole([ort], 2, d)
        self.assertEqual(ergebnis["torbole"][1]["wind_speed_10m"], [18.0, None, None, 18.0, 18.0, 18.0])

    def test_ensemble_laenge_und_zeiten(self):
        """C19: zwei Einträge für drei Orte landeten per zip() beim falschen Spot."""
        eintrag = {"hourly": {"time": ZEITEN, "wind_speed_10m_member01": [15.0, float("nan"), "x", 1e999, 15.0, 15.0]}}
        zeilen = []
        with mock.patch.object(urllib.request, "urlopen", return_value=json_antwort([eintrag, eintrag])):
            with self.assertRaises(ensemble.EnsembleError):
                ensemble.fetch([spot("a"), spot("b"), spot("c")], 1, timezone="Europe/Berlin", log=zeilen.append)
        self.assertTrue(any("2 Blöcke für 3 Spots" in z for z in zeilen), zeilen)
        kaputt = {"hourly": {"time": [[1]] + ZEITEN[1:], "wind_speed_10m_member01": [15.0] * 6}}
        with mock.patch.object(urllib.request, "urlopen", return_value=json_antwort([kaputt, eintrag])):
            out = ensemble.fetch([spot("a"), spot("b")], 1, timezone="Europe/Berlin")
        self.assertEqual(list(out), ["b"])
        self.assertEqual(out["b"]["members"], [[15.0, None, None, None, 15.0, 15.0]])
        stats = ensemble.window_stats(out["b"], ZEITEN, 12.0, 14.0)
        self.assertEqual(stats["members"], 1)
        self.assertTrue(all(math.isfinite(v) for v in stats.values()))

    def test_ensemble_hat_einen_absender(self):
        gesehen = []

        def urlopen(req, timeout=None):
            gesehen.append(req.headers.get("User-agent"))
            return json_antwort({"hourly": {"time": ZEITEN, "wind_speed_10m": [15.0] * 6}})
        with mock.patch.object(urllib.request, "urlopen", urlopen):
            ensemble.fetch([spot("a")], 1, timezone="Europe/Berlin")
        self.assertEqual(gesehen, [netz.USER_AGENT])
        self.assertRegex(netz.USER_AGENT, r"^Wingfoilscout/\d+\.\d+\.\d+ \(\+https://github\.com/DarkPirateGo/wingfoilscout\)$")


class Historisch(unittest.TestCase):
    def test_archiv_wird_bereinigt_und_kaputter_cache_neu_geholt(self):
        ort = spot("a")
        with tempfile.TemporaryDirectory() as d, mock.patch.object(historisch, "CACHE_DIR", Path(d)):
            with mock.patch.object(historisch, "_get", return_value=block(wind_speed_10m=[float("nan")] * 6)):
                daten = historisch.hole(ort, "2026-09-01", "2026-09-02", ["icon"], "Europe/Berlin")
            self.assertEqual(daten["hourly"]["wind_speed_10m"], [None] * 6)
            for datei in Path(d).glob("hist_*.json"):
                datei.write_text('{"hourly": {"time": [', encoding="utf-8")      # abgeschnitten
            with mock.patch.object(historisch, "_get", return_value=block()) as neu:
                daten = historisch.hole(ort, "2026-09-01", "2026-09-02", ["icon"], "Europe/Berlin")
            neu.assert_called_once()
            self.assertEqual(daten["hourly"]["wind_speed_10m"][0], 16.0)
            with mock.patch.object(historisch, "_get", return_value=dict(block(), utc_offset_seconds=1e300)):
                with self.assertRaises(historisch.HistorischError):
                    historisch.hole(ort, "2026-08-01", "2026-08-02", ["icon"], "Europe/Berlin")


# ── C4 + C12: Routing ────────────────────────────────────────────────────────

class Routing(unittest.TestCase):
    def test_nur_fahrzeiten_die_es_geben_kann(self):
        spots = [{"id": k, "lat": 51.0 + i / 10, "lon": 4.0} for i, k in enumerate("abcdefg")]
        antwort = {"code": "Ok",
                   "durations": [[0, 3600, float("nan"), float("inf"), -5, 48 * 3600, "x", 7200]],
                   "distances": [[0, 60000, 1, 1, 1, 1, 1, float("nan")]]}
        gefragt = []
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "routes.json"
            with mock.patch.object(routing, "_ask", lambda coords: gefragt.append(coords) or antwort):
                zeiten = routing.drive_times({"lat": 53.55234, "lon": 9.98876}, spots, pfad)
            self.assertEqual(zeiten, {"a": {"h": 1.0, "km": 60.0}})
            roh = pfad.read_text(encoding="utf-8")
            self.assertNotIn("NaN", roh)
            self.assertNotIn("Infinity", roh)
        # C12: der Startpunkt geht so grob raus wie der Cacheschlüssel
        self.assertTrue(gefragt[0].startswith("9.99,53.55;"), gefragt[0])
        self.assertNotIn("53.55234", gefragt[0])

    def test_vergifteter_oder_kaputter_cache_wird_neu_geroutet(self):
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "routes.json"
            pfad.write_text('{"51.74,3.83": {"a": {"h": NaN, "km": 63.0, "bei": [51.44, 4.21]}, '
                            '"b": {"h": 1.5, "km": 90.0, "bei": [52.0, 4.0]}}, "x": [1]}', encoding="utf-8")
            self.assertEqual(set(routing.load_cache(pfad)["51.74,3.83"]), {"b"})
            self.assertNotIn("x", routing.load_cache(pfad))
            pfad.write_text('{"51.74,3.83": {"a": ', encoding="utf-8")
            self.assertEqual(routing.load_cache(pfad), {})


# ── C5: Messwerte ────────────────────────────────────────────────────────────

class Messwerte(unittest.TestCase):
    """C5: NaN, Unendlich, Negatives und Unsinn aus den Stationsdiensten
    gingen bis in modellguete.json — und dort machte JSON.parse im Browser
    die Rückblick-Seite kaputt."""

    def test_dwd(self):
        text = ("STATIONS_ID;MESS_DATUM;QN_3;F;D;eor\n1;2026100112;3;nan;250;eor\n1;2026100113;3;inf;250;eor\n"
                "1;2026100114;3;-3;250;eor\n1;2026100115;3;80;250;eor\n1;2026100116;3;5.0;nan;eor\n")
        self.assertEqual(stationen.dwd_produkt(text), {"2026-10-01T16:00": {"kn": 9.7, "dir": None}})
        jetzt = ("STATIONS_ID;MESS_DATUM;QN;FF_10;DD_10;eor\n"
                 + "".join(f"1;2026100112{m:02d};1;{w};90;eor\n" for m, w in zip(range(0, 60, 10),
                                                                              ("nan", "inf", 5, 5, 5, -1))))
        st = stationen.dwd_now_produkt(jetzt)
        self.assertAlmostEqual(st["2026-10-01T12:00"]["kn"], 5 * stationen.MS_ZU_KN, places=1)

    def test_knmi(self):
        kopf, st = stationen.knmi_antwort("# 267:  nan  52.898  -1.30  STAVOREN\n# STN,YYYYMMDD,HH,DD,FH,FX\n"
                                          "267,20261001,13,250,-500,0\n267,20261001,14,250,nan,0\n"
                                          "267,20261001,15,250,60,0\n267,20261001,99,250,60,0\n")
        self.assertEqual(kopf, {}, "eine Lage mit NaN ersetzt die bekannte nicht")
        self.assertEqual(list(st), ["2026-10-01T14:00"])

    def test_geosphere_windguru_frankreich_rws_dmi(self):
        geo = json.loads('{"timestamps": ["2026-10-01T12:00+00:00", "2026-10-01T13:00+00:00"],'
                         '"features": [{"properties": {"parameters": {"ff": {"data": [1e999, 4.0]},'
                         '"dd": {"data": [90, NaN]}}}}]}')
        self.assertEqual(stationen.geosphere_antwort(geo), {"2026-10-01T13:00": {"kn": 7.8, "dir": None}})
        wg = stationen.windguru_antwort({"unixtime": [1790000000, 1790003600, 10 ** 17, 1790007200],
                                         "wind_avg": ["nan", 9999, 5, "12.5"], "wind_direction": [1, 2, 3, "x"]})
        self.assertEqual(list(wg.values()), [{"kn": 12.5, "dir": None}], "C21: 10**17 kostet nur seine Zeile")
        _, fenster = stationen.fr_lesen(["NUM_POSTE;NOM_USUEL;LAT;LON;AAAAMMJJHH;FF;DD",
                                         "29075001;BREST;48.44;-4.41;2026091712;nan;250",
                                         "29075001;BREST;48.44;-4.41;2026091713;6.2;inf",
                                         "29999001;NIRGENDS;nan;-4.41;2026091713;6.2;250"],
                                        "2026-09-17", "2026-09-17")
        self.assertEqual(fenster, {"29075001": {"2026-09-17T13:00": {"kn": 12.1, "dir": None}}})
        rws = {"WaarnemingenLijst": [{"MetingenLijst": [
            {"Tijdstip": "2026-10-01T12:00:00+00:00", "Meetwaarde": {"Waarde_Numeriek": v}} for v in (5.0, 80.0)]}]}
        self.assertEqual([w for _, w in stationen.rws_werte(rws)], [5.0])
        self.assertEqual(stationen._mittel_je_stunde([(stationen.datetime(2026, 10, 1, 12, m), w, 90.0)
                                                      for m, w in ((0, float("nan")), (10, 4.0), (20, 4.0))]), {},
                         "ein NaN zählt nicht als dritter Wert")

    def test_summen_ueberspringen_und_gedaechtnis_bleibt_json(self):
        vorhersage = {"2026-10-01T12:00": (14.0, 250.0), "2026-10-01T13:00": (15.0, float("nan")),
                      "2026-10-01T14:00": (float("inf"), 250.0)}
        messung = {"2026-10-01T12:00": (float("nan"), 250.0), "2026-10-01T13:00": (13.0, 250.0),
                   "2026-10-01T14:00": (13.0, 250.0)}
        s = modellvergleich.summen(vorhersage, messung)
        self.assertEqual((s["n"], s["fehler"], s["richtung_n"]), (1, 2.0, 0))
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "modellguete.json"
            # eine Datei aus der Zeit davor, mit NaN darin
            pfad.write_text('{"version": 1, "spots": {"x": {"tage": {"2026-09-01": {"station": "1", "km": NaN, '
                            '"m": {"icon": {"n": 3, "fehler": NaN, "betrag": 1.0}, "gfs": {"n": 2, "fehler": 1.0, '
                            '"betrag": 1.0}}}}}}}', encoding="utf-8")
            geladen = modellvergleich.gedaechtnis_laden(pfad)
            tag = geladen["spots"]["x"]["tage"]["2026-09-01"]
            self.assertEqual(list(tag["m"]), ["gfs"])
            self.assertIsNone(tag["km"])
            ergebnis = {"spots": [{"id": "x", "name": "X", "station": {"id": "1", "km": float("nan")},
                                   "vergleich": {"tage": {"icon": {"2026-10-01": s},
                                                          "ecmwf": {"2026-10-01": dict(s, betrag=float("inf"))}}}}]}
            daten = modellvergleich.merken(ergebnis, pfad)
            roh = pfad.read_text(encoding="utf-8")
            json.loads(roh, parse_constant=lambda c: self.fail(f"{c} in modellguete.json"))
            self.assertNotIn("ecmwf", daten["spots"]["x"]["tage"]["2026-10-01"]["m"])
            self.assertTrue(math.isfinite(modellvergleich.auswerten(daten)["modelle"][0]["masse"]["mae"]))

    def test_tagebuch_mittel(self):
        self.assertEqual(tagebuch._mittel([10.0, float("nan"), None, float("inf"), "x", True, 12]), 11.0)
        self.assertIsNone(tagebuch._mittel([float("nan")]))


# ── C6: Entpacken ────────────────────────────────────────────────────────────

DWD_TEXT = "STATIONS_ID;MESS_DATUM;QN_3;F;D;eor\n1;2026100112;3;5.0;90;eor\n"
DWD_STUNDE = {"2026-10-01T12:00": {"kn": 9.7, "dir": 90.0}}


def dwd_zip(pfad: Path, verfahren=zipfile.ZIP_DEFLATED, text: str = DWD_TEXT) -> Path:
    with zipfile.ZipFile(pfad, "w", verfahren) as z:
        z.writestr("produkt_ff_stunde_x.txt", text)
    return pfad


def dwd_lesen(pfad: Path) -> dict:
    return stationen.dwd_produkt(stationen._zip_zeilen(pfad, "produkt_ff_stunde", "DWD"))


class Entpacken(unittest.TestCase):
    def test_zip_grenze_und_kaputtes_zip(self):
        self.assertLessEqual(stationen.ZIP_MITGLIED_MAX, 32 * 1024 * 1024)
        with tempfile.TemporaryDirectory() as d:
            pfad = dwd_zip(Path(d) / "dwd_00001.zip")
            zeilen = stationen._zip_zeilen(pfad, "produkt_ff_stunde", "DWD")
            self.assertFalse(isinstance(zeilen, (str, list)), "ein Strom, kein ganzer Text")
            self.assertEqual(stationen.dwd_produkt(zeilen), DWD_STUNDE)
            with mock.patch.object(stationen, "ZIP_MITGLIED_MAX", 10):
                with self.assertRaises(stationen.StationError) as cm:
                    dwd_lesen(pfad)
            self.assertIn("entpackt größer als", str(cm.exception))
            self.assertFalse(pfad.exists(), "auch ein zu großes ZIP wird verworfen und neu geholt")
            # Schon das ZIP selbst: sein Verzeichnis liest `zipfile` vor jeder Prüfung ganz ein
            self.assertLessEqual(stationen.ZIP_DATEI_MAX, 16 * 1024 * 1024)
            dwd_zip(pfad, zipfile.ZIP_STORED, DWD_TEXT + "1;2026100113;3;5.0;90;eor\n" * 50_000)
            with mock.patch.object(stationen, "ZIP_DATEI_MAX", 1024 * 1024), \
                    mock.patch.object(zipfile, "ZipFile", side_effect=AssertionError("geöffnet")), \
                    self.assertRaises(stationen.StationError) as cm:
                dwd_lesen(pfad)
            self.assertIn("> 1 MB", str(cm.exception))
            self.assertFalse(pfad.exists())
            dwd_zip(pfad)
            pfad.write_bytes(pfad.read_bytes()[:40])                     # abgeschnitten
            with self.assertRaises(stationen.StationError):
                dwd_lesen(pfad)
            self.assertFalse(pfad.exists(), "das kaputte ZIP wird verworfen und beim nächsten Mal neu geholt")

    def test_nur_ohne_kompression_oder_mit_deflate(self):
        """Nachprüfung vom 04.10.2026: BZIP2 und LZMA entpackt `zipfile` je
        Lesevorgang ohne Grenze, und die Größe im Kopf ist nur behauptet — 1,2 KB
        BZIP2 mit „1000 Bytes“ im Kopf wurden zu 1 GB im Speicher. Solche
        Mitglieder (und verschlüsselte) werden gar nicht erst geöffnet."""
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "dwd_00001.zip"
            for verfahren, name in ((zipfile.ZIP_BZIP2, "BZIP2"), (zipfile.ZIP_LZMA, "LZMA")):
                with self.subTest(name):
                    dwd_zip(pfad, verfahren)
                    with mock.patch.object(zipfile.ZipFile, "open", side_effect=AssertionError("geöffnet")), \
                            self.assertRaises(stationen.StationError) as cm:
                        dwd_lesen(pfad)
                    self.assertIn(name, str(cm.exception))
                    self.assertFalse(pfad.exists(), "verworfen — beim nächsten Mal neu geholt")
            # verschlüsselt: Bit 0 der Flags im zentralen Verzeichnis
            roh = bytearray(dwd_zip(pfad).read_bytes())
            zentral = roh.rindex(b"PK\x01\x02")
            roh[zentral + 8] |= 0x01
            pfad.write_bytes(bytes(roh))
            with self.assertRaises(stationen.StationError) as cm:
                dwd_lesen(pfad)
            self.assertIn("flag_bits 0x1", str(cm.exception))
            for verfahren in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                with self.subTest(verfahren=verfahren):
                    self.assertEqual(dwd_lesen(dwd_zip(pfad, verfahren)), DWD_STUNDE)
                    self.assertEqual(stationen._zip_text(pfad, "produkt_ff_stunde", "DWD"), DWD_TEXT)

    def test_auch_deflate_liest_zeilen_mit_grenze(self):
        """Eine einzige Zeile ohne Umbruch, entpackt 24 MB — unter der Grenze
        fürs ganze Mitglied — kam bis 2.1.1 als ein Stück in den Speicher."""
        import tracemalloc
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "dwd_00001.zip"
            with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as z, \
                    z.open("produkt_ff_stunde_x.txt", "w") as f:
                f.write(DWD_TEXT.splitlines(keepends=True)[0].encode())
                for _ in range(24):
                    f.write(b"0" * (1024 * 1024))
            lief_schon = tracemalloc.is_tracing()
            if not lief_schon:
                tracemalloc.start()
            try:
                tracemalloc.reset_peak()
                vorher = tracemalloc.get_traced_memory()[0]
                with self.assertRaises(stationen.StationError) as cm:
                    dwd_lesen(pfad)
                spitze = tracemalloc.get_traced_memory()[1] - vorher
            finally:
                if not lief_schon:
                    tracemalloc.stop()
            self.assertIn("Zeile 2", str(cm.exception))
            self.assertLess(spitze, 4 * 1024 * 1024, "höchstens zwei Stücke, nicht die ganze Zeile")
            self.assertFalse(pfad.exists())

    def test_dwd_stundenwerte_mit_deflate_wie_vom_dwd(self):
        """Der ganze Weg einer DWD-Station, mit dem ZIP, wie der DWD es packt."""
        with tempfile.TemporaryDirectory() as d, mock.patch.object(stationen, "CACHE_DIR", Path(d)), \
                mock.patch.object(stationen, "_get", side_effect=stationen.StationError("kein Netz")):
            dwd_zip(Path(d) / "dwd_00001.zip")
            obs = stationen.dwd_stunden({"id": "00001", "name": "A", "lat": 54.5, "lon": 11.0},
                                        "2026-10-01", "2026-10-01")
        self.assertEqual(obs["stunden"], DWD_STUNDE)

    def test_meteo_france_zeilen_und_gesamtgroesse_begrenzt(self):
        import io
        lang = b"NUM_POSTE;NOM_USUEL\n" + b"x" * 5000 + b"\nnoch eine\n"
        with self.assertRaises(stationen.StationError) as cm:
            list(stationen._zeilen_begrenzt(io.BytesIO(lang), "fr_29.csv.gz", zeile_max=1000))
        self.assertIn("Zeile 2", str(cm.exception))
        with self.assertRaises(stationen.StationError):          # ohne Umbruch bis zum Ende
            list(stationen._zeilen_begrenzt(io.BytesIO(b"x" * 300_000), "fr_29.csv.gz", zeile_max=1000))
        viel = b"a;b\n" * 100_000
        with self.assertRaises(stationen.StationError):
            list(stationen._zeilen_begrenzt(io.BytesIO(viel), "fr_29.csv.gz", gesamt_max=200_000))
        self.assertEqual(list(stationen._zeilen_begrenzt(io.BytesIO(b"a;b\r\nc;d"), "x")), ["a;b", "c;d"])

    def test_meteo_france_datei_als_strom_kaputte_wird_verworfen(self):
        with tempfile.TemporaryDirectory() as d:
            datei = Path(d) / "fr_29.csv.gz"
            datei.write_bytes(gzip.compress(b"NUM_POSTE;NOM_USUEL;LAT;LON;AAAAMMJJHH;FF;DD\n"
                                            b"29075001;BREST;48.44;-4.41;2026091712;6.2;250\n"))
            st, fenster = stationen._fr_lesen_datei(datei, "2026-09-17", "2026-09-17")
            self.assertEqual([s["id"] for s in st], ["29075001"])
            datei.write_bytes(datei.read_bytes()[:30])
            with self.assertRaises(stationen.StationError):
                stationen._fr_lesen_datei(datei, "2026-09-17", "2026-09-17")
            self.assertFalse(datei.exists())


# ── C7, C8: Adressen ─────────────────────────────────────────────────────────

class Adressen(unittest.TestCase):
    def test_nur_die_datei_von_meteo_france(self):
        gut = stationen.FR_DATEIEN + "H_29_latest-2025-2026.csv.gz"
        self.assertTrue(stationen.fr_url_gilt(gut, "29"))
        self.assertTrue(stationen.fr_url_gilt(stationen.FR_DATEIEN + "H_2A_latest-2025-2026.csv.gz", "2A"))
        for boese in ("http://127.0.0.1:8765/beliebig?x=/H_29_latest-.csv.gz",
                      "file:///etc/hostname#/H_29_latest-.csv.gz",
                      "https://evil.example/H_29_latest-2025-2026.csv.gz",
                      stationen.FR_DATEIEN + "../../x/H_29_latest-2025-2026.csv.gz",
                      stationen.FR_DATEIEN + "H_29_latest-2025-2026.csv.gz?x=1",
                      stationen.FR_DATEIEN + "H_56_latest-2025-2026.csv.gz", None, 7):
            with self.subTest(url=boese):
                self.assertFalse(stationen.fr_url_gilt(boese, "29"))
        self.assertFalse(stationen.fr_url_gilt(stationen.FR_DATEIEN + "H_../_latest-2025-2026.csv.gz", "../"))

    def test_fremde_adresse_aus_data_gouv_und_im_cache(self):
        jahr = date.today().year
        muster = f"{stationen.FR_DATEIEN}H_29_latest-{jahr - 1}-{jahr}.csv.gz"
        api = json.dumps({"data": [{"url": "file:///etc/hostname#/H_29_latest-.csv.gz"},
                                   {"url": "https://evil.example/H_29_latest-2025-2026.csv.gz"}]}).encode()
        with tempfile.TemporaryDirectory() as d, mock.patch.object(stationen, "CACHE_DIR", Path(d)):
            with mock.patch.object(stationen, "_get", return_value=api):
                self.assertEqual(stationen.fr_datei_url("29"), muster)
            (Path(d) / "fr_29_url.txt").write_text("file:///etc/passwd", encoding="utf-8")
            with mock.patch.object(stationen, "_get", side_effect=stationen.StationError("aus")):
                self.assertEqual(stationen.fr_datei_url("29"), muster, "die gemerkte Adresse wird geprüft")

    def test_get_lehnt_ab_bevor_es_fragt(self):
        with mock.patch.object(urllib.request, "urlopen", side_effect=AssertionError("gefragt")):
            for url in ("file:///etc/hostname", "ftp://example.com/x", "data:text/plain,x", "http://example.com/x",
                        "http://127.0.0.1.evil.example/x"):
                with self.subTest(url=url), self.assertRaises(stationen.StationError) as cm:
                    stationen._get(url)
                self.assertIn("https://", str(cm.exception))

    def test_der_opener_oeffnet_nur_https_und_den_eigenen_rechner(self):
        # Die Wächter stecken im global installierten Opener …
        installiert = [type(h) for h in urllib.request._opener.handlers]
        waechter = (netz._NurHttps, netz._NurLokalesHttp, netz._KeineDatei, netz._KeinFtp, netz._KeineDaten)
        for klasse in waechter:
            self.assertIn(klasse, installiert)
        # … geprüft werden sie ohne Proxy aus der Umgebung: ein ALL_PROXY=socks5h://…
        # (manche Sandboxen setzen ihn) leitet die Anfrage vorher um, und urllib
        # kennt socks gar nicht — sie scheitert dann auch, aber mit anderem Grund.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), *waechter)
        for url in ("file:///etc/hostname", "data:text/plain,hallo", "ftp://invalid.invalid/x",
                    "http://invalid.invalid/x"):
            with self.subTest(url=url), self.assertRaises(urllib.error.URLError) as cm:
                opener.open(url, timeout=2)
            self.assertIn("nur https://", str(cm.exception.reason))
        self.assertTrue(netz.erlaubt("https://api.open-meteo.com/v1/forecast"))
        self.assertTrue(netz.erlaubt("http://127.0.0.1:8765/status"))
        self.assertFalse(netz.erlaubt("http://localhost.evil.example/"))
        self.assertFalse(netz.erlaubt("https:///ohne-host"))

    def test_weiterleitungen(self):
        """C8: der Anfang des Texts entschied — http://localhost.evil.example ging durch."""
        h = netz._NurHttps()
        fremd = urllib.request.Request("https://api.open-meteo.com/v1/forecast")
        lokal = urllib.request.Request("http://127.0.0.1:9/x")
        for ziel in ("http://localhost.evil.example/x", "http://127.0.0.1.evil.example/x", "http://127.0.0.1:8765/x",
                     "https://127.0.0.1:8765/x", "https://localhost/x", "ftp://evil.example/x",
                     "file:///etc/passwd", "http://[::1/x"):
            with self.subTest(ziel=ziel), self.assertRaises(urllib.error.HTTPError):
                h.redirect_request(fremd, None, 302, "Found", {}, ziel)
        self.assertEqual(h.redirect_request(fremd, None, 302, "Found", {}, "https://example.org/y").full_url,
                         "https://example.org/y")
        self.assertEqual(h.redirect_request(lokal, None, 302, "Found", {}, "http://localhost:8765/z").full_url,
                         "http://localhost:8765/z")


# ── C9, C11: lies ────────────────────────────────────────────────────────────

class Lesen(unittest.TestCase):
    def test_stueckweise_mit_grenze_und_ankuendigung(self):
        daten = b"x" * (200 * 1024)
        r = Antwort(daten, length=len(daten))
        self.assertEqual(netz.lies(r), daten)
        self.assertTrue(all(0 < n <= netz.STUECK for n in r.gewuenscht), "nie limit+1 auf einmal (C11)")
        with self.assertRaises(ValueError):
            netz.lies(Antwort(b"", length=netz.MAX_ANTWORT + 1))       # schon vor dem ersten Byte
        with self.assertRaises(ValueError):
            netz.lies(Antwort(b"x" * 2000), limit=1000)

    def test_frist_fuer_den_ganzen_koerper(self):
        """C9: das Zeitlimit von urlopen gilt je Lesevorgang — ein Server, der
        tröpfelt, hielt die Abfrage stundenlang offen."""
        r = Antwort(b"x" * 1000, pause_s=0.05)
        def stueckchen(n=-1):
            return Antwort.read1(r, 1)
        r.read1 = stueckchen
        t = time.monotonic()
        with self.assertRaises(TimeoutError):
            netz.lies(r, frist_s=0.3)
        self.assertLess(time.monotonic() - t, 2.0)
        self.assertIsInstance(TimeoutError(), OSError, "jede Quelle behandelt OSError schon als Netzfehler")

    def test_abgerissener_koerper_ist_ein_fehler(self):
        r = Antwort(b"x" * 10, length=1000)
        with self.assertRaises(ConnectionError):
            netz.lies(r)

    def test_mit_echtem_server(self):
        """Derselbe Weg über eine echte Verbindung zu 127.0.0.1: chunked und mit Länge."""
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path == "/chunked":
                    self.send_response(200)
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    for _ in range(3):
                        self.wfile.write(b"5\r\nhallo\r\n")
                    self.wfile.write(b"0\r\n\r\n")
                else:
                    self.send_response(200)
                    self.send_header("Content-Length", "100000")
                    self.end_headers()
                    self.wfile.write(b"y" * 100000)

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            basis = f"http://127.0.0.1:{srv.server_address[1]}"
            with urllib.request.urlopen(basis + "/chunked", timeout=5) as r:
                self.assertEqual(netz.lies(r), b"hallo" * 3)
            with urllib.request.urlopen(basis + "/lang", timeout=5) as r:
                self.assertEqual(len(netz.lies(r)), 100000)
        finally:
            srv.shutdown()
            srv.server_close()


# ── C10: XML ─────────────────────────────────────────────────────────────────

class Xml(unittest.TestCase):
    def test_tiefengrenze(self):
        self.assertIsNone(xmlsicher.lesen("<a>" * 65 + "</a>" * 65))
        self.assertIsNotNone(xmlsicher.lesen("<a>" * 64 + "</a>" * 64))
        self.assertIsNone(xmlsicher.lesen("<feed>" + "<entry>" * 4000 + "</entry>" * 4000 + "</feed>"))
        gpx = ('<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
               '<trkpt lat="51.7" lon="3.8"><ele>1</ele><extensions><x><y>z</y></x></extensions></trkpt>'
               '</trkseg></trk></gpx>')
        self.assertEqual(len(list(xmlsicher.lesen(gpx).iter())), 8)

    def test_meteoalarm_liest_jedes_element_einmal(self):
        """Auch unter der Tiefengrenze rechnete parse_feed quadratisch: 30
        ineinander geschachtelte Einträge mit Parametern über 60 000 Blättern
        kosteten sechs Sekunden für 236 KB. Gezählt wird, wie oft ein Name
        gelesen wird: je Element höchstens fünfmal (Suche nach Einträgen, Gang
        durch seinen Eintrag, Gang durch seinen Parameter) — nicht einmal je
        umgebender Ebene, wie bis 2.1.0."""
        paare, blaetter = 30, 3000
        feed = ("<feed>" + "<entry><title>Yellow T</title><parameter>" * paare + "<a/>" * blaetter
                + "</parameter></entry>" * paare + "</feed>")
        elemente = 1 + paare * 3 + blaetter
        echt, zaehler = meteoalarm._name, []

        def zaehlen(el):
            zaehler.append(1)
            return echt(el)
        with mock.patch.object(meteoalarm, "_name", zaehlen):
            warnungen = meteoalarm.parse_feed(feed)
        self.assertEqual(len(warnungen), paare)
        self.assertLessEqual(len(zaehler), 5 * elemente)

    def test_meteoalarm_kaputter_cache_ohne_netz(self):
        """C14: die Ausnahme in der Ausnahme — eine kaputte Datei und kein Netz."""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "netherlands.json").write_text('[{"level": 3, "ar', encoding="utf-8")
            with mock.patch.object(urllib.request, "urlopen", side_effect=OSError("kein Netz")):
                self.assertEqual(FETCH_COUNTRY("NL", d), [])
            gut = [{"level": 3, "area": "Zeeland", "title": "x"}, {"level": "3"}, "kaputt"]
            (Path(d) / "netherlands.json").write_text(json.dumps(gut), encoding="utf-8")
            with mock.patch.object(urllib.request, "urlopen", side_effect=OSError("kein Netz")):
                self.assertEqual(FETCH_COUNTRY("NL", d), gut[:1])


# ── C14, C20: Zwischenspeicher, Overpass ─────────────────────────────────────

class Zwischenspeicher(unittest.TestCase):
    def test_cache_lesen_und_ablegen(self):
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "x.json"
            self.assertIsNone(netz.cache_lesen(pfad))
            for inhalt in ('{"a": ', "\xff"):
                pfad.write_text(inhalt, encoding="latin-1")
                self.assertIsNone(netz.cache_lesen(pfad), inhalt[:10])
            # Zu tief verschachtelt: bis Python 3.13 scheitert json.loads daran
            # (RecursionError), neuere Versionen auf dem Mac lesen es (sie messen
            # den echten Stapel, und der ist dort 16 MB groß) — beim Prüflauf am
            # 04.10.2026 aufgefallen. Kaputt geht in keinem Fall etwas, und wer
            # eine bestimmte Art erwartet, bekommt None.
            pfad.write_text("[" * 100000 + "]" * 100000, encoding="latin-1")
            self.assertIn(type(netz.cache_lesen(pfad)), (type(None), list))
            self.assertIsNone(netz.cache_lesen(pfad, dict))
            netz.ablegen(pfad, '{"a": 1}')
            self.assertEqual(netz.cache_lesen(pfad, dict), {"a": 1})
            self.assertIsNone(netz.cache_lesen(pfad, list))
            with self.assertRaises(RuntimeError):
                with netz.ablegen_offen(pfad) as fh:
                    fh.write(b'{"halb')
                    raise RuntimeError("Absturz mitten im Schreiben")
            self.assertEqual(netz.cache_lesen(pfad), {"a": 1}, "die alte Fassung bleibt ganz")
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["x.json"], "keine Reste")

    def test_schutzgebiete_abgeschnittener_cache_wird_neu_geholt(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "spot_protected.json").write_text('{"_spot": [51.7, 3.8], "gebiete": [{"na', encoding="utf-8")
            antwort = {"elements": [{"tags": {"name": "Voordelta", "protect_class": "97"}}, "kaputt"]}
            with mock.patch.object(urllib.request, "urlopen", return_value=json_antwort(antwort)), \
                    mock.patch.object(overpass.time, "sleep", lambda *_: None):
                gebiete = overpass.fetch_protected("spot", 51.7, 3.8, cache_dir=d)
            self.assertEqual([g["name"] for g in gebiete], ["Voordelta"])
            self.assertEqual(json.loads((Path(d) / "spot_protected.json").read_text(encoding="utf-8"))["gebiete"],
                             gebiete)

    def test_overpass_zu_tiefes_json_versucht_den_zweiten_endpunkt(self):
        """C20: RecursionError ist kein ValueError — der zweite Endpunkt wurde nie gefragt."""
        antworten = [Antwort(b"[" * 100000 + b"]" * 100000), json_antwort({"elements": []})]
        with mock.patch.object(urllib.request, "urlopen", side_effect=antworten), \
                mock.patch.object(overpass.time, "sleep", lambda *_: None):
            self.assertEqual(overpass._ask("[out:json];", 0), {"elements": []})

    def test_stationslisten_kaputt_gemerkt(self):
        meta = json.dumps({"stations": [{"id": "1", "name": "A", "lat": 47.0, "lon": 11.0, "is_active": True},
                                        {"id": "2", "name": "B", "lat": "NaN", "lon": 11.0}]}).encode()
        with tempfile.TemporaryDirectory() as d, mock.patch.object(stationen, "CACHE_DIR", Path(d)):
            (Path(d) / "geosphere_stationen.json").write_text('{"stations": [{"id"', encoding="utf-8")
            with mock.patch.object(stationen, "_get", return_value=meta) as get:
                self.assertEqual([s["id"] for s in stationen.geosphere_stationen()], ["1"])
            get.assert_called_once()
            # Ist das Netz weg, bleibt die gemerkte Liste, auch wenn sie alt ist
            alt = time.time() - 40 * 24 * 3600
            os.utime(Path(d) / "geosphere_stationen.json", (alt, alt))
            with mock.patch.object(stationen, "_get", side_effect=stationen.StationError("aus")):
                self.assertEqual([s["id"] for s in stationen.geosphere_stationen()], ["1"])
            for name, lade in (("dmi_stationen.json", stationen.dmi_stationen),
                               ("rws2_stationen.json", stationen.rws_stationen)):
                (Path(d) / name).write_text("[{", encoding="utf-8")
                with self.subTest(name=name), \
                        mock.patch.object(stationen, "_get", side_effect=stationen.StationError("aus")), \
                        mock.patch.object(stationen, "_post_json", side_effect=stationen.StationError("aus")), \
                        self.assertRaises(stationen.StationError):
                    lade()                                   # neu geholt (und hier gescheitert), kein ValueError


# ── C15: Wann ein gemerkter Zeitraum endgültig ist ───────────────────────────

class Endgueltig(unittest.TestCase):
    def test_vor_dem_abschluss_geholt_gilt_nicht_fuer_immer(self):
        alt = (date.today() - timedelta(days=10)).isoformat()
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "dwd_00001.zip"
            pfad.write_bytes(b"x")
            frueh = time.time() - 9 * 24 * 3600          # einen Tag nach dem Zeitraum geholt
            os.utime(pfad, (frueh, frueh))
            self.assertFalse(stationen._brauchbar(pfad, alt))
            spaet = time.time() - 2 * 24 * 3600           # acht Tage danach: endgültig
            os.utime(pfad, (spaet, spaet))
            self.assertTrue(stationen._brauchbar(pfad, alt))

    def test_meteo_france_datei(self):
        alt = (date.today() - timedelta(days=10)).isoformat()
        with tempfile.TemporaryDirectory() as d, mock.patch.object(stationen, "CACHE_DIR", Path(d)):
            datei = Path(d) / "fr_29.csv.gz"
            datei.write_bytes(b"alt")
            frueh = time.time() - 9 * 24 * 3600
            os.utime(datei, (frueh, frueh))
            with mock.patch.object(stationen, "fr_datei_url", return_value="https://x/H_29.csv.gz"), \
                    mock.patch.object(stationen, "_get", return_value=b"neu") as get:
                stationen._fr_datei("29", alt)
                get.assert_called_once()
                self.assertEqual(datei.read_bytes(), b"neu")
                stationen._fr_datei("29", alt)                     # jetzt endgültig — kein zweiter Abruf
                get.assert_called_once()


# ── C26: Absagen der Regionalmodelle ─────────────────────────────────────────

class HighresAbsage(unittest.TestCase):
    def _lauf(self, cache: dict, abgelehnt=(), spots=None):
        spots = spots or [spot("tot", 45.87, 10.87, country="IT")]
        gefragt = []

        def anfrage(modell, batch, tage, tz):
            gefragt.append(modell)
            if modell in abgelehnt:
                raise urllib.error.HTTPError("u", 400, "No data", {}, None)
            return [{"hourly": {"time": ZEITEN, "wind_speed_10m": [18.0] * 6}} for _ in batch]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(highres, "_anfrage", anfrage), \
                mock.patch.object(highres.time, "sleep", lambda *_: None):
            highres.sichere_cache(d, cache)
            highres.hole(spots, 2, d)
            return gefragt, highres.lade_cache(d)

    def test_absage_gilt_sieben_tage(self):
        bei = [45.87, 10.87]
        heute = date.today()
        gefragt, cache = self._lauf({"tot": {"modell": None, "bei": bei, "seit": heute.isoformat()}})
        self.assertEqual(gefragt, [])
        gefragt, cache = self._lauf({"tot": {"modell": None, "bei": bei,
                                             "seit": (heute - timedelta(days=8)).isoformat()}})
        self.assertTrue(gefragt, "nach einer Woche wird neu gefragt")
        self.assertIsNotNone(cache["tot"]["modell"])
        gefragt, cache = self._lauf({"tot": {"modell": None, "bei": bei}})       # Eintrag von vor 2.1.1
        self.assertEqual(gefragt, [])
        self.assertEqual(cache["tot"]["seit"], heute.isoformat())

    def test_reicht_die_reihe_durch_statt_zu_pendeln(self):
        ort = spot("tot", 45.87, 10.87, country="IT")
        kandidaten = highres.kandidaten(ort)
        self.assertGreaterEqual(len(kandidaten), 3)
        a, b, c = kandidaten[:3]
        cache = {}
        for _ in range(3):
            gefragt, cache = self._lauf(cache, abgelehnt={a, b}, spots=[ort])
        self.assertEqual(cache["tot"]["modell"], c, "nach A und B kommt C — nicht wieder A")


if __name__ == "__main__":
    unittest.main()
