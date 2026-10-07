# Security

## Reporting a vulnerability

Please report security problems **privately**, not in public issues: open the
repository's [Security tab](https://github.com/DarkPirateGo/wingfoilscout/security)
and click **Report a vulnerability**. Private vulnerability reporting is
enabled for `DarkPirateGo/wingfoilscout`, so your report is not visible to the
public.

Wingfoilscout is maintained in spare time, so there is no guaranteed response
time.

## Security audit · 13 September 2026

What follows is the log of the security audit of 13 September 2026: the
introduction, then dated addenda (newest first), then the original findings.
Until version 2.1.0 the project was called Wingscout and its repository
`DarkPirateGo/wingscout`; the entries keep the name of their time.

Wingscout is a local tool: a small server on 127.0.0.1 that fetches weather
data from third-party services and builds an HTML page from it. The attack
surface is correspondingly small, but not zero — and two issues really were
open. The review was done by hand, line by line; automated tools such as
`bandit` or `pip-audit` were not available in this environment. The rules
from this audit are pinned down as tests in `tests/test_security.py`, so that
they don't silently disappear in the next rework.

### Addendum 7 October 2026: favourites (2.4.0)

2.4.0 adds one endpoint and one personal file; no new third-party service.
`POST /favoriten` takes JSON (`{"ids": […], "zuerst": true}`) and passes the
same checks as every POST — the access key in Wi-Fi mode, `Host`, `Origin`
and the `Sec-Fetch` headers (`_zugang`, `_same_origin`). It stores only what
looks like a catalogue ID and exists in the catalogue, at most ten; if the
catalogue can't be read, it stores nothing. `favoriten.json` is written
through `spotedit.schreibe_atomar` (0600 for a new file) and is listed in
`.gitignore` and `tools/persoenliche_daten.py`. On the start page the list
and the short catalogue reach the script as JSON through
`i18n.json_im_skript`, and the script inserts names only escaped. `/run`
cleans the list from the form again (`favoriten.bereinigen`); the search
names unknown IDs in the log and leaves them out. Pinned down in
`tests/test_favoriten.py`: a foreign origin gets 403, malformed input 400,
and in neither case is anything written.

### Addendum 4 October 2026: a fresh repository with 2.3.0

With 2.3.0 the licence changed from MIT to PolyForm Noncommercial 1.0.0
(README, “Data sources, licences and limits”). So that the repository no
longer hands out the earlier versions, it was deleted on GitHub and created
again, empty, under the same name. It starts with a single commit — the
state of 2.3.0 — and a single tag and release.

- **Gone from GitHub with the old repository:** every earlier commit, tag and
  release, the runs under “Actions”, and what the addendum on the 2.1.0
  review left open — older commits with earlier example values, catalogue
  notes and commit addresses other than the noreply one.
- **Not reachable:** copies made before — clones, downloaded archives,
  forks. Whoever has one keeps it under the MIT licence it came with; the new
  licence applies from 2.3.0 on.
- **Checked before the push** (by `tools/veroeffentlichen.sh`, which on a
  first commit checks the whole tree, not only the changes): author and
  committer address of the commit and the tagger address are the noreply
  address; no file from `tools/persoenliche_daten.py`; the home coordinate
  from `config.yaml` appears nowhere.
- **Settings are per repository** and were set again afterwards: private
  vulnerability reporting, secret protection with push protection,
  dependency graph and Dependabot alerts, the ruleset that protects `main`,
  the read-only token for Actions, and Pages (list in `DEVELOPMENT.md`).
- Every clone made before 2.3.0 is invalid — the new history shares no
  commit with the old one. Clone afresh.

**Cross-check afterwards:**
`https://github.com/DarkPirateGo/wingfoilscout/commit/50fdee3` (2.1.0) and
`https://github.com/DarkPirateGo/wingfoilscout/releases/tag/v2.1.0` must
return 404. Checked the same day: the commit page returns 404, and fetching
the commit by its full ID is refused (`not our ref`). As in the addendum of
3 October: what GitHub keeps internally after a deletion cannot be checked
from the outside.

### Addendum 4 October 2026: review of 2.1.0 — fixed in 2.1.0

2.1.0 brought a lot of new surface (four interface languages with a script
prelude on every page, a language endpoint, a website with videos), so the
whole project was reviewed again before the release — by four independent
reviewers with separate focus (HTTP surface; output encoding and the new
translations; external data and parsers; scripts, publishing, repository
content and privacy), each finding reproduced on a copy of the program. The
fixes were then checked by a fifth reviewer who had not written them; the
bypasses found in that round were fixed as well. Nothing critical or high
was found; the issues were denial of service, robustness and privacy. All
rules are pinned down as tests: `tests/test_sicherheit_http.py`,
`tests/test_sicherheit_quellen.py`, `tests/test_sicherheit_daten.py`,
`tests/test_sicherheit_repo.py`, plus additions to `tests/test_i18n.py` and
`tests/test_security.py`.

**Web server (medium)**
- Any website open in the same browser could load the expensive pages
  cross-site (browsers send no `Origin` with images or no-cors fetches): one
  core at 100 % and the app detectable via its logo. Now a cross-site or
  same-site request that is not a top-level navigation gets a cheap 403
  (`Sec-Fetch-Site`/`Sec-Fetch-Mode`; links into the app keep working).
- In LAN mode, devices without the key could hold hundreds of half-open
  connections (one thread and file descriptor each) and lock out even the
  Mac. Now: 15 s socket timeout, at most 64 connections and 24 from other
  devices, and a 30 s overall deadline per connection from other devices.
- Error messages of write requests contained absolute paths (with the macOS
  user name). Paths are now shortened; the full error goes to the terminal.
- A spot name with a lone surrogate character dropped the connection instead
  of showing an error page; every response is now encoded robustly.

**Output and translations (medium/low)**
- The translations embedded as JSON in every page escaped only `</`; a
  translation containing `<!--<script` broke every page, every report and the
  website demo. All inline-script data now escapes `< > &` and U+2028/2029,
  and non-finite numbers become `null`.
- Some translated texts went into HTML attributes unescaped (CSP blocked the
  injected handlers, but only CSP). Escaped now; translations may not contain
  more `" < >` than their German source text (catalogue test), and both
  `t()` implementations neutralise `<`/`>` in a translation whose source text
  has none.

**Data and parsers (medium/low)**
- A coordinate regex was cubic: one CSV field with many spaces kept an import
  busy for days and blocked every other action. Bounded; whitespace collapsed
  first; inputs over 2000 characters rejected. A second quadratic pattern in
  the import was rewritten.
- YAML aliases in `spots.yaml`/`config.yaml` could expand a 559-byte file to
  gigabytes on every page. Aliases are now rejected.
- Lone surrogates from an import made the catalogue unusable; names are now
  cleaned and invalid text in the catalogue is a clear error.
- Garbage values from data services (`NaN`, `Infinity`, `1e999`, text,
  broken time arrays) crashed the whole search; each source is now
  sanitised, and a spot with unusable data is skipped with a log line.
  Station measurements are range-checked; `modellguete.json` and the JSON
  answers never contain `NaN`.
- Decompression bombs in the station sources (DWD ZIP, Météo-France gzip,
  BZIP2/LZMA members) could use gigabytes; reading is now streamed and
  bounded, only stored/deflated ZIP members are accepted, the ZIP itself is
  capped at 8 MB.
- The Météo-France file URL from data.gouv.fr is validated strictly;
  `file:`, `ftp:`, `data:` and plain http to other hosts are refused; the
  redirect guard parses URLs instead of comparing prefixes; downloads have an
  overall deadline and are read in chunks (Python 3.9 no longer reserves the
  full size limit per request); XML deeper than 64 levels is rejected; broken
  cache files are treated as missing and written atomically; stale DWD and
  Météo-France caches expire.
- Privacy: the start point sent to the public OSRM server is rounded to two
  decimals (~1 km), like the cache key. README has a new section "What leaves
  your computer".
- Files with personal data were world-readable (`report.html`, caches,
  `tagebuch.json`), and `config.yaml` lost its 0600 after the logbook rewrote
  it. The program now runs with umask 077, and atomic rewrites keep the mode
  (or 0600 for new files).

**Publishing and repository (medium/low)**
- `tools/veroeffentlichen.sh` used `git add -A` without a stop. It now stages
  only tracked changes, lists new files and adds them only after you type
  `ja`, refuses forbidden paths (one list in `tools/persoenliche_daten.py`,
  used by the script, `tools/check.sh` and CI) and any coordinate within 1 km
  of your home in `config.yaml`, checks every commit it would push (author and
  committer must use the GitHub noreply address), and pushes only the branch
  and the new tag. `.gitignore` covers copies, temporary `.neu` files,
  exports, screenshots and editor files.
- Example values in `config.example.yaml`, the tests and the README now match
  the website demo (start point Hamburg, 53.55/9.99; rider 80 kg), and
  catalogue notes no longer address the reader personally; a test keeps
  second-person remarks out of the notes.
- The CI workflow runs with a read-only token and without stored
  credentials.

**What stays (accepted or for the maintainer to decide)**
- Older commits keep earlier versions of some files (example values,
  catalogue notes) and their commit metadata; only a history rewrite would
  change them.
- Browsers without `Sec-Fetch-*` headers (Safari before 16.4) are not
  protected against the cross-site load above; a popup opened by a click and
  then navigated by script is still served.
- A malicious data service that sends its status line and headers very
  slowly is bounded only per socket operation, not by the overall deadline.
- The home-coordinate check in the publishing script recognises decimal
  formats and map links, not degrees-minutes-seconds or other rare formats.
- Park4Night is queried with a browser User-Agent (as before) — a question of
  that site's terms, not of security.
- `script-src` allows the cdnjs host (Leaflet is pinned with SRI); PyYAML is
  installed from PyPI without hash pinning; commits and tags are unsigned.
- Logo and icon PNGs carry C2PA content credentials (generator metadata,
  nothing identifying).

### Addendum 3 October 2026: repository recreated (2.0.0)

After the history rewrite (step 3 in the addendum of 27 September), GitHub
kept the old commits available: `blob/<old ID>/config.yaml` could still be
retrieved in the then-private repository, with the notice that the commit did
not belong to any branch. On GitHub, a force-push replaces the branches but
does not delete the old commits; their IDs also appeared in the runs under
"Actions". So on 3 October the repository was deleted on GitHub and recreated
empty under the same name; the branch and the tags were pushed back from the
Mac.

Checked on the Mac beforehand, across all commits: neither `config.yaml` nor a
Takeout export nor the private address appears; there is only `main` plus the
tags, and the state was the same as on GitHub. The release entries of the 1.x
versions disappeared with the old repository — their content is complete in
`CHANGELOG.md`; the new repository starts with a single release, 2.0.0.

**Cross-check before switching to "public":**
`https://github.com/DarkPirateGo/wingscout/blob/64a93af/config.yaml` —
retrievable before the repository was recreated; afterwards it must return
404.

**Limit:** What GitHub keeps internally after a deletion cannot be checked
from the outside. If you want that ruled out as well, ask GitHub Support to
remove it (keyword "sensitive data").

### Addendum 27 September 2026: going public — what doesn't belong in the repository

Before switching to "public", all versioned files and the entire history were
searched (`git log --all -S`, `git grep` across all commits) for keys,
passwords, addresses, coordinates, names and email addresses.

**Secrets: none.** There are no API keys (Open-Meteo, OSRM, Overpass,
Nominatim, DWD, KNMI etc. don't need any); Windguru passwords live only in the
personal `config.yaml` (not versioned); the access key for Wi-Fi mode is
generated randomly at every start. The commits carry an Apple relay address,
not a real one.

**Personal data: four findings, all fixed in 1.19.2** (details in the
changelog): a versioned Google Takeout export, a private address in the import
script and in the raw extract, the personal `config.yaml` in four early
commits, and a salutation and a name in catalogue notes. The current tree is
clean — **the history is not**, because Git forgets nothing on its own.

**So, before switching to "public", in this order:**

1. `git rm --cached import/takeout-2026-09-13.csv` — the file stays on disk
   (gitignored) but leaves the repository. The test
   `test_persoenliche_importdateien_sind_nicht_versioniert` only passes after
   that.
2. `tools/veroeffentlichen.sh --version 1.19.2 "…"` as always.
3. `bash "Claude outputs/historie-bereinigen.sh"` — makes a backup of the
   whole folder (`wingscout-sicherung-<date>` next to it), removes
   `config.yaml` and every Takeout export from all commits, replaces the
   address in the old versions (`git filter-branch`, built into Git, nothing
   to install), checks that none of it is left, and then asks whether the
   branch and tags should be pushed with `--force`. After that, every earlier
   copy of the repository (other computers, old clones) is invalid — clone
   afresh. The script was rehearsed on a test repository with the same cases
   (early `config.yaml`, export, address, merge, annotated tags).
4. Only then, on GitHub: Settings → Danger Zone → Change visibility → Public.
   The licence (`LICENSE`, then MIT, © 2026 DARK) has been included since
   1.19.2; since 2.3.0 it is PolyForm Noncommercial 1.0.0.
   One more step came in between: after the force-push, GitHub kept the old
   commits as dangling copies, so the repository was deleted and recreated
   (addendum of 3 October).

**What stays public, deliberately:** the author's first name in the
changelog, in `DEVELOPMENT.md` (then `ENTWICKLUNG.md`) and as commit author;
Hamburg city centre as the example starting point (two decimal places,
~1 km, the same point as the demo on the website); the catalogue including
its own notes (spots are public places);
`import/jensdee_*` as the raw extract of a Google Maps list shared by link,
with attribution to its creator; `instagram.json` with the URLs of public
accounts (schools, surf centres, clubs) from a web search. If you don't want
any of this public, take it out before step 3 — the history then gets cleaned
along with it.

**Tests for this** (`tests/test_catalog.py`, `PersoenlicheKonfiguration`): no
`import/takeout-*.csv`, no GPX/KML/KMZ, no `tagebuch.json` or
`modellguete.json` in the repository; the Takeout filter is a pattern, not a
list of addresses; the starting point in the template (`config.example.yaml`)
is coarse. Since 4 October 2026 also `tests/test_sicherheit_repo.py`: the
list of paths that never belong in the repository (`tools/persoenliche_daten.py`,
used by `tools/veroeffentlichen.sh`, `tools/check.sh` and the check run on
GitHub) agrees with `.gitignore`, and catalogue notes don't address anyone
personally.

### Addendum 25 September 2026: review of 1.18.3 — fixed in 1.19.0

The entire code was read once more, with a focus on security and usability;
findings, reproductions and reasoning are in `REVIEW.md` (section "Review
25.09.2026"), and every finding is a test in `tests/test_review_2026_09.py`.
What was found and closed the same day with 1.19.0:

- **S1 (high):** the catalogue field `sectors[].water` went into the report
  unescaped; anyone writing the catalogue could get script into the report,
  where it runs under the origin of the user interface. Now the badge comes
  only from a fixed list, the text is escaped, and `load_spots` accepts only
  the fixed vocabulary for `water`, `quality`, `from`, `to`.
- **S2–S4:** GET checks the host like POST does (DNS rebinding could read);
  the key is compared as bytes (non-ASCII input raised an exception before
  the access check); control characters no longer get into the catalogue, and
  an unreadable catalogue is a `KatalogFehler` with a line number instead of a
  traceback.
- **S5–S7:** XML only without DOCTYPE and entities (`xmlsicher.py`, over the
  whole text; also for MeteoAlarm), a coordinate regex with bounds, only
  finite coordinates within range — from import files as well as from the
  catalogue.
- **S8–S14:** `nosniff`, `Referrer-Policy: no-referrer`, error messages
  without paths, additional sources no longer crash the search, size limits
  on import, `config.yaml` with `0600`, redirects only to `https://`, cache
  names sanitised, ZIP member sizes checked.

**Since 1.19.1, the second line of defence:** a Content Security Policy with a
nonce (`wingscout/csp.py`). Every response and every report file names a
freshly generated random nonce, and only `<script>` blocks carrying it run;
inline event handlers and `javascript:` URLs don't run at all. The only
third-party script is Leaflet from cdnjs, with a checksum; tiles come from
OpenStreetMap, requests and frames only from the app's own server. If escaping
fails again as it did in S1, the script stays silent — the browser refuses it,
also in the report file on the iPhone. Reproduced in Chromium with an
`<img onerror>` and a `<script>` written into the file. The rules are in
`tests/test_security.py` (`Richtlinie`, `RichtlinieLive`).

### Addendum 20 September 2026: access from the phone (1.17.0)

With `--lan`, Wingscout listens not only on 127.0.0.1 but on all addresses —
otherwise the iPhone couldn't reach it. That means any device on the same
network can knock: visitors on the guest Wi-Fi, the TV, the neighbour's kid.
So in this mode an access key is required:

- It is generated randomly at start (`secrets.token_urlsafe`), is part of the
  start URL and moves into a cookie on the first visit (`HttpOnly`,
  `SameSite=Lax`, 30 days). It is compared with `hmac.compare_digest`.
- Without a valid key: 401, for every URL, including images and data. From
  the Mac itself (127.0.0.1, ::1) no key is needed, as before.
- The key is valid only for this run: restart, new key.
- The origin check (`Host`/`Origin`) additionally knows the machine's own
  IPv4 addresses, but no host names — a name that points to the address stays
  locked out (DNS rebinding).
- Without `--lan` nothing changes. Both rules are pinned down as tests
  (`tests/test_security.py::Server`, `tests/test_webui.py::ZugangVomHandy`).

What this is **not**: encryption. On Wi-Fi the connection runs over
`http://`, so the key crosses the network in plain text. On a home network
with WPA2/WPA3 that is acceptable; on an open Wi-Fi (hotel, campsite)
Wingscout should not run with `--lan`. A certificate for a local IP address
would be the next step, but it would make the iPhone show a warning that has
to be clicked away — and that is exactly what you don't want to teach users.

### What was found and fixed

**Other websites could operate the server.** The server listens only on
127.0.0.1 — but any page open in the same browser may send requests to
127.0.0.1:8765. Without a check, any website could have started a search,
written spots into the catalogue, changed the defaults or shut Wingscout
down. Now every POST request checks the `Host` header (which catches DNS
rebinding) and, if present, the `Origin` header; browsers always set it on
requests from other sites. A foreign origin gets 403. Tested in
`tests/test_webui.py`.

**Spot names and notes went into the map unprotected.** The map data sits as
JSON in a `<script>` block; a name containing `</script>` would have ended the
script and could have run its own. On top of that, Leaflet inserts the popup
texts as HTML. Through adding spots — including from someone else's KML or
GPX file — code could thus have got into the report. Now `<`, `>` and `&` are
written as Unicode escapes in the JSON, and the popups neutralise name,
summary line and note before inserting them. Tested with a spot called
`<script>alert(1)</script>` in `tests/test_report_cli.py`.

**URLs from the Park4Night response went into links unchecked.** An entry
with `javascript:` instead of `https:` would have run code when clicked. Only
http(s) URLs go into an `href` now, everything else becomes empty; coordinates
from the third-party response are forced to numbers.

**The report loaded Leaflet from a CDN without a checksum.** Whoever tampers
with the CDN or the route to it runs code in the report. Both files now carry
`integrity` attributes (SHA-384, computed from the files served on
13 September 2026) and `crossorigin="anonymous"`. If cdnjs changes the files,
the map no longer loads — that is intentional; the checksums then need to be
recomputed.

**No size limit for requests and responses.** A form of arbitrary size or an
Overpass response of several gigabytes would have filled the memory. Requests
are limited to 4 MB (413), Overpass responses to 300 MB.

**Catalogue IDs became file names.** An ID like `../x` would have created
cache files outside the cache folder. IDs are validated when the catalogue is
loaded (only letters, digits, `-`, `_`) and additionally sanitised before
being used as a file name.

**Two runs at once.** A second click on the search button while a run was in
progress would have scrambled the shared log. While something is running, the
server answers with 409.

### What was checked and found to be fine

All YAML files are read with `safe_load`. Since 1.19.1 every page carries a
Content Security Policy with a nonce (see the addendum of 25 September). There
is no `eval`, `exec`, `subprocess` or `os.system`. Every network call has a
timeout. All third-party services are contacted over HTTPS. The server serves
only fixed paths (`/`, `/status`, `/report`); nothing is assembled from the
request path. Server data reaches the browser only via `textContent`, never
via `innerHTML`. There are no credentials, no keys and no access logs. The
only dependency is PyYAML.

### What deliberately stays as it is

The server has no login. It is reachable only from your own computer, and
whoever sits there has access to all files anyway; a login would protect
nothing that isn't already exposed.

If PyYAML is missing, the start scripts try to install it, as a last resort
with `--break-system-packages`. That is convenient but interferes with the
system's Python installation. If you don't want that, install PyYAML yourself
beforehand.

Park4Night, OSRM and Overpass are unofficial or demo APIs with no guarantees.
Everything that comes from them is treated as untrusted data — validated,
neutralised, never taken as an instruction. If one of these services fails,
the corresponding section is missing, nothing more.

### How to repeat the audit

    tools/check.sh                       # syntax, all tests, catalogue, leftovers
    python3 -m unittest tests.test_security -v

The rules are tests. New network calls without a timeout, new scripts without
a checksum, a `yaml.load` — any of these turns the check run red before a
commit happens.
