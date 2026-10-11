"""Die App fürs Dock (seit 2.5.0): Bauskript, Startskript, Symbol.

Bauen lässt sie sich nur auf dem Mac (osacompile, codesign). Geprüft wird
hier, was sich überall prüfen lässt — und was beim nächsten Umbau nicht
leise wegfallen darf.
"""
from __future__ import annotations

import shutil
import struct
import subprocess
import unittest

from tests.helpers import ROOT

BAU = ROOT / "tools" / "mac_app.sh"
START = ROOT / "tools" / "app_start.sh"
DOPPELKLICK = ROOT / "App fürs Dock erstellen.command"
SYMBOL = ROOT / "tools" / "mac-app" / "Wingfoilscout.icns"


def _ohne_kommentare(text: str) -> str:
    return "\n".join(z for z in text.splitlines() if not z.lstrip().startswith("#"))


class Skripte(unittest.TestCase):
    @unittest.skipUnless(shutil.which("bash"), "kein bash")
    def test_syntax(self):
        for pfad in (BAU, START, DOPPELKLICK):
            with self.subTest(pfad.name):
                r = subprocess.run(["bash", "-n", str(pfad)], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_kein_persoenlicher_pfad(self):
        """Den Pfad zum Ordner setzt das Bauskript erst auf dem Mac ein — im
        Repository steht keiner."""
        for pfad in (BAU, START, DOPPELKLICK):
            with self.subTest(pfad.name):
                self.assertNotIn("/Users/", pfad.read_text(encoding="utf-8"))

    def test_startet_nie_fuers_wlan(self):
        """Die App gibt nichts fürs Handy frei — das geschieht nur mit Absicht
        im Reiter „Handy“."""
        code = _ohne_kommentare(START.read_text(encoding="utf-8"))
        self.assertIn("-m wingscout.webui", code)
        self.assertNotIn("--lan", code)

    def test_start_sucht_python_wie_der_starter(self):
        """Eine App hat nicht den PATH des Terminals: gesucht wird wie dort, dann
        an den üblichen Orten — der Platzhalter /usr/bin/python3 nur mit den
        Befehlszeilenwerkzeugen. Fehlt etwas, übernimmt der Starter im Terminal."""
        code = _ohne_kommentare(START.read_text(encoding="utf-8"))
        for teil in ("command -v python3", "/opt/homebrew/bin/python3", "xcode-select -p",
                     "sys.version_info >= (3, 9)", "import sys, yaml", 'open "Wingfoilscout starten.command"',
                     "nohup", "cache/oberflaeche.log"):
            with self.subTest(teil):
                self.assertIn(teil, code)
        self.assertTrue((ROOT / "Wingfoilscout starten.command").is_file())

    def test_bau_ersetzt_das_symbol_und_signiert(self):
        """osacompile bringt ein eigenes Symbol als Asset-Katalog mit, das vorginge;
        jede Änderung im Bündel bricht die Signatur — ohne neue startet auf Apple
        Silicon nichts."""
        code = _ohne_kommentare(BAU.read_text(encoding="utf-8"))
        for teil in ("osacompile", "tools/mac-app/Wingfoilscout.icns", 'rm -f "$RES/Assets.car"',
                     "Delete :CFBundleIconName", "codesign --force --sign -", '$HOME/Applications',
                     "quoted form of starter"):
            with self.subTest(teil):
                self.assertIn(teil, code)
        self.assertLess(code.index("Assets.car"), code.index("codesign"))

    def test_doppelklick_ruft_das_bauskript(self):
        text = DOPPELKLICK.read_text(encoding="utf-8")
        self.assertIn('cd "$(dirname "$0")" || exit 1', text)
        self.assertIn("bash tools/mac_app.sh", text)


class Symbol(unittest.TestCase):
    def test_icns_mit_allen_groessen(self):
        """Ein ICNS-Container (Kennung, Länge, Einträge), jeder Eintrag ein
        quadratisches PNG in der Größe, die sein Typ verlangt."""
        daten = SYMBOL.read_bytes()
        self.assertEqual(daten[:4], b"icns")
        self.assertEqual(struct.unpack(">I", daten[4:8])[0], len(daten))
        groessen, pos = {}, 8
        while pos < len(daten):
            typ = daten[pos:pos + 4].decode("ascii")
            laenge = struct.unpack(">I", daten[pos + 4:pos + 8])[0]
            inhalt = daten[pos + 8:pos + laenge]
            with self.subTest(typ):
                self.assertEqual(inhalt[:8], b"\x89PNG\r\n\x1a\n")
                breite, hoehe = struct.unpack(">II", inhalt[16:24])
                self.assertEqual(breite, hoehe)
            groessen[typ] = breite
            pos += laenge
        self.assertEqual(pos, len(daten))
        self.assertEqual(groessen, {"icp4": 16, "icp5": 32, "ic11": 32, "icp6": 64, "ic12": 64, "ic07": 128,
                                    "ic13": 256, "ic08": 256, "ic14": 512, "ic09": 512, "ic10": 1024})

    def test_quelle_liegt_daneben(self):
        svg = (SYMBOL.parent / "symbol.svg").read_text(encoding="utf-8")
        self.assertIn("viewBox='0 0 1024 1024'", svg)


if __name__ == "__main__":
    unittest.main()
