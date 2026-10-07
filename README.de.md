# Wingfoilscout

*Diese Anleitung auf: [English](README.md) · **Deutsch** · [Français](README.fr.md) · [Español](README.es.md)*

Findet Wingfoil-Sessions im Umkreis und schreibt einen HTML-Report:
**wo es weht, wann, mit welchem Wing — und ob die Fahrt sich rechnet.**

Dafür verbindet Wingfoilscout drei Wettermodelle (plus ein Ensemble für die
Verlässlichkeit) mit Wissen über 278 Spots: Windsektoren, Ufergeometrie aus
OpenStreetMap, Tiden, Thermik, Fahrzeiten. Läuft lokal auf dem eigenen
Rechner, ohne Konto und ohne Fremdpakete außer PyYAML. Alle Windangaben in
**Knoten**. Die Oberfläche spricht Englisch, Deutsch, Französisch und
Spanisch.

<p align="center">
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/bilder/en/search-dark.png"><img src="docs/bilder/en/search-light.png" width="250" alt="Suche: Startpunkt, Startzeitpunkt, Favoriten und Voreinstellungen"></picture>
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/bilder/en/destinations-dark.png"><img src="docs/bilder/en/destinations-light.png" width="250" alt="Ein Favorit, dann die besten drei Ziele"></picture>
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/bilder/en/grid-dark.png"><img src="docs/bilder/en/grid-light.png" width="250" alt="Stundenraster: alle Spots Stunde für Stunde"></picture>
</p>
<p align="center"><sub>Beispielansicht mit erfundenen Wetterdaten ·
<a href="https://darkpiratego.github.io/wingfoilscout/">Website</a> ·
<a href="https://darkpiratego.github.io/wingfoilscout/demo.html">Beispiel-Report</a></sub></p>

Bis Version 2.0 hieß das Projekt **Wingscout**; ältere Einträge im Changelog
und in den Review- und Prüfberichten tragen noch diesen Namen. Intern heißt
das Python-Paket weiter `wingscout` — deshalb lauten die Befehle unten so.

Die aktuelle Version steht in `wingscout/__init__.py`, unter dem Logo rechts in der Reiterleiste jeder Seite und im Fuß jedes Reports · wie Wingfoilscout entscheidet: [`SCORING.md`](SCORING.md) · Änderungen in [`CHANGELOG.md`](CHANGELOG.md) (ältere Einträge auf Deutsch) · offene Befunde in [`REVIEW.md`](REVIEW.md) (deutsch, historisch) · Lizenz: [PolyForm Noncommercial 1.0.0](LICENSE) (© 2026 DARK)

---

## Installation

### Mac, mit Terminal (empfohlen)

Zwei Zeilen zum Einfügen ins **Terminal** — es liegt unter Programme →
Dienstprogramme, oder „Terminal“ in Spotlight eintippen:

1. **Einmal pro Mac: Apples Befehlszeilenwerkzeuge.** Sie bringen Python und
   `git` mit:

   ```bash
   xcode-select --install
   ```

   Ein Fenster fragt, ob sie installiert werden sollen: **Installieren**
   klicken, die Lizenz akzeptieren und warten, bis gemeldet wird, dass die
   Software installiert wurde — das dauert ein paar Minuten. Antwortet das
   Terminal, die Werkzeuge seien schon installiert, gleich weiter.

2. **Wingfoilscout holen und starten:**

   ```bash
   cd ~ && git clone https://github.com/DarkPirateGo/wingfoilscout.git && cd wingfoilscout && bash "Wingfoilscout starten.command"
   ```

   Die ganze Zeile auf einmal einfügen; jeder Teil läuft nur, wenn der davor
   geklappt hat. Sie legt den Ordner `wingfoilscout` in deinem
   Benutzerordner an, installiert beim ersten Mal PyYAML und öffnet die
   Oberfläche im Browser.

Danach startest du Wingfoilscout mit Doppelklick auf **„Wingfoilscout
starten“** in diesem Ordner und holst neue Versionen mit Doppelklick auf
**„Neuen Stand holen“** — alle Doppelklick-Dateien sind
[unten](#doppelklick-dateien) erklärt. Was `git` geholt hat, kam nicht über
den Browser, deshalb hält macOS es nicht auf.

Den Startpunkt wählst du in der Oberfläche. Dein Material trägst du einmal
in `config.yaml` ein — eine Textdatei im selben Ordner, die beim ersten
Start aus `config.example.yaml` entsteht.

### Mac, ohne Terminal

1. Auf der [Release-Seite](https://github.com/DarkPirateGo/wingfoilscout/releases/latest)
   unter „Assets“ **Source code (zip)** herunterladen und mit Doppelklick
   entpacken, falls der Browser das nicht schon getan hat.
2. Im Ordner **„Wingfoilscout starten“** doppelklicken. Beim ersten Mal
   lehnt macOS ab: *„Wingfoilscout starten.command“ nicht geöffnet — Apple
   konnte nicht überprüfen, ob „Wingfoilscout starten.command“ frei von
   Schadsoftware ist …* Die Datei kommt aus dem Internet und ist nicht von
   einem bei Apple registrierten Entwickler signiert. **Fertig** klicken.
3. **Systemeinstellungen → Datenschutz & Sicherheit** öffnen und nach unten
   zu **Sicherheit** scrollen: Dort steht, dass „Wingfoilscout
   starten.command“ blockiert wurde. **Dennoch öffnen** klicken, falls
   gefragt mit dem Passwort bestätigen, und wenn die Warnung noch einmal
   kommt, **Öffnen** klicken. Bis macOS 14 genügt Rechtsklick auf die Datei
   → **Öffnen**.
4. Fragt macOS, ob das Terminal auf den Ordner „Downloads“ zugreifen darf:
   erlauben. Bietet es an, die **Befehlszeilenwerkzeuge** zu installieren:
   installieren — sie bringen Python mit —, warten, bis es fertig ist, und
   noch einmal doppelklicken; das Startskript erkennt diesen Fall und sagt
   es.
5. Beim ersten Start installiert das Skript PyYAML; dann öffnet sich die
   Oberfläche im Browser.

Jede Doppelklick-Datei braucht Schritt 3 einmal, auch „Wingfoilscout fürs
iPhone starten“. Neue Versionen gibt es auf diesem Weg nur als neues ZIP:
`config.yaml`, `tagebuch.json`, `modellguete.json`, `ui_defaults.json`,
`favoriten.json` und `sprache.txt` aus dem alten Ordner in den neuen kopieren. Selbst
eingetragene Spots bleiben in der `spots.yaml` des alten Ordners — der Weg
übers Terminal behält sie beim Aktualisieren.

### Von Hand, oder unter Windows und Linux

Mit Python 3.9 oder neuer und `git`:

```bash
git clone https://github.com/DarkPirateGo/wingfoilscout.git
cd wingfoilscout
python3 -m pip install -r requirements.txt      # nur PyYAML
tools/install-hooks.sh                          # optional: Prüflauf vor jedem Commit
python3 -m wingscout.webui                      # Start: öffnet die Oberfläche im Browser
```

Auf dem Mac kommen Python 3.9 und `git` mit Apples Befehlszeilenwerkzeugen
(Schritt 1 oben). Sonst keine Abhängigkeiten außer PyYAML: Die Wetterdaten
kommen über die Standardbibliothek, der Report ist eine einzelne HTML-Datei.
Unter Windows startet `wingfoilscout.bat` die Oberfläche (ungetestet).

Eine Einschränkung hat Apples Python trotzdem: Es ist gegen LibreSSL 2.8.3 von
2018 gebaut. Damit kommt keine Verbindung zum Routing-Server zustande, das Log
meldet `SSLV3_ALERT_HANDSHAKE_FAILURE`, und die Anfahrt bleibt eine Schätzung
aus Luftlinie mal Faktor. Wetter und Report sind davon nicht betroffen. Ob es
dich betrifft, sagt

```bash
python3 -c "import ssl; print(ssl.OPENSSL_VERSION)"
```

Steht dort *LibreSSL*, behebt ein aktuelles Python (`brew install python` oder
der Installer von python.org, danach ein **neues** Terminalfenster) die Sache;
das bringt OpenSSL 3 mit. Steht dort *OpenSSL*, ist alles in Ordnung.

Danach `config.yaml` anpassen: `rider.home` auf den eigenen Startpunkt,
`quiver.wings` auf das eigene Material. Die Datei ist durchkommentiert; alles
darin ist zum Ändern da.

### Doppelklick-Dateien

Im Ordner liegen ein paar Dateien zum Doppelklicken im Finder auf dem Mac,
dazu `wingfoilscout.bat` für Windows. Ihre Namen bleiben in jeder Sprache
deutsch; diese Anleitung nennt sie ohne die Endung `.command`.

| Datei | Wofür | Was sie tut |
|---|---|---|
| `Wingfoilscout starten.command` | Start | öffnet die Oberfläche im Browser; installiert vorher PyYAML, falls es fehlt |
| `Wingfoilscout fürs iPhone starten.command` | Start mit iPhone-Zugang | dasselbe, aber die Oberfläche ist auch von einem iPhone im selben WLAN aus erreichbar (siehe [Auf dem iPhone](#auf-dem-iphone)) |
| `wingfoilscout.bat` | Start unter Windows | Windows: öffnet die Oberfläche im Browser |
| `Neuen Stand holen.command` | Aktualisieren | holt den aktuellen Stand von GitHub, ohne deine eigenen Änderungen zu verlieren, und lässt danach die Tests laufen (braucht einen `git`-Klon) |
| `Auf GitHub veröffentlichen.command` | Veröffentlichen | Prüflauf, Commit und Push — für Mitwirkende |
| `Tests ausführen.command` | Prüfung ohne Netz | der volle Prüflauf mit allen Tests (`tools/check.sh`) |
| `Ufergeometrie berechnen.command` | Ufergeometrie per Skript | einmaliger Lauf von `build_geometry.py` (siehe [Ufergeometrie](#ufergeometrie)) |
| `Prüfstand.command` | Prüfung mit Netz | startet `tools/pruefstand.py` (siehe [Der Prüfstand](#der-prüfstand--stimmt-es-noch)) |

## Benutzung

**Ohne Terminal:** Im Finder auf **„Wingfoilscout starten“** doppelklicken
(unter Windows: `wingfoilscout.bat`). Es öffnet sich eine Oberfläche im
Browser. Vorn stehen nur zwei Fragen — **Von wo aus?** und **Ab wann?** —,
deine [Favoriten](#favoriten) und darunter drei Voreinstellungen:

| | Tage | Nächte | Radius |
|---|---|---|---|
| **Spontan** | 2 | – | 250 km |
| **Wochenende** | 3 | – | 500 km |
| **Mit Übernachtung** | 4 | 2 am Stück | 1000 km |

Eine davon antippen, **„Spots suchen“** drücken, der Report erscheint
darunter. Das ist der ganze übliche Weg. Die Tage zählen ab jetzt — oder ab
dem Startzeitpunkt, wenn du einen setzt (siehe [Startzeitpunkt](#startzeitpunkt)).

Alles Feinere liegt hinter drei Klappen, und die behalten ihre Werte:

- **Suche genauer einstellen** — Zeitraum, Radius, Übernachtungen, Fahrzeit,
  was als Session zählt, Temperatur- und Böigkeitsgrenzen, Kabbel-Aversion,
  Seegras, Gewässertypen. Stellst du hier etwas um, erlischt die
  Voreinstellung, und darunter steht, was gerade gilt.
- **Datenquellen** — Ufergeometrie, Routing, Ensemble, Stellplätze, Marine,
  Warnungen, Demo-Modus. Hier sitzt auch der Knopf
  **„Fehlende berechnen“** für die Ufergeometrie, mit der Zahl der noch
  fehlenden Spots daneben.
- **Spots hinzufügen** — siehe unten.

Vier Felder tragen ein Fragezeichen mit Kurzerklärung: **Radius** (eine
Fahrstrecke, keine Luftlinie — siehe [Fahrzeit](#fahrzeit-geroutet-statt-geschätzt)),
**Mindestgüte**, **Böigkeit max.** und **Kabbel-Aversion**. Deren Namen sagen
aus sich heraus nichts, und im Report stehen sie später als Zahl da.

**„Als Standard merken“** speichert deine Eingaben als neue Startwerte (in
`ui_defaults.json`; deine kommentierte `config.yaml` bleibt unangetastet).

**Sprache:** Oberfläche und Report gibt es auf Englisch, Deutsch,
Französisch und Spanisch. Der Umschalter (DE · EN · FR · ES) sitzt oben
rechts neben dem Logo — am Handy im Fuß der Seite. Deine Wahl steht in
`sprache.txt` im Wingfoilscout-Ordner und gilt sofort für jede Seite — auch
für „Ziele“: Jede Suche legt ihren Report in allen vier Sprachen ab (in
`cache/report/`), Umschalten braucht also keine neue Suche. Nur die Datei
`report.html`, die du per AirDrop aufs Handy schicken kannst, bleibt in der
Sprache, in der die Suche lief; ein Report von vor 2.3.0 liegt bis zur
nächsten Suche nur in einer Sprache vor. Bis du eine wählst, richtet sich Wingfoilscout nach deinem
Browser: die erste der vier Sprachen in der Reihenfolge, die dein Browser
bevorzugt — Englisch, wenn er keine davon verlangt, Deutsch, wenn er gar keine
Sprache mitschickt. Die Umgebungsvariable `WINGSCOUT_SPRACHE` (`de`, `en`,
`fr` oder `es`) geht beidem vor. Zahlen, Datum und Uhrzeit stehen in der
Schreibweise der jeweiligen Sprache (auf Deutsch 4,2 und 20.09.2026 19:09).
Die Kommandozeile und die Terminalfenster der Doppelklick-Dateien wählen ihre
Sprache selbst, siehe [Kommandozeile](#kommandozeile).

**Hilfe in der App:** Der Knopf **?** oben rechts auf jeder Seite (am Handy
neben „Beenden“) öffnet diese Anleitung und die bebilderte Seite „Wie
Wingfoilscout rechnet“ — in der Sprache, die du gewählt hast.

Eine Grenze: Was aus Daten kommt statt aus dem Programm, bleibt in seiner
Originalsprache, meist Deutsch — Spotnamen, Notizen und die übrigen Texte im
Katalog (`spots.yaml`) sowie manche Orts- und Gebietsnamen aus
OpenStreetMap.

Nach **„Neuen Stand holen“** läuft eine schon offene Oberfläche mit dem alten
Code weiter, bis du Wingfoilscout beendest und neu startest — jede Seite zeigt
dann einen Balken, der das sagt. Und der Rückblick zeigt beim Öffnen sein
letztes Ergebnis; ist es älter als die letzte Suche oder mit einer früheren
Version gerechnet, steht das darüber, und „Prüfen“ rechnet neu.

### Startpunkt unterwegs

Oben in der Oberfläche steht **Von wo aus?**. Leer gelassen rechnet
Wingfoilscout ab deinem Zuhause, `rider.home` in `config.yaml` (die Vorlage
hat die Hamburger Innenstadt als Platzhalter). Trägst du etwas ein, gelten
Radius, Entfernung und Fahrzeit ab diesem Punkt — das ist der Fall, wenn du
schon unterwegs bist und wissen willst, was von *hier* aus geht.

Erkannt werden Dezimalgrad (`51.7625, 3.854` — Dezimalkomma oder -punkt),
Grad/Minuten/Sekunden (`51°45'45"N 3°51'14"E`) und ein hineinkopierter
Google-Maps-Link. Ein Ortsname („Hamburg“) ist keins davon: Seit 1.19.0 weist
Wingfoilscout ihn vor dem Start ab und sagt, was geht — vorher lief die Suche
still von Zuhause aus. Der Banner am Ende nennt den benutzten Startpunkt.

Dazu gibt es zwei Knöpfe. **„Karte“** klappt eine Karte auf: Klick hinein oder
Nadel ziehen, fertig — das ist der Weg, der immer funktioniert, solange Netz
da ist. **„Hier“** fragt den Browser nach der Ortung; das ist bequemer, hängt
aber davon ab, ob das Betriebssystem eine Position liefert. Safari auf macOS
antwortet hier gelegentlich gar nicht (Zeitüberschreitung), typischerweise
wenn WLAN aus ist — Macs orten sich über die WLAN-Netze in der Umgebung, nicht
über GPS. Die Meldung unter dem Knopf sagt jeweils, woran es lag.

Der Startpunkt wird bewusst **nicht** von „Als Standard merken“ gespeichert —
er gilt für heute und hier, nicht für den nächsten Start. Auf der
Kommandozeile geht dasselbe mit `--start "51.7625, 3.854"` und optional
`--start-name Brouwersdam`.

### Startzeitpunkt

Unter dem Startpunkt steht **Ab wann?**. Leer gelassen beginnt die Suche
jetzt, wie bisher. Wählst du Datum und Uhrzeit — etwa Samstag 9:00 —,
zählen die Tage der Voreinstellung ab diesem Tag, und die Stunden davor
stehen im Stundenraster blass als „vor dem gewählten Start“: So schaust du
schon am Mittwoch nur aufs Wochenende.

Die Vorhersagen reichen 16 Tage ab heute; unter dem Feld steht, bis wann.
Reichen Start und Tage darüber hinaus, kürzt die Suche den Zeitraum und sagt
es im Protokoll. Die Uhrzeit ist die deines Rechners; für jeden Spot wird sie
in dessen Ortszeit umgerechnet, wie jede Uhrzeit im Report. **„Jetzt“** leert
das Feld. Wie der Startpunkt wird der Startzeitpunkt **nicht** von „Als
Standard merken“ gespeichert. Auf der Kommandozeile: `--ab "2026-10-10 09:00"`
(oder `10.10.2026 09:00`, oder nur das Datum).

### Favoriten

Unter dem Startzeitpunkt steht **Favoriten**: deine Lieblingsspots, auf die
jede Suche zuerst schaut. Tipp einen Teil des Namens ein — „edersee“,
„tarifa“; Akzente sind egal, „etang“ findet „Étang de Leucate“ — und wähl den
Spot aus der Liste, die aufgeht (Pfeiltasten und Enter gehen auch). Er landet
als kleine Plakette in deiner Liste; ihr × nimmt ihn wieder heraus. Bis zu
zehn, in der Reihenfolge, in der du sie hinzufügst.

Sobald die Liste einen Eintrag hat, erscheint der Schalter **„Favoriten
zuerst zeigen“** (anfangs an). Mit ihm rechnet jede Suche deine Favoriten mit
— **auch außerhalb des Radius und trotz der Filter** (Saison, Gewässerarten,
Seegras, Hunde …) —, und der Report beginnt mit ihnen: **Favoriten → die
besten drei → Karte**. Jeder Favorit bekommt dieselbe Karte wie ein Ziel der
Suche, mit einem ★ statt des Rangs und einer Plakette: **Platz 4**, wenn er
auch unter den Zielen der Suche steht, oder **außerhalb der Suche**, mit dem
Grund als Tooltip („2799 km — außerhalb des Radius von 600 km“, „außerhalb der
Saison“). Ein Favorit ohne Session im Zeitraum bekommt eine flache Karte, die
sagt, warum — „Höchstens 8 kn (Sa 10.10. 14 Uhr) — dein Quiver fängt bei
10 kn an“ oder, wo Wind wäre, was diese Stunden ausschließt, in den Worten des
Stundenrasters („Wasser 9 °C unter deiner Grenze von 12 °C“, „außerhalb des
Tidenfensters …“) —, dazu die Absprünge zu Windy, Route und Karte. Unter den
besten drei und den weiteren Zielen trägt ein Favorit einen ★ vor dem Namen.

Die besten drei, die Karte und das Stundenraster bleiben die normale Suche:
Favoriten außerhalb davon tauchen dort nicht auf und verdrängen nichts. Sie
werden zusätzlich geholt und gerechnet — ein Grund, warum die Liste bei zehn
endet.

Jede Änderung wird sofort gemerkt, in `favoriten.json` im
Wingfoilscout-Ordner — persönlich wie das Tagebuch, nicht versioniert und
nicht Teil von „Als Standard merken“. Schaltest du „Favoriten zuerst zeigen“
aus, läuft die Suche ohne sie; die Liste bleibt. Auf der Kommandozeile nimmt
`--favoriten` allein die Liste aus der Oberfläche, `--favoriten
brouwersdam,silvaplana` die angegebenen Spot-IDs (die ID eines Spots steht in
`spots.yaml`).

### Spots hinzufügen

In der Klappe **Spots hinzufügen**. Eine Zeile je Spot, in jeder
Schreibweise, die unterwegs anfällt:

```
Hardtsee; 49.17008, 8.61477
49.17008, 8.61477 Hardtsee
Bostalsee; 49.56831, 7.07964; reservoir
https://www.google.com/maps/@51.7625,3.854,15z
```

Name davor oder dahinter, Gewässerart optional als letztes Feld (`sea`,
`lagoon`, `lake`, `reservoir`). Grad/Minuten/Sekunden werden ebenso erkannt.
Über das Dateifeld gehen außerdem die üblichen Exportformate: **GPX**
(Wegpunkte), **KML** aus Google My Maps (Ortsmarken), **GeoJSON** aus Google
Takeout und **CSV** mit Spalten für Breite und Länge. Eine KMZ-Datei ist ein
gepacktes KML — entpacken und die enthaltene `doc.kml` laden.

Eine Warnung zu Google-Listen aus Takeout: Deren CSV enthält oft nur Titel,
Notiz und eine Maps-Adresse mit Orts-ID, aber keine Koordinate. Steht im Link
eine Position (`.../@51.7625,3.854,15z`), wird sie genommen; sonst wird die
Zeile übersprungen und gezählt. Eine Orts-ID lässt sich ohne Abfrage bei
Google nicht in eine Koordinate übersetzen, und geraten wird hier nichts.
Punkte, die weniger als 300 m von einem vorhandenen Spot entfernt liegen,
werden übersprungen und gemeldet.

Die Spots landen in `spots.yaml` und zählen ab der nächsten Suche mit. Ist der
Haken **Ufergeometrie gleich mitrechnen** gesetzt, wird die Geometrie direkt
danach für die neuen Spots geholt — etwa eine Viertelminute je Spot.

Für alles, was dabei offenblieb, gibt es unter Datenquellen den Knopf
**Fehlende berechnen**. Daneben steht, wie viele Spots noch keine Geometrie
haben. Der Lauf arbeitet den Katalog der Reihe nach ab, speichert nach jedem
Spot und zeigt den Fortschritt im selben Protokoll; Abbrechen ist harmlos, und
beim nächsten Klick geht es bei den offenen weiter. Das Skript
`build_geometry.py` macht dasselbe und bleibt für die Kommandozeile erhalten —
nötig ist es aber nicht mehr.

Geraten werden dabei drei Dinge, die du nachsehen solltest: die Gewässerart
(Voreinstellung `lake`), der Untergrund (`shallow: none`, `seagrass: none`)
und das Landeskürzel, das aus groben Landesrahmen stammt und in Grenznähe
danebenliegen kann — es steuert nur, welcher Warnfeed gilt. Die Windsektoren
bleiben leer; die liefert die Ufergeometrie.

### Spot für alle vorschlagen

Spots, die du selbst einträgst, bleiben auf deinem Rechner. Damit einer für
alle in den Katalog kommt, gibt es **„Für alle vorschlagen“** — in der
Klappe **Spots hinzufügen** und unter **„Neuen Spot eintragen“** im Katalog.
Es öffnet ein Formular auf GitHub; im Katalog ist es schon mit dem
ausgefüllt, was du darüber eingegeben hast (Name, Koordinate, Notiz). Neben
jedem Spot im Katalog tut
**Korrektur vorschlagen** dasselbe für einen Spot, den es schon gibt. Du
brauchst ein kostenloses GitHub-Konto, und gesendet wird erst, wenn du das
Formular dort abschickst. Es fragt nach dem Gewässer, guten Windrichtungen,
dem, was andere wissen sollten, und woher dein Wissen stammt. Das Formular
geht auch direkt auf:
https://github.com/DarkPirateGo/wingfoilscout/issues/new?template=spot.yml

Jeder Vorschlag wird von Hand geprüft und kommt in den Katalog der nächsten
Version — jeder, der aktualisiert, bekommt ihn. Mit dem Abschicken bist du
einverstanden, dass er unter der Lizenz von Wingfoilscout veröffentlicht
wird und DARK ihn auch unter anderen Bedingungen nutzen darf
([CONTRIBUTING.md](CONTRIBUTING.md)).

### Koordinaten prüfen

Unter **Datenquellen** steht ein Knopf **„Koordinaten prüfen“**, sobald es
etwas zu prüfen gibt; ebenso der gleichnamige Reiter oben (seit 1.16.1 nur
dann — ist nichts offen, verschwindet er, und die Seite bleibt unter
`/pruefen` erreichbar). Er öffnet eine eigene Seite: links eine Karte, rechts
die Spots, die nachgesehen gehören. Ein Filter über der Liste trennt drei
Stufen:

- **Unbrauchbar** — höchstens 100 bis 300 m Wasser in *jeder* Richtung. Da
  liegt der Pin fast sicher an Land, auf einem Parkplatz oder im falschen
  Gewässer.
- **Fragwürdig** — mehr als einen Kilometer vom Pin ins Wasser versetzt.
  Nutzbar, aber der Pin sitzt schief.
- **Unbestätigt** — `verified: false`: Die Koordinate stammt aus einer
  importierten Liste, und niemand hat je hingeschaut. Bei der Takeout-Liste
  liegt sie bis etwa einen Kilometer daneben, weil die Spalte dort gerundet
  war. Das ist kein Fehler, nur eine offene Frage — diese Spots sind nach
  Entfernung vom Startpunkt sortiert, die nächsten zuerst, denn die kennst du
  am ehesten selbst.

Beide Knöpfe schreiben in `spots.yaml`: **„Übernehmen“** setzt die neue
Koordinate, **„Passt so“** bestätigt die vorhandene. Beide setzen
`verified: true` — wer die Nadel selbst gesetzt oder den Punkt angesehen hat,
hat damit geprüft. `geo_ok: true` kommt nur dort dazu, wo es auch wirklich
eine Geometriewarnung gibt.

Wichtig ist, was *nicht* in der Liste steht: Ein 800-Meter-Baggersee hat in
keiner Richtung offenes Wasser, und das ist kein Fehler. Eine frühere Fassung
meldete genau solche Spots und übersah dafür die wirklich falschen — eine
Liste, die das Falsche meldet, liest man nach dem zweiten Mal nicht mehr.

Korrigiert wird auf der Karte: Spot anklicken, Nadel ins Wasser ziehen oder
hineinklicken, **Übernehmen**. Die Koordinate landet in `spots.yaml` (samt
`verified: true`), die alte Ufergeometrie wird verworfen und sofort neu
gerechnet — nach ein paar Sekunden steht da, wie viel Anlauf der Spot jetzt
hat. Stimmt die Koordinate doch, nimmt **Passt so** den Spot dauerhaft aus der
Liste (`geo_ok: true` im Katalog).

Die Kommentare in `spots.yaml` bleiben dabei erhalten: Geschrieben wird auf
Textebene, nicht über einen YAML-Rundlauf.

### Katalog — alle Spots auf einen Blick

Der Reiter **Katalog** oben auf jeder Seite zeigt alle Spots, die
Wingfoilscout kennt: Suche über Name, Kennung, Region und Notiz; Filter nach
Land, Gewässerart und Merkmal (unbestätigt, mit Thermik, mit Shorebreak, mit
Instagram-Funden, Instagram noch nicht gesucht); sortierbar nach Name, Land,
Gewässerart und Entfernung vom Startpunkt. Ein Klick auf eine Zeile springt
auf der Karte zum Spot; die Karte zeigt immer die aktuelle Auswahl. Je Spot
stehen die Plaketten (bestätigt, Thermikwind, Shorebreak, Zugang, Hunde) und
die Absprünge zu Windy, OpenStreetMap und Instagram.

Unten auf der Seite: **„Schon drin?“** — Koordinate oder Namen eintippen, und
die Seite sagt, ob ein Spot in der Nähe schon im Katalog steht (bis 300 m:
„so gut wie derselbe Punkt“, bis 3 km: „in der Nähe“). So vermeidest du,
einen Spot zweimal einzutragen.

**Pflegen lässt sich der Katalog hier auch.** Darunter
**„Neuen Spot eintragen“**: Name, Koordinate, Gewässerart, Land (leer heißt
raten), Notiz, Kommentar — und auf Wunsch wird die Ufergeometrie gleich
gerechnet. Liegt schon ein Spot näher als 300 m, sagt die Seite es und trägt
erst auf „Trotzdem eintragen“ ein. In jeder Zeile stehen drei kleine Aktionen: **umbenennen**
(der Name ändert sich, die Kennung bleibt — an ihr hängen Ufergeometrie,
Instagram-Momentaufnahme und Prüfstand), **verschieben** (eine Nadel erscheint
auf der Karte: ziehen oder in die Karte klicken, dann „Übernehmen“ — dasselbe
wie auf der Prüfseite, mit neu gerechneter Ufergeometrie und `verified: true`)
und **löschen** (mit Nachfrage; der Spot verschwindet aus `spots.yaml`,
`geometry.json` und `instagram.json`, und sein Block steht im Protokoll, falls
es ein Versehen war). Alles wird auf Textebene in `spots.yaml` geschrieben,
und die Kommentare bleiben; während eine Suche oder ein Geometrielauf läuft,
wartet die Seite (409).
Daneben öffnet **Korrektur vorschlagen** das Formular auf
GitHub für diesen Spot (siehe [Spot für alle vorschlagen](#spot-für-alle-vorschlagen)).

### Dein Kommentar zu jedem Spot

Überall, wo ein Spot auftaucht, steht dein eigener Kommentar dabei und lässt
sich dort auch schreiben: im Katalog, an jedem Ziel im Report, im Popup auf
der Karte, auf der Prüfseite und im Rückblick — und beim Eintragen eines
neuen Spots gleich mit. „Kommentar schreiben“ öffnet ein Feld, „Speichern“
schreibt ihn als `comment` in `spots.yaml` (mehrzeilig, bis 2000 Zeichen;
leer gespeichert, verschwindet er wieder). Auch die Suche im Reiter Katalog
findet ihn.

Der Kommentar ist etwas anderes als die `notes`: Die Notiz beschreibt den
Spot (Herkunft, Regeln, was die Quelle sagt), der Kommentar ist deine eigene
Erfahrung — wo man parkt, wo der Einstieg ist, wie es beim letzten Mal war.
Er filtert nicht und geht nicht in den Score.

Eine Grenze: Der Report ist eine Datei. Solange er in der Oberfläche steht
(unter der Suche, oder über „in neuem Tab öffnen“), speichert der Kommentar
in den Katalog; öffnest du `report.html` direkt als Datei, sagt dir das Feld,
dass kein Programm dahinter ist. Ein Report zeigt den Stand des Katalogs zum
Zeitpunkt seiner Suche — ein neuer Kommentar steht sofort auf der Seite und
im nächsten Report.

### Rückblick — wie gut lag die letzte Vorhersage?

Der Reiter **Rückblick** nimmt die zehn besten Ziele der letzten Suche und
stellt für die letzten Tage **einschließlich heute, bis zur aktuellen Stunde**
(Anzahl wählbar, 1 bis 14, Voreinstellung 2) die aufgehobene Vorhersage neben
die gemessenen Winde der nächsten Wetterstation — Stunde für Stunde, als
Kurve und als Tabelle, mit mittlerem Fehler, Bias und Richtungstrefferquote
je Spot. Die Vorhersage läuft dafür durch dieselbe Bewertung wie im Report
(Regionalmodell, `wind_factor`, Thermikannahme); du siehst also, was
Wingfoilscout gesagt hätte, und was dann wirklich kam.

Was du dabei wissen musst, steht auch auf der Seite: Die aufgehobene
Vorhersage ist die mit dem kürzesten Vorlauf („heute für heute“, aus dem
Archiv von Open-Meteo), nicht die von vor drei Tagen; für den laufenden Tag
ist es die Vorhersage von heute Morgen, aus der laufenden Abfrage. Eine
Station misst über Land, der Spot liegt über Wasser — ein paar Knoten Abstand
sind normal.

Stationen kommen vom DWD (Deutschland), von KNMI und Rijkswaterstaat
(Niederlande — Rijkswaterstaat misst auf dem Wasser, an Messpfählen und
Küstenstationen), von GeoSphere (Österreich), DMI (Dänemark, seit 1.14.0) und
Météo-France (Frankreich); gesucht wird über Grenzen hinweg, ein belgischer
Spot bekommt also die nächste niederländische Station. Dazu kommen
Windguru-Stationen, wenn sie mit ihrem API-Passwort in `config.yaml` stehen
(`stationen: windguru:`, Vorlage in `config.example.yaml`) — ohne Passwort
gibt Windguru keine Messwerte heraus. **„Station bis … km“** (Vorgabe 30,
höchstens 100) legt fest, wie weit die Station vom Spot entfernt sein darf;
genommen wird die nächste, die fast alle Stunden bis jetzt hat (90 %), und hat
keine so viele, die nächste mit fast so vielen wie die beste (seit 1.14.1 —
vorher gewann die nächste, die überhaupt Werte hatte, auch wenn es nur die von
vorgestern waren). Die Station, die geliefert hat, steht mit Entfernung am
Ergebnis, eine übergangene nähere Station mit „statt …“ — je weiter weg,
desto weniger sagt sie über den Spot.

Und wie nah die Messung an „jetzt“ heranreicht, hängt am Dienst, mit Lücken:
DWD hat geprüfte Stunden bis vorgestern und den laufenden Tag aus
Zehnminutenwerten — gestern fehlt, bis die nächste Tagesdatei kommt; KNMI
reicht bis vorgestern (zwei Tage Verzug — dann steht „keine Werte für diese
Tage“ da, und die nächste Station kommt dran); Rijkswaterstaat, GeoSphere und
DMI reichen bis zur aktuellen Stunde; Météo-France bis heute früh (die
Tagesdatei erscheint morgens). Je Spot steht deshalb „Messung vorhanden: …“
mit den Stunden, die eine Messung haben; sonst bleibt die Kurve leer, und die
Kennzahlen zählen nur die gemeinsamen Stunden. Der feste Monatsvergleich für
Codeänderungen ist der **Prüfstand** ([`BENCHMARK.md`](BENCHMARK.md)); der
Rückblick beantwortet die Frage „Kann ich dem Report von eben trauen?“.

**Modelle im Vergleich** (seit 1.14.0): Unter jeder Kurve steht, welches
Wettermodell an diesem Spot am nächsten an der Messung lag — die globalen
ICON, ECMWF, das KI-Modell ECMWF-AIFS, GFS, Météo-France und UKMO und bis zu
drei Regionalmodelle, die den Spot abdecken (ICON-D2, AROME-HD, HARMONIE, CH1,
ICON-2I, AROME-AT, DMI). Die Modelle stehen roh da, ohne `wind_factor` und
Thermik; die „Wingfoilscout-Bewertung“ rechnet beides ein, als eigene Zeile.
Das Diagramm zeigt zunächst nur die Messung und als graue Fläche die Spanne
aller Modelle (seit 1.15.0). Mit den Knöpfen darunter lassen sich einzelne
Modelle, die Wingfoilscout-Bewertung und **„Bisher bestes Modell: …“**
zuschalten — das Modell, das laut Gedächtnis an diesem Spot am besten lag
(sonst über alle Spots); höchstens drei Linien zugleich. Unten auf der Seite:
die Rangliste über alle Ziele dieses Rückblicks und das **Gedächtnis** über
alle bisherigen Prüfungen (`modellguete.json`, persönlich, nicht versioniert)
— jeder Tag zählt einmal, und eine neue Prüfung ersetzt einen Tag, der schon
da ist. Nach ein paar Wochen sagt es dir, welches Modell wo trifft. Die
globalen Modelle lassen sich in `config.yaml` unter `rueckblick: modelle:`
ändern.

### Auf dem iPhone

Seit 1.17.0 ist die Oberfläche fürs Handy gebaut: unten eine Leiste mit vier
Punkten (Suche, Ziele, Rückblick, Tagebuch), der Report als Reiter „Ziele“
mit zugeklapptem Kopf, Stundenraster und breite Tabellen zum seitlichen
Wischen. Gebaut und geprüft für 320 bis 430 Punkte Breite — vom iPhone SE bis
zum Pro Max.

**Im WLAN, mit dem Mac als Rechenknecht.** Wingfoilscout hört normalerweise
nur auf 127.0.0.1. Für ein iPhone im selben Netz:

```
python3 -m wingscout.webui --lan
```

oder Doppelklick auf **„Wingfoilscout fürs iPhone starten“**. Das Terminal
zeigt dann eine Adresse wie `http://192.168.178.25:8765/?k=Xf3k…` — die in
Safari eintippen. Der Schlüssel darin ist dein Zugang: Ohne ihn bekommt jedes
andere Gerät im Netz eine 401. Er wandert einmal ins Cookie und gilt, bis
Wingfoilscout beendet wird; danach reicht die Adresse ohne `?k=`. Die Suche
läuft weiter auf dem Mac — das iPhone zeigt nur an und stößt Suchen an.

**Zum Home-Bildschirm.** In Safari „Teilen“ → „Zum Home-Bildschirm“:
Wingfoilscout startet dann wie eine App, ohne Adressleiste, mit eigenem
Symbol.

**Unterwegs ohne Mac.** Der Report ist eine einzige HTML-Datei
(`report.html` im Wingfoilscout-Ordner). Per AirDrop aufs iPhone geschickt,
lässt er sich dort ohne Netz und ohne Mac öffnen — alles außer der Karte, die
ihre Kacheln aus dem Internet holt.

### Tagebuch — deine Sessions eichen Wingfoilscout

Der Reiter **Tagebuch** (seit 1.16.0) hält fest, wie eine Session wirklich
war: Spot, Datum, Zeit von–bis, Wing, Leistung (untermotorisiert / passt /
übermotorisiert), Wasser (flach / kabbelig / Welle) und eine Note von 1
bis 5. Nach dem Eintragen holt Wingfoilscout für genau diese Stunden, was es
gesagt hätte (dieselbe Rechnung wie im Rückblick, mit Regionalmodell,
`wind_factor` und Thermik), was die einzelnen Modelle sagten und — wenn eine
Wetterstation in 30 km steht — was gemessen wurde. An der Session steht dann,
ob Wingfoilscout einen anderen Wing genommen oder anderes Wasser erwartet
hätte. Fehlt die Messung noch (DWD liefert gestern erst mit der nächsten
Tagesdatei), holt „Neu vergleichen“ sie später nach; findet ein neuer
Vergleich weniger als der alte (kein Netz), bleibt der alte stehen.

Aus mehreren Sessions werden **Vorschläge** — nie von selbst übernommen:

- **Windfenster je Wing** (`config.yaml`): untermotorisiert bei einem Wind,
  den der Quiver für diesen Wing schon als passend führt, hebt die
  Untergrenze; übermotorisiert im Fenster senkt die Obergrenze; „passt“
  außerhalb weitet das Fenster. Als Wind der Session gilt die Messung, wenn
  die Station höchstens 15 km weg ist, sonst die Vorhersage von Wingfoilscout.
- **Windfaktor je Spot** (`spots.yaml`): Jede Session grenzt ihn ein —
  „passt“ heißt, der rohe Modellwind derselben Stunden mal Faktor lag im
  Fenster des gefahrenen Wings. Vorgeschlagen wird der nächstliegende Faktor,
  zu dem alle Sessions des Spots passen (in Schritten von 0,05, zwischen 0,6
  und 1,5). Stunden mit angenommener Thermik zählen dafür nicht.

Ein Vorschlag braucht mindestens zwei Sessions, die in dieselbe Richtung
zeigen; widersprechen sich Sessions, gibt es keinen. Stützen dieselben
Sessions beide Arten von Vorschlag, sagt die Seite es dazu — beide zu
übernehmen, korrigierte denselben Befund doppelt. „Übernehmen“ ändert nur die
eine Zeile, Kommentare bleiben. Das Tagebuch liegt in `tagebuch.json` im
Wingfoilscout-Ordner: persönlich, nicht versioniert, nur auf diesem Rechner
(und in dessen Backup).

### Thermische Winde

An einer ganzen Reihe von Spots versagen die Standardmodelle. Die **Ora** am
Gardasee, der **Malojawind** im Engadin und der **Maestral** an der Adria
entstehen aus dem Temperaturunterschied zwischen Land und Wasser. Ein Gitter
von 7 bis 25 km mittelt genau die Täler und Küstenlinien weg, die diese
Zirkulation erzeugen — das Modell zeigt 5 kn, und vor Ort stehen 18 an.

**71 Spots im Katalog** tragen deshalb hinterlegtes Thermikwissen: Eigenname
des Windes, Monate, Zeitfenster, Richtung, typische Stärke, Verlässlichkeit
und **die Quelle**. Wingfoilscout nimmt dort Wind an, den kein Modell zeigt —
aber nur, wenn das Wetter dazu passt:

- **Einstrahlung seit Sonnenaufgang.** Die Thermik lebt nicht von der Sonne
  dieser Stunde, sondern davon, wie viel Wärme der Vormittag in den Boden
  gebracht hat. Deshalb die aufsummierte Globalstrahlung und nicht der
  Bedeckungsgrad — sie gewichtet hohe Cirren und tiefe Stratusdecken
  verschieden, wie es sein soll.
- **Gegenwind — und das ist der interessante Teil.** Ein ablandiger
  Gradientwind erstickt die Brise schon ab 7 bis 8 kn. Ein *schwacher*
  Gegenwind dagegen **verstärkt** sie: Er hält die Brisenfront an der Küste
  fest, statt sie landeinwärts davonlaufen zu lassen. Die Antwortkurve hat
  also ein Maximum bei etwa 3 kn Gegenwind und bricht danach steil ab. Genau
  deshalb funktioniert der Maestral — schwacher Nordwest-Gradient plus Thermik.
- **Gesperrte Grundströmung.** Der Malojawind kommt „praktisch nie bei
  nördlicher Grundströmung“, auch bei blauem Himmel. Solche Ausschlüsse stehen
  je Spot im Katalog.
- **Tageszeit** im hinterlegten Fenster, aufbauend und abflauend.

Im Report stehen die Thermikziele **als eigene Liste** direkt unter den besten
drei — sortiert nach dem Thermikpotenzial des besten Tages, nicht nach dem
Gesamtscore. Ohne diese Liste gingen sie unter, denn im normalen Ranking
zählt der Modellwind, und genau der ist dort zu niedrig. Der Balken daneben
ist das **Mittel über das ganze Thermikfenster** aus Einstrahlung und
Gegenwind, mal der Verlässlichkeit des Spots aus dem Katalog; die beste
einzelne Stunde steht im Tooltip. Bis 1.5.1 zeigte der Balken das Maximum,
und das war wertlos: An einem sonnigen Tag passt irgendwann jede Zutat, im
Lauf vom 16.09.2026 lagen deshalb alle fünf Ziele zwischen 96 und 100
Prozent. Dass der Balken nun selten über 90 Prozent geht, ist kein Defekt —
die Verlässlichkeit ist im Katalog nirgends höher als 0,95, und für die
meisten Spots ist sie ein bewusst vorsichtiger Schätzwert. Auf der Karte gibt
es dafür die Ebene **Thermische Winde**: ein orangefarbener Ring um jeden Spot mit
hinterlegtem Wissen. Der Ring ist reine Dekoration und fängt keine Klicks
ab — die Einzelheiten öffnen sich wie an jedem anderen Punkt auch.

Darunter steht **„Wann die Thermik läuft“**: dasselbe Stundenraster, aber nach
dem Thermikpotenzial eingefärbt. Orange heißt Potenzial, blass heißt
außerhalb des Fensters, und Grau heißt: Das Fenster wäre offen, aber der
Gradientwind oder die Grundströmung erstickt die Thermik heute. Ein Rahmen um
eine Stunde bedeutet, dass die Annahme dort wirklich greift — der Wind im
Report kommt aus der Thermik und nicht aus dem Modell. Anders als die Liste
darüber hängt das Raster nicht an den Zielen: Ein Spot, an dem die Modelle
keine einzige fahrbare Stunde sehen, steht trotzdem drin.

Was das Werkzeug **nicht** tut: Thermik erfinden. Es rechnet nur an Spots,
für die im Katalog steht, dass es dort eine gibt. Und wo keine Quelle eine
Stärke nennt — Chiemsee, Bodensee, Thunersee etwa —, wird
**keine angenommen**; der Spot erscheint nur als Kandidat in der Liste. Angenommener
Wind ist im Report immer als Annahme gekennzeichnet, nie als Messwert.

Abschaltbar über `thermal.enabled` in der Konfiguration, dämpfbar über
`thermal.trust`.

### Hochauflösende Regionalmodelle

Die globalen Modelle rechnen auf einem Gitter von 7 bis 25 km. Die Ora
entsteht in einem Tal, das an der engsten Stelle 2 km breit ist; der Maestral
lebt von einer Küstenlinie, die auf 25 km zu einer geraden Kante wird. Genau
diese Zirkulationen fallen durch das Gitter.

Wingfoilscout fragt deshalb zusätzlich Regionalmodelle ab, die auf
**1 bis 2,5 km** rechnen: `meteoswiss_icon_ch1` (Alpen), `italia_meteo_arpae_icon_2i`
(Oberitalien), `meteofrance_arome_france_hd`, `dwd_icon_d2`,
`knmi_harmonie_arome_netherlands`, `geosphere_arome_austria`,
`dmi_harmonie_arome_europe`. Wo eines davon antwortet, überschreibt es den
Wind — aber nur für die Stunden, die es abdeckt: Diese Modelle reichen zwei
bis drei Tage weit, die globalen bis zu sechzehn. Im Report steht bei jeder
Session, welches Modell sie geliefert hat.

Welches Modell zum Zug kommt, entscheidet **erst die Zuständigkeit, dann die
Auflösung**: für einen Punkt in Italien das italienische, auch wenn das
Schweizer ein feineres Gitter hat. Ein Modell am Rand seines Gebiets ist nicht
die bessere Auskunft — dort fehlen dem Anbieter die Stationen, gegen die er
prüft. Bei jeder Session steht der **typische** Unterschied zum groben Modell
dabei („CH1 +5 kn“) — der Median über die Stunden, die das feine Modell
abdeckt. Die Spitze steht im Tooltip. Bis 1.5.0 zeigte die Plakette die
Spitze, und das war irreführend: Sie wächst mit der Länge der Session statt
mit der Güte des Modells, weil aus mehr Stunden auch eine günstigere gezogen
wird. Im ersten echten Lauf war das messbar — Sessions bis acht
Stunden hatten im Median 0 kn, Sessions über sechzehn Stunden 6 kn.

Dass die meisten Plaketten nur den Modellnamen tragen, ist deshalb kein
Fehler, sondern das Ergebnis: Einen durchgehenden Zugewinn brachte im Lauf vom
16.09.2026 allein **CH1 in den Alpen** (Median +5 kn, 86 % der Sessions über
2 kn). **ICON-D2 an flachen deutschen Binnenseen brachte nichts** — die
Kontrollgruppe, die zeigt, dass die Rechnung stimmt: Wo es keine Zirkulation
aufzulösen gibt, gewinnt ein feineres Gitter nichts. Bei ICON-2I an der Adria
reichten sechs Sessions nicht für ein Urteil.

Zwei Eigenheiten machen das unbequemer, als es klingt. **Open-Meteo
dokumentiert nirgends, welches Modell welchen Punkt abdeckt** — in der Doku
steht nur „Central Europe“. Und eine Anfrage für einen Punkt außerhalb des
Modellgebiets wird mit HTTP 400 beantwortet, nicht mit leeren Werten: Bei
einer Sammelanfrage über zwanzig Koordinaten reißt ein einziger unpassender
Punkt alle anderen mit. Wingfoilscout halbiert deshalb abgelehnte Gruppen, bis
die Ausreißer feststehen, und **merkt sich das Ergebnis je Spot** in
`cache/highres.json`. Dieser Tanz findet einmal statt, nicht bei jedem Lauf —
und noch einmal, wenn sich die Koordinate des Spots ändert: Seit 1.7.0 trägt
jeder Eintrag im Zwischenspeicher (Overpass-Auszug, Schutzgebiete,
Modellzuordnung, Fahrzeit) die Koordinate, für die er gilt, und gilt für keine
andere.

Einmal vorab, damit der erste echte Lauf nicht damit anfängt:

```bash
python3 tools/highres_probe.py          # nur die Thermikspots
python3 tools/highres_probe.py --alle   # der ganze Katalog
```

Abschaltbar über den Haken **Hochauflösende Modelle** unter Datenquellen, über
`wind.highres` in der Konfiguration oder mit `--no-highres`.

### Wie sicher ist die Vorhersage?

Ist **Wahrscheinlichkeit (Ensemble)** angehakt, holt Wingfoilscout nach dem
Ranking für die besten Ziele zusätzlich das ICON-Ensemble: dieselbe
Wetterlage, vierzigmal mit leicht verschobenen Anfangsbedingungen gerechnet.
Jede Session bekommt dann eine Plakette — der Anteil der Rechnungen, die im
Zeitfenster über deine Fahrgrenze kommen, dazu die Spanne vom unteren zum
oberen Zehntel. Im Tooltip stehen der Median und der Anteil, der es bis ins
Wohlfühlband schafft.

Das ersetzt die Modell-Einigkeit nicht, sondern ergänzt sie: Drei Modelle
sagen dir, ob sich die Wetterdienste einig sind, vierzig Rechnungen sagen,
wie stabil die Lage überhaupt ist. Eine Einschränkung gehört dazu — das
Ensemble liegt auf einem gröberen Gitter. Am Brouwersdam landet die Abfrage
15 km vom Spot, das deterministische ICON 3 km. Deshalb wird daraus nur eine
Wahrscheinlichkeit gerechnet und nie ein Windwert überschrieben.

Seit 1.5.0 steht die Zahl nicht mehr nur da, sondern entscheidet mit. Der
Session-Score wird gedämpft mit ihr multipliziert:

    Faktor = (1 − weight) + weight · Anteil

Mit dem Standard `weight: 0.5` behält eine Session, die keine einzige der
vierzig Rechnungen trägt, die Hälfte ihres Scores — sie rutscht nach hinten,
verschwindet aber nicht. Roh zu multiplizieren würde bei einer unsicheren
Wetterlage den ganzen Report leeren, und dann stünde dort nichts, obwohl es
etwas zu entscheiden gibt. `weight: 0.0` stellt das Verhalten bis 1.4.3 her:
Die Plakette wird angezeigt und ändert nichts. Abgefragt wird für die
vordersten `ensemble.top` Ziele (Standard 20); wer dahinter liegt, wird weder
belohnt noch bestraft und kann dadurch an einem gedämpften Ziel vorbeiziehen.

Zwei Dinge weiß das Ensemble nicht, und seit 1.7.0 wird ihm beides gesagt.
Erstens kennt es weder das Regionalmodell noch den `wind_factor` eines Spots:
Gefragt wird deshalb nach der rohen Zahl, aus der nach beiden Korrekturen die
Fahrgrenze wird. Zweitens sieht es keine Thermik — an der Ora meldet es 5 kn
und 0 % Sicherheit, und bis 1.6.1 halbierte das genau die Sessions, die das
Tool eigens korrigiert hatte. An einer Thermiksession zählt jetzt die
**Verlässlichkeit des Spots** aus dem Katalog als Wahrscheinlichkeit, mit
demselben gedämpften Faktor; die Plakette sagt es („Thermik angenommen · 80 %
verlässlich“). Die Windstärke selbst ist seitdem `typical_kn` mal Potenzial —
die Verlässlichkeit steckt nicht mehr in den Knoten, wo sie einen Wert ergab,
der an keinem Tag vorkommt.

### Ortszeit

Alle Zeitangaben sind **Ortszeit am Spot**: Griechenland und Portugal werden
in ihrer eigenen Zeitzone abgefragt, die Kanaren und die Azoren in ihrer.
Jede Spalte des Stundenrasters zeigt dieselbe Ortsstunde, das Thermikfenster
aus dem Katalog gilt als Ortszeit, und „vorbei“ liest je Spot die richtige
Uhr. Bis 1.6.1 war alles Europe/Berlin — in Athen eine Stunde daneben.

### Tag, Nacht und jetzt

Eine Session liegt im Hellen und endet mit dem Tag. Sonnenauf- und
-untergang kommen aus der Vorhersage; fehlen sie, rechnet
`wingscout/sonne.py` sie aus Breite, Länge und Datum. Liegen beide vor,
vergleicht jeder Lauf sie und schreibt die größte Abweichung ins Protokoll —
so prüft sich die eigene Formel bei jedem Gebrauch selbst nach. Stunden, die
zum Zeitpunkt des Laufs schon vorbei sind, fallen ebenfalls raus.

Bis 1.4.3 galt nichts davon. Die Prüfung war eingebaut, griff aber nie: Mit
mehreren Modellen heißt das Feld in der Antwort `sunrise_dwd_icon_seamless`
statt `sunrise`. Dreißig Prozent aller Sessionstunden lagen dadurch zwischen
20 und 7 Uhr, und die längste zusammenhängende „Session“ dauerte 59 Stunden.

### Betrieb und Beenden

Die Oberfläche läuft nur auf deinem Rechner (127.0.0.1:8765) und ist von außen
nicht erreichbar. Zum Beenden dient der Knopf **Beenden** oben rechts in der
Reiterleiste, auf jeder Seite (am Handy als kleine Marke oben rechts) —
zweimal drücken, damit er nicht aus Versehen mitten in einem Lauf auslöst.

Ist Port 8765 schon von einem anderen Programm belegt (ein zweiter lokaler
Server, etwa eine andere Oberfläche, die denselben Port nimmt), weicht
Wingfoilscout auf den nächsten freien aus und sagt es im Terminal — dann
lautet die Adresse zum Beispiel `127.0.0.1:8766`, auch die fürs iPhone. Läuft
dort schon eine Oberfläche von Wingfoilscout, wird keine zweite gestartet,
sondern die laufende im Browser geöffnet. Fest wählen lässt sich der Port mit
`python3 -m wingscout.webui --port 8790`.

Eine Suche läuft im Programm, nicht im Browserfenster: Du kannst währenddessen
auf andere Reiter gehen — am Reiter „Suche“ pulst dann ein Punkt, und ist der
Report fertig, bekommt „Ziele“ einen grünen. Kommst du zur Suche zurück, zeigt
sie den laufenden oder den fertigen Lauf mit Uhrzeit. Nach dem Beenden endet
auch das Programm im Terminalfenster von selbst, und das Fenster kann
geschlossen werden. Strg+C im Terminal tut es weiterhin.

> Beim ersten Doppelklick meldet macOS möglicherweise, die Datei stamme von
> einem nicht verifizierten Entwickler. Ab macOS 15: Systemeinstellungen →
> Datenschutz & Sicherheit → ganz unten „Dennoch öffnen“; bis macOS 14 genügt
> Rechtsklick → Öffnen → Öffnen. Danach läuft sie normal. Alternativ einmal im
> Terminal: `xattr -d com.apple.quarantine "Wingfoilscout starten.command"`.

### Kommandozeile

```bash
python3 run.py                                   # 3 Tage, 500 km, öffnet den Report

python3 -m wingscout.cli --days 3 --radius 500   # Spontan-Modus
python3 -m wingscout.cli --days 7 --radius 1000  # langes Wochenende
python3 -m wingscout.cli --ab "2026-10-10 09:00" --days 2   # nur dieses Wochenende
python3 -m wingscout.cli --favoriten             # deine Favoriten zuerst (Liste aus der Oberfläche)
python3 -m wingscout.cli --demo                  # synthetische Daten, ohne Netz
python3 -m wingscout.cli --days 2 --model icon_d2 --open
```

| Option | Bedeutung |
|---|---|
| `--days N` | Vorhersagetage, 1–16 |
| `--ab ZEIT` | Startzeitpunkt statt jetzt (`2026-10-10 09:00`, `10.10.2026 09:00` oder nur das Datum); die Tage zählen ab ihm, höchstens 16 Tage voraus |
| `--radius KM` | Suchradius als Fahrstrecke in Kilometern — über OSRM geroutet, geschätzt (Luftlinie × Umwegfaktor) nur, wo OSRM nicht antwortet |
| `--max-drive H` | Obergrenze für die einfache Fahrt |
| `--min-hours H` | Mindestlänge, damit ein Block als Session zählt |
| `--model NAME` | ein Open-Meteo-Modell erzwingen, z. B. `icon_d2`, `icon_eu` |
| `--marine` | Wassertemperatur und Wellenmodell mitbewerten (nur Meer- und Lagunenspots); Tidenzeiten kommen auch ohne |
| `--no-geo` | Ufergeometrie ignorieren, nur die Sektoren aus dem Katalog nutzen |
| `--nights N` | geplante Übernachtungen — verlangt N+1 brauchbare Tage am Stück |
| `--demo` | erfundene Wetterdaten, um Layout und Logik zu prüfen |
| `--open` | den Report danach im Browser öffnen |
| `--favoriten [IDS]` | Favoriten zuerst zeigen: ohne Wert die Liste aus der Oberfläche (`favoriten.json`), sonst Spot-IDs mit Komma getrennt — immer gerechnet, auch außerhalb des Radius (siehe [Favoriten](#favoriten)) |
| `--sprache de\|en\|fr\|es` | Sprache von Meldungen und Report. Ohne die Option: die in der Oberfläche gewählte Sprache (`sprache.txt`), sonst die des Systems (`LC_ALL`, `LC_MESSAGES`, `LANG`, dann die macOS-Spracheinstellungen), sonst Englisch. Die Umgebungsvariable `WINGSCOUT_SPRACHE` schlägt sogar `--sprache` |

`python3 -m wingscout.webui` schreibt seine Terminalzeilen nach derselben
Regel, nur ohne `--sprache`. Der `--help`-Text von `wingscout.cli` entsteht
vor dieser Wahl: Er folgt nur `WINGSCOUT_SPRACHE` oder der in der Oberfläche
gewählten Sprache, sonst ist er deutsch. Auch die Doppelklick-Dateien
schreiben ihre eigenen Zeilen in den vier Sprachen (`tools/sprache.sh`):
`WINGSCOUT_SPRACHE`, dann die in der Oberfläche gewählte Sprache, dann die
macOS-Spracheinstellungen, dann `LC_ALL`, `LC_MESSAGES`, `LANG`, sonst
Englisch. Was sie ihrerseits starten, ist teils noch deutsch: Der Prüflauf
(`tools/check.sh`), das Aktualisieren (`tools/aktualisieren.sh`), der
Prüfstand und `build_geometry.py` melden sich auf Deutsch, und „Auf GitHub
veröffentlichen“ ist durchgehend deutsch.

## Dein Quiver → dein Windfenster

Der Quiver der Vorlage (`config.example.yaml`), geeicht auf 80 kg; dein
eigener kommt in `config.yaml`. Faustformel: untere Grenze ≈ 65/Fläche,
obere ≈ 108/Fläche. **Das sind Erfahrungswerte, keine Messungen.**

| Wing | von | bis |
|---|---|---|
| 6,5 m² | 10 kn | 17 kn |
| 5,0 m² | 13 kn | 22 kn |
| 4,2 m² | 15 kn | 26 kn |
| 3,5 m² | 19 kn | 31 kn |
| 2,5 m² | 26 kn | 43 kn |

Zusammen: **10–43 kn lückenlos abgedeckt.** Wohlfühlband für die Bewertung:
14–28 kn. Wenn sich eine Session anders angefühlt hat, als der Report sie
bewertet hat — ins **Tagebuch** eintragen; ab zwei Sessions schlägt es ein
anderes Fenster vor. Oder die Zahlen in `config.yaml` direkt ändern, nicht den
Code.

## Was der Report bewertet

Der ganze Entscheidungsweg — Vorfilter, die sieben Vetos je Stunde, der Score
aus fünf Teilen, Sessions, Verlässlichkeit, Reihenfolge der Ziele — steht in
[`SCORING.md`](SCORING.md), mit den Konfigurationswerten daneben — und mit
Abbildungen auf der Seite
[„Wie Wingfoilscout rechnet“](https://darkpiratego.github.io/wingfoilscout/bewertung.html)
(im Repository: `docs/bewertung.html`).
Hier die Kurzfassung:

| Anteil | Gewicht | Woher |
|---|---|---|
| Windstärke | 34 % | passender Wing, wie mittig der Wind im Bereich des Wings liegt, Wohlfühlband |
| Windrichtung | 24 % | Sektoren aus `spots.yaml` |
| Wasserzustand | 16 % | `water`-Label des Sektors × deine Kabbel-Aversion |
| Wetter | 14 % | Temperatur, Regen, CAPE |
| Böigkeit | 12 % | Böe ÷ Mittelwind |

### Fahrzeit: geroutet statt geschätzt

Die Anfahrt war früher Luftlinie mal Umwegfaktor bei angenommener
Durchschnittsgeschwindigkeit. Daran hängt die wichtigste Entscheidung des
ganzen Tools — lohnt die Fahrt —, und dafür ist das zu grob: Ab Brouwersdam
schätzt die Faustformel zum Oesterdam 44 km und 31 Minuten, geroutet sind es
63 km und 61 Minuten. In Zeeland liegen Dämme und Fähren dazwischen, in den
Alpen Pässe.

Jetzt fragt Wingfoilscout den öffentlichen OSRM-Server, und zwar über dessen
Tabellendienst: Ein einziger Aufruf liefert die Fahrzeit vom Startpunkt zu
allen Zielen auf einmal, und der komplette Katalog passt in eine Abfrage, die
Bruchteile einer Sekunde dauert. Die Ergebnisse landen in `cache/routes.json`,
mit dem Startpunkt auf gut einen Kilometer gerundet — auch der OSRM-Server
bekommt ihn nur so genau —, sodass wiederholte Suchen vom selben Ort aus gar
nichts mehr holen.

Damit die Schätzung keine Ziele verschluckt, bevor sie geprüft werden, läuft
der Vorfilter mit 35 % Zuschlag auf Radius und Fahrzeitgrenze; erst nach dem
Routing werden deine echten Grenzen angelegt. Ein zu pessimistisch
geschätztes Ziel gar nicht erst zu prüfen wäre der teurere Fehler.

Im Report steht „(geschätzt)“ hinter der Fahrzeit, wenn nicht geroutet werden
konnte; der Tooltip sagt immer, woher die Zahl stammt. Abschaltbar über den
Haken unter Datenquellen — dann gilt wieder `drive.detour_factor` aus der
Konfiguration.

**Der Radius ist eine Fahrstrecke.** In der Suche ist ein Spot nur, wenn
seine geroutete Fahrstrecke höchstens so lang ist wie der Radius — und die
Fahrt höchstens so lang wie „max. Fahrt“. Eine Luftlinie steht nur da, wo es
dabeisteht: der gestrichelte Kreis auf der Karte (Radius ÷ Umwegfaktor, nur
zur Orientierung) und die Spalte „km Luftlinie“ im Katalog, gemessen von
Zuhause. Unter „Nicht berücksichtigt“ zeigt die Spalte die Fahrstrecke —
geroutet, oder mit „≈“, wo sie nur geschätzt ist; bis 2.3.0 stand dort die
Luftlinie neben einem Grund, der die Straßenstrecke nannte („682 km“ neben
„1026 km — außerhalb des Radius von 1000 km“). Liefert OSRM für einige Spots
der Suche keine Route, sagt der Report es oben: Für diese galt der Radius nach
der Schätzung, und die echte Strecke kann länger sein.

### Stellplätze mit Hund

Unter jedem der besten Ziele stehen bis zu vier Plätze zum Übernachten aus
Park4Night, sortiert nach Entfernung, Art und Bewertung. **Hunde müssen
ausdrücklich erlaubt sein** — das ist hier ein harter Filter, anders als am
Spot selbst.

Zwei Dinge musst du dazu wissen. Erstens arbeitet der serverseitige
Tierfilter der Schnittstelle unzuverlässig: Er liefert auch Plätze ohne jede
Serviceangabe zurück. Gefiltert wird deshalb hier, nach dem Eintrag `animaux`
am Platz. Zweitens heißt eine fehlende Angabe fast nie „Hunde verboten“,
sondern „hat niemand eingetragen“. Solche Plätze fallen trotzdem raus, werden
aber gezählt — die Zahl steht unter der Liste. Wundert dich eine kurze Liste
an einer Küste voller Campingplätze, ist das der Grund, und der
Park4Night-Link daneben zeigt dann alles.

Tagesparkplätze, Picknickplätze und reine Ver- und Entsorgungsstellen (Wasser
und Abwasser) sind ausgeschlossen — dort kann man nicht übernachten. Die
Reihenfolge rechnet Größe, Entfernung und Bewertung in „gefühlte Kilometer“
um: Jede Stufe Richtung Campingplatz kostet anderthalb
Kilometer, eine gute Bewertung bringt bis zu einem Kilometer Vorsprung. So
gewinnt der kleine freie Stellplatz drei Kilometer weiter gegen den großen
Campingplatz direkt am Wasser, aber nicht der Bauernhof zwanzig Kilometer
landeinwärts.

Die Schnittstelle ist inoffiziell. Fällt sie aus, fehlt dieser Abschnitt und
sonst nichts. Abschaltbar über den Haken unter Datenquellen.

### Hunde und Erlaubnis am Spot

Zwei Felder im Katalog, `dogs` und `access`, erscheinen als Plakette am Ziel:
Hundeverbot, Leinenpflicht, Surfschein nötig, Vereinsmitgliedschaft, nur in
der ausgewiesenen Zone, Eintritt, ausdrücklich erlaubt, Erlaubnis unklar,
verboten. Steht nichts da, sagen die Quellen nichts — das ist etwas anderes
als „erlaubt“.

Gefiltert wird damit **nicht**. Ein Hundeverbot am Strand heißt nicht, dass
der Tag nichts taugt; es heißt, dass du es vorher weißt. Willst du solche
Spots trotzdem ausblenden, findest du dafür zwei Haken unter
**Suche genauer einstellen → Wasser** — beide standardmäßig aus.

### Shorebreak

An manchen Meeresspots bricht die Welle direkt am Ufer — für den Ein- und
Ausstieg mit Board und Wing ist das der ungemütlichste Teil des Tages. Das
Feld `shorebreak` im Katalog hält diese Beobachtung fest,
**rein als Information**: Es filtert nicht und geht nicht in den Score.

```yaml
  shorebreak:
    status: "yes"        # "yes" | "possible" | "no" | "unknown" — in Anführungszeichen!
    note: "Offener Atlantikstrand; bei Swell bricht die Welle direkt am Ufer."
    source: "Spotwissen — unbelegt, bitte prüfen"
```

`"yes"` erscheint als Plakette **Shorebreak** am Ziel, im Karten-Popup und im
Katalog, `"possible"` als **Shorebreak möglich**; die Notiz steht als Zeile
unter dem Kopf des Ziels und als Tooltip auf der Plakette. `"no"` und
`"unknown"` bleiben stumm — an einem See wäre „kein Shorebreak“ nur
Rauschen. Die Anführungszeichen sind Pflicht: YAML liest ein nacktes `yes` als
Wahrheitswert (dieselbe Falle wie bei `dogs: no`); der Katalogtest mahnt das
an.

Die Einträge aus 1.9.0 (34 Spots an Atlantik, Nordsee und Ärmelkanal) sind
eine erste Einschätzung nach Lage und Exposition, nicht nach eigener
Anschauung — daher `source: Spotwissen — unbelegt`. Wenn du einen Spot
kennst, korrigiere die Zeile und setze die Quelle.

### Tiden — Hoch- und Niedrigwasser je Spot

Seit 1.18.0 zeigt der Report an Tidenspots, wo die Tide gerade steht, und
kann sie auf Wunsch zur Regel machen. Die Quelle ist der modellierte
Wasserstand `sea_level_height_msl` aus der Marine-API von Open-Meteo,
stündlich auf einem 8-km-Raster — Gezeit und Windstau zusammen. Das ist
**kein amtlicher Gezeitenkalender**: Gegenüber der Tafel des nächsten Pegels
weichen die Zeiten ab — wie weit, ist noch nicht gegen eine Tafel geprüft
(siehe TODO); in Buchten und Flussmündungen ist mit mehr zu rechnen als an
offener Küste. Für „auflaufend bis 15 Uhr“ sollte es reichen; für den Fußweg
übers Watt nicht.

**Ob die Tide gilt**, entscheidet je Spot das Feld `tidal` — im Katalog unter
„Tiden …“ umzuschalten, oder von Hand in `spots.yaml`:

```yaml
  tidal: true      # Tide gilt hier, auch wenn das Modell wenig Hub zeigt
  tidal: false     # nie — Ostsee, Mittelmeer, eine Lagune hinter Schleusen
                   # weglassen = automatisch: Meer oder Lagune mit ≥ 0.5 m Hub
```

Die Automatik ist die Voreinstellung für alle Meer- und Lagunenspots: Das
Modell wird abgefragt, und zeigt es über den Zeitraum im Mittel mindestens
0,5 m Hub zwischen Hoch- und Niedrigwasser, gilt der Spot als Tidenspot
(Grenze `tide.auto_hub_min` in der Konfiguration). Achtung bei Lagunen hinter
Dämmen: Das 8-km-Raster sieht dort oft die Nordsee davor — die
Grevelingen-Seite und die Spuikom in Oostende stehen deshalb auf `false`.

**Was der Report zeigt:** am Ziel eine Tidenzeile mit der Lage jetzt
(„Jetzt auflaufend · Hochwasser um 14:50 (in 1 h 40 min)“ — der Satz wird
beim Öffnen des Reports gerechnet und jede Minute nachgeführt, weil der
Report eine Datei ist und „jetzt“ beim Erstellen etwas anderes war), darunter
Hoch- und Niedrigwasser je Tag auf die Minute (aus den Stundenwerten
interpoliert), Hub und Quelle. Die Sessionzeile nennt die Lage zu Beginn der
Session und die Hoch- und Niedrigwasser, die hineinfallen; der Tooltip im
Stundenraster die Lage der Stunde; das Karten-Popup dieselbe Zeile wie das
Ziel. Uhrzeiten sind Ortszeit am Spot, wie überall im Report.

**Ein Tidenfenster** macht die Tide zur Regel — nur wenn du eins setzt:

```yaml
  tide:
    fahrbar: hochwasser   # hochwasser | niedrigwasser | auflaufend | ablaufend
    stunden: 2            # ± Stunden um Hoch-/Niedrigwasser (nur bei hochwasser/niedrigwasser)
```

Schlüssel und Werte sind hier deutsch: `fahrbar`, `stunden`, `hochwasser` /
`niedrigwasser`, `auflaufend` / `ablaufend`. Stunden außerhalb des Fensters
fallen mit Veto heraus („außerhalb des Tidenfensters (HW ± 2 h)“), genau wie
Nacht oder zu kaltes Wasser; im Raster sind sie grau, und der Tooltip nennt
den Grund. `auflaufend` und `ablaufend` nehmen die ganze Halbtide von Scheitel
zu Scheitel. Ohne Fenster ändert die Tide **keinen Score** — sie ist dann
reine Anzeige. Welches Fenster ein Spot braucht, weiß nur, wer ihn kennt
(Sandbank bei Niedrigwasser, Wattstrand bei Hochwasser); deshalb liefert
Wingfoilscout keine Fenster mit, sondern einen Schalter im Katalog: „Tiden …“
neben umbenennen und verschieben, mit automatisch / ja / nein und der
Fensterwahl.

Der Haken „Wassertemperatur und Wellenmodell“ (`--marine`) hat mit der Tide
nichts mehr zu tun: Die Tidenzeiten kommen immer; der Haken entscheidet nur,
ob Wassertemperatur und Wellenhöhe aus dem Modell in die Bewertung eingehen.
Spots mit `tidal: false` werden ohne den Haken gar nicht erst abgefragt.

### Absprünge je Ziel

Unter jedem Ziel stehen sechs Links, die ersten vier auf die Koordinate des
Spots: **Windy** (Karte auf den Punkt zentriert — einen Deep-Link auf eine
Position kennt Windy nicht), **Route** (Google Maps, mit dem Startpunkt der
Suche als Ausgangspunkt, also mit der Entfernung ab da, wo du wirklich bist),
**Karte prüfen** (OpenStreetMap mit Markierung, um die Koordinate zu
kontrollieren) und **Park4Night** mit `lat`/`lng` auf den Spot, sodass die
Stellplätze gleich in der richtigen Ecke liegen. Dazu **Instagram** und
**Insta-Suche**, siehe unten.

### Instagram

Ob an einem Spot gewingt wird, sieht man auf Instagram schneller als in jedem
Forum. Automatisch prüfen lässt sich das aber nicht: Instagram hat keine
öffentliche Suche ohne Anmeldung und keine freie Schnittstelle, die „Gibt es
Posts von hier?“ beantwortet, und die Seiten abzugrasen verbieten die
Nutzungsbedingungen. Wingfoilscout macht deshalb zwei Dinge:

- **Zwei Links je Spot**, im Report, im Karten-Popup und im Katalog:
  **Instagram** führt auf die Ortsseite des Spots (alle dort markierten
  Posts), wenn eine bekannt ist, sonst auf den Hashtag aus dem Namen
  (`#brouwersdam`); **Insta-Suche** ist eine Google-Suche auf instagram.com
  nach Spotname und „wingfoil“ — die zeigt auch ohne Anmeldung, ob es Posts
  gibt. Der Hashtag lässt sich im Katalog vorgeben
  (`instagram: "#tag"`), ebenso eine ganze Adresse
  (`instagram: "https://www.instagram.com/…"`), etwa die Ortsseite oder ein
  Profil, das du selbst gefunden hast.
- **Eine Momentaufnahme** in `instagram.json`: Für 100 Spots wurde am
  18.09.2026 per Google gesucht (`site:instagram.com/explore/locations <Name>`
  für die Ortsseite, `site:instagram.com <Name> wingfoil` für Treffer).
  Behalten wurden Treffer, die Wing oder Foil im Titel tragen oder den
  Spotnamen zusammen mit einem Wassersportwort; Konten, die bei drei und mehr
  Spots auftauchten, sind raus. Das Ergebnis — 77 Ortsseiten, 104 Treffer —
  steht als Zeile **Instagram** unter dem Ziel und im Katalog, mit dem Datum
  und dem Vermerk „kein Beleg“: Es sind Suchtreffer, die sagen, wo man
  nachsieht, nicht der Beweis, dass dort gewingt wird. Für die übrigen rund
  100 benannten Spots steht die Suche noch aus (siehe `TODO.md`); der Link
  **Insta-Suche** tut für jeden Spot dasselbe mit einem Klick.

### Aufbau des Reports

Zuerst deine [Favoriten](#favoriten), wenn du sie eingeschaltet hast (seit
2.4.0), dann die besten drei Ziele (seit 2.3.0 vor der Karte), dann die Karte,
Thermik, Stundenraster, alle weiteren Ziele, alle Sessions als Tabelle, die
aussortierten Spots und die Wetterlogik mit deinen aktuellen Werten.

**Zwei Ansichten** (seit 1.20.0), umschaltbar oben unter der Überschrift:

- **Einfach** — die Antwort ohne den Apparat dahinter. Jedes Ziel ist eine
  Klappe mit zwei Zeilen: Rang, Name, Fahrt und Stunden auf dem Wasser, die
  Plaketten, die über Fahren oder Nichtfahren entscheiden (Fahrt lohnt,
  amtliche Warnungen, Thermik, Tide, Zahl der Hinweise) — und darunter die
  beste Session: wann, wie viel Wind, welcher Wing, welche Windlage. Alle
  Abschnitte weiter unten zeigen nur ihre Überschrift und einen Satz dazu. Ein
  Klick auf ein Ziel oder eine Überschrift öffnet genau das.
- **Ausführlich** — alles offen, wie der Report bis 1.19.2 aussah: Kommentar,
  Warnungen im Wortlaut, Tide, jede Session mit Modellen, Anlauf und Welle,
  Stellplätze, Links, Katalognotiz; die Abschnitte ausgeklappt. Nur „Weitere
  Ziele“ bleibt zu — 40 Karten auf einmal will niemand, auch nicht in der
  ausführlichen Ansicht.

Die Wahl merkt sich der Browser (`localStorage`), sie gilt also für jeden
neuen Report, bis du umschaltest. Ohne JavaScript gilt Einfach; die Klappen
brauchen keins.

Die Sessiontabelle lässt sich sortieren: Ein Klick auf eine Spalte — Spot,
Wann, Dauer, Wind, Lage, Richtung, Wing, Wasser, Score — sortiert, ein
zweiter dreht die Reihenfolge um. Zahlen, bei denen mehr besser ist (Dauer,
Wind, Score), kommen absteigend; Lage sortiert als sideshore, side-on,
auflandig, ablandig (die Sektorenurteile des Katalogs reihen sich dazwischen
ein), Wasser als flach, kabbelig, Welle. **Lage** ist die Windlage aus der
Ufergeometrie oder den Sektoren, **Richtung** die Himmelsrichtung, aus der
der Wind kommt. Gezeigt werden die ersten 40 der aktuellen Reihenfolge,
„alle … zeigen“ (mit der Zahl der Sessions) hebt die Grenze auf; bei
gleichem Wert entscheidet der Score.

Die Reihenfolge folgt dem, wofür du den Report öffnest: Wo ist es am besten,
wo liegt das, wie sieht die Woche aus? Platz 12 schaust du dir nur an, wenn
die ersten drei nichts hergeben.

### Stundenraster

Eine Zeile je Spot, eine Spalte je Stunde, oben die Uhrzeit. Zwei Lesarten,
umschaltbar über den Schalter darüber:

- **Güte** — lohnt sich die Stunde überhaupt? Die Farbe ist der Score aus
  Wind, Richtung, Böigkeit und Wetter.
- **Knoten** — welcher Wing ist dran? Rot unter 11 kn, orange bis zur
  Untergrenze deines Wohlfühlbands, grün im Band, orange darüber, rot ab der
  oberen Grenze und **dunkelrot über 30 kn**. Nacht- und ausgeschlossene
  Stunden bleiben blass, damit der Tagesrhythmus lesbar bleibt.

Grün ist immer das Wohlfühlband aus der Oberfläche und wandert mit, wenn du es
dort änderst. Die roten Enden stehen in `config.yaml` unter `wind.red_below`
(11), `wind.red_above` (26) und `wind.dark_above` (30). Läge ein rotes Ende
im Wohlfühlband — bei einem Band von 14–28 und Rot ab 26 wäre das so —,
weicht es aus, statt das Band zu zerschneiden. Eine Stunde kann so nie
gleichzeitig grün und rot sein.

Der Spotname führt zu **Windy**, die Entfernung daneben zur **Route** —
„Wie wird der Wind?“ und „Wie weit ist das?“ sind zwei Fragen, und jede hat
ihr eigenes Ziel.

Jede Zelle erklärt sich selbst: am Rechner im Tooltip, und seit 1.19.0 auch
mit einem Tipp oder Klick — dann steht unter dem Raster, was die Stunde war
(Spot, Uhrzeit, Wind, Güte und der Grund, wenn sie ausgeschlossen ist). Am
iPhone ist das der einzige Weg, denn dort gibt es keine Tooltips.

### Karte

Der Report öffnet mit einer Karte, und die ist eine eigene Ansicht, keine
Illustration. Punkte: gefüllt = Ziel mit Session (die Top 3 kräftiger),
blaugrau = im Radius, aber kein Wind, hohl = aussortiert (Grund im Popup).

Mit den Schaltern darunter lässt sich jede Ebene einzeln zeigen oder
ausblenden — 277 Punkte gleichzeitig sind sonst nur ein Farbteppich:

- **Top 3 / Session gefunden / windstill / aussortiert**, je einzeln
- **Stellplätze mit Hund** als eigene Ebene, mit Name, Bewertung, Entfernung
  zum Wasser und Park4Night-Link
- **Klick öffnet Windy statt der Details** — standardmäßig aus, weil ein Klick
  auf einen Spot seine Einzelheiten zeigen soll. Wer lieber direkt auf die
  Windkarte springt, schaltet es an. Auch ohne den Schalter führt der
  **Name im Popup** zu Windy
- **Namen der Treffer** dauerhaft einblenden; beim Überfahren zeigt ohnehin
  jeder Punkt seinen Namen
- **Radius** als gestrichelter Kreis
- **Auf Top 3**, **Alles zeigen**, **Vollbild** (Escape beendet es)

Im Popup eines Spots stehen die beste Session, Richtung und Wing, die Fahrt,
das **Stundenband** in derselben Farbskala wie das Raster (beim Überfahren
Uhrzeit und Knoten), die Koordinate zum Kopieren und vier Links: Windy,
Route, Park4Night und Karte prüfen (OpenStreetMap) — dazu Instagram, wo die
Adresse des Spots bekannt ist. Ein Klick zeichnet zusätzlich die Luftlinie
zum Startpunkt.

Die Karte lädt Leaflet von cdnjs und die Kacheln von OpenStreetMap, braucht
beim Öffnen also Internet; ohne Netz erscheint statt der Karte ein Hinweis,
und der Rest funktioniert weiter.

### Wetter im Detail

| Größe | Feld bei Open-Meteo | Regel |
|---|---|---|
| Gewitter | `weather_code` | Code 95/96/99 → die Stunde fällt raus. Dazu ein Gewitterschatten: bis 2 h davor und danach nur noch 40 % des Scores, mit Vermerk in der Session |
| Gewitterneigung | `cape` | ab 1200 J/kg → 70 %, ab 2000 J/kg → 35 %, jeweils mit Hinweis |
| Regen | `precipitation` | bis 0,6 mm/h kein Abzug, dann linear fallend bis 3,0 mm/h, darüber 20 % |
| Lufttemperatur | `temperature_2m` | außerhalb 7–35 °C fällt die Stunde raus; innerhalb 3 °C zur Grenze 80 % |
| Wassertemperatur | `sea_surface_temperature` | unter 7 °C fällt die Stunde raus — nur mit `--marine`, nur Meer und Lagune |
| Tide | `sea_level_height_msl` (Marine-API) | Hoch- und Niedrigwasser an Tidenspots; nur mit Tidenfenster im Katalog (`tide: fahrbar`) fallen Stunden außerhalb raus — sonst reine Anzeige |
| Tageslicht | `sunrise` / `sunset`, sonst gerechnet | 30 min nach Sonnenaufgang bis 30 min vor Sonnenuntergang |
| Vergangenheit | Uhrzeit des Laufs | Stunden, die schon vorbei sind, fallen raus |
| Bewölkung | `cloud_cover` | wird geholt, aber nicht bewertet |

Der **Gewitterschatten** ist der Punkt, an dem das Tool über ein
Forecast-Portal hinausgeht: Das Modell markiert nur die Stunde, in der es an
diesem Gitterpunkt das Gewitter vorhersagt — draußen auf dem Wasser
interessiert dich das Fenster drumherum genauso.

Die Wetterlogik steht als Tabelle auch im Report selbst, mit deinen aktuellen
Werten aus `config.yaml` — die beiden können also nicht auseinanderlaufen.

**Gewässer:** Süß- und Salzwasser sind beide eingeschlossen
(`water.include_types`). Zum Einschränken einzelne Typen aus der Liste
streichen.

**Harte Ausschlüsse:** Gewitter (Wettercode 95/96/99), Lufttemperatur
außerhalb 7–35 °C, kein passender Wing, Dunkelheit, durchgehender
Stehbereich, starkes Seegras, Spot außerhalb der Saison oder des Radius.

**Fahrzeit-Regel:** Deine Vorgabe „6 h Fahrt für 2 h Wasser pro Tag“ steht als
Faktor 3 in der Konfiguration. Ein Ziel gilt als lohnend („Fahrt lohnt“), wenn
`Fahrzeit ≤ 3 × durchschnittliche Wasserstunden pro Tag × (1 + 0.5 × Nächte)`,
gedeckelt bei `drive.max_hours`. Darüber wird es als „Fahrt grenzwertig“
markiert, und sein Rang wird mit 1 − 0,8 × Überschuss ÷ erlaubte Zeit
multipliziert — null bei 125 % über der erlaubten Zeit. Einzelheiten in
[`SCORING.md`](SCORING.md), Abschnitt 6.

## spots.yaml — das eigentliche Asset

Der Katalog ist von Hand gepflegt und **noch nicht verifiziert**. Jeder Spot
trägt `verified: false`, bis du ihn angesehen hast. Der Report verlinkt je
Spot eine Karte — Prüfen dauert Sekunden, und danach ist der Katalog mehr wert
als jedes Forecast-Portal. Was über „Spots hinzufügen“ aus einer **Datei**
kommt (GPX, KML, GeoJSON, CSV), ist unbestätigt und steht auf der Prüfseite;
was du selbst eintippst oder aus der Karte kopierst, gilt als angesehen. Ohne
Gewässerart bleibt `water_body: unknown` — der Spot fällt dann aus keinem
Filter, und die Ufergeometrie sagt später, in welchem Gewässer er liegt.

```yaml
- id: brouwersdam-grevelingen
  name: Brouwersdam – Grevelingenmeer (Innenseite)
  lat: 51.751
  lon: 3.836
  shallow: none | inshore | widespread
  seagrass: none | some | heavy
  season: [3,4,5,6,7,8,9,10,11]
  sectors:
    - {from: 200, to: 300, quality: best, water: flat}
  verified: false
```

`comment` ist dein eigener Kommentar (siehe oben), `notes` die Beschreibung.
`from`/`to` ist die Richtung, **aus der der Wind kommt** (Grad, 0 = Nord).
Sektoren dürfen über Nord laufen (`from: 320, to: 40`). `quality` ist
`best | good | ok | bad`, `water` ist `flat | chop | wave`.

Ein Spot mit `disabled: true` bleibt als Notiz im Katalog, fällt aber aus dem
Ranking — so wie Fehmarn/Gold wegen des Seegrases.

## Ufergeometrie

Der Teil, der die Handarbeit ersetzt.

```bash
python3 build_geometry.py            # einmalig, danach ohne Netz nutzbar
python3 build_geometry.py --only brouwersdam workum
python3 build_geometry.py --radius 25 --force
```

Für jeden Spot wird die Wassergeometrie aus OpenStreetMap geholt
(Küstenlinien, Seen, Lagunen, Stauseen), und **in 36 Richtungen wird der
Anlauf über Wasser gemessen** — der erste Schnittpunkt eines Strahls mit einer
Wassergrenze. Das Ergebnis liegt in `geometry.json` und ändert sich danach
nicht mehr.

Aus dieser einen Größe folgt der Rest:

| Anlauf in Luv | Platz in Lee | Windlage | Bewertung |
|---|---|---|---|
| klein | groß | **ablandig** | glatt, aber du treibst raus → Sicherheitshinweis; mit `offshore_veto_km` ein Veto, sobald so viel Wasser in Lee liegt |
| groß | klein | **auflandig** | Welle und Shorebreak direkt vor der Nase |
| beides groß | beides groß | **sideshore** | das Beste |
| klein | klein | kein offenes Wasser | die Koordinate stimmt nicht |

Die Wellenhöhe kommt aus der fetch-begrenzten SPM-Beziehung
`H_s = 0.0016 · U · √(F/g)` — 20 kn über 1 km ergeben 12 cm, über 40 km
1,05 m. Eine Ingenieursnäherung: Sie unterstellt gleichbleibenden Wind und
rechnet mit U10 statt mit dem Windstressfaktor. Für „glatt oder kabbelig“
reicht sie; eine Wellenvorhersage ersetzt sie nicht.

**Was das praktisch bringt:** Spots ohne handgepflegte Sektoren — die 26 Pins
aus Jens Dees Liste zum Beispiel — werden jetzt genauso bewertet wie deine
Referenzspots. Windlage und Wasserzustand kommen aus der Geometrie statt aus
Handarbeit. Deine eigenen Sektoren in `spots.yaml` haben Vorrang; mit
`geometry.prefer_manual_sectors: false` gewinnt stattdessen die Rechnung.

Liegt ein Spot auf dem Parkplatz statt im Wasser, wird der Messpunkt
automatisch ins Wasser verschoben (Seen über Punkt-in-Fläche, Küsten über die
OSM-Regel „Land links, Wasser rechts“). Spots, um die herum kaum offenes
Wasser liegt, listet `build_geometry.py` am Ende auf — dort stimmt meist die
Koordinate nicht.

Der erste Lauf über 277 Spots dauert 10–30 Minuten, fast nur Wartezeit auf die
Overpass-Server. Jeder Spot wird sofort gespeichert, Abbrechen ist also
harmlos.

## Was noch fehlt

- **Ufergeometrie für den Rest des Katalogs** — wie viele Spots noch fehlen,
  steht in der Oberfläche neben dem Knopf „Fehlende berechnen“; etwa eine
  Viertelminute je Spot. `geometry.json` ist versioniert: Nach einem Lauf
  gehört die Datei committet, sonst rechnet der nächste Klon alles von vorn.
- **Koordinaten prüfen**: 122 Spots stammen aus importierten Listen und sind
  auf drei bis vier Nachkommastellen gerundet, also bis etwa einen Kilometer
  ungenau. Der Report markiert sie; „Karte prüfen“ führt direkt zum Punkt.
- **Tiefenprofil** aus EMODnet: den Stehbereich messen statt schätzen. Für
  Meere ja, für Binnenseen nein — dafür gibt es keine freie Bathymetrie.

Die maßgebliche Liste steht in [`TODO.md`](TODO.md).

## Der Prüfstand — stimmt es noch?

Die Tests prüfen ohne Netz, ob der Code tut, was er soll. Der **Prüfstand**
prüft mit Netz, ob das Ganze noch stimmt: Doppelklick auf „Prüfstand“ oder
`python3 tools/pruefstand.py`. Er holt für sieben Spots mit bekanntem Wind
(Ora, Malojawind, Breva …) die laufende Vorhersage und prüft die Form der
Antwort, die Bewertung und ob die Thermik dort erscheint, wo sie hingehört; er
schickt einen Punkt auf der Schwäbischen Alb durch die Ufergeometrie und
erwartet „kein Wasser innerhalb von 3 km — liegt der Pin an Land?“; und für
zehn Spots mit einer Wetterstation in Reichweite vergleicht er die
aufgehobene Vorhersage eines festen Monats mit der **Messung** — je Modell und
für Wingfoilscout als Ganzes. Die Zahlen eines guten Laufs werden als
Grundlinie gemerkt; schneidet eine spätere Änderung schlechter ab, sagt der
Prüfstand es. Alles Weitere steht in [`BENCHMARK.md`](BENCHMARK.md).

## Datenquellen, Lizenzen und Grenzen

Wingfoilscout selbst steht unter der Lizenz
[PolyForm Noncommercial 1.0.0](LICENSE) (seit 2.3.0; bis 2.1.0 galt MIT):
Benutzen, Ändern und Weitergeben ist für jeden nicht-kommerziellen Zweck
erlaubt — privat, als Hobby, zum Lernen und Forschen und in gemeinnützigen
Organisationen, Bildungs- und öffentlichen Forschungseinrichtungen,
Einrichtungen für öffentliche Sicherheit, Gesundheit und Umweltschutz sowie
Behörden —, solange die Lizenzbedingungen (oder ihre Webadresse) und die
Zeile `Required Notice` mitgehen. Für kommerzielle Nutzung braucht es eine
eigene Lizenz von DARK: per Issue auf GitHub anfragen. Eine Gewähr gibt es
nicht — auch nicht für den Wind. Für die Daten gelten die Bedingungen ihrer
Quellen, siehe unten; `geometry.json` bleibt unter der ODbL von
OpenStreetMap.

Wetter: [Open-Meteo](https://open-meteo.com), freier Tarif, nicht-kommerziell,
10.000 Aufrufe pro Tag; die Daten stehen unter CC BY 4.0. Ein Lauf über 25
Spots kostet zwei Aufrufe.

Was im Repository liegt, und woher es stammt:

- `spots.yaml` — von Hand gepflegt. Die Herkunft jedes Eintrags steht im Kopf
  der Datei und im Feld `source`: Windfinder-Spotseiten (Koordinate und
  Beliebtheitsrang), eine geteilte Google-Maps-Liste, eigene Schätzungen
  (`verified: false`). Namen und Koordinaten sind Tatsachen; die Bewertungen
  und Notizen sind eigene Arbeit.
- `geometry.json` — aus OpenStreetMap berechnet (Küstenlinien, Wasserflächen,
  Landnutzung): © OpenStreetMap-Mitwirkende,
  [ODbL 1.0](https://www.openstreetmap.org/copyright). Wer die Datei
  weitergibt, gibt diesen Hinweis mit.
- `instagram.json` — nur Adressen öffentlicher Instagram-Seiten (Schulen,
  Vereine, Ortsseiten), gefunden per Websuche; keine Inhalte, keine Bilder.
- `pruefstand/grundlinie.json` — abgeleitete Kennzahlen (Abweichung je
  Modell), keine Messreihen.

Zur Laufzeit kommt Folgendes dazu, und nichts davon wird im Repository
abgelegt: Messwerte von DWD, KNMI, Rijkswaterstaat, GeoSphere Austria, DMI und
Météo-France (offene Daten, jeweils zu den Bedingungen des Dienstes),
Windguru nur mit dem API-Passwort einer Station, Fahrzeiten vom öffentlichen
OSRM-Server, Ortsnamen von Nominatim, Ufergeometrie von den Overpass-Servern,
Stellplätze als Links zu Park4Night, die Karte mit
[Leaflet](https://leafletjs.com) (BSD-2-Clause) und Kacheln von OpenStreetMap.
Für die öffentlichen Server gelten deren Nutzungsregeln; Wingfoilscout
speichert Antworten zwischen, damit sie nicht bei jedem Lauf gefragt werden.

Was der Report **nicht** weiß: den amtlichen Tidenstand (nur das 8-km-Modell,
siehe „Tiden“), die gemessene Wassertemperatur, Sperrzeiten,
Vogelschutzgebiete, ob der Parkplatz etwas kostet, ob gerade jemand anders da
ist. Der Report sagt dir, wo es sich lohnt, nachzuschauen — nicht, dass du
hinfahren sollst.

### Was deinen Rechner verlässt

Wingfoilscout hat keinen eigenen Server und kein Konto. Es spricht direkt mit
den öffentlichen Diensten unten, und jeder davon sieht deine IP-Adresse. Was
sie bekommen:

| Dienst | Bekommt |
|---|---|
| Open-Meteo (Vorhersagen, Seegang, Ensemble, aufgehobene Vorhersagen) | Spotkoordinaten |
| Overpass (Ufergeometrie) | Spotkoordinaten |
| Park4Night (Stellplätze) | Spotkoordinaten |
| Nominatim (Ortsname und Land eines Spots, den du hinzufügst) | Spotkoordinaten |
| OSRM (Fahrzeiten) | deinen Startpunkt, auf etwa einen Kilometer gerundet (zwei Nachkommastellen), dazu Spotkoordinaten |
| MeteoAlarm (Wetterwarnungen) | nur das Land |
| Wetterstationen — DWD, KNMI, Rijkswaterstaat, GeoSphere Austria, DMI, Météo-France (Rückblick, Tagebuch, Prüfstand) | Stationskennungen und Zeiträume |
| Windguru (nur wenn du eine Station eingetragen hast) | die Stationskennung und ihr API-Passwort, per HTTPS als POST |
| OpenStreetMap-Kachelserver (jede Karte) | die Kacheln des Gebiets, das die Karte zeigt |
| cdnjs (jede Karte) | die Anfrage nach der Leaflet-Bibliothek |

Dein Name, dein Gewicht, dein Material und dein Tagebuch bleiben auf deinem
Rechner. Deine Kommentare zu Spots landen in `spots.yaml` und reisen nur mit
dem Katalog — veröffentlichst du ihn, sind sie öffentlich. Links im Report und
im Katalog (Google Maps, Windy, Park4Night, Instagram …) schicken nichts, bis
du sie anklickst — der Routen-Link zu Google Maps trägt dann deinen
Startpunkt, so wie er für die Suche benutzt wurde.
**Für alle vorschlagen** und **Korrektur vorschlagen**
öffnen GitHub; was sie ins Formular eintragen (Name, Koordinate, Notiz),
steht dabei in der Adresse. Was du dort abschickst, ist öffentlich, unter
deinem GitHub-Namen.

## Weiterentwicklung

[`CONTRIBUTING.md`](CONTRIBUTING.md) beschreibt, wie zwei Leute daran
arbeiten, ohne sich gegenseitig in die Quere zu kommen;
[`DEVELOPMENT.md`](DEVELOPMENT.md) Aufbau, Tests und die Git-Regeln;
[`SECURITY.md`](SECURITY.md) die Prüfung vom 13.09.2026 mit Befunden und
Fixes; [`TODO.md`](TODO.md) ist die maßgebliche Liste offener Punkte;
[`CHANGELOG.md`](CHANGELOG.md) hält fest, was sich wann geändert hat.

Prüflauf vor jedem Commit: `tools/check.sh` oder im Finder „Tests ausführen“ —
rund 700 Tests, keine Fremdpakete, ein bis zwei Minuten. Nach einem frischen
Klon einmal `tools/install-hooks.sh` ausführen, damit der Prüflauf vor jedem
Commit läuft.

```
wingscout/          Programmcode (cli, score, report, webui, geometry, sources/)
.github/            Prüflauf auf GitHub, CODEOWNERS, PR-Vorlage
tests/              Tests, reines unittest
tools/              Prüflauf, Hooks, Veröffentlichen und Aktualisieren
import/             einmalige Importskripte und Rohlisten
spots.yaml          der Katalog — das eigentliche Asset
config.example.yaml alle Schwellen und Regeln, kommentiert — Vorlage
config.yaml         deine persönliche Fassung, nicht versioniert
geometry.json       berechnete Ufergeometrie, abgeleitet, aber versioniert
```
