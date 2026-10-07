"""Sprachen der Oberfläche (seit 2.1.0): Kataloge, Mechanik, Seiten in allen vier Sprachen.

Drei Teile, die verschiedene Fragen beantworten:

1. Die Kataloge (`wingscout/lang/*.json`): kennt jede Sprache jeden Text aus
   dem Code, und behält jede Übersetzung Platzhalter, Auszeichnung und Ränder
   des deutschen Texts? Dieselben Regeln, mit denen die Übersetzungen
   entstanden sind — hier stehen sie fest.
2. Die Mechanik (`wingscout/i18n.py`) mit kleinen Katalogen in einem
   Temporärordner: welche Sprache gilt, wann es beim Deutschen bleibt, Datum,
   der Vorspann für JavaScript — unabhängig davon, was in den echten steht.
3. Jede Seite und der Report in jeder Sprache: Sprache im `<html>`, der
   Umschalter, keine unaufgelösten Platzhalter. Das muss auch gelten, solange
   ein Katalog Lücken hat.

Nichts hier ändert etwas dauerhaft: die gespeicherte Wahl (`sprache.txt`)
liegt im Test immer in einem Temporärordner, und nach jedem Test gilt wieder
Deutsch — wie für alle anderen Tests (`tests/__init__.py`).
"""
from __future__ import annotations

import collections
import contextlib
import difflib
import html
import importlib.util
import inspect
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import yaml

from tests.helpers import CONFIG, ROOT, SPOTS, cfg as load_cfg
import wingscout
import wingscout.webui as w
from wingscout import cli, geo, i18n, rueckblick, tagebuch
from wingscout.config import KonfigFehler
from wingscout.spots import KatalogFehler, load_spots

FREMDSPRACHEN = [s for s in i18n.SPRACHEN if s != i18n.QUELLE]
PLATZ = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
TAG = re.compile(r"<\s*(/?)\s*([A-Za-z][A-Za-z0-9]*)((?:[^>'\"]|'[^']*'|\"[^\"]*\")*)>")
ATTR = re.compile(r"""([A-Za-z_:][-A-Za-z0-9_:.]*)\s*(?:=\s*('[^']*'|"[^"]*"|[^\s'">]+))?""")
UEBERSETZBAR = {"title", "alt", "aria-label", "placeholder"}       # Werte dieser Attribute sind Text
KOMPASS = geo.KOMPASS            # „N NNO NO …“ — geo.compass() teilt die Übersetzung in 16 Kürzel
SAMSTAG = {"de": "Sa 03.10.", "en": "Sat 3 Oct", "fr": "sam. 3 oct.", "es": "sáb 3 oct"}    # 3. Oktober 2026
NODE = shutil.which("node")
ZEIGEN = 20                       # so viele Funde nennt eine Fehlermeldung


# ── Gemeinsames ─────────────────────────────────────────────────────────────

_QUELLE: dict = {}


def quelltexte() -> dict:
    """Alle übersetzbaren Texte aus dem Code (Text → Fundstellen), wie
    `tools/i18n_texte.py` sie einsammelt — einmal je Prüflauf."""
    if "texte" not in _QUELLE:
        spec = importlib.util.spec_from_file_location("i18n_texte", ROOT / "tools" / "i18n_texte.py")
        modul = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modul)
        _QUELLE["texte"] = modul.alle_texte()
    return _QUELLE["texte"]


def platzhalter_namen() -> set:
    return {n for text in quelltexte() for n in PLATZ.findall(text)}


def auszeichnung(text: str) -> collections.Counter:
    """Die HTML-Tags eines Texts samt Attributen — die Werte von title, alt,
    aria-label und placeholder zählen nicht, die sind selbst Text."""
    aus = collections.Counter()
    for zu, name, rest in TAG.findall(text):
        attrs = []
        for attr, wert in ATTR.findall(rest):
            attr = attr.lower()
            attrs.append((attr, "…" if attr in UEBERSETZBAR else wert))
        aus[(zu, name.lower(), tuple(sorted(attrs)))] += 1
    return aus


def raender(text: str) -> tuple:
    return text[:len(text) - len(text.lstrip())], text[len(text.rstrip()):]


def liste(funde: list) -> str:
    rest = f"\n  … und {len(funde) - ZEIGEN} weitere" if len(funde) > ZEIGEN else ""
    return "\n".join("  " + f for f in funde[:ZEIGEN]) + rest


def keine_funde(test: unittest.TestCase, funde: list, kopf: str) -> None:
    """Scheitern mit einer lesbaren Liste — nicht mit dem repr aller Funde."""
    if funde:
        test.fail(f"{kopf}\n{liste(funde)}")


# Platzhalter, die so heißen wie ein Parameter von t() — `t("… {text}", text=…)`
# ginge nicht. `{text}` steht in zwei Skripttexten (web/suche.js); dort setzt
# das t() aus dem Vorspann ein, Python nie.
PARAMETER_VON_T = {name for name, p in inspect.signature(i18n.t).parameters.items()
                   if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)}


def t_mit(text: str, werte: dict) -> str:
    """`i18n.t(text, **werte)` — auch wenn ein Platzhalter mit einem Parameter
    von t() zusammenfällt: dann die Übersetzung über t() holen und mit
    derselben Rückfallregel einsetzen."""
    if not set(werte) & PARAMETER_VON_T:
        return i18n.t(text, **werte)
    roh = i18n.t(text)
    try:
        return roh.format(**werte)
    except (KeyError, IndexError, ValueError):
        return text.format(**werte)


def zuruecksetzen() -> None:
    """Wie vor dem Test: Kataloge frisch von der Platte, Deutsch im Thread."""
    i18n.neu_laden()
    i18n.setze(i18n.QUELLE)


def node_json(test: unittest.TestCase, code: str):
    """`code` in Node ausführen; was es auf stdout schreibt, als JSON."""
    if not NODE:
        test.skipTest("node fehlt")
    aus = subprocess.run([NODE, "-"], input=code, capture_output=True, text=True,
                         encoding="utf-8", timeout=30)
    test.assertEqual(aus.returncode, 0, aus.stderr[-2000:])
    return json.loads(aus.stdout)


@contextlib.contextmanager
def chromium(test: unittest.TestCase):
    """Eine Seite in Chromium (Playwright): (Seite, Fehler der Seite). Sie
    erreicht nur diesen Rechner — Leaflet von cdnjs und die Kacheln von
    OpenStreetMap werden abgewiesen, die Seiten zeichnen ohne Karte weiter.
    Ohne Playwright oder ohne startbares Chromium: übersprungen; installiert
    wird hier nichts (kein `playwright install`)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        test.skipTest("Playwright fehlt")
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as exc:                          # noqa: BLE001 — kein Browser, kein Test
            test.skipTest(f"Chromium startet nicht: {str(exc).splitlines()[0][:120]}")
        try:
            seite = browser.new_page()
            fehler: list = []
            seite.on("pageerror", lambda exc: fehler.append(str(exc)))
            seite.route("**/*", lambda route: route.continue_()
                        if route.request.url.startswith(("http://127.0.0.1:", "file:")) else route.abort())
            yield seite, fehler
        finally:
            browser.close()


def vorspann_teile(vorspann: str) -> tuple:
    """(window.T, window.I18N) aus dem Vorspann gelesen."""
    m = re.match(r"window\.T=(.*?);window\.I18N=(\{.*?\});window\.t = ", vorspann, re.S)
    if not m:
        raise AssertionError("Vorspann hat nicht die Form window.T=…;window.I18N=…;window.t = …")
    return json.loads(m.group(1)), json.loads(m.group(2))


def roh_im_vorspann(vorspann: str) -> list:
    """Zeichen, die in den Daten des Vorspanns (window.T, window.I18N) nur als
    Escape stehen dürfen: `<`, `>`, `&` — sonst kann ein Text darin Markup
    werden (`<!--<script`) — und U+2028/U+2029, die ältere Engines in einer
    Zeichenkette als Zeilenende lesen."""
    m = re.match(r"(window\.T=.*?;window\.I18N=\{.*?\});window\.t = ", vorspann, re.S)
    if not m:
        raise AssertionError("Vorspann hat nicht die Form window.T=…;window.I18N=…;window.t = …")
    daten = m.group(1)
    return [f"{zeichen!r} {daten.count(zeichen)}×" for zeichen in "<>&  " if zeichen in daten]


def offene_platzhalter(html_text: str) -> list:
    """`{n}`, `{name}` … im sichtbaren Teil einer Seite — ohne <script> und
    <style>, und nur Namen, die ein Text im Code als Platzhalter benutzt."""
    sichtbar = re.sub(r"<(script|style)\b[^>]*>.*?</\1\s*>", " ", html_text, flags=re.S | re.I)
    namen = platzhalter_namen()
    return [f"{m.group(0)} in …{sichtbar[max(0, m.start() - 60):m.end() + 60]}…".replace("\n", " ")
            for m in PLATZ.finditer(sichtbar) if m.group(1) in namen]


def pruefe_seite(test: unittest.TestCase, html_text: str, sprache: str, umschalter: bool = True) -> None:
    """Sprache im <html> und im Vorspann, der Umschalter mit der Sprache der
    Seite gewählt, keine unaufgelösten Platzhalter."""
    m = re.search(r"<html lang='([^']*)'", html_text)
    test.assertIsNotNone(m, "kein <html lang='…'>")
    test.assertEqual(m.group(1), sprache, "Sprache im <html>")
    m = re.search(r"window\.I18N=(\{.*?\});", html_text)
    test.assertIsNotNone(m, "kein Vorspann für die Skripte (window.I18N)")
    test.assertEqual(json.loads(m.group(1))["sprache"], sprache, "Sprache des Vorspanns")
    if umschalter:
        waehler = re.findall(r"<select class='sprachwahl'[^>]*>(.*?)</select>", html_text, re.S)
        test.assertTrue(waehler, "kein Sprachumschalter")
        for inhalt in waehler:
            optionen = re.findall(r"<option value='([^']*)'([^>]*)>", inhalt)
            test.assertEqual([wert for wert, _ in optionen], list(i18n.SPRACHEN))
            test.assertEqual([wert for wert, rest in optionen if re.search(r"\sselected\b", rest)],
                             [sprache], "im Umschalter gewählt ist die Sprache der Seite")
    keine_funde(test, offene_platzhalter(html_text), "unaufgelöste Platzhalter im sichtbaren Text:")


# Ein kleiner Katalog für die Seiten: je einer unbrauchbar, fragwürdig und
# unbestätigt (die Prüfseite zeigt alle drei Stufen), einer ohne Geometrie
# („fehlt sie noch“) — und schnell gelesen, anders als die 278 Spots.
KLEINE_SPOTS = [
    {"id": "alpha", "name": "Alpha <b>See</b>", "country": "DE", "lat": 49.5, "lon": 8.7, "water_body": "lake",
     "verified": True, "notes": "Notiz & mehr", "comment": "Parken am Ende", "sectors": []},
    {"id": "beta", "name": "Beta", "country": "NL", "lat": 51.76, "lon": 3.85, "water_body": "sea",
     "verified": True, "sectors": []},
    {"id": "gamma", "name": "Gamma", "country": "FR", "lat": 47.5, "lon": -3.1, "water_body": "lagoon",
     "verified": True, "sectors": []},
    {"id": "delta", "name": "Delta", "country": "AT", "lat": 47.8, "lon": 13.3, "water_body": "reservoir",
     "verified": False, "sectors": []},
]
KLEINE_GEOMETRIE = {"alpha": {"max_fetch_km": 5.0, "origin_offset_m": [0, 0]},
                    "beta": {"max_fetch_km": 0.1, "origin_offset_m": [0, 0]},       # kaum Wasser
                    "gamma": {"max_fetch_km": 4.0, "origin_offset_m": [2500, 0]}}   # weit versetzt


def kleiner_katalog(ordner: Path) -> tuple:
    sp, geo = ordner / "spots.yaml", ordner / "geometry.json"
    sp.write_text(yaml.safe_dump(KLEINE_SPOTS, allow_unicode=True, sort_keys=False), encoding="utf-8")
    geo.write_text(json.dumps(KLEINE_GEOMETRIE), encoding="utf-8")
    return sp, geo


def ersetze(ziel, name: str, wert, aufraeumen) -> None:
    """`ziel.name` für die Dauer des Tests (oder der Klasse) ersetzen."""
    p = mock.patch.object(ziel, name, wert)
    p.start()
    aufraeumen(p.stop)


def pruefzahl_zurueck(aufraeumen) -> None:
    """`webui._PRUEF_ZAHL` merkt sich den Stand der Katalogdateien — danach
    wieder der von vorher."""
    alt = dict(w._PRUEF_ZAHL)

    def zurueck():
        w._PRUEF_ZAHL.clear()
        w._PRUEF_ZAHL.update(alt)
    aufraeumen(zurueck)


# ── 1. Die Kataloge ─────────────────────────────────────────────────────────

class Kataloge(unittest.TestCase):
    """Die echten Kataloge in wingscout/lang/ gegen die Texte im Code."""

    @classmethod
    def setUpClass(cls):
        cls.texte = quelltexte()

    def setUp(self):
        self.addCleanup(zuruecksetzen)

    def katalog(self, sprache: str) -> dict:
        datei = i18n.LANG / f"{sprache}.json"
        try:
            daten = json.loads(datei.read_bytes().decode("utf-8"))
        except (OSError, ValueError) as exc:
            self.fail(f"{datei.name} nicht lesbar: {exc}")
        if not isinstance(daten, dict):
            self.fail(f"{datei.name}: oben muss ein JSON-Objekt stehen, nicht {type(daten).__name__}")
        return daten

    def eintraege(self, sprache: str):
        """(deutsch, übersetzt) — nur Texte, die es im Code gibt, und nur
        ausgefüllte; was fehlt oder übrig ist, melden eigene Tests."""
        for k, v in self.katalog(sprache).items():
            if k in self.texte and isinstance(v, str) and v.strip():
                yield k, v

    def test_texte_gefunden(self):
        """Ohne Texte wäre jede Vollständigkeit geschenkt."""
        stellen = [s for orte in self.texte.values() for s in orte]
        self.assertTrue(any(s.endswith(".js") for s in stellen), "kein Text aus wingscout/web/*.js")
        self.assertTrue(any(".py:" in s for s in stellen), "kein Text aus dem Python-Code")
        self.assertLessEqual(i18n.js_schluessel(), set(self.texte),
                             "der Vorspann sucht Texte, die das Einsammeln nicht kennt")

    def test_quelltexte_haben_nur_benannte_platzhalter(self):
        """Der deutsche Text selbst: nur `{name}`, keine freien Klammern — sonst
        stolpert `str.format` schon auf Deutsch, und keine Übersetzung kann die
        Regeln unten erfüllen."""
        fehler = []
        for k in self.texte:
            if "{" in PLATZ.sub("", k) or "}" in PLATZ.sub("", k):
                fehler.append(f"{k!r} ({self.texte[k][0]})")
                continue
            try:
                k.format(**{n: "x" for n in PLATZ.findall(k)})
            except (KeyError, IndexError, ValueError, AttributeError, TypeError) as exc:
                fehler.append(f"{k!r} ({self.texte[k][0]}): {type(exc).__name__} {exc}")
        keine_funde(self, fehler, "Quelltexte mit Klammern, die kein Platzhalter sind:")

    def test_jeder_text_ist_uebersetzt(self):
        for sprache in FREMDSPRACHEN:
            with self.subTest(sprache=sprache):
                kat = self.katalog(sprache)
                fehlend = [k for k in self.texte if not (isinstance(kat.get(k), str) and kat[k].strip())]
                keine_funde(self, [f"{k!r}  ({self.texte[k][0]})" for k in fehlend],
                            f"{sprache}: {len(fehlend)} von {len(self.texte)} Texten fehlen oder sind leer "
                            f"(alle: python3 tools/i18n_texte.py --fehlend {sprache}):")

    def test_keine_eintraege_ohne_text_im_code(self):
        for sprache in FREMDSPRACHEN:
            with self.subTest(sprache=sprache):
                uebrig = sorted(k for k in self.katalog(sprache) if k not in self.texte)
                keine_funde(self, [repr(k) for k in uebrig],
                            f"{sprache}: {len(uebrig)} Einträge ohne Text im Code (umbenannt oder entfernt?):")

    def test_dieselben_platzhalter(self):
        for sprache in FREMDSPRACHEN:
            with self.subTest(sprache=sprache):
                fehler = [f"{k!r}\n    → {v!r}" for k, v in self.eintraege(sprache)
                          if set(PLATZ.findall(k)) != set(PLATZ.findall(v))]
                keine_funde(self, fehler, f"{sprache}: Platzhalter weichen ab:")

    def test_keine_freien_klammern(self):
        """Eine Klammer, die kein Platzhalter ist, bricht `str.format` — die
        Zeile fiele aufs Deutsche zurück."""
        for sprache in FREMDSPRACHEN:
            with self.subTest(sprache=sprache):
                fehler = []
                for k, v in self.eintraege(sprache):
                    rest_k, rest_v = PLATZ.sub("", k), PLATZ.sub("", v)
                    if ("{" in rest_v or "}" in rest_v) and not ("{" in rest_k or "}" in rest_k):
                        fehler.append(f"{k!r}\n    → {v!r}")
                keine_funde(self, fehler, f"{sprache}: freie Klammern:")

    def test_dieselbe_auszeichnung(self):
        for sprache in FREMDSPRACHEN:
            with self.subTest(sprache=sprache):
                fehler = [f"{k!r}\n    → {v!r}" for k, v in self.eintraege(sprache)
                          if auszeichnung(k) != auszeichnung(v)]
                keine_funde(self, fehler, f"{sprache}: HTML-Tags oder Attribute weichen ab:")

    def test_keine_zusaetzlichen_anfuehrungszeichen_oder_spitzen_klammern(self):
        """Neben den Tags (gleich wie im Deutschen, siehe oben) kein `"`, `<`
        oder `>` mehr als im deutschen Text — die zweite Sicherung hinter dem
        Escaping: ein Text, der doch einmal roh in einem Attribut landet, kann
        es dann nicht sprengen (B2: bis 2.1.0 standen die Zelltitel des
        Stundenrasters roh in title="…"). Typografische Anführungszeichen („“
        «» “”) gehen immer."""
        for sprache in FREMDSPRACHEN:
            with self.subTest(sprache=sprache):
                fehler = []
                for k, v in self.eintraege(sprache):
                    rest_k, rest_v = TAG.sub("", k), TAG.sub("", v)
                    for zeichen in '"<>':
                        if rest_v.count(zeichen) > rest_k.count(zeichen):
                            fehler.append(f"{k!r}\n    → {v!r}: {zeichen} {rest_v.count(zeichen)}× "
                                          f"statt {rest_k.count(zeichen)}×")
                keine_funde(self, fehler, f"{sprache}: mehr \" < > als im deutschen Text:")

    def test_dieselben_raender(self):
        for sprache in FREMDSPRACHEN:
            with self.subTest(sprache=sprache):
                fehler = [f"{k!r}\n    → {v!r}" for k, v in self.eintraege(sprache) if raender(k) != raender(v)]
                keine_funde(self, fehler, f"{sprache}: Leerraum am Anfang oder Ende weicht ab:")

    def test_kompassrose_behaelt_16_kuerzel(self):
        """geo.compass() teilt die Übersetzung an Leerzeichen und braucht 16 Kürzel."""
        self.assertEqual(len(KOMPASS.split()), 16)
        self.assertIn(KOMPASS, self.texte, "die Kompassrose muss eingesammelt werden (N_ in geo.py)")
        for sprache in FREMDSPRACHEN:
            with self.subTest(sprache=sprache):
                v = dict(self.eintraege(sprache)).get(KOMPASS)
                if v is not None:
                    self.assertEqual(len(v.split()), 16, f"{sprache}: {v!r}")

    def test_dateien_sind_kanonisch(self):
        """Sortiert, eingerückt mit einem Leerzeichen, Umlaute als Umlaute, ein
        Zeilenende am Schluss — so bleiben die Diffs sauber, wer auch immer
        die Datei zuletzt geschrieben hat."""
        for sprache in FREMDSPRACHEN:
            with self.subTest(sprache=sprache):
                daten = self.katalog(sprache)
                datei = i18n.LANG / f"{sprache}.json"
                roh = datei.read_bytes().decode("utf-8")
                soll = json.dumps(daten, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
                if roh == soll:
                    continue
                unterschied = list(difflib.unified_diff(soll.splitlines(), roh.splitlines(), "kanonisch",
                                                        datei.name, n=0, lineterm=""))[:15]
                self.fail(f"{datei.name} ist nicht kanonisch geschrieben:\n"
                          + ("\n".join(unterschied) if unterschied else "  (nur Zeilenenden weichen ab)")
                          + "\nNeu schreiben: python3 -c \"import json,sys; p=sys.argv[1]; "
                            "d=json.load(open(p,encoding='utf-8')); open(p,'w',encoding='utf-8',newline='\\n')"
                            ".write(json.dumps(d,ensure_ascii=False,indent=1,sort_keys=True)+'\\n')\" "
                            f"wingscout/lang/{datei.name}")

    def test_jede_uebersetzung_laesst_sich_einsetzen(self):
        """Mit Werten für alle Platzhalter liefert `t()` die Übersetzung — und
        nicht still den deutschen Text, weil das Einsetzen scheiterte."""
        i18n.neu_laden()
        for sprache in FREMDSPRACHEN:
            with self.subTest(sprache=sprache):
                i18n.setze(sprache)
                fehler = []
                for k, v in self.eintraege(sprache):
                    werte = {n: f"«{n}»" for n in PLATZ.findall(k)}
                    try:
                        soll = v.format(**werte) if werte else v
                    except Exception as exc:                          # noqa: BLE001 — jeder Fehler ist ein Fund
                        fehler.append(f"{k!r}\n    → {v!r}: {type(exc).__name__} {exc}")
                        continue
                    ist = t_mit(k, werte)
                    if ist != soll:
                        fehler.append(f"{k!r}\n    → {ist!r} statt {soll!r}")
                keine_funde(self, fehler, f"{sprache}: Übersetzungen, die nicht ankommen:")


# ── 2. Mechanik, mit eigenen kleinen Katalogen ──────────────────────────────

class MitEigenenKatalogen(unittest.TestCase):
    """Kataloge und `sprache.txt` in einem Temporärordner, keine Sprache aus
    der Umgebung (`WINGSCOUT_SPRACHE`, `LC_ALL`, `LC_MESSAGES`, `LANG` sind
    weg — die Tests setzen, was sie brauchen). Danach ist alles wie vorher."""

    KATALOGE: dict = {}             # Sprache → Einträge, oder roher Dateiinhalt als Text
    SKRIPTE: dict | None = None     # Name → JavaScript für ein eigenes web/ (None: das echte)

    def setUp(self):
        self.addCleanup(zuruecksetzen)                # läuft als letztes, nach allen Rücknahmen
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        lang = self.tmp / "lang"
        lang.mkdir()
        for sprache, eintraege in self.KATALOGE.items():
            inhalt = eintraege if isinstance(eintraege, str) else json.dumps(eintraege, ensure_ascii=False)
            (lang / f"{sprache}.json").write_text(inhalt, encoding="utf-8")
        ersetze(i18n, "LANG", lang, self.addCleanup)
        self.datei = self.tmp / "sprache.txt"
        ersetze(i18n, "SPRACH_DATEI", self.datei, self.addCleanup)
        if self.SKRIPTE is not None:
            web = self.tmp / "web"
            web.mkdir()
            for name, code in self.SKRIPTE.items():
                (web / name).write_text(code, encoding="utf-8")
            ersetze(i18n, "WEB", web, self.addCleanup)
        umgebung = mock.patch.dict(os.environ)
        umgebung.start()
        self.addCleanup(umgebung.stop)
        for name in ("WINGSCOUT_SPRACHE", "LC_ALL", "LC_MESSAGES", "LANG"):
            os.environ.pop(name, None)
        i18n.neu_laden()

    def merke(self, sprache: str) -> None:
        self.datei.write_text(sprache + "\n", encoding="utf-8")


class Sprachwahl(MitEigenenKatalogen):
    def test_kopfzeile_des_browsers(self):
        faelle = [
            ("de-CH,de;q=0.9,en;q=0.8", "de"),
            ("de-CH", "de"),                                   # Region fällt weg
            ("en-GB,en;q=0.9", "en"),
            ("es-419,es;q=0.8", "es"),
            ("fr-CA", "fr"),
            ("DE-AT", "de"),                                   # Groß und klein
            ("it-IT,it;q=0.9,fr;q=0.5,de;q=0.4", "fr"),        # unbekannte überspringen, dann nach Gewicht
            ("de;q=0.5,fr;q=0.8", "fr"),                       # Gewicht vor Reihenfolge
            ("de;q=0.5, fr", "fr"),                            # ohne q: 1
            ("fr,de", "fr"),                                   # gleiches Gewicht: Reihenfolge
            ("de,fr", "de"),
            ("es;q=0.7,en;q=0.7", "es"),
            (" fr ; q = 0.9 , es ; q=0.95 ", "es"),            # Leerzeichen
            ("fr;q=., es;q=0.1", "es"),                        # unlesbares Gewicht zählt 0
            ("de;q=0,fr;q=0.1", "fr"),                         # q=0 heißt „bitte nicht“
            ("de;q=0", None),
            (",,de,,", "de"),
            ("it-IT,it;q=0.9", None),
            ("pt-BR,pt;q=0.9,*;q=0.1", None),
            ("*", None),
            ("", None),
            (None, None),
        ]
        for kopf, erwartet in faelle:
            with self.subTest(kopf=kopf):
                self.assertEqual(i18n.aus_header(kopf), erwartet)

    def test_unsinn_in_der_kopfzeile_ist_kein_absturz(self):
        for kopf in (",", ";;;", "q=0.9", ";q=1", "de;q=", "de;q", "de;q=abc", "de;q=1.2.3", "q=;,;=q",
                     "\x00\x7f\x80", "ä" * 5000, "de" + ";q=0.5" * 1000, "x" * 100000 + ",fr"):
            with self.subTest(kopf=kopf[:30]):
                self.assertIn(i18n.aus_header(kopf), list(i18n.SPRACHEN) + [None])

    def test_anfrage_umgebung_vor_wahl_vor_browser(self):
        # Nichts gewählt: der Browser — und spricht er keine der vier, Englisch;
        # ohne Kopfzeile (kein Browser) Deutsch
        self.assertEqual(i18n.fuer_anfrage(None), "de")
        self.assertEqual(i18n.fuer_anfrage(""), "de")
        self.assertEqual(i18n.fuer_anfrage("it-IT,it;q=0.9"), "en")
        self.assertEqual(i18n.fuer_anfrage("*"), "en")
        self.assertEqual(i18n.fuer_anfrage("es-ES,es;q=0.9"), "es")
        self.assertEqual(i18n.aktuell(), "es", "die Sprache der Anfrage gilt danach im Thread")
        # Gewählt im Umschalter: schlägt den Browser
        self.merke("fr")
        self.assertEqual(i18n.fuer_anfrage("es-ES,es;q=0.9"), "fr")
        self.assertEqual(i18n.fuer_anfrage(None), "fr")
        self.assertEqual(i18n.aktuell(), "fr")
        self.datei.write_text(" EN \n", encoding="utf-8")
        self.assertEqual(i18n.fuer_anfrage("es"), "en")
        self.datei.write_text("klingonisch\n", encoding="utf-8")       # unbrauchbar: zählt nicht
        self.assertEqual(i18n.fuer_anfrage("es"), "es")
        # WINGSCOUT_SPRACHE schlägt alles
        self.merke("fr")
        os.environ["WINGSCOUT_SPRACHE"] = "es"
        self.assertEqual(i18n.fuer_anfrage("de-DE"), "es")
        os.environ["WINGSCOUT_SPRACHE"] = " DE "
        self.assertEqual(i18n.fuer_anfrage("es"), "de")
        os.environ["WINGSCOUT_SPRACHE"] = "xx"                         # unbekannt: zählt nicht
        self.assertEqual(i18n.fuer_anfrage("es"), "fr")

    def test_kommandozeile_umgebung_vor_schalter_vor_wahl_vor_system(self):
        # Keine Spur einer Sprache: Englisch, wie tools/sprache.sh — und der
        # Mac des Testlaufs darf mit seinen Einstellungen nicht hineinreden
        macos = mock.patch.object(i18n, "aus_macos", return_value=None)
        macos.start()
        self.addCleanup(macos.stop)
        self.assertEqual(i18n.fuer_kommandozeile(), "en")
        os.environ["LANG"] = "it_IT.UTF-8"
        self.assertEqual(i18n.fuer_kommandozeile(), "en")
        os.environ["LANG"] = "C.UTF-8"
        self.assertEqual(i18n.fuer_kommandozeile(), "en")
        with mock.patch.object(i18n, "aus_macos", return_value="es"):  # Systemeinstellung, wenn LANG nichts sagt
            self.assertEqual(i18n.fuer_kommandozeile(), "es")
        os.environ["LANG"] = "fr_FR.UTF-8"
        self.assertEqual(i18n.fuer_kommandozeile(), "fr")
        os.environ["LC_MESSAGES"] = "es_ES.UTF-8"                       # vor LANG
        self.assertEqual(i18n.fuer_kommandozeile(), "es")
        os.environ["LC_ALL"] = "en_US.UTF-8"                            # vor allen
        self.assertEqual(i18n.fuer_kommandozeile(), "en")
        self.merke("fr")                                                # die Wahl vor dem System
        self.assertEqual(i18n.fuer_kommandozeile(), "fr")
        self.assertEqual(i18n.fuer_kommandozeile(None), "fr")
        self.assertEqual(i18n.fuer_kommandozeile("es"), "es")           # --sprache vor der Wahl
        self.assertEqual(i18n.aktuell(), "es")
        self.assertEqual(i18n.fuer_kommandozeile("xx"), "fr")           # unbekannt: zählt nicht
        os.environ["WINGSCOUT_SPRACHE"] = "de"                          # die Umgebung vor allem
        self.assertEqual(i18n.fuer_kommandozeile("es"), "de")
        self.assertEqual(i18n.aktuell(), "de")

    def test_sprache_gilt_je_thread(self):
        i18n.setze("fr")
        gesehen = {}

        def anderer():
            gesehen["vorher"] = i18n.aktuell()          # nichts gesetzt, nichts gewählt: Deutsch
            i18n.setze("es")
            gesehen["nachher"] = i18n.aktuell()

        th = threading.Thread(target=anderer)
        th.start()
        th.join(5)
        self.assertEqual(gesehen, {"vorher": "de", "nachher": "es"})
        self.assertEqual(i18n.aktuell(), "fr", "ein anderer Thread ändert die eigene Sprache nicht")
        # Ein Thread ohne eigene Sprache nimmt die Umgebung, sonst die Wahl
        self.merke("en")
        os.environ["WINGSCOUT_SPRACHE"] = "es"
        ohne = {}
        th = threading.Thread(target=lambda: ohne.update(umgebung=i18n.aktuell()))
        th.start()
        th.join(5)
        del os.environ["WINGSCOUT_SPRACHE"]
        th = threading.Thread(target=lambda: ohne.update(wahl=i18n.aktuell()))
        th.start()
        th.join(5)
        self.assertEqual(ohne, {"umgebung": "es", "wahl": "en"})
        self.assertEqual(i18n.setze("xx"), "de")                        # unbekannt: Deutsch
        self.assertEqual(i18n.setze(None), "de")


class Uebersetzen(MitEigenenKatalogen):
    KATALOGE = {
        "fr": {"Spots suchen": "Chercher des spots",
               "Hallo {name}": "Bonjour {name}",
               "{n} Spot": "{n} spot (fr)", "{n} Spots": "{n} spots (fr)",
               "Meer": "Mer",
               "Kaputt {n}": "Cassé {m}",          # falscher Platzhalter
               "Offen {n}": "Ouvert {n",            # bricht str.format
               "Leer": "",
               "Keine Zeichenkette": 5},
        "en": {"Spots suchen": "Search spots"},
        "de": {"Spots suchen": "Das darf nie erscheinen"},   # Deutsch ist die Quelle — eine de.json zählt nicht
        "es": "{kaputt",                                     # kein JSON
    }

    def test_uebersetzt_und_setzt_ein(self):
        i18n.setze("fr")
        self.assertEqual(i18n.t("Spots suchen"), "Chercher des spots")
        self.assertEqual(i18n.t("Hallo {name}", name="Ana"), "Bonjour Ana")
        self.assertIs(i18n.T, i18n.t)
        i18n.setze("en")
        self.assertEqual(i18n.T("Spots suchen"), "Search spots")

    def test_was_fehlt_bleibt_deutsch(self):
        i18n.setze("fr")
        self.assertEqual(i18n.t("Nicht übersetzt"), "Nicht übersetzt")
        self.assertEqual(i18n.t("Nicht übersetzt {n}", n=2), "Nicht übersetzt 2")
        self.assertEqual(i18n.t("Leer"), "Leer")                          # leere Übersetzung: keine
        self.assertEqual(i18n.t("Keine Zeichenkette"), "Keine Zeichenkette")
        i18n.setze("en")
        self.assertEqual(i18n.t("Hallo {name}", name="Ana"), "Hallo Ana")
        i18n.setze("es")                                                  # kaputte Datei: kein Absturz
        self.assertEqual(i18n.t("Spots suchen"), "Spots suchen")
        self.assertEqual(i18n.t("Hallo {name}", name="Ana"), "Hallo Ana")
        i18n.setze("de")
        self.assertEqual(i18n.t("Spots suchen"), "Spots suchen")
        self.assertEqual(i18n.katalog("de"), {})
        self.assertEqual(i18n.katalog("xx"), {})

    def test_kaputte_uebersetzung_faellt_auf_deutsch(self):
        """Lieber Deutsch als eine kaputte Zeile."""
        i18n.setze("fr")
        self.assertEqual(i18n.t("Kaputt {n}", n=3), "Kaputt 3")
        self.assertEqual(i18n.t("Offen {n}", n=1), "Offen 1")

    def test_einzahl_und_mehrzahl(self):
        i18n.setze("fr")
        self.assertEqual(i18n.tn("{n} Spot", "{n} Spots", 1), "1 spot (fr)")
        self.assertEqual(i18n.tn("{n} Spot", "{n} Spots", 0), "0 spots (fr)")
        self.assertEqual(i18n.tn("{n} Spot", "{n} Spots", 2), "2 spots (fr)")
        self.assertEqual(i18n.TN("{n} Spot in {land}", "{n} Spots in {land}", 3, land="NL"), "3 Spots in NL")
        i18n.setze("de")
        self.assertEqual(i18n.tn("{n} Spot", "{n} Spots", 1), "1 Spot")
        self.assertEqual(i18n.tn("{n} Spot", "{n} Spots", 7), "7 Spots")

    def test_n_markiert_nur(self):
        i18n.setze("fr")
        text = "Meer"
        self.assertIs(i18n.N_(text), text)
        self.assertEqual(i18n.t(i18n.N_(text)), "Mer")          # übersetzt wird erst beim Gebrauch

    def test_kataloge_werden_gemerkt_bis_neu_laden(self):
        i18n.setze("en")
        self.assertEqual(i18n.t("Spots suchen"), "Search spots")
        (i18n.LANG / "en.json").write_text(json.dumps({"Spots suchen": "Find spots"}), encoding="utf-8")
        self.assertEqual(i18n.t("Spots suchen"), "Search spots")
        i18n.neu_laden()
        self.assertEqual(i18n.t("Spots suchen"), "Find spots")


class Datum(MitEigenenKatalogen):
    def test_samstag_3_oktober_2026(self):
        erwartet = {"de": ("03.10.", "Sa"), "en": ("3 Oct", "Sat"), "fr": ("3 oct.", "sam."), "es": ("3 oct", "sáb")}
        for sprache, (datum, wochentag) in erwartet.items():
            for tag in (date(2026, 10, 3), datetime(2026, 10, 3, 14, 30)):
                with self.subTest(sprache=sprache, tag=tag):
                    i18n.setze(sprache)
                    self.assertEqual(i18n.tag(tag), SAMSTAG[sprache])
                    self.assertEqual(i18n.datum(tag), datum)
                    self.assertEqual(i18n.wochentag(tag), wochentag)

    def test_einstellig_und_sonntag(self):
        erwartet = {"de": ("Fr 02.01.", "So 04.10."), "en": ("Fri 2 Jan", "Sun 4 Oct"),
                    "fr": ("ven. 2 janv.", "dim. 4 oct."), "es": ("vie 2 ene", "dom 4 oct")}
        for sprache, (neujahr, sonntag) in erwartet.items():
            with self.subTest(sprache=sprache):
                i18n.setze(sprache)
                self.assertEqual(i18n.tag(date(2026, 1, 2)), neujahr)
                self.assertEqual(i18n.tag(date(2026, 10, 4)), sonntag)

    def test_volle_stunde(self):
        """Deutsch „08–14 Uhr“ wie bisher, sonst Uhrzeiten „08:00–14:00“."""
        for sprache, erwartet in {"de": ("08", "13", "9"), "en": ("08:00", "13:00", "09:00"),
                                  "fr": ("08:00", "13:00", "09:00"), "es": ("08:00", "13:00", "09:00")}.items():
            with self.subTest(sprache=sprache):
                i18n.setze(sprache)
                self.assertEqual(i18n.stunde(datetime(2026, 10, 3, 8, 0)), erwartet[0])
                self.assertEqual(i18n.stunde(13.0), erwartet[1])
                self.assertEqual(i18n.stunde(9), erwartet[2])

    def test_volle_stunde_ohne_zahl(self):
        """`from: .nan` im Katalog: bis 2.1.0 brach daran nur der Report in
        en/fr/es ab (`int(round(nan))`), die deutsche Zeile rechnet nicht.
        Jetzt dort ein Strich, auf Deutsch alles wie bisher (C24)."""
        for sprache in FREMDSPRACHEN:
            with self.subTest(sprache=sprache):
                i18n.setze(sprache)
                for wert in (float("nan"), float("inf"), -float("inf")):
                    self.assertEqual(i18n.stunde(wert), "–")
        i18n.setze("de")
        self.assertEqual(i18n.stunde(float("nan")), "nan")
        self.assertEqual(i18n.stunde(float("inf")), "inf")

    def test_sprache_aus_den_mac_einstellungen(self):
        import plistlib
        with tempfile.TemporaryDirectory() as heim:
            ordner = Path(heim) / "Library" / "Preferences"
            ordner.mkdir(parents=True)
            datei = ordner / ".GlobalPreferences.plist"
            with mock.patch.object(i18n.sys, "platform", "darwin"), \
                    mock.patch.object(i18n.Path, "home", return_value=Path(heim)):
                self.assertIsNone(i18n.aus_macos())                       # keine Datei
                datei.write_bytes(plistlib.dumps({"AppleLanguages": ["it-IT", "es-ES", "de-DE"]},
                                                 fmt=plistlib.FMT_BINARY))
                self.assertEqual(i18n.aus_macos(), "es")                  # die erste der vier
                datei.write_bytes(plistlib.dumps({"AppleLanguages": ["zh-Hans"]}))
                self.assertIsNone(i18n.aus_macos())
                datei.write_bytes(b"kaputt")
                self.assertIsNone(i18n.aus_macos())
            with mock.patch.object(i18n.sys, "platform", "linux"):
                self.assertIsNone(i18n.aus_macos())

    def test_tabellen_vollstaendig(self):
        self.assertEqual(set(i18n.WOCHENTAGE), set(i18n.SPRACHEN))
        self.assertEqual(set(i18n.MONATE), set(FREMDSPRACHEN))
        for sprache in i18n.SPRACHEN:
            with self.subTest(sprache=sprache):
                self.assertEqual(len(set(i18n.WOCHENTAGE[sprache])), 7)
                if sprache in i18n.MONATE:
                    self.assertEqual(len(set(i18n.MONATE[sprache])), 12)


class Vorspann(MitEigenenKatalogen):
    """`js_vorspann()`: die Übersetzungen, die die Skripte brauchen, `t()`,
    `N_()` und `tagKurz()` — vor allen anderen Skripten einer Seite."""

    SKRIPTE = {"probe.js": (
        "knopf.textContent = t('Hallo {name}');\n"
        "var a = t(\"Doppelt \\\"zitiert\\\"\");\n"
        "var b = N_('Nur im Skript');\n"
        "var c = t('Ende');\n"
        "var d = t('Unübersetzt');\n"
        "var e = t('{n} von {n}', {n: 2});\n"
        "var f = t('Sie sagt \\'hallo\\'');\n"
        "var g = halt('nicht') + set('auch nicht');\n")}
    KATALOGE = {
        "en": {"Hallo {name}": "Hello {name}", 'Doppelt "zitiert"': 'Double "quoted"',
               "Nur im Skript": "Script only", "Ende": "end </script><script>alert(1)</script>",
               "{n} von {n}": "{n} of {n}", "Sie sagt 'hallo'": "She says 'hello'",
               "Nur in Python": "Python only"},
        "fr": {"Hallo {name}": "Bonjour {name}", "Nur in Python": "Python seulement"},
        "es": {"Nur in Python": "Solo Python"},
    }
    JS = {"Hallo {name}", 'Doppelt "zitiert"', "Nur im Skript", "Ende", "Unübersetzt", "{n} von {n}",
          "Sie sagt 'hallo'"}

    def test_skripttexte_werden_eingesammelt(self):
        self.assertEqual(i18n.js_schluessel(), self.JS)
        self.assertEqual(i18n.js_texte("x = t('Zeile\\nzwei') + N_(\"a\\\\b\");"), ["Zeile\nzwei", "a\\b"])

    def test_nur_skripttexte_mit_uebersetzung(self):
        for sprache in i18n.SPRACHEN:
            with self.subTest(sprache=sprache):
                tabelle, _ = vorspann_teile(i18n.js_vorspann(sprache))
                kat = {k: v for k, v in self.KATALOGE.get(sprache, {}).items() if k in self.JS}
                self.assertEqual(tabelle, kat)
                self.assertNotIn("Nur in Python", tabelle)
                self.assertNotIn("Unübersetzt", tabelle)

    def test_ohne_angabe_die_sprache_des_threads(self):
        i18n.setze("fr")
        self.assertEqual(i18n.js_vorspann(), i18n.js_vorspann("fr"))
        self.assertIn('"sprache": "fr"', i18n.js_vorspann())

    def test_kann_das_skript_nicht_beenden(self):
        """`</script>` in einer Übersetzung darf den Block nicht schließen, und
        `}}` gilt den Tests als unaufgelöste Vorlage. Seit 2.1.0 steht in den
        Daten des Vorspanns gar kein `<`, `>` oder `&` mehr (B1, siehe
        VorspannMitMarkup)."""
        for sprache in i18n.SPRACHEN:
            with self.subTest(sprache=sprache):
                vorspann = i18n.js_vorspann(sprache)
                self.assertNotIn("</", vorspann)
                self.assertNotIn("}}", vorspann)
                keine_funde(self, roh_im_vorspann(vorspann), "roh in den Daten des Vorspanns:")
        tabelle, _ = vorspann_teile(i18n.js_vorspann("en"))
        self.assertEqual(tabelle["Ende"], "end </script><script>alert(1)</script>")

    def test_wochentage_ab_sonntag(self):
        """Wie `Date.getDay()`: 0 ist Sonntag."""
        for sprache in i18n.SPRACHEN:
            with self.subTest(sprache=sprache):
                _, daten = vorspann_teile(i18n.js_vorspann(sprache))
                wt = i18n.WOCHENTAGE[sprache]
                self.assertEqual(daten["sprache"], sprache)
                self.assertEqual(daten["wt"], [wt[6]] + list(wt[:6]))
                self.assertEqual(daten["monate"], list(i18n.MONATE.get(sprache, ())))
        _, daten = vorspann_teile(i18n.js_vorspann("de"))
        self.assertEqual(daten["wt"], ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"])

    def test_im_browser(self):
        """Der Vorspann in Node: `t()` mit Platzhaltern wie in Python,
        `tagKurz()` wie `i18n.tag()`."""
        probe = ("\nprocess.stdout.write(JSON.stringify({"
                 "hallo: t('Hallo {name}', {name: 'Ana'}),"
                 "dollar: t('Hallo {name}', {name: '$& $1'}),"
                 "zitat: t('Doppelt \"zitiert\"'),"
                 "nurJs: N_('Nur im Skript'),"
                 "nurJsT: t('Nur im Skript'),"
                 "ende: t('Ende'),"
                 "fehlt: t('Unübersetzt {n}', {n: 3}),"
                 "zweimal: t('{n} von {n}', {n: 2}),"
                 "geerbt: t('toString'),"
                 "samstag: tagKurz(new Date(2026, 9, 3)),"
                 "neujahr: tagKurz(new Date(2026, 0, 2)),"
                 "sonntag: tagKurz(new Date(2026, 9, 4)),"
                 "sprache: window.I18N.sprache}));\n")
        for sprache in i18n.SPRACHEN:
            with self.subTest(sprache=sprache):
                aus = node_json(self, "var window = globalThis;\n" + i18n.js_vorspann(sprache) + probe)
                i18n.setze(sprache)
                self.assertEqual(aus, {
                    "hallo": i18n.t("Hallo {name}", name="Ana"),
                    "dollar": i18n.t("Hallo {name}", name="$& $1"),
                    "zitat": i18n.t('Doppelt "zitiert"'),
                    "nurJs": "Nur im Skript",
                    "nurJsT": i18n.t("Nur im Skript"),
                    "ende": i18n.t("Ende"),
                    "fehlt": "Unübersetzt 3",
                    "zweimal": i18n.t("{n} von {n}", n=2),
                    "geerbt": "toString",
                    "samstag": SAMSTAG[sprache],
                    "neujahr": i18n.tag(date(2026, 1, 2)),
                    "sonntag": i18n.tag(date(2026, 10, 4)),
                    "sprache": sprache})
                if sprache == "en":                 # und nicht bloß überall der deutsche Text
                    # „Ende“ hat keine spitzen Klammern — die Übersetzung bringt
                    # keine mit (B1, ohne_fremde_klammern); in window.T steht sie roh
                    self.assertEqual((aus["hallo"], aus["zweimal"], aus["ende"]),
                                     ("Hello Ana", "2 of 2", "end &lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;"))


class VorspannMitMarkup(MitEigenenKatalogen):
    """Bis 2.1.0 ersetzte der Vorspann nur `</`. Eine Übersetzung mit
    `<!--<script` brachte den HTML-Tokenizer trotzdem in den Zustand „script
    data double escaped“: das nächste `</script>` schloss den Block nicht
    mehr, und jede Seite, jeder Report und docs/demo.html standen ohne Skript
    da (in Chromium nachgestellt). Jetzt stehen `<`, `>`, `&`, U+2028 und
    U+2029 in den Daten als Escapes, wie in den Karten- und Seitendaten (B1)."""

    BOESE = "end <!--<script x"
    ZEILEN = "eins zwei drei"
    SKRIPTE = {"probe.js": "a = t('Ende'); b = t('Zeilen'); c = t('Klammern & Co');\n"}
    KATALOGE = {"en": {"Ende": BOESE, "Zeilen": ZEILEN, "Klammern & Co": "<b>&amp;</b> > <"}}

    def test_daten_ohne_markup(self):
        vorspann = i18n.js_vorspann("en")
        keine_funde(self, roh_im_vorspann(vorspann), "roh in den Daten des Vorspanns:")
        self.assertNotIn(" ", vorspann)
        self.assertNotIn(" ", vorspann)
        tabelle, _ = vorspann_teile(vorspann)
        self.assertEqual(tabelle, self.KATALOGE["en"])

    def test_laeuft_in_node(self):
        """Die Daten kommen heil an (window.T, siehe oben); `t()` gibt sie
        ohne die spitzen Klammern heraus, die der deutsche Text nicht hat
        (B1, zweite Runde — FremdeKlammern)."""
        aus = node_json(self, "var window = globalThis;\n" + i18n.js_vorspann("en")
                        + "\nprocess.stdout.write(JSON.stringify({ende: t('Ende'), zeilen: t('Zeilen'),"
                          " klammern: t('Klammern & Co'), roh: window.T['Ende'], sprache: window.I18N.sprache}));\n")
        self.assertEqual(aus, {"ende": "end &lt;!--&lt;script x", "zeilen": self.ZEILEN,
                               "klammern": "&lt;b&gt;&amp;&lt;/b&gt; &gt; &lt;", "roh": self.BOESE, "sprache": "en"})

    @staticmethod
    def skripte(html_text: str) -> tuple:
        return html_text.count("<script"), html_text.count("</script>")

    def test_seite_behaelt_ihre_skripte(self):
        ersetze(w, "pruef_offen", lambda: 0, self.addCleanup)
        i18n.setze("de")
        deutsch = w.kein_report_page()
        i18n.setze("en")
        englisch = w.kein_report_page()
        self.assertIn("\\u003c!--\\u003cscript x", englisch)          # die Übersetzung ist da, nur escaped
        self.assertNotIn("<!--", englisch)
        self.assertEqual(self.skripte(englisch), self.skripte(deutsch))
        self.assertEqual(englisch.count("<script"), englisch.count("</script>"))

    def test_report_behaelt_seine_skripte(self):
        ersetze(w, "pruef_offen", lambda: 0, self.addCleanup)
        reports = {}
        with mock.patch.object(wingscout, "CACHE", self.tmp / "cache"):
            for sprache in ("de", "en"):
                datei = self.tmp / f"report-{sprache}.html"
                self.assertEqual(cli.main(["--demo", "--days", "1", "--radius", "300", "--out", str(datei), "--quiet",
                                           "--config", str(CONFIG), "--spots", str(SPOTS),
                                           "--geometry", str(self.tmp / "keine.json"), "--sprache", sprache]), 0)
                reports[sprache] = datei.read_text(encoding="utf-8")
        self.assertIn("\\u003c!--\\u003cscript x", reports["en"])
        self.assertNotIn("<!--", reports["en"])
        self.assertEqual(self.skripte(reports["en"]), self.skripte(reports["de"]))
        # Über den Server, mit Reiterleiste: ebenso
        mit = w.report_mit_reitern(reports["en"].encode("utf-8")).decode("utf-8")
        self.assertEqual(mit.count("<script"), mit.count("</script>"))
        self.assertNotIn("<!--", mit)


class FremdeKlammern(MitEigenenKatalogen):
    """Eine Übersetzung bringt keine spitzen Klammern mit, die der deutsche
    Text nicht hat: `t()` in Python und im Browser machen `&lt;` und `&gt;`
    daraus — vor dem Einsetzen, nie in den eingesetzten Werten (B1, zweite
    Runde; `i18n.ohne_fremde_klammern`). Der Katalogtest oben verbietet solche
    Übersetzungen; dies ist die zweite Sicherung, dort, wo der Text in die
    Seite geht. Texte mit Auszeichnung behalten sie, und Deutsch schlägt
    nichts nach — es bleibt Byte für Byte, wie es war."""

    SKRIPTE = {"probe.js": ("t('umbenennen'); t('Skript'); t('Hallo {name}'); t('Wert <b>{n}</b>');"
                            " t('a > b'); t('Ohne Übersetzung <i>{n}</i>');\n")}
    KATALOGE = {"en": {"umbenennen": "rename <!--", "Skript": "x <script>alert(1)</script>",
                       "Hallo {name}": "Hello <i>{name}", "Wert <b>{n}</b>": "Value <b>{n}</b>",
                       "a > b": "a > b <"}}
    # (deutscher Text, Werte, Englisch, Deutsch)
    FAELLE = [
        ("umbenennen", {}, "rename &lt;!--", "umbenennen"),
        ("Skript", {}, "x &lt;script&gt;alert(1)&lt;/script&gt;", "Skript"),
        ("Hallo {name}", {"name": "<b>Ana</b>"}, "Hello &lt;i&gt;<b>Ana</b>", "Hallo <b>Ana</b>"),   # der Wert bleibt
        ("Wert <b>{n}</b>", {"n": 3}, "Value <b>3</b>", "Wert <b>3</b>"),                         # Auszeichnung bleibt
        ("a > b", {}, "a > b &lt;", "a > b"),                                                     # je Zeichen
        ("Ohne Übersetzung <i>{n}</i>", {"n": "<!--"}, "Ohne Übersetzung <i><!--</i>",            # Deutsch: nichts
         "Ohne Übersetzung <i><!--</i>"),
    ]

    def test_in_python(self):
        for sprache, spalte in (("en", 2), ("de", 3)):
            i18n.setze(sprache)
            for fall in self.FAELLE:
                with self.subTest(sprache=sprache, text=fall[0]):
                    self.assertEqual(i18n.t(fall[0], **fall[1]), fall[spalte])

    def test_im_browser(self):
        """Der Vorspann in Node: dasselbe wie in Python."""
        probe = ("\nvar F = " + json.dumps([[k, werte] for k, werte, _, _ in self.FAELLE], ensure_ascii=False)
                 + ";\nprocess.stdout.write(JSON.stringify(F.map(function (f) {"
                   " return Object.keys(f[1]).length ? t(f[0], f[1]) : t(f[0]); })));\n")
        for sprache, spalte in (("en", 2), ("de", 3)):
            with self.subTest(sprache=sprache):
                aus = node_json(self, "var window = globalThis;\n" + i18n.js_vorspann(sprache) + probe)
                self.assertEqual(aus, [fall[spalte] for fall in self.FAELLE])

    def test_daten_bleiben_wie_im_katalog(self):
        """window.T trägt die Übersetzung, wie sie im Katalog steht (nur fürs
        Skript escaped) — entschärft wird erst in `t()`; und der Vorspann
        bleibt ohne `}}` und `</`."""
        vorspann = i18n.js_vorspann("en")
        tabelle, _ = vorspann_teile(vorspann)
        self.assertEqual(tabelle["umbenennen"], "rename <!--")
        self.assertNotIn("}}", vorspann)
        self.assertNotIn("</", vorspann)
        keine_funde(self, roh_im_vorspann(vorspann), "roh in den Daten des Vorspanns:")


class KlammernAufDenSeiten(MitEigenenKatalogen):
    """Die Funde vom 04.10.2026 an den echten Seiten und Skripten: „rename
    <!--“ als englisches „umbenennen“ ließ von 277 Zeilen der Katalogtabelle
    eine stehen (katalog.js baut sie mit innerHTML), „no comment <!--“ hielt
    die Skripte des Reports an — Kommentarkästen und Tide —, „Map <!--“
    schnitt den Text des Reports ab (B1). Im Browser, wenn Playwright und
    Chromium da sind."""

    KATALOGE = {"en": {"umbenennen": "rename <!--", "kein Kommentar": "no comment <!--", "Karte": "Map <!--"}}

    def setUp(self):
        super().setUp()
        sp, geo_datei = kleiner_katalog(self.tmp)
        pruefzahl_zurueck(self.addCleanup)
        for ziel, name, wert in ((w, "SPOTS_FILE", sp), (w, "GEOMETRY_FILE", geo_datei),
                                 (w, "DEFAULTS_FILE", self.tmp / "ui_defaults.json"),
                                 (w, "REPORT_FILE", self.tmp / "report.html"),
                                 (tagebuch, "TAGEBUCH", self.tmp / "tagebuch.json"),
                                 (rueckblick, "ERGEBNIS", self.tmp / "rueckblick.json"),
                                 (rueckblick, "LETZTER_LAUF", self.tmp / "letzter_lauf.json"),
                                 (w.Handler, "cfg_path", str(CONFIG))):
            ersetze(ziel, name, wert, self.addCleanup)
        self.merke("en")                       # gilt für die Anfragen an den Server

    def report(self) -> Path:
        datei = self.tmp / "report-en.html"
        with mock.patch.object(wingscout, "CACHE", self.tmp / "cache"):
            self.assertEqual(cli.main(["--demo", "--days", "2", "--radius", "300", "--out", str(datei), "--quiet",
                                       "--config", str(CONFIG), "--spots", str(SPOTS),
                                       "--geometry", str(self.tmp / "keine.json"), "--sprache", "en"]), 0)
        return datei

    def server(self) -> str:
        server = w.BegrenzterServer(("127.0.0.1", 0), w.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}"

    def test_report_behaelt_seinen_text(self):
        """Ohne Browser: die Überschrift als Text, kein Kommentar im HTML."""
        text = self.report().read_text(encoding="utf-8")
        self.assertIn("<h2>Map &lt;!--</h2>", text)
        self.assertNotIn("<!--", text)

    def test_katalogseite_im_browser(self):
        basis = self.server()
        n = len(KLEINE_SPOTS)
        with chromium(self) as (seite, fehler):
            seite.goto(basis + "/katalog")
            self.assertEqual(seite.locator("#ktbody > tr").count(), n, "jeder Spot eine Zeile")
            # Die Aktionen zeigt das CSS erst beim Überfahren — also der Text, nicht das Sichtbare
            self.assertEqual(seite.locator("#ktbody a[data-akt='umbenennen']").all_text_contents(), ["rename <!--"] * n)
            self.assertEqual(seite.locator("#ktbody .kmt .kmt-edit").count(), n, "jeder Kommentarkasten fertig")
            self.assertEqual(seite.locator("#ktbody .kmt-leer").all_text_contents(),
                             ["no comment <!--"] * (n - 1))                 # „alpha“ hat einen Kommentar
            self.assertEqual(fehler, [])

    def test_report_im_browser(self):
        datei = self.report()
        with chromium(self) as (seite, fehler):
            seite.goto(datei.as_uri())
            kaesten = seite.locator(".kmt").count()
            self.assertGreater(kaesten, 0)
            self.assertEqual(seite.locator(".kmt .kmt-edit").count(), kaesten, "jeder Kommentarkasten fertig")
            # „Stand … Uhr“ schreibt der Report, das Skript danach (tide.js)
            # ersetzt es beim Öffnen — lief es nicht, steht es noch da
            tiden = seite.locator(".tide-jetzt[data-tide]").all_inner_texts()
            self.assertTrue(tiden, "der Demo-Report hat Tiden")
            self.assertEqual([x for x in tiden if x.startswith("Stand ")], [], "die Tide lief nicht")
            self.assertEqual(seite.locator("#kartebox summary h2").inner_text(), "Map <!--")
            self.assertEqual(fehler, [])


class Hintergrundlauf(MitEigenenKatalogen):
    """Ein Lauf der Oberfläche spricht die Sprache der Anfrage, die ihn
    gestartet hat — er läuft in einem eigenen Thread (`webui._starte`)."""

    KATALOGE = {"fr": {"Probe": "Échantillon"}, "es": {"Probe": "Muestra"}}

    def setUp(self):
        super().setUp()
        with w.LOCK:
            vorher = dict(w.JOB)
            w.JOB.update(state="idle")

        def zurueck():
            with w.LOCK:
                w.JOB.clear()
                w.JOB.update(vorher)
        self.addCleanup(zurueck)

    def warte(self):
        ende = time.time() + 5
        while time.time() < ende:
            with w.LOCK:
                if w.JOB["state"] != "running" and w.JOB["ende"] is not None:
                    return
            time.sleep(0.02)
        self.fail("der Lauf ist nach 5 s nicht fertig")

    def test_lauf_in_der_sprache_der_anfrage(self):
        for sprache, probe in (("fr", "Échantillon"), ("es", "Muestra"), ("de", "Probe")):
            with self.subTest(sprache=sprache):
                i18n.setze(sprache)
                tor, gesehen = threading.Event(), {}

                def arbeit():
                    tor.wait(5)
                    gesehen.update(sprache=i18n.aktuell(), text=i18n.t("Probe"))
                    with w.LOCK:
                        w.JOB["state"] = "done"

                self.assertTrue(w._starte("run", arbeit))
                # Die Anfrage wechselt danach die Sprache — der Lauf behält seine
                i18n.setze("en")
                tor.set()
                self.warte()
                self.assertEqual(gesehen, {"sprache": sprache, "text": probe})
                self.assertEqual(i18n.aktuell(), "en")


class SeitenNehmenDieUebersetzung(MitEigenenKatalogen):
    KATALOGE = {"en": {"Katalog": "Catalogue ✓", "Sprache": "Language ✓"}}

    def test_uebersetzung_steht_auf_der_seite(self):
        ersetze(w, "pruef_offen", lambda: 0, self.addCleanup)
        home = {"lat": 53.55, "lon": 9.99}
        i18n.setze("en")
        seite = w.katalog_page([], home)
        self.assertIn("<h1>Catalogue ✓</h1>", seite)
        self.assertIn("<span>Catalogue ✓</span>", seite)              # der Reiter
        self.assertIn("aria-label='Language ✓'", seite)
        for sprache in ("de", "fr"):                                   # fr: kein Katalog — Deutsch
            i18n.setze(sprache)
            seite = w.katalog_page([], home)
            self.assertIn("<h1>Katalog</h1>", seite)
            self.assertIn(f"<html lang='{sprache}'>", seite)


class _Attribute(HTMLParser):
    """Alle Attribute aller Tags einer Seite als (Tag, Name, Wert) — so, wie
    ein Browser sie liest (Skript- und Stilblöcke sind Text)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.alle = []

    def handle_starttag(self, tag, attrs):
        self.alle.extend((tag, name, wert) for name, wert in attrs)

    handle_startendtag = handle_starttag


def eingeschleuste_attribute(html_text: str) -> list:
    leser = _Attribute()
    leser.feed(html_text)
    leser.close()
    return [f"<{tag} {name}={(wert or '')[:60]!r}>" for tag, name, wert in leser.alle
            if name.startswith(("data-boese", "data-kompass", "on"))]


class UebersetzungSprengtKeinAttribut(MitEigenenKatalogen):
    """Jeder übersetzte Text, der in einem Attribut steht, kommt escaped
    dorthin (B2). Geprüft mit einem Katalog, in dem jeder Text auf `"` und `'`
    samt eigenem Attribut endet, und einer Kompassrose mit solchen Kürzeln: wo
    eines davon als Attribut ankommt, stand ein Text roh in einem Attribut.
    Bis 2.1.0 waren das die Zelltitel des Stundenrasters (Uhrzeit, Richtung,
    Score, Tide) — im Demo-Report gut 9600 Attribute, die nur die Richtlinie
    (csp.py) stillhielt."""

    ZUSATZ = "\" data-boese=\"1' data-boese2='1"

    def setUp(self):
        katalog = {k: k + self.ZUSATZ for k in quelltexte()}
        katalog[KOMPASS] = " ".join(k + '"data-kompass="1' for k in KOMPASS.split())      # 16 Kürzel
        self.KATALOGE = {"en": katalog}
        super().setUp()
        sp, geo_datei = kleiner_katalog(self.tmp)
        pruefzahl_zurueck(self.addCleanup)
        for ziel, name, wert in ((w, "SPOTS_FILE", sp), (w, "GEOMETRY_FILE", geo_datei),
                                 (w, "DEFAULTS_FILE", self.tmp / "ui_defaults.json"),
                                 (tagebuch, "TAGEBUCH", self.tmp / "tagebuch.json")):
            ersetze(ziel, name, wert, self.addCleanup)
        i18n.setze("en")

    def test_der_katalog_greift(self):
        """Sonst prüften die Tests unten nur Deutsch."""
        self.assertTrue(i18n.t("Katalog").endswith(self.ZUSATZ))
        self.assertIn('"data-kompass="1', geo.compass(90))

    def test_seiten(self):
        cfg = load_cfg()
        spots = load_spots(str(w.SPOTS_FILE))
        home = cfg["rider"]["home"]
        eintraege = w.pruef_liste(home)[0]
        lauf = {"zeit": "2026-10-03T12:00", "demo": True, "top": [{"rang": 1, "id": "alpha", "name": "Alpha"}]}

        def mit_lan():
            with mock.patch.dict(w.LAN, aktiv=True, schluessel="k3y", adressen=("192.168.178.25",)):
                return w.page(cfg, w.form_defaults(cfg))

        seiten = {"suche": lambda: w.page(cfg, w.form_defaults(cfg)), "suche (WLAN)": mit_lan,
                  "katalog": lambda: w.katalog_page(spots, home), "pruefen": lambda: w.pruef_page(eintraege, home),
                  "rueckblick": lambda: w.rueckblick_page(cfg, {"zeit": "2026-10-01T09:00", "version": "1.0.0",
                                                                "spots": []}, lauf, 3, {}),
                  "tagebuch": lambda: w.tagebuch_page(cfg, spots, heute="2026-10-03"),
                  "kein report": w.kein_report_page, "fehler": lambda: w.fehler_page(KatalogFehler("x")),
                  "hilfe": w.hilfe_page, "hilfe (rechnet)": w.rechnung_page}
        for name, bauen in seiten.items():
            with self.subTest(seite=name):
                with contextlib.redirect_stderr(io.StringIO()):
                    html_text = bauen()
                self.assertIn(self.ZUSATZ.replace('"', "&quot;").replace("'", "&#x27;"), html_text,
                              "der Katalog kommt auf der Seite an")
                keine_funde(self, eingeschleuste_attribute(html_text), f"{name}: Attribute aus Übersetzungen:")

    def test_report(self):
        datei = self.tmp / "report.html"
        with mock.patch.object(wingscout, "CACHE", self.tmp / "cache"):
            self.assertEqual(cli.main(["--demo", "--days", "2", "--radius", "300", "--out", str(datei), "--quiet",
                                       "--config", str(CONFIG), "--spots", str(SPOTS),
                                       "--geometry", str(self.tmp / "keine.json"), "--sprache", "en"]), 0)
        roh = datei.read_bytes()
        text = roh.decode("utf-8")
        self.assertIn("class='cell", text)                                   # das Stundenraster ist da
        self.assertIn("&quot;data-kompass=&quot;1", text)                    # und mit ihm die Richtungen
        keine_funde(self, eingeschleuste_attribute(text), "Report: Attribute aus Übersetzungen:")
        keine_funde(self, eingeschleuste_attribute(w.report_mit_reitern(roh).decode("utf-8")),
                    "Report über den Server: Attribute aus Übersetzungen:")


# ── 3. Seiten und Report in jeder Sprache ───────────────────────────────────

class Seiten(unittest.TestCase):
    """Jede Seite der Oberfläche und der Report in allen vier Sprachen, mit den
    echten Katalogen — geprüft wird der Aufbau, nicht die Vollständigkeit."""

    @classmethod
    def setUpClass(cls):
        cls.addClassCleanup(zuruecksetzen)
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.tmp = Path(tmp.name)
        sp, geo = kleiner_katalog(cls.tmp)
        pruefzahl_zurueck(cls.addClassCleanup)
        for ziel, name, wert in ((w, "SPOTS_FILE", sp), (w, "GEOMETRY_FILE", geo),
                                 (w, "DEFAULTS_FILE", cls.tmp / "ui_defaults.json"),
                                 # Der Neustart-Hinweis steht damit auf jeder Seite — ein Text mit Platzhaltern mehr
                                 (w, "version_auf_platte", lambda: "9.9.9"),
                                 (tagebuch, "TAGEBUCH", cls.tmp / "tagebuch.json")):
            ersetze(ziel, name, wert, cls.addClassCleanup)
        cls.cfg = load_cfg()
        cls.spots = load_spots(str(sp))
        cls.home = cls.cfg["rider"]["home"]

    def setUp(self):
        self.addCleanup(i18n.setze, i18n.QUELLE)

    def seiten(self) -> dict:
        """Name → Seite, gebaut in der Sprache, die gerade gilt."""
        cfg, spots, home = self.cfg, self.spots, self.home
        eintraege = w.pruef_liste(home)[0]
        lauf = {"zeit": "2026-10-03T12:00", "demo": True, "top": [{"rang": 1, "id": "alpha", "name": "Alpha"}]}
        alt = {"zeit": "2026-10-01T09:00", "version": "1.0.0", "spots": []}       # überholt: Hinweis oben

        def mit_lan():
            with mock.patch.dict(w.LAN, aktiv=True, schluessel="k3y", adressen=("192.168.178.25",)):
                return w.page(cfg, w.form_defaults(cfg))

        return {
            "suche": lambda: w.page(cfg, w.form_defaults(cfg)),
            "suche (WLAN)": mit_lan,
            "katalog": lambda: w.katalog_page(spots, home),
            "pruefen": lambda: w.pruef_page(eintraege, home),
            "pruefen (ein Eintrag)": lambda: w.pruef_page(eintraege[:1], home),
            "pruefen (leer)": lambda: w.pruef_page([], home),
            "rueckblick": lambda: w.rueckblick_page(cfg, alt, lauf, 3, {"alpha": "Parken am Ende"}),
            "rueckblick (ohne Suche)": lambda: w.rueckblick_page(cfg, None, None, 2, {}),
            "tagebuch": lambda: w.tagebuch_page(cfg, spots, heute="2026-10-03"),
            "kein report": w.kein_report_page,
            "fehler (Katalog)": lambda: w.fehler_page(KatalogFehler("Doppelte Spot-ID: alpha")),
            "fehler (Konfiguration)": lambda: w.fehler_page(KonfigFehler("config.yaml nicht lesbar")),
            "fehler (Datei)": lambda: w.fehler_page(PermissionError(13, "Permission denied")),
            "hilfe": w.hilfe_page,
            "hilfe (rechnet)": w.rechnung_page,
        }

    def test_kleiner_katalog_zeigt_alle_stufen(self):
        """Sonst prüfte die Prüfseite unten weniger, als sie vorgibt."""
        self.assertEqual({e["stufe"] for e in w.pruef_liste(self.home)[0]}, {"unbrauchbar", "pruefen", "unbestaetigt"})
        self.assertEqual(w.geometry_state(), (4, 1))

    def test_jede_seite_in_jeder_sprache(self):
        for sprache in i18n.SPRACHEN:
            with self.subTest(sprache=sprache):
                i18n.setze(sprache)
                seiten = self.seiten()
                for name, bauen in seiten.items():
                    with self.subTest(sprache=sprache, seite=name):
                        with contextlib.redirect_stderr(io.StringIO()):      # fehler_page meldet sich im Terminal
                            html_text = bauen()
                        pruefe_seite(self, html_text, sprache)

    def test_report_in_jeder_sprache(self):
        """Der Report aus dem Demo-Lauf, mit `--sprache` von der Kommandozeile —
        als Datei und über den Server mit Reiterleiste und Umschalter."""
        with mock.patch.dict(os.environ), \
                mock.patch.object(i18n, "SPRACH_DATEI", self.tmp / "sprache.txt"), \
                mock.patch.object(wingscout, "CACHE", self.tmp / "cache"):   # letzter_lauf.json nicht in cache/
            os.environ.pop("WINGSCOUT_SPRACHE", None)
            for sprache in i18n.SPRACHEN:
                with self.subTest(sprache=sprache):
                    i18n.setze(i18n.QUELLE)          # nichts von der Runde davor
                    datei = self.tmp / f"report-{sprache}.html"
                    code = cli.main(["--demo", "--days", "1", "--radius", "300", "--out", str(datei), "--quiet",
                                     "--config", str(CONFIG), "--spots", str(SPOTS),
                                     "--geometry", str(self.tmp / "keine.json"), "--sprache", sprache])
                    self.assertEqual(code, 0)
                    self.assertEqual(i18n.aktuell(), sprache)
                    roh = datei.read_bytes()
                    pruefe_seite(self, roh.decode("utf-8"), sprache, umschalter=False)
                    pruefe_seite(self, w.report_mit_reitern(roh).decode("utf-8"), sprache)
                    # Datum und Uhrzeit bleiben beisammen (am Handy brach die
                    # Zeile dazwischen um), der Radius ohne „.0“ (2.1.0) und
                    # seit 2.4.0 als Fahrstrecke benannt
                    text = roh.decode("utf-8")
                    self.assertRegex(text, r"<p class='sub'>Wingfoilscout [^<]*<span class='nw'>[^<]+</span></p>")
                    with i18n.in_sprache(sprache):
                        radius = i18n.T("{km} km Fahrstrecke", km="300")
                    self.assertIn(f"</b> {radius}</span>", text)
                    self.assertNotIn("300.0 km", text)

    def test_startfeld_nennt_zuerst_den_heimatort(self):
        """Am Handy wird der Platzhalter abgeschnitten: bis 2.1.0 blieb von
        „Koordinate oder Maps-Link — leer: Hamburg“ nur der Anfang. Jetzt
        steht der Ort vorn, in jeder Sprache."""
        heim = self.home["name"]
        for sprache in i18n.SPRACHEN:
            with self.subTest(sprache=sprache):
                i18n.setze(sprache)
                seite = w.page(self.cfg, w.form_defaults(self.cfg))
                m = re.search(r'<input type="text" id="start"[^>]*\splaceholder="([^"]*)"', seite)
                self.assertIsNotNone(m, "kein Startfeld")
                self.assertTrue(html.unescape(m.group(1)).startswith(heim + " – "), m.group(1))

    def test_vorspann_mit_den_echten_katalogen(self):
        """Was die Seiten wirklich bekommen: nur Skripttexte, nichts, was das
        Skript beendet — und in Node setzt `t()` jeden Skripttext so ein wie
        `i18n.t()` in Python."""
        schluessel = sorted(i18n.js_schluessel())
        werte = {k: {n: f"«{n}»" for n in PLATZ.findall(k)} for k in schluessel}
        for sprache in i18n.SPRACHEN:
            with self.subTest(sprache=sprache):
                vorspann = i18n.js_vorspann(sprache)
                self.assertNotIn("</", vorspann)
                self.assertNotIn("}}", vorspann)
                keine_funde(self, roh_im_vorspann(vorspann), f"{sprache}: roh in den Daten des Vorspanns:")
                tabelle, _ = vorspann_teile(vorspann)
                self.assertEqual(tabelle, {k: v for k, v in i18n.katalog(sprache).items() if k in werte})
                if not NODE:
                    continue
                aus = node_json(self, "var window = globalThis;\n" + vorspann + "\nvar F = "
                                + json.dumps([[k, werte[k]] for k in schluessel], ensure_ascii=False)
                                + ";\nvar aus = {};\nF.forEach(function (f) { aus[f[0]] = t(f[0], f[1]); });\n"
                                  "aus['tagKurz'] = tagKurz(new Date(2026, 9, 3));\n"
                                  "process.stdout.write(JSON.stringify(aus));\n")
                i18n.setze(sprache)
                soll = {k: t_mit(k, werte[k]) for k in schluessel}
                soll["tagKurz"] = SAMSTAG[sprache]
                abweichend = [f"{k!r}: JS {aus.get(k)!r}, Python {soll[k]!r}" for k in soll if aus.get(k) != soll[k]]
                keine_funde(self, abweichend, f"{sprache}: JavaScript setzt anders ein als Python:")


class Umschalter(unittest.TestCase):
    """POST /sprache am laufenden Server: die Wahl landet in sprache.txt — hier
    einer im Temporärordner —, und jede Seite danach spricht sie."""

    SEITEN = ("/", "/katalog", "/pruefen", "/rueckblick", "/tagebuch", "/report", "/hilfe", "/hilfe/rechnung")

    @classmethod
    def setUpClass(cls):
        cls.addClassCleanup(zuruecksetzen)
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.tmp = Path(tmp.name)
        sp, geo = kleiner_katalog(cls.tmp)
        pruefzahl_zurueck(cls.addClassCleanup)
        for ziel, name, wert in ((i18n, "SPRACH_DATEI", cls.tmp / "sprache.txt"),
                                 (w, "SPOTS_FILE", sp), (w, "GEOMETRY_FILE", geo),
                                 (w, "DEFAULTS_FILE", cls.tmp / "ui_defaults.json"),
                                 (w, "REPORT_FILE", cls.tmp / "report.html"),
                                 (tagebuch, "TAGEBUCH", cls.tmp / "tagebuch.json"),
                                 (rueckblick, "ERGEBNIS", cls.tmp / "rueckblick.json"),
                                 (rueckblick, "LETZTER_LAUF", cls.tmp / "letzter_lauf.json"),
                                 (w.Handler, "cfg_path", str(CONFIG))):
            ersetze(ziel, name, wert, cls.addClassCleanup)
        cls.echt = cls.echte_wahl()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), w.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server.shutdown)

    @staticmethod
    def echte_wahl():
        datei = ROOT / "sprache.txt"
        return datei.read_bytes() if datei.exists() else None

    def setUp(self):
        umgebung = mock.patch.dict(os.environ)
        umgebung.start()
        self.addCleanup(umgebung.stop)
        os.environ.pop("WINGSCOUT_SPRACHE", None)
        self.datei = i18n.SPRACH_DATEI
        if self.datei.exists():
            self.datei.unlink()

    def anfrage(self, pfad, daten=None, kopf=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{pfad}", data=daten, headers=kopf or {},
                                     method="GET" if daten is None else "POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

    def waehle(self, wert, kopf=None):
        return self.anfrage("/sprache", urllib.parse.urlencode({"sprache": wert}).encode("utf-8"),
                            dict({"Content-Type": "application/x-www-form-urlencoded"}, **(kopf or {})))

    def sprache_der_seite(self, pfad="/katalog", kopf=None):
        code, text = self.anfrage(pfad, kopf={"Accept-Language": kopf} if kopf else None)
        self.assertEqual(code, 200, text[:300])
        return re.search(r"<html lang='([^']*)'", text).group(1)

    def test_wahl_wird_gemerkt_und_gilt_fuer_jede_seite(self):
        for sprache in ("fr", "es", "en", "de"):
            with self.subTest(sprache=sprache):
                code, body = self.waehle(sprache)
                self.assertEqual((code, json.loads(body)), (200, {"ok": True}))
                self.assertEqual(self.datei.read_text(encoding="utf-8").strip(), sprache)
                andere = next(s for s in i18n.SPRACHEN if s != sprache)
                for pfad in self.SEITEN:
                    with self.subTest(sprache=sprache, pfad=pfad):
                        # Der Browser will eine andere — die Wahl gilt
                        code, text = self.anfrage(pfad, kopf={"Accept-Language": andere})
                        self.assertEqual(code, 200, text[:300])
                        pruefe_seite(self, text, sprache)
        self.assertEqual(self.echte_wahl(), self.echt, "die echte sprache.txt bleibt, wie sie war")

    def test_unbekannte_sprache_ist_400(self):
        self.datei.write_text("es\n", encoding="utf-8")
        for wert in ("xx", "", "deutsch", "de-CH", "../sprache"):
            with self.subTest(wert=wert):
                code, _ = self.waehle(wert)
                self.assertEqual(code, 400)
        code, _ = self.anfrage("/sprache", b"", {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(code, 400)
        self.assertEqual(self.datei.read_text(encoding="utf-8"), "es\n")
        self.assertEqual(self.sprache_der_seite(), "es")

    def test_fremde_seite_schaltet_nicht_um(self):
        code, _ = self.waehle("fr", {"Origin": "https://boese-seite.example"})
        self.assertEqual(code, 403)
        self.assertFalse(self.datei.exists())

    def test_ohne_wahl_entscheidet_der_browser(self):
        for kopf, erwartet in ((None, "de"), ("es-ES,es;q=0.9,en;q=0.8", "es"), ("de-CH,de;q=0.9", "de"),
                               ("en-GB,en;q=0.9", "en"), ("fr-FR", "fr"), ("it-IT,it;q=0.9", "en")):
            with self.subTest(kopf=kopf):
                self.assertEqual(self.sprache_der_seite(kopf=kopf), erwartet)

    def test_umgebung_schlaegt_die_wahl(self):
        self.assertEqual(self.waehle("fr")[0], 200)
        os.environ["WINGSCOUT_SPRACHE"] = "es"
        self.assertEqual(self.sprache_der_seite(kopf="en"), "es")


if __name__ == "__main__":
    unittest.main()
