# TODO

As of 4 October 2026, version 2.3.0 (856 tests), published the same day as
the first commit of the recreated repository — release, Pages, About,
ruleset and security settings set again; the old 2.1.0 commit is gone from
GitHub. In it: **licence PolyForm Noncommercial 1.0.0** instead of MIT
(`SECURITY.md`); **spot suggestions
from the community** through a form on GitHub, opened from the app
(`CONTRIBUTING.md`); **installation on a fresh Mac** rewritten — the
Terminal way with `xcode-select --install` first, the ZIP way step by step
with “Open Anyway”; **the Destinations tab
follows the language switcher** — every search stores its report in all four
languages (`cache/report/`), switching needs no new search; texts computed
during the search (vetoes, session notes, reasons, compass points) are
translated when each version is written (`i18n.TD`, see `DEVELOPMENT.md`);
**start time** “Starting when?” next to “Starting from?” (`--ab` on the
command line), the days count from it, at most 16 days ahead; **the report
opens with the best three destinations**, the map follows. Before that,
2.1.0: **Wingscout is now called Wingfoilscout** (repository `DarkPirateGo/wingfoilscout`, the Python package
is still called `wingscout` internally); **the interface in four languages**
(German, English, French, Spanish — switcher next to logo and version, start
scripts and terminal lines included) and all documentation in English;
**security review of 4 October** with all findings fixed and re-checked
(`SECURITY.md`); the English website in `docs/` for GitHub Pages with
screenshots of the English interface, example report, methodology page and
two English videos (30 s intro, 1 min desktop); **help in the app** (“?” on every page: the guide and “How Wingfoilscout calculates” in all four languages, `README.de.md`/`.fr.md`/`.es.md`); `tools/veroeffentlichen.sh`
with guard rails (new files only after `ja`, no personal files, noreply
address required). The repository is public, with protection for `main` and
against secrets (`DEVELOPMENT.md`). 2.0.0: first public release — the
repository recreated on GitHub, without a dangling copy of the old history.
Before that, 1.20.x: `SCORING.md` explains the decision path,
`docs/bewertung.html` shows it with figures; the report in two levels —
Simple and Detailed; Review and Logbook find their run again after switching
tabs. Before that, 1.19.2: repository cleaned up for publication
(`SECURITY.md`, 27 Sep). Before that, 1.19.x: review implemented — security,
import, usability (`REVIEW.md`, 25 Sep), plus the Content Security Policy with
nonce as a second line of defence and the version number with the creator's
logo on every page. Before that, 1.18.x: tides per spot — automatic / yes /
no, tide state at the displayed time in the report, tide windows as a rule,
toggle in the catalogue. Before that, 1.17.0: Wingfoilscout on the iPhone —
tab bar at the bottom, report as the "Destinations" tab, Wi-Fi access with a
key, home-screen icon; 1.16.x: session logbook, CSS and JavaScript as
separate files, `pyproject.toml` and ruff. The probe with 1.14.0 (15:01) was
green throughout. Everything not listed here is built and tested. The version
history with the reasons is in `CHANGELOG.md`, the methodology in
`README.md`, the architecture in `DEVELOPMENT.md`, the findings of the code
review of 16 Sep, the structure review of 20 Sep and the security and
usability review of 25 Sep in `REVIEW.md`.

## Starting a new chat

This file is the handover. A new chat only needs the folder
`~/ClaudeCode/wingscout` and this sentence:

> Read TODO.md, CHANGELOG.md (the top three entries) and DEVELOPMENT.md
> — especially "Working with Claude" there. Then `git status` and
> `git log --oneline -8`. Then tell me where we stand.

What deliberately doesn't come along: the history of the conversations.
Everything from it that matters is in the repository — every decision with
its reason in the CHANGELOG, every open question here. Whatever isn't here
wasn't important enough to keep.

## State of the data

- 278 spots, 277 of them with shoreline geometry (missing:
  `the-harbor-of-boulogne-sur-mer`, now "Boulogne-sur-Mer – Hafen")
- 0 spots with `verified: false`, 0 spots with "Pin …" in the name (1.14.0:
  107 names from OpenStreetMap, 15 country codes corrected, 61 water body
  types set — details in the CHANGELOG)
- 22 spots with `water_body: unknown`
- 71 spots with thermal-wind knowledge, 25 of them without a sourced strength
- 34 spots with `shorebreak` (14 yes, 20 possible) — all unsourced, see below
- 100 spots in `instagram.json` (77 location pages, 104 hits, as of
  18 Sep 2026); 178 not searched yet — since 1.14.0 the former pins also
  have a name that can be searched for
- Benchmark baseline: `pruefstand/grundlinie.json`, set on 16 Sep with
  1.8.1
- `python3 tools/koordinaten_check.py --alle` (offline): 92 confirmed by
  name, 157 not checkable (sea or unnamed area), 26 "contradictions" —
  almost all name variants (Comer See / Lago di Como, Urnersee /
  Vierwaldstättersee) —, 3 pins on land (Leucate, Fos, and Brouwersdam
  without an extract)
- `modellguete.json` (the memory of the model comparison) is created with the
  first Review check under 1.14.0
- `tagebuch.json` (session logbook) is created with the first logged session;
  personal, not versioned — backed up only through the Mac's backup

## Open — Philipp

- **Try 2.3.0 once:** restart Wingfoilscout, run one search, then switch the
  language — “Destinations” should follow without a new search (a report
  from before 2.3.0 exists in one language only). Then try “Starting when?”
  with next Saturday: the hour grid should start on that day.
- **Try a spot suggestion once:** Catalogue → “Add a new spot”, fill in name
  and coordinate, click “Suggest it for everyone” — the form on GitHub should
  come up filled in. Submit a test only if you close it again afterwards
  (issues are public) — and check that it gets the label `spot`.
- **Share the posts** when you like: `Claude outputs/werbung/beitraege.md`
  (licence and spot form are in the texts).
- **Decide: Park4Night** is queried with a browser User-Agent (as before). A
  question of that site's terms of use, not of security.
- **Try the installation on a fresh Mac again** with the new guide. Tried on
  4 October: the ZIP's start file was blocked (“Apple could not verify …”,
  only “Move to Trash” and “Done”), and in Terminal `git clone` only asked
  for Apple's command line tools. Not yet confirmed: that the Terminal way
  (`xcode-select --install`, then the line from the README) runs through to
  the browser, and that “Open Anyway” under Privacy & Security lets the
  `.command` file start.
- **Look at the map in the report on the Mac** — since 1.19.1 a Content
  Security Policy applies. Whether the map loads under it is not confirmed:
  its library comes from cdnjs, which is blocked in Claude's environment.
- **Set tide windows** where you know the spots: Catalogue → "Tides…" →
  "rideable": around high tide / around low tide / only when rising / only
  when falling.
  St. Peter-Ording ("the water level decides everything") is the first
  candidate; I haven't entered a window because I don't know whether high or
  low tide applies there. And after the first real run, check whether the
  automatic setting hits the right spots ("Tides: auto" badge in the
  catalogue, tide line on the destination) — for lagoons behind dams, set it
  to "no" when in doubt.
- **Check tide times against a tide table:** once, compare the high-tide time
  from the report with BSH (Pegelonline) or Rijkswaterstaat for the same day.
  I don't know how far off the model is — I have no number for it; only the
  comparison will tell whether the 8 km grid is good enough at that spot.
- **Double-check on the iPhone** — I can't do that from here: does
  "Wingfoilscout fürs iPhone starten" run through, does the terminal show an
  address like `http://192.168.…:8765/?k=…`, and does Safari reach the
  interface with it? Does the tab bar sit above the home indicator, does no
  input field zoom in when tapped, and does "Share" → "Add to Home Screen"
  work with icon and name? I measured in Chromium at iPhone sizes
  (320–430 pt), not on a device.
- **Report on the go:** send `report.html` to the iPhone via AirDrop and open
  it there offline — the map stays empty (tiles come from the network),
  everything else should be there.
- **Try the logbook:** log your next session (Logbook tab). Wingfoilscout then
  fetches the forecast, the models and — if there is a station within
  30 km — the measurement for exactly those hours. Suggestions for the wind
  window and the wind factor appear once two sessions point in the same
  direction; nothing is changed without "Apply". Old sessions can be added
  afterwards as long as the services still have those days (not checked how
  far back that goes for each service).
- **ruff is installed** (20 Sep, `brew install ruff` — Homebrew's Python
  refuses `pip install`, PEP 668). `tools/check.sh` now also runs the linter.
  In Claude's working environment on the Mac (a small Linux environment of
  its own) ruff is not available; there the step is still skipped and the
  linter is run on a copy instead.
- **Look at the Review tab**: run a search, then the Review tab, "Check". The
  chart first shows only the measurement and the range, with the buttons to
  switch more on below it; "Best model so far: …" can be selected from the first
  check with 1.15.0 on. For IJmuiden Zone 1 it should say Rijkswaterstaat
  IJmuiden Buitenhaven, with "instead of KNMI IJmuiden …" — if IJmuiden is
  among the best ten. The memory only becomes meaningful after many checks —
  ideally check once after every wingfoil weekend.
- **Look over the new names** (Catalogue tab). They come from OpenStreetMap,
  not from local knowledge. Uncertain, because the nearest place was only a
  hamlet or a street name: "Chiemsee – Pfaffing", "Fehmarn – Gold Südost"
  (the catalogue already has "Fehmarn – Gold", 3.5 km away), "Bol – westlich
  Zlatni Rat (Brač)", "Naxos – Mikri Vigla Süd/Mitte/Nord", "Neretva-Delta –
  Komin Ost/West", "Walchensee – Kirchelwand (südlich Urfeld)",
  "Heiligenhafen – Seebrücke" (the shoreline geometry moved the point into the
  Binnensee lagoon, not into the Baltic — check the coordinate).
- **Duplicate spot on Naxos:** "Naxos-Stadt – Agios Georgios (zweiter Pin)"
  is 100 m from "Naxos – Agios Georgios". Remove one (Catalogue tab) or say
  which one should stay.
- **DWD, yesterday:** on 19 Sep the previous day was missing (the ten-minute
  "recent" values ended on the 13th); the probe of 20 Sep shows Pelzerhaken
  complete from midnight the day before yesterday up to 12 UTC today. Just
  keep an eye on it — if the gap reappears, the way forward is the
  observation file `weather/weather_reports/poi/<ID>-BEOB.csv` (needs the
  mapping CDC station ↔ POI ID from the MOSMIX station catalogue).
- **Windguru: only with a station password.** Windguru releases measurements
  only through its API, and every request needs the station's API password.
  For stations whose password you have: the block `stationen: windguru:` in
  `config.yaml` (template at the end of `config.example.yaml`); check with
  `python3 tools/pruefstand.py --sonde --config config.yaml`. It doesn't work
  without a password — the station pages on windguru.cz fetch their charts
  via an internal route that answers 401 without a session, and Wingfoilscout
  deliberately doesn't get around that.
- **Check the shore break where you know the spots.** The 34 entries are an
  estimate based on location and exposure (`source: Spotwissen — unbelegt`),
  not observations. In the Catalogue tab, choose the filter "With shore
  break"; correct them in `spots.yaml` in the spot's `shorebreak:` block —
  `status` in quotes (`"yes"`, `"possible"`, `"no"`), `note` and `source`
  free text. If a spot you know as a shore-break spot is missing: put the
  same block after the `id:` line; `bash tools/check.sh` tells you whether
  it is valid.
- **Catch up on Instagram for the remaining spots.** The search ran on 18 Sep
  in a chat with a limited search quota (200 web searches) and got as far as
  100 spots. A new chat has a new quota; the sentence for it:

  > Read TODO.md. Add the spots that are missing from `instagram.json` —
  > two web searches per spot as described in `instagram.json` under `wie`,
  > the same filter rule, only instagram.com URLs taken verbatim from the
  > results. `python3 -m unittest tests.test_instagram` must stay green.

  Until then, the **Insta search** link on every spot does the same with one
  click. The filter "Instagram not searched yet" in the catalogue shows which
  spots are missing.
- Compute the shoreline geometry for `the-harbor-of-boulogne-sur-mer` —
  "Compute missing" under Data sources. A harbour basin may end up as
  "Unusable" on the Check coordinates page; then the question is whether the
  pin sits in the right place
- Run the benchmark once — the scoring is unchanged, so the numbers must stay
  at the baseline (the baseline keeps its nine pairs fixed; the new services
  don't change them):

      python3 tools/pruefstand.py

- Cross-check the thermal winds where you have been yourself: the numbers for
  71 spots come from spot guides and club websites, not from measurement
  series. Particularly open are the direction at Walchensee (the source says
  "Richtung Nordost pfeifend", whistling towards the north-east — which
  leaves open where it comes from) and the Ora at Malcesine (three sources,
  range 4 to 16 kn)
- Three sample checks whose answer you know: Brouwersdam in a westerly —
  onshore or side-on; Kabbelaarsbank in a south-westerly — flat with a short
  fetch; Torbole in the afternoon — thermal wind from the south
- Experience only you have: which of the former pins should stay,
  coordinates of your home lakes, confirm Salagou
- Three rows of the Takeout list had no coordinate at all and are missing:
  "Area sosta camper (Free)", "Parking Area", "Windsurfspot"

## Open questions only a real run can answer

- **Are the logbook's suggestions any good?** The rules have been tested on
  made-up sessions, not on real ones. The main open questions are whether a
  station up to 15 km away captures the wind at the spot (over land it
  usually measures less) and whether "fits" in the sense of "somewhere within
  the window" is narrow enough to pin down the wind factor. Look at it after
  the first five or six sessions.

- **Which model is right where?** Since 1.14.0 the Review tab collects the
  answer in `modellguete.json`. After a few weeks of checks: is ICON-2I or
  CH1 ahead at Lake Garda, HARMONIE or ICON-D2 on the North Sea, and does the
  Wingfoilscout scoring beat the raw models? Then decide whether the search
  should weight the models (Open — development).

- **Does ICON-2I resolve the Ora at Lake Garda?** First answer from the
  benchmark of 16 Sep: on 1 of 2 suitable days — partially. CH1 sees the
  Maloja wind on 2 of 3 days, ICON-D2 the Walchensee wind on none, the global
  models none of them. So the assumption from the catalogue still carries the
  thermal wind, and the regional models complement it. Every benchmark run
  rewrites the table; after ten runs the number is reliable. The original
  question behind the high-resolution models, unanswered for three runs. In
  the run of 16 Sep only CH1 in the Alps brought a consistent gain (median
  +5 kn, 86 % of sessions above 2 kn); ICON-D2 on flat German inland lakes
  brought nothing — the control group that shows the calculation is right.
  For ICON-2I, six sessions weren't enough. Since 1.5.1 the badge shows the
  median instead of the best hour; only that makes the number reliable
- **Drive times:** since the Python update (OpenSSL 3.6.3 instead of
  LibreSSL 2.8.3) OSRM should answer. The log then says "Drive times: N
  destinations routed via OSRM" instead of a handshake error
- **bulbjerg:** the entry once said "in the water, 25 km fetch" and once
  "moved 2697 m, 0 km² area — check coordinate". Currently the first one
  applies. For an open North Sea coast that one looks more plausible;
  `build_geometry.py --only bulbjerg --force` fetches the extract afresh

## Open — development

- **Stored texts of Review and Logbook** stay in the language they were
  computed in — the reasons a spot has no comparison ("no station within
  30 km …") and the logbook's comparison notes — until the next "Check". The
  report has the mechanism since 2.3.0 (`i18n.TD`, translated when each
  language version is written); `cache/rueckblick.json` and `tagebuch.json`
  would need to store the recipe (template and values) instead of the text.
- **Review of 25 Sep (`REVIEW.md`)**: all findings implemented in 1.19.0, the
  Content Security Policy with nonce in 1.19.1. Open: `netz.MAX_ANTWORT` per
  source (cosmetic).
- **Structure review of 20 Sep (`REVIEW.md`)**: A1, A3 and A4 (local) are
  done in 1.16.0. Open, in this order: A7 (below), `daten/` and `docs/` as a
  version of their own (A2), a shared network helper in `sources/netz.py`
  (A5).
- **Bring the check run on GitHub up to date** (A7): the comment
  "132 Tests", add `modellguete.json` and `tagebuch.json` to the list of
  personal files, install ruff as well
  (`pip install -r requirements.txt ruff`) — needs a token with the
  `workflow` scope, or SSH, so not touched so far.
- **iPhone, next steps:** a QR code for the Wi-Fi address (saves typing;
  needs either ~200 lines of QR encoder or the `qrcode` package — so far
  Wingfoilscout's only dependency is PyYAML). A service worker would show the
  most recently loaded interface offline; without it, the report is the
  offline version on the go. Dynamic Type (text size from the iOS settings)
  is not supported.
- **Logbook, next steps:** editing a session (today: delete it and log it
  again); gusts in the comparison (the suggestions only use the mean wind).
- **Better tide sources** (1.18.0 uses Open-Meteo's 8 km model, tide and wind
  surge combined, not an official tide table): for the German North Sea
  Pegelonline (BSH/WSV, measured and astronomical), for the Netherlands
  Rijkswaterstaat (the DD-API provides `WATHTE` and the astronomical
  prediction) — both only at tide gauges, so each spot has to be assigned to
  the nearest gauge. France (SHOM) and the UK (UKHO) have tide tables, but no
  free API. The change would be small: `tide.uebersicht()` gets the table's
  high and low waters instead of the model series; everything downstream
  stays the same.
- **The tide in the map popup is the destination's tide line** — the tidal
  current (direction, strength) is missing everywhere; there is no free
  source for it that I know of.
- **Model weighting from the memory** — only once `modellguete.json` has a
  few weeks of data: the search could prefer, per region, the model that came
  closest to the measurements there (today: ICON first, the regional model
  overrides). With a switch, off by default.
- **Rijkswaterstaat: gusts.** The DD-API has `WINDST` ("maximum 3-second
  gust of the last ten minutes") at some of the locations (number of active
  ones with gusts not checked). With it, the Review tab could compare gusts
  as well.
- What remains open from the review of 16 Sep (section "Was nach 1.7.0 offen
  bleibt" in `REVIEW.md`): assigning warnings to spots without a `region`.
  Looked into on 20 Sep: the MeteoAlarm feed carries an `EMMA_ID` or `NUTS3`
  code per warning, but no polygon — nor does DWD's linked CAP file. It
  would need a table code → area; no free source for it has been found yet.
  Plus the question whether `offshore_veto_km` should get a default value.
- Review tab, more countries: Italy and Spain — no free hourly source
  without a key that I know of. KNMI for the current day would need the KNMI
  Data Platform key (free, but requires registration); on the coast,
  Rijkswaterstaat now covers the current day.
- Windguru without a password: the only clean way in would be to ask the
  station owner for the API password (many spots have a club station). There
  is no technical route Wingfoilscout should take here.
- Review tab, current day at Météo-France: the département file comes once a
  day. Météo-France also has an observation API with a key (free,
  registration) — with it, today would work too
- `stationen.FR_RAHMEN` are rough département bounding boxes written from
  memory. If the probe finds no station for a French spot even though there
  should be one within 12 km, the bounding box is probably to blame — then
  check the two nearest départements (`fr_departements(lat, lon)`)
- An `ensemble:` block is missing from the personal `config.yaml`; the
  defaults apply (`weight: 0.5`, `top: 20`). To tune them, copy the block
  from `config.example.yaml`
- A comment for bulk import too ("Add spots" on the Search page, text or
  file): there is no field for it there — add it in the catalogue after the
  import
- Tour mode: several days as a chain with minimal driving — only makes sense
  now that the drive times are real
- Research access and dog rules for the spots that have none yet
- Renew the Leaflet checksums if cdnjs changes the files (the map then stops
  loading; the checksums are in `report.py`)

## Deliberately not

- Water temperature for inland lakes: no free source
- Windy account: no public API
- Discovering spots automatically by crawling: too many false hits
- Inventing thermal winds: they are only calculated where the catalogue says
  there is one, and only assumed where a source gives a strength
