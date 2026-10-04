"""Modellvergleich im Rückblick: jedes Wettermodell einzeln gegen die Messung,
und das Gedächtnis über viele Prüfungen — ohne Netz."""
from __future__ import annotations
import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wingscout import modellvergleich as mv
from wingscout.pruefstand import masse
from wingscout.sources import historisch


def _reihe(werte: dict) -> dict:
    return {t: (v, 270.0) for t, v in werte.items()}


class Summen(unittest.TestCase):
    def test_summen_rechnen_wie_masse(self):
        """Zwei Wege, eine Zahl: der Vergleich rechnet über Summen (damit
        sich Tage und Spots addieren lassen), der Prüfstand direkt."""
        rnd = random.Random(7)
        stunden = [f"2026-09-{d:02d}T{h:02d}:00" for d in (18, 19) for h in range(24)]
        v = {t: (rnd.uniform(0, 25), rnd.uniform(0, 360)) for t in stunden}
        m = {t: (rnd.uniform(0, 25), rnd.choice([None, rnd.uniform(0, 360)])) for t in stunden[5:]}
        tag = {t for t in stunden if 8 <= int(t[11:13]) < 20}
        a, b = masse(v, m, tag), mv.masse_aus(mv.summen(v, m, tag))
        for k in ("n", "mae", "bias", "richtung", "richtung_n", "precision", "recall", "f1",
                  "gemessen_fahrbar", "gesagt_fahrbar", "fahrbar_n"):
            if isinstance(a[k], float):
                self.assertAlmostEqual(a[k], b[k], places=2, msg=k)
            else:
                self.assertEqual(a[k], b[k], k)
        # Je Tag getrennt und wieder zusammengezählt: dasselbe
        je_tag = mv.summen_je_tag(v, m, tag)
        self.assertEqual(sorted(je_tag), ["2026-09-18", "2026-09-19"])
        self.assertAlmostEqual(mv.masse_aus(mv.addiere(*je_tag.values()))["mae"], a["mae"], places=2)
        self.assertEqual(mv.masse_aus(mv.summen({}, m)), {"n": 0})


class Vergleich(unittest.TestCase):
    def test_sortiert_bestes_und_jetzt(self):
        stunden = [f"2026-09-19T{h:02d}:00" for h in range(24)] + [f"2026-09-20T{h:02d}:00" for h in range(24)]
        messung = {t: (12.0, 270.0) for t in stunden}
        reihen = [{"id": "gfs", "name": "GFS", "art": "global", "reihe": _reihe({t: 16.0 for t in stunden})},
                  {"id": "icon", "name": "ICON", "art": "global", "reihe": _reihe({t: 13.0 for t in stunden})},
                  {"id": "d2", "name": "ICON-D2", "art": "regional", "reihe": _reihe({t: 12.5 for t in stunden[:10]})}]
        wingscout = _reihe({t: 12.0 for t in stunden})
        vg = mv.vergleiche(reihen, wingscout, messung, set(stunden), "2026-09-20T11:00")
        self.assertEqual([z["id"] for z in vg["modelle"]], ["wingscout", "d2", "icon", "gfs"])
        self.assertEqual(vg["bestes"], "icon", "ICON-D2 hat nur 10 Stunden, Wingfoilscout ist kein Modell")
        icon = next(z for z in vg["modelle"] if z["id"] == "icon")
        self.assertEqual(icon["masse"]["n"], 24 + 12, "Stunden nach „jetzt“ zählen nicht")
        self.assertAlmostEqual(icon["masse"]["bias"], 1.0)
        self.assertEqual(sorted(vg["tage"]["icon"]), ["2026-09-19", "2026-09-20"])
        # Über zwei Spots zusammengezählt
        g = mv.gesamt([{"vergleich": vg}, {"vergleich": vg}, {"grund": "keine Station"}])
        icon_g = next(z for z in g if z["id"] == "icon")
        self.assertEqual((icon_g["spots"], icon_g["bestes"], icon_g["masse"]["n"]), (2, 2, 72))

    def test_reihen_holen(self):
        """Eine Anfrage für die globalen Modelle (Schlüssel mit Modell-Suffix),
        eine je Regionalmodell; was nicht antwortet, fehlt einfach."""
        zeiten = ["2026-09-19T12:00", "2026-09-19T13:00"]
        glob = {"utc_offset_seconds": 7200, "hourly": {
            "time": zeiten,
            "wind_speed_10m_dwd_icon_seamless": [10.0, 11.0], "wind_direction_10m_dwd_icon_seamless": [250, 260],
            "wind_speed_10m_ecmwf_ifs": [None, None], "wind_direction_10m_ecmwf_ifs": [None, None]}}
        fein = {"utc_offset_seconds": 7200, "hourly": {"time": zeiten, "wind_speed_10m": [14.0, 15.0],
                                                       "wind_direction_10m": [240, 245]}}
        spot = {"id": "brouwersdam", "name": "Brouwersdam", "lat": 51.76, "lon": 3.85, "country": "NL"}

        def regional(spot, modell, von, bis, tz):
            if modell == "knmi_harmonie_arome_netherlands":
                return fein
            raise historisch.HistorischError("HTTP 400")
        with mock.patch.object(historisch, "hole_bis_heute", return_value=glob) as h, \
                mock.patch.object(historisch, "hole_regional_bis_heute", side_effect=regional):
            reihen = mv.modellreihen(spot, "2026-09-19", "2026-09-19", "Europe/Amsterdam",
                                     globale=["dwd_icon_seamless", "ecmwf_ifs"])
        self.assertEqual(h.call_args.kwargs["hourly"], ["wind_speed_10m", "wind_direction_10m"])
        self.assertEqual([(r["id"], r["name"], r["art"]) for r in reihen],
                         [("dwd_icon_seamless", "ICON", "global"), ("knmi_harmonie_arome_netherlands", "HARMONIE", "regional")],
                         "ECMWF ohne Werte fehlt, die abgelehnten Regionalmodelle auch")
        self.assertEqual(reihen[0]["reihe"]["2026-09-19T10:00"], (10.0, 250.0), "Ortszeit → UTC")
        # Fällt die Anfrage der globalen Modelle aus, bleiben die regionalen
        with mock.patch.object(historisch, "hole_bis_heute", side_effect=historisch.HistorischError("weg")), \
                mock.patch.object(historisch, "hole_regional_bis_heute", side_effect=regional):
            reihen = mv.modellreihen(spot, "2026-09-19", "2026-09-19", "Europe/Amsterdam")
        self.assertEqual([r["id"] for r in reihen], ["knmi_harmonie_arome_netherlands"])


class Gedaechtnis(unittest.TestCase):
    def _ergebnis(self, bias: float, station: str = "1", tage=("2026-09-19",)) -> dict:
        stunden = [f"{tag}T{h:02d}:00" for tag in tage for h in range(24)]
        messung = {t: (12.0, 270.0) for t in stunden}
        reihen = [{"id": "icon", "name": "ICON", "art": "global", "reihe": _reihe({t: 12.0 + bias for t in stunden})},
                  {"id": "gfs", "name": "GFS", "art": "global", "reihe": _reihe({t: 14.0 for t in stunden})}]
        vg = mv.vergleiche(reihen, None, messung, set(stunden), "2099-01-01T00:00")
        return {"spots": [{"id": "b", "name": "Brouwersdam", "country": "NL",
                           "station": {"id": station, "km": 3.0}, "vergleich": vg},
                          {"id": "x", "name": "Ohne", "grund": "keine Station"}]}

    def test_ein_tag_zaehlt_einmal(self):
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "modellguete.json"
            mv.merken(self._ergebnis(1.0), pfad)
            daten = mv.merken(self._ergebnis(1.0), pfad)             # derselbe Tag noch einmal
            a = mv.auswerten(daten)
            icon = next(z for z in a["modelle"] if z["id"] == "icon")
            self.assertEqual((icon["masse"]["n"], icon["tage"], icon["spots"]), (24, 1, 1), "nicht doppelt gezählt")
            self.assertEqual((a["seit"], a["tage"], a["spots"]), ("2026-09-19", 1, 1))
            self.assertEqual(a["je_spot"][0]["bestes"], "ICON")
            # Die neue Prüfung ersetzt den Tag — und ein weiterer Tag kommt dazu
            daten = mv.merken(self._ergebnis(3.0, tage=("2026-09-19", "2026-09-20")), pfad)
            icon = next(z for z in mv.auswerten(daten)["modelle"] if z["id"] == "icon")
            self.assertEqual((icon["masse"]["n"], icon["tage"]), (48, 2))
            self.assertAlmostEqual(icon["masse"]["mae"], 3.0)
            # Eine andere Station: der Tag gilt neu, alte Modellsummen fallen weg
            e = self._ergebnis(1.0, station="2")
            e["spots"][0]["vergleich"]["tage"].pop("gfs")
            daten = mv.merken(e, pfad)
            tag = daten["spots"]["b"]["tage"]["2026-09-19"]
            self.assertEqual((tag["station"], sorted(tag["m"])), ("2", ["icon"]))
            gespeichert = json.loads(pfad.read_text(encoding="utf-8"))
            self.assertIn("stand", gespeichert)

    def test_nichts_zu_merken_schreibt_nichts(self):
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "modellguete.json"
            daten = mv.merken({"spots": [{"id": "x", "grund": "keine Station"}]}, pfad)
            self.assertFalse(pfad.exists())
            self.assertEqual(mv.auswerten(daten)["modelle"], [])
            pfad.write_text("kaputt", encoding="utf-8")
            self.assertEqual(mv.gedaechtnis_laden(pfad), {"version": 1, "spots": {}})

    def test_bisher_bestes(self):
        """„Bisher bestes Modell“: das beste am Spot laut Gedächtnis, sonst das
        beste über alle Spots — aber nur, wenn es am Spot eine Reihe hat."""
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "modellguete.json"
            daten = mv.merken(self._ergebnis(1.0, tage=("2026-09-18", "2026-09-19")), pfad)
            a = mv.auswerten(daten)
        self.assertEqual(a["je_spot"][0]["bestes_id"], "icon")
        self.assertEqual([m for m, _ in a["rangfolge"]], ["icon", "gfs"])
        zeile = {"id": "b", "modellnamen": {"icon": "ICON", "gfs": "GFS"}}
        bb = mv.bisher_bestes(zeile, a)
        self.assertEqual((bb["id"], bb["name"], bb["quelle"], bb["tage"]), ("icon", "ICON", "spot", 2))
        self.assertAlmostEqual(bb["mae"], 1.0)
        # Am Spot fehlt ICON in diesem Rückblick: das nächste in der Rangfolge des Spots
        bb = mv.bisher_bestes({"id": "b", "modellnamen": {"gfs": "GFS"}}, a)
        self.assertEqual((bb["id"], bb["quelle"]), ("gfs", "spot"))
        # Ein Spot ohne eigene Historie: die Rangliste über alle Spots
        bb = mv.bisher_bestes({"id": "neu", "modellnamen": {"icon": "ICON"}}, a)
        self.assertEqual((bb["id"], bb["quelle"]), ("icon", "gesamt"))
        # Nichts, was passt: keine Option — und die Wingfoilscout-Bewertung ist nie „bestes Modell“
        self.assertIsNone(mv.bisher_bestes({"id": "neu", "modellnamen": {"arome": "AROME"}}, a))
        self.assertIsNone(mv.bisher_bestes({"id": "b", "modellnamen": {}}, a))
        leer = mv.auswerten({"spots": {}})
        self.assertIsNone(mv.bisher_bestes(zeile, leer))

    def test_namen(self):
        self.assertEqual(mv.name("ecmwf_aifs025_single"), "ECMWF-KI")
        self.assertEqual(mv.name("dwd_icon_d2"), "ICON-D2")
        self.assertEqual(mv.name("irgendwas_seamless"), "IRGENDWAS")


if __name__ == "__main__":
    unittest.main()
