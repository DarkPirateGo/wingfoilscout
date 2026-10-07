# Changelog

Dates as DD.MM.YYYY. The version number lives in `wingscout/__init__.py` and
appears on every page of the interface (at the right of the tab bar, in the
footer on phones) and in the header and footer of every report — so you can
tell later which version a report was made with. From 2.1.0 on this file is
written in English; the entries up to 2.0.0 below are in German, as they were
written at the time.

## 2.4.0 — 07.10.2026

### Favourites

- **Your favourite spots, straight in the first form** (requested on
  6 October): below “Starting when?” there is a field **Favourites**. Type
  part of a spot's name and pick it from the list that opens — accents don't
  matter (“etang” finds “Étang de Leucate”), arrow keys and Enter work —; the
  spot lands in your list as a tag whose × takes it out again. Up to ten, in
  the order you add them. The list of matches is the logbook's own, not a
  `<datalist>` (iOS Safari lays that over the field); Enter in the field
  never starts the search.
- **“Show favourites first”** appears once the list has an entry (on to begin
  with). With it, every search also computes the favourites — **even outside
  the radius and despite the filters** (season, water types, seagrass,
  dogs …) — and the report begins with them: **Favourites → the best three →
  map**. The best three, the map and the hour grid stay the normal search;
  favourites outside it appear only in their own section and push nothing
  out. Favourites outside the search get the ensemble probability and
  overnight spots like the leading destinations; they are routed and
  computed as copies, so “Not considered” and the map show them as the
  search saw them. Only countries of the search bring an unassigned official
  warning into the report header. If nothing is left in the search, only the
  favourites are computed (and the log says so).
- **Each favourite gets the card of a destination**, with a ★ instead of the
  rank and a badge: “Rank n” when it is also among the destinations of the
  search, or “outside the search” with the reason as a tooltip (repeated in
  the opened card). A favourite without a session gets a flat card that says
  why — no forecast; sessions, but not N days in a row; no daylight hour; at
  most X kn, below your quiver; or, where there would be wind, the reason
  that rules those hours out, in the words of the hour grid — plus the links
  to Windy, the route and the map. Among the best three and the further
  destinations a favourite carries a ★ before its name; “What was searched”
  says how many favourites there were.
- **Stored with every change**, one request at a time, the newest state
  last (two quick clicks could otherwise arrive in the wrong order), through
  `POST /favoriten`, in
  `favoriten.json` in the Wingfoilscout folder — personal like the logbook:
  in `.gitignore` and `tools/persoenliche_daten.py`, 0600 like `config.yaml`,
  only IDs that are in the catalogue (same rule for IDs as the catalogue,
  `spots.ID_MUSTER`), at most ten (`SECURITY.md`, addendum of
  7 October). “Save as default” leaves the favourites out, like the starting
  point and the start time.
- **Command line:** `--favoriten` uses the list from the interface,
  `--favoriten a,b` the given spot IDs; unknown IDs are named in the log and
  skipped.
- New: `wingscout/favoriten.py`, `wingscout/web/favoriten.js`,
  `tests/test_favoriten.py` (40 tests: the list, the search and what it must
  leave alone, the section — in all four languages, a search computed in
  German equals character for character the report of a search in that
  language —, the interface and its endpoint, the script in Chromium, and the
  Windows line endings below). An independent review of the change found
  three medium issues (overnight spots added to search destinations, a
  favourite's routing changing the “Not considered” row, tests failing in
  winter) and a handful of small ones; all fixed before release and pinned
  down by tests.
  The front of the search page now holds the favourites too;
  `test_vordergrund_bleibt_schmal` allows the field, the hidden list and the
  switch, with the reason written into the test.
- `docs/`: the search and destinations screenshots and the example report
  show a favourite.

### The radius is a driving distance — and the report says so

- **Asked on 7 October:** “I only want spots within the driving distance I
  entered — a spot within 500 km is no use if the drive is 700 km”, after
  seeing two different distances for one spot. The search already worked that
  way: the prefilter estimates (straight line × detour factor, with a 35 %
  margin), OSRM then routes every remaining spot, and only spots whose routed
  driving distance is within the radius (and whose drive is within “max.
  drive”) stay. Only where OSRM gives no route does the estimate decide.
- **What showed two numbers:** “Not considered” listed the straight-line
  distance in its column and the road distance in the reason beside it
  (“682 km” next to “1026 km — outside the 1000 km radius”). The column now
  shows the driving distance — routed, or with “≈” and a tooltip where only
  estimated — and the list is sorted by it; its subtitle no longer says
  “within the radius”.
- **Said where it matters:** “What was searched” reads “Radius 1000 km by
  road”; the radius field in the form has a “?” explaining it; the dashed
  circle on the map is described as a straight-line orientation and is drawn
  with the detour factor from the configuration instead of a fixed 1.22; the
  Catalogue's distance column is headed “km (straight line)” with “from home”
  in its tooltip.
- **If OSRM gives no route** for some spots of the search (or routing is
  switched off), a note at the top of the report says for how many the
  driving distance is only estimated and that the real distance can be
  longer than the radius.
- `tests/test_report_cli.py` (class `Fahrstrecke`, 4 tests).

### Smaller changes

- **The reason a spot is left out names the radius you chose.** The
  prefilter measures with a 35 % margin before routing, and its sentence named
  the enlarged radius — “outside the 338 km radius” when 250 km was chosen.
  Now it measures with the margin and names the limit itself
  (`spots.entfernungsgrund`), in “Not considered” as well. For a favourite
  outside the search the reason uses the routed kilometres.
- **At night the hour grid says “outside daylight hours” first**, even when
  the water is also below your limit: night is now checked before the water
  temperature. Sessions and scores don't change — both block the hour.
- Every blocked hour also carries the kind of block (`veto_art`), for the
  favourites' “why not”.
- The list of matches under a field is shared by the logbook and the
  favourites (`.spotliste` in `basis.css`); arrow up with nothing selected
  now picks the last match, not the second to last (logbook too).

### Windows

- **No more double line breaks in the files Wingfoilscout writes.**
  `config.yaml` on the first start and everything written through
  `spotedit.schreibe_atomar` — the report, the catalogue, the logbook,
  `favoriten.json` and more — went through `os.open` without `O_BINARY`. On
  Windows that gives a text-mode descriptor, and the C library turned every
  line ending Python had already turned into CR LF into one more (found while
  answering what a Windows user would have to try, 6 October). Now binary
  and with `newline="\n"`. Simulated in the tests; **not tested on Windows
  itself**.
- **`wingfoilscout.bat` tries Python instead of only looking for it:**
  `python` can be the Microsoft Store placeholder, which only points to the
  Store — then the PyYAML install was the first thing to fail. It tries
  `python`, then the `py` launcher from python.org, asks for 3.9 or newer
  like the Mac start files, and says so in all four languages. **Not tested
  on Windows either.**

### Tests

- 901 tests (2.3.0: 856).

## 2.3.0 — 04.10.2026

### Destinations follows the language switcher

- **Switching the language now changes the Destinations tab too, without a
  new search.** Until 2.1.0 the report was written once, in the language that
  applied when the search started; after switching, every other page changed
  and Destinations stayed in the old language until the next search
  (reported on 4 October). Now every search that writes the report the
  interface shows (`report.html`) also stores it in all four languages in
  `cache/report/`, with an `index.json` of checksums; Destinations serves the
  version for the language of the page. If the checksums don't match — a
  report from an older version, a file replaced by hand —, it shows
  `report.html` as it is. A report from before 2.3.0 exists in one language
  only until the next search.
- **`report.html` itself** — the file you can AirDrop to the phone — stays in
  the language the search ran in.
- **Computed once, written four times:** texts that come out of the
  computation (an hour's veto, a session's notes, why a spot was left out,
  compass points, the kind of an overnight spot, the tide window) are created
  with `TD()` instead of `T()` and carry their recipe, so each language
  version sets them in its own language. Session directions are sorted in the
  language of the report, as a search in that language would sort them
  ("O" is "E" in English). The demo alert's event is stored as its German
  source text and translated in the report, like the events from the feed.
- `tests/test_report_sprachen.py`: a demo search computed in German and
  written in English, French and Spanish equals, character for character, the
  report a search in that language writes itself; the tab serves the version
  for the browser's language and for the switcher's; checksum, tampering and
  aborted writes fall back to `report.html`.

### Start time

- **“Starting when?”** sits below “Starting from?”: a date and time from which
  the search counts. Left empty, the search starts now as before. The days
  of the preset count from that day; the hours before the start appear in the
  hour grid as “before the chosen start”, like past hours. The hour grid,
  the map and the tide days show only the period searched; the season of the
  spots is judged by the months of that period.
- **16 days at most:** the forecasts reach 16 days from today, the field says
  how far. If start plus days go beyond, the search shortens the period and
  says so in the log; a start after the last forecast day is refused with a
  sentence. The sources are asked for the days from today to the end of the
  period.
- The time is the computer's local time; for each spot it is converted to the
  spot's local time, like "now". **“Now”** clears the field. Like the starting
  point, the start time is not stored by “Save as default”.
- Command line: `--ab "2026-10-10 09:00"` (also `10.10.2026 09:00`, or just
  the date). `cache/letzter_lauf.json` records it as `ab`.
- `wingscout/zeitraum.py` holds the rules; `tests/test_zeitraum.py` (24
  tests): reading, period and limit, hours in `score_hours`, command line,
  the form, `/run` and `/save`.

### The best three first

- **The report opens with the best three destinations**, directly below
  “What was searched”; the map follows them. Until 2.1 the map came first —
  on a phone collapsed, on a computer a whole screen — and the answer to
  “where is it best?” only below it (requested on 4 October).
  `tests/test_report_cli.py` checks the new order.

### Installation on a fresh Mac

- **Both ways to install failed on a Mac that had never had Apple's
  developer tools** (reported on 4 October). The ZIP's double-click file was
  stopped by macOS — since macOS 15 not even right-click → Open gets past the
  warning, only System Settings → Privacy & Security → “Open Anyway” —, and on the
  Terminal way `git` and `python3` only asked to install Apple's command line
  tools, so every command after them failed. The guide even said there was
  nothing to install.
- **The guide now leads with the Terminal way:** `xcode-select --install`
  once, then one line that fetches Wingfoilscout with `git` and starts it
  (`cd ~ && git clone … && cd wingfoilscout && bash "Wingfoilscout
  starten.command"`), each part only if the one before worked. What `git`
  fetches doesn't come through the browser, so macOS doesn't stop the
  double-click files later, and “Neuen Stand holen” updates.
- **The ZIP way** is described step by step: “Open Anyway”, the question
  about the Downloads folder, the command line tools — and that each
  double-click file needs the confirmation once. In the README in all four
  languages and on the website.

### Licence: PolyForm Noncommercial 1.0.0

- **Wingfoilscout is now under the PolyForm Noncommercial License 1.0.0**
  instead of MIT: free to use, change and pass on for any noncommercial
  purpose — personal use, hobby, study and research, and use by charitable,
  educational, public research, public-safety or health, environmental and
  government organisations. Commercial use needs a separate licence from
  DARK. `LICENSE` holds the exact text with the line
  `Required Notice: Copyright 2026 DARK (https://github.com/DarkPirateGo)` on
  top. By the OSI definition this is no longer an open-source licence; the
  website and the documentation say “free for noncommercial use” instead.
- Versions up to 2.1.0 were published under MIT, and copies of them keep
  that licence. `geometry.json` stays under the ODbL of OpenStreetMap.
- **A fresh repository:** so that GitHub no longer hands out the MIT
  versions, the repository was deleted and created again; this version is
  its first commit. Clones made before no longer fit, and “Neuen Stand
  holen” can't bridge the two histories: rename the old folder, clone afresh
  and copy your own files across (`DEVELOPMENT.md`, “Pushing to GitHub”).
  The releases of 2.0.0 and 2.1.0 went with the old repository; their
  content is in this file.

### Suggest a spot for everyone

- **A form on GitHub** (`.github/ISSUE_TEMPLATE/spot.yml`) for a new spot
  or a correction, without Git: name, coordinate, kind of water, good wind
  directions, notes, the source (required) and two required confirmations —
  the licence, and that it is your own knowledge or a source that may be
  passed on. Every suggestion is checked by hand and goes into the catalogue
  of the next version.
- **In the app:** “Suggest it for everyone” in the **Add spots** panel and
  below “Add a new spot” in the Catalogue opens the form — in the Catalogue
  filled in with what was entered above it (name, coordinate, note).
  “Suggest a correction” next to every spot does the same with that spot's
  name and coordinate. These are links: nothing is sent until the form is
  submitted on GitHub (free account), and the suggestion is public.
- `CONTRIBUTING.md`: “Suggesting a spot — no programming needed”, “Taking in
  a suggestion (maintainers)”, “Licence of contributions”; the pull request
  template asks for the licence agreement, too.
- `tests/test_spot_vorschlag.py` (11 tests): the form as GitHub requires it,
  the field names the app fills in, the address built in Python and in
  JavaScript, the links on both pages.

### Documentation

- README in all four languages: installation (above), “Starting when?” (new
  section), the language paragraph, the order of the report, `--ab`, the
  licence and “Suggest a spot for everyone”. `DEVELOPMENT.md`: texts in data
  (`TD()`), the language versions of the report, `zeitraum.py`, the fresh
  repository and the settings to set again, spot suggestions. `SECURITY.md`:
  addendum on the fresh repository. `CONTRIBUTING.md`: suggesting spots,
  taking them in, the licence of contributions. The website: installation,
  start time, licence and a link to suggest a spot; its screenshots of the
  search and of the destinations show 2.3.0, and the example report
  (`docs/demo.html`) is regenerated.
- 856 tests.

## 2.1.0 — 04.10.2026

### Wingscout is now Wingfoilscout

- **New name** wherever you see it: interface, report, home-screen web app,
  start files ("Wingfoilscout starten", "Wingfoilscout fürs iPhone starten",
  `wingfoilscout.bat`), terminal messages, documentation. The repository is
  `DarkPirateGo/wingfoilscout`; GitHub redirects the old links. The Python
  package stays `wingscout` — `python3 -m wingscout.webui` and your own
  folder keep working. Older entries here, `REVIEW.md` and
  `WAS-SICH-GEAENDERT-HAT.md` keep the old name.

### Four languages

- **Interface, report, progress and error messages in English, German, French
  and Spanish.** A switcher sits next to the logo and version number (on
  phones in the page footer); the choice is stored in `sprache.txt` (personal,
  not versioned) and applies to every page and the next report. Until you
  choose, the browser's language decides (English for any other language).
  On the command line: `--sprache de|en|fr|es`, otherwise the saved choice,
  the system language (`LANG`, macOS language settings) or English.
- **The start files** ("Wingfoilscout starten" & co.) print their terminal
  lines in the same four languages (`tools/sprache.sh`).
- **Numbers, dates and times** in the form of the language: "Sat 3 Oct",
  "20 Sep 2026, 19:09", "08:00–19:00", decimal point in English. German
  output is unchanged.
- **How it works:** the German source texts stay in the code (`T()`, `TN()`,
  `N_()` in Python, `t()`, `N_()` in JavaScript); the translations are in
  `wingscout/lang/en.json`, `fr.json`, `es.json` (1,079 texts each);
  `tools/i18n_texte.py` lists missing ones; `tests/test_i18n.py` checks that
  every language knows every text with the same placeholders and markup, and
  that every page and the report render in all four languages.
  `CONTRIBUTING.md` explains how to improve a translation.
- **Not translated:** spot notes and other catalogue data in `spots.yaml`
  and some place and area names from OpenStreetMap stay in their original
  language (mostly German); so do the maintainer tools (`tools/check.sh`,
  benchmark, geometry build).

### Help in the app

- **A “?” button on every page** (at the top right next to the language
  switcher; on phones next to “Quit”) opens the help: the complete guide
  (the README with a table of contents) and the illustrated page “How
  Wingfoilscout calculates” — both in English, German, French and Spanish,
  in the language you chose. To keep the tab bar in one row in all four
  languages, the version number now sits small under the logo.
- The guide is rendered by a small built-in Markdown renderer
  (`wingscout/hilfe.py`, no new dependency); links to other files of the
  repository open on GitHub. The methodology page is embedded with its
  figures; both are sanitised on the way out (no scripts, no foreign links).
- Translations: `README.de.md`, `README.fr.md`, `README.es.md` (also readable
  on GitHub) and `wingscout/hilfe/bewertung.de.html`, `.fr.html`, `.es.html`.
  Drift tests (`tests/test_hilfe.py`) notice when they fall behind the English
  originals: same headings, code blocks, links and numbers; for the
  methodology page the same tag structure.

### Documentation in English

- `README.md`, `SCORING.md` (was `BEWERTUNG.md`), `DEVELOPMENT.md` (was
  `ENTWICKLUNG.md`), `CONTRIBUTING.md` (was `MITARBEIT.md`), `SECURITY.md`
  (was `SICHERHEIT.md`, now with "Reporting a vulnerability"), `BENCHMARK.md`
  (was `PRUEFSTAND.md`), `TODO.md`, the methodology page `docs/bewertung.html`
  and the comments in `config.example.yaml`, `spots.yaml` and `.gitignore`.
  `REVIEW.md` and `WAS-SICH-GEAENDERT-HAT.md` stay as German historical
  documents.
- **Corrections found on the way:** the drive-time rule reaches zero only at
  +125 % over the allowed time (the figure said +25 %); with the default
  ensemble weight an hour in which the models disagree completely keeps 82 %
  of its score, not 70 % (agreement never drops below 0.4); `weight: 0.0`
  restores the behaviour up to 1.4.3 (the config comment said 1.4.2).
- README: the no-terminal route (ZIP from the release page, the two macOS
  prompts), screenshots, and a new section "What leaves your computer".

### Website, screenshots and videos

- **Landing page** at https://darkpiratego.github.io/wingfoilscout/ (GitHub
  Pages from `docs/`; switch it on once in the repository settings): in
  English, with screenshots of the English interface (light and dark), a
  30-second intro video and a one-minute video of the app on the computer,
  how to start, and what to know. The example report `docs/demo.html` is an
  English demo run from Hamburg with made-up weather data, marked as such.
  The pages load nothing from other servers, not even fonts; only the example
  report fetches the map like every report.
- **Fresh Mac:** without the command line tools `/usr/bin/python3` is only a
  placeholder. The start scripts now say that macOS wants to install the
  tools — and with them Python — and trigger that, instead of "Python is too
  old". Not yet tried on a fresh Mac.

### Security review of 4 October 2026

Four independent reviews of the HTTP surface, the output and translations,
the data sources and parsers, and the scripts, publishing and repository —
then a fifth review of the fixes. Nothing critical or high; all findings are
fixed and pinned down by tests (`SECURITY.md` has the full list). In short:

- Pages can no longer be loaded cross-site by other websites (a cheap 403);
  LAN mode limits connections and time per connection from other devices;
  error messages show no absolute paths.
- Translations can't break pages or inject markup; all data embedded in
  scripts is escaped; attributes are escaped.
- Imports and catalogue: no more catastrophic regex backtracking, YAML
  aliases rejected, invalid characters cleaned or reported clearly.
- Data services: garbage values, decompression bombs, slow downloads,
  redirects and unexpected URLs are handled; a broken spot is skipped instead
  of stopping the search; broken caches are fetched again.
- Privacy: the start point goes to the routing server rounded to ~1 km; files
  with personal data are only readable for you (umask 077, `config.yaml`
  keeps 0600); example values now match the website demo (Hamburg).
- Publishing (`tools/veroeffentlichen.sh`): new files are added only after
  you type `ja`; personal files and any coordinate near your home are
  refused; every commit must carry the GitHub noreply address; only the
  branch and the new tag are pushed. `.gitignore` is broader; the CI token is
  read-only.

### Smaller things

- The tab bar keeps logo, version, language switcher and "Quit" in one row;
  when space runs out they move to the next row together (before, "Quit"
  ended up alone on the left).
- The start field shows the home name first ("Hamburg – or paste a
  coordinate/Maps link"); on phones the useful part was cut off.
- Report: "Radius 500 km" instead of "500.0 km"; the timestamp in the header
  no longer breaks between date and time; the swipe hint above the session
  table named a drive-time column that doesn't exist.
- "1 Bewertungen" → "1 Bewertung" for overnight spots with one review; the
  check hint on the search page no longer lowercases "Ufergeometrie".
- Coordinates written as "N 51°45.750 E 3°51.233" are read correctly.
- In the collapsed line of a destination each part stays together on
  phones; after "Fetch 1 km · waves 0.17 m" there is a separator.
- What was prepared as 2.0.1 is included: the repository is public, the
  check from `SECURITY.md` held (the old commit returns 404), and
  `DEVELOPMENT.md` records the GitHub settings (protected `main`, push
  protection, private vulnerability reporting, Dependabot alerts, read-only
  workflow token). README: 71 thermal spots, not 73.
- 800 tests.

## 2.0.0 — 03.10.2026

### Erstes öffentliches Release

Keine Änderung an der Funktion gegenüber 1.20.3 — die Nummer markiert den
Schritt vom privaten zum öffentlichen Repository: Lizenz MIT, Persönliches
aus Stand und Historie entfernt (1.19.2), das Repository auf GitHub gelöscht
und neu angelegt, damit keine lose Kopie der alten Historie übrig bleibt
(`SICHERHEIT.md`, Nachtrag 03.10.). Alles davor war Entwicklung unter sich;
ab hier gilt: Wer klont, bekommt das, was in der README steht.

- `SICHERHEIT.md`: warum das Repository neu angelegt wurde, was vorher
  geprüft war und welche Gegenprobe vor dem Umschalten gilt.
- `ENTWICKLUNG.md`, „Auf GitHub schieben“: beschreibt das öffentliche
  Repository statt des privaten — was nicht hineingehört, hält `.gitignore`
  heraus und ein Test fest; dazu, was nach einer Neuanlage mit einem
  Fine-grained token zu tun ist, und warum künftige Commits besser die
  noreply-Adresse von GitHub tragen.
- Die Release-Einträge der Versionen 1.x gibt es auf GitHub nicht mehr — sie
  sind mit dem alten Repository verschwunden. Die Tags sind wieder da, der
  Inhalt jeder Version steht unten.

## 1.20.3 — 30.09.2026

- **`BEWERTUNG.html` — derselbe Weg mit Abbildungen.** Die Seite „Wie
  Wingscout rechnet“ (16.09., damals Stand 1.5.2) auf den heutigen Stand
  gebracht und ins Repository gelegt: Ablaufbild mit Marine-Daten und
  Windfaktor, sieben Vetos statt sechs (Tidenfenster und ablandig mit Wasser
  in Lee kamen dazu), Regionalmodell nach Landeskürzel (1.8.1), angenommener
  Thermikwind ohne Verlässlichkeit (die geht seit 1.6.2 in die Reihenfolge),
  ein eigener Abschnitt zur Tide, die Überbrückung einer knappen Stunde, der
  Fahrtfaktor als Formel, Plan B, 71 statt 73 Thermikspots; der Tagesgang der
  Thermik mit richtigen Achsen. Die Datei lädt nichts nach — keine Skripte,
  Schriften aus dem System —, auf GitHub zeigt sie ihren Quelltext,
  heruntergeladen ist sie die Seite.
- Richtiggestellt in `BEWERTUNG.md`: der Vorfilter prüft Radius und Fahrzeit
  mit 35 Prozent Zuschlag, erst nach dem Routing gelten sie genau.
- Ein Test hält `BEWERTUNG.html` mit `config.example.yaml` im Gleichschritt
  (Gewichte, Schwellen, Fahrt- und Plan-B-Grenzen) und prüft, dass die Seite
  keine Skripte und nichts von außen lädt (`tests/test_catalog.py`).
  512 Tests.

## 1.20.2 — 30.09.2026

- **`BEWERTUNG.md` — wie Wingscout entscheidet.** Der Entscheidungsweg von
  278 Spots zu „die besten drei“ stand bisher nur im Code und verteilt über
  sechs README-Kapitel. Jetzt eine Seite in der Reihenfolge, in der das
  Programm entscheidet: Vorfilter je Spot (zehn Gründe, die auch unter
  „Nicht berücksichtigt“ stehen), Wetter je Spot (Modelle, Regionalmodell,
  Windfaktor, Thermikannahme, Marine), je Stunde die sieben Vetos und die
  Note aus fünf Teilen mit jeder Zahl dahinter, Sessions, Verlässlichkeit,
  Reihenfolge der Ziele, und was nur Information ist. Jede Zahl mit ihrem
  Schlüssel in `config.yaml`; die README verweist darauf. Jede Aussage gegen
  den Code gelesen (`score.py`, `spots.py`, `geometry.py`, `thermik.py`,
  `cli.py`, `sources/ensemble.py`) — darunter, was bisher nirgends stand:
  Radius und Fahrzeit werden erst geschätzt und nach dem Routing noch einmal
  geprüft; der Fahrtfaktor fällt mit 0,8 × Überschreitung ÷ erlaubte Zeit;
  `p_ride` zählt Rechnungen mit mindestens zwei fahrbaren Stunden.
- Ein Test hält die Seite mit der Konfiguration im Gleichschritt: die fünf
  Gewichte und die genannten Schwellen müssen in `config.example.yaml`
  stehen, wie sie dort stehen (`tests/test_catalog.py`). 511 Tests.

## 1.20.1 — 30.09.2026

- **Rückblick und Tagebuch finden ihren Lauf wieder.** Dieselbe Lücke wie
  bei der Suchseite bis 1.18.2, nur zwei Reiter weiter: Rückblick starten,
  auf einen anderen Reiter, zurück — kein Spinner, „Prüfen“ frei, das alte
  Ergebnis stand da, als wäre nichts passiert, und das neue kam erst nach
  einem Neuladen (gefunden am 30.09.). Der Lauf selbst lief immer weiter
  (der Punkt am Reiter zeigte es seit 1.18.3), nur die Seite wusste beim
  Wiederkommen nichts davon. Jetzt fragen Rückblick- und Tagebuchseite beim
  Laden nach dem Stand: läuft ihr Lauf, zeigen sie Spinner, Protokoll und
  den gesperrten Knopf und pollen weiter; läuft etwas anderes (eine Suche,
  ein Import), warten sie mit „Wartet …“ statt beim Klick mit 409 abgewiesen
  zu werden; ist ihr Lauf fertig, steht das Ergebnis mit Uhrzeit da, wie auf
  der Suchseite. Nachgestellt im Browser gegen einen Server mit 8-Sekunden-
  Läufen: starten, wechseln, zurück (Schritt 5 von 8), fertig mit Uhrzeit,
  Neuladen zeigt es weiter; Tagebuchseite mitten in einem Lauf geöffnet;
  Rückblickseite während eines Tagebuchlaufs („Wartet …“).
- Ein Test (`tests/test_webui.py`). 510 Tests.

## 1.20.0 — 29.09.2026

### Der Report in zwei Stufen: Einfach und Ausführlich

Rückmeldung eines Mitlesers zur Ergebnisdarstellung: nichts fehle, aber sie
sei überfrachtet — besser gestaffelt, eine einfache Ansicht mit dem Nötigsten
und Aufklappen für die Einzelheiten. Er hatte recht: der Demo-Report war am
Rechner 17 000 px hoch, jedes Ziel eine Karte mit acht Zonen, und die Antwort
auf „wo lohnt es sich?“ stand irgendwo dazwischen.

- **Jedes Ziel ist eine Klappe.** Zugeklappt zwei Zeilen: Rang, Name, Fahrt
  und Wasserstunden rechts, die Plaketten, die über Fahren oder Nichtfahren
  entscheiden (Fahrt lohnt / grenzwertig, amtliche Warnungen als Zahl,
  Thermik, Tide, Zahl der Hinweise) — und darunter die beste Session in
  einer Zeile: wann, Wind, Wing, Lage, „+1 weitere Session“. Aufgeklappt
  alles, was bis 1.19.2 immer dastand: Fahrzeitregel und Plan B, Kommentar,
  Warnungen und Schutzgebiete im Wortlaut, Tide, jede Session mit Modellen,
  Anlauf und Welle, Stellplätze, Links, Katalognotiz.
- **Die Abschnitte sind Klappen:** Thermikziele, Wann die Thermik läuft,
  Stundenraster, Weitere Ziele, Alle Sessions, Nicht berücksichtigt, Wie das
  Wetter bewertet wird — zu, mit Überschrift und einem Satz dazu („50 Spots,
  Stunde für Stunde — Güte oder Knoten“). Die Karte und „Wonach gesucht
  wurde“ bleiben, wie sie waren.
- **Ansicht Einfach / Ausführlich** oben unter der Überschrift: Ausführlich
  öffnet alle Ziele und Abschnitte (außer „Weitere Ziele“), Einfach schließt
  sie. Die Wahl bleibt im Browser (`localStorage`) und gilt für jeden neuen
  Report; ohne Skript gilt Einfach, jede Klappe geht einzeln (`<details>`,
  kein Skript nötig; `web/ansicht.js` mit der Nonce der Seite).
- Der Demo-Report ist damit am Rechner 2 200 statt 17 000 px hoch, am Handy
  1 900 statt 37 000 — die drei besten Ziele stehen auf dem ersten Bildschirm.
- **Katalognotizen ohne Import-Floskel.** 163 Spots aus dem Takeout-Import
  trugen in `notes` denselben Satz („Aus der eigenen Google-Liste …; die
  Koordinate stammt nicht vom Pin …“, „Gewässerart offen …“) — was `source`,
  `verified` und `water_body` längst sagen. Der Satz stand in jedem Report
  und auf jeder Katalogseite; jetzt steht nur noch die eigene Notiz da, 85
  Spots haben keine mehr. `import/import_takeout.py` schreibt ihn nicht mehr.
- **Behoben: `spotedit.set_text` zerriss umgebrochene Werte.** `notes:` steht
  im Katalog oft über mehrere Zeilen; `set_text` ersetzte nur die Kopfzeile
  und ließ die Fortsetzung als Waisen stehen — die Datei war danach nicht
  mehr lesbar (gefunden beim Kürzen der Notizen; die Oberfläche schreibt
  bisher nur einzeilige Felder, deshalb fiel es nie auf). Jetzt gehört zum
  Feld alles, was tiefer eingerückt folgt — beim Ersetzen wie beim Leeren.
- Fünf neue Tests (`tests/test_report_cli.py` `Gestaffelt`,
  `tests/test_catalog.py`, `tests/test_spotedit.py`). 509 Tests, Python 3.9
  und 3.11, Rechner und 390 px nachgesehen.

## 1.19.2 — 27.09.2026

### Repository für die Veröffentlichung bereinigt

Vor dem Umstellen auf „öffentlich“ wurde der ganze versionierte Stand und die
Git-Historie nach Persönlichem und Geheimnissen durchsucht. Geheimnisse gab es
keine (kein Schlüssel, kein Passwort — Windguru-Passwörter stehen nur in der
persönlichen `config.yaml`, der WLAN-Schlüssel wird beim Start gewürfelt).
Persönliches gab es, und zwar an vier Stellen:

- **Ein Google-Takeout-Export lag im Repository** (`import/takeout-*.csv`,
  261 gespeicherte Orte mit eigenen Notizen — darunter Zuhause und Adressen),
  obwohl `.gitignore` ihn nennt: die Regel kam nach dem ersten Commit, und
  eine Regel entfernt nichts, was schon drin ist. Die Datei bleibt auf dem
  Rechner (der Import braucht sie), verlässt aber das Repository — samt
  Historie, siehe unten.
- **Eine Privatadresse stand im Importskript** (`import/import_takeout.py`
  übersprang zwei Nicht-Spots aus der Liste namentlich, einer davon eine
  Postanschrift) und in `import/jensdee_liste_roh.md`. Jetzt übergeht das
  Skript Adressen und Hallen per Muster; die Zeile im Rohextrakt ist weg.
- **Die persönliche `config.yaml` war in vier frühen Commits versioniert**
  (Name, Gewicht, Startpunkt) — heute nicht mehr, aber in der Historie.
- **Anrede und Name im Katalog:** 163 Notizen sagten „Aus deiner
  Google-Liste“, der Nachtrag hieß „Google-Takeout-Liste von Philipp“, eine
  Notiz sprach von „dein Stausee“. Jetzt neutral („Aus der eigenen
  Google-Liste“, „eigene Google-Takeout-Liste“). Der Startpunkt in
  `config.example.yaml` und im Jens-Dee-Import steht auf zwei Stellen
  (Stadtmitte, ~1 km) statt auf drei.

Was im aktuellen Stand steht, ist damit bereinigt. **Die Historie bereinigt
erst ein Umschreiben** (`git filter-branch`, in Git eingebaut) — das Skript
dafür liegt bei der Übergabe (`Claude outputs/historie-bereinigen.sh`,
durchgespielt an einem Testrepository mit denselben Fällen), die Schritte
stehen in `SICHERHEIT.md` („Nachtrag 27.09.2026“). Bis dahin bleibt das
Repository privat.

- Zwei neue Tests und ein erweiterter (`tests/test_catalog.py`,
  `PersoenlicheKonfiguration`): kein `import/takeout-*.csv`, keine GPX/KML,
  kein Tagebuch im Repository; der Takeout-Filter ist ein Muster und keine
  Adressliste; der Startpunkt der Vorlage ist grob. 504 Tests.
- **Lizenz: MIT** (`LICENSE`, © 2026 DARK) — ohne Lizenzdatei wäre ein
  öffentliches Repository „alle Rechte vorbehalten“; MIT erlaubt Benutzen,
  Ändern und Weitergeben gegen Nennung, ohne Gewähr. Verweis in der README und
  in `pyproject.toml`.
- Dazu aus dem Arbeitsbaum: der README-Abschnitt „Datenquellen, Lizenzen und
  Grenzen“ (Herkunft und Lizenz jeder versionierten Datei, was nur zur
  Laufzeit geholt wird) und die `.gitignore`-Regeln für Rohexporte
  (`import/takeout-*.csv`, GPX, KML, KMZ).
- Nachgetragen: die Überschrift **1.16.1** im Changelog fehlte — die Einträge
  standen unter 1.17.0.

## 1.19.1 — 25.09.2026

### Content-Security-Policy mit Nonce — die zweite Verteidigungslinie

Die erste Verteidigung ist das Escaping; die zweite greift, wenn es einmal
versagt — wie beim Sektorfeld `water` bis 1.18.3 (Review 25.09., S1, zweiter
Teil): fremdes Skript in einer Seite läuft dann trotzdem nicht.

- **Jede Antwort würfelt eine Nonce** (`wingscout/csp.py`; im Server je
  Anfrage im Thread, `webui.nonce()`), jeder `<script>`-Block der Seite trägt
  sie, die Kopfzeile `Content-Security-Policy` nennt sie — nur so laufen
  Skripte. Ereignisattribute (`onerror=`) und `javascript:`-Adressen sind
  damit tot; fremde Skripte gibt es nur eines, Leaflet von cdnjs, mit
  Prüfsumme wie bisher. Erlaubt ist genau, was die Seiten brauchen: Styles
  inline, Leaflet von cdnjs, Kacheln von OpenStreetMap, Marker-Bilder von
  cdnjs, Anfragen und Rahmen nur vom eigenen Server; kein `object`, keine
  fremde `base`, kein Formular nach draußen.
- **Die Report-Datei** bekommt dieselbe Richtlinie als `<meta http-equiv>`
  mit einer Nonce je Erzeugung: ein Katalogtext, der doch einmal roh in die
  Seite käme, kennt sie nicht — auch als `file://` auf dem iPhone. Liefert
  der Server die Datei aus, nimmt er die Nonce aus ihrem Kopf, damit
  Kopfzeile und Datei dasselbe sagen; ein Report von vor 1.19.1 hat keine
  und bekommt keine Richtlinie (sonst liefe darin nichts).
- Nachgestellt in Chromium: alle fünf Seiten, der Report über den Server und
  als Datei (Rechner und 390 px) ohne einen einzigen Verstoß — Karte,
  Tidenlage, Rastertipp, Kommentar-Editor, Beenden laufen; ein in die
  Report-Datei geschriebenes `<img onerror>` und ein `<script>` werden vom
  Browser verweigert („Refused to execute inline script“).
- Sieben neue Tests (`tests/test_security.py`, `Richtlinie` und
  `RichtlinieLive`): jede Seite trägt die Nonce an jedem Skript, keine
  Ereignisattribute, Richtlinie ohne `unsafe-inline` für Skripte, Kopfzeile
  und Seite nennen dieselbe Nonce, der Report seine eigene, ein alter keine.

### Versionsnummer und Logo des Erstellers auf jeder Seite

Bis 1.19.0 stand die Nummer nur klein in der Unterzeile der Suchseite und im
Fuß des Reports — auf Katalog, Rückblick und Tagebuch gar nicht; auf die
Frage „welche Version läuft hier?“ gab die Oberfläche keine Antwort.

- **Am Rechner rechts in der Reiterleiste**, vor „Beenden“: das Logo des
  Erstellers (`wingscout/web/logo.png`, 26 px hoch) und `v1.19.1` in der
  gedämpften Farbe, auf jeder Seite — auch im Report über den Server. Der
  Tooltip nennt beides.
- **Am Handy im Fuß jeder Seite**, mittig über der Leiste: dieselbe Marke
  (`seitenende()` schließt jede Seite; welche der beiden Stellen zu sehen
  ist, entscheidet das CSS). In der Leiste unten wäre kein Platz gewesen.
- **Im Report unter dem Fuß** als eigene Zeile „Logo · Wingscout 1.19.1“ —
  das Bild eingebettet (Data-URI, 44 kB), weil die Datei per AirDrop ohne
  Server geöffnet wird. Die Unterzeile der Suchseite verliert ihre Nummer:
  sie stünde sonst zweimal auf einem Bildschirm.
- Die Nummer ist die des laufenden Prozesses; liegt auf der Platte schon
  eine neuere, sagt das weiterhin der Neustart-Hinweis unter der Leiste.
- Das Bild kommt vom eigenen Server (`/logo.png`, `img-src 'self'` der
  Richtlinie); die Liste der ausgelieferten Bilddateien bleibt fest
  (`BILD_DATEIEN`) — `web/` ist kein freigegebenes Verzeichnis, `basis.css`
  oder `logo.PNG` sind 404. Nachgesehen in Chromium ohne Verstoß gegen die
  Richtlinie, am Rechner und bei 390 px.
- Zwölf neue Tests (`tests/test_marke.py`). 502 Tests.

## 1.19.0 — 25.09.2026

### Review vom 25.09. umgesetzt: Sicherheit, Import, Bedienung

Alle Befunde aus `REVIEW.md` („Review 25.09.2026“) in einer Version; die
Nummern unten sind die des Reviews. 484 Tests (57 neue, die meisten in
`tests/test_review_2026_09.py` — jeder stellt den alten Fehler nach), ruff
grün, Python 3.9 und 3.11, jede Seite am Rechner und am Handy nachgesehen.

**Sicherheit**

- **S1 · Katalogfeld `sectors[].water` stand unescaped im Report.** Jetzt
  baut `_wasser_pill()` die Plakette: Klasse nur aus der festen Liste, Text
  escaped. Zusätzlich normiert `load_spots` die Sektoren
  (`sektoren_normieren`: `water` ∈ flat/chop/wave, `quality` ∈
  best/good/ok/bad, `from`/`to` als Gradzahl) und meldet Fremdes als
  `KatalogFehler` mit Spot und Feld; der Katalogtest prüft `water` mit.
- **S2 · Host-Prüfung auch auf GET.** Eine fremde Seite, deren Name auf
  127.0.0.1 zeigt (DNS-Rebinding), konnte Katalog, Tagebuch und
  Heimatkoordinate lesen. Jetzt 403 wie bei POST.
- **S3 · Schlüsselvergleich als Bytes.** `compare_digest` auf Strings warf bei
  Nicht-ASCII (`?k=ü`) einen TypeError vor der Zugangsentscheidung.
- **S4 · Steuerzeichen.** `spotedit.set_text` und „umbenennen“ nehmen
  C0/C1-Zeichen heraus (`steuerzeichen_raus`); ein `\x01` im Spotnamen machte
  den ganzen Katalog unlesbar. `load_spots` und `load_config` machen aus
  `yaml.YAMLError` einen `KatalogFehler`/`KonfigFehler` mit Zeile.
- **S5 · XML nur ohne DOCTYPE und Entitäten** — `wingscout/xmlsicher.py`, für
  Dateiimport und MeteoAlarm-Feed, geprüft über den ganzen Text statt der
  ersten 4000 Zeichen (ein Kommentar davor reichte zur Umgehung).
- **S6 · Koordinaten-Regex mit Grenzen** (`[^NSEWO\n]{0,24}` statt `*`,
  Zeilen auf 500 Zeichen gekappt): 40 KB in einer Zeile kosteten vier
  Sekunden, 4 MB Stunden — und so lange antwortete jede Suche 409.
- **S7 · Endliche Koordinaten.** Importparser verwerfen `nan`, `inf` und
  Werte außerhalb ±90/±180 (mit Zeile im Protokoll); `load_spots` verlangt
  dasselbe. Ein `nan` aus einer GPX ging bis dahin als `latitude=nan` an
  Open-Meteo, das dann das ganze Paket von 20 Spots verwarf.
- **S8 · Antwort-Header:** `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, `Cache-Control: no-store` auch auf dem
  Schlüssel-Redirect.
- **S9 · Fehlertexte ohne Pfade:** `fehler_satz()` gibt dem Browser den Satz,
  das Terminal bekommt die Einzelheiten.
- **S10 · Zusatzquellen kosten nur noch ihren Punkt:** `tide.extrema` und
  `ensemble.window_stats` übergehen Unlesbares, `cli.py` fängt die
  Tidenübersicht wie die anderen Zusatzquellen.
- **S11 · `spotedit`:** `set_text` ersetzt einen von Hand geschriebenen
  Block-Skalar (`comment: |`) samt Kindern; `set_block` schreibt mit der
  Einrückung des Blocks statt fest zwei und vier Leerzeichen.
- **S12 · Mengengrenzen im Import:** höchstens 500 Treffer, Namen auf 120
  Zeichen, höchstens 40 Nominatim-Anfragen je Import (der Rest heißt nach
  seiner Koordinate); ein krummer Datensatz kostet den Datensatz, nicht die
  Datei (KML, GeoJSON, CSV).
- **S13 · Härtung:** `config.yaml` wird mit `0600` angelegt; `report.html`
  atomar geschrieben; Cache-Dateinamen aus Stations-IDs bereinigt; ZIP-Mitglieder
  vor dem Entpacken gemessen (200 MB); Weiterleitungen nur auf `https://`
  (`sources/netz.py`); korrupter Overpass-Cache wird neu geholt statt bei
  jedem Lauf zu scheitern; Instagram-Links nur `https`; der
  `.gitignore`-Test kennt `tagebuch.json`, `modellguete.json`, `config.yaml`.
- **S14 · Der Kasten „Auf dem iPhone“** (Adresse mit Schlüssel) ist am Handy
  ausgeblendet — die Regel fehlte, der Kommentar behauptete sie.

**Bedienung**

- **U1 · Ein kaputter Katalog (oder eine kaputte Konfiguration) zeigt eine
  Seite** statt einer toten Verbindung: Datei, Zeile, Grund, und was hilft.
- **U2 · Startfeld:** Platzhalter „Koordinate oder Maps-Link — leer:
  Heidelberg“; ein unlesbarer Startpunkt wird vor dem Start mit einem Satz
  abgewiesen statt still von Zuhause aus zu suchen; der Ergebnis-Banner nennt
  den Startpunkt („… von Heidelberg aus“).
- **U3 · Stundenraster:** Tipp oder Klick auf eine Zelle zeigt ihren Text in
  einem Kasten unter dem Raster (Spot, Stunde, Wind, Güte, Grund) — am
  iPhone gab es den Tooltip nicht.
- **U4 · Kontrast:** `--muted` von `#6C858F` auf `#536E7A` (4,9:1 auf dem
  Grund statt 3,6:1), Oberfläche und Report; Dunkelmodus unverändert.
- **U5 · Textwände:** „Was man wissen muss“ (Rückblick) und „So rechnet das
  Tagebuch“ sind zu und als Punkte gegliedert.
- **U6 · Datumsformat** TT.MM.JJJJ auch bei „Letzte Suche“ und „Verglichen“.
- **U7 · Katalog:** Aktionslinks am Rechner erst bei Hover oder Fokus der
  Zeile (am Handy weiter sichtbar), „Tiden …“, Filter „Zeige nur“.
- **U8 · Tagebuch:** „Güte 0 von 100“ statt „0/100“.
- **U9 · Rückblick:** vor dem ersten Lauf ein Satz statt Leere.
- **U10 · „Als Standard merken“** sagt, was gemerkt wird.

## 1.18.3 — 25.09.2026

- **Eine laufende Suche überlebt den Reiterwechsel — sichtbar.** Sie lief
  schon immer im Hintergrund weiter (der Lauf gehört zum Programm, nicht zum
  Fenster), aber die Suchseite wusste beim Wiederkommen nichts davon: kein
  Spinner, „Spots suchen“ frei, beim Klick 409 „Es läuft schon etwas“. Das
  sah aus wie abgebrochen (gefunden am 25.09.). Jetzt fragt die Suchseite beim
  Laden nach dem Stand: läuft etwas, zeigt sie Spinner, Protokoll und den
  gesperrten Knopf und pollt weiter; ist das Letzte fertig, zeigt sie das
  Ergebnis mit Uhrzeit und den Report darunter — auch wenn es während des
  Katalogbesuchs fertig wurde.
- **Jeder Reiter zeigt, dass etwas läuft** (`web/lauf.js`, auf jeder Seite und
  im Report über den Server): ein pulsender Punkt am Reiter, der den Lauf
  gestartet hat (Suche, Rückblick oder Tagebuch), und ein grüner Punkt an
  „Ziele“, wenn seit dem Öffnen der Seite ein neuer Report entstanden ist.
  Fragt alle zwei Sekunden nach `/status`; `JOB` trägt dafür Start und Ende
  (`seit`, `ende`) des letzten Laufs.
- Geprüft im Browser gegen einen Server, dessen Suche 25 s dauert: starten,
  auf Rückblick wechseln (Punkt an „Suche“), zurück (läuft weiter, Protokoll
  aktuell), auf Katalog warten (Punkt an „Ziele“), zurück (Ergebnis mit
  Uhrzeit, Report unten). Am Handy dasselbe in der Tab-Leiste.
- **Belegter Port.** Sitzt ein anderes Programm auf 8765, starb Wingscout
  bislang mit einem Traceback „Address already in use“ — der Starter meldete
  nur „mit Code 1 beendet“ (gefunden am 25.09., ein zweiter lokaler Server
  nahm denselben Port). Jetzt schaut `serve()` vorher nach: antwortet dort
  schon eine Wingscout-Oberfläche, wird keine zweite gestartet, sondern die
  laufende im Browser geöffnet; sitzt dort etwas anderes, nimmt Wingscout den
  nächsten freien Port (bis zehn weiter) und sagt es im Terminal — die
  iPhone-Adresse trägt den Port ohnehin. Scheitert das Öffnen trotzdem, gibt
  es einen Satz statt eines Tracebacks.

## 1.18.2 — 25.09.2026

- **„Beenden“ oben rechts auf jeder Seite.** Der Knopf saß unten im
  Suchformular — wer auf Ziele, Rückblick oder Tagebuch war, musste erst zurück
  zur Suche und ans Ende scrollen. Jetzt steht er rechts in der Reiterleiste,
  rot umrandet; am Handy, wo die Leiste unten sitzt, als kleine feste Marke
  oben rechts (die erste Zeile der Seite lässt ihr Platz). Weiterhin zwei
  Klicks: der erste macht ihn scharf („Wirklich beenden?“, gefüllt), nach
  fünf Sekunden ohne zweiten entschärft er sich. Das Skript (`web/beenden.js`)
  kommt mit dem Seitenfuß; dem Report setzt der Server es zusammen mit der
  Leiste ein, im eingebetteten Rahmen gibt es den Knopf nicht.

## 1.18.1 — 25.09.2026

- **Reiterleiste im Report am Rechner wieder oben.** Seit 1.17.0 setzte der
  Server die Leiste vor `</body>` ein — am Handy egal, weil sie dort unten
  festgeheftet ist, am Rechner aber ein Element im Textfluss und damit am Ende
  von 40 Bildschirmen Report: Wer „Ziele“ öffnete, kam nur mit dem
  Zurück-Knopf des Browsers zur Suche (gefunden am 25.09.). Jetzt steht sie am
  Anfang von `.wrap` vor der Überschrift, das Format im Kopf; im eingebetteten
  Rahmen nimmt sie sich weiterhin selbst heraus. Test mit einem echten
  Demo-Report.

## 1.18.0 — 24.09.2026

### Tiden: Hoch- und Niedrigwasser je Spot, zur Anzeigezeit gerechnet

Bis 1.17.0 stand die Gezeit nur bei neun Spots mit `tidal: true` in der
Sessionzeile — als volle Stunde des höchsten Modellwerts, nur mit dem Haken
„Wassertemperatur und Tiden“, und ohne jede Wirkung auf die Bewertung. Ein
Report, der um zehn erstellt und um vierzehn Uhr am Strand gelesen wird,
konnte nicht sagen, ob es gerade aufläuft.

- **Drei Stufen je Spot** statt eines Hakens: `tidal: true` (gilt), `false`
  (nie), weglassen = **automatisch** — Meer oder Lagune mit mindestens 0,5 m
  modelliertem Hub (`tide.auto_hub_min`). Die Automatik macht aus den neun
  Spots alle Nordsee-, Atlantik- und Kanalspots, ohne dass jemand 160 Einträge
  pflegen muss; Ostsee und Mittelmeer bleiben still. Zwei Lagunen hinter Dämmen
  stehen auf `false` (Grevelingen-Seite, Spuikom Oostende): das 8-km-Raster
  sieht dort die Nordsee davor.
- **Die Lage jetzt** steht am Ziel und im Karten-Popup — „Jetzt auflaufend ·
  Hochwasser um 14:50 (in 1 h 40 min)“ — und wird von `web/tide.js` beim Öffnen
  gerechnet und jede Minute nachgeführt. Die Scheitel reisen als Unix-Sekunden
  mit, gerechnet wird in der Ortszeit des Spots, nicht in der des Browsers.
  Ohne Skript bleibt der Stand vom Erstellen stehen.
- **Scheitel auf die Minute:** Parabel durch die drei Stunden um das Extremum
  (`tide.extrema`). Das Modell selbst ist nicht minutengenau, aber „14:25“
  statt „14:00“ nimmt den Sprung heraus, den die volle Stunde machte.
- **Tidenfenster** als Regel, nur wo gesetzt: `tide: {fahrbar: hochwasser |
  niedrigwasser | auflaufend | ablaufend, stunden: 2}`. Stunden außerhalb
  fallen mit Veto heraus („außerhalb des Tidenfensters (HW ± 2 h)“), nach dem
  Tageslicht-Veto und vor der Wingwahl; die Halbtiden reichen von Scheitel zu
  Scheitel. Wingscout liefert keine Fenster mit — welches ein Spot braucht,
  weiß nur, wer ihn kennt.
- **Schalter im Katalog:** „Tiden“ neben umbenennen und verschieben, mit
  automatisch / ja / nein und der Fensterwahl; Endpunkt `/katalog/tide`
  schreibt `tidal` und den Block `tide` auf Textebene (`spotedit.entferne_feld`
  nimmt ein Feld samt Unterblock heraus — `set_text(…, "")` konnte nur die
  Kopfzeile). Plakette „Tiden: auto/ja/nein · HW ± 2 h“, Filter „mit
  Tidenregel“.
- **Marine-Daten immer für Meer und Lagune**, nicht nur mit `--marine`: die
  Anfrage kostet dasselbe, ob sie eine oder drei Reihen holt. Der Haken heißt
  jetzt „Wassertemperatur und Wellenmodell“ und entscheidet nur noch, ob die
  beiden in die Bewertung eingehen; Spots mit `tidal: false` werden ohne ihn
  nicht angefragt. Bricht das Netz weg, endet die Schleife nach dem ersten
  Fehler statt jedes Paket in den 45-s-Timeout zu laufen.
- Sessionzeile: Lage zu Beginn und die Scheitel in der Session; Raster-Tooltip
  nennt die Lage der Stunde; Wettertabelle im Report erklärt die Regel; im
  Demo-Lauf haben die Meer-Spots verschiedene Hübe, damit auch die Automatik
  zu sehen ist.
- 26 neue Tests (`tests/test_tide.py`), darunter einer, der `tide.js` mit Node
  gegen feste Zeitpunkte rechnet — 453 Tests, ruff grün, Python 3.9 und 3.11.

Offen bleibt die Quelle: ein Modell auf 8 km, keine amtliche Tafel. Für die
Nordsee gäbe es Pegelonline (BSH) und Rijkswaterstaat mit gemessenen und
astronomischen Werten — siehe TODO.

## 1.17.0 — 20.09.2026

### Wingscout auf dem iPhone

Gemessen wurde am iPhone 13 mini (375 Punkte breit) gegen einen echten Report:
Er war **37 237 px hoch — 46 Bildschirme**, und die Antwort auf „wo lohnt es
sich?“ kam erst nach drei Wischern (Parameterkopf, Warnbanner, leerer
Kartenkasten). Die Übersichtstabelle war 942 px breit in einem 375-px-Fenster,
die Sessionzeile 681 px in 329 px sichtbar — beides schnitt rechts ab, ohne es
zu zeigen. Die Reiterleiste brach in zwei Zeilen und kostete 230 px oben.

- **Tab-Leiste unten statt Reiter oben** (ab 700 px Fensterbreite), vier
  Punkte mit Symbol und Beschriftung: Suche, Ziele, Rückblick, Tagebuch.
  Katalog und Koordinatenprüfung sind Arbeit mit Karte und Tabelle und bleiben
  dem Rechner vorbehalten; erreichbar sind sie weiterhin über die Suchseite
  und ihre Adresse. Apples Vorgaben raten von einem „Mehr“-Reiter ab, deshalb
  vier statt sechs.
- **Der Report ist der Reiter „Ziele“.** Über den Server bekommt er die
  Reiterleiste eingesetzt; die Datei selbst bleibt unverändert, damit sie per
  AirDrop aufs iPhone wandern und dort ohne Server geöffnet werden kann.
- **Antwort zuerst:** Parameter und Karte klappen am Handy zu (`web/mobil.js`,
  am Rechner bleibt alles offen). Das erste Ziel steht jetzt auf dem ersten
  Bildschirm.
- **Nichts schneidet mehr ab:** Sessionzeile und Stellplätze brechen um;
  Stundenraster und breite Tabellen wischen seitlich, mit Hinweis darüber und
  stehender erster Spalte. Im Raster sind die Stunden wieder beschriftet
  (vorher 3 px je Stunde).
- **Drei Fehler, die auch am Rechner welche waren:** Tabellen und Diagramme
  ohne eigenen Wischbereich dehnten als Flex- oder Rasterkind die ganze Seite
  (fehlendes `min-width:0`) — im Rückblick auf 444 px, im Katalog auf 535 px.
  Geprüft ist jetzt bei 320, 375, 390, 402 und 430 px: keine Seite läuft über
  den Rand.
- **Spotauswahl im Tagebuch ohne `datalist`.** Auf iOS Safari legt Safari deren
  Dropdown über das Eingabefeld, sobald mehr als etwa drei Vorschläge kommen;
  bei 278 Spots ist das unbenutzbar (belegt in einem Praxisbericht, siehe
  Recherche im Chat). Jetzt eine eigene Trefferliste mit tippgroßen Zeilen,
  Pfeiltasten und Escape — auch am Rechner besser.
- Was Safari sonst erzwingt: `viewport-fit=cover` plus `env(safe-area-inset-*)`
  für Dynamic Island und Home-Indikator, 16 px Schrift in Eingabefeldern
  (sonst zoomt Safari beim Antippen hinein und nicht wieder heraus), 44 px
  Tippziele, `svh`/`dvh` statt `100vh`. `user-scalable=no` steht bewusst
  nicht da: Safari ignoriert es seit iOS 10, und Zoom zu verbieten wäre eine
  Barriere.

### Zugang vom Handy — nur mit Schlüssel

- `python3 -m wingscout.webui --lan` (oder Doppelklick auf **„Wingscout fürs
  iPhone starten“**) lässt Wingscout zusätzlich im WLAN hören. Weil damit jedes
  Gerät im Netz anklopfen könnte, gilt dann ein **Zugangsschlüssel**: Er steht
  in der Startadresse, die das Terminal ausgibt (und die Oberfläche unter
  „Datenquellen“ zeigt), wandert einmal ins Cookie und gilt, bis Wingscout
  beendet wird. Ohne ihn: 401. Vom Mac selbst (127.0.0.1) wie bisher ohne.
- Die Herkunftsprüfung kennt jetzt auch die eigenen Netzadressen — aber nur
  die, nicht jeden Namen, der darauf zeigt (DNS-Rebinding).
- Ohne `--lan` ändert sich nichts: Wingscout hört weiter nur auf 127.0.0.1.
  Die Sicherheitstests halten beides fest (`tests/test_security.py`).

### Zum Home-Bildschirm

- Web-App-Manifest und Symbole (ein Windsack, 180/192/512 px, dazu eine
  maskierbare Fassung). „Teilen“ → „Zum Home-Bildschirm“ startet Wingscout
  dann ohne Safari-Leisten unter eigenem Namen.

### Nicht geprüft

Alles oben ist in Chromium bei iPhone-Maßen gemessen, nicht auf einem echten
Gerät: Safe Area, Tastaturverhalten, „Zum Home-Bildschirm“ und die Adresse im
WLAN muss Philipp am iPhone gegenprüfen.

## 1.16.1 — 20.09.2026

- **„Koordinaten prüfen“ steht nur noch da, wenn es etwas zu prüfen gibt.**
  Im Katalog ist gerade nichts offen — kein Spot mit `verified: false`, keine
  Ufergeometrie, die nicht zur Koordinate passt. Der Reiter führte damit auf
  eine Seite, die nur „Nichts zu prüfen“ sagt. Er kommt von selbst wieder,
  sobald ein Import unbestätigte Koordinaten bringt oder eine Geometrie
  auffällt; auf der Prüfseite selbst bleibt er stehen, damit sie sich nicht
  unter den Füßen wegzieht, wenn der letzte Eintrag abgehakt ist. Erreichbar
  ist sie immer unter `/pruefen`. Die Zahl dafür (`pruef_offen()`) wird
  gemerkt, solange `spots.yaml` und `geometry.json` unverändert sind — sonst
  läse jede Seite Katalog und Geometrie neu (~0,2 s).
- Ist nichts zu prüfen, zeigt die Prüfseite nur noch diesen Satz — vorher
  standen darüber die Erklärung der drei Stufen und eine leere Karte. Bei
  einem einzigen Eintrag schreibt sie „Ein Spot, der …“ statt „1 Spots,
  die …“.
- Der Hinweis im Prüflauf, wenn ruff fehlt, nennt jetzt `brew install ruff`
  (und `pipx`): Homebrews Python lehnt `pip install` seit PEP 668 ab, und
  genau darauf lief der alte Hinweis zu.

## 1.16.0 — 20.09.2026

### Session-Tagebuch — neuer Reiter „Tagebuch“

- **Eine Session eintragen:** Spot (aus dem Katalog), Datum, Zeit von–bis,
  Wing (aus dem Quiver), Leistung (untermotorisiert / passt /
  übermotorisiert), Wasser (flach / kabbelig / Welle), Note 1–5. Geprüft wird
  beim Eintragen: Spot und Wing müssen existieren, das Datum darf nicht in
  der Zukunft liegen, „bis“ nach „von“, eine Session von heute muss schon
  begonnen haben. Gespeichert in `tagebuch.json` im Projektordner —
  persönlich, in `.gitignore`, wie `config.yaml`.
- **Vergleich:** Nach dem Eintragen holt Wingscout im Hintergrund, was es für
  genau diese Stunden gesagt hätte, was jedes Modell sagte und — mit einer
  Station in 30 km — was gemessen wurde. Dieselbe Rechnung wie im Rückblick:
  dafür ist sie aus `rueckblick.rechne` in eine eigene Funktion
  `rueckblick.spot_zeile` gewandert. Ohne Station oder ohne Werte für den Tag
  steht wenigstens die Vorhersage da; „Neu vergleichen“ holt die Messung
  später nach. Weiß ein neuer Vergleich weniger als der alte (Netz weg,
  Station stumm), bleibt der alte stehen, mit Vermerk. An der Session steht,
  wenn Wingscout einen anderen Wing genommen oder anderes Wasser erwartet
  hätte.
- **Vorschläge für die Windfenster** (`config.yaml`): untermotorisiert bei
  einem Wind im Fenster hebt die Untergrenze knapp über den höchsten solchen
  Wind; übermotorisiert im Fenster senkt die Obergrenze knapp unter den
  niedrigsten; „passt“ außerhalb weitet das Fenster. Als Wind der Session
  gilt die Messung, wenn die Station höchstens 15 km weg liegt, sonst die
  Wingscout-Vorhersage — was genommen wurde, steht an jedem Beleg.
- **Vorschläge für den Windfaktor** (`spots.yaml`): jede Session grenzt ihn
  ein (roher Modellwind der Session-Stunden mal Faktor lag im Fenster des
  gefahrenen Wings, darunter oder darüber). Vorgeschlagen wird der
  nächstliegende Faktor, zu dem alle Sessions des Spots passen, auf 0,05
  gerundet, zwischen 0,6 und 1,5. Stunden mit angenommener Thermik zählen
  nicht. Ein erster Entwurf nahm bei „passt“ die Mitte des Fensters an — das
  unterstellte eine Genauigkeit, die „passt“ nicht hat, und schlug schon bei
  zwei Sessions mitten im Fenster eine Änderung vor.
- Beide Arten brauchen **mindestens zwei Sessions in dieselbe Richtung**;
  widersprechen sich Sessions, gibt es keinen Vorschlag, und die Seite sagt
  warum. Stützen dieselben Sessions einen Vorschlag für das Windfenster *und*
  einen für den Windfaktor (untermotorisiert passt zu beidem), steht dabei,
  dass beide zu übernehmen denselben Befund doppelt korrigiert.
- **Übernehmen** schreibt nur die eine Zeile (`- {size: 5.0, low: …, high: …}`
  bzw. `wind_factor:`), Kommentare bleiben; nur den Vorschlag, den der Server
  gerade selbst rechnet (sonst 409 „Seite neu laden“); nie während eine Suche
  läuft; lässt sich die Datei danach nicht laden, kommt die alte Fassung
  zurück. Nach einem neuen Windfaktor werden die Sessions dieses Spots neu
  verglichen. Neu dafür: `spotedit.set_zahl`.

### Unter der Haube (Struktur-Review vom 20.09., A1, A3, A4)

- **CSS und JavaScript als eigene Dateien** in `wingscout/web/` — für die
  Oberfläche und den Report, 15 Dateien. `webui.py` ging von 2 954 auf 1 569
  Zeilen (mit dem Tagebuch 1 819), `report.py` von 1 624 auf 1 137. Daten
  kommen als JSON in eine Variable vor dem Skript (`var KARTE`, `var LEAFLET`,
  `var TAGEBUCH`), statt in eine f-Vorlage eingesetzt zu werden. Geprüft:
  Prüf-, Katalog- und Rückblickseite bytegleich wie vorher, die Startseite
  bis auf `var LEAFLET`; die Karte im Report im Browser gegen eine
  nachgebaute Leaflet-Schnittstelle (die echte lädt im Prüfaufbau nicht):
  alle 278 Marker, keine Fehler.
- **`pyproject.toml`**: Name, Version aus `wingscout/__init__.py`, Python ab
  3.9, `PyYAML>=6,<7` (auch in `requirements.txt`), Regeln des Linters.
- **ruff im Prüflauf** (`tools/check.sh`, jetzt fünf Schritte: Syntax samt
  `node --check` über `web/*.js`, Linter, Tests, Katalog, Altlasten).
  Ausgewählt sind nur Pyflakes, Syntaxfehler und drei Bugbear-Regeln; fehlt
  ruff, wird der Schritt mit Hinweis übersprungen. Der erste Lauf fand acht
  ungenutzte Importe, fünf ungenutzte Variablen (drei im Code, zwei in einem
  Test), zwei f-Strings ohne Platzhalter und zwei doppelte Einträge in einer
  Menge in `tools/koordinaten_check.py` — alles behoben, nichts davon
  änderte ein Ergebnis.
- Nicht geändert: der Prüflauf auf GitHub (Workflow-Datei) — ein Push, der
  sie ändert, braucht einen Token mit `workflow`-Haken (siehe TODO).
- 410 Tests (vorher 364), davon 45 für das Tagebuch.

## 1.15.0 — 20.09.2026

### Rückblick: das Diagramm zeigt erst die Messung

- **Standard ist die Messung und die Spanne der Modelle — sonst nichts.**
  Bis 1.14.0 stand immer die Wingscout-Bewertung als Linie im Diagramm und
  dazu gestrichelt das beste Modell dieser Tage; an einem niederländischen
  Spot also „Wingscout“, die in den Stunden des Regionalmodells HARMONIE ist,
  und daneben oft noch einmal HARMONIE. Das las sich, als sei HARMONIE Wingscout. Jetzt ist keine Linie
  vorab an. Darunter lassen sich einzelne Modelle zuschalten, die
  Wingscout-Bewertung auch — höchstens drei Linien zugleich, jede mit eigener
  Farbe und eigenem Strichmuster (Farben mit dem Palettenprüfer gegen
  Farbfehlsichtigkeit geprüft). Die Farbe bleibt am Modell, wenn eine andere
  Linie abgeschaltet wird.
- **„Bisher bestes Modell“** als eigene Option: das Modell, das laut
  Gedächtnis (`modellguete.json`) an diesem Spot am besten lag (ab 24
  gemeinsamen Stunden), sonst das beste über alle Spots — und nur eines, das
  am Spot in diesem Rückblick eine Reihe hat. Ohne Historie steht die Option
  ausgegraut da.
- Die Kennzahlen oben auf jeder Karte gehören keiner Linie mehr: Stunden mit
  Messung, mittlere Spanne der Modelle, bestes Modell dieser Tage und bisher
  bestes Modell. Die Zahlen der Wingscout-Bewertung stehen in der Tabelle
  „Modelle im Vergleich“, samt dem Regionalmodell, das sie benutzt.
- Der Tooltip nennt die Messung, die Spanne und jede zugeschaltete Linie;
  „Alle Stunden als Tabelle“ hat jetzt je Modell eine Spalte — die
  Tabellenansicht jeder Linie.
- In den Tabellen heißt die Bewertung „Wingscout-Bewertung“, wie im Knopf.

### Rückblick: die Station mit der besseren Abdeckung

- **Der Rückblick nimmt die Station mit der besseren Abdeckung.** Bis 1.14.0
  gewann die nächste Station, die *überhaupt* Werte hatte. Die Sonde vom
  20.09. zeigte die Folge: IJmuiden Zone 1 bekam KNMI IJmuiden (0,8 km) mit
  24 Stunden, alle von vorgestern — Rijkswaterstaat IJmuiden Buitenhaven liegt
  genauso weit weg und misst bis jetzt; bei Gleichstand entschied die
  Kennung („225“ vor „ijmuiden…“). Jetzt gilt: die nächste Station, die
  mindestens 90 % der Stunden bis jetzt hat; hat keine so viel, die nächste
  mit wenigstens 80 % dessen, was die beste hat — eine Station 25 km weiter
  mit einer Stunde mehr verdrängt die nahe nicht. Gefragt wird der
  Entfernung nach und nur so weit, bis eine reicht; in der Regel bleibt es
  also bei einer Anfrage.
- Wurde eine nähere Station übergangen, steht sie am Ergebnis: „statt KNMI
  IJmuiden (0,8 km, nur 22 von 37 Stunden bis jetzt)“, dazu eine Zeile im
  Protokoll. Jedes Ergebnis trägt, wie viele Stunden bis jetzt die Station
  hatte und wie viele möglich waren.

## 1.14.0 — 20.09.2026

Ausgangspunkt war die Sonde vom 20.09., 13:40: DWD, KNMI, GeoSphere und
Open-Meteo grün, aber Météo-France „keine Stundenwerte“ für Leucate, und
unter „KNMI/RWS“ nur „49 Stationen“ — alles KNMI. Dazu drei Wünsche: die
Pin-Namen durch Orte ersetzen, den Code nach üblicher Praxis prüfen, und im
Rückblick mehr als ein Modell gegen die Messung stellen.

Neu in der Arbeitsweise: Die Dienste sind diesmal **vor** dem Bau gegen die
echten Schnittstellen geprüft worden — über den eingebauten Browser der
Desktop-App, der auf dem Mac läuft und Netz hat (ENTWICKLUNG.md,
„Arbeitsweise mit Claude“).

### Messdienste

- **Météo-France nahm Stationen ohne Windmessung.** Die nächste Station zu
  Leucate ist Fitou (11144001) — sie meldet Regen und Temperatur, die Spalte
  FF ist in keiner Zeile gefüllt. Als Station zählt jetzt nur, wer in der
  Département-Datei irgendwann Wind gemeldet hat; für Leucate ist das die
  Station Leucate (11202001), 5 km weiter. Die gemerkten Stationslisten
  heißen neu (`fr_*_windstationen.json`), die alten gelten nicht mehr.
- **Rijkswaterstaat über die neue Schnittstelle.** 1.13.0 war nach der
  Beschreibung der alten WaterWebservices gebaut; die lieferten keine
  Stationsliste mehr, und `nl_stationen` verschluckte den Fehler. Jetzt
  `ddapi20-waterwebservices.rijkswaterstaat.nl` (DD-API 2.0), am 20.09. im
  Browser geprüft. Was dabei herauskam und im Code steht:
  - Lage direkt als `Lat`/`Lon`, die Abfrage braucht nur noch den `Code`.
  - Wind ist `WINDSHD`, Richtung `WINDRTG` — am Code erkannt; an der
    Beschreibung („windsnelheid“) hätte auch die Standardabweichung gezählt.
  - Nur 56 von 438 Orten mit Wind im Katalog messen noch (viele Badestrände
    haben ihren letzten Wert von 2008). Die Stationsliste enthält nur Orte
    mit einem Wert aus den letzten sieben Tagen (`OphalenLaatsteWaarnemingen`,
    eine Anfrage für alle).
  - Jede Antwort trägt neben zwei gemessenen Reihen eine **Vorhersage**
    (`ProcesType` „verwachting“) mit Werten um 0,5 m/s. 1.13.0 hätte sie ins
    Stundenmittel gemischt. Genommen wird die auf 10 m korrigierte Messung.
  - Keine Werte im Zeitraum: HTTP 204 mit leerem Körper — kein Fehler mehr.
- **Die Sonde zeigt den Fehler von Rijkswaterstaat**, statt nur die KNMI-Zahl
  zu melden.
- **DMI (Dänemark), neu.** Die Open-Data-Schnittstelle `metObs v2` gibt
  Stationen und Zehnminutenwerte ohne Schlüssel heraus (am 20.09. geprüft,
  Werte bis zur aktuellen Stunde). Ein dänischer Spot bekommt jetzt die
  dänische Station statt List auf Sylt. Im TODO stand „mit kostenlosem
  Schlüssel — nicht geprüft“; ein Schlüssel ist nicht nötig.

### Rückblick: jedes Modell gegen die Messung

- Je Spot eine Tabelle **„Modelle im Vergleich“**: ICON, ECMWF, das KI-Modell
  ECMWF-AIFS, GFS, Météo-France, UKMO und bis zu drei Regionalmodelle, die den
  Spot abdecken — je Modell mittlerer Fehler, Bias, Richtung, F1 für „≥ 12 kn
  bei Tag“ und Stunden, sortiert, das beste mit Stern. Die Modelle stehen roh
  da (ohne `wind_factor`, ohne Thermik); „Wingscout“ ist die Bewertung mit
  beidem, als eigene Zeile. Welche Modelle Open-Meteo rückwirkend führt, ist
  am 20.09. an Brouwersdam und Torbole abgefragt (`modellvergleich.py`).
- Im Diagramm eine graue Fläche für die Spanne aller Modelle und das beste
  Modell gestrichelt; darunter Knöpfe, um ein anderes Modell hineinzulegen.
  Der Tooltip nennt den Wert des gezeigten Modells und die Spanne.
- Unten auf der Seite die **Rangliste** über alle Ziele des Rückblicks und
  das **Gedächtnis** über alle bisherigen Prüfungen: `modellguete.json`
  (persönlich, nicht versioniert) hält je Spot, Tag und Modell die Summen.
  Derselbe Tag wird ersetzt, nicht doppelt gezählt; wechselt die Station,
  gilt der Tag neu. Ein bestes Modell je Spot wird erst ab 24 gemeinsamen
  Stunden genannt. Die Suche selbst ändert sich dadurch nicht — ob die
  Rangliste später die Modelle gewichten soll, entscheidet sich, wenn sie
  ein paar Wochen Daten hat.
- Die globalen Vergleichsmodelle lassen sich in `config.yaml` unter
  `rueckblick: modelle:` ändern (Vorlage am Ende von `config.example.yaml`).
- Die Maße werden über Summen gerechnet, damit sich Tage und Spots addieren
  lassen; ein Test hält fest, dass das dieselben Zahlen gibt wie
  `pruefstand.masse`.

### Katalog: Namen, Länder, Gewässer

- **107 Spots umbenannt**, alle nach dem nächsten Ort laut OpenStreetMap
  (Nominatim, je Spot drei Abfragen: Stufe 17, 14, 10), und wo das nicht
  reichte, nach dem Gewässer aus dem Overpass-Auszug oder einer Suche:
  - alle 54 „Pin …“ (etwa „Pin 47.6143, 11.3394“ → „Walchensee – Urfeld“),
  - 22 durchnummerierte Einträge aus Jens Dees Liste („Dänemark 4
    (Jens-Dee-Pin)“ → „Hvidbjerg Strand – Øster Oksby“),
  - 9 Allerweltsnamen („Kite spot“, „beacharea“, „Parkplatz“, „von Jens“ …),
  - 22 Namen von Schulen, Bars, Parkplätzen ohne Ort — dort steht der Ort
    jetzt vorn und der alte Name in Klammern („Niobe“ → „Fehmarn –
    Gammendorf (Niobe)“).
  Die Kennungen (`pin-47-6143-11-3394` usw.) bleiben — an ihnen hängen
  Ufergeometrie, Instagram, Kommentare und Cache.
- Zwei Funde beim Umbenennen: „Allgäu / Forggensee 1“ liegt im Großen
  Alpsee bei Bühl, nicht im Forggensee. „Pin 37.0960, 25.3750“ liegt 100 m
  neben „Naxos – Agios Georgios“ (jetzt „… (zweiter Pin)“, Kandidat zum
  Zusammenlegen).
- **15 Landeskürzel korrigiert**, alle 278 Spots gegen OpenStreetMap
  geprüft (die offene Frage „Grenznähe“ aus dem TODO): vier „AT“ am Wörthsee,
  Kochelsee und Walchensee (DE), die Surferwiese Walchensee (DE), Reichenau
  (DE statt CH), Brognard bei Montbéliard (FR statt CH), Katoro bei Umag
  (HR statt SI), zwei albanische Strände (AL statt GR), Ada Bojana (ME statt
  AL), Foz do Miñor (ES statt PT), Fréjus (FR statt IT), La Nautique bei
  Narbonne (FR statt ES), Vega (NO statt SE).
- **61 Gewässerarten gesetzt**, wo sie `unknown` waren und der Befund
  eindeutig ist: Pin im oder höchstens 100 m neben einem benannten See,
  Stausee oder einer Lagune (Typ laut OpenStreetMap), oder laut
  Ufergeometrie auf der Seeseite der Küstenlinie bzw. im offenen Meer.
  Offen bleiben 22.
- **Neue Spots ohne Namen** heißen ab jetzt nach dem nächsten Ort, und das
  Land kommt aus OpenStreetMap statt aus den groben Rahmen
  (`sources/ortsname.py`, eine Anfrage je Sekunde, gemerkt). Fällt der
  Dienst aus, bleibt alles wie bisher.

### Behoben

- **`spotedit` änderte das falsche `name:`.** Ein Spot mit Thermikblock hat
  zwei davon — den eigenen und den des Windes (`thermal: name: "Nordwind"`).
  Umbenannt wurde der erste Treffer, also der Wind. Aufgefallen beim ersten
  Umbenennungslauf, der deshalb zurückgenommen und wiederholt wurde. Jetzt
  zählt nur die Ebene des Spots; gilt auch für Kommentar, Land und
  Flaggen. Ein Test hält es fest.
- Doppelter `csv`-Import in `stationen.py`.

### Prüfen

- **Die Tests kommen nicht mehr ins Netz.** `tests/__init__.py` sperrt jeden
  Aufruf außer 127.0.0.1. Anlass: ein Test der Sonde hatte Rijkswaterstaat
  wirklich angefragt.
- `REVIEW.md` hat einen zweiten Teil: die Struktur-Review vom 20.09. (A1–A8,
  mit Reihenfolge).

## 1.13.1 — 20.09.2026

- **Das Umkreis-Feld im Rückblick nahm keine 10 km an.** „Gültigen Wert
  eingeben“ bei allem außer 1 — und selbst die Vorgabe 30 wäre durchgefallen,
  sobald man sie anfasst. Der Browser prüft eine Zahl gegen `min + n·step`,
  und das Feld stand auf `min=1, step=5`: gültig waren nur 1, 6, 11 … Jetzt
  `step=1`, jede ganze Zahl von 1 bis 100 geht; ein Test rechnet das nach,
  statt nur die Attribute zu lesen. Gefunden von Philipp eine Stunde nach
  1.13.0.

## 1.13.0 — 20.09.2026

Zwei Bilder vom selben Tag. Erstens: ein Ergebnis von vorgestern sah aus
wie eines von heute — der Rückblick zeigte „für FR ist kein Messdienst
angebunden (nur DE, NL, AT)“, gerechnet am 18.09. mit 1.9.0, angezeigt am
20.09. unter 1.12.0, das Frankreich längst kannte. Zweitens: Schokkerstrand
„keine Messstation in 12 km“, Veerse Meer und Texel „Messwerte nicht
abrufbar (KNMI 316/235: keine Stundenwerte in der Antwort)“ — dabei war KNMI
nicht ausgefallen, es veröffentlicht nur mit zwei Tagen Verzug, und in 12 km
war eben nichts anderes.

### Rückblick: Stationen weiter weg, mehr Dienste, über Grenzen

- **Der Umkreis ist wählbar.** „Station bis … km“ neben den Tagen, Vorgabe
  30 km statt fester 12, höchstens 100. Genommen wird die nächste Station,
  die für die Tage Werte hat: hat die nächste noch nichts (KNMI, zwei Tage
  Verzug), kommt die zweitnächste, dann die dritte — bis fünf weiter. Wer
  geliefert hat, steht mit seiner Entfernung am Ergebnis; hat keine, steht
  der Grund da: „die Station hat für diese Tage noch keine Werte
  veröffentlicht — KNMI veröffentlicht die Stundenwerte mit zwei Tagen
  Verzug; auch keine andere in 30 km“. Je weiter die Station, desto weniger
  sagt sie über den Spot — das steht auf der Seite, die Entscheidung liegt
  beim Leser.
- **Über Grenzen hinweg.** Die Stationslisten von DWD, KNMI, Rijkswaterstaat
  und GeoSphere gelten für jeden Spot, egal welches Land im Katalog steht:
  ein belgischer Spot bekommt Cadzand, ein dänischer List auf Sylt. Nur
  Frankreich hängt am Spot (je Département eine Datei). „Für IT ist kein
  Messdienst angebunden“ gibt es nicht mehr — dafür ehrlich „keine
  Messstation in 30 km“.
- **Rijkswaterstaat (Niederlande), neu.** Die WaterWebservices liefern die
  Zehnminutenwerte der Messpfähle und Küstenstationen — Wind *auf dem
  Wasser*, nahe Echtzeit, ohne Schlüssel. Gebaut nach der veröffentlichten
  Beschreibung (rijkswaterstaatdata.nl/waterdata, gelesen am 20.09.), ohne
  Testabfrage: Katalog per POST, daraus die Orte mit Windgeschwindigkeit
  (an der Beschreibung „windsnelheid“ erkannt, nicht an einem geratenen
  Code), Lage aus EPSG:25831 nach WGS84 umgerechnet (Prüfpunkt Vlissingen),
  Werte per POST je Stärke und Richtung, zu Stundenmitteln gerechnet
  (Vektormittel für die Richtung), Einheit laut Antwort. Ob der Dienst so
  antwortet, zeigt `tools/pruefstand.py --sonde` — der erste Lauf bei dir.
- **KNMI: 49 statt 27 Stationen** (aus dem Gedächtnis, auch im
  Binnenland), und eine Antwort ohne Zeilen ist kein Ausfall mehr, sondern
  „noch keine Werte“ mit dem Verzug als Grund.
- **Windguru-Stationen, mit Passwort.** Windguru zeigt viele private
  Messstationen, gibt ihre Werte aber nur über die dokumentierte
  Schnittstelle heraus (Station JSON API, `wgsapi.php`), und die verlangt
  für jede Anfrage das API-Passwort der Station. Die Seiten selbst holen
  ihre Daten über einen internen Weg, der ohne Sitzung 401 antwortet — den
  umgeht Wingscout nicht. Also: Stationen, deren Passwort du hast (deine
  eigene, oder eine, deren Besitzer es dir gibt), kommen mit `id`, `lat`,
  `lon` und `passwort_md5` unter `stationen: windguru:` in `config.yaml`
  (Vorlage in `config.example.yaml`) und laufen dann wie jede andere
  Station mit — Werte in Knoten, Stundenmittel, gefiltert nach der
  Unixzeit. Ohne Eintrag gibt es die Quelle nicht.
- Sonde und Prüfstand kennen die neuen Quellen: die Sonde fragt jeden
  Dienst für sich (KNMI und Rijkswaterstaat je eines), sagt bei Windguru,
  wenn nichts konfiguriert ist, und `--dienste` meint jetzt die Länder der
  Spots — die Station darf von jedem Dienst kommen.

### Die Oberfläche sagt, wenn sie alt ist

- **Der Rückblick sagt, wenn sein Ergebnis überholt ist.** Jedes Ergebnis
  trägt jetzt Version und Suche, mit denen es gerechnet wurde. Ist die letzte
  Suche neuer als das Ergebnis oder das Programm eine andere Version, steht
  ein Balken darüber: „Dieses Ergebnis ist überholt: … „Prüfen“ rechnet neu.“
  Ergebnisse von vor 1.10.0 (ohne Version) gelten als überholt.
- **Jede Seite sagt, wenn ein Neustart fällig ist.** Nach „Neuen Stand
  holen“ oder einem Veröffentlichen läuft der alte Prozess mit dem alten Code
  weiter, bis man Wingscout beendet und neu startet — und nichts sagte das.
  Jetzt vergleicht jede Seite die laufende Version mit der in
  `wingscout/__init__.py` auf der Platte und zeigt den Unterschied als Balken
  mit dem Weg (beenden, neu starten).
- Ein Test hing am Katalogzustand („irgendein unbestätigter Spot“) und fiel,
  seit alle Koordinaten bestätigt sind — er setzt seinen Spot jetzt selbst
  auf unbestätigt.

### Veröffentlichen, das an sich selbst scheiterte

Der erste Versuch, 1.13.0 zu veröffentlichen, blieb am 20.09. im Commit
stecken: `veroeffentlichen.sh` lässt den Prüflauf laufen, setzt dann die
Versionsnummer, und der Pre-Commit-Hook lässt den Prüflauf noch einmal
laufen — jetzt mit der neuen Nummer. Ein Test hatte „1.12.0“ fest
verdrahtet und fiel genau dort. Zurück blieb eine gesetzte Versionsnummer
ohne Commit, und ein zweiter Aufruf wäre an „`__version__` nicht gefunden“
gescheitert, weil das Skript die schon gesetzte Nummer als Fehler las.

- Der Test nimmt die laufende Version statt einer festen Nummer.
- `veroeffentlichen.sh`: steht die Nummer schon drin, geht es weiter
  („Version steht schon auf 1.13.0“); scheitert der Commit, sagt das Skript,
  woran, und dass derselbe Befehl nach der Reparatur noch einmal reicht.
- Der Pre-Commit-Hook ruft `bash tools/check.sh` auf, damit ein verlorenes
  Ausführbar-Bit ihn nicht stumm scheitern lässt (`tools/install-hooks.sh`
  schreibt ihn so; der lokale Hook ist schon umgestellt).

## 1.12.0 — 19.09.2026

- **„Alle Sessions" sortierbar.** Die Tabelle stand nach Score sortiert da,
  auf 40 Zeilen gekappt — wer nach Dauer, Wind oder Wasser fragte, bekam nur
  die 40 mit dem besten Score. Jetzt stehen alle Sessions drin, jede Zelle
  trägt ihren Sortierwert, ein Klick auf die Spalte sortiert im Browser (der
  zweite dreht um), und gezeigt werden die ersten 40 der Reihenfolge, „alle
  zeigen" hebt das auf. Neue Spalte **Lage** (sideshore, side-on, auflandig,
  ablandig — aus Ufergeometrie oder Sektoren) neben der Himmelsrichtung;
  Wasser sortiert flach, kabbelig, Welle; Wind nach Maximum, dann Minimum;
  Wing nach dem kleinsten; bei Gleichstand entscheidet der Score.

## 1.11.0 — 19.09.2026

- **Dein Kommentar zu jedem Spot** — überall, wo ein Spot auftaucht: im
  Katalog, an jedem Ziel im Report, im Karten-Popup, auf der Prüfseite, im
  Rückblick, und beim Eintragen eines neuen Spots. Feld `comment` in
  `spots.yaml` (mehrzeilig, bis 2000 Zeichen, in Anführungszeichen mit `\n`;
  leer nimmt es heraus), geschrieben über `/katalog/kommentar`. Ein
  gemeinsames Stück Skript (`report.KOMMENTAR_JS`) macht aus jedem Kasten
  `.kmt` den Editor; nach dem Speichern erfährt es jeder Kasten desselben
  Spots auf der Seite — im Report also Ziel und Popup zugleich. Als Datei
  geöffnet sagt der Report ehrlich, dass kein Programm dahinter ist.

## 1.10.0 — 19.09.2026

Der erste Tag mit dem Rückblick brachte zwei Wünsche und einen Befund:
der laufende Tag fehlte, Frankreich hatte keine Station, und den Katalog
wollte man an Ort und Stelle pflegen können.

- **Rückblick bis heute.** Der Zeitraum endete gestern — am Freitag fehlte
  der Freitag. Jetzt reicht er bis zur aktuellen Stunde: für heute kommt die
  Vorhersage aus der laufenden Abfrage (`past_days`, derselbe kürzeste
  Vorlauf, nur noch nicht archiviert) und wird Stunde für Stunde mit dem
  Archiv zusammengesetzt (`historisch.hole_bis_heute`); die Messung kommt so
  nah an „jetzt", wie der Dienst es hergibt — DWD über die Zehnminutenwerte
  in „10_minutes/wind/now", GeoSphere über „tawes-v1-10min" der TAWES-Station
  daneben, beide hier zu Stundenmitteln gerechnet (Richtung als
  Vektormittel). Die Sonde vom 19.09., 08 UTC, hat die Grenzen gezeigt: die
  geprüften DWD-Stunden reichen bis vorgestern, die Zehnminuten-„recent",
  die gestern füllen sollen, standen auf dem 13.; KNMI reicht bis
  vorgestern; GeoSphere bis zur aktuellen Stunde; Météo-France bis heute
  03 UTC (Tagesdatei von 05:45 UTC). Deshalb steht je Spot „Messung
  vorhanden: Do 17.09. 00–23 Uhr · Sa 19.09. 00–07 Uhr" — die Lücke ist
  sichtbar statt verschwiegen, die Kennzahlen zählen nur gemeinsame Stunden.
  Caches, die bis heute reichen, gelten eine Stunde.
- **Frankreich hat Messstationen.** Météo-France veröffentlicht auf
  meteo.data.gouv.fr je Département eine Datei mit allen Stationen und
  Stunden der letzten zwei Jahre (FF, DD, UTC, mit Qualitätscodes; Werte mit
  Code 2 „zweifelhaft" bleiben draußen); welche Datei ein Spot braucht, sagt
  eine Rahmentabelle, die Stationen kommen aus der Datei selbst (5–15 MB je
  Département, danach im Cache). Die Dateiadresse wird über die data.gouv-API
  aufgelöst, weil der Name die Jahre trägt. Der Prüfstand kennt `--dienste`,
  um Frankreich auszulassen; die Sonde zeigt jetzt für jeden Dienst erste und
  letzte Stunde, auch für vorgestern bis heute, und lädt für Frankreich nur
  das Département des ersten Spots statt aller 55 — und sie läuft seit dem
  19.09. selbst in einem Test, ohne Netz, weil sie beim ersten Lauf an einer
  Tupel-Entpackung brach.
- **Katalog pflegen.** Auf der Katalogseite: neuen Spot eintragen (mit
  Doppelt-Warnung ab 300 m und auf Wunsch gleich gerechneter Ufergeometrie),
  umbenennen (die Kennung bleibt — an ihr hängen Geometrie, Instagram-Funde
  und Prüfstand), verschieben (Nadel auf der Karte, wie „Übernehmen" auf der
  Prüfseite) und löschen (mit Nachfrage; raus aus `spots.yaml`,
  `geometry.json` und `instagram.json`, der Block steht im Protokoll). Alles
  auf Textebene (`spotedit.entferne`, `set_text`), unter der Sperre der
  Prüfseite, mit Herkunftsprüfung. Das Suchfeld zeichnet die Tabelle nur noch
  bei Eingabe neu — sein `change` beim Verlassen warf den Umbenennen-Editor
  wieder weg.

## 1.9.0 — 18.09.2026

Zwei neue Reiter in der Oberfläche, ein alter Fehler auf der Karte, zwei neue
Angaben je Spot. Oben auf jeder Seite steht jetzt eine Reiterleiste — Suche,
Katalog, Koordinaten prüfen, Rückblick.

- **Neu: Rückblick.** Die zehn besten Ziele der letzten Suche gegen die
  Messung der nächsten Wetterstation über die vergangenen Tage (wählbar, 1 bis
  14, Voreinstellung 2): die aufgehobene Vorhersage aus dem Open-Meteo-Archiv
  läuft durch dieselbe Bewertung wie im Report — Regionalmodell,
  `wind_factor`, Thermikannahme — und steht Stunde für Stunde neben dem
  gemessenen Wind, als Kurve und als Tabelle, mit Fehler, Bias und
  Richtungstreffern je Spot (`wingscout/rueckblick.py`, Seite `/rueckblick`).
  Die Suche merkt sich dafür ihre Zielliste in `cache/letzter_lauf.json`. Die
  Grenzen stehen auf der Seite: Stationen nur in DE, NL und AT (bis 12 km),
  Vorhersage mit kürzestem Vorlauf, Station an Land gegen Spot auf dem Wasser.
  Caches für Zeiträume, die bis in die letzten drei Tage reichen, gelten sechs
  Stunden, weil die Dienste die jüngsten Stunden nachliefern; ältere bleiben
  für immer (`stationen._brauchbar`, auch fürs Archiv).
- **Neu: Katalog.** Alle Spots als Liste mit Suche, Filtern (Land, Gewässer,
  unbestätigt, Thermik, Shorebreak, Instagram), Sortierung und Karte, die
  die Auswahl zeigt. Unten **„Schon drin?"**: Koordinate oder Name eingeben,
  die Seite sagt, ob in 300 m oder 3 km schon ein Spot steht — damit kein
  Spot ein zweites Mal in den Katalog kommt.
- **Spots auf der Karte sind wieder anklickbar.** Der Radiuskreis um den
  Startpunkt war eine gefüllte, interaktive Leaflet-Fläche, zuletzt
  gezeichnet — er lag über allen Punkten innerhalb des Suchradius und
  schluckte jeden Klick. Seit 1.0.0, verdeckt vom Thermikring-Fehler, den
  1.5.3 behob. Beide Flächen liegen jetzt auf einer eigenen Ebene unter den
  Punkten, nicht interaktiv, ohne Mausereignisse; ein Test hält das fest.
- **Shorebreak als Angabe je Spot** — rein als Information, filtert nicht,
  geht nicht in den Score. `shorebreak: {status, note, source}` im Katalog
  (Status `"yes"`, `"possible"`, `"no"`, `"unknown"`, in Anführungszeichen —
  YAML liest ein nacktes `yes` als Wahrheitswert, `load_spots` übersetzt das
  zurück, der Katalogtest mahnt es an). Erscheint als Plakette am Ziel, als
  Zeile mit der Notiz darunter, im Karten-Popup und im Katalog. Erste
  Einschätzung für 34 Spots an Atlantik, Nordsee und Kanal (14 „ja", 20
  „möglich") nach Lage und Exposition, nicht nach eigener Anschauung — daher
  `source: Spotwissen — unbelegt, bitte prüfen`; wer einen Spot kennt,
  korrigiert die Zeile.
- **Instagram je Spot.** Automatisch prüfen, ob dort je etwas gepostet
  wurde, geht nicht (keine öffentliche Suche ohne Anmeldung, keine freie
  Schnittstelle, Abgrasen verboten). Stattdessen zwei Links im Report, im
  Popup und im Katalog — **Instagram** (Ortsseite, sonst Hashtag aus dem
  Namen; im Katalog vorgebbar als `instagram: "#tag"` oder ganze Adresse) und
  **Insta-Suche** (Google auf instagram.com mit Spotname und „wingfoil") —
  und eine Momentaufnahme `instagram.json`: für 100 benannte Spots am
  18.09.2026 per Google gesucht, 77 Ortsseiten und 104 gefilterte Treffer,
  mit Datum und Vermerk „kein Beleg" als Zeile unter dem Ziel. Die anderen
  rund 100 benannten Spots sind noch offen (Suchkontingent), siehe TODO.
  Modul `wingscout/instagram.py`, Adressen nur `https://…instagram.com/…`.
- **Landeskürzel korrigiert**, wo die Google-Liste geraten hatte und die
  Koordinate eindeutig ist: Ancona IT (war HR), Bomboklat/Gera Lario IT (CH),
  Orikum, Narta, Radhimë, Saranda AL (GR), Chiemsee-Feldwies und Tegernsee DE
  (AT), Lac d'Annecy FR (CH); dazu zehn Spots ohne Land: Albanien AL,
  Montenegro ME, Kanaren ES, Antigua AG. Das Kürzel entscheidet die Zeitzone
  (Kanaren: eine Stunde) und das bevorzugte Regionalmodell.
  `spotedit.set_text` setzt Textfelder in Anführungszeichen, Kommentare
  bleiben.
- Katalogtabelle: feste Spaltenbreiten, Links umbrechen — Land, Gewässer und
  Kilometer waren abgeschnitten.

## 1.8.1 — 16.09.2026

Der erste Lauf des Prüfstands mit Netz (16.09., 21:07): alle vier Dienste
antworten wie angebunden, 66 Prüfungen grün, ein Fehler, drei Warnungen —
und die ersten Zahlen. Neun Spots gegen ihre Stationen über den August:
mittlerer Fehler 1,4 bis 3,0 kn, Richtung in 89 bis 100 % der Stunden
richtig, Bias zwischen −2,3 und +2,5 kn. Die Thermiktabelle: an tauglichen
Tagen sieht CH1 den Malojawind an 2 von 3, ICON-2I die Ora an 1 von 2 und die
Breva an 0 von 2, ICON-D2 den Walchensee-Wind an 0 von 3; die globalen
Modelle sehen keine davon; Wingscout mit Annahme alle. Was der Lauf an
Fehlern zeigte, ist hier behoben:

- **Der Koordinaten-Check hielt den Landpunkt für Meer.** Gruppe D gab es nur
  für einen weit versetzten Pin; ein Pin, den der Geometrielauf gar nicht ins
  Wasser versetzen konnte, fiel in Gruppe B („Meer oder unbenannte Fläche“).
  Jetzt zählt zuerst, was der Geometrieeintrag sagt: ohne Wasser in drei
  Kilometern ist es Gruppe D.
- **Fehmarn bekam DMI statt ICON-D2.** Der Spot liegt im deutschen und im
  dänischen Heimatrahmen, beide Modelle haben 2 km, und bei Gleichstand
  entschied das Alphabet. Das Landeskürzel des Spots entscheidet jetzt vor
  dem Rahmen (Regel 4, die gemerkte Zuordnung wird einmal neu geprüft); die
  Rahmen bleiben für Spots ohne Kürzel.
- **Schweigt die nächste Station, kommt die zweitnächste.** Tholen (KNMI
  331) lieferte keine Winddaten, das Paar ging verloren. Jeder Spot kennt
  jetzt bis zu drei Ersatzstationen in Reichweite; die Grundlinie merkt sich
  die, die geliefert hat.
- **Zwei F1-Spalten statt einer.** „F1 Urteil“ (Wingscouts „fahrbar“ gegen
  die Messung) war an Binnenseen mit Landstation wertlos — bei sieben
  gemessenen Stunden über 12 kn im Monat entscheiden drei Stunden über die
  Kennzahl. Daneben steht jetzt „F1 Wind“ (Wingscout-Wind ≥ 12 gegen Messung
  ≥ 12) und die Zahl der gemessenen Stunden; der Grundlinienvergleich nimmt
  den Fehler und F1 Wind, das Urteil nur bei mindestens 30 solchen Stunden.
- KNMI lieferte einen Tag mehr als gefragt (768 statt 744 Stunden); alle drei
  Dienste schneiden jetzt auf den Zeitraum zu. „IJmuiden“ schreibt sich mit
  großem IJ.

## 1.8.0 — 16.09.2026

- **`geometry.json` wiederhergestellt — `build_geometry.py --force` hatte sie
  geleert.** Das Skript begann mit `--force` mit einem leeren Speicher; zusammen
  mit `--only` für sieben Spots blieben von 275 Einträgen sechs übrig, und
  Version 1.7.0 wurde so veröffentlicht. Der Bestand kam aus Git zurück
  (Stand `33ed50b`), die sechs neu gerechneten Spots liegen darüber, die zwei
  verwaisten Einträge (`pin-44-…`, `pin-46-…`) sind dabei entfallen: 275
  Einträge, jeder Spot hat seine Geometrie. `--force` beginnt jetzt immer beim
  vorhandenen Bestand und ersetzt nur, was es neu rechnet — ein Test hält das
  fest.
- **Neu: der Prüfstand** (`Prüfstand.command`, `tools/pruefstand.py`,
  `PRUEFSTAND.md`). Die Tests prüfen ohne Netz, ob der Code tut, was er soll;
  der Prüfstand prüft mit Netz, ob das Ganze noch stimmt, und liefert eine
  Zahl je Spot, die sich nach einer Änderung nicht unbemerkt verschlechtern
  darf. Vier Teile: sieben Referenzspots mit bekanntem Wind (Form der Antwort
  Feld für Feld, Bewertung, Thermiksignatur je Modell — das ist zugleich die
  Antwort auf die Frage nach ICON-2I und der Ora —, Abdeckung durch das
  zuständige Regionalmodell); ein Punkt an Land (Münsinger Alb), der als
  solcher erkannt werden muss; zehn Spots mit einer Wetterstation in zwölf
  Kilometern, für die die aufgehobene Vorhersage eines festen Monats (August
  2026) durch die ganze Bewertung läuft und gegen die **Messung** steht — MAE,
  Bias, Richtungstreffer, „fahrbar“ als F1, je Modell und für Wingscout als
  Ganzes; und die Grundlinie (`pruefstand/grundlinie.json`), gegen die jeder
  spätere Lauf vergleicht. Messwerte von DWD (Deutschland), KNMI
  (Niederlande) und GeoSphere (Österreich), alle frei, alle ohne Schlüssel;
  aufgehobene Vorhersagen aus der Historical-Forecast-API von Open-Meteo.
  Alles Geholte bleibt in `cache/pruefstand/`.
  Gebaut ohne Netz: die vier Dienste sind nach ihren veröffentlichten
  Beschreibungen angebunden, nicht gegen sie gelaufen. `--sonde` fragt jeden
  einmal an und zeigt, was kommt — das ist der erste Lauf.
- **Ein Pin an Land ist ein Pin an Land.** Der Prüfstand hat es beim Bau
  sofort gezeigt: Für einen Punkt ohne Wasser in drei Kilometern galt bis
  1.7.0 „Rose gilt“, sobald die Strahlen irgendwo Wasser trafen — auf der
  Schwäbischen Alb liefen sie zehn Kilometer über Land bis zur Donau, und der
  Punkt sah aus wie ein See mit offenem Wasser. Der Geometrieeintrag trägt jetzt
  `wasser`; ist es falsch, meldet die Prüfseite „unbrauchbar“, die Bewertung
  lässt die Rose weg, und der Report zeigt „Pin an Land?“. Die Rechnung aus
  einem Auszug ist als `shoreline.rechne()` vom Holen getrennt, damit Tests und
  Prüfstand denselben Weg nehmen.
- Neu: `WAS-SICH-GEAENDERT-HAT.md` — die Kurzfassung seit 1.0.0 für
  Benutzer. `Claude outputs/` steht in `.gitignore`.

## 1.7.0 — 16.09.2026

Die übrigen 25 Befunde aus `REVIEW.md`. Drei davon ändern, was im Report
steht — Thermikstärke, Ortszeit, Einigkeit —, der Rest macht das Programm
robuster gegen Fremdantworten, Nebenläufigkeit und eigene Tippfehler.

**Bewertung**

- **Die Verlässlichkeit steckt nicht mehr in der Windstärke.** `typical_kn`
  mal Verlässlichkeit mal Potenzial gab an der Ora 11 kn statt 16 — eine Zahl,
  die an keinem Tag auftritt: läuft die Ora, sind es 16, sonst 0. Der Wing
  wurde für 11 gewählt und passte in beiden Fällen nicht. Jetzt ist die Stärke
  `typical_kn` mal Potenzial, und die Verlässlichkeit geht als
  Wahrscheinlichkeit in die Reihenfolge ein — an der Stelle des Ensembles.
- **Das Ensemble bestraft die Thermik nicht mehr.** Es sieht an der Ora 5 kn
  und meldete 0 % Sicherheit; mit Gewicht 0,5 halbierte das genau die
  Sessions, die das Tool eigens korrigiert hatte. Thermiksessions tragen jetzt
  die Verlässlichkeit des Spots mit demselben gedämpften Faktor, das Ensemble
  lässt sie in Ruhe, und die Plakette sagt es: „Thermik angenommen · 80 %
  verlässlich“. Für alle anderen Sessions kennt die Ensemble-Frage jetzt
  `wind_factor` und den Unterschied zum Regionalmodell: gefragt wird nach der
  rohen Zahl, aus der nach beiden Korrekturen die Fahrgrenze würde.
- **„Modelle einig“ schließt das Regionalmodell ein.** Die Einigkeit wurde
  vor dem Einsetzen von CH1/ICON-D2 berechnet — die Plakette beschrieb drei
  Reihen, die niemand mehr sah, neben einem Wind, der von allen dreien fünf
  Knoten abwich. Nach dem Einsetzen wird sie neu gerechnet, mit dem feinen
  Modell als Mitglied; der Tooltip nennt die Modelle, um die es geht.
- **Eine Stunde knapp unter der Schwelle zerschneidet die Session nicht
  mehr.** 0,54 mitten im Nachmittag machte aus fünf Stunden zwei mal zwei, mit
  `min_hours: 3` gar nichts. Eine einzelne Stunde bis 0,1 unter der
  Mindestgüte zwischen zwei tragenden wird mitgenommen — mit Vermerk, nie mit
  Veto.
- **Fehlende Windrichtung wird nicht mehr Nord.** `or 0.0` machte aus None
  0°, und 0° wurde gegen Sektoren und Rose geprüft, als wäre es gemessen.
  Jetzt bleibt sie fehlend, die Lage wird neutral bewertet, und die Session
  trägt den Vermerk.
- **Die Wellenhöhe aus dem Wellenmodell wird benutzt** (nur mit „Wasser-
  temperatur und Tiden“, nur am Meer). Sie wurde geholt und verworfen; für
  alle galt die SPM-Näherung mit U10 ohne Dauer- und Tiefenbegrenzung. Wo das
  Modell antwortet, gilt seine Zahl, im Report als „(Wellenmodell)“ markiert;
  die Anlauflänge bleibt für die Windlage.
- **`offshore_veto_km`** (Standard 0 = aus): ablandig mit mindestens so viel
  Kilometern freiem Wasser in Lee ist keine Session mehr. Bisher war ablandig
  in jedem Fall nur ein Hinweis, und mit perfektem Wind kam eine Stunde
  trotzdem auf 0,88.
- **Ortszeit am Spot.** Alles wurde in Europe/Berlin abgefragt — in Athen und
  Lissabon standen die Uhrzeiten eine Stunde neben der Ortszeit, das
  Thermikfenster aus dem Katalog griff versetzt. Jede Quelle fragt jetzt je
  Zone des Landes (Kanaren und Azoren nach der Länge), „vorbei“ liest je Spot
  die richtige Uhr, der Report sagt „Ortszeit am Spot“.
- Saison nach jedem Monat, den der Zeitraum berührt, nicht nur nach dem
  Starttag. Das Ensemble-Fenster zählt die Stunde nach der Session nicht mehr
  mit. Die Sonnenstatistik beginnt mit jedem Lauf von vorn statt seit dem
  Start der Oberfläche zu summieren.

**Warnungen**

- **Warnungen nur noch mit Gebiet.** Ein Spot ohne `region` bekam alle
  Warnungen seines Landes: „Gewitter · Bornholm“ an dreizehn Nordseespots,
  „Kreis Plön“ an neun deutschen — 81 Plaketten aus 9 Warnungen, Rauschen, in
  dem die echte unterging. Ohne `region` steht am Spot nichts; was landesweit
  offen ist, sagt der Report einmal im Kopf. 192 von 275 Spots haben kein
  `region` — die Zuordnung über die CAP-Polygone des Feeds steht in REVIEW.md
  als nächster Schritt.

**Katalog und Zwischenspeicher**

- **Jeder Zwischenspeicher gilt für eine Koordinate.** Overpass-Auszug,
  Schutzgebiete, Modellzuordnung und Fahrzeit hingen an der Spot-ID: nach dem
  Verschieben der Nadel rechnete alles außer der Geometrie mit dem alten Punkt
  weiter, und wer die Koordinate von Hand in `spots.yaml` änderte, sogar die
  Geometrie. Jeder Eintrag trägt jetzt die Koordinate (vier Stellen) und gilt
  für keine andere. Alte Overpass-Auszüge ohne Stempel gelten weiter (das Holen
  ist teuer und bekommt den Stempel beim nächsten Mal); Modellzuordnung und
  Fahrzeit werden einmal neu geholt — ein Aufruf je neunzig Ziele.
- **Dateiimporte sind unbestätigt.** Hundert Wegpunkte aus einer fremden GPX
  hat niemand angesehen — sie bekamen trotzdem `verified: true` und kamen nie
  auf die Prüfseite. Aus einer Datei: `verified: false`, `source: importierte
  Datei`; getippt oder aus der Karte kopiert: bestätigt. Ohne Gewässerart
  bleibt `unknown` statt des geratenen `lake`, das einen Meeresspot bei
  abgewähltem „See“ verschwinden ließ und beim Versetzen ins Wasser die
  falsche Fläche bevorzugte.
- Die Cache-Pfade für Overpass und Warnfeeds sind absolut (`wingscout.CACHE`)
  statt relativ zum Arbeitsverzeichnis.

**Oberfläche und Stabilität**

- **Prüfseite und Hintergrundlauf schließen sich aus.** Beide schrieben
  ungeschützt in `spots.yaml` und `geometry.json` — „Fehlende berechnen“
  speichert nach jedem Spot, die Prüfseite las, änderte, schrieb. Läuft etwas,
  antwortet die Prüfseite mit 409; schreibt die Prüfseite, startet nichts;
  zwei Klicks auf der Prüfseite laufen nacheinander. Prüfen und Starten
  geschehen unter einem Lock, sonst sahen zwei gleichzeitige `/run` beide
  „frei“. Jede Datei wird atomar geschrieben (Nachbardatei plus Umbenennen),
  damit ein Leser nie ein halbes YAML sieht.
- `nan` und `inf` im Formular fallen auf den Startwert: `nan` als
  Temperaturgrenze schaltete die Prüfung stumm ab, `inf` als Radius hob ihn
  auf. Gemerkte Startwerte aus `ui_defaults.json` gehen durch dieselbe Prüfung
  wie das Formular. `X-Frame-Options: SAMEORIGIN` gegen das unsichtbare
  Einbetten der Prüfseite.
- GPX und KML mit `DOCTYPE` oder `ENTITY` werden abgelehnt — beides brauchen
  die Formate nie, und Entitäten, die sich tausendfach aufrufen, kosten
  Speicher.

**Quellen**

- Eine Park4Night-Antwort, die anders aussieht als beim Mitlesen (`rating:
  "n/a"`, `services` als Zeichenkette), kostet den Stellplatzblock, nicht den
  Lauf; die Adresse wird nur noch als Pfad an die Domain gehängt. Ensemble-
  Antworten in unerwarteter Form ebenso. Jede Antwort wird begrenzt gelesen
  (`sources/netz.py`, 64 MB; Overpass behält seine 300).
- Overpass fängt jetzt jeden Netzfehler (`OSError`), auch `socket.timeout`,
  das unter Python 3.9 keine `TimeoutError` ist — der zweite Endpunkt wurde
  bei einem Lese-Timeout nie versucht.
- Der Prüflauf und der Sicherheitstest sehen jetzt auch `tools/*.py` und
  `import/*.py`.

## 1.6.1 — 16.09.2026

Aus der Code-Review vom 16.09. (`REVIEW.md`, 29 Befunde). Vier davon hier
behoben — die zwei, die Sicherheitsregeln des Projekts verletzten, und die
zwei, die still falsch rechneten oder still hängen blieben. Der Rest steht
in `REVIEW.md` mit Vorschlag und Reihenfolge.

- **Die Einstrahlung kam bei der Thermik nie an.** `models.CORE` kannte
  `shortwave_radiation` nicht. Bei mehreren Modellen — der Voreinstellung —
  baut `normalize()` das `hourly` nur aus dieser Liste neu; alles andere ist
  danach `None`. `score_hours` las also immer `None`, und die Thermik rechnete
  mit dem Bewölkungs-Rückfall statt mit der Energie, für die 1.5.x sie
  umgebaut hatte (Cirren gegen Stratus — genau das kann die Bewölkung nicht).
  Derselbe Fehler wie bei den Sonnenzeiten in 1.5.0, eine Zeile tiefer, und
  aus demselben Grund unentdeckt: die Testdaten trugen die Stundenwerte ohne
  Modellsuffix. Nachgestellt: an einem sonnigen Tag mit 95 % Hochbewölkung
  stand das Potenzial um 15 Uhr bei 0,19 statt über 0,9. Jetzt steht das
  Feld in `CORE`, ein Test baut die Antwort mit Suffixen, und ein zweiter
  prüft rückwärts, dass jedes Feld, das `score_hours` liest, in `CORE` steht.
- **Ein kaputter Katalog ließ die Oberfläche für immer auf „läuft“ stehen.**
  `load_spots` warf `SystemExit`; die Worker fingen `Exception`, und
  `SystemExit` ist keine. Der Thread starb still, `JOB` blieb auf „running“,
  jeder Knopf antwortete 409 bis zum Neustart — ausgelöst durch einen Tippfehler
  in genau der Datei, die die Oberfläche selbst beschreibt. `load_spots` und
  `load_config` werfen jetzt `KatalogFehler` bzw. `KonfigFehler` (beides
  `ValueError`); erst die Kommandozeile macht daraus Meldung und Exit-Code 1,
  wie bisher. Die drei Hintergrundläufe teilen sich `_starte()`, das
  „running“ in jedem Fall verlässt: bei `Exception` mit der Meldung, bei allem
  anderen (`SystemExit`, `KeyboardInterrupt`) mit „Abbruch“, und bei einer
  Arbeit, die kein Ende meldet, mit „ohne Ergebnis“ statt Dauerlauf.
- **Leaflet wurde auf der Startseite ohne Prüfsumme nachgeladen.** Die
  Prüfseite und der Report trugen `integrity`, das Nachladen für die
  Startkarte (`js.src = …`) nicht — und der Sicherheitstest sah nur
  `report.py` und nur `<script src>`-Tags. Ein verändertes Skript vom CDN
  liefe mit den Rechten der Seite, und die darf den Katalog beschreiben und
  den Server beenden. Adressen und Prüfsummen stehen jetzt einmal als
  Konstanten, beide Seiten nutzen sie, und der Test prüft beide Dateien und
  beide Wege.
- **`Content-Length: -1` hielt einen Bearbeitungs-Thread fest.** Geprüft
  wurde nur nach oben; `rfile.read(-1)` las bis zum Verbindungsende, und das
  bestimmt der Absender. Nachgestellt: keine Antwort, bis der Client aufgibt —
  und danach lief die Anfrage sogar weiter. Negativ oder unlesbar gibt jetzt
  400, zu groß weiter 413; Test mit rohem Socket.
- Neu: `REVIEW.md` — Befunde mit Datei, Zeile, Schwere und Vorschlag, nach
  Sicherheit, Berechnung, Quellen. Die Übergabe in `TODO.md` verweist darauf.
- Die 409-Antwort „Es läuft schon etwas“ stand als Bytes-Literal mit
  `\u00e4` darin — für JSON richtig, für Python ein ungültiges Escape, das
  3.12 bei jedem Prüflauf als `SyntaxWarning` meldet. Jetzt über `_antwort()`
  wie die anderen JSON-Antworten.

## 1.6.0 — 16.09.2026

- **`tools/koordinaten_check.py`: was sich ohne Karte und ohne Netz nachprüfen
  lässt.** Der Geometrielauf beantwortet schon *liegt der Punkt im Wasser?* —
  und zwar für fast alle mit Ja. Er beantwortet nicht *liegt er im richtigen
  Wasser?*, und genau das ist der Fehler, den eine gerundete Koordinate
  erzeugt. Das Werkzeug vergleicht deshalb den Spotnamen mit dem `name`-Tag der
  Wasserfläche, in der der Punkt laut OpenStreetMap liegt. Die Daten liegen
  schon da: der Overpass-Auszug je Spot steht in `cache/geom`, samt Namen. Kein
  Netz nötig.
  Vier Gruppen: **A** Name bestätigt, **B** im Wasser aber nichts zu
  vergleichen, **C** Widerspruch, **D** Pin an Land. Auf Philipps Katalog:
  17 · 56 · 13 · 13.
- Der dritte Urteilswert „unklar" ist der wichtigste Teil davon. Die halbe
  importierte Liste heißt „Parkplatz", „beacharea" oder „Stellplatz Womo" —
  ohne diesen Wert landet jeder davon als Widerspruch in der Liste, und man
  arbeitet Fehlalarme ab statt Fehler. Mit ihm bleiben 13 Fälle übrig, die eine
  Antwort verdienen.
- Was es ausdrücklich **nicht** kann: Am Meer gibt es keine benannte Fläche —
  ob der Punkt am gemeinten Strand liegt oder drei Kilometer weiter, steht in
  keinem Tag. Ein unbenannter Baggersee bleibt unbenannt. Und ob man dort
  fahren darf, parken kann oder der Einstieg taugt, sagt kein Polygon. Deshalb
  bestätigt das Werkzeug nichts von selbst; `--setze-bestaetigt` schreibt
  `verified: true` nur für Gruppe A und nur auf ausdrücklichen Aufruf.

## 1.5.5 — 16.09.2026

- **Die Karte auf der Prüfseite bleibt jetzt wirklich stehen.** `sticky` stand
  schon da — nur auf der Karte selbst, und dort nützt es nichts: Ein klebendes
  Element wandert innerhalb seines Elternelements, und das Elternelement der
  Karte war genauso hoch wie sie. Mit vier Einträgen fiel das nicht auf, mit
  104 muss man nach jedem Spot hochscrollen, um den Punkt wiederzufinden.
  Jetzt klebt die Spalte statt der Karte: Sie steht im Raster neben der Liste,
  wird durch `align-items: start` nicht gestreckt und darf deshalb die ganze
  Listenhöhe entlangwandern. Die Karte ist zugleich höher geworden
  (74 % der Fensterhöhe statt 60, maximal 600 px).

## 1.5.4 — 16.09.2026

- **Die Prüfseite zeigt jetzt auch die unbestätigten Koordinaten.** Bisher
  listete sie nur, was die Ufergeometrie beanstandet. Die 103 Spots mit
  `verified: false` — Koordinaten aus importierten Listen, die nie jemand
  angesehen hat, bei der Takeout-Liste bis etwa einen Kilometer daneben —
  standen nirgends als abarbeitbare Liste. Was man nicht abarbeiten kann,
  arbeitet man nicht ab.
  Drei Stufen mit einem Filter darüber: unbrauchbar, fragwürdig, unbestätigt.
  Die Unbestätigten sind nach Entfernung vom Startpunkt sortiert, die nächsten
  zuerst — die kennt man am ehesten selbst.
- **„Passt so" bestätigt jetzt die Koordinate** (`verified: true`) statt nur
  die Geometriewarnung abzuhaken. `geo_ok` kommt weiterhin dazu, aber nur bei
  Spots, für die es auch wirklich eine Warnung gibt; sonst stünde der Vermerk
  bei hundert Spots ohne Anlass in der Datei.
- **Eine von Hand gesetzte Nadel gilt als Bestätigung.** Wer die Koordinate
  korrigiert, hat hingeschaut — `/pruefen/setzen` setzt deshalb ebenfalls
  `verified: true`. Bisher blieb ein gerade erst korrigierter Spot unbestätigt.

## 1.5.3 — 16.09.2026

- **Der Thermikring auf der Karte schluckte den Klick.** Genau an den Spots, für
  die die Einzelheiten am interessantesten sind, ließ sich das Popup nicht mehr
  öffnen: Der orangene Ring lag über dem Punkt, war anklickbar (Leaflet macht
  jede Form standardmäßig interaktiv) und trug einen eigenen Tooltip — hatte
  aber selbst kein Popup, also passierte beim Klicken nichts. Er ist jetzt
  dreifach entschärft: eigene Kartenebene unterhalb der Punkte,
  `interactive: false`, und die Ebene selbst auf `pointer-events: none`. Der
  Name der Thermik steht dafür im Tooltip des Punktes selbst („Torbole · Ora“).
- **Neuer Abschnitt „Wann die Thermik läuft“.** Ein eigenes Stundenraster nur
  für die Thermikspots, eingefärbt nach dem Thermikpotenzial statt nach dem
  Modellwind. Drei Zustände, und der mittlere ist der eigentliche Gewinn:
  orange für das Potenzial, blass für Stunden außerhalb des Thermikfensters —
  und ein eigenes Grau für Stunden, in denen das Fenster offen ist, das
  Potenzial aber auf null steht. Dort wäre heute Thermik fällig, und der
  Gradientwind oder die Grundströmung erstickt sie. Das stand bisher in keiner
  Darstellung des Reports.
  Stunden, in denen die Annahme wirklich greift, tragen einen Rahmen — dort
  kommt der Wind im Report aus der Thermik und nicht aus dem Modell.
- Anders als die Liste „Thermikziele“ darüber hängt das Raster nicht an den
  Zielen, sondern an den Stunden: Ein Spot, an dem die Modelle keine einzige
  fahrbare Stunde sehen, steht trotzdem drin. Das ist der Sinn der Sache — an
  genau diesen Spots liegen die Modelle ja daneben.

## 1.5.2 — 16.09.2026

- **Der Thermik-Balken unterscheidet wieder etwas.** Er zeigte das Maximum über
  die Session, und das ist an einem sonnigen Tag fast immer die eine Stunde, in
  der Tagesgang, Einstrahlung und Gegenwind zufällig alle drei passen: im Lauf
  vom 16.09. standen alle fünf Thermikziele bei 96 bis 100 Prozent. Gemittelt
  wird jetzt über das ganze Thermikfenster, mit dem Tagesgang gewichtet — der
  kürzt sich damit heraus, übrig bleibt, was heute wirklich verschieden ist:
  Einstrahlung und Gegenwind. Mal der Verlässlichkeit des Spots, denn zwischen
  „quasi täglich" und „wenn alles passt" liegt der eigentliche Unterschied
  zwischen zwei Thermikzielen. Die beste einzelne Stunde steht im Tooltip.
  Im Demolauf spreizen die zehn Ziele jetzt über 34 bis 46 Prozent statt über
  vier Prozentpunkte.
- Die Aufnahmeschwelle sinkt von 0,3 auf 0,15, weil die neue Zahl auf einer
  niedrigeren Skala liegt. Die Liste ist ohnehin auf zehn begrenzt und
  absteigend sortiert; ein schwacher Kandidat erscheint nur, wenn es keinen
  besseren gibt, und der kurze Balken sagt das dann selbst.
- **Zwei unbenannte Pins aus der Jens-Dee-Liste entfernt.** `pin-46-4554-9-7903`
  lag 780 m vom Silvaplanersee entfernt und meldete denselben Malojawind;
  `pin-44-5297-6-4047` lag 4,7 km von Lac de Serre-Ponçon – Plage de
  Chanterenne und meldete dieselbe Brise. Was nur an den Pins stand, steht
  jetzt bei den benannten Spots: Jens' Beobachtung „Nordföhn blockt, Südföhn
  unterstützt" bei Silvaplana, und bei Serre-Ponçon die Koordinate des Pins —
  der Eintrag dort trägt „KOORDINATE GESCHÄTZT", der Pin war ein echter. 275
  statt 277 Spots, die zugehörigen Einträge in `geometry.json` sind mit weg.

## 1.5.1 — 16.09.2026

- **Die Modell-Plakette zeigt den Median, nicht das Maximum** (Befund 3 aus der
  Analyse des Laufs vom 16.09.). Bis 1.5.0 stand dort der größte Unterschied
  zum groben Modell innerhalb der Session — eine Zahl, die mit der Länge der
  Session wächst und nicht mit der Güte des Modells: je mehr Stunden gezogen
  werden, desto günstiger fällt die beste aus. Im Report war das messbar, der
  Median des ausgewiesenen Unterschieds lag bei Sessions bis 8 Stunden bei
  0 kn und bei Sessions über 16 Stunden bei 6 kn. Auf der Plakette steht jetzt
  der typische Unterschied, die Spitze im Tooltip.
- **Unbedeckte Stunden zählen nicht mehr als null.** Die feinen Modelle reichen
  kürzer als die globalen; die alte Rechnung setzte fehlende Stunden auf 0,0
  und mittelte sie mit. Gezählt werden nur noch die Stunden, die das
  Regionalmodell wirklich abdeckt — der Tooltip nennt, wie viele es sind.
- Was das praktisch heißt: die meisten Plaketten werden nur noch den
  Modellnamen tragen. Genau das ist der ehrliche Befund — im Lauf vom 16.09.
  brachte allein CH1 in den Alpen einen durchgehenden Zugewinn (Median +5 kn,
  86 % der Sessions über 2 kn), ICON-D2 an flachen Binnenseen nichts, und
  HARMONIE, AROME-HD und ICON-2I nur gelegentlich.
- Befund 4 (Ensemble ohne Einfluss auf die Reihenfolge) war schon in 1.5.0
  behoben.

## 1.5.0 — 16.09.2026

Aus der Analyse von Philipps Lauf über 700 km. Vier Befunde, drei davon hier
behoben; alle drei änderten die Reihenfolge der Ziele.

- **Die Tageslichtprüfung lief seit jeher ins Leere.** Sie war eingebaut und
  griff nie: fordert man mehrere Modelle an, benennt Open-Meteo *jedes* Feld
  der Antwort um — aus `sunrise` wird `sunrise_dwd_icon_seamless`. Der Zugriff
  auf `sunrise` traf daneben, der `except`-Zweig schluckte es, und die
  Sonnenzeiten blieben leer. Die Folge im Report: 467 von 1552 Sessionstunden
  (30 %) lagen zwischen 20 und 7 Uhr, 15 Sessions komplett nachts. Der Suffix
  wird jetzt mitgelesen.
- **`sonne.py` als zweite Verteidigungslinie.** Auf ein einzelnes Feld einer
  fremden API mochte ich die Nacht nicht mehr stützen. Das Modul rechnet
  Auf- und Untergang aus Breite, Länge und Datum; fehlt die Angabe in der
  Antwort, wird gerechnet, und ist sie da, prüft jeder Lauf die eigene Formel
  gegen sie und schreibt die größte Abweichung ins Log. Geprüft habe ich die
  Rechnung gegen Invarianten statt gegen eine Tabelle — wahrer Mittag am
  15. Längengrad um 11:00 UTC, Tagbogen zur Tagundnachtgleiche zwölf Stunden,
  Polartag und Polarnacht. Der erste dieser Tests hat einen Vorzeichenfehler
  bei der Länge gefunden, den man am Nullmeridian nicht sieht.
- **Der Report bietet keine Vergangenheit mehr an.** Die Vorhersage beginnt um
  00:00 des laufenden Tages, einen Schnitt bei „jetzt" gab es nicht. Der Lauf
  von 10:59 Uhr führte deshalb als erste Session des Spitzenreiters `00–10 Uhr`
  auf — und zählte die zehn Stunden in „10 h Wasser an 2 Tagen" mit.
- **Eine Session endet mit dem Tag.** Ohne Tagesgrenze verband sich eine
  stabile Wetterlage über Nacht zu einem Block von bis zu 59 Stunden, und die
  Überschrift log, weil sie nur einen Tag und zwei Uhrzeiten zeigt:
  „Do 17.09. 00–00 Uhr · 48 h". Im Demolauf ist die längste Session jetzt 12 h.
- **Das Ensemble entscheidet mit.** `ensemble` kam in score.py kein einziges
  Mal vor: die Wahrscheinlichkeit stand im Report und hatte auf die
  Reihenfolge null Einfluss — deshalb trug Platz 2 eine Session mit „0 %
  sicher". Sie geht jetzt gedämpft in den Score ein,
  `Faktor = (1 − weight) + weight · p_ride`, Standard weight 0,5: ohne jede
  Rückendeckung bleibt die Hälfte. Roh zu multiplizieren würde den Report bei
  unsicherer Lage leeren. Einstellbar unter `ensemble:` in der Konfiguration,
  `weight: 0.0` stellt den alten Zustand her. Abgefragt wird die
  Wahrscheinlichkeit jetzt für 20 statt 8 Ziele, weil sie mitentscheidet.
- Noch offen, bewusst: die Modell-Plakette nennt weiter das Maximum über die
  Session statt des typischen Unterschieds. Mit der Tagesgrenze sind die
  Fenster wieder vergleichbar lang, damit ist der gröbste Teil des Problems
  weg — die Zahl bleibt aber die günstigste Stunde.

## 1.4.3 — 16.09.2026

- **Der Routing-Fehler nennt jetzt seine Ursache.** In Philipps erstem Lauf
  über 700 km stand im Log `SSLV3_ALERT_HANDSHAKE_FAILURE` — eine Meldung, die
  nach einem kaputten Server klingt. Der Server ist in Ordnung: Apples
  mitgeliefertes Python 3.9.6 ist gegen LibreSSL 2.8.3 von 2018 gebaut und
  bringt den Handschlag mit `router.project-osrm.org` nicht zustande. Das Tool
  prüft die eigene TLS-Fassung jetzt selbst und hängt den Grund samt Abhilfe an
  die Meldung, statt den Fehler nur durchzureichen. An der Funktion ändert sich
  nichts — ohne Routing bleibt es wie bisher bei der Schätzung, sichtbar an
  „geschätzt" am Spot. Das README sagt, woran man es erkennt.

## 1.4.2 — 16.09.2026

- **Die Hauptabfrage nimmt jetzt dieselbe Gitterzelle wie die feinen Modelle.**
  Open-Meteo verschiebt eine Koordinate standardmäßig auf eine Zelle ähnlicher
  Höhe *an Land*; für einen Spot, der naturgemäß auf dem Wasser liegt, ist das
  die falsche — über Land ist der Wind wegen der Rauigkeit systematisch
  schwächer. Die hochauflösenden Modelle fragten schon `cell_selection=nearest`
  ab, die globalen nicht. Der ausgewiesene Unterschied zwischen beiden maß
  damit zum Teil nur Land gegen Wasser statt grob gegen fein.
  Aufgefallen ist das an Philipps erstem echtem Lauf: die größten Zugewinne
  standen nicht an den Talwindspots, sondern an der flachen niederländischen
  Küste — dort gibt es keine Zirkulation aufzulösen, wohl aber einen
  Land-Wasser-Unterschied. Beide Abfragen nehmen jetzt die nächste Zelle; ein
  Test hält das fest.

## 1.4.1 — 16.09.2026

- **Das Modell des Landes gewinnt, nicht das feinste.** Der erste Probelauf
  über den Katalog gab dem Gardasee das Schweizer Modell (1 km) und Zeeland das
  französische (1,5 km): beide antworten dort, weil ihre Domains weit über die
  Landesgrenze reichen. Nur ist ein Modell am Rand seines Gebiets am
  schwächsten — dort fehlen dem Anbieter die Stationen, gegen die er rechnet,
  und Randartefakte sind ein bekanntes Problem (MeteoSwiss beschneidet die
  eigene Domain aus genau dem Grund um 20 km). Jetzt zählt erst die Zuständigkeit,
  dann die Auflösung: Gardasee und Comer See bekommen ICON-2I, Zeeland
  HARMONIE, Walchensee ICON-D2, Silvaplana weiterhin ICON-CH1.
- **Die Plakette zeigt den Unterschied zum groben Modell** (etwa „ICON-2I
  +9 kn"). Das ist die eigentliche Auskunft: deckt ein Modell den Punkt nur ab,
  oder trifft es die Zirkulation auch? Bei der Ora steht dort ein zweistelliges
  Plus, an einem flachen Küstenstreifen nahe null.
- Die gemerkte Zuordnung trägt jetzt die Nummer der Auswahlregel; ändert sie
  sich, wird neu geprüft statt mit veralteten Zuordnungen weitergerechnet.

## 1.4.0 — 16.09.2026

**Hochauflösende Regionalmodelle.** Die globalen rechnen auf 7 bis 25 km und
mitteln genau die Täler und Küstenlinien weg, in denen Ora, Maestral und
Malojawind entstehen. Wingscout fragt jetzt zusätzlich Modelle mit 1 bis 2,5 km
ab und überschreibt den Wind für die Stunden, die sie abdecken — zwei bis drei
Tage, danach gelten wieder die globalen. Im Report steht bei jeder Session,
welches Modell sie geliefert hat.

- `wingscout/sources/highres.py` mit sieben Modellen von MeteoSwiss, DWD,
  Météo-France, ARPAE, KNMI, GeoSphere und DMI.
- Open-Meteo dokumentiert keine Modellgrenzen und antwortet außerhalb der
  Domain mit HTTP 400 — bei einer Sammelanfrage reißt ein unpassender Punkt
  alle anderen mit. Abgelehnte Gruppen werden deshalb halbiert, bis die
  Ausreißer feststehen, und die Zuordnung wird je Spot in `cache/highres.json`
  gemerkt.
- `tools/highres_probe.py` klärt die Abdeckung einmal vorab.
- Abschaltbar über den Haken „Hochauflösende Modelle", `wind.highres` oder
  `--no-highres`.
- `cell_selection=nearest` statt der Voreinstellung: im Gebirge schiebt „land"
  den Punkt auf eine Zelle ähnlicher Höhe und landet damit am Hang statt auf
  dem Wasser.

## 1.3.0 — 15.09.2026

**Thermische Winde als eigene Datenquelle.** An Ora, Malojawind und Maestral
versagen die Standardmodelle, weil ihr Gitter die Täler und Küstenlinien
wegmittelt, die diese Zirkulation erzeugen.

- **73 Spots** tragen jetzt hinterlegtes Thermikwissen mit Eigenname, Monaten,
  Zeitfenster, Richtung, Stärke, Verlässlichkeit und **Quelle** — aus einer
  Recherche über Gardasee, Comer See, Engadin, Alpen- und Voralpenseen,
  französische Stauseen, Adria, Golfe du Lion und Nordsee. Vorher waren es 4.
- **`wingscout/thermik.py`**: aus der festen Zahl je Spot wird eine
  wetterabhängige. Eingestrahlte Energie seit Sonnenaufgang, Tageszeit und
  Gegenwind gehen ein. Die Antwort auf den Gegenwind ist dabei nicht fallend,
  sondern hat ein Maximum bei schwachem Gegenwind (Arritt 1993) und bricht
  ab 7 bis 9 kn ab (Centro Meteo Ligure, weeronline.nl). Jede Schwelle steht
  mit ihrer Quelle im Modul.
- **Thermikziele als eigene Liste** im Report, direkt unter den besten drei,
  sortiert nach dem Thermikpotenzial statt nach dem Gesamtscore.
- **Kartenebene „Thermische Winde"**: orangener Ring um jeden Spot mit
  hinterlegtem Wissen.
- Die Globalstrahlung wird jetzt mitgeholt (`shortwave_radiation`).
- Wo keine Quelle eine Stärke nennt, wird **keine angenommen** — 25 der 73
  Spots stehen nur als Kandidat in der Liste.

## 1.2.2 — 15.09.2026

- **Ein Klick auf einen Spot zeigt wieder die Einzelheiten.** Der Sprung zu
  Windy bei jedem Klick war zu grob: das Popup mit Stundenband, Fahrt und
  Stellplätzen ist das, wofür man klickt. Der Schalter „Klick öffnet Windy
  statt der Details" bleibt, ist aber aus.
- Dafür ist der **Name im Popup selbst ein Windy-Link** — ein Klick für die
  Einzelheiten, der zweite auf den Namen für die große Windkarte.

## 1.2.1 — 14.09.2026

- **Klick auf einen Spot in der Karte öffnet Windy** an dieser Koordinate.
  Zusätzlich, nicht statt: das Popup mit Stundenband, Fahrt und Stellplätzen
  geht weiterhin auf und wartet, wenn man aus dem Windy-Tab zurückkommt. Der
  Schalter „Klick öffnet Windy" in der Werkzeugleiste ist von Haus aus an.

## 1.2.0 — 13.09.2026

- **Seite „Koordinaten prüfen"** in der Oberfläche. Die Fundliste des
  Geometrielaufs stand bisher nur im Protokoll: man sah sie einmal, konnte
  nichts damit tun, und beim nächsten Start war sie weg. Jetzt gibt es eine
  eigene Seite mit Karte — Nadel ins Wasser ziehen, übernehmen, die Geometrie
  wird sofort neu gerechnet und sagt, ob es jetzt passt. „Passt so" nimmt einen
  Spot dauerhaft aus der Liste (`geo_ok: true`).
- `wingscout/spotedit.py`: einzelne Felder in `spots.yaml` ändern, ohne die
  Datei neu zu schreiben. Über PyYAML zu gehen hätte sämtliche Kommentare
  gekostet, und der Katalog besteht zu einem guten Teil aus Kommentaren.

## 1.1.1 — 13.09.2026

- **Die Warnliste nach dem Geometrielauf meldete das Falsche.** Sie nahm
  `open_share < 0.15` und nannte alles davon „Koordinate prüfen": 67 Spots, von
  denen 39 schlicht kleine Baggerseen waren — auf 800 m Wasser ist keine
  Richtung offen, das ist kein Fehler. Gleichzeitig fehlten 25 Spots, deren Pin
  kilometerweit danebenlag, die aber viel offenes Wasser hatten. Jetzt
  entscheidet die gemessene Rose statt der Statusmeldung, und die Liste ist
  zweigeteilt: 13 unbrauchbar (höchstens 100–200 m Wasser in jeder Richtung),
  23 zum Nachsehen (mehr als 1 km vom Pin versetzt), 227 unauffällig.
- Der Status „kein Wasser gefunden" stand auch dann da, wenn die Rose 17 km
  Anlauf gemessen hatte — der Snap war gescheitert, das Wasser aber da. Der
  Status behauptet jetzt nichts mehr, was die Messung widerlegt.
- Nach einem Lauf mit Fehlschlägen steht da, dass ein erneuter Start bei den
  offenen Spots weitermacht. Overpass ist zeitweise überlastet; das ist der
  Normalfall, kein Defekt.

## 1.1.0 — 13.09.2026

Zusammenarbeit: das Projekt ist jetzt zu zweit bedienbar, ohne dass einer dem
anderen die Arbeit überschreibt.

- **Konfiguration getrennt.** Versioniert ist nur `config.example.yaml`; die
  persönliche `config.yaml` (Startpunkt, Gewicht, Material) entsteht beim
  ersten Start daraus und wird ignoriert. Sie kollidiert damit nie beim
  Aktualisieren — vorher hätte jeder Pull die Werte des anderen mitgebracht.
- **Prüflauf auf GitHub** (`.github/workflows/tests.yml`): dieselben 132 Tests
  bei jedem Push auf `main` und jedem Pull Request, plus die Kontrolle, dass
  keine persönlichen Dateien versioniert sind.
- **`tools/veroeffentlichen.sh`** — prüfen, festschreiben, hochladen, in
  dieser Reihenfolge. Mit `--version X.Y.Z` zusätzlich Versionsnummer und Tag.
- **`tools/aktualisieren.sh`** — holen, ohne eigene Arbeit zu verlieren:
  beiseitelegen, rebasen, zurückholen, prüfen. Bei jedem Fehlschlag steht da,
  wie man zurückkommt.
- Beides auch als Doppelklick: „Auf GitHub veröffentlichen" und „Neuen Stand
  holen".
- **Merge-Treiber für `geometry.json`** (`tools/merge_geometry.py`): zwei
  unabhängige Geometrieläufe ergänzen sich, statt einen Konflikt zu erzeugen.
- **`MITARBEIT.md`**, CODEOWNERS und eine Pull-Request-Vorlage.
- **Läuft jetzt unter Python 3.9**, also unter der Fassung, die Apple auf dem
  Mac mitliefert. Vorher scheiterte dort schon das Einlesen einzelner Dateien,
  weil `str | None` in einer Signatur sofort ausgewertet wird — die Meldung
  sah nach einem kaputten Test aus statt nach einer alten Umgebung.
  `from __future__ import annotations` steht jetzt in jeder Datei; der volle
  Prüflauf ist unter 3.9.23 durchgelaufen. Der Prüflauf auf GitHub fährt 3.9
  und 3.12 nebeneinander, damit das so bleibt.

## 1.0.0 — 13.09.2026

Erste vollständige Fassung: Katalog, Bewertung, Oberfläche, Karte, Tests und
Sicherheitsprüfung sind beisammen und laufen ohne Fremdpakete außer PyYAML.

### Suche und Bewertung

- **Drei Wettermodelle** statt eines (ICON, GFS, ECMWF in einem Aufruf).
  Uneinige Stunden werden abgewertet und im Report markiert.
- **Ensemble-Wahrscheinlichkeit** aus ICON-EPS (40 Rechnungen): Anteil der
  Rechnungen über der Fahrgrenze, dazu die Spanne. Das Ensemble liegt auf
  einem gröberen Gitter, deshalb wird daraus nie ein Windwert abgeleitet.
- **Ufergeometrie** aus OpenStreetMap: Anlauflänge über Wasser in 36
  Richtungen, daraus ablandig/sideshore/auflandig und die Wellenhöhe nach der
  fetch-begrenzten SPM-Beziehung. Von Hand gepflegte Sektoren haben Vorrang.
- **Echte Fahrzeiten** über OSRM statt Luftlinie × 1,22; fällt OSRM aus, wird
  wieder geschätzt und das im Report gesagt.
- **Stellplätze mit Hund** über Park4Night — harter Filter, kein Bonus.
- **Amtliche Wetterwarnungen** (MeteoAlarm) und Schutzgebiete im Umkreis.
- **Thermik-Erfahrungswerte** für Spots, an denen kein Modell die Lage sieht
  (Ora am Gardasee, Malojawind), sichtbar als Annahme.
- **Tiden, Neoprenempfehlung, Plan B** je Ziel.

### Katalog

- 277 Spots, davon 165 aus einer Google-Takeout-Liste übernommen.
- Neue Spots lassen sich in der Oberfläche als Text oder Datei einwerfen
  (GPX, KML, GeoJSON, CSV); die Ufergeometrie wird auf Wunsch gleich
  mitgerechnet und bleibt dauerhaft gespeichert.
- 138 von 277 Spots haben ihre Ufergeometrie; der Rest steht in `TODO.md`.

### Oberfläche

- **Von vierzig sichtbaren Bedienelementen auf neun.** Vorn steht eine Frage
  (von wo aus?) und drei Voreinstellungen — Spontan, Wochenende, Mit
  Übernachtung —, darunter ein Knopf. Alles Feinere liegt hinter drei Klappen
  und behält seine Werte.
- Startpunkt als Koordinate, über die Browser-Ortung oder per Klick auf eine
  Karte.
- Fragezeichen mit Kurzerklärung an Mindestgüte, Böigkeit und
  Kabbel-Aversion.
- Beenden-Knopf (zweimal drücken), damit das Terminal nicht offen bleibt.

### Report

- Reihenfolge: Karte, die besten drei Ziele, Stundenraster, alle weiteren
  Ziele hinter einer Klappe.
- **Karte als eigene Ansicht**: Ebenen einzeln schaltbar, Stellplätze mit
  Hund als eigene Ebene, Stundenband im Popup, Namen der Treffer einblendbar,
  Koordinate zum Kopieren, Luftlinie zum Startpunkt, Vollbild.
- **Stundenraster in zwei Lesarten**: Güte (lohnt sich die Stunde?) und
  Knoten (welcher Wing?). Die Knotenskala ist rot/orange/grün/orange/rot mit
  eigenem Dunkelrot über 30 kn; grün ist immer das Wohlfühlband aus der
  Oberfläche.
- Spotname im Raster führt auf Windy, die Kilometerangabe auf die Route.

### Struktur

- 127 Tests ohne Fremdpakete, `tools/check.sh` als Prüflauf vor jedem Commit.
- Sicherheitsprüfung mit Befunden und Fixes in `SICHERHEIT.md`: CSRF über
  Origin/Host, XSS in Karten-JSON und Popups, SRI für Leaflet, Pfadprüfung
  im Cache.
- `ENTWICKLUNG.md` für Aufbau und Git-Regeln, `TODO.md` als maßgebliche
  Aufgabenliste.

### Behobene Fehler

- Der Report stand auf Englisch (`Tue 15.09.`), weil `strftime("%a")` der
  Locale des Prozesses folgt und die bei einem doppelgeklickten Python „C"
  ist. Jetzt feste deutsche Kürzel.
- Die Fahrzeit-Notiz lief zweimal durch die Escaping-Funktion und stand als
  `<span title=…>` wörtlich im Report.
- `run.py` hat seine Kommandozeilenargumente ignoriert — `run.py --demo` lief
  gegen die echte API.
- Der Prüflauf vor dem Commit lief mit `--schnell` und übersprang dabei
  ausgerechnet die Tests der Oberfläche.
- Overpass-Antworten von über 100 MB, fehlende Multipolygon-Ringe und ein
  falsch gewähltes Gewässer beim Versetzen ins Wasser ließen die
  Ufergeometrie scheitern.
- Ein einzelner HTTP-Fehler von Open-Meteo brach den ganzen Lauf ab; jetzt
  wird wiederholt und Teilausfall toleriert.
