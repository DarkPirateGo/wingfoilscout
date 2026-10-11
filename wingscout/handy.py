"""Wingfoilscout aufs Handy (seit 2.5.0): bleibender Zugangsschlüssel und ein
eigenes Zertifikat, damit Safari Wingfoilscout im WLAN über https öffnet.

Gewünscht am 10.10.2026, nachdem Safari auf dem iPhone die Adresse mit „Die
Steuerung ist fehlgeschlagen, da die Anfrage für eine HTTP-URL mit aktiviertem
Modus ‚HTTPS-Only‘ war“ abwies. Ist dort die Einstellung „Not Secure Connection
Warning“ an (Einstellungen → Apps → Safari), öffnet Safari im Heimnetz keine
http-Adresse. Zwei Wege, beide im Reiter „Handy“ erklärt:

1. Mit Zertifikat (empfohlen): Eine eigene Zertifizierungsstelle (CA) nur für
   diesen Mac stellt ein Serverzertifikat für seine Adressen im WLAN und seinen
   Bonjour-Namen aus und ist danach weg: Ihr Schlüssel entsteht im
   Arbeitsspeicher, unterschreibt ein einziges Mal und wird nie gespeichert
   (zertifikat.py — ohne openssl, ohne ein anderes Programm zu starten).
   Niemand kann damit später weitere Zertifikate ausstellen, denen das iPhone
   vertraut — auch nicht, wer an den Mac kommt. Das Zertifikat der CA geht als
   Profil aufs iPhone (AirDrop), wird dort installiert und unter
   „Zertifikatsvertrauenseinstellungen“ eingeschaltet. Ändert sich die Adresse
   des Macs so, dass das Zertifikat sie nicht mehr abdeckt, oder läuft es ab
   (nach gut zwei Jahren): neu erzeugen und das neue Profil aufs iPhone.
2. Ohne Zertifikat: die Safari-Einstellung aus; die Verbindung bleibt dann
   unverschlüsselt (http), wie bis 2.4.0.

Dazu bleibt der Zugangsschlüssel gleich, bis jemand einen neuen erzeugt. Bis
2.4.0 galt er nur für einen Lauf, und das Symbol auf dem Home-Bildschirm ging
nach jedem Neustart von Wingfoilscout ins Leere.

Alles liegt in `handy/` im Wingfoilscout-Ordner — persönlich und nie
versioniert (.gitignore, tools/persoenliche_daten.py); Dateien nur für den
Besitzer lesbar (0600, spotedit.schreibe_atomar).
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import plistlib
import re
import secrets
import socket
import ssl
import uuid
from datetime import date, timedelta
from pathlib import Path

from . import ROOT
from . import zertifikat as zert
from .i18n import T

ORDNER = ROOT / "handy"
ZUGANG = "zugang.json"
META = "zertifikat.json"
ZUSTAND = "zustand.json"          # was sich gezeigt hat (seit 2.5.1), siehe zustand()
CA = "wingfoilscout-ca.crt"
SERVER_CRT = "server.crt"
SERVER_KEY = "server.key"
PROFIL = "Wingfoilscout-iPhone.mobileconfig"
# Apple: Serverzertifikate höchstens 825 Tage (iOS 13, „Requirements for
# trusted certificates“) — ein paar Tage Luft für eine falsch gehende Uhr.
TAGE_SERVER = 820
TAGE_CA = 825
SCHLUESSEL_MUSTER = re.compile(r"[A-Za-z0-9_-]{16,64}")
NAME_MUSTER = re.compile(r"[A-Za-z0-9-]{1,63}\.local")
KENNUNG_MUSTER = re.compile(r"[0-9a-f]{16}")
BUNDLE = "io.github.darkpiratego.wingfoilscout"

# Wo macOS den Bonjour-Namen ablegt (System → Network → HostNames →
# LocalHostName) — dieselbe Datei, aus der `scutil --get LocalHostName` liest.
SYSTEMKONFIGURATION = Path("/Library/Preferences/SystemConfiguration/preferences.plist")


class HandyFehler(Exception):
    """Ein Satz für die Oberfläche: was nicht ging und was zu tun ist."""


def ordner(pfad: Path | str | None = None) -> Path:
    return Path(pfad) if pfad else ORDNER


def _schreiben(datei: Path, text: str) -> None:
    from .spotedit import schreibe_atomar
    datei.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    schreibe_atomar(datei, text)


# ── Zugangsschlüssel ─────────────────────────────────────────────────────────

def schluessel(pfad: Path | str | None = None) -> str:
    """Der Zugangsschlüssel fürs WLAN — beim ersten Mal erzeugt, danach derselbe."""
    try:
        daten = json.loads((ordner(pfad) / ZUGANG).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        daten = None
    wert = daten.get("schluessel") if isinstance(daten, dict) else None
    if isinstance(wert, str) and SCHLUESSEL_MUSTER.fullmatch(wert):
        return wert
    return neuer_schluessel(pfad)


def neuer_schluessel(pfad: Path | str | None = None) -> str:
    """Ein neuer Schlüssel: jedes Handy muss danach den Code neu scannen."""
    wert = secrets.token_urlsafe(12)                     # 16 Zeichen, 96 Bit
    _schreiben(ordner(pfad) / ZUGANG, json.dumps({"schluessel": wert}, indent=1) + "\n")
    return wert


# ── Adressen ─────────────────────────────────────────────────────────────────

def adressen() -> list[str]:
    """Die IPv4-Adressen dieses Rechners im lokalen Netz — die, über die der
    Mac ins Netz geht (meist das WLAN), zuerst. Der UDP-„Verbindungsaufbau“ zu
    einer Testadresse schickt kein Paket; er fragt nur, über welche eigene
    Adresse es dorthin ginge."""
    erste, weitere = None, set()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))                      # TEST-NET-1, nie erreichbar
        erste = s.getsockname()[0]
    except OSError:
        pass
    finally:
        s.close()
    try:
        for eintrag in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            weitere.add(eintrag[4][0])
    except OSError:
        pass
    alle = ([erste] if erste else []) + sorted(weitere - {erste})
    return [a for a in alle if a and not a.startswith("127.") and not a.startswith("0.")]


def bonjour_name(quelle: Path | str | None = None) -> str | None:
    """Der Name des Macs im lokalen Netz („Mein-Mac.local“) — das iPhone
    findet ihn über Bonjour, auch wenn sich die Adresse ändert. Gelesen aus
    den Systemeinstellungen (für alle lesbar; Wingfoilscout startet dafür kein
    Programm), sonst der Rechnername, wenn er auf .local endet — sonst None:
    Dann deckt das Zertifikat nur die Adressen ab."""
    try:
        with open(quelle or SYSTEMKONFIGURATION, "rb") as f:
            daten = plistlib.load(f)
        name = daten["System"]["Network"]["HostNames"]["LocalHostName"] + ".local"
    except Exception:        # fehlt, nicht lesbar, kaputt, anders gebaut: alles dasselbe
        name = ""
    if NAME_MUSTER.fullmatch(name):
        return name
    rechner = socket.gethostname()
    return rechner if NAME_MUSTER.fullmatch(rechner) else None


# ── Zertifikat ───────────────────────────────────────────────────────────────

def zertifikat(pfad: Path | str | None = None) -> dict | None:
    """Was das Zertifikat abdeckt: {"ips", "namen", "bis", "erstellt",
    "abgelaufen"} — seit 2.5.1 auch `kennung` (die ersten 16 Zeichen des
    SHA-256 über das Zertifikat der Zertifizierungsstelle: ändert sich mit
    jedem neu erzeugten, denn das iPhone braucht dann ein neues Profil) und
    `zeit` (wann es erzeugt wurde). None, wenn keines da ist oder es sich
    nicht laden lässt."""
    d = ordner(pfad)
    try:
        meta = json.loads((d / META).read_text(encoding="utf-8"))
        zeit = (d / META).stat().st_mtime
        kennung = hashlib.sha256(ssl.PEM_cert_to_DER_cert((d / CA).read_text(encoding="ascii"))).hexdigest()[:16]
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(meta, dict) or tls_kontext(pfad) is None:
        return None
    ips = [a for a in meta.get("ips") or [] if isinstance(a, str)]
    namen = [n for n in meta.get("namen") or [] if isinstance(n, str) and NAME_MUSTER.fullmatch(n)]
    bis = meta.get("bis") if isinstance(meta.get("bis"), str) else ""
    return {"ips": ips, "namen": namen, "bis": bis, "erstellt": str(meta.get("erstellt") or ""),
            "abgelaufen": bool(bis) and bis < date.today().isoformat(), "kennung": kennung, "zeit": zeit}


def tls_kontext(pfad: Path | str | None = None) -> ssl.SSLContext | None:
    """Der TLS-Kontext für den Server — None ohne (brauchbares) Zertifikat."""
    d = ordner(pfad)
    crt, key = d / SERVER_CRT, d / SERVER_KEY
    if not (crt.is_file() and key.is_file()):
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    except (AttributeError, ValueError):     # Apples Python 3.9 mit LibreSSL kennt das womöglich nicht
        pass
    try:
        ctx.load_cert_chain(str(crt), str(key))
    except (OSError, ssl.SSLError, ValueError):
        return None
    return ctx


def zertifikat_erzeugen(ips: list[str], name: str | None, pfad: Path | str | None = None) -> dict:
    """Eine Zertifizierungsstelle nur für diesen Mac, ein Serverzertifikat für
    `ips` und `name` — und das Profil fürs iPhone. Den Schlüssel der
    Zertifizierungsstelle gibt es nur, solange diese Funktion läuft: Er
    unterschreibt das Serverzertifikat und wird nirgends gespeichert. Ersetzt
    ein vorhandenes Zertifikat (das alte Profil auf dem iPhone ist dann
    nutzlos und kann weg)."""
    ips = [a for a in ips if _ist_ipv4(a)]
    if name is not None and not NAME_MUSTER.fullmatch(name):
        name = None
    if not ips and not name:
        raise HandyFehler(T("Keine Adresse im WLAN gefunden — ist der Mac im WLAN?"))
    heute = date.today()
    ca_name = ("Wingfoilscout", f"Wingfoilscout {heute.isoformat()}")
    server_schluessel = zert.rsa_schluessel()
    ca_der, server_der = _ausstellen(ca_name, server_schluessel, ips, [name] if name else [])
    d = ordner(pfad)
    _schreiben(d / SERVER_KEY, zert.pem(zert.privat_pkcs8(server_schluessel), "PRIVATE KEY"))
    _schreiben(d / SERVER_CRT, zert.pem(server_der, "CERTIFICATE"))
    _schreiben(d / CA, zert.pem(ca_der, "CERTIFICATE"))
    _schreiben(d / PROFIL, profil(ca_der).decode("utf-8"))
    meta = {"ips": ips, "namen": [name] if name else [], "erstellt": heute.isoformat(),
            "bis": (heute + timedelta(days=TAGE_SERVER)).isoformat()}
    _schreiben(d / META, json.dumps(meta, indent=1) + "\n")
    if tls_kontext(pfad) is None:
        raise HandyFehler(T("Das neue Zertifikat lässt sich nicht laden."))
    return zertifikat(pfad) or meta


def _ausstellen(ca_name: tuple[str, str], server_schluessel: dict, ips: list[str],
                namen: list[str]) -> tuple[bytes, bytes]:
    """Zertifizierungsstelle und Serverzertifikat. Eine eigene Funktion, damit
    der Schlüssel der Zertifizierungsstelle mit ihr endet — er verlässt sie
    nicht."""
    ca_schluessel = zert.rsa_schluessel()
    ca_der = zert.zertifikat(ca_schluessel, ca_schluessel, ca_name, ca_name, TAGE_CA, ca=True)
    server_der = zert.zertifikat(server_schluessel, ca_schluessel, ca_name, ("Wingfoilscout", "Wingfoilscout"),
                                 TAGE_SERVER, ca=False, ips=ips, dns=namen)
    return ca_der, server_der


def profil(ca_der: bytes) -> bytes:
    """Das Profil fürs iPhone: das Zertifikat der Zertifizierungsstelle als
    „Root“-Nutzlast (com.apple.security.root). Unsigniert — das iPhone zeigt
    beim Installieren „Nicht überprüft“; das ist bei einem selbst erzeugten
    Profil richtig so."""
    zertifikat_nutzlast = {
        "PayloadCertificateFileName": "wingfoilscout-ca.cer",
        "PayloadContent": ca_der,
        "PayloadDescription": T("Das Zertifikat deines Macs für Wingfoilscout im Heimnetz."),
        "PayloadDisplayName": "Wingfoilscout",
        "PayloadIdentifier": f"{BUNDLE}.zertifikat.{uuid.uuid4().hex}",
        "PayloadType": "com.apple.security.root",
        "PayloadUUID": str(uuid.uuid4()).upper(),
        "PayloadVersion": 1,
    }
    return plistlib.dumps({
        "PayloadContent": [zertifikat_nutzlast],
        "PayloadDescription": T("Damit dein iPhone Wingfoilscout auf deinem Mac verschlüsselt öffnet. Danach: "
                                "Einstellungen → Allgemein → Info → Zertifikatsvertrauenseinstellungen → "
                                "Wingfoilscout einschalten."),
        "PayloadDisplayName": T("Wingfoilscout im Heimnetz"),
        "PayloadIdentifier": f"{BUNDLE}.profil.{uuid.uuid4().hex}",
        "PayloadOrganization": "Wingfoilscout",
        "PayloadRemovalDisallowed": False,
        "PayloadType": "Configuration",
        "PayloadUUID": str(uuid.uuid4()).upper(),
        "PayloadVersion": 1,
    }, fmt=plistlib.FMT_XML)


def _ist_ipv4(text: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(text), ipaddress.IPv4Address)
    except ValueError:
        return False


# ── Was sich gezeigt hat (seit 2.5.1) ────────────────────────────────────────

def zustand(pfad: Path | str | None = None) -> dict:
    """Was sich der Mac fürs Handy merkt — nur, was sich gezeigt hat, nie
    bloß eine Wahl im Reiter:

    - `bewaehrt`: "https" oder "http" — auf diesem Weg ist ein iPhone schon
      durchgekommen; dazu `zeit` (wann zuletzt festgehalten) und bei https
      `kennung`, das Zertifikat, dem es vertraut hat. Danach öffnet der Reiter
      gleich mit dem QR-Code — solange dieser Weg noch gehen kann (siehe
      webui.handy_ansicht).
    - `profil`: die Kennung des Zertifikats, dessen Profil am Mac geladen wurde.
    """
    try:
        daten = json.loads((ordner(pfad) / ZUSTAND).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return {}
    if not isinstance(daten, dict):
        return {}
    aus: dict = {}
    if daten.get("bewaehrt") in ("https", "http"):
        aus["bewaehrt"] = daten["bewaehrt"]
        zeit = daten.get("zeit")
        aus["zeit"] = float(zeit) if isinstance(zeit, (int, float)) and not isinstance(zeit, bool) else 0.0
        if isinstance(daten.get("kennung"), str) and KENNUNG_MUSTER.fullmatch(daten["kennung"]):
            aus["kennung"] = daten["kennung"]
    if isinstance(daten.get("profil"), str) and KENNUNG_MUSTER.fullmatch(daten["profil"]):
        aus["profil"] = daten["profil"]
    return aus


def merken(pfad: Path | str | None = None, **werte) -> dict:
    """Einträge in zustand.json setzen — None nimmt einen heraus. Geschrieben
    wird nur, wenn sich etwas ändert."""
    alt = zustand(pfad)
    neu = dict(alt)
    for name, wert in werte.items():
        if wert is None:
            neu.pop(name, None)
        else:
            neu[name] = wert
    if neu != alt:
        _schreiben(ordner(pfad) / ZUSTAND, json.dumps(neu, indent=1, sort_keys=True) + "\n")
    return neu


# ── Die Adresse fürs iPhone ──────────────────────────────────────────────────

def startadressen(adressen_jetzt: list[str], port: int, schluessel_wert: str,
                  meta: dict | None) -> dict:
    """{"https": …, "http": …, "ueber": "ip"|"name"|""}: die Adresse für den
    QR-Code. https, wenn das Zertifikat eine Adresse von jetzt abdeckt — oder,
    hat sich die Adresse geändert, den Bonjour-Namen; sonst leer. http geht
    immer über die erste Adresse (Weg ohne Zertifikat)."""
    aus = {"https": "", "http": "", "ueber": ""}
    if adressen_jetzt:
        aus["http"] = f"http://{adressen_jetzt[0]}:{port}/?k={schluessel_wert}"
    if meta and not meta.get("abgelaufen"):
        for a in adressen_jetzt:
            if a in meta.get("ips", []):
                aus.update(https=f"https://{a}:{port}/?k={schluessel_wert}", ueber="ip")
                return aus
        for n in meta.get("namen", []):
            aus.update(https=f"https://{n}:{port}/?k={schluessel_wert}", ueber="name")
            return aus
    return aus
