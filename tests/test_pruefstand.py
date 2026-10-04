"""Der Prüfstand selbst, ohne Netz: Parser der Messdienste, Fehlermaße, die
Prüfungen an synthetischen Antworten, Grundlinienvergleich.

Die echten Dienste wurden beim Bau nicht erreicht (kein Netz im Prüfraum).
Die Formate hier sind die veröffentlichten — der erste Lauf mit Netz
(`tools/pruefstand.py --sonde`) zeigt, ob sie noch stimmen.
"""
from __future__ import annotations
import json
import tempfile
import unittest
import urllib.parse
from unittest import mock
from datetime import datetime
from pathlib import Path

from tests.helpers import cfg as load_cfg, ROOT
from wingscout import pruefstand as ps
from wingscout.sources import stationen

DWD_LISTE = """Stations_id von_datum bis_datum Stationshoehe geoBreite geoLaenge Stationsname Bundesland Abgabe
----------- --------- --------- ------------- --------- --------- ----------------------------------------- ---------- ------
05516 19730101 20260915             4     54.5279   11.0616 Fehmarn                                  Schleswig-Holstein Frei
02115 19370101 20260915            26     55.0110    8.4125 List auf Sylt                            Schleswig-Holstein Frei
00433 19510101 20260915            48     52.4675   13.4021 Berlin-Tempelhof                         Berlin Frei
"""

DWD_PRODUKT = """STATIONS_ID;MESS_DATUM;QN_3;   F;   D;eor
       5516;2026080112;    3;   6.2; 250;eor
       5516;2026080113;    3;   7.7; 260;eor
       5516;2026080114;    3;-999;-999;eor
"""

KNMI_CSV = """# BRON: KONINKLIJK NEDERLANDS METEOROLOGISCH INSTITUUT (KNMI)
# STN      LON(east)   LAT(north)  ALT(m)      NAME
# 267:         5.384       52.898      -1.30       STAVOREN
# DD        : Windrichting (in graden) gemiddeld over de laatste 10 minuten
# FH        : Uurgemiddelde windsnelheid (in 0.1 m/s)
# STN,YYYYMMDD,   HH,   DD,   FH,   FX
  267,20260801,    1,  240,   60,   80
  267,20260801,   13,  270,   77,  110
  267,20260801,   24,  990,   40,   60
"""

GEOSPHERE = {
    "timestamps": ["2026-08-01T12:00+00:00", "2026-08-01T13:00+00:00", "2026-08-01T14:00+00:00"],
    "features": [{"type": "Feature", "properties": {"station": "5904", "parameters": {
        "ff": {"name": "Windgeschwindigkeit", "unit": "m/s", "data": [6.2, 7.7, None]},
        "dd": {"name": "Windrichtung", "unit": "°", "data": [250, 260, 270]}}}}],
}


class Messdienste(unittest.TestCase):
    def test_dwd_stationsliste(self):
        liste = stationen.dwd_stationsliste(DWD_LISTE)
        self.assertEqual([s["id"] for s in liste], ["05516", "02115", "00433"])
        self.assertEqual(liste[1]["name"], "List auf Sylt")
        self.assertAlmostEqual(liste[0]["lat"], 54.5279)
        self.assertAlmostEqual(liste[0]["lon"], 11.0616)

    def test_dwd_produkt_in_knoten_und_utc(self):
        st = stationen.dwd_produkt(DWD_PRODUKT)
        self.assertEqual(sorted(st), ["2026-08-01T12:00", "2026-08-01T13:00"])   # -999 fehlt
        self.assertAlmostEqual(st["2026-08-01T12:00"]["kn"], 12.1, places=1)      # 6,2 m/s
        self.assertEqual(st["2026-08-01T13:00"]["dir"], 260.0)

    def test_knmi_kopf_und_stunden(self):
        kopf, st = stationen.knmi_antwort(KNMI_CSV)
        self.assertEqual(kopf["id"], "267")
        self.assertAlmostEqual(kopf["lat"], 52.898)
        self.assertEqual(kopf["name"], "Stavoren")
        self.assertEqual(stationen.knmi_antwort(KNMI_CSV.replace("STAVOREN", "IJMUIDEN"))[0]["name"], "IJmuiden")
        # Stunde 1 endet um 01 UTC → gehört zur Stunde, die um 00 beginnt
        self.assertIn("2026-08-01T00:00", st)
        self.assertAlmostEqual(st["2026-08-01T00:00"]["kn"], 11.7, places=1)     # 6,0 m/s
        self.assertEqual(st["2026-08-01T12:00"]["dir"], 270.0)
        self.assertIn("2026-08-01T23:00", st)                                     # Stunde 24
        self.assertIsNone(st["2026-08-01T23:00"]["dir"])                          # 990 = drehend

    def test_geosphere(self):
        st = stationen.geosphere_antwort(GEOSPHERE)
        self.assertEqual(sorted(st), ["2026-08-01T12:00", "2026-08-01T13:00"])
        self.assertAlmostEqual(st["2026-08-01T13:00"]["kn"], 15.0, places=1)
        self.assertEqual(st["2026-08-01T12:00"]["dir"], 250.0)

    def test_naechste_station_und_paare(self):
        spots = [{"id": "a", "name": "A", "country": "DE", "lat": 54.53, "lon": 11.06},
                 {"id": "b", "name": "B", "country": "DE", "lat": 50.0, "lon": 8.0}]
        liste = stationen.dwd_stationsliste(DWD_LISTE)
        st, km = stationen.naechste_station(spots[0], liste, 12.0)
        self.assertEqual(st["id"], "05516")
        self.assertLess(km, 1.0)
        self.assertEqual(stationen.naechste_station(spots[1], liste, 12.0), (None, 12.0))
        paare = ps.paare_waehlen([
            {"spot": spots[0], "quelle": "DWD", "station": {"id": "1"}, "km": 1.0},
            {"spot": spots[1], "quelle": "DWD", "station": {"id": "2"}, "km": 2.0},
            {"spot": spots[1], "quelle": "KNMI", "station": {"id": "3"}, "km": 3.0},
            {"spot": spots[1], "quelle": "KNMI", "station": {"id": "3"}, "km": 4.0},   # Station doppelt
        ], 3)
        self.assertEqual([p["quelle"] for p in paare], ["DWD", "KNMI", "DWD"])       # abwechselnd
        self.assertEqual(len({p["station"]["id"] for p in paare}), 3)


DWD_NOW = """STATIONS_ID;MESS_DATUM;QN;FF_10;DD_10;eor
       5516;202609181200;    1;   6.0; 350;eor
       5516;202609181210;    1;   6.0;  10;eor
       5516;202609181220;    1;   6.0; 350;eor
       5516;202609181230;    1;   6.0;  10;eor
       5516;202609181240;    1;   6.0; 350;eor
       5516;202609181250;    1;   6.0;  10;eor
       5516;202609181300;    1;   8.0; 270;eor
       5516;202609181310;    1;-999;-999;eor
       5516;202609181320;    1;   8.0; 270;eor
"""

FR_CSV = """NUM_POSTE;NOM_USUEL;LAT;LON;ALTI;AAAAMMJJHH;RR1;QRR1;FF;QFF;DD;QDD;FXI;QFXI
29075001;BREST-GUIPAVAS;48.444167;-4.412;94;2026091712;0.0;1;6.2;1;250;1;9.8;1
29075001;BREST-GUIPAVAS;48.444167;-4.412;94;2026091713;0.0;1;7.7;9;260;9;11.0;9
29075001;BREST-GUIPAVAS;48.444167;-4.412;94;2026091714;0.0;1;9.9;2;270;2;12.0;2
29075001;BREST-GUIPAVAS;48.444167;-4.412;94;2026091715;0.0;1;;;;;;
29024001;OUESSANT-STIFF;48.469;-5.058;68;2026091712;0.0;1;12.4;1;280;1;16.0;1
29024001;OUESSANT-STIFF;48.469;-5.058;68;2026091612;0.0;1;10.0;1;280;1;16.0;1
29199001;OHNE-WIND;48.30;-4.50;9;2026091712;0.4;1;;;;;;
29199001;OHNE-WIND;48.30;-4.50;9;2026091713;0.0;1;;;;;;
"""

GEOSPHERE_10MIN = {
    "timestamps": [f"2026-09-18T12:{m:02d}+00:00" for m in range(0, 60, 10)],
    "features": [{"type": "Feature", "properties": {"station": "11035", "parameters": {
        "FF": {"name": "Windgeschwindigkeit", "unit": "m/s", "data": [5.0, 5.0, 5.0, 5.0, 5.0, None]},
        "DD": {"name": "Windrichtung", "unit": "°", "data": [90, 90, 90, 90, 90, 90]}}}}],
}


class Echtzeit(unittest.TestCase):
    """Die Quellen für den laufenden Tag: Zehnminutenwerte zu Stunden."""

    def test_dwd_now_zu_stundenmitteln(self):
        st = stationen.dwd_now_produkt(DWD_NOW)
        self.assertEqual(sorted(st), ["2026-09-18T12:00"])                 # 13 Uhr hat nur zwei Werte
        self.assertAlmostEqual(st["2026-09-18T12:00"]["kn"], 6.0 * stationen.MS_ZU_KN, places=1)
        # 350° und 10° mitteln sich um Nord, nicht um Süd
        d = st["2026-09-18T12:00"]["dir"]
        self.assertTrue(d < 5 or d > 355, d)

    def test_geosphere_zehnminuten(self):
        reihen = stationen._geosphere_reihen(GEOSPHERE_10MIN)
        self.assertEqual(len(reihen), 5)
        st = stationen._mittel_je_stunde(reihen)
        self.assertAlmostEqual(st["2026-09-18T12:00"]["kn"], 5.0 * stationen.MS_ZU_KN, places=1)
        self.assertAlmostEqual(st["2026-09-18T12:00"]["dir"], 90.0, places=1)
        # Einheit km/h wird umgerechnet
        kmh = json.loads(json.dumps(GEOSPHERE_10MIN))
        kmh["features"][0]["properties"]["parameters"]["FF"]["unit"] = "km/h"
        self.assertAlmostEqual(stationen._geosphere_reihen(kmh)[0][1], 5.0 / 3.6, places=3)

    def test_dwd_kette_recent_zehn_now(self):
        """Stundenwerte „recent“ bis vorgestern, dann die Zehnminutenwerte
        „recent“, dann „now“ — die geprüfte Stunde gewinnt, wo es beide gibt,
        und ein Dienst, der fehlt, kostet nur seine Stunden."""
        from datetime import date, timedelta
        heute = date.today()
        gestern, vorgestern = heute - timedelta(days=1), heute - timedelta(days=2)
        recent = "STATIONS_ID;MESS_DATUM;QN_3;   F;   D;eor\n" + "".join(
            f"       5516;{vorgestern:%Y%m%d}{h:02d};    3;   5.0; 200;eor\n" for h in range(24))
        zehn = "STATIONS_ID;MESS_DATUM;QN;FF_10;DD_10;eor\n" + "".join(
            f"       5516;{tag:%Y%m%d}{h:02d}{m:02d};    1;   7.0; 250;eor\n"
            for tag in (vorgestern, gestern) for h in range(24) for m in range(0, 60, 10))
        now = "STATIONS_ID;MESS_DATUM;QN;FF_10;DD_10;eor\n" + "".join(
            f"       5516;{heute:%Y%m%d}{h:02d}{m:02d};    1;   9.0; 300;eor\n" for h in range(6) for m in range(0, 60, 10))
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            def zippe(name, innen, text):
                with zipfile.ZipFile(Path(d) / name, "w") as z:
                    z.writestr(innen, text)
            zippe("dwd_05516.zip", "produkt_ff_stunde_x.txt", recent)
            zippe("dwd_05516_zehn.zip", "produkt_zehn_min_ff_x.txt", zehn)
            zippe("dwd_05516_now.zip", "produkt_zehn_now_ff_x.txt", now)
            st = {"id": "05516", "name": "Fehmarn", "lat": 54.53, "lon": 11.06}
            with mock.patch.object(stationen, "CACHE_DIR", Path(d)), \
                    mock.patch.object(stationen, "_get", side_effect=AssertionError("kein Netz")):
                obs = stationen.dwd_stunden(st, vorgestern.isoformat(), heute.isoformat())
            h = obs["stunden"]
            self.assertEqual(len(h), 24 + 24 + 6)
            self.assertAlmostEqual(h[f"{vorgestern}T12:00"]["kn"], 5.0 * stationen.MS_ZU_KN, places=1)   # geprüft gewinnt
            self.assertAlmostEqual(h[f"{gestern}T12:00"]["kn"], 7.0 * stationen.MS_ZU_KN, places=1)      # Zehnminuten recent
            self.assertAlmostEqual(h[f"{heute}T05:00"]["kn"], 9.0 * stationen.MS_ZU_KN, places=1)        # now
            # Ohne die Zehnminutendatei: gestern fehlt, heute bleibt
            (Path(d) / "dwd_05516_zehn.zip").unlink()
            with mock.patch.object(stationen, "CACHE_DIR", Path(d)), \
                    mock.patch.object(stationen, "_get", side_effect=stationen.StationError("404")):
                obs = stationen.dwd_stunden(st, vorgestern.isoformat(), heute.isoformat())
            self.assertEqual(len(obs["stunden"]), 24 + 6)

    def test_frische_heute_stuendlich(self):
        from datetime import date, timedelta
        import os, time
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "x.json"
            pfad.write_text("{}", encoding="utf-8")
            heute = date.today().isoformat()
            alt = (date.today() - timedelta(days=10)).isoformat()
            self.assertTrue(stationen._brauchbar(pfad, heute))                 # eben geschrieben
            os.utime(pfad, (time.time() - 2 * 3600, time.time() - 2 * 3600))
            self.assertFalse(stationen._brauchbar(pfad, heute))                # heute: nach einer Stunde neu
            self.assertTrue(stationen._brauchbar(pfad, (date.today() - timedelta(days=1)).isoformat()))  # gestern: 6 h
            self.assertTrue(stationen._brauchbar(pfad, alt))                   # alt: für immer
            self.assertFalse(stationen._brauchbar(Path(d) / "fehlt.json", alt))


class MeteoFrance(unittest.TestCase):
    def test_departements_aus_koordinate(self):
        self.assertEqual(stationen.fr_departements(48.24, -4.55), ["29"])              # Crozon
        self.assertEqual(stationen.fr_departements(47.539, -3.14), ["56"])             # Quiberon
        self.assertIn("73", stationen.fr_departements(45.685, 5.883))                  # Lac du Bourget
        self.assertLessEqual(len(stationen.fr_departements(45.685, 5.883)), 2)
        self.assertEqual(len(stationen.fr_departements(49.0, 2.3)), 1)                 # Paris: kein Rahmen, der nächste

    def test_datei_lesen(self):
        stationen_, fenster = stationen.fr_lesen(FR_CSV.splitlines(), "2026-09-17", "2026-09-17")
        self.assertEqual([s["id"] for s in stationen_], ["29075001", "29024001"])
        self.assertEqual(stationen_[0]["name"], "Brest-Guipavas")
        self.assertEqual(stationen_[0]["dept"], "29")
        self.assertAlmostEqual(stationen_[0]["lat"], 48.444167)
        brest = fenster["29075001"]
        self.assertEqual(sorted(brest), ["2026-09-17T12:00", "2026-09-17T13:00"])     # 14 Uhr zweifelhaft, 15 Uhr leer
        self.assertAlmostEqual(brest["2026-09-17T12:00"]["kn"], 6.2 * stationen.MS_ZU_KN, places=1)
        self.assertEqual(brest["2026-09-17T13:00"]["dir"], 260.0)
        self.assertEqual(sorted(fenster["29024001"]), ["2026-09-17T12:00"])           # der 16. liegt außerhalb
        with self.assertRaises(stationen.StationError):
            stationen.fr_lesen(["A;B;C", "1;2;3"], "2026-09-17", "2026-09-17")

    def test_stationen_und_stunden_aus_dem_cache(self):
        import gzip
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(stationen, "CACHE_DIR", Path(d)), \
                    mock.patch.object(stationen, "_get", side_effect=AssertionError("kein Netz")):
                with gzip.open(Path(d) / "fr_29.csv.gz", "wt", encoding="utf-8") as fh:
                    fh.write(FR_CSV)
                spot = {"id": "goulien", "name": "Goulien", "country": "FR", "lat": 48.239, "lon": -4.545}
                liste = stationen.fr_stationen(spot)
                self.assertEqual({s["id"] for s in liste}, {"29075001", "29024001"})
                st = stationen.fr_stunden(liste[0], "2026-09-17", "2026-09-17")
                self.assertEqual(st["quelle"], "Météo-France")
                self.assertEqual(len(st["stunden"]), 2)
                # Paare: Frankreich wird je Spot geladen, die Station in Reichweite gefunden
                paare = stationen.paare_finden([spot, {"id": "b", "name": "Brest", "country": "FR", "lat": 48.44, "lon": -4.41}], 12.0)
                self.assertEqual([p["station"]["id"] for p in paare], ["29075001"])
                self.assertEqual(paare[0]["quelle"], "Météo-France")
                with self.assertRaises(stationen.StationError):
                    stationen.fr_stunden(liste[0], "2026-09-10", "2026-09-10")


RWS_KATALOG = {
    # Ausschnitt aus dem Katalog der DD-API 2.0, abgefragt am 20.09.2026
    "AquoMetadataLijst": [
        {"AquoMetadata_MessageID": 191, "Compartiment": {"Code": "LT", "Omschrijving": "Lucht"},
         "Grootheid": {"Code": "WINDRTG", "Omschrijving": "Windrichting"}, "Eenheid": {"Code": "graad"}},
        {"AquoMetadata_MessageID": 193, "Compartiment": {"Code": "LT", "Omschrijving": "Lucht"},
         "Grootheid": {"Code": "WINDSHD", "Omschrijving": "Windsnelheid"}, "Eenheid": {"Code": "m/s"}},
        {"AquoMetadata_MessageID": 194, "Compartiment": {"Code": "LT", "Omschrijving": "Lucht"},
         "Grootheid": {"Code": "WINDSHD_SD", "Omschrijving": "Standaarddeviatie van de windsnelheid"},
         "Eenheid": {"Code": "m/s"}},
        {"AquoMetadata_MessageID": 1, "Compartiment": {"Code": "OW", "Omschrijving": "Oppervlaktewater"},
         "Grootheid": {"Code": "WATHTE", "Omschrijving": "Waterhoogte"}, "Eenheid": {"Code": "cm"}},
    ],
    "LocatieLijst": [
        {"Code": "brouwersdam.brouwershavensegat.2", "Coordinatenstelsel": "ETRS89", "Lat": 51.766527,
         "Locatie_MessageID": 10, "Lon": 3.621747, "Naam": "Brouwersdam Brouwershavense Gat 2"},
        {"Code": "vlissingen", "Coordinatenstelsel": "ETRS89", "Lat": 51.442, "Locatie_MessageID": 11,
         "Lon": 3.6, "Naam": "Vlissingen"},
        {"Code": "baarland.badstrand", "Coordinatenstelsel": "ETRS89", "Lat": 51.394, "Locatie_MessageID": 12,
         "Lon": 3.898, "Naam": "Baarland, badstrand"},                     # Wind bis 2008 — stillgelegt
        {"Code": "pegel", "Coordinatenstelsel": "ETRS89", "Lat": 51.4, "Locatie_MessageID": 13,
         "Lon": 3.7, "Naam": "Nur Wasserstand"},
        {"Code": "sd.allein", "Coordinatenstelsel": "ETRS89", "Lat": 51.5, "Locatie_MessageID": 14,
         "Lon": 3.7, "Naam": "Nur Standardabweichung"},
    ],
    "AquoMetadataLocatieLijst": [
        {"AquoMetaData_MessageID": 193, "Locatie_MessageID": 10},
        {"AquoMetaData_MessageID": 191, "Locatie_MessageID": 10},
        {"AquoMetaData_MessageID": 193, "Locatie_MessageID": 11},
        {"AquoMetaData_MessageID": 193, "Locatie_MessageID": 12},
        {"AquoMetaData_MessageID": 1, "Locatie_MessageID": 13},
        {"AquoMetaData_MessageID": 194, "Locatie_MessageID": 14},
    ],
}


def _rws_reihe(code: str, einheit: str, werte: list, prozess: str = "meting",
               methode: str = "10 min. scal. gem. windsnelh. gecorr. naar KNMI hoogte (RMI)") -> dict:
    """Eine Reihe wie in der Antwort vom 20.09.2026: Zehnminutenwerte am
    19.09.2026 ab 13:00 in +01:00 (12:00 UTC)."""
    return {"AquoMetadata": {"Grootheid": {"Code": code}, "Eenheid": {"Code": einheit},
                             "Compartiment": {"Code": "LT"}, "ProcesType": prozess,
                             "WaardeBepalingsMethode": {"Code": "other:F136", "Omschrijving": methode}},
            "Locatie": {"Code": "brouwersdam.brouwershavensegat.2", "Lat": 51.766527, "Lon": 3.621747},
            "MetingenLijst": [{"Tijdstip": f"2026-09-19T13:{m:02d}:00.000+01:00",
                               "Meetwaarde": {"Waarde_Alfanumeriek": str(v), "Waarde_Numeriek": v},
                               "WaarnemingMetadata": {"Kwaliteitswaardecode": "00", "Statuswaarde": "Ongecontroleerd"}}
                              for m, v in zip(range(0, 60, 10), werte)]}


def _rws_antwort(code: str, einheit: str, werte: list, mit_vorhersage: bool = True) -> dict:
    """Wie der Dienst antwortet: zwei gemessene Reihen (roh und auf 10 m
    korrigiert) und eine Vorhersage mit Werten um 0,5 m/s."""
    reihen = [_rws_reihe(code, einheit, [w + 0.7 if isinstance(w, (int, float)) and w < 1000 else w for w in werte],
                         methode="10 minuut scalair gemiddelde van de windsnelheid"),
              _rws_reihe(code, einheit, werte)]
    if mit_vorhersage:
        reihen.append(_rws_reihe(code, einheit, [0.45] * 6, prozess="verwachting", methode="RWS Methodiek F233"))
    return {"Succesvol": True, "WaarnemingenLijst": reihen}


DMI_STATIONEN = {"type": "FeatureCollection", "features": [
    # Ausschnitt aus opendataapi.dmi.dk/v2/metObs/collections/station/items, 20.09.2026
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [8.1413, 56.0072]},
     "properties": {"stationId": "06058", "name": "Hvide Sande", "country": "DNK", "status": "Active", "validTo": None,
                    "type": "Synop", "parameterId": ["temp_dry", "wind_dir", "wind_speed", "wind_speed_past1h"]}},
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [8.10, 56.00]},
     "properties": {"stationId": "06058", "name": "Hvide Sande (alt)", "country": "DNK", "status": "Active",
                    "validTo": "2019-01-01T00:00:00Z", "parameterId": ["wind_speed"]}},        # verlegt: alte Lage
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [11.3879, 55.3224]},
     "properties": {"stationId": "06135", "name": "Flakkebjerg", "country": "DNK", "status": "Active", "validTo": None,
                    "parameterId": ["temp_dry", "humidity"]}},                                   # kein Wind
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-53.5381, 69.2511]},
     "properties": {"stationId": "04219", "name": "Qeqertarsuaq Heliport", "country": "GRL", "status": "Active",
                    "validTo": None, "parameterId": ["wind_speed", "wind_dir"]}},                # Grönland
]}


def _dmi_werte(param: str, werte: list) -> dict:
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [8.1413, 56.0072]},
         "properties": {"parameterId": param, "value": v, "observed": f"2026-09-20T12:{m:02d}:00Z", "stationId": "06058"}}
        for m, v in zip(range(0, 60, 10), werte)]}


class DMI(unittest.TestCase):
    """Dänemark (1.14.0), am 20.09.2026 gegen den Dienst geprüft."""

    def test_stationen(self):
        liste = stationen.dmi_stationen_aus(DMI_STATIONEN)
        self.assertEqual([(s["id"], s["name"]) for s in liste], [("06058", "Hvide Sande")],
                         "nur aktive dänische Stationen mit Wind, in der gültigen Lage")
        self.assertEqual((liste[0]["lat"], liste[0]["lon"], liste[0]["dienst"]), (56.0072, 8.1413, "DMI"))
        self.assertEqual(stationen.dmi_stationen_aus("kaputt"), [])

    def test_stunden(self):
        anfragen = []

        def get(url):
            anfragen.append(url)
            if "wind_speed" in url:
                return json.dumps(_dmi_werte("wind_speed", [5.0] * 6)).encode("utf-8")
            return json.dumps(_dmi_werte("wind_dir", [80, 90, 100, 90, 90, 90])).encode("utf-8")
        st = {"id": "06058", "name": "Hvide Sande", "lat": 56.0, "lon": 8.14, "dienst": "DMI"}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(stationen, "CACHE_DIR", Path(d)), \
                mock.patch.object(stationen, "_get", side_effect=get):
            obs = stationen.dmi_stunden(st, "2026-09-20", "2026-09-20")
            stationen.dmi_stunden(st, "2026-09-20", "2026-09-20")
        self.assertEqual(obs["quelle"], "DMI")
        self.assertEqual(list(obs["stunden"]), ["2026-09-20T12:00"])
        self.assertAlmostEqual(obs["stunden"]["2026-09-20T12:00"]["kn"], 9.7, places=1)
        self.assertAlmostEqual(obs["stunden"]["2026-09-20T12:00"]["dir"], 90.0, places=0)
        self.assertEqual(len(anfragen), 2, "danach aus dem Cache")
        self.assertIn("stationId=06058", anfragen[0])
        self.assertIn("datetime=2026-09-20T00%3A00%3A00Z%2F2026-09-20T23%3A59%3A59Z", anfragen[0])
        # Keine Werte: Hinweis statt Zahlen
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(stationen, "CACHE_DIR", Path(d)), \
                mock.patch.object(stationen, "_get", return_value=b'{"type": "FeatureCollection", "features": []}'):
            leer = stationen.dmi_stunden(st, "2026-09-20", "2026-09-20")
        self.assertEqual(leer["stunden"], {})
        self.assertIn("keine Windwerte", leer["hinweis"])

    def test_daenischer_spot_bekommt_die_daenische_station(self):
        spot = {"id": "hvide", "name": "Hvide Sande", "country": "DK", "lat": 56.0, "lon": 8.13}
        with mock.patch.object(stationen, "dmi_stationen", return_value=stationen.dmi_stationen_aus(DMI_STATIONEN)), \
                mock.patch.object(stationen, "dwd_stationen", return_value=[]), \
                mock.patch.object(stationen, "nl_stationen", return_value=[]), \
                mock.patch.object(stationen, "geosphere_stationen", return_value=[]), \
                mock.patch.dict(stationen.QUELLEN, {"DE": ("DWD", lambda spot=None: [], stationen.dwd_stunden),
                                                    "NL": ("KNMI/RWS", lambda spot=None: [], stationen.nl_stunden),
                                                    "AT": ("GeoSphere", lambda spot=None: [], stationen.geosphere_stunden)}):
            paare = stationen.paare_finden([spot], 30.0)
        self.assertEqual((paare[0]["quelle"], paare[0]["station"]["id"]), ("DMI", "06058"))


class Rijkswaterstaat(unittest.TestCase):
    """Gebaut am 20.09.2026 gegen die DD-API 2.0 — die Ausschnitte oben sind
    die Form, die der Dienst an diesem Tag geliefert hat."""

    def test_utm31_nach_wgs84(self):
        lat, lon = stationen.utm31_nach_wgs84(541518.745919649, 5699254.96425966)   # Vlissingen
        self.assertAlmostEqual(lat, 51.443, places=2)
        self.assertAlmostEqual(lon, 3.597, places=2)

    def test_groessen_nach_code_nicht_nach_wort(self):
        g = stationen.rws_groessen(RWS_KATALOG)
        self.assertEqual(g["speed"]["code"], "WINDSHD")
        self.assertEqual(g["dir"]["code"], "WINDRTG")
        self.assertEqual(g["speed"]["ids"], {193}, "die Standardabweichung der Windsnelheid zählt nicht")
        self.assertEqual(stationen.rws_groessen({"AquoMetadataLijst": []}), {})

    def test_stationen_nur_aktuelle_mit_wind(self):
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        jetzt = _dt.now(_tz.utc).replace(tzinfo=None, microsecond=0)
        letzte = {"WaarnemingenLijst": [
            dict(_rws_reihe("WINDSHD", "m/s", [5.0]), Locatie={"Code": "brouwersdam.brouwershavensegat.2"},
                 MetingenLijst=[{"Tijdstip": (jetzt - _td(hours=1)).isoformat() + "+00:00",
                                 "Meetwaarde": {"Waarde_Numeriek": 5.0}}]),
            dict(_rws_reihe("WINDSHD", "m/s", [5.0]), Locatie={"Code": "vlissingen"},
                 MetingenLijst=[{"Tijdstip": (jetzt - _td(hours=2)).isoformat() + "+01:00",
                                 "Meetwaarde": {"Waarde_Numeriek": 5.0}}]),
            dict(_rws_reihe("WINDSHD", "m/s", [5.0]), Locatie={"Code": "baarland.badstrand"},
                 MetingenLijst=[{"Tijdstip": "2008-09-15T07:02:00.000+01:00", "Meetwaarde": {"Waarde_Numeriek": 5.0}}]),
            # eine Vorhersage bis morgen macht einen stillgelegten Ort nicht aktuell
            dict(_rws_reihe("WINDSHD", "m/s", [0.4], prozess="verwachting"), Locatie={"Code": "baarland.badstrand"},
                 MetingenLijst=[{"Tijdstip": (jetzt + _td(hours=10)).isoformat() + "+00:00",
                                 "Meetwaarde": {"Waarde_Numeriek": 0.4}}]),
        ]}
        anfragen = []

        def post(url, koerper):
            anfragen.append((url, koerper))
            return letzte
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(stationen, "CACHE_DIR", Path(d)), \
                mock.patch.object(stationen, "rws_katalog", return_value=RWS_KATALOG), \
                mock.patch.object(stationen, "_post_json", side_effect=post):
            liste = stationen.rws_stationen()
            nochmal = stationen.rws_stationen()
        self.assertEqual([s["id"] for s in liste], ["brouwersdam.brouwershavensegat.2", "vlissingen"],
                         "ohne Pegel, ohne Standardabweichung, ohne den seit 2008 stillen Badestrand")
        self.assertEqual(nochmal, liste)
        self.assertEqual(len(anfragen), 1, "die Liste wird gemerkt")
        self.assertTrue(anfragen[0][0].endswith("/OphalenLaatsteWaarnemingen"))
        self.assertEqual(len(anfragen[0][1]["LocatieLijst"]), 3)
        b = liste[0]
        self.assertEqual((b["name"], b["dienst"], b["code_speed"], b["code_dir"]),
                         ("Brouwersdam Brouwershavense Gat 2", "RWS", "WINDSHD", "WINDRTG"))
        self.assertAlmostEqual(b["lat"], 51.76653, places=4)
        # Kein Ort liefert: ein Fehler mit Grund, keine leere Liste
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(stationen, "CACHE_DIR", Path(d)), \
                mock.patch.object(stationen, "rws_katalog", return_value=RWS_KATALOG), \
                mock.patch.object(stationen, "_post_json", return_value={"WaarnemingenLijst": []}):
            with self.assertRaises(stationen.StationError) as fehler:
                stationen.rws_stationen()
        self.assertIn("aktuelle", str(fehler.exception))

    def test_alter_katalog_mit_utm(self):
        """Ein Katalog im alten Format (X/Y in EPSG:25831) wird weiter gelesen."""
        ort = {"Code": "VLIS", "X": 541518.745919649, "Y": 5699254.96425966}
        lat, lon = stationen._rws_lage(ort)
        self.assertAlmostEqual(lat, 51.443, places=2)
        self.assertIsNone(stationen._rws_lage({"Code": "x"}))

    def test_werte_nur_gemessen_und_auf_10_m(self):
        speed = _rws_antwort("WINDSHD", "m/s", [5.0, 5.0, 5.0, 999999999, 5.0, 5.0])
        self.assertEqual(stationen.rws_einheit(speed), "m/s")
        werte = stationen.rws_werte(speed, "speed")
        self.assertEqual(len(werte), 5, "der Fehlwert fällt weg")
        self.assertEqual({v for _, v in werte}, {5.0}, "die auf 10 m korrigierte Reihe, nicht die rohe, nie die Vorhersage")
        self.assertEqual(werte[0][0], datetime(2026, 9, 19, 12, 0), "+01:00 → UTC")
        # Nur Vorhersage: nichts
        nur_vorhersage = {"WaarnemingenLijst": [_rws_reihe("WINDSHD", "m/s", [0.4] * 6, prozess="verwachting")]}
        self.assertEqual(stationen.rws_werte(nur_vorhersage, "speed"), [])
        # Verworfen (99) fällt weg, alte Listenform der Qualität wird auch gelesen
        r = _rws_reihe("WINDSHD", "m/s", [5.0, 6.0])
        r["MetingenLijst"][0]["WaarnemingMetadata"] = {"Kwaliteitswaardecode": "99"}
        r["MetingenLijst"][1]["WaarnemingMetadata"] = {"KwaliteitswaardecodeLijst": ["00"]}
        self.assertEqual([v for _, v in stationen.rws_werte({"WaarnemingenLijst": [r]})], [6.0])
        # In Knoten gemeldet → nach m/s, damit das Stundenmittel stimmt
        self.assertAlmostEqual(stationen.rws_werte(_rws_antwort("WINDSHD", "kn", [10.0]), "speed")[0][1], 5.144, places=2)
        self.assertEqual(stationen.rws_werte(_rws_antwort("WINDRTG", "graad", [90, 990], mit_vorhersage=False), "dir"),
                         [(datetime(2026, 9, 19, 12, 0), 90.0)])
        self.assertEqual(stationen.rws_werte("kaputt"), [])

    def test_stunden_und_anfrage(self):
        speed = _rws_antwort("WINDSHD", "m/s", [5.0] * 6)
        station = {"id": "brouwersdam.brouwershavensegat.2", "name": "Brouwersdam", "lat": 51.77, "lon": 3.62,
                   "dienst": "RWS", "code_speed": "WINDSHD", "code_dir": "WINDRTG"}
        anfragen = []

        def post(url, koerper):
            anfragen.append(koerper)
            code = koerper["AquoPlusWaarnemingMetadata"]["AquoMetadata"]["Grootheid"]["Code"]
            return speed if code == "WINDSHD" else _rws_antwort("WINDRTG", "graad", [80, 90, 100, 90, 90, 90])

        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(stationen, "CACHE_DIR", Path(d)), \
                mock.patch.object(stationen, "_post_json", side_effect=post):
            obs = stationen.rws_stunden(station, "2026-09-19", "2026-09-19")
            obs2 = stationen.rws_stunden(station, "2026-09-19", "2026-09-19")
            # Ein Paar aus der Grundlinie trägt nur id, name, lat, lon — die Codes sind fest
            obs3 = stationen.rws_stunden({"id": "brouwersdam.brouwershavensegat.2", "name": "B", "lat": 0, "lon": 0},
                                         "2026-09-19", "2026-09-19")
        self.assertEqual(obs["quelle"], "RWS")
        self.assertEqual(list(obs["stunden"]), ["2026-09-19T12:00"])
        self.assertAlmostEqual(obs["stunden"]["2026-09-19T12:00"]["kn"], 9.7, places=1)     # 5 m/s
        self.assertAlmostEqual(obs["stunden"]["2026-09-19T12:00"]["dir"], 90.0, places=0)
        self.assertEqual(len(anfragen), 2, "Stärke und Richtung, je eine Anfrage — danach aus dem Cache")
        self.assertEqual(obs2["stunden"], obs["stunden"])
        self.assertEqual(obs3["stunden"], obs["stunden"])
        k = anfragen[0]
        self.assertEqual(k["Locatie"], {"Code": "brouwersdam.brouwershavensegat.2"}, "die neue Schnittstelle will nur den Code")
        self.assertEqual(k["AquoPlusWaarnemingMetadata"]["AquoMetadata"]["Compartiment"], {"Code": "LT"})
        self.assertEqual(k["Periode"], {"Begindatumtijd": "2026-09-19T00:00:00.000+00:00",
                                        "Einddatumtijd": "2026-09-19T23:59:59.000+00:00"})

    def test_ohne_windwerte_ein_hinweis_statt_zahlen(self):
        station = {"id": "vlissingen", "name": "Vlissingen", "lat": 51.44, "lon": 3.6, "dienst": "RWS"}
        # So sieht HTTP 204 nach _post_json aus
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(stationen, "CACHE_DIR", Path(d)), \
                mock.patch.object(stationen, "_post_json", return_value={"Succesvol": True, "WaarnemingenLijst": []}):
            obs = stationen.rws_stunden(station, "2026-09-19", "2026-09-19")
        self.assertEqual(obs["stunden"], {})
        self.assertIn("keine Windwerte", obs["hinweis"])

    def test_leerer_koerper_ist_keine_ausnahme(self):
        """HTTP 204 — am 20.09. die Antwort für jeden Ort ohne Werte im Zeitraum."""
        class Antwort:
            status = 204
            def read(self, n=-1): return b""
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with mock.patch.object(stationen.urllib.request, "urlopen", return_value=Antwort()):
            self.assertEqual(stationen._post_json(stationen.RWS_WERTE, {}), {"Succesvol": True, "WaarnemingenLijst": []})

    def test_nl_liste_vereint_knmi_und_rws(self):
        with mock.patch.object(stationen, "rws_stationen", return_value=[{"id": "vlissingen", "name": "Vlissingen", "lat": 51.44, "lon": 3.6, "dienst": "RWS"}]):
            liste = stationen.nl_stationen()
        self.assertEqual({s["dienst"] for s in liste}, {"KNMI", "RWS"})
        with mock.patch.object(stationen, "rws_stationen", side_effect=stationen.StationError("weg")):
            liste = stationen.nl_stationen()
        self.assertEqual({s["dienst"] for s in liste}, {"KNMI"}, "ohne Rijkswaterstaat bleibt KNMI")
        # nl_stunden verteilt nach dem Dienst der Station
        with mock.patch.object(stationen, "rws_stunden", return_value="rws"), \
                mock.patch.object(stationen, "knmi_stunden", return_value="knmi"):
            self.assertEqual(stationen.nl_stunden({"id": "1", "dienst": "RWS"}, "a", "b"), "rws")
            self.assertEqual(stationen.nl_stunden({"id": "1", "dienst": "KNMI"}, "a", "b"), "knmi")
            self.assertEqual(stationen.nl_stunden({"id": "1"}, "a", "b"), "knmi")

    def test_knmi_ohne_zeilen_ist_kein_ausfall(self):
        """KNMI liefert die letzten zwei Tage noch nicht — die Antwort hat den
        Kopf, aber keine Zeile. Bis 1.13.0 hieß das „nicht abrufbar“."""
        kopf = "# BRON: KNMI\n# STN      LON(east)   LAT(north)  ALT(m)      NAME\n# STN,YYYYMMDD,   HH,   DD,   FH,   FX\n"
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(stationen, "CACHE_DIR", Path(d)), \
                mock.patch.object(stationen, "_get", return_value=kopf.encode()):
            obs = stationen.knmi_stunden({"id": "316", "name": "Schaar", "lat": 51.66, "lon": 3.69}, "2026-09-19", "2026-09-20")
            self.assertEqual(obs["stunden"], {})
            self.assertIn("zwei Tagen Verzug", obs["hinweis"])
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(stationen, "CACHE_DIR", Path(d)), \
                mock.patch.object(stationen, "_get", return_value=b"<html>Service Unavailable</html>"):
            with self.assertRaises(stationen.StationError):
                stationen.knmi_stunden({"id": "316", "name": "Schaar", "lat": 51.66, "lon": 3.69}, "2026-09-19", "2026-09-20")


class Windguru(unittest.TestCase):
    """Windguru gibt Messwerte nur mit dem Passwort der Station heraus; die
    Stationen kommen aus der Konfiguration. Antwortform laut der
    veröffentlichten Beschreibung (Station JSON API 1.2.22)."""

    def tearDown(self):
        stationen.windguru_setzen([])

    def test_stationen_aus_der_konfiguration(self):
        stationen.windguru_setzen([
            {"id": 1234, "name": "Mein Pfahl", "lat": 51.76, "lon": 3.85, "passwort_md5": "abc"},
            {"id": 99, "lat": 52.0, "lon": 4.0},                                  # ohne Passwort: nutzlos
            {"id": "x", "lat": "kaputt", "lon": 4.0, "passwort": "p"},           # kaputt: übergangen
            "kein dict",
        ])
        liste = stationen.windguru_stationen()
        self.assertEqual(len(liste), 1)
        self.assertEqual((liste[0]["id"], liste[0]["name"], liste[0]["dienst"], liste[0]["passwort"]),
                         ("1234", "Mein Pfahl", "Windguru", "abc"))
        stationen.windguru_setzen(None)
        self.assertEqual(stationen.windguru_stationen(), [])

    def test_antwort_parallel_listen(self):
        daten = {"datetime": ["2026-09-19 14:00:00", "2026-09-19 15:00:00", "2026-09-19 16:00:00"],
                 "unixtime": [1789819200, 1789822800, 1789826400],     # 12:00, 13:00, 14:00 UTC
                 "wind_avg": [12.3, None, 15.0], "wind_max": [18.0, None, 20.0], "wind_direction": [250, 260, 400]}
        st = stationen.windguru_antwort(daten)
        self.assertEqual(sorted(st), ["2026-09-19T12:00", "2026-09-19T14:00"], "null fällt weg")
        self.assertEqual(st["2026-09-19T12:00"], {"kn": 12.3, "dir": 250.0}, "Knoten bleiben Knoten")
        self.assertIsNone(st["2026-09-19T14:00"]["dir"], "400° ist keine Richtung")
        self.assertEqual(stationen.windguru_antwort([]), {})

    def test_stunden_mit_passwort(self):
        station = {"id": "1234", "name": "Pfahl", "lat": 51.76, "lon": 3.85, "dienst": "Windguru", "passwort": "abc"}
        gesehen = {}

        def get(url, data=None, encoding="utf-8"):
            gesehen["url"] = url
            gesehen["params"] = dict(urllib.parse.parse_qsl(data.decode()))
            return json.dumps({"unixtime": [1789819200, 1789732800], "wind_avg": [12.0, 9.0],
                               "wind_direction": [250, 200]}).encode()      # 19.09. 12 UTC und 18.09. 12 UTC

        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(stationen, "CACHE_DIR", Path(d)), \
                mock.patch.object(stationen, "_get", side_effect=get):
            obs = stationen.windguru_stunden(station, "2026-09-19", "2026-09-19")
        self.assertEqual(obs["quelle"], "Windguru")
        self.assertEqual(obs["stunden"], {"2026-09-19T12:00": {"kn": 12.0, "dir": 250.0}}, "nur der gefragte Tag")
        self.assertEqual(gesehen["url"], stationen.WINDGURU_API)
        p = gesehen["params"]
        self.assertEqual((p["id_station"], p["password"], p["q"], p["avg_minutes"], p["format"]),
                         ("1234", "abc", "station_data", "60", "json"))
        self.assertEqual((p["from"], p["to"]), ("2026-09-18 00:00:00", "2026-09-20 23:59:59"), "ein Tag Rand")
        # Ohne Passwort am Paar (Grundlinie) kommt es aus der Konfiguration —
        # und ohne Konfiguration ist das ein benannter Fehler
        stationen.windguru_setzen([{"id": 1234, "name": "Pfahl", "lat": 51.76, "lon": 3.85, "passwort_md5": "abc"}])
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(stationen, "CACHE_DIR", Path(d)), \
                mock.patch.object(stationen, "_get", side_effect=get):
            obs = stationen.windguru_stunden({"id": "1234", "name": "Pfahl", "lat": 51.76, "lon": 3.85}, "2026-09-19", "2026-09-19")
            self.assertEqual(gesehen["params"]["password"], "abc")
            with self.assertRaises(stationen.StationError):
                stationen.windguru_stunden({"id": "9", "name": "Fremd", "lat": 51.0, "lon": 3.0}, "2026-09-19", "2026-09-19")
        # Fehler der Schnittstelle und Antworten ohne JSON werden benannt
        for antwort in (b'{"error": "wrong password"}', b"Access denied", b'{"foo": 1}'):
            with tempfile.TemporaryDirectory() as d, \
                    mock.patch.object(stationen, "CACHE_DIR", Path(d)), \
                    mock.patch.object(stationen, "_get", return_value=antwort):
                with self.assertRaises(stationen.StationError, msg=antwort):
                    stationen.windguru_stunden(station, "2026-09-19", "2026-09-19")


class Grenzen(unittest.TestCase):
    """Die Stationslisten gelten für jeden Spot — ein belgischer Spot bekommt
    die nächste niederländische Station, ein dänischer die deutsche."""

    def _quellen(self):
        dwd = [{"id": "02115", "name": "List auf Sylt", "lat": 55.0110, "lon": 8.4125}]
        nl = [{"id": "308", "name": "Cadzand", "lat": 51.381, "lon": 3.379, "dienst": "KNMI"},
              {"id": "VLIS", "name": "Vlissingen", "lat": 51.443, "lon": 3.597, "dienst": "RWS"}]
        aufrufe = []

        def stunden(name):
            def lade(station, von, bis):
                aufrufe.append((name, station["id"]))
                return {"quelle": name, "station": station, "stunden": {}}
            return lade

        quellen = {
            "DE": ("DWD", lambda spot=None: dwd, stunden("DWD")),
            "NL": ("KNMI/RWS", lambda spot=None: nl, stunden("NL")),
            "AT": ("GeoSphere", lambda spot=None: [], stunden("GeoSphere")),
            "DK": ("DMI", lambda spot=None: [], stunden("DMI")),           # ohne dänische Station: Sylt
            "FR": ("Météo-France", lambda spot=None: (_ for _ in ()).throw(AssertionError("FR nur für FR-Spots")), stunden("FR")),
            "WG": ("Windguru", lambda spot=None: [], stunden("Windguru")),
        }
        return quellen, aufrufe

    def test_paare_ueber_die_grenze(self):
        quellen, _ = self._quellen()
        spots = [{"id": "knokke", "name": "Knokke", "country": "BE", "lat": 51.35, "lon": 3.29},
                 {"id": "roemoe", "name": "Rømø", "country": "DK", "lat": 55.10, "lon": 8.50},
                 {"id": "torbole", "name": "Torbole", "country": "IT", "lat": 45.87, "lon": 10.87}]
        with mock.patch.dict(stationen.QUELLEN, quellen, clear=True):
            paare = {p["spot"]["id"]: p for p in stationen.paare_finden(spots, 30.0)}
        self.assertEqual(paare["knokke"]["quelle"], "KNMI")
        self.assertEqual(paare["knokke"]["station"]["id"], "308")
        self.assertLess(paare["knokke"]["km"], 10)
        self.assertEqual([s["id"] for s in paare["knokke"]["ersatz"]], ["VLIS"], "die nächste danach, für den Fall")
        self.assertEqual(paare["roemoe"]["quelle"], "DWD")
        self.assertNotIn("torbole", paare, "in 30 km um Torbole misst keiner der Dienste")
        # Nur ein Dienst zugelassen (die Sonde fragt so): Belgien bleibt ohne
        with mock.patch.dict(stationen.QUELLEN, quellen, clear=True):
            nur_de = stationen.paare_finden(spots, 30.0, dienste=["DE"])
        self.assertEqual([p["spot"]["id"] for p in nur_de], ["roemoe"])
        # `laender` filtert weiterhin die Spots
        with mock.patch.dict(stationen.QUELLEN, quellen, clear=True):
            nur_dk = stationen.paare_finden(spots, 30.0, laender=["DK"])
        self.assertEqual([p["spot"]["id"] for p in nur_dk], ["roemoe"])

    def test_stundenwerte_nach_dienst_der_station(self):
        quellen, aufrufe = self._quellen()
        with mock.patch.dict(stationen.QUELLEN, quellen, clear=True):
            stationen.stunden_fuer_station({"id": "308", "dienst": "KNMI"}, "a", "b")
            stationen.stunden_fuer_station({"id": "VLIS", "dienst": "RWS"}, "a", "b")
            stationen.stunden_fuer_station({"id": "02115", "_land": "DE"}, "a", "b")
            # Paare aus der Grundlinie (vor 1.13.0): der Dienst steht am Paar
            stationen.stunden_fuer({"spot": {"country": "DE"}, "quelle": "DWD", "station": {"id": "02115"}}, "a", "b")
            with self.assertRaises(stationen.StationError):
                stationen.stunden_fuer_station({"id": "?", "dienst": "Nix"}, "a", "b")
        self.assertEqual(aufrufe, [("NL", "308"), ("NL", "VLIS"), ("DWD", "02115"), ("DWD", "02115")])


class Fehlermasse(unittest.TestCase):
    def test_masse(self):
        v = {f"t{i}": (15.0, 270.0) for i in range(10)}
        m = {f"t{i}": (13.0, 250.0) for i in range(10)}
        m["t9"] = (13.0, 100.0)
        r = ps.masse(v, m, tageslicht=set(v))
        self.assertEqual(r["n"], 10)
        self.assertAlmostEqual(r["bias"], 2.0)
        self.assertAlmostEqual(r["mae"], 2.0)
        self.assertAlmostEqual(r["richtung"], 0.9)
        self.assertEqual((r["precision"], r["recall"], r["f1"]), (1.0, 1.0, 1.0))
        # Vorhersage sagt fahrbar, Messung nicht: precision fällt
        m2 = {k: (5.0, 250.0) for k in m}
        r2 = ps.masse(v, m2, tageslicht=set(v))
        self.assertEqual(r2["precision"], 0.0)
        self.assertIsNone(r2["recall"])
        self.assertEqual(ps.masse({}, m)["n"], 0)

    def test_grundlinienvergleich(self):
        alt = {"zeitraum": ["2026-08-01", "2026-08-31"], "ergebnisse": {
            "a": {"reihen": {"Wingfoilscout": {"mae": 3.0}}, "sessions": {"f1": 0.7}},
            "b": {"reihen": {"Wingfoilscout": {"mae": 3.0}}, "sessions": {"f1": 0.7}}}}
        neu = {"zeitraum": ["2026-08-01", "2026-08-31"], "ergebnisse": [
            {"spot": "a", "name": "A", "reihen": {"Wingfoilscout": {"mae": 4.5}}, "sessions": {"f1": 0.7}},
            {"spot": "b", "name": "B", "reihen": {"Wingfoilscout": {"mae": 2.9}}, "sessions": {"f1": 0.72}},
            {"spot": "c", "name": "C", "reihen": {"Wingfoilscout": {"mae": 2.0}}, "sessions": {"f1": 0.5}}]}
        befunde = ps.vergleiche_grundlinie(alt, neu)
        stufen = {t.split(":")[0]: s for s, t in befunde}
        self.assertEqual(stufen["A"], "fehler")          # MAE +1,5
        self.assertEqual(stufen["B"], "ok")
        self.assertEqual(stufen["C"], "warnung")         # nicht in der Grundlinie
        anders = ps.vergleiche_grundlinie(dict(alt, zeitraum=["2026-07-01", "2026-07-31"]), neu)
        self.assertEqual(anders[0][0], "warnung")


def _fc(tage=2, suffix="_dwd_icon_seamless", **ersatz):
    n = 24 * tage
    zeiten = [f"2026-07-{15 + d:02d}T{h:02d}:00" for d in range(tage) for h in range(24)]
    strahlung = [0.0 if (h < 6 or h > 19) else 650.0 for _ in range(tage) for h in range(24)]
    h = {"time": zeiten,
         f"wind_speed_10m{suffix}": [4.0] * n, f"wind_gusts_10m{suffix}": [6.0] * n,
         f"wind_direction_10m{suffix}": [200.0] * n, f"temperature_2m{suffix}": [24.0] * n,
         f"precipitation{suffix}": [0.0] * n, f"cape{suffix}": [0.0] * n,
         f"weather_code{suffix}": [1] * n, f"cloud_cover{suffix}": [10.0] * n,
         f"shortwave_radiation{suffix}": strahlung}
    h.update(ersatz)
    return {"utc_offset_seconds": 7200,
            "hourly": h,
            "daily": {"time": [f"2026-07-{15 + d:02d}" for d in range(tage)],
                      f"sunrise{suffix}": [f"2026-07-{15 + d:02d}T05:47" for d in range(tage)],
                      f"sunset{suffix}": [f"2026-07-{15 + d:02d}T20:58" for d in range(tage)]}}


TORBOLE = {"id": "torbole", "name": "Torbole", "lat": 45.87, "lon": 10.87, "country": "IT", "sectors": [],
           "thermal": {"name": "Ora", "months": [4, 5, 6, 7, 8, 9, 10], "from": 13, "to": 20,
                       "dir": 180, "typical_kn": 16, "reliability": 0.7, "suppressed_by": [0]}}


class Referenzpruefungen(unittest.TestCase):
    def setUp(self):
        self.cfg = load_cfg()

    def test_form_einer_guten_antwort(self):
        befunde = ps.pruefe_format(TORBOLE, _fc(), self.cfg)
        self.assertFalse([t for s, t in befunde if s == "fehler"], befunde)
        self.assertTrue(any("Sonnenaufgang" in t for _, t in befunde))

    def test_fehlendes_feld_faellt_auf(self):
        fc = _fc()
        del fc["hourly"]["shortwave_radiation_dwd_icon_seamless"]
        befunde = ps.pruefe_format(TORBOLE, fc, self.cfg)
        self.assertTrue(any(s == "fehler" and "shortwave_radiation" in t for s, t in befunde))

    def test_falsche_zeitzone_faellt_auf(self):
        fc = _fc()
        fc["utc_offset_seconds"] = 3600            # Italien im Juli: 7200
        befunde = ps.pruefe_format(TORBOLE, fc, self.cfg)
        fehler = [t for s, t in befunde if s == "fehler"]
        self.assertTrue(any("Zeitversatz" in t or "Sonnenaufgang" in t for t in fehler), befunde)

    def test_nacht_als_session_faellt_auf(self):
        from wingscout.score import score_hours
        rows = score_hours(TORBOLE, _fc(), self.cfg)
        for r in rows:
            if r["t"].hour == 1:
                r["score"] = 0.8
        befunde = ps.pruefe_bewertung(TORBOLE, rows, self.cfg)
        self.assertTrue(any(s == "fehler" and "Nacht" in t for s, t in befunde))

    def test_thermiksignatur_und_saison(self):
        from wingscout.score import score_hours
        models = ["dwd_icon_seamless"]
        # Sonnig, schwacher Wind aus Süd — die Annahme greift, das Modell zeigt 4 kn
        rows = score_hours(TORBOLE, _fc(), self.cfg)
        sig = ps.thermik_signatur(TORBOLE, _fc(), rows, models)
        self.assertEqual(sig["sonnig"], 2)
        self.assertEqual(sig["modelle"]["ICON"], 0, "4 kn im Modell sind keine Ora")
        self.assertEqual(sig["wingscout"], 2, "die Annahme liefert die Ora")
        self.assertGreater(sig["angenommen"], 0)
        befunde = ps.pruefe_thermik(TORBOLE, _fc(), rows, models, monat=7)
        self.assertEqual(befunde[0][0], "ok", befunde)
        # Außerhalb der Saison darf nichts angenommen werden
        befunde = ps.pruefe_thermik(TORBOLE, _fc(), rows, models, monat=1)
        self.assertEqual(befunde[0][0], "fehler")
        # Regionalmodell, das die Ora sieht: 18 kn aus Süd am Nachmittag
        fc = _fc()
        n = len(fc["hourly"]["time"])
        fein = {"time": fc["hourly"]["time"],
                "wind_speed_10m": [18.0 if 13 <= int(t[11:13]) < 20 else 4.0 for t in fc["hourly"]["time"]],
                "wind_gusts_10m": [22.0] * n, "wind_direction_10m": [180.0] * n}
        fc["_highres"] = ("italia_meteo_arpae_icon_2i", fein)
        rows = score_hours(TORBOLE, fc, self.cfg)
        sig = ps.thermik_signatur(TORBOLE, fc, rows, models)
        self.assertEqual(sig["modelle"]["ICON-2I"], 2)


class Landpunkt(unittest.TestCase):
    def test_synthetischer_landpunkt_wird_erkannt(self):
        befunde = ps.land_offline(load_cfg())
        self.assertFalse([t for s, t in befunde if s != "ok"], befunde)

    def test_rechne_kennt_wasser(self):
        from wingscout.shoreline import rechne, befund
        from tests.helpers import square_lake
        lat, lon = 52.0, 5.0
        # Spot 60 m westlich eines 2-km-Sees: wird versetzt, ist Wasser
        eintrag = rechne(square_lake(lat, lon, x0=60, x1=2060, y0=-1000, y1=1000),
                         {"id": "s", "lat": lat, "lon": lon}, 25.0, 36)
        self.assertTrue(eintrag["wasser"])
        self.assertIsNone(befund(eintrag))
        # See zehn Kilometer weiter: kein Wasser innerhalb von 3 km — Pin an Land
        eintrag = rechne(square_lake(lat, lon, x0=10000, x1=14000, y0=-2000, y1=2000),
                         {"id": "s", "lat": lat, "lon": lon}, 25.0, 36)
        self.assertFalse(eintrag["wasser"])
        self.assertGreater(eintrag["max_fetch_km"], 5, "die Rose allein sähe offenes Wasser")
        self.assertEqual(befund(eintrag)[0], "unbrauchbar")
        # Alte Einträge ohne das Feld bleiben, wie sie sind
        self.assertIsNone(befund({"max_fetch_km": 12.0, "origin_offset_m": [0, 0]}))


class Vergangenheit(unittest.TestCase):
    def test_vergleich_paar(self):
        cfg = load_cfg()
        spot = {"id": "fehmarn-gruener-brink", "name": "Fehmarn", "lat": 54.53, "lon": 11.06,
                "country": "DE", "sectors": []}
        fc = _fc(tage=2, **{"wind_speed_10m_dwd_icon_seamless": [15.0] * 48,
                            "wind_speed_10m_ncep_gfs_seamless": [17.0] * 48,
                            "wind_direction_10m_dwd_icon_seamless": [270.0] * 48})
        # Messung: 13 kn aus West, UTC = Ortszeit − 2 h
        stunden = {}
        for t in fc["hourly"]["time"]:
            lokal = datetime.fromisoformat(t)
            utc = lokal.replace(hour=(lokal.hour - 2) % 24) if lokal.hour >= 2 else None
            if utc is not None:
                stunden[utc.strftime("%Y-%m-%dT%H:00")] = {"kn": 13.0, "dir": 265.0}
        obs = {"quelle": "DWD", "station": {"id": "05516", "name": "Fehmarn"}, "stunden": stunden}
        paar = {"spot": spot, "quelle": "DWD", "station": obs["station"], "km": 0.5}
        erg = ps.vergleich_paar(paar, obs, fc, cfg, None, ["dwd_icon_seamless", "ncep_gfs_seamless"])
        self.assertIn("ICON", erg["reihen"])
        self.assertIn("GFS", erg["reihen"])
        self.assertIn("Wingfoilscout", erg["reihen"])
        self.assertAlmostEqual(erg["reihen"]["ICON"]["bias"], 2.0, places=1)
        self.assertAlmostEqual(erg["reihen"]["GFS"]["bias"], 4.0, places=1)
        self.assertGreaterEqual(erg["reihen"]["ICON"]["richtung"], 0.99)
        self.assertGreater(erg["reihen"]["Wingfoilscout"]["n"], 40)
        self.assertIsNotNone(erg["sessions"]["f1"])
        text = ps.tabelle_vergangenheit([erg])
        self.assertIn("Fehmarn", text)
        self.assertIn("Wingfoilscout", text)

    def test_vergangenheit_nimmt_die_naechste_station_wenn_die_erste_schweigt(self):
        """Tholen lieferte im ersten Lauf keine Winddaten — dann kommt die
        zweitnächste Station dran, statt dass das Paar verloren geht."""
        from unittest import mock
        from wingscout.sources import stationen as st_mod, historisch
        cfg = load_cfg()
        spot = {"id": "oesterdam", "name": "Oesterdam", "lat": 51.52, "lon": 4.20, "country": "NL", "sectors": []}
        liste = [{"id": "331", "name": "Tholen", "lat": 51.48, "lon": 4.19},
                 {"id": "324", "name": "Stavenisse", "lat": 51.55, "lon": 4.15}]
        fc = _fc(tage=2)
        fc["hourly"]["time"] = [t.replace("2026-07-", "2026-08-") for t in fc["hourly"]["time"]]
        fc["daily"] = {"time": ["2026-08-15", "2026-08-16"], "sunrise_dwd_icon_seamless": ["2026-08-15T06:20", "2026-08-16T06:22"],
                       "sunset_dwd_icon_seamless": ["2026-08-15T21:00", "2026-08-16T20:58"]}
        stunden = {}
        for t in fc["hourly"]["time"]:
            lokal = datetime.fromisoformat(t)
            if lokal.hour >= 2:
                stunden[lokal.replace(hour=lokal.hour - 2).strftime("%Y-%m-%dT%H:00")] = {"kn": 9.0, "dir": 200.0}

        def stunden_fuer(paar, von, bis):
            if paar["station"]["id"] == "331":
                raise st_mod.StationError("KNMI 331: keine Stundenwerte in der Antwort")
            return {"quelle": "KNMI", "station": dict(paar["station"]), "stunden": stunden}

        with mock.patch.object(st_mod, "paare_finden", return_value=[
                    {"spot": spot, "quelle": "KNMI", "station": liste[0], "km": 4.5, "ersatz": [liste[1]]}]), \
                mock.patch.object(st_mod, "stunden_fuer", side_effect=stunden_fuer), \
                mock.patch.object(historisch, "hole", return_value=fc), \
                mock.patch.object(historisch, "hole_regional", return_value=None):
            erg = ps.vergangenheit(cfg, [spot], {}, "2026-08-15", "2026-08-16", 10, log=lambda *a: None)
        self.assertEqual(len(erg["ergebnisse"]), 1)
        self.assertEqual(erg["ergebnisse"][0]["station"]["id"], "324")
        self.assertEqual(erg["paare"][0]["station"]["id"], "324", "die Grundlinie merkt sich die, die geliefert hat")
        self.assertFalse([t for s, t in erg["befunde"] if s == "fehler"], erg["befunde"])

    def test_grundlinie_schreiben_und_lesen(self):
        erg = {"zeitraum": ["2026-08-01", "2026-08-31"], "schwelle_kn": 12.0, "paare": [],
               "ergebnisse": [{"spot": "a", "name": "A", "quelle": "DWD", "km": 1.0,
                               "station": {"id": "1", "name": "S"},
                               "reihen": {"Wingfoilscout": {"n": 500, "mae": 3.1, "bias": -0.4}},
                               "sessions": {"f1": 0.66}}]}
        with tempfile.TemporaryDirectory() as d:
            pfad = Path(d) / "grundlinie.json"
            ps.grundlinie_schreiben(erg, "1.8.0", pfad)
            g = ps.grundlinie_lesen(pfad)
        self.assertEqual(g["version"], "1.8.0")
        self.assertEqual(g["ergebnisse"]["a"]["reihen"]["Wingfoilscout"]["mae"], 3.1)


class Bericht(unittest.TestCase):
    def test_bericht_zaehlt(self):
        text = ps.bericht([("Eins", [("ok", "a"), ("warnung", "b"), ("fehler", "c")], "Tabelle")])
        self.assertIn("✓ a", text)
        self.assertIn("✗ c", text)
        self.assertIn("1 ok · 1 Warnungen · 1 Fehler", text)
        self.assertIn("Tabelle", text)

    def test_werkzeug_laeuft_ohne_netz_durch(self):
        """`--nur land --ohne-netz`: der Teil ohne Netz muss grün sein und 0 zurückgeben."""
        import subprocess
        import sys
        p = subprocess.run([sys.executable, str(ROOT / "tools" / "pruefstand.py"), "--nur", "land",
                            "--ohne-netz"], capture_output=True, text=True, timeout=120)
        self.assertIn("ohne Netz · Geometrie: kein Wasser", p.stdout)
        self.assertIn("0 Fehler", p.stdout)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_sonde_laeuft_mit_untergeschobenen_diensten(self):
        """Die Sonde selbst, ohne Netz: jeder Dienst wird untergeschoben, der
        Ablauf muss bis zum Ende laufen und 0 zurückgeben. Am 19.09. brach sie
        an einer Tupel-Entpackung — `*zeitraum` entpackte einen String — und
        kein Test hatte den Ablauf je ausgeführt."""
        import importlib.util
        from tests.helpers import cfg as load_cfg
        from wingscout.spots import load_spots
        from wingscout.sources import historisch
        spec = importlib.util.spec_from_file_location("pruef_tool", ROOT / "tools" / "pruefstand.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        st = {"id": "1", "name": "Test", "lat": 51.7625, "lon": 3.854}

        def liste(spot=None):
            return [st]

        def stunden(station, von, bis):
            return {"quelle": "X", "station": station,
                    "stunden": {f"{von}T12:00": {"kn": 10.0, "dir": 200.0}, f"{bis}T13:00": {"kn": 12.0, "dir": 210.0}}}

        fc = {"hourly": {"time": ["2026-08-01T00:00"], "wind_speed_10m_dwd_icon_seamless": [1.0]}}
        quellen = {land: (name, liste, stunden) for land, (name, _, _) in stationen.QUELLEN.items()}
        import io
        from contextlib import redirect_stdout
        aus = io.StringIO()
        with mock.patch.dict(stationen.QUELLEN, quellen, clear=True), \
                mock.patch.object(historisch, "hole", return_value=fc), \
                mock.patch.object(historisch, "hole_bis_heute", return_value=fc), \
                mock.patch.object(stationen, "rws_stationen", return_value=[st]), \
                redirect_stdout(aus):
            code = tool.sonde(load_cfg(), load_spots(ROOT / "spots.yaml"))
        text = aus.getvalue()
        self.assertEqual(code, 0, text)
        # Fehlt Rijkswaterstaat in der NL-Liste, sagt die Sonde warum — am
        # 20.09. stand dort nur „49 Stationen“, und der Ausfall war unsichtbar
        aus2 = io.StringIO()
        with mock.patch.dict(stationen.QUELLEN, quellen, clear=True), \
                mock.patch.object(historisch, "hole", return_value=fc), \
                mock.patch.object(historisch, "hole_bis_heute", return_value=fc), \
                mock.patch.object(stationen, "rws_stationen", side_effect=stationen.StationError("HTTP 404")), \
                redirect_stdout(aus2):
            code2 = tool.sonde(load_cfg(), load_spots(ROOT / "spots.yaml"))
        self.assertEqual(code2, 1)
        self.assertIn("✗ Rijkswaterstaat: Stationsliste — HTTP 404", aus2.getvalue())
        self.assertIn("Brouwersdam ↔ X Test (0.0 km), 2026-08-01–2026-08-31: 2 Stunden", text)
        self.assertIn("letzte", text)
        self.assertIn("Open-Meteo bis heute", text)
        self.assertNotIn("✗", text)
        # Jeder Dienst für sich: die Teststation liegt am Brouwersdam, also
        # findet DWD keinen DE-Spot in Reichweite — und sagt das, statt das
        # niederländische Paar noch einmal zu zeigen
        self.assertIn("keine Station in 12 km um einen DE-Spot", text)
        # Windguru-Stationen kommen aus der Konfiguration; die Teststation
        # gilt als konfiguriert und wird gegen den nächsten Spot geprüft
        self.assertIn("Windguru: 1 Stationen aus der Konfiguration", text)
        # Ohne Windguru-Eintrag in der Konfiguration: Hinweis, kein Fehler
        quellen["WG"] = (stationen.QUELLEN["WG"][0], lambda spot=None: [], stunden)
        aus = io.StringIO()
        with mock.patch.dict(stationen.QUELLEN, quellen, clear=True), \
                mock.patch.object(historisch, "hole", return_value=fc), \
                mock.patch.object(historisch, "hole_bis_heute", return_value=fc), \
                mock.patch.object(stationen, "rws_stationen", return_value=[st]), \
                redirect_stdout(aus):
            code = tool.sonde(load_cfg(), load_spots(ROOT / "spots.yaml"))
        self.assertEqual(code, 0, aus.getvalue())
        self.assertIn("Windguru: keine Station in der Konfiguration", aus.getvalue())
        self.assertIn("--config config.yaml", aus.getvalue())


if __name__ == "__main__":
    unittest.main()
