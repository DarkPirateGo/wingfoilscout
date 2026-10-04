"""Gemeinsames für alle Netzaufrufe: wohin, wie viel, wie lange — und wie gemerkt.

Ein `read` ohne Grenze liest, bis der Server aufhört — und ob er das tut,
entscheidet der Server. Overpass hatte die Grenze schon (300 MB, weil dort
große Antworten normal sind); die anderen Quellen antworten mit Kilobytes,
höchstens ein paar Megabyte. Alles darüber ist ein Fehler, kein Datensatz.

Seit 2.1.1 (Review 04.10.2026) gilt außerdem:

  · Wohin: `https://` überallhin, `http://` nur zum eigenen Rechner
    (127.0.0.1, localhost — die Tests, die Oberfläche selbst). `file:`,
    `ftp:` und `data:` öffnet `urllib` sonst ebenso bereitwillig; eine
    Adresse aus einer fremden Antwort hätte damit eine Datei der Platte
    lesen lassen (C7). Weiterleitungen gehen nur auf `https://` — und auf den
    eigenen Rechner nur, wenn die Anfrage schon dort war (C8).
  · Wie lange: das Zeitlimit von `urlopen` gilt je Lesevorgang. Ein Server,
    der alle 40 Sekunden ein Byte schickt, hielte eine Abfrage stundenlang
    offen; `lies` setzt deshalb eine Frist für den ganzen Körper (C9).
  · Wie viel: gelesen wird in Stücken von 64 KB. `resp.read(limit + 1)`
    legte unter Python 3.9 vor dem ersten Byte einen Puffer in voller
    Grenzgröße an — 64 MB je Abfrage, 300 MB bei Overpass (C11).
  · Wie gemerkt: `ablegen` schreibt atomar, `cache_lesen` nimmt eine kaputte
    Datei als fehlend. Ein halb geschriebener Zwischenspeicher hielt einen
    Dienst sonst still und dauerhaft für leer (C14).
"""
from __future__ import annotations
import contextlib
import http.client
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .. import __version__
from ..i18n import T, TN, N_                                      # noqa: F401

MAX_ANTWORT = 64 * 1024 * 1024
FRIST_S = 180.0                 # so lange darf ein Antwortkörper höchstens dauern
STUECK = 64 * 1024
LOKAL = ("127.0.0.1", "localhost")
# Ein Absender, der sich zu erkennen gibt — Overpass und Nominatim verlangen
# das in ihren Nutzungsregeln, und alle anderen sollen dieselbe Auskunft
# bekommen. Park4Night bleibt bei seiner eigenen Kennung (siehe dort).
USER_AGENT = f"Wingfoilscout/{__version__} (+https://github.com/DarkPirateGo/wingfoilscout)"


def _teile(url):
    try:
        return urllib.parse.urlsplit(str(url))
    except ValueError:                                  # z. B. „http://[::1“
        return None


def lokal(url) -> bool:
    """Zeigt die Adresse auf den eigenen Rechner? Verglichen wird der Host,
    nicht der Anfang des Texts: `http://127.0.0.1.evil.example` ist fremd."""
    teile = _teile(url)
    return bool(teile) and (teile.hostname or "").lower() in LOKAL


def erlaubt(url) -> bool:
    """`https://` mit Host — oder `http://` zum eigenen Rechner. Sonst nichts."""
    teile = _teile(url)
    if not teile or not teile.hostname:
        return False
    schema = teile.scheme.lower()
    return schema == "https" or (schema == "http" and teile.hostname.lower() in LOKAL)


def _kurz(url) -> str:
    """Schema und Host — der Rest (Pfad, Anfrage) gehört nicht ins Protokoll."""
    teile = _teile(url)
    if not teile:
        return "?"
    return f"{teile.scheme}://{teile.hostname or ''}" if teile.scheme else str(url)[:40]


def _abgelehnt(url) -> urllib.error.URLError:
    return urllib.error.URLError(T("Adresse abgelehnt — erlaubt ist nur https:// ({adresse})", adresse=_kurz(url)))


def nur_https(url) -> None:
    """Wirft (URLError, also OSError), wenn die Adresse nicht `erlaubt` ist —
    für Adressen aus fremden Antworten, vor dem Aufruf und nicht erst im
    Opener, der das ebenso ablehnt."""
    if not erlaubt(url):
        raise _abgelehnt(url)


class _NurHttps(urllib.request.HTTPRedirectHandler):
    """Weiterleitungen nur auf `https://` — und auf den eigenen Rechner nur,
    wenn die Anfrage schon dorthin ging (Tests, die Oberfläche selbst). Jeder
    Dienst wird über HTTPS angesprochen; ein kompromittierter Endpunkt könnte
    sonst auf Klartext umleiten, und `urllib` folgte bis 1.18.3 jeder
    `Location` (Review 25.09., S13). Bis 2.1.0 prüfte die Regel den Anfang
    des Texts: `http://localhost.evil.example` ging durch, und jeder fremde
    Dienst durfte auf jeden Port des eigenen Rechners umleiten (C8)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not erlaubt(newurl):
            raise urllib.error.HTTPError(newurl, code, T("Weiterleitung auf eine unverschlüsselte Adresse abgelehnt"),
                                         headers, fp)
        if lokal(newurl) and not lokal(req.full_url):
            raise urllib.error.HTTPError(newurl, code, T("Weiterleitung auf den eigenen Rechner abgelehnt"),
                                         headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _NurLokalesHttp(urllib.request.HTTPHandler):
    """Klartext nur zum eigenen Rechner."""

    def http_open(self, req):
        if not lokal(req.full_url):
            raise _abgelehnt(req.full_url)
        return super().http_open(req)


class _KeineDatei(urllib.request.FileHandler):
    def file_open(self, req):
        raise _abgelehnt(req.full_url)


class _KeinFtp(urllib.request.FTPHandler):
    def ftp_open(self, req):
        raise _abgelehnt(req.full_url)


class _KeineDaten(urllib.request.DataHandler):
    def data_open(self, req):
        raise _abgelehnt(req.full_url)


urllib.request.install_opener(urllib.request.build_opener(_NurHttps, _NurLokalesHttp, _KeineDatei, _KeinFtp,
                                                          _KeineDaten))


def _rest(resp) -> int | None:
    """Wie viele Bytes der Körper laut Kopf (noch) hat — `HTTPResponse.length`,
    None, wenn es keiner sagt (chunked, oder ein Ersatzobjekt im Test)."""
    n = getattr(resp, "length", None)
    return n if isinstance(n, int) and not isinstance(n, bool) and n >= 0 else None


def lies(resp, limit: int = MAX_ANTWORT, frist_s: float | None = FRIST_S) -> bytes:
    """Antwortkörper lesen, aber nie mehr als `limit` Bytes und nie länger als
    `frist_s` Sekunden (None: ohne Frist).

    Zu groß ist ein ValueError wie bisher — schon bevor gelesen wird, wenn
    `Content-Length` es ankündigt. Zu langsam ist ein TimeoutError, ein
    abgerissener Körper ein ConnectionError; beide sind OSError, also das,
    was jede Quelle schon als Netzfehler behandelt. Ein abgerissener Körper
    galt bis 2.1.0 als vollständig und landete so im Zwischenspeicher.

    Gelesen wird mit `read1`: ein Systemaufruf je Stück, damit die Frist
    zwischen den Stücken greift. Ein Objekt ohne `read1` (Ersatz im Test)
    wird mit `read` gelesen; dort heißt ein kürzeres Stück: Ende.
    """
    def zu_gross():
        return ValueError(T("Antwort größer als {mb} MB", mb=limit // (1024 * 1024)))

    angekuendigt = _rest(resp)
    if angekuendigt is not None and angekuendigt > limit:
        raise zu_gross()
    ende = time.monotonic() + frist_s if frist_s else None
    stueckweise = getattr(resp, "read1", None)
    teile: list[bytes] = []
    n = 0
    try:
        while True:
            wunsch = min(STUECK, limit + 1 - n)
            stueck = stueckweise(wunsch) if callable(stueckweise) else resp.read(wunsch)
            if not stueck:
                break
            n += len(stueck)
            if n > limit:
                raise zu_gross()
            teile.append(stueck)
            if not callable(stueckweise) and len(stueck) < wunsch:
                break
            if ende is not None and time.monotonic() > ende:
                raise TimeoutError(T("Antwort nach {s} s noch nicht vollständig", s=f"{frist_s:.0f}"))
    except http.client.HTTPException as exc:            # IncompleteRead, LineTooLong …
        raise ConnectionError(T("Antwort unvollständig ({fehler})", fehler=type(exc).__name__)) from exc
    if callable(stueckweise) and _rest(resp):
        raise ConnectionError(T("Antwort unvollständig ({fehler})", fehler=f"{n} / {n + _rest(resp)} B"))
    return b"".join(teile)


# ── Zwischenspeicher ─────────────────────────────────────────────────────────

def cache_lesen(pfad, art: type | tuple | None = None):
    """Eine gemerkte JSON-Antwort — oder None, wenn die Datei fehlt, nicht
    lesbar ist (abgeschnitten, kaputt, zu tief verschachtelt) oder nicht die
    erwartete Art hat. None heißt für den Aufrufer: neu holen."""
    try:
        daten = json.loads(Path(pfad).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    if art is not None and not isinstance(daten, art):
        return None
    return daten


@contextlib.contextmanager
def ablegen_offen(pfad):
    """Atomar schreiben: eine Nachbardatei mit eigenem Namen zum Hineinschreiben
    (binär); erst wenn der Block ohne Fehler endet, wird sie umbenannt. Wer
    liest, sieht die alte Fassung oder die neue, nie eine halbe — auch nicht
    nach einem Absturz mitten im Schreiben."""
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(pfad.parent), prefix=f".{pfad.name}.", suffix=".neu")
    try:
        with os.fdopen(fd, "wb") as fh:
            yield fh
        os.replace(tmp, pfad)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def ablegen(pfad, inhalt: str | bytes) -> None:
    """Text (UTF-8) oder Bytes atomar ablegen — siehe `ablegen_offen`."""
    with ablegen_offen(pfad) as fh:
        fh.write(inhalt.encode("utf-8") if isinstance(inhalt, str) else inhalt)
