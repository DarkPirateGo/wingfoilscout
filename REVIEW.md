# Review

Drei Reviews in dieser Datei: 16.09.2026 (Code, Stand 1.6.0, direkt darunter),
20.09.2026 (Struktur, Stand 1.14.0) und **25.09.2026 (Sicherheit und
Bedienung, Stand 1.18.3, ganz unten — dort steht, was offen ist)**.

Stand 16.09.2026, Review gegen Version 1.6.0 (Commit `33ed50b`). Vier Befunde
sind als 1.6.1 behoben (S1, S2, B1, S3), die übrigen 25 als 1.7.0 — die
Beschreibungen unten bleiben als Begründung stehen, der Status steht bei jedem
Abschnitt. Was danach noch offen ist, steht ganz unten. Gelesen wurde der gesamte
Code (`wingscout/`, `sources/`, `tools/`, Skripte, Tests, Workflow), nicht nur
die Diffs. Schwerpunkt: Sicherheit, dann Berechnung, Bewertung, Quellen und
Stabilität. Jeder Befund nennt Datei und Zeile im heutigen Stand; Zeilen in
`webui.py` beziehen sich auf die Fassung von 1.6.1.

Was sich ohne Netz nachstellen ließ, wurde nachgestellt (S2, S3, S4, B1). Was
eine Fremdantwort bräuchte, ist als Lesebefund gekennzeichnet.

## Kurzfazit

Die Angriffsfläche ist klein und bewusst gehalten: Server nur auf 127.0.0.1,
Origin- und Host-Prüfung auf jedem POST, `yaml.safe_load`, `_esc()` und
JSON-Unicode-Escapes im Report, `_safe_url()` für fremde Adressen, `safe_id()`
für Dateinamen, ein Zeitlimit an jedem `urlopen`. Eine echte Lücke von außen
habe ich nicht gefunden. Zwei Stellen widersprachen den eigenen Regeln des
Projekts und sind behoben (S1, S2). Der Rest der Sicherheitsbefunde ist
Härtung.

Gewichtiger ist die Struktur. Ein Befund war ein Fehler derselben Art wie der
Sonnenaufgangsfehler aus 1.5.0: die Einstrahlung für die Thermik fiel beim
Zusammenführen der Modelle stillschweigend weg (B1, behoben). Offen bleiben
drei Stellen, an denen die Bewertung gegen sich selbst arbeitet (B2, B3, B5),
und eine Handvoll Caches, die nach einer Koordinatenkorrektur veraltet sind
(Q1).

## Behoben in 1.6.1

**B1 · Die Einstrahlung für die Thermik kam nie an.** `models.py` `CORE`
enthielt `shortwave_radiation` nicht; bei mehreren Modellen (Voreinstellung)
baute `normalize()` das `hourly` nur aus `CORE` neu, `score.py`
`val("shortwave_radiation")` war `None`, und `thermik.energie_faktor()` nahm
immer die Bewölkung. Nachgestellt: sonniger Tag mit 95 % Hochbewölkung,
Potenzial um 15 Uhr 0,19 statt > 0,9. Jetzt in `CORE`; ein Test baut die
Antwort mit Suffixen, ein zweiter prüft, dass alles, was `score_hours` liest,
in `CORE` steht.

**S3 · `SystemExit` aus `load_spots()` ließ die Oberfläche auf „läuft“
stehen.** Jetzt `KatalogFehler`/`KonfigFehler` (`ValueError`), `SystemExit`
erst in `cli.main` und in den `__main__`-Blöcken der Skripte; die drei
Hintergrundläufe laufen über `_starte()`, das „running“ in jedem Fall
verlässt (auch bei `BaseException`, auch wenn die Arbeit kein Ende meldet).
Drei Tests in `test_webui.py`, zwei in `test_catalog.py`.

**S1 · Leaflet wurde auf der Startseite ohne Prüfsumme nachgeladen.**
`webui.py`, ehemals `loadLeaflet()` um Zeile 1061: `js.src = …` ohne
`integrity`. ENTWICKLUNG.md verlangt die Prüfsumme für jedes Skript von außen,
`tests/test_security.py` prüfte aber nur `report.py` und nur `<script src>`-
Tags — die Zuweisung im JavaScript lief an beidem vorbei. Ein verändertes
Skript vom CDN liefe mit den Rechten der Seite, und die darf `spots.yaml`
beschreiben und den Server beenden. Jetzt: Adressen und Prüfsummen einmal als
Konstanten (`LEAFLET_*`), von Prüfseite und Nachladen gemeinsam genutzt; der
Test deckt beide Dateien und beide Wege ab. Die Prüfsummen sind dieselben,
die die Prüfseite schon trug; gegen cdnjs nachrechnen konnte ich sie von hier
aus nicht (kein Netz zu cdnjs).

**S2 · `Content-Length: -1` hielt einen Bearbeitungs-Thread fest.**
`webui.py`, ehemals `_form()`/`_json()`: `int(...)` prüfte nur nach oben,
`rfile.read(-1)` las bis zum Verbindungsende — und das bestimmt der Absender.
Nachgestellt: keine Antwort, bis der Client aufgibt; danach lief die Anfrage
sogar weiter (ein `/save` mit leerem Körper schrieb `ui_defaults.json`). Jetzt
`_laenge()`: negativ oder unlesbar → 400, zu groß → 413. Test mit rohem Socket
in `test_webui.py`. Nur vom eigenen Rechner erreichbar, deshalb keine hohe
Schwere — aber ein hängender Thread je Anfrage ist ein Ausfall, den man sich
nicht erklären kann.

## Sicherheit — behoben in 1.7.0

**S4 · `nan` und `inf` gehen durchs Formular.** `webui.py:81` `num()` nimmt
`float("nan")`. `air_min = nan` schaltet die Temperaturprüfung ab, weil jeder
Vergleich mit `nan` falsch ist — nachgestellt: `score_weather(-30 °C)` gibt
1,0 zurück. `radius = inf` hebt den Radius auf. Kein Angriff, aber ein Filter,
der stumm aus ist. Abhilfe: `math.isfinite()` in `num()`, sonst Startwert.
Schwere: niedrig.

**S5 · Lesen und Schreiben von `spots.yaml`/`geometry.json` ohne Sperre
nebeneinander.** `webui.py:1378` (`/pruefen/setzen`: `load_store`, `pop`,
`save_store`) läuft, während ein Hintergrundlauf (`run_batch`, „Fehlende
berechnen“) nach jedem Spot dieselbe Datei schreibt; `/pruefen/ok` ändert
`spots.yaml` zweimal hintereinander per Lesen-Ersetzen-Schreiben, während
`start_ingest` anhängt. Verlorene Schreibvorgänge sind möglich, und die
Prüfseite prüft `JOB` nicht. Dazu die Prüfung-dann-Start-Lücke in
`webui.py:1444`: zwei gleichzeitige `/run` sehen beide „nicht beschäftigt“.
Abhilfe: einen Prozess-Lock (`threading.Lock`) um jedes Lesen-Ändern-Schreiben
der beiden Dateien, und `/pruefen/*` bei laufendem Job mit 409 abweisen.
Schwere: mittel (Datenintegrität des eigentlichen Assets).

**S6 · Fremde XML-Dateien werden ungebremst geparst.** `ingest.py:105/135`
`ET.fromstring` auf GPX/KML aus fremder Hand. Ein Entity-Bombe (Billion
Laughs) kostet Speicher; `expat` ≥ 2.4 bremst das (hier 2.4.7), Apples 3.9
hat je nach macOS-Stand eine ältere Fassung. Abhilfe ohne Zusatzpaket: Text
mit `<!DOCTYPE` oder `<!ENTITY` vor dem Parsen ablehnen — GPX und KML
brauchen beides nie. Schwere: niedrig (die Datei wählt man selbst).

**S7 · Park4Night-Adresse wird nur vorn geprüft.** `park4night.py:121`
`"https://park4night.com" + url` — ein `url` wie `.evil.example/x` ergibt
`https://park4night.com.evil.example/x` und passiert `_safe_url()`. Setzt
eine manipulierte Antwort voraus. Abhilfe: nur anhängen, wenn `url` mit `/`
beginnt. Schwere: niedrig.

**S8 · Keine `X-Frame-Options`/`frame-ancestors`.** Die Prüfseite hat Knöpfe,
die schreiben; eine fremde Seite könnte sie unsichtbar einbetten
(Clickjacking). `SAMEORIGIN` passt, weil die Startseite den Report selbst
einbettet. Eine Zeile in `_send()`. Schwere: niedrig.

**S9 · `ui_defaults.json` wird ungeprüft in die Seite geschrieben.**
`webui.py:73` nimmt jeden JSON-Inhalt, `field()` in Zeile 466 setzt `value`
ohne `html.escape`. Geschrieben wird die Datei nur vom Server selbst; wer sie
von Hand verbiegt, hat den Rechner ohnehin. Trotzdem: die Werte einmal durch
dieselbe Prüfung wie `parse_form` schicken. Schwere: sehr niedrig.

**S10 · Unter Python 3.9 wird der Overpass-Ausweichserver bei Zeitüberschreitung
nie versucht.** `overpass.py:117/230` fängt `TimeoutError`; in 3.9 ist
`socket.timeout` davon keine Unterklasse (erst ab 3.10 dasselbe). Ein Lese-
Timeout nach 330 s fällt durch bis `run_batch` und wird als „Fehler beim
Rechnen“ gemeldet statt als „Overpass nicht erreichbar“, ohne den zweiten
Endpunkt. Abhilfe: `socket.timeout` mit aufnehmen (oder `OSError`). Schwere:
niedrig — betrifft nur die 3.9-Untergrenze, die das Projekt aber ausdrücklich
trägt.

**S11 · Außerhalb des Prüflaufs:** `import/*.py` und `tools/*.py` liegen nicht
in `SRC` von `test_security.py:14` und nicht in Schritt 1 von `check.sh`;
`.github/workflows/tests.yml:30` bindet `actions/checkout@v4` über ein Tag
statt einen Commit-Hash. Beides Hinweise, keine Lücken.

## Berechnung und Bewertung — behoben in 1.7.0

**B2 · Die Verlässlichkeit steckt in der Windstärke.** `thermik.py:208`
`erwartet = typical_kn · reliability · trust · p`. Ora mit 18 kn bei 75 %
Verlässlichkeit ergibt 13,5 kn — eine Zahl, die an keinem Tag auftritt: läuft
die Ora, sind es 18, sonst 0. Der Wing wird für 13,5 kn gewählt und passt in
beiden Fällen nicht; mit `p` bis 1,15 kommt 15,5 heraus. Dieselbe
Verlässlichkeit geht in `thermik.py:175` noch einmal in das angezeigte
Potenzial ein. Vorschlag: Stärke = `typical_kn · p` (physikalisch), die
Verlässlichkeit als Wahrscheinlichkeit dort, wo Wahrscheinlichkeiten hingehören
— in die Sicherheitsplakette und den Ensemble-Faktor (B3). Schwere: mittel,
konzeptionell.

**B3 · Das Ensemble bestraft genau die Spots, die das Tool korrigiert.**
`cli.py:130-136` und `ensemble.py:93`: `p_ride` zählt rohe Ensemble-Mitglieder
(grobes Gitter, 15–25 km) gegen `ride_kn`. Der Wind, der die Session trägt,
kommt aber aus Thermikannahme, `wind_factor` oder dem Regionalmodell — alles
Korrekturen, die das Ensemble nicht kennt. Eine Thermiksession mit 5 kn im
Modell bekommt `p_ride ≈ 0` und den Score halbiert (`apply_ensemble`, g = 0,5).
Im Lauf vom 16.09. lag keine der drei Thermiksessions unter den ersten 20,
deshalb ist es dort nicht messbar; die Logik ist es trotzdem. Abhilfe:
Sessions mit `thermal: True` vom Ensemble-Faktor ausnehmen (und stattdessen
die Verlässlichkeit aus B2 nutzen); bei `wind_factor` die Schwelle durch den
Faktor teilen; bei Regionalmodell-Sessions den Median-Unterschied auf die
Schwelle anrechnen. Schwere: mittel.

**B4 · Fehlende Windrichtung wird zu Nord.** `score.py:305`
`val("wind_direction_10m") or 0.0` — `None` wird 0°, dann werden Sektoren
abgeglichen und die Rose bei Nord gelesen, als wäre das gemessen. Abhilfe:
`None` weiterreichen und in `score_direction`/`score_from_geometry` neutral
bewerten (`unknown_direction_score`). Schwere: niedrig, aber falsch.

**B5 · „Modelle einig“ meint drei Modelle, die gar nicht angezeigt werden.**
`score.py:276` berechnet `wind_agree`/`wind_spread` aus den globalen Modellen;
`score.py:283` überschreibt danach den Wind mit CH1/ICON-D2. Die Plakette
„ICON, GFS und ECMWF liegen nah beieinander“ steht dann neben einem Wind, der
von allen dreien 5 kn abweicht — und `score.py:404` dämpft mit einer
Einigkeit, die den benutzten Wert nicht einschließt. Abhilfe: nach
`einsetzen()` Spread und Agree neu rechnen, mit dem feinen Modell als
Mitglied; oder die Plakette für Regionalmodell-Stunden anders beschriften.
Schwere: mittel für die Lesbarkeit des Reports.

**B6 · Eine Stunde knapp unter der Schwelle zerschneidet die Session.**
`score.py:509` — eine Stunde mit 0,54 mitten in einem sonst tragenden
Nachmittag macht aus einer 5-h-Session zwei von je 2 h; mit `min_hours: 3`
bleibt gar keine übrig, und das Ziel verschwindet aus dem Report. Vorschlag: eine einzelne Stunde
über `min_score − 0,1` überbrücken, wenn beide Nachbarn tragen. Schwere:
niedrig, aber die Reihenfolge der Ziele hängt daran.

**B7 · Die Wellenhöhe aus dem Wellenmodell wird geholt und weggeworfen.**
`marine.py:58` liefert `wave_height` (DWD EWAM, 5 km); `cli.py:317` gibt nur
`sst` und `tide` weiter. Für alle Spots gilt die SPM-Näherung
(`geometry.py:420`) mit U10 und ohne Dauer- und Tiefenbegrenzung — der
Fußnotentext sagt das ehrlich. An Meeresspots liegt die bessere Zahl schon im
Speicher. Abhilfe: wo `wave` vorhanden, `wave_m` daraus, Fetch nur noch für
die Windlage. Schwere: mittel für Meeresspots (111 von 275).

**B8 · Alle Zeiten sind Berliner Zeit, auch in Griechenland und Portugal.**
`openmeteo.py:69` und `ensemble.py:37` fragen fest `Europe/Berlin` ab. Für
18 Spots (GR 15, PT 3) stehen die Uhrzeiten im Report eine Stunde neben der
Ortszeit, und das Thermikfenster `from/to` aus dem Katalog — gemeint als
Ortszeit — greift versetzt. Sonnenzeiten sind in sich stimmig, weil sie aus
derselben Antwort kommen. Abhilfe: `timezone=auto` je Abfrage und
`utc_offset_seconds` mitführen; oder je Spot die Zone aus dem Land. Schwere:
niedrig, wächst mit dem Katalog.

**B9 · Saison nach dem Kalendermonat des Starttags.** `cli.py:228`
`date.today().month` — ein Lauf am 30.09. über 16 Tage bewertet Oktoberspots
nach der Septembersaison. Schwere: niedrig.

**B10 · Ensemble-Fenster eine Stunde zu lang.** `cli.py:130` `hour_stamps`
schließt `end` ein, `end` ist aber exklusiv (`block[-1].t + 1 h`). Schwere:
sehr niedrig.

**B11 · Warnungen ohne Gebiet gelten landesweit — an jedem Spot.**
`meteoalarm.py:120`: bei leerem `region` bekommt der Spot alle Warnungen des
Landes; 192 von 275 Spots haben kein `region`. Im Report vom 16.09.: 81
Warnplaketten aus 9 Warnungen, „Moderate Thunderstorm · Bornholm“ an 13
dänischen Spots, „Kreis Plön“ an 9 deutschen. Das ist Rauschen, das die
echte Warnung unsichtbar macht. Abhilfe: ohne `region` nichts anhängen und im
Kopf des Reports „N landesweite Warnungen, Gebiet unbekannt“ sagen; besser:
der Feed trägt `cap:geocode`/Polygone — Punkt-in-Polygon mit dem, was
`geometry.py` schon kann. Schwere: mittel für den Nutzen der Warnungen.

**B12 · Der Score ist rein additiv — ablandig ist kein Veto.** Mit den
Gewichten aus `config.example.yaml` erreicht eine Stunde mit perfektem Wind
und Richtung „ablandig“ (0,5) etwa 0,88 und zählt als gute Session; es bleibt
bei der Warnung. Das ist eine Entscheidung, keine Panne — aber sie sollte
bewusst sein: bei `fetch_down` > 10 km ablandig ist die Frage nicht Komfort,
sondern Rückweg. Vorschlag: `offshore_veto_km` als Option. Schwere:
Designfrage.

**B13 · Importierte Dateien gelten als bestätigt und als See.**
`ingest.py:290` setzt `verified: True` für alles, was über „Spots
hinzufügen“ kommt — auch für eine GPX mit hundert Wegpunkten aus fremder
Hand, für die die Prüfseite gedacht ist. `ingest.py:280` setzt
`water_body: "lake"`, wenn nichts angegeben ist, obwohl der Katalog dafür
`unknown` kennt und `eligible()` genau diesen Wert durchlässt; ein Meeresspot
wird so zum See, fällt bei abgewähltem „See“ raus und bekommt beim Snap die
falsche Bevorzugung. Abhilfe: `verified` nur für Freitext mit Koordinate
(eigene Eingabe), `False` für Dateiimporte; `water or "unknown"`. Schwere:
mittel für die Datenqualität.

## Quellen und Caches — behoben in 1.7.0

**Q1 · Alle Caches hängen an der Spot-ID, keiner an der Koordinate.**
`overpass.py:155` (`{id}_{radius}km.json.gz`), `overpass.py:219`
(`{id}_protected.json`, wird auch mit `--force` nie erneuert),
`highres.py:246` (Modellzuordnung), `routing.py:105` (Fahrzeit). Nach einer
Korrektur über die Prüfseite holt `build_one(force=True)` die Geometrie
frisch — Schutzgebiete, Regionalmodell und Fahrzeit bleiben die der alten
Koordinate. Wer die Koordinate von Hand in `spots.yaml` ändert und den
Eintrag aus `geometry.json` nimmt, rechnet sogar die Geometrie aus dem alten
Overpass-Auszug. Abhilfe: Koordinate (auf 4 Stellen) in jeden Cache-Eintrag
schreiben und bei Abweichung neu holen. Schwere: mittel — heute, sieben
Korrekturen nach dem letzten Commit, konkret relevant.

**Q2 · Zwei Caches liegen relativ zum Arbeitsverzeichnis.**
`overpass.py:137/208` `"cache/geom"`, `meteoalarm.py:106` `"cache/alerts"`;
`highres` und `routing` dagegen absolut über `ROOT`. Wer `python3 -m
wingscout.webui` aus einem anderen Ordner startet, bekommt einen zweiten
Cache-Baum und ein Overpass-Volllauf. Die `.command`-Dateien machen `cd`,
deshalb fällt es nicht auf. Abhilfe: `ROOT / "cache"` durchreichen. Schwere:
niedrig.

**Q3 · Eine kaputte Park4Night-Antwort beendet den ganzen Lauf.**
`park4night.py:116-118` `float(place["rating"])`, `int(place["review"])`,
`round(float(distance))` ohne Fang; `fetch()` in Zeile 188 fängt nur
`Park4NightError`; `cli.py:169` `add_camping` hat keinen `try`. Ein `rating:
"n/a"` in einer inoffiziellen Schnittstelle, die sich „jederzeit ändern“
kann, wirft `ValueError` bis in den Worker. Verstößt gegen die Regel aus
ENTWICKLUNG.md, dass jede Quelle ausfallen darf. Abhilfe: `_num()` überall
in `_tidy()`, `except Exception` je Spot in `fetch()`. Gleiches Muster in
`ensemble.py:57` (`entry.get` auf Nicht-Dict) und `cli.py:117` (nur
`EnsembleError` gefangen). Schwere: mittel.

**Q4 · Antworten werden ohne Größenlimit gelesen.** Nur Overpass hat
`MAX_BYTES`; `openmeteo`, `ensemble`, `highres`, `marine`, `routing`,
`park4night`, `meteoalarm` lesen `resp.read()` bis zum Ende. Ein Server, der
nicht aufhört, füllt den Speicher. `resp.read(LIMIT + 1)` wie bei Overpass.
Schwere: niedrig.

**Q5 · `SONNE_STATISTIK` ist ein Modul-Global und wird nie zurückgesetzt.**
`score.py:27`. In der Oberfläche summiert es über alle Läufe der Sitzung;
`abweichung_min` ist das Maximum seit Start, nicht seit diesem Lauf, und zwei
gleichzeitige Läufe (S5) schrieben durcheinander. Abhilfe: je Lauf ein Dict
durchreichen. Schwere: niedrig.

## Was gut ist — und bleiben sollte

Die Tests prüfen Regeln, nicht Zeilen: `test_security.py` hält die
Entscheidungen des Audits fest, `test_catalog.py` die Form des Assets, der
synthetische See die Geometrie. `spotedit` arbeitet auf Textebene und erhält
die Kommentare des Katalogs. Jede Quelle liegt in einem eigenen Modul mit
eigenem Fehlertyp. Die Modell-Plakette zeigt seit 1.5.1 den Median — das war
die richtige Korrektur, und dieselbe Skepsis gegenüber „bester Stunde“ würde
B2 und B6 lösen. Der Changelog begründet; deshalb ließ sich B1 überhaupt als
Widerspruch erkennen.

## Was nach 1.7.0 offen bleibt

- **B11, zweite Stufe:** Warnungen ohne `region` stehen jetzt einmal im Kopf
  statt an jedem Spot. Besser wäre die Zuordnung über die Polygone oder
  EMMA-Gebietskennungen im CAP-Feed — Punkt-in-Polygon kann `geometry.py`
  schon. Dann bekämen auch die 192 Spots ohne `region` ihre Warnung.
- **B8, Rand:** die Zeitzone kommt aus dem Landeskürzel; Spots ohne Land
  (10 im Katalog) laufen als Mitteleuropa. `timezone=auto` bei Open-Meteo wäre
  je Punkt exakt, aber für Punkte auf dem Wasser nicht sicher belegt.
- **B12** ist als Option gebaut und steht auf 0 (nur Warnung). Ob 10 km die
  richtige Grenze ist, sagt nur die Erfahrung.
- **Q1, Altbestand:** Overpass-Auszüge ohne Stempel gelten weiter. Wer sicher
  sein will, dass kein Auszug zu einer inzwischen korrigierten Koordinate
  gehört, lässt `build_geometry.py --force` einmal über die 7 heute
  korrigierten Spots laufen (`--only …`).
- Der Prüflauf lief unter 3.10 und 3.14; die 3.9-Untergrenze prüft nur der
  Prüflauf auf GitHub.

---

# Struktur-Review 20.09.2026 (Stand 1.14.0)

Die Frage diesmal: Wie würde ein Softwareentwickler, der das Projekt zum
ersten Mal öffnet, Ordner und Code beurteilen? Kurz: **für ein
Ein-Personen-Werkzeug ungewöhnlich sauber** — ein Paket mit klaren Modulen,
jede Fremdquelle in ihrem eigenen Modul mit eigenem Fehlertyp, rund 360 Tests
ohne Netz, Prüflauf vor jedem Commit und auf GitHub unter Python 3.9 und 3.12,
eine einzige Stelle für die Versionsnummer, ein Changelog, der begründet.
Was ein Entwickler bemängeln würde, ist fast alles eine Frage der
*Größe*: Der Programmcode (ohne Tests) ist von 1.0.0 bis 1.14.0 von rund
5 700 auf 12 600 Zeilen gewachsen, dazu 5 700 Zeilen Tests — und einige
Stellen tragen das nicht mehr gut.

## Was gut ist — und bleiben sollte

- `wingscout/` als Paket, `sources/` ein Modul je Dienst, `tests/`, `tools/`
  — die übliche Aufteilung, sofort lesbar.
- Tests prüfen Regeln statt Zeilen (siehe oben); die Sicherheitsregeln
  stehen als Tests fest (`test_security.py`).
- Jede Datei wird atomar geschrieben, jeder Cache trägt die Koordinate, für
  die er gilt, jede Antwort wird begrenzt gelesen.
- Eine Abhängigkeit (PyYAML), sonst Standardbibliothek — auf einem frischen
  Mac in einer Minute lauffähig.

## Befunde

**A1 · Die Oberfläche ist eine Datei mit drei Sprachen darin (hoch).**
`webui.py` hat 2 860 Zeilen, davon grob die Hälfte HTML, CSS und JavaScript
in Python-Zeichenketten; `report.py` (1 600 Zeilen) ebenso. Folgen: kein
Editor hilft beim JavaScript, Fehler zeigen sich erst im Browser, und in den
f-String-Vorlagen muss jede geschweifte Klammer verdoppelt werden (ENTWICKLUNG.md
warnt davor). Üblich wäre: CSS und JS als eigene Dateien
(`wingscout/web/static/*.css`, `*.js`), vom Server ausgeliefert oder beim
Seitenbau eingelesen (`importlib.resources`), die Seitenfunktionen je Reiter
in ein eigenes Modul, Routing und Handler in `wingscout/web/server.py`.
Vorschlag: schrittweise, eine Seite je Version, angefangen beim Rückblick
(sein JavaScript ist schon ein reiner String ohne f-String). `check.sh` prüft
dann jede JS-Datei mit `node --check`, wenn Node da ist. Aufwand: zwei, drei
Sitzungen; Risiko mittel, weil die Oberfläche am häufigsten bricht — die
Tests in `test_webui.py` fangen das meiste.

**A2 · Der Projektordner ist voll (mittel).** 34 Einträge auf oberster
Ebene (25 davon versioniert): sechs Doppelklick-Starter (dazu
`wingscout.bat` für Windows), neun Markdown-Dateien, Daten (`spots.yaml`,
`geometry.json`, `instagram.json`), Skripte (`run.py`, `build_geometry.py`)
und erzeugte Dateien (`report.html`,
`demo_report.html`). Üblich wäre `daten/` für Katalog und abgeleitete Daten
und `docs/` für ENTWICKLUNG, PRUEFSTAND, REVIEW, WAS-SICH-GEAENDERT-HAT; im
Hauptordner blieben README, CHANGELOG, TODO, MITARBEIT, SICHERHEIT (GitHub
erkennt die letzten beiden unter ihren englischen Namen `CONTRIBUTING.md`
und `SECURITY.md`), die Starter (die sollen mit einem Doppelklick im Finder
erreichbar bleiben) und die Konfiguration. Nicht nebenbei machen: Pfade
stehen in Code, Tests, Doku, Anleitungen im TODO und im Merge-Treiber
(`.gitattributes`) — ein eigener Schritt mit eigener Version.

**A3 · Kein `pyproject.toml` (mittel).** Abhängigkeiten stehen in
`requirements.txt` (`PyYAML>=6.0`, ohne Obergrenze), Projektangaben nirgends
maschinenlesbar. Üblich ist heute ein `pyproject.toml` mit Name, Version
(aus `wingscout/__init__.py` gelesen), `requires-python = ">=3.9"`,
`PyYAML>=6,<7` und der Konfiguration der Werkzeuge (unten). Kosten: eine
Datei, kein Umbau.

**A4 · Kein Linter (mittel).** Fehler, die ein Linter in Sekunden findet,
fallen hier nur über Tests auf oder gar nicht: In `stationen.py` stand `csv`
doppelt importiert (in 1.14.0 aufgeräumt). Vorschlag: `ruff` mit den
Pyflakes-Regeln (ungenutzte Importe und Variablen, Namen, die es nicht gibt)
im Prüflauf auf GitHub; lokal nur, wenn installiert, damit ein frischer Mac
nicht scheitert. Typprüfung (`mypy`) später und nur für `sources/`, wo die
Antworten fremder Dienste die meisten Überraschungen bringen.

**A5 · Das Netz steckt in acht Kopien (niedrig).** Jede Quelle baut ihren
Request selbst: User-Agent, Timeout, Fehlertyp, JSON lesen — acht leicht
verschiedene `_get`/`_post_json`. Eine gemeinsame Hilfe in
`sources/netz.py` (`hole_json(url, timeout, ua)`, `sende_json(...)`) würde
das vereinheitlichen; `lies()` ist dafür schon der Anfang. Nutzen: eine
Stelle für Wiederholungen, Größenlimit und Protokoll.

**A6 · Zustand auf Modulebene (niedrig).** `webui.JOB`, `LOCK` und das
Protokoll, dazu `score.SONNE_STATISTIK` (Q5 der Review vom 16.09.): für eine Oberfläche mit
einem Benutzer vertretbar und durch `_starte()` gut gekapselt. Wenn die
Oberfläche weiter wächst, gehört das in eine kleine Klasse, die man in
Tests frisch anlegen kann, statt globale Werte zurückzusetzen.

**A7 · Der Prüflauf auf GitHub ist hinter dem lokalen zurück (niedrig).**
Der Kommentar in `.github/workflows/tests.yml` nennt 132 Tests (es sind
rund 360), und die Liste der persönlichen Dateien, die nie versioniert sein
dürfen, kennt `modellguete.json` noch nicht (`.gitignore` schon). Nicht in
1.14.0 geändert: ein Push, der die Workflow-Datei ändert, braucht einen
Token mit dem Haken `workflow` (ENTWICKLUNG.md), und der vorhandene hat ihn
nicht. Wer das nachzieht: Token erweitern oder per SSH pushen.

**A8 · Testabdeckung wird nicht gemessen (niedrig).** Rund 360 Tests sagen
nicht, welche Zweige nie laufen. Ein Lauf mit `coverage` (einmal, ohne
Zielwert) zeigt die weißen Flecken — Vermutung: Zweige in `report.py` und
`cli.py`.

## In 1.14.0 schon behoben

- Tests konnten ins Netz — jetzt gesperrt (`tests/__init__.py`).
- `spotedit` schrieb in Unterblöcke: ein Spot mit Thermikblock hat zwei
  `name:`, und umbenannt wurde der Wind statt des Spots. Jetzt zählt nur
  die Ebene des Spots, ein Test hält es fest.
- Doppelter Import in `stationen.py`.

## In 1.16.0 behoben

- **A1:** CSS und JavaScript der Oberfläche *und* des Reports stehen als
  eigene Dateien in `wingscout/web/` (15 Dateien), gelesen beim Start über
  `lies_web()`; `check.sh` prüft das JavaScript mit `node --check`.
  `webui.py` ging von 2 954 auf 1 569 Zeilen (mit dem neuen Tagebuch jetzt
  1 819), `report.py` von 1 624 auf 1 137. Daten gehen als JSON in eine
  Variable vor dem Skript, statt in die Vorlage eingesetzt zu werden. Die
  Ausgabe ist geprüft gleich: Prüf-, Katalog- und Rückblickseite bytegleich,
  die Startseite bis auf das neue `var LEAFLET`; die Karte im Report im
  Browser gegen eine nachgebaute Leaflet-Schnittstelle: alle 278 Marker,
  keine Fehler. Anders als vorgeschlagen bleiben
  Seitenfunktionen und Handler in `webui.py` — das lohnt erst, wenn die
  Oberfläche weiter wächst. Übrig als Vorlage: das HTML-Gerüst von `page()`
  und `report._raster_schalter` (%-Vorlage).
- **A3:** `pyproject.toml` mit Name, Version aus `wingscout/__init__.py`,
  `requires-python = ">=3.9"`, `PyYAML>=6,<7` und den Regeln des Linters;
  `requirements.txt` hat dieselbe Obergrenze.
- **A4, lokal:** ruff im Prüflauf (Pyflakes, Syntaxfehler, drei
  Bugbear-Regeln für veränderliche Vorgabewerte), übersprungen mit Hinweis,
  wenn nicht installiert. Der erste Lauf fand acht ungenutzte Importe, drei
  ungenutzte Variablen im Code und zwei in einem Test, zwei f-Strings ohne
  Platzhalter und zwei doppelte Einträge in einer Menge
  (`koordinaten_check.py`) — nichts davon ein Fehler im Ergebnis, alles
  behoben. Ein Probelauf mit weiteren Bugbear-Regeln meldete B023 in
  `score.py` (Schleifenvariable in einer inneren Funktion) — ein Fehlalarm,
  die Funktion wird in derselben Runde aufgerufen; die Regel ist deshalb
  nicht ausgewählt. Auf GitHub läuft ruff noch nicht mit — das gehört zu A7.

## Reihenfolge, wenn es weitergehen soll

1. Prüflauf auf GitHub nachziehen (A7) samt ruff — braucht den Token mit
   `workflow`-Haken.
2. `daten/` und `docs/` (A2), als eigene Version.
3. Gemeinsame Netzhilfe (A5), wenn ohnehin eine Quelle angefasst wird.

---

# Review 25.09.2026 (Stand 1.18.3): Sicherheit und Bedienung

**Stand nach 1.19.1:** alle Befunde unten sind umgesetzt (CHANGELOG 1.19.0
führt jeden mit seiner Nummer auf; `tests/test_review_2026_09.py` stellt sie
nach), auch der zweite Teil von S8 — die Content-Security-Policy mit Nonce
kam als 1.19.1 (`wingscout/csp.py`). Die Texte darunter sind der Befund vom
Morgen, als Begründung stehen gelassen.

Gelesen wurde der ganze Code — `wingscout/`, `sources/`, `web/*.js`, die
Startskripte, `tools/`, Tests — in drei getrennten Durchgängen (Server und
Endpunkte; Parser, Fremddienste und Dateien; Browser-Seite), danach jeder
Befund gegen den Code geprüft und, wo es ohne Netz ging, nachgestellt. Zur
Bedienung: alle Seiten in Chromium bei 1280 px und 390 px durchgeklickt,
dazu die Zustände, die man im Alltag trifft (unlesbarer Katalog, unlesbarer
Startpunkt, laufende Suche, leere Seiten). Zeilenangaben gelten für 1.18.3.
Schwere: **hoch** (jetzt beheben), **mittel** (in der nächsten Version),
**niedrig** (bei Gelegenheit), **Hinweis** (Härtung, kein Fehler).

## Kurzfazit

Die Grundhaltung stimmt weiterhin: `safe_load`, `_esc()` an praktisch jeder
Stelle, fünf vollständige `esc()`-Fassungen im JavaScript, JSON im Skript
gegen `</script>` gehärtet, Timeouts und Größenlimits an jedem Netzaufruf,
nur HTTPS, Herkunftsprüfung auf jedem POST, Zugangsschlüssel mit
`compare_digest`, atomares Schreiben, strikt geprüftes Tagebuch. Tests halten
die Regeln fest. Von außen — ohne Zugang zum Rechner oder zum Katalog — habe
ich keinen Weg gefunden, etwas auszuführen.

Gefunden habe ich trotzdem **eine echte Lücke** (S1: ein Katalogfeld landet
unescaped im Report, und der Report läuft unter der Herkunft der Oberfläche)
und **sechs Wege, den Katalog oder die Oberfläche lahmzulegen** (S2–S7): ein
Steuerzeichen im Spotnamen, eine gebaute GPX-Datei, ein 40-KB-Paste, eine
Koordinate `nan`. Nichts davon ist heute ausnutzbar, ohne dass jemand eine
Datei liefert, die du einliest, oder den Katalog schreibt — aber genau das ist
der Plan (geteilter Katalog, Community-Spots). Deshalb gehören S1–S7 vor die
Öffnung des Katalogs, und S1 sofort.

Bei der Bedienung ist der größte Punkt, dass ein kaputter Katalog die Seiten
Katalog, Tagebuch und Rückblick **ohne jede Meldung** verschwinden lässt
(U1); dann ein Startfeld, das Ortsnamen zu erlauben scheint, sie aber still
verwirft (U2); und Stundenraster-Tooltips, die es am iPhone nicht gibt (U3).
Der Rest ist Politur: Kontrast, Datumsformate, Textwände.

## Sicherheit

**S1 · Katalogfeld `sectors[].water` steht unescaped im Report (hoch,
nachgestellt).** `score.py:162` reicht `sec.get("water", "chop")` roh aus dem
Katalog durch (`row["water"]` → Session `water`), und `report.py:672`
(`_sessions_tabelle`) sowie `report.py:833` (`_trip_article`) schreiben es in
Klasse und Text: `<span class='pill p-{s['water']}'>{WATER_LABEL.get(s['water'],
s['water'])}</span>` — beide ohne `_esc`. Alle anderen Katalogwerte laufen
durch `_esc`; `water` gilt intern als festes Wort (`flat`/`chop`/`wave`), wird
aber weder in `load_spots` (`spots.py:125`) noch im Katalogtest geprüft
(`test_catalog.py` prüft `quality`, `from`, `to`, nicht `water`).
Nachgestellt: ein Sektor mit `water: "chop'><img src=x onerror=alert(1)>"`,
Demo-Lauf → im Report steht `<span class='pill p-chop'><img src=x
onerror=alert(1)>` viermal als echtes Markup. Der Report wird unter `/report`
**mit der Herkunft der Oberfläche** ausgeliefert und auf der Startseite im
Rahmen eingebettet; Skript darin ruft dieselben POST-Endpunkte wie die
Oberfläche (`_same_origin` ist erfüllt): Katalog löschen, umschreiben,
Wingscout beenden. Per AirDrop wandert dieselbe Datei aufs iPhone. Wer den
Katalog schreibt — heute du, morgen eine Beitragende —, kann das auslösen;
der Dateiimport setzt keine Sektoren, eine geteilte `spots.yaml` schon.
*Fix:* an beiden Stellen Klasse aus einer Whitelist (`s['water'] if s['water']
in WATER_LABEL else 'chop'`) und Text durch `_esc`; in `load_spots` die
Sektoren normieren (`water` ∈ {flat, chop, wave}, `quality` ∈ QUALITY_SCORE,
`from`/`to` Zahlen) mit `KatalogFehler` bei Unbekanntem; Katalogtest um
`water` ergänzen; ein Test mit bösartigem Sektor neben dem bestehenden mit
bösartigem Namen (`test_report_cli.py`).

**S2 · GET prüft den Host nicht, nur POST (mittel, Mechanik nachgestellt).**
`do_GET` (`webui.py:2020`) ruft nur `_zugang()`, `_same_origin()`
(`webui.py:1575`, Host-Whitelist gegen DNS-Rebinding) läuft nur in `do_POST`.
Eine fremde Webseite im selben Browser kann mit einem eigenen Namen, der auf
127.0.0.1 zeigt, `/status`, `/katalog`, `/tagebuch/daten`,
`/rueckblick/daten`, `/report` und die Startseite (mit `var HOME = {lat,
lon}`, im WLAN-Betrieb mit dem Zugangsschlüssel in der Klappe „Datenquellen“)
lesen; POST bleibt zu Recht 403. Nachgestellt mit `Host: evil.example:8799`
→ 200 samt Inhalt. Das ist Lesen, nicht Schreiben — aber genau die Daten, die
schützenswert sind (Heimatkoordinate, Aufenthaltsmuster aus dem Tagebuch).
Chrome blockt solche Aufrufe aus dem Internet inzwischen teilweise (Private
Network Access), Safari nicht verlässlich. *Fix:* `_same_origin()` auch in
`do_GET`, mindestens der Host-Teil; bei fremdem Host 403 wie bei POST.

**S3 · Nicht-ASCII im Schlüssel oder Cookie wirft vor der Zugangsprüfung
(mittel, nachgestellt).** `zugang_pruefen` (`webui.py:149`, `:153`) ruft
`hmac.compare_digest` auf Strings; bei Nicht-ASCII (`?k=%C3%BC`, ein Cookie
mit `ü`) wirft das `TypeError: comparing strings with non-ASCII characters is
not supported`. Der Handler stirbt mit Traceback im Terminal (Pfade,
Benutzername), die Verbindung bricht ab; der Server läuft weiter. Erreichbar
im WLAN-Betrieb von jedem Gerät ohne Schlüssel. *Fix:* beide Seiten als Bytes
vergleichen (`hmac.compare_digest(a.encode(), b.encode())`) — das ist der
vorgesehene Weg für beliebige Eingaben; Test mit `ü` im Schlüssel.

**S4 · Steuerzeichen über „umbenennen“ machen den Katalog unlesbar (mittel,
nachgestellt).** `spotedit.set_text` (`spotedit.py:167`) escaped nur `\`,
`"`, `\n`, `\t`; alle anderen Steuerzeichen (`\x00`–`\x1f`, `\x7f`,
`\x80`–`\x9f`) landen wörtlich im Skalar, und PyYAMLs Reader lehnt sie beim
nächsten Laden ab („special characters are not allowed“). Nachgestellt:
`set_text(p, "a", "name", "Spot\x01X")` → `load_spots` wirft `ReaderError`.
Der Kommentarpfad läuft über `kommentar_putzen` (sauber), der Namenspfad
`/katalog/umbenennen` (`webui.py` ab 1717) nur über `" ".join(name.split())`
— das entfernt Leerraum, keine Steuerzeichen; JSON transportiert `\u0001`.
Ein Katalog mit 278 Spots ist danach für alle Seiten unlesbar, bis jemand die
Datei von Hand repariert (siehe U1). Dazu: `ReaderError`/`ParserError` sind
`yaml.YAMLError`, kein `ValueError` — `load_spots` reicht sie unverpackt
durch, obwohl mehrere Stellen in `webui.py` nur `ValueError` fangen. *Fix:*
in `set_text` Steuerzeichen entfernen (oder als `\xNN` schreiben) und
`kommentar_putzen` auch für Namen nutzen; in `load_spots` `yaml.YAMLError` zu
`KatalogFehler` mit Zeilenangabe machen; Test „jedes Zeichen < 0x20 durch
`set_text`, danach liest `load_spots`“.

**S5 · Die DOCTYPE-Sperre im Import ist umgehbar (mittel, nachgestellt).**
`ingest._xml` (`ingest.py:102`, `:111`) sucht `<!doctype`/`<!entity` nur in
den ersten 4000 Zeichen, und `parse_text` (`:251`) erkennt das Format per
Substring in den ersten 2000 — auch innerhalb eines XML-Kommentars. Eine
Datei mit `<!-- <gpx> -->`, 4200 Zeichen Kommentar, dann dem echten `<!DOCTYPE
… [<!ENTITY …>]>` und `<gpx>` wird als GPX geroutet, die Sperre sieht nichts,
`ET.fromstring` expandiert die Entitäten. Nachgestellt: zwei Ebenen → ein
Wegpunkt mit 200 Zeichen Namen aus 4 Zeichen Quelle. Mit Apples Python 3.9
(altes expat ohne Amplifikationslimit — der Grund, den die Docstring selbst
nennt) heißt das Speicher und CPU des Hintergrundjobs nach Belieben; mit
neuem expat bricht es ab. Nebenbei gibt es im Importpfad kein Längenlimit für
Namen (S7). Dasselbe `ET.fromstring` ohne Sperre steht in
`sources/meteoalarm.py:50` (Feed über HTTPS — nur mit manipuliertem Server
relevant, niedrig). *Fix:* die Prüfung über den ganzen Text
(`re.search(r"<!\s*(doctype|entity)", text, re.I)`), besser: einen
`ET.XMLParser` mit expat-Handlern, die bei DOCTYPE/Entity abbrechen (so macht
es defusedxml, ohne neue Abhängigkeit nachbaubar), in einer gemeinsamen
Hilfe für Import und MeteoAlarm; Formaterkennung nach dem Entfernen von
XML-Kommentaren oder am geparsten Wurzeltag.

**S6 · Quadratische Laufzeit im Koordinaten-Regex (mittel, nachgestellt).**
`ingest.DMS_PAIR` (`ingest.py:51`) enthält zweimal `[^NSEWO]*`; `parse_line`
ruft es je Zeile. Gemessen: eine Zeile aus `1°1x` wiederholt — 20 KB → 1,1 s,
40 KB → 4,1 s, Vervierfachung je Verdopplung; bei 4 MB (`MAX_BODY`) sind das
Stunden. Der Import läuft als Hintergrundjob, und solange er läuft, bekommt
jede Suche und jede Katalogänderung 409 „Es läuft schon etwas“; abbrechen
kann man ihn nicht. *Fix:* Zeilen vor dem Regex kappen (`line[:500]` —
keine Koordinatenzeile ist länger) und die Quantoren begrenzen
(`[^NSEWO\n]{0,20}`), dazu Treffer je Import deckeln.

**S7 · `nan`, `inf` und Koordinaten außerhalb des Bereichs kommen aus
Importdateien in den Katalog (mittel, Parser nachgestellt).** `ingest.py:129`
(GPX), `:170` (KML), `:200` (GeoJSON), `:238` (CSV) prüfen nur `float()`; nur
der Freitext- und Link-Pfad läuft durch `geo._plausible`. Nachgestellt:
`<wpt lat="nan" lon="3.8">` und `<wpt lat="95" lon="200">` kommen beide als
Treffer zurück; `append_to_yaml` schreibt `.nan`, `load_spots` liest es,
`eligible` behält den Spot immer (jeder Vergleich mit NaN ist False), und die
Open-Meteo-Anfrage trägt `latitude=nan`. Open-Meteo antwortet auf ungültige
Koordinaten mit 400, `fetch` verwirft dann das **ganze Paket von 20 Spots**
(Lesebefund; die API-Antwort selbst ließ sich ohne Netz nicht prüfen). Ein
einzelner Wegpunkt einer fremden Datei kann damit jede Suche vergiften, bis
er von Hand entfernt ist; `lon="inf"` lässt den Import gleich mit `math
domain error` sterben. *Fix:* in `build_entry` und in `load_spots`
`math.isfinite` plus Bereich (−90…90, −180…180), sonst Treffer verwerfen und
in `problems` nennen bzw. `KatalogFehler` mit Spot-ID.

**S8 · Fehlende Antwort-Header (niedrig).** `_send` (`webui.py:1528`) setzt
`Content-Type` mit Zeichensatz, `Cache-Control: no-store` und `X-Frame-Options:
SAMEORIGIN` — gut. Es fehlen `X-Content-Type-Options: nosniff`,
`Referrer-Policy` (externe Links tragen `rel="noopener"`, nicht `noreferrer`;
der Schlüssel steht dank des 302 zwar nie in einer gerenderten Adresse, die
lokale Adresse geht aber als Referer an Windy, Google, Park4Night) und eine
`Content-Security-Policy`; der 302 in `_zugang` (`:1990`) trägt kein
`no-store`. *Fix:* `nosniff` und `Referrer-Policy: no-referrer` in `_send`;
`no-store` auch im Redirect. Eine CSP lohnt als zweite Verteidigungslinie
gegen S1-artige Fehler, verlangt aber Arbeit: alle Skripte sind inline
(`lies_web()`), also je Antwort eine Nonce an jedem `<script>`, `style-src`
mit `'unsafe-inline'` (Raster-Zellen tragen `style=`), `script-src` und
`style-src` mit `https://cdnjs.cloudflare.com`, `img-src` mit den
OSM-Kacheln und `data:`, `connect-src 'self'`, `object-src 'none'`, `base-uri
'none'`. Für die Report-Datei ginge dasselbe als `<meta http-equiv>` mit einer
Nonce je Erzeugung — ein Katalogtext kennt sie nicht, sein Skript bliebe stumm,
auch als `file://` auf dem iPhone. Inline-Ereignisattribute (`onclick=`) gibt
es nirgends; das erleichtert den Umbau.

**S9 · Fehlermeldungen tragen lokale Pfade (niedrig).** Mehrere
`_antwort(400, error=f"… {exc}")` (z. B. `webui.py` bei „Konnte nicht
speichern“) und die ungefangenen Tracebacks (S3, U1) geben Ausnahmetexte mit
Dateipfaden und Benutzernamen an den Browser bzw. ins Terminal. Am eigenen
Rechner unerheblich, im WLAN-Betrieb unnötig. *Fix:* nach außen der Satz,
Details ins Terminal.

**S10 · Zusatzquellen können die ganze Suche zu Fall bringen (niedrig,
Lesebefund).** `tide.extrema` (`tide.py:47`) rechnet `datetime.fromisoformat`
und `float` über die Marine-Antwort ohne Schutz, und `cli.py` fängt nur den
Abruf, nicht die Verarbeitung; ein unlesbarer Zeitstempel oder ein String
statt Zahl → `ValueError` → kein Report. Ebenso `ensemble.window_stats`
außerhalb des `try` in `cli.py`. Routing, Highres, Park4Night, MeteoAlarm
sind dagegen als Ganzes gefangen. *Fix:* `extrema` tolerant (`continue` bei
`TypeError`/`ValueError`), `window_stats` nur mit Zahlen rechnen, beide Blöcke
in `cli.py` wie die anderen Zusatzquellen fangen.

**S11 · `spotedit` und handgepflegte Blöcke (niedrig, nachgestellt).** Steht
`comment: |` mehrzeilig im Katalog, ersetzt `set_text` nur die Kopfzeile und
lässt die Kinder als Waisen stehen → `ParserError`; `set_block`
(`spotedit.py:116`) schreibt feste zwei bzw. vier Leerzeichen statt der
Einrückung des Blocks — bei einem Spot mit vier Leerzeichen wandern `name`,
`lat`, `lon` unter `tide:` → „Spot ohne name“. Im gelieferten Katalog sind
alle Blöcke zweifach eingerückt und einzeilig; das ist ein Fallstrick für
Handpflege, kein Angriff. *Fix:* `set_text` erkennt `|`/`>` und Kinder und
ersetzt wie `entferne_feld` den ganzen Unterblock; `set_block` nutzt
`_einrueckung`.

**S12 · Import ohne Mengengrenzen (Hinweis).** `webui.py` `start_ingest`:
`viele` schützt nur Treffer mit Namen; je namenlosem Punkt eine
Nominatim-Anfrage mit 1,1 s Sperre — 10 000 namenlose Wegpunkte (passen in
4 MB) sind drei Stunden Hintergrundjob, 10 000 Anfragen gegen die
Nutzungsregeln von Nominatim und danach 10 000 neue Spots (jede Suche fragt
dann 500 Open-Meteo-Pakete). Namen sind im Importpfad nicht auf 120 Zeichen
gekappt wie in `/katalog/neu`. Import-Parser sterben zudem an gültigen, aber
ungewöhnlichen Dateien (leeres `<coordinates>`, `coordinates` als Objekt,
CSV-Feld über 128 KB) — ein Datensatz kostet die ganze Datei. *Fix:* Treffer
je Import deckeln (z. B. 500), Nominatim-Anfragen je Import (z. B. 40, der
Rest heißt nach Koordinate), Namen kappen, je Datensatz fangen und in
`problems` melden.

**S13 · Härtung in `sources/` (Hinweis).** Stations-IDs aus Netzantworten
werden zu Cache-Dateinamen (`stationen.py` Rijkswaterstaat, GeoSphere, DMI,
Météo-France `dept` auch in den URL-Pfad) — ein Ausbruch aus `cache/` ist
wegen fester Präfixe praktisch nicht möglich, `overpass.safe_id()` davor wäre
trotzdem richtig. DWD-ZIP-Mitglieder werden ohne Größenprüfung entpackt
(`stationen.py:269`, `:304`; 64 MB Grenze gilt nur komprimiert). `urllib`
folgt Weiterleitungen auch auf `http://`. `netz.MAX_ANTWORT` 64 MB für
Dienste, die Kilobytes liefern. Korrupter Overpass-Cache (`overpass.py:190`)
wirft ungefangen bei jedem Lauf. `instagram._sicher` lässt `http://` zu.
`config.py:39` legt `config.yaml` (Heimat, ggf. Windguru-Passwort) mit
Standard-Rechten an — `0o600` wäre angemessen. `report.write`
(`report.py:1226`) schreibt nicht atomar, während `/report` die Datei
jederzeit ausliefert. Der Test `test_gitignore_deckt_persoenliches_ab` führt
`tagebuch.json`, `modellguete.json`, `config.yaml` nicht auf (die
`.gitignore` schon).

**S14 · Kleinigkeiten, geprüft (Hinweis).** Der Kasten „Auf dem iPhone“ mit
dem Schlüssel (`webui.py:680`) trägt `nurgross`, aber nur `.reiter a.nurgross`
hat eine CSS-Regel — er ist am Handy sichtbar; der Kommentar im Code sagt das
Gegenteil (harmlos, wer ihn sieht, hat den Schlüssel). `_json_im_skript`
escaped U+2028/2029 nicht — seit ES2019 in Skript-Literalen erlaubt, kein
Befund. Same-Origin: `Origin: null`, fremde Origin, fremder Host,
`text/plain`-Formular von fremder Seite — alle 403 (nachgestellt); fehlender
Origin (curl) läuft über den Host. Schlüssel: 72 Bit, `compare_digest`,
Cookie `HttpOnly; SameSite=Lax`, 302 nimmt `k` aus der Adresse — in Ordnung.
`parse_form` klemmt jeden Zahlenwert; Tagebuch, `/katalog/neu`, `/pruefen/*`
prüfen strikt. Kein `eval`, kein Shell-Aufruf, keine inline-Ereignisattribute.
ruff mit den Bandit-Regeln (`--select S`) findet nichts über S5 hinaus.

## Bedienung

**U1 · Ein kaputter Katalog lässt Seiten wortlos verschwinden (hoch,
nachgestellt).** Mit einer unlesbaren `spots.yaml` (ein fehlendes
Anführungszeichen genügt — oder S4) antworten `/katalog`, `/tagebuch` und
`/rueckblick` gar nicht: `do_GET` (`webui.py:2020`) fängt nichts, der Handler
stirbt, der Browser zeigt „Verbindung unterbrochen“, der Grund steht nur im
Terminal. Die Suchseite lädt noch, eine Suche endet dann mit Jobfehler. Wer
nicht ins Terminal schaut, hält Wingscout für kaputt. *Fix:* in `do_GET` und
`do_POST` `KatalogFehler`, `yaml.YAMLError`, `KonfigFehler` und `OSError`
fangen und eine Seite ausgeben: „Katalog nicht lesbar — spots.yaml, Zeile
9253: …“ mit dem Hinweis, was zu tun ist (Zeile ansehen, `git checkout
spots.yaml`, Prüflauf); `load_spots` muss dafür `YAMLError` in `KatalogFehler`
verpacken (S4).

**U2 · Das Startfeld verspricht Ortsnamen und verwirft sie still (mittel,
nachgestellt).** „Von wo aus?“ zeigt als Platzhalter den Namen des
Startpunkts („Heidelberg“), akzeptiert aber nur Koordinaten und Maps-Links
(`geo.parse_position`). Wer „Hamburg“ eintippt, bekommt eine Suche von
Heidelberg aus; der einzige Hinweis ist eine Zeile im zugeklappten Protokoll
(`Startpunkt "Hamburg" nicht lesbar — bleibe bei Heidelberg`), der Banner
sagt „23 Sessions in 23 Zielen“. *Fix:* Platzhalter „Koordinate oder
Maps-Link — leer = Heidelberg“; unlesbare Eingabe vor dem Start mit 400
abweisen und im Banner sagen, was geht („51.76, 3.85 · ein Google-Maps-Link ·
„Hier“ · „Karte““); im Ergebnis-Banner den benutzten Startpunkt nennen („von
Heidelberg aus“).

**U3 · Stundenraster ohne Tooltips am iPhone (mittel).** Jede Zelle erklärt
sich nur über `title` (`report.py`, Raster) — am Handy gibt es kein Hover,
mit Tastatur keinen Fokus. Genau dort, wo man unterwegs wissen will, warum
eine Stunde grau ist (Nacht? Tidenfenster? kein Wing?), fehlt die Antwort.
*Fix:* Tipp/Klick auf eine Zelle zeigt den Text in einem kleinen Kasten
unter dem Raster (ein Handler in `mobil.js` oder `sessions.js`, `title`
bleibt für den Rechner); Zellen mit `tabindex` und `aria-label`.

**U4 · Gedämpfter Text unter der Lesbarkeitsgrenze (mittel).** `--muted:
#6C858F` erreicht 3,6:1 auf dem Seitengrund und 3,9:1 auf Weiß; WCAG AA
verlangt 4,5:1 für Text unter 18 pt — und gerade die kleinen Zeilen (0,76–0,88
rem: Sessiondetails, Tidenmeta, Katalognotizen, Hinweise) stehen darin. Im
Dunkelmodus ist es in Ordnung (6,0:1). *Fix:* `--muted: #536E7A` (4,9:1 auf
Grund, 5,4:1 auf Weiß, 4,5:1 auf `--surface-2`), Dunkelmodus unverändert;
Report-CSS gleich mit.

**U5 · Textwände (niedrig).** „Was man wissen muss“ (Rückblick) und „So
rechnet das Tagebuch“ sind am Rechner aufgeklappt und ein einziger Absatz
über 15 Zeilen; am Handy klappt `mobil.js` sie zu. *Fix:* auch am Rechner zu,
und der Inhalt als fünf kurze Punkte (Was gilt als Messung · Welche Modelle ·
Was MAE/Bias/F1 heißen · Woher die Station · Was das Gedächtnis tut).

**U6 · Datumsformate (niedrig).** „Letzte Suche: 2026-09-25 14:27“
(Rückblick) und „Verglichen 2026-09-20 19:09“ (Tagebuch) neben „So 20.09.2026“
überall sonst — ENTWICKLUNG.md und CHANGELOG verlangen TT.MM.JJJJ. *Fix:*
eine Hilfe `datum_de()` für beide Seiten.

**U7 · Katalogzeilen (niedrig).** Vier Aktionslinks in jeder der 278 Zeilen
(„umbenennen verschieben Tiden löschen“) sind dauerhaft sichtbar — Rauschen
neben dem Namen; „Tiden“ ist ein Hauptwort zwischen Tätigkeitswörtern; der
Filter heißt „Nur“. *Fix:* Aktionen am Rechner erst bei Hover/Fokus der Zeile
(am Handy weiter sichtbar), „Tiden …“ oder „Tiden einstellen“, Filter „Zeige
nur“.

**U8 · Unerklärte Zahl im Tagebuch (niedrig).** Die Session-Karte zeigt
„0/100 · Thermik angenommen“ unter „Wingscout sagte“ — die Güte, ohne dass es
dasteht. *Fix:* „Güte 0 von 100“.

**U9 · Leerer Rückblick (Hinweis).** Vor dem ersten Lauf steht unter der
Erklärung nichts; ein Satz „Noch kein Rückblick — auf „Prüfen“ drücken“
orientiert.

**U10 · „Als Standard merken“ (Hinweis).** Der Knopf steht allein unter den
Klappen, ohne zu sagen, was gemerkt wird; die Bestätigung erscheint nur nach
dem Klick. *Fix:* Titel oder Hinweistext „merkt die Einstellungen aus den
Klappen für den nächsten Start (nicht den Startpunkt)“.

**U11 · Schlüsselkasten am Handy (Hinweis, siehe S14).** Wer am iPhone in
„Datenquellen“ schaut, sieht den Kasten „Auf dem iPhone“ mit der Adresse für
das iPhone — auf dem iPhone. Ausblenden (`.gruppe.nurgross{display:none}` in
der Handy-Regel).

## Was gut ist — und bleiben sollte

- Jede Antwort wird begrenzt gelesen, jede Anfrage begrenzt angenommen; jeder
  Netzaufruf hat ein Zeitlimit; nur HTTPS. Tests halten das.
- `_esc()` und die `esc()`-Fassungen im JavaScript sind vollständig (& < > " ')
  und werden auf Namen, Notizen, Kommentare, Fremdtexte, Popups, Tooltips
  angewendet; JSON im Skript ersetzt `<`, `>`, `&`; Links nur über
  `_safe_url`/`_sicher`; Leaflet mit SRI.
- Herkunftsprüfung auf POST, Schlüssel mit `compare_digest`, `HttpOnly`-Cookie,
  302 nimmt den Schlüssel aus der Adresse.
- `spotedit` trifft per `re.escape(spot_id)` und Zeilenanker nur den eigenen
  Block, Feldnamen `[a-z_]+`, Werte doppelt angeführt (`x"\n- id: evil` bleibt
  nachweislich ein String), atomar per `os.replace`.
- Tagebuch: `pruefe()` prüft jedes Feld gegen Katalog, Quiver und Wertebereich.
- Zwei-Klick-Schutz an „Beenden“ und „Löschen“, 409 statt Doppelstart,
  Sperren zwischen Prüfseite und Hintergrundjob.

## Reihenfolge

Geplant waren drei Versionen (1.18.4 Sicherheit, 1.18.5 Import, 1.19.0
Bedienung); umgesetzt wurde alles am selben Tag als **1.19.0**. Was bleibt:

- ~~CSP mit Nonce (S8, zweiter Teil)~~ — gebaut in 1.19.1: je Antwort eine
  Nonce an jedem `<script>`, `style-src 'unsafe-inline'`, cdnjs und
  OSM-Kacheln freigegeben, für die Report-Datei als `<meta http-equiv>` mit
  Nonce je Erzeugung; in Chromium ohne Verstoß nachgestellt.
- `netz.MAX_ANTWORT` je Quelle statt 64 MB für alle (S13, Kosmetik).
- Tastaturbedienung des Stundenrasters (U3 deckt Tipp und Klick ab; ein
  Fokus auf tausend Zellen wäre für Tastaturnutzer eher ein Hindernis — eine
  Zeile mit Pfeiltasten wäre der richtige Bau, wenn jemand ihn braucht).
