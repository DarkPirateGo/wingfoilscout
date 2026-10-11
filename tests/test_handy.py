"""Reiter „Handy“ (seit 2.5.0): QR-Code, bleibender Zugangsschlüssel,
Zertifikat für https im WLAN — und dass nichts davon die Sicherheitsregeln
aufweicht.

Kein Test schreibt in den echten Ordner `handy/`: Jeder lenkt
`handy.ORDNER` in einen Wegwerf-Ordner um (`EigenerOrdner`).
"""
from __future__ import annotations

import hashlib
import json
import os
import plistlib
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from tests.helpers import CONFIG
from wingscout import handy, qr, zertifikat as zert
import wingscout.webui as w


# Ein Zertifikat für alle Tests, die eines brauchen: zwei RSA-Schlüssel
# kosten in Python ein, zwei Sekunden. Erzeugt wird es trotzdem auf dem
# echten Weg (handy.zertifikat_erzeugen); nur der Knopf im laufenden Server
# erzeugt eigens eins (FreigabeImWlan).
VORRAT: dict = {}


def setUpModule():
    VORRAT["tmp"] = tempfile.TemporaryDirectory()
    VORRAT["ordner"] = Path(VORRAT["tmp"].name) / "handy"
    VORRAT["meta"] = handy.zertifikat_erzeugen(["127.0.0.1", "127.0.0.2", "192.168.1.23", "kein-ip"],
                                               "Test-Mac.local", pfad=VORRAT["ordner"])


def tearDownModule():
    VORRAT["tmp"].cleanup()


class EigenerOrdner(unittest.TestCase):
    """Ein Wegwerf-Ordner statt `handy/` im Projekt, Freigabe danach aus."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ordner = Path(tmp.name) / "handy"
        patcher = mock.patch.object(handy, "ORDNER", self.ordner)
        patcher.start()
        self.addCleanup(patcher.stop)
        alt = dict(w.LAN)
        self.addCleanup(lambda: (w.freigabe_beenden(), w.LAN.update(alt)))

    def zertifikat_holen(self) -> None:
        shutil.copytree(VORRAT["ordner"], self.ordner, dirs_exist_ok=True)


# ── QR-Code ──────────────────────────────────────────────────────────────────

def _bits(m) -> str:
    return "".join("1" if b else "0" for zeile in m for b in zeile)


def _bch_format(maske: int) -> int:
    """Das Formatfeld für Stufe M (Kennbits 00) und `maske`, wie die Norm es baut."""
    rest = maske
    for _ in range(10):
        rest = (rest << 1) ^ ((rest >> 9) * 0x537)
    return (maske << 10 | rest) ^ 0x5412


class QRCode(unittest.TestCase):
    # Feste Ergebnisse (SHA-256 über die Module, Zeile für Zeile). Beim Bau am
    # 10.10.2026 mit einem unabhängigen Leser geprüft: OpenCV 4.13
    # (cv2.QRCodeDetector) las jeden dieser Codes als genau diesen Text.
    FESTE = {
        "https://192.168.1.23:8765/?k=Ab3dEf6hIj9lMn0p":
            "d360507f125ff19bbd9e2b53dda0414384fb553fa31e6483a240b6249371e1d2",
        "http://10.0.0.5:8766/?k=0123456789abcdef":
            "31ca17b260b0d986bb0fcef2a93a7c599094218471bde7e6e51ccc1749645ee1",
        "https://Mein-Mac.local:8765/?k=Zz-_Yy09Xx87Ww65":
            "ad6c868e76c2c1f0688ff1d49fca782596d391b481f6d0f28208831c1920e652",
        "Wingfoilscout": "521b89362daadc3bf7f276ff3d17585659cdd86d434ffdfce9174fc7713461d8",
        "x" * 213: "f673820bb5ccd3f0f6035d879c98fa30d6d1f03153cace0b9a23da4e0a681a53",
    }

    def test_feste_ergebnisse(self):
        for text, soll in self.FESTE.items():
            with self.subTest(text[:30]):
                self.assertEqual(hashlib.sha256(_bits(qr.matrix(text)).encode()).hexdigest(), soll)

    def test_groesse_waechst_mit_dem_text(self):
        # Fassungsvermögen bei Fehlerkorrektur M im Byte-Modus, Versionen 1 bis 10
        grenzen = [14, 26, 42, 62, 84, 106, 122, 152, 180, 213]
        for version, grenze in enumerate(grenzen, 1):
            with self.subTest(version=version):
                self.assertEqual(len(qr.matrix("a" * grenze)), 17 + 4 * version)
                if version < 10:
                    self.assertEqual(len(qr.matrix("a" * (grenze + 1))), 17 + 4 * (version + 1))
        with self.assertRaises(ValueError):
            qr.matrix("a" * 214)

    def test_feste_muster(self):
        """Suchmuster, Trennlinien, Taktlinien, das dunkle Modul, das
        Formatfeld in beiden Kopien — und ab Version 7 das Versionsfeld."""
        for text in self.FESTE:
            m = qr.matrix(text)
            n = len(m)
            version = (n - 17) // 4
            with self.subTest(version=version):
                for x0, y0 in ((0, 0), (n - 7, 0), (0, n - 7)):
                    for dy in range(7):
                        for dx in range(7):
                            soll = dx in (0, 6) or dy in (0, 6) or (2 <= dx <= 4 and 2 <= dy <= 4)
                            self.assertEqual(m[y0 + dy][x0 + dx], soll, (x0, y0, dx, dy))
                for i in range(8):
                    self.assertFalse(m[7][i] or m[i][7] or m[7][n - 1 - i] or m[n - 8][i])
                for i in range(8, n - 8):
                    self.assertEqual(m[6][i], i % 2 == 0)
                    self.assertEqual(m[i][6], i % 2 == 0)
                self.assertTrue(m[4 * version + 9][8])

                eins = [m[i][8] for i in range(6)] + [m[7][8], m[8][8], m[8][7]] + [m[8][14 - i] for i in range(9, 15)]
                zwei = [m[8][n - 1 - i] for i in range(8)] + [m[n - 15 + i][8] for i in range(8, 15)]
                self.assertEqual(eins, zwei)
                wert = sum(int(b) << i for i, b in enumerate(eins))
                self.assertIn(wert, [_bch_format(maske) for maske in range(8)])

                if version >= 7:
                    rest = version
                    for _ in range(12):
                        rest = (rest << 1) ^ ((rest >> 11) * 0x1F25)
                    feld = version << 12 | rest
                    for i in range(18):
                        a, b = n - 11 + i % 3, i // 3
                        self.assertEqual(m[b][a], bool(feld >> i & 1))
                        self.assertEqual(m[a][b], bool(feld >> i & 1))

    def test_svg_zum_einbetten(self):
        bild = qr.svg("Wingfoilscout", titel="Code")
        self.assertTrue(bild.startswith("<svg viewBox='0 0 29 29'"))      # 21 Module + 2 × 4 Ruhezone
        self.assertNotIn("xmlns", bild)                                   # im HTML nicht nötig
        self.assertIn("<title>Code</title>", bild)
        self.assertIn("fill='#fff'", bild)
        self.assertEqual(bild.count("<path"), 1)


# ── Zugangsschlüssel ─────────────────────────────────────────────────────────

class Zugangsschluessel(EigenerOrdner):
    def test_bleibt_ueber_neustarts_gleich(self):
        erster = handy.schluessel()
        self.assertRegex(erster, r"^[A-Za-z0-9_-]{16}$")
        self.assertEqual(handy.schluessel(), erster)
        self.assertEqual(json.loads((self.ordner / handy.ZUGANG).read_text())["schluessel"], erster)

    def test_neuer_ersetzt_den_alten(self):
        alt = handy.schluessel()
        neu = handy.neuer_schluessel()
        self.assertNotEqual(alt, neu)
        self.assertEqual(handy.schluessel(), neu)

    def test_kaputte_datei_gibt_einen_neuen(self):
        self.ordner.mkdir(parents=True)
        for inhalt in ("kein json", '{"schluessel": "kurz"}', '{"schluessel": "mit leerzeichen drin !!"}', "[]"):
            with self.subTest(inhalt):
                (self.ordner / handy.ZUGANG).write_text(inhalt)
                self.assertRegex(handy.schluessel(), r"^[A-Za-z0-9_-]{16}$")

    @unittest.skipIf(os.name != "posix", "Dateirechte nur unter macOS/Linux")
    def test_nur_fuer_den_besitzer(self):
        handy.schluessel()
        self.assertEqual((self.ordner / handy.ZUGANG).stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.ordner.stat().st_mode & 0o077, 0)

    def test_die_seite_legt_keinen_an(self):
        """Den Reiter ansehen erzeugt nichts — erst die Freigabe braucht den Schlüssel."""
        w.handy_page(w.handy_stand())
        self.assertFalse(self.ordner.exists())


# ── Bonjour-Name ─────────────────────────────────────────────────────────────

class BonjourName(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.datei = Path(tmp.name) / "preferences.plist"

    def _plist(self, name, fmt=plistlib.FMT_BINARY):
        self.datei.write_bytes(plistlib.dumps({"System": {"Network": {"HostNames": {"LocalHostName": name}}}},
                                              fmt=fmt))

    def test_aus_den_systemeinstellungen(self):
        self._plist("Mein-Mac")
        self.assertEqual(handy.bonjour_name(self.datei), "Mein-Mac.local")
        self._plist("Mein-Mac-2", fmt=plistlib.FMT_XML)
        self.assertEqual(handy.bonjour_name(self.datei), "Mein-Mac-2.local")

    def test_sonst_der_rechnername_wenn_er_auf_local_endet(self):
        self.datei.write_text("kaputt")
        with mock.patch("socket.gethostname", return_value="Mein-Mac.local"):
            self.assertEqual(handy.bonjour_name(self.datei), "Mein-Mac.local")
        # Mit einer FRITZ!Box heißt der Mac oft „…fritz.box“ — das findet das iPhone nicht über Bonjour
        with mock.patch("socket.gethostname", return_value="mein-mac.fritz.box"):
            self.assertIsNone(handy.bonjour_name(self.datei))
        with mock.patch("socket.gethostname", return_value="mein-mac"):
            self.assertIsNone(handy.bonjour_name(self.datei / "fehlt"))

    def test_nur_ein_harmloser_name(self):
        for name in ("Mein Mac", "a/../b", "x" * 64, "", 7):
            with self.subTest(name), mock.patch("socket.gethostname", return_value="localhost"):
                self._plist(name)
                self.assertIsNone(handy.bonjour_name(self.datei))


# ── Zertifikat ───────────────────────────────────────────────────────────────

def _antwort(ctx, port, name, pfad="/manifest.webmanifest", host="127.0.0.1"):
    """Eine Anfrage über TLS an 127.0.0.1:`port`, geprüft wird gegen `name`."""
    with socket.create_connection((host, port), timeout=10) as roh:
        with ctx.wrap_socket(roh, server_hostname=name) as s:
            s.sendall(f"GET {pfad} HTTP/1.0\r\nHost: {host}:{port}\r\n\r\n".encode())
            teile = []
            while True:
                stueck = s.recv(65536)
                if not stueck:
                    break
                teile.append(stueck)
    return b"".join(teile)


class Zertifikat(unittest.TestCase):
    """Das Zertifikat aus dem Vorrat, von allen Seiten geprüft — mit OpenSSL
    als Gegenstelle, wie Safari auf dem iPhone eine ist."""

    @classmethod
    def setUpClass(cls):
        cls.ordner, cls.meta = VORRAT["ordner"], VORRAT["meta"]
        cls.ca = str(cls.ordner / handy.CA)

    def test_was_es_abdeckt(self):
        self.assertEqual(self.meta["ips"], ["127.0.0.1", "127.0.0.2", "192.168.1.23"])
        self.assertEqual(self.meta["namen"], ["Test-Mac.local"])
        self.assertEqual(self.meta["erstellt"], date.today().isoformat())
        self.assertEqual(self.meta["bis"], (date.today() + timedelta(days=handy.TAGE_SERVER)).isoformat())
        self.assertFalse(self.meta["abgelaufen"])
        self.assertEqual(handy.zertifikat(self.ordner), self.meta)

    def test_im_ordner_liegt_kein_schluessel_der_zertifizierungsstelle(self):
        """Nur der Schlüssel des Servers ist gespeichert — der, mit dem die
        Zertifizierungsstelle unterschrieben hat, war nur im Arbeitsspeicher."""
        self.assertEqual(sorted(p.name for p in self.ordner.iterdir()),
                         sorted([handy.CA, handy.SERVER_CRT, handy.SERVER_KEY, handy.PROFIL, handy.META]))
        for datei in self.ordner.iterdir():
            with self.subTest(datei.name):
                self.assertEqual("PRIVATE KEY" in datei.read_text(encoding="utf-8"), datei.name == handy.SERVER_KEY)
                if os.name == "posix":
                    self.assertEqual(datei.stat().st_mode & 0o777, 0o600)

    def _server(self):
        """Ein TLS-Server mit handy.tls_kontext, der eine Verbindung bedient."""
        kontext = handy.tls_kontext(self.ordner)
        self.assertIsNotNone(kontext)
        lauscher = socket.socket()
        lauscher.bind(("127.0.0.1", 0))
        lauscher.listen(4)
        self.addCleanup(lauscher.close)

        def bedienen():
            try:
                roh, _ = lauscher.accept()
                with kontext.wrap_socket(roh, server_side=True) as s:
                    s.recv(1024)
                    s.sendall(b"HTTP/1.0 200 OK\r\n\r\nhallo")
            except (OSError, ssl.SSLError):
                pass
        threading.Thread(target=bedienen, daemon=True).start()
        return lauscher.getsockname()[1]

    def test_handshake_mit_adresse_und_name(self):
        """OpenSSL prüft dabei Kette, Unterschrift, Verwendungszweck und
        SubjectAltName — wie Safari, wenn das Profil installiert ist."""
        ctx = ssl.create_default_context(cafile=self.ca)
        for name in ("127.0.0.1", "Test-Mac.local"):
            with self.subTest(name):
                self.assertTrue(_antwort(ctx, self._server(), name).endswith(b"hallo"))

    def test_anderer_name_oder_ohne_profil_kein_vertrauen(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            _antwort(ssl.create_default_context(cafile=self.ca), self._server(), "anderer-mac.local")
        with self.assertRaises(ssl.SSLCertVerificationError):
            _antwort(ssl.create_default_context(), self._server(), "127.0.0.1")    # nur die üblichen Wurzeln

    def test_apples_vorgaben(self):
        """Höchstens 825 Tage, Namen im SubjectAltName, Version 3, und die
        Zertifizierungsstelle darf nichts unterhalb weiter beglaubigen lassen."""
        ctx = ssl.create_default_context(cafile=self.ca)
        port = self._server()
        with socket.create_connection(("127.0.0.1", port), timeout=10) as roh:
            with ctx.wrap_socket(roh, server_hostname="127.0.0.1") as s:
                cert = s.getpeercert()
        von, bis = (ssl.cert_time_to_seconds(cert[k]) for k in ("notBefore", "notAfter"))
        self.assertLessEqual((bis - von) / 86400, 825)
        self.assertEqual(cert["version"], 3)
        self.assertEqual(cert["subjectAltName"], (("IP Address", "127.0.0.1"), ("IP Address", "127.0.0.2"),
                                                  ("IP Address", "192.168.1.23"), ("DNS", "Test-Mac.local")))

    @unittest.skipUnless(shutil.which("openssl"), "openssl nicht installiert")
    def test_openssl_verify_streng(self):
        version = subprocess.run(["openssl", "version"], capture_output=True, text=True).stdout
        if not version.startswith("OpenSSL"):
            self.skipTest(f"anderes openssl: {version.strip()}")     # LibreSSL auf dem Mac kennt nicht jede Option
        for pruefung in (["-verify_ip", "192.168.1.23"], ["-verify_hostname", "Test-Mac.local"]):
            with self.subTest(pruefung[0]):
                aus = subprocess.run(["openssl", "verify", "-x509_strict", "-purpose", "sslserver", *pruefung,
                                      "-CAfile", self.ca, str(self.ordner / handy.SERVER_CRT)],
                                     capture_output=True, text=True)
                self.assertEqual(aus.returncode, 0, aus.stdout + aus.stderr)

    def test_profil_traegt_nur_das_zertifikat_der_zertifizierungsstelle(self):
        profil = plistlib.loads((self.ordner / handy.PROFIL).read_bytes())
        self.assertEqual(profil["PayloadType"], "Configuration")
        self.assertFalse(profil["PayloadRemovalDisallowed"])
        (nutzlast,) = profil["PayloadContent"]
        self.assertEqual(nutzlast["PayloadType"], "com.apple.security.root")
        self.assertEqual(nutzlast["PayloadContent"],
                         ssl.PEM_cert_to_DER_cert((self.ordner / handy.CA).read_text()))

    def test_ohne_adresse_kein_zertifikat(self):
        with self.assertRaises(handy.HandyFehler):
            handy.zertifikat_erzeugen(["kein-ip"], "kein name", pfad=self.ordner / "leer")

    def test_kaputte_dateien(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(handy.zertifikat(d))
            self.assertIsNone(handy.tls_kontext(d))
            for datei in (handy.SERVER_CRT, handy.SERVER_KEY, handy.CA, handy.META):
                shutil.copy(self.ordner / datei, Path(d) / datei)
            self.assertIsNotNone(handy.zertifikat(d))
            (Path(d) / handy.SERVER_KEY).write_text("kein Schlüssel")
            self.assertIsNone(handy.tls_kontext(d))
            self.assertIsNone(handy.zertifikat(d))


class Bausteine(unittest.TestCase):
    """Die Kodierung im Kleinen — Werte aus RFC 5280 und X.690."""

    def test_der(self):
        self.assertEqual(zert._oid("1.2.840.113549.1.1.11").hex(), "06092a864886f70d01010b")
        self.assertEqual(zert._int(127).hex(), "02017f")
        self.assertEqual(zert._int(128).hex(), "02020080")          # sonst wäre es negativ
        self.assertEqual(zert._laenge(300).hex(), "82012c")

    def test_signatur_passt_zum_schluessel(self):
        k = zert.rsa_schluessel(1024)                                 # klein: nur fürs Rechnen
        self.assertEqual(k["n"].bit_length(), 1024)
        self.assertEqual(k["n"], k["p"] * k["q"])
        sig = int.from_bytes(zert._signieren(b"Wingfoilscout", k), "big")
        em = pow(sig, k["e"], k["n"]).to_bytes(128, "big")
        self.assertTrue(em.startswith(b"\x00\x01\xff"))
        self.assertTrue(em.endswith(hashlib.sha256(b"Wingfoilscout").digest()))

    def test_zeit_ab_2050(self):
        from datetime import datetime, timezone
        self.assertEqual(zert._zeit(datetime(2049, 12, 31, tzinfo=timezone.utc))[:1], b"\x17")    # UTCTime
        self.assertEqual(zert._zeit(datetime(2050, 1, 1, tzinfo=timezone.utc))[:1], b"\x18")      # GeneralizedTime


# ── Die Adresse fürs iPhone ──────────────────────────────────────────────────

class Startadressen(unittest.TestCase):
    META = {"ips": ["192.168.1.23"], "namen": ["Mein-Mac.local"], "abgelaufen": False}

    def test_https_ueber_die_adresse_im_zertifikat(self):
        aus = handy.startadressen(["192.168.1.23"], 8765, "k" * 16, self.META)
        self.assertEqual(aus["https"], "https://192.168.1.23:8765/?k=" + "k" * 16)
        self.assertEqual(aus["ueber"], "ip")
        self.assertEqual(aus["http"], "http://192.168.1.23:8765/?k=" + "k" * 16)

    def test_neue_adresse_dann_der_name(self):
        aus = handy.startadressen(["192.168.1.99"], 8765, "k" * 16, self.META)
        self.assertEqual(aus["https"], "https://Mein-Mac.local:8765/?k=" + "k" * 16)
        self.assertEqual(aus["ueber"], "name")

    def test_ohne_passendes_oder_abgelaufen_nur_http(self):
        self.assertEqual(handy.startadressen(["192.168.1.99"], 8765, "k", dict(self.META, namen=[]))["https"], "")
        self.assertEqual(handy.startadressen(["192.168.1.23"], 8765, "k", dict(self.META, abgelaufen=True))["https"], "")
        self.assertEqual(handy.startadressen(["192.168.1.23"], 8765, "k", None)["https"], "")
        self.assertEqual(handy.startadressen([], 8765, "k", None), {"https": "", "http": "", "ueber": ""})

    def test_abgelaufen_steht_im_zertifikat(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(handy, "tls_kontext", return_value=object()):
                (Path(d) / handy.CA).write_text("x")
                (Path(d) / handy.META).write_text(json.dumps({"ips": ["192.168.1.23"], "bis": "2020-01-01"}))
                self.assertTrue(handy.zertifikat(d)["abgelaufen"])


# ── Der Reiter ───────────────────────────────────────────────────────────────

class Reiter(unittest.TestCase):
    STAND = {"aktiv": False, "adressen": ["192.168.1.23"], "zertifikat": None, "passt": False,
             "https": "", "http": ""}

    def test_ohne_freigabe_der_knopf_und_kein_code(self):
        seite = w.handy_page(dict(self.STAND))
        self.assertIn("data-pfad='/handy/freigeben'", seite)
        self.assertIn("data-pfad='/handy/zertifikat'", seite)
        self.assertNotIn("class='hqr'", seite)
        self.assertNotIn("/handy/profil", seite)            # erst mit Zertifikat
        self.assertIn("Not Secure Connection Warning", seite)

    def test_freigegeben_mit_zertifikat(self):
        url = "https://192.168.1.23:8765/?k=" + "k" * 16
        meta = {"ips": ["192.168.1.23"], "namen": [], "erstellt": "2026-10-10", "bis": "2029-01-07",
                "abgelaufen": False}
        seite = w.handy_page(dict(self.STAND, aktiv=True, zertifikat=meta, passt=True, https=url,
                                  http=url.replace("https", "http")))
        self.assertIn("<div class='hqr'><svg viewBox", seite)
        self.assertIn(url, seite)
        self.assertIn("href='/handy/profil'", seite)
        self.assertIn("„Wingfoilscout 2026-10-10“", seite)    # so heißt die Zertifizierungsstelle auf dem iPhone
        self.assertIn("data-pfad='/handy/beenden'", seite)

    def test_freigegeben_ohne_zertifikat_warnt(self):
        url = "http://192.168.1.23:8765/?k=" + "k" * 16
        seite = w.handy_page(dict(self.STAND, aktiv=True, http=url))
        self.assertIn(url, seite)
        self.assertIn("class='hart offen'", seite)
        self.assertIn("class='hwarn'", seite)

    def test_zertifikat_passt_nicht_mehr(self):
        meta = {"ips": ["192.168.1.5"], "namen": [], "erstellt": "2026-10-10", "bis": "2029-01-07",
                "abgelaufen": False}
        self.assertIn("passt nicht", w.handy_page(dict(self.STAND, zertifikat=meta)))
        self.assertIn("abgelaufen", w.handy_page(dict(self.STAND, zertifikat=dict(meta, abgelaufen=True))))


class Probeserver(w.BegrenzterServer):
    """„Von außen“ ist hier jede Verbindung — im Test kommt alles von 127.0.0.1."""
    aussen = False

    def von_aussen(self, client_address):
        return self.aussen


class ServerBasis(EigenerOrdner):
    """Ein echter Server auf 127.0.0.1 (der Probeserver)."""

    def setUp(self):
        super().setUp()
        w.Handler.cfg_path = str(CONFIG)
        self.server = Probeserver(("127.0.0.1", 0), w.Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        alt_port = w.PORT["nr"]
        w.PORT["nr"] = self.port
        self.addCleanup(lambda: w.PORT.update(nr=alt_port))

    def _http(self, methode, pfad, koerper=None):
        import http.client
        verbindung = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            kopf = {"Content-Type": "application/json"} if koerper is not None else {}
            verbindung.request(methode, pfad, body=koerper, headers=kopf)
            r = verbindung.getresponse()
            return r.status, dict(r.getheaders()), r.read()
        finally:
            verbindung.close()



class AmLaufendenServer(ServerBasis):
    """Reiter, Profil und Knöpfe am Server — mit Zertifikat spricht er https
    und http auf demselben Port."""

    def test_reiter_und_profil_am_mac(self):
        status, _, seite = self._http("GET", "/handy")
        self.assertEqual(status, 200)
        self.assertIn("data-pfad='/handy/freigeben'".encode(), seite)
        self.assertEqual(self._http("GET", "/handy/profil")[0], 404)       # noch kein Zertifikat
        self.zertifikat_holen()
        status, kopf, profil = self._http("GET", "/handy/profil")
        self.assertEqual(status, 200)
        self.assertEqual(kopf["Content-Type"], "application/x-apple-aspen-config")
        self.assertIn("attachment", kopf["Content-Disposition"])
        self.assertEqual(plistlib.loads(profil)["PayloadType"], "Configuration")

    def test_vom_handy_nur_der_hinweis_und_keine_knoepfe(self):
        Probeserver.aussen = True
        self.addCleanup(setattr, Probeserver, "aussen", False)
        status, _, seite = self._http("GET", "/handy")
        self.assertEqual(status, 200)
        self.assertNotIn(b"data-pfad", seite)
        for pfad in ("/handy/freigeben", "/handy/beenden", "/handy/zertifikat", "/handy/schluessel"):
            with self.subTest(pfad):
                self.assertEqual(self._http("POST", pfad, b"{}")[0], 403)
        self.assertFalse(self.ordner.exists())                            # nichts erzeugt

    def test_unbekannter_knopf(self):
        self.assertEqual(self._http("POST", "/handy/finder", b"{}")[0], 404)

    def test_https_und_http_auf_einem_port(self):
        self.zertifikat_holen()
        self.server.tls = handy.tls_kontext()
        ctx = ssl.create_default_context(cafile=str(self.ordner / handy.CA))
        for name in ("127.0.0.1", "Test-Mac.local"):
            with self.subTest(name):
                antwort = _antwort(ctx, self.port, name)
                self.assertTrue(antwort.startswith(b"HTTP/1.0 200"), antwort[:80])
        self.assertEqual(self._http("GET", "/manifest.webmanifest")[0], 200)

    def test_gescheiterter_handshake_haelt_nichts_fest(self):
        self.zertifikat_holen()
        self.server.tls = handy.tls_kontext()
        with socket.create_connection(("127.0.0.1", self.port), timeout=10) as s:
            s.sendall(b"\x16\x03\x01\x00\x05kaputt")
            try:
                while s.recv(1024):                                     # ein TLS-Alarm, dann schließt er
                    pass
            except ConnectionResetError:                                # … oder gleich, samt ungelesenem Rest
                pass
        for _ in range(100):
            if self.server.offen["alle"] == 0:
                break
            time.sleep(0.05)
        self.assertEqual(self.server.offen, {"alle": 0, "aussen": 0})
        self.assertEqual(self._http("GET", "/manifest.webmanifest")[0], 200)


class FreigabeImWlan(ServerBasis):
    """Freigeben und beenden über die Knöpfe — ein Server je Adresse im
    WLAN, hier 127.0.0.2. Andere Geräte spielt 127.0.0.3 (unter Linux ist
    127.0.0.0/8 ganz da; macOS kennt ohne Weiteres nur 127.0.0.1)."""

    def setUp(self):
        super().setUp()
        try:
            with socket.socket() as probe:
                probe.bind(("127.0.0.2", 0))
            with socket.socket() as probe:
                probe.bind(("127.0.0.3", 0))
        except OSError:
            self.skipTest("127.0.0.2/127.0.0.3 nicht verfügbar")
        patcher = mock.patch.object(handy, "adressen", return_value=["127.0.0.2"])
        patcher.start()
        self.addCleanup(patcher.stop)

    def _von(self, pfad, cookie=""):
        """GET an 127.0.0.2 als anderes Gerät (Absender 127.0.0.3)."""
        with socket.create_connection(("127.0.0.2", self.port), timeout=10, source_address=("127.0.0.3", 0)) as s:
            s.sendall(f"GET {pfad} HTTP/1.0\r\nHost: 127.0.0.2:{self.port}\r\nCookie: {cookie}\r\n\r\n".encode())
            teile = []
            while True:
                stueck = s.recv(65536)
                if not stueck:
                    break
                teile.append(stueck)
        return b"".join(teile)

    def test_freigeben_schluessel_beenden(self):
        self.assertEqual(self._http("POST", "/handy/freigeben", b"{}")[0], 200)
        self.assertTrue(w.LAN["aktiv"])
        schluessel = handy.schluessel()
        self.assertEqual(w.LAN["schluessel"], schluessel)
        self.assertTrue(self._von("/").startswith(b"HTTP/1.0 401"))
        mit = self._von(f"/?k={schluessel}")
        self.assertTrue(mit.startswith(b"HTTP/1.0 302"))
        self.assertIn(f"wingscout_schluessel={schluessel}".encode(), mit)
        self.assertTrue(self._von("/manifest.webmanifest", f"wingscout_schluessel={schluessel}")
                        .startswith(b"HTTP/1.0 200"))

        # Neuer Schlüssel: der alte gilt sofort nicht mehr
        self.assertEqual(self._http("POST", "/handy/schluessel", b"{}")[0], 200)
        self.assertTrue(self._von("/manifest.webmanifest", f"wingscout_schluessel={schluessel}")
                        .startswith(b"HTTP/1.0 401"))

        self.assertEqual(self._http("POST", "/handy/beenden", b"{}")[0], 200)
        self.assertFalse(w.LAN["aktiv"])
        with self.assertRaises(OSError):
            self._von("/")

    def test_zertifikat_waehrend_der_freigabe(self):
        """„Zertifikat erzeugen“ bei laufender Freigabe: ab der nächsten
        Verbindung spricht der Server im WLAN https — ohne Neustart."""
        self.assertEqual(self._http("POST", "/handy/freigeben", b"{}")[0], 200)
        self.assertFalse(w.LAN["tls"])
        self.assertEqual(self._http("POST", "/handy/zertifikat", b"{}")[0], 200)
        self.assertTrue(w.LAN["tls"])
        stand = w.handy_stand()
        self.assertTrue(stand["https"].startswith(f"https://127.0.0.2:{self.port}/?k="))
        ctx = ssl.create_default_context(cafile=str(self.ordner / handy.CA))
        with socket.create_connection(("127.0.0.2", self.port), timeout=10, source_address=("127.0.0.3", 0)) as roh:
            with ctx.wrap_socket(roh, server_hostname="127.0.0.2") as s:
                s.sendall(f"GET /manifest.webmanifest HTTP/1.0\r\nHost: 127.0.0.2:{self.port}\r\n"
                          f"Cookie: wingscout_schluessel={handy.schluessel()}\r\n\r\n".encode())
                self.assertTrue(s.recv(1024).startswith(b"HTTP/1.0 200"))


if __name__ == "__main__":
    unittest.main()
