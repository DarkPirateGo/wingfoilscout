# The benchmark

The tests (start file `Tests ausführen`) check offline whether the code does
what it is supposed to do. The benchmark checks **online** whether the whole
thing still holds up — against the weather services, against spots with
well-known wind, against a point on land and against **measured** winds from
the past. Its purpose is a number per spot that must not get worse unnoticed
after a change to the code.

To start: double-click **`Prüfstand.command`** — or in a terminal, from the
project folder:

    python3 tools/pruefstand.py

The first run takes a few minutes (measurements and past forecasts are
downloaded), after that seconds: everything fetched is kept in
`cache/pruefstand/`.

The tool and its files keep their German names: *Prüfstand* (benchmark),
*Grundlinie* (baseline), *Sonde* (probe).

## The four parts

**1. Reference spots.** Seven spots where the wind is well known: Torbole
(Ora from the south from midday), Silvaplana (Maloja wind from the
south-west), Domaso (Breva), plus Brouwersdam, Walchensee, Fehmarn and a spot
on Naxos to check the local time. For these, the benchmark fetches the current
forecast of all models and checks:

- *Shape of the response:* Are all the fields there that the scoring reads —
  with the model name appended, the way Open-Meteo names them when several
  models are requested? That is exactly where values were silently lost twice
  (sun times in 1.5.0, solar radiation in 1.6.1). Is the wind between 0 and
  80 kn, the gust not below the mean wind, radiation zero at night and not
  zero at midday? Does sunrise match our own calculation (within 15 minutes)?
  Does the response carry the country's time zone?
- *Scoring:* No night hour with a score above zero. All scores between 0
  and 1.
- *Thermal wind:* On suitable days — sunny, with weak gradient wind — the
  table shows per model on how many days it sees the stored thermal direction
  within the window, and next to it Wingfoilscout as a whole (model plus
  assumption). Wingfoilscout must show it on every suitable day; missing one
  day is a warning, more is an error. Outside the season nothing may be
  assumed. This is also the answer to the old question of whether ICON-2I
  resolves the Ora: the ICON-2I column in the table.
- *Regional model:* Does each spot get an answer from the model responsible
  for it (Torbole ICON-2I, Silvaplana CH1, Zeeland HARMONIE, Walchensee
  ICON-D2)?

**2. A point on land.** The Münsinger Alb (48.42° N, 9.55° E): karst, no
water within three kilometres, the Danube fifteen kilometres away. The
shoreline geometry must say "no water within 3 km", the Check coordinates
page must list the point as unusable, the coordinate check
(`tools/koordinaten_check.py`) must classify it as "on land", and the scoring
must not use its fetch rose. The same check runs beforehand offline on a
made-up extract (a lake ten kilometres away, nothing else) — and while the
benchmark was being built, it found a bug right away: up to 1.7.0 such a
point counted as "rose valid", and the rays ran across ten kilometres of land
to the Danube.

**3. The past — forecast versus measurement.** Ten spots that have a weather
station within twelve kilometres at most; the benchmark finds the pairs
itself, alternating between the services — and across borders, since the
station may come from any service:

| Country | Service | What it provides |
|---|---|---|
| Germany | DWD Open Data | Hourly mean wind at 10 m, roughly the last 500 days |
| Netherlands | KNMI uurgegevens | Hourly means, 49 stations on the coast, on the IJsselmeer and inland (list written from memory, positions taken from the response) |
| Netherlands | Rijkswaterstaat WaterWebservices | Ten-minute values from measuring poles and coastal stations (on the water), averaged to hours — since 1.13.0, built from the documentation, not yet test-queried |
| Austria | GeoSphere Data Hub | Hourly means from the TAWES network |
| France | Météo-France via meteo.data.gouv.fr | Hourly means, one file per département |
| — | Windguru | Only stations with an API password from `config.yaml` (`stationen: windguru:`), values in knots |

For a **fixed period** (1 to 31 August 2026) it fetches the forecast as
Open-Meteo issued it at the time, runs it through the entire scoring — with
regional model, `wind_factor`, thermal wind — and compares it hour by hour
with the measurement. Per spot and per series (ICON, GFS, ECMWF, the regional
model, Wingfoilscout as a whole):

- **MAE** — mean absolute error in knots. The number in the table.
- **Bias** — forecast too high or too low, on average.
- **Direction** — share of hours (measured wind 8 kn or more) with a deviation
  of at most 45°.
- **F1 wind** — the question that matters, applied to the wind: daytime hours
  above 12 kn. When Wingfoilscout's wind was above 12, how often was the
  measurement too (precision); how many of the measured hours did it catch
  (recall); both combined as F1 (1.0 would be perfect).
- **F1 verdict** — the same with Wingfoilscout's verdict "rideable" (rating
  above the threshold, no veto) instead of the wind. Next to it **h≥12**, the
  number of measured daytime hours above 12 kn: with seven such hours in a
  month an F1 says nothing, with a hundred it does. The baseline comparison
  therefore uses the error and F1 wind, and the verdict only from thirty hours
  upwards.

A station measures over land, a spot lies over water — so the numbers are not
a verdict on the truth but a yardstick: after a change they must stay the same
or get better. For orientation, from the first run on 16 September 2026
covering August: 1.4 to 3.0 kn mean absolute error, direction right in 89 to
100 % of the hours. If the nearest station is silent (Tholen was), the
benchmark takes the second-nearest within range.

**4. The baseline.** `pruefstand/grundlinie.json` holds the numbers of the run
that serves as the yardstick. It is only set on request:

    python3 tools/pruefstand.py --grundlinie-setzen

From then on every run compares against it: MAE worse by more than 1 kn or F1
worse by more than 0.1 means **error**. Better means: good — and if that was
intended, set the baseline again. The baseline also remembers the spot ↔
station pairs, so that every run compares the same ones.

## When to run it

- After every change to `score.py`, `thermik.py`, `models.py`, `geometry.py`
  or to a source in `sources/`.
- Once a month for no particular reason: weather services change their
  responses without telling anyone.
- **Before** setting a new baseline: first understand why the numbers are
  different.

## Reading the output

    ✓  OK
    !  warning — take a look, no reason for alarm (a service doesn't answer,
       a station is too far away, thermal wind missed on one day)
    ✗  error — something calculates wrongly or is worse than the baseline

Exit code for the terminal: 0 all OK, 1 at least one error, 2 nothing could be
checked (no network).

## The probe

    python3 tools/pruefstand.py --sonde

queries every service once and shows what it returns: how many stations,
which station for which spot, how many hours, first and last hour — for the
benchmark month and for the day before yesterday up to today. The last hour
shows how close each service gets to "now". The benchmark was built without
network access; on 16 September 2026 the probe confirmed DWD, KNMI, GeoSphere
and the Open-Meteo archive, on 19 September Météo-France, the ten-minute
values from DWD and GeoSphere, and the forecast up to today (1.10.0). On
20 September it revealed two bugs: Rijkswaterstaat returned no station list
(old URL; 1.14.0 uses the new one), and for Leucate Météo-France picked a
station without wind measurement (1.14.0 only takes stations with wind).
The probe with 1.14.0 (20 September, 15:01 CEST) confirmed all services:
Rijkswaterstaat with 56 locations (pair Oesterdam ↔ Tholen Bergsediepsluis,
1.3 km, values up to the last full hour), Météo-France with the Leucate wind
station (2.5 km from the spot), DMI with 67 stations (pair Drejby Strand ↔
Kegnæs Fyr, 1.1 km, up to the last full hour). For Rijkswaterstaat, the probe
shows one pair per service (KNMI and Rijkswaterstaat share the Dutch list);
for Windguru, only what is in the configuration (not yet probed).
If a service ever starts answering differently, this is the way to see it
before the numbers built on it mean something wrong.

## What the benchmark can't do

- At Lake Garda, Lake Como and in the Engadine there is no freely accessible
  station — there, the thermal wind remains a comparison between models, not
  one against measurements. Italy, Spain, Denmark, Norway: no measurement
  service connected.
- The archived forecast is the one with the shortest lead time ("today for
  today"). It doesn't tell you how good the forecast was three days ahead —
  that would need Open-Meteo's Previous Runs API.
- Hourly mean versus model hour: the two don't refer to exactly the same half
  hour. That costs about half a knot of error, the same for all.
- The period lies within a single summer-time period, on purpose: across the
  day the clocks change, the time offset of the response no longer fits.

## The Review tab in the interface

Since 1.9.0 the same calculation is available in the interface as the
**Review** tab — but with a different question. The benchmark measures a
fixed month at ten fixed spots so that code changes can be compared; the
Review tab takes the ten best destinations of the *latest search* and the
*last few days up to the current hour* (selectable, 1 to 14, including today
since 1.10.0) and shows what Wingfoilscout would have said and what the
station then measured. Same sources, same metrics (`pruefstand.masse`), same
limits: forecast with the shortest lead time, land versus water. For periods
reaching into the last three days, the cache is valid for six hours, for
periods up to today for one hour — the services deliver the most recent hours
bit by bit; everything older is kept forever.

## The measurement services

| Country | Service | Quality-checked hourly values | The last few days | Status according to the probe (19 Sep, 08 UTC; from 1.14.0: 20 Sep, 13 UTC) |
|---|---|---|---|---|
| DE | DWD, CDC "recent" | Up to the day before yesterday, daily | Ten-minute values "recent" (the days in between) and "now" (current UTC day), averaged to hours | 19 Sep: yesterday was missing, the ten-minute "recent" values ended on the 13th — 20 Sep: complete up to 12 UTC (61 hours from the day before yesterday) |
| NL | KNMI, uurgegevens | Up to the day before yesterday | — (the response for the last two days has the header but no rows — since 1.13.0 shown as "no values for these days", with the two-day delay as the reason, not as a failure) | Up to 17 Sep |
| NL | Rijkswaterstaat, WaterWebservices (DD-API 2.0, since 1.14.0) | — | Ten-minute values from the measuring poles, averaged to hours — only the measurement corrected to 10 m, never the forecast that comes with it | 56 of 438 locations currently deliver; up to the last full hour (12 UTC) |
| DK | DMI, metObs v2 (since 1.14.0) | — | Ten-minute values, averaged to hours | 67 stations; up to the last full hour (12 UTC) |
| AT | GeoSphere, klima-v2-1h | With a delay | "tawes-v1-10min" from the neighbouring TAWES station (up to 3 km away), averaged to hours | Up to the current hour |
| FR | Météo-France via meteo.data.gouv.fr | One file per département covering the last two years, refreshed every morning | — (the file reaches until shortly before it was generated) | Up to 03 UTC today; since 1.14.0 only stations with wind measurement (31 instead of 53 around Leucate) |
| — | Windguru, Station JSON API (`wgsapi.php`) | Hourly means from the station's minute series, as far back as it goes | Up to now | Only with a password; not yet probed |

The Review tab doesn't simply take the nearest station but — since 1.14.1 —
the nearest one *that has almost all hours up to now* (90 %); if none has that
many, the nearest with at least 80 % of what the best one has. Up to six
stations are queried within the radius set in the "Station up to … km" field
(30, at most 100), and only as many as it takes until one is good enough. Up
to 1.14.0 the nearest station with any values at all won: at IJmuiden, KNMI
with the hours up to the day before yesterday instead of Rijkswaterstaat with
those up to now. The lists apply across borders: a Belgian spot gets Cadzand
(KNMI), a spot on the German–Danish border the nearest station of either
country. How much a station 40 km away says about the spot is for the reader
to judge; the distance is shown next to it.

For each spot, the Review tab shows which hours have a measurement
("Measurement available"); where there is none, the curve stays empty, and
the metrics only count the hours both have.

France has no station list to download — the stations are listed in the
département files themselves (5 to 15 MB, zipped). Which file a spot needs is
decided by a rough table of bounding boxes (`stationen.FR_RAHMEN`); in
borderline cases, the two nearest. On the first run without a baseline, the
benchmark therefore downloads the files of all départements that have spots —
a few hundred MB; `--dienste DE,NL,AT` leaves France out. The baseline of
16 September keeps its nine pairs fixed; with it, France is only added if you
set a new baseline. Doubtful values (quality code 2) are left out.

Rijkswaterstaat is the one source that measures on the water: measuring poles
and coastal stations, ten-minute values via the WaterWebservices, since 1.14.0
via the new API `ddapi20-waterwebservices.rijkswaterstaat.nl` (no key, "fair
use"). The old URL, against which 1.13.0 had been built blind, returned no
station list to the probe on 20 September — and because the NL list swallowed
the failure, it only said "49 stations" (all KNMI). Since 1.14.0 the probe
reports the error. Checked in the browser on 20 September: the service's
catalogue (just under 2 MB, cached for 30 days) lists the locations with
`Lat`/`Lon`; wind is the quantity `WINDSHD`, direction `WINDRTG` (identified
by the code — the description "windsnelheid" also matches the standard
deviation). Of 438 locations with wind in the catalogue, 56 currently
deliver; the rest are decommissioned, so Wingfoilscout asks once a week with
`OphalenLaatsteWaarnemingen` which ones have measured in the last seven days.
A values response carries two measured series and a **forecast**
(`ProcesType` "verwachting", values around 0.5 m/s); the measurement
corrected to the standard height is the one used. If there are no values in
the period, the service answers with HTTP 204.

DMI (Denmark, since 1.14.0): the open data API `metObs v2`
(`opendataapi.dmi.dk`) provides stations and ten-minute values without a
key — checked on 20 September. Active Danish stations with `wind_speed` are
used (not Greenland and the Faroe Islands); a Danish spot thus gets the
Danish station instead of List on Sylt.

Windguru releases a station's values only through its API (Station JSON API
1.2.22, `wgsapi.php`), and every request needs `password` — the station's API
password or its MD5 hash. The station pages on windguru.cz fetch their charts
via an internal route that answers 401 without a session; Wingfoilscout does
not get around it. Stations with a password go into `config.yaml` under
`stationen: windguru:` (template in `config.example.yaml`); by default the
probe reads the template, so use `--config config.yaml` if it should check
your stations. Values come in knots, filtered by Unix time (the local-time
stamps in the response have no time zone); the documentation doesn't say in
which time zone `from`/`to` are interpreted, so an extra day of margin is
requested.
