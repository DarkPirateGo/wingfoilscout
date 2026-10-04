"""Die Oberfläche als HTTP-Server: Befunde der Sicherheitsdurchsicht vom 03.10.2026.

Jeder Test steht für einen Befund und prüft am laufenden Server oder an der
Funktion, an der er hing:

- A1  fremde Seiten laden nichts ein (Sec-Fetch-Site/-Mode/-Dest)
- A2  begrenzte Verbindungen, ein Zeitlimit je Lesevorgang und — zweite
      Runde — eine Frist je Verbindung für andere Geräte
- A3  was der Server schreibt, gehört nur dem Benutzer (umask 077)
- A4  Fehlermeldungen ohne Pfade und Benutzernamen
- C2  ein unerwarteter ValueError (z. B. UnicodeEncodeError) wird beantwortet;
      zweite Runde: Werte aus Dateien in Meldungen, jede Antwort mit „replace“
- C4  kein Absturz an NaN/inf im Report
- C5  JSON-Antworten ohne NaN — zweite Runde: auch die Daten in den Skripten
- C17 der Blick auf einen belegten Port liest höchstens 64 kB

Nichts hier ändert etwas dauerhaft: Katalog und Geometrie liegen in einem
Temporärordner, Zeitlimit, umask und `JOB` sind danach wie vorher.
"""
from __future__ import annotations

import argparse
import contextlib
import html
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import yaml

from tests.helpers import CONFIG, ROOT
import wingscout.webui as w
from wingscout import i18n, ingest, report, rueckblick, spotedit, tagebuch
from wingscout.config import KonfigFehler, load_config
from wingscout.spots import KatalogFehler, load_spots

KLEINER_KATALOG = [
    {"id": "alpha", "name": "Alpha", "country": "DE", "lat": 49.5, "lon": 8.7, "water_body": "lake",
     "verified": True, "sectors": []},
]
GEHEIM = "/Users/geheim/wingfoilscout/spots.yaml"


def anfrage(port: int, pfad: str, kopf: dict | None = None, daten: bytes | None = None,
            methode: str | None = None):
    """(Status, Kopfzeilen, Rumpf als Bytes) — auch bei 4xx/5xx."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}{pfad}", data=daten, headers=kopf or {},
                                 method=methode or ("GET" if daten is None else "POST"))
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def roh_anfrage(port: int, text: bytes) -> bytes:
    """Eine Anfrage, wie sie urllib nicht schicken würde — die Antwort bis zum Ende."""
    with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
        s.sendall(text)
        return bis_zum_ende(s)


def bis_zum_ende(s: socket.socket, sekunden: float = 10) -> bytes:
    """Alles, was der Server schickt, bis er die Verbindung schließt."""
    s.settimeout(sekunden)
    teile = []
    while True:
        try:
            stueck = s.recv(65536)
        except (ConnectionResetError, ConnectionAbortedError):
            stueck = b""
        if not stueck:
            return b"".join(teile)
        teile.append(stueck)


def warte_bis(bedingung, sekunden: float = 5.0) -> bool:
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        if bedingung():
            return True
        time.sleep(0.02)
    return bedingung()


def geschlossen(s: socket.socket, sekunden: float = 5.0) -> bool:
    """Hat der Server die Verbindung geschlossen (statt sie offen zu halten)?"""
    s.settimeout(sekunden)
    try:
        return s.recv(1) == b""
    except (ConnectionResetError, ConnectionAbortedError):
        return True
    except socket.timeout:
        return False


def aktuelle_maske() -> int:
    maske = os.umask(0)
    os.umask(maske)
    return maske


class LaufenderServer(unittest.TestCase):
    """Ein Server auf einem freien Port, mit kleinem Katalog im Temporärordner."""

    SERVER = w.BegrenzterServer

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.tmp = Path(tmp.name)
        spots, geo = cls.tmp / "spots.yaml", cls.tmp / "geometry.json"
        spots.write_text(yaml.safe_dump(KLEINER_KATALOG, allow_unicode=True, sort_keys=False), encoding="utf-8")
        geo.write_text("{}", encoding="utf-8")
        # Alles, was ein Weg schreiben könnte, liegt im Temporärordner — auch
        # sprache.txt: geht eine Abweisung hier einmal durch, schaltet sonst
        # ein Test die echte Sprachwahl um
        for ziel, name, wert in ((w, "SPOTS_FILE", spots), (w, "GEOMETRY_FILE", geo),
                                 (w, "DEFAULTS_FILE", cls.tmp / "ui_defaults.json"),
                                 (w, "REPORT_FILE", cls.tmp / "report.html"),
                                 (i18n, "SPRACH_DATEI", cls.tmp / "sprache.txt"),
                                 (rueckblick, "ERGEBNIS", cls.tmp / "rueckblick.json"),
                                 (rueckblick, "LETZTER_LAUF", cls.tmp / "letzter_lauf.json"),
                                 (tagebuch, "TAGEBUCH", cls.tmp / "tagebuch.json"),
                                 (w.Handler, "cfg_path", str(CONFIG))):
            p = mock.patch.object(ziel, name, wert)
            p.start()
            cls.addClassCleanup(p.stop)
        alt = dict(w._PRUEF_ZAHL)
        cls.addClassCleanup(lambda: (w._PRUEF_ZAHL.clear(), w._PRUEF_ZAHL.update(alt)))
        cls.server = cls.SERVER(("127.0.0.1", 0), w.Handler)
        cls.port = cls.server.server_address[1]
        cls.eigen = f"http://127.0.0.1:{cls.port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server.shutdown)

    def post_json(self, pfad: str, daten: dict):
        status, _, rumpf = anfrage(self.port, pfad, {"Origin": self.eigen, "Content-Type": "application/json"},
                                   json.dumps(daten).encode("utf-8"))
        return status, json.loads(rumpf or b"{}")


# ── A1: fremde Seiten laden nichts ein ──────────────────────────────────────

class FremdeSeiten(LaufenderServer):
    """`<img src=http://127.0.0.1:8765/logo.png>` und `fetch(…, {mode: "no-cors"})`
    schicken keinen Origin-Header — bis 2.1.0 kamen sie durch: Erkennen, dass
    Wingfoilscout läuft, und Rechenzeit verbrennen (A1)."""

    def kopf(self, seite, modus, ziel=None):
        k = {"Sec-Fetch-Site": seite, "Sec-Fetch-Mode": modus}
        if ziel is not None:
            k["Sec-Fetch-Dest"] = ziel
        return k

    def test_einbetten_und_laden_von_fremden_seiten_ist_403(self):
        faelle = [("/logo.png", "cross-site", "no-cors", "image"),          # <img>
                  ("/", "cross-site", "no-cors", "empty"),                  # fetch(…, {mode: "no-cors"})
                  ("/status", "cross-site", "cors", "empty"),               # fetch
                  ("/katalog", "same-site", "no-cors", "script"),           # <script> von 127.0.0.1:3000
                  ("/icon-192.png", "same-site", "no-cors", "image"),
                  ("/", "cross-site", "navigate", "iframe"),                # <iframe> ist eingebettet
                  ("/report", "same-site", "navigate", "frame")]
        # Abgewiesen wird, bevor eine Seite entsteht: ohne Rechenzeit
        with mock.patch.object(w, "page", side_effect=AssertionError("Seite gebaut")), \
                mock.patch.object(w, "katalog_page", side_effect=AssertionError("Seite gebaut")):
            for pfad, seite, modus, ziel in faelle:
                with self.subTest(pfad=pfad, seite=seite, modus=modus, ziel=ziel):
                    status, _, rumpf = anfrage(self.port, pfad, self.kopf(seite, modus, ziel))
                    self.assertEqual(status, 403, rumpf[:200])
                    self.assertNotIn(b"\x89PNG", rumpf)
            # Vorausladen auf Geheiß einer fremden Seite: eine Navigation, aber kein Klick
            for zweck in ("prefetch", "prefetch;prerender"):
                with self.subTest(zweck=zweck):
                    kopf = dict(self.kopf("cross-site", "navigate", "document"), **{"Sec-Purpose": zweck})
                    self.assertEqual(anfrage(self.port, "/", kopf)[0], 403)

    def test_navigation_bleibt_erlaubt(self):
        """Der Starter öffnet die Seite (none), das iPhone tippt sie ein (none),
        die eigenen Seiten holen ihre Daten (same-origin), ein Link von einer
        anderen Seite schickt das ganze Fenster her (cross-site, navigate)."""
        faelle = [("/", "none", "navigate", "document"),
                  ("/", "cross-site", "navigate", "document"),
                  ("/katalog", "same-site", "navigate", "document"),
                  ("/", "cross-site", "navigate", None),               # ohne Dest: wie bisher
                  ("/status", "same-origin", "cors", "empty"),
                  ("/logo.png", "same-origin", "no-cors", "image")]
        for pfad, seite, modus, ziel in faelle:
            with self.subTest(pfad=pfad, seite=seite, modus=modus, ziel=ziel):
                status, _, rumpf = anfrage(self.port, pfad, self.kopf(seite, modus, ziel))
                self.assertEqual(status, 200, rumpf[:200])

    def test_ohne_sec_fetch_wie_bisher(self):
        """curl, alte Browser, die Tests: nur Host und Origin entscheiden."""
        self.assertEqual(anfrage(self.port, "/status")[0], 200)
        self.assertEqual(anfrage(self.port, "/logo.png")[0], 200)
        self.assertEqual(anfrage(self.port, "/status", {"Host": "boese.example"})[0], 403)

    def test_post_von_fremder_seite_auch_mit_passendem_origin(self):
        """Ein POST mit `cross-site` wird abgewiesen, auch wenn der Origin passt
        — die Kopfzeile kann keine Seite fälschen."""
        status, _, _ = anfrage(self.port, "/sprache", {"Origin": self.eigen, "Sec-Fetch-Site": "cross-site",
                                                       "Sec-Fetch-Mode": "no-cors",
                                                       "Content-Type": "application/x-www-form-urlencoded"},
                               b"sprache=fr")
        self.assertEqual(status, 403)


# ── A2: Obergrenze für Verbindungen, Zeitlimit ──────────────────────────────

class Probeserver(w.BegrenzterServer):
    """Kleine Grenzen; „von außen“ ist, wer von einem gemerkten Port kommt —
    im Test kommt alles von 127.0.0.1."""
    MAX_VERBINDUNGEN = 6
    MAX_VON_AUSSEN = 3
    aussen_ports: set = set()

    def von_aussen(self, client_address):
        return client_address[1] in self.aussen_ports


class MitGeraetenVonAussen(LaufenderServer):
    """Der Probeserver und Verbindungen „von außen“ (von einem gemerkten
    Port) oder vom Mac — alle schließt der Test am Ende selbst."""

    SERVER = Probeserver

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Erst am Ende vergessen: der Server ordnet eine Verbindung beim
        # Schließen noch einmal zu, und das muss dasselbe ergeben wie beim Öffnen
        cls.addClassCleanup(Probeserver.aussen_ports.clear)

    def setUp(self):
        self.offene: list[socket.socket] = []
        self.addCleanup(self.alle_schliessen)

    def zeitlimit(self, sekunden: float) -> None:
        p = mock.patch.object(w.Handler, "timeout", sekunden)
        p.start()
        self.addCleanup(p.stop)

    def alle_schliessen(self):
        for s in self.offene:
            s.close()
        self.offene.clear()
        warte_bis(lambda: self.server.offen == {"alle": 0, "aussen": 0})

    def verbinden(self, aussen: bool) -> socket.socket:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        if aussen:
            Probeserver.aussen_ports.add(s.getsockname()[1])
        s.connect(("127.0.0.1", self.port))
        self.offene.append(s)
        return s


class Verbindungsgrenze(MitGeraetenVonAussen):
    """Halb offene Verbindungen ohne Schlüssel erschöpften bis 2.1.0 Threads und
    Dateinummern — danach kam auch der Mac selbst nicht mehr dran (A2)."""

    def setUp(self):
        super().setUp()
        # Langes Zeitlimit: die halb offenen Verbindungen sollen bleiben, bis der Test sie schließt
        self.zeitlimit(60)

    def test_von_aussen_ist_alles_ausser_dem_mac(self):
        self.assertFalse(w.BegrenzterServer.von_aussen(("127.0.0.1", 50000)))
        self.assertFalse(w.BegrenzterServer.von_aussen(("::1", 50000, 0, 0)))
        self.assertTrue(w.BegrenzterServer.von_aussen(("192.168.178.25", 50000)))
        self.assertTrue(w.BegrenzterServer.von_aussen(("127.0.0.2", 50000)))      # wie zugang_pruefen

    def test_der_mac_kommt_immer_dran(self):
        for _ in range(3):
            self.verbinden(aussen=True)
        self.assertTrue(warte_bis(lambda: self.server.offen == {"alle": 3, "aussen": 3}), self.server.offen)
        # Die vierte von außen: sofort zu, ohne Thread
        vierte = self.verbinden(aussen=True)
        self.assertTrue(geschlossen(vierte), "die Verbindung über der Grenze blieb offen")
        self.assertEqual(self.server.offen, {"alle": 3, "aussen": 3})
        # Vom Mac selbst geht es weiter
        status, _, rumpf = anfrage(self.port, "/status")
        self.assertEqual(status, 200)
        self.assertIn("state", json.loads(rumpf))
        self.assertTrue(warte_bis(lambda: self.server.offen == {"alle": 3, "aussen": 3}), self.server.offen)
        # Bis zur Gesamtgrenze auch lokal — darüber ist auch für den Mac zu
        for _ in range(3):
            self.verbinden(aussen=False)
        self.assertTrue(warte_bis(lambda: self.server.offen == {"alle": 6, "aussen": 3}), self.server.offen)
        self.assertTrue(geschlossen(self.verbinden(aussen=False)))
        # Alles zu: die Zähler gehen auf null, und es geht wieder
        self.alle_schliessen()
        self.assertEqual(self.server.offen, {"alle": 0, "aussen": 0})
        self.assertEqual(anfrage(self.port, "/status")[0], 200)

    def test_wer_nichts_schickt_fliegt_nach_dem_zeitlimit(self):
        with mock.patch.object(w.Handler, "timeout", 0.4):
            stumm = self.verbinden(aussen=True)
            self.assertTrue(warte_bis(lambda: self.server.offen["aussen"] == 1))
            beginn = time.monotonic()
            self.assertTrue(geschlossen(stumm, 5), "die stumme Verbindung blieb offen")
            self.assertLess(time.monotonic() - beginn, 4)
            self.assertTrue(warte_bis(lambda: self.server.offen == {"alle": 0, "aussen": 0}), self.server.offen)
            # Eine richtige Anfrage innerhalb des Limits geht
            self.assertEqual(anfrage(self.port, "/status")[0], 200)


class FristFuerAndereGeraete(MitGeraetenVonAussen):
    """Das Zeitlimit gilt je Lesevorgang: wer alle zehn Sekunden ein Byte der
    Kopfzeilen schickte, hielt eine Verbindung bis 2.1.0 beliebig lange — ohne
    Schlüssel, den prüft der Handler erst an den ganzen Kopfzeilen —, und 24
    solche sperrten das iPhone aus (A2, zweite Runde). Jetzt gilt für andere
    Geräte eine Frist für die ganze Verbindung: hier eine Sekunde, im Betrieb
    30. Der Mac selbst hat keine."""

    FRIST = 1.0
    ABSTAND = 0.15                     # so oft kommt ein Byte — öfter als das Zeitlimit

    def setUp(self):
        super().setUp()
        self.zeitlimit(0.5)
        p = mock.patch.object(w.Handler, "FRIST_VON_AUSSEN", self.FRIST)
        p.start()
        self.addCleanup(p.stop)

    def tropfen(self, s: socket.socket, daten: bytes, hoechstens: float = 6.0):
        """`daten` Byte für Byte, alle ABSTAND Sekunden eines. Rückgabe: nach
        wie vielen Sekunden der Server die Verbindung schloss — None, wenn sie
        nach allem (oder nach `hoechstens` Sekunden) noch offen ist."""
        beginn = time.monotonic()
        s.settimeout(self.ABSTAND)
        for i in range(len(daten)):
            if time.monotonic() - beginn > hoechstens:
                return None
            try:
                s.sendall(daten[i:i + 1])
                antwort = s.recv(1)
            except socket.timeout:
                continue                            # noch offen: das nächste Byte
            except OSError:                         # zurückgesetzt, Rohr gebrochen
                return time.monotonic() - beginn
            self.assertEqual(antwort, b"", "der Server antwortete auf eine halbe Anfrage")
            return time.monotonic() - beginn
        return None

    def kopf(self, pfad: str = "/status") -> bytes:
        return f"GET {pfad} HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nX-Langsam: ".encode()

    def test_tropfen_haelt_die_verbindung_nicht_mehr(self):
        s = self.verbinden(aussen=True)
        s.sendall(self.kopf())                      # die Frist zählt ab der Annahme
        dauer = self.tropfen(s, b"a" * 200)
        self.assertIsNotNone(dauer, "die tropfende Verbindung blieb offen")
        self.assertGreater(dauer, self.FRIST - 0.4, "das Zeitlimit kam vor der Frist — der Test prüfte nichts")
        self.assertLess(dauer, self.FRIST + 3)
        self.assertTrue(warte_bis(lambda: self.server.offen == {"alle": 0, "aussen": 0}), self.server.offen)

    def test_der_mac_hat_keine_frist(self):
        s = self.verbinden(aussen=False)
        beginn = time.monotonic()
        s.sendall(self.kopf())
        self.assertIsNone(self.tropfen(s, b"a" * int(2.5 * self.FRIST / self.ABSTAND)),
                          "die Verbindung vom Mac wurde geschlossen")
        self.assertGreater(time.monotonic() - beginn, 1.5 * self.FRIST)
        s.sendall(b"\r\n\r\n")
        antwort = bis_zum_ende(s)
        self.assertTrue(antwort.startswith(b"HTTP/1.0 200"), antwort[:100])

    def test_das_iphone_kommt_wieder_dran(self):
        """Alle Plätze von außen belegt (hier 3 statt 24) — mit langem
        Zeitlimit hält auch Schweigen sie so fest wie Tropfen: nach der Frist
        sind sie frei, und das iPhone kommt dran."""
        self.zeitlimit(60)
        for _ in range(Probeserver.MAX_VON_AUSSEN):
            self.verbinden(aussen=True).sendall(b"G")
        self.assertTrue(warte_bis(lambda: self.server.offen["aussen"] == Probeserver.MAX_VON_AUSSEN),
                        self.server.offen)
        self.assertTrue(geschlossen(self.verbinden(aussen=True), 2), "über der Grenze bleibt es zu")
        self.assertTrue(warte_bis(lambda: self.server.offen == {"alle": 0, "aussen": 0}, self.FRIST + 3),
                        self.server.offen)
        iphone = self.verbinden(aussen=True)
        iphone.sendall(f"GET /status HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n\r\n".encode())
        antwort = bis_zum_ende(iphone)
        self.assertTrue(antwort.startswith(b"HTTP/1.0 200"), antwort[:100])

    def test_eigene_arbeit_zaehlt_nicht(self):
        """Overpass und Nominatim: die Arbeit an Katalog und Koordinaten dauert
        manchmal länger als die Frist — die Antwort kommt trotzdem an, die
        Frist ruht, solange der Server selbst rechnet."""
        rumpf = json.dumps({"id": "alpha", "name": "Neu"}).encode()
        anfrage = (f"POST /katalog/umbenennen HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nOrigin: {self.eigen}\r\n"
                   f"Content-Type: application/json\r\nContent-Length: {len(rumpf)}\r\n\r\n").encode() + rumpf
        s = self.verbinden(aussen=True)
        with mock.patch.object(spotedit, "set_text", side_effect=lambda *a, **k: time.sleep(2 * self.FRIST)):
            s.sendall(anfrage)
            antwort = bis_zum_ende(s, 15)
        self.assertTrue(antwort.startswith(b"HTTP/1.0 200"), antwort[:200])
        self.assertIn(b'"ok": true', antwort)

    def test_halber_koerper_wird_nicht_bearbeitet(self):
        """Kommt der Körper nicht ganz an — die Gegenstelle ist weg, oder die
        Frist ist um —, wird nichts bearbeitet. Bis 2.1.0 ging der Rest durch:
        ein halbes Formular wäre als Standard gemerkt worden."""
        rumpf = b"days=5&radius=200&marine=on"
        kopf = (f"POST /save HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nOrigin: {self.eigen}\r\n"
                f"Content-Type: application/x-www-form-urlencoded\r\nContent-Length: {len(rumpf) + 40}\r\n\r\n").encode()
        # Vom Mac: abgebrochen, die Verbindung zum Schreiben geschlossen
        mac = self.verbinden(aussen=False)
        mac.sendall(kopf + rumpf)
        mac.shutdown(socket.SHUT_WR)
        self.assertEqual(bis_zum_ende(mac), b"")
        # Von außen: der Rest tropft und kommt nie ganz — die Frist schließt
        aussen = self.verbinden(aussen=True)
        aussen.sendall(kopf + rumpf)
        self.assertIsNotNone(self.tropfen(aussen, b"&x=1" * 10))
        self.assertTrue(warte_bis(lambda: self.server.offen == {"alle": 0, "aussen": 0}), self.server.offen)
        self.assertFalse(w.DEFAULTS_FILE.exists(), "der halbe Körper wurde gespeichert")

    def test_eine_anfrage_je_verbindung(self):
        """Die Frist gilt je Verbindung — mit HTTP/1.0 ist das je Anfrage: auch
        wer Keep-alive möchte, bekommt eine Antwort, dann ist zu (sonst zählte
        das Warten bis zur nächsten Anfrage mit)."""
        self.assertEqual(w.Handler.protocol_version, "HTTP/1.0")
        s = self.verbinden(aussen=True)
        s.sendall(f"GET /status HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nConnection: keep-alive\r\n\r\n".encode())
        antwort = bis_zum_ende(s)                   # kommt nur zurück, wenn der Server schließt
        self.assertTrue(antwort.startswith(b"HTTP/1.0 200"), antwort[:100])
        self.assertIn(b'"state"', antwort)

    def test_kein_timer_bleibt_liegen(self):
        def timer():
            return {t for t in threading.enumerate() if isinstance(t, threading.Timer)}
        vorher = timer()
        for _ in range(3):
            s = self.verbinden(aussen=True)
            s.sendall(f"GET /status HTTP/1.0\r\nHost: 127.0.0.1:{self.port}\r\n\r\n".encode())
            self.assertTrue(bis_zum_ende(s).startswith(b"HTTP/1.0 200"))
        self.assertTrue(warte_bis(lambda: timer() <= vorher), timer() - vorher)


class ZeitlimitVorgabe(unittest.TestCase):
    def test_vorgabe(self):
        """Im Betrieb 15 s: lang genug fürs iPhone im WLAN, kurz genug gegen
        Hängenlassen; die Grenze von außen kleiner als die ganze. Die Frist
        für andere Geräte länger als das Zeitlimit, eine Anfrage je
        Verbindung (HTTP/1.0)."""
        self.assertEqual(w.Handler.timeout, 15)
        self.assertLessEqual(w.BegrenzterServer.MAX_VERBINDUNGEN, 64)
        self.assertLessEqual(w.BegrenzterServer.MAX_VON_AUSSEN, 24)
        self.assertLess(w.BegrenzterServer.MAX_VON_AUSSEN, w.BegrenzterServer.MAX_VERBINDUNGEN)
        self.assertTrue(w.BegrenzterServer.daemon_threads, "Threads dürfen das Beenden nicht aufhalten")
        self.assertEqual(w.Handler.FRIST_VON_AUSSEN, 30)
        self.assertGreater(w.Handler.FRIST_VON_AUSSEN, w.Handler.timeout)
        self.assertEqual(w.Handler.protocol_version, "HTTP/1.0")


# ── A3: umask 077, solange der Server läuft ─────────────────────────────────

class Dateirechte(unittest.TestCase):
    def test_serve_setzt_die_maske_und_gibt_sie_zurueck(self):
        vorher = aktuelle_maske()
        gesehen = {}
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        class Attrappe:
            def __init__(self, adresse, handler):
                gesehen["adresse"] = adresse

            def serve_forever(self):
                gesehen["maske"] = aktuelle_maske()
                datei = Path(tmp.name) / "report.html"
                datei.write_text("x", encoding="utf-8")
                gesehen["rechte"] = datei.stat().st_mode & 0o777

            def server_close(self):
                pass

        alt = (dict(w.SERVER), dict(w.PORT))
        self.addCleanup(lambda: (w.SERVER.update(alt[0]), w.PORT.update(alt[1])))
        with mock.patch.object(w, "BegrenzterServer", Attrappe), \
                mock.patch.object(w, "port_klaeren", return_value={"port": 48765, "hinweis": "", "laeuft": ""}), \
                contextlib.redirect_stdout(io.StringIO()):
            w.serve(48765, open_browser=False)
        self.assertEqual(gesehen["adresse"], ("127.0.0.1", 48765))
        self.assertEqual(gesehen["maske"], 0o077)
        self.assertEqual(gesehen["rechte"], 0o600)
        self.assertEqual(aktuelle_maske(), vorher, "nach dem Server gilt wieder die alte Maske")

    def test_import_aendert_die_maske_nicht(self):
        """Nur der Start des Servers setzt sie — wer das Modul lädt, behält seine."""
        aus = subprocess.run([sys.executable, "-c", "import os; os.umask(0o022); import wingscout.webui; "
                              "print(oct(os.umask(0o022)))"], cwd=str(ROOT), capture_output=True, text=True,
                             timeout=120)
        self.assertEqual(aus.returncode, 0, aus.stderr[-2000:])
        self.assertEqual(aus.stdout.strip(), "0o22")


# ── A4: Fehlermeldungen ohne Pfade ──────────────────────────────────────────

class FehlerOhnePfade(LaufenderServer):
    """Die Schreibwege der Katalog- und Prüfseite gaben die Ausnahme roh an den
    Browser — samt `/Users/<name>/…` (A4)."""

    def test_fehler_satz(self):
        with mock.patch.object(w.Path, "home", return_value=Path("/Users/geheim")):
            faelle = [
                (KatalogFehler(f"Spot-Katalog nicht gefunden: {w.ROOT / 'spots.yaml'}"),
                 "Spot-Katalog nicht gefunden: spots.yaml"),
                (KonfigFehler("Konfiguration nicht gefunden: /Users/geheim/x/config.yaml"),
                 "Konfiguration nicht gefunden: ~/x/config.yaml"),
                (PermissionError(13, "Permission denied", GEHEIM),
                 "Datei nicht lesbar oder schreibbar (Permission denied)"),
                (FileNotFoundError(2, "No such file or directory", GEHEIM),
                 "Datei nicht lesbar oder schreibbar (No such file or directory)"),
                (urllib.error.URLError("timed out"), "URLError"),
                (ConnectionResetError(54, "Connection reset by peer"), "ConnectionResetError"),
                (spotedit.SpotNichtGefunden("gibt-es-nicht"), "gibt-es-nicht"),
                (tagebuch.TagebuchFehler("Wing fehlt."), "Wing fehlt."),
                (RuntimeError(f"kaputt in {GEHEIM}"), "RuntimeError"),
                (ValueError(GEHEIM), "ValueError"),
            ]
            for exc, soll in faelle:
                with self.subTest(exc=repr(exc)):
                    self.assertEqual(w.fehler_satz(exc), soll)

    def test_schreibwege_ohne_pfad(self):
        """Jeder Schreibweg mit einer Datei, die sich nicht schreiben lässt:
        der Grund im Browser, der Pfad nur im Terminal."""
        fehler = PermissionError(13, "Permission denied", GEHEIM)
        faelle = [
            ("/katalog/kommentar", {"id": "alpha", "comment": "x"}, spotedit, "set_text", 400),
            ("/katalog/umbenennen", {"id": "alpha", "name": "Neu"}, spotedit, "set_text", 400),
            ("/katalog/loeschen", {"id": "alpha"}, spotedit, "entferne", 400),
            ("/katalog/tide", {"id": "alpha", "tidal": "auto"}, spotedit, "entferne_feld", 400),
            ("/pruefen/ok", {"id": "alpha"}, spotedit, "set_flag", 400),
            ("/pruefen/setzen", {"id": "alpha", "koordinate": "49.51, 8.71"}, spotedit, "set_coords", 400),
            ("/katalog/neu", {"name": "Neu", "koordinate": "10.5, 20.5", "country": "DE"},
             ingest, "append_to_yaml", 400),
        ]
        for pfad, daten, modul, funktion, code in faelle:
            with self.subTest(pfad=pfad):
                terminal = io.StringIO()
                with mock.patch.object(modul, funktion, side_effect=fehler), contextlib.redirect_stderr(terminal):
                    status, antwort = self.post_json(pfad, daten)
                self.assertEqual(status, code, antwort)
                self.assertIn("Permission denied", antwort["error"])
                self.assertNotIn("geheim", antwort["error"])
                self.assertNotIn("/", antwort["error"].replace("/ ", ""))
                self.assertIn(GEHEIM, terminal.getvalue(), "der volle Grund gehört ins Terminal")

    def test_tagebuch_nicht_schreibbar(self):
        terminal = io.StringIO()
        with mock.patch.object(tagebuch, "pruefe", return_value={}), \
                mock.patch.object(tagebuch, "eintragen", side_effect=PermissionError(13, "Permission denied", GEHEIM)), \
                contextlib.redirect_stderr(terminal):
            status, antwort = self.post_json("/tagebuch/neu", {"spot": "alpha"})
        self.assertEqual(status, 500)
        self.assertIn("Permission denied", antwort["error"])
        self.assertNotIn("geheim", antwort["error"])

    def test_unbekannter_spot_bleibt_lesbar(self):
        status, antwort = self.post_json("/katalog/umbenennen", {"id": "gibt-es-nicht", "name": "x"})
        self.assertEqual(status, 400)
        self.assertIn("gibt-es-nicht", antwort["error"])

    def test_laufender_fehler_im_status_ohne_pfad(self):
        """`/status` zeigt den Traceback eines gescheiterten Laufs — mit Pfaden
        relativ zum Wingfoilscout-Ordner statt absolut."""
        with w.LOCK:
            vorher = dict(w.JOB)
            w.JOB.update(state="idle")

        def zurueck():
            with w.LOCK:
                w.JOB.clear()
                w.JOB.update(vorher)
        self.addCleanup(zurueck)

        def arbeit():
            # Quellen melden ihre Fehler roh ins Protokoll — auch das geht über /status hinaus
            w._log("Cache:", PermissionError(13, "Permission denied", str(w.ROOT / "cache" / "y.json")))
            raise RuntimeError(f"kaputt: {w.ROOT / 'cache' / 'x.json'}")

        self.assertTrue(w._starte("run", arbeit, ausfuehrlich=True))
        self.assertTrue(warte_bis(lambda: w.JOB["state"] == "error"))
        status, _, rumpf = anfrage(self.port, "/status")
        stand = json.loads(rumpf)
        self.assertIn("Traceback", stand["error"])
        self.assertIn("cache/x.json".replace("/", os.sep), stand["error"])
        self.assertIn("cache/y.json".replace("/", os.sep), stand["log"][0])
        for text in [stand["error"]] + stand["log"]:
            self.assertNotIn(str(w.ROOT) + os.sep, text)


# ── C2: unerwartete Fehler werden beantwortet ───────────────────────────────

class UnerwarteteFehler(LaufenderServer):
    """Ein ValueError, der nicht KatalogFehler/KonfigFehler ist — z. B. ein
    UnicodeEncodeError aus einem Spotnamen mit einzelnem Surrogat —, ließ bis
    2.1.0 die Verbindung wortlos abreißen (C2)."""

    def test_unerwarteter_fehler_gibt_die_fehlerseite(self):
        terminal = io.StringIO()
        with mock.patch.object(w, "katalog_page", side_effect=ValueError("kaputt")), \
                contextlib.redirect_stderr(terminal):
            status, kopf, rumpf = anfrage(self.port, "/katalog")
        self.assertEqual(status, 500)
        self.assertIn("text/html", kopf.get("Content-Type"))
        self.assertIn("ValueError", rumpf.decode("utf-8"))
        self.assertIn("Traceback", terminal.getvalue(), "der Grund steht im Terminal")

    def test_seite_mit_surrogat_kommt_mit_fragezeichen(self):
        """Jede Antwort aus Text geht durch `als_bytes()` — UTF-8 mit
        „replace“ (C2, zweite Runde): ein einzelnes Surrogat kostet die Seite
        nicht mehr. Bis dahin kam an ihrer Stelle die Fehlerseite."""
        with mock.patch.object(w, "katalog_page", return_value="<p>kaputt \ud800 ä</p>"):
            status, kopf, rumpf = anfrage(self.port, "/katalog")
        self.assertEqual(status, 200)
        self.assertIn("text/html", kopf.get("Content-Type"))
        self.assertEqual(rumpf.decode("utf-8"), "<p>kaputt ? ä</p>")

    def test_fehlerseite_mit_surrogat_reisst_nicht_ab(self):
        """Auch die Fehlerseite selbst: an ihrem `encode("utf-8")` riss die
        Verbindung bis 2.1.0 ohne Antwort ab."""
        with mock.patch.object(w, "katalog_page", side_effect=KatalogFehler("kaputt")), \
                mock.patch.object(w, "fehler_page", return_value="<p>Fehler \ud800</p>"):
            status, _, rumpf = anfrage(self.port, "/katalog")
        self.assertEqual((status, rumpf), (500, b"<p>Fehler ?</p>"))

    def test_kurze_antworten_mit_surrogat(self):
        """403, 404 und die anderen kurzen Antworten ebenso — ein Surrogat kann
        auch aus einer Übersetzung kommen (JSON liest `\\ud800` klaglos)."""
        with mock.patch.object(w, "T", lambda text, **werte: text + " \ud800"):
            status, _, rumpf = anfrage(self.port, "/gibt-es-nicht")
            self.assertEqual((status, rumpf.decode("utf-8")), (404, "Nicht gefunden. ?"))
            status, _, rumpf = anfrage(self.port, "/status", {"Host": "boese.example"})
            self.assertEqual((status, rumpf.decode("utf-8")), (403, "Fremde Herkunft. ?"))

    def test_als_bytes(self):
        self.assertEqual(w.als_bytes("a\ud800b\udfff"), b"a?b?")
        for text in ("", "Größe <b> & Co", "日本 🌊"):
            self.assertEqual(w.als_bytes(text), text.encode("utf-8"))

    def test_json_mit_surrogat_bleibt_gueltig(self):
        with mock.patch.object(w, "tagebuch_daten", return_value={"name": "kaputt \ud800", "ok": "ä"}):
            status, kopf, rumpf = anfrage(self.port, "/tagebuch/daten")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(rumpf.decode("ascii")), {"name": "kaputt \ud800", "ok": "ä"})

    def test_json_weg_gibt_die_fehlerseite_wie_bisher(self):
        """Wie ein kaputter Katalog (tests/test_review_2026_09.py, U1): auch
        auf den Datenwegen die Fehlerseite — das Skript dort scheitert dann an
        `r.json()` und behält, was es zeigt."""
        fehler = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        with mock.patch.object(rueckblick, "laden", side_effect=fehler), \
                contextlib.redirect_stderr(io.StringIO()):
            status, kopf, rumpf = anfrage(self.port, "/rueckblick/daten")
        self.assertEqual(status, 500)
        self.assertIn("text/html", kopf.get("Content-Type"))
        self.assertIn("UnicodeDecodeError", rumpf.decode("utf-8"))

    def test_post_antwortet_mit_json(self):
        with mock.patch.object(w, "start_geometry", side_effect=UnicodeError("kaputt")), \
                contextlib.redirect_stderr(io.StringIO()):
            status, _, rumpf = anfrage(self.port, "/geometry", {"Origin": self.eigen,
                                                                "Content-Type": "application/x-www-form-urlencoded"},
                                       b"")
        self.assertEqual(status, 500)
        self.assertEqual(json.loads(rumpf), {"error": "UnicodeError"})

    def test_unlesbare_adresse_ist_404_kein_abbruch(self):
        """`GET http://[x/` — urlparse wirft ValueError („Invalid IPv6 URL“);
        `//[x` ebenso, wo Python einen führenden Doppelschrägstrich nicht
        schon selbst kürzt (vor 3.11.4)."""
        for methode in (b"GET", b"POST"):
            for pfad in (b"http://[x/", b"//[x"):
                with self.subTest(methode=methode, pfad=pfad):
                    antwort = roh_anfrage(self.port, methode + b" " + pfad + b" HTTP/1.0\r\nHost: 127.0.0.1:"
                                          + str(self.port).encode() + b"\r\nContent-Length: 0\r\n\r\n")
                    self.assertTrue(antwort.startswith(b"HTTP/1.0 404"), antwort[:100])

    def test_urlparse_wirft_wirklich(self):
        """Sonst prüfte der Test oben nichts."""
        with self.assertRaises(ValueError):
            urllib.parse.urlparse("http://[x/")

    def test_keine_zweite_antwort_auf_eine_tote_verbindung(self):
        """Bricht die Verbindung beim Schreiben ab, wird nicht noch eine
        Fehlerseite hinterhergeschrieben — bis 2.1.0 hieß das ein Traceback."""
        h = w.Handler.__new__(w.Handler)
        h._begonnen = False
        h.close_connection = False
        with mock.patch.object(w.Handler, "_send", side_effect=AssertionError("geschrieben")):
            h._fehler_antwort(BrokenPipeError(32, "Broken pipe"), als_json=False)
            h._fehler_antwort(socket.timeout("timed out"), als_json=True)
            h._begonnen = True
            with contextlib.redirect_stderr(io.StringIO()):
                h._fehler_antwort(ValueError("mitten in der Antwort"), als_json=False)
        self.assertTrue(h.close_connection)


class WerteAusDateienInMeldungen(LaufenderServer):
    """Ein Eintrag ohne `lon` (oder ohne `id`) mit einzelnem Surrogat im
    Namen, eine Winggröße `"x\\uD800"` mit low ≥ high: die Meldung nahm den
    Wert roh aus der Datei, die Fehlerseite ließ sich nicht als UTF-8
    schreiben, und die Verbindung riss ab — Katalog, Tagebuch, Prüfseite, beim
    Quiver auch Start- und Rückblickseite (C2, zweite Runde: beim Nachprüfen
    gefunden). Jetzt kommen solche Werte über `i18n.meldungswert()` in die
    Meldung — auf einer Zeile, ohne Steuerzeichen und Surrogate, gekürzt."""

    SPOTS_SEITEN = ("/katalog", "/tagebuch", "/pruefen", "/tagebuch/daten")
    CONFIG_SEITEN = ("/", "/katalog", "/tagebuch", "/pruefen", "/rueckblick")

    def datei(self, name: str, text: str) -> Path:
        pfad = self.tmp / name
        pfad.write_text(text, encoding="utf-8")
        self.addCleanup(pfad.unlink)
        return pfad

    def kaputter_quiver(self) -> Path:
        cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        cfg["quiver"]["wings"].append({"size": "x\ud800", "low": 22, "high": 13})
        pfad = self.datei("config-quiver.yaml", yaml.safe_dump(cfg, allow_unicode=False))
        self.assertIn('"x\\uD800"', pfad.read_text(encoding="utf-8"), "so steht es in der Datei")
        return pfad

    def seiten(self, pfade, soll: str) -> None:
        """Jede Seite antwortet mit der Fehlerseite (500, gültiges UTF-8) und
        nennt den Grund — im Browser wie im Terminal."""
        terminal = io.StringIO()
        with contextlib.redirect_stderr(terminal):
            for pfad in pfade:
                with self.subTest(pfad=pfad):
                    status, kopf, rumpf = anfrage(self.port, pfad)
                    self.assertEqual(status, 500)
                    self.assertIn("text/html", kopf.get("Content-Type"))
                    self.assertIn(html.escape(soll), rumpf.decode("utf-8"))
        self.assertNotIn("UnicodeEncodeError", terminal.getvalue())
        self.assertIn(soll, terminal.getvalue(), "der Grund steht im Terminal")

    def test_spot_ohne_lon_mit_surrogat_im_namen(self):
        kaputt = self.datei("spots-lon.yaml", '- id: bad-b\n  name: "Bad \\uD800 name"\n  lat: 53.5\n')
        with mock.patch.object(w, "SPOTS_FILE", kaputt):
            self.seiten(self.SPOTS_SEITEN, "Spot ohne 'lon': Bad name")

    def test_spot_ohne_id_mit_surrogat_im_namen(self):
        kaputt = self.datei("spots-id.yaml", '- name: "Bad \\uD800 name"\n  lat: 53.5\n  lon: 8.0\n')
        with mock.patch.object(w, "SPOTS_FILE", kaputt):
            self.seiten(self.SPOTS_SEITEN, "Spot ohne 'id': Bad name")

    def test_quiver_mit_surrogat(self):
        with mock.patch.object(w.Handler, "cfg_path", str(self.kaputter_quiver())):
            self.seiten(self.CONFIG_SEITEN, "Wing x: low muss kleiner als high sein.")

    def test_die_meldungen_selbst(self):
        """Ohne Server: was in der Meldung steht, lässt sich schreiben und
        steht auf einer Zeile; ein sauberer Wert bleibt, wie er war."""
        lang = "Sehr lang " * 20
        faelle = [
            ('- id: a\n  name: "Bad \\uD800 name"\n  lat: 1.0\n', "Spot ohne 'lon': Bad name"),
            ('- id: a\n  name: "Esc\\e[31mRot\\e[0m\\nzweite\\tZeile"\n  lat: 1.0\n',
             "Spot ohne 'lon': Esc[31mRot[0m zweite Zeile"),
            ('- id: a\n  name: Hardtsee\n  lon: 1.0\n', "Spot ohne 'lat': Hardtsee"),
            (f'- id: a\n  name: "{lang}"\n  lat: 1.0\n', "Spot ohne 'lon': " + lang.strip()[:59].rstrip() + "…"),
            ('- id: a\n  lat: 1.0\n  lon: 2.0\n  notes: "\\uD800"\n', "Spot ohne 'name': {'id': 'a', 'lat': 1.0, "
                                                                       "'lon': 2.0, 'notes': '\\ud800'}"),
        ]
        for nr, (text, soll) in enumerate(faelle):
            with self.subTest(soll=soll):
                with self.assertRaises(KatalogFehler) as fang:
                    load_spots(self.datei(f"spots-{nr}.yaml", text))
                self.assertEqual(str(fang.exception), soll)
                str(fang.exception).encode("utf-8")
        with self.assertRaises(KonfigFehler) as fang:
            load_config(self.kaputter_quiver())
        self.assertEqual(str(fang.exception), "Wing x: low muss kleiner als high sein.")
        # Der Regelfall wie bisher: die Zahl, wie str() sie schreibt
        cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        cfg["quiver"]["wings"][0].update(low=30, high=12)
        with self.assertRaises(KonfigFehler) as fang:
            load_config(self.datei("config-normal.yaml", yaml.safe_dump(cfg)))
        self.assertEqual(str(fang.exception),
                         f"Wing {cfg['quiver']['wings'][0]['size']}: low muss kleiner als high sein.")

    def test_meldungswert(self):
        m = i18n.meldungswert
        self.assertEqual(m("Hardtsee"), "Hardtsee")
        self.assertEqual(m(4.5), "4.5")
        self.assertEqual(m("Plage\u00a0de\tKer\nhillio\u2028x"), "Plage de Ker hillio x")
        self.assertEqual(m("rtl\u202eevil \x7f\x9b ok"), "rtlevil ok")         # Format- und C1-Zeichen
        self.assertEqual(m("Ü" * 61), "Ü" * 59 + "…")
        self.assertEqual(len(m("x" * 10_000)), i18n.MELDUNG_LAENGE)
        self.assertEqual(m("abc", 2), "a…")
        if hasattr(sys, "set_int_max_str_digits"):                          # ab 3.11: str() einer Riesenzahl wirft
            self.assertEqual(m(10 ** 5000), "…")


# ── C5: JSON ohne NaN ───────────────────────────────────────────────────────

def streng(rumpf: bytes):
    """JSON lesen wie der Browser: NaN und Infinity sind keine Zahlen."""
    def nein(wert):
        raise ValueError(f"kein JSON: {wert}")
    return json.loads(rumpf, parse_constant=nein)


class JsonOhneNaN(LaufenderServer):
    def test_json_bytes(self):
        nan, inf = float("nan"), float("inf")
        self.assertEqual(w.json_bytes({"a": nan, "b": [1.5, inf, (-inf, 2)], "c": {"d": nan, "e": "ü"}}),
                         '{"a": null, "b": [1.5, null, [null, 2]], "c": {"d": null, "e": "ü"}}'.encode("utf-8"))
        # Der Regelfall bleibt Byte für Byte, was json.dumps schreibt
        normal = {"x": 1.25, "y": [1, 2, None, True], "z": "Größe <b>"}
        self.assertEqual(w.json_bytes(normal), json.dumps(normal, ensure_ascii=False).encode("utf-8"))
        self.assertEqual(w.json_bytes(normal, ensure_ascii=True), json.dumps(normal).encode("utf-8"))

    def test_rueckblick_daten_mit_nan(self):
        kaputt = {"mae": float("nan"), "liste": [1.5, float("inf")], "tief": {"x": -float("inf")}}
        with mock.patch.object(rueckblick, "laden", return_value=kaputt):
            status, _, rumpf = anfrage(self.port, "/rueckblick/daten")
        self.assertEqual(status, 200)
        self.assertEqual(streng(rumpf), {"mae": None, "liste": [1.5, None], "tief": {"x": None}})

    def test_tagebuch_daten_mit_nan(self):
        with mock.patch.object(w, "tagebuch_daten", return_value={"sessions": [{"gemessen_kn": float("nan")}]}):
            status, _, rumpf = anfrage(self.port, "/tagebuch/daten")
        self.assertEqual(status, 200)
        self.assertEqual(streng(rumpf), {"sessions": [{"gemessen_kn": None}]})

    def test_status_mit_nan(self):
        with w.LOCK:
            vorher = dict(w.JOB)
            w.JOB["seit"] = float("nan")
        try:
            status, _, rumpf = anfrage(self.port, "/status")
        finally:
            with w.LOCK:
                w.JOB.clear()
                w.JOB.update(vorher)
        self.assertEqual(status, 200)
        self.assertIsNone(streng(rumpf)["seit"])


# ── Daten in Skripten: ein Weg für alle ─────────────────────────────────────

NODE = shutil.which("node")

# Gerade genug DOM, damit rueckblick.js lädt und chart() sich aufrufen lässt
DOM_ATTRAPPE = """
var window = globalThis;
function el() { return {addEventListener: function () {}, style: {}, querySelectorAll: function () { return []; },
                        innerHTML: '', textContent: ''}; }
var document = {getElementById: function () { return el(); }, querySelectorAll: function () { return []; },
                addEventListener: function () {}};
var fetch = function () { return new Promise(function () {}); };
var WSKommentar = {alle: function () {}};
var DATEN = null, KOMMENTARE = {};
"""


class DatenInSkripten(unittest.TestCase):
    """Alle Daten, die eine Seite oder der Report in ein Skript schreibt,
    gehen durch `i18n.json_im_skript`: `<`, `>`, `&`, U+2028/U+2029 als
    Escapes, NaN und ±Unendlich als `null`. Bis 2.1.0 schrieb jede Seite ihr
    eigenes `json.dumps`: ein `Infinity` aus einer alten cache/rueckblick.json
    ließ das Diagramm des Rückblicks ohne Ende Gitterlinien zeichnen, U+2028
    in einem Namen brach ältere JavaScript-Engines (zweite Runde)."""

    BOESE = "a\u2028b\u2029c </script><!--<script> & d"

    def setUp(self):
        # Die Reiterleiste und die Startseite fragen den echten Katalog — hier unnötig
        for name, wert in (("pruef_offen", lambda: 0), ("geometry_state", lambda: (1, 0)),
                           ("pruef_liste", lambda home=None: ([], {}))):
            p = mock.patch.object(w, name, wert)
            p.start()
            self.addCleanup(p.stop)

    def daten(self, text: str, name: str):
        """`var NAME = …;` aus einem Skript: roh ohne < > & U+2028 U+2029,
        streng gelesen (NaN und Infinity sind kein JSON)."""
        m = re.search(r"var " + name + r" = (.*?);\n", text, re.S)
        self.assertIsNotNone(m, f"var {name} fehlt")
        for zeichen in ("<", ">", "&", "\u2028", "\u2029"):
            self.assertNotIn(zeichen, m.group(1), f"{name}: {zeichen!r} roh im Skript")
        return streng(m.group(1))

    def test_der_gemeinsame_weg(self):
        nan, inf = float("nan"), float("inf")
        self.assertEqual(i18n.json_im_skript({"a": nan, "b": [inf, 1.5, (-inf,)], "c": self.BOESE}),
                         '{"a": null, "b": [null, 1.5, [null]], "c": "a\\u2028b\\u2029c \\u003c/script\\u003e'
                         '\\u003c!--\\u003cscript\\u003e \\u0026 d"}')
        # Der Regelfall bleibt Byte für Byte, was die Seiten bis 2.1.0 schrieben
        normal = [{"id": "a", "name": "Größe <b> & Co", "lat": 49.5, "comment": "x\ny", "n": 3, "ok": True, "x": None}]
        bisher = (json.dumps(normal, ensure_ascii=False)
                  .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))
        self.assertEqual(i18n.json_im_skript(normal), bisher)
        self.assertEqual(i18n.json_endlich(normal, ensure_ascii=False), json.dumps(normal, ensure_ascii=False))
        self.assertEqual(i18n.json_endlich(5.0), "5.0")

    def test_rueckblick(self):
        nan, inf = float("nan"), float("inf")
        daten = {"zeit": "2026-10-03T12:00", "version": "0", "von": "2026-10-01", "bis": "2026-10-03", "max_km": inf,
                 "spots": [{"id": "alpha", "name": self.BOESE,
                            "stunden": [{"t": "2026-10-03T12:00", "m": inf, "mv": {"icon": nan, "gfs": 999999.0}}]}]}
        seite = w.rueckblick_page(load_config(CONFIG), daten, None, 2, {"alpha": self.BOESE})
        d = self.daten(seite, "DATEN")
        stunde = d["spots"][0]["stunden"][0]
        self.assertEqual((stunde["m"], stunde["mv"]["icon"], stunde["mv"]["gfs"]), (None, None, 999999.0))
        self.assertIsNone(d["max_km"])
        self.assertEqual(d["spots"][0]["name"], self.BOESE)
        self.assertEqual(self.daten(seite, "KOMMENTARE"), {"alpha": self.BOESE})

    def test_katalog_und_pruefseite(self):
        nan = float("nan")
        home = {"lat": 53.55, "lon": 9.99}
        spot = {"id": "alpha", "name": self.BOESE, "country": "DE", "lat": nan, "lon": 8.7, "water_body": "lake",
                "verified": True, "comment": self.BOESE}
        seite = w.katalog_page([spot], home)
        s = self.daten(seite, "SPOTS")[0]
        self.assertEqual((s["name"], s["comment"], s["lat"]), (self.BOESE, self.BOESE, None))
        self.assertEqual(self.daten(seite, "HOME"), home)
        eintrag = {"id": "alpha", "name": self.BOESE, "lat": 49.5, "lon": 8.7, "stufe": "pruefen", "grund": "g",
                   "comment": self.BOESE, "fetch_km": nan}                  # aus einer kaputten geometry.json
        seite = w.pruef_page([eintrag], {"lat": nan, "lon": 9.99})
        s = self.daten(seite, "SPOTS")[0]
        self.assertEqual((s["name"], s["fetch_km"]), (self.BOESE, None))
        self.assertEqual(self.daten(seite, "HOME"), {"lat": None, "lon": 9.99})

    def test_tagebuch(self):
        nan = float("nan")
        daten = {"sessions": [{"id": "s1", "spot": "alpha", "datum": "2026-10-01", "von": "10:00",
                               "vergleich": {"gemessen_kn": nan, "modelle": {"icon": float("inf")}}}],
                 "namen": {"alpha": self.BOESE}, "wings": [{"size": 5.0, "low": nan, "high": 20.0}],
                 "vorschlaege": [], "station_nah_km": 30.0}
        with mock.patch.object(w, "tagebuch_daten", return_value=daten):
            seite = w.tagebuch_page(load_config(CONFIG), [{"id": "alpha", "name": self.BOESE, "country": "DE"}],
                                    heute="2026-10-03")
        d = self.daten(seite, "TAGEBUCH")
        self.assertEqual(d["sessions"][0]["vergleich"], {"gemessen_kn": None, "modelle": {"icon": None}})
        self.assertEqual((d["wings"][0]["low"], d["namen"]["alpha"]), (None, self.BOESE))
        self.assertEqual(self.daten(seite, "SPOTS"), [{"id": "alpha", "name": self.BOESE, "region": "DE"}])

    def test_startseite(self):
        """`var HOME = {lat: …, lon: …}` bleibt in seiner Form (test_webui) —
        nur ein `.nan` in config.yaml steht als `null` da statt als `nan`,
        an dem bis 2.1.0 das ganze Skript der Startseite scheiterte."""
        cfg = load_config(CONFIG)
        lon = float(cfg["rider"]["home"]["lon"])
        cfg["rider"]["home"]["lat"] = float("nan")
        seite = w.page(cfg, w.form_defaults(cfg))
        self.assertIn(f"var HOME = {{lat: null, lon: {lon}}};\n", seite)
        self.assertEqual(self.daten(seite, "LEAFLET")["jsSri"], w.LEAFLET_JS_SRI)

    def test_report(self):
        """Die Karte (KARTE), die Grenzen des Stundenrasters (G) und die
        Tidenübersicht im Attribut, die das Skript mit JSON.parse liest."""
        nan, inf = float("nan"), float("inf")
        spot = {"id": "x", "name": self.BOESE, "lat": nan, "lon": 8.0, "drive_h": 1.0, "road_km": 10.0,
                "notes": "", "comment": self.BOESE}
        karte = report._map_block([], {}, [(spot, self.BOESE)], load_config(CONFIG), argparse.Namespace(radius=inf),
                                  nonce="n")
        d = self.daten(karte, "KARTE")
        self.assertIsNone(d["radius_km"])
        m = d["markers"][0]
        self.assertEqual((m["lat"], m["name"], m["kmt"], m["line"]), (None, self.BOESE, self.BOESE, self.BOESE))
        raster = report._raster_schalter({"dunkel_ueber": nan, "rot_unter": 8.0, "rot_ueber": inf,
                                          "gruen_von": 12.0, "gruen_bis": 22.0}, "n")
        self.assertEqual(streng(re.search(r"var G = (\{.*?\}), ROT = ", raster).group(1)),
                         {"dunkel_ueber": None, "rot_unter": 8.0, "rot_ueber": None, "gruen_von": 12.0,
                          "gruen_bis": 22.0})
        tide = report._tide_json({"aktiv": True, "hub": nan, "ereignisse": [], "versatz": 0})
        self.assertIsNone(streng(html.unescape(tide))["hub"])

    @unittest.skipUnless(NODE, "node fehlt")
    def test_rueckblick_diagramm(self):
        """rueckblick.js: unsinnige Windwerte — 999999 kn, Unendlich, negativ,
        Text — sind im Diagramm Lücken und ziehen die Achse nicht mit. Bis
        2.1.0 zeichnete es für 999999 kn 100 001 Gitterlinien, für Infinity
        ohne Ende. Mit sinnvollen Werten dasselbe Diagramm wie ohne die
        unsinnigen."""
        def stunden(werte):
            return [{"t": f"2026-10-0{1 + i // 24}T{i % 24:02d}:00", "m": m, "mv": {"icon": a, "gfs": 9.0}, "v": 7.5}
                    for i, (m, a) in enumerate(werte)]
        normal = stunden([(5 + i % 7, 4 + i % 5) for i in range(48)])
        kaputt = [dict(h) for h in normal]
        for i, wert in ((5, 999999.0), (6, float("inf")), (7, -40.0), (8, "12")):
            kaputt[i]["m"] = wert
            kaputt[i + 10]["mv"] = {"icon": wert, "gfs": wert}
        kaputt[20]["v"] = float("nan")
        # json.dumps schreibt Infinity und NaN — in einem Skript ist das JavaScript
        code = (DOM_ATTRAPPE + i18n.js_vorspann("de") + "\n" + (w.WEB / "rueckblick.js").read_text(encoding="utf-8")
                + "\nvar SPOTS = " + json.dumps([{"name": "normal", "stunden": normal},
                                                 {"name": "kaputt", "stunden": kaputt}]) + ";\n"
                "var aus = {};\nSPOTS.forEach(function (sp, i) {\n"
                "  sp._an = [{id: 'icon', slot: 0}, {id: 'wingscout', slot: 1}];\n"
                "  var svg = chart(sp, i);\n"
                "  aus[sp.name] = {gitter: (svg.match(/class=\"gitter\"/g) || []).length,\n"
                "                  max: Number(svg.match(/data-max=\"([^\"]*)\"/)[1]),\n"
                "                  riesig: /(^|[^0-9.])[0-9]{5,}/.test(svg)};\n"   # Koordinaten weit außerhalb
                "});\nprocess.stdout.write(JSON.stringify(aus));\n")
        lauf = subprocess.run([NODE, "-"], input=code, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(lauf.returncode, 0, lauf.stderr[-2000:])
        aus = json.loads(lauf.stdout)
        self.assertEqual(aus["normal"], {"gitter": 4, "max": 15, "riesig": False})
        self.assertEqual(aus["kaputt"], aus["normal"])


# ── C4: NaN im Report ───────────────────────────────────────────────────────

class ReportMitNaN(unittest.TestCase):
    def test_marker_band(self):
        nan, inf = float("nan"), float("inf")
        rows = [{"score": nan, "wind": inf}, {"score": 0.5, "wind": 12.4}, {"score": inf, "wind": nan},
                {"score": -inf, "wind": -inf}, {"score": 1.7, "wind": 140.0}]
        sc, wd = report._marker_band(rows)
        self.assertEqual(sc, "04009")
        self.assertEqual(wd, "0012000099")

    def test_marker_band_wie_bisher(self):
        """Endliche Werte: genau die Formel von vorher."""
        rows = [{"score": s / 37, "wind": s * 1.37 - 3} for s in range(-5, 60)]
        sc = "".join(str(min(9, max(0, int(round(r["score"] * 9))))) for r in rows)
        wd = "".join(f"{min(99, max(0, int(round(r['wind'])))):02d}" for r in rows)
        self.assertEqual(report._marker_band(rows), (sc, wd))


# ── C17: der Blick auf einen belegten Port ──────────────────────────────────

class Endlos(BaseHTTPRequestHandler):
    """Ein fremdes Programm, das auf /status nicht aufhört zu antworten."""
    gesendet = 0

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        stueck = b"[" + b"1," * 32767
        ende = time.monotonic() + 6
        try:
            while time.monotonic() < ende:
                self.wfile.write(stueck)
                Endlos.gesendet += len(stueck)
                time.sleep(0.01)
        except OSError:
            pass

    def log_message(self, *a):
        pass


class Portprobe(unittest.TestCase):
    def test_liest_hoechstens_64_kb(self):
        fremd = ThreadingHTTPServer(("127.0.0.1", 0), Endlos)
        threading.Thread(target=fremd.serve_forever, daemon=True).start()
        try:
            beginn = time.monotonic()
            self.assertEqual(w.port_belegt_von(fremd.server_address[1]), "fremd")
            self.assertLess(time.monotonic() - beginn, 4, "die ganze Antwort gelesen statt 64 kB")
        finally:
            fremd.shutdown()
            fremd.server_close()

    def test_eigener_server_mit_langem_protokoll(self):
        """Die eigene /status-Antwort kann länger als 64 kB sein — sie zählt trotzdem."""
        with w.LOCK:
            vorher = dict(w.JOB)
            w.JOB["log"] = ["x" * 99] * 2000                     # gut 200 kB
        eigen = ThreadingHTTPServer(("127.0.0.1", 0), w.Handler)
        threading.Thread(target=eigen.serve_forever, daemon=True).start()
        try:
            self.assertEqual(w.port_belegt_von(eigen.server_address[1]), "wingscout")
        finally:
            eigen.shutdown()
            eigen.server_close()
            with w.LOCK:
                w.JOB.clear()
                w.JOB.update(vorher)

    def test_kurz_genug_fuer_json(self):
        self.assertGreaterEqual(w.PROBE_GRENZE, 16 * 1024)
        self.assertLessEqual(w.PROBE_GRENZE, 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
