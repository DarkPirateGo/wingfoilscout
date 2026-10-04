"""Wingfoilscout · Oberfläche im Browser.

Startet einen kleinen Server auf dem eigenen Rechner, zeigt ein Formular mit
allen Parametern und den fertigen Report darunter. Nur Standardbibliothek —
kein Flask, kein Node, nichts zu installieren.

    python3 -m wingscout.webui            # öffnet http://127.0.0.1:8765
"""
from __future__ import annotations
import argparse
import contextlib
import copy
import hmac
import secrets
import socket
import sys
import html
import json
import math
import os
import re
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__
from . import csp
from . import i18n
from .i18n import T, TN, N_                                       # noqa: F401
from .config import load_config, quiver_range, KonfigFehler
from .spots import KatalogFehler
from .geo import parse_position
from .cli import run_search
from . import instagram
from . import zeitraum
from .report import KOMMENTAR_CSS, KOMMENTAR_JS, kommentar_kasten, fassung as report_fassung

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS_FILE = ROOT / "ui_defaults.json"
REPORT_FILE = ROOT / "report.html"
SPOTS_FILE = ROOT / "spots.yaml"
GEOMETRY_FILE = ROOT / "geometry.json"

# Leaflet von cdnjs, mit Prüfsumme: ohne `integrity` liefe jedes Skript, das
# der CDN-Server ausliefert, mit den Rechten dieser Seite — und die darf den
# Katalog beschreiben und den Server beenden. Die Prüfsummen stehen einmal
# hier, damit die Prüfseite und das Nachladen auf der Startseite dieselben
# nutzen; ändert cdnjs die Dateien, lädt die Karte nicht mehr (siehe TODO).
LEAFLET_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"
LEAFLET_CSS_SRI = "sha384-c6Rcwz4e4CITMbu/NBmnNS8yN2sC3cUElMEMfP3vqqKFp7GOYaaBBCqmaWBjmkjb"
LEAFLET_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"
LEAFLET_JS_SRI = "sha384-NElt3Op+9NBMCYaef5HxeJmU4Xeard/Lku8ek6hoPTvYkQPh3zLIrJP7KiRocsxO"

# CSS und JavaScript der Oberfläche liegen seit 1.16.0 als eigene Dateien in
# wingscout/web/ — ein Editor liest sie als das, was sie sind, `node --check`
# prüft das JavaScript (tools/check.sh), und geschweifte Klammern müssen nicht
# mehr verdoppelt werden. Gelesen wird einmal beim Start, wie vorher die
# Konstanten. Nur page() bleibt eine f-Vorlage für das HTML der Startseite;
# ihr Skript steht in web/suche.js und bekommt Heimat und Kartenbibliothek
# über `start_js` davor.
from . import WEB, lies_web as _web                               # noqa: E402,F401
from . import SPOT_FORMULAR                                         # noqa: E402


SUCHE_JS = _web("suche.js")
# Klappt am Handy zusammen, was am Rechner ausgeschrieben dasteht (lange
# Erklärungen, Karte, Parameter) — siehe web/mobil.js.
# Am Ende jeder Seite: mobil.js (klappt am Handy zusammen), beenden.js (der
# Knopf „Beenden“ in der Reiterleiste, seit 1.18.2 auf jeder Seite) und
# lauf.js (der Punkt am Reiter, wenn etwas läuft, seit 1.18.3).
MOBIL_JS_ROH = ("\n" + _web("mobil.js") + "\n" + _web("beenden.js") + "\n" + _web("lauf.js")
                + "\n" + _web("sprache.js"))

# ── Nonce je Antwort (Content-Security-Policy, seit 1.19.1) ──────────────────
# Jede Antwort würfelt eine Nonce; jeder <script>-Block der Seite trägt sie,
# die Kopfzeile nennt sie — nur so laufen die Skripte. Sie liegt im Thread,
# weil jede Anfrage in ihrem eigenen bearbeitet wird und die Seitenbauer sie
# so ohne Umbau jeder Signatur finden. Wer eine Seite ohne Anfrage baut
# (Tests), bekommt eine frische. Siehe wingscout/csp.py.
_NONCE = threading.local()


def nonce_neu() -> str:
    _NONCE.wert = csp.neue_nonce()
    return _NONCE.wert


def nonce() -> str:
    return getattr(_NONCE, "wert", None) or nonce_neu()


def skript(code: str) -> str:
    """Ein <script>-Block mit der Nonce dieser Antwort."""
    return csp.skript(nonce(), code)


def mobil_js() -> str:
    """Am Ende jeder Seite: mobil.js, beenden.js, lauf.js — mit Nonce."""
    return skript(MOBIL_JS_ROH)


# Das Logo des Erstellers (seit 1.19.1): wie die Symbole eine PNG-Datei aus
# web/, ausgeliefert unter dieser Adresse — `img-src 'self'` der Richtlinie
# lässt sie zu. 400 × 109 px mit 256 Farben (33 kB); gezeigt wird es 26 px hoch.
LOGO_DATEI = "/logo.png"

# Die Hilfe: Anleitung (README) und „Wie Wingfoilscout rechnet“
# (docs/bewertung.html) — gerendert in wingscout/hilfe.py, die Seiten unten
# (`hilfe_page`, `rechnung_page`), erreichbar über das „?“ in der Leiste.
from .hilfe import ANLEITUNG_PFAD as HILFE_PFAD, RECHNUNG_PFAD          # noqa: E402


def marke() -> str:
    """Logo des Erstellers und Versionsnummer — rechts in der Reiterleiste am
    Rechner, im Fuß der Seite am Handy (seit 1.19.1; welche von beiden zu
    sehen ist, entscheidet das CSS). Die Nummer ist die des laufenden
    Prozesses: liegt auf der Platte schon eine neuere, sagt das
    `neustart_hinweis()` gleich unter der Leiste. In der Leiste steht sie
    klein unter dem Logo (reiter.css), damit die Leiste mit dem Knopf „?“ in
    allen vier Sprachen eine Zeile bleibt; im Fuß daneben."""
    v = html.escape(__version__)
    return (f"<span class='marke' title='{html.escape(T('Wingfoilscout {version} · erstellt von DARK', version=v))}'>"
            f"<img src='{LOGO_DATEI}' alt='DARK' height='26'>"
            f"<span class='version'>v{v}</span></span>")


def sprachwahl() -> str:
    """Der Umschalter DE · EN · FR · ES (seit 2.1.0) — neben Logo und Version,
    also oben in der Leiste am Rechner und im Fuß am Handy. Die Wahl gilt für
    alle Seiten und für den nächsten Report (`web/sprache.js`, POST /sprache).
    Bis 2.1.0 stand er in der Marke; jetzt daneben, weil die Marke in der
    Leiste Logo und Nummer übereinander stellt."""
    jetzt = i18n.aktuell()
    optionen = "".join(
        f"<option value='{k}' title='{html.escape(name)}'{' selected' if k == jetzt else ''}>{k.upper()}</option>"
        for k, name in i18n.SPRACHEN.items())
    return (f"<select class='sprachwahl' aria-label='{html.escape(T('Sprache'))}' "
            f"title='{html.escape(T('Sprache'))}'>{optionen}</select>")


def seitenende() -> str:
    """Das Ende jeder Seite der Oberfläche: der Fuß mit Logo und Version, das
    schließende `</div>` des `.wrap`, dann die Skripte (`mobil_js()`). Der
    Fuß ist am Handy die Stelle für die Marke — die Leiste sitzt dort unten
    und hat keinen Platz dafür; am Rechner steht sie oben in der Leiste, und
    der Fuß bleibt unsichtbar."""
    return "<footer class='seitenfuss'>" + marke() + sprachwahl() + "</footer></div>" + mobil_js()


def hilfe_knopf(aktiv: str) -> str:
    """Das runde „?“ in der Leiste, zwischen Sprache und „Beenden“: führt zur
    Anleitung und zu „Wie Wingfoilscout rechnet“ (`hilfe_page`,
    `rechnung_page`). Auf den Hilfeseiten ist es hervorgehoben — dort steht
    kein Reiter auf „an“. Am Handy sitzt es fest oben rechts neben „Beenden“
    (reiter.css)."""
    hier = " aria-current='page'" if aktiv.startswith(HILFE_PFAD) else ""
    return (f"<a href='{HILFE_PFAD}' class='hilfeknopf' title='{html.escape(T('Hilfe'))}' "
            f"aria-label='{html.escape(T('Hilfe'))}'{hier}>?</a>")

# Als Web-App auf dem Home-Bildschirm: Safari nimmt dafür das Manifest und
# `apple-touch-icon`. Seit Safari 26 öffnet jede hinzugefügte Seite ohnehin als
# Web-App; das Manifest bestimmt Name, Startadresse und Farben.
MANIFEST = json.dumps({
    "name": "Wingfoilscout", "short_name": "Wingfoilscout", "start_url": "/", "scope": "/",
    "display": "standalone", "orientation": "portrait-primary", "lang": "de",
    "background_color": "#F2F4F5", "theme_color": "#AE1F68",
    "description": "Wingfoil-Spots im Umkreis: wo es weht, wann, mit welchem Wing.",
    "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
              {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
              {"src": "/icon-512-maskable.png", "sizes": "512x512", "type": "image/png",
               "purpose": "maskable"}]}, ensure_ascii=False, indent=1)
SYMBOLE_DATEIEN = {"/icon-180.png", "/icon-192.png", "/icon-512.png", "/icon-512-maskable.png"}
# Alles, was der Server als Bild ausliefert — eine feste Liste, keine
# Verzeichnisfreigabe: andere Namen unter web/ bleiben unerreichbar.
BILD_DATEIEN = SYMBOLE_DATEIEN | {LOGO_DATEI}

WATER_TYPES = [("sea", N_("Meer")), ("lagoon", N_("Lagune")), ("lake", N_("See")), ("reservoir", N_("Stausee"))]
GRASS = [("heavy", N_("nur starken Bewuchs")), ("some", N_("auch mäßigen Bewuchs")), ("none", N_("jeden Bewuchs"))]

# `seit`/`ende`: Unix-Sekunden von Start und Ende des letzten Laufs — die
# Seiten zeigen damit „läuft seit …“ bzw. „fertig um …“, und der Reiter
# „Ziele“ weiß, ob der Report jünger ist als die Seite, die ihn anzeigt.
JOB = {"state": "idle", "log": [], "error": None, "summary": "", "kind": "run", "seit": None, "ende": None}
SERVER = {"instance": None}
PORT = {"nr": 8765}                  # für die Adresse, die dem iPhone angezeigt wird
LOCK = threading.Lock()
# Wie viele Anfragen der Prüfseite gerade in `spots.yaml`/`geometry.json`
# schreiben — unter LOCK gezählt, damit kein Hintergrundlauf startet, während
# eine Korrektur halb geschrieben ist, und keine Korrektur, während ein Lauf
# dieselben Dateien beschreibt. Bis 1.6.1 stand hier nichts: „Fehlende
# berechnen“ speicherte nach jedem Spot, die Prüfseite las, änderte, schrieb —
# wer beides gleichzeitig tat, verlor eines von beiden.
PRUEFEN_AKTIV = {"n": 0}

# ── Zugang vom Handy (seit 1.17.0) ───────────────────────────────────────────
# Wingfoilscout hört normalerweise nur auf 127.0.0.1: was auf dem Mac läuft,
# erreicht nur der Mac. Mit `--lan` hört er auf allen Adressen, damit das
# iPhone im selben WLAN drankommt — und damit auch jedes andere Gerät im Netz,
# also der Nachbar im offenen Gäste-WLAN und der smarte Fernseher. Deshalb gilt
# dann ein Zugangsschlüssel: Er steht in der Startadresse, wandert einmal ins
# Cookie und gilt, bis Wingfoilscout beendet wird. Ohne ihn kommt vom Netz her
# niemand an Katalog, Tagebuch oder den Beenden-Knopf.
LAN = {"aktiv": False, "schluessel": "", "adressen": ()}
COOKIE = "wingscout_schluessel"


def eigene_adressen() -> list:
    """Die IPv4-Adressen dieses Rechners im lokalen Netz.

    Der UDP-„Verbindungsaufbau“ zu einer Testadresse schickt kein einziges
    Paket; er fragt nur das Betriebssystem, über welche eigene Adresse es
    dorthin ginge. Das ist der verlässlichste Weg, die Adresse im WLAN zu
    erfahren — `gethostname()` liefert auf dem Mac oft nur 127.0.0.1.
    """
    aus = set()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))            # TEST-NET-1, nie erreichbar
        aus.add(s.getsockname()[0])
    except OSError:
        pass
    finally:
        s.close()
    try:
        for eintrag in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            aus.add(eintrag[4][0])
    except OSError:
        pass
    return sorted(a for a in aus if not a.startswith("127."))


def zugang_pruefen(ip: str, schluessel_in_url: str, cookie_kopf: str) -> str:
    """Darf diese Anfrage bedient werden? „frei“, „setzen“ oder „abweisen“.

    Als eigene Funktion, weil sich hier eine Sicherheitsregel entscheidet und
    eine Funktion sich ohne Server prüfen lässt (tests/test_webui.py).
    """
    if not LAN["aktiv"]:
        return "frei"
    if ip in ("127.0.0.1", "::1"):
        return "frei"                          # der Mac selbst
    # Als Bytes: `compare_digest` auf Strings wirft bei Nicht-ASCII einen
    # TypeError — ein `?k=ü` von irgendwem im WLAN ließ den Handler bis 1.18.3
    # mit Traceback sterben, noch vor der Zugangsentscheidung (Review 25.09., S3).
    soll = LAN["schluessel"].encode("utf-8")
    if schluessel_in_url and hmac.compare_digest(schluessel_in_url.encode("utf-8"), soll):
        return "setzen"
    for teil in (cookie_kopf or "").split(";"):
        name, _, wert = teil.strip().partition("=")
        if name == COOKIE and wert and hmac.compare_digest(wert.encode("utf-8"), soll):
            return "frei"
    return "abweisen"
SCHREIB_LOCK = threading.Lock()      # zwei Klicks auf der Prüfseite nacheinander, nicht ineinander


# ── Voreinstellungen ─────────────────────────────────────────────────────────

def form_defaults(cfg) -> dict:
    """Startwerte aus config.yaml, überschrieben von zuletzt gemerkten Eingaben."""
    w, wa, d, se, wi = cfg["weather"], cfg["water"], cfg["drive"], cfg["session"], cfg["wind"]
    values = {
        "start": "", "start_name": "", "ab": "",
        "days": 3, "radius": 500, "nights": 0,
        "max_drive": d["max_hours"], "min_hours": se["min_hours"], "min_score": se["min_score"],
        "air_min": w["air_temp_min"], "air_max": w["air_temp_max"], "water_min": w["water_temp_min"],
        "gust_bad": wi["gust_bad"], "pref_low": wi["preferred_low"], "pref_high": wi["preferred_high"],
        "chop": wa["chop_aversion"], "grass": wa.get("exclude_seagrass", "heavy"),
        "shallow": bool(wa.get("exclude_shallow", True)),
        "req_dogs": bool((cfg.get("rules") or {}).get("require_dogs")),
        "no_forbidden": bool((cfg.get("rules") or {}).get("exclude_forbidden")),
        "types": list(wa.get("include_types") or [t for t, _ in WATER_TYPES]),
        "marine": False, "geo": True, "demo": False, "alerts": True, "ensemble": True,
        "highres": True,
        "camping": True, "routing": True,
    }
    if DEFAULTS_FILE.exists():
        try:
            gemerkt = json.loads(DEFAULTS_FILE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            gemerkt = None
        if isinstance(gemerkt, dict):
            # Geschrieben hat die Datei der Server selbst — aber was in der
            # Seite landet, geht trotzdem durch dieselbe Prüfung wie eine
            # Formulareingabe: nur bekannte Schlüssel, nur der Typ des
            # Startwerts, keine Zeichenkette an einer Stelle, die ohne
            # Escaping in ein value="…" geschrieben wird.
            roh = {}
            for key, wert in gemerkt.items():
                if key not in values:
                    continue
                if isinstance(wert, list):
                    roh[key] = [str(x) for x in wert]
                elif isinstance(wert, bool):
                    if wert:
                        roh[key] = ["on"]
                else:
                    roh[key] = [str(wert)]
            geprueft = parse_form(roh, values)
            # Nur, was gemerkt wurde — ein Haken, den es beim Merken noch
            # nicht gab, behält seinen Startwert statt auf „aus“ zu fallen.
            values.update({k: geprueft[k] for k in gemerkt if k in geprueft})
    return values


def parse_form(raw: dict, base: dict) -> dict:
    """Formularwerte einlesen, alles Unlesbare fällt auf den Startwert zurück."""
    def num(key, cast=float):
        # `float("nan")` und `float("inf")` sind gültige Zahlen für Python und
        # ungültige für jeden Vergleich: eine Temperaturgrenze `nan` schaltet
        # die Prüfung stumm ab, ein Radius `inf` hebt ihn auf. Beides fällt
        # auf den Startwert zurück wie jede andere unlesbare Eingabe.
        # Dezimalkomma oder -punkt, in jeder Sprache: „1,5“ wie „1.5“.
        try:
            text = raw.get(key, [""])[0]
            wert = cast(text.replace(",", ".") if cast is float and isinstance(text, str) else text)
        except (ValueError, TypeError, IndexError):
            return base[key]
        return wert if math.isfinite(wert) else base[key]

    def txt(key, limit=120):
        return (raw.get(key, [""])[0] or "").strip()[:limit]

    return {
        "start": txt("start"), "start_name": txt("start_name", 60), "ab": txt("ab", 40),
        "days": max(1, min(16, num("days", int))),
        "radius": max(10.0, num("radius")),
        "nights": max(0, min(14, num("nights", int))),
        "max_drive": max(0.5, num("max_drive")),
        "min_hours": max(0.5, num("min_hours")),
        "min_score": min(0.95, max(0.1, num("min_score"))),
        "air_min": num("air_min"), "air_max": num("air_max"), "water_min": num("water_min"),
        "gust_bad": num("gust_bad"), "pref_low": num("pref_low"), "pref_high": num("pref_high"),
        "chop": min(1.0, max(0.0, num("chop"))),
        "grass": (raw.get("grass", ["heavy"])[0] if raw.get("grass", [""])[0] in dict(GRASS) else base["grass"]),
        "shallow": "shallow" in raw,
        "req_dogs": "req_dogs" in raw, "no_forbidden": "no_forbidden" in raw,
        "types": [t for t in raw.get("types", []) if t in dict(WATER_TYPES)] or base["types"],
        "marine": "marine" in raw, "geo": "geo" in raw, "demo": "demo" in raw,
        "ensemble": "ensemble" in raw, "camping": "camping" in raw,
        "highres": "highres" in raw,
        "routing": "routing" in raw,
        "alerts": "alerts" in raw,
    }


def apply_to_config(cfg, v: dict):
    cfg = copy.deepcopy(cfg)
    cfg["weather"]["air_temp_min"] = v["air_min"]
    cfg["weather"]["air_temp_max"] = v["air_max"]
    cfg["weather"]["water_temp_min"] = v["water_min"]
    cfg["wind"]["gust_bad"] = v["gust_bad"]
    cfg["wind"]["preferred_low"] = v["pref_low"]
    cfg["wind"]["preferred_high"] = v["pref_high"]
    cfg["water"]["chop_aversion"] = v["chop"]
    cfg["water"]["exclude_seagrass"] = v["grass"]
    cfg["water"]["exclude_shallow"] = v["shallow"]
    cfg["water"]["include_types"] = v["types"]
    cfg.setdefault("rules", {})["require_dogs"] = v.get("req_dogs", False)
    cfg["rules"]["exclude_forbidden"] = v.get("no_forbidden", False)
    cfg["session"]["min_hours"] = v["min_hours"]
    cfg["session"]["min_score"] = v["min_score"]
    cfg["drive"]["max_hours"] = v["max_drive"]
    return cfg


def _ab(v: dict):
    """Der Startzeitpunkt aus dem Formular (seit 2.3.0) — unlesbar wie leer:
    `/run` hat ihn vorher geprüft und hätte mit einem Satz abgelehnt."""
    try:
        return zeitraum.lesen(v.get("ab"))
    except ValueError:
        return None


def make_args(v: dict):
    return argparse.Namespace(
        days=v["days"], radius=v["radius"], nights=v["nights"],
        start=v.get("start") or None, start_name=v.get("start_name") or None, ab=_ab(v),
        max_drive=v["max_drive"], min_hours=v["min_hours"],
        spots=str(SPOTS_FILE), out=str(REPORT_FILE),
        geometry=str(GEOMETRY_FILE), no_geo=not v["geo"],
        marine=v["marine"], demo=v["demo"], model=None, open=False, quiet=True,
        no_alerts=not v.get("alerts", True),
        no_ensemble=not v.get("ensemble", True),
        no_highres=not v.get("highres", True),
        no_camping=not v.get("camping", True),
        no_routing=not v.get("routing", True),
    )


# ── Lauf im Hintergrund ──────────────────────────────────────────────────────

def _log(*parts) -> None:
    # Das Protokoll geht über `/status` an den Browser — Pfade darin gekürzt
    # wie in fehler_satz() (2.1.0, A4): Quellen melden ihre Fehler roh.
    zeile = _ohne_pfade(" ".join(str(p) for p in parts))
    with LOCK:
        JOB["log"].append(zeile)


def _starte(kind: str, arbeit, ausfuehrlich: bool = False) -> bool:
    """`arbeit()` im Hintergrund — und `JOB` verlässt „running“ in jedem Fall.

    Rückgabe False, wenn gerade etwas läuft oder die Prüfseite schreibt:
    Prüfen und Setzen geschehen unter demselben LOCK, sonst sähen zwei
    gleichzeitige Anfragen beide „frei“ und starteten beide.

    Bis 1.6.0 fing jeder Worker `Exception`. `SystemExit` ist keine: ein
    Katalog mit doppelter ID (damals `SystemExit` aus `load_spots`) ließ den
    Thread still sterben, `JOB` blieb auf „läuft“, jeder Knopf antwortete 409
    bis zum Neustart — und nichts sagte, warum. Jetzt kommt `load_spots` mit
    einem `ValueError`, und für alles, was trotzdem an `Exception` vorbeigeht,
    steht hier der zweite Fang. `ausfuehrlich` hängt den Traceback an: bei der
    Suche liegt der Fehler meist tief in einer Quelle, und `str(exc)` allein
    wäre dann nur „'foo'“.
    """
    sprache = i18n.aktuell()       # die Sprache der Anfrage, die den Lauf startet

    def worker():
        i18n.setze(sprache)
        try:
            arbeit()
        except Exception as exc:                                  # noqa: BLE001
            text = str(exc) or type(exc).__name__
            if ausfuehrlich:
                text = traceback.format_exc(limit=3)
            # `/status` gibt den Text an den Browser: Pfade gekürzt, wie in
            # fehler_satz() — der Traceback bleibt lesbar, der Benutzername
            # bleibt auf dem Mac (2.1.0, A4).
            with LOCK:
                JOB.update(state="error", error=_ohne_pfade(text))
        except BaseException as exc:                              # noqa: BLE001 — SystemExit & Co.
            with LOCK:
                JOB.update(state="error", error=_ohne_pfade(T("Abbruch: {fehler}", fehler=repr(exc))))
            raise
        finally:
            with LOCK:
                if JOB["state"] == "running":     # die Arbeit hat kein Ende gemeldet
                    JOB.update(state="error", error=T("Der Lauf endete ohne Ergebnis."))
                JOB["ende"] = time.time()

    with LOCK:
        if JOB["state"] == "running" or PRUEFEN_AKTIV["n"]:
            return False
        JOB.update(state="running", log=[], error=None, summary="", kind=kind, seit=time.time(), ende=None)
    threading.Thread(target=worker, daemon=True).start()
    return True


def start_run(cfg_path: str, v: dict) -> bool:
    def arbeit():
        cfg = apply_to_config(load_config(cfg_path), v)
        args = make_args(v)
        code = run_search(cfg, args, _log)
        with LOCK:
            if code == 0:
                JOB["state"] = "done"
                JOB["summary"] = T("{sessions} Sessions in {ziele} Zielen von {heim} aus",
                                   sessions=getattr(args, '_n_sessions', 0), ziele=getattr(args, '_n_trips', 0),
                                   heim=cfg['rider']['home']['name'])
            else:
                JOB["state"] = "error"
                JOB["error"] = (T("Kein Spot übrig — Radius erhöhen oder Filter lockern.")
                                if code == 2 else T("Der Lauf ist fehlgeschlagen, siehe Protokoll."))

    return _starte("run", arbeit, ausfuehrlich=True)


def start_ingest(cfg_path: str, text: str, with_geometry: bool) -> bool:
    """Neue Spots eintragen und, wenn gewünscht, gleich die Geometrie rechnen.

    Läuft im Hintergrund und schreibt ins selbe Protokoll wie die Suche, damit
    die Oberfläche nur eine Anzeige braucht.
    """
    def arbeit():
        from . import ingest
        from .spots import load_spots

        hits, problems = ingest.parse_text(text)
        for bad in problems[:8]:
            _log(T("nicht lesbar: {zeile}", zeile=bad[:70]))
        if not hits:
            raise ValueError(T("Keine Koordinate erkannt. Eine Zeile je Spot, "
                               "z.B. „Hardtsee; 49.17008, 8.61477\"."))

        existing = load_spots(str(SPOTS_FILE))
        taken = {s["id"] for s in existing}
        entries = []
        # Aus einer Datei: nie angesehen, also unbestätigt — die Prüfseite
        # listet sie. Getippt oder aus der Karte kopiert: bestätigt.
        bestaetigt = not ingest.ist_datei(text)
        if not bestaetigt:
            _log(T("Dateiimport: die Koordinaten gelten als unbestätigt und stehen auf der Prüfseite."))
        from .sources import ortsname
        # Name (wo keiner mitkam) und Land aus OpenStreetMap — eine Anfrage je
        # Sekunde; bei großen Dateien nur für die Spots ohne Namen, und
        # höchstens 40 je Import: 10 000 namenlose Wegpunkte wären sonst drei
        # Stunden und ein Verstoß gegen die Nutzungsregeln von Nominatim
        # (Review 25.09.2026, S12). Der Rest heißt nach seiner Koordinate.
        viele = len(hits) > 40
        anfragen = 0
        for name, lat, lon, water in hits:
            double = ingest.too_close(lat, lon, existing)
            if double:
                _log(T("schon im Katalog: {name} → {doppelt}",
                       name=name or f"{lat:.4f}, {lon:.4f}", doppelt=double['name']))
                continue
            ort = None
            if (not name or not viele) and anfragen < 40:
                ort = ortsname.vorschlag(lat, lon)
                anfragen += 1
            elif not name and anfragen == 40:
                _log(T("Mehr als 40 Punkte ohne Namen — die weiteren heißen nach ihrer Koordinate."))
                anfragen += 1
            entry = ingest.build_entry(name, lat, lon, water, taken, verified=bestaetigt, ort=ort)
            taken.add(entry["id"])
            entries.append(entry)
            _log(T("neu: {name} ({lat}, {lon}, {wasser}, {land})", name=entry['name'],
                   lat=f"{entry['lat']:.5f}", lon=f"{entry['lon']:.5f}", wasser=entry['water_body'],
                   land=entry['country'] or T("Land unbekannt")))

        if not entries:
            with LOCK:
                JOB.update(state="done", summary=T("Nichts Neues — alles stand schon im Katalog."))
            return

        ingest.append_to_yaml(SPOTS_FILE, entries)
        _log(T("{n} Spots in spots.yaml geschrieben.", n=len(entries)))

        done = 0
        if with_geometry:
            from .shoreline import load_store, run_batch
            gcfg = load_config(cfg_path).get("geometry", {})
            store = load_store(GEOMETRY_FILE)
            _log(T("Ufergeometrie für {n} neue Spots …", n=len(entries)))
            done, _ = run_batch(entries, store, GEOMETRY_FILE,
                                gcfg.get("max_fetch_km", 25.0),
                                gcfg.get("ray_count", 36), _log)

        # Ein Satz je Fall statt Bruchstücken: übersetzt wird der ganze Satz
        if with_geometry:
            fertig = T("{n} Spots aufgenommen, {m} mit Ufergeometrie — sie zählen ab der nächsten Suche mit.",
                       n=len(entries), m=done)
        else:
            fertig = T("{n} Spots aufgenommen — sie zählen ab der nächsten Suche mit.", n=len(entries))
        with LOCK:
            JOB.update(state="done", summary=fertig)

    return _starte("ingest", arbeit)


def start_geometry(cfg_path: str, recompute: bool = False) -> bool:
    """Ufergeometrie für alle Spots holen, denen sie noch fehlt.

    Damit ist das Skript nicht mehr nötig: aufnehmen, rechnen, suchen — alles
    über dieselbe Oberfläche. Abbrechen ist harmlos, jeder fertige Spot ist
    schon gespeichert, und beim nächsten Mal geht es bei den offenen weiter.
    """
    def arbeit():
        from .shoreline import auffaellig, load_store, missing, run_batch
        from .spots import load_spots

        gcfg = load_config(cfg_path).get("geometry", {})
        radius = gcfg.get("max_fetch_km", 25.0)
        n_dirs = gcfg.get("ray_count", 36)
        spots = load_spots(str(SPOTS_FILE))
        store = load_store(GEOMETRY_FILE)
        todo = spots if recompute else missing(spots, store)

        _log(T("{n} Spots · {fertig} schon berechnet · {offen} offen · Umkreis {km} km · {richtungen} Richtungen",
               n=len(spots), fertig=len(store), offen=len(todo), km=f"{radius:.0f}", richtungen=n_dirs))
        if not todo:
            with LOCK:
                JOB.update(state="done", summary=T("Alle Spots haben schon eine Ufergeometrie."))
            return

        done, failed = run_batch(todo, store, GEOMETRY_FILE, radius, n_dirs, _log)
        schlecht, pruefen = auffaellig(store)
        if schlecht:
            _log("")
            _log(T("Unbrauchbar — hier stimmt die Koordinate fast sicher nicht ({n}):", n=len(schlecht)))
            for sid, grund, _ in schlecht[:12]:
                _log(f"  · {sid}: {grund}")
        if pruefen:
            _log("")
            _log(T("Weit vom Pin ins Wasser versetzt — Koordinate nachsehen ({n}):", n=len(pruefen)))
            for sid, grund, _ in pruefen[:12]:
                _log(f"  · {sid}: {grund}")
        if schlecht or pruefen:
            _log("")
            _log(T("Alle davon stehen unter „Koordinaten prüfen“ (Datenquellen) — "
                   "dort auf der Karte nachsehen und gleich korrigieren."))
        if failed:
            _log("")
            _log(T("{n} Spots sind nicht durchgelaufen (meist Overpass überlastet). "
                   "Noch einmal auf „Fehlende berechnen\" — der Lauf macht bei den "
                   "offenen weiter, nichts geht doppelt.", n=failed))
        # Eine Aufzählung: jedes Glied ein eigener Ausdruck, verbunden mit Komma
        teile = [T("{n} Spots gerechnet", n=done)]
        if failed:
            teile.append(T("{n} fehlgeschlagen", n=failed))
        if schlecht:
            teile.append(T("{n} unbrauchbar", n=len(schlecht)))
        if pruefen:
            teile.append(T("{n} zum Nachsehen", n=len(pruefen)))
        with LOCK:
            JOB.update(state="done", summary=", ".join(teile))

    return _starte("ingest", arbeit)


# ── Seite ────────────────────────────────────────────────────────────────────

CSS = _web("basis.css")


# Kurzerklärungen für die Felder, deren Name allein nichts sagt. Sie stehen
# hier und nicht als Fließtext neben dem Feld, weil sie beim zweiten Mal nur
# noch stören — man liest sie einmal und danach nie wieder.
ERKLAERUNG = {
    "min_score": N_("Wie gut eine Stunde mindestens sein muss, damit sie als Session zählt. "
                    "Die Güte fasst Windstärke, Richtung zum Ufer, Böigkeit und Temperatur "
                    "zu einer Zahl zwischen 0 und 1 zusammen. 0,55 lässt auch mittelmäßige "
                    "Stunden durch, 0,8 zeigt nur noch Sahnetage."),
    "gust_bad": N_("Böe geteilt durch Mittelwind. 1,0 wäre gleichmäßiger Wind, 1,6 heißt: "
                   "in den Böen 60 % mehr als im Mittel — das reißt am Wing und macht "
                   "ablandige Lagen unangenehm. Stunden darüber fallen raus."),
    "highres": N_("Zusätzlich Regionalmodelle mit 1 bis 2,5 km Gitter statt der 7 bis "
                  "25 km der globalen. Sie lösen Talwinde und Seebrisen auf, die im groben "
                  "Gitter verschwinden — Ora, Maestral, Thermik an den Alpenseen. Dafür "
                  "reichen sie nur zwei bis drei Tage; danach gelten wieder die globalen."),
    "chop": N_("Wie sehr dich kurze, steile Welle stört. Wingfoilscout schätzt sie aus der "
               "Anlauflänge des Windes über dem Wasser: viel offenes Wasser vor dem Spot "
               "heißt viel Kabbelwasser. 0 = egal, 1 = du willst Flachwasser."),
    "marine": N_("Wassertemperatur (unter deiner Grenze fällt die Stunde raus) und die "
                 "Wellenhöhe aus dem Wellenmodell statt aus Anlauf und Wind — nur an Meer- "
                 "und Lagunenspots. Die Tidenzeiten kommen seit 1.18.0 immer mit, unabhängig "
                 "von diesem Haken; ein- und ausschalten lassen sie sich je Spot im Katalog."),
}


def hinweis(name: str) -> str:
    """Das kleine Fragezeichen hinter einem Feldnamen."""
    text = ERKLAERUNG.get(name)
    if not text:
        return ""
    text = T(text)
    # Kein title-Attribut: das gäbe zusätzlich den Systemtooltip, also zwei
    # Kästen übereinander. Die eigene Box erscheint sofort und bei Tastaturfokus.
    return (f'<span class="info" tabindex="0" role="note" '
            f'aria-label="{html.escape(text)}">?'
            f'<span class="infobox">{html.escape(text)}</span></span>')


def field(name, label, value, step="1", unit="", mn=None, mx=None):
    a = f' min="{mn}"' if mn is not None else ""
    b = f' max="{mx}"' if mx is not None else ""
    u = f' <span class="u">{html.escape(unit)}</span>' if unit else ""
    return (f'<div><label for="{name}">{html.escape(label)}{u}{hinweis(name)}</label>'
            f'<input type="number" id="{name}" name="{name}" value="{value}" step="{step}"{a}{b}></div>')


def text_field(name, label, value, placeholder=""):
    return (f'<div><label for="{name}">{html.escape(label)}</label>'
            f'<input type="text" id="{name}" name="{name}" value="{html.escape(str(value))}" '
            f'placeholder="{html.escape(placeholder)}" autocomplete="off"></div>')


def pruef_liste(home: dict | None = None) -> tuple[list, dict]:
    """Alles, was auf der Karte nachgesehen gehört — in einer Liste.

    Drei Gruppen, die verschiedene Fragen stellen. „Unbrauchbar" und „prüfen"
    kommen aus der Ufergeometrie: dort passt die gemessene Wasserfläche nicht
    zur Koordinate. „Unbestätigt" kommt aus dem Katalog: `verified: false`
    heißt, dass die Koordinate aus einer importierten Liste stammt und nie
    jemand hingeschaut hat — bei der Takeout-Liste bis etwa einen Kilometer
    daneben. Das ist kein Fehler, nur eine offene Frage, und sie stand bisher
    nirgends als abarbeitbare Liste.

    Der Geometriespeicher kennt nur IDs, der Katalog nur Koordinaten. Erst
    zusammen ergibt sich eine Zeile, mit der man etwas anfangen kann.
    """
    from .geo import haversine_km
    from .shoreline import auffaellig, load_store
    from .spots import load_spots
    spots = {s["id"]: s for s in load_spots(str(SPOTS_FILE))}
    erledigt = {sid for sid, s in spots.items() if s.get("geo_ok")}
    store = load_store(GEOMETRY_FILE)
    schlecht, pruefen = auffaellig(store, ignorieren=erledigt)
    raus, gesehen = [], set()
    for stufe, gruppe in (("unbrauchbar", schlecht), ("pruefen", pruefen)):
        for sid, grund, eintrag in gruppe:
            spot = spots.get(sid)
            if not spot:
                continue                      # Geometrie ohne Spot: verwaist
            gesehen.add(sid)
            raus.append({
                "id": sid, "name": spot["name"], "lat": spot["lat"], "lon": spot["lon"],
                "stufe": stufe, "grund": grund, "comment": str(spot.get("comment") or ""),
                "fetch_km": eintrag.get("max_fetch_km"),
            })
    # Die Unbestätigten nach Entfernung vom Startpunkt: die nächsten kennt man
    # am ehesten selbst, und dort lohnt das Nachsehen zuerst.
    offen = [s for sid, s in spots.items()
             if not s.get("verified") and sid not in gesehen]
    if home:
        offen.sort(key=lambda s: haversine_km(home["lat"], home["lon"], s["lat"], s["lon"]))
    else:
        offen.sort(key=lambda s: s["name"])
    for spot in offen:
        if home:
            grund = T("Koordinate nie bestätigt · {km} km Luftlinie",
                      km=f"{haversine_km(home['lat'], home['lon'], spot['lat'], spot['lon']):.0f}")
        else:
            grund = T("Koordinate nie bestätigt")
        raus.append({"id": spot["id"], "name": spot["name"], "lat": spot["lat"],
                     "lon": spot["lon"], "stufe": "unbestaetigt", "grund": grund,
                     "comment": str(spot.get("comment") or ""),
                     "fetch_km": (store.get(spot["id"]) or {}).get("max_fetch_km")})
    return raus, spots


def geometry_state() -> tuple[int, int]:
    """(Spots im Katalog, davon ohne Ufergeometrie) — für die Anzeige."""
    try:
        from .shoreline import load_store
        from .spots import load_spots
        spots = load_spots(str(SPOTS_FILE))
        store = load_store(GEOMETRY_FILE)
        return len(spots), sum(1 for s in spots if s["id"] not in store)
    except Exception:                                     # noqa: BLE001
        return 0, 0


# Reiter: Pfad, Name, Symbol, und ob er am Handy in die Tab-Leiste gehört.
# Am Rechner stehen alle oben; am Handy bleiben vier — Apples Vorgaben raten
# von einem „Mehr“-Reiter ab, und Katalog und Koordinatenprüfung sind Arbeit
# mit Karte und Tabelle, also Rechnerarbeit. Erreichbar bleiben sie über die
# Suchseite.
REITER = [("/", N_("Suche"), "lupe", True),
          ("/report", N_("Ziele"), "flagge", True),
          ("/katalog", N_("Katalog"), "liste", False),
          ("/pruefen", N_("Koordinaten prüfen"), "nadel", False),
          ("/rueckblick", N_("Rückblick"), "kurve", True),
          ("/tagebuch", N_("Tagebuch"), "buch", True)]

# Strichzeichnungen für die Tab-Leiste am Handy, 24×24, in der Textfarbe.
SYMBOLE = {
    "lupe": "<circle cx='11' cy='11' r='7'/><path d='M16.5 16.5 21 21'/>",
    "flagge": "<path d='M6 21V4'/><path d='M6 5h10.5l-2.4 3.4L16.5 12H6z'/>",
    "liste": "<path d='M9 6h11M9 12h11M9 18h11'/><circle cx='4.5' cy='6' r='1.1'/>"
             "<circle cx='4.5' cy='12' r='1.1'/><circle cx='4.5' cy='18' r='1.1'/>",
    "nadel": "<path d='M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z'/><circle cx='12' cy='10' r='2.4'/>",
    "kurve": "<path d='M3 20V4'/><path d='M3 20h18'/><path d='m6 15 4-4 3.5 3L20 7'/>",
    "buch": "<path d='M5 5.5A2 2 0 0 1 7 3.5h11v15H7a2 2 0 0 0-2 2z'/><path d='M9 8h6M9 11.5h6'/>",
}


def symbol(name: str) -> str:
    return (f"<svg viewBox='0 0 24 24' aria-hidden='true'>{SYMBOLE.get(name, '')}</svg>")


def seitenkopf(titel: str, css: str, extra: str = "") -> str:
    """Der Kopf jeder Seite — eine Stelle für alles, was am Handy zählt.

    `viewport-fit=cover` ist die Bedingung dafür, dass `env(safe-area-inset-*)`
    überhaupt Werte liefert; ohne das läge die Tab-Leiste unter dem
    Home-Indikator. `user-scalable=no` steht hier bewusst nicht: Safari
    ignoriert es seit iOS 10, und Zoom zu verbieten wäre eine Barriere.
    """
    return (f"<!doctype html><html lang='{i18n.aktuell()}'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>"
            "<meta name='apple-mobile-web-app-title' content='Wingfoilscout'>"
            "<link rel='manifest' href='/manifest.webmanifest'>"
            "<link rel='apple-touch-icon' href='/icon-180.png'>"
            "<link rel='icon' href='/icon-192.png' type='image/png'>"
            f"<title>{html.escape(titel)}</title>" + extra
            + "<style>" + css + "</style>" + skript(i18n.js_vorspann()) + "</head><body>")

# Wie viele Spots gerade auf der Prüfseite stehen — gemerkt, solange sich
# `spots.yaml` und `geometry.json` nicht ändern. Jede Seite fragt danach
# (`reiter()`), und die Liste zu rechnen kostet einen Katalog- und einen
# Geometrieeinlesevorgang (~0,2 s).
_PRUEF_ZAHL = {"stand": None, "n": 0}


def pruef_offen() -> int:
    """Einträge auf der Prüfseite. 0 heißt: nichts nachzusehen."""
    try:
        stand = (SPOTS_FILE.stat().st_mtime_ns, SPOTS_FILE.stat().st_size,
                 GEOMETRY_FILE.stat().st_mtime_ns, GEOMETRY_FILE.stat().st_size)
    except OSError:
        stand = None
    if stand is not None and _PRUEF_ZAHL["stand"] == stand:
        return _PRUEF_ZAHL["n"]
    try:
        n = len(pruef_liste()[0])
    except Exception:                                     # noqa: BLE001
        return 0            # ein kaputter Katalog kostet den Reiter, nicht die Seite
    _PRUEF_ZAHL.update(stand=stand, n=n)
    return n

REITER_CSS = _web("reiter.css")


def version_auf_platte() -> str:
    """Die Versionsnummer, die in `wingscout/__init__.py` steht — nicht die,
    mit der dieser Prozess läuft. Nach „Neuen Stand holen“ oder einem
    Veröffentlichen laufen die alten Seiten weiter, bis man Wingfoilscout neu
    startet; die beiden Nummern unterscheiden sich dann."""
    try:
        text = (ROOT / "wingscout" / "__init__.py").read_text(encoding="utf-8")
    except OSError:
        return __version__
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.M)
    return m.group(1) if m else __version__


def handy_kasten(port: int = 8765) -> str:
    """Die Adresse fürs iPhone — nur, wenn Wingfoilscout im WLAN erreichbar ist.

    Am Handy steht der Kasten nicht: wer ihn dort sähe, ist schon drauf.
    """
    if not LAN["aktiv"] or not LAN["adressen"]:
        return ("<div class='gruppe nurgross'><h4>" + T("Auf dem iPhone") + "</h4>"
                "<p class='hint' style='margin:0'>"
                + T("Wingfoilscout hört nur auf diesem Mac. Für das iPhone im "
                    "selben WLAN im Terminal <code>python3 -m wingscout.webui --lan</code> starten (oder "
                    "„Wingfoilscout fürs iPhone starten“ doppelklicken) — dann steht dort die Adresse samt "
                    "Zugangsschlüssel.")
                + "</p></div>")
    zeilen = "".join(
        f"<div style='font:13px/1.8 ui-monospace,Menlo,monospace;word-break:break-all'>"
        f"http://{html.escape(a)}:{port}/?k={html.escape(LAN['schluessel'])}</div>"
        for a in LAN["adressen"])
    return ("<div class='gruppe nurgross'><h4>" + T("Auf dem iPhone") + "</h4>"
            + zeilen +
            "<p class='hint' style='margin:6px 0 0'>"
            + T("Im selben WLAN in Safari eintippen, dann "
                "„Teilen“ → „Zum Home-Bildschirm“. Der Schlüssel gilt, bis Wingfoilscout beendet wird.")
            + "</p></div>")


def neustart_hinweis() -> str:
    """Ein Balken, wenn auf der Platte ein neuerer Stand liegt als der, der
    gerade läuft — sonst nichts. Ohne ihn wundert man sich, warum eine neue
    Funktion „nicht da“ ist, obwohl sie längst veröffentlicht wurde."""
    platte = version_auf_platte()
    if platte == __version__:
        return ""
    return ("<div class='banner b-warn'>"
            + T("Wingfoilscout läuft noch mit Version {version}, "
                "auf der Platte liegt schon {platte}. Oben rechts „Beenden“, "
                "dann neu starten (Doppelklick auf „Wingfoilscout starten“) — erst dann gilt der neue Stand.",
                version=html.escape(__version__), platte=html.escape(platte))
            + "</div>")


def reiter(aktiv: str) -> str:
    """Die Reiter jeder Seite — am Rechner oben, am Handy als Leiste unten
    (dieselbe Auszeichnung, den Rest macht `reiter.css`). Darunter der Hinweis,
    wenn ein Neustart fällig ist.

    „Koordinaten prüfen“ steht nur da, wenn es etwas zu prüfen gibt (seit
    1.16.1). Ist die Liste leer, ist der Reiter eine Einladung zu einer
    Seite, die nichts zeigt; er kommt von selbst wieder, sobald ein Import
    unbestätigte Koordinaten bringt oder eine Ufergeometrie nicht zur
    Koordinate passt. Auf der Seite selbst bleibt er stehen, damit sie sich
    nicht unter den Füßen wegzieht, wenn der letzte Eintrag abgehakt ist.
    """
    return reiter_leiste(aktiv) + neustart_hinweis()


def reiter_leiste(aktiv: str) -> str:
    """Nur die Leiste, ohne den Neustart-Hinweis — der braucht die Formate der
    Oberfläche, und der Report bringt seine eigenen mit.

    Rechts in der Leiste der Knopf „Beenden“ (seit 1.18.2 hier statt unten im
    Suchformular, damit er auf jedem Reiter zu sehen ist — am Handy als kleine
    Marke oben rechts, weil die Leiste dort unten sitzt). Sein Skript
    (`web/beenden.js`) kommt mit `MOBIL_JS` am Ende jeder Seite; dem Report
    setzt `report_mit_reitern` es eigens ein."""
    teile = []
    for pfad, name, sym, am_handy in REITER:
        if pfad == "/pruefen" and pfad != aktiv and not pruef_offen():
            continue
        # Der aktive Reiter steht immer da — auch am Handy, sonst sieht man
        # auf der Katalog- oder Prüfseite nicht, wo man gerade ist.
        klassen = ["an"] if pfad == aktiv else ([] if am_handy else ["nurgross"])
        klasse = f" class='{' '.join(klassen)}'" if klassen else ""
        teile.append(f"<a href='{pfad}'{klasse}>{symbol(sym)}<span>{html.escape(T(name))}</span></a>")
    # Marke (Logo, Version), Sprache, Hilfe und „Beenden“ als eine Gruppe:
    # passt die Leiste nicht in eine Zeile (lange Reiter auf Französisch, dazu
    # „Koordinaten prüfen“), rückt die Gruppe geschlossen nach rechts in die
    # zweite Zeile, statt „Beenden“ allein links darunter zu stellen (bis
    # 2.1.0). Am Handy sind „?“ und „Beenden“ die Gruppe, fest oben rechts.
    teile.append("<span class='rechts'>" + marke() + sprachwahl() + hilfe_knopf(aktiv)
                 + "<button type='button' class='aus' id='quit' "
                 f"title='{html.escape(T('Wingfoilscout beenden — zweimal drücken'))}'>{T('Beenden')}</button></span>")
    return "<nav class='reiter'>" + "".join(teile) + "</nav>"


PRUEF_CSS = _web("pruefen.css")


def pruef_page(eintraege: list, home: dict) -> str:
    """Die Prüfseite: links die auffälligen Spots, rechts eine Karte.

    Warum überhaupt eine eigene Seite: die Fundliste stand bisher nur im
    Protokoll des Geometrielaufs — man sah sie einmal, konnte aber nichts damit
    tun und beim nächsten Start war sie weg. Was man nicht abarbeiten kann,
    arbeitet man nicht ab.

    Die Karte ist das eigentliche Werkzeug. Ob eine Koordinate stimmt, sieht
    man nicht an Zahlen, sondern daran, ob die Nadel im Wasser steht.
    """
    # Daten im Skript wie überall: <, >, &, U+2028/U+2029 als Escapes, NaN und
    # Unendlich als null — eine kaputte `max_fetch_km` aus geometry.json
    # stand bis 2.1.0 als `NaN` in der Seite (i18n.json_im_skript)
    daten = i18n.json_im_skript(eintraege)
    heim = i18n.json_im_skript({"lat": home["lat"], "lon": home["lon"]})

    karten = []
    for e in eintraege:
        mild = {"unbrauchbar": "", "pruefen": " mild"}.get(e["stufe"], " offen")
        karten.append(
            "<div class='pkarte' data-stufe='" + html.escape(e["stufe"]) + "' "
            "data-id='" + html.escape(e["id"]) + "'>"
            "<div class='pkopf'><b>" + html.escape(e["name"]) + "</b>"
            "<span class='pgrund" + mild + "'>" + html.escape(e["grund"]) + "</span></div>"
            "<p class='pkoord'>" + f"{e['lat']:.5f}, {e['lon']:.5f}" + "</p>"
            + kommentar_kasten(e["id"], e.get("comment", "")) +
            "<div class='pzeile'>"
            "<button type='button' class='ghost mini zeigen'>" + T("Auf der Karte") + "</button>"
            "<input type='text' class='neu' placeholder='" + html.escape(T("neue Koordinate")) + "' autocomplete='off'>"
            "<button type='button' class='ghost mini uebernehmen'>" + T("Übernehmen") + "</button>"
            "<button type='button' class='ghost mini passt'>" + T("Passt so") + "</button>"
            "</div>"
            "<div class='pzeile'>"
            "<a href='https://www.openstreetmap.org/?mlat=" + str(e["lat"]) + "&mlon=" + str(e["lon"])
            + "#map=15/" + str(e["lat"]) + "/" + str(e["lon"]) + "' target='_blank' rel='noopener'>OSM</a>"
            "<a href='https://www.google.com/maps/search/?api=1&query="
            + urllib.parse.quote(f"{e['lat']},{e['lon']}") + "' target='_blank' rel='noopener'>Google Maps</a>"
            "<a href='https://www.windy.com/?" + str(e["lat"]) + "," + str(e["lon"])
            + ",13' target='_blank' rel='noopener'>Windy</a>"
            "</div>"
            "<p class='pmsg'></p></div>")

    # Ist nichts zu prüfen, steht auch nur das da: keine Erklärung von drei
    # Stufen, die niemand sieht, und keine leere Karte (seit 1.16.1).
    leer = ("<p class='sub'>"
            + T("Nichts zu prüfen — alle Koordinaten sind plausibel und bestätigt. "
                "Deshalb steht der Reiter „Koordinaten prüfen“ auf den anderen Seiten gerade nicht "
                "oben; er kommt wieder, sobald ein Import unbestätigte Koordinaten bringt oder eine "
                "Ufergeometrie nicht zur Koordinate passt. Erreichbar bleibt diese Seite immer unter "
                "<code>/pruefen</code>.")
            + "</p>"
            if not eintraege else "")
    erklaerung = ("" if not eintraege else
                  "<p class='sub'>"
                  + TN("Ein Spot, der auf der Karte nachgesehen gehört.",
                       "{n} Spots, die auf der Karte nachgesehen gehören.", len(eintraege))
                  + " " + T("<b>Unbrauchbar</b> und <b>fragwürdig</b> kommen aus der Ufergeometrie: "
                            "dort passt die gemessene Wasserfläche nicht zur Koordinate. <b>Unbestätigt</b> "
                            "heißt, dass die Koordinate aus einer importierten Liste stammt und nie jemand "
                            "hingeschaut hat — bei der Takeout-Liste bis etwa einen Kilometer daneben; diese "
                            "sind nach Entfernung sortiert, die nächsten zuerst.")
                  + "<br>"
                  + T("Nadel ziehen oder ins Wasser klicken, dann übernehmen — die Geometrie wird gleich "
                      "neu gerechnet und die Koordinate gilt als bestätigt. „Passt so“ bestätigt sie, "
                      "ohne etwas zu ändern.")
                  + "</p>")
    karte = ("" if not eintraege else
             "<div class='pspalten'><div class='pmapsp'><div id='pmap'></div></div>"
             "<div class='pliste'>" + "".join(karten) + "</div></div>"
             "<script src='" + LEAFLET_JS + "' "
             "integrity='" + LEAFLET_JS_SRI + "' "
             "crossorigin='anonymous'></script>"
             + skript("\nvar SPOTS = " + daten + ";\nvar HOME = " + heim + ";\n"
                      + KOMMENTAR_JS + "\nwindow.WSKommentar.alle();\n" + PRUEF_JS + "\n"))

    zahl = {"unbrauchbar": 0, "pruefen": 0, "unbestaetigt": 0}
    for e in eintraege:
        zahl[e["stufe"]] = zahl.get(e["stufe"], 0) + 1
    knoepfe = [("alle", T("Alle {n}", n=len(eintraege)))]
    if zahl["unbrauchbar"]:
        knoepfe.append(("unbrauchbar", T("Unbrauchbar {n}", n=zahl['unbrauchbar'])))
    if zahl["pruefen"]:
        knoepfe.append(("pruefen", T("Fragwürdig {n}", n=zahl['pruefen'])))
    if zahl["unbestaetigt"]:
        knoepfe.append(("unbestaetigt", T("Unbestätigt {n}", n=zahl['unbestaetigt'])))
    filter_leiste = ("" if len(knoepfe) < 2 else
                     "<div class='pfilter'>" + "".join(
                         "<button type='button' data-stufe='" + k + "'"
                         + (" class='an'" if k == "alle" else "") + ">" + html.escape(t)
                         + "</button>" for k, t in knoepfe) + "</div>")

    return (seitenkopf(T("Wingfoilscout · Koordinaten prüfen"), CSS + REITER_CSS + PRUEF_CSS + KOMMENTAR_CSS,
                       "<link rel='stylesheet' href='" + LEAFLET_CSS + "' "
                       "integrity='" + LEAFLET_CSS_SRI + "' crossorigin='anonymous'>")
            + "<div class='wrap weit'>"
            + reiter("/pruefen") +
            "<h1>" + T("Koordinaten prüfen") + "</h1>"
            + leer + erklaerung + filter_leiste + karte + seitenende() + "</body></html>")


PRUEF_JS = _web("pruefen.js")


# ── Katalog ──────────────────────────────────────────────────────────────────

KATALOG_CSS = _web("katalog.css")


def kommentar_putzen(wert) -> str | None:
    """Kommentartext aus der Anfrage: Umbrüche vereinheitlicht, Steuerzeichen
    außer Umbruch und Tab weg, Ränder gekappt. None, wenn er zu lang ist."""
    text = str(wert or "").replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(c for c in text if c in "\n\t" or (ord(c) >= 32 and ord(c) != 127))
    text = "\n".join(z.rstrip() for z in text.split("\n")).strip()
    return None if len(text) > 2000 else text


def katalog_daten(spots: list) -> list:
    """Was die Katalogseite je Spot braucht — schlank, weil 275 davon in die Seite gehen."""
    aus = []
    ig = instagram.lade()
    for s in spots:
        th = s.get("thermal") or {}
        sb = s.get("shorebreak") or {}          # load_spots hat das Feld normiert
        aus.append({
            "id": s["id"], "name": s["name"], "country": s.get("country") or "",
            "region": s.get("region") or "", "water": s.get("water_body") or "unknown",
            "lat": float(s["lat"]), "lon": float(s["lon"]),
            "verified": bool(s.get("verified")), "thermik": th.get("name") or (T("Thermik") if th else ""),
            "shorebreak": sb.get("status", "") if isinstance(sb, dict) else "",
            "shorebreak_note": _kurz(str(sb.get("note") or ""), 140) if isinstance(sb, dict) else "",
            "access": s.get("access") or "", "dogs": s.get("dogs") or "",
            "notes": _kurz(str(s.get("notes") or ""), 140),
            "comment": str(s.get("comment") or ""),
            "source": _kurz(str(s.get("source") or ""), 80),
            "instagram": s.get("instagram") or "",
            "ig": dict(instagram.links(s, ig)),         # {"Instagram": …, "Insta-Suche": …}
            "ig_funde": [{"url": f["url"], "titel": f["titel"], "text": instagram.beschriftung(f["url"], f["titel"])}
                         for f in instagram.funde(s, ig).get("funde", [])[:5]],
            "ig_urteil": instagram.funde(s, ig).get("urteil", ""),
            "aus": bool(s.get("disabled") or s.get("reference_only")),
            # Tiden (1.18.0): True/False aus dem Katalog, None = Automatik;
            # `tide` ist das Fenster, wenn eines gesetzt ist.
            "tidal": s.get("tidal") if isinstance(s.get("tidal"), bool) else None,
            "tide": ({"fahrbar": s["tide"].get("fahrbar", ""), "stunden": s["tide"].get("stunden", 2)}
                     if isinstance(s.get("tide"), dict) else None),
        })
    aus.sort(key=lambda x: x["name"].lower())
    return aus


def _kurz(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n - 1].rstrip(" ,;.") + "…"


def spot_vorschlag(werte: dict | None = None) -> str:
    """Die Adresse des Formulars „Spot vorschlagen“ auf GitHub (seit 2.3.0),
    auf Wunsch vorausgefüllt — die Schlüssel sind die `id`s der Felder in
    .github/ISSUE_TEMPLATE/spot.yml (name, koordinate, hinweise …). Nur ein
    Link: gesendet wird erst, wenn jemand das Formular dort abschickt."""
    felder = {"template": "spot.yml"}
    felder.update({k: str(v)[:300] for k, v in (werte or {}).items() if v})
    return SPOT_FORMULAR + "?" + urllib.parse.urlencode(felder)


def vorschlag_satz(kennung: str = "") -> str:
    """Der Satz mit dem Link „Für alle vorschlagen“ — auf der Suchseite (Klappe
    „Spots hinzufügen“) und im Katalog. Wer einen Spot nur für sich einträgt,
    behält ihn auf dem eigenen Rechner; in den Katalog für alle kommt er über
    das Formular."""
    kennung = f" id='{kennung}'" if kennung else ""
    link = (f"<a{kennung} href='{html.escape(spot_vorschlag())}' target='_blank' rel='noopener noreferrer'>"
            + html.escape(T("Für alle vorschlagen")) + "</a>")
    return T("Für alle in den Katalog: {link} — ein Formular auf GitHub (kostenloses Konto nötig). "
             "Gesendet wird erst, wenn du es dort abschickst.", link=link)


def katalog_page(spots: list, home: dict) -> str:
    """Alle Spots auf einer Seite: suchen, filtern, auf der Karte sehen.

    Der Zweck ist, den eigenen Katalog zu kennen — welche Spots es schon gibt,
    bevor man einen zum zweiten Mal einträgt. Deshalb steht unten die Frage
    „Schon drin?“: Name oder Koordinate eingeben, und die nächsten Spots
    erscheinen mit Abstand.
    """
    daten = i18n.json_im_skript(katalog_daten(spots))           # wie auf der Prüfseite
    heim = i18n.json_im_skript({"lat": float(home["lat"]), "lon": float(home["lon"])})
    laender = sorted({(s.get("country") or "") for s in spots if s.get("country")})
    land_opts = "<option value=''>" + T("alle Länder") + "</option>" + "".join(
        f"<option value='{html.escape(l)}'>{html.escape(l)}</option>" for l in laender)
    wasser_opts = "<option value=''>" + T("alle Gewässer") + "</option>" + "".join(
        f"<option value='{k}'>{html.escape(T(t))}</option>" for k, t in WATER_TYPES + [("unknown", N_("unbekannt"))])
    return (seitenkopf(T("Wingfoilscout · Katalog"), CSS + REITER_CSS + KATALOG_CSS + KOMMENTAR_CSS,
                       "<link rel='stylesheet' href='" + LEAFLET_CSS + "' "
                       "integrity='" + LEAFLET_CSS_SRI + "' crossorigin='anonymous'>")
            + "<div class='wrap weit'>"
            + reiter("/katalog") +
            "<h1>" + T("Katalog") + "</h1>"
            "<p class='sub'>"
            + T("Alle Spots, die Wingfoilscout kennt. Suchen, filtern, anklicken — und unten "
                "nachsehen, ob ein Spot schon drin ist, bevor du ihn ein zweites Mal einträgst.")
            + "</p>"
            "<div class='karte'>"
            "<div class='ksuche'>"
            "<div><label for='ksuch'>" + T("Suchen") + "</label>"
            "<input type='text' id='ksuch' placeholder='" + html.escape(T("Name, Land, Gewässer, Notiz …"))
            + "' autocomplete='off'></div>"
            "<div style='flex:0'><label for='kland'>" + T("Land") + "</label><select id='kland'>" + land_opts + "</select></div>"
            "<div style='flex:0'><label for='kwasser'>" + T("Gewässer") + "</label><select id='kwasser'>" + wasser_opts + "</select></div>"
            "<div style='flex:0'><label for='kwas'>" + T("Zeige nur") + "</label><select id='kwas'>"
            "<option value=''>" + T("alle") + "</option><option value='unbestaetigt'>" + T("unbestätigte") + "</option>"
            "<option value='thermik'>" + T("mit Thermik") + "</option><option value='shorebreak'>" + T("mit Shorebreak") + "</option>"
            "<option value='instagram'>" + T("mit Instagram-Funden") + "</option>"
            "<option value='insta_offen'>" + T("Instagram noch nicht gesucht") + "</option>"
            "<option value='tide'>" + T("mit Tidenregel") + "</option></select></div>"
            "</div>"
            "<p class='kzahl' id='kzahl'></p>"
            "</div>"
            "<div class='kspalten'>"
            "<div class='kliste'><table><thead><tr>"
            "<th data-k='name' class='sort auf'>" + T("Spot") + "</th><th data-k='country'>" + T("Land")
            + "</th><th data-k='water'>" + T("Gewässer") + "</th>"
            "<th data-k='km'>km</th></tr></thead><tbody id='ktbody'></tbody></table></div>"
            "<div class='kmapsp'><div id='kmap'></div>"
            # Den Namen des Spots setzt katalog.js in das <b> am Satzanfang — als
            # Platzhalter im Satz, damit eine Übersetzung ihn umstellen kann,
            # ohne das Element anzufassen, das das Skript sucht.
            "<div class='kzieh' id='kzieh' style='display:none'>"
            + T("{name} verschieben: Nadel ziehen oder "
                "in die Karte klicken, dann übernehmen.", name="<b id='kziehname'></b>")
            + " <span class='mono' id='kziehkoord'></span> "
            "<button type='button' class='klein' id='kziehok'>" + T("Übernehmen") + "</button> "
            "<button type='button' class='klein grau' id='kziehnein'>" + T("Abbrechen") + "</button></div>"
            "<div class='karte kdoppel'><label for='kneu'>" + T("Schon drin? Name oder Koordinate eines neuen Spots") + "</label>"
            "<div class='feldzeile'><input type='text' id='kneu' placeholder='"
            + html.escape(T("z. B. 51.7625, 3.854 oder „Brouwersdam“")) + "' autocomplete='off'></div>"
            "<div class='treffer' id='ktreffer'></div>"
            "<details class='kneuform' id='kneuform'><summary>" + T("Neuen Spot eintragen") + "</summary>"
            "<div class='kfelder'>"
            "<div><label for='kname'>" + T("Name") + "</label><input type='text' id='kname' placeholder='"
            + html.escape(T("z. B. Plage de Kerhillio")) + "' autocomplete='off'></div>"
            "<div><label for='kkoord'>" + T("Koordinate") + "</label><input type='text' id='kkoord' placeholder='51.7625, 3.854' autocomplete='off'></div>"
            "<div><label for='kwasserneu'>" + T("Gewässer") + "</label><select id='kwasserneu'><option value=''>" + T("weiß nicht") + "</option>"
            "<option value='sea'>" + T("Meer") + "</option><option value='lagoon'>" + T("Lagune") + "</option><option value='lake'>" + T("See") + "</option>"
            "<option value='reservoir'>" + T("Stausee") + "</option></select></div>"
            "<div><label for='klandneu'>" + T("Land (Kürzel, leer = raten)") + "</label><input type='text' id='klandneu' maxlength='2' placeholder='FR' autocomplete='off' style='width:70px'></div>"
            "<div class='breit'><label for='knotiz'>" + T("Notiz") + "</label><input type='text' id='knotiz' placeholder='"
            + html.escape(T("kurz: was der Spot ist")) + "' autocomplete='off'></div>"
            "<div class='breit'><label for='kkommentar'>" + T("Kommentar") + "</label><textarea id='kkommentar' rows='2' maxlength='2000' "
            "placeholder='" + html.escape(T("Was man hier wissen muss — Parken, Einstieg, wie es war …")) + "'></textarea></div>"
            "<div class='breit'><label class='check'><input type='checkbox' id='kgeo' checked> "
            + T("Ufergeometrie gleich rechnen (dauert ein paar Sekunden)") + "</label></div>"
            "</div>"
            "<div class='feldzeile'><button type='button' class='klein' id='kneuok'>" + T("Eintragen") + "</button>"
            "<span class='kmeld' id='kneumeld'></span></div>"
            "</details>"
            # Für alle (seit 2.3.0): katalog.js füllt den Link beim Klick mit
            # dem, was oben steht — Name, Koordinate, Notiz.
            "<p class='kvorschlag'>" + vorschlag_satz("kvorschlag") + "</p>"
            "<div class='kmeld' id='kmeldung'></div></div>"
            "</div></div>"
            "<script src='" + LEAFLET_JS + "' integrity='" + LEAFLET_JS_SRI + "' crossorigin='anonymous'></script>"
            + skript("\nvar SPOTS = " + daten + ";\nvar HOME = " + heim + ";\nvar VORSCHLAG = "
                     + i18n.json_im_skript(SPOT_FORMULAR) + ";\n" + KOMMENTAR_JS + "\n" + KATALOG_JS + "\n") +
            seitenende() + "</body></html>")


KATALOG_JS = _web("katalog.js")


# ── Rückblick ────────────────────────────────────────────────────────────────

RUECKBLICK_CSS = _web("rueckblick.css")


def rueckblick_page(cfg, daten: dict | None, lauf: dict | None, tage: int, kommentare: dict | None = None,
                    max_km: float | None = None) -> str:
    """Die Rückblick-Seite: die besten Ziele der letzten Suche gegen die Messung.

    Der Prüfstand misst einen festen Monat an festen Spots, damit sich
    Änderungen am Code vergleichen lassen. Hier steht die andere Frage, die man
    beim Lesen des Reports hat: kann ich dem trauen? Dafür die Ziele, die der
    Report gerade oben hat, und die Tage, die gerade vorbei sind.
    """
    from .rueckblick import veraltet, MAX_KM_VORGABE, MAX_KM_GRENZE
    hinweis = veraltet(daten, lauf, __version__)
    # Der Umkreis: was zuletzt gewählt war, sonst die Vorgabe (seit 1.13.0 wählbar)
    try:
        max_km = float(max_km or (daten or {}).get("max_km") or MAX_KM_VORGABE)
    except (TypeError, ValueError):
        max_km = float(MAX_KM_VORGABE)
    max_km = max(1.0, min(float(MAX_KM_GRENZE), max_km))
    if not lauf:
        lauf_text = T("Noch keine Suche gelaufen — erst eine Suche starten, dann hier prüfen.")
    else:
        n_top = len(lauf.get("top") or [])
        zeit = html.escape(datum_lesbar(str(lauf.get("zeit", ""))))
        if lauf.get("demo"):
            zeit = T("{zeit} (Demo)", zeit=zeit)
        lauf_text = (T("Letzte Suche: {zeit} · {n} Ziele, die ersten {k} werden geprüft",
                       zeit=zeit, n=n_top, k=min(10, n_top))
                     if lauf.get("top") else
                     T("Letzte Suche: {zeit} · {n} Ziele", zeit=zeit, n=n_top))
    # Ein `Infinity` aus einer alten cache/rueckblick.json stand bis 2.1.0 als
    # JavaScript in der Seite, und das Diagramm zeichnete ohne Ende
    # Gitterlinien — der Reiter hing. Jetzt `null` (i18n.json_im_skript), und
    # rueckblick.js lässt unsinnige Werte aus dem Diagramm.
    payload = i18n.json_im_skript(daten or None)
    kmt = i18n.json_im_skript(kommentare or {})
    return (seitenkopf(T("Wingfoilscout · Rückblick"), CSS + REITER_CSS + RUECKBLICK_CSS + KOMMENTAR_CSS)
            + "<div class='wrap weit'>"
            + reiter("/rueckblick") +
            "<h1>" + T("Rückblick") + "</h1>"
            "<p class='sub'>"
            + T("Wie gut lagen die Wettermodelle an den besten Zielen der letzten Suche? "
                "Für die letzten Tage bis zur aktuellen Stunde holt Wingfoilscout die gemessenen Winde der "
                "nächsten Wetterstation und die Vorhersagen, wie sie damals waren. Das Diagramm zeigt die "
                "Messung und die Spanne aller Modelle; einzelne Modelle, das bisher beste und die "
                "Wingfoilscout-Bewertung lassen sich darunter zuschalten.")
            + "</p>"
            "<div class='karte'>"
            "<form id='rf' class='rform'>"
            "<div><label for='tage'>" + T("Tage (einschließlich heute)") + "</label>"
            "<input type='number' id='tage' name='tage' value='" + str(int(tage)) + "' min='1' max='14' step='1'></div>"
            "<div><label for='max_km'>" + T("Station bis … km") + "</label>"
            # step='1', nicht 5: der Browser prüft den Wert gegen min + n·step —
            # mit min=1 und step=5 wären nur 1, 6, 11 … gültig, 10 und sogar die
            # Vorgabe 30 nicht („Gültigen Wert eingeben“, 20.09.)
            "<input type='number' id='max_km' name='max_km' value='" + str(int(round(max_km))) + "' min='1' max='"
            + str(int(MAX_KM_GRENZE)) + "' step='1'></div>"
            "<button type='submit' class='go' id='rgo' style='width:auto;margin:0;padding:12px 22px;font-size:.95rem'"
            + (" disabled" if not lauf else "") + ">" + T("Prüfen") + "</button>"
            "</form>"
            "<p class='rlauf' id='rlauf'>" + lauf_text + "</p>"
            "<div id='rstatus' class='status' style='display:none;margin-top:12px'>"
            "<span class='spinner'></span><span id='rstatustext'>" + T("Läuft …") + "</span></div>"
            "<div id='rbanner' style='margin-top:12px'>"
            + (f"<div class='banner b-warn'>{html.escape(hinweis)}</div>" if hinweis else "") + "</div>"
            "<details id='rprotokoll' style='margin-top:10px;display:none'><summary>" + T("Protokoll") + "</summary>"
            "<div class='inhalt'><pre id='rlog'></pre></div></details>"
            "</div>"
            "<div id='rergebnis'></div>"
            # Zu, auch am Rechner, und als Punkte statt als ein Absatz über
            # fünfzehn Zeilen (Review 25.09., U5). `mobil.js` fasst diese
            # Klappe bewusst nicht an.
            "<details class='erklaerung'><summary>" + T("Was man wissen muss") + "</summary>"
            "<ul class='rerklaer'>"
            "<li>" + T("<b>Welche Vorhersage:</b> die aufgehobene mit dem kürzesten Vorlauf — „heute für heute“, "
                       "nicht die von vor drei Tagen; für den laufenden Tag die von heute Morgen.") + "</li>"
            "<li>" + T("<b>Woher die Messung:</b> DWD (Deutschland), KNMI und Rijkswaterstaat (Niederlande — "
                       "Rijkswaterstaat misst am Wasser), GeoSphere (Österreich), DMI (Dänemark), Météo-France "
                       "(Frankreich); gesucht wird über Grenzen hinweg, ein belgischer Spot bekommt die nächste "
                       "niederländische Station. Dazu Windguru-Stationen, wenn sie mit ihrem API-Passwort in der "
                       "Konfiguration stehen (<code>stationen: windguru:</code> in <code>config.yaml</code>, Beispiel in "
                       "<code>config.example.yaml</code>). Eine Station misst über Land in zehn Metern Höhe, der Spot "
                       "liegt über Wasser; an der Küste misst sie meist weniger als draußen.") + "</li>"
            "<li>" + T("<b>Welche Station:</b> „Station bis … km“ sagt, wie weit sie vom Spot liegen darf. Genommen "
                       "wird die nächste, die fast alle Stunden bis jetzt hat (90 %); hat keine so viel, die nächste mit "
                       "fast so vielen wie die beste. Wurde eine nähere übergangen, steht sie dabei. Je weiter weg, desto "
                       "weniger sagt sie über den Spot.") + "</li>"
            "<li>" + T("<b>Lücken:</b> wie nah die Messung an „jetzt“ heranreicht, hängt am Dienst. DWD hat geprüfte "
                       "Stunden bis vorgestern und den laufenden Tag aus Zehnminutenwerten — gestern fehlt, bis die "
                       "nächste Tagesdatei kommt; KNMI reicht bis vorgestern, Rijkswaterstaat, GeoSphere und DMI bis zur "
                       "aktuellen Stunde, Météo-France bis heute früh. Je Spot steht, welche Stunden eine Messung haben; "
                       "ohne Messung bleibt die Kurve leer.") + "</li>"
            "<li>" + T("<b>Die Zahlen:</b> <b>MAE</b> mittlerer Fehler in Knoten · <b>Bias</b> zu viel oder zu wenig "
                       "gesagt, im Mittel · <b>Richtung</b> Anteil der Stunden mit höchstens 45° Abweichung (nur bei "
                       "gemessenen ≥ 8 kn) · <b>F1 Wind</b> wie gut „über 12 kn bei Tag“ getroffen wurde, 1,0 wäre "
                       "perfekt.") + "</li>"
            "<li>" + T("<b>Modelle im Vergleich:</b> jedes Wettermodell einzeln gegen dieselbe Messung — die globalen "
                       "(ICON, ECMWF, das KI-Modell ECMWF-AIFS, GFS, Météo-France, UKMO) und bis zu drei Regionalmodelle, "
                       "die den Spot abdecken; roh, ohne Windfaktor und Thermik, die „Wingfoilscout-Bewertung“ rechnet beides "
                       "ein. Jede Prüfung wandert ins Gedächtnis (<code>modellguete.json</code>); unten steht die Rangliste "
                       "über alle bisherigen. <b>Bisher bestes Modell</b>: das laut Gedächtnis an diesem Spot beste (ab 24 "
                       "gemeinsamen Stunden), sonst das beste über alle Spots. Ins Diagramm passen drei Linien zugleich.")
            + "</li>"
            "</ul></details>"
            "<div class='rtip' id='rtip'></div>"
            + skript("\nvar DATEN = " + payload + ";\nvar KOMMENTARE = " + kmt + ";\n" + KOMMENTAR_JS + "\n" + RUECKBLICK_JS + "\n") +
            seitenende() + "</body></html>")


RUECKBLICK_JS = _web("rueckblick.js")


def start_rueckblick(cfg_path: str, tage: int, max_km: float | None = None) -> bool:
    """Die besten Ziele der letzten Suche gegen die Messung — im Hintergrund."""
    def arbeit():
        from . import rueckblick
        from .shoreline import load_store
        from .spots import load_spots
        lauf = rueckblick.letzter_lauf()
        if not lauf or not lauf.get("top"):
            raise ValueError(T("Noch keine Suche gelaufen — erst suchen, dann zurückblicken."))
        cfg = load_config(cfg_path)
        spots = {s["id"]: s for s in load_spots(str(SPOTS_FILE))}
        top = list(lauf["top"])[:10]
        _log(T("Rückblick über {tage} Tage für {n} Ziele der Suche vom {zeit}",
               tage=tage, n=len(top), zeit=str(lauf.get('zeit', '')).replace('T', ' ')))
        ergebnis = rueckblick.rechne(cfg, spots, top, tage, load_store(GEOMETRY_FILE), log=_log,
                                     max_km=max_km or rueckblick.MAX_KM_VORGABE)
        rueckblick.mit_gedaechtnis(ergebnis)
        rueckblick.speichern(ergebnis)
        mit = [s for s in ergebnis["spots"] if s.get("masse")]
        with LOCK:
            JOB.update(state="done",
                       summary=T("{n} von {gesamt} Zielen mit Messstation verglichen ({von} bis {bis})",
                                 n=len(mit), gesamt=len(ergebnis['spots']),
                                 von=ergebnis['von'], bis=ergebnis['bis']))
    return _starte("rueckblick", arbeit)


# ── Session-Tagebuch (seit 1.16.0) ───────────────────────────────────────────

TAGEBUCH_CSS = _web("tagebuch.css")
TAGEBUCH_JS = _web("tagebuch.js")


def tagebuch_daten(cfg, spots_by_id: dict) -> dict:
    """Was die Tagebuchseite zeigt: die Sessions (neueste zuerst), die Namen
    ihrer Spots, der Quiver und die Vorschläge."""
    from . import tagebuch
    daten = tagebuch.laden()
    sessions = sorted(daten["sessions"], key=lambda s: (str(s.get("datum", "")), str(s.get("von", ""))),
                      reverse=True)
    return {"sessions": sessions,
            "namen": {s["spot"]: spots_by_id[s["spot"]]["name"] for s in sessions
                      if s.get("spot") in spots_by_id},
            "wings": [{"size": float(w["size"]), "low": float(w["low"]), "high": float(w["high"])}
                      for w in cfg["quiver"]["wings"]],
            "vorschlaege": tagebuch.vorschlaege(daten, cfg, spots_by_id),
            "station_nah_km": tagebuch.STATION_NAH_KM}


def tagebuch_page(cfg, spots: list, heute: str | None = None) -> str:
    """Die Tagebuchseite: eine Session eintragen, die Sessions mit dem, was
    Wingfoilscout, die Modelle und die Messstation für diese Stunden sagten, und
    die Vorschläge für Windfenster und Windfaktor."""
    from . import tagebuch
    spots_by_id = {s["id"]: s for s in spots}
    daten = tagebuch_daten(cfg, spots_by_id)
    heute = heute or date.today().isoformat()
    letzte = daten["sessions"][0] if daten["sessions"] else {}
    liste = sorted(({"id": s["id"], "name": s["name"], "region": s.get("region") or s.get("country") or ""}
                    for s in spots), key=lambda s: s["name"].lower())
    daten["letzte"] = {"spot": letzte.get("spot"), "wing": letzte.get("wing")}

    def wahl(name: str, werte) -> str:
        return ("<div class='twahl' role='radiogroup'>" + "".join(
            f"<label><input type='radio' name='{name}' value='{html.escape(str(k))}'>"
            f"<span>{html.escape(str(t))}</span></label>" for k, t in werte) + "</div>")

    return (seitenkopf(T("Wingfoilscout · Tagebuch"), CSS + REITER_CSS + TAGEBUCH_CSS)
            + "<div class='wrap weit'>"
            + reiter("/tagebuch") +
            "<h1>" + T("Tagebuch") + "</h1>"
            "<p class='sub'>"
            + T("Was auf dem Wasser wirklich war — gegen das, was Wingfoilscout, die Wettermodelle und "
                "die nächste Messstation für genau diese Stunden sagten. Aus mehreren Sessions werden Vorschläge "
                "für die Windfenster deiner Wings und den Windfaktor eines Spots.")
            + "</p>"
            "<div class='karte'>"
            "<h2 class='th2'>" + T("Session eintragen") + "</h2>"
            "<form id='tf' class='tform' autocomplete='off' novalidate>"
            "<div class='row'>"
            # Keine `datalist`: auf iOS Safari legt sie ihr Dropdown über das
            # Eingabefeld, sobald mehr als etwa drei Vorschläge kommen — bei 278
            # Spots ist sie unbenutzbar. Stattdessen eine eigene Trefferliste
            # (web/tagebuch.js), die auch am Rechner besser zu bedienen ist.
            "<div class='tbreit tspotfeld'><label for='tspot'>" + T("Spot") + "</label>"
            "<input type='text' id='tspot' autocomplete='off' autocorrect='off' autocapitalize='off' "
            "spellcheck='false' role='combobox' aria-expanded='false' aria-controls='tspotliste' "
            "placeholder='" + html.escape(T("Name eintippen")) + "'>"
            "<input type='hidden' name='spot' id='tspotid'>"
            "<div id='tspotliste' class='tspotliste' role='listbox' hidden></div></div>"
            "<div><label for='tdatum'>" + T("Datum") + "</label>"
            f"<input type='date' id='tdatum' name='datum' value='{html.escape(heute)}' max='{html.escape(heute)}'></div>"
            "<div><label for='tvon'>" + T("von") + "</label><input type='time' id='tvon' name='von'></div>"
            "<div><label for='tbis'>" + T("bis") + "</label><input type='time' id='tbis' name='bis'></div>"
            "<div><label for='twing'>" + T("Wing") + "</label><select id='twing' name='wing'></select></div>"
            "</div>"
            # Die Beschriftungen stehen als Tabellen in tagebuch.py — übersetzt wird hier
            "<div class='tzeile'><span class='tlabel'>" + T("Leistung") + "</span>"
            + wahl("leistung", [(k, T(t)) for k, t in tagebuch.LEISTUNG.items()]) + "</div>"
            "<div class='tzeile'><span class='tlabel'>" + T("Wasser") + "</span>"
            + wahl("wasser", [(k, T(t)) for k, t in tagebuch.WASSER.items()]) + "</div>"
            "<div class='tzeile'><span class='tlabel'>" + T("Note") + "</span>"
            + wahl("note", [(n, n) for n in range(1, 6)]) +
            "<span class='tklein'>" + T("1 schlecht · 5 top") + "</span></div>"
            "<button type='submit' class='go' id='tgo'>" + T("Eintragen") + "</button>"
            "</form>"
            "<div id='tstatus' class='status' style='display:none;margin-top:12px'>"
            "<span class='spinner'></span><span id='tstatustext'>" + T("Läuft …") + "</span></div>"
            "<div id='tbanner' style='margin-top:12px'></div>"
            "<details id='tprotokoll' style='margin-top:10px;display:none'><summary>" + T("Protokoll") + "</summary>"
            "<div class='inhalt'><pre id='tlog'></pre></div></details>"
            "</div>"
            "<div id='tvorschlaege'></div>"
            "<div id='tsessions'></div>"
            "<details class='erklaerung'><summary>" + T("So rechnet das Tagebuch") + "</summary>"
            "<ul class='rerklaer'>"
            "<li>" + T("<b>Was verglichen wird:</b> zu jeder Session holt Wingfoilscout, was es für genau diese Stunden "
                       "gesagt hätte — mit Regionalmodell, Windfaktor und Thermik, dieselbe Rechnung wie im Rückblick —, "
                       "was die einzelnen Modelle sagten und, wenn eine Messstation in 30 km steht, was gemessen "
                       "wurde.") + "</li>"
            "<li>" + T("<b>Was als Wind der Session gilt:</b> die Messung, wenn die Station höchstens "
                       "{km} km entfernt ist, sonst die Wingfoilscout-Vorhersage; was genommen "
                       "wurde, steht an jedem Beleg. Eine Station misst über Land in zehn Metern Höhe, an der Küste "
                       "meist weniger als draußen auf dem Wasser. Fehlt die Messung noch (beim DWD kommt gestern erst "
                       "mit der nächsten Tagesdatei), holt „Neu vergleichen“ sie später nach.",
                       km=f"{tagebuch.STATION_NAH_KM:.0f}") + "</li>"
            "<li>" + T("<b>Windfenster:</b> untermotorisiert bei einem Wind, den der Quiver für diesen Wing schon "
                       "als passend führt, hebt die Untergrenze; übermotorisiert im Fenster senkt die Obergrenze; "
                       "„passt“ außerhalb weitet das Fenster.") + "</li>"
            "<li>" + T("<b>Windfaktor:</b> jede Session grenzt ihn ein — „passt“ heißt, der rohe Modellwind "
                       "derselben Stunden mal Faktor lag im Fenster des gefahrenen Wings, untermotorisiert darunter, "
                       "übermotorisiert darüber. Vorgeschlagen wird der nächstliegende Faktor, zu dem alle Sessions des "
                       "Spots passen — die kleinste Änderung, die sie erklärt —, auf 0,05 gerundet, zwischen "
                       "{von} und {bis}. "
                       "Stunden mit angenommener Thermik zählen dafür nicht.",
                       von=i18n.zahl(tagebuch.FAKTOR_GRENZEN[0]),
                       bis=i18n.zahl(tagebuch.FAKTOR_GRENZEN[1])) + "</li>"
            "<li>" + T("<b>Übernehmen:</b> ein Vorschlag braucht mindestens {n} Sessions, die in "
                       "dieselbe Richtung zeigen, und ändert nichts von selbst — „Übernehmen“ schreibt das Windfenster in "
                       "<code>config.yaml</code> oder den Windfaktor in <code>spots.yaml</code>, nur diese eine Zeile, "
                       "Kommentare bleiben.", n=tagebuch.MIN_BELEGE) + "</li>"
            "<li>" + T("<b>Wo es liegt:</b> <code>tagebuch.json</code> im Wingfoilscout-Ordner — nur auf diesem Rechner, "
                       "nicht auf GitHub.") + "</li>"
            "</ul></details>"
            # Wie jede Seite: i18n.json_im_skript — auch ein `NaN` aus einer
            # tagebuch.json wird dort `null`
            + skript("\nvar TAGEBUCH = " + i18n.json_im_skript(daten) + ";\nvar SPOTS = " + i18n.json_im_skript(liste)
                     + ";\n" + TAGEBUCH_JS + "\n") +
            seitenende() + "</body></html>")


def start_tagebuch(cfg_path: str, ids: list) -> bool:
    """Vorhersage und Messung für diese Sessions holen — im Hintergrund.
    Zurückgeschrieben wird in die Datei, wie sie am Ende ist (siehe
    `tagebuch.vergleich_eintragen`)."""
    def arbeit():
        from . import tagebuch
        from .shoreline import load_store
        from .spots import load_spots
        gesucht = set(ids)
        sessions = [s for s in tagebuch.laden()["sessions"] if s.get("id") in gesucht]
        if not sessions:
            raise ValueError(T("Keine dieser Sessions steht noch im Tagebuch."))
        cfg = load_config(cfg_path)
        spots = {s["id"]: s for s in load_spots(str(SPOTS_FILE))}
        _log(TN("Vergleich für {n} Session", "Vergleich für {n} Sessions", len(sessions)))
        tagebuch.vergleichen(cfg, spots, load_store(GEOMETRY_FILE), sessions, log=_log)
        zahl = tagebuch.vergleich_eintragen({s["id"]: s["vergleich"] for s in sessions})
        n = zahl["neu"]
        gemessen = sum(1 for s in sessions if (s.get("vergleich") or {}).get("gemessen_kn") is not None)
        text = TN("{n} Session verglichen, {m} davon mit Messung.",
                  "{n} Sessions verglichen, {m} davon mit Messung.", n, m=gemessen)
        if zahl["behalten"]:
            text += " " + T("Bei {n} fand der neue Vergleich weniger als der vorige "
                            "(Netz oder Station) — dort bleibt der vorige stehen.", n=zahl['behalten'])
        with LOCK:
            JOB.update(state="done", summary=text)
    return _starte("tagebuch", arbeit)


PRESETS = [
    # (Schlüssel, Titel, Untertitel, Tage, Nächte, Radius km)
    #
    # „Nächte" ist kein Komfortwunsch, sondern ein Filter: bei einer Nacht muss
    # ein Spot zwei brauchbare Tage am Stück haben. Deshalb steht in der Mitte
    # bewusst der gleiche Wert wie in den Startwerten — sonst zeigt die Seite
    # beim ersten Öffnen „Eigene Einstellung" und keine Voreinstellung leuchtet.
    ("spontan", N_("Spontan"), N_("2 Tage · 250 km"), 2, 0, 250),
    ("wochenende", N_("Wochenende"), N_("3 Tage · 500 km"), 3, 0, 500),
    ("tour", N_("Mit Übernachtung"), N_("4 Tage · 2 am Stück · 1000 km"), 4, 2, 1000),
]


def page(cfg, v: dict) -> str:
    """Die Oberfläche: eine Entscheidung vorn, alles andere dahinter.

    Die erste Fassung zeigte vierzig Bedienelemente gleichzeitig — Mindest-Score,
    Kabbel-Aversion, Böigkeitsgrenze, vier Gewässertypen. Das ist ein Mischpult.
    Gebraucht wird meistens nur zweierlei: von wo, und wie lange. Alles andere
    hat einen brauchbaren Wert und gehört weggeklappt, ohne verloren zu gehen.
    """
    lo, hi = quiver_range(cfg)
    n_spots, n_missing = geometry_state()
    hlat = float(cfg["rider"]["home"]["lat"])
    hlon = float(cfg["rider"]["home"]["lon"])
    heim = cfg["rider"]["home"]["name"]          # escaped mit dem ganzen Platzhaltertext (Startfeld)

    grass_opts = "".join(
        f'<option value="{k}"{" selected" if v["grass"] == k else ""}>{html.escape(T(t))}</option>'
        for k, t in GRASS)
    type_boxes = "".join(
        f'<label><input type="checkbox" name="types" value="{k}"'
        f'{" checked" if k in v["types"] else ""}> {html.escape(T(t))}</label>' for k, t in WATER_TYPES)
    preset_buttons = "".join(
        f'<button type="button" class="preset" data-tage="{tage}" data-naechte="{n}" '
        f'data-radius="{r}" aria-pressed="false"><b>{html.escape(T(titel))}</b>'
        f'<span>{html.escape(T(unter))}</span></button>'
        for _, titel, unter, tage, n, r in PRESETS)

    # Wie viele Spots sehen nach falscher Koordinate aus? Die Zahl steht hier,
    # weil man sie sonst nur einmal im Protokoll des Geometrielaufs sähe —
    # und dort nichts damit anfangen kann.
    try:
        alle = pruef_liste(cfg.get("rider", {}).get("home"))[0]
    except Exception:                                          # noqa: BLE001
        alle = []
    n_pruefen = sum(1 for e in alle if e["stufe"] != "unbestaetigt")
    n_offen = sum(1 for e in alle if e["stufe"] == "unbestaetigt")
    teile = []
    if n_pruefen:
        teile.append(T("bei {n} passt die Ufergeometrie nicht zur Koordinate", n=n_pruefen))
    if n_offen:
        teile.append(T("{n} sind nie bestätigt worden", n=n_offen))
    pruef_zeile = ("" if not teile else
                   f'<div class="fuss" style="margin-top:10px">'
                   f'<a class="ghost mini" href="/pruefen" target="_blank" rel="noopener" '
                   f'style="text-decoration:none;border:1px solid var(--line);'
                   f'border-radius:9px;padding:10px 13px;color:var(--ink-2)">'
                   f'{T("Koordinaten prüfen")}</a>'
                   '<span class="hint">'
                   + T("{befund} — auf der Karte nachsehen und korrigieren.",
                       befund=html.escape(_gross(" · ".join(teile))))
                   + '</span></div>')

    zustand = ('<span class="hint">'
               + T("{n} von {gesamt} Spots fehlt sie noch. "
                   "Einmalig je Spot, danach rechnet die Suche ohne Netz.", n=n_missing, gesamt=n_spots)
               + '</span>'
               if n_missing else
               '<span class="hint">' + T("Alle {n} Spots haben eine.", n=n_spots) + '</span>')
    geo_knopf = (f'<div class="gruppe"><h4>{T("Ufergeometrie")}</h4>'
                 f'<div class="fuss" style="margin-top:0">'
                 f'<button type="button" class="ghost mini" id="rungeo">'
                 f'{T("Fehlende berechnen") if n_missing else T("Neu berechnen")}</button>'
                 f'{zustand}</div>{pruef_zeile}</div>')

    # Was das Skript der Startseite aus Python braucht: Heimatkoordinate und
    # Kartenbibliothek (Adresse und Prüfsumme). Der Rest steht in web/suche.js.
    # Die Zahlen über i18n.json_im_skript wie alle Daten in Skripten: ein `.nan`
    # in config.yaml stand bis 2.1.0 als `nan` in der Seite — ein
    # ReferenceError, und das ganze Skript der Startseite lief nicht.
    # „Ab wann?“ (seit 2.3.0): frühestens jetzt, spätestens der letzte Tag der
    # Vorhersage — der Kalender des Browsers zeigt nur, was geht.
    ab_min = zeitraum.fuer_feld(datetime.now())
    letzter = zeitraum.letzter_tag()
    ab_max = letzter.isoformat() + "T23:59"

    start_js = ("var HOME = {lat: " + i18n.json_im_skript(hlat) + ", lon: " + i18n.json_im_skript(hlon) + "};\n"
                "var LEAFLET = " + i18n.json_im_skript({"css": LEAFLET_CSS, "cssSri": LEAFLET_CSS_SRI,
                                                        "js": LEAFLET_JS, "jsSri": LEAFLET_JS_SRI}) + ";")

    return seitenkopf("Wingfoilscout", CSS + REITER_CSS) + f"""<div class="wrap" id="wrap">
{reiter("/")}
<h1>Wingfoilscout</h1>
<p class="sub">{T('{n} Spots im Katalog · dein Quiver deckt {lo}–{hi} kn ab', n=n_spots, lo=f'{lo:.0f}', hi=f'{hi:.0f}')}</p>

<form id="f">
  <div class="karte">
    <label for="start">{T('Von wo aus?')}</label>
    <div class="feldzeile">
      <input type="text" id="start" name="start" value="{html.escape(str(v.get("start", "")))}"
             placeholder="{html.escape(T('{heim} – oder Koordinate/Maps-Link einfügen', heim=heim))}" autocomplete="off">
      <button type="button" class="ghost mini" id="gps" title="{html.escape(T('Aktuelle Position über den Browser'))}">{T('Hier')}</button>
      <button type="button" class="ghost mini" id="pick" title="{html.escape(T('Punkt auf der Karte wählen'))}">{T('Karte')}</button>
    </div>
    <p id="gpsmsg" class="klein"></p>
    <div id="pickmap" style="display:none;height:300px;margin-top:12px;border-radius:10px;
         border:1px solid var(--line)"></div>

    <div class="abwann">
      <label for="ab">{T('Ab wann?')}</label>
      <div class="feldzeile">
        <input type="datetime-local" id="ab" name="ab" value="{html.escape(str(v.get("ab", "")))}"
               min="{ab_min}" max="{ab_max}">
        <button type="button" class="ghost mini" id="abjetzt" title="{html.escape(T('Feld leeren — die Suche beginnt jetzt'))}">{T('Jetzt')}</button>
      </div>
      <p class="klein">{T('Leer heißt jetzt. Die Tage zählen ab hier, die Vorhersage reicht bis {datum}.', datum=i18n.datum_jahr(letzter))}</p>
    </div>

    <div class="presets">{preset_buttons}</div>
    <p class="eigen" id="eigen"></p>

    <button type="submit" class="go" id="go">{T('Spots suchen')}</button>
  </div>

  <details id="mehr">
    <summary>{T('Suche genauer einstellen')}</summary>
    <div class="inhalt">
      <div class="gruppe"><h4>{T('Zeitraum und Weg')}</h4><div class="row">
        {field("days", T('Tage voraus'), v["days"], "1", "", 1, 16)}
        {field("radius", T('Radius'), v["radius"], "10", "km", 10)}
        {field("nights", T('Übernachtungen'), v["nights"], "1", T('Nächte'), 0, 14)}
        {field("max_drive", T('max. Fahrt'), v["max_drive"], "0.5", "h", 0.5)}
      </div>
      <p class="hint" style="margin:9px 0 0">{T('''Eine Übernachtung heißt: der Spot muss zwei
      brauchbare Tage am Stück haben. Das grenzt ein, statt zu erlauben.''')}</p></div>

      <div class="gruppe"><h4>{T('Was als Session zählt')}</h4><div class="row">
        {field("min_hours", T('Mindestdauer'), v["min_hours"], "0.5", "h", 0.5)}
        {field("min_score", T('Mindestgüte'), v["min_score"], "0.05", "0–1", 0.1, 0.95)}
        {field("pref_low", T('Wohlfühlband von'), v["pref_low"], "1", T('kn'))}
        {field("pref_high", T('Wohlfühlband bis'), v["pref_high"], "1", T('kn'))}
      </div></div>

      <div class="gruppe"><h4>{T('Grenzen')}</h4><div class="row">
        {field("air_min", T('Luft von'), v["air_min"], "1", "°C")}
        {field("air_max", T('Luft bis'), v["air_max"], "1", "°C")}
        {field("water_min", T('Wasser ab'), v["water_min"], "1", "°C")}
        {field("gust_bad", T('Böigkeit max.'), v["gust_bad"], "0.05", T('Böe/Mittel'), 1)}
      </div></div>

      <div class="gruppe"><h4>{T('Wasser')}</h4>
      <div class="row" style="margin-bottom:12px">
        {field("chop", T('Kabbel-Aversion'), v["chop"], "0.05", "0–1", 0, 1)}
        <div><label for="grass">{T('Seegras ausschließen')}</label>
          <select id="grass" name="grass">{grass_opts}</select></div>
      </div>
      <div class="checks">
        <label><input type="checkbox" name="shallow"{" checked" if v["shallow"] else ""}>
          {T('Nur Spots mit Tiefe')}</label>
        <label><input type="checkbox" name="req_dogs"{" checked" if v.get("req_dogs") else ""}>
          {T('Hundeverbote ausblenden')}</label>
        <label><input type="checkbox" name="no_forbidden"{" checked" if v.get("no_forbidden") else ""}>
          {T('Spots ohne Erlaubnis ausblenden')}</label>
      </div>
      <div class="checks" style="margin-top:11px">{type_boxes}</div></div>
    </div>
  </details>

  <details id="quellen">
    <summary>{T('Datenquellen')}</summary>
    <div class="inhalt">
      <div class="checks">
        <label><input type="checkbox" name="geo"{" checked" if v["geo"] else ""}>
          {T('Ufergeometrie nutzen')}</label>
        <label><input type="checkbox" name="routing"{" checked" if v.get("routing", True) else ""}>
          {T('Fahrzeiten routen')}</label>
        <label><input type="checkbox" name="ensemble"{" checked" if v.get("ensemble", True) else ""}>
          {T('Wahrscheinlichkeit (Ensemble)')}</label>
        <label><input type="checkbox" name="highres"{" checked" if v.get("highres", True) else ""}>
          {T('Hochauflösende Modelle')}{hinweis("highres")}</label>
        <label><input type="checkbox" name="camping"{" checked" if v.get("camping", True) else ""}>
          {T('Stellplätze mit Hund')}</label>
        <label><input type="checkbox" name="marine"{" checked" if v["marine"] else ""}>
          {T('Wassertemperatur und Wellenmodell')}{hinweis("marine")}</label>
        <label><input type="checkbox" name="alerts"{" checked" if v.get("alerts", True) else ""}>
          {T('Wetterwarnungen')}</label>
        <label><input type="checkbox" name="demo"{" checked" if v["demo"] else ""}>
          {T('Demo-Modus')}</label>
      </div>
      {geo_knopf}
      {handy_kasten(PORT["nr"])}
    </div>
  </details>

  <details id="spots">
    <summary>{T('Spots hinzufügen')}</summary>
    <div class="inhalt">
      <p class="hint" style="margin:0 0 12px">{T('''Eine Zeile je Spot: Name und Koordinate in beliebiger
      Reihenfolge, Gewässerart optional als letztes Feld. Als Datei gehen GPX, KML, GeoJSON und CSV.''')}</p>
      <textarea id="spots_text" name="spots_text" rows="4" spellcheck="false"
        placeholder="Hardtsee; 49.17008, 8.61477&#10;https://www.google.com/maps/@51.7625,3.854,15z"></textarea>
      <div class="checks" style="margin-top:12px">
        <label><input type="checkbox" name="spot_geo" checked> {T('Ufergeometrie gleich mitrechnen')}</label>
        <label style="gap:8px">{T('Datei:')} <input type="file" id="spotfile"
          accept=".gpx,.kml,.json,.geojson,.csv,.txt"></label>
      </div>
      <div class="fuss">
        <button type="button" class="ghost mini" id="addspots">{T('Aufnehmen')}</button>
        <span class="hint">{T('Landet in <code>spots.yaml</code> und zählt ab der nächsten Suche mit.')}</span>
      </div>
      <p class="hint" style="margin:10px 0 0">{vorschlag_satz()}</p>
    </div>
  </details>

  <div class="fuss">
    <button type="button" class="ghost mini" id="save"
            title="{html.escape(T('Merkt die Einstellungen aus den Klappen für den nächsten Start — nicht den Startpunkt'))}">{T('Als Standard merken')}</button>
    <span class="hint" id="hint">{T('Einstellungen aus den Klappen für den nächsten Start merken (nicht den Startpunkt).')}</span>
  </div>
</form>

<div id="panel">
  <div id="banner"></div>
  <div id="statusbox" class="status" style="display:none">
    <span class="spinner"></span><span id="statustext">{T('Suche läuft …')}</span>
  </div>
  <details id="protokoll" style="margin-top:10px;display:none">
    <summary>{T('Protokoll')}</summary><div class="inhalt"><pre id="log"></pre></div>
  </details>
  <div id="frame"></div>
</div>

{skript(start_js + chr(10) + SUCHE_JS)}
{seitenende()}</body></html>"""


# ── Server ───────────────────────────────────────────────────────────────────

def _gross(text: str) -> str:
    """Erster Buchstabe groß, der Rest wie er ist — `str.capitalize()` machte
    bis 2.1.0 aus „Ufergeometrie“ mitten im Satz „ufergeometrie“."""
    return text[:1].upper() + text[1:]


def report_mit_reitern(roh: bytes) -> bytes:
    """Den gespeicherten Report so ausliefern, dass die Reiterleiste dabei ist.

    Die Datei selbst bleibt unangetastet: sie wandert per AirDrop aufs iPhone
    und wird dort ohne Server geöffnet — Reiter, die ins Leere zeigen, wären
    da verkehrt. Über den Server dagegen ist der Report der Reiter „Ziele“ und
    braucht den Weg zurück zu Suche, Rückblick und Tagebuch.

    Die eingesetzten Skripte tragen die Nonce aus dem Kopf der Datei (seit
    1.19.1) — die Datei hat ihre eigene, und Kopfzeile und Datei müssen
    dieselbe nennen; `report_nonce()` liest sie für die Kopfzeile. Ein Report
    von vor 1.19.1 hat keine; dann kommen die Skripte ohne, und der Server
    schickt für diese Antwort keine Richtlinie.
    """
    # Die Leiste gehört an den Anfang der Seite, wie auf jeder anderen: am
    # Rechner ist sie ein Element im Textfluss, und bis 1.18.0 stand sie vor
    # `</body>` — am Handy egal (dort ist sie unten festgeheftet), am Rechner
    # aber unsichtbar am Ende von 40 Bildschirmen Report; zurück zur Suche ging
    # nur mit dem Zurück-Knopf des Browsers (gefunden am 25.09.2026).
    if b"</body>" not in roh:
        return roh
    stil = als_bytes("<style>" + REITER_CSS + "</style>")
    # Im eingebetteten Report (die Startseite zeigt ihn am Rechner in einem
    # Rahmen) wäre die Leiste eine zweite Navigation im Fenster — sie würde den
    # Rahmen umschalten statt die Seite. Also nimmt sie sich dort selbst heraus.
    n = csp.nonce_aus_datei(roh)
    kopf = f"<script nonce='{n}'>" if n else "<script>"
    # Ein Report von vor 2.1.0 hat keinen Sprachvorspann; beenden.js und
    # lauf.js brauchen aber `t()` — dann kommt er hier mit.
    vorspann = "" if b"window.T=" in roh else i18n.js_vorspann() + "\n"
    leiste = als_bytes(reiter_leiste("/report")
                       + kopf + vorspann + "if (window.top !== window.self) "
                         "document.querySelector('nav.reiter').remove();\n"
                       + _web("beenden.js") + "\n" + _web("lauf.js") + "\n" + _web("sprache.js") + "</script>")
    if b"</head>" in roh:
        roh = roh.replace(b"</head>", stil + b"</head>", 1)
    else:
        leiste = stil + leiste
    anfang = b"<div class='wrap'>"
    if anfang in roh:
        return roh.replace(anfang, anfang + leiste, 1)
    if b"<body>" in roh:
        return roh.replace(b"<body>", b"<body>" + leiste, 1)
    return roh.replace(b"</body>", leiste + b"</body>", 1)


def report_in_sprache(roh: bytes, sprache: str | None = None) -> bytes:
    """Der Report der letzten Suche in der Sprache der Anfrage — wenn die
    Suche ihn so abgelegt hat (seit 2.3.0, report.fassungen_schreiben), sonst
    report.html, wie es ist. Bis 2.1.0 zeigte „Ziele“ nach dem Umschalten der
    Sprache den Report weiter in der alten, bis zur nächsten Suche."""
    return report_fassung(roh, sprache or i18n.aktuell()) or roh


def datum_lesbar(iso: str) -> str:
    """„2026-09-25T14:27“ → „25.09.2026 14:27“ — wie überall sonst in der
    Oberfläche (Review 25.09., U6), in der Form der Sprache: „25 Sep 2026,
    14:27“ (i18n.datum_zeit). Was nicht so aussieht, bleibt, wie es ist."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?", iso or "")
    if not m:
        return iso or ""
    try:
        dt = datetime(*(int(g or 0) for g in m.groups()))
    except ValueError:                                    # 2026-02-30, 25:00
        return iso
    return i18n.datum_zeit(dt) if m.group(4) else i18n.datum_jahr(dt)


# Die Gegenstelle ist weg oder antwortet nicht mehr. `socket.timeout` eigens:
# erst seit Python 3.10 ist es dasselbe wie TimeoutError.
ABGERISSEN = (ConnectionError, TimeoutError, socket.timeout)


def _ohne_pfade(text: str) -> str:
    """Absolute Pfade gekürzt: was im Wingfoilscout-Ordner liegt, heißt wie
    darin („spots.yaml“, „wingscout/cli.py“), der Rest des Benutzerordners
    „~/…“ — der Benutzername (macOS: /Users/<name>/) bleibt auf dem Mac."""
    ersatz = [(str(ROOT) + os.sep, "")]
    try:
        ersatz.append((str(Path.home()) + os.sep, "~" + os.sep))
    except (RuntimeError, KeyError, OSError):                  # kein Benutzerordner bestimmbar
        pass
    for pfad, kurz in ersatz:
        if len(pfad) > 2:
            text = text.replace(pfad, kurz)
    return text


def fehler_satz(exc: BaseException) -> str:
    """Ein Satz für den Browser, ohne Dateipfade und Benutzernamen: die stehen
    im Terminal (Review 25.09., S9).

    Wörtlich weiter geht nur, was Wingfoilscout selbst als Satz formuliert —
    Katalog, Konfiguration, Tagebuch, Overpass, der unbekannte Spot (seine
    Kennung kam mit der Anfrage) —, mit gekürzten Pfaden. Eine Datei, die sich
    nicht lesen oder schreiben lässt, nennt den Grund, nicht den Pfad; alles
    andere nur seine Art. Bis 2.1.0 gaben die Schreibwege der Katalog- und
    Prüfseite die Ausnahme roh weiter, samt `/Users/<name>/…` (A4)."""
    from .sources.overpass import OverpassError
    from .spotedit import SpotNichtGefunden
    from .tagebuch import TagebuchFehler
    if isinstance(exc, (KatalogFehler, KonfigFehler, TagebuchFehler, OverpassError, SpotNichtGefunden)):
        return _ohne_pfade(str(exc))
    # Netz und Gegenstelle sind keine Datei: dort nur die Art (URLError, …)
    if isinstance(exc, OSError) and not isinstance(exc, (urllib.error.URLError,) + ABGERISSEN):
        return T("Datei nicht lesbar oder schreibbar ({grund})", grund=exc.strerror or type(exc).__name__)
    return type(exc).__name__


def fehler_page(exc: BaseException) -> str:
    """Die Seite, wenn Katalog oder Konfiguration nicht lesbar sind — mit dem
    Grund und dem, was zu tun ist. Bis 1.18.3 brach die Verbindung ohne ein
    Wort ab (Review 25.09., U1)."""
    grund = fehler_satz(exc)
    print(T("Seite nicht gebaut: {fehler}", fehler=exc), file=sys.stderr)
    was = ("spots.yaml" if isinstance(exc, KatalogFehler) else
           "config.yaml" if isinstance(exc, KonfigFehler) else T("eine Datei"))
    return (seitenkopf(T("Wingfoilscout · Fehler"), CSS + REITER_CSS) + "<div class='wrap'>"
            + reiter_leiste("") +
            "<h1>" + T("Das geht gerade nicht") + "</h1>"
            "<p class='sub'>" + T("{datei} lässt sich nicht lesen.", datei=html.escape(was)) + "</p>"
            f"<div class='banner b-err'>{html.escape(grund)}</div>"
            "<div class='karte'><p style='margin:0 0 10px'>" + T("Was hilft:") + "</p>"
            "<ul style='margin:0;padding-left:20px;line-height:1.7'>"
            "<li>" + T("Die genannte Stelle in <code>{datei}</code> ansehen — meist ein fehlendes "
                       "Anführungszeichen oder eine verrutschte Einrückung.", datei=html.escape(was)) + "</li>"
            "<li>" + T("Wenn die Datei aus Git kommt: <code>git checkout spots.yaml</code> holt den letzten "
                       "sauberen Stand zurück (eigene Änderungen seit dem letzten Commit gehen dabei verloren).")
            + "</li>"
            "<li>" + T("<code>bash tools/check.sh</code> nennt jeden Fehler im Katalog mit Spot und Feld.") + "</li>"
            "</ul></div>" + seitenende() + "</body></html>")


def kein_report_page() -> str:
    """Der Reiter „Ziele“, solange noch keine Suche gelaufen ist."""
    return (seitenkopf(T("Wingfoilscout · Ziele"), CSS + REITER_CSS) + "<div class='wrap'>"
            + reiter("/report") +
            "<h1>" + T("Ziele") + "</h1>"
            "<p class='sub'>"
            + T("Hier stehen die besten Ziele der letzten Suche — mit Wind, Wing, Fahrzeit "
                "und Stellplätzen.")
            + "</p>"
            "<div class='karte'><p style='margin:0 0 14px'>"
            + T("Noch kein Report vorhanden. Die Suche läuft auf "
                "dem Mac und dauert je nach Umkreis ein bis zwei Minuten.")
            + "</p>"
            "<a href='/' style='text-decoration:none'><button type='button' class='go' "
            "style='margin-top:0'>" + T("Zur Suche") + "</button></a></div>"
            + seitenende() + "</body></html>")


# ── Hilfe ────────────────────────────────────────────────────────────────────
# Zwei Seiten hinter dem „?“ der Leiste: die Anleitung (das README) und „Wie
# Wingfoilscout rechnet“ (docs/bewertung.html) — in der Sprache der
# Oberfläche, sonst auf Englisch mit einem Satz dazu. Gerendert und gesäubert
# wird in wingscout/hilfe.py, einmal je Datei und Stand.

HILFE_CSS = _web("hilfe.css")
HILFE_SEITEN = [(HILFE_PFAD, N_("Anleitung")), (RECHNUNG_PFAD, N_("Wie Wingfoilscout rechnet"))]


def hilfe_kopf(aktiv: str, uebersetzt: bool) -> str:
    """Titel, die Umschaltung Anleitung · Wie Wingfoilscout rechnet und — wenn
    es die Seite in dieser Sprache noch nicht gibt — der Satz dazu."""
    hier = " aria-current='page'"
    wahl = "".join(f"<a href='{pfad}'{hier if pfad == aktiv else ''}>{html.escape(T(name))}</a>"
                   for pfad, name in HILFE_SEITEN)
    hinweis = ("" if uebersetzt else
               "<p class='hilfehinweis'>"
               + html.escape(T("Diese Seite ist noch nicht übersetzt — hier steht die englische Fassung."))
               + "</p>")
    return ("<div class='hilfekopf'><h1>" + html.escape(T("Hilfe")) + "</h1>"
            f"<nav class='hilfewahl' aria-label='{html.escape(T('Hilfe'))}'>{wahl}</nav></div>" + hinweis)


def hilfe_page() -> str:
    """Die Anleitung: das README der Sprache, mit Inhaltsverzeichnis der
    Abschnitte (am Rechner daneben, am Handy zugeklappt darüber)."""
    from . import hilfe
    a = hilfe.anleitung(i18n.aktuell())
    inhalt = "".join(f"<li><a href='#{html.escape(anker)}'>{html.escape(text)}</a></li>" for anker, text in a.inhalt)
    return (seitenkopf(T("Wingfoilscout · Anleitung"), CSS + REITER_CSS + HILFE_CSS)
            + "<div class='wrap hilfe'>" + reiter(HILFE_PFAD) + hilfe_kopf(HILFE_PFAD, a.uebersetzt)
            + "<div class='anleitungsraster'>"
            "<details class='inhaltsliste zu-am-handy' open><summary>" + html.escape(T("Inhalt")) + "</summary>"
            "<nav aria-label='" + html.escape(T("Inhalt")) + "'><ol>" + inhalt + "</ol></nav></details>"
            f"<article class='anleitung' lang='{a.sprache}'>" + a.html + "</article></div>"
            + seitenende() + "</body></html>")


def rechnung_page() -> str:
    """„Wie Wingfoilscout rechnet“: der Inhalt der Methodenseite mit ihren
    Abbildungen, gesäubert, in ihrem eigenen Kasten (`.methode`) — ihr Stil
    gilt nur dort, in hellem und dunklem Modus wie auf der Website."""
    from . import hilfe
    r = hilfe.rechnung(i18n.aktuell())
    return (seitenkopf(T("Wie Wingfoilscout rechnet"), CSS + REITER_CSS + r.css + "\n" + HILFE_CSS)
            + "<div class='wrap hilfe'>" + reiter(RECHNUNG_PFAD) + hilfe_kopf(RECHNUNG_PFAD, r.uebersetzt)
            + f"<article class='methode' lang='{r.sprache}'>" + r.html + "</article>"
            + seitenende() + "</body></html>")


class AnfrageZuGross(ValueError):
    """Mehr als `Handler.MAX_BODY` — darauf antwortet `_post` mit 413. Eine
    eigene Klasse, weil die Meldung seit 2.1.0 übersetzt wird und „groß“
    darin kein verlässliches Erkennungszeichen mehr ist."""


def als_bytes(text: str) -> bytes:
    """Der Rumpf einer Antwort aus Text — jede Seite und jede Meldung des
    Servers geht hier durch (`Handler._send` nimmt auch Text und schickt ihn
    hier durch): UTF-8, und was sich so nicht schreiben lässt, als „?“.

    Das ist ein einzelnes Surrogat (U+D800–DFFF): Python hält es in einem
    Text, YAML und JSON lesen es klaglos aus einer Datei, UTF-8 kennt es
    nicht. Ein strenges `encode("utf-8")` warf dann UnicodeEncodeError — bis
    2.1.0 auch beim Schreiben der Fehlerseite selbst, und die Verbindung riss
    ohne ein Wort ab (C2). Lieber ein Fragezeichen an der Stelle."""
    return text.encode("utf-8", "replace")


def json_bytes(wert, ensure_ascii: bool = False) -> bytes:
    """Eine JSON-Antwort, die `response.json()` im Browser lesen kann.

    Python schreibt eine Zahl, die keine ist, als `NaN` oder `Infinity` — das
    ist kein JSON, und der Browser verwirft dann die ganze Antwort: ein
    kaputter Messwert in `rueckblick.json` ließ bis 2.1.0 den ganzen Rückblick
    leer (C5). Jetzt steht dort `null` (`i18n.json_endlich`, derselbe Weg wie
    für die Daten in den Skripten der Seiten). Ein einzelnes Surrogat
    (`\\ud800` aus einer Datei) lässt sich nicht als UTF-8 schreiben; dann
    kommt die Antwort als ASCII mit Escapes — die Daten bleiben ganz, statt
    ein „?“ zu bekommen wie eine Seite (`als_bytes`)."""
    text = i18n.json_endlich(wert, ensure_ascii=ensure_ascii)
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError:
        return i18n.json_endlich(wert, ensure_ascii=True).encode("ascii")


class BegrenzterServer(ThreadingHTTPServer):
    """Der Server der Oberfläche: ein ThreadingHTTPServer mit Obergrenze für
    gleichzeitig offene Verbindungen (seit 2.1.0, A2).

    Je Verbindung ein Thread und eine Dateinummer — und den Zugangsschlüssel
    prüft der Handler erst, wenn die Kopfzeilen vollständig da sind. Mit
    `--lan` konnte deshalb jedes Gerät im WLAN ohne Schlüssel ein paar hundert
    Verbindungen halb öffnen und offen halten; macOS gibt einem Prozess 256
    Dateinummern, danach nahm Wingfoilscout keine Verbindung mehr an, auch
    nicht vom Mac selbst. Jetzt: höchstens `MAX_VERBINDUNGEN` zugleich, davon
    höchstens `MAX_VON_AUSSEN` von anderen Geräten — der Mac selbst kommt
    immer dran. Was darüber liegt, wird sofort geschlossen, ohne Thread. Dazu
    das Zeitlimit je Lese- und Schreibvorgang (`Handler.timeout`) und für
    andere Geräte eine Frist für die ganze Verbindung (`Handler.setup`).
    """
    MAX_VERBINDUNGEN = 64
    MAX_VON_AUSSEN = 24

    def __init__(self, *args, **kwargs):
        self._offen_lock = threading.Lock()
        self.offen = {"alle": 0, "aussen": 0}
        super().__init__(*args, **kwargs)

    @staticmethod
    def von_aussen(client_address) -> bool:
        """Nicht vom Mac selbst — dieselbe Regel wie in `zugang_pruefen`."""
        return not client_address or client_address[0] not in ("127.0.0.1", "::1")

    def process_request(self, request, client_address):
        aussen = self.von_aussen(client_address)
        with self._offen_lock:
            frei = (self.offen["alle"] < self.MAX_VERBINDUNGEN
                    and (not aussen or self.offen["aussen"] < self.MAX_VON_AUSSEN))
            if frei:
                self.offen["alle"] += 1
                self.offen["aussen"] += int(aussen)
        if not frei:
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._zu(aussen)                  # kein Thread gestartet, der sie wieder freigäbe
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._zu(self.von_aussen(client_address))

    def _zu(self, aussen: bool) -> None:
        with self._offen_lock:
            self.offen["alle"] -= 1
            self.offen["aussen"] -= int(aussen)

    def handle_error(self, request, client_address):
        # Gegenstelle weg oder zu langsam: kein Traceback im Terminal — bei
        # einer Flut halb offener Verbindungen wären es Hunderte
        if isinstance(sys.exc_info()[1], ABGERISSEN):
            return
        super().handle_error(request, client_address)


class Handler(BaseHTTPRequestHandler):
    cfg_path = str(ROOT / "config.yaml")
    # Zeitlimit je Lese- und Schreibvorgang auf der Verbindung (seit 2.1.0,
    # A2): wer eine Verbindung öffnet und nichts schickt — oder eine Antwort
    # nicht abholt —, belegt Thread und Dateinummer höchstens 15 s lang.
    # Rechnen (Ufergeometrie, Overpass) zählt nicht dazu, nur das Warten auf
    # die Gegenstelle. Siehe BegrenzterServer.
    timeout = 15
    # Dazu für andere Geräte eine Frist für die ganze Verbindung, von der
    # Annahme, bis die Antwort raus ist (seit 2.1.0, A2) — siehe setup().
    FRIST_VON_AUSSEN = 30
    # Eine Anfrage je Verbindung — die Vorgabe von http.server, hier
    # ausdrücklich: die Frist je Verbindung ist damit eine je Anfrage. Mit
    # HTTP/1.1 und Keep-alive zählte die Wartezeit zwischen zwei Anfragen mit.
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):        # kein Zugriffsprotokoll im Terminal
        pass

    # ── Frist für andere Geräte (A2) ────────────────────────────────────────

    def setup(self):
        """Wie bei jeder Verbindung — und für andere Geräte die Frist:
        höchstens `FRIST_VON_AUSSEN` Sekunden von der Annahme, bis die Antwort
        raus ist.

        Das Zeitlimit (`timeout`) gilt je Lese- und Schreibvorgang. Wer alle
        zehn Sekunden ein Byte der Kopfzeilen schickte, hielt eine Verbindung
        damit bis 2.1.0 beliebig lange — ohne Schlüssel, denn den prüft der
        Handler erst an den vollständigen Kopfzeilen; 24 solche Verbindungen
        (MAX_VON_AUSSEN) sperrten das iPhone aus. Läuft die Frist ab, schließt
        ein Timer die Verbindung in beide Richtungen (`_frist_um`); Lesen und
        Schreiben im Bearbeitungsthread enden dann sofort, und der Platz ist
        frei. Der Mac selbst hat keine Frist. Eine Anfrage je Verbindung
        (HTTP/1.0): eine Seite ist in ein, zwei Sekunden gebaut, die Suche
        läuft im Hintergrund. Nur die Arbeit an Katalog und Koordinaten wartet
        auf Overpass und Nominatim — die hält die Frist an (`_frist_angehalten`)."""
        super().setup()
        self._frist_sperre = threading.Lock()
        self._frist = None                # der laufende Timer, wenn einer läuft
        self._frist_ende = False          # finish() war da: nichts mehr schließen
        self.frist_abgelaufen = False
        von_aussen = getattr(self.server, "von_aussen", BegrenzterServer.von_aussen)
        if von_aussen(self.client_address):
            self._frist_starten()

    def _frist_starten(self) -> None:
        with self._frist_sperre:
            if self._frist_ende or self.frist_abgelaufen:
                return
            frist = threading.Timer(self.FRIST_VON_AUSSEN, self._frist_um)
            frist.daemon = True
            self._frist = frist
            frist.start()

    def _frist_um(self) -> None:
        """Die Frist ist abgelaufen: die Verbindung zu, in beide Richtungen.
        Unter der Sperre, die auch finish() nimmt — sonst träfe das Schließen
        womöglich schon eine neue Verbindung mit derselben Dateinummer."""
        with self._frist_sperre:
            if self._frist_ende:
                return
            self.frist_abgelaufen = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    @contextlib.contextmanager
    def _frist_angehalten(self):
        """Eigene Arbeit des Servers zählt nicht zur Frist: Overpass rechnet
        die Ufergeometrie eines verschobenen Spots, Nominatim nennt den Ort
        eines neuen — das dauert manchmal länger als die Frist, und die
        Antwort ginge verloren, obwohl gespeichert ist. Angehalten wird erst,
        wenn die Anfrage ganz gelesen ist und der Zugang geprüft — wer keinen
        Schlüssel hat, kommt nie hierher. Für die Antwort selbst gilt danach
        wieder eine volle Frist (und je Schreibvorgang das Zeitlimit)."""
        lief = False
        sperre = getattr(self, "_frist_sperre", None)
        if sperre is not None:
            with sperre:
                if self._frist is not None:
                    self._frist.cancel()
                    self._frist, lief = None, True
        try:
            yield
        finally:
            if lief:
                self._frist_starten()

    def _zu_spaet(self) -> bool:
        """Ist die Frist schon um, ist die Verbindung zu und die Anfrage
        womöglich nur halb da — dann wird nichts mehr bearbeitet."""
        if getattr(self, "frist_abgelaufen", False):
            self.close_connection = True
            return True
        return False

    def finish(self):
        sperre = getattr(self, "_frist_sperre", None)
        if sperre is not None:
            with sperre:
                self._frist_ende = True
                if self._frist is not None:
                    self._frist.cancel()
                    self._frist = None
        super().finish()

    # ── Antworten ───────────────────────────────────────────────────────────

    def _send(self, code, body, ctype="text/html; charset=utf-8", nonce_wert=None):
        """`body`: Bytes — oder Text, der dann durch `als_bytes()` geht.

        `nonce_wert`: None = die Nonce dieser Anfrage (Regelfall), ein Text =
        eine bestimmte (der gespeicherte Report bringt seine eigene mit),
        False = keine Richtlinie (ein Report von vor 1.19.1 hat keine Nonce,
        und ohne Nonce liefe darin kein Skript)."""
        if isinstance(body, str):
            body = als_bytes(body)
        self._begonnen = True             # ab hier keine zweite Antwort mehr (_fehler_antwort)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if ctype.startswith("text/html") and nonce_wert is not False:
            self.send_header("Content-Security-Policy", csp.richtlinie(nonce_wert or nonce()))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # SAMEORIGIN, nicht DENY: die Startseite bettet den Report selbst ein.
        # Eine fremde Seite könnte sonst die Prüfseite unsichtbar einbetten
        # und Klicks auf „Passt so“ unterschieben.
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        # Kein MIME-Raten, und kein Referer nach draußen: die Links zu Windy,
        # Google Maps und Park4Night müssen nicht wissen, von welcher lokalen
        # Adresse sie kamen (Review 25.09., S8).
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    MAX_BODY = 4 * 1024 * 1024          # 4 MB — reicht für jede GPX-Datei, die jemand ernsthaft lädt

    def _laenge(self) -> int:
        """Content-Length prüfen, bevor gelesen wird.

        `rfile.read(-1)` läse bis zum Ende der Verbindung — und die hält der
        Absender so lange offen, wie er will. Eine negative oder unlesbare
        Länge ist deshalb ein Fehler, keine leere Anfrage.
        """
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError(T("Ungültige Content-Length"))
        if length < 0:
            raise ValueError(T("Ungültige Content-Length"))
        if length > self.MAX_BODY:
            raise AnfrageZuGross(T("Anfrage zu groß"))
        return length

    def _rumpf(self) -> bytes:
        """Der Körper der Anfrage, ganz — sonst ConnectionAbortedError.

        Kommen weniger Bytes, als Content-Length sagt, ist die Gegenstelle
        mittendrin weg oder die Frist um (A2, `setup`): dann wird nichts
        bearbeitet, und die Verbindung schließt ohne Antwort. Bis 2.1.0 ging
        der Rest durch — ein halbes Formular hätte eine Suche mit halben
        Werten gestartet oder als Standard gemerkt."""
        length = self._laenge()
        roh = self.rfile.read(length)
        if len(roh) < length or getattr(self, "frist_abgelaufen", False):
            raise ConnectionAbortedError("Anfrage unvollständig")
        return roh

    def _form(self) -> dict:
        raw = self._rumpf().decode("utf-8", "replace")
        return urllib.parse.parse_qs(raw, keep_blank_values=True)

    def _json(self) -> dict:
        """JSON-Körper lesen — für die Prüfseite, die einzelne Werte schickt.
        Zu tief verschachtelt (RecursionError) ist auch kein gültiges JSON."""
        roh = self._rumpf()
        try:
            daten = json.loads(roh.decode("utf-8", "replace") or "{}")
        except (ValueError, RecursionError):
            raise ValueError(T("Kein gültiges JSON"))
        if not isinstance(daten, dict):
            raise ValueError(T("Erwartet wird ein JSON-Objekt"))
        return daten

    def _same_origin(self) -> bool:
        """Nur der eigene Browser-Tab darf etwas auslösen.

        Der Server hört nur auf 127.0.0.1 — aber jede Webseite, die im selben
        Browser offen ist, kann an 127.0.0.1:8765 Anfragen schicken. Ohne diese
        Prüfung könnte eine fremde Seite eine Suche starten, den Katalog
        beschreiben oder Wingfoilscout beenden. Browser senden bei Anfragen von
        fremden Seiten immer einen Origin-Header; stimmt er nicht, kommt 403.
        Der Host-Header fängt zusätzlich DNS-Rebinding ab. Seit 2.1.0 auch
        die Sec-Fetch-Kopfzeilen, siehe `_fremder_abruf()`.
        """
        if self._fremder_abruf():
            return False
        host = (self.headers.get("Host") or "").lower()
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        # Im WLAN-Betrieb zusätzlich die eigenen Adressen — aber nur die, nicht
        # jeden Namen: ein fremder Name, der auf 127.0.0.1 zeigt, bleibt so
        # ausgesperrt (DNS-Rebinding).
        allowed |= {f"{adresse}:{port}" for adresse in LAN["adressen"]}
        if host not in allowed:
            return False
        origin = self.headers.get("Origin")
        if origin and origin.lower() not in {f"http://{h}" for h in allowed}:
            return False
        return True

    def _fremder_abruf(self) -> bool:
        """Lädt eine fremde Seite hier etwas ein — als Bild, Skript, Rahmen,
        per `fetch` —, statt den Browser hierher zu schicken? (seit 2.1.0, A1)

        Bei solchen Anfragen setzt der Browser keinen Origin-Header: ein
        `<img src="http://127.0.0.1:8765/logo.png">` oder ein
        `fetch(…, {mode: "no-cors"})` von irgendeiner Webseite kam bis 2.1.0
        durch. Jede Seite im Browser konnte so feststellen, dass Wingfoilscout
        läuft (das Logo lädt), und den Rechner mit teuren Seiten beschäftigen
        (die Startseite kostet knapp eine Sekunde Rechenzeit). Die
        Sec-Fetch-Kopfzeilen kann keine Webseite fälschen: `cross-site` und
        `same-site` (eine andere Seite, auch auf 127.0.0.1 mit anderem Port)
        dürfen nur das ganze Fenster hierher schicken — einen Link, ein
        Lesezeichen. Was der Starter öffnet und was am iPhone eingetippt wird,
        kommt als `none`, alles aus den eigenen Seiten als `same-origin`.
        Ohne diese Kopfzeilen (alte Browser, curl, die Tests) bleibt es bei der
        Prüfung von Host und Origin."""
        seite = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if seite not in ("cross-site", "same-site"):
            return False
        # Vorausladen auf Geheiß einer fremden Seite (Speculation Rules) kommt
        # als Navigation, ist aber nie ein Klick: `Sec-Purpose: prefetch`
        if "prefetch" in (self.headers.get("Sec-Purpose") or self.headers.get("Purpose") or "").lower():
            return True
        modus = (self.headers.get("Sec-Fetch-Mode") or "").strip().lower()
        ziel = (self.headers.get("Sec-Fetch-Dest") or "").strip().lower()
        # Ein Rahmen ist auch eine Navigation, aber eine eingebettete — die
        # Richtlinie verbietet ihn ohnehin (frame-ancestors, X-Frame-Options)
        return not (modus == "navigate" and ziel in ("", "document"))

    def _antwort(self, code: int, **werte):
        self._send(code, json_bytes(werte), "application/json")

    def _fehler(self, code: int, vorlage: str, exc: BaseException) -> None:
        """Eine Fehlerantwort als JSON — `vorlage` mit dem Platzhalter
        `{fehler}`. Der Browser bekommt `fehler_satz(exc)`, ohne Pfade und
        Benutzernamen (bis 2.1.0 die rohe Ausnahme, A4); was dabei wegfällt,
        steht im Terminal."""
        satz = fehler_satz(exc)
        if satz != str(exc):
            print(T(vorlage, fehler=exc), file=sys.stderr)
        self._antwort(code, error=T(vorlage, fehler=satz))

    def _fehler_antwort(self, exc: BaseException, als_json: bool) -> None:
        """Was nach einer Ausnahme beim Bearbeiten noch zu sagen ist — eine
        Fehlerseite oder JSON. Nichts, wenn die Gegenstelle weg ist oder die
        Antwort schon begonnen hat: eine zweite Antwort mitten in der ersten
        wäre nur Datensalat, und ein zweiter Schreibversuch auf eine tote
        Verbindung hinterließ bis 2.1.0 einen Traceback im Terminal."""
        if isinstance(exc, ABGERISSEN) or getattr(self, "_begonnen", False):
            self.close_connection = True
            return
        if not isinstance(exc, (KatalogFehler, KonfigFehler, OSError)):
            # Unerwartet — z. B. ein ValueError beim Bauen einer Seite (C2).
            # Bis 2.1.0 brach daran die Verbindung wortlos ab; der Traceback
            # bleibt fürs Terminal. Die Fehlerseite selbst geht durch
            # als_bytes(): ein Surrogat in der Meldung kostet sie nicht mehr.
            traceback.print_exc(limit=4, file=sys.stderr)
        try:
            if als_json:
                self._antwort(500, error=fehler_satz(exc))
            else:
                self._send(500, als_bytes(fehler_page(exc)))
        except ABGERISSEN:
            self.close_connection = True

    def _pruefen(self, path: str) -> None:
        """Koordinate korrigieren oder einen Spot als angesehen abhaken —
        und seit 1.10.0 die Katalogpflege: anlegen, umbenennen, löschen,
        verschieben (`/katalog/…`).

        Alles schreibt in `spots.yaml` — deshalb auf Textebene (siehe
        `spotedit`), damit die Kommentare des Katalogs erhalten bleiben, und
        unter derselben Sperre wie die Prüfseite: nie während eine Suche oder
        ein Geometrielauf die Datei liest oder schreibt.
        """
        try:
            daten = self._json()
        except ValueError as exc:
            self._antwort(400, error=str(exc))
            return
        spot_id = str(daten.get("id") or "")
        if not spot_id and path != "/katalog/neu":
            self._antwort(400, error=T("Kein Spot angegeben."))
            return
        # Ab hier eigene Arbeit: das Warten auf die Schreibsperre, Overpass,
        # Nominatim — sie zählt nicht zur Frist eines anderen Geräts (A2)
        with self._frist_angehalten():
            with LOCK:
                if JOB["state"] == "running":
                    self._antwort(409, error=T("Gerade läuft eine Suche oder ein Geometrielauf — "
                                               "erst abwarten, dann noch einmal."))
                    return
                PRUEFEN_AKTIV["n"] += 1
            try:
                with SCHREIB_LOCK:
                    if path.startswith("/katalog/"):
                        self._katalog_schreiben(path, spot_id, daten)
                    else:
                        self._pruefen_schreiben(path, spot_id, daten)
            finally:
                with LOCK:
                    PRUEFEN_AKTIV["n"] -= 1

    def _katalog_schreiben(self, path: str, spot_id: str, daten: dict) -> None:
        """Katalogpflege von der Katalogseite aus.

        Die Kennung (`id`) bleibt beim Umbenennen stehen: an ihr hängen die
        Ufergeometrie, die Instagram-Momentaufnahme, die Grundlinie des
        Prüfstands und jeder Cache. Löschen nimmt den Spot aus `spots.yaml`,
        aus `geometry.json` und aus `instagram.json`; der Block landet im
        Protokoll, falls es ein Versehen war. Verschieben ist dasselbe wie
        „Übernehmen" auf der Prüfseite.
        """
        from . import spotedit
        from .geo import parse_position
        from .shoreline import load_store, save_store
        from .spots import load_spots

        if path == "/katalog/verschieben":
            self._pruefen_schreiben("/pruefen/setzen", spot_id, daten)
            return

        if path == "/katalog/kommentar":
            text = kommentar_putzen(daten.get("comment"))
            if text is None:
                self._antwort(400, error=T("Ein Kommentar darf höchstens 2000 Zeichen haben."))
                return
            try:
                spotedit.set_text(SPOTS_FILE, spot_id, "comment", text)
            except (LookupError, OSError, ValueError) as exc:
                self._fehler(400, N_("Konnte nicht speichern: {fehler}"), exc)
                return
            self._antwort(200, ok=True, comment=text,
                          message=(T("Kommentar gespeichert.") if text else T("Kommentar entfernt.")))
            return

        if path == "/katalog/tide":
            # Drei Stufen für `tidal` (auto = Feld weg, ja/nein = true/false)
            # und wahlweise ein Tidenfenster als Block `tide:`; leer = keins.
            from .tide import FENSTER_ARTEN, FENSTER_STUNDEN, fenster_text
            modus = str(daten.get("tidal") or "auto").strip().lower()
            fahrbar = str(daten.get("fahrbar") or "").strip().lower()
            if modus not in ("auto", "ja", "nein"):
                self._antwort(400, error=T("Tiden: auto, ja oder nein."))
                return
            if fahrbar and fahrbar not in FENSTER_ARTEN:
                self._antwort(400, error=T("Fenster: hochwasser, niedrigwasser, auflaufend oder ablaufend."))
                return
            try:
                stunden = float(str(daten.get("stunden") or FENSTER_STUNDEN).replace(",", "."))
            except ValueError:
                self._antwort(400, error=T("Stunden: eine Zahl zwischen 0,5 und 6."))
                return
            if not 0.5 <= stunden <= 6:
                self._antwort(400, error=T("Stunden: eine Zahl zwischen 0,5 und 6."))
                return
            if modus == "nein" and fahrbar:
                self._antwort(400, error=T("Ein Tidenfenster passt nicht zu „Tiden: nein“."))
                return
            try:
                if modus == "auto":
                    spotedit.entferne_feld(SPOTS_FILE, spot_id, "tidal")
                else:
                    spotedit.set_flag(SPOTS_FILE, spot_id, "tidal", modus == "ja")
                if fahrbar:
                    zeilen = [f"fahrbar: {fahrbar}"]
                    if fahrbar in ("hochwasser", "niedrigwasser"):
                        zeilen.append(f"stunden: {stunden:g}")
                    spotedit.set_block(SPOTS_FILE, spot_id, "tide", zeilen)
                else:
                    spotedit.entferne_feld(SPOTS_FILE, spot_id, "tide")
            except (LookupError, OSError, ValueError) as exc:
                self._fehler(400, N_("Konnte nicht speichern: {fehler}"), exc)
                return
            fenster = {"fahrbar": fahrbar, "stunden": stunden} if fahrbar else None
            wort = T({"auto": N_("automatisch"), "ja": N_("ja"), "nein": N_("nein")}[modus])
            self._antwort(200, ok=True, tidal=modus, tide=fenster,
                          message=(T("Tiden: {wort}, fahrbar {fenster} — gilt ab der nächsten Suche.",
                                     wort=wort, fenster=fenster_text(fenster))
                                   if fenster else
                                   T("Tiden: {wort} — gilt ab der nächsten Suche.", wort=wort)))
            return

        if path == "/katalog/umbenennen":
            name = " ".join(spotedit.steuerzeichen_raus(str(daten.get("name") or "")).split())
            if not name or len(name) > 120:
                self._antwort(400, error=T("Ein Name braucht 1 bis 120 Zeichen."))
                return
            try:
                spotedit.set_text(SPOTS_FILE, spot_id, "name", name)
            except (LookupError, OSError, ValueError) as exc:
                self._fehler(400, N_("Konnte nicht speichern: {fehler}"), exc)
                return
            self._antwort(200, ok=True, name=name, message=T("Umbenannt in „{name}“.", name=name))
            return

        if path == "/katalog/loeschen":
            try:
                weg = spotedit.entferne(SPOTS_FILE, spot_id)
            except (LookupError, OSError, ValueError) as exc:
                self._fehler(400, N_("Konnte nicht löschen: {fehler}"), exc)
                return
            _log(T("Spot {id} aus dem Katalog gelöscht. Der Block, falls es ein Versehen war:", id=spot_id)
                 + "\n" + weg.rstrip())
            store = load_store(GEOMETRY_FILE)
            if store.pop(spot_id, None) is not None:
                save_store(GEOMETRY_FILE, store)
            from . import instagram
            instagram.entferne(spot_id)
            self._antwort(200, ok=True, message=T("„{id}“ gelöscht — der Eintrag steht im Protokoll.", id=spot_id))
            return

        if path != "/katalog/neu":
            self._antwort(404, error=T("Unbekannter Weg."))
            return

        from . import ingest
        name = " ".join(str(daten.get("name") or "").split())
        punkt = parse_position(str(daten.get("koordinate") or ""))
        if not punkt:
            self._antwort(400, error=T("Koordinate nicht lesbar — z. B. 51.7625, 3.854."))
            return
        if len(name) > 120:
            self._antwort(400, error=T("Ein Name braucht höchstens 120 Zeichen."))
            return
        lat, lon = punkt
        wasser = str(daten.get("water") or "") or None
        if wasser and wasser not in ("sea", "lagoon", "lake", "reservoir", "unknown"):
            self._antwort(400, error=T("Unbekannte Gewässerart."))
            return
        try:
            vorhanden = load_spots(str(SPOTS_FILE))
        except ValueError as exc:
            self._fehler(400, N_("Katalog nicht lesbar: {fehler}"), exc)
            return
        doppelt = ingest.too_close(lat, lon, vorhanden)
        if doppelt and not daten.get("trotzdem"):
            self._antwort(409, error=T("Da steht schon „{name}“ (näher als 300 m).", name=doppelt['name']),
                          doppelt=doppelt["id"])
            return
        from .sources import ortsname
        land_gegeben = bool(str(daten.get("country") or "").strip())
        ort = ortsname.vorschlag(lat, lon) if (not name or not land_gegeben) else None
        eintrag = ingest.build_entry(name, lat, lon, wasser, {s["id"] for s in vorhanden}, verified=True, ort=ort)
        notiz = " ".join(str(daten.get("notes") or "").split())
        if notiz:
            eintrag["notes"] = notiz[:500]
        kommentar = kommentar_putzen(daten.get("comment"))
        if kommentar is None:
            self._antwort(400, error=T("Ein Kommentar darf höchstens 2000 Zeichen haben."))
            return
        if kommentar:
            eintrag["comment"] = kommentar
        land = str(daten.get("country") or "").strip().upper()
        if land:
            if not re.fullmatch(r"[A-Z]{2}", land):
                self._antwort(400, error=T("Landeskürzel: zwei Buchstaben, z. B. FR."))
                return
            eintrag["country"] = land
        try:
            ingest.append_to_yaml(SPOTS_FILE, [eintrag])
        except OSError as exc:
            self._fehler(400, N_("Konnte nicht speichern: {fehler}"), exc)
            return
        _log(T("neu im Katalog: {name} ({lat}, {lon}) als {id}", name=eintrag['name'],
               lat=f"{lat:.5f}", lon=f"{lon:.5f}", id=eintrag['id']))
        antwort = {"ok": True, "id": eintrag["id"], "name": eintrag["name"], "country": eintrag["country"],
                   "water": eintrag["water_body"], "lat": eintrag["lat"], "lon": eintrag["lon"],
                   "notes": eintrag["notes"], "comment": eintrag.get("comment", "")}
        if daten.get("geometrie"):
            # Wie auf der Prüfseite: die Ufergeometrie gleich rechnen, mit
            # einer ehrlichen Meldung, wenn Overpass gerade nicht mag.
            from .shoreline import befund, build_one
            gcfg = load_config(self.cfg_path).get("geometry", {})
            try:
                geo = build_one(eintrag, float(gcfg.get("max_fetch_km", 25.0)), int(gcfg.get("ray_count", 36)), force=True)
                store = load_store(GEOMETRY_FILE)
                store[eintrag["id"]] = geo
                save_store(GEOMETRY_FILE, store)
                auffaellig = befund(geo)
                antwort["message"] = (T("Eingetragen. Ufergeometrie gerechnet — {befund}", befund=auffaellig[1])
                                      if auffaellig else
                                      T("Eingetragen, {km} km Anlauf in der besten Richtung.",
                                        km=f"{geo['max_fetch_km']:.1f}"))
            except Exception as exc:                          # noqa: BLE001
                antwort["message"] = T("Eingetragen. Die Ufergeometrie ließ sich gerade nicht rechnen ({fehler}) — "
                                       "„Fehlende berechnen“ holt das nach.", fehler=fehler_satz(exc))
        else:
            antwort["message"] = T("Eingetragen — „Fehlende berechnen“ in den Datenquellen holt die Ufergeometrie.")
        self._antwort(200, **antwort)

    def _pruefen_schreiben(self, path: str, spot_id: str, daten: dict) -> None:
        from . import spotedit
        from .geo import parse_position
        from .shoreline import befund, build_one, load_store, save_store
        from .spots import load_spots

        if path == "/pruefen/ok":
            # Zwei Vermerke mit verschiedener Bedeutung: `verified` heißt „die
            # Koordinate stimmt", `geo_ok` heißt „die Geometriewarnung habe ich
            # gesehen und sie geht in Ordnung". Der zweite nur dort, wo es auch
            # eine Warnung gibt — sonst stünde er bei hundert Spots ohne Anlass.
            try:
                spotedit.set_flag(SPOTS_FILE, spot_id, "verified", True)
                eintrag = load_store(GEOMETRY_FILE).get(spot_id)
                if eintrag and befund(eintrag):
                    spotedit.set_flag(SPOTS_FILE, spot_id, "geo_ok", True)
            except (LookupError, OSError, ValueError) as exc:
                self._fehler(400, N_("Konnte nicht speichern: {fehler}"), exc)
                return
            self._antwort(200, ok=True, erledigt=True,
                          message=T("Koordinate bestätigt — taucht nicht wieder auf."))
            return

        if path != "/pruefen/setzen":
            self._antwort(404, error=T("Unbekannter Weg."))
            return

        punkt = parse_position(str(daten.get("koordinate") or ""))
        if not punkt:
            self._antwort(400, error=T("Koordinate nicht lesbar."))
            return
        lat, lon = punkt
        try:
            spotedit.set_coords(SPOTS_FILE, spot_id, lat, lon)
            # Wer die Nadel selbst gesetzt hat, hat hingeschaut: das ist genau
            # die Bestätigung, die `verified` meint.
            spotedit.set_flag(SPOTS_FILE, spot_id, "verified", True)
        except (LookupError, OSError, ValueError) as exc:
            self._fehler(400, N_("Konnte nicht speichern: {fehler}"), exc)
            return

        # Die alte Geometrie gilt für die alte Koordinate — sie muss weg,
        # auch wenn das Neurechnen gleich scheitert.
        store = load_store(GEOMETRY_FILE)
        store.pop(spot_id, None)
        save_store(GEOMETRY_FILE, store)

        spot = next((x for x in load_spots(str(SPOTS_FILE)) if x["id"] == spot_id), None)
        if spot is None:
            self._antwort(200, ok=True, message=T("Koordinate gespeichert."))
            return
        cfg = load_config(self.cfg_path)
        gcfg = cfg.get("geometry", {})
        radius = float(gcfg.get("max_fetch_km", 25.0))
        n_dirs = int(gcfg.get("ray_count", 36))
        try:
            eintrag = build_one(spot, radius, n_dirs, force=True)
        except Exception as exc:                              # noqa: BLE001
            self._antwort(200, ok=True, erledigt=False,
                          message=T("Koordinate gespeichert. Die Ufergeometrie ließ sich "
                                    "gerade nicht rechnen ({fehler}) — „Fehlende berechnen“ "
                                    "holt das nach.", fehler=fehler_satz(exc)))
            return
        store[spot_id] = eintrag
        save_store(GEOMETRY_FILE, store)
        neuer = befund(eintrag)
        if neuer:
            self._antwort(200, ok=True, erledigt=False,
                          message=T("Gespeichert und neu gerechnet — aber weiterhin auffällig: {befund}",
                                    befund=neuer[1]))
        else:
            self._antwort(200, ok=True, erledigt=True,
                          message=T("Gespeichert. Jetzt {km} km "
                                    "Anlauf in der besten Richtung — sieht gut aus.",
                                    km=f"{eintrag['max_fetch_km']:.1f}"))

    def _tagebuch(self, path: str) -> None:
        """Session eintragen, löschen, neu vergleichen, Vorschlag übernehmen."""
        from . import tagebuch
        from .spots import load_spots
        try:
            daten = self._json()
        except ValueError as exc:
            self._antwort(400, error=str(exc))
            return
        try:
            cfg = load_config(self.cfg_path)
            spots = {s["id"]: s for s in load_spots(str(SPOTS_FILE))}
        except ValueError as exc:
            self._fehler(500, N_("Konfiguration oder Katalog nicht lesbar: {fehler}"), exc)
            return

        if path == "/tagebuch/neu":
            try:
                eintrag = tagebuch.pruefe(daten, spots, cfg["quiver"]["wings"])
                session = tagebuch.eintragen(eintrag)
            except tagebuch.TagebuchFehler as exc:
                self._antwort(400, error=str(exc))
                return
            except OSError as exc:
                self._fehler(500, N_("Tagebuch nicht schreibbar: {fehler}"), exc)
                return
            self._antwort(200, ok=True, id=session["id"],
                          gestartet=start_tagebuch(self.cfg_path, [session["id"]]))
        elif path == "/tagebuch/loeschen":
            if not tagebuch.loeschen(str(daten.get("id") or "")):
                self._antwort(404, error=T("Diese Session steht nicht (mehr) im Tagebuch."))
                return
            self._antwort(200, ok=True)
        elif path == "/tagebuch/vergleichen":
            ids = daten.get("ids")
            if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
                self._antwort(400, error=T("Keine Session angegeben."))
                return
            if start_tagebuch(self.cfg_path, ids):
                self._antwort(200, ok=True)
            else:
                self._antwort(409, error=T("Es läuft schon etwas — bitte warten."))
        elif path == "/tagebuch/uebernehmen":
            self._tagebuch_uebernehmen(daten, cfg, spots)
        else:
            self._antwort(404, error=T("Unbekannter Weg."))

    def _tagebuch_uebernehmen(self, daten: dict, cfg, spots: dict) -> None:
        """Einen Vorschlag übernehmen — nur den, der gerade vorgeschlagen ist.
        Geschrieben wird unter derselben Sperre wie auf der Prüfseite, nie
        während ein Lauf `config.yaml` oder `spots.yaml` liest; lässt sich die
        Datei danach nicht mehr laden, kommt die alte Fassung zurück."""
        from . import spotedit, tagebuch
        from .spots import load_spots
        try:
            v = tagebuch.passender_vorschlag(tagebuch.vorschlaege(tagebuch.laden(), cfg, spots), daten)
        except tagebuch.TagebuchFehler as exc:
            self._antwort(409, error=str(exc))
            return
        with LOCK:
            if JOB["state"] == "running":
                self._antwort(409, error=T("Gerade läuft eine Suche oder ein Vergleich — erst abwarten, "
                                           "dann noch einmal."))
                return
            PRUEFEN_AKTIV["n"] += 1
        try:
            with SCHREIB_LOCK:
                pfad = Path(self.cfg_path) if v["art"] == "windfenster" else SPOTS_FILE
                alt = pfad.read_text(encoding="utf-8")
                try:
                    if v["art"] == "windfenster":
                        tagebuch.wing_setzen(pfad, v["size"], v["low"], v["high"])
                        load_config(pfad)
                        meldung = T("Wing {groesse} m²: Windfenster jetzt {von}–{bis} kn "
                                    "(config.yaml). Gilt ab der nächsten Suche.",
                                    groesse=i18n.zahl(v['size'], 1), von=f"{v['low']:g}", bis=f"{v['high']:g}")
                    else:
                        spotedit.set_zahl(pfad, v["id"], "wind_factor", v["wert"])
                        load_spots(str(pfad))
                        meldung = T("{spot}: Windfaktor jetzt {faktor} (spots.yaml). "
                                    "Die Sessions dort werden neu verglichen.",
                                    spot=spots[v['id']]['name'], faktor=i18n.zahl(v['wert']))
                except Exception as exc:                              # noqa: BLE001
                    spotedit.schreibe_atomar(pfad, alt)
                    self._fehler(400, N_("Nicht übernommen: {fehler}"), exc)
                    return
        finally:
            with LOCK:
                PRUEFEN_AKTIV["n"] -= 1
        gestartet = False
        if v["art"] == "windfaktor":
            # Die Wingfoilscout-Werte der Sessions rechneten mit dem alten Faktor
            ids = [s["id"] for s in tagebuch.laden()["sessions"] if s.get("spot") == v["id"]]
            gestartet = bool(ids) and start_tagebuch(self.cfg_path, ids)
        self._antwort(200, ok=True, message=meldung, gestartet=gestartet)

    def _zugang(self) -> bool:
        """Im WLAN-Betrieb: ohne Schlüssel keine Antwort. Rückgabe False heißt,
        dass schon geantwortet wurde."""
        try:
            zerlegt = urllib.parse.urlparse(self.path)
        except ValueError:                    # `http://[x/` — unlesbar, also auch kein Schlüssel darin
            zerlegt = urllib.parse.urlparse("")
        k = (urllib.parse.parse_qs(zerlegt.query).get("k") or [""])[0]
        urteil = zugang_pruefen(self.client_address[0], k, self.headers.get("Cookie", ""))
        if urteil == "frei":
            return True
        if urteil == "setzen":
            # Den Schlüssel ins Cookie und ohne ihn in der Adresse weiterleiten,
            # damit er nicht in jedem Link und jeder Weitergabe mitwandert.
            ziel = zerlegt.path or "/"
            rest = "&".join(t for t in zerlegt.query.split("&") if not t.startswith("k="))
            if rest:
                ziel += "?" + rest
            self.send_response(302)
            self.send_header("Location", ziel)
            self.send_header("Set-Cookie", f"{COOKIE}={LAN['schluessel']}; Path=/; Max-Age=2592000; "
                                           f"HttpOnly; SameSite=Lax")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False
        self._send(401, als_bytes("<!doctype html><meta charset='utf-8'><title>Wingfoilscout</title>"
                                  "<body style='font:16px/1.5 -apple-system,sans-serif;padding:40px 24px;color:#14303C'>"
                                  "<h1 style='font-size:1.3rem'>" + T("Kein Zugang") + "</h1>"
                                  "<p>" + T("Diese Wingfoilscout-Oberfläche ist für das Heimnetz freigegeben, aber nur "
                                            "mit dem Schlüssel aus der Startadresse. Sie steht im Terminalfenster auf "
                                            "dem Mac, das Wingfoilscout gestartet hat.") + "</p></body>"))
        return False

    def _anfang(self) -> str | None:
        """Was jede Anfrage zuerst braucht: eine Nonce, die Sprache, den Pfad.
        None heißt: die Adresse ist unlesbar — `GET http://[x/` (vor Python
        3.11.4 auch `GET //[x`) ließ `urlparse` bis 2.1.0 mit einem ValueError
        aussteigen und die Verbindung abreißen."""
        self._begonnen = False
        nonce_neu()
        i18n.fuer_anfrage(self.headers.get("Accept-Language"))
        try:
            return urllib.parse.urlparse(self.path).path
        except ValueError:
            return None

    def do_GET(self):
        if self._zu_spaet():              # die Frist ist um (A2): nichts mehr bauen
            return
        path = self._anfang()
        try:
            if not self._zugang():
                return
            # Auch beim Lesen nur der eigene Host: eine fremde Seite, deren Name
            # auf 127.0.0.1 zeigt (DNS-Rebinding), konnte bis 1.18.3 Katalog,
            # Tagebuch und Heimatkoordinate lesen — POST war zu, GET nicht
            # (Review 25.09., S2).
            if not self._same_origin():
                self._send(403, als_bytes(T("Fremde Herkunft.")))
                return
            if path is None:
                self._send(404, als_bytes(T("Nicht gefunden.")))
                return
            self._get(path)
        except (KatalogFehler, KonfigFehler, OSError, ValueError) as exc:
            # Ein kaputter Katalog ließ bis 1.18.3 die Verbindung wortlos
            # abbrechen; der Grund stand nur im Terminal (Review 25.09., U1).
            # Seit 2.1.0 auch jeder andere ValueError — UnicodeEncodeError ist
            # einer (C2). Auch auf den JSON-Wegen die Seite: die Skripte lesen
            # dort nur Daten, eine Fehlerseite lässt `r.json()` scheitern, und
            # die Seite behält, was sie zeigt.
            self._fehler_antwort(exc, als_json=False)

    def _get(self, path: str) -> None:
        if path == "/":
            cfg = load_config(self.cfg_path)
            self._send(200, als_bytes(page(cfg, form_defaults(cfg))))
        elif path == "/status":
            with LOCK:
                self._send(200, json_bytes(JOB, ensure_ascii=True), "application/json")
        elif path == "/pruefen":
            cfg = load_config(self.cfg_path)
            eintraege, _ = pruef_liste(cfg["rider"]["home"])
            self._send(200, als_bytes(pruef_page(eintraege, cfg["rider"]["home"])))
        elif path == "/katalog":
            from .spots import load_spots
            cfg = load_config(self.cfg_path)
            self._send(200, als_bytes(katalog_page(load_spots(str(SPOTS_FILE)), cfg["rider"]["home"])))
        elif path == "/rueckblick":
            from . import rueckblick
            from .spots import load_spots
            cfg = load_config(self.cfg_path)
            daten = rueckblick.laden()
            tage = int((daten or {}).get("tage") or 2)
            try:
                kommentare = {s["id"]: s.get("comment", "") for s in load_spots(str(SPOTS_FILE)) if s.get("comment")}
            except ValueError:
                kommentare = {}
            self._send(200, als_bytes(rueckblick_page(cfg, daten, rueckblick.letzter_lauf(), tage, kommentare)))
        elif path == "/tagebuch":
            from .spots import load_spots
            cfg = load_config(self.cfg_path)
            self._send(200, als_bytes(tagebuch_page(cfg, load_spots(str(SPOTS_FILE)))))
        elif path == "/tagebuch/daten":
            from .spots import load_spots
            cfg = load_config(self.cfg_path)
            spots = {s["id"]: s for s in load_spots(str(SPOTS_FILE))}
            self._send(200, json_bytes(tagebuch_daten(cfg, spots)), "application/json")
        elif path == "/rueckblick/daten":
            from . import rueckblick
            self._send(200, json_bytes(rueckblick.laden()), "application/json")
        elif path == "/manifest.webmanifest":
            self._send(200, als_bytes(MANIFEST), "application/manifest+json; charset=utf-8")
        elif path in BILD_DATEIEN:
            self._send(200, (WEB / path.lstrip("/")).read_bytes(), "image/png")
        elif path == HILFE_PFAD:
            self._send(200, als_bytes(hilfe_page()))
        elif path == RECHNUNG_PFAD:
            self._send(200, als_bytes(rechnung_page()))
        elif path == "/report":
            if REPORT_FILE.exists():
                roh = report_in_sprache(REPORT_FILE.read_bytes())
                self._send(200, report_mit_reitern(roh), nonce_wert=csp.nonce_aus_datei(roh) or False)
            else:
                self._send(200, als_bytes(kein_report_page()))
        else:
            self._send(404, als_bytes(T("Nicht gefunden.")))

    def do_POST(self):
        if self._zu_spaet():
            return
        path = self._anfang()
        try:
            if not self._zugang():
                return
            if not self._same_origin():
                self._send(403, als_bytes(json.dumps({"error": T("fremde Herkunft")}, separators=(",", ":"))),
                           "application/json")
                return
            if path is None:
                self._send(404, als_bytes(T("Nicht gefunden.")))
                return
            self._post(path)
        except (KatalogFehler, KonfigFehler, OSError, ValueError) as exc:
            self._fehler_antwort(exc, als_json=True)

    def _post(self, path: str) -> None:
        if path.startswith("/pruefen/") or path.startswith("/katalog/"):
            self._pruefen(path)
            return
        if path.startswith("/tagebuch/"):
            self._tagebuch(path)
            return
        try:
            raw = self._form()
        except ValueError as exc:
            code = 413 if isinstance(exc, AnfrageZuGross) else 400
            self._send(code, als_bytes(json.dumps({"error": str(exc)})), "application/json")
            return
        if path == "/sprache":
            # Der Umschalter (seit 2.1.0): gemerkt in sprache.txt, gilt ab der
            # nächsten Seite und für den nächsten Report.
            wahl = (raw.get("sprache", [""])[0] or "").strip().lower()
            if wahl not in i18n.SPRACHEN:
                self._send(400, b'{"error":"sprache"}', "application/json")
                return
            i18n.speichern(wahl)
            i18n.setze(wahl)
            self._send(200, b'{"ok":true}', "application/json")
            return
        cfg = load_config(self.cfg_path)
        values = parse_form(raw, form_defaults(cfg))

        def gestartet(ok: bool) -> None:
            if ok:
                self._send(200, b'{"ok":true}', "application/json")
            else:
                self._antwort(409, error=T("Es läuft schon etwas — bitte warten."))

        if path == "/run":
            # Ein Ortsname im Startfeld lief bis 1.18.3 still von Zuhause aus,
            # der Hinweis stand nur im zugeklappten Protokoll (Review 25.09., U2).
            start = str(values.get("start") or "").strip()
            if start and not parse_position(start):
                self._antwort(400, error=T("Startpunkt „{start}“ nicht lesbar. Es geht eine Koordinate "
                                           "(51.76, 3.85), ein Google-Maps-Link, „Hier“ oder „Karte“ — "
                                           "leer heißt {heim}.", start=start[:60], heim=cfg['rider']['home']['name']))
                return
            # Der Startzeitpunkt (seit 2.3.0): lesbar und nicht hinter dem
            # letzten Vorhersagetag — sonst ein Satz statt eines Laufs.
            ab_text = str(values.get("ab") or "").strip()
            if ab_text:
                try:
                    zeitraum.fenster(zeitraum.lesen(ab_text), values["days"])
                except zeitraum.ZuWeit:
                    self._antwort(400, error=T("Startzeitpunkt nach dem letzten Vorhersagetag — die Vorhersage "
                                               "reicht bis {bis}.", bis=i18n.datum_jahr(zeitraum.letzter_tag())))
                    return
                except ValueError:
                    self._antwort(400, error=T("Startzeitpunkt „{ab}“ nicht lesbar — Datum und Uhrzeit wählen "
                                               "oder das Feld leeren, dann gilt jetzt.", ab=ab_text[:40]))
                    return
            gestartet(start_run(self.cfg_path, values))
        elif path == "/rueckblick/start":
            try:
                tage = int(raw.get("tage", ["2"])[0])
            except (ValueError, TypeError):
                tage = 2
            from .rueckblick import MAX_TAGE, MAX_KM_VORGABE, MAX_KM_GRENZE, letzter_lauf
            tage = max(1, min(MAX_TAGE, tage))
            try:
                max_km = float(str(raw.get("max_km", [str(MAX_KM_VORGABE)])[0]).replace(",", "."))
                if not math.isfinite(max_km):
                    raise ValueError
            except (ValueError, TypeError):
                max_km = float(MAX_KM_VORGABE)
            max_km = max(1.0, min(float(MAX_KM_GRENZE), max_km))
            if not (letzter_lauf() or {}).get("top"):
                self._antwort(400, error=T("Noch keine Suche gelaufen — erst suchen, dann zurückblicken."))
                return
            gestartet(start_rueckblick(self.cfg_path, tage, max_km))
        elif path == "/shutdown":
            self._send(200, b'{"ok":true}', "application/json")
            # Aus dem Bearbeitungs-Thread heraus würde shutdown() sich selbst
            # blockieren — also aus einem eigenen, kurz nachdem die Antwort raus ist.
            def stop():
                time.sleep(0.3)
                server = SERVER.get("instance")
                if server is not None:
                    server.shutdown()
            threading.Thread(target=stop, daemon=True).start()
        elif path == "/geometry":
            gestartet(start_geometry(self.cfg_path))
        elif path == "/addspots":
            text = (raw.get("spots_text", [""])[0] or "")
            gestartet(start_ingest(self.cfg_path, text, "spot_geo" in raw))
        elif path == "/save":
            # Der Startpunkt wird bewusst nicht gemerkt: er gilt für heute und
            # hier, nicht für den nächsten Start. Leer heißt Zuhause. Ebenso der
            # Startzeitpunkt (seit 2.3.0): leer heißt jetzt.
            keep = {k: val for k, val in values.items() if k not in ("start", "start_name", "ab")}
            DEFAULTS_FILE.write_text(json.dumps(keep, indent=1, ensure_ascii=False), encoding="utf-8")
            self._send(200, b'{"ok":true}', "application/json")
        else:
            self._send(404, als_bytes(T("Nicht gefunden.")))


def port_belegt_von(port: int) -> str | None:
    """Wer auf dem Port antwortet: None (frei), „wingscout“ (eine laufende
    Wingfoilscout-Oberfläche — `/status` liefert ihren Stand) oder „fremd“ (ein
    anderes Programm). Ein zweites Programm auf demselben Port ist keine
    Theorie: ein anderer lokaler Server, der ebenfalls 8765 nimmt, ließ
    Wingfoilscout bis 1.18.3 mit einem Traceback „Address already in use“ sterben
    (25.09.2026)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        if s.connect_ex(("127.0.0.1", port)) != 0:
            return None
    try:
        # Höchstens 64 kB: was dort antwortet, ist womöglich nicht von uns, und
        # `read()` ohne Grenze las bis 2.1.0 alles, was es schickt (C17). Die
        # eigene Antwort kann länger sein (das Protokoll eines langen Laufs) —
        # dann reicht ihr Anfang, den schreibt `json.dumps(JOB)` immer gleich.
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=2) as r:
            roh = r.read(PROBE_GRENZE + 1)
        if len(roh) > PROBE_GRENZE:
            return "wingscout" if re.match(rb'\{"state": "[a-z]+", "log": \[', roh) else "fremd"
        daten = json.loads(roh.decode("utf-8"))
        if isinstance(daten, dict) and "state" in daten and "log" in daten:
            return "wingscout"
    except Exception:                                             # noqa: BLE001 — jede Antwort außer unserer
        pass
    return "fremd"


PROBE_GRENZE = 64 * 1024


def port_klaeren(port: int) -> dict:
    """Welchen Port die Oberfläche nimmt.

    {"port": …, "hinweis": …, "laeuft": …}: der gewünschte Port, wenn er frei
    ist; der nächste freie (bis zehn weiter), wenn ein fremdes Programm darauf
    sitzt; `laeuft` = die Adresse einer Wingfoilscout-Oberfläche, die dort schon
    läuft — dann wird keine zweite gestartet, sondern die offene geöffnet.
    """
    wer = port_belegt_von(port)
    if wer is None:
        return {"port": port, "hinweis": "", "laeuft": ""}
    if wer == "wingscout":
        url = f"http://127.0.0.1:{port}/"
        return {"port": None, "laeuft": url,
                "hinweis": T("Wingfoilscout läuft schon auf {url} — es wird kein zweites gestartet.", url=url)}
    for kandidat in range(port + 1, port + 11):
        if port_belegt_von(kandidat) is None:
            return {"port": kandidat, "laeuft": "",
                    "hinweis": T("Port {port} ist von einem anderen Programm belegt — "
                                 "Wingfoilscout nimmt deshalb {neu}.", port=port, neu=kandidat)}
    return {"port": None, "laeuft": "",
            "hinweis": T("Ports {von} bis {bis} sind alle belegt — ein anderes Programm beenden oder --port setzen.",
                         von=port, bis=port + 10)}


def serve(port: int = 8765, open_browser: bool = True, config: str | None = None,
          lan: bool = False) -> None:
    # Was die Oberfläche schreibt, gehört nur dem Benutzer: report.html,
    # cache/, tagebuch.json, modellguete.json, sprache.txt, ui_defaults.json —
    # mit der üblichen Maske 022 konnte bis 2.1.0 jeder Benutzer des Macs sie
    # lesen (A3). Gesetzt beim Start des Servers, nicht beim Import: wer das
    # Modul nur lädt (Tests, Werkzeuge), behält seine Maske; und danach gilt
    # wieder die alte.
    alte_maske = os.umask(0o077)
    try:
        _serve(port, open_browser, config, lan)
    finally:
        os.umask(alte_maske)


def _serve(port: int, open_browser: bool, config: str | None, lan: bool) -> None:
    if config:
        Handler.cfg_path = config
    wahl = port_klaeren(port)
    if wahl["hinweis"]:
        print(wahl["hinweis"])
    if wahl["laeuft"]:
        if lan:
            print(T("Für den WLAN-Zugang fürs iPhone: dort oben rechts „Beenden“, dann diesen Starter noch einmal."))
        if open_browser:
            webbrowser.open(wahl["laeuft"])
        return
    if wahl["port"] is None:
        raise SystemExit(1)
    port = wahl["port"]
    if lan:
        LAN.update(aktiv=True, schluessel=secrets.token_urlsafe(9), adressen=tuple(eigene_adressen()))
    PORT["nr"] = port
    try:
        server = BegrenzterServer(("0.0.0.0" if lan else "127.0.0.1", port), Handler)
    except OSError as exc:
        print(T("Port {port} lässt sich nicht öffnen ({fehler}). Läuft dort ein anderes Programm? "
                "Dann dieses beenden oder Wingfoilscout mit --port starten.", port=port, fehler=exc))
        raise SystemExit(1) from exc
    SERVER["instance"] = server
    url = f"http://127.0.0.1:{port}/"
    print(T("Wingfoilscout läuft auf {url}", url=url))
    if lan:
        if LAN["adressen"]:
            print("\n" + T("Auf dem iPhone im selben WLAN (Safari öffnen und eintippen):"))
            for adresse in LAN["adressen"]:
                print(f"    http://{adresse}:{port}/?k={LAN['schluessel']}")
            print("\n" + T("Danach „Teilen“ → „Zum Home-Bildschirm“, dann startet Wingfoilscout wie eine App."))
        else:
            print("\n" + T("Keine Netzadresse gefunden — ist der Mac im WLAN?"))
        print(T("Der Schlüssel gilt, bis Wingfoilscout beendet wird. Ohne ihn kommt vom Netz "
                "her niemand an deine Daten."))
    print(T("Zum Beenden den Knopf oben rechts in der Oberfläche drücken — "
            "oder hier Strg+C."))
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("\n" + T("Wingfoilscout beendet."))


if __name__ == "__main__":
    # Die Meldungen im Terminal in der Sprache der Kommandozeile: gespeicherte
    # Wahl, sonst die des Systems (die Seiten wählen je Anfrage selbst).
    i18n.fuer_kommandozeile()
    ap = argparse.ArgumentParser(description=T("Wingfoilscout-Oberfläche im Browser."))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--lan", action="store_true",
                    help=T("auch im WLAN erreichbar (fürs iPhone), mit Zugangsschlüssel"))
    a = ap.parse_args()
    serve(a.port, not a.no_open, a.config, a.lan)
