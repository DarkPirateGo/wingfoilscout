"""Der Testlauf selbst: er schreibt nicht in `cache/` des Projekts.

Bis 2.5.2 legte jede Demo-Suche eines Tests über `cli.main` dort
`letzter_lauf.json` ab, und nach jedem Prüflauf — also nach jedem
Veröffentlichen — zeigte der Reiter Rückblick eine Demo-Suche als „letzte
Suche“ (Review 07.10.2026). Seit 2.5.3 legt `tests/__init__.py` CACHE für den
ganzen Lauf um; diese Tests merken, wenn das jemand rückgängig macht oder ein
Modul CACHE vorher übernimmt.
"""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path

import wingscout
from tests import CACHE_IM_TEST, CACHE_DES_PROJEKTS
from tests.helpers import SPOTS, CONFIG


def _stand(pfad: Path):
    """Ob es die Datei gibt und wann sie zuletzt geschrieben wurde."""
    try:
        st = pfad.stat()
    except FileNotFoundError:
        return None
    return (st.st_mtime_ns, st.st_size)


class CacheImTest(unittest.TestCase):
    def test_cache_liegt_ausserhalb_des_projekts(self):
        self.assertEqual(CACHE_DES_PROJEKTS, wingscout.ROOT / "cache")
        self.assertEqual(wingscout.CACHE, CACHE_IM_TEST)
        self.assertNotEqual(wingscout.CACHE.resolve().parent, wingscout.ROOT.resolve())

    def test_module_uebernehmen_den_cache_des_tests(self):
        from wingscout import pruefstand, report, rueckblick
        for name, pfad in (("rueckblick.LETZTER_LAUF", rueckblick.LETZTER_LAUF),
                           ("rueckblick.ERGEBNIS", rueckblick.ERGEBNIS),
                           ("pruefstand.LETZTER_LAUF", pruefstand.LETZTER_LAUF),
                           ("report.fassungen_ordner()", report.fassungen_ordner())):
            with self.subTest(name):
                self.assertTrue(Path(pfad).is_relative_to(CACHE_IM_TEST), pfad)

    def test_demo_suche_schreibt_nicht_ins_projekt(self):
        from wingscout.cli import main
        vorher = _stand(CACHE_DES_PROJEKTS / "letzter_lauf.json")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(main(["--demo", "--days", "1", "--radius", "300", "--out", str(Path(d) / "r.html"),
                                   "--quiet", "--config", str(CONFIG), "--spots", str(SPOTS),
                                   "--geometry", str(Path(d) / "keine.json")]), 0)
        self.assertTrue((CACHE_IM_TEST / "letzter_lauf.json").exists())
        self.assertEqual(_stand(CACHE_DES_PROJEKTS / "letzter_lauf.json"), vorher)


if __name__ == "__main__":
    unittest.main()
