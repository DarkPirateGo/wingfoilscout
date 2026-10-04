# How Wingfoilscout decides

The path from 278 spots in the catalogue to “The best three”, in the order in
which the program takes it. Every number here is also in `config.yaml` (the
template `config.example.yaml` gives the defaults, and all of them are there to
be changed) or in `spots.yaml`; the code for it is in `wingscout/score.py`,
`spots.py`, `geometry.py`, `thermik.py` and `tide.py`. Wind values are in
knots.

The same with figures — a flow chart, the decision tree for the regional
models, curves for wind, gusts, model agreement and thermal wind, and the wind
angle from the shoreline geometry — is on the page
[“How Wingfoilscout calculates”](https://darkpiratego.github.io/wingfoilscout/bewertung.html)
(in the repository: `docs/bewertung.html`). It loads nothing from elsewhere and
works without a network connection, including as a downloaded file.

## At a glance

1. **Prefilter per spot** — season, radius, drive time, water type, rules.
2. **Weather per spot** — three global models, a regional model where available,
   water temperature, waves and tide at the sea; an assumption at thermal spots.
3. **Per hour** — first seven vetoes, then a score made of five components.
4. **Sessions** — consecutive hours above the threshold, two hours or more.
5. **Reliability** — the ensemble damps whatever is uncertain.
6. **Destinations** — rating × drive × hours on the water, plus a Plan B.
7. **What is for information only** — warnings, protected areas, overnight
   spots, tides without a window.

## 1. Prefilter per spot

`spots.eligible()` takes every spot in the catalogue and excludes, in this
order — the first reason that applies is shown in the report under “Not
considered”:

| Reason | Source |
|---|---|
| reference spot only | `reference_only: true` in the catalogue |
| disabled | `disabled: true` |
| water type not wanted | `water.include_types` (default: sea, lagoon, lake, reservoir — all of them) |
| too much seagrass | `seagrass` at or above `water.exclude_seagrass` (default `heavy`) |
| standing depth throughout | `shallow: widespread`, if `water.exclude_shallow: true` |
| dogs prohibited | only with `rules.require_dogs: true` (off by default) |
| wingfoiling prohibited | only with `rules.exclude_forbidden: true` (off by default) |
| out of season | the spot's `season` against the months of the period |
| outside the radius | road kilometres above the chosen radius |
| too far to drive | drive time above `drive.max_hours` (default 12 h) |

Radius and drive time are checked twice. The prefilter estimates: straight-line
distance times `drive.detour_factor` (1.22), driven at `drive.avg_speed_kmh`
(85) — and adds a 35% allowance to the radius and the upper limit, so that no
spot fails because of an overly pessimistic rule of thumb. For the spots that
make it through, Wingfoilscout then fetches the real drive time from the public
OSRM server and checks radius and upper limit again, this time without the
allowance; where the server does not respond (or with routing switched off),
the estimate applies without the allowance. Which of the two applies is shown
in the report, in the drive-time tooltip at each destination.

## 2. Weather per spot

- **Three global models** (`wind.models`: ICON, GFS, ECMWF; ICON is the
  primary model). The wind in the report is that of the primary model; from
  the spread between the three (plus the regional model where it supplies the
  wind), each hour gets an **agreement** between 0.4 and 1: 1.0 up to a spread
  of 3 kn, falling linearly to 0.4 at 9 kn and staying there.
- **Regional model** (`wind.highres: true`): ICON-D2, AROME or HARMONIE
  replace the wind hour by hour where they cover the spot — a grid of
  1–2.5 km instead of 7–25, but only two to three days ahead.
- **Wind factor** of the spot (`wind_factor`, calibrated from the logbook)
  scales wind and gusts — 1.15 means: experience shows it blows 15% more there
  than the models say.
- **Thermal wind** (`thermal:` in the catalogue, `thermal.enabled`): at spots
  with stored knowledge about their thermal, Wingfoilscout assumes the typical
  wind within its time window, damped according to the solar energy received
  since sunrise, cloud cover and opposing wind — but only if that is more than
  the model wind, and always marked as an assumption in the report. A light
  opposing wind of up to 3 kn helps; from 9 kn it's over. The thresholds,
  each with its source, are in `wingscout/thermik.py`.
- **At the sea and in lagoons**, water temperature, wave height and water
  level come from Open-Meteo's marine model (8 km grid).
- **Sunrise and sunset** per spot and day, calculated by Wingfoilscout itself.

## 3. Per hour: first the vetoes, then the score

An hour hit by a veto gets a score of 0 and appears faded in the hourly grid —
with the reason in the tooltip. The order:

1. **Already past** — the hour lies before the start of the search.
2. **Water too cold** — below `weather.water_temp_min` (7 °C); only where a
   water temperature is available (sea and lagoon, with the “Water temperature
   and wave model” box ticked).
3. **Night** — outside the period from 30 minutes after sunrise to 30 minutes
   before sunset.
4. **Outside the tide window** — only at spots with `tide: {fahrbar: …,
   stunden: …}` in the catalogue; without a window, the tide does not change
   any score.
5. **No suitable wing** — the wind is outside all ranges of the quiver
   (`quiver.wings`, `low`–`high` for each wing).
6. **Offshore with too much water downwind** — only with
   `geometry.offshore_veto_km` above 0 (default 0: just a warning in the
   session).
7. **Thunderstorm or temperature** — `weather_code` 95, 96, 99 (`thunder_codes`)
   or air temperature outside `air_temp_min`–`air_temp_max` (7–35 °C).

Whatever is left gets a score between 0 and 1, made of five components
(`weights`, defaults):

| Component | Weight | How it is calculated |
|---|---|---|
| Wind speed | 34% | **Centrality** within the range of the best-fitting wing (inner half of the range 1.0, falling linearly to 0.5 towards the edge) × **comfort band** `wind.preferred_low`–`preferred_high` (14–28 kn: 1.0; outside it −0.4 per 8 kn of distance, at least 0.6). |
| Wind direction | 24% | From the **sectors** in `spots.yaml`: `best` 1.0 · `good` 0.85 · `ok` 0.6 · `bad` 0.15; direction outside all sectors 0.2; spot without sectors `wind.unknown_direction_score` (0.6). If the spot has no sectors but a **shoreline geometry**, the upwind fetch and the downwind room decide: side-shore 1.0 · side-on 0.88 · onshore 0.55 · offshore 0.50 · no open water 0.10 (`geometry.offshore_max_m` 400 m, `lee_room_min_m` 500 m; `prefer_manual_sectors: true` gives hand-maintained sectors priority). |
| Water state | 16% | flat 1.0 · choppy 0.72 · waves 0.42, weighted with `water.chop_aversion` (0.7): 1 − aversion × (1 − value). Above 22 kn, everything except flat additionally counts × 0.9. The label comes from the sector, otherwise from the wave height: the wave model where there is one, otherwise the SPM approximation from fetch and wind — below 0.25 m flat, below 0.60 m choppy, above that waves. Without a sector and without shoreline geometry, choppy applies. |
| Weather | 14% | Within 3 °C of a temperature limit × 0.8. Rain from `rain_soft_mm` (0.6 mm/h) falling linearly to half at `rain_hard_mm` (3.0 mm/h), from there × 0.2. CAPE from `cape_warn` (1200 J/kg) × 0.7, from `cape_bad` (2000) × 0.35. |
| Gustiness | 12% | Gust ÷ mean wind: up to `wind.gust_ok` (1.25) 1.0, from `wind.gust_bad` (1.60) 0.3, linear in between. Gusts more than 6 kn above the top of the highest wing range: at most 0.25. |

Score = sum of weight × component, divided by the sum of the weights. Then
two corrections:

- **Models that disagree** pull it down: score × ((1 − `wind.agreement_weight`) +
  `agreement_weight` × agreement). Since the agreement never drops below 0.4,
  with the default 0.3 an hour on which the models are completely at odds
  (9 kn apart or more) still keeps 82% (0.7 + 0.3 × 0.4).
- **Thunderstorm shadow:** hours up to `weather.thunder_shadow_h` (2) before and
  after a thunderstorm hour × 0.4, with a note.

## 4. Sessions

The hours of a spot are turned into sessions (`build_sessions`):

- An hour **qualifies** at `session.min_score` (0.55) or above, if it has no
  veto.
- A **single** hour up to 0.1 below the threshold between two qualifying hours
  is bridged — with a note, only without a veto, and only one.
- Qualifying hours must follow each other **without gaps** and lie on the same
  day; night ends every session anyway.
- A block counts from `session.min_hours` (2 h).

The session's score is the mean of its hours. Added to that are the wind range
(from–to), the strongest gust, the directions, the range of suitable wings, the
block's worst water verdict and best direction verdict, temperature, fetch and
waves, the agreement, the tide state and the warnings — that is the row shown
under each destination when you expand it in the report.

## 5. Reliability

For the top `ensemble.top` (20) destinations, Wingfoilscout fetches the
ensemble (ICON-EPS from Open-Meteo, around forty runs of the same weather
situation). `p_ride` is the share of runs that reach the lower end of your
quiver in at least two hours of the session — adjusted for the regional model
and the wind factor, so that the ensemble judges the same number that is shown
in the report. The score is multiplied by it in **damped** form:

    factor = (1 − ensemble.weight) + ensemble.weight × p_ride

With the default 0.5, a session that no ensemble run supports keeps half:
uncertain destinations slide down the list but do not disappear. For
**thermal sessions**, the spot's reliability from the catalogue
(`thermal.reliability`, 0.6 if not specified) takes the place of `p_ride` — for
all of them, not just the top twenty — because the ensemble cannot see the
thermal wind and would otherwise only penalise it. A limitation you need to
know: destinations ranked below 20th place are neither rewarded nor penalised.

## 6. Destinations and their ranking

For each spot, `rank_trips` combines the sessions:

- **Hours on the water** per day, capped at `session.useful_hours_cap` (5 h) —
  counting more would just be wishful thinking; from that, the average per day.
- **Allowed drive time** = `drive.hours_per_water_hour` (3) × hours per day
  × (1 + 0.5 × nights), at most `drive.max_hours` (12 h). The rule behind it:
  a six-hour drive is fine for two hours on the water per day. If the drive is
  within that, the **drive factor** is 1.0; above it, 1 − 0.8 × excess ÷
  allowed time, at least 0 — shown in the report as “Drive borderline”. So one
  hour too many with four allowed costs 20%, and the factor reaches 0 once the
  drive is 125% over the allowed time (2.25 times the allowed time).
- **Rating** = session scores, weighted by their hours.
- **Rank** = rating × drive factor × min(1, 0.55 + 0.15 × hours on the water).
- With “Overnight trip”, only spots with enough **consecutive days** count.
- **Plan B:** the best other destination within `drive.plan_b_km` (120 km of
  estimated road distance, straight line × 1.22) with a day in common.

The best three are at the top of the report, the rest under “More
destinations” — complete, not cut off.

## 7. What is for information only

The report shows these, but they do not go into the score: official warnings
(MeteoAlarm), protected areas, shore break, Instagram finds, the comment on the
spot, the tide state without a window — and the **overnight spots**
(Park4Night, `camping.max_distance_km` 15 km): there, “dogs allowed” is a hard
filter (`camping.dog_required`), but it filters overnight spots, not wingfoil
spots.

## Where the numbers live

| Where | What |
|---|---|
| `config.yaml` → `quiver` | your wings with their wind range |
| `wind` | comfort band, gustiness, models, agreement, regional model |
| `weather` | temperature, rain, CAPE, thunderstorms, thunderstorm shadow |
| `tide`, `thermal`, `water`, `geometry` | automatic tide detection, thermal wind on/off, chop aversion, shoreline geometry |
| `drive`, `session`, `ensemble`, `weights` | drive rule, session thresholds, ensemble damping, the five weights |
| `spots.yaml` | per spot: sectors, water, seagrass, standing depth, thermal wind, tide, wind factor |
| `wingscout/score.py` | `score_hours`, `build_sessions`, `apply_ensemble`, `rank_trips` |
| `wingscout/geometry.py`, `thermik.py`, `tide.py` | wind angle from the shoreline geometry, thermal assumption, tide window |

How well all this hits the mark is checked by the Review against measured winds
(`README.md`, section “Review”) and by the Logbook against your sessions.
