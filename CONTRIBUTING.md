# Contributing

Wingfoilscout is a personal tool, not a product. This page describes how two
people work on it without wrecking each other's work.
Anyone can suggest a spot, without Git — that comes first. What you
contribute is under Wingfoilscout's licence; see
[Licence of contributions](#licence-of-contributions) at the end.

## Suggesting a spot — no programming needed

The quickest way to improve the catalogue is the form on GitHub:
https://github.com/DarkPirateGo/wingfoilscout/issues/new?template=spot.yml

The app opens it for you: **“Suggest it for everyone”** in the **Add spots**
panel and below **“Add a new spot”** in the Catalogue tab — there filled in
with what you entered above it —, and **suggest a correction** next to
every spot in the catalogue, filled in with that spot's name and
coordinate. You need a free GitHub account. The form asks for the name, the
coordinate, the kind of water, good wind directions, what others should
know and — required — where your knowledge comes from.

A suggestion is a public issue under your GitHub name. Don't put anything
private in it: no home addresses, phone numbers or names of other people.

What happens next: someone who looks after the catalogue checks the
suggestion (see below) and adds it to `spots.yaml`; from the next version
on, it is in the catalogue for everyone. The issue is closed with a note
saying which version.

### Taking in a suggestion (maintainers)

1. **Read it.** Without a source that can be checked — sessions of your own
   there count, a page that says so is better — ask in the issue before
   adding anything. Leave out spots on private ground and in areas where
   wingfoiling is not allowed.
2. **Add it** on your own computer: paste `Name; lat, lon; water type` into
   the **Add spots** panel with **Compute shoreline geometry right away**
   ticked. Points less than 300 m from an existing spot are skipped — for a
   correction, change the existing spot in the Catalogue (rename, move,
   comment) instead.
3. **Check it.** Put the pin where you get into the water with **move** in
   the Catalogue (it recomputes the geometry and sets `verified: true`).
   In `spots.yaml`, check what was guessed (water type, bottom, country),
   put the note in `notes` and the source in `source`.
4. **Publish** as usual with `tools/veroeffentlichen.sh`, and mention the
   issue in the CHANGELOG entry ("suggested in #12"). Close the issue with
   the version the spot is in.

## One-time setup

```bash
git clone https://github.com/DarkPirateGo/wingfoilscout.git
cd wingfoilscout
python3 -m pip install -r requirements.txt      # PyYAML only
tools/install-hooks.sh                          # check run before every commit
```

On first start, Wingfoilscout creates your own `config.yaml` from
`config.example.yaml`. **It belongs to you alone** and isn't versioned —
enter your starting point, your weight and your gear there. It never shows
up in a commit and so never causes a conflict.

## The workflow

Nobody works directly on `main`. Instead:

```bash
git switch -c what-you-are-doing   # your own branch, named after what it's about
# … work …
tools/check.sh                     # must be green
git status                         # what changed — and is anything personal among it?
git add -u                         # changes to files that are already versioned
git add path/to/new-file           # new files: name each one you mean to publish
git commit -m "…"
git push -u origin what-you-are-doing
```

Don't use `git add -A` or `git add .`: they take along everything that
`.gitignore` doesn't happen to know — a copy of your `config.yaml`, an export,
a screenshot. Whatever is pushed stays public in the history. With the hook
from `tools/install-hooks.sh`, the check run refuses a commit that contains a
personal file or the home coordinate from your `config.yaml`.

Then open a **pull request** on GitHub. The check run runs there again
automatically, and the diff is visible before anything lands on `main`.
Changes are merged after review.

The same goes the other way round — get the latest version with

```bash
tools/aktualisieren.sh             # or double-click "Neuen Stand holen"
```

("Neuen Stand holen" is German for "get the latest version"; the
double-click scripts keep their German names.) It puts unfinished work
aside, fetches, puts your commits on top, brings back what it put aside and
runs the checks at the end. If something goes wrong, it tells you how to get
back — nothing is thrown away.

## What breaks easily

**`spots.yaml`** is the catalogue and the actual asset: 278 spots with wind
sectors, water conditions, rules. Additions are welcome — the easiest way is
the form ([Suggesting a spot](#suggesting-a-spot--no-programming-needed));
with Git, through a pull request, and preferably through the UI ("Add
spots") rather than by hand — it checks coordinates and prevents
duplicates.

**`geometry.json`** is derived but versioned: half an hour of Overpass
queries is worth it. Two people who independently compute missing spots
create a conflict here that isn't really one — so there is a merge driver
that merges both versions (`tools/install-hooks.sh` registers it; without
it, Git reports a normal conflict).

**The UI** (`wingscout/webui.py`): since 1.16.0 its CSS and JavaScript are
separate files in `wingscout/web/`, served unchanged. Write them as plain CSS
and JavaScript — doubled braces, a leftover from the old f-string templates,
end up as a syntax error in the browser, and the page stays blank. A test
checks for this, but knowing it saves you the search. If Node is installed,
the check run also runs `node --check` on every script.

More on this in `DEVELOPMENT.md` under "What to watch out for when making
changes".

## What doesn't belong in the repository

`config.yaml` and any copy of it, `report.html`, `ui_defaults.json`,
`cache/`, your logbook (`tagebuch.json`), your favourites (`favoriten.json`),
the memory of the model comparison (`modellguete.json`), your language choice
(`sprache.txt`), the app's
half-written `*.neu` files, exports for importing (Takeout, GPX, KML,
GeoJSON, CSV or JSON in `import/`, ZIP archives), screenshots, editor backups
and local Claude settings. All of it is in `.gitignore`;
`tools/persoenliche_daten.py` keeps the same list, and the check run (locally
and on GitHub) raises an alarm if one of these files ends up in a commit
anyway. `tools/veroeffentlichen.sh` asks before it adds any new file.

## Check run

```bash
tools/check.sh            # all tests (700+), no extra packages, one to two minutes
tools/check.sh --schnell  # "quick": syntax and the fast tests only
```

A new feature without a test isn't a finished feature. The tests don't need
a network — whatever can't be tested without one is cut off at the
interface and tested with canned responses (`tests/test_sources.py` shows
how).

## Translations

The UI comes in German, English, French and Spanish. German is the source
language: texts are written in German in the code, and
`wingscout/lang/<code>.json` (`en`, `fr`, `es`) maps each German source
text — the key — to its translation. To fix or complete a translation:

- edit `wingscout/lang/<code>.json` and change only the values, never the
  keys;
- keep placeholders like `{n}` or `{name}` exactly as they are (you may move
  them within the sentence), keep HTML tags such as `<b>…</b>` or
  `<code>…</code>` with their attributes (only the text of `title`, `alt`,
  `aria-label` and `placeholder` is translated), and keep any space at the
  start or end of a text;
- keep the file's form: keys sorted, indented by one space, characters such
  as é or ñ written as they are (not as `\u…`), a newline at the end. If
  your editor reformats the file, the test that checks this prints a one-line
  command that writes it back in this form;
- run `python3 tools/i18n_texte.py` to see what's missing
  (`--fehlend <code>`, "missing", lists one language's gaps as JSON), then
  run the tests with `tools/check.sh` — they check that every language is
  complete and keeps the same placeholders and tags.

A missing or empty entry shows the German text; a file that isn't valid JSON
makes the whole language fall back to German. Restart Wingfoilscout to see
your changes, and pick the language with the DE · EN · FR · ES switcher next
to the logo (or start it with `WINGSCOUT_SPRACHE=fr python3 -m wingscout.webui`).
The tests themselves always run in German. New text in the code is written in
German, wrapped in `T()` (Python) or `t()` (JavaScript), and needs an entry in
every language file — see "Languages (i18n)" in `DEVELOPMENT.md`. Spot names
and notes in `spots.yaml` are data, not interface text: they aren't
translated. A new language takes more than a JSON file: it also has to be
added to `SPRACHEN` in `wingscout/i18n.py`, together with its weekday and
month abbreviations and its number and date formats (`DEZIMAL`, `TAUSENDER`,
`GRUPPE_AB`, `LOCALE`, `VOR_UHRZEIT`), and to `tools/sprache.sh` and the
`sag` lines of the double-click files for their terminal messages.

### The guide and "How Wingfoilscout calculates"

The **?** button in the app shows this README and the methodology page in the
language of the interface; until a translation exists, it shows the English
one with a note. Both live as files next to the original:

- **The guide:** `README.md` is the original; `README.de.md`, `README.fr.md`
  and `README.es.md` are its translations. Keep the structure: the same
  headings at the same levels in the same order, the same code blocks (the
  commands stay; translating the comments in them is fine), the same
  addresses — translate the text of a link, never its target. A link to a
  section of the same file (`[below](#double-click-files)`) must point at the
  *translated* heading, written the way GitHub makes anchors: lower case,
  punctuation and symbols removed, every space a hyphen (`## Doppelklick-Dateien`
  → `#doppelklick-dateien`, `## Der Prüfstand — stimmt es noch?` →
  `#der-prüfstand--stimmt-es-noch`). The double-click files keep their German
  names. Keep the language line at the top, with your language in bold.
- **The methodology page:** `docs/bewertung.html` is the original (it is
  also the page on the website); the translations are
  `wingscout/hilfe/bewertung.de.html`, `.fr.html` and `.es.html`. Set
  `<html lang="…">` to the language and translate the text between the tags
  and the text of `title` and `aria-label` attributes — tags, other
  attributes, `id`s, classes and links stay exactly as they are, and so does
  every number (with your decimal comma, if your language uses one). Leave
  the stylesheet alone: the app always uses the one from the original.

The app sanitises both before showing them (no scripts, no raw HTML in the
guide, no outside addresses that would load something), so a mistake can
make a page look wrong but can't do harm. Whether a translation still
matches its original, the drift tests check:

```bash
python3 -m unittest tests.test_hilfe -v
```

They compare headings, code blocks, addresses and anchors of each README,
and tags, attributes and numbers of each methodology page; a translation
that doesn't exist yet is *skipped*, one that no longer matches fails and
names the first difference. When `README.md` or `docs/bewertung.html`
changes, the same change belongs in every translation — the tests say
where. No restart is needed to see a change: the app reads the files again
when they change.

## Licence of contributions

Wingfoilscout is under the PolyForm Noncommercial License 1.0.0
([`LICENSE`](LICENSE)); versions up to 2.1.0 were under the MIT licence.
Whatever you contribute — a pull request, a spot suggestion, a
translation — you contribute under the same licence, and you agree that
DARK may also license it under other terms, for example when someone asks
for a commercial licence of Wingfoilscout. The spot form and the pull
request template ask you to confirm this.

Only contribute what you may pass on: your own knowledge and your own work,
or material whose source allows it. Text, photos or spot data copied from
other guides, apps or websites don't belong here — a link to them as the
source does.
