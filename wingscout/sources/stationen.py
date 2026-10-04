"""Gemessener Wind von Wetterstationen — für Prüfstand und Rückblick.

Sechs Dienste, alle frei, alle ohne Schlüssel, alle mit Stundenmitteln — dazu
Windguru-Stationen, für die man das Passwort hat:

  DWD (Deutschland)   opendata.dwd.de, CDC-Stundenwerte Wind, „recent“ (die
                      letzten rund 500 Tage). Je Station ein ZIP mit einer
                      Textdatei: STATIONS_ID;MESS_DATUM;QN_3;F;D — F in m/s,
                      D in Grad, -999 fehlt, Zeit in UTC. Die Sonde vom
                      19.09., 08 UTC: reicht bis zum 17., also bis
                      vorgestern. Dazu die Zehnminutenwerte FF_10/DD_10
                      (hier zu Stundenmitteln gerechnet): „10_minutes/wind/
                      recent“ für die Tage dazwischen (laut Beschreibung
                      täglich, am 19.09. aber vom 13.) und „…/now“ für den
                      laufenden UTC-Tag, stündlich frisch.
  KNMI (Niederlande)  daggegevens.knmi.nl/klimatologie/uurgegevens, das alte
                      Skript-Formular: Stunde 1–24 (Stunde HH endet um HH UTC),
                      FH = Stundenmittel in 0,1 m/s, DD in Grad (990 = drehend).
                      Reicht bis vorgestern (Sonde vom 19.09.); für die
                      letzten Tage antwortet der Dienst mit Kopf ohne Zeilen.
  GeoSphere (Österreich) dataset.api.hub.geosphere.at, Datensatz klima-v2-1h:
                      ff in m/s, dd in Grad, Zeitstempel UTC, JSON. Für die
                      letzten Stunden dazu „tawes-v1-10min“, die Zehnminuten-
                      werte der TAWES-Stationen, hier zu Stunden gemittelt —
                      zusammen bis zur aktuellen Stunde (Sonde vom 19.09.).
  Météo-France (Frankreich) meteo.data.gouv.fr, „Données climatologiques de
                      base – horaires“: je Département eine csv.gz mit allen
                      Stationen und Stunden der letzten zwei Jahre (FF in m/s,
                      DD in Grad, Zeit UTC), einmal am Tag morgens geschrieben
                      mit den Stunden bis kurz davor (Sonde vom 19.09.: Datei
                      von 05:45 UTC, Werte bis 03:00 UTC). Die Datei eines
                      Départements ist 5 bis 15 MB groß; welche gebraucht
                      wird, sagt eine grobe Rahmentabelle.
  Rijkswaterstaat (Niederlande) ddapi20-waterwebservices.rijkswaterstaat.nl,
                      die Zehnminutenwerte der Messpfähle und Küstenstationen
                      (Wind auf dem Wasser), JSON per POST, nahe Echtzeit —
                      am 20.09.2026 gegen den Dienst geprüft, siehe unten.
  DMI (Dänemark)      opendataapi.dmi.dk/v2/metObs, Zehnminutenwerte der
                      Stationen als GeoJSON, ohne Schlüssel, bis zur aktuellen
                      Stunde — seit 1.14.0, am 20.09.2026 geprüft.
  Windguru            wgsapi.php, nur mit dem API-Passwort der Station —
                      die Stationen stehen in der persönlichen config.yaml.

Alle liefern das Stundenmittel des Windes in rund 10 m Höhe über der Station
— die Landdienste nicht über dem Wasser. Eine Küstenstation misst in der
Regel weniger als draußen am Spot; deshalb vergleicht der Prüfstand Läufe
gegeneinander (gegen eine gemerkte Grundlinie), nicht gegen eine absolute
Wahrheit. Die Stationslisten der landesweiten Dienste gelten für jeden Spot,
auch über die Grenze (`paare_finden`): ein belgischer Spot bekommt die
nächste niederländische Station, ein dänischer die deutsche.

Rückgabe überall gleich:
    {"quelle": "DWD", "station": {"id", "name", "lat", "lon"},
     "stunden": {"2026-08-01T13:00": {"kn": 12.3, "dir": 250.0}, …}}   # UTC

Was hier steht, wurde im September 2026 nach den veröffentlichten
Beschreibungen gebaut; DWD, KNMI, GeoSphere und Météo-France hat die Sonde vom
19./20.09. bestätigt, Rijkswaterstaat ist am 20.09. im Browser gegen den
Dienst geprüft. `tools/pruefstand.py --sonde` fragt jeden Dienst einmal an und
zeigt, was er wirklich antwortet.
"""
from __future__ import annotations
import csv
import io
import json
import re
import math
import urllib.parse
import urllib.request
import zipfile
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import CACHE
from ..geo import haversine_km
from ..i18n import T, TN, N_                                      # noqa: F401
from .netz import lies, cache_lesen, ablegen, nur_https, USER_AGENT
import gzip

CACHE_DIR = CACHE / "pruefstand"
TIMEOUT = 60
FRIST_S = 600            # ein ganzer Download (Météo-France: bis 15 MB) — auch über eine langsame Leitung
MS_ZU_KN = 1.0 / 0.514444
# Mehr misst keine Station in Europa — darüber ist es ein Fehlwert, kein Wind.
# Bis 2.1.0 gingen NaN, Unendlich und Negatives aus den Antworten weiter bis
# ins Gedächtnis der Modellgüte (C5).
MAX_WIND_MS = 75.0
STATIONEN_TAGE = 30      # Stationslisten ohne eigene Frist (DWD, GeoSphere): so lange gemerkt


class StationError(RuntimeError):
    pass


def _get(url: str, data: bytes | None = None, encoding: str = "utf-8") -> bytes:
    try:
        # Nur https:// — die Adresse der Météo-France-Datei kommt aus einer
        # fremden Antwort, und `urllib` öffnete bis 2.1.0 auch file: und ftp: (C7).
        nur_https(url)
        req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return lies(resp, frist_s=FRIST_S)
    except Exception as exc:                            # noqa: BLE001
        raise StationError(f"{url.split('?')[0]}: {exc}") from exc


def _json(roh: bytes, was: str):
    """Eine JSON-Antwort — unlesbar (auch: zu tief verschachtelt) ist ein StationError."""
    try:
        return json.loads(roh.decode("utf-8"))
    except (ValueError, RecursionError) as exc:
        raise StationError(f"{was}: " + T("Antwort nicht lesbar: {fehler}", fehler=type(exc).__name__)) from None


def _text_lesen(pfad: Path, encoding: str = "utf-8") -> str | None:
    try:
        return pfad.read_text(encoding=encoding)
    except (OSError, ValueError):
        return None


def _verwerfen(pfad: Path) -> None:
    """Eine kaputte Datei aus dem Zwischenspeicher nehmen — beim nächsten Mal
    wird neu geholt, statt für immer an ihr zu scheitern."""
    try:
        pfad.unlink()
    except OSError:
        pass


# ── Was als Messwert zählt ───────────────────────────────────────────────────

def _wind_ms(f, faktor: float = 1.0) -> float | None:
    """Eine Windgeschwindigkeit in m/s, die eine Station gemessen haben kann:
    endlich, 0 bis 75 m/s. Sonst None — Fehlwert (-999), NaN, Unsinn.
    `faktor` rechnet die Einheit der Antwort in m/s um (Knoten: 1 / MS_ZU_KN)."""
    if f is None or isinstance(f, bool):
        return None
    try:
        f = float(f) * faktor
    except (TypeError, ValueError, OverflowError):
        return None
    return f if math.isfinite(f) and 0.0 <= f <= MAX_WIND_MS else None


def _richtung(d) -> float | None:
    """Eine Windrichtung in Grad, 0 bis 360 — sonst None (990 = drehend, Unsinn)."""
    if d is None or isinstance(d, bool):
        return None
    try:
        d = float(d)
    except (TypeError, ValueError, OverflowError):
        return None
    return d if math.isfinite(d) and 0.0 <= d <= 360.0 else None


def _lage(lat, lon) -> tuple[float, float] | None:
    """Breite und Länge einer Station, endlich und im Wertebereich — sonst None."""
    try:
        la, lo = float(lat), float(lon)
    except (TypeError, ValueError, OverflowError):
        return None
    if math.isfinite(la) and math.isfinite(lo) and -90.0 <= la <= 90.0 and -180.0 <= lo <= 180.0:
        return la, lo
    return None


def _stationen_ok(liste) -> list[dict] | None:
    """Eine gemerkte Stationsliste, mit der sich rechnen lässt — sonst None."""
    if not isinstance(liste, list):
        return None
    aus = [st for st in liste if isinstance(st, dict) and st.get("id") is not None
           and _lage(st.get("lat"), st.get("lon")) is not None]
    return aus if len(aus) == len(liste) else None


def _cache_pfad(name: str) -> Path:
    """Ein Dateiname im Cache — bereinigt, weil Stations-IDs aus Netzantworten
    darin stehen (Rijkswaterstaat, GeoSphere, DMI, Météo-France). Alles außer
    Buchstaben, Ziffern, Punkt, Strich und Unterstrich wird zu `_`, ein
    führender Punkt auch; so führt keine ID aus dem Ordner heraus
    (Review 25.09., S13)."""
    sauber = re.sub(r"[^A-Za-z0-9._-]", "_", str(name))[:160].lstrip(".") or "leer"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / sauber


ZIP_MITGLIED_MAX = 32 * 1024 * 1024       # entpackt — die DWD-Dateien haben ein paar MB
ZIP_ZEILE_MAX = 64 * 1024                 # eine Zeile der DWD-Dateien hat keine hundert Zeichen
# Das ZIP selbst — beim DWD einige hundert KB. Schon sein Verzeichnis kostet
# Speicher: `zipfile` legt für jeden Eintrag ein Objekt an, bevor sich irgend
# etwas prüfen lässt; 63 MB (unter der Download-Grenze) mit 1,4 Millionen
# Einträgen belegten 550 MB.
ZIP_DATEI_MAX = 8 * 1024 * 1024
# Nur diese zwei Verfahren: bei ihnen entpackt `zipfile` je Lesevorgang
# höchstens so viel, wie verlangt ist. BZIP2 und LZMA entpackt es ohne jede
# Grenze, und die Größe im Kopf des Mitglieds ist nur eine Behauptung: 1,2 KB
# BZIP2 mit „1000 Bytes“ im Kopf wurden in einem einzigen Lesevorgang zu 1 GB
# im Speicher (Nachprüfung der Korrekturen, 04.10.2026). Der DWD packt mit Deflate.
ZIP_VERFAHREN = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
_ZIP_VERFAHREN_NAMEN = {zipfile.ZIP_BZIP2: "BZIP2", zipfile.ZIP_LZMA: "LZMA"}
# Bit 0: verschlüsselt, Bit 5: „compressed patched data“, Bit 6: starke
# Verschlüsselung — `zipfile` scheitert daran mit Fehlern, die kein StationError sind.
_ZIP_FLAGS_UNLESBAR = 0x01 | 0x20 | 0x40


def _zip_zeilen(pfad: Path, praefix: str, was: str):
    """Die Zeilen des Mitglieds mit dem Präfix aus dem ZIP — als Strom.

    Erst die Größe des ZIP (`ZIP_DATEI_MAX`), dann der Kopf des Mitglieds:
    ohne Kompression oder mit Deflate gepackt (`ZIP_VERFAHREN`), nicht
    verschlüsselt, entpackt nicht größer als `ZIP_MITGLIED_MAX` — die
    Download-Grenze gilt nur komprimiert, und Deflate packt bis 1000:1
    (Review 25.09., S13). Dann Zeile für Zeile mit Grenzen
    (`_zeilen_begrenzt`): keine Zeile länger als `ZIP_ZEILE_MAX`, alles
    zusammen nicht mehr als `ZIP_MITGLIED_MAX` — gezählt wird, was wirklich
    herauskommt, nicht was der Kopf verspricht. Bis 2.1.0 kam das Mitglied als
    ein Text und danach als Liste aller Zeilen in den Speicher, bis 200 MB
    entpackt — aus 50 KB ZIP wurden 1,3 GB (C6).

    Die Zeilen kommen ohne Zeilenende. Ein ZIP, das sich so nicht lesen lässt,
    wird verworfen und beim nächsten Mal neu geholt."""
    try:
        if pfad.stat().st_size > ZIP_DATEI_MAX:
            raise StationError(T("{datei} nicht lesbar: {grund}", datei=pfad.name,
                                 grund=f"> {ZIP_DATEI_MAX // (1024 * 1024)} MB"))
        with zipfile.ZipFile(pfad) as z:
            # Geprüft und geöffnet wird dasselbe Mitglied (die ZipInfo, nicht
            # der Name): zwei Mitglieder mit gleichem Namen ändern daran nichts.
            info = next((i for i in z.infolist() if i.filename.startswith(praefix)), None)
            if info is None:
                raise StationError(T("{was}: keine {praefix}-Datei in {datei}", was=was, praefix=praefix,
                                     datei=pfad.name))
            if info.compress_type not in ZIP_VERFAHREN or info.flag_bits & _ZIP_FLAGS_UNLESBAR:
                verfahren = _ZIP_VERFAHREN_NAMEN.get(info.compress_type, f"compress_type {info.compress_type}")
                if info.compress_type in ZIP_VERFAHREN:
                    verfahren = f"flag_bits {info.flag_bits:#x}"
                raise StationError(T("{datei} nicht lesbar: {grund}", datei=pfad.name,
                                     grund=f"{info.filename}, {verfahren}"))
            if info.file_size > ZIP_MITGLIED_MAX:
                raise StationError(T("{was}: {datei} ist entpackt größer als {mb} MB",
                                     was=was, datei=info.filename, mb=ZIP_MITGLIED_MAX // (1024 * 1024)))
            with z.open(info) as roh:
                yield from _zeilen_begrenzt(roh, pfad.name, zeile_max=ZIP_ZEILE_MAX, gesamt_max=ZIP_MITGLIED_MAX,
                                            encoding="latin-1", was=was)
    except StationError:
        _verwerfen(pfad)
        raise
    except (zipfile.BadZipFile, zlib.error, EOFError, OSError, ValueError, NotImplementedError) as exc:
        _verwerfen(pfad)
        raise StationError(T("{datei} nicht lesbar: {grund}", datei=pfad.name, grund=type(exc).__name__)) from None


def _zip_text(pfad: Path, praefix: str, was: str) -> str:
    """Das Mitglied als ein Text — nur noch für kleine Dateien (Tests, Sonde)."""
    return "".join(f"{zeile}\n" for zeile in _zip_zeilen(pfad, praefix, was))


def _zeilen(text):
    """Ein Text oder schon Zeilen (ein Strom aus `_zip_zeilen`) — Zeile für
    Zeile, ohne erst eine Liste aller Zeilen zu bauen."""
    return io.StringIO(text, newline=None) if isinstance(text, str) else text


FRISCH_S = 6 * 3600
FRISCH_HEUTE_S = 3600


def _brauchbar(pfad: Path, bis: str) -> bool:
    """Gilt eine gemerkte Antwort noch?

    Ein Zeitraum, der mehr als drei Tage zurückliegt, ändert sich nicht mehr —
    der Prüfstand liest ihn für immer aus dem Cache, wenn die Antwort *danach*
    geholt wurde. Eine, die geholt wurde, als er noch jung war, gilt nur so
    lange wie eine junge: bis 2.1.0 galt auch sie für immer, und ein Tag, den
    der Dienst erst später vollständig hatte, blieb für immer ohne Messung
    (C15). Reicht der Zeitraum bis in die letzten drei Tage, liefern die
    Dienste nach und nach mehr Stunden; dann wird nach sechs Stunden neu
    geholt. Reicht er bis heute (der Rückblick fragt den laufenden Tag),
    nach einer Stunde.
    """
    try:
        geholt = pfad.stat().st_mtime
    except OSError:
        return False
    from datetime import date
    try:
        ende = date.fromisoformat(bis)
    except ValueError:
        return True
    abstand = (date.today() - ende).days
    if abstand > 3 and _endgueltig(geholt, ende):
        return True
    import time
    alter = time.time() - geholt
    return alter < (FRISCH_HEUTE_S if abstand <= 0 else FRISCH_S)


def _endgueltig(geholt: float, ende) -> bool:
    """Wurde die Datei geholt, als der Zeitraum schon abgeschlossen war —
    mehr als drei Tage nach seinem letzten Tag?"""
    from datetime import date
    try:
        return (date.fromtimestamp(geholt) - ende).days > 3
    except (OverflowError, OSError, ValueError):
        return False


def _mittel_je_stunde(werte: list) -> dict:
    """Zehnminutenwerte [(datetime, m/s, Grad|None)] → Stundenmittel.

    Die Stunde HH fasst die Werte mit Stempel HH:00 bis HH:50 zusammen. Die
    Richtung ist das Vektormittel, mit der Stärke gewichtet — das arithmetische
    Mittel aus 350° und 10° wäre 180°, also Süd statt Nord. Was kein Messwert
    sein kann (NaN, negativ, über 75 m/s), zählt nicht mit.
    """
    gruppen: dict = {}
    for t, f, d in werte:
        f = _wind_ms(f)
        if f is None:
            continue
        gruppen.setdefault(_stunde(t), []).append((f, _richtung(d)))
    out = {}
    for stunde, liste in sorted(gruppen.items()):
        if len(liste) < 3:                            # eine halbe Stunde ist kein Stundenmittel
            continue
        f_mittel = sum(f for f, _ in liste) / len(liste)
        x = sum(f * math.cos(math.radians(d)) for f, d in liste if d is not None)
        y = sum(f * math.sin(math.radians(d)) for f, d in liste if d is not None)
        richtung = (math.degrees(math.atan2(y, x)) % 360.0) if (x or y) else None
        out[stunde] = {"kn": round(f_mittel * MS_ZU_KN, 1),
                       "dir": (round(richtung, 1) if richtung is not None else None)}
    return out


def _juenger_als(pfad: Path, sekunden: float) -> bool:
    import time
    try:
        return time.time() - pfad.stat().st_mtime < sekunden
    except OSError:
        return False


def _gestern() -> str:
    from datetime import date
    return (date.today() - timedelta(days=1)).isoformat()


def _stunde(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:00")


# ── DWD ──────────────────────────────────────────────────────────────────────

DWD_BASIS = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/wind/recent/"
DWD_LISTE = DWD_BASIS + "FF_Stundenwerte_Beschreibung_Stationen.txt"


def dwd_stationsliste(text: str) -> list[dict]:
    """Die Stationsbeschreibung: feste Spalten, durch Leerzeichen getrennt.

    Stations_id von_datum bis_datum Stationshoehe geoBreite geoLaenge
    Stationsname Bundesland [Abgabe]. Der Name darf Leerzeichen enthalten,
    das Bundesland nicht — deshalb von hinten gelesen.
    """
    out = []
    for zeile in text.splitlines()[2:]:
        teile = zeile.split()
        if len(teile) < 8:
            continue
        sid, von, bis = teile[0], teile[1], teile[2]
        lage = _lage(teile[4], teile[5])
        if lage is None:
            continue
        lat, lon = lage
        rest = teile[6:]
        if rest and rest[-1].lower() == "frei":
            rest = rest[:-1]
        name = " ".join(rest[:-1]) if len(rest) > 1 else rest[0]
        out.append({"id": sid, "name": name, "lat": lat, "lon": lon, "von": von, "bis": bis})
    return out


def dwd_stationen() -> list[dict]:
    """Die Stationsliste — einen Monat gemerkt (bis 2.1.0 für immer, auch eine
    abgeschnittene). Ist das Netz weg, gilt die alte weiter."""
    pfad = _cache_pfad("dwd_stationen.txt")
    text = _text_lesen(pfad, "latin-1")
    gemerkt = dwd_stationsliste(text) if text else []
    if gemerkt and _juenger_als(pfad, STATIONEN_TAGE * 24 * 3600):
        return gemerkt
    try:
        roh = _get(DWD_LISTE)
    except StationError:
        if gemerkt:
            return gemerkt
        raise
    liste = dwd_stationsliste(roh.decode("latin-1", "replace"))
    if liste:
        ablegen(pfad, roh)
    return liste


def _im_zeitraum(stunde: str, von: str | None, bis: str | None) -> bool:
    return (von is None or stunde[:10] >= von) and (bis is None or stunde[:10] <= bis)


def dwd_produkt(text, von: str | None = None, bis: str | None = None) -> dict:
    """produkt_ff_stunde_*.txt → {UTC-Stunde: {"kn", "dir"}} — `text` als ein
    Text oder als Zeilen; mit `von`/`bis` nur die Stunden dieser Tage."""
    out = {}
    for zeile in _zeilen(text):
        teile = [t.strip() for t in zeile.split(";")]
        if len(teile) < 5 or not teile[1].isdigit() or len(teile[1]) < 10:
            continue
        try:
            t = datetime.strptime(teile[1][:10], "%Y%m%d%H")
        except ValueError:
            continue
        f = _wind_ms(teile[3])
        if f is None:                                   # -999 fehlt, NaN und Unsinn ebenso
            continue
        stunde = _stunde(t)
        if _im_zeitraum(stunde, von, bis):
            out[stunde] = {"kn": round(f * MS_ZU_KN, 1), "dir": _richtung(teile[4])}
    return out


DWD_NOW = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/10_minutes/wind/now/"
DWD_ZEHN = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/10_minutes/wind/recent/"


def dwd_now_produkt(text, von: str | None = None, bis: str | None = None) -> dict:
    """produkt_zehn_now_ff_*.txt → Stundenmittel {UTC-Stunde: {"kn", "dir"}}.

    Spalten laut Beschreibung: STATIONS_ID;MESS_DATUM;QN;FF_10;DD_10;eor —
    MESS_DATUM als JJJJMMTTHHMM in UTC, -999 fehlt. Gelesen wird nach
    Spaltennamen, damit eine zusätzliche Spalte nichts verschiebt. `text` als
    ein Text oder als Zeilen; mit `von`/`bis` nur die Werte dieser Tage.
    """
    kopf = None
    werte = []
    for zeile in _zeilen(text):
        if not zeile.strip():
            continue
        teile = [t.strip() for t in zeile.split(";")]
        if kopf is None:
            kopf = [t.upper() for t in teile]
            try:
                i_t, i_f = kopf.index("MESS_DATUM"), kopf.index("FF_10")
                i_d = kopf.index("DD_10") if "DD_10" in kopf else None
            except ValueError:
                return {}
            continue
        if len(teile) <= max(i_t, i_f):
            continue
        try:
            t = datetime.strptime(teile[i_t][:12], "%Y%m%d%H%M")
        except ValueError:
            continue
        f = _wind_ms(teile[i_f])
        if f is None or not _im_zeitraum(_stunde(t), von, bis):
            continue
        werte.append((t, f, _richtung(teile[i_d]) if i_d is not None and i_d < len(teile) else None))
    return _mittel_je_stunde(werte)


def _dwd_zehn_zip(pfad: Path, url: str, frisch_s: int, von: str | None = None, bis: str | None = None) -> dict:
    """Ein Zehnminuten-ZIP holen (wenn älter als `frisch_s`) und zu Stunden mitteln."""
    if not _juenger_als(pfad, frisch_s):
        ablegen(pfad, _get(url))
    return dwd_now_produkt(_zip_zeilen(pfad, "produkt_zehn", "DWD"), von, bis)


def dwd_now_stunden(station: dict, von: str, bis: str) -> dict:
    """Die Stunden des laufenden Tags aus „now“ — nur der aktuelle UTC-Tag,
    stündlich neu (die Sonde vom 19.09.: 00:00 bis 07:30 um 08:10 UTC)."""
    sid = int(station["id"])
    pfad = _cache_pfad(f"dwd_{sid:05d}_now.zip")
    stunden = _dwd_zehn_zip(pfad, f"{DWD_NOW}10minutenwerte_wind_{sid:05d}_now.zip", FRISCH_HEUTE_S, von, bis)
    return {k: v for k, v in stunden.items() if von <= k[:10] <= bis}


def dwd_zehn_stunden(station: dict, von: str, bis: str) -> dict:
    """Die Zehnminutenwerte „recent“ zu Stunden gemittelt — für die Tage, die
    die geprüften Stundenwerte noch nicht haben. Die Stundenwerte „recent“
    reichten am 19.09. um 08 UTC bis zum 17., also bis vorgestern; die
    Zehnminutenwerte „recent“ werden laut Beschreibung täglich geschrieben
    und sollten gestern enthalten — am 19.09. standen sie allerdings auf dem
    13., die Datei ist also nicht immer frisch. Was sie hat, wird genommen."""
    sid = int(station["id"])
    pfad = _cache_pfad(f"dwd_{sid:05d}_zehn.zip")
    stunden = _dwd_zehn_zip(pfad, f"{DWD_ZEHN}10minutenwerte_wind_{sid:05d}_akt.zip", FRISCH_S, von, bis)
    return {k: v for k, v in stunden.items() if von <= k[:10] <= bis}


def dwd_stunden(station: dict, von: str, bis: str) -> dict:
    sid = int(station["id"])
    pfad = _cache_pfad(f"dwd_{sid:05d}.zip")
    if not _brauchbar(pfad, bis):
        ablegen(pfad, _get(f"{DWD_BASIS}stundenwerte_FF_{sid:05d}_akt.zip"))
    stunden = dwd_produkt(_zip_zeilen(pfad, "produkt_ff_stunde", f"DWD {sid}"), von, bis)
    if bis >= _gestern():
        # Die Stundenwerte „recent“ enden vorgestern (einmal am Tag geschrieben,
        # mit einem Tag Verzug). Was fehlt, kommt aus den Zehnminutenwerten:
        # „recent“ für die Tage dazwischen, „now“ für den laufenden Tag. Die
        # geprüfte Stunde gewinnt, wo es beide gibt.
        letzte = max(stunden)[:10] if stunden else ""
        for holen in (dwd_zehn_stunden, dwd_now_stunden):
            try:
                for k, v in holen(station, max(von, letzte), bis).items():
                    stunden.setdefault(k, v)
            except Exception:                           # noqa: BLE001 — dann eben ohne
                pass
    return {"quelle": "DWD", "station": station, "stunden": stunden}


# ── KNMI ─────────────────────────────────────────────────────────────────────

KNMI_URL = "https://www.daggegevens.knmi.nl/klimatologie/uurgegevens"

# Die KNMI-Stationen aus dem Gedächtnis, auf etwa einen Kilometer: Küste,
# Delta, IJsselmeer — seit 1.13.0 auch das Binnenland, damit ein Spot ohne
# Küstenstation in Reichweite die nächste im Land bekommt. Die genaue Lage
# steht im Kopf jeder KNMI-Antwort und ersetzt diese Werte, sobald die
# Station einmal abgefragt wurde.
KNMI_KANDIDATEN = [
    ("209", "IJmond", 52.465, 4.518), ("210", "Valkenburg", 52.171, 4.430),
    ("215", "Voorschoten", 52.141, 4.437), ("225", "IJmuiden", 52.463, 4.555),
    ("235", "De Kooy", 52.928, 4.781), ("240", "Schiphol", 52.318, 4.790),
    ("242", "Vlieland", 53.241, 4.921), ("248", "Wijdenes", 52.634, 5.174),
    ("249", "Berkhout", 52.644, 4.979), ("251", "Hoorn Terschelling", 53.392, 5.346),
    ("257", "Wijk aan Zee", 52.506, 4.603), ("258", "Houtribdijk", 52.649, 5.401),
    ("260", "De Bilt", 52.100, 5.180), ("267", "Stavoren", 52.898, 5.384),
    ("269", "Lelystad", 52.458, 5.520), ("270", "Leeuwarden", 53.224, 5.752),
    ("273", "Marknesse", 52.703, 5.888), ("275", "Deelen", 52.056, 5.873),
    ("277", "Lauwersoog", 53.413, 6.200), ("278", "Heino", 52.435, 6.259),
    ("279", "Hoogeveen", 52.750, 6.574), ("280", "Eelde", 53.125, 6.585),
    ("283", "Hupsel", 52.069, 6.657), ("285", "Huibertgat", 53.575, 6.399),
    ("286", "Nieuw Beerta", 53.196, 7.150), ("290", "Twenthe", 52.274, 6.891),
    ("308", "Cadzand", 51.381, 3.379), ("310", "Vlissingen", 51.442, 3.596),
    ("311", "Hoofdplaat", 51.379, 3.672), ("312", "Oosterschelde", 51.768, 3.622),
    ("313", "Vlakte van de Raan", 51.505, 3.242), ("315", "Hansweert", 51.447, 3.998),
    ("316", "Schaar", 51.657, 3.694), ("319", "Westdorpe", 51.226, 3.861),
    ("323", "Wilhelminadorp", 51.527, 3.884), ("324", "Stavenisse", 51.596, 4.006),
    ("330", "Hoek van Holland", 51.992, 4.122), ("331", "Tholen", 51.480, 4.193),
    ("340", "Woensdrecht", 51.449, 4.342), ("343", "Rotterdam Geulhaven", 51.893, 4.313),
    ("344", "Rotterdam", 51.962, 4.447), ("348", "Cabauw", 51.970, 4.926),
    ("350", "Gilze-Rijen", 51.566, 4.936), ("356", "Herwijnen", 51.859, 5.146),
    ("370", "Eindhoven", 51.451, 5.377), ("375", "Volkel", 51.659, 5.707),
    ("377", "Ell", 51.198, 5.763), ("380", "Maastricht", 50.906, 5.762),
    ("391", "Arcen", 51.498, 6.197),
]


def knmi_stationen() -> list[dict]:
    return [{"id": i, "name": n, "lat": la, "lon": lo, "dienst": "KNMI"} for i, n, la, lo in KNMI_KANDIDATEN]


def knmi_antwort(text: str) -> tuple[dict, dict]:
    """KNMI-CSV → (Stationsangaben aus dem Kopf, {UTC-Stunde: {"kn","dir"}}).

    Stunde HH (1–24) ist das Mittel der Stunde, die um HH UTC endet; sie wird
    der Stunde zugeschrieben, die um HH−1 beginnt — so wie das Modell seine
    Stunde nennt.
    """
    station, stunden = {}, {}
    spalten = None
    for zeile in text.splitlines():
        z = zeile.strip()
        if not z:
            continue
        if z.startswith("#"):
            inhalt = z.lstrip("#").strip()
            teile = inhalt.replace(":", " ").split()
            # "# 267:  5.384  52.898  -1.30  STAVOREN"
            if len(teile) >= 5 and teile[0].isdigit():
                lage = _lage(teile[2], teile[1])
                if lage is not None:
                    station = {"id": teile[0], "lon": lage[1], "lat": lage[0],
                               "name": " ".join(teile[4:]).title().replace("Ij", "IJ")}
            elif inhalt.upper().startswith("STN"):
                spalten = [t.strip().upper() for t in inhalt.split(",")]
            continue
        teile = [t.strip() for t in z.split(",")]
        if spalten is None or len(teile) < len(spalten):
            continue
        werte = dict(zip(spalten, teile))
        try:
            tag = datetime.strptime(werte["YYYYMMDD"], "%Y%m%d")
            hh = int(werte["HH"])
            fh = float(werte["FH"]) if werte.get("FH") not in (None, "") else None
        except (KeyError, ValueError):
            continue
        ms = _wind_ms(fh / 10.0) if fh is not None else None        # FH in 0,1 m/s
        if ms is None or not 1 <= hh <= 24:
            continue
        richtung = _richtung(werte.get("DD"))           # 990 = drehend → None
        t = tag + timedelta(hours=hh - 1)
        stunden[_stunde(t)] = {"kn": round(ms * MS_ZU_KN, 1), "dir": richtung}
    return station, stunden


def knmi_stunden(station: dict, von: str, bis: str) -> dict:
    sid = str(station["id"])
    pfad = _cache_pfad(f"knmi_{sid}_{von}_{bis}.csv")
    text = _text_lesen(pfad) if _brauchbar(pfad, bis) else None
    if text is None:
        start = von.replace("-", "") + "01"
        ende = bis.replace("-", "") + "24"
        body = urllib.parse.urlencode({"stns": sid, "vars": "DD:FH:FX", "start": start, "end": ende}).encode()
        text = _get(KNMI_URL, data=body).decode("utf-8", "replace")
        ablegen(pfad, text)
    kopf, stunden = knmi_antwort(text)
    stunden = {k: v for k, v in stunden.items() if von <= k[:10] <= bis}
    if not stunden and "STN" not in text.upper():
        raise StationError(T("KNMI {station}: keine lesbare Antwort", station=sid))
    # Keine Zeilen im Zeitraum ist kein Fehler: KNMI veröffentlicht mit zwei
    # Tagen Verzug (Sonde vom 19.09.). Der Aufrufer sieht die leere Menge und
    # sagt es so — bis 1.13.0 hieß das „nicht abrufbar“ und klang nach Ausfall.
    st = dict(station)
    st.update({k: v for k, v in kopf.items() if v not in (None, "")})   # genaue Lage aus dem Kopf
    # `hinweis` ist Anzeigetext (Protokoll und Begründung im Rückblick), nicht gespeichert
    return {"quelle": "KNMI", "station": st, "stunden": stunden,
            "hinweis": ("" if stunden else T("KNMI veröffentlicht die Stundenwerte mit zwei Tagen Verzug"))}


# ── Rijkswaterstaat ──────────────────────────────────────────────────────────
#
# Die WaterWebservices von Rijkswaterstaat liefern die Zehnminutenwerte der
# Messpfähle und Küstenstationen — Wind auf dem Wasser, nicht auf dem
# Flughafen — ohne Schlüssel, nahe Echtzeit, unter „fair use“ („Iedereen is
# vrij deze open data in te zien en … te gebruiken“, rijkswaterstaatdata.nl).
#
# Seit 1.14.0 über die neue Schnittstelle („DD-API 2.0“,
# ddapi20-waterwebservices.rijkswaterstaat.nl, Pfade ohne `_DBO`). Die
# alten Adressen unter waterwebservices.rijkswaterstaat.nl, nach denen 1.13.0
# blind gebaut war, lieferten der Sonde vom 20.09.2026 keine Stationsliste.
# Was hier steht, wurde am 20.09.2026 gegen den Dienst geprüft (im Browser,
# 13:50 MESZ):
#
#   Katalog   POST …/METADATASERVICES/OphalenCatalogus — 2 499 Orte mit `Lat`,
#             `Lon` (ETRS89, für diesen Zweck gleich WGS84; kein X/Y mehr),
#             `Code` in Kleinbuchstaben („brouwersdam.brouwershavensegat.2“).
#             Wind: Grootheid `WINDSHD` (m/s) und `WINDRTG` (Grad),
#             Compartiment `LT`. Daneben `WINDSHD_SD`, `WS1`, `WS10`,
#             `WINDST` (Böe) — deshalb zählt der Code, nicht ein Wort in der
#             Beschreibung. Koppeltabelle `AquoMetadataLocatieLijst` mit
#             `AquoMetaData_MessageID` (großes D) und `Locatie_MessageID`.
#   Aktuell   Von 438 Orten mit WINDSHD im Katalog hatten nur 56 Werte von
#             heute; der Rest ist stillgelegt (Badestrände mit Werten von
#             2008). `OphalenLaatsteWaarnemingen` sagt je Ort den letzten
#             Wert — die Stationsliste enthält nur Orte mit einem Wert aus den
#             letzten sieben Tagen.
#   Werte     POST …/ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen mit
#             `Locatie: {Code}` (ohne Koordinate). Ohne Werte im Zeitraum
#             antwortet der Dienst mit HTTP 204 und leerem Körper. Eine
#             Antwort trägt mehrere Reihen: zwei gemessene (`ProcesType`
#             „meting“ — eine davon „gecorr. naar KNMI hoogte“, also auf die
#             Normhöhe von 10 m umgerechnet) und eine VORHERSAGE
#             (`ProcesType` „verwachting“) mit Werten um 0,5 m/s. Die
#             Vorhersage darf nie ins Mittel — 1.13.0 hätte sie mitgemittelt.
#             Genommen wird die auf 10 m korrigierte Messung, sonst die
#             längste gemessene Reihe. `Tijdstip` mit Zeitzone (+01:00),
#             `Meetwaarde.Waarde_Numeriek`, `WaarnemingMetadata.
#             Kwaliteitswaardecode` („00“; „99“ heißt verworfen).

RWS_BASIS = "https://ddapi20-waterwebservices.rijkswaterstaat.nl/"
RWS_KATALOG = RWS_BASIS + "METADATASERVICES/OphalenCatalogus"
RWS_WERTE = RWS_BASIS + "ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen"
RWS_LETZTE = RWS_BASIS + "ONLINEWAARNEMINGENSERVICES/OphalenLaatsteWaarnemingen"
RWS_VERWORFEN = {"99"}          # Kwaliteitswaardecode für verworfene Werte
RWS_CODE = {"speed": "WINDSHD", "dir": "WINDRTG"}
RWS_AKTUELL_TAGE = 7


def _post_json(url: str, koerper: dict) -> object:
    """POST mit JSON. Ein leerer Körper (HTTP 204, „nichts im Zeitraum“) ist
    kein Fehler, sondern eine Antwort ohne Reihen."""
    daten = json.dumps(koerper).encode("utf-8")
    req = urllib.request.Request(url, data=daten, method="POST",
                                 headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            roh = lies(resp, frist_s=FRIST_S)
            if getattr(resp, "status", 200) == 204 or not roh.strip():
                return {"Succesvol": True, "WaarnemingenLijst": []}
            return json.loads(roh.decode("utf-8"))
    except Exception as exc:                            # noqa: BLE001
        raise StationError(f"{url.rsplit('/', 1)[-1]}: {exc}") from exc


def utm31_nach_wgs84(x: float, y: float) -> tuple[float, float]:
    """EPSG:25831 (ETRS89 / UTM Zone 31N) → (lat, lon). Die übliche Rückrechnung
    (Krüger-Reihe); auf wenige Meter genau, mehr braucht die Stationssuche nicht.
    Prüfpunkt: Vlissingen VLIS (541518.7, 5699254.9) → 51.44° N, 3.60° O.
    Nur noch für einen Katalog im alten Format (X/Y statt Lat/Lon)."""
    a, f = 6378137.0, 1 / 298.257222101
    k0, e2 = 0.9996, 2 * f - f * f
    ep2 = e2 / (1 - e2)
    lon0 = math.radians(3.0)
    xm, ym = x - 500000.0, y
    m = ym / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 * e2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 * e1 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu))
    n1 = a / math.sqrt(1 - e2 * math.sin(phi1) ** 2)
    t1 = math.tan(phi1) ** 2
    c1 = ep2 * math.cos(phi1) ** 2
    r1 = a * (1 - e2) / (1 - e2 * math.sin(phi1) ** 2) ** 1.5
    d = xm / (n1 * k0)
    lat = phi1 - (n1 * math.tan(phi1) / r1) * (d * d / 2
          - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * ep2) * d ** 4 / 24
          + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * ep2 - 3 * c1 * c1) * d ** 6 / 720)
    lon = lon0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6
                  + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * ep2 + 24 * t1 * t1) * d ** 5 / 120) / math.cos(phi1)
    return math.degrees(lat), math.degrees(lon)


def rws_katalog() -> dict:
    """Der Katalog: welche Größen es gibt, welche Orte, und was wo gemessen
    wird. Groß (knapp 2 MB), deshalb 30 Tage gemerkt."""
    pfad = _cache_pfad("rws2_katalog.json")
    if _juenger_als(pfad, 30 * 24 * 3600):
        daten = cache_lesen(pfad, dict)
        if daten is not None and "LocatieLijst" in daten:
            return daten
    daten = _post_json(RWS_KATALOG, {"CatalogusFilter": {"Compartimenten": True, "Grootheden": True, "Eenheden": True}})
    if not isinstance(daten, dict) or "LocatieLijst" not in daten:
        raise StationError(T("Rijkswaterstaat: unerwarteter Katalog ({antwort})", antwort=str(daten)[:100]))
    ablegen(pfad, json.dumps(daten))
    return daten


def rws_groessen(katalog: dict) -> dict:
    """{"speed": {"code", "ids"}, "dir": {…}} — Windgeschwindigkeit und
    -richtung in der Luft. Entscheidend ist der Code (WINDSHD, WINDRTG): an der
    Beschreibung erkannt hätte „Standaarddeviatie van de windsnelheid“ mitgezählt."""
    aus: dict = {}
    for meta in katalog.get("AquoMetadataLijst") or []:
        g = meta.get("Grootheid") or {}
        code = str(g.get("Code") or "").upper()
        comp = str((meta.get("Compartiment") or {}).get("Code") or "").upper()
        if comp and comp != "LT":
            continue
        art = next((a for a, c in RWS_CODE.items() if c == code), None)
        if art is None:
            continue
        eintrag = aus.setdefault(art, {"code": code, "ids": set()})
        eintrag["ids"].add(meta.get("AquoMetadata_MessageID"))
    return aus


def _rws_lage(ort: dict) -> tuple[float, float] | None:
    """Lat/Lon des Orts — im neuen Katalog direkt, im alten als UTM X/Y."""
    try:
        if ort.get("Lat") is not None and ort.get("Lon") is not None:
            return float(ort["Lat"]), float(ort["Lon"])
        return utm31_nach_wgs84(float(ort["X"]), float(ort["Y"]))
    except (KeyError, TypeError, ValueError):
        return None


def rws_letzte(codes: list[str]) -> dict:
    """{Code: letzter gemessener Zeitpunkt (UTC, ISO)} — eine Anfrage für alle
    Orte. Vorhersagereihen zählen nicht."""
    daten = _post_json(RWS_LETZTE, {
        "AquoPlusWaarnemingMetadataLijst": [{"AquoMetadata": {"Compartiment": {"Code": "LT"},
                                                              "Grootheid": {"Code": RWS_CODE["speed"]}}}],
        "LocatieLijst": [{"Code": c} for c in codes]})
    aus: dict = {}
    for reihe in (daten.get("WaarnemingenLijst") or []) if isinstance(daten, dict) else []:
        if not _rws_gemessen(reihe):
            continue
        code = str((reihe.get("Locatie") or {}).get("Code") or "")
        for m in reihe.get("MetingenLijst") or []:
            t = _rws_zeit(m.get("Tijdstip"))
            if code and t and (code not in aus or t > aus[code]):
                aus[code] = t
    return {c: t.isoformat(timespec="minutes") for c, t in aus.items()}


def rws_stationen() -> list[dict]:
    """Die Orte, an denen Rijkswaterstaat den Wind *zurzeit* misst, mit Lage.
    Eine Woche gemerkt — so lange ändert sich die Liste der Messpfähle nicht."""
    pfad = _cache_pfad("rws2_stationen.json")
    if _juenger_als(pfad, RWS_AKTUELL_TAGE * 24 * 3600):
        gemerkt = _stationen_ok(cache_lesen(pfad, list))
        if gemerkt is not None:
            return gemerkt
    katalog = rws_katalog()
    groessen = rws_groessen(katalog)
    if "speed" not in groessen:
        raise StationError(T("Rijkswaterstaat: keine Windgeschwindigkeit (WINDSHD) im Katalog gefunden"))
    ids = groessen["speed"]["ids"]
    orte_mit_wind = {k.get("Locatie_MessageID") for k in (katalog.get("AquoMetadataLocatieLijst") or [])
                     if (k.get("AquoMetaData_MessageID") in ids or k.get("AquoMetadata_MessageID") in ids)}
    alle = []
    for ort in katalog.get("LocatieLijst") or []:
        if ort.get("Locatie_MessageID") not in orte_mit_wind:
            continue
        lage = _rws_lage(ort)
        if lage is None or not (49 < lage[0] < 56.5 and 1 < lage[1] < 9):
            continue
        alle.append({"id": str(ort.get("Code") or ort.get("Locatie_MessageID")),
                     "name": str(ort.get("Naam") or ort.get("Code")),
                     "lat": round(lage[0], 5), "lon": round(lage[1], 5), "dienst": "RWS",
                     "code_speed": groessen["speed"]["code"], "code_dir": (groessen.get("dir") or {}).get("code")})
    grenze = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=RWS_AKTUELL_TAGE)).isoformat(timespec="minutes")
    letzte = rws_letzte([s["id"] for s in alle])
    aus = [dict(s, letzte=letzte[s["id"]]) for s in alle if letzte.get(s["id"], "") >= grenze]
    if not aus:
        raise StationError(T("Rijkswaterstaat: von {n} Orten mit Wind im Katalog liefert keiner aktuelle Werte",
                             n=len(alle)))
    ablegen(pfad, json.dumps(aus))
    return aus


def _rws_zeit(t) -> datetime | None:
    """`Tijdstip` → naive UTC-Zeit."""
    try:
        stempel = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if stempel.tzinfo is not None:
        stempel = (stempel - stempel.utcoffset()).replace(tzinfo=None)
    return stempel


def _rws_gemessen(reihe: dict) -> bool:
    """Gemessen, nicht vorhergesagt. Ohne `ProcesType` (altes Format): gemessen."""
    meta = reihe.get("AquoMetadata") if isinstance(reihe, dict) else None
    art = str((meta or {}).get("ProcesType") or "meting").lower()
    return art == "meting"


def _rws_reihe(daten: object) -> dict | None:
    """Die eine Reihe, die zählt: gemessen, bevorzugt auf 10 m korrigiert
    („gecorr. naar KNMI hoogte“), sonst die längste."""
    if not isinstance(daten, dict):
        return None
    reihen = [r for r in daten.get("WaarnemingenLijst") or [] if isinstance(r, dict) and _rws_gemessen(r)]
    if not reihen:
        return None

    def rang(r):
        meta = r.get("AquoMetadata") or {}
        wbm = str((meta.get("WaardeBepalingsMethode") or {}).get("Omschrijving") or "").lower()
        return ("knmi hoogte" in wbm, len(r.get("MetingenLijst") or []))
    return max(reihen, key=rang)


def rws_einheit(daten: object) -> str:
    """Die Einheit der gewählten Reihe (Eenheid.Code), etwa „m/s“."""
    reihe = _rws_reihe(daten)
    meta = (reihe or {}).get("AquoMetadata") or {}
    code = (meta.get("Eenheid") or {}).get("Code") if isinstance(meta, dict) else None
    return str(code or "").strip().lower()


def rws_in_ms(wert: float, einheit: str) -> float:
    """Was die Antwort liefert, in m/s — entschieden wird nach der Einheit in
    der Antwort (am 20.09. „m/s“)."""
    e = (einheit or "").lower()
    if e in ("kn", "kt", "kts", "knoop", "knopen", "knots"):
        return wert / MS_ZU_KN
    if e in ("km/h", "km/u", "kmh"):
        return wert / 3.6
    return wert                                          # m/s, oder nichts gesagt


def rws_werte(daten: object, art: str = "speed") -> list:
    """OphalenWaarnemingen-Antwort → [(datetime UTC, Wert)] aus der einen
    gemessenen Reihe (`_rws_reihe`). Für „speed“ in m/s, für „dir“ in Grad
    0–360; verworfene Werte (Qualität 99), Fehlwerte und Unsinn fallen weg."""
    reihe = _rws_reihe(daten)
    if reihe is None:
        return []
    einheit = rws_einheit(daten)
    aus = []
    for m in reihe.get("MetingenLijst") or []:
        meta = m.get("WaarnemingMetadata") or {}
        q = meta.get("Kwaliteitswaardecode")
        if q is None:
            q = (meta.get("KwaliteitswaardecodeLijst") or [None])[0]
        if str(q) in RWS_VERWORFEN:
            continue
        wert = m.get("Meetwaarde") or {}
        v = wert.get("Waarde_Numeriek") if isinstance(wert, dict) else wert
        stempel = _rws_zeit(m.get("Tijdstip"))
        if stempel is None or v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if art == "dir":
            v = _richtung(v)
        else:
            v = _wind_ms(rws_in_ms(v, einheit))         # Fehlwert (999…), NaN oder Unsinn → None
        if v is None:
            continue
        aus.append((stempel, v))
    return aus


def _vervollstaendigt(station: dict, liste: list, dienst: str) -> dict:
    """Ein Paar aus der Grundlinie trägt nur id, name, lat, lon — was die
    Abfrage sonst braucht (Lage in UTM, Größen-Codes, Passwort), steht in der
    Stationsliste. Fehlt die Station dort, ist das ein Fehler, kein Raten."""
    sid = str(station["id"])
    voll = next((st for st in liste if str(st["id"]) == sid), None)
    if voll is None:
        raise StationError(T("{dienst} {station}: nicht in der Stationsliste", dienst=dienst, station=sid))
    aus = dict(voll)
    aus.update({k: v for k, v in station.items() if k in ("name", "lat", "lon") and v not in (None, "")})
    return aus


def rws_stunden(station: dict, von: str, bis: str) -> dict:
    """Zehnminutenwerte zu Stundenmitteln, m/s → Knoten. Zwei Abfragen: Stärke
    und Richtung, jede für sich gemerkt."""
    sid = str(station["id"])
    reihen = {}
    for art in ("speed", "dir"):
        code = station.get(f"code_{art}") or RWS_CODE[art]
        pfad = _cache_pfad(f"rws2_{sid}_{art}_{von}_{bis}.json")
        daten = cache_lesen(pfad) if _brauchbar(pfad, bis) else None
        if daten is None:
            koerper = {
                "Locatie": {"Code": sid},
                "AquoPlusWaarnemingMetadata": {
                    "AquoMetadata": {"Compartiment": {"Code": "LT"}, "Grootheid": {"Code": code}}},
                "Periode": {"Begindatumtijd": f"{von}T00:00:00.000+00:00",
                            "Einddatumtijd": f"{bis}T23:59:59.000+00:00"},
            }
            daten = _post_json(RWS_WERTE, koerper)
            ablegen(pfad, json.dumps(daten))
        reihen[art] = rws_werte(daten, art)
    if not reihen.get("speed"):
        return {"quelle": "RWS", "station": station, "stunden": {},
                "hinweis": T("Rijkswaterstaat hat für diese Tage keine Windwerte geliefert")}
    richtung = {t: d for t, d in reihen.get("dir") or []}
    werte = [(t, v, richtung.get(t)) for t, v in reihen["speed"]]
    stunden = {k: v for k, v in _mittel_je_stunde(werte).items() if von <= k[:10] <= bis}
    return {"quelle": "RWS", "station": station, "stunden": stunden}


# ── Niederlande: KNMI und Rijkswaterstaat zusammen ───────────────────────────

def nl_stationen(spot=None) -> list[dict]:
    """KNMI (Stundenwerte, zwei Tage Verzug) und Rijkswaterstaat (Zehnminuten-
    werte auf dem Wasser, nahe Echtzeit) in einer Liste — die Entfernung
    entscheidet, und wer für den Zeitraum nichts hat, gibt an die nächste ab."""
    aus = knmi_stationen()
    try:
        aus += rws_stationen()
    except StationError:
        pass                                             # dann eben nur KNMI
    return aus


def nl_stunden(station: dict, von: str, bis: str) -> dict:
    return rws_stunden(station, von, bis) if station.get("dienst") == "RWS" else knmi_stunden(station, von, bis)


# ── Windguru-Stationen ───────────────────────────────────────────────────────
#
# Windguru zeigt auf seinen Seiten viele private Messstationen. Lesen lassen
# sie sich nur über die dokumentierte Schnittstelle (wgsapi.php, „Windguru
# Station JSON API“, stations.windguru.cz/json_api_stations.html), und die
# verlangt für jede Anfrage `password` — das API-Passwort der Station oder
# dessen MD5-Summe, das der Besitzer setzt. Die Seiten selbst holen ihre Daten
# über einen internen Weg, der ohne Sitzung 401 antwortet; den umgeht
# Wingfoilscout nicht. Antwort laut Beschreibung: parallele Listen `unixtime`,
# `datetime` (Ortszeit), `wind_avg`/`wind_max` in Knoten, `wind_direction`
# in Grad; fehlende Werte sind null. Also:
# Stationen, deren Passwort du hast (deine eigene, oder eine, deren Besitzer
# es dir gibt), kommen in die persönliche config.yaml:
#
#   stationen:
#     windguru:
#       - {id: 1234, name: "Mein Pfahl", lat: 51.76, lon: 3.85, passwort_md5: "…"}
#
# `passwort_md5` ist die MD5-Summe des API-Passworts (die Schnittstelle nimmt
# auch Klartext; die Summe steht besser in einer Datei). Ohne Einträge gibt es
# diese Quelle nicht.

WINDGURU_API = "https://www.windguru.cz/int/wgsapi.php"
WINDGURU_KONFIG: list = []


def windguru_setzen(eintraege) -> None:
    """Die Stationen aus der Konfiguration übernehmen (rueckblick, pruefstand)."""
    WINDGURU_KONFIG[:] = [e for e in (eintraege or []) if isinstance(e, dict)]


def windguru_stationen(spot=None) -> list[dict]:
    aus = []
    for e in WINDGURU_KONFIG:
        try:
            lage = _lage(e["lat"], e["lon"])
            if lage is None:
                continue
            aus.append({"id": str(e["id"]), "name": str(e.get("name") or f"Windguru {e['id']}"),
                        "lat": lage[0], "lon": lage[1], "dienst": "Windguru",
                        "passwort": str(e.get("passwort_md5") or e.get("passwort") or "")})
        except (KeyError, TypeError, ValueError):
            continue
    return [a for a in aus if a["passwort"]]


def windguru_antwort(daten: object) -> dict:
    """station_data mit avg_minutes=60 → {UTC-Stunde: {"kn","dir"}}. Die
    Zeitstempel kommen als Unixzeit (`unixtime`) — die ist eindeutig, die
    `datetime`-Strings stehen in der Ortszeit der Station."""
    if not isinstance(daten, dict):
        return {}
    zeiten, winde, richtungen = (daten.get(k) for k in ("unixtime", "wind_avg", "wind_direction"))
    zeiten, winde, richtungen = (x if isinstance(x, list) else [] for x in (zeiten, winde, richtungen))
    aus = {}
    for i, t in enumerate(zeiten):
        w = winde[i] if i < len(winde) else None
        if _wind_ms(w, 1.0 / MS_ZU_KN) is None:         # null, NaN, 9999 kn, Text
            continue
        d = richtungen[i] if i < len(richtungen) else None
        try:
            # Eine Unixzeit jenseits des Jahres 9999 wirft OSError oder
            # OverflowError — bis 2.1.0 brach das die ganze Antwort ab (C21).
            stempel = datetime.fromtimestamp(int(t), timezone.utc).replace(tzinfo=None)
        except (TypeError, ValueError, OverflowError, OSError):
            continue
        aus[_stunde(stempel)] = {"kn": round(float(w), 1), "dir": _richtung(d)}
    return aus


def windguru_stunden(station: dict, von: str, bis: str) -> dict:
    if not station.get("passwort"):
        station = _vervollstaendigt(station, windguru_stationen(), "Windguru")
    sid = str(station["id"])
    pfad = _cache_pfad(f"windguru_{sid}_{von}_{bis}.json")
    daten = cache_lesen(pfad, dict) if _brauchbar(pfad, bis) else None
    if daten is None:
        # In welcher Zeitzone `from`/`to` gelesen werden, sagt die Beschreibung
        # nicht — einen Tag Rand auf beiden Seiten, gefiltert wird unten nach
        # der Unixzeit, die eindeutig ist.
        from datetime import date
        rand_von = (date.fromisoformat(von) - timedelta(days=1)).isoformat()
        rand_bis = (date.fromisoformat(bis) + timedelta(days=1)).isoformat()
        params = {"id_station": sid, "password": station.get("passwort", ""), "q": "station_data",
                  "from": f"{rand_von} 00:00:00", "to": f"{rand_bis} 23:59:59", "avg_minutes": 60,
                  "vars": "wind_avg,wind_max,wind_direction", "format": "json"}
        text = _get(WINDGURU_API, data=urllib.parse.urlencode(params).encode()).decode("utf-8", "replace")
        try:
            daten = json.loads(text)
        except (ValueError, RecursionError):
            raise StationError(T("Windguru {station}: keine JSON-Antwort ({antwort})",
                                 station=sid, antwort=repr(text.strip()[:80]))) from None
        if isinstance(daten, dict) and daten.get("error"):
            raise StationError(f"Windguru {sid}: {daten.get('error')}")
        if not isinstance(daten, dict) or "unixtime" not in daten:
            raise StationError(T("Windguru {station}: unerwartete Antwort ({antwort})",
                                 station=sid, antwort=repr(text.strip()[:80])))
        ablegen(pfad, json.dumps(daten))
    stunden = {k: v for k, v in windguru_antwort(daten).items() if von <= k[:10] <= bis}
    return {"quelle": "Windguru", "station": station, "stunden": stunden}


# ── GeoSphere ────────────────────────────────────────────────────────────────

GEOSPHERE = "https://dataset.api.hub.geosphere.at/v1/station/historical/klima-v2-1h"


def _geosphere_liste(daten) -> list[dict]:
    """Metadaten-Antwort → Stationen mit Lage (aktiv oder nicht)."""
    out = []
    stationen = daten.get("stations") if isinstance(daten, dict) else None
    for st in stationen if isinstance(stationen, list) else []:
        try:
            lage = _lage(st["lat"], st["lon"])
            if lage is None:
                continue
            out.append({"id": str(st["id"]), "name": str(st.get("name", st["id"])),
                        "lat": lage[0], "lon": lage[1], "aktiv": bool(st.get("is_active", True))})
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
    return out


def _metadaten(pfad: Path, url: str, frist_s: float) -> list[dict]:
    """Eine GeoSphere-Stationsliste — gemerkt für `frist_s`, eine kaputte
    Datei zählt als keine, und ist das Netz weg, gilt die alte weiter."""
    gemerkt = _geosphere_liste(cache_lesen(pfad, dict))
    if gemerkt and _juenger_als(pfad, frist_s):
        return gemerkt
    try:
        roh = _get(url)
        daten = _json(roh, "GeoSphere")
    except StationError:
        if gemerkt:
            return gemerkt
        raise
    liste = _geosphere_liste(daten)
    if liste:
        ablegen(pfad, json.dumps(daten))
    return liste


def geosphere_stationen() -> list[dict]:
    """Die Klimastationen — einen Monat gemerkt (bis 2.1.0 für immer, und eine
    abgeschnittene Datei warf bei jedem Lauf)."""
    out = _metadaten(_cache_pfad("geosphere_stationen.json"), GEOSPHERE + "/metadata", STATIONEN_TAGE * 24 * 3600)
    return [s for s in out if s["aktiv"]]


def _geosphere_reihen(daten: dict) -> list:
    """GeoJSON-Antwort → [(UTC-Zeitstempel, m/s, Grad|None)], Einheit umgerechnet."""
    if not isinstance(daten, dict):
        return []
    zeiten = daten.get("timestamps") or []
    features = daten.get("features") or []
    if not isinstance(zeiten, list) or not isinstance(features, list) or not features \
            or not isinstance(features[0], dict):
        return []
    params = (features[0].get("properties") or {}).get("parameters") or {}
    if not isinstance(params, dict):
        return []
    ff = next((params[k] for k in ("ff", "FF", "vv", "VV") if k in params), None)
    dd = next((params[k] for k in ("dd", "DD") if k in params), None)
    if not ff or not isinstance(ff, dict):
        return []
    werte_ff = ff.get("data") or []
    werte_dd = (dd if isinstance(dd, dict) else {}).get("data") or []
    if not isinstance(werte_ff, list) or not isinstance(werte_dd, list):
        return []
    # Die Einheit steht in der Antwort — m/s ist der Regelfall, aber wer
    # sie ignoriert, bekommt bei km/h zweimal zu viel Wind.
    einheit = str(ff.get("unit") or "m/s").lower()
    if "km" in einheit:
        faktor = 1.0 / 3.6
    elif "kn" in einheit or "kt" in einheit:
        faktor = 0.514444
    else:
        faktor = 1.0
    out = []
    for i, t in enumerate(zeiten):
        f_ms = _wind_ms(werte_ff[i] if i < len(werte_ff) else None, faktor)
        if f_ms is None:                                # fehlt, NaN, 1e999, negativ
            continue
        d = werte_dd[i] if i < len(werte_dd) else None
        try:
            stempel = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
            if stempel.tzinfo is not None:
                stempel = (stempel - stempel.utcoffset()).replace(tzinfo=None)
        except (TypeError, ValueError, OverflowError):
            continue
        out.append((stempel, f_ms, _richtung(d)))
    return out


def geosphere_antwort(daten: dict) -> dict:
    """Stundenwerte (klima-v2-1h) → {UTC-Stunde: {"kn", "dir"}}."""
    return {_stunde(t): {"kn": round(f * MS_ZU_KN, 1), "dir": d} for t, f, d in _geosphere_reihen(daten)}


GEOSPHERE_TAWES = "https://dataset.api.hub.geosphere.at/v1/station/historical/tawes-v1-10min"


def geosphere_tawes_stationen() -> list[dict]:
    """Die TAWES-Stationen (Zehnminutenwerte, nahe Echtzeit) — eigene Kennungen,
    deshalb wird zur Klimastation die nächste TAWES-Station gesucht."""
    out = _metadaten(_cache_pfad("geosphere_tawes_stationen.json"), GEOSPHERE_TAWES + "/metadata", 24 * 3600)
    return [{k: v for k, v in s.items() if k != "aktiv"} for s in out if s["aktiv"]]


def geosphere_tawes_stunden(station: dict, von: str, bis: str, max_km: float = 3.0) -> dict:
    """Stundenmittel aus den Zehnminutenwerten der TAWES-Station neben der
    Klimastation — für die Stunden, die klima-v2-1h noch nicht hat."""
    tawes, km = naechste_station(station, geosphere_tawes_stationen(), max_km)
    if not tawes:
        return {}
    sid = str(tawes["id"])
    pfad = _cache_pfad(f"geosphere_tawes_{sid}_{von}_{bis}.json")
    daten = cache_lesen(pfad, dict) if _brauchbar(pfad, bis) else None
    if daten is None:
        for namen in ("FF,DD", "ff,dd"):
            params = {"parameters": namen, "start": f"{von}T00:00", "end": f"{bis}T23:50",
                      "station_ids": sid, "output_format": "geojson"}
            try:
                daten = _json(_get(f"{GEOSPHERE_TAWES}?{urllib.parse.urlencode(params)}"), "GeoSphere TAWES")
                break
            except StationError as exc:
                if "400" not in str(exc):
                    raise
        if daten is None:
            raise StationError(T("GeoSphere TAWES {station}: Parameter FF/DD nicht angenommen", station=sid))
        ablegen(pfad, json.dumps(daten))
    stunden = _mittel_je_stunde(_geosphere_reihen(daten))
    return {k: v for k, v in stunden.items() if von <= k[:10] <= bis}


def geosphere_stunden(station: dict, von: str, bis: str) -> dict:
    sid = str(station["id"])
    pfad = _cache_pfad(f"geosphere_{sid}_{von}_{bis}.json")
    daten = cache_lesen(pfad, dict) if _brauchbar(pfad, bis) else None
    if daten is None:
        params = {"parameters": "ff,dd", "start": f"{von}T00:00", "end": f"{bis}T23:00",
                  "station_ids": sid, "output_format": "geojson"}
        daten = _json(_get(f"{GEOSPHERE}?{urllib.parse.urlencode(params)}"), "GeoSphere")
        ablegen(pfad, json.dumps(daten))
    stunden = {k: v for k, v in geosphere_antwort(daten).items() if von <= k[:10] <= bis}
    if bis >= _gestern():
        # klima-v2-1h ist geprüft und kommt mit Verzug; die letzten Stunden
        # liefern die Zehnminutenwerte der TAWES-Station daneben.
        try:
            for k, v in geosphere_tawes_stunden(station, max(von, _gestern()), bis).items():
                stunden.setdefault(k, v)
        except Exception:                               # noqa: BLE001
            pass
    if not stunden:
        raise StationError(T("GeoSphere {station}: keine Stundenwerte in der Antwort", station=sid))
    return {"quelle": "GeoSphere", "station": station, "stunden": stunden}


# ── Météo-France ─────────────────────────────────────────────────────────────

FR_DATENSATZ = "https://www.data.gouv.fr/api/2/datasets/6569b4473bedf2e7abad3b72/resources/"
FR_DATEIEN = "https://meteofrance.s3.sbg.io.cloud.ovh.net/data/synchro_ftp/BASE/HOR/"
# Grenzen für das Entpacken (C6). Eine Zeile der Datei hat einige hundert
# Zeichen, die Datei eines Départements entpackt einige hundert MB. Bis 2.1.0
# las `csv` jede Zeile ganz, bevor seine Feldgrenze griff — eine einzige Zeile
# ohne Umbruch füllte den Speicher, egal wie klein die gepackte Datei war.
FR_ZEILE_MAX = 64 * 1024
FR_ENTPACKT_MAX = 1024 * 1024 * 1024
FR_MAX_POSTEN = 2000            # ein Département hat ein paar hundert Messposten

# Grobe Rahmen der Départements mit Küste oder Wingfoil-See — nur um zu
# entscheiden, welche Datei geladen wird. Ein Punkt liegt oft in zwei Rahmen
# (Rhône-Mündung, Alpenseen); dann werden die zwei nächsten geladen, und die
# Station entscheidet die Entfernung. Grenzen auf etwa zehn Kilometer, aus
# dem Gedächtnis; die Sonde zeigt, ob die Station gefunden wird.
FR_RAHMEN = {
    "59": (50.0, 51.1, 2.05, 4.25), "62": (50.0, 51.0, 1.55, 3.2), "80": (49.6, 50.4, 1.35, 3.2),
    "76": (49.25, 50.1, 0.05, 1.8), "14": (48.75, 49.45, -1.2, 0.45), "50": (48.45, 49.75, -1.95, -0.75),
    "35": (47.6, 48.75, -2.3, -1.0), "22": (48.0, 48.95, -3.7, -1.9), "29": (47.7, 48.8, -5.2, -3.35),
    "56": (47.25, 48.25, -3.75, -2.0), "44": (46.85, 47.85, -2.6, -0.95), "85": (46.25, 47.1, -2.45, -0.5),
    "17": (45.1, 46.4, -1.6, 0.05), "33": (44.2, 45.6, -1.35, 0.35), "40": (43.5, 44.55, -1.55, 0.15),
    "64": (42.75, 43.65, -1.85, 0.05), "66": (42.3, 42.95, 1.7, 3.2), "11": (42.6, 43.5, 1.65, 3.25),
    "34": (43.2, 43.95, 2.5, 4.2), "30": (43.45, 44.45, 3.25, 4.85), "13": (43.15, 43.95, 4.2, 5.85),
    "83": (42.95, 43.85, 5.65, 6.95), "06": (43.45, 44.4, 6.6, 7.75), "2A": (41.3, 42.4, 8.5, 9.45),
    "2B": (41.8, 43.05, 8.55, 9.6), "74": (45.65, 46.45, 5.8, 7.05), "73": (45.05, 45.95, 5.6, 7.2),
    "38": (44.7, 45.9, 4.75, 6.4), "05": (44.2, 45.15, 5.4, 7.1), "04": (43.65, 44.65, 5.5, 6.95),
    "39": (46.25, 47.3, 5.25, 6.2), "01": (45.6, 46.5, 4.7, 6.15), "51": (48.5, 49.4, 3.4, 5.05),
    "52": (47.55, 48.7, 4.6, 5.9), "10": (47.9, 48.7, 3.4, 4.9), "55": (48.4, 49.6, 4.9, 5.85),
    "12": (43.7, 44.95, 1.85, 3.45),
}


def fr_departements(lat: float, lon: float, n: int = 2) -> list[str]:
    """Die Départements, deren Datei für diesen Punkt in Frage kommt — die
    treffenden Rahmen, nach Abstand zur Rahmenmitte, höchstens `n`; trifft
    keiner, der nächste."""
    def abstand(d):
        b = FR_RAHMEN[d]
        return math.hypot(lat - (b[0] + b[1]) / 2, (lon - (b[2] + b[3]) / 2) * math.cos(math.radians(lat)))
    treffer = [d for d, b in FR_RAHMEN.items() if b[0] <= lat <= b[1] and b[2] <= lon <= b[3]]
    if not treffer:
        return [min(FR_RAHMEN, key=abstand)]
    return sorted(treffer, key=abstand)[:n]


def fr_url_gilt(url, dept: str) -> bool:
    """Nur die Datei dieses Départements, und nur von Météo-France selbst:
    `FR_DATEIEN` + `H_<dept>_latest-JJJJ-JJJJ.csv.gz`, nichts davor oder
    dahinter. Bis 2.1.0 genügte „enthält /H_29_latest- und endet auf
    .csv.gz“ — die Antwort von data.gouv.fr hätte jede Adresse nennen können,
    auch file:///… (C7)."""
    return (isinstance(url, str) and bool(re.fullmatch(r"[0-9]{2}|2[AB]", str(dept)))
            and url.startswith(FR_DATEIEN)
            and re.fullmatch(rf"H_{dept}_latest-\d{{4}}-\d{{4}}\.csv\.gz", url[len(FR_DATEIEN):]) is not None)


def fr_datei_url(dept: str) -> str:
    """Die Adresse der Datei „letzte zwei Jahre“ eines Départements.

    Der Dateiname trägt die Jahre (`H_29_latest-2025-2026.csv.gz`) und
    wechselt zum Jahreswechsel; deshalb wird er über die Datensatz-API von
    data.gouv.fr aufgelöst und einen Tag gemerkt. Antwortet die API nicht —
    oder nennt sie keine Adresse, die `fr_url_gilt` —, gilt das Muster mit
    dem laufenden Jahr. Die gemerkte Adresse wird genauso geprüft.
    """
    pfad = _cache_pfad(f"fr_{dept}_url.txt")
    if _juenger_als(pfad, 24 * 3600):
        gemerkt = (_text_lesen(pfad) or "").strip()
        if fr_url_gilt(gemerkt, dept):
            return gemerkt
    url = ""
    try:
        params = {"page": 1, "page_size": 50, "q": f"departement_{dept}"}
        daten = _json(_get(f"{FR_DATENSATZ}?{urllib.parse.urlencode(params)}"), "data.gouv.fr")
        eintraege = daten.get("data") if isinstance(daten, dict) else None
        for r in eintraege if isinstance(eintraege, list) else []:
            u = r.get("url") if isinstance(r, dict) else None
            if fr_url_gilt(u, dept):
                url = u
                break
    except StationError:
        url = ""
    if not url:
        from datetime import date
        jahr = date.today().year
        url = f"{FR_DATEIEN}H_{dept}_latest-{jahr - 1}-{jahr}.csv.gz"
        if not fr_url_gilt(url, dept):                  # kein Département, das es gibt
            raise StationError(T("unerwartete Antwort: {antwort}", antwort=f"Météo-France {dept!r}"))
    ablegen(pfad, url)
    return url


def fr_lesen(zeilen, von: str, bis: str) -> tuple[list, dict]:
    """Die Département-Datei → (Stationen, {poste: {UTC-Stunde: {"kn","dir"}}}).

    Spalten mit Semikolon, Kopfzeile; laut Feldbeschreibung: NUM_POSTE (acht
    Ziffern, die ersten zwei das Département), NOM_USUEL, LAT, LON,
    AAAAMMJJHH (UTC), FF = Wind über 10 Minuten in 10 m (m/s), DD (Grad),
    hinter jedem Wert sein Qualitätscode (QFF, QDD): 9 gefiltert, 0 und 1
    geprüft, 2 zweifelhaft. Zweifelhafte Werte bleiben draußen.

    Als Station zählt nur, wer in der Datei irgendwann einen Wind gemeldet
    hat. Viele Posten messen nur Regen und Temperatur — die Sonde vom 20.09.
    nahm für Leucate den nächsten, Fitou (11144001), und fand „keine
    Stundenwerte“: Fitou hat die Spalte FF in keiner Zeile. Die Windstation
    Leucate (11202001) liegt 5 km weiter.
    """
    leser = csv.reader(zeilen, delimiter=";")
    kopf = None
    stationen: dict = {}
    fenster: dict = {}
    mit_wind: set = set()
    ohne_lage: set = set()
    for teile in leser:
        if kopf is None:
            kopf = [t.strip().upper() for t in teile]
            try:
                i_p, i_n = kopf.index("NUM_POSTE"), kopf.index("NOM_USUEL")
                i_lat, i_lon, i_t = kopf.index("LAT"), kopf.index("LON"), kopf.index("AAAAMMJJHH")
                i_f, i_d = kopf.index("FF"), kopf.index("DD")
            except ValueError as exc:
                raise StationError(T("Météo-France: Spalte fehlt ({fehler})", fehler=exc)) from exc
            i_qf = kopf.index("QFF") if "QFF" in kopf else None
            continue
        if len(teile) <= max(i_p, i_n, i_lat, i_lon, i_t, i_f, i_d):
            continue
        poste = teile[i_p].strip()
        if poste not in stationen:
            if poste in ohne_lage:
                continue
            lage = _lage(teile[i_lat], teile[i_lon])
            if lage is None:
                ohne_lage.add(poste)
                if len(ohne_lage) > FR_MAX_POSTEN:
                    raise StationError(T("unerwartete Antwort: {antwort}", antwort=f"Météo-France > {FR_MAX_POSTEN} LAT/LON"))
                continue
            if len(stationen) >= FR_MAX_POSTEN:
                raise StationError(T("unerwartete Antwort: {antwort}",
                                     antwort=f"Météo-France > {FR_MAX_POSTEN} NUM_POSTE"))
            stationen[poste] = {"id": poste, "name": teile[i_n].strip().title(),
                                "lat": lage[0], "lon": lage[1], "dept": poste[:2]}
        f_text = teile[i_f].strip()
        if not f_text:
            continue
        mit_wind.add(poste)
        stempel = teile[i_t].strip()
        if len(stempel) < 10:
            continue
        tag = f"{stempel[:4]}-{stempel[4:6]}-{stempel[6:8]}"
        if not (von <= tag <= bis):
            continue
        if i_qf is not None and teile[i_qf].strip() == "2":
            continue
        f = _wind_ms(f_text)
        if f is None:                                   # Text, negativ, nan, inf
            continue
        fenster.setdefault(poste, {})[f"{tag}T{stempel[8:10]}:00"] = {
            "kn": round(f * MS_ZU_KN, 1), "dir": _richtung(teile[i_d].strip() or None)}
    return [st for p, st in stationen.items() if p in mit_wind], fenster


def _zeilen_begrenzt(roh, datei: str, zeile_max: int | None = None, gesamt_max: int | None = None,
                     encoding: str = "utf-8", was: str = "Météo-France"):
    """Zeilen (Fehler beim Dekodieren ersetzt) aus einem binären Strom — dem
    entpackten gzip oder ZIP-Mitglied —, jede höchstens `zeile_max` Bytes,
    alle zusammen höchstens `gesamt_max`. Was darüber geht, ist ein
    StationError, bevor es im Speicher steht (C6). `roh.read(n)` muss dafür
    höchstens n Bytes entpacken — gzip und Deflate tun das, BZIP2 und LZMA
    in `zipfile` nicht (`ZIP_VERFAHREN`)."""
    zeile_max = zeile_max or FR_ZEILE_MAX
    gesamt_max = gesamt_max or FR_ENTPACKT_MAX

    def zu_lang(nr: int) -> StationError:
        return StationError(T("{datei} nicht lesbar, Zeile {zeile}: {grund}", datei=datei, zeile=nr,
                              grund=f"> {zeile_max // 1024} KB"))

    gesamt, nr, rest = 0, 0, b""
    while True:
        stueck = roh.read(64 * 1024)
        if not stueck:
            break
        gesamt += len(stueck)
        if gesamt > gesamt_max:
            raise StationError(T("{was}: {datei} ist entpackt größer als {mb} MB",
                                 was=was, datei=datei, mb=gesamt_max // (1024 * 1024)))
        teile = (rest + stueck).split(b"\n")
        rest = teile.pop()                              # angefangene Zeile — wartet aufs nächste Stück
        for zeile in teile:
            nr += 1
            if len(zeile) > zeile_max:
                raise zu_lang(nr)
            yield zeile.decode(encoding, "replace").rstrip("\r")
        if len(rest) > zeile_max:
            raise zu_lang(nr + 1)
    if rest:
        yield rest.decode(encoding, "replace").rstrip("\r")


def _fr_lesen_datei(datei: Path, von: str, bis: str) -> tuple[list, dict]:
    """Die gepackte Datei eines Départements lesen, als Strom mit Grenzen.
    Eine kaputte Datei (abgeschnitten, kein gzip) wird verworfen und beim
    nächsten Mal neu geholt, statt für immer an ihr zu scheitern."""
    try:
        with gzip.open(datei, "rb") as roh:
            return fr_lesen(_zeilen_begrenzt(roh, datei.name), von, bis)
    except (OSError, EOFError, zlib.error) as exc:
        _verwerfen(datei)
        raise StationError(T("{datei} nicht lesbar: {grund}", datei=datei.name, grund=type(exc).__name__)) from None


def _fr_datei(dept: str, bis: str) -> Path:
    """Die Datei des Départements — 5 bis 15 MB, deshalb nicht stündlich:
    Météo-France schreibt sie einmal am Tag, hier gilt sie sechs Stunden,
    und für einen Zeitraum, der länger als drei Tage zurückliegt, für immer —
    sofern sie geholt wurde, als er das schon tat (C15, siehe `_brauchbar`)."""
    from datetime import date
    pfad = _cache_pfad(f"fr_{dept}.csv.gz")
    try:
        geholt = pfad.stat().st_mtime
    except OSError:
        geholt = None
    gilt = False
    if geholt is not None:
        try:
            ende = date.fromisoformat(bis)
            gilt = (date.today() - ende).days > 3 and _endgueltig(geholt, ende)
        except ValueError:
            gilt = True
        gilt = gilt or _juenger_als(pfad, FRISCH_S)
    if not gilt:
        ablegen(pfad, _get(fr_datei_url(dept)))
    return pfad


def _fr_fenster(dept: str, von: str, bis: str) -> tuple[list, dict]:
    """Stationen und Stunden eines Départements im Zeitraum.

    Die Datei hat über hunderttausend Zeilen; gelesen wird sie einmal je
    Stand, und zwar gleich für den gefragten Zeitraum *und* die letzten drei
    Wochen — der Rückblick fragt danach mehrere Spots desselben Départements
    für dieselben Tage, ohne dass die Datei noch einmal durchlaufen wird.
    """
    from datetime import date
    datei = _fr_datei(dept, bis)
    merk = _cache_pfad(f"fr_{dept}_windfenster.json")
    try:
        merk_gilt = merk.stat().st_mtime >= datei.stat().st_mtime
    except OSError:
        merk_gilt = False
    if merk_gilt:
        daten = cache_lesen(merk, dict) or {}
        stationen = _stationen_ok(daten.get("stationen"))
        if (stationen is not None and isinstance(daten.get("fenster"), dict)
                and str(daten.get("von", "9")) <= von and str(daten.get("bis", "0")) >= bis):
            fenster = {poste: {k: v for k, v in st.items() if von <= k[:10] <= bis}
                       for poste, st in daten["fenster"].items() if isinstance(st, dict)}
            return stationen, fenster
    heute = date.today()
    lese_von = min(von, (heute - timedelta(days=21)).isoformat())
    lese_bis = max(bis, heute.isoformat())
    stationen, alles = _fr_lesen_datei(datei, lese_von, lese_bis)
    ablegen(merk, json.dumps({"von": lese_von, "bis": lese_bis, "stationen": stationen, "fenster": alles}))
    ablegen(_cache_pfad(f"fr_{dept}_windstationen.json"), json.dumps(stationen))
    fenster = {poste: {k: v for k, v in st.items() if von <= k[:10] <= bis} for poste, st in alles.items()}
    return stationen, fenster


def fr_stationen(spot: dict | None = None) -> list[dict]:
    """Die Stationen der Départements um den Spot. Ohne Spot: alles, was
    schon einmal geladen wurde — eine Liste ganz Frankreichs wäre 95 Dateien."""
    if spot is None:
        aus = []
        for pfad in sorted(CACHE_DIR.glob("fr_*_windstationen.json")) if CACHE_DIR.exists() else []:
            aus.extend(_stationen_ok(cache_lesen(pfad, list)) or [])
        return aus
    aus = []
    for dept in fr_departements(float(spot["lat"]), float(spot["lon"])):
        merk = _cache_pfad(f"fr_{dept}_windstationen.json")
        gemerkt = _stationen_ok(cache_lesen(merk, list)) if _juenger_als(merk, 30 * 24 * 3600) else None
        if gemerkt is not None:
            aus.extend(gemerkt)
            continue
        # Noch nie geladen: die Datei holen und lesen — die Stationsliste
        # fällt dabei ab, die letzten drei Wochen liegen danach im Cache.
        from datetime import date
        heute = date.today()
        stationen, _ = _fr_fenster(dept, heute.isoformat(), heute.isoformat())
        aus.extend(stationen)
    return aus


def fr_stunden(station: dict, von: str, bis: str) -> dict:
    dept = str(station.get("dept") or str(station["id"])[:2])
    _, fenster = _fr_fenster(dept, von, bis)
    stunden = fenster.get(str(station["id"])) or {}
    if not stunden:
        raise StationError(T("Météo-France {station}: keine Stundenwerte im Zeitraum", station=station["id"]))
    return {"quelle": "Météo-France", "station": station, "stunden": stunden}


# ── DMI (Dänemark) ───────────────────────────────────────────────────────────
#
# Das Dänische Meteorologische Institut veröffentlicht die Messwerte seiner
# Stationen über die „Open Data“-Schnittstelle metObs v2
# (opendataapi.dmi.dk/v2/metObs), GeoJSON, ohne Schlüssel — am 20.09.2026 im
# Browser geprüft, 14:17 MESZ:
#
#   Stationen  …/collections/station/items: `stationId`, `name`, `country`
#              („DNK“, daneben Grönland und Färöer), `status` („Active“),
#              `validTo` (null = gilt noch; dieselbe Station steht mit jeder
#              Verlegung einmal da), `parameterId` (Liste, darin `wind_speed`
#              und `wind_dir`), Lage in `geometry.coordinates` [lon, lat].
#   Werte      …/collections/observation/items?stationId=…&parameterId=
#              wind_speed&datetime=<von>Z/<bis>Z: je Feature `observed` (UTC,
#              alle zehn Minuten) und `value` (m/s bzw. Grad). Bis zu dem, was
#              gerade gemessen wurde (12:10 UTC um 12:17 UTC).
#
# Bis 1.13 bekam ein dänischer Spot bestenfalls die deutsche Station auf
# Sylt; jetzt die nächste dänische.

DMI_BASIS = "https://opendataapi.dmi.dk/v2/metObs/collections/"


def dmi_stationen_aus(daten: object) -> list[dict]:
    """Station-Antwort → aktive dänische Stationen mit Windmessung, je Station
    die gültige Lage (validTo leer)."""
    aus = {}
    for f in (daten.get("features") or []) if isinstance(daten, dict) else []:
        p = f.get("properties") or {}
        params = p.get("parameterId") or []
        if (p.get("country") or "") != "DNK" or p.get("status") != "Active" or p.get("validTo"):
            continue
        if "wind_speed" not in params:
            continue
        try:
            lon, lat = (float(v) for v in (f.get("geometry") or {}).get("coordinates")[:2])
        except (TypeError, ValueError, IndexError, AttributeError):
            continue
        if _lage(lat, lon) is None:
            continue
        sid = str(p.get("stationId") or "")
        if sid:
            aus[sid] = {"id": sid, "name": str(p.get("name") or sid), "lat": round(lat, 5), "lon": round(lon, 5),
                        "dienst": "DMI", "richtung": "wind_dir" in params}
    return sorted(aus.values(), key=lambda s: s["id"])


def dmi_stationen() -> list[dict]:
    """Die dänischen Windstationen — eine Woche gemerkt."""
    pfad = _cache_pfad("dmi_stationen.json")
    if _juenger_als(pfad, 7 * 24 * 3600):
        gemerkt = _stationen_ok(cache_lesen(pfad, list))
        if gemerkt is not None:
            return gemerkt
    daten = _json(_get(f"{DMI_BASIS}station/items?limit=10000"), "DMI")
    aus = dmi_stationen_aus(daten)
    if not aus:
        raise StationError(T("DMI: keine aktive dänische Windstation in der Antwort"))
    ablegen(pfad, json.dumps(aus))
    return aus


def dmi_werte(daten: object) -> list:
    """Observation-Antwort → [(datetime UTC, Wert)]."""
    aus = []
    for f in (daten.get("features") or []) if isinstance(daten, dict) else []:
        p = (f.get("properties") or {}) if isinstance(f, dict) else {}
        try:
            t = datetime.fromisoformat(str(p.get("observed")).replace("Z", "+00:00"))
            v = float(p.get("value"))
            if t.tzinfo is not None:
                t = (t - t.utcoffset()).replace(tzinfo=None)
        except (TypeError, ValueError, OverflowError, AttributeError):
            continue
        aus.append((t, v))
    return aus


def dmi_stunden(station: dict, von: str, bis: str) -> dict:
    """Zehnminutenwerte zu Stundenmitteln, m/s → Knoten."""
    sid = str(station["id"])
    reihen = {}
    for param in ("wind_speed", "wind_dir"):
        pfad = _cache_pfad(f"dmi_{sid}_{param}_{von}_{bis}.json")
        daten = cache_lesen(pfad, dict) if _brauchbar(pfad, bis) else None
        if daten is None:
            params = {"stationId": sid, "parameterId": param, "limit": 20000,
                      "datetime": f"{von}T00:00:00Z/{bis}T23:59:59Z"}
            daten = _json(_get(f"{DMI_BASIS}observation/items?{urllib.parse.urlencode(params)}"), "DMI")
            ablegen(pfad, json.dumps(daten))
        reihen[param] = dmi_werte(daten)
    speed = [(t, v) for t, v in reihen["wind_speed"] if _wind_ms(v) is not None]
    if not speed:
        return {"quelle": "DMI", "station": station, "stunden": {},
                "hinweis": T("DMI hat für diese Tage keine Windwerte geliefert")}
    richtung = {t: d for t, d in reihen["wind_dir"] if _richtung(d) is not None}
    stunden = {k: v for k, v in _mittel_je_stunde([(t, v, richtung.get(t)) for t, v in speed]).items()
               if von <= k[:10] <= bis}
    return {"quelle": "DMI", "station": station, "stunden": stunden}


# ── Zuordnung Spot ↔ Station ─────────────────────────────────────────────────

# Je Land: Anzeigename, Stationsliste (nimmt einen Spot entgegen — Frankreich
# lädt nur die Départements um ihn herum), Stundenwerte.
QUELLEN = {
    "DE": ("DWD", lambda spot=None: dwd_stationen(), dwd_stunden),
    "NL": ("KNMI/RWS", nl_stationen, nl_stunden),
    "AT": ("GeoSphere", lambda spot=None: geosphere_stationen(), geosphere_stunden),
    "FR": ("Météo-France", fr_stationen, fr_stunden),
    "DK": ("DMI", lambda spot=None: dmi_stationen(), dmi_stunden),
    "WG": ("Windguru", windguru_stationen, windguru_stunden),     # kein Land: nur, was in der Konfiguration steht
}
JE_SPOT = {"FR"}          # Stationsliste hängt am Spot, nicht am Land
LANDESWEIT = ("DE", "NL", "AT", "DK", "WG")   # Listen, die für jeden Spot gelten — auch über die Grenze


def naechste_station(spot: dict, stationen: list[dict], max_km: float) -> tuple[dict | None, float]:
    beste, d_beste = None, max_km
    for st in stationen:
        d = haversine_km(spot["lat"], spot["lon"], st["lat"], st["lon"])
        if d < d_beste:
            beste, d_beste = st, d
    return beste, d_beste


def naechste_stationen(spot: dict, stationen: list[dict], max_km: float) -> list[tuple[dict, float]]:
    """Alle Stationen in Reichweite, die nächste zuerst — falls die erste
    keine Winddaten liefert (Tholen im ersten Lauf), kommt die zweite dran."""
    aus = []
    for st in stationen:
        d = haversine_km(spot["lat"], spot["lon"], st["lat"], st["lon"])
        if d < max_km:
            aus.append((st, round(d, 1)))
    aus.sort(key=lambda x: (x[1], x[0]["id"]))
    return aus


def paare_finden(spots, max_km: float = 12.0, log=None, laender=None, dienste=None) -> list[dict]:
    """Spots mit einer Station in Reichweite, nach Entfernung sortiert.

    Rückgabe: [{"spot": spot, "quelle": "DWD", "station": {...}, "km": 4.2,
    "ersatz": [die nächsten fünf weiteren Stationen]}]. Ein Dienst, der nicht
    antwortet, kostet seine Paare, nicht die anderen. `laender` beschränkt die
    Spots auf diese Länder — Frankreich kostet je Département eine Datei von
    5 bis 15 MB, das will man beim Prüfstand nicht immer. `dienste` beschränkt
    die Stationslisten auf diese Kürzel aus QUELLEN (die Sonde fragt jeden
    Dienst für sich); ohne Angabe zählen alle.
    """
    say = log or (lambda *a: None)
    if laender is not None:
        erlaubt = {str(l).upper() for l in laender}
        spots = [s for s in spots if (s.get("country") or "").upper() in erlaubt]
    if not spots:
        return []
    zugelassen = None if dienste is None else {str(d).upper() for d in dienste}
    # Die landesweiten Listen gelten für jeden Spot: ein Spot in Belgien
    # bekommt die KNMI-Station in Cadzand, einer auf Sylt womöglich die
    # dänische in Højer. Nur Frankreich hängt am Spot (je Département eine Datei).
    stationen_alle: list = []
    for land in LANDESWEIT:
        if (zugelassen is not None and land not in zugelassen) or land not in QUELLEN:
            continue
        name, lade, _ = QUELLEN[land]
        try:
            for st in lade():
                st = dict(st)
                st.setdefault("dienst", name)
                st["_land"] = land
                stationen_alle.append(st)
        except Exception as exc:                        # noqa: BLE001
            say("    " + T("{dienst}: Stationsliste nicht abrufbar ({fehler})", dienst=name, fehler=exc))
    paare = []
    for spot in spots:
        land = (spot.get("country") or "").upper()
        kandidaten = list(stationen_alle)
        if land in JE_SPOT and land in QUELLEN and (zugelassen is None or land in zugelassen):
            name, lade, _ = QUELLEN[land]
            try:
                for st in lade(spot):
                    st = dict(st)
                    st.setdefault("dienst", name)
                    st["_land"] = land
                    kandidaten.append(st)
            except Exception as exc:                    # noqa: BLE001
                say("    " + T("{dienst}: Stationen um {spot} nicht abrufbar ({fehler})",
                              dienst=name, spot=spot.get("name", spot["id"]), fehler=exc))
        reihe = naechste_stationen(spot, kandidaten, max_km)
        if reihe:
            st, km = reihe[0]
            paare.append({"spot": spot, "quelle": st.get("dienst") or QUELLEN[st["_land"]][0],
                          "station": st, "km": km, "ersatz": [s for s, _ in reihe[1:6]]})
    paare.sort(key=lambda p: (p["km"], p["spot"]["id"]))
    return paare


def stunden_fuer_station(station: dict, von: str, bis: str) -> dict:
    """Die Stundenwerte einer Station — welcher Dienst, sagt die Station selbst."""
    land = station.get("_land")
    if not land:
        dienst = str(station.get("dienst") or "")
        land = next((l for l, (n, _, _) in QUELLEN.items() if n == dienst or dienst in n.split("/")), None)
    if land not in QUELLEN:
        raise StationError(T("Station {station}: kein Dienst bekannt", station=station.get("id")))
    _, _, lade = QUELLEN[land]
    return lade(station, von, bis)


def stunden_fuer(paar: dict, von: str, bis: str) -> dict:
    station = dict(paar["station"])
    if not station.get("_land") and not station.get("dienst"):
        # Paare aus der Grundlinie (vor 1.13.0): der Dienst steht am Paar
        station["dienst"] = paar.get("quelle") or ""
        land = (paar["spot"].get("country") or "").upper()
        if land in QUELLEN and not station["dienst"]:
            station["_land"] = land
    return stunden_fuer_station(station, von, bis)
