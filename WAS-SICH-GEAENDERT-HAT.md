# Was sich seit 1.0.0 geändert hat

Von 1.0.0 (13.09.2026) bis 1.16.0 (20.09.2026), in sieben Tagen. Dies ist die
Kurzfassung für jemanden, der das Programm benutzt: was der Report heute anders
sagt als am ersten Tag, und warum. Die lange Fassung mit jeder Begründung steht
in `CHANGELOG.md`, die Review vom 16.09. in `REVIEW.md`.

## In einem Satz

1.0.0 konnte schon alles, was Wingscout ausmacht — Spots im Umkreis, drei
Wettermodelle, Ufergeometrie, Fahrzeiten, Stellplätze, ein Report. Seitdem
wurde vor allem eines besser: **wo das Programm danebenlag, sagt es das jetzt,
oder es liegt nicht mehr daneben.** Drei Fehler, die still falsch rechneten,
sind gefunden und behoben; die Wetterdaten sind feiner; die Thermik ist ein
eigenes Kapitel; und der Katalog lässt sich prüfen, statt nur zu wachsen.

## Die Zahlen

| | 1.0.0 | 1.16.0 |
|---|---|---|
| Spots im Katalog | 277 | 278 |
| … mit Ufergeometrie | 138 | 277 |
| … mit Thermikwissen | 4 | 71 |
| … mit Shorebreak-Angabe | – | 34 |
| … mit Instagram-Funden | – | 100 |
| Wettermodelle je Spot | 3 globale | 3 globale + bis zu 1 regionales (1–2,5 km) |
| Messdienste (Rückblick, Prüfstand, Tagebuch) | – | DWD, KNMI, Rijkswaterstaat, GeoSphere, DMI, Météo-France, Windguru mit Passwort |
| Tests | 127 | 410 |
| Python | ab 3.10 | ab 3.9 (das, was der Mac mitbringt) |
| Fremdpakete | PyYAML | PyYAML |

## Drei Fehler, die niemand sah

Zwei davon hatten dieselbe Ursache: Fragt man Open-Meteo nach mehreren
Modellen gleichzeitig, hängt es an jeden Wert den Modellnamen an — aus
`sunrise` wird `sunrise_dwd_icon_seamless`. Was das nicht wusste, griff ins
Leere, ohne Fehlermeldung. Der dritte war schlicht eine fehlende Grenze.

- **Die Nacht galt als fahrbar** (bis 1.5.0). Die Tageslichtprüfung war seit
  dem ersten Tag eingebaut und hat nie gegriffen. Im Report vom 16.09. lagen
  30 % aller Sessionstunden zwischen 20 und 7 Uhr. Seitdem liest das Programm
  den Modellnamen mit — und rechnet Sonnenauf- und -untergang zusätzlich
  selbst aus, damit so etwas nicht wieder unbemerkt bleibt.
- **Die Thermik rechnete ohne Sonne** (bis 1.6.1). Die Einstrahlung, für die
  das Thermikmodul gebaut war, kam nie an; es nahm immer den groben Ersatz
  (Bewölkung). Ein Test prüft jetzt, dass jeder Wert, den die Bewertung
  liest, auch beim Zusammenführen überlebt.
- **Der Report bot die Vergangenheit an** (bis 1.5.0). Wer um elf startete,
  bekam als beste Session „00–10 Uhr“ — und die Stunden zählten mit.

## Wetterdaten: feiner und ehrlicher

- **Regionalmodelle** (1.4.0): Sieben Modelle mit 1 bis 2,5 km Gitter von
  MeteoSwiss, DWD, Météo-France, ARPAE, KNMI, GeoSphere und DMI legen sich für
  zwei bis drei Tage über die globalen. Sie sehen Talwinde und Seebrisen, die
  ein 7-bis-25-km-Gitter wegmittelt. Im Report steht bei jeder Session, welches
  Modell den Wind geliefert hat, und wie viel es gegenüber dem groben ändert.
  Das Modell des Landes gewinnt vor dem feinsten, weil ein Modell am Rand
  seines Gebiets am schlechtesten ist.
- **Die Plakette zeigt den typischen Unterschied, nicht den besten** (1.5.1).
  Vorher stand dort die günstigste Stunde, und die wurde umso günstiger, je
  länger die Session war.
- **Die Wahrscheinlichkeit entscheidet mit** (1.5.0). Vierzig Rechnungen
  derselben Wetterlage sagen, wie sicher die eine Zahl ist. Bis dahin stand
  das nur im Report; Platz 2 konnte „0 % sicher“ tragen. Jetzt geht es
  gedämpft in die Reihenfolge ein: ohne jede Rückendeckung bleibt die Hälfte.
- **Ortszeit am Spot** (1.7.0). Bisher war alles Berliner Zeit — in
  Griechenland und Portugal eine Stunde daneben.
- **„Modelle einig“ meint jetzt auch das Regionalmodell** (1.7.0). Vorher
  bezog sich die Plakette auf drei Reihen, die man gar nicht mehr sah.
- Beide Abfragen nehmen dieselbe Gitterzelle (die nächste, nicht die ähnlich
  hohe an Land), sonst maß der Vergleich zum Teil nur Land gegen Wasser.

## Thermik: aus einer Zahl wird Wetter

- **71 Spots mit Thermikwissen** (1.3.0) statt 4: Name des Windes, Monate,
  Zeitfenster, Richtung, Stärke, Verlässlichkeit — und die Quelle dazu. Wo
  keine Quelle eine Stärke nennt, wird keine angenommen.
- **Die Stärke hängt am Tag** (1.3.0): eingestrahlte Energie seit
  Sonnenaufgang, Tageszeit, und der Gegenwind — der schwach hilft und ab
  7 bis 9 kn alles erstickt.
- **Eigene Liste „Thermikziele“** unter den besten drei, sortiert nach dem
  Potenzial des Tages; **eigenes Stundenraster „Wann die Thermik läuft“**
  (1.5.3), das auch zeigt, wann das Fenster offen wäre und der Tag trotzdem
  tot ist.
- **Die Verlässlichkeit steckt nicht mehr in den Knoten** (1.7.0). 16 kn bei
  70 % Verlässlichkeit gaben 11 kn — eine Zahl, die an keinem Tag auftritt.
  Jetzt sind es 16 kn mal Tagespotenzial, und die 70 % gehen als
  Wahrscheinlichkeit in die Reihenfolge ein, dort, wo sonst das Ensemble
  steht — das die Thermik nämlich nicht sehen kann und sie bisher bestrafte.

## Katalog: prüfen statt nur sammeln

- **Seite „Koordinaten prüfen“** (1.2.0): Nadel ins Wasser ziehen, übernehmen,
  die Ufergeometrie wird sofort neu gerechnet. Seit 1.5.4 stehen dort auch
  alle Spots, deren Koordinate aus einer Liste stammt und die nie jemand
  angesehen hat — nach Entfernung sortiert, die nächsten zuerst.
- **Koordinaten-Check ohne Netz** (1.6.0): `tools/koordinaten_check.py`
  prüft aus dem Zwischenspeicher, ob ein Pin im Gewässer liegt, das sein
  Name sagt. Ergebnis heute: 17 bestätigt, 56 nicht prüfbar (Meer), 13
  Widersprüche, 13 an Land.
- **Die Warnliste nach dem Geometrielauf meldete das Falsche** (1.1.1): 67
  Treffer, davon 39 harmlose Baggerseen, und 25 wirklich falsche Pins fehlten.
  Jetzt entscheidet die gemessene Anlauflänge.
- **Dateiimporte gelten als unbestätigt** (1.7.0). Hundert Wegpunkte aus einer
  fremden GPX hat niemand angesehen — sie standen trotzdem nie auf der
  Prüfseite. Was du selbst eintippst, gilt weiter als angesehen.
- **Was du korrigierst, bleibt korrigiert** (1.7.0). Bisher rechneten
  Schutzgebiete, Modellzuordnung und Fahrzeit nach dem Verschieben einer Nadel
  mit dem alten Punkt weiter. Jeder Zwischenspeicher weiß jetzt, für welche
  Koordinate er gilt.
- Zwei doppelte Pins entfernt, ihre Notizen bei den benannten Spots.

## Report und Oberfläche

- Klick auf einen Spot zeigt die Einzelheiten; der Name im Popup führt zu
  Windy (1.2.2).
- **Warnungen nur noch dort, wo sie gelten** (1.7.0). Ein Spot ohne
  Regionsangabe bekam alle Warnungen seines Landes: „Gewitter · Bornholm“ an
  dreizehn Nordseespots. Jetzt steht so etwas einmal im Kopf des Reports.
- **Wellenhöhe aus dem Wellenmodell** (1.7.0), wo es antwortet (Meer, mit
  „Wassertemperatur und Tiden“). Vorher galt überall die Faustformel.
- Eine einzelne Stunde knapp unter der Schwelle zerschneidet die Session
  nicht mehr (1.7.0). Neue Option `offshore_veto_km`: ablandig mit viel Wasser
  in Lee kann ein Ausschluss sein statt nur ein Hinweis (Standard: aus).
- Der Thermikring auf der Karte schluckt keine Klicks mehr (1.5.3), die
  Karte der Prüfseite bleibt beim Scrollen stehen (1.5.5).
- **Die Spots auf der Karte sind anklickbar** (1.9.0). Der Radiuskreis um
  den Startpunkt lag als Fläche über allen Punkten im Suchradius und fing
  jeden Klick ab — seit 1.0.0, hinter dem Thermikring-Fehler versteckt. Jetzt
  liegt er als Dekoration unter den Punkten.
- **Die Oberfläche sagt, wenn sie alt ist** (1.13.0): nach einem Update
  ein Balken „Wingscout läuft noch mit …, auf der Platte liegt …“; der
  Rückblick sagt, wenn sein Ergebnis von einer früheren Suche oder Version
  stammt.
- **Alle Sessions sortierbar** (1.12.0): die Tabelle nach Dauer, Wind,
  Lage (sideshore … ablandig), Wasser (flach … Welle) oder Score ordnen —
  Spalte anklicken.
- **Dein Kommentar zu jedem Spot** (1.11.0): überall, wo ein Spot steht —
  Katalog, Ziel im Report, Karten-Popup, Prüfseite, Rückblick, neuer Spot —
  lässt sich ein eigener Kommentar schreiben, der in `spots.yaml` landet.
- **Zwei neue Reiter** (1.9.0). **Katalog**: alle Spots mit Suche, Filtern
  und Karte, unten die Frage „Schon drin?" — Koordinate eintippen, die Seite
  sagt, ob dort schon ein Spot steht — und seit 1.10.0 die Pflege: neu
  eintragen, umbenennen, verschieben, löschen, ohne die Datei anzufassen.
  **Rückblick**: die zehn besten Ziele der letzten Suche gegen die Messung
  der nächsten Wetterstation über die letzten Tage, Stunde für Stunde — die
  Frage „kann ich dem trauen?" für den Report von eben; seit 1.10.0 bis zur
  aktuellen Stunde und mit Frankreich, seit 1.13.0 mit wählbarem Umkreis
  (30 km, bis 100), über Grenzen hinweg, mit Rijkswaterstaat (Wind auf dem
  Wasser, nahe Echtzeit — nach der Beschreibung gebaut, die Sonde muss es
  bestätigen) und mit Windguru-Stationen, für die man das Passwort hat; die
  nächste Station, die Werte hat, kommt dran, und die Seite sagt, wenn ihr
  Ergebnis überholt ist — mit den bekannten Grenzen (Vorhersage mit
  kürzestem Vorlauf; Land gegen Wasser; wie nah die Messung an „jetzt"
  heranreicht, hängt am Dienst).
- **Shorebreak** (1.9.0) steht als Plakette und Notiz an 34 Meeresspots —
  rein als Information, eine Einschätzung nach Lage, unbelegt, zum Prüfen.
- **Instagram** (1.9.0): zwei Links je Spot (Ortsseite oder Hashtag, und
  eine Google-Suche auf instagram.com mit „wingfoil") und für 100 Spots eine
  Momentaufnahme gefundener Ortsseiten und Treffer — Suchtreffer mit Datum,
  kein Beleg. Ob dort gewingt wird, zeigt der Klick; automatisch prüfen lässt
  Instagram das nicht zu.
- **Landeskürzel korrigiert** (1.9.0), wo die Google-Liste geraten hatte:
  Ancona ist Italien, Orikum und Saranda sind Albanien, der Chiemsee ist
  Bayern. Das Kürzel entscheidet über Zeitzone und Regionalmodell.

## Der Prüfstand (1.8.0)

Die Tests prüfen ohne Netz, ob der Code tut, was er soll. Der **Prüfstand**
prüft mit Netz, ob das Ganze noch stimmt: sieben Spots mit bekanntem Wind
gegen alle Modelle, ein Punkt auf der Schwäbischen Alb, der als „an Land“
erkannt werden muss, und zehn Spots mit einer Wetterstation in Reichweite,
für die die alte Vorhersage eines festen Monats gegen die **Messung** steht —
je Modell und für Wingscout als Ganzes. Die Zahlen eines guten Laufs werden
als Grundlinie gemerkt; eine spätere Änderung, die schlechter rechnet, fällt
auf. Beim Bau hat er gleich zwei Dinge gefunden: einen Punkt an Land hielt die
Ufergeometrie für offenes Wasser, und `build_geometry.py --force` hatte die
Geometrie aller anderen Spots gelöscht (1.7.0 kam mit sechs statt 275
Einträgen heraus; wiederhergestellt).

## Zu zweit und ohne Überraschungen

- **Zusammenarbeit** (1.1.0): persönliche `config.yaml` wird nicht mehr
  versioniert; ein Prüflauf auf GitHub bei jedem Push; „Auf GitHub
  veröffentlichen“ und „Neuen Stand holen“ als Doppelklick; zwei
  Geometrieläufe vertragen sich beim Zusammenführen.
- **Läuft mit Apples Python** (1.1.0), ohne dass man etwas installiert.
- **Die Oberfläche bleibt nicht mehr hängen** (1.6.1). Ein Tippfehler in
  `spots.yaml` ließ sie bis zum Neustart auf „läuft“ stehen. Jetzt steht die
  Meldung im Protokoll. Prüfseite und Hintergrundlauf schreiben nicht mehr
  gleichzeitig in dieselben Dateien (1.7.0).
- **Sicherheit** (1.6.1, 1.7.0): Kartenskripte nur noch mit Prüfsumme, auch
  beim Nachladen; kaputte Anfragen halten keinen Thread mehr fest; fremde
  Dateien mit Tricks werden abgelehnt; eine kaputte Antwort von Park4Night
  oder vom Ensemble kostet den Abschnitt, nicht den Lauf.
- Der Routing-Fehler nennt seine Ursache (1.4.3): Apples Python 3.9 kommt mit
  dem OSRM-Server nicht zusammen, das ist kein kaputter Server.

## 1.14.0: Modelle im Vergleich, Namen statt Koordinaten

Der Rückblick stellt jetzt jedes Wettermodell einzeln gegen die Messung und
merkt sich über alle Prüfungen, welches wo am besten lag. Rijkswaterstaat
läuft über die neue Schnittstelle (und mischt keine Vorhersage mehr in die
Messung), Dänemark hat mit DMI eigene Stationen, und Météo-France nimmt nur
noch Stationen, die Wind messen. Im Katalog heißt kein Spot mehr „Pin …“:
107 Namen kommen aus OpenStreetMap, 15 Landeskürzel sind korrigiert.

## 1.15.0: Der Rückblick zeigt erst die Messung

Im Diagramm stehen zunächst nur die Messung und die Spanne aller Modelle;
einzelne Modelle, die Wingscout-Bewertung und das bisher beste Modell lassen
sich zuschalten.

## 1.16.0: Das Tagebuch

Ein neuer Reiter hält fest, wie eine Session wirklich war — Spot, Zeit, Wing,
untermotorisiert / passt / übermotorisiert, Wasser, Note — und legt daneben,
was Wingscout, die Modelle und die nächste Messstation für genau diese
Stunden sagten. Aus mehreren Sessions werden Vorschläge für die Windfenster
der Wings und den Windfaktor eines Spots, die du übernimmst oder nicht.
Unter der Haube: CSS und JavaScript der Oberfläche liegen als eigene Dateien
vor, und ein Linter prüft den Code mit.

## Was offen ist

Steht in `TODO.md` (für dich) und am Ende von `REVIEW.md` (zum Bauen). Die
Frage, seit drei Läufen unbeantwortet: Löst ICON-2I die Ora am Gardasee auf?
Das sagt nur ein echter Lauf an einem echten Ora-Tag.
