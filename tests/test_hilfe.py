"""Die Hilfe in der App: Anleitung (README) und „Wie Wingfoilscout rechnet“
(docs/bewertung.html) — wingscout/hilfe.py und die Seiten /hilfe,
/hilfe/rechnung.

Fünf Teile:

1. Der Markdown-Renderer: Escaping (auch gegen feindliche Eingaben), Anker
   wie auf GitHub, Listen, Tabellen, Code, wohin Links führen.
2. Das Säubern der Rechenseite und das Eingrenzen ihres Stils.
3. Die Seiten in allen vier Sprachen: Sprache, Inhaltsverzeichnis, Nonce an
   jedem Skript, keine Ereignisattribute, nichts von außen.
4. Der Server: Richtlinie, die Sicherheitsprüfungen, WLAN-Betrieb, keine
   Dateien über den Pfad.
5. Drift: passen die Übersetzungen (README.xx.md, wingscout/hilfe/
   bewertung.xx.html) noch zum englischen Original? Fehlt eine Übersetzung,
   wird der Test übersprungen (sichtbar als „skipped“); weicht sie ab,
   scheitert er — mit der Stelle, an der es hakt.
"""
from __future__ import annotations

import collections
import html
import os
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

from tests.helpers import CONFIG, ROOT
import wingscout.webui as w
from wingscout import hilfe, i18n

UEBERSETZUNGEN = [s for s in i18n.SPRACHEN if s != hilfe.ORIGINAL]


# ── Gemeinsames ─────────────────────────────────────────────────────────────

class _Tags(HTMLParser):
    """Alle Start-Tags mit Attributen, und ob die Tags aufgehen und zugehen."""
    LEER = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
            "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags: list = []
        self.offen: list = []
        self.fehler: list = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, attrs))
        if tag not in self.LEER:
            self.offen.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.tags.append((tag, attrs))

    def handle_endtag(self, tag):
        if tag in self.LEER:
            return
        if not self.offen or self.offen[-1] != tag:
            self.fehler.append(f"</{tag}> bei offen {self.offen[-3:]}")
            if tag in self.offen:
                while self.offen.pop() != tag:
                    pass
            return
        self.offen.pop()


def tags(text: str) -> _Tags:
    leser = _Tags()
    leser.feed(text)
    leser.close()
    return leser


def ausgeglichen(test: unittest.TestCase, text: str) -> None:
    """Jedes Tag, das aufgeht, geht in der richtigen Reihenfolge wieder zu."""
    leser = tags(text)
    test.assertEqual(leser.fehler, [], text[:300])
    test.assertEqual(leser.offen, [], text[:300])


def ereignisattribute(text: str) -> list:
    return [f"<{t} {n}>" for t, attrs in tags(text).tags for n, _ in attrs if n.lower().startswith("on")]


def erlaubte_links(test: unittest.TestCase, text: str) -> None:
    """Jedes href ist http(s), mailto, #… oder ein Weg in der App."""
    for tag, attrs in tags(text).tags:
        for name, wert in attrs:
            if name in ("href", "xlink:href") and wert is not None:
                test.assertRegex(wert, r"^(?:https?://|mailto:|#|/hilfe(?:/rechnung)?(?:#|$))", f"<{tag} {name}={wert!r}>")


def md(text: str, **optionen) -> str:
    return hilfe.rendern(text, **optionen).html


# ── 1. Markdown ─────────────────────────────────────────────────────────────

class Escaping(unittest.TestCase):
    """Jeder Text kommt escaped auf die Seite; rohes HTML gar nicht."""

    FEINDLICH = [
        "<script>alert(1)</script>",
        "Hallo <script>alert(1)</script> Welt",
        "x <img src=x onerror=alert(1)> y <svg onload=alert(1)>",
        "<iframe src=javascript:alert(1)></iframe>",
        "<div onclick='alert(1)'>\n*mehr*\n</div>",
        "<a href=\"javascript:alert(1)\">klick</a>",
        "[a](javascript:alert(1)) [b](JaVaScRiPt:alert(1)) [c](&#106;avascript:alert(1)) [d](&#x6A;avascript:x)",
        "[e](data:text/html;base64,PHNjcmlwdD4=) [f](vbscript:msgbox) [g](file:///etc/passwd) [h](//evil.example/)",
        "[i](<java script:alert(1)>) [j](\\javascript:alert(1)) [k](javascript&colon;alert(1))",
        "<javascript:alert(1)> <data:text/html,x>",
        "![x](javascript:alert(1)) ![y\" onerror=\"alert(1)](z.png)",
        "[x](http://a \"t\\\" onmouseover=\\\"alert(1)\")",
        "[x](http://a\"onmouseover=\"alert(1))",
        "<!-- <script>alert(1)</script> -->",
        "`<script>` und ``<b onclick=x>``",
        "```html\n<script>alert(1)</script>\n```",
        "| <script> | <b>x</b> |\n|---|---|\n| [y](javascript:z) | `<i>` |",
        "> <script>alert(1)</script>\n> [z](javascript:x)",
        "- <img src=x onerror=alert(1)>\n  - [w](javascript:w)",
        "**<script>** *</script>* ~~<style>~~",
        "&lt;script&gt; &#60;script&#62; \\<script\\>",
        "[\x00x](http://a\x00b) \ud800",
        "Text\n<script>\nalert(1)\n</script>\nnach",
        "<style>body{display:none}</style>\n\nweiter",
    ]

    def test_feindliche_eingaben(self):
        for text in self.FEINDLICH:
            with self.subTest(text=text):
                aus = md(text)
                self.assertNotRegex(aus.lower(), r"<\s*/?\s*(?:script|iframe|img|svg|style|object|embed|span|kbd)\b")
                self.assertNotRegex(aus, r'<div(?! class="tabelle)')
                self.assertEqual(ereignisattribute(aus), [])
                self.assertNotIn("javascript:", " ".join(v or "" for _, a in tags(aus).tags for _, v in a).lower())
                erlaubte_links(self, aus)
                ausgeglichen(self, aus)

    def test_text_und_code_werden_escaped(self):
        self.assertEqual(md("a < b & c > d"), "<p>a &lt; b &amp; c &gt; d</p>\n")
        self.assertEqual(md("`<b>&amp;`"), "<p><code>&lt;b&gt;&amp;amp;</code></p>\n")
        self.assertEqual(md("```\n<b>\n```"), "<pre><code>&lt;b&gt;\n</code></pre>\n")
        self.assertEqual(md("&copy; &amp; &unbekannt; &#38;"), "<p>© &amp; &amp;unbekannt; &amp;</p>\n")
        self.assertIn("<code>&lt;script&gt;</code>", md("`<script>`"))

    def test_rohes_html_wird_weggelassen(self):
        readme = ('Vorher.\n\n<p align="center">\n<picture><source media="(prefers-color-scheme: dark)" '
                  'srcset="docs/a.png"><img src="docs/b.png" width="250" alt="Suche"></picture>\n</p>\n'
                  '<p align="center"><sub>Beispiel ·\n<a href="https://example.org/">Website</a></sub></p>\n\nNachher.')
        self.assertEqual(md(readme), "<p>Vorher.</p>\n<p>Nachher.</p>\n")
        self.assertEqual(md("<!-- Notiz -->\n\nText"), "<p>Text</p>\n")
        # Im Absatz fällt das Tag weg, der Text bleibt; <br> wird ein Umbruch
        self.assertEqual(md("a <kbd>Strg</kbd>+<kbd>C</kbd> <br> b"), "<p>a Strg+C <br>\n b</p>\n")
        self.assertEqual(md("x <span style='color:red'>rot</span> y"), "<p>x rot y</p>\n")

    def test_unausgeglichene_auszeichnung(self):
        for text in ("**fett", "*a **b", "a **b *c", "__x_", "~~weg", "[link(", "[a](http://b", "![bild",
                     "`code", "```\noffen", "> zitat\n>> tiefer\n- liste\n  * innen", "**a [b** c](http://d)",
                     "*a [b*](http://c)", "***", "_*_*_*", "[[[x]]]", "a\\", "<<<>>>", "&&&;;"):
            with self.subTest(text=text):
                aus = md(text)
                ausgeglichen(self, aus)
                erlaubte_links(self, aus)
        self.assertEqual(md("**fett *kursiv"), "<p>**fett *kursiv</p>\n")
        self.assertEqual(md("[a](http://b"), "<p>[a](http://b</p>\n")

    def test_tiefe_verschachtelung_ist_kein_absturz(self):
        aus = md("> " * 500 + "tief")
        self.assertIn("tief", aus)
        ausgeglichen(self, aus)
        aus = md("\n".join("  " * i + "- x" for i in range(200)))
        ausgeglichen(self, aus)
        aus = md("*a " * 3000 + "**b" * 3000)                 # viele Trenner: wörtlich, nicht quadratisch
        ausgeglichen(self, aus)
        aus = md("[" * 5000 + "x" + "](http://a)" * 10)
        ausgeglichen(self, aus)


class Laufzeit(unittest.TestCase):
    """Auch feindliche Eingaben bleiben linear: ein offenes `<!--` suchte bis
    zum Ende — 15 000 davon in einem Absatz waren 9 Sekunden."""

    def test_keine_quadratische_laufzeit(self):
        import time
        faelle = {
            "Kommentare": "x <!--" * 15000, "Anweisungen": "x <?" * 15000, "CDATA": "x <![CDATA[" * 8000,
            "Deklarationen": "x <!A" * 15000, "Backticks": "".join("`" * k + "x" for k in range(1, 300)),
            "Attribute": 'x <a b="' * 10000 + ">", "Titel": '[x](y "' * 8000, "Klammern": "]" * 60000 + "[" * 60000,
            "Sterne": "*a _b " * 10000, "Links": "[a](b) " * 8000, "Adressen": "https://a.org/x " * 10000,
            "Verweise": "[a]: /x\n\n" + "[a] " * 20000,
        }
        for name, text in faelle.items():
            with self.subTest(name=name):
                beginn = time.monotonic()
                hilfe.rendern(text)
                self.assertLess(time.monotonic() - beginn, 3.0)
        # Säubern: ein Ende ohne Anfang unter tiefer Verschachtelung prüfte bis dahin die ganze Liste
        for name, text in {"fremde Enden": "<div>" * 20000 + "</span>" * 20000,
                           "tief": "<div>" * 20000 + "x" + "</div>" * 20000, "offen": "<span>" * 30000}.items():
            with self.subTest(name=name):
                beginn = time.monotonic()
                ausgeglichen(self, hilfe.saeubern(text))
                self.assertLess(time.monotonic() - beginn, 3.0)


class Inline(unittest.TestCase):
    def test_betonung(self):
        self.assertEqual(md("**fett** *kursiv* _auch_ __fett__ ***beides*** ~~weg~~"),
                         "<p><strong>fett</strong> <em>kursiv</em> <em>auch</em> <strong>fett</strong> "
                         "<em><strong>beides</strong></em> <del>weg</del></p>\n")
        self.assertEqual(md("snake_case_name und 2*3*4"), "<p>snake_case_name und 2<em>3</em>4</p>\n")
        self.assertEqual(md("**„Station bis … km“** (Vorgabe)"),
                         "<p><strong>„Station bis … km“</strong> (Vorgabe)</p>\n")
        self.assertEqual(md("**Fine-tune the search → Water**"), "<p><strong>Fine-tune the search → Water</strong></p>\n")

    def test_code_vor_allem_anderen(self):
        self.assertEqual(md("`*nicht* [kein](link)`"), "<p><code>*nicht* [kein](link)</code></p>\n")
        self.assertEqual(md("`` a ` b ``"), "<p><code>a ` b</code></p>\n")

    def test_harte_umbrueche(self):
        self.assertEqual(md("eins  \nzwei\\\ndrei\nvier"), "<p>eins<br>\nzwei<br>\ndrei\nvier</p>\n")

    def test_bilder_werden_ihr_alternativtext(self):
        self.assertEqual(md("![Suche: Startpunkt](docs/a.png)"), "<p>Suche: Startpunkt</p>\n")
        self.assertEqual(md("[![Abzeichen](b.svg)](https://example.org)"),
                         '<p><a href="https://example.org" target="_blank" rel="noopener noreferrer">Abzeichen</a></p>\n')

    def test_nackte_adressen(self):
        aus = md("Siehe https://example.org/a_b_c. Und (https://x.org/a_(b)), www.example.com!")
        self.assertIn('<a href="https://example.org/a_b_c" target="_blank" rel="noopener noreferrer">https://example.org/a_b_c</a>.', aus)
        self.assertIn('<a href="https://x.org/a_(b)"', aus)
        self.assertIn('<a href="http://www.example.com"', aus)

    def test_kein_link_im_link(self):
        """Der innere Link gilt, der äußere nicht mehr (CommonMark) — und nie
        steht ein <a> in einem <a>, auch nicht über eine nackte Adresse."""
        for text in ("[https://a.org und [b](https://b.org)](https://c.org)", "[x <https://a.org> y](https://b.org)",
                     "[www.a.org](https://b.org)"):
            with self.subTest(text=text):
                aus = md(text)
                ausgeglichen(self, aus)
                tiefe, tiefste = 0, 0
                for m in re.finditer(r"<(/?)a\b", aus):
                    tiefe += -1 if m.group(1) else 1
                    tiefste = max(tiefste, tiefe)
                self.assertEqual(tiefste, 1, aus)
        self.assertEqual(md("[https://a.org und [b](https://b.org)](https://c.org)"),
                         '<p>[https://a.org und <a href="https://b.org" target="_blank" rel="noopener noreferrer">b</a>]'
                         '(<a href="https://c.org" target="_blank" rel="noopener noreferrer">https://c.org</a>)</p>\n')

    def test_verweise(self):
        aus = md("[Text][r], [r][] und [r].\n\n[r]: https://ref.example \"Titel\"")
        self.assertEqual(aus.count('<a href="https://ref.example" title="Titel"'), 3)
        self.assertNotIn("[r]:", aus)


class Links(unittest.TestCase):
    """Wohin ein Link in der App führt (`link_ziel`)."""

    def ziel(self, adresse, basis=""):
        return hilfe.link_ziel(adresse, basis)

    def test_im_repository(self):
        blob = "https://github.com/DarkPirateGo/wingfoilscout/blob/main/"
        faelle = {
            "README.md": ("/hilfe", False), "README.de.md#x": ("/hilfe#x", False), "./README.fr.md": ("/hilfe", False),
            "docs/bewertung.html": ("/hilfe/rechnung", False), "docs/bewertung.html#tide": ("/hilfe/rechnung#tide", False),
            "SCORING.md": (blob + "SCORING.md", True), "LICENSE": (blob + "LICENSE", True),
            "DEVELOPMENT.md#tests": (blob + "DEVELOPMENT.md#tests", True), "/CHANGELOG.md": (blob + "CHANGELOG.md", True),
            "tools/check.sh": (blob + "tools/check.sh", True),
            "Wingfoilscout starten.command": (blob + "Wingfoilscout%20starten.command", True),
            "docs/demo.html": ("https://darkpiratego.github.io/wingfoilscout/demo.html", True),
            "docs/index.html": ("https://darkpiratego.github.io/wingfoilscout/", True),
            "#command-line": ("#command-line", False),
        }
        for adresse, soll in faelle.items():
            with self.subTest(adresse=adresse):
                self.assertEqual(self.ziel(adresse), soll)

    def test_von_der_rechenseite_aus(self):
        """Die Rechenseite liegt in docs/: ihre relativen Links meinen die Website."""
        self.assertEqual(self.ziel("index.html", "docs/"), ("https://darkpiratego.github.io/wingfoilscout/", True))
        self.assertEqual(self.ziel("demo.html", "docs/"), ("https://darkpiratego.github.io/wingfoilscout/demo.html", True))
        self.assertEqual(self.ziel("bewertung.html#ziele", "docs/"), ("/hilfe/rechnung#ziele", False))
        self.assertEqual(self.ziel("../SCORING.md", "docs/"),
                         ("https://github.com/DarkPirateGo/wingfoilscout/blob/main/SCORING.md", True))
        self.assertEqual(self.ziel("../README.md", "docs/"), ("/hilfe", False))

    def test_nach_draussen(self):
        self.assertEqual(self.ziel("https://open-meteo.com"), ("https://open-meteo.com", True))
        self.assertEqual(self.ziel("http://a.example/x y"), ("http://a.example/x%20y", True))
        self.assertEqual(self.ziel("mailto:a@b.example"), ("mailto:a@b.example", False))
        self.assertEqual(self.ziel("https://github.com/DarkPirateGo/wingfoilscout/releases/latest"),
                         ("https://github.com/DarkPirateGo/wingfoilscout/releases/latest", True))
        # Die Rechenseite auf der Website ist die in der App
        self.assertEqual(self.ziel("https://darkpiratego.github.io/wingfoilscout/bewertung.html"),
                         ("/hilfe/rechnung", False))

    def test_kein_link(self):
        for adresse in ("javascript:alert(1)", " JavaScript:alert(1)", "java\tscript:x", "\x01javascript:x",
                        "data:text/html,x", "vbscript:x", "file:///etc/passwd", "ftp://x", "//evil.example/x",
                        "\\\\evil\\x", "../../etc/passwd", "../x", "", "   ", "ht tp://x", "java script:x"):
            with self.subTest(adresse=adresse):
                self.assertIsNone(self.ziel(adresse))

    def test_im_text(self):
        aus = md("[Anleitung](README.de.md) · [Wertung](SCORING.md) · [böse](javascript:alert(1)) · "
                 "[Mail](mailto:x@y.example) · [hier](#oben)")
        self.assertIn('<a href="/hilfe">Anleitung</a>', aus)
        self.assertIn('<a href="https://github.com/DarkPirateGo/wingfoilscout/blob/main/SCORING.md" target="_blank" '
                      'rel="noopener noreferrer">Wertung</a>', aus)
        self.assertIn(" böse ", aus)
        self.assertIn('<a href="mailto:x@y.example">Mail</a>', aus)
        self.assertIn('<a href="#oben">hier</a>', aus)


class Anker(unittest.TestCase):
    """Anker wie auf GitHub (github-slugger)."""

    def test_slug(self):
        faelle = {
            "The benchmark — is it still right?": "the-benchmark--is-it-still-right",
            "spots.yaml — the real asset": "spotsyaml--the-real-asset",
            "Your quiver → your wind range": "your-quiver--your-wind-range",
            "Data sources, licences and limits": "data-sources-licences-and-limits",
            "Without a terminal (Mac)": "without-a-terminal-mac",
            "Über Wingfoilscout": "über-wingfoilscout",
            "Fahrzeit: geroutet, nicht geschätzt": "fahrzeit-geroutet-nicht-geschätzt",
            "Marées — pleine et basse mer": "marées--pleine-et-basse-mer",
            "¿Qué tan segura es la previsión?": "qué-tan-segura-es-la-previsión",
            "wind_factor & 2.1.0 🌊": "wind_factor--210-",            # wie GitHub: das Leerzeichen vor dem Emoji bleibt
            "  Viel   Platz  ": "--viel---platz--",
            "C++ / C#": "c--c",
        }
        for text, soll in faelle.items():
            with self.subTest(text=text):
                self.assertEqual(hilfe.slug(text), soll)

    def test_doppelte_bekommen_eine_nummer(self):
        s = hilfe.Slugs()
        self.assertEqual([s(x) for x in ("Karte", "Karte", "karte", "Karte-1", "Karte")],
                         ["karte", "karte-1", "karte-2", "karte-1-1", "karte-3"])

    def test_ueberschriften_bekommen_ihren_anker(self):
        g = hilfe.rendern("# Titel\n\n## `spots.yaml` — *the* real asset\n\n### Map\n\n### Map\n\n#### Vier ####")
        self.assertIn('<h1 id="titel">Titel</h1>', g.html)
        self.assertIn('<h2 id="spotsyaml--the-real-asset"><code>spots.yaml</code> — <em>the</em> real asset</h2>', g.html)
        self.assertIn('<h3 id="map-1">Map</h3>', g.html)
        self.assertIn('<h4 id="vier">Vier</h4>', g.html)
        self.assertEqual([(s, a) for s, a, _ in g.ueberschriften],
                         [(1, "titel"), (2, "spotsyaml--the-real-asset"), (3, "map"), (3, "map-1"), (4, "vier")])

    def test_versatz(self):
        """Die Seite hat ihre eigene <h1>: im README wird # zu <h2>."""
        self.assertEqual(md("# A\n## B\n#### D", versatz=1), '<h2 id="a">A</h2>\n<h3 id="b">B</h3>\n<h5 id="d">D</h5>\n')

    def test_die_anker_des_readme_stimmen(self):
        """Jeder Link auf eine Stelle im README selbst trifft eine Überschrift."""
        g = hilfe.rendern((ROOT / "README.md").read_text(encoding="utf-8"))
        anker = {a for _, a, _ in g.ueberschriften}
        self.assertTrue(g.anker, "das README verweist auf eigene Abschnitte")
        self.assertEqual([a for a in g.anker if a not in anker], [])
        self.assertIn("the-benchmark--is-it-still-right", anker)


class Bloecke(unittest.TestCase):
    def test_verschachtelte_listen(self):
        aus = md("- eins\n  - zwei\n    1. drei\n    2. vier\n- fünf\n\n3) ab drei\n4) weiter")
        self.assertEqual(aus, "<ul>\n<li>eins\n<ul>\n<li>zwei\n<ol>\n<li>drei</li>\n<li>vier</li>\n</ol></li>\n</ul></li>\n"
                              "<li>fünf</li>\n</ul>\n<ol start=\"3\">\n<li>ab drei</li>\n<li>weiter</li>\n</ol>\n")

    def test_lose_liste_und_fortsetzung(self):
        aus = md("- **Fett** — erste Zeile\n  zweite Zeile\n\n- nächster Punkt\nfaul fortgesetzt")
        self.assertEqual(aus, "<ul>\n<li>\n<p><strong>Fett</strong> — erste Zeile\nzweite Zeile</p>\n</li>\n"
                              "<li>\n<p>nächster Punkt\nfaul fortgesetzt</p>\n</li>\n</ul>\n")

    def test_tabellen(self):
        aus = md("| Option | Bedeutung | x |\n|:---|---:|:-:|\n| `--sprache de\\|en` | **fett** \\| Strich |\n| eins |")
        self.assertEqual(aus, '<div class="tabelle"><table>\n<thead><tr><th style="text-align:left">Option</th>'
                              '<th style="text-align:right">Bedeutung</th><th style="text-align:center">x</th></tr></thead>\n'
                              '<tbody>\n<tr><td style="text-align:left"><code>--sprache de|en</code></td>'
                              '<td style="text-align:right"><strong>fett</strong> | Strich</td><td style="text-align:center"></td></tr>\n'
                              '<tr><td style="text-align:left">eins</td><td style="text-align:right"></td>'
                              '<td style="text-align:center"></td></tr>\n</tbody>\n</table></div>\n')
        self.assertEqual(md("| a | b |\n|---|---|"), '<div class="tabelle"><table>\n<thead><tr><th>a</th><th>b</th></tr>'
                                                     "</thead>\n\n</table></div>\n")
        # Keine Tabelle ohne passende Trennzeile
        self.assertEqual(md("a | b\n--- | --- | ---"), "<p>a | b\n--- | --- | ---</p>\n")

    def test_code(self):
        g = hilfe.rendern("```bash\n# kein Titel\npython3 run.py   # Kommentar\n```\n\n~~~\n```\n~~~\n\n    eingerückt\n\n"
                          "```\noffen bis zum Ende")
        self.assertEqual(g.html, '<pre><code class="language-bash"># kein Titel\npython3 run.py   # Kommentar\n</code></pre>\n'
                                 "<pre><code>```\n</code></pre>\n<pre><code>eingerückt\n</code></pre>\n"
                                 "<pre><code>offen bis zum Ende\n</code></pre>\n")
        self.assertEqual(g.zaeune, 3)
        self.assertEqual(g.ueberschriften, [])

    def test_zitat_linie_ueberschrift(self):
        self.assertEqual(md("> Zitat\nfaul\n> > tiefer\n\n---\n\nTitel\n=====\n\nZwei\n---"),
                         "<blockquote>\n<p>Zitat\nfaul</p>\n<blockquote>\n<p>tiefer</p>\n</blockquote>\n</blockquote>\n"
                         '<hr>\n<h1 id="titel">Titel</h1>\n<h2 id="zwei">Zwei</h2>\n')

    def test_sprachzeile_faellt_weg(self):
        text = ("# Wingfoilscout\n\n*Diese Anleitung auf: [English](README.md) · **Deutsch** · [Français](README.fr.md)*\n\n"
                "Findet Sessions. Siehe [die englische](README.md).")
        self.assertEqual(md(text, ohne_sprachzeile=True),
                         '<h1 id="wingfoilscout">Wingfoilscout</h1>\n<p>Findet Sessions. Siehe <a href="/hilfe">die englische</a>.</p>\n')
        self.assertIn("Diese Anleitung auf", md(text))

    def test_das_echte_readme(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        g = hilfe.rendern(text, versatz=1, ohne_sprachzeile=True)
        ausgeglichen(self, g.html)
        erlaubte_links(self, g.html)
        self.assertEqual(ereignisattribute(g.html), [])
        self.assertNotIn("<picture", g.html)
        self.assertNotIn("This guide in", g.html)
        self.assertIn('<h3 id="command-line">Command line</h3>'.replace("h3", "h4"), g.html)
        self.assertIn('<a href="#command-line">Command line</a>', g.html)
        # Seit 2.3.0 stehen Codeblöcke auch eingerückt in Aufzählungen (Installation)
        self.assertEqual(g.zaeune, len(re.findall(r"^ *```", text, re.M)) // 2)
        self.assertIn("<code>--sprache de|en|fr|es</code>", g.html)
        self.assertIn('<a href="/hilfe/rechnung">“How Wingfoilscout calculates”</a>', g.html)


# ── 2. Die Rechenseite ──────────────────────────────────────────────────────

class Saeubern(unittest.TestCase):
    def test_feindliches_faellt_weg(self):
        quelle = """<!doctype html><html lang="de"><head><meta charset="utf-8"><title>T</title>
<base href="https://evil.example/"><link rel="stylesheet" href="https://evil.example/x.css">
<meta http-equiv="refresh" content="0;url=https://evil.example"><style>body{x:1}</style>
<script>alert(1)</script></head><body onload="alert(1)">
<div class="huelle" ONCLICK="alert(1)" onmouseover='x'>
<p>Text &amp; <b>fett</b> &lt;script&gt;</p>
<script src="https://evil.example/x.js"></script><script>alert(2)</script>
<iframe src="https://evil.example"></iframe><object data="x.swf"></object><embed src="x.swf">
<noscript><img src=x onerror=alert(1)></noscript><template><b>t</b></template>
<form action="/shutdown" method="post"><button formaction="/shutdown">Weiter</button><input name="x"></form>
<a href="javascript:alert(1)">j</a> <a href="data:text/html,x">d</a> <a href=" JAVASCRIPT:alert(1)">J</a>
<a href="index.html">Start</a> <a href="demo.html">Demo</a> <a href="#grenzen">unten</a>
<a href="https://github.com/DarkPirateGo/wingfoilscout" target="_self" rel="opener">GitHub</a>
<a href="mailto:a@b.example">Mail</a> <a href="//evil.example">pr</a> <a href="vbscript:x">v</a>
<img src="https://tracker.example/p.gif" alt="t"><img src="bilder/x.png" alt="lokal">
<p style="position:fixed;top:0;color:red;background:url(https://evil.example/x)">stil</p>
<p style="color:expression(alert(1))">ie</p>
<svg viewBox="0 0 10 10"><title>Titel im SVG</title><defs><marker id="pf"><path d="M0,0"/></marker></defs>
<a xlink:href="javascript:alert(1)"><text>x</text></a><use href="https://evil.example/s.svg#a"/><use href="#pf"/>
<line marker-end="url(#pf)" stroke="var(--gruen)"/><rect fill="url(https://evil.example/f)"/>
<animate attributeName="href" to="javascript:alert(1)"/><set attributeName="onclick" to="alert(1)"/>
<foreignObject><div onclick="x">fo</div></foreignObject><script>alert(3)</script></svg>
<h1>Eins</h1><h2>Zwei</h2>
<div><span>offen
</body></html>"""
        aus = hilfe.saeubern(quelle, versatz=1)
        klein = aus.lower()
        for weg in ("<script", "<iframe", "<object", "<embed", "<link", "<meta", "<base", "<style", "<noscript",
                    "<template", "<form", "<button", "<input", "<animate", "<set", "<foreignobject", "<title>t</title>",
                    "evil.example", "tracker.example", "alert(", "javascript", "vbscript", "data:text", "position",
                    "expression", "formaction", "<!doctype", "<html", "<body", "<head"):
            with self.subTest(weg=weg):
                self.assertNotIn(weg, klein)
        self.assertEqual(ereignisattribute(aus), [])
        ausgeglichen(self, aus)
        erlaubte_links(self, aus)
        self.assertIn("<p>Text &amp; <b>fett</b> &lt;script&gt;</p>", aus)
        self.assertIn('<a href="https://darkpiratego.github.io/wingfoilscout/" target="_blank" rel="noopener noreferrer">Start</a>', aus)
        self.assertIn('<a href="https://darkpiratego.github.io/wingfoilscout/demo.html" target="_blank" '
                      'rel="noopener noreferrer">Demo</a>', aus)
        self.assertIn('<a href="#grenzen">unten</a>', aus)
        self.assertIn('<a href="https://github.com/DarkPirateGo/wingfoilscout" target="_blank" rel="noopener noreferrer">GitHub</a>', aus)
        self.assertIn('<a href="mailto:a@b.example">Mail</a>', aus)
        self.assertIn("<a>j</a>", aus)                          # das Ziel ist weg, der Text bleibt
        self.assertIn('<p style="top:0;color:red">stil</p>', aus)
        self.assertIn("<title>Titel im SVG</title>", aus)
        self.assertIn('<use href="#pf"/>', aus)
        self.assertIn('<line marker-end="url(#pf)" stroke="var(--gruen)"/>', aus)
        self.assertIn("<rect/>", aus)
        self.assertIn('<img alt="t"><img alt="lokal">', aus)
        self.assertIn("Weiter", aus)
        self.assertIn("<h2>Eins</h2><h3>Zwei</h3>", aus)        # eine Stufe tiefer: die Seite hat ihre <h1>
        # Was offen blieb, wird geschlossen — auch das <div class="huelle"> vom Anfang
        self.assertTrue(aus.rstrip().endswith("<div><span>offen\n</span></div></div>"), aus[-80:])

    def test_die_echte_seite(self):
        quelle = hilfe.bewertung_datei("en").read_text(encoding="utf-8")
        aus = hilfe.saeubern(quelle, versatz=1)
        ausgeglichen(self, aus)
        erlaubte_links(self, aus)
        self.assertEqual(ereignisattribute(aus), [])
        self.assertNotIn("<style", aus)
        self.assertNotIn("<!--", aus)
        self.assertEqual(aus.count("<svg"), quelle.count("<svg"))
        self.assertIn('<section id="pipeline">', aus)
        self.assertIn('marker-end="url(#pf)"', aus)
        self.assertNotIn("<h1", aus)
        self.assertIn('href="https://darkpiratego.github.io/wingfoilscout/"', aus)


class StilEingrenzen(unittest.TestCase):
    def test_regeln(self):
        css = """/* Kommentar mit { und } */
:root{--a:#fff;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--a:#000}}
:root[data-theme="dark"]{--a:#111}
body{background:var(--a)} html body .x{y:1}
h1,h2,h3{font-family:"A, B {x}",serif} .h1, #h2, h1.k {z:1}
a:focus-visible,summary:focus-visible{outline:0}
figure svg{display:block}
@import url(https://evil.example/x.css);
@font-face{font-family:X;src:url(https://evil.example/x.woff)}
@keyframes drehen{from{opacity:0}to{opacity:1}}
@supports (display:grid){.k{display:grid}}
.boese{content:"</style><script>alert(1)</script>"}"""
        aus = hilfe.css_eingrenzen(css, ".m", versatz=1)
        self.assertIn(".m{--a:#fff;color-scheme:light}", aus)
        self.assertIn('@media (prefers-color-scheme:dark){.m:not([data-theme="light"]){--a:#000}}', aus)
        self.assertIn('.m[data-theme="dark"]{--a:#111}', aus)
        self.assertIn(".m{background:var(--a)}", aus)
        self.assertIn(".m .x{y:1}", aus)
        self.assertIn('.m h2,.m h3,.m h4{font-family:"A, B {x}",serif}', aus)
        self.assertIn(".m .h1,.m #h2,.m h2.k{z:1}", aus)
        self.assertIn(".m a:focus-visible,.m summary:focus-visible{outline:0}", aus)
        self.assertIn(".m figure svg{display:block}", aus)
        self.assertIn("@keyframes drehen{from{opacity:0}to{opacity:1}}", aus)
        self.assertIn("@supports (display:grid){.m .k{display:grid}}", aus)
        self.assertNotIn("evil.example", aus)
        self.assertNotIn("Kommentar", aus)
        self.assertNotIn("</", aus)
        # Jede Regel gilt nur in .m
        for kopf in re.findall(r"(?:^|[}\n])([^{}@]+)\{", aus):
            for waehler in kopf.split(","):
                if waehler.strip() not in ("from", "to"):
                    self.assertTrue(waehler.strip().startswith(".m"), waehler)

    def test_der_echte_stil(self):
        quelle = hilfe.bewertung_datei("en").read_text(encoding="utf-8")
        aus = hilfe.css_eingrenzen(hilfe.stil_aus(quelle), ".methode", versatz=1)
        self.assertIn(".methode{--schrift-titel:", aus)
        self.assertIn('@media (prefers-color-scheme:dark){.methode:not([data-theme="light"]){--papier:', aus)
        self.assertIn(".methode{margin:0}", aus)                 # <style>body{margin:0}</style>
        self.assertIn(".methode h2,.methode h3,.methode h4{", aus)
        self.assertNotRegex(aus, r"(?:^|[},])\s*(?:body|html|:root|h1)\b")
        self.assertNotIn("url(", aus)


# ── 3. Die Seiten ───────────────────────────────────────────────────────────

class Seiten(unittest.TestCase):
    """Beide Hilfeseiten in allen vier Sprachen."""

    @classmethod
    def setUpClass(cls):
        hilfe.vergessen()
        p = mock.patch.object(w, "pruef_offen", lambda: 0)          # die Leiste fragt sonst den Katalog
        p.start()
        cls.addClassCleanup(p.stop)

    def setUp(self):
        self.addCleanup(i18n.setze, i18n.QUELLE)

    def seiten(self, sprache: str) -> dict:
        i18n.setze(sprache)
        n = w.nonce_neu()
        return n, {"anleitung": w.hilfe_page(), "rechnung": w.rechnung_page()}

    def test_jede_sprache(self):
        from tests.test_i18n import pruefe_seite
        for sprache in i18n.SPRACHEN:
            n, seiten = self.seiten(sprache)
            for name, seite in seiten.items():
                with self.subTest(sprache=sprache, seite=name):
                    pruefe_seite(self, seite, sprache)
                    # Jedes Skript mit der Nonce, keins von außen, keins ohne
                    skripte = re.findall(r"<script\b[^>]*>", seite)
                    self.assertTrue(skripte)
                    self.assertEqual(set(skripte), {f"<script nonce='{n}'>"})
                    self.assertEqual(ereignisattribute(seite), [])
                    ausgeglichen(self, seite.split("<body>", 1)[1].rsplit("</body>", 1)[0])
                    # Nichts von außen: keine Adresse in src, kein fremdes Stylesheet, keine url() nach draußen
                    for tag, attrs in tags(seite).tags:
                        for attr, wert in attrs:
                            if attr in ("src", "srcset", "poster", "data") or (attr == "href" and tag != "a"):
                                self.assertNotRegex(wert or "", r"^\s*(?:[a-z]+:|//)", f"<{tag} {attr}={wert!r}>")
                    self.assertEqual([u for u in re.findall(r"url\(([^)]*)\)", seite) if not u.strip("'\"").startswith("#")], [])
                    self.assertNotIn("@import", seite)
                    erlaubte = [v for t, a in tags(seite).tags if t == "a" for k, v in a if k == "href"]
                    for href in erlaubte:
                        self.assertRegex(href, r"^(?:https?://|mailto:|#|/)", href)
                    # Das „?“ steht in der Leiste und ist hervorgehoben, die Umschaltung zeigt die Seite
                    self.assertIn("class='hilfeknopf'", seite)
                    self.assertRegex(seite, r"<a href='/hilfe' class='hilfeknopf' title='[^']+' aria-label='[^']+' aria-current='page'>\?</a>")
                    pfad = "/hilfe" if name == "anleitung" else "/hilfe/rechnung"
                    self.assertIn(f"<a href='{pfad}' aria-current='page'>", seite)
                    self.assertEqual(seite.count("aria-current='page'"), 2)
                    ohne_skripte = re.sub(r"<script\b.*?</script>", "", seite, flags=re.S)
                    self.assertEqual(ohne_skripte.count("<h1"), 1)
                    self.assertIn("<footer class='seitenfuss'>", seite)

    def test_inhaltsverzeichnis(self):
        for sprache in i18n.SPRACHEN:
            with self.subTest(sprache=sprache):
                _, seiten = self.seiten(sprache)
                seite = seiten["anleitung"]
                a = hilfe.anleitung(sprache)
                self.assertIn("<details class='inhaltsliste zu-am-handy' open><summary>", seite)
                eintraege = re.findall(r"<li><a href='#([^']+)'>", seite.split("<details class='inhaltsliste", 1)[1].split("</details>", 1)[0])
                text = hilfe.readme_datei(a.sprache).read_text(encoding="utf-8")
                self.assertEqual(len(eintraege), len(re.findall(r"^## ", re.sub(r"```.*?```", "", text, flags=re.S), re.M)))
                self.assertGreaterEqual(len(eintraege), 8)
                for anker in eintraege:
                    self.assertIn(f' id="{html.escape(anker)}"', seite)

    def test_rechenseite_mit_ihrem_stil(self):
        _, seiten = self.seiten("en")
        seite = seiten["rechnung"]
        self.assertIn("<article class='methode' lang='en'>", seite)
        self.assertIn(".methode{--schrift-titel:", seite)
        self.assertLess(seite.index(".methode{--schrift-titel:"), seite.index(".hilfekopf{"), "hilfe.css darf nachbessern")
        self.assertIn('<section id="pipeline">', seite)
        self.assertIn("How Wingfoilscout calculates</h2>", seite)

    def test_ohne_uebersetzung_die_englische_mit_hinweis(self):
        with tempfile.TemporaryDirectory() as d:
            ordner = Path(d)
            (ordner / "docs").mkdir()
            (ordner / "hilfe").mkdir()
            (ordner / "README.md").write_text("# Wingfoilscout\n\n## Usage\n\nEnglish text.\n", encoding="utf-8")
            (ordner / "docs" / "bewertung.html").write_text(
                "<html lang='en'><head><style>:root{--x:1}</style></head><body><h1>How</h1><p>English</p></body></html>",
                encoding="utf-8")
            (ordner / "README.fr.md").write_text("# Wingfoilscout\n\n## Utilisation\n\nTexte français.\n", encoding="utf-8")
            (ordner / "hilfe" / "bewertung.fr.html").write_text("<html lang='fr'><body><h1>Comment</h1></body></html>",
                                                                  encoding="utf-8")
            hilfe.vergessen()
            self.addCleanup(hilfe.vergessen)
            with mock.patch.object(hilfe, "ROOT", ordner), mock.patch.object(hilfe, "ORDNER", ordner / "hilfe"):
                for sprache in ("de", "es"):
                    _, seiten = self.seiten(sprache)
                    with self.subTest(sprache=sprache):
                        self.assertIn("<p class='hilfehinweis'>", seiten["anleitung"])
                        self.assertIn("<article class='anleitung' lang='en'>", seiten["anleitung"])
                        self.assertIn("English text.", seiten["anleitung"])
                        self.assertIn("<p class='hilfehinweis'>", seiten["rechnung"])
                        self.assertIn("<article class='methode' lang='en'>", seiten["rechnung"])
                        self.assertIn(f"<html lang='{sprache}'>", seiten["anleitung"])
                _, seiten = self.seiten("fr")
                self.assertNotIn("<p class='hilfehinweis'>", seiten["anleitung"])
                self.assertIn("<article class='anleitung' lang='fr'>", seiten["anleitung"])
                self.assertIn("<li><a href='#utilisation'>Utilisation</a></li>", seiten["anleitung"])
                self.assertIn("<article class='methode' lang='fr'>", seiten["rechnung"])
                self.assertIn(".methode{--x:1}", seiten["rechnung"])     # der Stil kommt aus dem Original
                _, seiten = self.seiten("en")
                self.assertNotIn("<p class='hilfehinweis'>", seiten["anleitung"] + seiten["rechnung"])
                # Eine Sprache, die es nicht gibt, ist Englisch — kein Pfad aus der Anfrage
                self.assertEqual(hilfe.anleitung("../../etc").sprache, "en")
                (ordner / "README.md").unlink()
                hilfe.vergessen()
                with self.assertRaises(FileNotFoundError):
                    hilfe.anleitung("en")

    def test_gemerkt_je_stand_der_datei(self):
        with tempfile.TemporaryDirectory() as d:
            ordner = Path(d)
            datei = ordner / "README.md"
            datei.write_text("# A\n\n## Eins\n", encoding="utf-8")
            hilfe.vergessen()
            self.addCleanup(hilfe.vergessen)
            echt = hilfe.rendern
            with mock.patch.object(hilfe, "ROOT", ordner), mock.patch.object(hilfe, "rendern", side_effect=echt) as zaehler:
                self.assertEqual(hilfe.anleitung("en").inhalt, [("eins", "Eins")])
                hilfe.anleitung("en")
                self.assertEqual(zaehler.call_count, 1)
                datei.write_text("# A\n\n## Eins\n\n## Zwei\n", encoding="utf-8")
                os.utime(datei, ns=(datei.stat().st_atime_ns, datei.stat().st_mtime_ns + 10 ** 9))
                self.assertEqual(hilfe.anleitung("en").inhalt, [("eins", "Eins"), ("zwei", "Zwei")])
                self.assertEqual(zaehler.call_count, 2)

    def test_kaputte_datei_ist_kein_absturz(self):
        with tempfile.TemporaryDirectory() as d:
            ordner = Path(d)
            (ordner / "README.md").write_bytes(b"# A\n\n## Kaputt \xff\xfe\n\nText\x00 <script>x</script>\n")
            hilfe.vergessen()
            self.addCleanup(hilfe.vergessen)
            with mock.patch.object(hilfe, "ROOT", ordner):
                a = hilfe.anleitung("en")
        self.assertIn("Kaputt ��", a.html)
        self.assertNotIn("<script", a.html)


class Leiste(unittest.TestCase):
    """Das „?“ auf jeder Seite — auch in der Leiste, die der Report über den
    Server bekommt —, zwischen Sprache und „Beenden“."""

    def test_reihenfolge(self):
        with mock.patch.object(w, "pruef_offen", lambda: 0):
            for aktiv in ("/", "/katalog", "/report", "", "/hilfe", "/hilfe/rechnung"):
                with self.subTest(aktiv=aktiv):
                    leiste = w.reiter_leiste(aktiv)
                    rechts = leiste[leiste.index("<span class='rechts'>"):]
                    stellen = [rechts.index(x) for x in ("class='marke'", "class='sprachwahl'", "class='hilfeknopf'", "id='quit'")]
                    self.assertEqual(stellen, sorted(stellen))
                    self.assertEqual(leiste.count("class='hilfeknopf'"), 1)
                    self.assertEqual("aria-current='page'" in leiste, aktiv.startswith("/hilfe"))
                    self.assertIn("title='Hilfe' aria-label='Hilfe'", leiste)
            aus = w.report_mit_reitern(b"<html><head></head><body><div class='wrap'><h1>R</h1></div></body></html>").decode("utf-8")
            self.assertIn("<a href='/hilfe' class='hilfeknopf'", aus)

    def test_stil(self):
        reiter = (w.WEB / "reiter.css").read_text(encoding="utf-8")
        rechner, handy = reiter.split("@media (max-width:700px)", 1)
        # Am Rechner: Version klein unter dem Logo, damit die Leiste eine Zeile bleibt
        self.assertRegex(rechner, r"\.reiter \.marke\{margin-left:auto;[^}]*flex-direction:column")
        self.assertIn(".reiter .hilfeknopf{", rechner)
        self.assertIn(".reiter .hilfeknopf[aria-current=page]{", rechner)
        # Am Handy: „?“ und „Beenden“ als feste Gruppe oben rechts, Platz in der ersten Zeile
        self.assertRegex(handy, r"\.reiter \.rechts\{position:fixed;top:calc\(10px \+ env\(safe-area-inset-top\)\);"
                                r"right:calc\(12px \+ env\(safe-area-inset-right\)\)")
        self.assertIn(".reiter .rechts .sprachwahl{display:none}", handy)
        self.assertNotRegex(handy, r"\.reiter \.aus\{position:fixed")
        self.assertIn(".reiter + .hilfekopf > h1{padding-right:", handy.replace(",.reiter + .hilfekopf", "\n.reiter + .hilfekopf"))
        basis = (w.WEB / "basis.css").read_text(encoding="utf-8")
        self.assertIn(".seitenfuss{display:flex;justify-content:center;align-items:center;gap:9px", basis)
        # Die Sprache steht neben der Marke, nicht mehr in ihr: ohne `width:auto`
        # nähme sie im Fuß die ganze Zeile (basis.css: select{width:100%})
        self.assertRegex(reiter, r"\n\.sprachwahl\{[^}]*width:auto")


# ── 4. Der Server ───────────────────────────────────────────────────────────

class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        hilfe.vergessen()
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        for ziel, name, wert in ((w.Handler, "cfg_path", str(CONFIG)), (w, "pruef_offen", lambda: 0),
                                 (i18n, "SPRACH_DATEI", Path(tmp.name) / "sprache.txt")):
            p = mock.patch.object(ziel, name, wert)
            p.start()
            cls.addClassCleanup(p.stop)
        cls.server = w.BegrenzterServer(("127.0.0.1", 0), w.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server.shutdown)

    def anfrage(self, pfad, kopf=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{pfad}", headers=kopf or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.headers, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read().decode("utf-8", "replace")

    def test_beide_seiten_mit_richtlinie(self):
        for pfad in ("/hilfe", "/hilfe/rechnung"):
            with self.subTest(pfad=pfad):
                status, kopf, seite = self.anfrage(pfad)
                self.assertEqual(status, 200)
                self.assertEqual(kopf.get("Content-Type"), "text/html; charset=utf-8")
                n = re.search(r"'nonce-([A-Za-z0-9_-]+)'", kopf.get("Content-Security-Policy") or "").group(1)
                self.assertEqual(set(re.findall(r"<script\b[^>]*>", seite)), {f"<script nonce='{n}'>"})
                self.assertEqual(kopf.get("X-Frame-Options"), "SAMEORIGIN")
                self.assertEqual(kopf.get("X-Content-Type-Options"), "nosniff")

    def test_sprache_des_browsers(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("WINGSCOUT_SPRACHE", None)
            for sprache in i18n.SPRACHEN:
                for pfad in ("/hilfe", "/hilfe/rechnung"):
                    with self.subTest(sprache=sprache, pfad=pfad):
                        status, _, seite = self.anfrage(pfad, {"Accept-Language": sprache})
                        self.assertEqual(status, 200)
                        self.assertIn(f"<html lang='{sprache}'>", seite)

    def test_sicherheitspruefungen_gelten(self):
        """Fremde Seiten betten nichts ein, fremde Namen kommen nicht durch."""
        for pfad in ("/hilfe", "/hilfe/rechnung"):
            with self.subTest(pfad=pfad):
                kopf = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "iframe"}
                self.assertEqual(self.anfrage(pfad, kopf)[0], 403)
                kopf = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Dest": "script"}
                self.assertEqual(self.anfrage(pfad, kopf)[0], 403)
                self.assertEqual(self.anfrage(pfad, {"Host": "boese.example"})[0], 403)
                kopf = {"Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
                self.assertEqual(self.anfrage(pfad, kopf)[0], 200)

    def test_keine_dateien_ueber_den_pfad(self):
        for pfad in ("/hilfe/", "/hilfe/README.md", "/README.md", "/README.de.md", "/docs/bewertung.html",
                     "/hilfe/../README.md", "/hilfe/rechnung/", "/hilfe/bewertung.de.html", "/wingscout/hilfe/bewertung.de.html",
                     "/hilfe.css", "/hilfe/rechnung?datei=../config.yaml"):
            with self.subTest(pfad=pfad):
                status, _, seite = self.anfrage(pfad)
                if pfad.startswith("/hilfe/rechnung?"):
                    self.assertEqual(status, 200)              # die Abfrage zählt nicht
                    self.assertNotIn("rider:", seite)
                else:
                    self.assertEqual(status, 404, seite[:100])

    def test_im_wlan_nur_mit_schluessel(self):
        """Mit --lan: ein anderes Gerät ohne Schlüssel bekommt 401, mit dem
        Cookie die Seite — wie jede andere Seite."""
        class Attrappe:
            server_address = ("0.0.0.0", 8765)

        class Probe(w.Handler):
            def __init__(self, pfad, cookie=""):
                self.client_address = ("192.168.178.9", 4711)
                self.path = pfad
                self.headers = {"Cookie": cookie, "Host": "192.168.178.25:8765"}
                self.server = Attrappe()
                self.antwort = None

            def _send(self, code, body, ctype="text/html; charset=utf-8", nonce_wert=None):
                self.antwort = (code, body if isinstance(body, bytes) else w.als_bytes(body))

        with mock.patch.dict(w.LAN, aktiv=True, schluessel="geheim-123", adressen=("192.168.178.25",)):
            for pfad in ("/hilfe", "/hilfe/rechnung"):
                with self.subTest(pfad=pfad):
                    ohne = Probe(pfad)
                    ohne.do_GET()
                    self.assertEqual(ohne.antwort[0], 401)
                    mit = Probe(pfad, "wingscout_schluessel=geheim-123")
                    mit.do_GET()
                    self.assertEqual(mit.antwort[0], 200)
                    self.assertIn(b"class='hilfekopf'", mit.antwort[1])


# ── 5. Drift: passen die Übersetzungen noch zum Original? ───────────────────
# Was hier scheitert, heißt: README.md oder docs/bewertung.html hat sich
# geändert (oder die Übersetzung), und die Übersetzung zieht nicht mehr mit.
# Die Meldung nennt die Stelle; dort die Übersetzung nachziehen.

_URL = re.compile(r"https?://[^\s)<>\"'`\]]+")


def _urls(text: str) -> set:
    return {u.rstrip(".,;:!?*_~") for u in _URL.findall(text)}


class DriftAnleitung(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (ROOT / "README.md").read_text(encoding="utf-8")
        cls.g_original = hilfe.rendern(cls.original)

    def uebersetzung(self, sprache: str) -> str:
        datei = ROOT / f"README.{sprache}.md"
        if not datei.exists():
            self.skipTest(f"{datei.name} gibt es noch nicht")
        return datei.read_text(encoding="utf-8")

    def test_ueberschriften(self):
        """Dieselben Überschriften je Stufe in derselben Reihenfolge."""
        soll = [(stufe, text) for stufe, _, text in self.g_original.ueberschriften]
        for sprache in UEBERSETZUNGEN:
            with self.subTest(sprache=sprache):
                g = hilfe.rendern(self.uebersetzung(sprache))
                ist = [(stufe, text) for stufe, _, text in g.ueberschriften]
                stufen_soll, stufen_ist = [s for s, _ in soll], [s for s, _ in ist]
                if stufen_ist != stufen_soll:
                    nr = next((i for i, (a, b) in enumerate(zip(stufen_soll, stufen_ist)) if a != b),
                              min(len(soll), len(ist)))
                    self.fail(f"README.{sprache}.md: {len(ist)} Überschriften statt {len(soll)}; erste Abweichung bei "
                              f"Nr. {nr + 1}: Original {soll[nr] if nr < len(soll) else '—'}, "
                              f"Übersetzung {ist[nr] if nr < len(ist) else '—'}")

    def test_codebloecke(self):
        for sprache in UEBERSETZUNGEN:
            with self.subTest(sprache=sprache):
                g = hilfe.rendern(self.uebersetzung(sprache))
                self.assertEqual(g.zaeune, self.g_original.zaeune,
                                 f"README.{sprache}.md: Zahl der Codeblöcke (```) weicht ab")

    def test_adressen(self):
        """Dieselben Adressen nach draußen — keine fehlt, keine kommt dazu."""
        soll = _urls(self.original)
        for sprache in UEBERSETZUNGEN:
            with self.subTest(sprache=sprache):
                ist = _urls(self.uebersetzung(sprache))
                self.assertEqual((sorted(soll - ist), sorted(ist - soll)), ([], []),
                                 f"README.{sprache}.md: (fehlen, kommen dazu)")

    def test_anker_treffen(self):
        """Jeder Link auf einen eigenen Abschnitt (#…) trifft eine Überschrift
        derselben Datei — mit den Ankern, die GitHub aus den übersetzten
        Überschriften macht."""
        for sprache in UEBERSETZUNGEN:
            with self.subTest(sprache=sprache):
                g = hilfe.rendern(self.uebersetzung(sprache))
                anker = {a for _, a, _ in g.ueberschriften}
                self.assertEqual([a for a in g.anker if a not in anker], [],
                                 f"README.{sprache}.md: Anker ohne Überschrift (vorhanden: {sorted(anker)[:60]})")
                self.assertEqual(len(g.anker), len(self.g_original.anker),
                                 f"README.{sprache}.md: Zahl der Links auf eigene Abschnitte weicht ab")


class _Bau(HTMLParser):
    """Der Bau einer HTML-Seite: Tags mit Attributnamen (und den Werten, die
    nicht übersetzt werden), dazu der Text ohne <style>/<script>."""
    WERTE = ("href", "src", "id", "class", "xlink:href")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.folge: list = []
        self.texte: list = []
        self.lang = None
        self._weg = 0

    def _tag(self, art, tag, attrs):
        namen = tuple(sorted(n for n, _ in attrs))
        werte = tuple((n, v) for n, v in sorted(attrs, key=lambda x: x[0]) if n in self.WERTE)
        self.folge.append((art, tag, namen, werte))

    def handle_starttag(self, tag, attrs):
        if tag == "html":
            self.lang = dict(attrs).get("lang")
        if tag in ("style", "script"):
            self._weg += 1
        self._tag("<", tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._tag("</>", tag, attrs)

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self._weg = max(0, self._weg - 1)
        self.folge.append((">", tag, (), ()))

    def handle_data(self, data):
        if not self._weg:
            self.texte.append(data)


def _bau(text: str) -> _Bau:
    b = _Bau()
    b.feed(text)
    b.close()
    return b


def zahlen(texte: list) -> collections.Counter:
    """Die Zahlen im Text, gleich geschrieben in jeder Sprache: Dezimalkomma
    wie -punkt (0,55 = 0.55), Tausender mit schmalem Leerzeichen wie mit
    Punkt oder Komma, volle Uhrzeiten ohne „:00“ (15:00 = 15 h)."""
    aus = collections.Counter()
    for t in texte:
        t = re.sub(r"(?<!\d)(\d{1,2}):00(?!\d)", r"\1", t)
        t = re.sub(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)", r"\1 \2", t)
        t = re.sub(r"(\d)[   ](?=\d{3}(?!\d))", r"\1.", t)
        for z in re.findall(r"\d+(?:[.,]\d+)*", t):
            aus[z.replace(",", ".")] += 1
    return aus


class DriftRechnung(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = _bau(hilfe.bewertung_datei("en").read_text(encoding="utf-8"))

    def uebersetzung(self, sprache: str) -> _Bau:
        datei = hilfe.bewertung_datei(sprache)
        if not datei.exists():
            self.skipTest(f"wingscout/hilfe/{datei.name} gibt es noch nicht")
        return _bau(datei.read_text(encoding="utf-8"))

    def test_der_zahlenvergleich_selbst(self):
        self.assertEqual(zahlen(["0,55 und 1.000 bis 15:00, 14:50", "10\u00a0000 €", "v2.1.0"]),
                         zahlen(["0.55 und 1,000 bis 15 h, 14 h 50", "10\u202f000 €", "v2.1.0"]))
        self.assertNotEqual(zahlen(["0,55"]), zahlen(["0,5"]))

    def test_gleicher_bau(self):
        """Dieselben Tags in derselben Folge, dieselben Attribute — und
        dieselben Werte für href, src, id, class, xlink:href."""
        soll = self.original.folge
        for sprache in UEBERSETZUNGEN:
            with self.subTest(sprache=sprache):
                ist = self.uebersetzung(sprache).folge
                if ist != soll:
                    nr = next((i for i, (a, b) in enumerate(zip(soll, ist)) if a != b), min(len(soll), len(ist)))
                    self.fail(f"bewertung.{sprache}.html: {len(ist)} Tags statt {len(soll)}; erste Abweichung bei "
                              f"Tag Nr. {nr + 1}:\n  Original:    {soll[nr] if nr < len(soll) else '—'}\n"
                              f"  Übersetzung: {ist[nr] if nr < len(ist) else '—'}")

    def test_sprache(self):
        self.assertEqual(self.original.lang, "en")
        for sprache in UEBERSETZUNGEN:
            with self.subTest(sprache=sprache):
                self.assertEqual(self.uebersetzung(sprache).lang, sprache)

    def test_gleiche_zahlen(self):
        soll = zahlen(self.original.texte)
        for sprache in UEBERSETZUNGEN:
            with self.subTest(sprache=sprache):
                ist = zahlen(self.uebersetzung(sprache).texte)
                self.assertEqual((dict(soll - ist), dict(ist - soll)), ({}, {}),
                                 f"bewertung.{sprache}.html: (fehlen, kommen dazu) — Zahlen im Text")


if __name__ == "__main__":
    unittest.main()
