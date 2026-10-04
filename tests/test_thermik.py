"""Thermische Winde: die belegten Schwellen und das, was daraus folgt.

Die Zahlen in diesen Tests stammen aus der Recherche und stehen so auch im
Modul. Sie hier festzunageln ist der Punkt: wer sie später ändert, soll das
bewusst tun und die Quelle dazu nennen können.
"""
from __future__ import annotations
import unittest
from datetime import datetime

from tests.helpers import cfg as load_cfg
from wingscout import thermik


ORA = {"name": "Ora", "months": [5, 6, 7, 8, 9], "from": 13, "to": 20,
       "dir": 180, "typical_kn": 16, "reliability": 0.7}


class Gegenwind(unittest.TestCase):
    """Die Antwort auf den Gradientwind ist nicht fallend, sondern hat ein Maximum.

    Arritt 1993: die stärkste Seebrise entsteht bei leichtem ablandigem Wind,
    nicht bei Windstille — er hält die Brisenfront an der Küste fest.
    """

    def test_rueckenwind_stoert_nicht(self):
        # Gradient aus derselben Richtung wie die Thermik: keine Störung
        self.assertEqual(thermik.gegenwind_faktor(15, 180, 180), 1.0)

    def test_schwacher_gegenwind_verstaerkt(self):
        schwach = thermik.gegenwind_faktor(3, 0, 180)
        self.assertGreater(schwach, 1.0)
        self.assertAlmostEqual(schwach, thermik.VERSTAERKUNG, places=2)

    def test_der_verlauf_hat_ein_maximum(self):
        werte = [thermik.gegenwind_faktor(kn, 0, 180) for kn in range(0, 13)]
        self.assertEqual(werte.index(max(werte)), 3)          # Maximum bei 3 kn
        self.assertEqual(werte[-1], 0.0)                       # 12 kn: erstickt

    def test_bricht_bei_neun_knoten_ab(self):
        # Centro Meteo Ligure: ab 7–8 kn ablandig keine Seebrise mehr
        self.assertGreater(thermik.gegenwind_faktor(6, 0, 180), 0.9)
        self.assertLess(thermik.gegenwind_faktor(8, 0, 180), 0.2)
        self.assertEqual(thermik.gegenwind_faktor(9, 0, 180), 0.0)

    def test_ohne_bekannte_richtung_vorsichtig(self):
        # Kein `dir` im Katalog: der volle Wind zählt als Gegenwind
        self.assertEqual(thermik.gegenwind_faktor(12, 90, None), 0.0)


class Tagesgang(unittest.TestCase):
    def test_nur_im_fenster(self):
        self.assertEqual(thermik.tagesgang(12, 13, 20), 0.0)
        self.assertEqual(thermik.tagesgang(20, 13, 20), 0.0)
        self.assertGreater(thermik.tagesgang(16, 13, 20), 0.9)

    def test_baut_auf_und_flaut_ab(self):
        werte = [thermik.tagesgang(h, 13, 20) for h in range(13, 20)]
        self.assertLess(werte[0], werte[2])                    # baut auf
        self.assertLess(werte[-1], werte[3])                   # flaut ab


class Einstrahlung(unittest.TestCase):
    def test_energie_schlaegt_bewoelkung(self):
        # Ist die Energie bekannt, entscheidet sie — auch bei viel Bewölkung
        self.assertAlmostEqual(thermik.energie_faktor(1800, 90), 1.0, places=2)
        self.assertAlmostEqual(thermik.energie_faktor(0, 0), 0.0, places=2)

    def test_bewoelkung_als_rueckfall(self):
        self.assertGreater(thermik.energie_faktor(None, 0), 0.9)
        self.assertLess(thermik.energie_faktor(None, 100), 0.2)


class EinstrahlungDurchDieModelle(unittest.TestCase):
    def test_suffigierte_einstrahlung_kommt_bei_der_thermik_an(self):
        """Drei Modelle → `shortwave_radiation_dwd_icon_seamless`. Ein sonniger
        Tag mit dichter Hochbewölkung: die Einstrahlung sagt 1,0, die Bewölkung
        sagt 0,15. Bis 1.6.0 gewann die Bewölkung, weil die Einstrahlung beim
        Zusammenführen verloren ging."""
        from wingscout.score import score_hours
        cfg = load_cfg()
        tag, n = "2026-07-15", 24
        suffix = "_dwd_icon_seamless"
        fc = {"utc_offset_seconds": 7200,
              "hourly": {"time": [f"{tag}T{h:02d}:00" for h in range(n)],
                         f"wind_speed_10m{suffix}": [3.0] * n,
                         f"wind_gusts_10m{suffix}": [4.0] * n,
                         f"wind_direction_10m{suffix}": [180.0] * n,
                         f"temperature_2m{suffix}": [24.0] * n,
                         f"precipitation{suffix}": [0.0] * n,
                         f"cape{suffix}": [0.0] * n,
                         f"weather_code{suffix}": [2] * n,
                         f"cloud_cover{suffix}": [95.0] * n,
                         f"shortwave_radiation{suffix}": [0.0] * 6 + [700.0] * 12 + [0.0] * 6},
              "daily": {"time": [tag], f"sunrise{suffix}": [f"{tag}T05:30"],
                        f"sunset{suffix}": [f"{tag}T21:15"]}}
        spot = {"id": "t", "name": "T", "lat": 45.87, "lon": 10.87,
                "thermal": dict(ORA, months=[7]), "sectors": []}
        rows = {r["t"].hour: r for r in score_hours(spot, fc, cfg)}
        # 15 Uhr: Fenster offen, 6 300 Wh/m² seit Sonnenaufgang, Rückenwind.
        self.assertGreater(rows[15]["thermik_p"], 0.9, rows[15]["thermik_p"])
        self.assertTrue(rows[15]["thermal"], "Annahme greift bei voller Einstrahlung")


class Annahme(unittest.TestCase):
    def setUp(self):
        self.cfg = load_cfg()
        self.spot = {"thermal": ORA}
        self.sommer = datetime(2026, 7, 15, 15)

    def test_schoener_tag_bringt_thermik(self):
        wind, wdir, an, p = thermik.annahme(self.spot, self.sommer, 4.0, 200.0,
                                            self.cfg, 1800.0, 5.0)
        self.assertTrue(an)
        self.assertGreater(wind, 9.0)
        self.assertEqual(wdir, 180)
        self.assertGreater(p, 0.9)

    def test_staerke_ist_typische_staerke_mal_potenzial(self):
        """Die Verlässlichkeit steckt nicht mehr in den Knoten: 16 kn bei 70 %
        gaben bis 1.6.1 elf Knoten — eine Zahl, die an keinem Tag auftritt."""
        wind, _, an, p = thermik.annahme(self.spot, self.sommer, 4.0, 200.0,
                                         self.cfg, 1800.0, 5.0)
        self.assertTrue(an)
        self.assertAlmostEqual(wind, 16 * p, places=6)
        self.assertGreater(wind, 14.0)

    def test_bedeckter_tag_bringt_kaum_etwas(self):
        wind, _, an, p = thermik.annahme(self.spot, self.sommer, 4.0, 200.0,
                                         self.cfg, 120.0, 100.0)
        self.assertFalse(an)
        self.assertLess(p, 0.15)

    def test_kraeftiger_gegenwind_erstickt_sie(self):
        _, _, an, p = thermik.annahme(self.spot, self.sommer, 12.0, 0.0,
                                      self.cfg, 1800.0, 0.0)
        self.assertFalse(an)
        self.assertEqual(p, 0.0)

    def test_ausserhalb_der_saison(self):
        winter = datetime(2026, 1, 15, 15)
        _, _, an, p = thermik.annahme(self.spot, winter, 4.0, 200.0, self.cfg, 1800.0, 0.0)
        self.assertFalse(an)
        self.assertEqual(p, 0.0)

    def test_modellwind_schlaegt_annahme(self):
        # Zeigt das Modell schon mehr, wird nichts angenommen
        wind, _, an, _ = thermik.annahme(self.spot, self.sommer, 22.0, 180.0,
                                         self.cfg, 1800.0, 0.0)
        self.assertFalse(an)
        self.assertEqual(wind, 22.0)

    def test_spot_ohne_belegte_staerke_bekommt_keinen_wind(self):
        """Wo keine Quelle eine Zahl nennt, wird keine erfunden."""
        spot = {"thermal": {"name": "Seewind", "months": [7], "from": 12, "to": 19,
                            "reliability": 0.4}}
        wind, _, an, p = thermik.annahme(spot, self.sommer, 4.0, 200.0, self.cfg, 1800.0, 0.0)
        self.assertFalse(an)
        self.assertEqual(wind, 4.0)
        self.assertGreater(p, 0.0)              # gilt trotzdem als Thermikstunde

    def test_gesperrte_grundstroemung(self):
        """Der Malojawind kommt bei nördlicher Höhenströmung nicht (SRF Meteo)."""
        maloja = {"thermal": dict(ORA, name="Malojawind", dir=225, suppressed_by=[0, 45])}
        _, _, an, p = thermik.annahme(maloja, self.sommer, 8.0, 20.0, self.cfg, 1800.0, 0.0)
        self.assertFalse(an)
        self.assertEqual(p, 0.0)

    def test_abschaltbar(self):
        cfg = dict(self.cfg, thermal={"enabled": False})
        _, _, an, _ = thermik.annahme(self.spot, self.sommer, 4.0, 200.0, cfg, 1800.0, 0.0)
        self.assertFalse(an)


class Katalog(unittest.TestCase):
    """Was im Katalog steht, muss zum Modell passen."""

    def test_alle_thermikeintraege_sind_vollstaendig(self):
        from tests.helpers import SPOTS
        from wingscout.spots import load_spots
        mit = [s for s in load_spots(SPOTS) if s.get("thermal")]
        self.assertGreater(len(mit), 50)
        for s in mit:
            th = s["thermal"]
            with self.subTest(spot=s["id"]):
                self.assertIn("source", th, "jeder Eintrag braucht seine Quelle")
                self.assertTrue(th.get("note"))
                self.assertTrue(th.get("months"))
                self.assertLessEqual(max(th["months"]), 12)
                self.assertLess(th["from"], th["to"])
                self.assertLessEqual(th["to"], 24)
                if th.get("dir") is not None:
                    self.assertTrue(0 <= th["dir"] < 360)
                if th.get("typical_kn"):
                    self.assertTrue(3 < th["typical_kn"] < 40)
                    self.assertTrue(0 < th["reliability"] <= 1)


class Tagespotenzial(unittest.TestCase):
    """Der Balken zeigte das Maximum und stand deshalb immer auf Anschlag.

    Im Lauf vom 16.09.2026 lagen alle fünf Thermikziele zwischen 96 und
    100 Prozent — der Balken unterschied nichts.
    """

    TH = {"from": 12, "to": 19, "reliability": 0.8, "dir": 225}

    def _werte(self, faktor):
        """Ein ganzer Tag, in dem die Bedingungen konstant `faktor` gut sind."""
        return [(h, thermik.tagesgang(h, 12, 19) * faktor) for h in range(24)]

    def test_ideale_bedingungen_ergeben_die_verlaesslichkeit(self):
        self.assertAlmostEqual(thermik.tagespotenzial(self.TH, self._werte(1.0)), 0.8, places=3)

    def test_halbe_einstrahlung_halbiert(self):
        self.assertAlmostEqual(thermik.tagespotenzial(self.TH, self._werte(0.5)), 0.4, places=3)

    def test_erstickte_thermik_ergibt_null(self):
        self.assertEqual(thermik.tagespotenzial(self.TH, self._werte(0.0)), 0.0)

    def test_eine_gute_stunde_macht_keinen_guten_tag(self):
        """Genau der Fall, an dem das Maximum scheiterte."""
        werte = [(h, thermik.tagesgang(h, 12, 19) * (1.0 if h == 15 else 0.1)) for h in range(24)]
        p = thermik.tagespotenzial(self.TH, werte)
        self.assertLess(p, 0.3)
        self.assertGreater(p, 0.0)

    def test_verlaesslichkeit_trennt_zwei_gleiche_tage(self):
        stark = dict(self.TH, reliability=0.95)
        schwach = dict(self.TH, reliability=0.4)
        self.assertGreater(thermik.tagespotenzial(stark, self._werte(1.0)),
                           thermik.tagespotenzial(schwach, self._werte(1.0)) + 0.5)

    def test_stunden_ausserhalb_des_fensters_zaehlen_nicht(self):
        drin = self._werte(1.0)
        plus = drin + [(h, 0.0) for h in (3, 4, 5)]
        self.assertAlmostEqual(thermik.tagespotenzial(self.TH, drin),
                               thermik.tagespotenzial(self.TH, plus), places=6)

    def test_leere_eingabe(self):
        self.assertEqual(thermik.tagespotenzial(self.TH, []), 0.0)


class ThermikRaster(unittest.TestCase):
    """Eigenes Stundenraster für die Thermikspots — und ein Ring, der nichts abfängt."""

    def _rows(self, tag="2026-09-17", angenommen=(15,)):
        from datetime import datetime, timedelta
        start = datetime.fromisoformat(tag + "T00:00")
        rows = []
        for h in range(24):
            t = start + timedelta(hours=h)
            drin = 12 <= h < 19
            p = thermik.tagesgang(h, 12, 19) if drin else 0.0
            rows.append({"t": t, "day": tag, "wind": 16.0 if h in angenommen else 7.0,
                         "thermik_p": round(p, 2), "thermik_tag": 0.8,
                         "thermal": h in angenommen})
        return rows

    def _spot(self, sid, monate, name="Ora"):
        return {"id": sid, "name": sid.title(), "lat": 45.87, "lon": 10.87,
                "thermal": {"name": name, "from": 12, "to": 19, "months": monate,
                            "typical_kn": 16, "reliability": 0.8, "dir": 180}}

    def test_farben_trennen_die_drei_zustaende(self):
        from wingscout.report import _thermik_zelle
        aus = _thermik_zelle(0.0, False)
        tot = _thermik_zelle(0.0, True)
        schwach = _thermik_zelle(0.3, True)
        voll = _thermik_zelle(1.15, True)
        self.assertEqual(len({aus, tot, schwach, voll}), 4, "jeder Zustand braucht eine eigene Farbe")
        self.assertIn("surface-2", aus)
        self.assertNotIn("217,138,43", tot, "die erstickte Zelle darf nicht orange sein")
        self.assertIn("217,138,43", schwach)
        # Stärkeres Potenzial heißt kräftigere Farbe.
        self.assertGreater(float(voll.rsplit(",", 1)[1].rstrip(")")),
                           float(schwach.rsplit(",", 1)[1].rstrip(")")))

    def test_zeile_je_spot_in_saison(self):
        from wingscout.report import _thermik_raster
        from tests.helpers import cfg as load_cfg
        all_rows = {
            "a": (self._spot("garda", [5, 6, 7, 8, 9]), self._rows()),
            "b": (self._spot("winterspot", [1, 2]), self._rows()),
            "c": ({"id": "c", "name": "Ohne", "lat": 50.0, "lon": 8.0}, self._rows()),
        }
        html = _thermik_raster(all_rows, load_cfg(), {"lat": 49.4, "lon": 8.7})
        self.assertIn("Garda", html)
        self.assertNotIn("Winterspot", html, "außerhalb der Saison gehört der Spot nicht ins Raster")
        self.assertNotIn("Ohne", html, "ohne Thermikwissen gibt es keine Zeile")
        self.assertIn("grid-template-columns:repeat(24,1fr)", html)

    def test_angenommene_stunde_bekommt_einen_rahmen(self):
        from wingscout.report import _thermik_raster
        from tests.helpers import cfg as load_cfg
        html = _thermik_raster({"a": (self._spot("garda", [9]), self._rows(angenommen=(15, 16)))},
                               load_cfg(), {"lat": 49.4, "lon": 8.7})
        self.assertEqual(html.count("class='cell tan'"), 2)
        self.assertIn("angenommen 16 kn", html)
        self.assertIn("außerhalb des Thermikfensters", html)

    def test_leeres_raster_bleibt_leer(self):
        from wingscout.report import _thermik_raster
        from tests.helpers import cfg as load_cfg
        self.assertEqual(_thermik_raster({}, load_cfg(), {"lat": 49.4, "lon": 8.7}), "")


class ThermikRingAufDerKarte(unittest.TestCase):
    """Der Ring lag über dem Spot und schluckte den Klick auf die Einzelheiten."""

    def _js(self):
        from tests.helpers import cfg as load_cfg
        from wingscout.report import _map_block
        import argparse
        args = argparse.Namespace(radius=500, days=3, demo=True, start_name=None)
        return _map_block([], {}, [], load_cfg(), args)

    def test_ring_ist_dreifach_entschaerft(self):
        js = self._js()
        self.assertIn("interactive: false", js)
        self.assertIn("pane: 'dekor'", js)                 # seit 1.9.0 die Ebene für alle Dekoration
        self.assertIn("createPane('dekor')", js)
        self.assertIn("pointerEvents = 'none'", js)

    def test_name_der_thermik_haengt_am_punkt_nicht_am_ring(self):
        js = self._js()
        ring = js[js.find("L.circleMarker([m.lat, m.lon], {radius: 13"):]
        ring = ring[:ring.find("addTo(ebenen.thermik)")]
        self.assertNotIn("bindTooltip", ring, "der Ring darf keinen eigenen Tooltip mehr haben")
        self.assertIn("esc(m.name) + (m.thermik ?", js)
