"""Sprachen der Oberfläche (seit 2.1.0): Deutsch, Englisch, Französisch, Spanisch.

Quelle ist der deutsche Text im Code. `T("Spots suchen")` liefert ihn in der
gewählten Sprache aus `wingscout/lang/<sprache>.json`; fehlt dort eine
Übersetzung, bleibt es beim deutschen Text — eine Lücke kostet nie die Seite.
Platzhalter stehen in geschweiften Klammern und kommen als Schlüsselwörter:
`T("{n} Spots im Katalog", n=278)`. Einzahl und Mehrzahl: `TN("{n} Warnung",
"{n} Warnungen", n)`. Texte, die erst später übersetzt werden (Tabellen auf
Modulebene), markiert `N_()` fürs Einsammeln und lässt sie unverändert;
übersetzt wird beim Gebrauch mit `T(TABELLE[k])`. Spitze Klammern, die der
deutsche Text nicht hat, bringt eine Übersetzung nicht mit — `t()` macht
`&lt;`/`&gt;` daraus (`ohne_fremde_klammern`), im Browser ebenso.

Texte, die beim Rechnen in Daten landen und später angezeigt werden — im
Report, der seit 2.3.0 in allen vier Sprachen aus einer Suche entsteht —,
kommen aus `TD()`/`TND()`: derselbe Text wie aus `T()`, der sich mit
`uebersetzt()` in einer anderen Sprache neu setzen lässt (Abschnitt „Texte in
Daten“ unten).

Welche Sprache gilt, liegt im Thread: jede Anfrage der Oberfläche setzt sie
(gespeicherte Wahl, sonst die Sprache des Browsers), ein Suchlauf übernimmt
die der Anfrage, die ihn gestartet hat, und die Kommandozeile nimmt die
gespeicherte Wahl oder die des Systems. `WINGSCOUT_SPRACHE` in der Umgebung
legt sie fest — die Tests laufen so immer auf Deutsch.

JavaScript bekommt die Übersetzungen, die es braucht, als `window.T` vor
seinen eigenen Skripten (`js_vorspann()`), dazu `t()` mit denselben
Platzhaltern und `N_()`. Welche Texte das sind, steht in den Skripten selbst:
jedes `t('…')` und `N_('…')` in `wingscout/web/*.js`.

Zahlen und Daten in der Form der Sprache — 4,2 · 4.2, 20.09.2026 19:09 ·
20 Sep 2026, 19:09 — kommen aus `zahl()`, `datum_jahr()` und `datum_zeit()`
am Ende dieser Datei, im Browser aus `zahlFmt()` und `datumZeit()`.

`tools/i18n_texte.py` sammelt alle Quelltexte ein; die Tests prüfen, dass
jede Sprache jeden davon kennt und dieselben Platzhalter und Auszeichnungen
behält.
"""
from __future__ import annotations

import contextlib
import functools
import json
import math
import os
import plistlib
import re
import sys
import threading
from pathlib import Path

SPRACHEN = {"de": "Deutsch", "en": "English", "fr": "Français", "es": "Español"}
QUELLE = "de"                 # die Sprache, in der die Texte im Code stehen
FREMD = "en"                  # wenn der Browser keine der vier spricht

PAKET = Path(__file__).resolve().parent
LANG = PAKET / "lang"
WEB = PAKET / "web"
SPRACH_DATEI = PAKET.parent / "sprache.txt"       # die gespeicherte Wahl (persönlich, nicht versioniert)

_lokal = threading.local()
_kataloge: dict[str, dict[str, str]] = {}
_sperre = threading.Lock()


# ── Welche Sprache gilt ─────────────────────────────────────────────────────

def fest() -> str | None:
    """`WINGSCOUT_SPRACHE` aus der Umgebung — schlägt alles andere."""
    s = (os.environ.get("WINGSCOUT_SPRACHE") or "").strip().lower()
    return s if s in SPRACHEN else None


def gespeichert() -> str | None:
    """Die im Umschalter gewählte Sprache, falls es eine gibt."""
    try:
        s = SPRACH_DATEI.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None
    return s if s in SPRACHEN else None


def speichern(sprache: str) -> str:
    if sprache not in SPRACHEN:
        raise ValueError(f"Unbekannte Sprache: {sprache}")
    SPRACH_DATEI.write_text(sprache + "\n", encoding="utf-8")
    return sprache


def aus_header(accept_language: str | None) -> str | None:
    """Die erste der vier Sprachen, die der Browser nennt — nach Gewicht.
    `de-CH,de;q=0.9,en;q=0.8` → de; `it-IT,it;q=0.9` → None."""
    kandidaten = []
    for nr, teil in enumerate((accept_language or "").split(",")):
        teil = teil.strip()
        if not teil:
            continue
        code, _, rest = teil.partition(";")
        q = 1.0
        m = re.search(r"q\s*=\s*([0-9.]+)", rest)
        if m:
            try:
                q = float(m.group(1))
            except ValueError:
                q = 0.0
        if q <= 0:                       # q=0 heißt „bitte nicht“
            continue
        kandidaten.append((-q, nr, code.strip().lower()[:2]))
    for _, _, code in sorted(kandidaten):
        if code in SPRACHEN:
            return code
    return None


def aus_umgebung() -> str | None:
    """Die Sprache des Systems (LC_ALL, LC_MESSAGES, LANG), falls eine der vier."""
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        code = (os.environ.get(name) or "").strip().lower()[:2]
        if code in SPRACHEN:
            return code
    return None


def aus_macos() -> str | None:
    """Die erste der vier Sprachen aus den Systemeinstellungen eines Macs
    (AppleLanguages). Ein doppelgeklicktes Terminal setzt LANG nicht immer;
    dieselbe Regel nimmt tools/sprache.sh für die Zeilen der Startdateien.
    Gelesen wird die Einstellungsdatei selbst — kein `defaults`-Aufruf, die
    Sicherheitsregeln verbieten fremde Prozesse (tests/test_security.py)."""
    if sys.platform != "darwin":
        return None
    try:
        with open(Path.home() / "Library" / "Preferences" / ".GlobalPreferences.plist", "rb") as f:
            daten = plistlib.load(f)
    except Exception:                                         # noqa: BLE001 — dann eben nicht
        return None
    for eintrag in (daten.get("AppleLanguages") if isinstance(daten, dict) else None) or []:
        code = str(eintrag).strip().lower()[:2]
        if code in SPRACHEN:
            return code
    return None


def fuer_anfrage(accept_language: str | None) -> str:
    """Was für eine Anfrage der Oberfläche gilt — und setzt es im Thread."""
    return setze(fest() or gespeichert() or aus_header(accept_language)
                 or (FREMD if accept_language else QUELLE))


def fuer_kommandozeile(wahl: str | None = None) -> str:
    """Für Terminal und Kommandozeile: --sprache, sonst die gespeicherte Wahl,
    sonst die des Systems — und Englisch, wenn keine der vier passt, wie in
    tools/sprache.sh."""
    return setze(fest() or (wahl if wahl in SPRACHEN else None) or gespeichert()
                 or aus_umgebung() or aus_macos() or FREMD)


def setze(sprache: str | None) -> str:
    _lokal.sprache = sprache if sprache in SPRACHEN else QUELLE
    return _lokal.sprache


def aktuell() -> str:
    s = getattr(_lokal, "sprache", None)
    if s:
        return s
    return fest() or gespeichert() or QUELLE


@contextlib.contextmanager
def in_sprache(sprache: str):
    """Für die Dauer des Blocks gilt `sprache` in diesem Thread, danach genau
    das, was vorher galt — auch „nichts gesetzt“ (dann entscheiden wieder
    Umgebung und gespeicherte Wahl). Für den Report in den anderen Sprachen
    (seit 2.3.0)."""
    vorher = getattr(_lokal, "sprache", None)
    setze(sprache)
    try:
        yield _lokal.sprache
    finally:
        if vorher is None:
            try:
                del _lokal.sprache
            except AttributeError:
                pass
        else:
            _lokal.sprache = vorher


# ── Übersetzen ──────────────────────────────────────────────────────────────

def katalog(sprache: str) -> dict[str, str]:
    if sprache == QUELLE or sprache not in SPRACHEN:
        return {}
    with _sperre:
        if sprache not in _kataloge:
            try:
                daten = json.loads((LANG / f"{sprache}.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                daten = {}
            if not isinstance(daten, dict):          # z. B. eine Liste: lieber Deutsch als ein Absturz
                daten = {}
            _kataloge[sprache] = {k: v for k, v in daten.items() if isinstance(v, str) and v}
        return _kataloge[sprache]


def neu_laden() -> None:
    """Kataloge beim nächsten Zugriff frisch lesen (Tests, Übersetzer)."""
    with _sperre:
        _kataloge.clear()
    _OHNE_WERTE.clear()
    global _JS_SCHLUESSEL
    _JS_SCHLUESSEL = None


def t(text: str, /, **werte) -> str:
    """`text` in der gültigen Sprache, mit eingesetzten Platzhaltern.
    (`text` nur nach Stelle, damit ein Platzhalter `{text}` gehen kann.)"""
    s = aktuell()
    ziel = text
    if s != QUELLE:                        # Deutsch ist die Quelle: kein Nachschlagen, nichts ersetzt
        uebersetzt = katalog(s).get(text)
        if uebersetzt is not None:
            ziel = ohne_fremde_klammern(text, uebersetzt)
    if not werte:
        return ziel
    try:
        return ziel.format(**werte)
    except Exception:                      # noqa: BLE001 — z. B. {n[0]} oder {n.x} in einer Übersetzung
        return text.format(**werte)        # lieber Deutsch als eine kaputte Zeile


def ohne_fremde_klammern(quelle: str, uebersetzung: str) -> str:
    """Die Übersetzung mit den spitzen Klammern, die der deutsche Text hat —
    keine weiteren: `<` wird `&lt;`, wenn der deutsche Text kein `<` enthält,
    `>` ebenso `&gt;`.

    Die meisten Texte landen als HTML in der Seite — im Report, in den Zeilen
    der Katalogtabelle (`innerHTML`). Bis 2.1.0 reichte dort eine Übersetzung
    wie „rename <!--“: der Rest der Zeile wurde Kommentar, die Katalogseite
    zeigte noch eine von 277 Zeilen, der Report verlor seinen Text und seine
    Skripte (B1). Die Kataloge prüft ein Test (gleiche Tags, kein `<` oder `>`
    mehr als im Deutschen) — dies ist die zweite Sicherung, dort, wo der Text
    gebraucht wird. Texte mit Auszeichnung („<b>Lücken:</b> …“) bleiben, wie
    sie sind; ihre Tags hält der Test fest. Ersetzt wird in der Übersetzung
    vor dem Einsetzen, nie in den eingesetzten Werten — die escapt, wer sie
    einsetzt. Für jede Übersetzung, die den Test besteht, ändert sich nichts.
    Dieselbe Regel gilt im Browser (`t()` in `js_vorspann()`)."""
    if "<" not in quelle:
        uebersetzung = uebersetzung.replace("<", "&lt;")
    if ">" not in quelle:
        uebersetzung = uebersetzung.replace(">", "&gt;")
    return uebersetzung


def tn(einzahl: str, mehrzahl: str, /, n: int, **werte) -> str:
    """Einzahl für n == 1, sonst Mehrzahl; `n` steht als Platzhalter bereit."""
    return t(einzahl if n == 1 else mehrzahl, n=n, **werte)


# Im Code heißen sie T(), TN() und N_(): `t` ist in Report und Suche schon
# der Name für ein Ziel oder eine Uhrzeit, und ein Import mit diesem Namen
# würde von jeder Schleife überdeckt.
T = t
TN = tn


def N_(text: str) -> str:
    """Markiert einen Text fürs Einsammeln, ohne ihn zu übersetzen — für
    Tabellen auf Modulebene; übersetzt wird beim Gebrauch mit `t(TABELLE[k])`."""
    return text


# ── Texte in Daten ──────────────────────────────────────────────────────────
# Seit 2.3.0 schreibt eine Suche ihren Report in allen vier Sprachen, und der
# Reiter „Ziele“ folgt dem Umschalter ohne neue Suche. Bis dahin entstand der
# Report einmal, in der Sprache beim Start der Suche — wer danach umschaltete,
# sah „Ziele“ weiter in der alten (gemeldet am 04.10.2026).
#
# Gerechnet wird einmal, geschrieben viermal. Was beim Rechnen als Text in die
# Daten wandert — das Veto einer Stunde, die Hinweise einer Session, warum ein
# Spot nicht berücksichtigt ist, die Himmelsrichtung, die Art eines
# Stellplatzes —, entsteht deshalb mit `TD()` statt `T()`: als Text genau
# derselbe, dazu mit dem Rezept, ihn in einer anderen Sprache neu zu setzen.
# Der Report schickt solche Texte durch `uebersetzt()` (report._esc tut es
# für alles, was es escaped). Ob nichts vergessen ist, prüft
# tests/test_report_sprachen.py: eine Demo-Suche, auf Deutsch gerechnet und
# auf Englisch, Französisch und Spanisch geschrieben, muss Zeichen für Zeichen
# dem Report gleichen, den eine Suche in der jeweiligen Sprache schreibt.


class Text(str):
    """Ein Text aus `TD()`/`TND()` (oder `spaeter()`): als `str` genau das,
    was `T()` geliefert hätte — er vergleicht, sortiert, hasht und landet in
    JSON wie dieser —, dazu `neu`, das ihn in der jeweils geltenden Sprache neu
    setzt, und `sprache`, in der er entstand.

    Was mit ihm weiterrechnet (`+`, `join`, `format`, `html.escape`), bekommt
    einen gewöhnlichen `str` in der Sprache von damals: neu gesetzt wird nur,
    was vorher durch `uebersetzt()` geht."""

    def __new__(cls, wortlaut: str = "", neu=None, sprache: str | None = None):
        obj = super().__new__(cls, wortlaut)
        obj.neu = neu
        obj.sprache = sprache
        return obj

    def __reduce__(self):                      # copy.deepcopy und pickle: mit Rezept
        return (Text, (str(self), self.neu, self.sprache))


class _Rezept:
    """Wie ein Text aus `TD()` entstand: Vorlage (mit Mehrzahl) und Werte.
    Ein Wert, der selbst ein solcher Text ist, wird mit neu gesetzt."""
    __slots__ = ("vorlage", "mehrzahl", "werte")

    def __init__(self, vorlage: str, mehrzahl: str | None, werte: dict):
        self.vorlage, self.mehrzahl, self.werte = vorlage, mehrzahl, werte

    def __call__(self) -> str:
        werte = {k: uebersetzt(v) for k, v in self.werte.items()}
        if self.mehrzahl is None:
            return t(self.vorlage, **werte)
        return tn(self.vorlage, self.mehrzahl, **werte)

    def __reduce__(self):
        return (_Rezept, (self.vorlage, self.mehrzahl, self.werte))


# Ohne Werte ist ein Text je Sprache immer derselbe: einmal angelegt statt je
# Stunde („außerhalb der Tageslichtzeit“ steht an jeder Nachtstunde).
_OHNE_WERTE: dict[tuple[str, str], Text] = {}


def td(text: str, /, **werte) -> Text:
    """Wie `t()`, für Texte, die in Daten landen und später in einer anderen
    Sprache gezeigt werden können (siehe oben)."""
    s = aktuell()
    if not werte:
        fertig = _OHNE_WERTE.get((s, text))
        if fertig is None:
            fertig = _OHNE_WERTE[(s, text)] = Text(t(text), _Rezept(text, None, {}), s)
        return fertig
    return Text(t(text, **werte), _Rezept(text, None, werte), s)


def tnd(einzahl: str, mehrzahl: str, /, n: int, **werte) -> Text:
    """Wie `tn()`, für Texte in Daten (siehe `td()`)."""
    return Text(tn(einzahl, mehrzahl, n, **werte), _Rezept(einzahl, mehrzahl, dict(werte, n=n)), aktuell())


def spaeter(funktion, /, *args) -> Text:
    """`funktion(*args)` als Text, der sich in einer anderen Sprache neu
    rechnet — für Werte, deren Form an der Sprache hängt (eine Uhrzeit aus
    `stunde()`, eine Zahl aus `zahl()`) und die in einem `TD()` stehen."""
    return Text(funktion(*args), functools.partial(funktion, *args), aktuell())


def uebersetzt(wert):
    """Ein Text aus `TD()`, `TND()` oder `spaeter()` in der jetzt geltenden
    Sprache — neu gesetzt, wenn er in einer anderen entstand. Alles andere
    kommt unverändert zurück."""
    if not isinstance(wert, Text) or wert.neu is None or wert.sprache == aktuell():
        return wert
    try:
        return wert.neu()
    except Exception:                          # noqa: BLE001 — lieber der Wortlaut von damals als keine Seite
        return str(wert)


def vorlage(wert) -> str | None:
    """Die deutsche Vorlage eines Texts aus `TD()`/`TND()` (die Einzahl) —
    sonst None. Für die seltene Frage, *welcher* Satz es war, ohne den
    Wortlaut einer Sprache zu vergleichen (cli: ist ein Favorit wegen der
    Entfernung draußen?)."""
    rezept = getattr(wert, "neu", None) if isinstance(wert, Text) else None
    return rezept.vorlage if isinstance(rezept, _Rezept) else None


TD = td
TND = tnd


MELDUNG_LAENGE = 60


def meldungswert(wert, laenge: int = MELDUNG_LAENGE) -> str:
    """Ein Wert aus einer Datei für eine Fehlermeldung — ein Spotname, eine
    Winggröße, der ganze Eintrag, wenn ihm der Name fehlt: auf einer Zeile,
    ohne Steuer- und Formatzeichen, ohne einzelne Surrogate, höchstens
    `laenge` Zeichen.

    Die Meldung steht im Terminal und auf der Fehlerseite im Browser. Ein
    `"Bad \\uD800 name"` in einem Eintrag ohne `lon` (oder eine Winggröße
    `"x\\uD800"`) ließ bis 2.1.0 genau diese Fehlerseite scheitern: sie ließ
    sich nicht als UTF-8 schreiben, die Verbindung riss ab — auf Katalog,
    Tagebuch, Prüfseite, beim Quiver auch auf der Startseite (C2). Ein
    Escape-Zeichen im Namen hätte dazu das Terminal umgestellt. Ein sauberer
    kurzer Wert bleibt, wie er ist: `str(wert)`."""
    try:
        text = str(wert)
    except ValueError:                  # ab Python 3.11: eine Zahl mit zu vielen Stellen für einen Text
        return "…"
    # Leerraum jeder Art wird ein Leerzeichen, alles andere Unsichtbare fällt weg
    text = " ".join("".join(c if c.isprintable() else " " if c.isspace() else "" for c in text).split())
    return text if len(text) <= laenge else text[:laenge - 1].rstrip() + "…"


# ── Datum ───────────────────────────────────────────────────────────────────
# Feste Kürzel statt strftime("%a"): die Locale eines doppelgeklickten Pythons
# ist unter macOS „C“ (siehe report._tag, 1.6.x).

WOCHENTAGE = {                                    # Montag zuerst, wie datetime.weekday()
    "de": ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    "fr": ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."),
    "es": ("lun", "mar", "mié", "jue", "vie", "sáb", "dom"),
}
MONATE = {
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    "fr": ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."),
    "es": ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"),
}


def wochentag(dt) -> str:
    return WOCHENTAGE[aktuell()][dt.weekday()]


def datum(dt) -> str:
    """Tag und Monat kurz: 03.10. · 3 Oct · 3 oct. · 3 oct"""
    s = aktuell()
    if s == "de":
        return dt.strftime("%d.%m.")
    return f"{dt.day} {MONATE[s][dt.month - 1]}"


def stunde(wert) -> str:
    """Eine volle Stunde für „{von}–{bis} Uhr“ und „{stunde} Uhr“: auf Deutsch
    die Zahl allein wie bisher („08“; aus einer Zahl „13“), in den anderen
    Sprachen als Uhrzeit („08:00“, „13:00“) — dort kommt der Text ohne „Uhr“
    aus und sieht so aus wie die Uhrzeiten mit Minuten aus dem Tagebuch."""
    deutsch = aktuell() == QUELLE
    if hasattr(wert, "strftime"):
        return wert.strftime("%H") if deutsch else wert.strftime("%H:%M")
    zahl_ = float(wert)
    if deutsch:
        return f"{zahl_:.0f}"
    # `nan`/`inf` aus einem kaputten Katalogwert (`from: .nan`): ein Strich
    # statt eines Absturzes — bis 2.1.0 brach daran nur der Report in en/fr/es
    # ab, `int(round(nan))` wirft; die deutsche Zeile oben rechnet nicht.
    if not math.isfinite(zahl_):
        return "–"
    return f"{int(round(zahl_)):02d}:00"


def tag(dt) -> str:
    """Wochentag und Datum: Sa 03.10. · Sat 3 Oct · sam. 3 oct. · sáb 3 oct"""
    return f"{wochentag(dt)} {datum(dt)}"


# ── JavaScript ──────────────────────────────────────────────────────────────

_JS_SCHLUESSEL: set[str] | None = None
_JS_TEXT = re.compile(r"""\b(?:t|N_)\(\s*(?:'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)")""")


def _js_unescape(s: str) -> str:
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s)


def js_texte(code: str) -> list[str]:
    """Alle Texte in `t('…')` und `N_('…')` eines Skripts."""
    return [_js_unescape(a if a else b) for a, b in _JS_TEXT.findall(code)]


def js_schluessel() -> set[str]:
    global _JS_SCHLUESSEL
    if _JS_SCHLUESSEL is None:
        gesammelt: set[str] = set()
        for datei in sorted(WEB.glob("*.js")):
            gesammelt.update(js_texte(datei.read_text(encoding="utf-8")))
        _JS_SCHLUESSEL = gesammelt
    return _JS_SCHLUESSEL


def endlich(wert):
    """NaN und ±Unendlich als None — in Wörterbüchern, Listen und Tupeln,
    beliebig tief; alles andere bleibt, wie es ist."""
    if isinstance(wert, float):
        return wert if math.isfinite(wert) else None
    if isinstance(wert, dict):
        return {k: endlich(v) for k, v in wert.items()}
    if isinstance(wert, (list, tuple)):
        return [endlich(v) for v in wert]
    return wert


def json_endlich(wert, **optionen) -> str:
    """`json.dumps(wert, **optionen)` — nur ohne NaN und Infinity: eine Zahl,
    die keine ist, steht als `null` da.

    Python schreibt sie als `NaN`/`Infinity`. Das ist kein JSON (JSON.parse
    verwirft das Ganze), und in einem <script> ist es zwar JavaScript, aber
    ein `Infinity` aus einer alten `cache/rueckblick.json` ließ das Diagramm
    des Rückblicks ohne Ende Gitterlinien zeichnen — der Reiter hing (2.1.0).
    Der Umweg über `endlich()` nur, wenn es nötig ist: der Regelfall bleibt
    Byte für Byte, was `json.dumps` schreibt."""
    try:
        return json.dumps(wert, allow_nan=False, **optionen)
    except ValueError:
        return json.dumps(endlich(wert), allow_nan=False, **optionen)


def json_im_skript(wert) -> str:
    """JSON, das wörtlich in einem <script>-Block stehen darf — für alle
    Daten, die eine Seite oder der Report in ein Skript schreibt (Vorspann,
    Katalog, Prüfseite, Rückblick, Tagebuch, Startseite, Karte des Reports).

    `<`, `>` und `&` als Unicode-Escapes: dann ergibt kein Text darin Markup.
    Bis 2.1.0 ersetzte der Vorspann nur `</` — eine Übersetzung mit
    `<!--<script` brachte den HTML-Tokenizer trotzdem in den Zustand „script
    data double escaped“, in dem das nächste `</script>` den Block nicht mehr
    schließt: jede Seite, jeder Report stand dann ohne Skript da. U+2028/U+2029
    dazu, weil ältere JavaScript-Engines sie in Zeichenketten als Zeilenende
    lesen. JSON.parse und JavaScript lesen die Escapes als dieselben Zeichen.
    NaN und ±Unendlich als `null` (`json_endlich`)."""
    return (json_endlich(wert, ensure_ascii=False)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def js_vorspann(sprache: str | None = None) -> str:
    """JavaScript vor allen anderen Skripten einer Seite: die Übersetzungen,
    die die Skripte brauchen, `t()`, `N_()`, die Datumskürzel und die
    Zahlen- und Datumsformen der Sprache (`zahlFmt()`, `datumZeit()`)."""
    s = sprache or aktuell()
    kat = katalog(s)
    tabelle = {k: kat[k] for k in sorted(js_schluessel()) if k in kat}
    wt = WOCHENTAGE[s]
    daten = {"sprache": s, "wt": [wt[6]] + list(wt[:6]),          # Sonntag zuerst wie Date.getDay()
             "monate": list(MONATE.get(s, ())),
             "locale": LOCALE[s], "dezimal": DEZIMAL[s], "vor_uhrzeit": VOR_UHRZEIT[s]}
    return ("window.T=" + json_im_skript(tabelle) + ";window.I18N=" + json_im_skript(daten) + ";"
            # Keine zwei schließenden Klammern hintereinander: die Tests suchen
            # nach „}}“ als Zeichen einer unaufgelösten Vorlage. Wie t() oben:
            # eine Übersetzung bringt keine spitzen Klammern mit, die der
            # deutsche Text nicht hat (ohne_fremde_klammern) — ersetzt vor dem
            # Einsetzen, nie in den Werten; ohne Übersetzung bleibt der Text.
            "window.t = function (s, p) { var r = s;"
            " if (window.T && Object.prototype.hasOwnProperty.call(window.T, s)) { r = String(window.T[s]);"
            " if (String(s).indexOf('<') < 0) r = r.split('<').join('&lt;');"
            " if (String(s).indexOf('>') < 0) r = r.split('>').join('&gt;'); }"
            " if (p) { for (var k in p) { if (Object.prototype.hasOwnProperty.call(p, k)) { r = r.split('{' + k + '}').join(String(p[k])); } } }"
            " return r; };"
            " window.N_ = function (s) { return s; };"
            " window.tagKurz = function (d) { var I = window.I18N, m = I.monate;"
            " var tg = ('0' + d.getDate()).slice(-2), mo = ('0' + (d.getMonth() + 1)).slice(-2);"
            " return I.wt[d.getDay()] + ' ' + (I.sprache === 'de' ? tg + '.' + mo + '.' : d.getDate() + ' ' + m[d.getMonth()]); };"
            # Wie zahl() unten: ohne `stellen` die Zahl, wie JavaScript sie
            # schreibt, mit dem Dezimalzeichen der Sprache (1,5 · 1.5); mit
            # `stellen` höchstens so viele Nachkommastellen, mindestens
            # `mindestens`, Tausender wie toLocaleString (1.234,5 · 1,234.5 ·
            # 1 234,5 · 1234,5 und 12.345,5 im Spanischen).
            " window.zahlFmt = function (v, stellen, mindestens) { var I = window.I18N;"
            " if (stellen == null) return String(v).replace('.', I.dezimal);"
            " return Number(v).toLocaleString(I.locale, {maximumFractionDigits: stellen, minimumFractionDigits: mindestens || 0}); };"
            # Wie datum_zeit() unten, aus „2026-09-20T19:09“: 20.09.2026 19:09 ·
            # 20 Sep 2026, 19:09 · 20 sept. 2026 19:09 · 20 sep 2026 19:09; ein
            # Datum ohne Uhrzeit bleibt ohne. Was nicht so aussieht, bleibt stehen.
            r" window.datumZeit = function (iso) { var I = window.I18N, m = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}:\d{2}))?/);"
            " if (!m) return iso || '';"
            " var mo = I.monate[Number(m[2]) - 1];"
            " if (I.sprache !== 'de' && !mo) return iso;"
            " return (I.sprache === 'de' ? m[3] + '.' + m[2] + '.' + m[1] : Number(m[3]) + ' ' + mo + ' ' + m[1])"
            " + (m[4] ? I.vor_uhrzeit + m[4] : ''); };")


# ── Zahlen und Datum mit Jahr ───────────────────────────────────────────────
# Was auf Deutsch ein Dezimalkomma, Tausenderpunkte oder ein Datum wie
# „20.09.2026“ trägt, steht in jeder Sprache in ihrer Form. Zahlen, die auch
# auf Deutsch mit Punkt dastehen (Wingrößen „4.2–6.5 m²“, Fahrzeit „1.5 h“),
# bleiben überall so. Im Browser dasselbe: `zahlFmt()` und `datumZeit()` aus
# `js_vorspann()`, mit den Monatskürzeln aus MONATE.

DEZIMAL = {"de": ",", "en": ".", "fr": ",", "es": ","}
# Tausender wie toLocaleString() im Browser: Französisch mit schmalem
# geschütztem Leerzeichen (U+202F), Spanisch erst ab fünf Stellen vor dem
# Komma (1234, aber 12.345).
TAUSENDER = {"de": ".", "en": ",", "fr": " ", "es": "."}
GRUPPE_AB = {"de": 4, "en": 4, "fr": 4, "es": 5}
LOCALE = {"de": "de-DE", "en": "en-GB", "fr": "fr-FR", "es": "es-ES"}    # für toLocaleString()
VOR_UHRZEIT = {"de": " ", "en": ", ", "fr": " ", "es": " "}             # 20 Sep 2026, 19:09


def zahl(x, stellen: int | None = None, gruppen: bool = False) -> str:
    """Eine Zahl für Text auf der Seite: 4,2 · 4.2 · 4,2 · 4,2.

    Mit `stellen` genau so viele Nachkommastellen, sonst ohne überflüssige
    Nullen (wie `:g`). Tausender trennt nur `gruppen=True`: 12.345,5 ·
    12,345.5 · 12 345,5 · 12.345,5 — ohne steht 12345,5, wie bisher."""
    s = aktuell()
    text = f"{float(x):.{stellen}f}" if stellen is not None else f"{float(x):g}"
    ganz, punkt, rest = text.partition(".")
    ziffern = ganz.lstrip("-")
    if gruppen and ziffern.isdigit() and len(ziffern) >= GRUPPE_AB[s]:
        ganz = ganz[:len(ganz) - len(ziffern)] + f"{int(ziffern):,}".replace(",", TAUSENDER[s])
    return ganz + (DEZIMAL[s] + rest if punkt else "")


def datum_jahr(dt) -> str:
    """Tag, Monat und Jahr: 18.09.2026 · 18 Sep 2026 · 18 sept. 2026 · 18 sep 2026"""
    if aktuell() == "de":
        return dt.strftime("%d.%m.%Y")
    return f"{datum(dt)} {dt.year}"


def datum_zeit(dt) -> str:
    """Datum mit Jahr und Uhrzeit: 20.09.2026 19:09 · 20 Sep 2026, 19:09 ·
    20 sept. 2026 19:09 · 20 sep 2026 19:09"""
    return datum_jahr(dt) + VOR_UHRZEIT[aktuell()] + dt.strftime("%H:%M")
