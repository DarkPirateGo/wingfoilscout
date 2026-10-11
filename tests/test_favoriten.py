"""Favoriten (seit 2.4.0, gewünscht am 06.10.2026).

In der ersten Eingabemaske Spots per Eintippen zu einer Liste hinzufügen;
mit „Favoriten zuerst zeigen“ rechnet jede Suche sie mit — auch außerhalb des
Radius und trotz der Filter — und der Report beginnt mit ihnen: Favoriten →
die besten drei → Karte. Die besten drei, Karte und Raster bleiben bei der
normalen Suche. Hier geprüft: die Liste (favoriten.py), die Suche (cli), der
Abschnitt im Report in allen vier Sprachen, die Oberfläche mit ihrem
Speicherweg und — wenn Chromium da ist — das Skript im Browser.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import stat
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import wingscout
from tests.helpers import cfg as load_cfg, CONFIG, SPOTS, ROOT
import tests.test_report_sprachen as tsp
from tests.test_i18n import chromium
from tests.test_sonne import _forecast, SPOT as SONNENSPOT
from wingscout import cli, i18n, report
from wingscout import favoriten as fav
from wingscout import spotedit
from wingscout import webui as w
from wingscout import config as config_mod
from wingscout.config import load_config
from wingscout.score import (score_hours, rank_trips, plan_b, beste_fenster, build_sessions,
                             score_wind, score_wind_ausserhalb)
from wingscout.spots import load_spots, eligible, entfernungsgrund, ist_entfernungsgrund

GEOMETRIE = ROOT / "geometry.json"
# Vom Platzhalter-Zuhause der Vorlage (Hamburg) aus, Radius 600 km: zwei in der
# Suche (Stausee, Meer), zwei weit draußen (Meer in Spanien, Stausee in Navarra)
# und eine ID, die es nicht gibt. Alle vier haben das ganze Jahr Saison — mit
# Brouwersdam (März bis November) scheiterten die Tests im Winter
# (Review 07.10.2026).
DRIN = ["de-edersee-bringhausen", "wingfoil-surfschule-fehmarn"]
DRAUSSEN = ["wingfoil-center-tarifa", "escuela-navarra-de-vela-nafarroako-bela-"]
FAVORITEN = DRIN + DRAUSSEN
RADIUS = "600"


def suchen(tmp: Path, *extra: str, config: Path = CONFIG) -> tuple[argparse.Namespace, str, list]:
    """Eine Demo-Suche wie `cli.main`, aber mit den Argumenten zum Nachsehen.
    `cache/` in `tmp`: eine Suche legt `letzter_lauf.json` für den Rückblick
    ab — nicht in den Ordner des Projekts."""
    args = cli.parse_args(["--demo", "--days", "2", "--radius", RADIUS, "--out", str(tmp / "r.html"), "--quiet",
                           "--config", str(config), "--spots", str(SPOTS), "--geometry", str(GEOMETRIE), *extra])
    args.ab = None
    log: list = []
    with mock.patch.object(wingscout, "CACHE", tmp / "cache"):
        code = cli.run_search(load_config(config), args, log.append)
    assert code == 0, (code, log)
    return args, (tmp / "r.html").read_text(encoding="utf-8"), log


def kaltes_wasser(tmp: Path) -> Path:
    """Die Vorlage mit Wassergrenze 30 °C: im Demo-Lauf ist jeder Meerspot
    gesperrt — so gibt es Favoriten ohne Session („warum nicht“)."""
    text = CONFIG.read_text(encoding="utf-8")
    neu, n = re.subn(r"(?m)^(\s*water_temp_min:\s*)\d+", r"\g<1>30", text)
    assert n == 1, "water_temp_min nicht gefunden"
    pfad = tmp / "kalt.yaml"
    pfad.write_text(neu, encoding="utf-8")
    return pfad


def gewitter(tmp: Path) -> Path:
    """Die Vorlage mit jedem Wettercode als Gewitter: im Demo-Lauf ist jede
    Stunde gesperrt — so gibt es Favoriten, die auch ohne deine Grenzen kein
    Fenster haben (flache Karte mit dem Grund)."""
    text = CONFIG.read_text(encoding="utf-8")
    neu, n = re.subn(r"(?m)^(\s*thunder_codes:\s*)\[[^\]]*\]", r"\g<1>[" + ", ".join(map(str, range(100))) + "]", text)
    assert n == 1, "thunder_codes nicht gefunden"
    pfad = tmp / "gewitter.yaml"
    pfad.write_text(neu, encoding="utf-8")
    return pfad


def ueberschriften(html_text: str) -> list[str]:
    return [re.sub(r"<[^>]+>", "", h) for h in re.findall(r"<h2[^>]*>(.*?)</h2>", html_text)]


# ── 1. Die Liste ────────────────────────────────────────────────────────────

class Liste(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.datei = Path(tmp.name) / "favoriten.json"
        patcher = mock.patch.object(fav, "DATEI", self.datei)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_nur_ids_jede_einmal_hoechstens_zehn(self):
        # Dieselbe Regel wie im Katalog (spots.ID_MUSTER): Groß erlaubt, Pfade nicht
        self.assertEqual(fav.bereinigen(" a, b,,a,B,../x,c-d_1 "), ["a", "b", "B", "c-d_1"])
        self.assertEqual(fav.bereinigen(["a", 3, None, "a", "x y"]), ["a"])
        self.assertEqual(fav.bereinigen({"a": 1}), [])
        self.assertEqual(fav.bereinigen(None), [])
        self.assertEqual(fav.bereinigen([f"s{i}" for i in range(15)]), [f"s{i}" for i in range(10)])
        self.assertEqual(fav.bereinigen(["a", "b", "c"], bekannte={"c", "a"}), ["a", "c"])
        self.assertEqual(fav.bereinigen(["x" * 81]), [], "länger als eine ID im Katalog sein kann")

    def test_ohne_oder_mit_kaputter_datei_leer(self):
        self.assertEqual(fav.laden(), {"ids": [], "zuerst": True})
        for inhalt in ("", "{", "[]", "null", '"a"', "[" * 50000 + "]" * 50000):
            with self.subTest(inhalt=inhalt[:10]):
                self.datei.write_text(inhalt, encoding="utf-8")
                self.assertEqual(fav.laden(), {"ids": [], "zuerst": True})
        self.datei.write_text('{"ids": ["a", "../b", "a"], "zuerst": "ja"}', encoding="utf-8")
        self.assertEqual(fav.laden(), {"ids": ["a"], "zuerst": True})

    def test_speichern_und_wieder_laden(self):
        gespeichert = fav.speichern(["b", "a", "zz", "b"], False, bekannte={"a", "b"})
        self.assertEqual(gespeichert, {"ids": ["b", "a"], "zuerst": False})
        self.assertEqual(fav.laden(), gespeichert)
        roh = self.datei.read_text(encoding="utf-8")
        self.assertTrue(roh.endswith("}\n"))
        self.assertNotIn("\r", roh)
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(self.datei.stat().st_mode), 0o600, "persönlich wie config.yaml")

    def test_was_ein_lauf_rechnet(self):
        fav.speichern(["a", "b"], False)
        for wert, erwartet in ((None, []), ("", []), ("x,y", ["x", "y"]), (["z"], ["z"]),
                               (fav.GEMERKT, ["a", "b"]), (True, ["a", "b"])):
            with self.subTest(wert=wert):
                self.assertEqual(fav.aus_args(argparse.Namespace(favoriten=wert)), erwartet)
        self.assertEqual(fav.aus_args(argparse.Namespace()), [])

    def test_kommandozeile(self):
        self.assertIsNone(cli.parse_args([]).favoriten)
        self.assertEqual(cli.parse_args(["--favoriten"]).favoriten, fav.GEMERKT)
        self.assertEqual(cli.parse_args(["--favoriten", "a,b"]).favoriten, "a,b")


# ── 2. Entfernung: der Grund nennt den gewählten Radius ─────────────────────

class Entfernung(unittest.TestCase):
    def test_gemessen_mit_zuschlag_genannt_ohne(self):
        """Bis 2.3.0 stand „außerhalb des Radius von 338 km“, wenn 250 km
        gewählt waren — der Vorfilter rechnet mit Zuschlag."""
        weit = {"road_km": 400.0, "drive_h": 4.0}
        grund = entfernungsgrund(weit, 250, 10, zuschlag=1.35)
        self.assertEqual(grund, "400 km — außerhalb des Radius von 250 km")
        self.assertTrue(ist_entfernungsgrund(grund))
        self.assertIsNone(entfernungsgrund({"road_km": 300.0, "drive_h": 3.0}, 250, 10, zuschlag=1.35))
        lang = entfernungsgrund({"road_km": 100.0, "drive_h": 5.0}, 250, 3, zuschlag=1.35)
        self.assertEqual(lang, "5.0 h Fahrt über der Obergrenze von 3.0 h")
        self.assertTrue(ist_entfernungsgrund(lang))
        self.assertFalse(ist_entfernungsgrund(i18n.TD("außerhalb der Saison")))
        self.assertFalse(ist_entfernungsgrund("400 km — außerhalb des Radius von 250 km"), "nur ein TD()")
        self.assertFalse(ist_entfernungsgrund(None))

    def test_vorfilter_nennt_den_radius_der_suche(self):
        cfg = load_cfg()
        _, raus = eligible(load_spots(str(SPOTS)), cfg, 7, 250, None, zuschlag=1.35)
        radien = {m for _, g in raus for m in re.findall(r"außerhalb des Radius von (\d+) km", g)}
        self.assertEqual(radien, {"250"})

    def test_vorlage_eines_texts(self):
        self.assertEqual(i18n.vorlage(i18n.TD("außerhalb der Saison")), "außerhalb der Saison")
        self.assertEqual(i18n.vorlage(i18n.TND("{n} Tag", "{n} Tage", n=3)), "{n} Tag")
        self.assertIsNone(i18n.vorlage("außerhalb der Saison"))
        self.assertIsNone(i18n.vorlage(None))
        with i18n.in_sprache("en"):
            englisch = i18n.TD("außerhalb der Saison")
        self.assertEqual(i18n.vorlage(englisch), "außerhalb der Saison", "in jeder Sprache dieselbe Vorlage")


# ── 3. Die Suche ────────────────────────────────────────────────────────────

class Suche(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.tmp = Path(tmp.name)
        cls.args, cls.html, cls.log = suchen(cls.tmp, "--favoriten", ",".join(FAVORITEN + ["gibt-es-nicht"]))
        (cls.tmp / "ohne").mkdir()
        cls.ohne_args, cls.ohne_html, _ = suchen(cls.tmp / "ohne")

    def eintrag(self, sid: str) -> dict:
        return next(e for e in self.args._favoriten if e["spot"]["id"] == sid)

    def test_in_der_reihenfolge_der_liste_unbekanntes_faellt_weg(self):
        self.assertEqual([e["spot"]["id"] for e in self.args._favoriten], FAVORITEN)
        self.assertEqual(self.args._fav_ids, FAVORITEN)
        self.assertIn("Favorit „gibt-es-nicht“ steht nicht im Katalog — übergangen", self.log)
        self.assertIn("Favoriten: 4, davon 2 außerhalb der Suche — werden zusätzlich gerechnet", self.log)

    def test_draussen_gerechnet_mit_grund_drinnen_mit_platz(self):
        for sid in DRAUSSEN:
            with self.subTest(sid=sid):
                e = self.eintrag(sid)
                self.assertIsNone(e["rang"])
                self.assertIsNotNone(e["trip"], "auch außerhalb des Radius gerechnet")
                self.assertTrue(e["rows"])
                self.assertRegex(e["grund"], r"^\d+ km — außerhalb des Radius von 600 km$")
        for sid in DRIN:
            with self.subTest(sid=sid):
                e = self.eintrag(sid)
                self.assertIsNone(e["grund"])
                if e["trip"] is not None:
                    self.assertIsInstance(e["rang"], int)

    def test_suche_selbst_bleibt_wie_ohne_favoriten(self):
        """Die besten drei, Karte und Raster: dieselbe Suche — die Favoriten
        draußen tauchen dort nicht auf."""
        self.assertEqual(self.args._n_trips, self.ohne_args._n_trips)
        self.assertEqual(self.args._n_sessions, self.ohne_args._n_sessions)
        for sid in DRAUSSEN:
            name = self.eintrag(sid)["spot"]["name"]
            with self.subTest(sid=sid):
                raster = self.html.split("<h2>Stundenraster</h2>")[1].split("<h2>")[0]
                self.assertNotIn(name, raster)
                beste = self.html.split("<h2>Die besten drei</h2>")[1].split("<h2>")[0]
                self.assertNotIn(name, beste)
        self.assertEqual(self.ohne_args._favoriten, [])


class SucheBleibtUnberuehrt(unittest.TestCase):
    """Befunde des Reviews vom 07.10.2026: Favoriten ändern an der Suche
    nichts — nicht die Stellplätze ihrer Ziele, nicht die Spots der Tabelle
    „Nicht berücksichtigt“, nicht den Kopfhinweis zu Warnungen."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def test_stellplaetze_nur_fuer_favoriten_draussen(self):
        """Ein Favorit unter den Zielen der Suche, etwa auf Platz 12, bekam
        Stellplätze — auf der Karte und unter „Weitere Ziele“, die ohne ihn
        keine hätten."""
        aufrufe = []

        def merken(trips, cfg, args, log, top=8):
            aufrufe.append([t["spot"]["id"] for t in trips[:top]])
        with mock.patch.object(cli, "add_camping", merken):
            args, _, _ = suchen(self.tmp, "--favoriten", ",".join(FAVORITEN))
        draussen = [e["spot"]["id"] for e in args._favoriten if e["trip"] and e["rang"] is None]
        self.assertTrue(set(draussen) <= set(DRAUSSEN))
        self.assertEqual(aufrufe[1:], [draussen] if draussen else [])

    def test_nicht_beruecksichtigt_bleibt_wie_die_suche_es_sah(self):
        """Die Favoriten draußen werden als Kopie geroutet: in der Tabelle steht
        für sie die Schätzung der Suche, mit dem Grund aus derselben Zahl; die
        Karte des Favoriten nennt die geroutete Strecke."""
        def routen(spots, cfg, args, log):
            for s in spots:
                s.update(road_km=round(s["dist_km"] * 1.3, 1), drive_h=round(s["dist_km"] * 1.3 / 90, 2),
                         drive_source="Routing")
        with mock.patch.object(cli, "fahrzeiten_routen", routen):
            args, html, _ = suchen(self.tmp, "--favoriten", ",".join(FAVORITEN))
        teil = html.split("<h2>Nicht berücksichtigt</h2>")[1]
        for sid in DRAUSSEN:
            with self.subTest(sid=sid):
                e = next(x for x in args._favoriten if x["spot"]["id"] == sid)
                spot = e["spot"]
                self.assertEqual(spot["drive_source"], "Routing")
                self.assertEqual(e["grund"], f"{spot['road_km']:.0f} km — außerhalb des Radius von 600 km")
                zeile = teil.split(f"<td>{report._esc(spot['name'])}</td>")[1].split("</tr>")[0]
                self.assertIn("≈&#8239;", zeile, "in der Tabelle die Schätzung der Suche")
                self.assertNotIn(f"{spot['road_km']:.0f} km", zeile)

    def test_geroutet_in_reichweite(self):
        """Hat nur die Schätzung des Vorfilters einen Favoriten aussortiert,
        sagt der Grund das — statt der Zahl der Schätzung neben der Route."""
        def routen(spots, cfg, args, log):
            for s in spots:
                s.update(road_km=100.0, drive_h=1.2, drive_source="Routing")
        with mock.patch.object(cli, "fahrzeiten_routen", routen):
            args, _, _ = suchen(self.tmp, "--favoriten", "wingfoil-center-tarifa")
        self.assertEqual(args._favoriten[0]["grund"],
                         "nach der Schätzung zu weit, geroutet in Reichweite — vom Vorfilter aussortiert")

    def test_landesweite_warnungen_nur_aus_laendern_der_suche(self):
        landesweit = {"DE": ["a"], "ES": ["b"], "DK": ["c"]}
        cli.nur_laender_der_suche(landesweit, [{"country": "de", "region": ""},
                                               {"country": "DK", "region": "Fyn"}])
        self.assertEqual(landesweit, {"DE": ["a"]})

    def test_nur_favoriten_wenn_die_suche_leer_ist(self):
        args, html, log = suchen(self.tmp, "--radius", "1", "--favoriten", "wingfoil-center-tarifa")
        self.assertIn("Kein Spot in der Suche übrig — gerechnet werden nur die Favoriten.", log)
        self.assertNotIn("Kein Spot übrig — Radius erhöhen oder Filter lockern.", log)
        self.assertEqual(args._n_trips, 0)
        self.assertEqual(ueberschriften(html)[:2], ["Favoriten", "Beste Ziele"])


# ── 4. Der Report ───────────────────────────────────────────────────────────

class Bericht(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.tmp = Path(tmp.name)
        cls.args, cls.html, _ = suchen(cls.tmp, "--favoriten", ",".join(FAVORITEN))
        (cls.tmp / "ohne").mkdir()
        _, cls.ohne, _ = suchen(cls.tmp / "ohne")
        (cls.tmp / "kalt").mkdir()
        cls.kalt_args, cls.kalt, _ = suchen(cls.tmp / "kalt", "--favoriten", ",".join(FAVORITEN),
                                            config=kaltes_wasser(cls.tmp))

    def abschnitt(self, html_text: str) -> str:
        return html_text.split("<h2>Favoriten</h2>")[1].split("<h2>")[0]

    def test_favoriten_dann_die_besten_drei_dann_karte(self):
        folge = ueberschriften(self.html)
        self.assertEqual(folge[:3], ["Favoriten", "Die besten drei", "Karte"])
        self.assertNotIn("Favoriten", ueberschriften(self.ohne))
        self.assertNotIn("id='fav-", self.ohne)
        self.assertNotIn("favstern'", self.ohne)

    def test_eine_karte_je_favorit_mit_stern(self):
        teil = self.abschnitt(self.html)
        self.assertEqual(re.findall(r"id='fav-(\d+)'", teil), ["1", "2", "3", "4"])
        self.assertEqual(teil.count("<span class='rank fav'"), 4)
        self.assertNotIn("<span class='rank'>", teil, "kein Rang der Suche im Abschnitt")
        self.assertIn("Immer gerechnet, auch außerhalb des Radius — in der Reihenfolge deiner Liste.", teil)
        for e in self.args._favoriten:
            with self.subTest(sid=e["spot"]["id"]):
                self.assertIn(report._esc(e["spot"]["name"]), teil)
                if e["rang"]:
                    self.assertIn(f"title='Platz {e['rang']} unter den Zielen der Suche'>Platz {e['rang']}</span>", teil)
                if e["grund"]:
                    self.assertIn(f"title='{report._esc(e['grund'])}'>außerhalb der Suche</span>", teil)
        self.assertEqual(teil.count("— als Favorit trotzdem gerechnet."), len(DRAUSSEN))
        self.assertIn("<b>Favoriten</b> 4", self.html)

    def test_stern_bei_den_zielen_der_suche(self):
        """Ein Favorit unter den Zielen der Suche trägt dort einen Stern."""
        rest = self.html.split("<h2>Die besten drei</h2>")[1]
        sterne = re.findall(r"<details class='trip' id='ziel-(\d+)'><summary><span class='rank'>\d+</span>"
                            r"<span class='name'><span class='favstern'", rest)
        erwartet = sorted(str(e["rang"]) for e in self.args._favoriten if e["rang"])
        self.assertEqual(sorted(sterne), erwartet)

    def test_ohne_session_das_beste_fenster(self):
        """Mit Wassergrenze 30 °C hat kein Meerspot eine Session. Bis 2.4.0
        standen Fehmarn (in der Suche) und Tarifa (draußen) als flache Karte mit
        dem Grund da; seit 2.5.0 (gewünscht am 10.10.2026) bekommen sie ihr
        bestes Fenster, ohne die Grenze gerechnet und mit ihr gekennzeichnet."""
        teil = self.abschnitt(self.kalt)
        self.assertNotIn("class='trip favleer'", teil)
        for sid in ("wingfoil-surfschule-fehmarn", "wingfoil-center-tarifa"):
            with self.subTest(sid=sid):
                e = next(x for x in self.kalt_args._favoriten if x["spot"]["id"] == sid)
                self.assertEqual(e["n_sessions"], 0)
                self.assertIsNone(e["rang"])
                self.assertTrue(e["ohne_grenzen"])
                for s in e["trip"]["sessions"]:
                    self.assertRegex(str(s["ohne_grenzen"][0]), r"^Wasser \d+ °C unter deiner Grenze von 30 °C$")
                    self.assertEqual(s["warn"][0], s["ohne_grenzen"][0], "vorn in den Hinweisen der Session")
                karte = teil.split(f"id='fav-{FAVORITEN.index(sid) + 1}'>")[1].split("</details>")[0]
                self.assertRegex(karte, r"<span class='pill p-warn' title='Wasser \d+ °C unter deiner Grenze von "
                                        r"30 °C'>außerhalb deiner Grenzen</span>")
                self.assertRegex(re.sub(r"<[^>]+>", " ", karte),
                                 r"Mit deinen Grenzen keine Session: Wind reicht zeitweise \(\d+ kn, [^)]+\), aber: "
                                 r"Wasser \d+ °C unter deiner Grenze von 30 °C\. Gezeigt ist das beste Fenster im "
                                 r"Zeitraum, ohne diese Grenzen gerechnet\.")
        # Die Suche selbst bleibt bei deinen Grenzen: Fehmarn ist kein Ziel
        beste = self.kalt.split("<h2>Die besten drei</h2>")[1].split("<h2>Karte</h2>")[0]
        self.assertIn("id='ziel-1'", beste)
        self.assertNotIn("Fehmarn – Burg, Hafen", beste)

    def test_ohne_jedes_fenster_die_flache_karte(self):
        """Sperrt etwas, das keine Grenze von dir ist (hier: Gewitter in jeder
        Stunde), gibt es auch ohne deine Grenzen kein Fenster — dann bleibt die
        flache Karte mit dem Grund."""
        (self.tmp / "gewitter").mkdir()
        args, html_text, _ = suchen(self.tmp / "gewitter", "--favoriten", ",".join(FAVORITEN),
                                    config=gewitter(self.tmp))
        teil = self.abschnitt(html_text)
        leer = re.findall(r"<div class='trip favleer' id='fav-(\d+)'>(.*?)</div><div class='links'>", teil, re.S)
        self.assertEqual([n for n, _ in leer], ["1", "2", "3", "4"])
        self.assertTrue(all(e["trip"] is None for e in args._favoriten))
        texte = " ".join(re.sub(r"<[^>]+>", " ", inhalt) for _, inhalt in leer)
        self.assertRegex(texte, r"Wind reicht zeitweise \(\d+ kn, [^)]+\), aber: Gewitter gemeldet\.")
        self.assertIn("außerhalb der Suche", texte, "Tarifa liegt draußen")
        self.assertIn("windy.com", teil.split("class='trip favleer'")[1])


class WarumNichts(unittest.TestCase):
    """Der eine Satz unter einem Favoriten ohne Session."""

    def setUp(self):
        self.cfg = load_cfg()
        self.lo = config_mod.quiver_range(self.cfg)[0]
        self.args = argparse.Namespace(nights=0)

    def zeilen(self, wind, art=None, veto=None, stunden=(10, 11, 12, 13)):
        from datetime import datetime
        return [{"t": datetime(2026, 10, 8, h), "wind": wind, "veto_art": art, "veto": veto} for h in stunden]

    def satz(self, rows, n_sessions=0, nights=0):
        return report._warum_nichts({"rows": rows, "n_sessions": n_sessions}, self.cfg,
                                    argparse.Namespace(nights=nights))

    def test_die_faelle(self):
        self.assertEqual(self.satz(None), "Keine Vorhersage für diesen Spot.")
        self.assertEqual(self.satz(self.zeilen(30, "nacht", i18n.TD("außerhalb der Tageslichtzeit"))),
                         "Im Zeitraum keine Stunde bei Tageslicht.")
        schwach = self.satz(self.zeilen(self.lo - 3))
        self.assertTrue(schwach.startswith(f"Höchstens {self.lo - 3:.0f} kn (Do 08.10. 10 Uhr) — dein Quiver "
                                           f"fängt bei {self.lo:.0f} kn an."), schwach)
        self.assertEqual(self.satz(self.zeilen(self.lo + 5)),
                         f"Wind reicht zeitweise ({self.lo + 5:.0f} kn, Do 08.10. 10 Uhr), aber nicht lange "
                         "oder gut genug für eine Session.")

    def test_der_haeufigste_grund_in_seinen_eigenen_worten(self):
        rows = (self.zeilen(self.lo + 8, "wetter", i18n.TD("Gewitter gemeldet"), stunden=(12, 13, 14))
                + self.zeilen(self.lo + 9, "tide", i18n.TD("außerhalb des Tidenfensters ({fenster})",
                                                           fenster="HW ± 2 h"), stunden=(16,)))
        satz = self.satz(rows)
        # Wind und Uhrzeit der Stunde, aus der der Grund stammt — nicht die der
        # windigsten (16 Uhr, gesperrt durchs Tidenfenster)
        self.assertEqual(satz, f"Wind reicht zeitweise ({self.lo + 8:.0f} kn, Do 08.10. 12 Uhr), "
                               "aber: Gewitter gemeldet.")
        with i18n.in_sprache("en"):
            englisch = self.satz(rows)
            self.assertIn(i18n.T("Gewitter gemeldet"), englisch)
        self.assertNotIn("Gewitter", englisch)

    def test_leere_karte_escaped_und_hat_absprünge(self):
        spot = {"id": "x", "name": "<b>Böse</b>", "lat": 54.0, "lon": 11.0, "drive_h": 2.5,
                "drive_source": "Schätzung"}
        teil = report._fav_leer(2, {"spot": spot, "rows": None, "n_sessions": 0,
                                    "grund": i18n.TD("außerhalb der Saison")},
                                self.cfg, self.args, {"lat": 53.5, "lon": 10.0})
        self.assertIn("<div class='trip favleer' id='fav-2'>", teil)
        self.assertIn("&lt;b&gt;Böse&lt;/b&gt;", teil)
        self.assertNotIn("<b>Böse", teil)
        self.assertIn("title='außerhalb der Saison'>außerhalb der Suche</span>", teil)
        self.assertIn("Keine Vorhersage für diesen Spot.", teil)
        self.assertIn("2.5 h Fahrt (geschätzt)", teil)
        self.assertIn("<div class='links'><a href=", teil)


class ImmerEinZiel(unittest.TestCase):
    """Gewünscht am 07.10.2026, seit 2.5.0: jeder Favorit wird gerechnet, auch
    wenn die Eingaben der Suche nicht passen. Bis 2.4.0 stand ein Favorit mit Sessions,
    aber ohne die Tage am Stück der Suche, als flache Karte da („Sessions gibt
    es, aber keine 3 Tage am Stück.“) — jetzt bekommt er sein Ziel, mit einer
    Plakette, die das sagt."""

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.tmp = Path(tmp.name)
        # Sechs Tage am Stück in einer Suche über zwei: kein Ziel der Suche —
        # und jeder Favorit trotzdem eins
        cls.args, cls.html, _ = suchen(cls.tmp, "--nights", "5", "--favoriten", ",".join(FAVORITEN))

    def test_jeder_favorit_mit_sessions_hat_ein_ziel(self):
        self.assertEqual(self.args._n_trips, 0)
        self.assertTrue(all(e["n_sessions"] for e in self.args._favoriten), "Voraussetzung des Tests")
        for e in self.args._favoriten:
            with self.subTest(sid=e["spot"]["id"]):
                self.assertIsNotNone(e["trip"])
                self.assertIsNone(e["rang"])
                self.assertEqual(e["am_stueck"], 6)
                self.assertLess(e["trip"]["run_len"], 6)

    def test_plakette_sagt_es(self):
        teil = self.html.split("<h2>Favoriten</h2>")[1].split("<h2>")[0]
        self.assertNotIn("class='trip favleer'", teil)
        self.assertEqual(teil.count("<span class='pill p-warn' title='Die Suche verlangt 6 brauchbare Tage am "
                                    "Stück — dieser Favorit hat sie nicht und steht trotzdem hier.'>keine 6 Tage "
                                    "am Stück</span>"), len(FAVORITEN))
        cfg = load_config(CONFIG)
        with i18n.in_sprache("en"):
            englisch = report._favoriten_block(cfg, self.args, cfg["rider"]["home"])
        self.assertEqual(englisch.count("title='The search asks for 6 usable days in a row — this favourite "
                                        "doesn&#x27;t have them and is shown anyway.'>not 6 days in a row</span>"),
                         len(FAVORITEN))

    def test_ohne_tage_am_stueck_zaehlen_die_naechte_fuer_die_fahrt(self):
        cfg = load_cfg()
        spot = {"id": "a", "name": "A", "lat": 54.0, "lon": 11.0, "drive_h": 3.0}
        sessions = [{"spot": spot, "day": tag, "hours": 3.0, "score": 0.7, "start": f"{tag}T12:00"}
                    for tag in ("2026-10-08", "2026-10-10")]
        self.assertEqual(rank_trips(sessions, cfg, nights=1), [], "die Suche selbst verlangt die Tage")
        mit, = rank_trips(sessions, cfg, nights=1, am_stueck=False)
        ohne, = rank_trips(sessions, cfg, nights=0)
        self.assertEqual(mit["run_len"], 1)
        self.assertEqual(mit["acceptable_drive_h"], round(min(ohne["acceptable_drive_h"] * 1.5,
                                                             cfg["drive"]["max_hours"]), 1))

    def test_plan_b_auch_aus_den_zielen_der_suche(self):
        cfg = load_cfg()
        fav = {"spot": {"id": "f", "name": "F", "lat": 54.0, "lon": 11.0}, "days": ["2026-10-08"],
               "rank": 0.4, "total_hours": 4.0}
        ziel = {"spot": {"id": "z", "name": "Z", "lat": 54.1, "lon": 11.0}, "days": ["2026-10-08"],
                "rank": 0.6, "total_hours": 5.0}
        plan_b([fav], cfg)
        self.assertIsNone(fav["plan_b"])
        plan_b([fav], cfg, kandidaten=[ziel, fav])
        self.assertEqual(fav["plan_b"]["name"], "Z")
        self.assertNotIn("plan_b", ziel, "die Ziele der Suche bleiben, wie sie sind")

    def test_plan_b_erst_nach_dem_ensemble(self):
        """Das Ensemble wählt den Plan B unter den Zielen, die es bekommt, neu
        — für die Favoriten wären das nur sie selbst."""
        def ensemble(trips, cfg, args, log, top=None):
            if top is not None:                    # nur der Aufruf für die Favoriten
                for t in trips:
                    t["plan_b"] = {"name": "vom Ensemble", "km": 1, "hours": 1.0}
        (self.tmp / "ens").mkdir()
        with mock.patch.object(cli, "add_ensemble", ensemble):
            args, _, _ = suchen(self.tmp / "ens", "--favoriten", ",".join(FAVORITEN))
        geprueft = [e for e in args._favoriten if e["trip"] and e["rang"] is None]
        self.assertTrue(geprueft)
        for e in geprueft:
            with self.subTest(sid=e["spot"]["id"]):
                self.assertNotEqual((e["trip"]["plan_b"] or {}).get("name"), "vom Ensemble")


class BestesFenster(unittest.TestCase):
    """score_hours(…, grenzen=False) und score.beste_fenster (seit 2.5.0)."""

    def setUp(self):
        self.cfg = load_cfg()
        self.fc = _forecast("2026-09-16", "_dwd_icon_seamless")      # 18 kn aus West, 07–19 Uhr hell

    def tag(self, rows):
        return [r for r in rows if r.get("veto_art") not in ("nacht", "vorbei", "vor_start")]

    def test_wasser_luft_und_quiver_sperren_nicht_mehr(self):
        self.cfg["weather"]["water_temp_min"] = 30
        self.cfg["weather"]["air_temp_max"] = 15                      # 18 °C in der Vorhersage
        self.cfg["quiver"]["wings"] = [{"size": 2.0, "low": 45, "high": 60}]
        sst = {t: 12.0 for t in self.fc["hourly"]["time"]}
        mit = self.tag(score_hours(SONNENSPOT, self.fc, self.cfg, sst))
        self.assertTrue(mit and all(r["veto_art"] == "wasser" for r in mit))
        ohne = score_hours(SONNENSPOT, self.fc, self.cfg, sst, grenzen=False)
        self.assertTrue(any(r.get("veto_art") == "nacht" for r in ohne), "die Nacht sperrt weiter")
        tag = self.tag(ohne)
        self.assertTrue(tag)
        for r in tag:
            self.assertIsNone(r["veto"])
            self.assertGreater(r["score"], 0)
            self.assertNotIn("wing", r)
            self.assertEqual(sorted(a for a, _ in r["ausser"]), ["luft", "quiver", "wasser"])
        fenster = beste_fenster(SONNENSPOT, ohne, self.cfg)
        self.assertEqual(len(fenster), 1)
        s = fenster[0]
        # Richtung, Wasser und Wetter passen — die Güte reicht trotz des Winds
        self.assertGreaterEqual(s["score"], self.cfg["session"]["min_score"])
        self.assertEqual([str(x) for x in s["ohne_grenzen"]],
                         ["höchstens 18 kn — dein Quiver fängt bei 45 kn an",
                          "Wasser 12 °C unter deiner Grenze von 30 °C",
                          "Luft 18 °C außerhalb deiner Grenzen 7–15 °C"])
        self.assertEqual(s["wings"], [])
        with i18n.in_sprache("en"):
            self.assertEqual(str(i18n.uebersetzt(s["ohne_grenzen"][0])), i18n.T(
                "höchstens {kn} kn — dein Quiver fängt bei {lo} kn an", kn="18", lo="45"))

    def test_gewitter_sperrt_auch_ohne_grenzen(self):
        self.cfg["weather"]["thunder_codes"] = [1]
        ohne = score_hours(SONNENSPOT, self.fc, self.cfg, grenzen=False)
        self.assertTrue(all(r["veto"] for r in ohne))
        self.assertEqual(beste_fenster(SONNENSPOT, ohne, self.cfg), [])

    def zeilen(self, *scores):
        from datetime import datetime
        return [{"t": datetime(2026, 10, 10, 10 + i), "day": "2026-10-10", "score": s, "veto": None,
                 "wind": 15.0, "gust": 18.0, "dir_name": "W", "temp": 15.0, "warn": [], "wing": 5.0}
                for i, s in enumerate(scores)]

    def test_eine_stunde_reicht_und_wird_genannt(self):
        self.cfg["session"].update(min_hours=2, min_score=0.55)
        rows = self.zeilen(0.3, 0.8, 0.3)
        self.assertEqual(build_sessions(SONNENSPOT, rows, self.cfg), [])
        s, = beste_fenster(SONNENSPOT, rows, self.cfg)
        self.assertEqual((s["start"].hour, s["hours"]), (11, 1))
        self.assertEqual([str(x) for x in s["ohne_grenzen"]], ["nur 1 h — deine Mindestdauer ist 2 h"])
        self.assertEqual([str(x) for x in s["warn"]][:1], ["nur 1 h — deine Mindestdauer ist 2 h"])

    def test_die_stunden_nah_an_der_besten(self):
        """Erreicht keine Stunde deine Mindestgüte, ist das Fenster, was bis 15 %
        unter der besten Stunde liegt — nicht der ganze Tag."""
        self.cfg["session"].update(min_hours=2, min_score=0.55)
        rows = self.zeilen(0.2, 0.36, 0.42, 0.40, 0.25)
        s, = beste_fenster(SONNENSPOT, rows, self.cfg)
        self.assertEqual((s["start"].hour, s["hours"]), (11, 3))
        self.assertEqual([str(x) for x in s["ohne_grenzen"]], ["Güte 0.39 — deine Mindestgüte ist 0.55"])

    def test_wind_ausserhalb_je_naeher_desto_besser(self):
        self.cfg["quiver"]["wings"] = [{"size": 5.0, "low": 12, "high": 25}]
        werte = [score_wind_ausserhalb(kn, self.cfg) for kn in (2, 6, 9, 11.9)]
        self.assertEqual(werte, sorted(werte))
        self.assertLessEqual(max(werte), 0.3)
        self.assertGreater(score_wind_ausserhalb(28, self.cfg), score_wind_ausserhalb(35, self.cfg))
        self.assertLessEqual(score_wind_ausserhalb(11.9, self.cfg), score_wind(12, self.cfg)[0])


class NachtVorWasser(unittest.TestCase):
    """Seit 2.4.0 sperrt die Nacht vor dem Wasser: nachts geht es nie, und die
    Favoriten suchen die beste Stunde nur bei Tageslicht."""

    def test_reihenfolge_der_sperren(self):
        cfg = load_cfg()
        cfg["weather"]["water_temp_min"] = 30
        fc = _forecast("2026-09-16", "_dwd_icon_seamless")
        rows = score_hours(SONNENSPOT, fc, cfg, {t: 12.0 for t in fc["hourly"]["time"]})
        arten = {r["t"].hour: r["veto_art"] for r in rows}
        self.assertEqual(arten[3], "nacht")
        self.assertEqual(arten[13], "wasser")
        self.assertEqual({r["veto_art"] for r in rows}, {"nacht", "wasser"})


# ── 5. Alle vier Sprachen aus einer Suche ───────────────────────────────────

class InJederSprache(tsp.Umgebung):
    """Wie tests/test_report_sprachen.py, mit Favoriten: auf Deutsch gerechnet
    und in jeder Sprache geschrieben gleicht der Report dem einer Suche in
    dieser Sprache — Gründe, „warum nicht“, Plaketten eingeschlossen."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.kalt = kaltes_wasser(cls.tmp)
        cls.extra = ("--radius", RADIUS, "--favoriten", ",".join(FAVORITEN))
        with mock.patch.object(tsp, "CONFIG", cls.kalt):
            assert tsp.suche(cls.standard, "de", *cls.extra) == 0
        cls.deutsch = cls.standard.read_text(encoding="utf-8")

    def test_deckt_beide_kartenarten_ab(self):
        """Ziele der Suche und beste Fenster ohne deine Grenzen (seit 2.5.0;
        die flache Karte prüfen `WarumNichts` und `Bericht`)."""
        self.assertIn("<h2>Favoriten</h2>", self.deutsch)
        self.assertIn("<details class='trip' id='fav-", self.deutsch)
        self.assertIn(">außerhalb deiner Grenzen</span>", self.deutsch)
        self.assertIn("Mit deinen Grenzen keine Session:", self.deutsch)
        self.assertIn("außerhalb des Radius von 600 km", self.deutsch)

    def test_jede_fassung_gleicht_der_suche_in_ihrer_sprache(self):
        for sprache in tsp.FREMDE:
            with self.subTest(sprache=sprache):
                fassung = report.fassung(self.standard.read_bytes(), sprache).decode("utf-8")
                eigene = self.tmp / f"eigen-{sprache}.html"
                with mock.patch.object(tsp, "CONFIG", self.kalt):
                    self.assertEqual(tsp.suche(eigene, sprache, *self.extra), 0)
                a, b = tsp.ohne_zeit(fassung), tsp.ohne_zeit(eigene.read_text(encoding="utf-8"))
                self.assertTrue(a == b, "Fassung aus der deutschen Suche ≠ Suche auf " + sprache + ", "
                                + tsp.erste_abweichung(a, b))
                self.assertNotIn("Favoriten", ueberschriften(fassung))
                self.assertNotIn("außerhalb der Suche", fassung)


# ── 6. Die Oberfläche ───────────────────────────────────────────────────────

class OberflaecheOhneServer(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        for patcher in (mock.patch.object(fav, "DATEI", self.tmp / "favoriten.json"),
                        mock.patch.object(w, "DEFAULTS_FILE", self.tmp / "ui_defaults.json")):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.cfg = load_cfg()

    def test_startwerte_aus_favoriten_json_nicht_aus_ui_defaults(self):
        self.assertEqual((w.form_defaults(self.cfg)["favoriten"], w.form_defaults(self.cfg)["fav_zuerst"]),
                         ([], True))
        fav.speichern(["brouwersdam"], False)
        w.DEFAULTS_FILE.write_text(json.dumps({"favoriten": ["silvaplana"], "fav_zuerst": True, "radius": 321}),
                                   encoding="utf-8")
        werte = w.form_defaults(self.cfg)
        self.assertEqual((werte["favoriten"], werte["fav_zuerst"], werte["radius"]), (["brouwersdam"], False, 321))

    def test_formular_und_lauf(self):
        basis = w.form_defaults(self.cfg)
        werte = w.parse_form({"favoriten": ["brouwersdam,../x,silvaplana"], "fav_zuerst": ["on"]}, basis)
        self.assertEqual((werte["favoriten"], werte["fav_zuerst"]), (["brouwersdam", "silvaplana"], True))
        self.assertEqual(w.make_args(werte).favoriten, ["brouwersdam", "silvaplana"])
        ohne_haken = w.parse_form({"favoriten": ["brouwersdam"]}, basis)
        self.assertFalse(ohne_haken["fav_zuerst"])
        self.assertEqual(w.make_args(ohne_haken).favoriten, [], "ohne den Haken keine Favoriten")
        self.assertEqual(w.parse_form({}, basis)["favoriten"], [])

    def test_seite(self):
        leer = w.page(self.cfg, w.form_defaults(self.cfg))
        self.assertIn('id="favsuche"', leer)
        self.assertIn('<div class="favan" id="favan" hidden>', leer)
        self.assertIn('<ul id="favchips" class="favchips" aria-label="Deine Favoriten" hidden>', leer)
        self.assertIn('name="favoriten" id="favoriten" value=""', leer)
        self.assertIn("var FAV_SPOTS = ", leer)
        self.assertIn(w.FAVORITEN_JS.strip()[:60], leer)
        fav.speichern(["gibt-es-nicht", "brouwersdam"], False)
        seite = w.page(self.cfg, w.form_defaults(self.cfg))
        self.assertIn('name="favoriten" id="favoriten" value="brouwersdam"', seite, "nur, was der Katalog kennt")
        self.assertIn('<div class="favan" id="favan">', seite)
        self.assertIn('id="fav_zuerst">', seite, "der Haken gemerkt aus")
        daten = json.loads(re.search(r"var FAVORITEN = (\{.*?\});", seite).group(1))
        self.assertEqual(daten, {"ids": ["brouwersdam"], "zuerst": False, "max": fav.MAX})
        liste = json.loads(re.search(r"var FAV_SPOTS = (\[.*?\]);", seite).group(1))
        self.assertEqual(len(liste), len(load_spots(str(SPOTS))))
        self.assertEqual(set(liste[0]), {"id", "name", "region"})

    def test_katalog_gemerkt_bis_er_sich_aendert(self):
        kopie = self.tmp / "spots.yaml"
        kopie.write_bytes(SPOTS.read_bytes())
        with mock.patch.object(w, "SPOTS_FILE", kopie):
            erste = w.fav_katalog()
            self.assertIs(w.fav_katalog(), erste)
            kopie.write_text("- nicht: [ein, katalog\n", encoding="utf-8")
            self.assertEqual(w.fav_katalog(), [], "kaputter Katalog: keine Trefferliste, keine kaputte Seite")
            with self.assertRaises(Exception):
                w.fav_katalog(streng=True)


class OberflaecheMitServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.tmp = Path(tmp.name)
        for patcher in (mock.patch.object(fav, "DATEI", cls.tmp / "favoriten.json"),
                        mock.patch.object(w, "DEFAULTS_FILE", cls.tmp / "ui_defaults.json"),
                        mock.patch.object(w.Handler, "cfg_path", str(CONFIG))):
            patcher.start()
            cls.addClassCleanup(patcher.stop)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), w.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server.shutdown)

    def setUp(self):
        fav.DATEI.unlink(missing_ok=True)

    def post(self, pfad, body, origin=None, art="application/json"):
        kopf = {"Content-Type": art, "Origin": origin or f"http://127.0.0.1:{self.port}"}
        daten = body if isinstance(body, bytes) else json.dumps(body).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{pfad}", data=daten, method="POST", headers=kopf)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_merken(self):
        ids = ["brouwersdam", "gibt-es-nicht", "silvaplana"] + [s["id"] for s in w.fav_katalog()[:12]]
        code, antwort = self.post("/favoriten", {"ids": ids, "zuerst": False})
        self.assertEqual(code, 200, antwort)
        self.assertEqual(antwort["ids"][:2], ["brouwersdam", "silvaplana"])
        self.assertEqual(len(antwort["ids"]), fav.MAX)
        self.assertFalse(antwort["zuerst"])
        self.assertEqual(fav.laden(), {"ids": antwort["ids"], "zuerst": False})

    def test_unsinn_wird_abgewiesen(self):
        for body in (b"kein json", {"ids": "brouwersdam"}, {"ids": [1, 2]}, {"ids": [], "zuerst": "ja"}):
            with self.subTest(body=body):
                code, antwort = self.post("/favoriten", body)
                self.assertEqual(code, 400)
                self.assertIn("error", antwort)
        self.assertFalse(fav.DATEI.exists())

    def test_fremde_herkunft(self):
        code, _ = self.post("/favoriten", {"ids": ["brouwersdam"], "zuerst": True}, origin="https://boese.example")
        self.assertEqual(code, 403)
        self.assertFalse(fav.DATEI.exists())

    def test_als_standard_merken_laesst_die_favoriten_aus(self):
        roh = urllib.parse.urlencode({"favoriten": "brouwersdam", "fav_zuerst": "on", "radius": "333",
                                      "start": "51.7, 3.8"}).encode()
        code, _ = self.post("/save", roh, art="application/x-www-form-urlencoded")
        self.assertEqual(code, 200)
        gemerkt = json.loads(w.DEFAULTS_FILE.read_text(encoding="utf-8"))
        self.assertEqual(gemerkt["radius"], 333.0)
        for schluessel in ("favoriten", "fav_zuerst", "start", "start_name", "ab"):
            self.assertNotIn(schluessel, gemerkt)
        self.assertFalse(fav.DATEI.exists())


class ImBrowser(unittest.TestCase):
    """web/favoriten.js in Chromium: eintippen, wählen, merken, herausnehmen —
    und Enter im Feld startet nie die Suche."""

    @classmethod
    def setUpClass(cls):
        OberflaecheMitServer.setUpClass.__func__(cls)

    def test_eintippen_waehlen_merken(self):
        fav.DATEI.unlink(missing_ok=True)
        basis = f"http://127.0.0.1:{self.port}"
        with chromium(self) as (seite, fehler):
            anfragen: list = []
            seite.on("request", lambda r: anfragen.append(r.url))
            seite.goto(basis + "/")
            self.assertTrue(seite.locator("#favan").is_hidden())
            seite.fill("#favsuche", "EDERSEE bringh")
            self.assertTrue(seite.locator("#favliste").is_visible())
            self.assertIn("Edersee", seite.locator("#favliste button").first.inner_text())
            with seite.expect_response(lambda r: r.url.endswith("/favoriten")):
                seite.press("#favsuche", "Enter")
            self.assertEqual(seite.input_value("#favoriten"), "de-edersee-bringhausen")
            self.assertEqual(seite.locator("#favchips li").count(), 1)
            self.assertTrue(seite.locator("#favan").is_visible())
            self.assertEqual(fav.laden(), {"ids": ["de-edersee-bringhausen"], "zuerst": True})
            # Ohne Akzent findet es den Spot mit Akzent; schon Gewähltes nicht noch einmal
            seite.fill("#favsuche", "etang leucate")
            self.assertIn("Étang", seite.locator("#favliste button").first.inner_text())
            with seite.expect_response(lambda r: r.url.endswith("/favoriten")):
                seite.locator("#favliste button").first.click()
            seite.fill("#favsuche", "edersee bringh")
            self.assertTrue(seite.locator("#favliste").is_hidden())
            self.assertEqual(seite.inner_text("#favmsg"), "Schon unter deinen Favoriten.")
            seite.fill("#favsuche", "gibt es nicht")
            self.assertEqual(seite.inner_text("#favmsg"), "Kein Spot im Katalog passt dazu.")
            seite.press("#favsuche", "Enter")                     # kein Treffer: nichts, keine Suche
            self.assertFalse([u for u in anfragen if u.endswith("/run")])
            # Haken aus, dann den ersten herausnehmen
            with seite.expect_response(lambda r: r.url.endswith("/favoriten")):
                seite.uncheck("#fav_zuerst")
            self.assertFalse(fav.laden()["zuerst"])
            with seite.expect_response(lambda r: r.url.endswith("/favoriten")):
                seite.locator("#favchips button.favweg").first.click()
            self.assertEqual(fav.laden()["ids"], [i for i in seite.input_value("#favoriten").split(",") if i])
            self.assertEqual(seite.locator("#favchips li").count(), 1)
            # Nach dem Neuladen steht die Liste wieder da
            seite.reload()
            self.assertEqual(seite.locator("#favchips li").count(), 1)
            self.assertFalse(seite.is_checked("#fav_zuerst"))
            self.assertEqual(fehler, [])

    def test_schnelle_aenderungen_kommen_in_der_richtigen_reihenfolge_an(self):
        """Zwei schnelle Klicks auf × — die erste Antwort verzögert: gemerkt ist
        am Ende, was die Seite zeigt (Review 07.10.2026: bis dahin kam die ältere
        Anfrage zuletzt an und stellte den Favoriten wieder her)."""
        fav.speichern(["de-edersee-bringhausen", "wingfoil-surfschule-fehmarn"], True)
        echt = w.Handler._favoriten
        erste = threading.Event()

        def langsam(handler):
            if not erste.is_set():
                erste.set()
                time.sleep(0.8)
            return echt(handler)
        with mock.patch.object(w.Handler, "_favoriten", langsam), chromium(self) as (seite, fehler):
            seite.goto(f"http://127.0.0.1:{self.port}/")
            seite.locator("#favchips button.favweg").first.click()
            seite.locator("#favchips button.favweg").first.click()
            seite.wait_for_timeout(2500)
            self.assertEqual(seite.input_value("#favoriten"), "")
            self.assertEqual(fav.laden()["ids"], [])
            self.assertEqual(fehler, [])

    def test_pfeil_hoch_waehlt_den_letzten_treffer(self):
        with chromium(self) as (seite, fehler):
            seite.goto(f"http://127.0.0.1:{self.port}/")
            seite.fill("#favsuche", "fehmarn")
            n = seite.locator("#favliste button").count()
            self.assertGreater(n, 2)
            seite.press("#favsuche", "ArrowUp")
            self.assertEqual(seite.get_attribute("#favsuche", "aria-activedescendant"), f"favopt-{n - 1}")
            self.assertEqual(fehler, [])


# ── 7. Windows: Zeilenenden beim Schreiben ──────────────────────────────────

class ZeilenendenUnterWindows(unittest.TestCase):
    """Unter Windows öffnet `os.open` ohne O_BINARY im Textmodus; zusammen mit
    Pythons eigener Übersetzung wurde jedes Zeilenende doppelt (config.yaml
    beim ersten Start, alles über spotedit.schreibe_atomar). Seit 2.4.0 binär
    und mit `newline="\\n"`. Hier ohne Windows nachgestellt: der Schalter ist
    ein erfundenes Bit, das der Prüfling mitgeben muss."""

    BIT = 1 << 29

    def pruefen(self, schreiben):
        echt_open, echt_fdopen = os.open, os.fdopen
        gesehen: dict = {}

        def open_(pfad, flags, *rest, **kw):
            if flags & os.O_CREAT:
                gesehen["binaer"] = bool(flags & self.BIT)
            return echt_open(pfad, flags & ~self.BIT, *rest, **kw)

        def fdopen_(fd, *a, **kw):
            if a and "w" in a[0]:
                gesehen["newline"] = kw.get("newline")
            return echt_fdopen(fd, *a, **kw)

        with mock.patch.object(config_mod, "BINAER", self.BIT), mock.patch.object(spotedit, "BINAER", self.BIT), \
                mock.patch("os.open", open_), mock.patch("os.fdopen", fdopen_):
            schreiben()
        self.assertEqual(gesehen, {"binaer": True, "newline": "\n"})

    def test_atomar_schreiben(self):
        with tempfile.TemporaryDirectory() as d:
            ziel = Path(d) / "x.json"
            self.pruefen(lambda: spotedit.schreibe_atomar(ziel, "eins\nzwei\n"))
            self.assertEqual(ziel.read_bytes(), b"eins\nzwei\n")

    def test_config_beim_ersten_start(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "config.example.yaml").write_text("a: 1\nb: 2\n", encoding="utf-8")
            ziel = Path(d) / "config.yaml"
            with contextlib.redirect_stderr(io.StringIO()):
                self.pruefen(lambda: config_mod.ensure_config(ziel))
            self.assertEqual(ziel.read_bytes(), b"a: 1\nb: 2\n")

    def test_auf_diesem_rechner_der_echte_schalter(self):
        self.assertEqual(config_mod.BINAER, getattr(os, "O_BINARY", 0))
        self.assertIs(spotedit.BINAER, config_mod.BINAER)


if __name__ == "__main__":
    unittest.main()
