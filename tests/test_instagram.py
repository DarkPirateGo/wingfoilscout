"""Instagram je Spot: Hashtag, Absprünge, Momentaufnahme."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT
from wingscout import instagram


class Hashtag(unittest.TestCase):
    def test_aus_dem_namen(self):
        self.assertEqual(instagram.tag({"name": "St. Peter-Ording"}), "stpeterording")
        self.assertEqual(instagram.tag({"name": "Île d'Oléron – Séulières"}), "iledoleronseulieres")
        self.assertEqual(instagram.tag({"name": "Comer See – Domaso"}), "comerseedomaso")
        self.assertEqual(instagram.tag({"name": ""}), "")

    def test_aus_dem_katalog(self):
        self.assertEqual(instagram.tag({"name": "X", "instagram": "#Wing_Foil ok"}), "Wing_Foilok")
        # Kein Hashtag, sondern eine Adresse — dann gilt der Name
        self.assertEqual(instagram.tag({"name": "X", "instagram": "https://www.instagram.com/x/"}), "x")
        # Etwas, das keine Adresse ist, wird als Hashtag gelesen — nie als Adresse
        self.assertEqual(instagram.tag({"name": "X", "instagram": "javascript:alert(1)"}), "javascriptalert1")


class Absprünge(unittest.TestCase):
    def test_ohne_momentaufnahme(self):
        links = dict(instagram.links({"id": "x", "name": "Brouwersdam"}, daten={}))
        self.assertEqual(links["Instagram"], "https://www.instagram.com/explore/tags/brouwersdam/")
        self.assertEqual(links["Insta-Suche"],
                         "https://www.google.com/search?q=site%3Ainstagram.com%20%22Brouwersdam%22%20wingfoil")
        self.assertEqual([k for k, _ in instagram.links({"id": "x", "name": ""}, daten={})], ["Insta-Suche"])

    def test_katalog_vor_momentaufnahme_vor_hashtag(self):
        daten = {"stand": "2026-09-18", "spots": {"x": {"ort": "https://www.instagram.com/explore/locations/1/x/",
                                                        "funde": [], "urteil": "keine"}}}
        self.assertEqual(dict(instagram.links({"id": "x", "name": "X"}, daten))["Instagram"],
                         "https://www.instagram.com/explore/locations/1/x/")
        eigene = {"id": "x", "name": "X", "instagram": "https://www.instagram.com/explore/locations/2/y/"}
        self.assertEqual(dict(instagram.links(eigene, daten))["Instagram"],
                         "https://www.instagram.com/explore/locations/2/y/")
        # Nur instagram.com und nur http(s) — sonst zählt die Adresse nicht
        fremd = {"id": "x", "name": "X", "instagram": "https://example.com/x"}
        self.assertEqual(dict(instagram.links(fremd, {}))["Instagram"], "https://www.instagram.com/explore/tags/x/")

    def test_beschriftung(self):
        b = instagram.beschriftung
        self.assertEqual(b("https://www.instagram.com/explore/locations/1/x/"), "Ort")
        self.assertEqual(b("https://www.instagram.com/explore/locations/1/x/", "Lago di Santa Croce"), "Ort: Lago di Santa Croce")
        self.assertEqual(b("https://www.instagram.com/explore/locations/1/x/", "A" * 40), "Ort: " + "A" * 32 + "…")
        self.assertEqual(b("https://www.instagram.com/konto/", "egal"), "@konto")
        self.assertEqual(b("https://www.instagram.com/explore/tags/brouwersdam/"), "#brouwersdam")
        self.assertEqual(b("https://www.instagram.com/p/DYfX2rdluNt/"), "Beitrag")
        self.assertEqual(b("https://www.instagram.com/reel/abc/"), "Reel")
        self.assertEqual(b("https://www.instagram.com/foilschool/reel/abc/"), "@foilschool (Reel)")
        self.assertEqual(b("https://www.instagram.com/foilschool/p/abc/"), "@foilschool (Beitrag)")
        self.assertEqual(b("https://www.instagram.com/foilschool/"), "@foilschool")
        self.assertEqual(b("https://www.instagram.com/"), "Instagram")


class Momentaufnahme(unittest.TestCase):
    def test_laden_und_funde(self):
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "instagram.json"
            pfad.write_text(json.dumps({"stand": "2026-09-18", "spots": {
                "x": {"ort": "https://www.instagram.com/explore/locations/1/x/", "ort_titel": "X", "urteil": "wing",
                      "funde": [{"url": "https://www.instagram.com/a/", "titel": "A"},
                                {"url": "http://evil.example/", "titel": "B"},
                                {"url": "javascript:alert(1)", "titel": "C"}]}}}), encoding="utf-8")
            daten = instagram.lade(pfad)
            f = instagram.funde({"id": "x"}, daten)
            self.assertEqual(f["ort"], "https://www.instagram.com/explore/locations/1/x/")
            self.assertEqual([x["url"] for x in f["funde"]], ["https://www.instagram.com/a/"])
            self.assertEqual(f["urteil"], "wing")
            self.assertEqual(instagram.funde({"id": "y"}, daten), {})
            # Kaputte Datei: leer, kein Absturz
            pfad.write_text("{nicht json", encoding="utf-8")
            import os, time
            os.utime(pfad, (time.time() + 5, time.time() + 5))
            self.assertEqual(instagram.lade(pfad), {})
        self.assertEqual(instagram.lade(Path(d) / "gibt-es-nicht.json"), {})

    def test_eintrag_entfernen(self):
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "instagram.json"
            pfad.write_text(json.dumps({"stand": "2026-09-18", "spots": {"x": {"funde": [], "urteil": "keine"},
                                                                          "y": {"funde": [], "urteil": "keine"}}}),
                            encoding="utf-8")
            self.assertTrue(instagram.entferne("x", pfad))
            self.assertEqual(list(json.loads(pfad.read_text(encoding="utf-8"))["spots"]), ["y"])
            self.assertFalse(instagram.entferne("x", pfad))
            self.assertFalse(instagram.entferne("x", Path(d) / "fehlt.json"))

    def test_die_versionierte_datei_ist_sauber(self):
        """instagram.json im Repo: nur instagram.com-Adressen, bekannte Urteile,
        ein Datum — und jeder Spot darin steht im Katalog."""
        from wingscout.spots import load_spots
        daten = json.loads((ROOT / "instagram.json").read_text(encoding="utf-8"))
        self.assertRegex(daten["stand"], r"^\d{4}-\d{2}-\d{2}$")
        ids = {s["id"] for s in load_spots(ROOT / "spots.yaml")}
        self.assertGreaterEqual(len(daten["spots"]), 50)
        for sid, e in daten["spots"].items():
            with self.subTest(spot=sid):
                self.assertIn(sid, ids)
                self.assertIn(e["urteil"], instagram.URTEIL_TEXT)
                for url in ([e["ort"]] if e.get("ort") else []) + [f["url"] for f in e["funde"]]:
                    self.assertRegex(url, r"^https://www\.instagram\.com/[A-Za-z0-9_./%-]+/?$")
                self.assertLessEqual(len(e["funde"]), 5)


if __name__ == "__main__":
    unittest.main()
