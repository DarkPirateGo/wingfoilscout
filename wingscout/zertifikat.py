"""Zertifikate ohne openssl und ohne Zusatzpaket (seit 2.5.0, für handy.py).

Wingfoilscout startet keine anderen Programme (SECURITY.md), und seine
einzige Abhängigkeit ist PyYAML. Für den verschlüsselten Weg aufs iPhone
braucht es aber eine kleine Zertifizierungsstelle und ein Serverzertifikat.
Also hier, mit dem, was Python mitbringt: RSA-Schlüssel (2048 Bit, Primzahlen nach Miller-Rabin mit
Zufallsbasen aus `secrets`), X.509 v3 in DER, Signatur RSASSA-PKCS1-v1_5 mit
SHA-256 (RFC 8017, RFC 5280). Geprüft wird es in tests/test_handy.py mit einem
echten TLS-Handshake über Pythons ssl-Modul (OpenSSL) und — wo vorhanden —
mit `openssl verify`.

Was die Zertifikate tragen, folgt Apples Vorgaben für TLS-Serverzertifikate
(„Requirements for trusted certificates in iOS 13 and macOS 10.15“): RSA mit
mindestens 2048 Bit, SHA-256, die Namen im SubjectAltName (nicht im CN),
ExtendedKeyUsage serverAuth, höchstens 825 Tage gültig.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import math
import secrets
from datetime import datetime, timedelta, timezone

E = 65537
_KLEINE = [p for p in range(3, 2000) if all(p % q for q in range(2, int(p ** 0.5) + 1))]

# OIDs (RFC 5280, RFC 8017)
_RSA = "1.2.840.113549.1.1.1"
_SHA256_RSA = "1.2.840.113549.1.1.11"
_O, _CN = "2.5.4.10", "2.5.4.3"
_BASIC, _KEYUSAGE, _EKU, _SAN = "2.5.29.19", "2.5.29.15", "2.5.29.37", "2.5.29.17"
_SKI, _AKI = "2.5.29.14", "2.5.29.35"
_SERVERAUTH = "1.3.6.1.5.5.7.3.1"
# DigestInfo-Präfix für SHA-256 (RFC 8017, 9.2, Anmerkung 1)
_DIGESTINFO_SHA256 = bytes.fromhex("3031300d060960864801650304020105000420")


# ── RSA ──────────────────────────────────────────────────────────────────────

def _wahrscheinlich_prim(n: int, runden: int = 40) -> bool:
    """Miller-Rabin mit zufälligen Basen: eine zusammengesetzte Zahl
    besteht eine Runde mit höchstens 1/4 Wahrscheinlichkeit."""
    if n < 3 or n % 2 == 0:
        return n == 2
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for _ in range(runden):
        a = 2 + secrets.randbelow(n - 3)
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _primzahl(bits: int) -> int:
    while True:
        # die beiden obersten Bits gesetzt: p·q hat dann sicher die volle Länge
        k = secrets.randbits(bits) | (3 << (bits - 2)) | 1
        if any(k % p == 0 for p in _KLEINE):
            continue
        if math.gcd(k - 1, E) == 1 and _wahrscheinlich_prim(k):
            return k


def rsa_schluessel(bits: int = 2048) -> dict:
    """Ein RSA-Schlüsselpaar: n, e, d und die Teile für den Chinesischen
    Restsatz, wie PKCS #1 sie ablegt."""
    while True:
        p, q = _primzahl(bits // 2), _primzahl(bits // 2)
        n = p * q
        if p != q and n.bit_length() == bits:
            break
    d = pow(E, -1, (p - 1) * (q - 1))
    return {"n": n, "e": E, "d": d, "p": p, "q": q, "dp": d % (p - 1), "dq": d % (q - 1), "qinv": pow(q, -1, p)}


def _signieren(daten: bytes, schluessel: dict) -> bytes:
    """RSASSA-PKCS1-v1_5 mit SHA-256."""
    k = (schluessel["n"].bit_length() + 7) // 8
    t = _DIGESTINFO_SHA256 + hashlib.sha256(daten).digest()
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    s = pow(int.from_bytes(em, "big"), schluessel["d"], schluessel["n"])
    return s.to_bytes(k, "big")


# ── DER ──────────────────────────────────────────────────────────────────────

def _laenge(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    roh = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(roh)]) + roh


def _tlv(tag: int, inhalt: bytes) -> bytes:
    return bytes([tag]) + _laenge(len(inhalt)) + inhalt


def _int(n: int) -> bytes:
    roh = n.to_bytes(max(1, (n.bit_length() + 8) // 8), "big")      # vorne 0x00, wenn das oberste Bit gesetzt ist
    return _tlv(0x02, roh)


def _seq(*teile: bytes) -> bytes:
    return _tlv(0x30, b"".join(teile))


def _set(*teile: bytes) -> bytes:
    return _tlv(0x31, b"".join(teile))


def _oid(punktiert: str) -> bytes:
    zahlen = [int(x) for x in punktiert.split(".")]
    aus = bytearray([40 * zahlen[0] + zahlen[1]])
    for z in zahlen[2:]:
        teile = [z & 0x7F]
        z >>= 7
        while z:
            teile.append(0x80 | (z & 0x7F))
            z >>= 7
        aus.extend(reversed(teile))
    return _tlv(0x06, bytes(aus))


def _bits(roh: bytes, ungenutzt: int = 0) -> bytes:
    return _tlv(0x03, bytes([ungenutzt]) + roh)


def _octets(roh: bytes) -> bytes:
    return _tlv(0x04, roh)


def _utf8(text: str) -> bytes:
    return _tlv(0x0C, text.encode("utf-8"))


def _zeit(zeitpunkt: datetime) -> bytes:
    """UTCTime bis 2049, danach GeneralizedTime (RFC 5280, 4.1.2.5)."""
    if zeitpunkt.year < 2050:
        return _tlv(0x17, zeitpunkt.strftime("%y%m%d%H%M%SZ").encode("ascii"))
    return _tlv(0x18, zeitpunkt.strftime("%Y%m%d%H%M%SZ").encode("ascii"))


def _name(organisation: str, name: str) -> bytes:
    return _seq(_set(_seq(_oid(_O), _utf8(organisation))), _set(_seq(_oid(_CN), _utf8(name))))


def _erweiterung(oid: str, wert: bytes, kritisch: bool = False) -> bytes:
    return _seq(_oid(oid), *([_tlv(0x01, b"\xff")] if kritisch else []), _octets(wert))


def _oeffentlich(schluessel: dict) -> bytes:
    """SubjectPublicKeyInfo mit dem RSAPublicKey (RFC 8017, A.1.1)."""
    return _seq(_seq(_oid(_RSA), b"\x05\x00"), _bits(_seq(_int(schluessel["n"]), _int(schluessel["e"]))))


def _kennung(schluessel: dict) -> bytes:
    """Schlüsselkennung nach RFC 5280, 4.2.1.2 (1): SHA-1 über den RSAPublicKey."""
    return hashlib.sha1(_seq(_int(schluessel["n"]), _int(schluessel["e"])), usedforsecurity=False).digest()


def zertifikat(antragsteller: dict, aussteller: dict, aussteller_name: tuple[str, str],
               name: tuple[str, str], tage: int, ca: bool, ips=(), dns=()) -> bytes:
    """Ein X.509-v3-Zertifikat (DER) für `antragsteller` (öffentlicher Teil),
    signiert mit `aussteller` (privater Teil). `ca`: Zertifizierungsstelle
    (darf nur Zertifikate unterschreiben) — sonst Serverzertifikat für `ips`
    und `dns`."""
    jetzt = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=5)   # Uhren gehen nicht gleich
    if ca:
        erweiterungen = [
            _erweiterung(_BASIC, _seq(_tlv(0x01, b"\xff"), _int(0)), kritisch=True),   # CA, keine Zwischenstellen
            _erweiterung(_KEYUSAGE, _bits(bytes([0b00000110]), 1), kritisch=True),     # keyCertSign, cRLSign
            _erweiterung(_SKI, _octets(_kennung(antragsteller))),
        ]
    else:
        namen = [_tlv(0x87, ipaddress.ip_address(a).packed) for a in ips]               # [7] iPAddress
        namen += [_tlv(0x82, d.encode("ascii")) for d in dns]                           # [2] dNSName
        erweiterungen = [
            _erweiterung(_BASIC, _seq(), kritisch=True),                                # keine CA
            _erweiterung(_KEYUSAGE, _bits(bytes([0b10100000]), 5), kritisch=True),      # digitalSignature, keyEncipherment
            _erweiterung(_EKU, _seq(_oid(_SERVERAUTH))),
            _erweiterung(_SAN, _seq(*namen)),
            _erweiterung(_SKI, _octets(_kennung(antragsteller))),
            _erweiterung(_AKI, _seq(_tlv(0x80, _kennung(aussteller)))),
        ]
    algorithmus = _seq(_oid(_SHA256_RSA), b"\x05\x00")
    tbs = _seq(
        _tlv(0xA0, _int(2)),                                    # Version 3
        _int(secrets.randbits(63) + 1),                         # Seriennummer, zufällig und positiv
        algorithmus,
        _name(*aussteller_name),
        _seq(_zeit(jetzt), _zeit(jetzt + timedelta(days=tage))),
        _name(*name),
        _oeffentlich(antragsteller),
        _tlv(0xA3, _seq(*erweiterungen)),
    )
    return _seq(tbs, algorithmus, _bits(_signieren(tbs, aussteller)))


def privat_der(schluessel: dict) -> bytes:
    """RSAPrivateKey nach PKCS #1 (RFC 8017, A.1.2)."""
    return _seq(*(_int(schluessel[k]) if k else _int(0)
                  for k in (None, "n", "e", "d", "p", "q", "dp", "dq", "qinv")))


def privat_pkcs8(schluessel: dict) -> bytes:
    """Derselbe Schlüssel als PrivateKeyInfo (PKCS #8, RFC 5208) — „PRIVATE
    KEY“ im PEM, das Format, das jede TLS-Bibliothek liest."""
    return _seq(_int(0), _seq(_oid(_RSA), b"\x05\x00"), _octets(privat_der(schluessel)))


def pem(der: bytes, art: str) -> str:
    text = base64.b64encode(der).decode("ascii")
    zeilen = "\n".join(text[i:i + 64] for i in range(0, len(text), 64))
    return f"-----BEGIN {art}-----\n{zeilen}\n-----END {art}-----\n"
