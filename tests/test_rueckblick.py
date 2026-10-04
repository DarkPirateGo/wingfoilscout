"""Rückblick: die besten Ziele der letzten Suche gegen die Messung — ohne Netz.

Die Dienste werden untergeschoben; geprüft wird, dass aus Vorhersage und
Messung je Spot Kennzahlen und ein Stundenverlauf entstehen, dass Spots ohne
Station ehrlich als solche stehen, und dass die Seite und ihr Ablauf laufen.
"""
from __future__ import annotations
import re
import json
import tempfile
import threading
import time
import unittest
import urllib.request
from datetime import date, datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from tests.helpers import cfg as load_cfg, CONFIG
from wingscout import rueckblick
from wingscout.sources import stationen, historisch
import wingscout.webui as w


def _fc(tage, von: str):
    n = 24 * tage
    d0 = date.fromisoformat(von)
    zeiten = [f"{d0.replace(day=d0.day + d).isoformat()}T{h:02d}:00" for d in range(tage) for h in range(24)]
    s = "_dwd_icon_seamless"
    return {"utc_offset_seconds": 7200,
            "hourly": {"time": zeiten, f"wind_speed_10m{s}": [14.0] * n, f"wind_gusts_10m{s}": [17.0] * n,
                       f"wind_direction_10m{s}": [270.0] * n, f"temperature_2m{s}": [20.0] * n,
                       f"precipitation{s}": [0.0] * n, f"cape{s}": [0.0] * n, f"weather_code{s}": [1] * n,
                       f"cloud_cover{s}": [20.0] * n, f"shortwave_radiation{s}": [300.0] * n},
            "daily": {"time": [t[:10] for t in zeiten[::24]],
                      f"sunrise{s}": [t[:10] + "T06:30" for t in zeiten[::24]],
                      f"sunset{s}": [t[:10] + "T20:00" for t in zeiten[::24]]}}


def _messung(fc, kn=12.0, richtung=260.0):
    out = {}
    for t in fc["hourly"]["time"]:
        lokal = datetime.fromisoformat(t)
        if lokal.hour >= 2:
            out[lokal.replace(hour=lokal.hour - 2).strftime("%Y-%m-%dT%H:00")] = {"kn": kn, "dir": richtung}
    return out


SPOTS = {
    "fehmarn": {"id": "fehmarn", "name": "Fehmarn", "lat": 54.53, "lon": 11.06, "country": "DE", "sectors": []},
    "torbole": {"id": "torbole", "name": "Torbole", "lat": 45.87, "lon": 10.87, "country": "IT", "sectors": []},
    "weitweg": {"id": "weitweg", "name": "Weit weg", "lat": 50.0, "lon": 9.0, "country": "DE", "sectors": []},
}
TOP = [{"rang": 1, "id": "fehmarn", "name": "Fehmarn"}, {"rang": 2, "id": "torbole", "name": "Torbole"},
       {"rang": 3, "id": "weitweg", "name": "Weit weg"}]


class Rechnung(unittest.TestCase):
    def test_zeitraum(self):
        """Die letzten N Tage einschließlich heute — Freitag heißt: auch Freitag."""
        heute = date(2026, 9, 18)
        self.assertEqual(rueckblick.zeitraum(2, heute), ("2026-09-17", "2026-09-18"))
        self.assertEqual(rueckblick.zeitraum(1, heute), ("2026-09-18", "2026-09-18"))
        self.assertEqual(rueckblick.zeitraum(99, heute)[0], "2026-09-05")     # höchstens 14

    def test_ziele_gegen_messung(self):
        heute = date(2026, 9, 18)
        von, bis = rueckblick.zeitraum(2, heute)
        fc = _fc(2, von)
        station = {"id": "05516", "name": "Fehmarn", "lat": 54.5279, "lon": 11.0616}

        def paare(spots, max_km, log=None):
            return [{"spot": SPOTS["fehmarn"], "quelle": "DWD", "station": station, "km": 0.3, "ersatz": []}]

        def stunden(paar, v, b):
            return {"quelle": "DWD", "station": station, "stunden": _messung(fc)}

        jetzt = datetime(2026, 9, 18, 12, 30)                              # UTC, 14:30 Ortszeit
        with mock.patch.object(stationen, "paare_finden", side_effect=paare), \
                mock.patch.object(stationen, "stunden_fuer", side_effect=stunden), \
                mock.patch.object(historisch, "hole_bis_heute", return_value=fc), \
                mock.patch.object(historisch, "hole_regional_bis_heute", return_value=None):
            erg = rueckblick.rechne(load_cfg(), SPOTS, TOP, 2, {}, log=lambda *a: None, heute=heute, jetzt=jetzt)
        self.assertEqual((erg["von"], erg["bis"], erg["tage"]), (von, bis, 2))
        self.assertEqual(erg["bis_utc"], "2026-09-18T12:00")
        from wingscout import __version__
        self.assertEqual(erg["version"], __version__)
        self.assertEqual([s["id"] for s in erg["spots"]], ["fehmarn", "torbole", "weitweg"])
        f = erg["spots"][0]
        self.assertEqual(f["station"]["quelle"], "DWD")
        self.assertLess(f["station"]["km"], 1.0)
        self.assertAlmostEqual(f["masse"]["bias"], 2.0, places=1)          # 14 gesagt, 12 gemessen
        self.assertGreaterEqual(f["masse"]["richtung"], 0.99)
        # 24 Stunden gestern + heute bis 14 Uhr Ortszeit (12 UTC) = 39 Stunden; die Zukunft fehlt
        self.assertEqual(len(f["stunden"]), 24 + 15)
        self.assertEqual(f["stunden"][-1]["t"], "2026-09-18T14:00")
        self.assertEqual(f["stunden"][12]["v"], 14.0)
        self.assertEqual(f["stunden"][12]["m"], 12.0)
        self.assertIsNone(f["stunden"][0]["m"], "vor 02:00 Ortszeit gibt es keine Messung im Testdatensatz")
        self.assertEqual(f["messung_bis"], max(_messung(fc)))
        self.assertEqual(f["abdeckung"], "Do 17.09. 02–23 Uhr · Fr 18.09. 02–14 Uhr")   # 00 und 01 Uhr fehlen im Testdatensatz
        # Die Kennzahlen zählen nur Stunden bis jetzt
        self.assertLessEqual(f["masse"]["n"], 39)
        # Modellvergleich (1.14.0): jedes Modell einzeln, die Bewertung als eigene Zeile
        vg = f["vergleich"]
        self.assertEqual({z["id"] for z in vg["modelle"]}, {"dwd_icon_seamless", "wingscout"})
        icon = next(z for z in vg["modelle"] if z["id"] == "dwd_icon_seamless")
        self.assertAlmostEqual(icon["masse"]["bias"], 2.0, places=1)
        self.assertEqual(vg["bestes"], "dwd_icon_seamless")
        self.assertEqual(f["stunden"][12]["mv"], {"dwd_icon_seamless": 14.0})
        self.assertEqual(erg["vergleich_gesamt"][0]["spots"], 1)
        # Gedächtnis und „bisher bestes Modell“ (1.15.0)
        with tempfile.TemporaryDirectory() as d:
            rueckblick.mit_gedaechtnis(erg, Path(d) / "modellguete.json")
        self.assertEqual(erg["spots"][0]["bisher_bestes"]["id"], "dwd_icon_seamless")
        self.assertEqual(erg["spots"][0]["bisher_bestes"]["quelle"], "spot")
        self.assertNotIn("bisher_bestes", erg["spots"][1], "ohne Station kein Vergleich, keine Option")
        self.assertIsNone(erg["spots"][1].get("vergleich"))
        # Italien: kein Dienst dort, und über die Grenze reicht keine Station
        # in den Umkreis — ehrlich gesagt, keine Zahlen; der Text nennt den
        # Umkreis (Vorgabe 30 km) und dass über Grenzen hinweg gesucht wurde
        t = erg["spots"][1]
        self.assertIsNone(t["masse"])
        self.assertIn("keine Messstation in 30 km", t["grund"])
        self.assertIn("über Grenzen hinweg", t["grund"])
        self.assertEqual(erg["max_km"], 30)
        # Deutschland, aber keine Station in Reichweite
        self.assertIn("keine Messstation", erg["spots"][2]["grund"])

    def test_archiv_und_laufende_vorhersage_zusammengesetzt(self):
        """Bis gestern aus dem Archiv, heute aus der laufenden Vorhersage —
        Stunde für Stunde eine Antwort, ohne Lücke und ohne Doppelung."""
        archiv = _fc(1, "2026-09-17")
        live = _fc(2, "2026-09-17")
        live["hourly"]["wind_speed_10m_dwd_icon_seamless"] = [9.0] * 48       # Archiv gewinnt, wo es beides gibt
        aus = historisch.zusammensetzen(archiv, live, "2026-09-17", "2026-09-18")
        self.assertEqual(len(aus["hourly"]["time"]), 48)
        self.assertEqual(aus["hourly"]["time"][0], "2026-09-17T00:00")
        self.assertEqual(aus["hourly"]["time"][-1], "2026-09-18T23:00")
        w = aus["hourly"]["wind_speed_10m_dwd_icon_seamless"]
        self.assertEqual((w[0], w[23], w[24], w[47]), (14.0, 14.0, 9.0, 9.0))
        self.assertEqual(aus["daily"]["time"], ["2026-09-17", "2026-09-18"])
        self.assertEqual(len(aus["daily"]["sunrise_dwd_icon_seamless"]), 2)
        # Nur die laufende Vorhersage (Archiv nicht erreichbar): dieselbe Form
        nur_live = historisch.zusammensetzen(None, live, "2026-09-18", "2026-09-18")
        self.assertEqual(len(nur_live["hourly"]["time"]), 24)
        with self.assertRaises(historisch.HistorischError):
            historisch.zusammensetzen(None, None, "2026-09-18", "2026-09-18")

    def test_hole_bis_heute_fragt_archiv_und_live(self):
        aufrufe = []

        def hole(spot, von, bis, models, tz, hourly=None):
            aufrufe.append(("archiv", von, bis))
            return _fc(1, von)

        def live(spot, past, models, tz, felder, mit_daily=True):
            aufrufe.append(("live", past))
            return _fc(2, "2026-09-17")

        with mock.patch.object(historisch, "_heute", return_value=date(2026, 9, 18)), \
                mock.patch.object(historisch, "hole", side_effect=hole), \
                mock.patch.object(historisch, "_live", side_effect=live):
            aus = historisch.hole_bis_heute(SPOTS["fehmarn"], "2026-09-17", "2026-09-18", ["dwd_icon_seamless"], "Europe/Berlin")
            self.assertEqual(aufrufe, [("archiv", "2026-09-17", "2026-09-17"), ("live", 1)])
            self.assertEqual(len(aus["hourly"]["time"]), 48)
            # Zeitraum ganz in der Vergangenheit: nur das Archiv
            aufrufe.clear()
            historisch.hole_bis_heute(SPOTS["fehmarn"], "2026-09-10", "2026-09-11", ["dwd_icon_seamless"], "Europe/Berlin")
            self.assertEqual(aufrufe, [("archiv", "2026-09-10", "2026-09-11")])

    def test_naechste_station_wenn_die_erste_noch_nichts_hat(self):
        """Schokkerstrand am 20.09.: KNMI 316 hatte für die letzten zwei Tage
        keine Zeilen (zwei Tage Verzug) — die Seite sagte „nicht abrufbar“ und
        blieb leer. Jetzt kommt die nächste Station dran, die Werte hat; hat
        keine welche, steht der Grund dabei."""
        heute = date(2026, 9, 18)
        von, bis = rueckblick.zeitraum(2, heute)
        fc = _fc(2, von)
        knmi = {"id": "316", "name": "Schaar", "lat": 51.66, "lon": 3.69, "dienst": "KNMI"}
        rws = {"id": "VLIS", "name": "Vlissingen", "lat": 51.44, "lon": 3.60, "dienst": "RWS"}
        spot = {"id": "brouwersdam", "name": "Brouwersdam", "lat": 51.76, "lon": 3.85, "country": "NL", "sectors": []}
        top = [{"rang": 1, "id": "brouwersdam", "name": "Brouwersdam"}]
        gefragt = []

        def stunden(paar, v, b):
            st = paar["station"]
            gefragt.append(st["id"])
            if st["dienst"] == "KNMI":
                return {"quelle": "KNMI", "station": st, "stunden": {},
                        "hinweis": "KNMI veröffentlicht die Stundenwerte mit zwei Tagen Verzug"}
            return {"quelle": "RWS", "station": st, "stunden": _messung(fc)}

        paar = {"spot": spot, "quelle": "KNMI", "station": knmi, "km": 14.9, "ersatz": [rws]}
        jetzt = datetime(2026, 9, 18, 12, 30)
        with mock.patch.object(stationen, "paare_finden", return_value=[paar]), \
                mock.patch.object(stationen, "stunden_fuer", side_effect=stunden), \
                mock.patch.object(historisch, "hole_bis_heute", return_value=fc), \
                mock.patch.object(historisch, "hole_regional_bis_heute", return_value=None):
            erg = rueckblick.rechne(load_cfg(), {"brouwersdam": spot}, top, 2, {}, log=lambda *a: None,
                                    heute=heute, jetzt=jetzt, max_km=40)
        z = erg["spots"][0]
        self.assertEqual(gefragt, ["316", "VLIS"])
        self.assertEqual((z["station"]["quelle"], z["station"]["id"]), ("RWS", "VLIS"))
        self.assertAlmostEqual(z["station"]["km"], 40.0, delta=3.0,
                               msg="die Entfernung gilt für die Station, die geliefert hat")
        self.assertIsNotNone(z["masse"])
        self.assertEqual(erg["max_km"], 40)
        # Beide ohne Werte: der Grund nennt den Verzug und den Umkreis
        paar2 = {"spot": spot, "quelle": "KNMI", "station": knmi, "km": 14.9, "ersatz": [dict(knmi, id="235", name="De Kooy")]}
        with mock.patch.object(stationen, "paare_finden", return_value=[paar2]), \
                mock.patch.object(stationen, "stunden_fuer", side_effect=stunden), \
                mock.patch.object(historisch, "hole_bis_heute", return_value=fc), \
                mock.patch.object(historisch, "hole_regional_bis_heute", return_value=None):
            erg = rueckblick.rechne(load_cfg(), {"brouwersdam": spot}, top, 2, {}, log=lambda *a: None,
                                    heute=heute, jetzt=jetzt, max_km=40)
        z = erg["spots"][0]
        self.assertIsNone(z["masse"])
        self.assertEqual(z["station"]["id"], "316", "die nächste bleibt in der Meldung")
        self.assertIn("noch keine Werte veröffentlicht — KNMI veröffentlicht die Stundenwerte mit zwei Tagen Verzug", z["grund"])
        self.assertIn("auch keine andere in 40 km", z["grund"])
        # Der Umkreis wird begrenzt
        with mock.patch.object(stationen, "paare_finden", return_value=[]) as pf, \
                mock.patch.object(historisch, "hole_bis_heute", return_value=fc):
            erg = rueckblick.rechne(load_cfg(), {"brouwersdam": spot}, top, 2, {}, log=lambda *a: None,
                                    heute=heute, jetzt=jetzt, max_km=5000)
        self.assertEqual(pf.call_args[0][1], 100.0)
        self.assertIn("keine Messstation in 100 km", erg["spots"][0]["grund"])

    def test_station_mit_der_besseren_abdeckung(self):
        """IJmuiden Zone 1 am 20.09.: KNMI IJmuiden (0,8 km) hatte 24 Stunden,
        alle von vorgestern; Rijkswaterstaat Buitenhaven, genauso weit weg,
        hatte Werte bis jetzt. Bis 1.14.0 gewann KNMI, weil es überhaupt Werte
        hatte (und bei Gleichstand die Kennung „225“ vor „ijmuiden…“ kommt)."""
        heute = date(2026, 9, 18)
        von, bis = rueckblick.zeitraum(2, heute)
        fc = _fc(2, von)
        voll = _messung(fc)
        alt = {t: v for t, v in voll.items() if t < f"{bis}T00:00"}          # nur vorgestern/gestern
        knmi = {"id": "225", "name": "IJmuiden", "lat": 52.4636, "lon": 4.5552, "dienst": "KNMI"}
        rws = {"id": "ijmuiden.buitenhaven", "name": "IJmuiden, buitenhaven", "lat": 52.463, "lon": 4.555, "dienst": "RWS"}
        weit = {"id": "235", "name": "De Kooy", "lat": 52.92, "lon": 4.78, "dienst": "KNMI"}
        spot = {"id": "nl-ijmuiden-zone1", "name": "IJmuiden Zone 1", "lat": 52.45636, "lon": 4.55121,
                "country": "NL", "sectors": []}
        top = [{"rang": 1, "id": spot["id"], "name": spot["name"]}]
        jetzt = datetime(2026, 9, 18, 12, 30)
        moeglich = rueckblick.moegliche_stunden(von, "2026-09-18T12:00")
        self.assertEqual(moeglich, 24 + 13)

        def rechne(werte: dict):
            gefragt = []

            def stunden(paar, v, b):
                st = paar["station"]
                gefragt.append(st["id"])
                return {"quelle": st["dienst"], "station": st, "stunden": werte[st["id"]]}
            paar = {"spot": spot, "quelle": "KNMI", "station": knmi, "km": 0.8, "ersatz": [rws, weit]}
            with mock.patch.object(stationen, "paare_finden", return_value=[paar]), \
                    mock.patch.object(stationen, "stunden_fuer", side_effect=stunden), \
                    mock.patch.object(historisch, "hole_bis_heute", return_value=fc), \
                    mock.patch.object(historisch, "hole_regional_bis_heute", return_value=None):
                erg = rueckblick.rechne(load_cfg(), {spot["id"]: spot}, top, 2, {}, log=lambda *a: None,
                                        heute=heute, jetzt=jetzt)
            return erg["spots"][0], gefragt

        # KNMI nur bis gestern, Rijkswaterstaat bis jetzt: Rijkswaterstaat, und die übergangene steht dabei
        z, gefragt = rechne({"225": alt, "ijmuiden.buitenhaven": voll, "235": voll})
        self.assertEqual(z["station"]["id"], "ijmuiden.buitenhaven")
        self.assertEqual(gefragt, ["225", "ijmuiden.buitenhaven"], "reicht eine, wird keine weitere gefragt")
        self.assertEqual((z["station"]["stunden"], z["station"]["moeglich"]), (35, 37))
        self.assertEqual(z["station"]["statt"]["quelle"], "KNMI")
        self.assertEqual(z["station"]["statt"]["stunden"], 22)
        # Hat die nächste fast alles, bleibt sie — ohne weitere Anfrage
        z, gefragt = rechne({"225": voll, "ijmuiden.buitenhaven": voll, "235": voll})
        self.assertEqual((z["station"]["id"], gefragt), ("225", ["225"]))
        self.assertNotIn("statt", z["station"])
        # Keine hat 90 %: die nächste mit wenigstens 80 % der besten, nicht die weite mit einer Stunde mehr
        knapp = dict(list(voll.items())[:20])
        etwas_mehr = dict(list(voll.items())[:21])
        z, gefragt = rechne({"225": knapp, "ijmuiden.buitenhaven": {}, "235": etwas_mehr})
        self.assertEqual(gefragt, ["225", "ijmuiden.buitenhaven", "235"])
        self.assertEqual(z["station"]["id"], "225")

    def test_station_waehlen(self):
        w = rueckblick.station_waehlen
        self.assertIsNone(w([], 40))
        self.assertIsNone(w([({}, {}, 1.0, 0), ({}, {}, 2.0, 0)], 40))
        self.assertEqual(w([({}, {}, 1.0, 10), ({}, {}, 2.0, 38)], 40), 1)       # 38 ≥ 90 % von 40
        self.assertEqual(w([({}, {}, 1.0, 30), ({}, {}, 9.0, 34)], 40), 0)       # 30 ≥ 80 % von 34
        self.assertEqual(w([({}, {}, 1.0, 20), ({}, {}, 9.0, 34)], 40), 1)       # 20 < 80 % von 34

    def test_abdeckung_nennt_die_luecke(self):
        """DWD und KNMI haben gestern nicht — der Text sagt, was da ist."""
        st = [{"t": f"2026-09-17T{h:02d}:00", "m": 10.0} for h in range(24)]
        st += [{"t": f"2026-09-18T{h:02d}:00", "m": None} for h in range(24)]
        st += [{"t": f"2026-09-19T{h:02d}:00", "m": 9.0} for h in range(10)]
        self.assertEqual(rueckblick.abdeckung(st), "Do 17.09. 00–23 Uhr · Sa 19.09. 00–09 Uhr")
        self.assertEqual(rueckblick.abdeckung([{"t": "2026-09-19T05:00", "m": None}]), "")

    def test_ueberholtes_ergebnis_wird_benannt(self):
        """Am 20.09. zeigte die Seite ein Ergebnis vom 18.09. (Version 1.9.0,
        „für FR kein Messdienst“), obwohl 1.10.0 Frankreich kannte — und
        nichts sagte es. Jetzt steht es dabei."""
        alt = {"zeit": "2026-09-18T23:54", "spots": []}                     # vor 1.10.0: keine Version im Ergebnis
        lauf = {"zeit": "2026-09-20T09:20", "top": [{"rang": 1, "id": "x", "name": "X"}]}
        text = rueckblick.veraltet(alt, lauf, "1.12.0")
        self.assertIn("die letzte Suche (2026-09-20 09:20) ist neuer als dieser Rückblick (2026-09-18 23:54)", text)
        self.assertIn("mit Version vor 1.10.0 gerechnet, das Programm ist jetzt 1.12.0", text)
        self.assertTrue(text.endswith("„Prüfen“ rechnet neu."))
        frisch = {"zeit": "2026-09-20T09:30", "version": "1.12.0", "spots": []}
        self.assertEqual(rueckblick.veraltet(frisch, lauf, "1.12.0"), "")
        self.assertIn("Version 1.12.0 gerechnet, das Programm ist jetzt 1.13.0", rueckblick.veraltet(frisch, lauf, "1.13.0"))
        self.assertEqual(rueckblick.veraltet(None, lauf, "1.12.0"), "")
        # Die Seite zeigt den Hinweis als Balken. Ein frisches Ergebnis trägt die
        # laufende Version — nicht eine feste Nummer: genau so eine feste Nummer
        # hat am 20.09. den Commit von 1.13.0 scheitern lassen, weil das
        # Veröffentlichen erst die Version setzt und dann die Tests laufen lässt.
        from wingscout import __version__
        html = w.rueckblick_page(load_cfg(), alt, lauf, 2)
        self.assertIn("class='banner b-warn'>Dieses Ergebnis ist überholt", html)
        aktuell = dict(frisch, version=__version__)
        self.assertNotIn("Dieses Ergebnis ist überholt", w.rueckblick_page(load_cfg(), aktuell, lauf, 2))

    def test_speichern_und_laden(self):
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "rueckblick.json"
            rueckblick.speichern({"von": "a", "spots": []}, pfad)
            self.assertEqual(rueckblick.laden(pfad)["von"], "a")
            self.assertIsNone(rueckblick.laden(Path(d) / "gibt-es-nicht.json"))


class Seite(unittest.TestCase):
    def test_seite_baut_und_escaped(self):
        cfg = load_cfg()
        daten = {"zeit": "2026-09-18T09:00", "von": "2026-09-16", "bis": "2026-09-17", "tage": 2,
                 "spots": [{"id": "x", "name": "<script>alert(1)</script>", "rang": 1, "country": "DE",
                            "station": {"id": "1", "name": "S", "quelle": "DWD", "km": 0.5},
                            "masse": {"n": 40, "mae": 2.1, "bias": -0.4, "richtung": 0.9, "richtung_n": 30, "f1": 0.7,
                                      "gemessen_fahrbar": 20},
                            "stunden": [{"t": "2026-09-16T12:00", "v": 14.0, "vd": 270, "m": 12.0, "md": 260,
                                         "modell": None, "thermik": False}]}]}
        html = w.rueckblick_page(cfg, daten, {"zeit": "2026-09-17T13:45", "top": TOP}, 2)
        self.assertIn("class='reiter'", html)
        self.assertIn("Letzte Suche: 17.09.2026 13:45", html)
        self.assertNotIn("<script>alert", html)
        self.assertIn("\\u003cscript\\u003e", html)
        self.assertIn("var DATEN = ", html)
        js = re.split(r"<script[^>]*>", html)[1].split("</script>")[0]
        self.assertNotIn("innerHTML = j.", js)
        # ohne Suche: Knopf aus, klare Ansage
        leer = w.rueckblick_page(cfg, None, None, 2)
        self.assertIn("Noch keine Suche gelaufen", leer)
        self.assertIn("disabled", leer.split("id='rgo'")[1][:120])


class Ablauf(unittest.TestCase):
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

    def _post(self, path, body=b"", headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body, method="POST",
                                     headers=dict({"Origin": f"http://127.0.0.1:{self.port}"}, **(headers or {})))
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def _get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as r:
            return r.status, r.read()

    def test_ohne_suche_kein_start(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(rueckblick, "LETZTER_LAUF", Path(d) / "nix.json"):
            code, body = self._post("/rueckblick/start", body=b"tage=2")
        self.assertEqual(code, 400)
        self.assertIn("keine Suche", json.loads(body)["error"])

    def test_lauf_von_der_seite_bis_zu_den_daten(self):
        with tempfile.TemporaryDirectory() as d:
            lauf = Path(d) / "letzter_lauf.json"
            lauf.write_text(json.dumps({"zeit": "2026-09-17T13:45", "top": TOP}), encoding="utf-8")
            erg = Path(d) / "rueckblick.json"

            gesehen = {}

            def rechne(cfg, spots, top, tage, geometry, log=None, heute=None, jetzt=None, max_km=None):
                log("gerechnet")
                gesehen["max_km"] = max_km
                return {"zeit": "x", "von": "a", "bis": "b", "tage": tage, "max_km": max_km,
                        "spots": [{"id": t["id"], "name": t["name"], "rang": t["rang"], "country": "DE",
                                   "station": {"id": "1", "name": "S", "quelle": "DWD", "km": 1.0},
                                   "masse": {"n": 10, "mae": 1.0}, "stunden": []} for t in top]}

            from wingscout import modellvergleich
            with mock.patch.object(rueckblick, "LETZTER_LAUF", lauf), \
                    mock.patch.object(rueckblick, "ERGEBNIS", erg), \
                    mock.patch.object(modellvergleich, "GUETE", Path(d) / "modellguete.json"), \
                    mock.patch.object(rueckblick, "rechne", side_effect=rechne):
                code, body = self._get("/rueckblick")
                self.assertEqual(code, 200)
                seite = body.decode("utf-8")
                self.assertIn("Letzte Suche: 17.09.2026 13:45", seite)
                # Das Umkreis-Feld mit der Vorgabe, und die Erklärung nennt die neuen Quellen
                self.assertIn("name='max_km' value='30' min='1' max='100'", seite)
                # Der Browser lässt nur min + n·step zu: mit step=5 waren 10 und
                # die Vorgabe 30 „kein gültiger Wert“ (20.09.) — jede ganze Zahl muss gehen
                import re
                feld = re.search(r"<input[^>]*name='max_km'[^>]*>", seite).group(0)
                attr = dict(re.findall(r"(\w+)='([^']*)'", feld))
                self.assertEqual(attr["step"], "1")
                for wert in (10, 30, 100):
                    self.assertEqual((wert - int(attr["min"])) % int(attr["step"]), 0, wert)
                self.assertIn("Rijkswaterstaat", seite)
                # Standard im Diagramm: nur Messung und Spanne — keine Linie ist vorab an (1.15.0)
                self.assertIn("function angeschaltet(spot) { return spot._an || []; }", seite)
                self.assertNotIn("modellZeige", seite)
                self.assertIn("Bisher bestes Modell", seite)
                self.assertIn("Windguru", seite)
                self.assertIn("über Grenzen hinweg", seite)
                # Der Umkreis kommt aus dem Formular, wird begrenzt (1–100 km) und
                # landet im Ergebnis; Unsinn fällt auf die Vorgabe zurück
                code, body = self._post("/rueckblick/start", body=b"tage=3&max_km=45")
                self.assertEqual(code, 200, body)
                for _ in range(100):
                    time.sleep(0.05)
                    with w.LOCK:
                        if w.JOB["state"] != "running":
                            break
                with w.LOCK:
                    self.assertEqual(w.JOB["state"], "done", w.JOB)
                    self.assertEqual(w.JOB["kind"], "rueckblick")
                    self.assertIn("3 von 3 Zielen", w.JOB["summary"])
                    w.JOB.update(state="idle")
                code, body = self._get("/rueckblick/daten")
                daten = json.loads(body)
                self.assertEqual(daten["tage"], 3)
                self.assertEqual(len(daten["spots"]), 3)
                self.assertEqual(gesehen["max_km"], 45.0)
                self.assertTrue(erg.exists())
                # Die Seite bietet den zuletzt gewählten Umkreis wieder an
                code, body = self._get("/rueckblick")
                self.assertIn("name='max_km' value='45'", body.decode("utf-8"))
                # Zu groß, zu klein, kein Wert: alles landet in 1–100 km
                for roh, erwartet in ((b"tage=1&max_km=999", 100.0), (b"tage=1&max_km=0", 1.0),
                                      (b"tage=1&max_km=abc", 30.0), (b"tage=1&max_km=nan", 30.0)):
                    code, body = self._post("/rueckblick/start", body=roh)
                    self.assertEqual(code, 200, body)
                    for _ in range(100):
                        time.sleep(0.05)
                        with w.LOCK:
                            if w.JOB["state"] != "running":
                                break
                    with w.LOCK:
                        self.assertEqual(w.JOB["state"], "done", w.JOB)
                        w.JOB.update(state="idle")
                    self.assertEqual(gesehen["max_km"], erwartet, roh)


if __name__ == "__main__":
    unittest.main()
