"""Der Katalog ist das eigentliche Asset — hier wird er auf Form geprüft.

Ein Tippfehler in spots.yaml fällt sonst erst Wochen später auf, wenn ein
Spot stumm aus dem Ranking verschwindet oder `dogs: no` zu `False` wird.
"""
from __future__ import annotations
import unittest
from datetime import date
from pathlib import Path

import yaml

from tests.helpers import cfg as load_cfg, SPOTS, CONFIG
from wingscout.spots import load_spots, eligible
from wingscout.config import quiver_range

WATER = {"sea", "lagoon", "lake", "reservoir", "unknown"}
SHALLOW = {"none", "inshore", "widespread"}
GRASS = {"none", "some", "heavy"}
DOGS = {"yes", "no", "leash"}
ACCESS = {"frei", "gebuehr", "schein", "verein", "zone", "verboten", "unklar"}
QUALITY = {"best", "good", "ok", "bad"}
SHOREBREAK = {"yes", "possible", "no", "unknown"}


class Katalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spots = load_spots(SPOTS)
        doc = yaml.safe_load(SPOTS.read_text(encoding="utf-8"))
        cls.raw = doc["spots"] if isinstance(doc, dict) else doc

    def test_mindestgroesse(self):
        self.assertGreaterEqual(len(self.spots), 100)

    def test_ids_eindeutig_und_dateitauglich(self):
        ids = [s["id"] for s in self.spots]
        self.assertEqual(len(ids), len(set(ids)))
        for sid in ids:
            self.assertRegex(sid, r"^[a-z0-9][a-z0-9_-]{0,79}$", sid)

    def test_pflichtfelder_und_wertebereiche(self):
        for s in self.spots:
            with self.subTest(spot=s["id"]):
                self.assertTrue(s["name"].strip())
                self.assertTrue(-90 <= s["lat"] <= 90 and -180 <= s["lon"] <= 180)
                self.assertIn(s["water_body"], WATER)
                self.assertIn(s["shallow"], SHALLOW)
                self.assertIn(s["seagrass"], GRASS)
                self.assertTrue(set(s["season"]) <= set(range(1, 13)))
                self.assertIsInstance(s.get("verified", False), bool)
                for sec in s.get("sectors", []):
                    self.assertTrue(0 <= sec["from"] <= 360 and 0 <= sec["to"] <= 360)
                    self.assertIn(sec.get("quality", "ok"), QUALITY)

    def test_regelfelder_sind_strings_nicht_wahrheitswerte(self):
        # YAML 1.1 liest ein nacktes `no` als False — genau das darf nicht passieren.
        for entry in self.raw:
            with self.subTest(spot=entry["id"]):
                if "dogs" in entry:
                    self.assertIn(entry["dogs"], DOGS, f"dogs={entry['dogs']!r} — in Anführungszeichen setzen")
                if "access" in entry:
                    self.assertIn(entry["access"], ACCESS)

    def test_shorebreak_ist_ein_block_mit_bekanntem_status(self):
        """`shorebreak:` ist reine Information — aber mit festem Wortschatz,
        damit „ja" nicht einmal als `yes`, einmal als `ja` und einmal als
        `true` dasteht. Im Rohtext muss der Status ein Wort in
        Anführungszeichen sein: YAML 1.1 liest ein nacktes `yes` als True."""
        for entry in self.raw:
            with self.subTest(spot=entry["id"]):
                if "shorebreak" not in entry:
                    continue
                sb = entry["shorebreak"]
                self.assertIsInstance(sb, dict, "shorebreak als Block mit status/note/source schreiben")
                self.assertIn(sb.get("status"), SHOREBREAK,
                              f"status={sb.get('status')!r} — eines von {sorted(SHOREBREAK)}, in Anführungszeichen")
                for feld in ("note", "source"):
                    self.assertIsInstance(sb.get(feld, ""), str, f"{feld} muss Text sein")
        # Nach dem Laden ist der Block normiert, und es gibt ihn wirklich
        mit = [s for s in self.spots if s.get("shorebreak")]
        self.assertGreaterEqual(len(mit), 10)
        for s in mit:
            self.assertEqual(set(s["shorebreak"]), {"status", "note", "source"}, s["id"])
            # Ein See hat keinen Shorebreak — das Feld gehört ans Meer
            self.assertIn(s.get("water_body"), {"sea", "lagoon", "unknown"}, s["id"])

    def test_laenderkuerzel(self):
        for s in self.spots:
            self.assertRegex(s.get("country") or "XX", r"^[A-Z]{2}$", s["id"])

    def test_keine_zwei_geprueften_spots_auf_derselben_stelle(self):
        # Nur für geprüfte Koordinaten: Näherungen aus fremden Listen dürfen
        # zusammenfallen, das ist ja gerade ihr Kennzeichen.
        from wingscout.geo import haversine_km
        seen = []
        for s in [x for x in self.spots if x.get("verified")]:
            for o in seen:
                self.assertGreater(haversine_km(s["lat"], s["lon"], o["lat"], o["lon"]), 0.05,
                                   f"{s['id']} und {o['id']} liegen aufeinander")
            seen.append(s)


class ShorebreakFeld(unittest.TestCase):
    def test_normierung(self):
        from wingscout.spots import shorebreak_normieren
        self.assertIsNone(shorebreak_normieren(None))
        self.assertIsNone(shorebreak_normieren(""))
        self.assertEqual(shorebreak_normieren("possible"),
                         {"status": "possible", "note": "", "source": ""})
        self.assertEqual(shorebreak_normieren({"status": "YES", "note": " steil "}),
                         {"status": "yes", "note": "steil", "source": ""})
        # YAML 1.1: nacktes yes/no wird zum Wahrheitswert — nicht stumm verlieren
        self.assertEqual(shorebreak_normieren(True)["status"], "yes")
        self.assertEqual(shorebreak_normieren({"status": False})["status"], "no")
        self.assertEqual(shorebreak_normieren({"note": "x"})["status"], "unknown")

    def test_load_spots_normiert_und_laesst_leeres_weg(self):
        import tempfile
        text = ("- id: a\n  name: A\n  lat: 1\n  lon: 2\n  shorebreak: yes\n"
                "- id: b\n  name: B\n  lat: 1\n  lon: 2\n  shorebreak:\n"
                "- id: c\n  name: C\n  lat: 1\n  lon: 2\n  shorebreak:\n    status: \"possible\"\n    note: n\n")
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "s.yaml"
            pfad.write_text(text, encoding="utf-8")
            a, b, c = load_spots(pfad)
        self.assertEqual(a["shorebreak"]["status"], "yes")
        self.assertNotIn("shorebreak", b)
        self.assertEqual(c["shorebreak"], {"status": "possible", "note": "n", "source": ""})


class Vorfilter(unittest.TestCase):
    def setUp(self):
        self.cfg = load_cfg()
        self.spots = load_spots(SPOTS)

    def test_radius_und_fahrzeit(self):
        keep, dropped = eligible(self.spots, self.cfg, date.today().month, 200, None)
        self.assertTrue(keep)
        for s in keep:
            self.assertLessEqual(s["road_km"], 200)
        self.assertEqual(len(keep) + len(dropped), len(self.spots))
        self.assertEqual([s["drive_h"] for s in keep], sorted(s["drive_h"] for s in keep))

    def test_stehbereich_und_seegras(self):
        _, dropped = eligible(self.spots, self.cfg, 7, 5000, 99)
        gruende = {r for _, r in dropped}
        self.assertTrue(any("Stehbereich" in g for g in gruende))

    def test_regeln_filtern_nur_auf_wunsch(self):
        ohne, _ = eligible(self.spots, self.cfg, 7, 5000, 99)
        self.cfg["rules"] = {"require_dogs": True, "exclude_forbidden": True}
        mit, dropped = eligible(self.spots, self.cfg, 7, 5000, 99)
        self.assertLess(len(mit), len(ohne))
        self.assertTrue(any("Hunde" in r for _, r in dropped))


class Konfiguration(unittest.TestCase):
    def test_laedt_und_ist_plausibel(self):
        c = load_cfg()
        lo, hi = quiver_range(c)
        self.assertLess(lo, hi)
        self.assertLess(c["weather"]["air_temp_min"], c["weather"]["air_temp_max"])
        self.assertLess(c["wind"]["preferred_low"], c["wind"]["preferred_high"])
        self.assertGreater(c["drive"]["max_hours"], 0)
        self.assertIn("rules", c)
        for w in c["quiver"]["wings"]:
            self.assertLess(w["low"], w["high"])

    def test_saison_ueber_den_zeitraum(self):
        """Ein Lauf am 30.09. über sechzehn Tage berührt den Oktober."""
        cfg = load_cfg()
        from wingscout.spots import Spot
        spot = Spot({"id": "okt", "name": "Oktoberspot", "lat": 49.5, "lon": 8.7, "season": [10],
                     "sectors": [], "seagrass": "none", "shallow": "none"})
        self.assertEqual(len(eligible([spot], cfg, 9, 5000, 100)[0]), 0)
        self.assertEqual(len(eligible([spot], cfg, {9, 10}, 5000, 100)[0]), 1)

    def test_zeitzone_je_land(self):
        from wingscout.spots import zeitzone, nach_zeitzone
        self.assertEqual(zeitzone({"country": "GR", "lon": 23.7}), "Europe/Athens")
        self.assertEqual(zeitzone({"country": "PT", "lon": -8.6}), "Europe/Lisbon")
        self.assertEqual(zeitzone({"country": "PT", "lon": -25.7}), "Atlantic/Azores")
        self.assertEqual(zeitzone({"country": "ES", "lon": -3.7}), "Europe/Berlin")
        self.assertEqual(zeitzone({"country": "ES", "lon": -14.2}), "Atlantic/Canary")
        self.assertEqual(zeitzone({"country": "DE", "lon": 8.7}), "Europe/Berlin")
        self.assertEqual(zeitzone({"country": "", "lon": 8.7}), "Europe/Berlin")
        gruppen = nach_zeitzone([{"country": "DE", "lon": 8}, {"country": "GR", "lon": 23},
                                 {"country": "NL", "lon": 4}])
        self.assertEqual([tz for tz, _ in gruppen], ["Europe/Berlin", "Europe/Athens"])
        self.assertEqual(len(gruppen[0][1]), 2)
        self.assertEqual(nach_zeitzone([{"country": "GR", "lon": 23}], "Europe/Berlin")[0][0],
                         "Europe/Berlin")

    def test_kaputter_katalog_ist_ein_wertfehler_kein_programmende(self):
        """`load_spots` entscheidet nicht, ob das Programm endet — das tut
        die Kommandozeile. Ein `SystemExit` aus einer Bibliotheksfunktion
        ging in der Oberfläche an jedem `except Exception` vorbei."""
        import tempfile
        from wingscout.spots import KatalogFehler
        from wingscout.config import KonfigFehler, load_config
        with tempfile.TemporaryDirectory() as d:
            for inhalt in ("- id: a\n  name: A\n  lat: 1\n  lon: 1\n- id: a\n  name: B\n  lat: 2\n  lon: 2\n",
                           "- id: 'a b'\n  name: A\n  lat: 1\n  lon: 1\n",
                           "- name: ohne id\n  lat: 1\n  lon: 1\n",
                           "- nur eine Zeichenkette\n",
                           "kein: katalog\n"):
                pfad = Path(d) / "spots.yaml"
                pfad.write_text(inhalt, encoding="utf-8")
                with self.assertRaises(KatalogFehler, msg=inhalt):
                    load_spots(pfad)
            with self.assertRaises(KatalogFehler):
                load_spots(Path(d) / "gibt-es-nicht.yaml")
            leer = Path(d) / "config.yaml"
            leer.write_text("quiver: {}\n", encoding="utf-8")
            with self.assertRaises(KonfigFehler):
                load_config(leer)
        self.assertTrue(issubclass(KatalogFehler, ValueError))
        self.assertFalse(issubclass(KatalogFehler, SystemExit))

    def test_kommandozeile_meldet_und_endet(self):
        """An der Kommandozeile bleibt es bei Meldung und Exit-Code 1."""
        import tempfile
        from wingscout.cli import main
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "spots.yaml"
            pfad.write_text("- id: a\n  name: A\n  lat: 1\n  lon: 1\n- id: a\n  name: B\n  lat: 2\n  lon: 2\n",
                            encoding="utf-8")
            with self.assertRaises(SystemExit) as cm:
                main(["--spots", str(pfad), "--config", str(CONFIG), "--demo", "--quiet",
                      "--out", str(Path(d) / "r.html")])
        self.assertIn("Doppelte Spot-ID", str(cm.exception))

    def test_bewertung_md_stimmt_mit_der_konfiguration(self):
        """`SCORING.md` (früher `BEWERTUNG.md`, jetzt englisch) erklärt den
        Entscheidungsweg mit den Standardwerten — die müssen die aus
        `config.example.yaml` sein, sonst erklärt die Seite ein anderes
        Programm (1.20.2)."""
        import yaml as _yaml
        from tests.helpers import ROOT
        text = (ROOT / "SCORING.md").read_text(encoding="utf-8")
        cfg = _yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        for teil, name in (("wind", "Wind speed"), ("direction", "Wind direction"), ("water", "Water state"),
                           ("weather", "Weather"), ("gust", "Gustiness")):
            self.assertIn(f"| {name} | {round(cfg['weights'][teil] * 100)}% |", text, teil)
        w, we, d, se, en = cfg["wind"], cfg["weather"], cfg["drive"], cfg["session"], cfg["ensemble"]

        def punkt(zahl, stellen):                   # 1.25 → „1.25“, wie die englische Seite es schreibt
            return f"{zahl:.{stellen}f}"
        erwartet = {
            "Wohlfühlband": f"({w['preferred_low']}–{w['preferred_high']} kn: 1.0",
            "Böigkeit": f"`wind.gust_ok` ({punkt(w['gust_ok'], 2)})",
            "Böigkeit hart": f"`wind.gust_bad` ({punkt(w['gust_bad'], 2)})",
            "Einigkeit": f"with the default {punkt(w['agreement_weight'], 1)}",
            "Lufttemperatur": f"({we['air_temp_min']}–{we['air_temp_max']} °C)",
            "Wassertemperatur": f"`weather.water_temp_min` ({we['water_temp_min']} °C)",
            "Regen": f"`rain_soft_mm` ({punkt(we['rain_soft_mm'], 1)} mm/h)",
            "Regen hart": f"`rain_hard_mm` ({punkt(we['rain_hard_mm'], 1)} mm/h)",
            "CAPE": f"`cape_warn` ({we['cape_warn']} J/kg)",
            "CAPE hart": f"`cape_bad` ({we['cape_bad']})",
            "Gewitterschatten": f"`weather.thunder_shadow_h` ({we['thunder_shadow_h']})",
            "Fahrtregel": f"`drive.hours_per_water_hour` ({d['hours_per_water_hour']:g})",
            "Fahrt max": f"`drive.max_hours` ({d['max_hours']:g} h)",
            "Plan B": f"`drive.plan_b_km` ({d['plan_b_km']} km",
            "Session-Schwelle": f"`session.min_score` ({punkt(se['min_score'], 2)})",
            "Session-Dauer": f"`session.min_hours` ({se['min_hours']:g} h)",
            "Stundendeckel": f"`session.useful_hours_cap` ({se['useful_hours_cap']:g} h)",
            "Ensemble": f"With the default {punkt(en['weight'], 1)}",
            "Ensemble Ziele": f"`ensemble.top` ({en['top']})",
        }
        for was, satz in erwartet.items():
            self.assertIn(satz, text, f"{was}: „{satz}“ fehlt in SCORING.md")

    def test_bewertung_html_stimmt_mit_der_konfiguration(self):
        """`docs/bewertung.html` zeigt denselben Weg mit Abbildungen — die Zahlen in
        Balken, Kurven und Tabellen müssen die aus `config.example.yaml` sein
        (die Seite ist englisch, also mit Dezimalpunkt).
        Und die Datei bleibt, was sie verspricht: kein Skript, kein Abruf nach
        draußen, auch nicht für Schriften (1.20.3)."""
        import re as _re
        import yaml as _yaml
        from tests.helpers import ROOT
        roh = (ROOT / "docs" / "bewertung.html").read_text(encoding="utf-8")
        text = " ".join(roh.split())                  # Zeilenumbrüche im Fließtext zählen nicht
        cfg = _yaml.safe_load(CONFIG.read_text(encoding="utf-8"))

        def punkt(zahl, stellen):
            return f"{zahl:.{stellen}f}"
        for teil in ("wind", "direction", "water", "weather", "gust"):
            self.assertIn(f">{punkt(cfg['weights'][teil], 2)}</text>", text, teil)
        w, we, se, en, d = cfg["wind"], cfg["weather"], cfg["session"], cfg["ensemble"], cfg["drive"]
        lo = min(x["low"] for x in cfg["quiver"]["wings"])
        hi = max(x["high"] for x in cfg["quiver"]["wings"])
        for satz in (f"comfort band {w['preferred_low']}–{w['preferred_high']} kn",
                     f"{lo} … {hi} kn",
                     f">{punkt(w['gust_ok'], 2)}</text>", f">{punkt(w['gust_bad'], 2)}</text>",
                     f"({punkt(1 - w['agreement_weight'], 1)} + {punkt(w['agreement_weight'], 1)} · agreement)",
                     f"&lt; {we['water_temp_min']} °C",
                     f"{we['air_temp_min']} … {we['air_temp_max']} °C",
                     f"from {punkt(we['rain_soft_mm'], 1)} mm/h · from {punkt(we['rain_hard_mm'], 1)} mm/h",
                     f"from {we['cape_warn']} · from {we['cape_bad']} J/kg",
                     f"± {we['thunder_shadow_h']} h around a thunderstorm hour",
                     f"≥ {punkt(se['min_score'], 2)} · ≥ {se['min_hours']:g} h",
                     f"capped at {se['useful_hours_cap']:g} h",
                     f"weight = {punkt(en['weight'], 1)}",
                     f"for the top {en['top']} destinations",
                     f"{d['hours_per_water_hour']:g} h of driving per 1 h on the water",
                     f"hard cap at {d['max_hours']:g} h",
                     f"within {d['plan_b_km']} km"):
            self.assertIn(satz, text, f"„{satz}“ fehlt in docs/bewertung.html")
        self.assertNotIn("<script", text.lower())
        self.assertEqual(_re.findall(r'(?:src|href)="(https?://[^"]+)"', text), [])
        self.assertNotIn("@import", text)

    def test_nur_safe_load(self):
        # config.py und spots.py dürfen YAML nie mit dem vollen Loader lesen
        for name in ("wingscout/config.py", "wingscout/spots.py", "wingscout/ingest.py"):
            text = (CONFIG.parent / name).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"yaml\.load\(")


if __name__ == "__main__":
    unittest.main()


class PersoenlicheKonfiguration(unittest.TestCase):
    """Die persönliche config.yaml darf nie im Repository landen.

    Sie enthält Namen, Gewicht und Heimatkoordinate, und sie ist bei jedem
    anders — genau die Datei, die beim gemeinsamen Arbeiten sonst bei jedem
    Aktualisieren kollidiert.
    """

    def test_nur_die_vorlage_ist_versioniert(self):
        import subprocess
        from tests.helpers import ROOT
        versioniert = subprocess.run(["git", "ls-files"], cwd=ROOT,
                                     capture_output=True, text=True).stdout.split()
        if not versioniert:
            self.skipTest("kein Git-Repository")
        self.assertIn("config.example.yaml", versioniert)
        for persoenlich in ("config.yaml", "ui_defaults.json", "report.html"):
            self.assertNotIn(persoenlich, versioniert, f"{persoenlich} ist versioniert")

    def test_vorlage_enthaelt_keine_persoenlichen_angaben(self):
        """Geprüft wird, was in der Vorlage stehen soll: Platzhalter. Eine Liste
        der Werte, die dort nicht stehen dürfen, stünde selbst im Repository —
        bis 2.1.0 tat sie das (Review 04.10.2026, D3)."""
        from tests.helpers import ROOT
        text = (ROOT / "config.example.yaml").read_text(encoding="utf-8")
        fahrer = yaml.safe_load(text)["rider"]
        self.assertEqual(fahrer["name"], "Fahrer")
        self.assertEqual(fahrer["weight_kg"], 80)
        # Der Startpunkt der Vorlage ist der Demo-Punkt der Website: Hamburg,
        # Stadtmitte auf zwei Stellen (~1 km) — kein Wohnort (Review 04.10.2026, D2)
        self.assertEqual(fahrer["home"], {"name": "Hamburg", "lat": 53.55, "lon": 9.99})
        self.assertRegex(text, r"lat: 53\.55\n\s+lon: 9\.99\n")

    def test_persoenliche_importdateien_sind_nicht_versioniert(self):
        """Ein Google-Export (Takeout) ist eine persönliche Liste — mit Zuhause,
        Adressen, Notizen. Bis 1.19.1 lag einer im Repository, obwohl
        `.gitignore` ihn nannte: die Regel kam nach dem ersten Commit, und
        eine Regel entfernt nichts, was schon drin ist."""
        import subprocess
        from tests.helpers import ROOT
        versioniert = subprocess.run(["git", "ls-files"], cwd=ROOT,
                                     capture_output=True, text=True).stdout.split()
        if not versioniert:
            self.skipTest("kein Git-Repository")
        for pfad in versioniert:
            self.assertFalse(pfad.startswith("import/takeout-"), pfad)
            self.assertNotIn(pfad.rsplit(".", 1)[-1], ("gpx", "kml", "kmz"), pfad)
            self.assertNotIn(pfad, ("tagebuch.json", "modellguete.json"), pfad)

    def test_notizen_ohne_import_floskel(self):
        """Herkunft und Genauigkeit stehen in `source` und `verified`, die
        Gewässerart in `water_body` — die Notiz wiederholte das bis 1.19.2 als
        Fließtext, 163-mal derselbe Satz in jedem Report (1.20.0)."""
        from tests.helpers import ROOT
        for s in load_spots(str(SPOTS)):
            n = s.get("notes") or ""
            self.assertNotIn("Google-Liste", n, s["id"])
            self.assertNotIn("Takeout", n, s["id"])
            self.assertNotIn("Gewässerart offen", n, s["id"])
            self.assertNotIn("nachträglich ergänzten Spalte", n, s["id"])
        text = (ROOT / "import" / "import_takeout.py").read_text(encoding="utf-8")
        self.assertNotIn("Gewässerart offen", text)
        self.assertNotIn("Aus der eigenen Google-Liste", text)

    def test_takeout_filter_ist_ein_muster_und_kein_adressbuch(self):
        """Was der Takeout-Import als „kein Spot“ übergeht, steht als Muster im
        Skript — nicht als Liste von Namen und Adressen aus der eigenen Liste."""
        import importlib.util
        from tests.helpers import ROOT
        spec = importlib.util.spec_from_file_location("import_takeout", ROOT / "import" / "import_takeout.py")
        modul = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modul)
        self.assertTrue(hasattr(modul.NICHT_SPOT, "search"), "NICHT_SPOT ist ein Regex")
        for kein_spot in ("Musterstraße 12", "Am Weg 3a", "Irgendeine Sporthalle", "Seestrasse 63"):
            self.assertTrue(modul.NICHT_SPOT.search(kein_spot), kein_spot)
        for spot in ("Brouwersdam", "Strandhaus Ammersee", "Étang du Pâquis – Brognard", "Spot 3"):
            self.assertFalse(modul.NICHT_SPOT.search(spot), spot)
        text = (ROOT / "import" / "import_takeout.py").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"\d{5} [A-ZÄÖÜ][a-zäöü]+", "keine Postanschrift im Skript")

    def test_wird_aus_der_vorlage_angelegt(self):
        import shutil
        import tempfile
        from pathlib import Path
        from tests.helpers import ROOT
        from wingscout.config import load_config
        with tempfile.TemporaryDirectory() as d:
            ordner = Path(d)
            shutil.copy(ROOT / "config.example.yaml", ordner / "config.example.yaml")
            ziel = ordner / "config.yaml"
            self.assertFalse(ziel.exists())
            cfg = load_config(ziel)
            self.assertTrue(ziel.exists())
            self.assertEqual(cfg["rider"]["home"]["name"], "Hamburg")
            # Zweiter Aufruf überschreibt nichts
            ziel.write_text(ziel.read_text(encoding="utf-8").replace("Fahrer", "Jemand"),
                            encoding="utf-8")
            self.assertEqual(load_config(ziel)["rider"]["name"], "Jemand")
