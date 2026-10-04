"""Hochauflösende Regionalmodelle — vor allem: was passiert bei Ablehnung.

Open-Meteo dokumentiert keine Modellgrenzen und beantwortet eine Anfrage für
einen Punkt außerhalb der Domain mit HTTP 400. Bei einer Sammelanfrage reißt
ein einziger unpassender Punkt alle anderen mit. Diese Tests decken genau
diesen Fall ab — er lässt sich ohne Netz sonst nirgends prüfen, und im
Ernstfall wäre er ein stiller Datenverlust.
"""
from __future__ import annotations
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from wingscout.sources import highres


def spot(sid, lat, lon):
    return {"id": sid, "name": sid, "lat": lat, "lon": lon}


def antwort(spots, stunden=3):
    """Was Open-Meteo für eine abgedeckte Gruppe liefert."""
    zeiten = [f"2026-07-15T{h:02d}:00" for h in range(12, 12 + stunden)]
    return [{"hourly": {"time": zeiten,
                        "wind_speed_10m": [18.0] * stunden,
                        "wind_gusts_10m": [22.0] * stunden,
                        "wind_direction_10m": [180.0] * stunden}} for _ in spots]


class Vorauswahl(unittest.TestCase):
    def test_rahmen_waehlt_plausible_modelle(self):
        garda = spot("garda", 45.87, 10.87)
        self.assertIn("italia_meteo_arpae_icon_2i", highres.kandidaten(garda))
        zeeland = spot("zeeland", 51.76, 3.85)
        self.assertIn("knmi_harmonie_arome_netherlands", highres.kandidaten(zeeland))
        # Weit außerhalb: kein Kandidat, also auch keine Anfrage
        self.assertEqual(highres.kandidaten(spot("kanaren", 28.1, -15.4)), [])

    def test_landesmodell_vor_feinerer_aufloesung(self):
        """Ein Modell am Rand seines Gebiets ist nicht die bessere Auskunft.

        Der erste Probelauf gab dem Gardasee das Schweizer Modell (1 km) und
        Zeeland das französische (1,5 km) — beide antworten dort, sind aber
        weit außerhalb ihres Zuständigkeitsgebiets.
        """
        erwartet = {
            "torbole": ("italia_meteo_arpae_icon_2i", 45.87, 10.87),
            "domaso": ("italia_meteo_arpae_icon_2i", 46.148, 9.332),
            "silvaplana": ("meteoswiss_icon_ch1", 46.449, 9.795),
            "walchensee": ("dwd_icon_d2", 47.588, 11.313),
            "brouwersdam": ("knmi_harmonie_arome_netherlands", 51.763, 3.854),
            "serre-poncon": ("meteofrance_arome_france_hd", 44.541, 6.461),
        }
        for sid, (modell, lat, lon) in erwartet.items():
            with self.subTest(spot=sid):
                self.assertEqual(highres.kandidaten(spot(sid, lat, lon))[0], modell)

    def test_innerhalb_eines_landes_gewinnt_die_aufloesung(self):
        # Die Schweiz: nur CH1 ist daheim, es steht vorn
        # Fehmarn liegt im deutschen und im dänischen Rahmen, beide Modelle
        # haben 2 km: das Landeskürzel entscheidet, nicht das Alphabet.
        fehmarn = dict(spot("fehmarn", 54.53, 11.06), country="DE")
        self.assertEqual(highres.kandidaten(fehmarn)[0], "dwd_icon_d2")
        self.assertEqual(highres.kandidaten(dict(fehmarn, country="DK"))[0], "dmi_harmonie_arome_europe")
        ch = highres.kandidaten(spot("ch", 46.92, 8.60))
        self.assertEqual(ch[0], "meteoswiss_icon_ch1")
        # Die übrigen folgen nach Auflösung sortiert
        rest = [highres.aufloesung(m) for m in ch[1:]]
        self.assertEqual(rest, sorted(rest))


class Ablehnung(unittest.TestCase):
    """Ein 400 für die Gruppe darf die brauchbaren Punkte nicht mitreißen."""

    def _lauf(self, spots, abgelehnt: set):
        aufrufe = []

        def falsche_anfrage(modell, batch, tage, tz):
            aufrufe.append([s["id"] for s in batch])
            if any(s["id"] in abgelehnt for s in batch):
                raise urllib.error.HTTPError("u", 400, "No data is available for this location",
                                             {}, None)
            return antwort(batch)

        with mock.patch.object(highres, "_anfrage", falsche_anfrage), \
             mock.patch.object(highres.time, "sleep", lambda *_: None), \
             tempfile.TemporaryDirectory() as d:
            ergebnis, stat = highres.hole(spots, 2, d)
            cache = json.loads((Path(d) / highres.CACHE_NAME).read_text(encoding="utf-8"))
        return ergebnis, stat, cache, aufrufe

    def test_ein_ausreisser_kostet_nicht_die_gruppe(self):
        spots = [spot(f"s{i}", 45.87, 10.87) for i in range(8)]
        ergebnis, stat, cache, aufrufe = self._lauf(spots, {"s3"})
        self.assertEqual(len(ergebnis), 7, "sieben Punkte müssen durchkommen")
        self.assertNotIn("s3", ergebnis)
        self.assertGreater(len(aufrufe), 1, "die Gruppe muss halbiert worden sein")
        self.assertLess(len(aufrufe), 12, "aber nicht jeder Punkt einzeln")

    def test_abdeckung_wird_gemerkt(self):
        spots = [spot("drin", 45.87, 10.87), spot("draussen", 45.88, 10.88)]
        _, _, cache, _ = self._lauf(spots, {"draussen"})
        self.assertEqual(cache["drin"]["modell"], highres.kandidaten(spots[0])[0])
        # Für den abgelehnten Punkt ist das nächstgröbere Modell vorgemerkt
        self.assertIsNotNone(cache["draussen"]["modell"])
        self.assertNotEqual(cache["draussen"]["modell"], cache["drin"]["modell"])

    def test_gemerkte_absage_kostet_keine_anfrage(self):
        with tempfile.TemporaryDirectory() as d:
            highres.sichere_cache(d, {"tot": {"modell": None, "bei": [45.87, 10.87]}})
            with mock.patch.object(highres, "_anfrage") as anfrage:
                ergebnis, stat = highres.hole([spot("tot", 45.87, 10.87)], 2, d)
            anfrage.assert_not_called()
            self.assertEqual(ergebnis, {})

    def test_zuordnung_gilt_nur_fuer_die_koordinate(self):
        """Nach einer Korrektur der Nadel wird neu geprüft — bis 1.6.1 rechnete
        der Lauf mit dem Modell des alten Punkts weiter. Ein Eintrag ohne
        Stempel (aus der Zeit davor) zählt wie keiner."""
        for gemerkt in ({"modell": None, "bei": [45.20, 10.20]},      # anderer Punkt
                        {"modell": None}):                              # ohne Stempel
            with tempfile.TemporaryDirectory() as d:
                highres.sichere_cache(d, {"tot": gemerkt})
                with mock.patch.object(highres, "_anfrage", return_value=[{"hourly": {"time": []}}]) as anfrage:
                    highres.hole([spot("tot", 45.87, 10.87)], 2, d)
                anfrage.assert_called()
                neu = highres.lade_cache(d)["tot"]
                self.assertEqual(neu["bei"], [45.87, 10.87])

    def test_netzfehler_ist_kein_absturz(self):
        def kaputt(*_a, **_k):
            raise OSError("Netz weg")
        with mock.patch.object(highres, "_anfrage", kaputt), \
             tempfile.TemporaryDirectory() as d:
            ergebnis, stat = highres.hole([spot("s", 45.87, 10.87)], 2, d)
        self.assertEqual(ergebnis, {})


class Einsetzen(unittest.TestCase):
    """Die feine Reihe legt sich stundenweise über die grobe — nicht weiter."""

    def basis(self, stunden=8):
        zeiten = [f"2026-07-15T{h:02d}:00" for h in range(10, 10 + stunden)]
        return {"time": zeiten,
                "wind_speed_10m": [6.0] * stunden,
                "wind_gusts_10m": [8.0] * stunden,
                "wind_direction_10m": [90.0] * stunden}

    def test_nur_die_abgedeckten_stunden(self):
        grob = self.basis(8)
        fein = {"time": [f"2026-07-15T{h:02d}:00" for h in range(12, 15)],
                "wind_speed_10m": [18.0, 19.0, 20.0],
                "wind_gusts_10m": [23.0, 24.0, 25.0],
                "wind_direction_10m": [180.0, 181.0, 182.0]}
        ersetzt = highres.einsetzen(grob, fein, "ICON-2I")
        self.assertEqual(ersetzt, 3)
        self.assertEqual(grob["wind_speed_10m"][:2], [6.0, 6.0])       # davor unberührt
        self.assertEqual(grob["wind_speed_10m"][2:5], [18.0, 19.0, 20.0])
        self.assertEqual(grob["wind_speed_10m"][5:], [6.0, 6.0, 6.0])  # danach wieder grob
        self.assertEqual(grob["wind_direction_10m"][2], 180.0)

    def test_unterschied_zum_groben_modell(self):
        """Die eigentliche Auskunft: deckt das Modell den Punkt nur ab — oder trifft es auch?"""
        grob = self.basis(4)
        fein = {"time": grob["time"][1:3], "wind_speed_10m": [18.0, 6.5],
                "wind_gusts_10m": [22.0, 8.0], "wind_direction_10m": [180.0, 90.0]}
        highres.einsetzen(grob, fein, "ICON-2I")
        # Stunde 1: das feine Modell sieht 12 kn mehr — da steckt eine Zirkulation.
        # Stunde 2: fast kein Unterschied, das grobe Gitter reichte schon.
        self.assertEqual(grob["wind_unterschied"], [None, 12.0, 0.5, None])

    def test_herkunft_wird_vermerkt(self):
        grob = self.basis(4)
        fein = {"time": ["2026-07-15T11:00"], "wind_speed_10m": [17.0],
                "wind_gusts_10m": [20.0], "wind_direction_10m": [200.0]}
        highres.einsetzen(grob, fein, "CH1")
        self.assertEqual(grob["wind_herkunft"], [None, "CH1", None, None])
        self.assertIn("CH1", grob["wind_models"])
        self.assertIn("grob", grob["wind_models"])     # die grobe Reihe bleibt vergleichbar

    def test_luecken_im_feinen_modell(self):
        grob = self.basis(4)
        fein = {"time": grob["time"], "wind_speed_10m": [15.0, None, 16.0, None],
                "wind_gusts_10m": [18.0, None, 19.0, None],
                "wind_direction_10m": [170.0, None, 171.0, None]}
        self.assertEqual(highres.einsetzen(grob, fein, "D2"), 2)
        self.assertEqual(grob["wind_speed_10m"], [15.0, 6.0, 16.0, 6.0])


class ImScoring(unittest.TestCase):
    """Kommt die feine Reihe wirklich bis in die Session an?"""

    def test_feine_reihe_ersetzt_den_wind_und_wird_vermerkt(self):
        from tests.helpers import cfg as load_cfg, SPOTS
        from wingscout.spots import load_spots
        from wingscout.demo import build as demo_build
        from wingscout.score import score_hours, build_sessions

        cfg = load_cfg()
        spot = [s for s in load_spots(SPOTS) if s["id"] == "torbole"][0]
        fc = demo_build([spot], 2)[spot["id"]]
        zeiten = fc["hourly"]["time"]
        tag2 = zeiten[24][:10]
        fenster = [t for t in zeiten if t.startswith(tag2) and 10 <= int(t[11:13]) < 18]
        ohne = score_hours(spot, fc, cfg)

        fc["_highres"] = ("italia_meteo_arpae_icon_2i", {
            "time": fenster,
            "wind_speed_10m": [19.0] * len(fenster),
            "wind_gusts_10m": [23.0] * len(fenster),
            "wind_direction_10m": [180.0] * len(fenster)})
        mit = score_hours(spot, fc, cfg)

        markiert = [r for r in mit if r.get("modell")]
        self.assertEqual(len(markiert), len(fenster))
        self.assertEqual({r["modell"] for r in markiert}, {"ICON-2I"})
        self.assertTrue(all(r["wind"] == 19.0 for r in markiert))
        # Außerhalb des Fensters bleibt alles, wie es war
        aussen = [(a["t"], a["wind"]) for a in ohne if not a["t"].isoformat()[:13] + ":00" in fenster]
        nachher = {b["t"]: b["wind"] for b in mit}
        for t, wind in aussen[:5]:
            self.assertEqual(nachher[t], wind)
        session = [s for s in build_sessions(spot, mit, cfg) if s.get("modell")]
        self.assertTrue(session, "die Session muss das Modell mitführen")
        self.assertEqual(session[0]["modell"], "ICON-2I")
