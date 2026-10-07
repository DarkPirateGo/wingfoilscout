"""Was nie ins öffentliche Repository darf — und die Wächter dafür.

Review 04.10.2026: `tools/veroeffentlichen.sh` nahm mit `git add -A` alles
mit, was `.gitignore` nicht kannte (D1), schrieb mit jeder Adresse fest (D4)
und schob jeden lokalen Tag mit (D7); Notizen im Katalog sprachen den
Maintainer persönlich an (D5); der Takeout-Import schrieb `nan` in den
Katalog (C23) und übernahm eigene Notizen ungefragt.

Geprüft wird, was gelten soll — nie gegen eine Liste privater Werte: die
stünde selbst im Repository (D3). Wo ein Startpunkt gebraucht wird, ist er
erfunden; die eigene config.yaml wird nur zur Laufzeit gelesen.
"""
from __future__ import annotations
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from tests.helpers import ROOT, SPOTS


def _modul(name: str, pfad: Path):
    spec = importlib.util.spec_from_file_location(name, pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


waechter = _modul("persoenliche_daten", ROOT / "tools" / "persoenliche_daten.py")

# So entsteht Persönliches neben dem Projekt: Kopien im Finder, die
# Zwischendateien der App, Exporte, Bildschirmfotos, Editor- und Claude-Dateien.
VERBOTEN = (
    "config.yaml", "config Kopie.yaml", "config-alt.yaml", "config.example Kopie.yaml",
    "config.yaml.neu", "tagebuch.json", "tagebuch Kopie.json", "tagebuch.json.neu",
    "favoriten.json", "favoriten Kopie.json", "favoriten-alt.json", "favoriten.json.neu",
    "modellguete.json", "modellguete.json.neu", "ui_defaults.json", "ui_defaults Kopie.json",
    "report.html", "report Kopie.html", "report.html.neu", "spots.yaml.neu", "sprache.txt",
    "cache/routes.json", "import/Gespeicherte Orte.csv", "import/takeout-2026-09-13.csv",
    "import/Saved Places.json", "Takeout/Saved Places.json",
    "Takeout/Maps (your places)/Saved Places.json", "touren/heimweg.gpx", "spur.kml",
    "karte.kmz", "orte.geojson", "import/orte.geojson", "takeout-20260913T120000Z-001.zip",
    "spots.yaml.bak", "README.md~", ".spots.yaml.swp", "wingscout/.webui.py.swo",
    ".claude/settings.local.json", "CLAUDE.local.md",
    "Bildschirmfoto 2026-10-03 um 12.00.00.png", "docs/Screenshot 2026-10-03 at 12.00.00.png",
    "Bildschirmaufnahme 2026-10-03 um 12.00.00.mov", "Screen Recording 2026-10-03 at 12.00.00.mov",
    ".DS_Store", "docs/.DS_Store", "Claude outputs/release-v2.1.0.md", "live_lauf.json",
    "vorschau.html", "lauf_tmp.html",
)
# Versioniert und es bleibt so — auch, was einem der Muster nahekommt.
ERLAUBT = (
    "config.example.yaml", "spots.yaml", "geometry.json", "instagram.json",
    "pruefstand/grundlinie.json", "import/import_takeout.py", "import/import_jensdee.py",
    "import/jensdee_liste_roh.md", "import/jensdee_pins.yaml", "import/merge_catalog.py",
    "docs/demo.html", "docs/index.html", "docs/bewertung.html", "docs/.nojekyll",
    "docs/bilder/en/search-light.png", "docs/bilder/vorschau.jpg",
    "docs/video/wingfoilscout-promo-en.mp4", "docs/video/promo-poster.jpg",
    "wingscout/lang/en.json", "wingscout/web/icon-512.png", "wingscout/web/karte.js",
    "wingscout/favoriten.py", "wingscout/web/favoriten.js", "tests/test_favoriten.py",
    "tests/test_catalog.py", ".github/workflows/tests.yml", ".gitignore", ".gitattributes",
    "tools/veroeffentlichen.sh", "tools/persoenliche_daten.py", "Tests ausführen.command",
    "Auf GitHub veröffentlichen.command", "pyproject.toml", "requirements.txt", "CHANGELOG.md",
)


def _ohne_git_umgebung() -> dict:
    """Die Umgebung ohne GIT_*: im Pre-Commit-Hook zeigen GIT_DIR und
    GIT_INDEX_FILE auf das echte Repository — ein Git-Aufruf in einem
    Wegwerf-Ordner landete sonst dort."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _versioniert() -> list[str]:
    """Die versionierten Dateien — leer ohne Git oder außerhalb eines Repositorys."""
    if shutil.which("git") is None:
        return []
    aus = subprocess.run(["git", "-c", "core.quotepath=off", "ls-files"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8")
    return aus.stdout.splitlines() if aus.returncode == 0 else []


class Verbotsliste(unittest.TestCase):
    def test_persoenliches_wird_erkannt(self):
        for pfad in VERBOTEN:
            with self.subTest(pfad):
                self.assertTrue(waechter.grund(pfad))

    def test_versioniertes_bleibt_erlaubt(self):
        for pfad in ERLAUBT + tuple(_versioniert()):
            with self.subTest(pfad):
                self.assertIsNone(waechter.grund(pfad))

    def test_gitignore_deckt_dieselbe_liste(self):
        """Was der Wächter verbietet, ignoriert auch .gitignore — sonst stünde es
        in der Frage nach neuen Dateien, und ein »ja« nähme es mit. Und nichts,
        was versioniert bleiben soll, wird ignoriert."""
        if shutil.which("git") is None:
            self.skipTest("kein git")
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q"], cwd=d, env=_ohne_git_umgebung(), check=True)
            shutil.copy(ROOT / ".gitignore", Path(d) / ".gitignore")
            aus = subprocess.run(["git", "-c", "core.quotepath=off", "check-ignore", "--no-index",
                                  "--stdin", "-n", "-v"], cwd=d, env=_ohne_git_umgebung(),
                                 input="\n".join(VERBOTEN + ERLAUBT) + "\n",
                                 capture_output=True, text=True, encoding="utf-8").stdout
        ignoriert = set()
        for zeile in aus.splitlines():
            quelle, _, pfad = zeile.partition("\t")
            datei, _, rest = quelle.partition(":")
            muster = rest.partition(":")[2]
            if datei == ".gitignore" and not muster.startswith("!"):
                ignoriert.add(pfad)
        for pfad in VERBOTEN:
            with self.subTest(pfad):
                self.assertIn(pfad, ignoriert, "von .gitignore nicht abgedeckt")
        for pfad in ERLAUBT:
            with self.subTest(pfad):
                self.assertNotIn(pfad, ignoriert, "von .gitignore ignoriert")

    def test_nichts_versioniertes_ist_ignoriert(self):
        if not _versioniert():
            self.skipTest("kein Git-Repository")
        aus = subprocess.run(["git", "-c", "core.quotepath=off", "ls-files", "-ci", "--exclude-standard"],
                             cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout
        self.assertEqual(aus.splitlines(), [])

    def test_alte_regeln_bleiben(self):
        """tests/test_security.py und test_review_2026_09.py lesen .gitignore
        zeilenweise — die bisherigen Einträge stehen weiter für sich."""
        zeilen = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        for eintrag in ("config.yaml", "/config*.yaml", "!/config.example.yaml", "*.neu",
                        "tagebuch.json", "Takeout/", "import/*.csv", "Bildschirmfoto*"):
            self.assertIn(eintrag, zeilen)


class Heimatkoordinate(unittest.TestCase):
    """Der Wächter für den eigenen Startpunkt — mit einem erfundenen Punkt."""

    PUNKT = ("12.34", "56.789")

    def test_schreibweisen_werden_erkannt(self):
        """Genau, gröber, genauer, etwas daneben — alles keinen Kilometer weit."""
        for text in ('{"lat": 12.34, "lon": 56.789}', "origin=12.34,56.789&destination=1.5,2.5",
                     "  lat: 12.34\n    lon: 56.789\n", "12,34 56,789", "[56.789, 12.34]",
                     '"lat": 12.3449, "lon": 56.7891', "12.34/56.79", "12.343, 56.785"):
            with self.subTest(text):
                self.assertTrue(waechter.fundstellen(text, *self.PUNKT))

    def test_andere_punkte_nicht(self):
        for text in ("12.36, 56.789", "12.34, 56.81", "112.34, 56.789", "12.3, 56.8",
                     "-12.34, 56.789", "lat: 12.34\n" + "x" * 200 + "\nlon: 56.789", "12.34 und sonst nichts"):
            with self.subTest(text):
                self.assertEqual(waechter.fundstellen(text, *self.PUNKT), [])

    def test_zeilennummer(self):
        self.assertEqual(waechter.fundstellen('a\nb\n{"lat": 12.34, "lon": 56.789}\n', *self.PUNKT), [3])

    def test_heimat_aus_der_config(self):
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "config.yaml"
            self.assertIsNone(waechter.heimat(pfad))                       # keine Datei: nichts zu prüfen
            pfad.write_text("rider:\n  home:\n    lat: 12.340\n    lon: 56.789\n", encoding="utf-8")
            self.assertEqual(waechter.heimat(pfad), ("12.34", "56.789"))
            pfad.write_text("rider:\n  name: x\n", encoding="utf-8")
            self.assertIsNone(waechter.heimat(pfad))
            pfad.write_text("rider: [\n", encoding="utf-8")
            with self.assertRaises(ValueError):                           # unlesbar: nicht prüfbar
                waechter.heimat(pfad)

    def test_eigener_startpunkt_steht_in_keiner_versionierten_datei(self):
        """Gegen die eigene config.yaml: ihr `rider.home` steht in keiner
        versionierten Textdatei. Ohne config.yaml oder ohne Git (frischer Klon,
        ZIP, Prüflauf auf GitHub) gibt es nichts zu vergleichen."""
        punkt = waechter.heimat()
        dateien = _versioniert()
        if punkt is None or not dateien:
            self.skipTest("keine config.yaml mit rider.home oder kein Git-Repository")
        if punkt == ("53.55", "9.99"):
            self.skipTest("der eigene Startpunkt ist der Demo-Punkt")
        for name in dateien:
            pfad = ROOT / name
            if not pfad.is_file():
                continue
            roh = pfad.read_bytes()
            if b"\0" in roh[:8192]:
                continue                                                  # Bild, Video
            with self.subTest(name):
                self.assertEqual(waechter.fundstellen(roh.decode("utf-8", "replace"), *punkt), [],
                                 "Zeilen mit dem eigenen Startpunkt")


class KatalogOhneAnrede(unittest.TestCase):
    """Notizen und Quellen im Katalog sind öffentliche Daten — sie sprechen
    niemanden an („Deine Referenz“, „du kennst das von Gold“; bis 2.1.0)."""

    DU = re.compile(r"\bdein\w*\b|\bdich\b|\bdir\b|\bdu (kennst|hast|bist|fährst)\b", re.IGNORECASE)

    def _texte(self, wert, schluessel=""):
        if isinstance(wert, dict):
            for k, v in wert.items():
                yield from self._texte(v, str(k))
        elif isinstance(wert, list):
            for v in wert:
                yield from self._texte(v, schluessel)
        elif isinstance(wert, str) and schluessel.startswith(("note", "source")):
            yield schluessel, wert

    def test_notizen_und_quellen(self):
        geprueft = 0
        for spot in yaml.safe_load(SPOTS.read_text(encoding="utf-8")):
            for schluessel, text in self._texte(spot):
                geprueft += 1
                with self.subTest(spot=spot["id"], feld=schluessel):
                    self.assertIsNone(self.DU.search(text), text[:160])
        self.assertGreater(geprueft, 300, "Notizen und Quellen nicht gefunden")

    def test_das_muster_trifft_die_anrede_und_nicht_das_franzoesische(self):
        for text in ("Deine Referenz.", "von dir als schlecht bewertet", "du kennst das von Gold",
                     "für dein Setup klären", "aus deinem Ranking", "Du hast ihn schon im Katalog"):
            with self.subTest(text):
                self.assertTrue(self.DU.search(text))
        for text in ("Lac du Der", "Plage du Vougo", "Bouches-du-Rhône", "Étang du Pâquis – Brognard",
                     "Abendwind vom Massif du Chat", "Le Grau-du-Roi", "für das eigene Setup klären"):
            with self.subTest(text):
                self.assertIsNone(self.DU.search(text))


class TakeoutImport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modul = _modul("import_takeout", ROOT / "import" / "import_takeout.py")

    def test_unbrauchbare_koordinaten_fliegen_raus(self):
        """`nan` schrieb `.nan` in den Katalog, `inf` brach den Import ab."""
        zeilen = [{"Titel": "N", "Breitengrad": "nan", "Längengrad": "3.8"},
                  {"Titel": "I", "Breitengrad": "inf", "Längengrad": "3.8"},
                  {"Titel": "R", "Breitengrad": "95", "Längengrad": "200"},
                  {"Titel": "P", "URL": "https://www.google.com/maps/search/123.4,500.2"},
                  {"Titel": "Strand Gut", "Breitengrad": "51.7", "Längengrad": "3.8"}]
        neu, uebersprungen = self.modul.auswerten(zeilen, [])
        self.assertEqual([e["name"] for e in neu], ["Strand Gut"])
        self.assertEqual({n for n, g in uebersprungen if g == self.modul.UNBRAUCHBAR}, {"N", "I", "R", "P"})
        text = yaml.safe_dump(neu, allow_unicode=True)
        self.assertNotIn(".nan", text)
        self.assertNotIn(".inf", text)

    def test_eigene_notizen_nur_auf_wunsch(self):
        zeilen = [{"Titel": "Gesetzte Markierung", "Notiz": "Lieblingsplatz\nParken hinter der Halle",
                   "URL": "https://www.google.com/maps/search/51.7,3.8"},
                  {"Titel": "Strand Zwei", "Notiz": "Nur bei Westwind", "Breitengrad": "52.1",
                   "Längengrad": "4.2"}]
        neu, _ = self.modul.auswerten(zeilen, [])
        self.assertEqual([e["notes"] for e in neu], ["", ""])
        self.assertTrue(neu[0]["name"].startswith("Pin "), "auch kein Name aus der Notiz")
        self.assertEqual(neu[1]["water_body"], "sea")                     # eingeordnet wird trotzdem
        neu, _ = self.modul.auswerten(zeilen, [], mit_notizen=True)
        self.assertEqual(neu[0]["name"], "Lieblingsplatz")
        self.assertEqual(neu[1]["notes"], "Nur bei Westwind")


class Werkzeuge(unittest.TestCase):
    """Was in den Skripten nicht wieder verschwinden darf."""

    @staticmethod
    def _code(pfad: Path) -> str:
        return "\n".join(z for z in pfad.read_text(encoding="utf-8").splitlines()
                         if not z.lstrip().startswith("#"))

    def test_veroeffentlichen(self):
        code = self._code(ROOT / "tools" / "veroeffentlichen.sh")
        self.assertNotRegex(code, r"git add (-A|--all|\.)(\s|$)")
        self.assertIn("git add -u", code)
        self.assertIn("ls-files --others --exclude-standard", code)
        # jeder neue Name, auch das Ziel einer Umbenennung, ohne Anführungszeichen
        self.assertIn("diff --cached --name-only -z --no-renames --diff-filter=ACMRT", code)
        self.assertNotIn("--diff-filter=A ", code)
        self.assertIn("persoenliche_daten.py heimat", code)
        self.assertIn("--src-prefix=a/ --dst-prefix=b/", code)
        self.assertIn("@users.noreply.github.com", code)
        self.assertIn("git var GIT_AUTHOR_IDENT", code)
        self.assertIn("git var GIT_COMMITTER_IDENT", code)
        self.assertNotIn("--tags", code)
        self.assertIn('git push --atomic --no-follow-tags origin "$zweig" "refs/tags/v$version"', code)
        self.assertIn('git push --no-follow-tags origin "$zweig"', code)
        pushes = re.findall(r"(?m)^\s*git push\b.*$", code)
        self.assertEqual(len(pushes), 2, "kein weiterer Weg nach oben")
        for zeile in pushes:
            self.assertIn("--no-follow-tags", zeile)

    def test_pruefung_auf_github(self):
        text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        ablauf = yaml.safe_load(text)
        self.assertEqual(ablauf["permissions"], {"contents": "read"})
        schritte = ablauf["jobs"]["tests"]["steps"]
        self.assertIs(schritte[0]["with"]["persist-credentials"], False)
        self.assertTrue(any("persoenliche_daten.py dateien" in s.get("run", "") for s in schritte))

    def test_check_und_doppelklick(self):
        check = self._code(ROOT / "tools" / "check.sh")
        self.assertNotIn("PIPESTATUS", check)
        self.assertIn("persoenliche_daten.py dateien", check)
        self.assertIn("persoenliche_daten.py heimat", check)
        # wie in veroeffentlichen.sh: Namen ohne Anführungszeichen, Vorsilben fest
        self.assertIn("diff --cached --name-only -z --no-renames --diff-filter=ACMRT", check)
        self.assertIn("--src-prefix=a/ --dst-prefix=b/", check)
        doppelklick = (ROOT / "Tests ausführen.command").read_text(encoding="utf-8")
        self.assertIn('cd "$(dirname "$0")" || exit 1', doppelklick)

    def test_contributing_lehrt_kein_git_add_alles(self):
        text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        for block in re.findall(r"```bash\n(.*?)```", text, re.S):
            self.assertNotRegex(block, r"(?m)^\s*git add (-A|--all|\.)(\s|$)")


@unittest.skipUnless(shutil.which("bash") and shutil.which("git"), "bash oder git fehlt")
class VeroeffentlichenImWegwerfRepo(unittest.TestCase):
    """tools/veroeffentlichen.sh einmal echt: ein Wegwerf-Repository, ein
    lokales „GitHub“ (bare), ein Prüflauf, der immer grün ist, und eine
    config.yaml mit einem erfundenen Startpunkt. Auf dem Mac läuft das mit
    dessen bash 3.2."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = _ohne_git_umgebung()
        self.env.update(HOME=str(self.tmp), XDG_CONFIG_HOME=str(self.tmp), GIT_CONFIG_NOSYSTEM="1")
        werkzeug = self.tmp / "bin"                     # dasselbe Python wie dieser Testlauf
        werkzeug.mkdir()
        (werkzeug / "python3").symlink_to(sys.executable)
        self.env["PATH"] = f"{werkzeug}{os.pathsep}{self.env.get('PATH', '')}"
        self.remote, self.repo = self.tmp / "github.git", self.tmp / "repo"
        self.git("init", "-q", "--bare", str(self.remote), cwd=self.tmp)
        (self.repo / "tools").mkdir(parents=True)
        (self.repo / "wingscout").mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "1+test@users.noreply.github.com")
        for name in ("veroeffentlichen.sh", "persoenliche_daten.py"):
            shutil.copy(ROOT / "tools" / name, self.repo / "tools" / name)
        shutil.copy(ROOT / ".gitignore", self.repo / ".gitignore")
        self.schreibe("tools/check.sh", "#!/usr/bin/env bash\nexit 0\n")
        self.schreibe("wingscout/__init__.py", '__version__ = "1.0.0"\n')
        self.schreibe("CHANGELOG.md", "## 1.0.1 — Test\n")
        self.schreibe("spots.yaml", "- id: a\n")
        self.schreibe("config.yaml", "rider:\n  home:\n    lat: 12.34\n    lon: 56.789\n")
        self.git("add", ".gitignore", "tools", "wingscout", "CHANGELOG.md", "spots.yaml")
        self.git("commit", "-q", "-m", "Anfang")
        self.git("remote", "add", "origin", str(self.remote))
        self.git("push", "-q", "-u", "origin", "HEAD")
        self.git("tag", "-a", "v0.9.0-alt", "-m", "ein alter Tag, der hierbleiben soll")

    def schreibe(self, name: str, text: str):
        (self.repo / name).write_text(text, encoding="utf-8")

    def git(self, *args, cwd=None) -> str:
        r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=cwd or self.repo, env=self.env,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def veroeffentlichen(self, *args, eingabe: str = "", env: dict | None = None):
        return subprocess.run(["bash", "tools/veroeffentlichen.sh", *args], cwd=self.repo,
                              env=dict(self.env, **(env or {})), input=eingabe, capture_output=True, text=True,
                              encoding="utf-8", timeout=120)

    def commits(self) -> int:
        return int(self.git("rev-list", "--count", "HEAD"))

    def zweig(self) -> str:
        return self.git("symbolic-ref", "--short", "HEAD").strip()

    def oben(self, remote: Path | None = None) -> str:
        """Was auf dem lokalen „GitHub“ liegt: jeder Zweig und Tag mit Stand."""
        return self.git("ls-remote", str(remote or self.remote))

    def oben_adressen(self) -> set:
        """Jede Adresse auf dem lokalen „GitHub“: Autor, Committer, Tagger."""
        commits = self.git("--git-dir", str(self.remote), "log", "--all", "--format=%ae%n%ce").split()
        tagger = self.git("--git-dir", str(self.remote), "for-each-ref", "--format=%(taggeremail)", "refs/tags").split()
        return set(commits) | {t.strip("<>") for t in tagger}

    def test_normaler_lauf_fragt_nach_neuem_und_schiebt_nur_den_neuen_tag(self):
        self.schreibe("spots.yaml", "- id: b\n")
        self.schreibe("neu.md", "Hallo\n")
        r = self.veroeffentlichen("--version", "1.0.1", "Test", eingabe="ja\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("neu.md", r.stdout)
        self.assertEqual(sorted(self.git("show", "--name-only", "--format=", "HEAD").split()),
                         ["neu.md", "spots.yaml", "wingscout/__init__.py"])
        oben = self.git("ls-remote", str(self.remote))
        self.assertIn(self.git("rev-parse", "HEAD").strip(), oben)
        self.assertIn("refs/tags/v1.0.1", oben)
        self.assertNotIn("v0.9.0-alt", oben)

    def test_ohne_ja_kommt_nichts_neues_mit(self):
        self.schreibe("spots.yaml", "- id: b\n")
        self.schreibe("notizen.txt", "privat\n")
        r = self.veroeffentlichen("Test", eingabe="\n")                   # Enter: abbrechen
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(self.commits(), 1)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")
        r = self.veroeffentlichen("Test", eingabe="nein\n")               # nein: ohne sie weiter
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD").split(), ["spots.yaml"])
        self.assertIn("?? notizen.txt", self.git("status", "--short"))

    def test_verbotene_datei_wird_abgelehnt(self):
        self.schreibe("config Kopie.yaml", "rider: {}\n")
        self.git("add", "-f", "config Kopie.yaml")                         # an .gitignore vorbei
        r = self.veroeffentlichen("Test")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("config Kopie.yaml", r.stdout)
        self.assertEqual(self.commits(), 1)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")
        self.assertTrue((self.repo / "config Kopie.yaml").exists())

    def test_heimatkoordinate_wird_abgelehnt(self):
        self.schreibe("spots.yaml", "- id: b\n  lat: 12.34\n  lon: 56.789\n")
        r = self.veroeffentlichen("Test")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("spots.yaml, Zeile 2", r.stdout)
        self.assertEqual(self.commits(), 1)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")

    def test_ohne_noreply_adresse_geschieht_nichts(self):
        self.git("config", "user.email", "jemand@example.com")
        self.schreibe("spots.yaml", "- id: b\n")
        r = self.veroeffentlichen("--version", "1.0.1", "Test")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("users.noreply.github.com", r.stdout)
        self.assertIn('git config user.email "<id>+DarkPirateGo', r.stdout)  # eigene Angabe im Repository
        self.assertEqual(self.commits(), 1)
        self.assertIn('"1.0.0"', (self.repo / "wingscout" / "__init__.py").read_text(encoding="utf-8"))

    def test_versionsangabe_wird_geprueft(self):
        for args, meldung in ((["--version"], "braucht eine Nummer"),
                              (["--version", "1.2"], "X.Y.Z"),
                              (["--version", "1.0.1", "eins", "zwei"], "Zu viele Angaben"),
                              (["--tags"], "Unbekannte Angabe")):
            with self.subTest(args):
                r = self.veroeffentlichen(*args)
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn(meldung, r.stdout)

    # ── Nachprüfung der Korrekturen, 04.10.2026 ──────────────────────────────

    def assertNichtsGeschehen(self, r, vorher: str, commits: int = 1):
        """Abgelehnt — kein Commit, nichts vorgemerkt, nichts hochgeladen, kein Tag."""
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.commits(), commits, r.stdout)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")
        self.assertEqual(self.oben(), vorher, "nichts hochgeladen")
        self.assertEqual(self.git("tag", "-l", "v1.0.1"), "")

    def test_author_und_committer_email_gelten_vor_user_email(self):
        """D4: user.email war anonym, aber author.email oder committer.email
        setzte eine private Adresse — Commit, Tag und Push gingen damit durch."""
        vorher = self.oben()
        for schluessel, ort, befehl in (("author.email", "--local", "git config --unset author.email"),
                                        ("committer.email", "--local", "git config --unset committer.email"),
                                        ("committer.email", "--global", "git config --global --unset committer.email")):
            with self.subTest(schluessel=schluessel, ort=ort):
                self.git("config", ort, schluessel, "privat@example.de")
                self.schreibe("spots.yaml", "- id: b\n")
                r = self.veroeffentlichen("--version", "1.0.1", "Test")
                self.git("config", ort, "--unset", schluessel)
                self.assertNichtsGeschehen(r, vorher)
                self.assertIn("privat@example.de", r.stdout)
                self.assertIn(befehl, r.stdout)
                self.assertIn('"1.0.0"', (self.repo / "wingscout" / "__init__.py").read_text(encoding="utf-8"))

    def test_umgebungsvariablen_gelten_vor_allem(self):
        """D4: GIT_AUTHOR_EMAIL, GIT_COMMITTER_EMAIL — und EMAIL, wenn user.email fehlt."""
        vorher = self.oben()
        self.schreibe("spots.yaml", "- id: b\n")
        for name in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
            with self.subTest(name):
                r = self.veroeffentlichen("Test", env={name: "privat@example.de"})
                self.assertNichtsGeschehen(r, vorher)
                self.assertIn(f"unset {name}", r.stdout)
        self.git("config", "--unset", "user.email")
        r = self.veroeffentlichen("Test", env={"EMAIL": "privat@example.de"})
        self.assertNichtsGeschehen(r, vorher)
        self.assertIn("privat@example.de", r.stdout)
        self.assertIn('git config --global user.email "<id>+DarkPirateGo', r.stdout)
        # Eine anonyme Adresse mit einer privaten darin geht auch nicht durch
        r = self.veroeffentlichen("Test", env={"GIT_AUTHOR_EMAIL": "a<privat@example.de>@users.noreply.github.com",
                                              "GIT_COMMITTER_EMAIL": "1+test@users.noreply.github.com"})
        self.assertNichtsGeschehen(r, vorher)

    def test_frueherer_commit_mit_privater_adresse(self):
        """D4: ein Commit, der noch nicht oben war, ging ungeprüft mit hoch —
        auch ohne neue Änderungen (»noch nicht gepushte Commits«)."""
        vorher = self.oben()
        self.schreibe("spots.yaml", "- id: b\n")
        self.git("-c", "user.email=privat@example.de", "commit", "-qam", "Von Hand")
        r = self.veroeffentlichen()                                       # keine neuen Änderungen
        self.assertNichtsGeschehen(r, vorher, commits=2)
        self.assertIn("Von Hand", r.stdout)
        self.assertIn("privat@example.de", r.stdout)
        self.assertIn("Es ist nur der letzte Commit", r.stdout)
        self.assertIn("git commit --amend --reset-author --no-edit", r.stdout)
        self.schreibe("CHANGELOG.md", "## 1.0.1 — Test\n\nMehr.\n")
        r = self.veroeffentlichen("Test")                                 # mit neuen Änderungen
        self.assertNichtsGeschehen(r, vorher, commits=2)
        self.assertIn("Von Hand", r.stdout)
        # So wie die Meldung es sagt: neu festschreiben, dann geht alles durch
        self.git("commit", "-q", "--amend", "--reset-author", "--no-edit")
        r = self.veroeffentlichen("Test")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(self.git("rev-parse", "HEAD").strip(), self.oben())
        self.assertEqual(self.oben_adressen(), {"1+test@users.noreply.github.com"})
        # Liegt der private Commit weiter zurück, hilft --amend nicht
        vorher = self.oben()
        self.schreibe("spots.yaml", "- id: c\n")
        self.git("-c", "user.email=privat@example.de", "commit", "-qam", "Wieder von Hand")
        self.schreibe("spots.yaml", "- id: d\n")
        self.git("commit", "-qam", "Danach")
        r = self.veroeffentlichen()
        self.assertNichtsGeschehen(r, vorher, commits=5)
        self.assertIn("Wieder von Hand", r.stdout)
        self.assertNotIn("Danach", r.stdout)
        self.assertIn("um Hilfe fragen", r.stdout)

    def test_frueherer_commit_mit_verbotener_datei_oder_heimat(self):
        """Was ein früherer Commit hinzufügt, steht in der Historie, auch wenn
        ein späterer es wieder entfernt — der Push nähme es mit."""
        vorher = self.oben()
        self.schreibe("config Kopie.yaml", "rider: {}\n")
        self.git("add", "-f", "config Kopie.yaml")
        self.git("commit", "-qm", "Kopie aus Versehen")
        self.git("rm", "-q", "--cached", "config Kopie.yaml")
        self.git("commit", "-qm", "Wieder raus")
        r = self.veroeffentlichen()
        self.assertNichtsGeschehen(r, vorher, commits=3)
        self.assertIn("config Kopie.yaml", r.stdout)
        self.git("reset", "-q", "--hard", "HEAD~2")
        self.schreibe("spots.yaml", "- id: b\n  lat: 12.34\n  lon: 56.789\n")
        self.git("commit", "-qam", "Mit Heimat")
        self.schreibe("spots.yaml", "- id: b\n")
        self.git("commit", "-qam", "Ohne Heimat")
        r = self.veroeffentlichen()
        self.assertNichtsGeschehen(r, vorher, commits=3)
        self.assertIn("spots.yaml, Zeile 2", r.stdout)

    def test_umbenennung_in_takeout(self):
        """D1: »mv import/jensdee_pins.yaml takeout/« und »ja« — Git meldet das
        als Umbenennung, und das Skript sah nur neu angelegte Dateien. Klein
        geschrieben: .gitignore kennt Takeout/, und wo Groß und klein zählen
        (Linux; hier auch auf dem Mac), ist takeout/ nicht ignoriert."""
        self.git("config", "core.ignorecase", "false")
        (self.repo / "import").mkdir()
        self.schreibe("import/jensdee_pins.yaml", "pins: []\n")
        self.git("add", "import/jensdee_pins.yaml")
        self.git("commit", "-qm", "Pins")
        self.git("push", "-q", "origin", "HEAD")
        vorher = self.oben()
        (self.repo / "takeout").mkdir()
        (self.repo / "import" / "jensdee_pins.yaml").rename(self.repo / "takeout" / "jensdee_pins.yaml")
        r = self.veroeffentlichen("Test", eingabe="ja\n")
        self.assertNichtsGeschehen(r, vorher, commits=2)
        self.assertIn("takeout/jensdee_pins.yaml", r.stdout)
        self.assertTrue((self.repo / "takeout" / "jensdee_pins.yaml").exists(), "auf dem Mac bleibt sie")
        # Dasselbe schon vorgemerkt (git mv), ganz ohne Frage
        (self.repo / "takeout" / "jensdee_pins.yaml").unlink()
        self.git("checkout", "--", "import/jensdee_pins.yaml")
        self.git("mv", "import/jensdee_pins.yaml", "takeout/pins.yaml")
        r = self.veroeffentlichen("Test")
        self.assertNichtsGeschehen(r, vorher, commits=2)
        self.assertIn("takeout/pins.yaml", r.stdout)

    def test_name_in_anfuehrungszeichen(self):
        """Ohne -z schreibt Git  takeout/Saved "Places".json  als
        "takeout/Saved \\"Places\\".json" — das Muster für takeout/ griff nicht."""
        vorher = self.oben()
        (self.repo / "takeout").mkdir()
        self.schreibe('takeout/Saved "Places".json', "{}\n")
        self.git("add", "-f", 'takeout/Saved "Places".json')
        r = self.veroeffentlichen("Test")
        self.assertNichtsGeschehen(r, vorher)
        self.assertIn('takeout/Saved "Places".json', r.stdout)

    def test_heimat_auch_mit_eigenen_diff_einstellungen(self):
        """Mit diff.noprefix oder diff.mnemonicPrefix fehlt die Vorsilbe b/ im
        Diff — die Suche nach der Heimatkoordinate übersprang jede Datei."""
        vorher = self.oben()
        self.schreibe("spots.yaml", "- id: b\n  lat: 12.34\n  lon: 56.789\n")
        for einstellung in ("diff.noprefix", "diff.mnemonicPrefix"):
            with self.subTest(einstellung):
                self.git("config", einstellung, "true")
                r = self.veroeffentlichen("Test")
                self.assertNichtsGeschehen(r, vorher)
                self.assertIn("spots.yaml, Zeile 2", r.stdout)
                # ein Commit von Hand: dieselbe Suche vor dem Push
                self.git("commit", "-qam", "Von Hand")
                r = self.veroeffentlichen()
                self.assertNichtsGeschehen(r, vorher, commits=2)
                self.assertIn("spots.yaml, Zeile 2", r.stdout)
                self.git("reset", "-q", "--soft", "HEAD~1")
                self.git("reset", "-q")
                self.git("config", "--unset", einstellung)

    def test_push_followtags_schiebt_keinen_alten_tag_mit(self):
        """D7: mit push.followTags in der eigenen Git-Einstellung nahm der Push
        jeden älteren annotierten Tag mit, der auf den Zweig zeigt."""
        self.git("config", "push.followTags", "true")
        self.schreibe("spots.yaml", "- id: b\n")
        r = self.veroeffentlichen("--version", "1.0.1", "Test")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.schreibe("spots.yaml", "- id: c\n")
        r = self.veroeffentlichen("Test")                                 # ohne Tag: nur der Zweig
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        oben = self.oben()
        self.assertIn(self.git("rev-parse", "HEAD").strip(), oben)
        self.assertIn("refs/tags/v1.0.1", oben)
        self.assertNotIn("v0.9.0-alt", oben)

    def test_erster_push_prueft_die_ganze_historie(self):
        """Ohne Upstream und ohne Stand von origin (erster Push) zählt jeder
        Commit. Bis 2.1.1 hieß es dann »alles ist schon oben« — ohne Push."""
        leer = self.tmp / "leer.git"
        self.git("init", "-q", "--bare", str(leer), cwd=self.tmp)
        self.git("remote", "set-url", "origin", str(leer))
        self.git("branch", "--unset-upstream")
        self.git("update-ref", "-d", f"refs/remotes/origin/{self.zweig()}")
        self.git("-c", "user.email=privat@example.de", "commit", "--allow-empty", "-qm", "Alt und privat")
        r = self.veroeffentlichen()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("Alt und privat", r.stdout)
        self.assertIn("git fetch origin", r.stdout)
        self.assertEqual(self.oben(leer), "")
        self.git("reset", "-q", "--hard", "HEAD~1")
        r = self.veroeffentlichen()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("noch nicht gepushte Commits", r.stdout)
        self.assertIn(self.git("rev-parse", "HEAD").strip(), self.oben(leer))
        self.assertNotIn("v0.9.0-alt", self.oben(leer))

    def test_letzte_pruefung_vor_dem_push(self):
        """Auch was das Skript selbst festschreibt, wird vor dem Push geprüft:
        nach einem Cherry-Pick mit Konflikt übernimmt `git commit` den Autor
        des fremden Commits — obwohl die eigene Adresse stimmt."""
        zweig = self.zweig()
        self.git("checkout", "-q", "-b", "fremd")
        self.schreibe("spots.yaml", "- id: fremd\n")
        self.git("-c", "user.email=privat@example.de", "commit", "-qam", "Fremder Stand")
        self.git("checkout", "-q", zweig)
        self.schreibe("spots.yaml", "- id: eigen\n")
        self.git("commit", "-qam", "Eigen")
        self.git("push", "-q", "origin", zweig)
        vorher = self.oben()
        pick = subprocess.run(["git", "cherry-pick", "fremd"], cwd=self.repo, env=self.env, capture_output=True)
        self.assertNotEqual(pick.returncode, 0, "der Konflikt gehört zum Test")
        self.schreibe("spots.yaml", "- id: beide\n")
        r = self.veroeffentlichen("--version", "1.0.1", "Auflösung")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("Festgeschrieben", r.stdout)
        self.assertIn("privat@example.de", r.stdout)
        self.assertIn("git commit --amend --reset-author --no-edit", r.stdout)
        self.assertEqual(self.oben(), vorher, "nichts hochgeladen")
        self.assertEqual(self.git("tag", "-l", "v1.0.1"), "", "der Tag ist wieder weg — der nächste Lauf setzt ihn neu")
        self.git("commit", "-q", "--amend", "--reset-author", "--no-edit")
        r = self.veroeffentlichen("--version", "1.0.1", "Auflösung")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("refs/tags/v1.0.1", self.oben())
        self.assertEqual(self.oben_adressen(), {"1+test@users.noreply.github.com"})


if __name__ == "__main__":
    unittest.main()
