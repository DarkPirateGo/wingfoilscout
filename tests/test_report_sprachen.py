"""Der Report in allen vier Sprachen aus einer Suche (seit 2.3.0).

Bis 2.1.0 schrieb eine Suche ihren Report einmal, in der Sprache beim Start
der Suche. Der Reiter „Ziele“ zeigt diese Datei — wer danach die Sprache
umschaltete, sah ihn weiter in der alten, bis zur nächsten Suche (gemeldet am
04.10.2026). Jetzt legt eine Suche dieselben Ergebnisse in allen vier Sprachen
ab: gerechnet einmal, die Texte aus der Rechnung (Veto einer Stunde, Hinweise
einer Session, Gründe, Himmelsrichtungen) je Sprache neu gesetzt
(`i18n.TD`, `i18n.uebersetzt`).

Der wichtigste Test hier vergleicht Zeichen für Zeichen: eine Demo-Suche, auf
Deutsch gerechnet und auf Englisch, Französisch und Spanisch geschrieben, muss
dem Report gleichen, den eine Suche in der jeweiligen Sprache selbst schreibt.
Bleibt irgendwo ein Text aus der Rechnung in der Sprache der Suche stehen,
fällt es dort auf.
"""
from __future__ import annotations

import contextlib
import copy
import html
import io
import json
import os
import pickle
import re
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

import wingscout
from wingscout import cli, geo, i18n, report
from wingscout import webui as w

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.example.yaml"
SPOTS = ROOT / "spots.yaml"
GEOMETRIE = ROOT / "geometry.json"
FREMDE = [s for s in i18n.SPRACHEN if s != i18n.QUELLE]


def ohne_zeit(text: str) -> str:
    """Was sich zwischen zwei Läufen von selbst ändert: die Nonce, die Zeit
    der Erstellung und die Lage der Tide „jetzt“."""
    text = re.sub(r"nonce-[A-Za-z0-9+/=_-]+", "nonce-X", text)
    text = re.sub(r"nonce='[^']*'", "nonce='X'", text)
    text = re.sub(r"<title>[^<]*</title>", "<title></title>", text)
    text = re.sub(r"<span class='nw'>[^<]*</span>", "<span class='nw'></span>", text)
    text = re.sub(r"(<span class='tide-jetzt'[^>]*>)[^<]*(</span>)", r"\1\2", text)
    return re.sub(r'"tide_text": "[^"]*"', '"tide_text": ""', text)


def erste_abweichung(a: str, b: str) -> str:
    """Wo zwei Reports auseinandergehen — für eine lesbare Fehlermeldung."""
    i = next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return f"ab Zeichen {i}:\n  {a[max(0, i - 120):i + 120]!r}\n  {b[max(0, i - 120):i + 120]!r}"


def suche(out: Path, sprache: str, *extra: str) -> int:
    with contextlib.redirect_stderr(io.StringIO()):
        return cli.main(["--demo", "--days", "4", "--radius", "1500", "--out", str(out), "--quiet",
                         "--config", str(CONFIG), "--spots", str(SPOTS), "--geometry", str(GEOMETRIE),
                         "--sprache", sprache, *extra])


class Umgebung(unittest.TestCase):
    """Eigener Ordner für Report und Zwischenspeicher, keine gespeicherte
    Sprachwahl, und `--sprache` gilt (die Tests laufen sonst fest auf Deutsch)."""

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.tmp = Path(tmp.name)
        cls.standard = cls.tmp / "report.html"
        for patcher in (mock.patch.object(wingscout, "CACHE", cls.tmp / "cache"),
                        mock.patch.object(wingscout, "REPORT", cls.standard),
                        mock.patch.object(w, "REPORT_FILE", cls.standard),
                        mock.patch.object(i18n, "SPRACH_DATEI", cls.tmp / "sprache.txt"),
                        mock.patch.dict(os.environ)):
            patcher.start()
            cls.addClassCleanup(patcher.stop)
        os.environ.pop("WINGSCOUT_SPRACHE", None)
        vorher = getattr(i18n._lokal, "sprache", None)
        cls.addClassCleanup(i18n.setze, vorher or i18n.QUELLE)

    @classmethod
    def ordner(cls) -> Path:
        return cls.tmp / "cache" / "report"


class GleichWieInDerSpracheGerechnet(Umgebung):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        assert suche(cls.standard, "de") == 0
        cls.deutsch = cls.standard.read_text(encoding="utf-8")

    def test_alle_vier_fassungen_liegen_bereit(self):
        index = json.loads((self.ordner() / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(index["sprachen"]), sorted(i18n.SPRACHEN))
        # Die deutsche Fassung ist report.html selbst
        self.assertEqual(report.fassung(self.standard.read_bytes(), "de"), self.standard.read_bytes())
        for sprache in i18n.SPRACHEN:
            roh = report.fassung(self.standard.read_bytes(), sprache)
            self.assertIsNotNone(roh, sprache)
            self.assertIn(f"<html lang='{sprache}'>".encode(), roh)

    def test_die_demo_deckt_die_texte_aus_der_rechnung_ab(self):
        """Damit der Vergleich unten etwas beweist: der deutsche Report enthält
        Texte aus allen Ecken der Rechnung."""
        for text in ("außerhalb der Tageslichtzeit",                 # Veto einer Stunde (score)
                     "außerhalb des Radius",                         # Grund im Katalogfilter (spots)
                     "Nicht berücksichtigt",
                     "Regen (bis",                                   # Hinweis einer Session
                     "Gewitter",
                     "Modelle uneinig (bis",
                     "class='tide",                                  # Tide am Ziel
                     "SSW"):                                         # Himmelsrichtung
            with self.subTest(text=text):
                self.assertIn(text, self.deutsch)

    def test_jede_fassung_gleicht_dem_report_einer_suche_in_ihrer_sprache(self):
        for sprache in FREMDE:
            with self.subTest(sprache=sprache):
                fassung = report.fassung(self.standard.read_bytes(), sprache).decode("utf-8")
                eigene = self.tmp / f"eigen-{sprache}.html"
                self.assertEqual(suche(eigene, sprache), 0)
                a, b = ohne_zeit(fassung), ohne_zeit(eigene.read_text(encoding="utf-8"))
                self.assertTrue(a == b, "Fassung aus der deutschen Suche ≠ Suche auf " + sprache + ", "
                                + erste_abweichung(a, b))

    def test_in_der_englischen_fassung_steht_nichts_mehr_deutsch(self):
        englisch = report.fassung(self.standard.read_bytes(), "en").decode("utf-8")
        for deutsch, uebersetzt in (("außerhalb der Tageslichtzeit", "outside daylight hours"),
                                    ("etwas Regen (bis", "some rain (up to")):
            with self.subTest(text=deutsch):
                self.assertNotIn(deutsch, englisch)
                self.assertIn(uebersetzt, englisch)

    def test_eine_suche_mit_eigenem_ziel_laesst_die_fassungen_in_ruhe(self):
        """`--out` woanders hin (Kommandozeile, Tests): die Fassungen gehören
        weiter zum Report, den die Oberfläche zeigt."""
        vorher = {p.name: p.read_bytes() for p in self.ordner().iterdir()}
        self.assertEqual(suche(self.tmp / "anderswo.html", "en"), 0)
        self.assertEqual({p.name: p.read_bytes() for p in self.ordner().iterdir()}, vorher)


class ZieleFolgtDerSprache(Umgebung):
    """Der Reiter „Ziele“ über den Server: die Fassung der Spracheinstellung."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        assert suche(cls.standard, "fr") == 0
        server = w.BegrenzterServer(("127.0.0.1", 0), w.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        cls.addClassCleanup(server.server_close)
        cls.addClassCleanup(server.shutdown)
        cls.basis = f"http://127.0.0.1:{server.server_address[1]}"

    def setUp(self):
        with contextlib.suppress(FileNotFoundError):
            i18n.SPRACH_DATEI.unlink()

    def holen(self, browser: str = "") -> str:
        anfrage = urllib.request.Request(self.basis + "/report", headers={"Accept-Language": browser})
        with urllib.request.urlopen(anfrage, timeout=30) as antwort:
            return antwort.read().decode("utf-8")

    def test_ohne_wahl_die_sprache_des_browsers(self):
        for browser, sprache in (("en-GB,en;q=0.9", "en"), ("es-ES", "es"), ("de-DE", "de"), ("fr", "fr")):
            with self.subTest(browser=browser):
                seite = self.holen(browser)
                self.assertIn(f"<html lang='{sprache}'>", seite)
                self.assertIn("nav class='reiter'", seite)          # mit Reiterleiste

    def test_mit_wahl_im_umschalter_diese(self):
        for sprache in i18n.SPRACHEN:
            with self.subTest(sprache=sprache):
                i18n.speichern(sprache)
                self.assertIn(f"<html lang='{sprache}'>", self.holen("es-ES"))

    def test_ein_report_ohne_passende_fassungen_kommt_wie_er_ist(self):
        """Eine Suche einer älteren Version (oder ein von Hand ersetzter
        Report): report.html passt nicht mehr zum Index — dann eben in seiner
        Sprache statt einer fremden Fassung."""
        roh = self.standard.read_bytes()
        self.addCleanup(self.standard.write_bytes, roh)
        self.standard.write_bytes(roh.replace(b"</body>", b"<!-- anders --></body>", 1))
        seite = self.holen("en")
        self.assertIn("<html lang='fr'>", seite)
        self.assertIn("<!-- anders -->", seite)


class FassungNurWennAllesPasst(Umgebung):
    """`report.fassung()` liefert nur, was genau zu diesem Report gehört."""

    def setUp(self):
        self.ordner().mkdir(parents=True, exist_ok=True)
        for p in self.ordner().iterdir():
            p.unlink()
        self.haupt = b"<html lang='de'>Haupt</html>"
        self.standard.write_bytes(self.haupt)
        with i18n.in_sprache("de"):
            report.fassungen_schreiben(self.standard, lambda: f"<html lang='{i18n.aktuell()}'>x</html>")

    def test_alles_passt(self):
        self.assertEqual(report.fassung(self.haupt, "de"), self.haupt)
        self.assertEqual(report.fassung(self.haupt, "es"), b"<html lang='es'>x</html>")

    def test_unbekannte_sprache(self):
        for sprache in ("it", "", "../index", "de/../es"):
            with self.subTest(sprache=sprache):
                self.assertIsNone(report.fassung(self.haupt, sprache))

    def test_anderer_report(self):
        self.assertIsNone(report.fassung(self.haupt + b" ", "en"))

    def test_fassung_veraendert(self):
        (self.ordner() / "report.en.html").write_bytes(b"<html lang='en'>untergeschoben</html>")
        self.assertIsNone(report.fassung(self.haupt, "en"))
        self.assertIsNotNone(report.fassung(self.haupt, "fr"))

    def test_index_fehlt_oder_kaputt(self):
        index = self.ordner() / "index.json"
        for inhalt in (None, "", "{", "[]", '{"report": 1}', '{"report": "x", "sprachen": []}',
                       "[" * 100000 + "]" * 100000):
            with self.subTest(inhalt=(inhalt or "")[:20]):
                if inhalt is None:
                    index.unlink(missing_ok=True)
                else:
                    index.write_text(inhalt, encoding="utf-8")
                self.assertIsNone(report.fassung(self.haupt, "en"))

    def test_waehrend_des_schreibens_gilt_der_alte_index_nicht_mehr(self):
        """Der Index geht als Erstes weg: scheitert das Schreiben mittendrin,
        zeigt „Ziele“ report.html statt einer Mischung aus zwei Suchen."""
        def kaputt():
            raise RuntimeError("abgebrochen")
        with i18n.in_sprache("de"), self.assertRaises(RuntimeError):
            report.fassungen_schreiben(self.standard, kaputt)
        self.assertFalse((self.ordner() / "index.json").exists())
        self.assertIsNone(report.fassung(self.haupt, "de"))


class TexteInDaten(unittest.TestCase):
    """`i18n.TD()`: derselbe Text wie aus `T()`, in jeder Sprache neu zu setzen."""

    def test_wie_t_und_neu_gesetzt(self):
        with i18n.in_sprache("de"):
            veto = i18n.TD("außerhalb der Tageslichtzeit")
            regen = i18n.TD("Regen {mm} mm/h", mm="2.5")
            self.assertEqual(veto, "außerhalb der Tageslichtzeit")
            self.assertEqual(regen, i18n.T("Regen {mm} mm/h", mm="2.5"))
            self.assertIsInstance(veto, str)
            self.assertIs(i18n.uebersetzt(veto), veto)              # in seiner Sprache: unverändert
        with i18n.in_sprache("en"):
            self.assertEqual(i18n.uebersetzt(veto), i18n.T("außerhalb der Tageslichtzeit"))
            self.assertEqual(i18n.uebersetzt(regen), i18n.T("Regen {mm} mm/h", mm="2.5"))
            self.assertNotEqual(i18n.uebersetzt(veto), "außerhalb der Tageslichtzeit")

    def test_verschachtelt_und_mehrzahl(self):
        with i18n.in_sprache("de"):
            innen = i18n.TD("HW ± {h} h", h="2")
            aussen = i18n.TD("außerhalb des Tidenfensters ({fenster})", fenster=innen)
            warnungen = i18n.TND("{n} Warnung", "{n} Warnungen", 3)
        with i18n.in_sprache("fr"):
            self.assertEqual(i18n.uebersetzt(aussen),
                             i18n.T("außerhalb des Tidenfensters ({fenster})", fenster=i18n.T("HW ± {h} h", h="2")))
            self.assertEqual(i18n.uebersetzt(warnungen), i18n.TN("{n} Warnung", "{n} Warnungen", 3))

    def test_alles_andere_bleibt(self):
        with i18n.in_sprache("en"):
            for wert in ("gewöhnlicher Text", "", None, 3, ["a"], i18n.Text("ohne Rezept")):
                self.assertIs(i18n.uebersetzt(wert), wert)

    def test_kopie_und_pickle_behalten_das_rezept(self):
        with i18n.in_sprache("de"):
            original = [i18n.TD("Regen {mm} mm/h", mm="1.0"), geo.compass(90)]
        for kopie in (copy.deepcopy(original), pickle.loads(pickle.dumps(original))):
            with i18n.in_sprache("en"):
                self.assertEqual([i18n.uebersetzt(x) for x in kopie], [i18n.uebersetzt(x) for x in original])

    def test_himmelsrichtung(self):
        with i18n.in_sprache("de"):
            ost = geo.compass(90)
            self.assertEqual(ost, "O")
        with i18n.in_sprache("en"):
            self.assertEqual(i18n.uebersetzt(ost), geo.compass(90))
            self.assertEqual(i18n.uebersetzt(ost), i18n.T(geo.KOMPASS).split()[4])

    def test_in_sprache_stellt_den_alten_zustand_wieder_her(self):
        def stand():
            return getattr(i18n._lokal, "sprache", "ungesetzt")
        ergebnis = []

        def im_thread():
            ergebnis.append(stand())
            with i18n.in_sprache("es"):
                ergebnis.append(i18n.aktuell())
            ergebnis.append(stand())
            i18n.setze("fr")
            with i18n.in_sprache("en"):
                ergebnis.append(i18n.aktuell())
            ergebnis.append(stand())
        t = threading.Thread(target=im_thread)
        t.start()
        t.join()
        self.assertEqual(ergebnis, ["ungesetzt", "es", "ungesetzt", "en", "fr"])

    def test_report_escaped_neu_gesetzt(self):
        """`report._esc()` setzt einen Text aus der Rechnung in der Sprache des
        Reports neu — und escaped ihn danach, die Werte eingeschlossen."""
        with i18n.in_sprache("de"):
            text = i18n.TD("{kn} kn — kein passender Wing im Quiver", kn="<9>")
        with i18n.in_sprache("en"):
            self.assertEqual(report._esc(text), html.escape(i18n.T("{kn} kn — kein passender Wing im Quiver",
                                                                   kn="<9>")))
            self.assertNotIn("<9>", report._esc(text))
            self.assertNotIn("kein passender Wing", report._esc(text))


if __name__ == "__main__":
    unittest.main()
