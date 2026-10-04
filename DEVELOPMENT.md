# Development

Many names in the code — modules, functions, files, start scripts — are
German, because Wingfoilscout started as a German-only tool. This guide
explains them as they come up.

## Architecture

    wingscout/            the package — everything that computes
      cli.py              the flow of a search: catalogue → forecast → scoring → report
      config.py           reads config.yaml, quiver wind ranges
      spots.py            reads and pre-filters the catalogue
      geo.py              coordinates, distances, positions from text
      geometry.py         shoreline geometry: rings, rays, fetch length
      shoreline.py        fetches and stores the shoreline geometry per spot
      ingest.py           new spots from text, GPX, KML, GeoJSON, CSV
      xmlsicher.py        third-party XML without DOCTYPE and entities
                          (file import, MeteoAlarm)
      csp.py              Content Security Policy with a nonce per response or
                          per report — only our own scripts run (since 1.19.1)
      models.py           merges several weather models
      score.py            hourly scoring, sessions, trips
      tide.py             tides: high and low water to the minute, state per
                          hour, tide windows, the three settings (auto/yes/no)
      report.py           the HTML report
      webui.py            the browser UI: Search, Catalogue, Check coordinates,
                          Review, Logbook (one tab bar, `reiter()`), the two Help
                          pages behind the "?" in the tab bar; server,
                          endpoints, HTML skeleton
      hilfe.py            Help in the app: a small Markdown renderer for the
                          README (anchors as on GitHub, everything escaped, raw
                          HTML dropped), the sanitiser and the scoped CSS for
                          the methodology page — see "Help in the app" below
      hilfe/              bewertung.de.html, bewertung.fr.html, bewertung.es.html:
                          the translated methodology pages (the English one is
                          docs/bewertung.html)
      web/                CSS and JavaScript of the UI and the report as separate
                          files (since 1.16.0), read with `lies_web()`; also
                          mobil.js (collapses things on phones), ansicht.js
                          (Simple/Detailed in the report), tide.js (tide state
                          at the displayed time), beenden.js (the Quit button
                          in the tab bar), lauf.js (the dot on the tab while
                          something is running), sprache.js (the language
                          switcher), hilfe.css (the Help pages), the
                          home-screen icons (icon-*.png) and the creator's logo
                          (logo.png, in tab bar, footer and report)
      i18n.py             UI languages (since 2.1.0): T(), TN(), N_(), TD(), which
                          language applies, dates — see "Languages (i18n)" below
      zeitraum.py         the period of a search (since 2.3.0): start time
                          ("Starting when?", --ab), days from it, 16-day limit
      lang/               en.json, fr.json, es.json — the translations, keyed by
                          the German source text
      rueckblick.py       Review: recent destinations against the measurements of
                          the last few days; `spot_zeile()` computes one spot,
                          also for the Logbook
      tagebuch.py         session Logbook: your own sessions against forecast and
                          measurement, suggested wind ranges and wind factors
      modellvergleich.py  each weather model on its own against the measurements,
                          memory across all reviews (modellguete.json)
      pruefstand.py       the checks of the benchmark (see below)
      instagram.py        links out to Instagram, and the snapshot
      spotedit.py         changes single fields in spots.yaml, keeping comments
      thermik.py, sonne.py, sources/highres.py — thermal potential, sun position,
                          assignment of the regional models
      demo.py             synthetic weather data
      sources/            one module per third-party service: openmeteo, marine,
                          meteoalarm, overpass, ensemble, park4night, routing,
                          historisch (archive + running forecast up to today),
                          stationen (DWD, KNMI, Rijkswaterstaat, GeoSphere, DMI,
                          Météo-France, Windguru), ortsname (Nominatim: place
                          and country for new spots without a name)
    tests/                unittest, no extra dependencies, no network (blocked)
    tools/                check run, benchmark, hook, translation check
                          (i18n_texte.py), terminal language of the
                          double-click files (sprache.sh)
    README.md             the guide (English); README.de.md, README.fr.md,
                          README.es.md its translations — shown in the app too
    spots.yaml            the catalogue — the actual asset
    config.yaml           all thresholds, with comments
    geometry.json         computed shoreline geometry per spot (versioned, because
                          it is expensive)
    instagram.json        snapshot of the Instagram search per spot (versioned;
                          dated data — deleting it only costs the finds)
    pruefstand/           baseline of the benchmark (versioned)
    modellguete.json      memory of the model comparison (personal, not versioned)
    tagebuch.json         the session logbook (personal, not versioned)
    sprache.txt           the language chosen in the switcher (personal, not
                          versioned)
    pyproject.toml        package metadata (Python ≥ 3.9, PyYAML) and the linter rules
    cache/                fetched raw data (not versioned)

Rule for third-party services: any module in `sources/` may fail without
failing the run. The forecast is the only mandatory source; everything else
is supplementary and is reported in the log when it fails. That includes: a
response that looks different from the one captured when the module was
written counts as a failure of that source, not as a crash —
`except Exception` per spot, `_num()` for every field, and every response is
read with a size limit through `sources/netz.py::lies()`.

Every cache entry carries the coordinate it is valid for (`_spot` in the
Overpass extract, `bei` for protected areas, model assignment and drive
time) and is valid for no other. A coordinate correction therefore refetches
everything, without anyone having to remember to.

`load_spots` and `load_config` raise `KatalogFehler`/`KonfigFehler`
(`ValueError`), never `SystemExit` — that decision belongs to the command
line (`cli.main`, the `__main__` blocks of the scripts). In the UI, all
background work goes through `webui._starte()`, which always leaves the
"running" state again, whatever happens; the Check coordinates page and the
background runs exclude each other (409), and every file is written
atomically (`spotedit.schreibe_atomar`).

### Languages (i18n)

Since 2.1.0 the UI, the report and the program's messages come in German,
English, French and Spanish (`wingscout/i18n.py`). German stays the source
language: texts are written in German in the code, and that German text is
the key in `wingscout/lang/en.json`, `fr.json` and `es.json`. A missing
translation falls back to German, and so does a translation whose
placeholders don't fit — a gap never breaks a page.

- **Python:** `T("Spots suchen")` returns the text in the current language.
  Placeholders are named and passed as keywords:
  `T("{n} Spots im Katalog", n=278)`; singular and plural:
  `TN("{n} Warnung", "{n} Warnungen", n)`. Tables at module level are built
  at import time, so their texts are only marked with `N_()` and translated
  where they are used: `T(TABELLE[k])`. The upper-case names are deliberate:
  `t` already names a destination or a time in report and search. `T()` never
  escapes — escape the values you pass in, exactly as before.
- **Texts in data (since 2.3.0):** a search computes once and writes its
  report in all four languages (`report.fassungen_schreiben()`, stored in
  `cache/report/` with an `index.json` of checksums; the Destinations tab
  serves the version of the request's language, `webui.report_in_sprache()`).
  So a text that is created while computing and shown later — an hour's veto,
  a session's notes, why a spot was left out, a compass point, the kind of an
  overnight spot — comes from `TD()`/`TND()` instead of `T()`/`TN()`: the same
  string (it compares, sorts and serialises like it), which also carries its
  recipe (template and values). `i18n.uebersetzt(x)` sets it in the language
  that applies now; `report._esc()` does that for everything it escapes, so
  only joins and script data need it explicitly. A value whose form depends
  on the language (an hour from `stunde()`) goes in as `i18n.spaeter(f, x)`.
  `tests/test_report_sprachen.py` holds it together: a demo search computed
  in German and written in English, French and Spanish must equal, character
  for character, the report a search in that language writes itself — a `T()`
  left in the computation shows up there as a difference. Texts stored as
  JSON (Review, Logbook) lose the recipe and stay in the language they were
  computed in (see `TODO.md`).
- **JavaScript:** every page gets the translations its scripts need as
  `window.T`, ahead of its own scripts (`js_vorspann()`), plus `t()` with the
  same placeholders — `t('{n} Spots', {n: x})` — and `N_()`. Only literal
  strings written directly inside `t('…')` or `N_('…')` in
  `wingscout/web/*.js` are collected: no concatenation, no variables, no
  template literals.
- **Numbers, dates and hours** come in the form of the language; the German
  output is the same as before 2.1.0. In Python: `i18n.zahl()` (decimal comma
  or point — 4,2 · 4.2; thousands separators only with `gruppen=True`),
  `datum_jahr()` (18.09.2026 · 18 Sep 2026 · 18 sept. 2026 · 18 sep 2026),
  `datum_zeit()` (20.09.2026 19:09 · 20 Sep 2026, 19:09), `stunde()` (a full
  hour for "{von}–{bis} Uhr": "08" in German as before, "08:00" in the other
  languages), plus `tag()`, `wochentag()` and `datum()` for weekday and short
  date. In the browser, `zahlFmt()`, `datumZeit()` and `tagKurz()` from
  `js_vorspann()` do the same. Numbers that German also writes with a point
  (wing sizes "4.2–6.5 m²", drive "1.5 h") stay that way in every language.
  Weekday and month abbreviations come from fixed tables (`WOCHENTAGE`,
  `MONATE`), not from `strftime("%a")`: a double-clicked Python on macOS runs
  with the "C" locale.
- **Which language applies** is set per thread — the first that fits:
  - *UI pages* (`i18n.fuer_anfrage()`, on every request): the environment
    variable `WINGSCOUT_SPRACHE` (`de`, `en`, `fr`, `es`), then the choice
    stored in `sprache.txt`, then the browser's `Accept-Language` — the first
    of the four languages by weight (the region doesn't count, `de-CH` → `de`;
    `q=0` means "not wanted" and is skipped) — then English if the browser
    sends a header that names none of the four, German if there is no header
    at all. A search run takes the language of the request that started it.
  - *Command line and terminal* (`i18n.fuer_kommandozeile()`: `wingscout.cli`,
    `run.py`, the terminal lines of `wingscout.webui`): `WINGSCOUT_SPRACHE`,
    then `--sprache` (cli only), then `sprache.txt`, then `LC_ALL`,
    `LC_MESSAGES`, `LANG`, then the macOS language settings (`AppleLanguages`,
    read from `~/Library/Preferences/.GlobalPreferences.plist` itself — no
    `defaults` call, the security rules forbid starting other processes),
    then English. `wingscout.cli` builds its `--help` before that choice, so
    the help follows only `WINGSCOUT_SPRACHE` or `sprache.txt` and is German
    otherwise.
  - *Double-click files* (`*.command`): they print their own terminal lines
    through `tools/sprache.sh`, which they source (`. tools/sprache.sh`) and
    which provides `sag "Deutsch" "English" "Français" "Español"`; a missing
    translation falls back to English, then German. The order there:
    `WINGSCOUT_SPRACHE`, then `sprache.txt`, then the macOS language settings
    (`defaults read -g AppleLanguages`), then `LC_ALL`, `LC_MESSAGES`, `LANG`,
    then English. If `tools/sprache.sh` is missing, the lines stay German. It
    exports nothing — the Python a script starts chooses its own language — and
    it is written for bash 3.2, the one macOS ships (no associative arrays, no
    `${x,,}`). The tools the scripts call (`tools/check.sh`,
    `tools/aktualisieren.sh`, the benchmark, `build_geometry.py`) still print
    German, and "Auf GitHub veröffentlichen" doesn't use `sprache.sh` at all.
- **The language switcher** (DE · EN · FR · ES) sits next to the logo and
  version — in the tab bar on a computer, in the footer on a phone
  (`sprachwahl()` in `webui.py`, `web/sprache.js`). The choice goes to the
  server (`POST /sprache`), is stored in `sprache.txt` (personal, in
  `.gitignore`) and applies from the next page on — the Destinations tab
  included, since 2.3.0 (see "Texts in data" above); the page then reloads in
  the new language. `report.html` itself stays in the language of its search.
- **Tests run in German:** `tests/__init__.py` sets `WINGSCOUT_SPRACHE=de`, so
  the tests check the German texts whatever the switcher or the system
  language says on that machine. The languages themselves are covered by
  `tests/test_i18n.py`: every text from the code is translated in every
  language and no entry is left over; placeholders, HTML tags with their
  attributes (the text of `title`, `alt`, `aria-label` and `placeholder`
  aside) and leading or trailing whitespace are the same as in the German
  text, and every translation can actually be filled in; the files are in
  canonical form (keys sorted, indented by one space, characters not escaped,
  a newline at the end — on failure the test prints the one-liner that
  rewrites the file); the order of the language choice (browser header,
  `sprache.txt`, `WINGSCOUT_SPRACHE`, `--sprache`, system and macOS settings);
  `POST /sprache` on a running server; and every page of the UI plus the
  report rendered in all four languages (language in `<html>`, the switcher,
  no unresolved placeholders). Those tests switch languages for themselves,
  with `sprache.txt` in a temporary folder, and leave German behind.
- **Missing translations:** `python3 tools/i18n_texte.py` collects every
  source text and shows per language how many are translated, missing or
  left over (no longer in the code); `--fehlend en` prints the missing
  English texts as JSON, `--alle` all texts with where they occur. The tests
  check that every language knows every text and keeps the same placeholders
  and markup. Translations are read once per process: after editing a
  `lang/*.json` file, restart Wingfoilscout (or call `i18n.neu_laden()`).
- **What isn't translated:** data rather than program text. Spot names,
  notes and the other texts in the catalogue (`spots.yaml`) and some place and
  area names from OpenStreetMap stay in their original language, mostly
  German.

### Help in the app

The "?" button in the tab bar — on every page, also in the bar the server
puts into the report; on phones fixed at the top right next to "Quit" —
opens two pages in the current UI language, inside the normal frame (tab bar,
footer, Content Security Policy with nonce), reachable in Wi-Fi mode like any
other page:

- **`GET /hilfe`, the guide:** `README.md`, or `README.<code>.md` for German,
  French and Spanish, with a table of contents of the `##` sections (beside
  the text on a computer, collapsed above it on a phone).
- **`GET /hilfe/rechnung`, "How Wingfoilscout calculates":**
  `docs/bewertung.html`, or `wingscout/hilfe/bewertung.<code>.html`, with its
  figures, in its own box.

If a translation is missing, the English version is shown with a translated
one-line note, and the content carries `lang="en"`. Both pages are built in
`wingscout/hilfe.py`, once per file and modification time — an edited
README shows up on the next page load, without a restart:

- **The guide** goes through `hilfe.rendern()`, a small Markdown renderer
  without a third-party package: headings with the same anchors GitHub makes
  (`slug()`: lower case, punctuation and symbols removed, spaces → hyphens,
  repeats get `-1`, `-2` …), so links like `(#command-line)` work; paragraphs,
  nested lists, fenced and indented code, inline code, bold/italic, pipe
  tables, quotes, rules, hard line breaks. Every text is escaped. Raw HTML in
  the Markdown is *not* rendered but dropped (the screenshot block at the
  top of the README — the app is the interface), an image becomes its alt
  text, and the language line ("This guide in: …") is left out because the
  app has its own switcher. Where links lead (`link_ziel()`): http(s) and
  mailto open in a new tab; a README → the guide; `docs/bewertung.html` (and
  its address on the website) → `/hilfe/rechnung`; any other file of the
  repository → its page on GitHub; `#anchor` stays on the page; everything
  else (`javascript:`, `data:` …) is shown as plain text. Headings move down
  one level — the page has its own `<h1>`.
- **The methodology page** is embedded, not framed: `hilfe.saeubern()` takes
  the content of its `<body>` and drops scripts, frames, objects, forms,
  `<link>`/`<meta>`/`<base>`, comments, every `on…` attribute, every address
  that would load something, and every link that isn't http(s), mailto, `#…`
  or a path in the repository. Relative links resolve against `docs/`:
  `index.html` → the website, `demo.html` → the example report; external links
  open in a new tab. Whatever is left open is closed, so a broken translation
  can't break the page around it. Its stylesheet comes from the English
  `docs/bewertung.html` only — a translation supplies text, not style — and
  goes through `css_eingrenzen()`: `.methode` in front of every selector,
  `:root`, `html` and `body` become `.methode` itself, so the page's colour
  variables (the dark ones too) apply inside its box and nowhere else.
  `wingscout/web/hilfe.css` adds the frame (paper card on a computer, full
  width on a phone).

**When `README.md` or `docs/bewertung.html` changes, the translations need the
same change.** The drift tests in `tests/test_hilfe.py` say where:

- `README.<code>.md` against `README.md`: the same headings per level in the
  same order, the same number of fenced code blocks, the same set of external
  addresses, and every link to a section of the same file (`#…`) hits one of
  its headings — with the anchors GitHub makes from the *translated*
  headings.
- `wingscout/hilfe/bewertung.<code>.html` against `docs/bewertung.html`: the
  same sequence of tags with the same attribute names, the same values of
  `href`, `src`, `id`, `class` and `xlink:href`, `<html lang="<code>">`, and
  the same numbers in the text (decimal comma and point count as the same,
  "15:00" as "15 h").

A translation that doesn't exist yet shows up as *skipped*, one that has
drifted as a failure naming the first difference. `SCORING.md` stays
English-only; the methodology page and its translations follow it (see
"Working with Claude").

## Tests

    tools/check.sh                       # full check run, one to two minutes
    python3 -m unittest discover -s tests -t .
    python3 -m unittest tests.test_geometry -v

Or in the Finder: double-click **"Tests ausführen"** ("run tests").

`tools/check.sh` checks in five steps: syntax (every `.py` file, plus
`node --check` over `wingscout/web/*.js` if Node is installed), linter, tests,
catalogue, leftovers (`print()` outside the UI, personal files or the home
coordinate from `config.yaml` in the commit). The linter is **ruff** with a
deliberately small rule selection
(`pyproject.toml`): Pyflakes (unused imports and variables, undefined
names), syntax errors and three Bugbear rules for mutable default values. No
style rules — the lines are long on purpose. If ruff is missing, the step is
skipped with a note; run `python3 -m pip install ruff` once and it is
included from then on. The check run on GitHub doesn't install ruff yet and
therefore skips it (see `TODO.md`, "Prüflauf auf GitHub nachziehen" — bring
the GitHub check run up to date).

The tests don't need a network — and since 1.14.0 they don't get one:
`tests/__init__.py` replaces `urllib.request.urlopen` with a version that
rejects everything except 127.0.0.1 with `NetzImTest`. On 20 September a
test of the probe had actually queried Rijkswaterstaat, because a new request
had not been stubbed. Third-party responses are stubbed — real excerpts,
captured in the browser. The shoreline geometry is tested on a synthetic
lake, the server on a real server process on a free port.
`tests/test_catalog.py` checks the catalogue's form: unique IDs, value
ranges, `dogs`/`access` as text and not as booleans.

What a test should find: regressions. On its first run the synthetic lake
immediately exposed a bug (moving a point into the water took the nearest
vertex instead of the nearest point on the shoreline), and the escaping
tests found two XSS paths in the map. Those are the valuable tests — tests
that merely repeat what the code does are not.

### The benchmark — with network

    python3 tools/pruefstand.py            # or double-click "Prüfstand"
    python3 tools/pruefstand.py --sonde    # does every service answer?

("Prüfstand" is the German name of the benchmark; `--sonde` runs the
probe.) What the tests can't see: whether the weather services still answer
the way the code reads them, and whether the scoring on real data is still
as good as before. That is what `wingscout/pruefstand.py` (the checks),
`sources/historisch.py` (archived forecasts) and `sources/stationen.py`
(measurements from DWD, KNMI, GeoSphere) are for. The run ends with a report
and an exit code; the numbers of a good run are kept as the baseline in
`pruefstand/grundlinie.json` (versioned), which every later run compares
against. Not part of `check.sh`: it needs a network and takes minutes. The
description for users is in `BENCHMARK.md`.

One rule the benchmark forced right when it was built: **the shoreline
geometry states whether its origin lies in the water** (`wasser` in the
entry). Without water within three kilometres the rose is meaningless, even
if it measures ten kilometres — the rays then run over land.

## Git

Before every commit, the hook runs `tools/check.sh`. The hook isn't
versioned; after a fresh clone, run `tools/install-hooks.sh` once.

For a while the hook ran with `--schnell` ("quick"), and that was a mistake:
the subset `test_[gics]*.py` left out the UI of all things — the part that
breaks most often. The full run took five seconds at the time — no reason to
leave anything out. `--schnell` still exists for manual use.

These don't belong in the repository: `config.yaml` and copies of it,
`cache/`, `report.html`, `ui_defaults.json`, `modellguete.json`,
`tagebuch.json`, the app's `*.neu` files, exports (Takeout, GPX/KML/GeoJSON,
ZIP), screenshots, editor backups, local Claude settings. They are listed in
`.gitignore`, and `tools/persoenliche_daten.py` holds the same list as
patterns: `tools/veroeffentlichen.sh` refuses them, and both the local check
run and the one on GitHub raise an alarm if one ends up in a commit anyway
(`tests/test_sicherheit_repo.py` keeps the two lists in step). The same tool
looks for the home coordinate from your `config.yaml` in what is about to be
committed. `geometry.json` is versioned even though it is derived: half an
hour of Overpass queries is worth it.

`config.yaml` is personal (starting point, weight, gear). Only
`config.example.yaml` is versioned; on first start, `ensure_config()` creates
the personal copy from it. That way it never conflicts when updating —
before, every pull would have brought in the other person's values.

`geometry.json` has its own merge driver (`tools/merge_geometry.py`,
registered by `tools/install-hooks.sh`). Otherwise two people who
independently compute missing spots create a conflict that isn't really one:
the entries complement each other. The driver merges both versions; for the
same spot ID your own version wins, since the content is derived anyway. If
the driver isn't in your local Git configuration, Git reports a normal
conflict — nothing breaks.

### The two scripts

`tools/veroeffentlichen.sh` ("publish"; or double-click **"Auf GitHub
veröffentlichen"**, "publish on GitHub") checks, commits and pushes — in that
order, because whatever doesn't pass the tests shouldn't be uploaded in the
first place. With `--version 1.1.0` it also sets the number in
`wingscout/__init__.py`, requires a matching section in `CHANGELOG.md` and
creates the tag. Since 4 October 2026 (review findings D1, D4, D7) it

- commits changes to files that are already versioned (`git add -u`) and
  lists new files, which only go in if you type `ja` ("yes"; `nein` leaves
  them on the Mac, Enter cancels) — no more `git add -A`;
- refuses if a path from `tools/persoenliche_daten.py` or the home coordinate
  from `config.yaml` is in the commit;
- stops before doing anything unless `git config user.email` is the GitHub
  `…@users.noreply.github.com` address;
- pushes only the branch and the new tag, atomically
  (`git push --atomic origin main refs/tags/vX.Y.Z`) — never all local tags.

`tools/aktualisieren.sh` ("update"; or double-click **"Neuen Stand
holen"**, "get the latest version") fetches: it puts your unfinished work
aside, runs `fetch` and `rebase`, brings back what it put aside, and runs the
checks. If something goes wrong, it tells you how to get back — nothing is
thrown away, every intermediate state is in the stash or the reflog. If the
check run fails on the new state, it names the previous commit to jump back
to.

### Check run on GitHub

`.github/workflows/tests.yml` runs `tools/check.sh` on every push to `main`
and on every pull request. The same check run as locally, just independent
of whether anyone has installed the hook. It also checks that no personal
files are versioned.

**Careful when pushing with a token:** GitHub rejects commits that create or
change anything under `.github/workflows/` if the token lacks the permission
for it ("refusing to allow a Personal Access Token to create or update
workflow") — *Workflows: Read and write* on a fine-grained token, the
`workflow` scope on a classic one. Over SSH the restriction doesn't apply.

Editing a file with `sed -i` on the Mac occasionally loses the executable bit
of the `.command` and `tools/` scripts; `chmod +x` fixes it.

### Pushing to GitHub

The repository has been **public** since 2.0.0; for 2.3.0 it was deleted
and created again with a fresh history, so that it no longer hands out the
MIT versions (`SECURITY.md`, addendum of 4 October 2026, and "A fresh
repository" below). What doesn't belong in it —
the personal `config.yaml` (name, weight, home coordinates), Takeout
exports, `tagebuch.json`, `modellguete.json` and the rest of the list in
`tools/persoenliche_daten.py` — is kept out by `.gitignore` and by
`tools/veroeffentlichen.sh`, and `tests/test_catalog.py` and
`tests/test_sicherheit_repo.py` fail if it gets versioned anyway; details in
`SECURITY.md`. Whatever has been pushed stays in the history — and on GitHub
it remains retrievable as a dangling copy even after a force push (see the
addendum of 3 October 2026 there). So look before publishing, not after.

Account: **DarkPirateGo**, repository `DarkPirateGo/wingfoilscout`. One-time
setup, after an empty repository named `wingfoilscout` has been created on
github.com (without README, .gitignore or licence — those are already here):

```bash
cd ~/ClaudeCode/wingscout
git remote add origin https://github.com/DarkPirateGo/wingfoilscout.git
git push -u --follow-tags origin main    # only tags on main's history, never a stray old one
```

After that, `git push` is enough.

Until 2.1.0 the repository was called `wingscout` (the local folder and the
Python package keep that name). A clone made before 2.3.0 — under either
name — no longer fits: the history starts anew with 2.3.0, and
`tools/aktualisieren.sh` would try to put the old commits on top of the new
ones and stop halfway (if it did: `git rebase --abort`, then `git stash pop`).
Rename the old folder, clone afresh and copy your personal files across from
the old folder (`config.yaml`, `tagebuch.json`, `modellguete.json`,
`ui_defaults.json`, `sprache.txt`; also `spots.yaml` and `geometry.json` if
you added spots of your own):

```bash
git clone https://github.com/DarkPirateGo/wingfoilscout.git
```

**Signing in when pushing.** This account has no GitHub password — so git
needs one of the following:

- **Fine-grained personal access token** (recommended): on github.com,
  *Settings → Developer settings → Personal access tokens → Fine-grained
  tokens → Generate new token*. Give it an **expiration** (90 days, say — a
  token that leaks stops working by itself), under *Repository access* only
  `wingfoilscout`, and under *Repository permissions* **Contents: Read and
  write** plus **Workflows: Read and write** — without the latter, every push
  that touches `.github/workflows/` is rejected (*Metadata: Read-only* is
  added automatically and can't be removed). On the first `git push`, git
  asks for a username (`DarkPirateGo`) and a password — enter the token
  there. macOS then remembers it in the Keychain. When the token expires,
  the push fails with an authentication error; create a new one and enter it
  at the next push. If the repository is deleted and recreated on GitHub,
  assign it to the token again.
- **SSH key**: `ssh-keygen -t ed25519 -C "wingscout"`, add the contents of
  `~/.ssh/id_ed25519.pub` under *Settings → SSH and GPG keys*, and use
  `git@github.com:DarkPirateGo/wingfoilscout.git` as the address. No expiry
  to look after, and the workflow restriction doesn't apply.

A classic token with the `repo` scope works too, but don't use it here: it
can read and write every repository of the account, private ones included,
and still needs the `workflow` scope for changes under `.github/workflows/`.

**Attributing commits.** Anyone who looks at the history can read the
author address of every commit, so commits and tags carry the
`…@users.noreply.github.com` address from *Settings → Emails* — it doesn't
forward anywhere, and GitHub links the commits to the profile with it:

```bash
git config user.email "<ID>+DarkPirateGo@users.noreply.github.com"
```

Since 4 October 2026 `tools/veroeffentlichen.sh` refuses to commit or tag
with any other address and says how to set it (`git config --global
user.email …` for all repositories, or the line above for this one). Up to
2.1.0 most commits carried an Apple relay address; that history went with
the old repository. As a second safety net, *Settings → Emails → Block
command line pushes that expose my email* makes GitHub reject such commits
as well.

**Settings on GitHub** (3 October 2026, after switching to public; set
again after the repository was recreated for 2.3.0 — a new repository starts
without any of them):

- Ruleset "Protect main" (*Settings → Rules → Rulesets*, target: default
  branch): deleting and force-pushing `main` are blocked. Normal pushes from
  `tools/veroeffentlichen.sh` go through; the ruleset deliberately requires
  neither pull requests nor passing check runs, otherwise the script could no
  longer push directly. Anyone who has to rewrite the history again disables
  the ruleset first — otherwise GitHub rejects the force push.
- *Advanced Security*: Secret Protection with push protection (a push
  containing a recognisable secret is rejected), Private vulnerability
  reporting, Dependency graph and Dependabot alerts on; automatic Dependabot
  pull requests and CodeQL off.
- *Actions*: workflows get a read-only token; workflows from outside
  contributors' pull requests run only after approval.
- *Pages*: source branch `main`, folder `/docs` — the landing page
  https://darkpiratego.github.io/wingfoilscout/.
- *Issues*: the label `spot` (*Issues → Labels → New label*). The spot form
  (`.github/ISSUE_TEMPLATE/spot.yml`) assigns it; GitHub drops a label that
  doesn't exist without saying so.
- *About* (the gear next to "About" on the repository page): description,
  "Use your GitHub Pages website", topics.
- Account: email address private; future commits carry the
  `…@users.noreply.github.com` address (`git config user.email` in this
  folder).

**A fresh repository (2.3.0).** With the licence change to PolyForm
Noncommercial 1.0.0, the repository was deleted on GitHub and created again,
empty, under the same name; on the Mac, `main` was started anew as a branch
without history (`git checkout --orphan`), the old tags were deleted, and
`tools/veroeffentlichen.sh --version 2.3.0` made the first commit and pushed
it. The publish script handles that case: on a first commit it checks the
whole tree. The old history exists only in a backup bundle outside the
project folder (`Claude outputs/neu-anlegen.sh` made it). Should it ever be
necessary again: back up the history, delete and recreate the repository on
GitHub (the ruleset and every other setting go with the old one), assign the
new repository to the token, push, then set the settings above again.

A GitHub release is made from the tag: on the repository page *Releases →
Draft a new release*, select tag `v1.0.0` and paste the section from
`CHANGELOG.md` as the description. For the next version, increase the number
in `wingscout/__init__.py`, add the section to the changelog and set
`git tag -a v1.1.0 -m "…"`.

## Working with Claude — what a new chat needs to know

Philipp (the maintainer) isn't a programmer but a vibe coder: he reads,
decides, tries things out and publishes; Claude writes the code directly in
the folder `~/ClaudeCode/wingscout` (the folder connected to the desktop
app). The conversation history doesn't carry over into a new chat — that's
why the rules are written down here, not kept in anyone's head:

- **The entry point** is the sentence at the top of `TODO.md`. `TODO.md` is
  the handover, `CHANGELOG.md` holds the reasons, this file is the
  architecture. Whatever isn't in any of the three wasn't important enough.
- **Keep `SCORING.md` and `docs/bewertung.html` in step:** whoever changes a
  threshold, a weight or a veto changes the matching sentence in both — the
  tests `test_bewertung_md_stimmt_mit_der_konfiguration` and
  `test_bewertung_html_stimmt_mit_der_konfiguration` remind you when a number
  no longer matches. `docs/bewertung.html` is the very page published as the
  methodology page; a change belongs in both files — and in its translations
  in `wingscout/hilfe/`, just as a change to `README.md` belongs in
  `README.de.md`, `README.fr.md` and `README.es.md`. The drift tests in
  `tests/test_hilfe.py` name what no longer matches (see "Help in the app").
- **`docs/` is the landing page** (GitHub Pages, since 2.1.0): `index.html`,
  the example report `demo.html`, `bewertung.html` and the images. If the UI
  changes visibly, regenerate the screenshots and the example report — never
  from your own `config.yaml`: copy the folder, give the copy a `config.yaml`
  with a neutral starting point (so far Hamburg, 53.55 / 9.99), then
  `python3 -m wingscout.cli --demo --days 3 --radius 500 --sprache en` →
  `docs/demo.html`. The screenshots: start the UI from the copy in English
  (`WINGSCOUT_SPRACHE=en python3 -m wingscout.webui`, or pick EN in the
  switcher — the choice lands in the copy's own `sprache.txt`) and capture it
  at phone size (390 × 797 points, double resolution, light and dark, demo
  notice hidden, 256 colours): the Search tab, the Destinations, an expanded
  destination and the hourly grid —
  `docs/bilder/en/{search,destinations,details,grid}-{light,dark}.png`. The
  pages load nothing from third-party servers (no fonts either); only the
  example report, like every report, fetches the map from cdnjs and
  OpenStreetMap.
- **Nothing personal in versioned files** — no exports (Takeout, GPX), no
  addresses, no home as a starting point or example coordinate (examples
  and tests use Hamburg, 53.55/9.99, like the demo), no body weight, and
  catalogue notes don't address anyone personally ("your Google list",
  "your reference") or measure distances from anyone's home. Tests check
  what *should* be there, never a list of private values — such a list would
  itself be public. The tests in `tests/test_catalog.py`
  (`PersoenlicheKonfiguration`) and `tests/test_sicherheit_repo.py` watch
  over this; `SECURITY.md` (addendum of 27 September 2026) says what had to
  be done before publishing.
- **Claude never commits or pushes.** Philipp publishes, always with the
  same script, and Claude hands him the command ready to paste — with
  `cd ~/ClaudeCode/wingscout` in front and the next free version number:

      tools/veroeffentlichen.sh --version X.Y.Z "Description"

  The script sets the number in `wingscout/__init__.py` itself.
  `git tag --sort=-v:refname | head -1` shows the latest tag and so which
  number is next — look it up, don't guess: Philipp also publishes in the
  middle of work, and then everything after that goes into a new section,
  not into the one already published. Every version needs its section
  `## X.Y.Z — DD.MM.YYYY` at the top of `CHANGELOG.md`, otherwise the script
  asks. A pure documentation change goes out without `--version`.
- **Before every handover** to Philipp: `bash tools/check.sh` green, the test
  count in `TODO.md` up to date, and `TODO.md` in the state a new chat should
  find it in. What Philipp should do himself afterwards (restart, probe,
  trying things out) goes under "Offen — Philipp" ("open — Philipp") with
  commands ready to copy.
- **One English release note per version**, `Claude outputs/release-vX.Y.Z.md`,
  for the GitHub release: what's new, the numbers, how to update. The folder
  is where the desktop app saves files; it is in `.gitignore` but sits inside
  the project folder; the previous notes are the template.
- **Languages.** The conversation with Philipp stays **German**.
  Documentation, changelog entries and release notes are written in
  **English** since 2.1.0; `REVIEW.md` and `WAS-SICH-GEAENDERT-HAT.md` stay
  German as historical documents. Code comments stay German, as before. UI
  texts stay German in the source code and are translated through
  `wingscout/lang/en.json`, `fr.json` and `es.json` — `T()`/`TN()`/`N_()` in
  Python, `t()`/`N_()` in JavaScript (see "Languages (i18n)" above);
  `python3 tools/i18n_texte.py` lists missing translations, and the tests
  check that every language is complete. Explanations without jargon,
  commands always as a block to copy.
- **Call uncertain things uncertain.** Anything built from a description
  without reaching the service is marked "not yet probed" ("nicht gesondet"
  in German files) in `BENCHMARK.md` and `TODO.md` until
  `tools/pruefstand.py --sonde` has confirmed it. Numbers from memory
  (station lists, bounding boxes) are marked as such. A wrong answer given
  with conviction is worse than "I don't know".
- **Check services before building.** The working folder where Claude runs
  code has no network — but the desktop app's built-in browser runs on
  Philipp's Mac and has one. Through it, APIs can be queried in advance
  (JavaScript `fetch` on a page of the service itself, so that CORS doesn't
  block it). That is how Rijkswaterstaat (new address), DMI, the Open-Meteo
  models and the place names (Nominatim, one request per second) were
  checked on 20 September. Only what can't be reached this way is built
  blind — and then it is marked "not yet probed".
- **Licence:** PolyForm Noncommercial 1.0.0 since 2.3.0 (MIT up to 2.1.0).
  `LICENSE` is the exact licence text with the `Required Notice` line on top —
  never reword it. Don't call Wingfoilscout "open source" (the licence isn't
  one by the OSI definition); "free for noncommercial use, source code on
  GitHub" is accurate. `geometry.json` stays under the ODbL of OpenStreetMap.
- **Spot suggestions** come in as issues with the label `spot`, from the form
  `.github/ISSUE_TEMPLATE/spot.yml`. The app opens it with the fields filled
  in (`webui.spot_vorschlag()`, `vorschlagUrl()`/`korrekturUrl()` in
  `katalog.js`); the parameter names must be the `id`s of the form's fields —
  `tests/test_spot_vorschlag.py` checks that. How a suggestion is taken in:
  `CONTRIBUTING.md`, "Taking in a suggestion".
- **After every publish, quit and restart Wingfoilscout** — the running UI
  has said so itself since 1.13.0, but the reminder still belongs in the
  answer.

## What to watch out for when making changes

Everything that goes into the report passes through `_esc()`; everything that
goes into the map data is written as JSON with Unicode escapes. New external
URLs in links go through `_safe_url()`. New external scripts get an
`integrity` attribute. New network calls get a `timeout`. The tests in
`tests/test_security.py` enforce this.

Since 1.16.0, CSS and JavaScript live as separate files in `wingscout/web/`
and are served unchanged — no more doubled braces, and `node --check` in the
check run finds syntax errors before a page stays blank. Data goes as JSON
into a variable ahead of the script (`var TAGEBUCH = …`, `var KARTE = …`),
with `<`, `>` and `&` as Unicode escapes so that a spot name like
`</script>` can't end the script (`_json_im_skript`). The only templates
left are the HTML skeleton of the start page (`page()`, an f-string) and the
grid toggle in the report (`_raster_schalter`, a %-template).

Every `.py` file starts with `from __future__ import annotations`. Without
it, Python evaluates type hints immediately, and `str | None` only exists
from 3.10 on — a file without this line can't even be loaded under Apple's
bundled Python 3.9. The error then looks like a broken test, not like an old
environment; that is exactly how it happened on 13 September 2026 (113
instead of 132 tests, one module not loaded at all).

The minimum is therefore **3.9**, verified with the full check run under
3.9.23. The check run on GitHub runs 3.9 and 3.12 side by side, so that
nobody slips in syntax unnoticed that won't run on a fresh Mac.
`tools/check.sh` and the double-click start check the version first and say
so in plain words.

For phones, since 1.17.0: every page's viewport has `viewport-fit=cover`,
otherwise `env(safe-area-inset-*)` returns only zeros and the tab bar sits
under the home indicator. Input fields need a font size of at least 16 px,
otherwise Safari zooms in on tap and doesn't zoom back out. Full height is
`svh`/`dvh`, not `vh`. And if you put a table or a chart inside a flex or
grid child, set `min-width: 0` — otherwise the child grows with its widest
content and stretches the whole page instead of scrolling sideways (exactly
what had happened in the Review and Catalogue tabs). `<datalist>` is not an
option on iOS: Safari puts the dropdown over the input field.

In YAML, `no`, `yes`, `on` and `off` are booleans. Put text fields with these
values in quotes — `dogs: "no"`.
