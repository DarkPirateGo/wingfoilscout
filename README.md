# Wingfoilscout

*This guide in: **English** · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md)*

Finds wingfoil sessions around you and writes an HTML report:
**where the wind blows, when, with which wing — and whether the drive is worth it.**

It combines three weather models (plus an ensemble for reliability) with
knowledge about 278 spots: wind sectors, shoreline geometry from
OpenStreetMap, tides, thermals, drive times. It runs locally on your own
computer, with no account and no third-party packages except PyYAML. All wind
speeds are in **knots**. The interface speaks English, German, French and
Spanish.

<p align="center">
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/bilder/en/search-dark.png"><img src="docs/bilder/en/search-light.png" width="250" alt="Search: starting point, start time, favourites and presets"></picture>
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/bilder/en/destinations-dark.png"><img src="docs/bilder/en/destinations-light.png" width="250" alt="A favourite, then the best three destinations"></picture>
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/bilder/en/grid-dark.png"><img src="docs/bilder/en/grid-light.png" width="250" alt="Hourly grid: every spot, hour by hour"></picture>
</p>
<p align="center"><sub>Example view with made-up weather data ·
<a href="https://darkpiratego.github.io/wingfoilscout/">Website</a> ·
<a href="https://darkpiratego.github.io/wingfoilscout/demo.html">Example report</a></sub></p>

Until version 2.0 the project was called **Wingscout**; older entries in the
changelog and in the review and audit reports still carry that name.
Internally the Python package is still called `wingscout` — that's why the
commands below look the way they do.

The current version is in `wingscout/__init__.py`, under the logo at the right of the tab bar on every page and in the footer of every report · how Wingfoilscout decides: [`SCORING.md`](SCORING.md) · changes in [`CHANGELOG.md`](CHANGELOG.md) (older entries in German) · open findings in [`REVIEW.md`](REVIEW.md) (German, historical) · licence: [PolyForm Noncommercial 1.0.0](LICENSE) (© 2026 DARK)

---

## Installation

### On a Mac, with Terminal (recommended)

Two lines to paste into **Terminal** — you'll find it under Applications →
Utilities, or type “Terminal” into Spotlight:

1. **Once per Mac: Apple's command line tools.** They bring Python and
   `git`:

   ```bash
   xcode-select --install
   ```

   A window asks whether to install them: click **Install**, accept the
   licence and wait until it says the software was installed — that takes a
   few minutes. If Terminal answers that the tools are already installed, go
   straight on.

2. **Fetch Wingfoilscout and start it:**

   ```bash
   cd ~ && git clone https://github.com/DarkPirateGo/wingfoilscout.git && cd wingfoilscout && bash "Wingfoilscout starten.command"
   ```

   Paste the whole line at once; each part only runs if the one before
   worked. It creates the folder `wingfoilscout` in your home folder,
   installs PyYAML the first time and opens the interface in the browser.

After that, start Wingfoilscout with a double-click on **“Wingfoilscout
starten”** (German for “Start Wingfoilscout”) in that folder, and get new
versions with a double-click on **“Neuen Stand holen”** — all double-click
files are explained [below](#double-click-files). What `git` fetched didn't
come through the browser, so macOS doesn't block it.

You choose the starting point in the interface. You enter your gear once in
`config.yaml` — a text file in the same folder that is created from
`config.example.yaml` on the first start.

### On a Mac, without Terminal

1. On the [release page](https://github.com/DarkPirateGo/wingfoilscout/releases/latest),
   download **Source code (zip)** under “Assets” and unzip it with a
   double-click, if the browser hasn't done that already.
2. In the folder, double-click **“Wingfoilscout starten”**. The first time,
   macOS refuses and says Apple could not verify that the file is free of
   malware — it comes from the internet and isn't signed by a developer
   registered with Apple. Click **Done**.
3. Open **System Settings → Privacy & Security** and scroll down to
   **Security**: there it says that “Wingfoilscout starten.command” was
   blocked. Click **Open Anyway**, confirm with your password if asked, and
   click **Open** when the warning comes back. Up to macOS 14, right-click
   the file → **Open** is enough.
4. If macOS asks whether Terminal may access the Downloads folder, allow it.
   If it offers to install the **command line developer tools**: install
   them — they bring Python —, wait until they're done and double-click
   again; the start script recognises this case and says so.
5. The first start installs PyYAML; then the interface opens in the browser.

Every double-click file needs step 3 once, “Wingfoilscout fürs iPhone
starten” included. New versions come only as a new ZIP this way: copy
`config.yaml`, `tagebuch.json`, `modellguete.json`, `ui_defaults.json`,
`favoriten.json` and `sprache.txt` from the old folder into the new one. Spots you added yourself
stay in the old folder's `spots.yaml` — the Terminal way keeps them when
updating.

### By hand, or on Windows and Linux

With Python 3.9 or newer and `git`:

```bash
git clone https://github.com/DarkPirateGo/wingfoilscout.git
cd wingfoilscout
python3 -m pip install -r requirements.txt      # PyYAML only
tools/install-hooks.sh                          # optional: check run before every commit
python3 -m wingscout.webui                      # start: opens the interface in the browser
```

On a Mac, Python 3.9 and `git` come with Apple's command line tools (step 1
above). No other dependencies apart from PyYAML: the weather data come in via
the standard library, and the report is a single HTML file. On Windows,
`wingfoilscout.bat` starts the interface (untested).

Apple's Python does have one limitation, though: it is built against LibreSSL
2.8.3 from 2018. With it, no connection to the routing server can be made; the
log reports `SSLV3_ALERT_HANDSHAKE_FAILURE`, and the drive stays an estimate
from straight-line distance times a factor. Weather and report are not
affected. To find out whether this applies to you, run

```bash
python3 -c "import ssl; print(ssl.OPENSSL_VERSION)"
```

If it says *LibreSSL*, a current Python fixes it (`brew install python` or the
installer from python.org, then a **new** terminal window); that comes with
OpenSSL 3. If it says *OpenSSL*, all is well.

Then adjust `config.yaml`: `rider.home` to your own starting point,
`quiver.wings` to your own gear. The file is commented throughout; everything
in it is there to be changed.

### Double-click files

The folder contains a few files to double-click in the Finder on a Mac, plus
`wingfoilscout.bat` for Windows. They keep their German names; this README
refers to them without the `.command` extension.

| File | In English | What it does |
|---|---|---|
| `Wingfoilscout starten.command` | Start Wingfoilscout | opens the interface in the browser; installs PyYAML first if it's missing |
| `Wingfoilscout fürs iPhone starten.command` | Start Wingfoilscout for iPhone | the same, but the interface can also be reached from an iPhone on the same Wi-Fi (see [On the iPhone](#on-the-iphone)) |
| `wingfoilscout.bat` | — | Windows: opens the interface in the browser |
| `Neuen Stand holen.command` | Get the latest version | fetches the current state from GitHub without losing your own changes, then runs the tests (needs a `git` clone) |
| `Auf GitHub veröffentlichen.command` | Publish to GitHub | check run, commit and push — for contributors |
| `Tests ausführen.command` | Run tests | the full check run with all tests (`tools/check.sh`) |
| `Ufergeometrie berechnen.command` | Compute shoreline geometry | one-off run of `build_geometry.py` (see [Shoreline geometry](#shoreline-geometry)) |
| `Prüfstand.command` | Benchmark | runs `tools/pruefstand.py` (see [The benchmark](#the-benchmark--is-it-still-right)) |

## Usage

**Without a terminal:** double-click **“Wingfoilscout starten”** in the Finder
(on Windows: `wingfoilscout.bat`). An interface opens in the browser. Up front
there are just two questions — **Starting from?** and **Starting when?** —,
your [favourites](#favourites), and below them three presets:

| | Days | Nights | Radius |
|---|---|---|---|
| **Spontaneous** | 2 | – | 250 km |
| **Weekend** | 3 | – | 500 km |
| **Overnight trip** | 4 | 2 in a row | 1000 km |

Tap one, press **“Find spots”**, and the report appears below. That's all you
usually need to do. The days count from now — or from the start time, if you
set one (see [Start time](#start-time)).

Everything more detailed sits behind three collapsible panels, which keep
their values:

- **Fine-tune the search** — period, radius, nights, drive time, what counts
  as a session, temperature and gustiness limits, chop aversion, seagrass,
  water types. If you change something here, the preset is deselected and a
  line below shows what currently applies.
- **Data sources** — shoreline geometry, routing, ensemble, overnight spots,
  marine, warnings, demo mode. This is also where you find the **“Compute
  missing”** button for the shoreline geometry, with the number of spots still
  missing next to it.
- **Add spots** — see below.

Four fields carry a question mark with a short explanation: **Radius** (a
driving distance, not a straight line — see [Drive time](#drive-time-routed-not-estimated)),
**Minimum rating**, **Gustiness max.** and **Chop aversion**. Their names
don't explain themselves, and in the report they later appear as a number.

**“Save as default”** stores your inputs as the new starting values (in
`ui_defaults.json`; your commented `config.yaml` stays untouched).

**Language:** the interface and the report are available in English, German,
French and Spanish. The switcher (DE · EN · FR · ES) sits next to the logo at
the top right — on phones in the page footer. Your
choice is stored in `sprache.txt` in the Wingfoilscout folder and applies to
every page straight away — the Destinations tab included: each search stores
its report in all four languages (in `cache/report/`), so switching needs no
new search. Only the file `report.html`, the one you can AirDrop to your
phone, stays in the language the search ran in; a report from before 2.3.0
exists in one language only until the next search. Until you pick one, Wingfoilscout follows
your browser: the first of the four languages in your browser's order of
preference — English if the browser asks for none of them, German if it sends
no language at all. The environment variable `WINGSCOUT_SPRACHE` (`de`, `en`,
`fr` or `es`) overrides both. Numbers, dates and times appear in the form of
the language (in English 4.2 and 20 Sep 2026, 19:09). The command line and
the terminal windows of the double-click files choose their language on their
own, see [Command line](#command-line).

**Help in the app:** the **?** button at the top right of every page (on phones
next to “Quit”) opens this guide and the illustrated page “How Wingfoilscout
calculates” — in the language you chose.

One limitation: what comes from data rather than from the program stays in its
original language, mostly German — spot names, notes and the other texts in
the catalogue (`spots.yaml`), and some place and area names from
OpenStreetMap.

After **“Neuen Stand holen”** (getting the latest version), an interface that
is already open keeps running the old code until you quit Wingfoilscout and
start it again — every page then shows a bar saying so. And the Review tab
shows its last result when you open it; if that is older than the last search
or was computed with an earlier version, a note above it says so, and “Check”
recomputes it.

### Starting point on the road

At the top of the interface it says **Starting from?**. Left empty,
Wingfoilscout calculates from your home, `rider.home` in `config.yaml` (the
template has Hamburg city centre as a placeholder). If you enter something,
radius, distance and drive time count from that point — that's the case when
you are already on the road and want to know what's possible from *here*.

Recognised formats are decimal degrees (`51.7625, 3.854` — decimal comma or
point), degrees/minutes/seconds (`51°45'45"N 3°51'14"E`) and a pasted Google
Maps link. A place name (“Hamburg”) is none of these: since 1.19.0
Wingfoilscout rejects it before starting and says what works — before that,
the search silently ran from home. The banner at the end names the starting
point that was used.

There are also two buttons. **“Map”** opens a map: click into it or drag the
pin, done — that's the way that always works, as long as you have a
connection. **“Here”** asks the browser for your location; that's more
convenient, but depends on whether the operating system provides a position.
Safari on macOS sometimes doesn't answer at all here (timeout), typically when
Wi-Fi is off — Macs locate themselves via the Wi-Fi networks around them, not
via GPS. The message under the button tells you what the cause was.

The starting point is deliberately **not** stored by “Save as default” — it
applies to today and here, not to the next start. On the command line, the
same works with `--start "51.7625, 3.854"` and optionally
`--start-name Brouwersdam`.

### Start time

Below the starting point it asks **Starting when?**. Left empty, the search
starts now, as it always has. If you pick a date and time — say Saturday
9:00 —, the days of the preset count from that day, and the hours before it
are greyed out in the hour grid as “before the chosen start”: on a Wednesday
you can look at the weekend alone.

The forecasts reach 16 days from today; the field says how far that is. If
the start plus the days go beyond it, the search shortens the period and says
so in the log. The time is that of your computer; for each spot it is
converted to local time there, like every time in the report. **“Now”**
clears the field. Like the starting point, the start time is **not** stored
by “Save as default”. On the command line: `--ab "2026-10-10 09:00"` (or
`10.10.2026 09:00`, or just the date).

### Favourites

Below the start time it says **Favourites**: your favourite spots, which every
search looks at first. Type part of a name — “edersee”, “tarifa”; accents
don't matter, “etang” finds “Étang de Leucate” — and pick the spot from the
list that opens (arrow keys and Enter work too). It lands in your list as a
small tag; its × takes it out again. Up to ten, in the order you add them.

Once the list has an entry, the switch **“Show favourites first”** appears
(on to begin with). With it on, every search also computes your favourites —
**even outside the radius and despite the filters** (season, water types,
seagrass, dogs …) — and the report starts with them: **Favourites → the best
three → map**. Each favourite gets the same card as a destination of the
search, with a ★ instead of the rank and a badge: **Rank 4** if it is also
among the destinations of the search, or **outside the search**, with the
reason as a tooltip (“2799 km — outside the 600 km radius”, “out of season”).
A favourite without a session in the period gets a flat card that says why —
“At most 8 kn (Sat 10 Oct 14:00) — your quiver starts at 10 kn”, or, where
there would be wind, what rules those hours out, in the words of the hour
grid (“water 9 °C below your limit of 12 °C”, “outside the tide window …”) —
plus the links to Windy, the route and the map. Among the best three and the
further destinations, a favourite carries a ★ before its name.

The best three, the map and the hour grid stay the normal search: favourites
outside it don't appear there and don't push anything out. They are fetched
and computed in addition — one reason the list stops at ten.

Every change is stored straight away, in `favoriten.json` in the
Wingfoilscout folder — personal like the logbook, not versioned, and not part
of “Save as default”. Switch “Show favourites first” off and the search runs
without them; the list stays. On the command line, `--favoriten` alone uses
the list from the interface, `--favoriten brouwersdam,silvaplana` the spot IDs
given (the ID of a spot is in `spots.yaml`).

### Add spots

In the **Add spots** panel. One line per spot, in any notation you come across
on the road:

```
Hardtsee; 49.17008, 8.61477
49.17008, 8.61477 Hardtsee
Bostalsee; 49.56831, 7.07964; reservoir
https://www.google.com/maps/@51.7625,3.854,15z
```

Name before or after, water type optional as the last field (`sea`,
`lagoon`, `lake`, `reservoir`). Degrees/minutes/seconds are recognised as
well. The file field also accepts the usual export formats: **GPX**
(waypoints), **KML** from Google My Maps (placemarks), **GeoJSON** from Google
Takeout and **CSV** with columns for latitude and longitude. A KMZ file is a
zipped KML — unzip it and load the `doc.kml` inside.

A word of warning about Google lists from Takeout: their CSV often contains
only the title, note and a Maps address with a place ID, but no coordinate. If
the link contains a position (`.../@51.7625,3.854,15z`), it is used; otherwise
the line is skipped and counted. A place ID can't be turned into a coordinate
without querying Google, and nothing gets guessed here. Points less than 300 m
from an existing spot are skipped and reported.

The spots go into `spots.yaml` and count from the next search on. If the
**Compute shoreline geometry right away** checkbox is ticked, the geometry is
fetched for the new spots straight afterwards — about a quarter of a minute
per spot.

For anything left open, there is the **Compute missing** button under Data
sources. Next to it, it says how many spots don't have a geometry yet. The run
works through the catalogue in order, saves after every spot and shows its
progress in the same log; cancelling is harmless, and the next click carries
on with the open ones. The script `build_geometry.py` does the same and is
still there for the command line — but it's no longer needed.

Three things get guessed in the process, and you should check them: the water
type (default `lake`), the bottom (`shallow: none`, `seagrass: none`) and the
country code, which comes from rough country boxes and can be wrong near
borders — it only controls which warning feed applies. The wind sectors stay
empty; the shoreline geometry supplies them.

### Suggest a spot for everyone

Spots you add yourself stay on your computer. To get one into the catalogue
for everyone, use **“Suggest it for everyone”** — in the **Add spots** panel
and below **“Add a new spot”** in the Catalogue tab. It opens a form on
GitHub; in the Catalogue, the form comes filled in with what you entered
above it (name, coordinate, note). Next
to every spot in the catalogue, **suggest a correction** does the same for a
spot that is already listed. You need a free GitHub account, and nothing is
sent until you submit the form there. It asks for the water, good wind
directions, what others should know and where your knowledge comes from. The
form also opens directly:
https://github.com/DarkPirateGo/wingfoilscout/issues/new?template=spot.yml

Every suggestion is checked by hand and goes into the catalogue of the next
version — everyone who updates gets it. By submitting it you agree that it
may be published under Wingfoilscout's licence and that DARK may also use it
under other terms ([CONTRIBUTING.md](CONTRIBUTING.md)).

### Check coordinates

Under **Data sources** there is a **“Check coordinates”** button as soon as
there is something to check; likewise the tab of the same name at the top
(since 1.16.1 only then — if nothing is open, it disappears, and the page
remains reachable at `/pruefen`). It opens a page of its own: a map on the
left, on the right the spots that need looking at. A filter above the list
separates three levels:

- **Unusable** — at most 100 to 300 m of water in *every* direction. The pin
  is then almost certainly on land, in a car park or in the wrong body of
  water.
- **Questionable** — shifted more than a kilometre from the pin into the
  water. Usable, but the pin is off.
- **Unconfirmed** — `verified: false`: the coordinate comes from an imported
  list and nobody has ever looked. For the Takeout list it is up to about a
  kilometre off, because the column there was rounded. That's not an error,
  just an open question — these spots are sorted by distance from the starting
  point, nearest first, because those are the ones you are most likely to know
  yourself.

Both buttons write to `spots.yaml`: **“Apply”** sets the new coordinate,
**“Looks right”** confirms the existing one. Both set `verified: true` —
whoever placed the pin themselves or looked at the point has checked it.
`geo_ok: true` is only added where there actually is a geometry warning.

What matters is what is *not* on the list: an 800-metre quarry lake has no open
water in any direction, and that is not an error. An earlier version reported
exactly such spots and missed the truly wrong ones instead — a list that
reports the wrong things stops being read after the second time.

Corrections happen on the map: click the spot, drag the pin into the water or
click into it, **Apply**. The coordinate goes into `spots.yaml` (together with
`verified: true`), the old shoreline geometry is discarded and recomputed
straight away — after a few seconds it shows how much fetch the spot now has.
If the coordinate is right after all, **Looks right** removes the spot from
the list for good (`geo_ok: true` in the catalogue).

The comments in `spots.yaml` are preserved: writing happens at the text level,
not via a YAML round trip.

### Catalogue — all spots at a glance

The **Catalogue** tab at the top of every page shows all spots Wingfoilscout
knows: search by name, ID, region and note; filters by country, water type and
feature (unconfirmed, with thermal, with shore break, with Instagram finds,
Instagram not yet searched); sortable by name, country, water type and
distance from the starting point. Clicking a row jumps to the spot on the map;
the map always shows the current selection. Each spot comes with its badges
(confirmed, thermal wind, shore break, access, dogs) and links to Windy,
OpenStreetMap and Instagram.

At the bottom of the page: **“Already listed?”** — type in a coordinate or a
name, and the page tells you whether a spot nearby is already in the catalogue
(up to 300 m: “practically the same point”, up to 3 km: “nearby”). That's how
you avoid entering a spot twice.

**You can maintain the catalogue here too.** Below that, **“Add a new
spot”**: name, coordinate, water type, country (empty means guess), note,
comment — and, if you like, the shoreline geometry is computed right away. If
there is already a spot closer than 300 m, the page says so and only adds the
new one on “Add anyway”. Each row has three small actions: **rename** (the
name changes, the ID stays — shoreline geometry, Instagram snapshot and
benchmark are tied to it), **move** (a pin appears on the map: drag it or
click into the map, then “Apply” — the same as on the check page, with
recomputed shoreline geometry and `verified: true`) and **delete** (with a
confirmation prompt; the spot disappears from `spots.yaml`, `geometry.json`
and `instagram.json`, and its block appears in the log in case it was a
mistake). Everything is written to `spots.yaml` at the text level, and the
comments stay; while a search or a geometry run is in progress, the page
waits (409).
Next to the actions, **suggest a correction** opens the
GitHub form for that spot (see [Suggest a spot for everyone](#suggest-a-spot-for-everyone)).

### Your comment on every spot

Wherever a spot appears, your own comment is shown with it and can be written
right there: in the catalogue, on every destination in the report, in the map
popup, on the check page and in the Review — and straight away when you add a
new spot. “Write a comment” opens a field, “Save” writes it as `comment` to
`spots.yaml` (multi-line, up to 2000 characters; saving it empty removes it).
The Catalogue tab also finds it via the search.

The comment is something different from the `notes`: the note describes the
spot (origin, rules, what the source says), the comment is your own
experience — where to park, where to get in, what it was like last time. It
doesn't filter and doesn't go into the score.

One limitation: the report is a file. As long as it is shown in the interface
(below the search, or via “open in new tab”), the comment is saved to the
catalogue; if you open `report.html` directly as a file, the field tells you
there is no program behind it. A report shows the state of the catalogue at
the time of its search — a new comment appears immediately on the page and in
the next report.

### Review — how good was the last forecast?

The **Review** tab takes the ten best destinations of the last search and, for
the last few days **including today, up to the current hour** (number
selectable, 1 to 14, default 2), puts the archived forecast next to the
measured winds of the nearest weather station — hour by hour, as a curve and
as a table, with mean error, bias and direction hit rate per spot. The
forecast runs through the same scoring as in the report (regional model,
`wind_factor`, thermal assumption); so you see what Wingfoilscout would have
said, and what actually happened.

What you need to know is also on the page: the archived forecast is the one
with the shortest lead time (“today for today”, from Open-Meteo's archive),
not the one from three days earlier; for the current day it is this morning's
forecast, from the running query. A station measures over land, the spot is
over water — a few knots of difference are normal.

Stations come from DWD (Germany), from KNMI and Rijkswaterstaat (Netherlands —
Rijkswaterstaat measures on the water, at measuring posts and coastal
stations), from GeoSphere (Austria), DMI (Denmark, since 1.14.0) and
Météo-France (France); the search crosses borders, so a Belgian spot gets the
nearest Dutch station. On top of that come Windguru stations, if they are
listed with their API password in `config.yaml` (`stationen: windguru:`,
template in `config.example.yaml`) — without a password, Windguru doesn't hand
out measurements. **“Station up to … km”** (default 30, at most 100) sets how
far the station may be from the spot; the nearest one that has almost all
hours up to now (90 %) is taken, and if none has that many, the nearest one
with almost as many as the best (since 1.14.1 — before that, the nearest one
with any values at all won, even if they were only from the day before
yesterday). The station that delivered is shown with its distance next to the
result, a closer station that was passed over with “instead of …” — the
farther away, the less it says about the spot.

And how close the measurement gets to “now” depends on the service, with gaps:
DWD has quality-checked hours up to the day before yesterday and the current
day from ten-minute values — yesterday is missing until the next daily file
arrives; KNMI goes up to the day before yesterday (two days' delay — then it
says “no values for these days”, and the next station gets its turn);
Rijkswaterstaat, GeoSphere and DMI go up to the current hour; Météo-France up
to early this morning (the daily file appears in the morning). So for each
spot it says “Measurement available: …” with the hours that have a
measurement; otherwise the curve stays empty, and the statistics only count
the hours both have. The fixed monthly comparison for code changes is the
**benchmark** ([`BENCHMARK.md`](BENCHMARK.md)); the Review answers the
question “can I trust the report I just got?”.

**Model comparison** (since 1.14.0): under each curve it says which weather
model came closest to the measurement at this spot — the global ICON, ECMWF,
the AI model ECMWF-AIFS, GFS, Météo-France and UKMO, and up to three regional
models that cover the spot (ICON-D2, AROME-HD, HARMONIE, CH1, ICON-2I,
AROME-AT, DMI). The models are shown raw, without `wind_factor` and thermal;
the “Wingfoilscout rating” includes both, as a row of its own. The chart
initially shows only the measurement and, as a grey band, the range of all
models (since 1.15.0). The buttons below it switch on individual models, the
Wingfoilscout rating and **“Best model so far: …”** — the model that, according
to the memory, did best at this spot (otherwise across all spots); at most
three lines at once. At the bottom of the page: the ranking across all
destinations of this review and the **memory** of all checks so far
(`modellguete.json`, personal, not versioned) — each day counts once, and a
new check replaces a day that is already there. After a few weeks it tells you
which model gets it right where. The global models can be changed in
`config.yaml` under `rueckblick: modelle:`.

### On the iPhone

Since 1.17.0 the interface is built for phones: a bar at the bottom with four
items (Search, Destinations, Review, Logbook), the report as the
“Destinations” tab with a collapsed header, the hourly grid and wide tables to
swipe sideways. Built and tested for widths of 320 to 430 points — from the
iPhone SE to the Pro Max.

**On Wi-Fi, with the Mac doing the work.** Wingfoilscout normally listens only
on 127.0.0.1. For an iPhone on the same network:

```
python3 -m wingscout.webui --lan
```

or double-click **“Wingfoilscout fürs iPhone starten”**. The terminal then
shows an address like `http://192.168.178.25:8765/?k=Xf3k…` — type it into
Safari. The key in it is your access: without it, every other device on the
network gets a 401. It is stored in a cookie once and stays valid until
Wingfoilscout is quit; after that, the address without `?k=` is enough. The
search still runs on the Mac — the iPhone only shows the results and starts
searches.

**To the Home Screen.** In Safari, “Share” → “Add to Home Screen”:
Wingfoilscout then starts like an app, without an address bar, with its own
icon.

**On the road without a Mac.** The report is a single HTML file
(`report.html` in the Wingfoilscout folder). Sent to the iPhone via AirDrop,
it can be opened there without a network and without the Mac — everything
except the map, which fetches its tiles from the internet.

### Logbook — your sessions calibrate Wingfoilscout

The **Logbook** tab (since 1.16.0) records what a session was really like:
spot, date, time from–to, wing, power (underpowered / just right /
overpowered), water (flat / choppy / wave) and a grade from 1 to 5. Once you
have entered it, Wingfoilscout fetches, for exactly those hours, what it would
have said (the same calculation as in the Review, with regional model,
`wind_factor` and thermal), what the individual models said and — if there is
a weather station within 30 km — what was measured. The session then shows
whether Wingfoilscout would have picked a different wing or expected
different water. If the measurement is still missing (DWD only delivers
yesterday with the next daily file), “Compare again” fetches it later; if a
new comparison finds less than the old one (no network), the old one stays.

Several sessions turn into **suggestions** — never applied automatically:

- **Wind range per wing** (`config.yaml`): underpowered at a wind that the
  quiver already lists as suitable for this wing raises the lower limit;
  overpowered within the range lowers the upper limit; “just right” outside
  it widens the range. The session's wind is the measurement if the station is
  at most 15 km away, otherwise Wingfoilscout's forecast.
- **Wind factor per spot** (`spots.yaml`): every session narrows it down —
  “just right” means the raw model wind of the same hours times the factor was
  within the range of the wing you rode. The suggestion is the closest factor
  that all of the spot's sessions fit (in steps of 0.05, between 0.6 and 1.5).
  Hours with an assumed thermal don't count for this.

A suggestion needs at least two sessions pointing in the same direction; if
sessions contradict each other, there is none. If the same sessions support
both kinds of suggestion, the page says so — applying both would correct the
same finding twice. “Apply” changes only that one line; comments stay. The
logbook lives in `tagebuch.json` in the Wingfoilscout folder: personal, not
versioned, only on this computer (and in its backup).

### Thermal winds

At quite a few spots the standard models fail. The **Ora** on Lake Garda, the
**Maloja wind** in the Engadine and the **Maestral** on the Adriatic are
driven by the temperature difference between land and water. A grid of 7 to
25 km averages away exactly the valleys and coastlines that create this
circulation — the model shows 5 kn, and on site it's blowing 18.

That's why **71 spots in the catalogue** carry stored thermal knowledge: the
wind's local name, months, time window, direction, typical strength,
reliability and **the source**. Wingfoilscout assumes wind there that no model
shows — but only if the weather fits:

- **Irradiation since sunrise.** The thermal doesn't live off the sunshine of
  this hour but off how much heat the morning has put into the ground. Hence
  the accumulated global radiation rather than the cloud cover — it weights
  high cirrus and low stratus decks differently, as it should.
- **Opposing wind — and this is the interesting part.** An offshore gradient
  wind smothers the breeze from as little as 7 to 8 kn. A *weak* opposing
  wind, on the other hand, **strengthens** it: it holds the breeze front at
  the coast instead of letting it run off inland. So the response curve peaks
  at about 3 kn of opposing wind and drops steeply after that. That's exactly
  why the Maestral works — a weak north-westerly gradient plus thermal.
- **Blocked background flow.** The Maloja wind comes “practically never with a
  northerly background flow”, even under a blue sky. Such exclusions are
  stored per spot in the catalogue.
- **Time of day** within the stored window, building up and dying down.

In the report, the thermal destinations appear **as a list of their own**
right below the best three — sorted by the thermal potential of the best day,
not by the overall score. Without that list they would get lost, because the
normal ranking counts the model wind, and that's exactly what is too low
there. The bar next to each one is the **mean over the whole thermal window**
of irradiation and opposing wind, times the spot's reliability from the
catalogue; the best single hour is in the tooltip. Up to 1.5.1 the bar showed
the maximum, and that was worthless: on a sunny day every ingredient fits at
some point, so in the run of 16 Sep 2026 all five destinations were between
96 and 100 per cent. That the bar now rarely goes above 90 per cent is not a
defect — the reliability is nowhere higher than 0.95 in the catalogue, and for
most spots it is a deliberately cautious estimate. On the map there is a
**Thermal winds** layer for this: an orange ring around every spot with stored
knowledge. The ring is pure decoration and doesn't catch any clicks — the
details open as on any other point.

Below that comes **“When the thermal works”**: the same hourly grid, but
coloured by thermal potential. Orange means potential, pale means outside the
window, and grey means: the window would be open, but the gradient wind or the
background flow smothers the thermal today. A frame around an hour means the
assumption really applies there — the wind in the report comes from the
thermal and not from the model. Unlike the list above it, the grid doesn't
depend on the destinations: a spot where the models don't see a single
rideable hour is still in it.

What the tool does **not** do: invent thermals. It only calculates at spots
where the catalogue says there is one. And where no source gives a strength —
Chiemsee, Lake Constance, Lake Thun, for example — **none is assumed**; the
spot only appears as a candidate in the list. Assumed wind is always marked as
an assumption in the report, never as a measured value.

Can be switched off via `thermal.enabled` in the configuration, and damped via
`thermal.trust`.

### High-resolution regional models

The global models compute on a 7 to 25 km grid. The Ora arises in a valley
that is 2 km wide at its narrowest point; the Maestral lives off a coastline
that turns into a straight edge at 25 km. Exactly these circulations fall
through the grid.

So Wingfoilscout additionally queries regional models that compute at **1 to
2.5 km**: `meteoswiss_icon_ch1` (Alps), `italia_meteo_arpae_icon_2i`
(northern Italy), `meteofrance_arome_france_hd`, `dwd_icon_d2`,
`knmi_harmonie_arome_netherlands`, `geosphere_arome_austria`,
`dmi_harmonie_arome_europe`. Where one of them answers, it overrides the
wind — but only for the hours it covers: these models reach two to three days
ahead, the global ones up to sixteen. In the report, every session shows which
model supplied it.

Which model gets its turn is decided **first by jurisdiction, then by
resolution**: for a point in Italy the Italian model, even if the Swiss one
has a finer grid. A model at the edge of its area is not the better source —
there the provider lacks the stations to check against. Each session shows the
**typical** difference to the coarse model (“CH1 +5 kn”) — the median over the
hours the fine model covers. The peak is in the tooltip. Up to 1.5.0 the badge
showed the peak, and that was misleading: it grows with the length of the
session rather than with the quality of the model, because more hours offer a
more favourable one to pick. In the first real run this was measurable —
sessions of up to eight hours had a median of 0 kn, sessions over sixteen
hours 6 kn.

So the fact that most badges carry only the model name is not a bug but the
result: in the run of 16 Sep 2026, only **CH1 in the Alps** brought a
consistent gain (median +5 kn, 86 % of sessions above 2 kn). **ICON-D2 on flat
German inland lakes brought nothing** — the control group that shows the
calculation is right: where there is no circulation to resolve, a finer grid
gains nothing. For ICON-2I on the Adriatic, six sessions weren't enough for a
verdict.

Two quirks make this more awkward than it sounds. **Open-Meteo doesn't
document anywhere which model covers which point** — the docs only say
“Central Europe”. And a request for a point outside a model's domain is
answered with HTTP 400, not with empty values: in a batch request for twenty
coordinates, a single unsuitable point takes all the others down with it.
Wingfoilscout therefore halves rejected groups until the outliers are pinned
down, and **remembers the result per spot** in `cache/highres.json`. This
dance happens once, not on every run — and once more if the spot's coordinate
changes: since 1.7.0 every cache entry (Overpass extract, protected areas,
model assignment, drive time) carries the coordinate it applies to, and
applies to no other.

Once in advance, so that the first real run doesn't start with it:

```bash
python3 tools/highres_probe.py          # thermal spots only
python3 tools/highres_probe.py --alle   # the whole catalogue
```

Can be switched off via the **High-resolution models** checkbox under Data
sources, via `wind.highres` in the configuration or with `--no-highres`.

### How certain is the forecast?

If **Ensemble probability** is ticked, Wingfoilscout additionally fetches the
ICON ensemble for the best destinations after the ranking: the same weather
situation, computed forty times with slightly shifted initial conditions.
Every session then gets a badge — the share of runs that get above your
riding threshold in the time window, plus the spread from the lower to the
upper decile. The tooltip shows the median and the share that makes it into
the comfort band.

This doesn't replace model agreement, it complements it: three models tell you
whether the weather services agree, forty runs tell you how stable the
situation is in the first place. One limitation comes with it — the ensemble
sits on a coarser grid. At Brouwersdam the query lands 15 km from the spot,
the deterministic ICON 3 km. That's why it is only used to compute a
probability and never overrides a wind value.

Since 1.5.0 the number no longer just sits there but has a say. The session
score is multiplied by it, damped:

    factor = (1 − weight) + weight · share

With the default `weight: 0.5`, a session that not a single one of the forty
runs supports keeps half its score — it slides down but doesn't disappear.
Multiplying raw would empty the whole report in an uncertain weather
situation, and then nothing would be there even though there is something to
decide. `weight: 0.0` restores the behaviour up to 1.4.3: the badge is shown
and changes nothing. The query covers the top `ensemble.top` destinations
(default 20); anything further down is neither rewarded nor penalised and can
therefore overtake a damped destination.

There are two things the ensemble doesn't know, and since 1.7.0 it is told
both. First, it knows neither the regional model nor a spot's `wind_factor`:
so it is asked for the raw number that becomes the riding threshold after both
corrections. Second, it doesn't see thermals — at the Ora it reports 5 kn and
0 % certainty, and up to 1.6.1 that halved exactly the sessions the tool had
specifically corrected. For a thermal session, the **spot's reliability** from
the catalogue now counts as the probability, with the same damped factor; the
badge says so (“Thermal assumed · 80 % reliable”). Since then the wind speed
itself is `typical_kn` times potential — the reliability is no longer baked
into the knots, where it produced a value that doesn't occur on any day.

### Local time

All timestamps are **local time at the spot**: Greece and Portugal are
queried in their own time zone, the Canaries and the Azores in theirs. Every
column of the hourly grid shows the same local hour, the thermal window from
the catalogue counts as local time, and “past” reads the right clock for each
spot. Up to 1.6.1 everything was Europe/Berlin — an hour off in Athens.

### Day, night and now

A session takes place in daylight and ends with the day. Sunrise and sunset
come from the forecast; if they're missing, `wingscout/sonne.py` computes them
from latitude, longitude and date. If both are available, every run compares
them and writes the largest deviation to the log — so the tool's own formula
checks itself every time it is used. Hours that are already over at the time
of the run are dropped as well.

Up to 1.4.3, none of this applied. The check was built in but never kicked in:
with several models, the field in the response is called
`sunrise_dwd_icon_seamless` instead of `sunrise`. As a result, thirty per cent
of all session hours lay between 20:00 and 7:00, and the longest continuous
“session” lasted 59 hours.

### Running and quitting

The interface runs only on your computer (127.0.0.1:8765) and can't be reached
from outside. To quit, use the **Quit** button at the top right of the tab
bar, on every page (on phones a small label at the top right) — press it
twice, so that it isn't triggered by accident in the middle of a run.

If port 8765 is already taken by another program (a second local server, for
example another interface that uses the same port), Wingfoilscout moves to the
next free one and says so in the terminal — the address is then, for example,
`127.0.0.1:8766`, including the one for the iPhone. If a Wingfoilscout
interface is already running there, no second one is started; the running one
is opened in the browser instead. You can set the port explicitly with
`python3 -m wingscout.webui --port 8790`.

A search runs in the program, not in the browser window: you can switch to
other tabs in the meantime — a dot then pulses on the “Search” tab, and when
the report is ready, “Destinations” gets a green one. When you come back to
the search, it shows the running or finished run with its time. After you
quit, the program in the terminal window ends by itself too, and the window
can be closed. Ctrl+C in the terminal still works as well.

> On the first double-click, macOS may report that the file comes from an
> unidentified developer. From macOS 15: System Settings → Privacy & Security
> → at the very bottom “Open Anyway”; up to macOS 14, right-click → Open →
> Open is enough. After that it runs normally. Alternatively, run this once in
> the terminal: `xattr -d com.apple.quarantine "Wingfoilscout starten.command"`.

### Command line

```bash
python3 run.py                                   # 3 days, 500 km, opens the report

python3 -m wingscout.cli --days 3 --radius 500   # spontaneous mode
python3 -m wingscout.cli --days 7 --radius 1000  # long weekend
python3 -m wingscout.cli --ab "2026-10-10 09:00" --days 2   # that weekend only
python3 -m wingscout.cli --favoriten             # your favourites first (list from the interface)
python3 -m wingscout.cli --demo                  # synthetic data, no network needed
python3 -m wingscout.cli --days 2 --model icon_d2 --open
```

| Option | Meaning |
|---|---|
| `--days N` | forecast days, 1–16 |
| `--ab TIME` | start time instead of now (`2026-10-10 09:00`, `10.10.2026 09:00` or just the date); the days count from it, at most 16 days ahead |
| `--radius KM` | search radius as driving distance in kilometres — routed via OSRM, estimated (straight line × detour factor) only where OSRM doesn't answer |
| `--max-drive H` | upper limit for the one-way drive |
| `--min-hours H` | minimum length for a block to count as a session |
| `--model NAME` | force an Open-Meteo model, e.g. `icon_d2`, `icon_eu` |
| `--marine` | also rate water temperature and wave model (sea and lagoon spots only); tide times come without it too |
| `--no-geo` | ignore the shoreline geometry, use only the catalogue sectors |
| `--nights N` | planned nights — requires N+1 usable days in a row |
| `--demo` | made-up weather data, to check layout and logic |
| `--open` | open the report in the browser afterwards |
| `--favoriten [IDS]` | show favourites first: without a value the list from the interface (`favoriten.json`), otherwise spot IDs separated by commas — always computed, even outside the radius (see [Favourites](#favourites)) |
| `--sprache de\|en\|fr\|es` | language of messages and report. Without it: the language chosen in the interface (`sprache.txt`), otherwise the system's (`LC_ALL`, `LC_MESSAGES`, `LANG`, then the macOS language settings), otherwise English. The environment variable `WINGSCOUT_SPRACHE` beats even `--sprache` |

`python3 -m wingscout.webui` writes its terminal lines by the same rule, just
without `--sprache`. The `--help` text of `wingscout.cli` is put together
before that choice: it follows only `WINGSCOUT_SPRACHE` or the language chosen
in the interface, otherwise it is German. The double-click files print their
own lines in the four languages too (`tools/sprache.sh`): `WINGSCOUT_SPRACHE`,
then the language chosen in the interface, then the macOS language settings,
then `LC_ALL`, `LC_MESSAGES`, `LANG`, otherwise English. What they start in
turn is partly still German: the check run (`tools/check.sh`), updating
(`tools/aktualisieren.sh`), the benchmark and `build_geometry.py` print German
messages, and “Auf GitHub veröffentlichen” is German throughout.

## Your quiver → your wind range

The template's quiver (`config.example.yaml`), calibrated for 80 kg; your own
goes into `config.yaml`. Rule of thumb: lower limit ≈ 65/area, upper
≈ 108/area. **These are values from experience, not measurements.**

| Wing | from | to |
|---|---|---|
| 6.5 m² | 10 kn | 17 kn |
| 5.0 m² | 13 kn | 22 kn |
| 4.2 m² | 15 kn | 26 kn |
| 3.5 m² | 19 kn | 31 kn |
| 2.5 m² | 26 kn | 43 kn |

Together: **10–43 kn covered without gaps.** Comfort band for the rating:
14–28 kn. If a session felt different from how the report rated it — enter it
in the **Logbook**; from two sessions on, it suggests a different range. Or
change the numbers in `config.yaml` directly, not the code.

## What the report rates

The whole decision path — pre-filter, the seven vetoes per hour, the score
made of five components, sessions, reliability, order of the destinations — is
described in [`SCORING.md`](SCORING.md), with the configuration values next to
it — and with figures on the page
[“How Wingfoilscout calculates”](https://darkpiratego.github.io/wingfoilscout/bewertung.html)
(in the repository: `docs/bewertung.html`).
Here is the short version:

| Component | Weight | Based on |
|---|---|---|
| Wind speed | 34 % | matching wing, how central it sits in the wing's range, comfort band |
| Wind direction | 24 % | sectors from `spots.yaml` |
| Water state | 16 % | the sector's `water` label × your chop aversion |
| Weather | 14 % | temperature, rain, CAPE |
| Gustiness | 12 % | gust ÷ mean wind |

### Drive time: routed, not estimated

The drive used to be straight-line distance times a detour factor at an
assumed average speed. That carries the most important decision of the whole
tool — is the drive worth it — and it is too crude for that: from Brouwersdam,
the rule of thumb estimates 44 km and 31 minutes to the Oesterdam; routed,
it's 63 km and 61 minutes. In Zeeland there are dams and ferries in between,
in the Alps mountain passes.

Now Wingfoilscout asks the public OSRM server, using its table service: a
single call returns the drive time from the starting point to all
destinations at once, and the complete catalogue fits into one query that
takes a fraction of a second. Results are stored in `cache/routes.json`, with
the starting point rounded to just over a kilometre — the OSRM server, too,
only gets it at that precision — so repeated searches from the same place
don't fetch anything at all.

So that the estimate doesn't swallow destinations before they are checked, the
pre-filter runs with a 35 % margin on the radius and the drive-time limit;
your real limits are only applied after routing. Not checking a destination
that was estimated too pessimistically would be the costlier mistake.

In the report, “(estimated)” follows the drive time if routing wasn't
possible; the tooltip always says where the number comes from. Can be switched
off via the checkbox under Data sources — then `drive.detour_factor` from the
configuration applies again.

**The radius is a driving distance.** A spot is in the search only if its
routed driving distance is at most the radius — and the drive at most the
“Max. drive” hours. A straight line appears only where it says so: the dashed
circle on the map (radius ÷ detour factor, for orientation only) and the
“km (straight line)” column of the Catalogue, measured from home. In “Not
considered” the column shows the driving distance — routed, or with “≈” where
it is only an estimate; up to 2.3.0 it showed the straight line next to a
reason quoting the road distance (“682 km” beside “1026 km — outside the
1000 km radius”). If OSRM gives no route for some spots of the search, the
report says so at the top: for those the radius was checked against the
estimate, and the real distance can be longer.

### Dog-friendly overnight spots

Under each of the best destinations there are up to four places to stay
overnight from Park4Night, sorted by distance, type and rating. **Dogs must be
explicitly allowed** — that's a hard filter here, unlike at the spot itself.

Two things you need to know. First, the API's server-side pet filter is
unreliable: it also returns places without any service information at all. So
the filtering happens here, based on the place's `animaux` entry. Second,
missing information almost never means “dogs forbidden” but “nobody entered
it”. Such places are still dropped, but counted — the number appears below
the list. If a short list on a coast full of campsites surprises you, that's
the reason, and the Park4Night link next to it then shows everything.

Day car parks, picnic areas and pure service points (water and waste) are
excluded — you can't stay overnight there. The order converts size, distance
and rating into “felt kilometres”: each step up towards a full campsite costs
one and a half kilometres, a good rating earns up to one kilometre of lead.
That way the small free pitch three kilometres further away beats the big
campsite right on the water, but the farm twenty kilometres inland doesn't.

The API is unofficial. If it fails, this section is missing and nothing else.
Can be switched off via the checkbox under Data sources.

### Dogs and permission at the spot

Two catalogue fields, `dogs` and `access`, appear as a badge on the
destination: no dogs, dogs on a lead, surf licence required, club membership,
designated zone only, entry fee, explicitly allowed, permission unclear,
prohibited. If nothing is shown, the sources say nothing — that's not the same
as “allowed”.

This does **not** filter anything. A dog ban on the beach doesn't mean the day
is no good; it means you know in advance. If you want to hide such spots
anyway, you'll find two checkboxes for that under **Fine-tune the search →
Water** — both off by default.

### Shore break

At some sea spots the wave breaks right at the shore — for getting in and out
with board and wing, that's the least pleasant part of the day. The
`shorebreak` field in the catalogue records this observation, **purely as
information**: it doesn't filter and doesn't go into the score.

```yaml
  shorebreak:
    status: "yes"        # "yes" | "possible" | "no" | "unknown" — in quotes!
    note: "Offener Atlantikstrand; bei Swell bricht die Welle direkt am Ufer."
    source: "Spotwissen — unbelegt, bitte prüfen"
```

`"yes"` appears as a **Shore break** badge on the destination, in the map
popup and in the catalogue, `"possible"` as **Shore break possible**; the note
appears as a line under the destination's header and as a tooltip on the
badge. `"no"` and `"unknown"` stay silent — on a lake, “no shore break” would
just be noise. The quotes are mandatory: YAML reads a bare `yes` as a boolean
(the same trap as with `dogs: no`); the catalogue test flags it.

The entries from 1.9.0 (34 spots on the Atlantic, the North Sea and the
Channel) are a first assessment based on location and exposure, not on
first-hand observation — hence `source: Spotwissen — unbelegt` (“spot
knowledge — unverified”). If you know a spot, correct the line and set the
source.

### Tides — high and low tide per spot

Since 1.18.0 the report shows at tidal spots where the tide currently stands,
and can make it a rule if you want. The source is the modelled water level
`sea_level_height_msl` from Open-Meteo's marine API, hourly on an 8 km grid —
tide and wind setup together. This is **not an official tide table**: compared
with the table for the nearest tide gauge, the times differ — by how much has
not yet been checked against a table (see TODO); in bays and estuaries, expect
more than on an open coast. For “rising until 15:00” it should be good enough;
for walking across the mudflats it isn't.

**Whether the tide applies** is decided per spot by the `tidal` field — you can
switch it in the catalogue under “Tides…”, or by hand in `spots.yaml`:

```yaml
  tidal: true      # the tide applies here, even if the model shows little range
  tidal: false     # never — Baltic, Mediterranean, a lagoon behind locks
                   # leave out = automatic: sea or lagoon with ≥ 0.5 m range
```

Automatic is the default for all sea and lagoon spots: the model is queried,
and if it shows an average range of at least 0.5 m between high and low tide
over the period, the spot counts as a tidal spot (limit `tide.auto_hub_min` in
the configuration). Careful with lagoons behind dams: the 8 km grid often sees
the North Sea in front of them — the Grevelingen side and the Spuikom in
Ostend are therefore set to `false`.

**What the report shows:** on the destination, a tide line with the current
state (“Now rising · high tide at 14:50 (in 1 h 40 min)” — the sentence is
computed when the report is opened and updated every minute, because the
report is a file and “now” meant something else when it was created), below it
high and low tide for each day to the minute (interpolated from the hourly
values), range and source. The session line names the state at the start of
the session and the high and low tides that fall within it; the tooltip in the
hourly grid the state for that hour; the map popup the same line as the
destination. Times are local time at the spot, as everywhere in the report.

**A tide window** makes the tide a rule — only if you set one:

```yaml
  tide:
    fahrbar: hochwasser   # hochwasser | niedrigwasser | auflaufend | ablaufend
    stunden: 2            # ± hours around high/low tide (only with hochwasser/niedrigwasser)
```

The keys and values are German: `fahrbar` = rideable, `stunden` = hours,
`hochwasser` / `niedrigwasser` = high / low tide, `auflaufend` / `ablaufend` =
rising / falling. Hours outside the window are dropped with a veto (“outside
the tide window (HW ± 2 h)”), just like night or water that's too cold; in the
grid they are grey, and the tooltip gives the reason. `auflaufend` and
`ablaufend` take the whole half tide from one turn of the tide to the next.
Without a window, the tide changes **no score** — it is then display only.
Which window a spot needs is only known to someone who knows the spot (a
sandbank at low tide, a mudflat beach at high tide); that's why Wingfoilscout
doesn't ship any windows but a switch in the catalogue instead: “Tides…” next to
rename and move, with automatic / yes / no and the choice of window.

The “Water temperature and wave model” checkbox (`--marine`) no longer has
anything to do with the tide: tide times always come; the checkbox only decides
whether water temperature and wave height from the model go into the rating.
Spots with `tidal: false` aren't queried at all without the checkbox.

### Links for each destination

Under each destination there are six links, the first four pointing at the
spot's coordinate: **Windy** (map centred on the point — Windy has no deep link
to a position), **Route** (Google Maps, with the search's starting point as
the origin, i.e. with the distance from where you really are), **Check map**
(OpenStreetMap with a marker, to verify the coordinate) and **Park4Night** with
`lat`/`lng` on the spot, so the overnight spots show up in the right area
straight away. Plus **Instagram** and **Insta search**, see below.

### Instagram

Whether people go winging at a spot shows up faster on Instagram than in any
forum. But it can't be checked automatically: Instagram has no public search
without logging in and no free API that answers “are there posts from here?”,
and its terms of use forbid scraping the pages. So Wingfoilscout does two
things:

- **Two links per spot**, in the report, in the map popup and in the
  catalogue: **Instagram** leads to the spot's location page (all posts tagged
  there) if one is known, otherwise to the hashtag made from the name
  (`#brouwersdam`); **Insta search** is a Google search on instagram.com for
  the spot name and “wingfoil” — which shows even without logging in whether
  there are posts. The hashtag can be set in the catalogue
  (`instagram: "#tag"`), as can a full address
  (`instagram: "https://www.instagram.com/…"`), such as the location page or a
  profile you found yourself.
- **A snapshot** in `instagram.json`: for 100 spots, a Google search was run
  on 18 Sep 2026 (`site:instagram.com/explore/locations <Name>` for the
  location page, `site:instagram.com <Name> wingfoil` for hits). Hits were kept
  if they have wing or foil in the title, or the spot name together with a
  water-sports word; accounts that turned up at three or more spots were
  removed. The result — 77 location pages, 104 hits — appears as an
  **Instagram** line under the destination and in the catalogue, with the date
  and the remark “not proof”: these are search hits that tell you where to
  look, not proof that people wing there. For the remaining roughly 100 named
  spots the search is still to be done (see `TODO.md`); the **Insta search**
  link does the same for any spot with one click.

### Layout of the report

Your [favourites](#favourites) first, if you have switched them on (since
2.4.0), then the best three destinations (since 2.3.0 above the map), then
the map, thermals, hourly grid, all further destinations, all sessions as a table, the
excluded spots, and the weather logic with your current values.

**Two views** (since 1.20.0), switchable at the top below the heading:

- **Simple** — the answer without the machinery behind it. Each destination is
  a collapsible panel with two lines: rank, name, drive and hours on the
  water, the badges that decide whether to go or not (Worth the drive, official
  warnings, thermal, tide, number of notes) — and below that the best session:
  when, how much wind, which wing, which wind angle. All sections further down
  show only their heading and one sentence about it. Clicking a destination or
  a heading opens exactly that.
- **Detailed** — everything open, the way the report looked up to 1.19.2:
  comment, warnings in full, tide, every session with models, fetch and waves,
  overnight spots, links, catalogue note; the sections expanded. Only “More
  destinations” stays closed — nobody wants 40 cards at once, not even in the
  detailed view.

The browser remembers the choice (`localStorage`), so it applies to every new
report until you switch. Without JavaScript, Simple applies; the collapsible
panels don't need it.

The session table can be sorted: a click on a column — Spot, When, Duration,
Wind, Angle, Direction, Wing, Water, Score — sorts it, a second click reverses
the order. Numbers where more is better (Duration, Wind, Score) come in
descending order; Angle sorts as side-shore, side-on, onshore, offshore (the
catalogue's sector verdicts slot in between), Water as flat, choppy, wave.
**Angle** is the wind angle from the shoreline geometry or the sectors,
**Direction** the compass direction the wind comes from. The first 40 of the
current order are shown, “show all …” (with the number of sessions) lifts the
limit; for equal values the score decides.

The order follows what you open the report for: where is it best, where is
that, what does the week look like. You only look at number 12 if the first
three don't deliver.

### Hourly grid

One row per spot, one column per hour, the time at the top. Two ways to read
it, switchable with the toggle above:

- **Rating** — is the hour worth it at all? The colour is the score from wind,
  direction, gustiness and weather.
- **Knots** — which wing do you need? Red below 11 kn, orange up to the lower limit
  of your comfort band, green within the band, orange above it, red from the
  upper limit and **dark red above 30 kn**. Night hours and excluded hours stay
  pale, so the rhythm of the day remains readable.

Green is always the comfort band from the interface and moves with it when you
change it there. The red ends are in `config.yaml` under `wind.red_below`
(11), `wind.red_above` (26) and `wind.dark_above` (30). If a red end fell
inside the comfort band — with a band of 14–28 and red from 26, that would be
the case — it gives way instead of cutting the band in two. So an hour can
never be green and red at the same time.

The spot name leads to **Windy**, the distance next to it to the **Route** —
“what will the wind be?” and “how far is it?” are two questions, and each has
its own target.

Every cell explains itself: on a computer in the tooltip, and since 1.19.0 also
with a tap or click — then below the grid it says what the hour was (spot,
time, wind, rating and the reason if it is excluded). On the iPhone that's the
only way, because there are no tooltips there.

### Map

The report opens with a map, and it is a view of its own, not an illustration.
Dots: filled = destination with a session (the top 3 stronger), blue-grey =
within the radius but no wind, hollow = excluded (reason in the popup).

With the switches below it, each layer can be shown or hidden individually —
otherwise 277 dots at once are just a carpet of colour:

- **Top 3 / Session found / No wind / Excluded**, each individually
- **Dog-friendly overnight spots** as a layer of their own, with name, rating,
  distance to the water and Park4Night link
- **Click opens Windy instead of details** — off by default, because a click on
  a spot should show its details. If you'd rather jump straight to the wind
  map, switch it on. Even without the switch, the **name in the popup** leads to
  Windy
- **Names of matches** shown permanently; on hover, every dot shows its name
  anyway
- **Radius** as a dashed circle
- **Zoom to top 3**, **Show all**, **Full screen** (Escape ends it)

The popup of a spot shows the best session, direction and wing, the drive, the
**hour strip** in the same colour scale as the grid (hover for time and
knots), the coordinate to copy and four links: Windy, Route, Park4Night and
Check map (OpenStreetMap) — plus Instagram where the spot's address is known. A
click also draws the straight line to the starting point.

The map loads Leaflet from cdnjs and the tiles from OpenStreetMap, so it needs
internet when it is opened; without a network, a notice appears instead of the
map and the rest keeps working.

### Weather in detail

| Quantity | Open-Meteo field | Rule |
|---|---|---|
| Thunderstorm | `weather_code` | Code 95/96/99 → the hour is dropped. Plus a thunderstorm shadow: up to 2 h before and after, only 40 % of the score, with a note in the session |
| Thunderstorm potential | `cape` | from 1200 J/kg → 70 %, from 2000 J/kg → 35 %, each with a note |
| Rain | `precipitation` | no deduction up to 0.6 mm/h, then falling linearly up to 3.0 mm/h, above that 20 % |
| Air temperature | `temperature_2m` | outside 7–35 °C the hour is dropped; within 3 °C of a limit, 80 % |
| Water temperature | `sea_surface_temperature` | below 7 °C the hour is dropped — only with `--marine`, only sea and lagoon |
| Tide | `sea_level_height_msl` (marine API) | high and low tide at tidal spots; only with a tide window in the catalogue (`tide: fahrbar`) are hours outside it dropped — otherwise display only |
| Daylight | `sunrise` / `sunset`, otherwise computed | 30 min after sunrise until 30 min before sunset |
| Past | time of the run | hours that are already over are dropped |
| Cloud cover | `cloud_cover` | fetched, but not rated |

The **thunderstorm shadow** is where the tool goes beyond a forecast portal:
the model only flags the hour in which it predicts the storm at this grid
point — out on the water, you care just as much about the window around it.

The weather logic also appears as a table in the report itself, with your
current values from `config.yaml` — so the two can't drift apart.

**Water bodies:** fresh and salt water are both included
(`water.include_types`). To restrict this, remove individual types from the
list.

**Hard exclusions:** thunderstorm (weather code 95/96/99), air temperature
outside 7–35 °C, no matching wing, darkness, standing depth throughout, heavy
seagrass, spot out of season or outside the radius.

**Drive-time rule:** your guideline “6 h of driving for 2 h on the water per
day” is stored as factor 3 in the configuration. A destination counts as
worthwhile (“Worth the drive”) if
`drive time ≤ 3 × average hours on the water per day × (1 + 0.5 × nights)`,
capped at `drive.max_hours`. Beyond that it is marked “Drive borderline”, and
its rank is multiplied by 1 − 0.8 × excess ÷ allowed time — zero at 125 % over
the allowed time. Details in [`SCORING.md`](SCORING.md), section 6.

## spots.yaml — the real asset

The catalogue is maintained by hand and **not yet verified**. Every spot
carries `verified: false` until you have looked at it. The report links a map
for each spot — checking takes seconds, and afterwards the catalogue is worth
more than any forecast portal. Whatever comes in from a **file** via “Add
spots” (GPX, KML, GeoJSON, CSV) is unconfirmed and appears on the check page;
whatever you type in yourself or copy from the map counts as looked at.
Without a water type, it stays `water_body: unknown` — the spot then isn't
excluded by any filter, and the shoreline geometry later tells what kind of
water it is in.

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

`comment` is your own comment (see above), `notes` is the description.
`from`/`to` is the direction **the wind comes from** (degrees, 0 = north).
Sectors may wrap around north (`from: 320, to: 40`). `quality` is
`best | good | ok | bad`, `water` is `flat | chop | wave`.

A spot with `disabled: true` stays in the catalogue as a note but drops out of
the ranking — like Fehmarn/Gold, because of the seagrass.

## Shoreline geometry

The part that replaces the manual work.

```bash
python3 build_geometry.py            # once; usable offline afterwards
python3 build_geometry.py --only brouwersdam workum
python3 build_geometry.py --radius 25 --force
```

For every spot, the water geometry is fetched from OpenStreetMap (coastlines,
lakes, lagoons, reservoirs), and the **fetch over water is measured in 36
directions** — the first intersection of a ray with a water boundary. The
result is stored in `geometry.json` and doesn't change after that.

Everything else follows from this one quantity:

| Fetch upwind | Room downwind | Wind angle | Assessment |
|---|---|---|---|
| small | large | **offshore** | smooth, but you drift out → safety note; with `offshore_veto_km`, a veto once there is that much water downwind |
| large | small | **onshore** | waves and shore break right in front of you |
| both large | both large | **side-shore** | the best |
| small | small | no open water | the coordinate is wrong |

The wave height comes from the fetch-limited SPM relation
`H_s = 0.0016 · U · √(F/g)` — 20 kn over 1 km give 12 cm, over 40 km 1.05 m.
An engineering approximation: it assumes steady wind and uses U10 instead of
the wind stress factor. It is good enough for “smooth or choppy”; it doesn't
replace a wave forecast.

**What this means in practice:** spots without hand-maintained sectors — the
26 pins from Jens Dee's list, for example — are now rated just like your
reference spots. Wind angle and water state come from the geometry instead of
manual work. Your own sectors in `spots.yaml` take precedence; with
`geometry.prefer_manual_sectors: false`, the calculation wins instead.

If a spot sits on the car park instead of in the water, the measuring point is
moved into the water automatically (lakes via point-in-polygon, coasts via the
OSM rule “land on the left, water on the right”). Spots with hardly any open
water around them are listed by `build_geometry.py` at the end — there, the
coordinate is usually wrong.

The first run over 277 spots takes 10–30 minutes, almost all of it waiting for
the Overpass servers. Every spot is saved immediately, so cancelling is
harmless.

## What is still missing

- **Shoreline geometry for the rest of the catalogue** — how many spots are
  still missing is shown in the interface next to the “Compute missing”
  button; about a quarter of a minute per spot. `geometry.json` is versioned:
  after a run it should be committed, otherwise the next clone computes
  everything from scratch.
- **Check coordinates**: 122 spots come from imported lists and are rounded to
  three or four decimal places, i.e. up to about a kilometre off. The report
  marks them; “Check map” leads straight to the point.
- **Depth profile** from EMODnet: measure the standing depth instead of
  estimating it. Seas yes, inland lakes no — there is no free bathymetry for
  them.

The authoritative list is in [`TODO.md`](TODO.md).

## The benchmark — is it still right?

The tests check offline whether the code does what it should. The
**benchmark** checks online whether the whole thing still holds up:
double-click “Prüfstand” or run `python3 tools/pruefstand.py`. For seven spots
with well-known winds (Ora, Maloja wind, Breva …) it fetches the current
forecast and checks the shape of the response, the rating and whether the
thermal shows up where it belongs; it sends a point on the Swabian Jura
through the shoreline geometry and expects “no water within 3 km — is the pin
on land?”; and for ten spots
with a weather station in range, it compares the archived forecast of a fixed
month with the **measurement** — per model and for Wingfoilscout as a whole.
The figures of a good run are stored as a baseline; if a later change makes
things worse, the benchmark says so. Everything else is in
[`BENCHMARK.md`](BENCHMARK.md).

## Data sources, licences and limits

Wingfoilscout itself is under the [PolyForm Noncommercial 1.0.0](LICENSE)
licence (since 2.3.0; versions up to 2.1.0 were MIT): you may use, change and
pass it on for any noncommercial purpose — personal use, hobby, study and
research, and use by charitable, educational, public research, public-safety
or health, environmental and government organisations — as long as the
licence terms (or their web address) and the `Required Notice` line go with
it. Commercial use needs a separate licence from DARK: ask via an issue on
GitHub. There is no warranty — not for the wind either. The data are subject
to the terms of their sources, see below; `geometry.json` stays under the
ODbL of OpenStreetMap.

Weather: [Open-Meteo](https://open-meteo.com), free tier, non-commercial,
10,000 calls per day; the data are licensed under CC BY 4.0. A run over 25
spots costs two calls.

What is in the repository, and where it comes from:

- `spots.yaml` — maintained by hand. The origin of every entry is given in the
  file header and in the `source` field: Windfinder spot pages (coordinate and
  popularity rank), a shared Google Maps list, own estimates
  (`verified: false`). Names and coordinates are facts; the ratings and notes
  are original work.
- `geometry.json` — computed from OpenStreetMap (coastlines, water areas, land
  use): © OpenStreetMap contributors,
  [ODbL 1.0](https://www.openstreetmap.org/copyright). If you pass the file on,
  pass this notice on with it.
- `instagram.json` — only addresses of public Instagram pages (schools, clubs,
  location pages), found via web search; no content, no images.
- `pruefstand/grundlinie.json` — derived figures (deviation per model), no
  measurement series.

At runtime the following are added, and none of it is stored in the
repository: measurements from DWD, KNMI, Rijkswaterstaat, GeoSphere Austria,
DMI and Météo-France (open data, each under the terms of the service),
Windguru only with a station's API password, drive times from the public OSRM
server, place names from Nominatim, shoreline geometry from the Overpass
servers, overnight spots as links to Park4Night, the map with
[Leaflet](https://leafletjs.com) (BSD-2-Clause) and tiles from OpenStreetMap.
The usage rules of the public servers apply; Wingfoilscout caches responses so
that they aren't queried on every run.

What the report does **not** know: the official tide level (only the 8 km
model, see “Tides”), the measured water temperature, closure periods, bird
sanctuaries, whether the car park costs money, whether anyone else is there
right now. The report tells you where it's worth taking a look — not that you
should go.

### What leaves your computer

Wingfoilscout has no server of its own and no account. It talks directly to
the public services below, and each of them sees your IP address. What they
receive:

| Service | Receives |
|---|---|
| Open-Meteo (forecasts, sea state, ensemble, archived forecasts) | spot coordinates |
| Overpass (shoreline geometry) | spot coordinates |
| Park4Night (overnight spots) | spot coordinates |
| Nominatim (place name and country of a spot you add) | spot coordinates |
| OSRM (drive times) | your starting point rounded to about a kilometre (two decimal places), plus spot coordinates |
| MeteoAlarm (weather warnings) | only the country |
| Weather stations — DWD, KNMI, Rijkswaterstaat, GeoSphere Austria, DMI, Météo-France (Review, Logbook, benchmark) | station IDs and date ranges |
| Windguru (only if you configured a station) | the station ID and its API password, sent over HTTPS as POST |
| OpenStreetMap tile server (every map) | the tiles of the area the map shows |
| cdnjs (every map) | the request for the Leaflet library |

Your name, weight, gear and logbook stay on your computer. Your comments on
spots are written to `spots.yaml` and travel only with the catalogue — if you
publish it, they are public. Links in the report and in the catalogue (Google
Maps, Windy, Park4Night, Instagram …) send nothing until you click them — the
Google Maps route link then carries your starting point as it was used for
the search.
**Suggest it for everyone** and **suggest a correction** open GitHub; what
they fill in (name, coordinate, note) travels in the address. What you
submit there is public, under your GitHub name.

## Development

[`CONTRIBUTING.md`](CONTRIBUTING.md) describes how two people work on it
without getting in each other's way; [`DEVELOPMENT.md`](DEVELOPMENT.md) covers
the structure, tests and Git rules; [`SECURITY.md`](SECURITY.md) the audit of
13 Sep 2026 with findings and fixes; [`TODO.md`](TODO.md) is the authoritative
list of open items; [`CHANGELOG.md`](CHANGELOG.md) records what changed when.

Check run before every commit: `tools/check.sh` or “Tests ausführen” in the
Finder — around 700 tests, no third-party packages, one to two minutes. After a
fresh clone, run `tools/install-hooks.sh` once so that the check runs before
every commit.

```
wingscout/          program code (cli, score, report, webui, geometry, sources/)
.github/            check run on GitHub, CODEOWNERS, PR template
tests/              tests, plain unittest
tools/              check run, hooks, publishing and updating
import/             one-off import scripts and raw lists
spots.yaml          the catalogue — the real asset
config.example.yaml all thresholds and rules, commented — template
config.yaml         your personal version, not versioned
geometry.json       computed shoreline geometry, derived but versioned
```
