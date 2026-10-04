"""Session-Tagebuch: Eingabe prüfen, Datei, Auswertung, Vorschläge, Übernehmen.

Ohne Netz: der Vergleich mit Vorhersage und Messung bekommt die Rechnung des
Rückblicks untergeschoben. Geschrieben wird nur in Temporärordner.
"""
from __future__ import annotations
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path

import yaml

from tests.helpers import cfg as load_cfg, CONFIG, SPOTS
from wingscout import tagebuch as tb
from wingscout.config import load_config

WINGS = [{"size": 6.5, "low": 10, "high": 17}, {"size": 5.0, "low": 13, "high": 22},
         {"size": 4.2, "low": 15, "high": 26}]
SPOTS_BY_ID = {"brouwersdam": {"id": "brouwersdam", "name": "Brouwersdam", "wind_factor": 1.0},
               "gardasee": {"id": "gardasee", "name": "Torbole", "wind_factor": 1.2}}
JETZT = datetime(2026, 9, 20, 17, 0)


def roh(**aenderung) -> dict:
    d = {"spot": "brouwersdam", "datum": "2026-09-19", "von": "14:30", "bis": "16:10", "wing": "5",
         "leistung": "passt", "wasser": "kabbelig", "note": "4"}
    d.update(aenderung)
    return d


def session(wing=5.0, leistung="passt", gemessen=None, km=5.0, vorhersage=None, roh_kn=None,
            spot="brouwersdam", datum="2026-09-19", sid=None) -> dict:
    vg = {"station": {"quelle": "RWS", "name": "Test", "km": km}, "gemessen_kn": gemessen,
          "wingscout_kn": vorhersage, "roh_kn": roh_kn}
    return {"id": sid or f"{leistung}{gemessen}{vorhersage}{roh_kn}", "spot": spot, "datum": datum,
            "von": "14:00", "bis": "16:00", "wing": wing, "leistung": leistung, "wasser": "flach", "note": 3,
            "vergleich": vg}


class Eingabe(unittest.TestCase):
    def test_saubere_eingabe(self):
        e = tb.pruefe(roh(von="9:05"), SPOTS_BY_ID, WINGS, jetzt=JETZT)
        self.assertEqual(e, {"spot": "brouwersdam", "datum": "2026-09-19", "von": "09:05", "bis": "16:10",
                             "wing": 5.0, "leistung": "passt", "wasser": "kabbelig", "note": 4})

    def test_fehler_werden_benannt(self):
        faelle = [(roh(spot="gibtsnicht"), "Unbekannter Spot"),
                  (roh(datum="19.09.2026"), "Datum"),
                  (roh(datum="2026-09-21"), "Zukunft"),
                  (roh(von="25:00"), "Uhrzeit"),
                  (roh(von="16:00", bis="15:00"), "nach „von“"),
                  (roh(von="15:00", bis="15:00"), "nach „von“"),
                  (roh(wing="5.5"), "nicht im Quiver"),
                  (roh(wing=""), "Wing fehlt"),
                  (roh(leistung="super"), "Leistung"),
                  (roh(wasser=""), "Wasser"),
                  (roh(note="6"), "1 bis 5"),
                  (roh(note="x"), "Note fehlt"),
                  (roh(datum="2026-09-20", von="18:00", bis="19:00"), "beginnt erst")]
        for eingabe, text in faelle:
            with self.subTest(text=text), self.assertRaises(tb.TagebuchFehler) as cm:
                tb.pruefe(eingabe, SPOTS_BY_ID, WINGS, jetzt=JETZT)
            self.assertIn(text, str(cm.exception))

    def test_heute_laufende_session_geht(self):
        e = tb.pruefe(roh(datum="2026-09-20", von="15:00", bis="18:00"), SPOTS_BY_ID, WINGS, jetzt=JETZT)
        self.assertEqual(e["bis"], "18:00")

    def test_stunden_der_session(self):
        self.assertEqual(tb.stunden_der_session({"von": "14:30", "bis": "16:10"}), [14, 15, 16])
        self.assertEqual(tb.stunden_der_session({"von": "14:00", "bis": "16:00"}), [14, 15])
        self.assertEqual(tb.stunden_der_session({"von": "14:00", "bis": "14:30"}), [14])


class Datei(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pfad = Path(self.tmp.name) / "tagebuch.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_leer_und_kaputt_ergeben_ein_leeres_tagebuch(self):
        self.assertEqual(tb.laden(self.pfad)["sessions"], [])
        self.pfad.write_text("{kaputt", encoding="utf-8")
        self.assertEqual(tb.laden(self.pfad)["sessions"], [])

    def test_eintragen_loeschen(self):
        a = tb.eintragen(tb.pruefe(roh(), SPOTS_BY_ID, WINGS, jetzt=JETZT), self.pfad)
        b = tb.eintragen(tb.pruefe(roh(leistung="unter"), SPOTS_BY_ID, WINGS, jetzt=JETZT), self.pfad)
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(len(tb.laden(self.pfad)["sessions"]), 2)
        self.assertTrue(tb.loeschen(a["id"], self.pfad))
        self.assertFalse(tb.loeschen(a["id"], self.pfad))
        self.assertEqual([s["id"] for s in tb.laden(self.pfad)["sessions"]], [b["id"]])

    def test_vergleich_landet_in_der_datei_wie_sie_jetzt_ist(self):
        """Während der Vergleich läuft, wird eine Session gelöscht und eine
        eingetragen — das Zurückschreiben darf beides nicht zurückdrehen."""
        a = tb.eintragen(dict(tb.pruefe(roh(), SPOTS_BY_ID, WINGS, jetzt=JETZT)), self.pfad)
        b = tb.eintragen(dict(tb.pruefe(roh(), SPOTS_BY_ID, WINGS, jetzt=JETZT)), self.pfad)
        tb.loeschen(b["id"], self.pfad)
        c = tb.eintragen(dict(tb.pruefe(roh(), SPOTS_BY_ID, WINGS, jetzt=JETZT)), self.pfad)
        n = tb.vergleich_eintragen({a["id"]: {"gemessen_kn": 15.0}, b["id"]: {"gemessen_kn": 1.0}}, self.pfad)
        self.assertEqual(n, {"neu": 1, "behalten": 0})
        daten = {s["id"]: s for s in tb.laden(self.pfad)["sessions"]}
        self.assertEqual(set(daten), {a["id"], c["id"]})
        self.assertEqual(daten[a["id"]]["vergleich"], {"gemessen_kn": 15.0})
        self.assertNotIn("vergleich", daten[c["id"]])


    def test_ein_fehlschlag_loescht_keine_messung(self):
        a = tb.eintragen(dict(tb.pruefe(roh(), SPOTS_BY_ID, WINGS, jetzt=JETZT)), self.pfad)
        tb.vergleich_eintragen({a["id"]: {"gemessen_kn": 15.0, "wingscout_kn": 17.0}}, self.pfad)
        zahl = tb.vergleich_eintragen({a["id"]: {"grund": "nicht abrufbar (Netz)", "gerechnet": "x"}}, self.pfad)
        self.assertEqual(zahl, {"neu": 0, "behalten": 1})
        vg = tb.laden(self.pfad)["sessions"][0]["vergleich"]
        self.assertEqual(vg["gemessen_kn"], 15.0)
        self.assertEqual(vg["letzter_versuch"]["grund"], "nicht abrufbar (Netz)")
        # Mehr Wissen ersetzt den alten Stand samt Vermerk
        tb.vergleich_eintragen({a["id"]: {"gemessen_kn": 14.0, "wingscout_kn": 16.0}}, self.pfad)
        self.assertNotIn("letzter_versuch", tb.laden(self.pfad)["sessions"][0]["vergleich"])


class Auswertung(unittest.TestCase):
    def test_nur_die_stunden_der_session(self):
        s = {"datum": "2026-09-19", "von": "14:30", "bis": "15:30"}
        zeile = {"station": {"km": 4.0}, "stunden": [
            {"t": "2026-09-19T13:00", "v": 30.0, "m": 30.0, "mv": {"icon": 30.0}},
            {"t": "2026-09-19T14:00", "v": 16.0, "m": 14.0, "mv": {"icon": 13.0, "ecmwf": 17.0}},
            {"t": "2026-09-19T15:00", "v": 18.0, "m": None, "mv": {"icon": 15.0, "ecmwf": 19.0}},
            {"t": "2026-09-20T14:00", "v": 40.0, "m": 40.0, "mv": {}}]}
        rows = [{"t": datetime(2026, 9, 19, 14), "wind": 16.0, "thermal": False, "wing": 5.0, "water": "chop", "score": 0.6},
                {"t": datetime(2026, 9, 19, 15), "wind": 18.0, "thermal": True, "wing": 5.0, "water": "chop", "score": 0.8},
                {"t": datetime(2026, 9, 19, 16), "wind": 30.0, "thermal": False, "wing": 4.2, "water": "wave", "score": 0.1}]
        a = tb.auswerten(s, zeile, rows, wind_factor=1.25)
        self.assertEqual(a["wingscout_kn"], 17.0)
        self.assertEqual(a["gemessen_kn"], 14.0)
        self.assertEqual(a["gemessen_h"], 1)
        self.assertEqual(a["modelle"], {"icon": 14.0, "ecmwf": 18.0})
        self.assertEqual(a["spanne"], [14.0, 18.0])
        self.assertTrue(a["thermik"])
        # roh: nur die Stunde ohne Thermikannahme, zurückgerechnet ohne Windfaktor
        self.assertEqual(a["roh_kn"], 12.8)
        self.assertEqual(a["wing_vorschlag"], 5.0)
        self.assertEqual(a["wasser_vorhersage"], "kabbelig")
        self.assertEqual(a["score"], 70)

    def test_ohne_stunden_steht_ein_grund(self):
        a = tb.auswerten({"datum": "2026-09-19", "von": "14:00", "bis": "15:00"}, {"stunden": []}, None, 1.0)
        self.assertIn("keine Stunden", a["grund"])

    def test_wind_der_session(self):
        self.assertEqual(tb.wind_der_session(session(gemessen=15.0, km=5, vorhersage=18.0))[0], 15.0)
        wind, basis = tb.wind_der_session(session(gemessen=15.0, km=25, vorhersage=18.0))
        self.assertEqual((wind, basis), (18.0, "Wingfoilscout-Vorhersage"))
        self.assertEqual(tb.wind_der_session(session())[0], None)


class Windfenster(unittest.TestCase):
    def vorschlag(self, sessions, groesse=5.0):
        return next(v for v in tb.vorschlaege_windfenster(sessions, WINGS) if v["size"] == groesse)

    def test_untermotorisiert_im_fenster_hebt_die_untergrenze(self):
        v = self.vorschlag([session(leistung="unter", gemessen=14.2), session(leistung="unter", gemessen=15.4)])
        self.assertEqual((v["low_neu"], v["high_neu"]), (16, None))
        self.assertEqual(len(v["belege"]), 2)

    def test_eine_session_reicht_nicht(self):
        v = self.vorschlag([session(leistung="unter", gemessen=15.4)])
        self.assertEqual((v["low_neu"], v["high_neu"]), (None, None))

    def test_widerspruch_gibt_keinen_vorschlag(self):
        v = self.vorschlag([session(leistung="unter", gemessen=14.2), session(leistung="unter", gemessen=15.4),
                            session(leistung="passt", gemessen=14.8)])
        self.assertIsNone(v["low_neu"])
        self.assertIn("widersprüchlich", v["gruende"][0])

    def test_passt_unter_der_untergrenze_weitet(self):
        v = self.vorschlag([session(gemessen=11.3), session(gemessen=12.1)])
        self.assertEqual(v["low_neu"], 11)

    def test_passt_unten_gegen_untermotorisiert(self):
        v = self.vorschlag([session(gemessen=11.3), session(gemessen=12.1),
                            session(leistung="unter", gemessen=12.0)])
        self.assertIsNone(v["low_neu"])
        self.assertIn("widersprüchlich", " ".join(v["gruende"]))

    def test_uebermotorisiert_senkt_die_obergrenze(self):
        v = self.vorschlag([session(leistung="ueber", gemessen=18.6), session(leistung="ueber", gemessen=20.0)])
        self.assertEqual(v["high_neu"], 18)

    def test_passt_ueber_der_obergrenze_weitet(self):
        v = self.vorschlag([session(gemessen=23.2), session(gemessen=24.6)])
        self.assertEqual(v["high_neu"], 25)

    def test_ferne_station_zaehlt_nicht_die_vorhersage_schon(self):
        v = self.vorschlag([session(leistung="unter", gemessen=15.0, km=25, vorhersage=14.0),
                            session(leistung="unter", gemessen=15.0, km=25, vorhersage=14.5)])
        self.assertEqual(v["low_neu"], 15)
        self.assertEqual({b["basis"] for b in v["belege"]}, {"Wingfoilscout-Vorhersage"})

    def test_kein_fenster_mehr_wird_nicht_vorgeschlagen(self):
        v = self.vorschlag([session(leistung="unter", gemessen=21.0), session(leistung="unter", gemessen=21.5),
                            session(leistung="ueber", gemessen=14.0), session(leistung="ueber", gemessen=13.2)])
        self.assertEqual((v["low_neu"], v["high_neu"]), (None, None))
        self.assertIn("kein Fenster", v["gruende"][-1])


class Windfaktor(unittest.TestCase):
    """5,0 m²: 13–22 kn. Eine Session mit rohem Modellwind r verlangt bei
    „passt“ einen Faktor zwischen 13/r und 22/r."""

    def vorschlag(self, sessions):
        return tb.vorschlaege_windfaktor(sessions, WINGS, SPOTS_BY_ID)

    def test_passende_sessions_bestaetigen(self):
        # roh 15 und 16: erlaubt 0,87–1,47 und 0,81–1,38 — 1,0 liegt drin
        v = self.vorschlag([session(roh_kn=15.0), session(roh_kn=16.0)])
        self.assertIsNone(v[0]["neu"])
        self.assertIn("passen zum Faktor 1", v[0]["grund"])
        self.assertIn("0,87–1,38", v[0]["grund"])

    def test_zu_wenig_modellwind_hebt_den_faktor(self):
        # roh 10 und 10,5 bei „passt“: mindestens 1,30 und 1,24 → 1,3
        v = self.vorschlag([session(roh_kn=10.0), session(roh_kn=10.5)])
        self.assertEqual(v[0]["neu"], 1.3)
        self.assertEqual(len(v[0]["belege"]), 2)

    def test_eine_session_reicht_nicht(self):
        v = self.vorschlag([session(roh_kn=10.0), session(roh_kn=15.0)])
        self.assertIsNone(v[0]["neu"])
        self.assertIn("1 Session spricht für einen höheren", v[0]["grund"])

    def test_untermotorisiert_senkt_den_faktor(self):
        # untermotorisiert bei roh 16 und 17: höchstens 0,81 und 0,76 → 0,75
        v = self.vorschlag([session(leistung="unter", roh_kn=16.0), session(leistung="unter", roh_kn=17.0)])
        self.assertEqual(v[0]["neu"], 0.75)

    def test_uebermotorisiert_hebt_den_faktor(self):
        # übermotorisiert bei roh 20 und 21: mindestens 1,10 und 1,05 → 1,1
        v = self.vorschlag([session(leistung="ueber", roh_kn=20.0), session(leistung="ueber", roh_kn=21.0)])
        self.assertEqual(v[0]["neu"], 1.1)

    def test_widerspruch(self):
        # passt bei roh 10 verlangt ≥ 1,30, untermotorisiert bei roh 12 verlangt < 1,08
        v = self.vorschlag([session(roh_kn=10.0), session(roh_kn=10.5), session(leistung="unter", roh_kn=12.0)])
        self.assertIsNone(v[0]["neu"])
        self.assertIn("widersprüchlich", v[0]["grund"])

    def test_grenzen(self):
        v = self.vorschlag([session(roh_kn=6.0), session(roh_kn=6.5)])
        self.assertEqual(v[0]["neu"], 1.5)
        self.assertIn("begrenzt auf 1,5", v[0]["grund"])

    def test_thermik_und_fehlender_modellwind_zaehlen_nicht(self):
        self.assertEqual(self.vorschlag([session(roh_kn=None), session(roh_kn=0.2)]), [])


class Ueberschneidung(unittest.TestCase):
    def test_dieselben_sessions_tragen_beide_vorschlaege(self):
        """Zweimal untermotorisiert auf dem 5,0er bei 14 und 15 kn gemessen, die
        Modelle sagten roh 16 und 17: das Windfenster soll steigen — und der
        Windfaktor sinken. Die Seite muss sagen, dass das derselbe Befund ist."""
        sessions = [session(leistung="unter", gemessen=14.2, roh_kn=16.0, sid="a"),
                    session(leistung="unter", gemessen=15.4, roh_kn=17.0, sid="b")]
        cfg = {"quiver": {"wings": WINGS}}
        vs = tb.vorschlaege({"sessions": sessions}, cfg, SPOTS_BY_ID)
        fenster = next(w for w in vs["windfenster"] if w["size"] == 5.0)
        self.assertEqual(fenster["low_neu"], 16)
        self.assertEqual(vs["windfaktor"][0]["neu"], 0.75)
        self.assertTrue(fenster["ueberschneidung"])
        self.assertTrue(vs["windfaktor"][0]["ueberschneidung"])
        self.assertIn("bis 0,76", vs["windfaktor"][0]["grund"])

    def test_ohne_gemeinsame_sessions_kein_hinweis(self):
        sessions = [session(roh_kn=10.0, gemessen=17.0, sid="a"), session(roh_kn=10.5, gemessen=17.0, sid="b")]
        vs = tb.vorschlaege({"sessions": sessions}, {"quiver": {"wings": WINGS}}, SPOTS_BY_ID)
        self.assertEqual(vs["windfaktor"][0]["neu"], 1.3)
        self.assertFalse(vs["windfaktor"][0]["ueberschneidung"])


class Uebernehmen(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name) / "config.yaml"
        shutil.copy(CONFIG, self.cfg)

    def tearDown(self):
        self.tmp.cleanup()

    def test_wing_setzen_aendert_nur_diese_zeile(self):
        vorher = self.cfg.read_text(encoding="utf-8").splitlines()
        tb.wing_setzen(self.cfg, 5.0, 15, 22)
        nachher = self.cfg.read_text(encoding="utf-8").splitlines()
        anders = [(a, b) for a, b in zip(vorher, nachher) if a != b]
        self.assertEqual(len(vorher), len(nachher))
        self.assertEqual(len(anders), 1)
        self.assertIn("size: 5.0", anders[0][1])
        wing = next(w for w in load_config(self.cfg)["quiver"]["wings"] if w["size"] == 5.0)
        self.assertEqual((wing["low"], wing["high"]), (15, 22))

    def test_unbekannter_wing_und_unsinn(self):
        with self.assertRaises(tb.TagebuchFehler):
            tb.wing_setzen(self.cfg, 5.5, 15, 22)
        with self.assertRaises(tb.TagebuchFehler):
            tb.wing_setzen(self.cfg, 5.0, 22, 15)

    def test_nur_der_aktuelle_vorschlag(self):
        vs = {"windfenster": [{"size": 5.0, "low": 13, "high": 22, "low_neu": 16, "high_neu": None}],
              "windfaktor": [{"id": "brouwersdam", "neu": 1.15}, {"id": "gardasee", "neu": None}]}
        self.assertEqual(tb.passender_vorschlag(vs, {"art": "windfenster", "size": 5, "low": 16, "high": 22}),
                         {"art": "windfenster", "size": 5.0, "low": 16.0, "high": 22.0})
        self.assertEqual(tb.passender_vorschlag(vs, {"art": "windfaktor", "id": "brouwersdam", "wert": 1.15})["wert"],
                         1.15)
        for eingabe in ({"art": "windfenster", "size": 5, "low": 17, "high": 22},
                        {"art": "windfenster", "size": 6.5, "low": 10, "high": 17},
                        {"art": "windfenster", "size": "x"},
                        {"art": "windfaktor", "id": "gardasee", "wert": 1.2},
                        {"art": "windfaktor", "id": "brouwersdam", "wert": 1.3},
                        {"art": "irgendwas"}):
            with self.subTest(eingabe=eingabe), self.assertRaises(tb.TagebuchFehler):
                tb.passender_vorschlag(vs, eingabe)


class Vergleich(unittest.TestCase):
    """`vergleichen` mit untergeschobener Rechnung des Rückblicks."""

    def setUp(self):
        from wingscout import rueckblick
        from wingscout.sources import stationen
        self.rb, self.st = rueckblick, stationen
        self.alt = (rueckblick.spot_zeile, stationen.paare_finden, tb._nur_vorhersage)
        stationen.paare_finden = lambda spots, km, log=None: [{"spot": spots[0]}]

    def tearDown(self):
        self.rb.spot_zeile, self.st.paare_finden, tb._nur_vorhersage = self.alt

    def test_mit_messung(self):
        rows = [{"t": datetime(2026, 9, 19, 14), "wind": 15.0, "thermal": False, "wing": 5.0, "water": "flat", "score": 0.5}]
        self.rb.spot_zeile = lambda *a, **k: ({"station": {"km": 3.0, "name": "X", "quelle": "DWD"},
                                              "stunden": [{"t": "2026-09-19T14:00", "v": 15.0, "m": 13.0, "mv": {}}]}, rows)
        s = session(sid="a")
        tb.vergleichen(load_cfg(), SPOTS_BY_ID, {}, [s], jetzt=datetime(2026, 9, 20, 10))
        self.assertEqual(s["vergleich"]["gemessen_kn"], 13.0)
        self.assertEqual(s["vergleich"]["wasser_vorhersage"], "flach")
        self.assertIn("gerechnet", s["vergleich"])

    def test_ohne_messung_bleibt_die_vorhersage(self):
        self.rb.spot_zeile = lambda *a, **k: ({"station": {"km": 8.0}, "grund": "die Station hat für diese Tage "
                                              "noch keine Werte veröffentlicht"}, None)
        rows = [{"t": datetime(2026, 9, 19, 14), "wind": 15.0, "thermal": False}]
        tb._nur_vorhersage = lambda *a, **k: ({"stunden": [{"t": "2026-09-19T14:00", "v": 15.0, "m": None,
                                                           "mv": {"icon": 14.0, "gfs": 16.0}}]}, rows)
        s = session(sid="b")
        tb.vergleichen(load_cfg(), SPOTS_BY_ID, {}, [s], jetzt=datetime(2026, 9, 20, 10))
        vg = s["vergleich"]
        self.assertEqual(vg["wingscout_kn"], 15.0)
        self.assertIsNone(vg["gemessen_kn"])
        self.assertEqual(vg["spanne"], [14.0, 16.0])
        self.assertIn("nur die Vorhersage", vg["grund"])
        self.assertEqual(vg["station"], {"km": 8.0})

    def test_ohne_stationsliste_bleibt_die_vorhersage(self):
        def weg(*a, **k):
            raise OSError("Tunnel connection failed")
        self.st.paare_finden = weg
        self.rb.spot_zeile = lambda *a, **k: ({"station": None, "grund": "keine Messstation in 30 km"}, None)
        tb._nur_vorhersage = lambda *a, **k: ({"stunden": [{"t": "2026-09-19T14:00", "v": 15.0, "m": None,
                                                           "mv": {}}]}, [])
        s = session(sid="c")
        tb.vergleichen(load_cfg(), SPOTS_BY_ID, {}, [s], jetzt=datetime(2026, 9, 20, 10))
        self.assertEqual(s["vergleich"]["wingscout_kn"], 15.0)
        self.assertIn("Stationen nicht abrufbar (Tunnel", s["vergleich"]["grund"])

    def test_fehler_kostet_nur_diese_session(self):
        def kaputt(*a, **k):
            raise OSError("Zeitüberschreitung")
        self.rb.spot_zeile = kaputt
        a, b = session(sid="a"), session(sid="b", spot="weg")
        tb.vergleichen(load_cfg(), SPOTS_BY_ID, {}, [a, b], jetzt=datetime(2026, 9, 20, 10))
        self.assertIn("Zeitüberschreitung", a["vergleich"]["grund"])
        self.assertIn("nicht mehr im Katalog", b["vergleich"]["grund"])


class Oberflaeche(unittest.TestCase):
    """Seite und Endpunkte gegen Kopien von Konfiguration, Katalog und Tagebuch."""

    @classmethod
    def setUpClass(cls):
        import wingscout.webui as w
        cls.w = w
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        cls.cfg, cls.spots, cls.buch = d / "config.yaml", d / "spots.yaml", d / "tagebuch.json"
        shutil.copy(CONFIG, cls.cfg)
        shutil.copy(SPOTS, cls.spots)
        cls.alt = (w.Handler.cfg_path, w.SPOTS_FILE, tb.TAGEBUCH, w.start_tagebuch)
        w.Handler.cfg_path, w.SPOTS_FILE, tb.TAGEBUCH = str(cls.cfg), cls.spots, cls.buch
        cls.gestartet = []
        w.start_tagebuch = lambda cfg_path, ids: cls.gestartet.append(list(ids)) or True
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), w.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.spot = yaml.safe_load(cls.spots.read_text(encoding="utf-8"))[0]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        w = cls.w
        w.Handler.cfg_path, w.SPOTS_FILE, tb.TAGEBUCH, w.start_tagebuch = cls.alt
        cls.tmp.cleanup()

    def setUp(self):
        self.buch.unlink(missing_ok=True)
        self.gestartet.clear()

    def post(self, pfad, daten, origin=True):
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = f"http://127.0.0.1:{self.port}"
        else:
            headers["Origin"] = "https://fremd.example"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{pfad}", data=json.dumps(daten).encode(),
                                     method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def get(self, pfad):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{pfad}", timeout=10) as r:
            return r.read().decode("utf-8")

    def eingabe(self, **aenderung):
        d = {"spot": self.spot["id"], "datum": "2026-09-19", "von": "14:00", "bis": "16:00", "wing": 5.0,
             "leistung": "passt", "wasser": "flach", "note": 4}
        d.update(aenderung)
        return d

    def test_seite_und_reiter(self):
        text = self.get("/tagebuch")
        self.assertIn("Session eintragen", text)
        self.assertIn("href='/tagebuch' class='an'", text)
        self.assertIn("<span>Tagebuch</span>", text)               # Reiter mit Symbol (1.17.0)
        self.assertIn("var TAGEBUCH = {", text)
        self.assertIn("var SPOTS = [", text)
        self.assertIn("/tagebuch", self.get("/"))                   # Reiter auch auf der Startseite

    def test_skriptdaten_brechen_nicht_aus(self):
        seite = self.w.tagebuch_page(load_cfg(), [{"id": "x", "name": "</script><b>", "region": ""}])
        self.assertNotIn("</script><b>", seite)
        self.assertIn("\\u003c/script\\u003e", seite)

    def test_eintragen_loeschen(self):
        code, j = self.post("/tagebuch/neu", self.eingabe())
        self.assertEqual(code, 200, j)
        self.assertTrue(j["gestartet"])
        self.assertEqual(self.gestartet, [[j["id"]]])
        daten = json.loads(self.get("/tagebuch/daten"))
        self.assertEqual([s["id"] for s in daten["sessions"]], [j["id"]])
        self.assertEqual(daten["namen"][self.spot["id"]], self.spot["name"])
        code, _ = self.post("/tagebuch/loeschen", {"id": j["id"]})
        self.assertEqual(code, 200)
        code, _ = self.post("/tagebuch/loeschen", {"id": j["id"]})
        self.assertEqual(code, 404)

    def test_falsche_eingabe_wird_nicht_gespeichert(self):
        code, j = self.post("/tagebuch/neu", self.eingabe(wing=9.9))
        self.assertEqual(code, 400)
        self.assertIn("Quiver", j["error"])
        self.assertFalse(self.buch.exists())

    def test_fremde_herkunft(self):
        code, _ = self.post("/tagebuch/neu", self.eingabe(), origin=False)
        self.assertEqual(code, 403)
        self.assertFalse(self.buch.exists())

    def test_vergleichen_braucht_ids(self):
        self.assertEqual(self.post("/tagebuch/vergleichen", {"ids": []})[0], 400)
        self.assertEqual(self.post("/tagebuch/vergleichen", {"ids": [1]})[0], 400)
        self.assertEqual(self.post("/tagebuch/vergleichen", {"ids": ["abc"]})[0], 200)
        self.assertEqual(self.gestartet, [["abc"]])

    def _zwei_mal_untermotorisiert(self):
        for wind in (14.2, 15.4):
            s = tb.eintragen(tb.pruefe(self.eingabe(leistung="unter"), {self.spot["id"]: self.spot},
                                       load_config(self.cfg)["quiver"]["wings"]))
            tb.vergleich_eintragen({s["id"]: {"station": {"km": 3.0}, "gemessen_kn": wind, "wingscout_kn": wind,
                                              "roh_kn": None}})

    def test_windfenster_uebernehmen(self):
        self._zwei_mal_untermotorisiert()
        vorher = self.cfg.read_text(encoding="utf-8")
        code, j = self.post("/tagebuch/uebernehmen", {"art": "windfenster", "size": 5.0, "low": 17, "high": 22})
        self.assertEqual(code, 409)                                  # nicht der aktuelle Vorschlag
        self.assertEqual(self.cfg.read_text(encoding="utf-8"), vorher)
        code, j = self.post("/tagebuch/uebernehmen", {"art": "windfenster", "size": 5.0, "low": 16, "high": 22})
        self.assertEqual(code, 200, j)
        wing = next(w for w in load_config(self.cfg)["quiver"]["wings"] if w["size"] == 5.0)
        self.assertEqual((wing["low"], wing["high"]), (16, 22))
        self.cfg.write_text(vorher, encoding="utf-8")

    def test_windfaktor_uebernehmen_und_neu_vergleichen(self):
        wings = load_config(self.cfg)["quiver"]["wings"]
        for roh_kn in (10.0, 10.5):
            s = tb.eintragen(tb.pruefe(self.eingabe(), {self.spot["id"]: self.spot}, wings))
            tb.vergleich_eintragen({s["id"]: {"station": {"km": 3.0}, "gemessen_kn": 17.0, "roh_kn": roh_kn}})
        faktor = float(self.spot.get("wind_factor") or 1.0)
        daten = json.loads(self.get("/tagebuch/daten"))
        neu = next(f for f in daten["vorschlaege"]["windfaktor"] if f["id"] == self.spot["id"])["neu"]
        self.assertEqual(neu, 1.3, "Testannahme: der erste Spot hat Windfaktor 1,0")
        self.assertNotEqual(neu, faktor)
        vorher = self.spots.read_text(encoding="utf-8")
        code, j = self.post("/tagebuch/uebernehmen", {"art": "windfaktor", "id": self.spot["id"], "wert": neu})
        self.assertEqual(code, 200, j)
        erster = yaml.safe_load(self.spots.read_text(encoding="utf-8"))[0]
        self.assertEqual(erster["wind_factor"], 1.3)
        self.assertIn("1,3", j["message"])
        self.assertEqual(len(self.gestartet), 1)                     # die Sessions dort neu vergleichen
        self.assertEqual(len(self.gestartet[0]), 2)
        self.spots.write_text(vorher, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
