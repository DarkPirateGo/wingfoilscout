"""Einzelne Felder in spots.yaml ändern, ohne die Datei neu zu schreiben.

PyYAML kann die Datei laden und wieder ausgeben — dabei gingen aber sämtliche
Kommentare verloren, und `spots.yaml` besteht zu einem guten Teil aus
Kommentaren: Herkunft der Einträge, Bedeutung der Felder, Notizen je Spot. Der
Katalog ist das eigentliche Asset; ihn für eine Koordinatenkorrektur
umzuformatieren wäre ein schlechter Tausch.

Deshalb wird hier auf Textebene gearbeitet: den Block des Spots finden, in
diesem Block die betroffene Zeile ersetzen, alles andere unangetastet lassen.
Ein Block beginnt mit `- id: <kennung>` am Zeilenanfang und endet vor dem
nächsten `- ` in Spalte 1.
"""
from __future__ import annotations
import math
import os
import re
from pathlib import Path

from .i18n import T, TN, N_                                       # noqa: F401
from .config import BINAER


def schreibe_atomar(pfad: str | Path, text: str) -> None:
    """Erst in eine Nachbardatei, dann umbenennen — ein Leser sieht die alte
    Fassung oder die neue, nie eine halbe. `write_text` direkt auf den Katalog
    ließ die Oberfläche mit einem halben YAML in `load_spots` laufen, wenn
    sie in dem Moment die Startseite baute.

    Die Nachbardatei bekommt die Rechte der Datei, die sie ersetzt — eine neue
    nur 0600. Bis 2.1.0 entstand sie mit den Standardrechten, und nach
    „Übernehmen“ im Tagebuch war `config.yaml` (Startpunkt, Passwörter) für
    jeden Benutzer des Rechners lesbar statt 0600 (Review 04.10.2026, A3/C13).
    Ein Rest von einem abgebrochenen Lauf wird vorher entfernt, sonst behielte
    er seine alten Rechte; scheitert das Schreiben, verschwindet die
    Nachbardatei wieder."""
    pfad = Path(pfad)
    tmp = pfad.with_name(pfad.name + ".neu")
    try:
        modus = os.stat(pfad).st_mode & 0o777
    except FileNotFoundError:
        modus = 0o600
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    # Binär und ohne Übersetzung der Zeilenenden — unter Windows sonst doppelt
    # (config.BINAER).
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | BINAER, modus)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, pfad)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class SpotNichtGefunden(LookupError):
    pass


def _block(zeilen: list[str], spot_id: str) -> tuple[int, int]:
    """(erste, letzte+1) Zeile des Blocks — oder SpotNichtGefunden."""
    start = None
    for i, z in enumerate(zeilen):
        if start is None:
            if re.match(rf"-\s+id:\s*{re.escape(spot_id)}\s*$", z.rstrip()):
                start = i
            continue
        if z.startswith("- "):
            return start, i
    if start is None:
        raise SpotNichtGefunden(spot_id)
    return start, len(zeilen)


def _einrueckung(zeilen: list[str], von: int, bis: int) -> str:
    """Die Einrückung der Felder des Spots selbst — die der ersten Zeile nach
    `- id:`, sonst zwei Leerzeichen."""
    for i in range(von + 1, bis):
        if zeilen[i].strip() and not zeilen[i].lstrip().startswith("#"):
            return zeilen[i][:len(zeilen[i]) - len(zeilen[i].lstrip())]
    return "  "


def steuerzeichen_raus(text: str) -> str:
    """Alles unter 0x20 außer Zeilenumbruch und Tabulator, dazu DEL und die
    C1-Zeichen, verschwindet. PyYAML lehnt sie auch in Anführungszeichen ab
    („special characters are not allowed“) — ein `\x01` im Spotnamen machte
    bis 1.18.3 den ganzen Katalog unlesbar (Review 25.09., S4).

    Ebenso einzelne Surrogate (U+D800–DFFF): Python hält sie in einem Text,
    YAML schreibt sie als `"\\uD800"` und liest sie zurück, aber keine Seite
    kann sie als UTF-8 ausgeben (Review 04.10.2026, C2)."""
    return "".join(c for c in text
                   if c in "\n\t" or (ord(c) >= 32 and ord(c) != 127 and not 0x80 <= ord(c) <= 0x9F
                                      and not 0xD800 <= ord(c) <= 0xDFFF))


def _unterblock(zeilen: list[str], von: int, bis: int, feld: str) -> bool:
    """Steht das Feld als Block da — `feld:` ohne Wert, `feld: |` oder `feld: >`
    mit eingerückten Kindern?"""
    einr = _einrueckung(zeilen, von, bis)
    kopf = re.compile(rf"^{re.escape(einr)}{re.escape(feld)}:\s*([|>][-+0-9]*)?\s*$")
    for i in range(von, bis):
        if kopf.match(zeilen[i]):
            return i + 1 < bis and (not zeilen[i + 1].strip()
                                    or len(zeilen[i + 1]) - len(zeilen[i + 1].lstrip()) > len(einr))
    return False


def _feld_muster(zeilen: list[str], von: int, bis: int, feld: str) -> re.Pattern:
    """Nur ein Feld auf der Ebene des Spots, nie eines in einem Unterblock.
    Bis 1.13 traf `name:` die erste Zeile mit diesem Namen — bei einem Spot
    mit Thermikblock war das `thermal: name: "Nordwind"`, nicht der Spotname
    (gefunden beim Umbenennen der Pins am 20.09.)."""
    return re.compile(rf"^{re.escape(_einrueckung(zeilen, von, bis))}{re.escape(feld)}:\s")


def _feld_ende(zeilen: list[str], i: int, bis: int, einr: str) -> int:
    """Erste Zeile hinter dem Feld, das in Zeile `i` beginnt. Dazu gehört
    alles, was tiefer eingerückt folgt: die Kinder eines Blocks — und die
    Fortsetzungszeilen eines umgebrochenen Werts. `notes:` steht im Katalog
    oft als mehrzeiliger Text; wer nur die Kopfzeile ersetzte, ließ den Rest
    als Waisen stehen, und YAML las die Datei nicht mehr (gefunden am
    29.09.2026 beim Kürzen von 163 Notizen). Leerzeilen am Ende gehören dem
    Nachbarn, nicht dem Feld."""
    ende = i + 1
    while ende < bis and (not zeilen[ende].strip()
                          or len(zeilen[ende]) - len(zeilen[ende].lstrip()) > len(einr)):
        ende += 1
    while ende > i + 1 and not zeilen[ende - 1].strip():
        ende -= 1
    return ende


def _setze_feld(zeilen: list[str], von: int, bis: int, feld: str, wert: str) -> None:
    """Feld im Block ersetzen — samt Fortsetzungszeilen — oder direkt hinter
    `id:` einfügen."""
    muster = _feld_muster(zeilen, von, bis, feld)
    einr = _einrueckung(zeilen, von, bis)
    for i in range(von, bis):
        if muster.match(zeilen[i]):
            zeilen[i:_feld_ende(zeilen, i, bis, einr)] = [f"{einr}{feld}: {wert}\n"]
            return
    zeilen.insert(von + 1, f"{einr}{feld}: {wert}\n")


def set_coords(pfad: str | Path, spot_id: str, lat: float, lon: float) -> None:
    """Koordinate eines Spots ändern. Sechs Nachkommastellen sind ~10 cm."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        # Die Prüfseite zeigt die Meldung („Konnte nicht speichern: …“)
        raise ValueError(T("Koordinate außerhalb des Gültigen: {lat}, {lon}", lat=lat, lon=lon))
    pfad = Path(pfad)
    zeilen = pfad.read_text(encoding="utf-8").splitlines(keepends=True)
    von, bis = _block(zeilen, spot_id)
    _setze_feld(zeilen, von, bis, "lat", f"{lat:.6f}".rstrip("0").rstrip("."))
    _setze_feld(zeilen, von, bis, "lon", f"{lon:.6f}".rstrip("0").rstrip("."))
    _setze_feld(zeilen, von, bis, "verified", "true")
    schreibe_atomar(pfad, "".join(zeilen))


def set_block(pfad: str | Path, spot_id: str, feld: str, zeilen_neu: list[str]) -> None:
    """Einen verschachtelten Block im Spot ersetzen oder anlegen (z. B. `thermal:`).

    `zeilen_neu` sind die Kindzeilen ohne Einrückung; die Einrückung setzt diese
    Funktion. Ein vorhandener Block wird mitsamt seinen Kindern ersetzt, alles
    andere im Spot bleibt stehen.
    """
    if not re.fullmatch(r"[a-z_]+", feld):
        raise ValueError(f"Unerwarteter Feldname: {feld}")
    pfad = Path(pfad)
    zeilen = pfad.read_text(encoding="utf-8").splitlines(keepends=True)
    von, bis = _block(zeilen, spot_id)

    kopf = re.compile(rf"^(\s+){re.escape(feld)}:\s*$")
    start = ende = None
    for i in range(von, bis):
        if kopf.match(zeilen[i]):
            start = i
            tiefe = len(zeilen[i]) - len(zeilen[i].lstrip())
            ende = i + 1
            while ende < bis and (not zeilen[ende].strip()
                                  or len(zeilen[ende]) - len(zeilen[ende].lstrip()) > tiefe):
                ende += 1
            break

    # Mit der Einrückung des Blocks, nicht fest zwei und vier Leerzeichen: bei
    # einem Spot mit vier wanderten name, lat, lon sonst unter den neuen
    # Block (Review 25.09., S11).
    einr = _einrueckung(zeilen, von, bis)
    neu = [f"{einr}{feld}:\n"] + [f"{einr}  {z}\n" for z in zeilen_neu]
    if start is None:
        zeilen[von + 1:von + 1] = neu
    else:
        zeilen[start:ende] = neu
    schreibe_atomar(pfad, "".join(zeilen))


def set_flag(pfad: str | Path, spot_id: str, feld: str, wert: bool) -> None:
    """Ein Wahrheitsfeld setzen, etwa `geo_ok: true` für „habe ich angesehen"."""
    if not re.fullmatch(r"[a-z_]+", feld):
        raise ValueError(f"Unerwarteter Feldname: {feld}")
    pfad = Path(pfad)
    zeilen = pfad.read_text(encoding="utf-8").splitlines(keepends=True)
    von, bis = _block(zeilen, spot_id)
    _setze_feld(zeilen, von, bis, feld, "true" if wert else "false")
    schreibe_atomar(pfad, "".join(zeilen))


def set_zahl(pfad: str | Path, spot_id: str, feld: str, wert: float) -> None:
    """Ein Zahlenfeld setzen, etwa `wind_factor: 1.15` (seit 1.16.0 aus dem
    Session-Tagebuch). Geschrieben wird die kürzeste Form, die YAML wieder als
    dieselbe Zahl liest — `1.0`, nicht `1`, damit die Spalte einheitlich bleibt."""
    if not re.fullmatch(r"[a-z_]+", feld):
        raise ValueError(f"Unerwarteter Feldname: {feld}")
    wert = float(wert)
    if not math.isfinite(wert):
        raise ValueError(f"Keine Zahl: {wert}")
    pfad = Path(pfad)
    zeilen = pfad.read_text(encoding="utf-8").splitlines(keepends=True)
    von, bis = _block(zeilen, spot_id)
    _setze_feld(zeilen, von, bis, feld, repr(round(wert, 3)))
    schreibe_atomar(pfad, "".join(zeilen))


def set_text(pfad: str | Path, spot_id: str, feld: str, wert: str) -> None:
    """Ein Textfeld setzen, etwa `country: AL` oder den Kommentar. Der Wert
    kommt in Anführungszeichen, damit YAML ihn nie umdeutet — `no` wäre sonst
    False; Zeilenumbrüche werden als `\\n` geschrieben, was YAML in
    Anführungszeichen wieder zu Umbrüchen macht. Ein leerer Wert nimmt das
    Feld aus dem Block."""
    if not re.fullmatch(r"[a-z_]+", feld):
        raise ValueError(f"Unerwarteter Feldname: {feld}")
    wert = steuerzeichen_raus(str(wert).replace("\r\n", "\n").replace("\r", "\n"))
    pfad = Path(pfad)
    zeilen = pfad.read_text(encoding="utf-8").splitlines(keepends=True)
    von, bis = _block(zeilen, spot_id)
    # Ein von Hand geschriebener Block-Skalar (`comment: |` mit eingerückten
    # Zeilen) wird samt Kindern ersetzt — bis 1.18.3 blieb die Kopfzeile
    # allein übrig und die Kinder standen als Waisen da (Review 25.09., S11).
    if _unterblock(zeilen, von, bis, feld):
        entferne_feld(pfad, spot_id, feld)
        zeilen = pfad.read_text(encoding="utf-8").splitlines(keepends=True)
        von, bis = _block(zeilen, spot_id)
    if wert == "":
        muster = _feld_muster(zeilen, von, bis, feld)
        einr = _einrueckung(zeilen, von, bis)
        for i in range(von, bis):
            if muster.match(zeilen[i]):
                del zeilen[i:_feld_ende(zeilen, i, bis, einr)]
                break
    else:
        roh = wert.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
        _setze_feld(zeilen, von, bis, feld, '"' + roh + '"')
    schreibe_atomar(pfad, "".join(zeilen))


def entferne_feld(pfad: str | Path, spot_id: str, feld: str) -> bool:
    """Ein Feld aus dem Block nehmen — ein einfaches wie `tidal: true` samt
    Zeile, einen Unterblock wie `tide:` samt seiner Kinder. Zurück kommt, ob
    etwas da war. `set_text(…, "")` kann das nur für einfache Felder; ein
    Blockkopf ohne Kinder ließe die Kinder als Waisen stehen, und YAML
    läse den Spot danach nicht mehr."""
    if not re.fullmatch(r"[a-z_]+", feld):
        raise ValueError(f"Unerwarteter Feldname: {feld}")
    pfad = Path(pfad)
    zeilen = pfad.read_text(encoding="utf-8").splitlines(keepends=True)
    von, bis = _block(zeilen, spot_id)
    einr = _einrueckung(zeilen, von, bis)
    kopf = re.compile(rf"^{re.escape(einr)}{re.escape(feld)}:(\s|$)")
    for i in range(von, bis):
        if not kopf.match(zeilen[i]):
            continue
        del zeilen[i:_feld_ende(zeilen, i, bis, einr)]
        schreibe_atomar(pfad, "".join(zeilen))
        return True
    return False


def entferne(pfad: str | Path, spot_id: str) -> str:
    """Den Block eines Spots aus der Datei nehmen; zurück kommt der entfernte
    Text, damit der Aufrufer ihn ins Protokoll schreiben kann. Kommentare vor
    dem Block bleiben stehen — sie hängen am Vorgänger, nicht am Spot."""
    pfad = Path(pfad)
    zeilen = pfad.read_text(encoding="utf-8").splitlines(keepends=True)
    von, bis = _block(zeilen, spot_id)
    # Leerzeilen direkt hinter dem Block gehören zu ihm; steht er am Ende der
    # Datei (so hängt „Spots hinzufügen“ an), auch die Leerzeile davor.
    while bis < len(zeilen) and not zeilen[bis].strip():
        bis += 1
    if bis >= len(zeilen):
        while von > 0 and not zeilen[von - 1].strip():
            von -= 1
    weg = "".join(zeilen[von:bis])
    del zeilen[von:bis]
    schreibe_atomar(pfad, "".join(zeilen))
    return weg

