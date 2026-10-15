# Metrology log of the NPEC camera rig

This is the log: every measurement, test method and result, with its source. For the case that
these measurements can be trusted, read `docs/measurement-trust.md` first.

**Status:** first draft 2026-10-05; raw-data sources, repeat counts and camera coverage added
2026-10-08; M2 acceptance on SN001 added 2026-10-14 (section 14). The camera was replaced on
2026-10-07 (old SN000, new SN001; section 8.2); current calibration and bands are the new camera's
from 2026-10-14. Section 13 says which results have
been repeated on SN001. Kept current as findings come in (CLAUDE.md, *Write up every
measurement*). Numbers marked **decision** are settings chosen by the project, not measurements.
Section 11 lists inconsistencies between project files that still need checking. Section 9
holds the M2 physical acceptance tests, run 2026-10-05 on SN000. Section 14 holds their repeat on
SN001 (method written 2026-10-09, run 2026-10-12 to 10-14; summary in 14.7). Current calibration
and bands: SN001, 2026-10-14, lens 6.05 (14.6).

This document states every number the rig relies on to report plant canopy area and how far that
area can be trusted: what was measured, how, how often, the result, and what it does and does
not cover. It is written for a scientist without a background in measurement science
(metrology), and is meant as the basis for reports and a possible paper on the rig.

## 1. The principle

> Certainty is measured, never derived. If a number cannot be demonstrated with a ruler, a
> printed target, or a repeated observation, it does not ship.

The rig does not estimate its accuracy from a model of the camera and lens. It photographs printed
targets of known size, measured with callipers, and reports how far its own area readings of
those targets are off, position by position. Earlier attempts at this project modelled the camera
instead and never produced a working application.

## 2. How an area is measured

1. **Targets.** Calibration sheets carry square AprilTags (36h11 family). Each print run is measured
   with callipers; the current tags are 30.0 mm on a side.
2. **Calibration.** With the camera focus locked, the rig photographs sheets spread over the
   table. Each tag's apparent size in pixels, against its known size in millimetres, gives the
   scale (pixels per millimetre) at that spot. A smooth scale field is fitted across the image.
3. **Area.** An object's area in mm² is its area in pixels divided by the square of the local
   scale.
4. **Validation.** The sheets are moved to different trays and photographed again, 3 times. Each
   tag's area is computed with the calibration and compared with its true area. The spread of
   these errors in each tray slot is that slot's stated uncertainty (its *band*).

**Area error** throughout this document: (area read by the rig − true area) / true area, in
percent. A tag of true area 900 mm² read as 909 mm² has an area error of +1.0%. A change between
two area errors (for example +1.00% to +1.03%) is given in *points* (+0.03 points).

## 3. Physical references

| Quantity | Value | How measured | Date | Covers / does not cover |
|---|---|---|---|---|
| Calibration tag side | 30.0 ± 0.1 mm (readings X 30.10, 30.11, 29.96; Y 30.04, 29.96, 29.94; mean 30.018, SD 0.075, range 29.94 to 30.11) | Callipers, 3 tags (left, middle and right of one sheet), X and Y once each, outer edge to outer edge of the black border | 2026-09-21 (print of 2026-09-20, IDs 300 to 449) | That print run only. Every new print is measured again. ±0.1 mm on 30 mm is about ±0.67% in area |
| Corner tag side | 50.018 mm mean, SD 0.11 (X 50.09, 50.07, 49.92; Y 50.17, 49.87, 49.99) | Callipers, 3 tags, X and Y once each, as above | 2026-09-21 | Corner tags are used for the rig health check (tripwire) and table view, not for area |
| Sheet scale bars, nominal 180 mm | 30 mm sheet: 180.13, 179.91, 179.74 (mean 179.93, SD 0.20). 50 mm sheet: 180.10, 179.93, 180.06 (mean 180.03, SD 0.09) | Callipers, 3 readings of the bar on each of 2 sheets | 2026-09-21 | Confirms the sheets printed at 100% scale (both means within 0.04% of 180). The repeat readings of one bar spread over up to 0.39 mm, wider than the 0.1 mm resolution trusted (below) |
| Reference tag 500 side (60 mm, 36h11 ID 500, fixed at the north table edge) | 60.06 mm mean, SD 0.04 (Y 60.07, 60.05, 60.10, 60.05; X 60.01, 60.05, 60.00, 60.13) | Callipers, 8 readings, remeasured with care | 2026-10-06 | Supersedes a first set the same day (59.58 to 60.26, mean 59.94, SD 0.22; commit `8f77e8d`). Placed 2026-10-06 at the supervisor's suggestion as a static target |
| Callipers used for every reading in this table | NEIKO callipers; no model or serial number available | Stated by Aaron | 2026-10-08 | Not checked against a reference standard. The only independent check: the steel tape and the callipers agree on the sheets' 180 mm scale bars (section 9.2) |
| Calliper resolution trusted | 0.1 mm | **Decision** | | Readings are not used beyond 0.1 mm |
| Sheet-to-sheet difference | up to about 0.7% in area between sheets that both measure 30.0 mm | Fit residuals, 6 pages, 3 sessions | 2026-09-30 to 10-01 | `reference/arducam-central-error-2026-10.md` |
| Tray heights, table surface to the top edge of the tray | Black tray 40 mm; 4x5 tray 105 mm; 4x4 tray 150 mm; 1x1 tray 175 mm | Tape measure, by Aaron, one reading per tray, given in cm (4, 10.5, 15, 17.5) | 2026-10-09 | One tape reading each, so a few mm either way. For the black, 4x4 and 1x1 trays the top edge is the growing-medium height (Aaron, 2026-10-09). The 4x5 is the exception: see the next row |
| Growing medium height, 4x5 tray | 100 mm above the table surface; the tray lip stands 5 mm above the growing medium | Callipers, the 100 mm "normal tray" value of the height test (section 4); Aaron confirmed on 2026-10-09 that it is the growing-medium height and that the lip stands 5 mm proud of it | 2026-10-01 (callipers), 2026-10-09 (confirmed) | The height used for the 4x5 tray on the experiments page. Only the 4x5 has a lip above the growing medium |

**Where the calliper readings are.** The 2026-09-21 readings were typed by Aaron into a table and
given to a Claude Code session (2026-09-21 07:36 UTC), and given again on 2026-09-29 with the
mean rounded to 30.0 mm. The 2026-09-29 date in earlier versions of this log and in CLAUDE.md is
that second date; the measurement was made on or before 2026-09-21 (calibrations from 2026-09-21
12:12 UTC already used 30.02 mm). No other copy exists; this table is the record. The tag 500
readings were given the same way on 2026-10-06. The table does not record which 3 tags were
measured, only that they were at the left, middle and right of the sheet.

**Tray heights: lip and growing medium.** The height test of 2026-10-01 (section 4) used "normal
trays 100 mm, tall tray 175 mm", by callipers. The tape readings of 2026-10-09 gave 105 mm for the
4x5 (normal) tray. Aaron resolved the difference the same day: 100 mm is the height of the growing
medium, the height that matters for area because the plants start there, and the tray's lip stands
5 mm above it. The tape reading was to the lip.

Why tag size matters most: on the previous rig, trusting the 30 mm printed on the box (the tags
measured 29.3106 mm) caused about 4.7% area error, larger than any other source. The lesson is to
measure every printed sheet.

## 4. Camera and geometry

| Quantity | Value | How measured | Date | Notes |
|---|---|---|---|---|
| Camera | Arducam 64MP, serial SN001 from 2026-10-07 (SN000 before) | Serial as given by Aaron | 2026-10-07 | Replaced; comparison in section 8.2 |
| Image size | 9152 × 6944 px | Camera configuration | | Arducam 64MP |
| Scale at tray height | 4.858 px/mm mean (replacement camera, lens 6.04); old camera 4.85 px/mm at the image centre (2026-10-05) | Calibration fit, 355 tags, 08:18 UTC calibration | 2026-10-08 | About 0.21 mm per pixel; earlier calibrations 4.5 to 4.8 |
| Scale on the table surface | 4.52 px/mm (at the image centre), 6.79% below tray height in length, 15.1% in area | Calibration fit, 355 tags on the table, same camera position | 2026-10-05 | At 0.145% of area per mm this corresponds to about 100 mm of height (derived, not taped) |
| Camera height above the table surface | about 1482 mm, a best estimate, not a precise value | Tape measure, by Aaron, without touching the camera (stated as "around 148.2 cm", 2026-10-01 08:38 UTC). A good-faith estimate: the point on the camera measured to and the uncertainty were not recorded | 2026-10-01 | Old camera SN000, before the swap. Not re-measured since. The table-to-tray scale change (row above) is consistent with it |
| Height above tray top | about +0.145% area per mm for small heights (model); over a 75 mm step the model gives 11.8% and the one test 11.2% to 12.0% | See *The height test* below | 2026-10-01 | Bands cover flat objects at tray-top height only. Plant height adds to the uncertainty (section 7) |
| Perspective across the table | corrected by the scale field; positions mapped with a four-corner homography | Saved calibration frames | 2026-09-22 | Perspective within the table plane is modelled; lens distortion is not (section 10) |

**The height test (2026-10-01, old camera SN000).** One tray 75 mm taller than the others (Aaron:
the tall tray is 175 mm, the normal trays 100 mm, both measured with callipers) was put in 3 slots in
turn, one validation round each: North 2, North 4, South 6. Lens 6.18, locked. Validation session
`20261001T082459271029`, calibration `20260930T094710139674` (the one current at that time,
identified by time). The sheets on the tall tray read 11.2% to 12.0% large.

*Prediction.* A camera at height H sees an object at distance D below it at a scale proportional
to 1/D, so area goes as 1/D². With H = 1482 mm (the tape-measure estimate, not a precise value), the normal tray top is 1382 mm from the camera and
the tall one 1307 mm: (1382 / 1307)² = 1.118, so 11.8% large. The figure **0.145% per mm** used in
this log is the slope of this model at tray-top height (2 / 1382 mm), the figure for small
heights; it is derived from Aaron's heights, not measured on its own. The effect grows as an object
comes nearer the camera, so over a larger height the average per mm is higher: over 75 mm the
model's 11.8% is 0.157% per mm. The test read 11.2% to 12.0% (0.149% to 0.160% per mm on
average), so it agrees with the model's prediction. For a plant tens of millimetres tall, the
larger average applies.

*What is stored.* The session's summary file is not in `/var/lib/npec-rig/calibration/validations/`;
the per-slot results are not stored anywhere. The 3 photos remain:
`/var/lib/npec-rig/captures/2026-10-01/082504_362942`, `082555_100396`, `082647_630918`. The
11.2% to 12.0% range comes from the session's report at the time (the chat record of that session
gives the low end as 11.3%).

*Covers.* One test, one camera (SN000), one height step (75 mm), 3 slots, one round each. The model
depends on the camera's height above the table, not on which camera unit is fitted.

## 5. Calibration

Current calibration (`20261008T081832283098`, 2026-10-08 08:18 UTC, replacement camera SN001,
lens position 6.04, 30.0 mm tags, 355 tags, 4 corner tags): scale field residual 0.50% (standard
deviation of the tags' scale about the fitted field). Made after the camera swap and the removal of
packing foam from the new camera (section 8.2). Its validation: section 8.2, "Recalibration after
the foam came off".

Before the camera swap: calibration `20261005T141101923639`, 2026-10-05 14:11 UTC, lens position
6.27, 30.0 mm tags, 355 tags, 4 corner tags: scale field residual 0.52%, holdout coverage error
0.4%.

It replaced the 07:11 UTC calibration (lens 6.15, also 0.52%), which no longer fitted after the
camera was knocked and re-framed in the roll test (section 9.3).

**How repeatable the residual is.** Each calibration is stored as
`/var/lib/npec-rig/calibration/<id>.json` (residual in `scale_field.residual_std_pct`). The file
does not record which camera made it, so the camera is assigned by date. Counting only calibrations
with the sheets on the trays and the current 30 mm sheets:

| Camera | Calibrations | Dates | Residual |
|---|---|---|---|
| SN000 | 8 | 2026-09-29 14:34 to 2026-10-05 14:11 UTC | 0.516% to 0.700% |
| SN001 | 3 (`20261007T114505498348`, `20261007T122200583188`, `20261008T081832283098`) | 2026-10-07 to 2026-10-08 | 0.491% to 0.503% |

Earlier calibrations (58 between 2026-09-21 and 09-28, sheets on the table, some with the old
rig's 29.3106 mm tag size) gave 1.48% to 2.01% and are not comparable. The holdout coverage error
(0.4%) quoted for `20261005T141101923639` is not stored in its file; its source was not found.

| Quantity | Value | Basis |
|---|---|---|
| Fitted scale field | a tilted plane over the image | **Decision**, simplest shape for a camera looking down at a slight angle |
| Local uncertainty claimed by the calibration | spread of the 5 nearest tags' residuals | **Decision** (k = 5); heatmap uses k = 40. Found too small in 7 of 12 slots (section 9.4). **Decision 2026-10-05:** removed from what the operator sees; the validation band (section 6) is the uncertainty |
| Area-shape check | worst tag -0.45%, mean -0.05% | 17 calibration frames, 2104 tags, 2026-09-21. Squaring a length scale is adequate for area at this level |
| Calibration needs focus locked and all 4 corner tags visible | | **Decision**, overridable |

## 6. Validation and the per-slot bands

**Method.** After calibration, the operator moves each sheet to a different tray, leaving the trays
in place, and the rig photographs the table. This is one round. 3 rounds are required
(**decision**). A round counts only if at least 50% of tags moved more than 5 mm, so the same
layout is not counted twice (basis: a real shuffle moved 83% to 90% of tags; an untouched table
moved 0%). The calibration photograph is never a round, because the scale field was fitted to
those same tags. From 2026-10-07 the counted rounds should span at least 20 minutes, first to
last, with the chamber door closed for every round (**decision**, Aaron 2026-10-07; basis: run 3j
in section 8.1 found readings rising and falling on a cycle of about 19 minutes, and an open door
disturbed Control A). A shorter spread is not blocked: the session records its span
(`round_span_minutes`, `short_span`) and its status says "rounds spread over N min, under the
recommended 20". Counted rounds should also be at least 10 minutes apart (**decision**, Aaron
2026-10-07, first set at 6 and changed to 10 the same day so the rounds fall at 0, 10 and 20
minutes; with a cycle of about 19 minutes the first and last round then see nearly the same point
of it, so 3 rounds sample about 2 points of the cycle, and the cycle length varies with the
experiment): the page counts down to the next round and asks before a sooner one, and a session
with a shorter gap records it (`shortest_gap_minutes`, `short_gap`) and says "rounds N min apart,
under the recommended 10". The door cannot be detected by the rig; the operator confirms it for every round.

**The band.** For each tray slot, the band is the 95th percentile of the absolute area error of
all tags in that slot over all counted rounds: 95% of the tags read within that distance of
their true area. Fewer than 10 tags in a slot gives "not measured" (**decision**).

Every validation session is stored as `/var/lib/npec-rig/calibration/validations/<session>.json`,
with each round's tag errors.

**Current bands, replacement camera SN001** (session `20261008T081846523784`, calibration
`20261008T081832283098`, lens 6.04, rounds at 08:20, 08:32 and 08:43 UTC, 23.6 minutes first to
last, door closed; 86.5%, 76.9% and 73.5% of tags moved; 30 tags per slot per round except one
slot of 25 in each round, so 85 to 90 per slot): ±1.3% (South 5) to ±2.7% (South 4); median of the
slot medians -0.14 points; per-slot table in section 8.2, "Recalibration after the foam came off".
This is one validation session; how much a slot's band changes between sessions is shown by the
two SN000 sessions of 2026-10-05 and 2026-10-07 below (up to 1.5 points, North 1).

**Bands of the old camera SN000 on 2026-10-05** (session `20261005T141310628479`, calibration
`20261005T141101923639`, lens 6.27, 3 rounds at 14:13, 14:14 and 14:15 UTC, 92% to 96% of tags moved, 85 to 90 tags per slot;
spread over 1.5 minutes, under the recommended 20, so these bands do not include the 19-minute
cycle of run 3j):

| Slot | Band | Median error | Slot | Band | Median error |
|---|---|---|---|---|---|
| North 1 | ±1.77% | -0.30 | South 1 | ±2.22% | -0.69 |
| North 2 | ±1.86% | +0.51 | South 2 | ±1.58% | +0.38 |
| North 3 | ±2.64% | -0.39 | South 3 | ±2.44% | +0.16 |
| North 4 | ±2.93% | -0.62 | South 4 | ±1.97% | +0.35 |
| North 5 | ±1.73% | +0.21 | South 5 | ±2.16% | -0.21 |
| North 6 | ±2.22% | +0.03 | South 6 | ±2.11% | -0.72 |

Slot medians moved at most 0.9 points between rounds (limit 2.5).

**Earlier bands, same day** (session `20261005T071549445423`, calibration of 07:11 UTC, lens 6.15,
3 counted rounds, 85 to 90 tags per slot; superseded when the camera moved):

| Slot | Band | Median error | Slot | Band | Median error |
|---|---|---|---|---|---|
| North 1 | ±2.12% | +0.13 | South 1 | ±1.89% | -0.01 |
| North 2 | ±1.94% | +0.71 | South 2 | ±1.63% | +0.45 |
| North 3 | ±2.69% | -0.18 | South 3 | ±2.25% | +0.52 |
| North 4 | ±3.36% | -0.48 | South 4 | ±2.38% | +0.38 |
| North 5 | ±1.43% | +0.00 | South 5 | ±1.51% | +0.09 |
| North 6 | ±2.98% | -0.53 | South 6 | ±1.78% | +0.04 |

Two calibrations and validations on the same day, at different camera positions and lens
positions, gave bands of ±1.43% to ±3.36% and ±1.58% to ±2.93%.

The bands belong to one calibration at one locked lens position. A new focus position means a new
calibration and validation.

**Validation of 2026-10-07, the first with rounds spread over time** (session
`20261007T070451149884`, same calibration `20261005T141101923639`, lens 6.27, chamber door closed;
rounds at 07:05, 07:14 and 07:26 UTC, 20.9 minutes first to last, shortest gap 9.6 minutes (the
10-minute gap was set while this session ran; the countdown then showed 6, so its status reads
"rounds 9.6 min apart, under the recommended 10"); 94%, 97% and 80% of tags moved; 80 to 90 tags
per slot). This is the old camera's last validation and the baseline for section 8.2.

| Slot | Band | Median error | Slot | Band | Median error |
|---|---|---|---|---|---|
| North 1 | ±3.3% | -0.90 | South 1 | ±2.8% | -1.33 |
| North 2 | ±2.5% | -0.80 | South 2 | ±2.2% | -0.76 |
| North 3 | ±2.9% | -1.36 | South 3 | ±1.5% | -0.16 |
| North 4 | ±2.3% | -0.25 | South 4 | ±1.6% | +0.11 |
| North 5 | ±2.4% | -0.71 | South 5 | ±3.1% | -1.20 |
| North 6 | ±3.0% | -0.91 | South 6 | ±2.2% | -0.37 |

Against the 2026-10-05 validation of the same calibration: bands ±1.5% to ±3.3% (then ±1.43% to
±3.36%); the median of the slot medians -0.78 points (then +0.07), a change of about -0.85 points,
inside the 2.5-point whole-table check. Between the two lay the cold start, the camera fault and
the lens tests of 2026-10-06 (section 8.1, runs 3 to 3j). Which of these, if any, caused the change
is not known.

**Checks on a validation**, each with the data it was set from:

| Check | Limit | Basis |
|---|---|---|
| A slot's median moves between rounds | 2.5 points | 3 validations with no known fault moved slot medians by at most 0.71, 1.48 and 1.96 points; a 96%-scale sheet reads about 7.8 points small (2026-09-30) |
| One slot reads off from the others | 3.0 points | 8 sessions: normal slots within 2.15 points of the all-slot median; an 89%-scale sheet read about 20.5 points off |
| Whole table reads off | 2.5 points | Same 8 sessions: within 0.66 points of 0 |
| Fraction of slots off together, to call it a whole-round shift | 50% | **Decision**, no data cited |

### 6.1 The percentile band compared with a normal (2 × RMS) estimate (method written 2026-10-13, before any number was computed)

**Question.** The band is a percentile: it makes no assumption about the shape of the errors. The
usual metrology route to a 95% interval is the GUM's expanded uncertainty, U = k × u with k = 2
(JCGM 100:2008, sections 6.2.1 and 6.3.3), which is about 95% only when the errors are roughly normal, and
which treats a known bias separately. On this rig's data, do the two give the same number? Where
they differ, is the percentile catching a tail that a normal estimate would miss? No change to how
the rig computes or reports the band (issue #146).

**Data.** Stored validation sessions, read only, from
`/var/lib/npec-rig/calibration/validations/`. In each, the signed area error (%) of every tag in a
slot, pooled over the counted rounds, exactly as the rig pools them for the band:

| Session | Camera | Calibration | Lens | Note |
|---|---|---|---|---|
| `20261005T071549445423` | SN000 | 07:11 UTC | 6.15 | 3 counted rounds |
| `20261005T141310628479` | SN000 | `20261005T141101923639` | 6.27 | Rounds over 1.5 min |
| `20261007T070451149884` | SN000 | `20261005T141101923639` | 6.27 | Rounds over 20.9 min |
| `20261008T081846523784` | SN001 | `20261008T081832283098` | 6.04 | Rounds over 23.6 min |
| `20261012T070703613469` | SN001 | `20261012T070607812512` | 5.97 | Section 14.1, first session |
| `20261013T074951947771` | SN001 | `20261012T070607812512` | 5.97 | Section 14.1, repeat |
| `20261013T081945572660` | SN001 | `20261012T070607812512` | 5.97 | Third session of the same calibration |

The last three are the SN001 acceptance validations of section 14. Their pass or fail under 14.1
is reported there, not here. `20261009T073553378279` is left out: it was an interface check, not
part of acceptance (section 14.1).

**What is computed, per slot and session** (n = number of tags, 80 to 90; e = signed error in %):

1. `band`: 95th percentile of |e|, linear interpolation between order statistics (numpy's
   default, the same call the rig makes). It must reproduce the stored band and median to
   rounding; if any slot does not, the comparison stops and the mismatch is reported.
2. `median`: median of e, the slot's bias.
3. `rms`: square root of the mean of e², and `2 × rms`. RMS contains the bias: rms² is about
   bias² plus spread².
4. `gum_style`: |median| + 2 × SD, where SD = sqrt(Σ(e − median)² / (n − 1)), the spread about
   the median. This is bias plus a normal 95% spread, kept apart as the GUM keeps them.
5. `ratio`: band / (2 × rms).
6. Skewness: the sample skewness g1 (third moment about the mean over the second to the power
   1.5, divisor n). Normal errors give 0; with 90 tags its standard error is about
   sqrt(6/90) = 0.26. Tails: the share of tags below median − 2 × SD and above median + 2 × SD.
   Normal errors give 2.3% on each side, about 2 tags of 90.
7. Per-round slot medians, and the within-round SD (each tag about its own round's median), to
   show how much of the spread lies between rounds rather than between tags.

**Agreement rule (set beforehand).** Band and 2 × rms agree when they differ by 0.3 points or
less.

**What normal errors would give (worked out beforehand).** If a slot's errors were normal with
spread σ and no bias, the band would be 1.96σ and 2 × rms would be 2σ, a ratio of 0.98. With a
bias equal to σ, the band would be about 2.65σ and 2 × rms about 2.83σ, a ratio of about 0.93.
So for normal errors the ratio lies between about 0.93 and 0.98, with 2 × rms slightly the wider.
A ratio near 1 or above means a heavier tail than normal; well below 0.93 means a lighter one.

**Central slots (set beforehand).** The central low reading (section 7) is within about 1500 px
of the image centre, (4576, 3472) in the 9152 × 6944 frame. No slot centre lies that close. A slot
counts as central when its centre, as stored in the session, lies within 2000 px of the image
centre. From the stored layouts this should be North 3, North 4, South 3 and South 4 (about 1550
to 1850 px; every other slot is more than 2600 px away); the script lists them per session. They
hold the tags nearest the central error.

*Corrected after the run, 2026-10-13:* the distances above were read from one session's layout
only. Per session the four central slots lie 1231 to 1833 px from the image centre, and the
nearest other slot 2429 to 2571 px (`centre_dist_px` in `results.csv`). Some central slot
centres do lie within 1500 px: North 3 in `20261005T071549445423` (1455 px), North 3 and North 4
in `20261005T141310628479` and `20261007T070451149884` (1231 and 1481 px), South 4 in the three
sessions of calibration `20261012T070607812512` (1457 px). Which slots count as central is the
same in every session: North 3, North 4, South 3, South 4.

**What it cannot show.** 3 rounds are not 3 independent samples of 85 to 90 tags: the tags in one
photograph share the calibration, the lens position and the point in the 19-minute chamber cycle
(section 8.1, run 3j). So no confidence level is attached to any band or ratio here. Wilks (1941)
gives distribution-free tolerance limits from order statistics, which is the basis for using a
percentile without assuming a shape, but his result needs independent observations.

**Raw data and script.** `/home/pi/scratch/146-p95-vs-rms/` (`compare.py`, and its output
`results.csv` and `rounds.csv`; `tables.py` makes the tables below from `results.csv`).

**Result (computed 2026-10-13).** The script reproduced the stored band, median and tag count of
every slot in every session (84 slot-sessions: 7 sessions of 12 slots). All values are in points
of area error (%). (c) marks a central slot.

**Per-slot tables.** Band, median, 2 × RMS and |median| + 2 SD in points; ratio is band / (2 × RMS); below / above 2 SD is the share of tags (%) below median - 2 SD and above median + 2 SD; round medians are the slot's median in each counted round, in order.

**`20261005T071549445423`**

| Slot | n | Band | Median | 2 × RMS | Band - 2 × RMS | Ratio | \|Median\| + 2 SD | Skew | Below / above 2 SD | Round medians | SD within rounds |
|---|---|---|---|---|---|---|---|---|---|---|---|
| North 1 | 85 | 2.12 | +0.13 | 2.10 | +0.02 | 1.01 | 2.24 | -0.57 | 4.7 / 1.2 | +0.33, +0.22, +0.05 | 1.08 |
| North 2 | 85 | 1.94 | +0.71 | 2.19 | -0.25 | 0.89 | 2.45 | -0.35 | 5.9 / 1.2 | +0.75, +0.61, +0.81 | 0.88 |
| North 3 (c) | 90 | 2.69 | -0.18 | 2.64 | +0.05 | 1.02 | 2.75 | -0.51 | 5.6 / 0.0 | -0.54, -0.17, +0.16 | 1.27 |
| North 4 (c) | 90 | 3.36 | -0.48 | 3.36 | -0.01 | 1.00 | 3.56 | -0.40 | 4.4 / 0.0 | -0.51, -1.07, -0.20 | 1.52 |
| North 5 | 90 | 1.43 | +0.00 | 1.53 | -0.10 | 0.93 | 1.54 | -0.05 | 1.1 / 1.1 | +0.00, -0.39, +0.22 | 0.77 |
| North 6 | 90 | 2.98 | -0.53 | 2.45 | +0.53 | 1.21 | 2.61 | -1.20 | 7.8 / 0.0 | -0.53, -0.55, -0.56 | 1.05 |
| South 1 | 90 | 1.89 | -0.01 | 1.94 | -0.05 | 0.97 | 1.96 | -0.10 | 3.3 / 1.1 | +0.16, -0.13, -0.10 | 0.99 |
| South 2 | 85 | 1.63 | +0.45 | 1.71 | -0.08 | 0.95 | 1.95 | -0.34 | 5.9 / 0.0 | +0.47, +0.50, +0.32 | 0.76 |
| South 3 (c) | 90 | 2.25 | +0.52 | 2.51 | -0.26 | 0.89 | 3.01 | -0.58 | 4.4 / 0.0 | +0.31, +0.53, +0.63 | 1.26 |
| South 4 (c) | 90 | 2.38 | +0.38 | 2.55 | -0.17 | 0.93 | 3.01 | -0.48 | 5.6 / 0.0 | +0.56, +0.38, -0.19 | 1.28 |
| South 5 | 90 | 1.51 | +0.09 | 1.64 | -0.13 | 0.92 | 1.72 | +0.23 | 2.2 / 3.3 | +0.42, -0.16, -0.01 | 0.84 |
| South 6 | 90 | 1.78 | +0.04 | 1.82 | -0.04 | 0.98 | 1.86 | -0.14 | 2.2 / 2.2 | +0.27, +0.45, -0.11 | 0.91 |

**`20261005T141310628479`**

| Slot | n | Band | Median | 2 × RMS | Band - 2 × RMS | Ratio | \|Median\| + 2 SD | Skew | Below / above 2 SD | Round medians | SD within rounds |
|---|---|---|---|---|---|---|---|---|---|---|---|
| North 1 | 85 | 1.77 | -0.30 | 2.09 | -0.32 | 0.85 | 2.30 | -0.04 | 1.2 / 1.2 | +0.06, -0.30, -0.67 | 1.01 |
| North 2 | 90 | 1.86 | +0.51 | 1.97 | -0.11 | 0.94 | 2.33 | -0.52 | 6.7 / 1.1 | +0.52, +0.70, +0.35 | 0.91 |
| North 3 (c) | 85 | 2.64 | -0.39 | 2.82 | -0.18 | 0.94 | 3.09 | +0.09 | 2.4 / 2.4 | -0.75, -0.12, -0.45 | 1.34 |
| North 4 (c) | 90 | 2.93 | -0.62 | 3.14 | -0.21 | 0.93 | 3.56 | -0.07 | 1.1 / 1.1 | -0.53, -1.07, -0.41 | 1.50 |
| North 5 | 90 | 1.73 | +0.21 | 1.74 | -0.01 | 0.99 | 1.88 | -0.13 | 2.2 / 1.1 | +0.23, +0.19, +0.41 | 0.83 |
| North 6 | 88 | 2.22 | +0.03 | 2.51 | -0.29 | 0.88 | 2.57 | -1.34 | 3.4 / 1.1 | +0.04, -0.33, +0.24 | 1.30 |
| South 1 | 85 | 2.22 | -0.69 | 2.37 | -0.14 | 0.94 | 2.57 | -0.03 | 1.2 / 1.2 | -0.84, -0.55, -0.89 | 0.95 |
| South 2 | 90 | 1.58 | +0.38 | 1.59 | -0.01 | 0.99 | 1.91 | -0.20 | 3.3 / 1.1 | +0.37, +0.12, +0.53 | 0.77 |
| South 3 (c) | 90 | 2.44 | +0.16 | 2.60 | -0.16 | 0.94 | 2.79 | -0.65 | 4.4 / 0.0 | -0.21, +0.65, -0.12 | 1.27 |
| South 4 (c) | 90 | 1.97 | +0.35 | 2.06 | -0.08 | 0.96 | 2.34 | -0.58 | 4.4 / 0.0 | +0.32, +0.56, +0.57 | 1.02 |
| South 5 | 88 | 2.16 | -0.21 | 2.32 | -0.16 | 0.93 | 2.46 | -0.37 | 4.5 / 1.1 | +0.16, -0.21, -0.52 | 1.11 |
| South 6 | 90 | 2.11 | -0.72 | 2.27 | -0.16 | 0.93 | 2.76 | +0.48 | 0.0 / 4.4 | -0.89, -0.66, -0.72 | 1.03 |

**`20261007T070451149884`**

| Slot | n | Band | Median | 2 × RMS | Band - 2 × RMS | Ratio | \|Median\| + 2 SD | Skew | Below / above 2 SD | Round medians | SD within rounds |
|---|---|---|---|---|---|---|---|---|---|---|---|
| North 1 | 86 | 3.26 | -0.90 | 3.35 | -0.08 | 0.98 | 3.46 | -1.45 | 4.7 / 0.0 | -1.28, -0.89, -0.58 | 1.25 |
| North 2 | 88 | 2.52 | -0.80 | 2.60 | -0.09 | 0.97 | 2.74 | -0.19 | 4.5 / 1.1 | -1.40, -0.80, -0.42 | 0.86 |
| North 3 (c) | 90 | 2.91 | -1.36 | 3.33 | -0.42 | 0.87 | 3.65 | +0.03 | 2.2 / 2.2 | -1.96, -0.83, -0.65 | 0.98 |
| North 4 (c) | 90 | 2.33 | -0.25 | 2.38 | -0.05 | 0.98 | 2.61 | -0.36 | 3.3 / 0.0 | -0.38, -0.30, -0.20 | 1.19 |
| North 5 | 80 | 2.41 | -0.71 | 2.22 | +0.19 | 1.08 | 2.64 | -0.04 | 1.2 / 1.2 | -0.89, -0.57, -0.20 | 0.92 |
| North 6 | 80 | 2.97 | -0.91 | 3.22 | -0.25 | 0.92 | 3.37 | -1.40 | 3.8 / 0.0 | -1.58, -0.57, -0.93 | 1.15 |
| South 1 | 89 | 2.82 | -1.33 | 3.28 | -0.46 | 0.86 | 3.31 | +0.09 | 3.4 / 3.4 | -1.61, -1.25, -1.20 | 0.97 |
| South 2 | 88 | 2.21 | -0.76 | 2.39 | -0.18 | 0.92 | 2.51 | -0.04 | 1.1 / 0.0 | -1.27, -0.56, -0.65 | 0.83 |
| South 3 (c) | 90 | 1.55 | -0.16 | 1.58 | -0.03 | 0.98 | 1.71 | -0.08 | 3.3 / 2.2 | -0.43, -0.07, -0.02 | 0.77 |
| South 4 (c) | 85 | 1.62 | +0.11 | 1.66 | -0.04 | 0.98 | 1.77 | -0.49 | 5.9 / 0.0 | -0.05, +0.23, +0.31 | 0.83 |
| South 5 | 81 | 3.07 | -1.20 | 3.30 | -0.23 | 0.93 | 3.29 | -0.34 | 2.5 / 1.2 | -1.72, -1.13, -0.98 | 1.00 |
| South 6 | 90 | 2.24 | -0.37 | 2.09 | +0.15 | 1.07 | 2.31 | -0.35 | 4.4 / 1.1 | -0.42, -0.42, -0.02 | 0.97 |

**`20261008T081846523784`**

| Slot | n | Band | Median | 2 × RMS | Band - 2 × RMS | Ratio | \|Median\| + 2 SD | Skew | Below / above 2 SD | Round medians | SD within rounds |
|---|---|---|---|---|---|---|---|---|---|---|---|
| North 1 | 90 | 2.30 | +0.83 | 2.50 | -0.21 | 0.92 | 3.01 | -0.04 | 0.0 / 1.1 | +0.88, +0.47, +1.00 | 1.11 |
| North 2 | 90 | 2.46 | +0.26 | 1.90 | +0.56 | 1.29 | 2.20 | -1.51 | 6.7 / 0.0 | -0.04, +0.31, +0.33 | 0.94 |
| North 3 (c) | 85 | 1.97 | -0.45 | 2.22 | -0.25 | 0.89 | 2.44 | -0.10 | 3.5 / 0.0 | -0.48, -0.86, -0.11 | 0.96 |
| North 4 (c) | 85 | 2.46 | -0.43 | 2.34 | +0.13 | 1.05 | 2.51 | -0.61 | 4.7 / 0.0 | -0.26, -0.13, -0.83 | 1.01 |
| North 5 | 90 | 1.54 | -0.68 | 1.74 | -0.21 | 0.88 | 2.04 | +0.15 | 1.1 / 3.3 | -0.68, -0.59, -0.71 | 0.69 |
| North 6 | 90 | 1.58 | +0.17 | 1.94 | -0.36 | 0.81 | 2.08 | +0.27 | 1.1 / 3.3 | +0.36, +0.02, +0.19 | 0.97 |
| South 1 | 90 | 1.35 | -0.36 | 1.44 | -0.09 | 0.94 | 1.79 | +0.32 | 1.1 / 4.4 | -0.14, -0.36, -0.30 | 0.71 |
| South 2 | 90 | 1.37 | +0.34 | 1.66 | -0.28 | 0.83 | 1.78 | +0.84 | 0.0 / 2.2 | +0.32, +0.49, +0.30 | 0.73 |
| South 3 (c) | 85 | 2.08 | -0.13 | 2.13 | -0.05 | 0.98 | 2.24 | -0.44 | 4.7 / 0.0 | +0.02, -0.47, +0.06 | 1.02 |
| South 4 (c) | 90 | 2.70 | -0.86 | 2.99 | -0.29 | 0.90 | 3.26 | -0.10 | 2.2 / 2.2 | -0.56, -0.56, -1.24 | 1.17 |
| South 5 | 90 | 1.32 | -0.16 | 1.43 | -0.11 | 0.92 | 1.55 | +0.05 | 2.2 / 1.1 | -0.49, -0.09, -0.09 | 0.71 |
| South 6 | 90 | 2.39 | +0.77 | 2.55 | -0.15 | 0.94 | 2.84 | -0.29 | 3.3 / 0.0 | +0.93, +0.64, +0.94 | 1.04 |

**`20261012T070703613469`**

| Slot | n | Band | Median | 2 × RMS | Band - 2 × RMS | Ratio | \|Median\| + 2 SD | Skew | Below / above 2 SD | Round medians | SD within rounds |
|---|---|---|---|---|---|---|---|---|---|---|---|
| North 1 | 90 | 2.95 | +0.67 | 2.81 | +0.14 | 1.05 | 3.46 | -1.08 | 6.7 / 0.0 | +0.62, +0.63, +0.75 | 1.41 |
| North 2 | 90 | 1.45 | -0.03 | 1.51 | -0.06 | 0.96 | 1.56 | +1.18 | 0.0 / 4.4 | +0.06, -0.09, +0.00 | 0.76 |
| North 3 (c) | 90 | 2.70 | -0.58 | 2.55 | +0.15 | 1.06 | 2.73 | -0.64 | 5.6 / 0.0 | -0.57, -0.64, -0.46 | 1.09 |
| North 4 (c) | 85 | 2.40 | -0.40 | 2.37 | +0.04 | 1.02 | 2.55 | -0.36 | 4.7 / 0.0 | -0.62, -0.19, -0.59 | 1.06 |
| North 5 | 90 | 1.39 | -0.31 | 1.51 | -0.12 | 0.92 | 1.76 | -0.01 | 2.2 / 3.3 | -0.34, -0.38, -0.19 | 0.72 |
| North 6 | 90 | 1.83 | +0.12 | 1.97 | -0.14 | 0.93 | 2.07 | +0.07 | 1.1 / 1.1 | +0.17, +0.07, -0.06 | 0.99 |
| South 1 | 90 | 1.36 | -0.07 | 2.22 | -0.86 | 0.61 | 2.28 | -2.34 | 3.3 / 0.0 | -0.32, +0.02, -0.12 | 1.10 |
| South 2 | 90 | 3.03 | +0.52 | 2.67 | +0.37 | 1.14 | 2.78 | +1.53 | 0.0 / 6.7 | +0.55, +0.58, +0.44 | 1.13 |
| South 3 (c) | 90 | 2.85 | -0.42 | 2.66 | +0.19 | 1.07 | 2.89 | -0.67 | 4.4 / 0.0 | -0.31, -0.35, -0.68 | 1.23 |
| South 4 (c) | 85 | 3.39 | -0.95 | 3.46 | -0.07 | 0.98 | 3.59 | -0.33 | 4.7 / 0.0 | -0.70, -0.78, -1.52 | 1.27 |
| South 5 | 85 | 1.30 | +0.15 | 1.49 | -0.19 | 0.88 | 1.61 | +0.28 | 1.2 / 1.2 | +0.18, +0.11, +0.19 | 0.74 |
| South 6 | 90 | 2.58 | +1.14 | 2.96 | -0.38 | 0.87 | 3.06 | -0.54 | 3.3 / 1.1 | +1.00, +1.37, +1.17 | 0.96 |

**`20261013T074951947771`**

| Slot | n | Band | Median | 2 × RMS | Band - 2 × RMS | Ratio | \|Median\| + 2 SD | Skew | Below / above 2 SD | Round medians | SD within rounds |
|---|---|---|---|---|---|---|---|---|---|---|---|
| North 1 | 90 | 2.43 | +0.64 | 2.55 | -0.12 | 0.95 | 2.90 | +0.07 | 2.2 / 3.3 | +0.55, +0.88, +0.37 | 1.16 |
| North 2 | 90 | 1.43 | +0.11 | 1.50 | -0.07 | 0.95 | 1.63 | -0.67 | 3.3 / 0.0 | +0.11, -0.11, +0.15 | 0.75 |
| North 3 (c) | 85 | 2.51 | -0.62 | 2.71 | -0.20 | 0.93 | 2.89 | -0.40 | 3.5 / 0.0 | -0.40, -0.54, -1.17 | 1.13 |
| North 4 (c) | 85 | 2.88 | -0.62 | 2.67 | +0.22 | 1.08 | 3.04 | -0.56 | 3.5 / 0.0 | -0.58, -0.23, -0.71 | 1.22 |
| North 5 | 90 | 3.12 | +0.25 | 2.36 | +0.75 | 1.32 | 2.53 | +1.49 | 0.0 / 6.7 | +0.20, +0.56, +0.02 | 1.10 |
| North 6 | 90 | 2.13 | +0.36 | 2.22 | -0.09 | 0.96 | 2.44 | -0.17 | 3.3 / 1.1 | +0.60, +0.12, +0.12 | 1.08 |
| South 1 | 90 | 1.17 | +0.19 | 1.23 | -0.05 | 0.96 | 1.43 | -0.12 | 4.4 / 1.1 | +0.24, +0.19, +0.14 | 0.63 |
| South 2 | 90 | 1.89 | +0.58 | 2.23 | -0.34 | 0.85 | 2.68 | -2.12 | 4.4 / 0.0 | +0.44, +0.54, +0.75 | 1.05 |
| South 3 (c) | 90 | 2.45 | -0.22 | 2.34 | +0.11 | 1.05 | 2.46 | -0.62 | 5.6 / 0.0 | -0.56, +0.14, -0.18 | 1.11 |
| South 4 (c) | 85 | 3.04 | -0.86 | 3.23 | -0.19 | 0.94 | 3.42 | -0.33 | 3.5 / 0.0 | -0.86, -1.10, -0.76 | 1.28 |
| South 5 | 90 | 1.09 | +0.22 | 1.32 | -0.23 | 0.83 | 1.52 | -0.16 | 1.1 / 1.1 | +0.23, +0.21, +0.17 | 0.66 |
| South 6 | 90 | 5.69 | +1.29 | 4.83 | +0.86 | 1.18 | 5.08 | +2.12 | 0.0 / 6.7 | +1.59, +1.40, +0.91 | 1.85 |

**`20261013T081945572660`**

| Slot | n | Band | Median | 2 × RMS | Band - 2 × RMS | Ratio | \|Median\| + 2 SD | Skew | Below / above 2 SD | Round medians | SD within rounds |
|---|---|---|---|---|---|---|---|---|---|---|---|
| North 1 | 90 | 2.80 | +0.73 | 2.69 | +0.11 | 1.04 | 2.94 | +0.48 | 1.1 / 4.4 | +0.71, +0.62, +0.78 | 1.13 |
| North 2 | 90 | 1.55 | -0.03 | 1.63 | -0.08 | 0.95 | 1.66 | +0.13 | 2.2 / 2.2 | +0.03, +0.02, -0.36 | 0.83 |
| North 3 (c) | 85 | 2.60 | -0.47 | 2.63 | -0.04 | 0.99 | 2.85 | -0.81 | 4.7 / 0.0 | +0.16, -0.72, -0.52 | 1.14 |
| North 4 (c) | 85 | 2.57 | -0.34 | 2.57 | -0.00 | 1.00 | 2.75 | -0.59 | 3.5 / 0.0 | -0.61, +0.12, -0.73 | 1.15 |
| North 5 | 90 | 1.16 | +0.00 | 1.31 | -0.16 | 0.88 | 1.32 | +0.31 | 0.0 / 2.2 | +0.07, +0.00, -0.04 | 0.67 |
| North 6 | 90 | 2.14 | +0.42 | 2.24 | -0.10 | 0.96 | 2.45 | +0.33 | 1.1 / 3.3 | +0.60, +0.19, +0.45 | 1.01 |
| South 1 | 90 | 1.54 | +0.01 | 1.68 | -0.14 | 0.92 | 1.70 | +0.25 | 0.0 / 4.4 | -0.08, +0.08, -0.19 | 0.87 |
| South 2 | 90 | 1.96 | +0.58 | 2.05 | -0.10 | 0.95 | 2.18 | +0.69 | 0.0 / 2.2 | +0.59, +0.70, +0.58 | 0.80 |
| South 3 (c) | 90 | 2.58 | -0.24 | 2.49 | +0.09 | 1.03 | 2.64 | -0.67 | 5.6 / 0.0 | -0.00, -0.82, +0.24 | 1.16 |
| South 4 (c) | 85 | 3.26 | -1.21 | 3.74 | -0.48 | 0.87 | 3.96 | -0.25 | 2.4 / 1.2 | -1.81, -0.90, -0.89 | 1.33 |
| South 5 | 90 | 1.08 | +0.27 | 1.25 | -0.17 | 0.86 | 1.47 | -0.05 | 2.2 / 1.1 | +0.27, +0.26, +0.27 | 0.61 |
| South 6 | 90 | 2.66 | +1.36 | 3.17 | -0.51 | 0.84 | 3.23 | -0.56 | 5.6 / 0.0 | +1.54, +1.43, +0.95 | 0.97 |

**Summary.**

1. **Agreement.** In 70 of 84 slot-sessions the band and 2 × RMS differ by 0.3 points or less (9
   to 11 of 12 slots per session). The median ratio is 0.95 (lowest 0.61, highest 1.32), inside
   the 0.93 to 0.98 that normal errors would give.
2. **Where they differ by more than 0.3 points.** The band is wider in 5 of 84, and 2 × RMS is
   wider in 9 of 84. Where 2 × RMS is wider, it is the more cautious number, as it is for normal
   errors with a bias.
3. **The 5 slots where the band is wider are none of the central ones** (0 of 28 central
   slot-sessions): North 6 (2026-10-05 07:15, +0.53), North 2 (2026-10-08, +0.56), South 2
   (2026-10-12, +0.37), North 5 (2026-10-13 07:49, +0.75) and South 6 (2026-10-13 07:49, +0.86).
   Each has a tail on one side only: 6.7% to 7.8% of its tags lie beyond 2 SD on that side, none
   on the other, and its skew is 1.2 to 2.1 in size. In each, the tail tags come from one or two
   of the 3 photographs. For example, South 6 on 2026-10-13 07:49 has 6 tags reading +5.6% to
   +9.4% in round 1 and none in rounds 2 and 3; North 2 on 2026-10-08 has 6 tags at -2.5% to
   -3.0%, all in round 1. So these tails are something that happened to a group of tags in one
   photograph, not scatter from tag to tag. What it was is in item 8. In these 5 slots |median| + 2 SD is also smaller than the band: a normal
   estimate, with or without the bias kept apart, would have reported a narrower band than the
   tags showed.
4. **Central slots.** Band and 2 × RMS agree in 26 of 28 (median ratio 0.98); the other 2 have
   2 × RMS wider. Their errors lean low: skew is negative in 26 of 28 (median -0.46), and on
   average 4.1% of their tags lie below median - 2 SD against 0.4% above (2.3% each for normal
   errors; the other slots: 2.6% and 1.9%). This is the pattern the central low reading (section
   7) would give, with the tags of a central slot nearest the image centre reading smallest (in 8
   of the 28 slot-sessions the slot centre itself is within 1500 px of the image centre), but
   that was not tested here. The lean is not strong enough to push the band past 2 × RMS.
5. **All slots.** Skew is below -0.52 (2 standard errors) in 24 of 84 and above +0.52 in 6. On
   average 3.1% of tags lie below median - 2 SD and 1.4% above. The errors lean towards reading
   small.
6. **|Median| + 2 SD** is wider than the band in 79 of 84 (median by 0.29 points, at most 0.92),
   and narrower in the 5 slots of item 3.
7. **Between rounds.** The SD of tags about their own round's median (median over slot-sessions
   1.01 points) is nearly the whole SD about the slot median (1.03): their ratio has a median of
   1.00 and is never below 0.86. A slot's 3 round medians differ by a median of 0.40 points, at
   most 1.31. Most of a slot's spread is between tags in the same photograph; shifts between
   rounds add little to the SD. The one-sided tails of item 3 are the exception, since each
   belongs to one photograph.
8. **Cause of the 5 tails: visual inspection (Aaron, 2026-10-13).** Aaron looked at each round
   photograph holding a tail, copied to `/home/pi/scratch/` and named by date, UTC time, slot and
   round (for example `2026-10-13_0754UTC_South6_round1_sheet-not-flat.jpg`). Method: by eye, on
   screen, one look per photograph; no measurement of flatness or sharpness. Result:

   | Slot | Session | Round photograph | Tail | Seen |
   |---|---|---|---|---|
   | South 6 | 2026-10-13 07:49 | `rig/2026-10-13/075436_099643` (round 1) | 6 tags, +5.6% to +9.4% | Sheet not flat (also recorded under #116, section 14.1) |
   | North 5 | 2026-10-13 07:49 | `rig/2026-10-13/080440_535100` (round 2) | 6 tags, +2.9% to +4.3% | Sheet not flat |
   | South 2 | 2026-10-12 07:07 | `rig/2026-10-12/070819_803320` (round 1) | 2 tags, +3.6% and +5.0% | Sheet not flat |
   | South 2 | 2026-10-12 07:07 | `rig/2026-10-12/071825_823198` (round 2) | 4 tags, +3.0% to +4.1% | Sheet not flat |
   | North 2 | 2026-10-08 08:18 | `captures/2026-10-08/082015_437774` (round 1) | 6 tags, -2.5% to -2.9% | Sheet not flat |
   | North 6 | 2026-10-05 07:15 (SN000) | `captures/2026-10-05/071633_026877` (round 1) | 4 tags, -2.9% to -4.4% | No apparent issue |
   | North 6 | 2026-10-05 07:15 (SN000) | `captures/2026-10-05/071708_248354` (round 2) | 3 tags, -2.8% to -3.3% | No apparent issue |

   Paths are under `/var/lib/npec-rig/`. A sheet not lying flat is seen in 4 of the 5 slots,
   every one on SN001; North 6 on SN000 has no cause found. The errors go both ways: lifted tags
   read large, and a tilted tag shows the camera less area and reads small (North 2). Height
   alone does not account for the size: at about 0.145% of area per mm (section 7), +9.4% would
   need about 65 mm of lift, so something more than the lift (for example blur moving the
   detected corners) is likely involved; this was not measured. None of these rounds was flagged
   by the validation checks (section 6). The session files do not record which tag gave which
   error, so the tail tags were not matched one by one to the parts of the sheets seen lifted.

**What this means.** On this rig's data the percentile band and the normal estimate 2 × RMS are
the same number to within 0.3 points in 5 of every 6 slot-sessions, so using a percentile costs
nothing where the errors are close to normal. Where they differ by more, it is in both
directions: in 9 slot-sessions 2 × RMS is the wider, as normal errors with a bias would give; in
5 the band is the wider, and every one of those 5 is a group of tags in one or two photographs
reading off together, all on the same side. In those 5 a normal estimate would have
under-reported the spread by 0.37 to 0.86 points. In 4 of the 5, all on SN001, the sheet was
seen not to lie flat (item 8): the largest departures from normal errors in this data come from
sheets not lying flat, which the validation checks do not catch. The central slots, where the known central error sits, are not among them.

**What it does not show.** No confidence level can be attached to any band or ratio here: the 3
rounds are not independent samples of 85 to 90 tags (method, above). With 85 to 90 tags the
95th percentile lies between the 4th and 5th largest |error|, so 5 or 6 tags reading off together
decide the band; in this data such groups put the band above 2 × RMS by up to
0.86 points. Whether a round with a sheet not lying flat should count is not decided here. 7 sessions from 4
calibrations, 2 cameras; nothing here covers plants, plant height or segmentation. The pass or
fail of the 14.1 repeat validation is not judged here.

**Background and sources** (checked against the primary texts on 2026-10-13 unless stated).

- GUM (JCGM 100:2008): the expanded uncertainty is U = k × u_c(y) (6.2.1); "taking k = 2
  produces an interval having a level of confidence of approximately 95 percent" when the
  distribution is "approximately normal" and the degrees of freedom are large enough (6.3.3). A
  measurement result is taken as "corrected for all recognized significant systematic effects"
  (3.2.4), and enlarging the uncertainty instead of applying a known correction "should be
  avoided" (6.3.1, note). The rig's band does the opposite on purpose: it keeps each slot's bias
  inside the band, because the bias is measured per session and not corrected.
- Wilks, S. S. (1941), "Determination of sample sizes for setting tolerance limits", Annals of
  Mathematical Statistics 12(1): 91-96, doi:10.1214/aoms/1177731788. Tolerance limits from order
  statistics are valid "for any unknown continuous distribution" (p. 93). From his one-sided
  result (Eq. 6, p. 94), the largest of 59 independent observations bounds at least 95% of the
  population with confidence 1 - 0.95^59 = 0.952 (58 gives 0.949). The figure 59 is worked out
  here, not stated by Wilks; Blatman et al. (2017, arXiv:1701.02373, Table 1) state it. It needs
  independent observations, which these tags are not (method, above).
- NDEP, Guidelines for Digital Elevation Data, Version 1.0 (2004): in open terrain, where random
  errors "typically follow a normal distribution" (1.5.2.6), accuracy at 95% is 1.96 × RMSE
  (1.5.3.1); elsewhere "a normal distribution of error cannot be assumed and, therefore, RMSE
  cannot be used to calculate the 95-percent accuracy value", and the 95th percentile is used
  (1.5.3.2).
- ASPRS Positional Accuracy Standards, Edition 1, Version 1.0 (2014; published in
  Photogrammetric Engineering & Remote Sensing 81(3), 2015, A1-A26): non-vegetated vertical
  accuracy is RMSE × 1.96, for terrain "where elevation errors typically follow a normal error
  distribution"; vegetated vertical accuracy is "the 95th percentile of the absolute value of
  vertical errors" (7.4). Edition 2 (2023, Version 2 2024) drops the 95% level and reports RMSE
  only, with vegetated accuracy "assessed and reported as found". **Not checked against the
  standard itself** (behind a login): from FGDC/NGAC slides (April 2024) and Abdullah, PE&RS
  91(5), 2025, whose reason is that the 95% level "offers no additional benefits to the RMSE while
  causing considerable confusion".

NDEP and ASPRS use 1.96, not the GUM's 2. The difference is 2% of 2 × RMS, at most 0.10 points
here. Recounted with 1.96 × RMS (not part of the method set beforehand): 72 of 84 agree within
0.3 points, the band is wider in the same 5, and 1.96 × RMS is wider in 7 instead of 9.

## 7. Known error sources

**Central error of the Arducam (closed investigation, `reference/arducam-central-error-2026-10.md`).**
Targets within about 1500 px of the image centre read smaller than targets in mid-field. A Canon
camera photographing the same table does not see it, so it belongs to the Arducam, not the table,
sheets, trays, lighting or detector. Its size depends on the focus lens position:

| Lens position | Ring 1000 to 1500 px from centre (points) |
|---|---|
| 6.10 | -3.63 |
| 6.18 | -2.20 |
| 6.26 | -1.10 |
| 6.36 | -0.05 |
| 6.44 | +0.49 (59 of 355 targets no longer readable) |

One photograph per position, 2026-10-01, old camera SN000, nothing else changed. On average about
1.2 points per 0.1 of lens position. With one photograph per position there is no repeat at any
one position; the photo-to-photo noise (section 8, at most about 0.2 to 0.3 points for one photo) is small
against the 4-point change across the sweep. Each value comes from one least-squares fit per
photo: every tag's area error is fitted with a tilted plane across the image plus one offset for
each ring of distance from the image centre; the value is the ring's offset against the ring 2500
to 3500 px from centre. Calibration `20261001T091727374749`. The photos record the focus lock as
off. Raw data: 12 photos,
`/var/lib/npec-rig/captures/2026-10-01/142831_730852` to `150403_404929`, listed in
`/home/pi/scratch/sweep_log.txt` (times there are chamber local time, UTC+2); script
`/home/pi/scratch/sweep_check.py`. The ring 0 to 1000 px holds only 5 tags; it reads further low
(down to -5.27 points at 6.10), which is the "-5.27" in the investigation's record.

On SN001 the central error has been checked once, at lens 6.16 with the packing foam still on
(section 8.2: ring 0 to 1000 px -2.80%); it has not been measured against lens position, and not
after the foam came off. The focus position is the experimenter's choice; the rig does not tune it for
accuracy. Validation measures the resulting error per slot, which is why central slots have wider
bands.

**Plant height.** About +0.145% area per mm above the tray top (section 4). Not included in the
bands.

**Segmentation** (separating plant from background). Not yet measured on this rig. Expected to be
several percent. Measured at milestone M5.

## 8. Repeatability and stability

| Quantity | Result | How measured | Date |
|---|---|---|---|
| Photograph-to-photograph noise, old camera SN000 | 0.27 and 0.46 points: the standard deviation over 348 tags of the difference between two photos (12.5% light against 25%, and 50% against 25%). A difference of two photos carries about 1.4 (√2) times one photo's noise, and here also any effect of the light change, so one photo's noise is at most about 0.19 to 0.33 points (derived) | 3 photos, one per light level, auto-exposure compensating (3377, 7119 and 1714 µs), nothing else changed, calibration `20261001T091727374749`. Photos `captures/2026-10-01/113019_175501` (25%), `113116_696924` (12.5%), `113126_805785` (50%); script `/home/pi/scratch/intensity_test.py`; the output exists only in that session's chat record | 2026-10-01 |
| Photograph-to-photograph noise, replacement camera | median per-tag standard deviation 0.15 points (middle half of tags 0.12 to 0.19) | 10 photos in a row, nothing changed, fixed exposure, packing foam still on (section 8.2, step 3) | 2026-10-07 |
| App restart, replacement camera | 5 warm restarts: median -0.04 to +0.06, every slot within ±0.24 | As run 3i, foam still on (section 8.2, step 5) | 2026-10-07 |
| One photo a minute for 6.8 hours, replacement camera | no drift (each hour's median within 0.06 points of the others); the 20-minute cycle present, swing about 0.5 to 0.6 points, following the chamber's humidity (r -0.86) and temperature (r +0.61) | Overnight run after the foam came off, chamber's own record (section 8.2) | 2026-10-07 |
| Removing packing foam from the camera body | readings about 0.8 points lower and slots about 15% less sharp, lasting at least 6.8 hours; a new calibration was needed | Step 6 and overnight photos against the last photo before removal (section 8.2) | 2026-10-07 |
| Lens moved and driven back to the same position | median change -0.03 points, spread 0.28, 355 of 355 tags; over 60 min largest slot change +0.35 points (about 1/6 of that slot's band) | Autofocus moved the lens, re-locked at 6.15, photographs at +0, +15, +30, +60 min, each tag compared with itself. One run. Raw data `/home/pi/scratch/lens-return-2026-10-05/` and validation session `20261005T071549445423`, rounds 4 onward | 2026-10-05, `reference/lens-return-2026-10.md` |
| Drift at a fixed lens position after moves | central ring changed 1.3 points in 35 min | Lens sweep then return to 6.18 | 2026-10-01 |
| Change over time with nothing moved (control) | over 45 to 60 min: median within ±0.17 points, central ring within ±0.26, single slots up to 0.52 (about 1/4 of that slot's band); goes up and down, not a steady drift | Same method, lens untouched, two series (one partly disturbed by people in the chamber). Raw data `/home/pi/scratch/lens-control-2026-10-05/` | 2026-10-05, `reference/lens-return-2026-10.md` |
| One photo a minute for 2 hours, no reopen, lens locked (run 3j) | a repeating cycle of about 19 minutes: median swings by about 0.35 points (-0.08 to +0.33 against the first photo), largest slot 0.62; no drift (each cycle returns to the same low point); sharpness rises and falls with it; follows the chamber's air temperature (19.8 to 20.3 °C, every 19 min, correlation 0.84) and humidity cycle | Plain photos through the app, section 8.1 run 3j, compared with the chamber's 1-minute log | 2026-10-06 |
| App restart | right after: median +0.08 and +0.09 points (two attempts), 355 of 355 tags; over 60 min median within ±0.13, largest slot -0.29 (about 1/6 of its band); inside the control range | Server killed and restarted, lens driven back to 6.15 at start-up; repeat-photograph test (section 8.1). Two attempts. Raw data `/home/pi/scratch/lens-restart-2026-10-05/` and `lens-restart-2026-10-05b/`, validation session `20261005T111520006719` | 2026-10-05, `reference/lens-return-2026-10.md` |
| Power cut (cold start) | right after: median -1.73 points, 291 of 354 tags found, central slots blurrier; +15 min -0.41, +30 -0.38, +60 -0.14 (largest slot -0.62); recovers with no lens move | Pi off about 30 min, camera not opened until the run; repeat-photograph test (run 3) | 2026-10-06 |
| Two calibrations in a row | scale fields agreed within 0.02% to 0.16% | 332 and 340 tags, lens moved away and back, 2026-09-25 | Before the current lens-drive method |

On 2026-10-05, the changes after moving the lens and driving it back (run 1) and after an app
restart (run 2) were inside the ordinary change over time measured by the control, so neither
added anything detectable. The 2026-10-01
drift (1.3 points) was about 5 times larger than anything seen on 2026-10-05. The reason is not
known.

**Photos flagged as not covered by the validation bands (built 2026-10-08, #49).** Two
conditions measured above (a lens away from its locked position, and the hour after a cold start)
are not covered by the bands, so every photo record now says whether it was taken under one of
them. This is a record of conditions, not a correction: a flagged photo is kept, not changed.

- *Lens check.* The lens position the camera reports in the photo's own data is compared with the
  focus lock. The photo is flagged when focus is not locked, when no position is reported, or when
  the two differ by more than 0.005. The 0.005 is the tolerance the app already uses to confirm a
  lens move, a decision, not a measurement. Limit: a camera that ignores lens commands reports the
  old position (section 11, open point 3), so this catches a lens reported elsewhere, not a lens
  that moved while the report did not.
- *Cold-start window.* Each photo records the Linux boot ID, the seconds since the Pi booted (the
  kernel's own count, which does not depend on the clock), the seconds since the app started, and
  the gap before the app started. A photo is flagged when the Pi has been up less than 60 minutes.
  **The 60 minutes is a decision, not a measurement.** It comes from one cold start on the old
  camera (Pi off about 30 min, recovered over about an hour, table above). Measured once on SN001
  (2026-10-14, section 14.3): readings back by +15 minutes. The 60 minutes stays a decision. A reboot without a power cut is flagged too, because
  it is not known whether the camera stays warm through one. Checked on the rig, 2026-10-08: a
  photo with focus locked at 6.04 reported 6.04 and was not flagged; one with focus unlocked was
  flagged. The cold-start flag itself is checked by unit tests only, because the Pi was not
  rebooted to test it.
- *Camera-fault window (#51, built 2026-10-09).* The camera runs in its own program. Every camera
  call has a time limit; when one runs out, the program is ended, a new one opens the camera, and
  the app restores the settings and drives the lens back the one consistent way (the lock is kept
  only if the camera confirms the lens there). The fault and the restart are saved with the boot ID
  and uptime (`camera_events`, `docs/database.md`), and a photo taken within 60 minutes after the
  restart is flagged as not covered by the bands. The window counts from the restart, which reopens
  the camera and drives the lens again, so after a long outage the photos once the camera is back
  still get the whole hour. **The 60 minutes is a
  decision, not a measurement**: on 2026-10-06 a camera fault left the central trays about half as
  sharp at the same reported lens position (section 8.1, run 3g), and how long such a change lasts
  has not been measured, so the cold-start window is used until it is. **The time limits are
  decisions too**: 30 s for a full-res photo (measured 2.7 to 2.8 s, section 8.2, step 3), 20 s for
  reopening the camera (Reset camera measured 2.3 to 2.5 s), 90 s for autofocus (above its own 60 s
  limit), 10 s for every other call, and 30 s to open the camera. They are set several times above
  the measured calls because a false alarm costs more (the lens is moved and an hour of photos is
  flagged) than a late one (one photo). Limit: only a call that does not finish counts. A camera
  fault that libcamera recovers from by itself, without a call hanging, is not seen.
  Checked on the rig, 2026-10-09 (SN001, focus locked at 6.04): the camera program was frozen
  (`kill -STOP`) and a photo asked for. The app answered after 30.1 s that the camera stopped
  responding; the new camera program was ready 1.1 s later, with focus locked again at 6.04, and the
  next photo was flagged as taken after a camera fault (lens reported 6.040, not flagged). Killing
  the app with SIGKILL also ended the camera program. A full-res photo took 2.70 to 2.81 s (3
  photos), against 2.67 to 2.71 s before this change; the live preview and focus zoom kept 10 and 5
  frames per second; free memory stayed above 12.8 GB of 16 GB during photos.
- *Validation.* A validation round whose photo is flagged is held back from the bands, with the
  reason shown; the operator can still count it (Aaron, 2026-10-08).
- *Not covered.* A camera fault in the middle of a run (frontend timeout, run 3g) is not detected
  yet: it happens inside the camera software and the app does not see it.

### 8.1 The repeat-photograph stability test

This is the test behind the lens-return, control, restart and power-cut results. It asks whether
the rig reads the same area for the same object after a disturbance, compared with how much the
reading changes when nothing is disturbed.

**Procedure**

1. Calibration and validation are done, focus is locked, and the calibration sheets lie on the
   trays. Nothing on the table is touched for the rest of the test; the chamber stays closed.
2. **Reference photograph:** one validation-round photograph taken through the app, right before
   the disturbance (or at the start, for a control).
3. **Disturbance:** the event being tested (or none, for a control). The time is recorded in UTC.
4. **Follow-up photographs:** validation-round photographs at +0, +15, +30 and +60 minutes after
   the disturbance, taken by a script calling the app's own round endpoint. The app holds them
   back as "not moved", so they never count towards a validation; their measurements are stored.
   Focus status (locked, lens position) is recorded with each photograph.
5. **Comparison:** each calibration tag is matched to itself in the reference photograph (same
   tag ID, within 20 px; IDs repeat across sheets, so position is needed). For each photograph:
   the median and standard deviation of the change in area error over all matched tags, the
   median for the ring 1000 to 1500 px from the image centre (where the lens-dependent central
   error is largest), and the median per tray slot. Tags that do not match (moved or hidden) are
   left out and counted.
6. **Judgement:** the disturbance added nothing detectable if its changes fall within the
   control's range. Every slot change is also compared with that slot's own validation band.

Script and analysis: `reference/lens-return-2026-10-analyse.py` (reads stored tag detections,
changes nothing).

**Runs**

| Run | Disturbance | Date (UTC) | Status | Result |
|---|---|---|---|---|
| 1 | Autofocus moved the lens 4 times (distance not recorded), then re-locked at 6.15 | 2026-10-05, 07:34 | Done | Inside the control range (section 8 table) |
| Control A | None; people working in the chamber, door opened, one sheet moved, 23 tags hidden | 2026-10-05, 09:02 to 10:02 | Done, disturbed | 332 tags compared |
| Control B | None; undisturbed | 2026-10-05, 10:02 to 10:47 | Done | Median within ±0.10, slots up to 0.52 |
| 2 | App restart: the server process is killed and started again. At start-up the app drives the lens to the locked position the same way as Lock focus (0.3 below, pause, target) and waits until the camera reports it there | 2026-10-05, 10:53 and 11:15 | Done (first attempt disturbed after +0) | Inside the control range |
| 3 | Power cut at the rig: the Pi is switched off long enough to cool (for example 30 minutes), then on | 2026-10-06, 08:30 to 09:31 | Done | Large change right after, recovering within an hour (below) |

**Run 3 method, written before the run (2026-10-06).** The Pi was shut down on the evening of
2026-10-05 and left off for about 30 minutes, then booted; the app was not started and the camera
not opened until the run, so the camera did not warm up and the focus motor had been without
power. Lights at full, door closed, nothing on the table touched since the last validation round.
Two differences from steps 2 and 4 above: (1) the reference is the last validation round before
the shutdown, `2026-10-05/141511_466090` (session `20261005T141310628479`, round 3, 14:15:11 UTC),
because a fresh reference would have opened the camera; (2) the follow-up photographs are plain
captures through the app (`POST /capture`, the same full-res capture path as a round), because
that session is closed and a new session would count the first photograph as a validation round.
The app is started by hand; at start-up it drives the lens to the persisted 6.27 and restores the
lock. Photographs at +0, +15, +30 and +60 minutes after the lock is restored. Analysis as above,
each tag compared with itself in the reference.

**Run 3b method, written before it runs (2026-10-06), added after the +0 photograph** showed the
central slots blurrier than in the reference. Question: does driving the lens to both ends of its
range before driving it to the focus position restore the sharpness? Right after the +60
photograph, nothing else changed: the lens is set to the minimum, then the maximum of the
camera's probed range, then to 6.27, each held 30 s, with the reported position and the focus
score read every second (which also shows whether the lens follows commands after a full-res
capture, the open lens bug). Then Lock focus (the app's usual 0.3-below approach), then one
capture. Compared with the +60 photograph: sharpness on the tag sheets at each slot centre, tags
detected, and the per-tag area change against the reference.

**Run 3 results** (app started 08:30:54 UTC; lens reported 6.27 and locked at 08:31:01; reference
`2026-10-05/141511_466090`, 354 tags). Sharpness is the Laplacian variance of a 600 px square at
each slot centre on the tag sheets, as a ratio to the reference (1.00 unchanged).

| Photo | Time (UTC) | Tags matched | Median change | Spread (SD) | Ring 1000 to 1500 px | Largest slot median | Sharpness, median of 12 slots | Sharpness, North 3 / South 3 / South 4 |
|---|---|---|---|---|---|---|---|---|
| +0 | 08:31:03 | 291 | -1.73 | 1.03 | -1.07 | -2.81 (North 2) | 0.82 | 0.43 / 0.38 / 0.43 |
| +15 | 08:46:06 | 348 | -0.41 | 0.57 | -0.02 | -0.88 (South 1) | 0.94 | 0.79 / 0.78 / 0.82 |
| +30 | 09:01:04 | 346 | -0.38 | 0.66 | -0.08 | -1.00 (South 1) | 0.95 | 0.80 / 0.79 / 0.83 |
| +60 | 09:31:03 | 352 | -0.14 | 0.50 | +0.02 | -0.62 (South 1) | 0.97 | 0.90 / 0.91 / 0.92 |

The image did not move (tags within about 3.5 px of the reference, scale change 0.02%) and the
reported lens position was 6.27 throughout. Right after a cold start the central trays are
blurrier, fewer tags are found, and areas read about 1.7 points low; North 2 (-2.81) is outside
its band (±1.86%). Without any lens move the picture sharpens and the readings return: by +15
min most of the change is gone, by +60 the median is -0.14 and the largest slot -0.62, close to
the control's 0.52. The likely cause is the camera warming up after being cold; it was not
measured directly. **Practical consequence:** after a power cut, readings in roughly the first
15 minutes after the app opens the camera are not covered by the bands; by 60 minutes they are
close to the ordinary change over time.

**Run 3b result: the sweep did not happen; the lens bug reproduced instead.** After the 4
full-res captures of run 3 (plain `POST /capture`, no calibration, no knock, no Autofocus), the
lens was set to 0.0 and to 15.0 and held 30 s at each: every command returned 200, but all 100
per-second readings of the reported position were 6.27 and the focus score stayed between 374 and
380, so the lens did not move. Lock focus then reported success at 6.27, the position the lens
already reported. The after-sweep photograph (09:32:52) matches +60 (median -0.11, sharpness
0.96). So whether a sweep to both ends improves sharpness is still not known.

**Run 3c method, written before it runs (2026-10-06):** the run 3b sequence repeated in a freshly
restarted app (server killed and started again, start-up drive to 6.27 and lock), before any
full-res capture in that process, so the lens follows commands. Compared with the +60 and
after-sweep photographs and the reference, as in run 3b.

**Run 3c result** (restart 09:36:16 UTC, locked 6.27 at 09:36:20). The lens followed every
command: focus score 375 before, 3.1 at 0.0, 2.3 at 15.0, 336 to 340 back at 6.27 (the focus-aid
square is at table height, below the trays). Photograph 09:38:07 against the reference: 354 of
354 tags matched, median change +0.30 points (spread 0.48), ring 1000 to 1500 px +0.04, slots
-0.06 (North 4) to +0.59 (North 1). Sharpness, median of 12 slots, 1.03 (0.96 just before the
sweep); North 3 / South 3 / South 4 1.02 / 1.08 / 1.05; North 4 fell from 1.13 to 0.84.

Reading: after the sweep every tag was found again and most slots were as sharp as in the
reference, but the readings moved by about +0.4 points from just before (-0.11 to +0.30), more
than the control's median change (within ±0.17). One run, 7 minutes after +60, with a restart in
between (a restart alone moved readings +0.08 and +0.09 on 2026-10-05), so the sweep's own effect
is not separated from warming up and the restart. It does show the lens lands slightly
differently after a different route to the same reported position.

**Run 3d method, written before it runs (2026-10-06, about 11:40 UTC).** Photographs at 11:18 to
11:19 UTC (after the lens diagnosis, several app restarts and the slice 1 fix) found 318 tags
against 359 at 09:38, with the central slots about half as sharp (North 3 / South 3 / South 4
0.51 / 0.46 / 0.51), lens reported 6.27 both times and no tag moved (318 of 318 within 20 px,
median 2.2 px). Question: does driving the lens to both ends of its range, then to 6.27 and Lock
focus, restore the sharpness? With the slice 1 fix the lens follows commands after a capture.
Steps, nothing else changed, door closed: one capture; lens to 0.0, 15.0, 6.27 (15 s each, reported
position and focus score read twice a second); Lock focus; two captures. Compared: tags found,
sharpness per slot against the 2026-10-05 reference, and per-tag area change against the first
capture. Raw data: `/home/pi/scratch/lens-fix-check-2026-10-06/`.

**Run 3d result.** Before the run Aaron had moved the lens and locked it again at 6.27 (after a
capture, through the app). The lens followed every command (focus score 3.1 at 0.0, 2.3 at 15.0,
375 back at 6.27).

| Photo | Time (UTC) | Tags found | Sharpness, median of 12 slots | North 3 / South 3 / South 4 | Median change against P1 |
|---|---|---|---|---|---|
| (11:18, before Aaron's lock) | 11:18:32 | 318 | 0.90 | 0.51 / 0.46 / 0.51 | |
| P1, before the sweep | 11:30:03 | 341 | 0.93 | 0.66 / 0.63 / 0.69 | |
| P2, after sweep and lock | 11:31:01 | 339 matched | 0.93 | 0.82 / 0.81 / 0.86 | +0.39 (spread 0.43) |
| P3, 5 s later | 11:31:06 | 338 matched | 0.95 | 0.85 / 0.87 / 0.90 | +0.50 (spread 0.50) |
| (09:38, after run 3c's sweep) | 09:38:07 | 359 | 1.03 | 1.02 / 1.08 / 1.05 | |

Reading: with the lens reported at 6.27 every time, the sharpness of the central slots ranged
from about half to fully that of the reference over the day, depending on the lens's history.
The sweep raised it, but not to the 09:38 level. Readings moved with it: +0.39 points after the
sweep, and P3 moved a further +0.11 from P2 with no command between them except the drive back
after P2's capture. This does not reopen the closed central-error investigation, but it measures
that the error at one reported lens position is not fixed from one lens history to the next.

**Run 3e method, written before it runs (2026-10-06, about 11:55 UTC): does the static tag 500
show it?** During an experiment no one will re-validate, so a change in the lens landing has to
be seen in the photographs themselves. Tag 500 (section 3) never moves, so a change in its
apparent area or sharpness between photographs comes from the camera side. Question: when the
calibration tags' readings change with the lens history, does tag 500 change too, and by more
than its photograph-to-photograph noise (0.15% in area between two photographs at 11:45)? Four
conditions, 2 captures each, nothing on the table touched, door closed: (1) nothing changed;
(2) lens to 0.0, 15.0, 6.27 (10 s each), Lock focus; (3) app restart (start-up drive to 6.27);
(4) the sweep of (2) again. For each capture: tag 500's area in pixels and the sharpness of a
500 px square around it; the calibration tags' median area error with the current calibration,
for all tags, the North row and the central slots (North 3, North 4, South 3, South 4). Compared
as changes against the first capture of condition 1. Raw data:
`/home/pi/scratch/lens-fix-check-2026-10-06/tag500-test/`.

**Run 3e result** (11:53 to 11:55 UTC; the lens followed every command, Lock focus confirmed 6.27
each time). Changes against the first capture; calibration tags in points of area error:

| Capture | Tag 500 area | Tag 500 sharpness | Tags | All tags | North row | Central slots |
|---|---|---|---|---|---|---|
| 1 nothing changed, a | 0.00% | 30.8 | 350 | 0.00 | 0.00 | 0.00 |
| 1 nothing changed, b | -0.26% | 30.8 | 345 | -0.03 | -0.16 | +0.02 |
| 2 sweep and lock, a | -0.27% | 30.1 | 349 | +0.03 | -0.02 | +0.06 |
| 2 sweep and lock, b | -0.12% | 32.4 | 350 | +0.18 | +0.03 | +0.13 |
| 3 app restart, a | -0.13% | 34.2 | 351 | +0.40 | +0.19 | +0.25 |
| 3 app restart, b | +0.13% | 35.9 | 352 | +0.29 | +0.15 | +0.16 |
| 4 sweep again, a | +0.14% | 34.2 | 352 | +0.33 | +0.20 | +0.30 |
| 4 sweep again, b | +0.07% | 36.6 | 351 | +0.40 | +0.22 | +0.32 |

Reading: none of the four conditions moved the calibration tags by more than 0.40 points this
time, much less than the cold start (-1.73) or the 11:18 photographs. Tag 500's area varied
-0.27% to +0.14% with no pattern; two photographs 5 s apart differed by 0.26%, so its area cannot
show a change of this size. Its sharpness rose 19% (30.8 to 36.6) while the tags rose 0.40 points,
which may track the change but is not shown by 8 photographs. Not answered: whether tag 500 shows
a larger change. That needs a condition that is known to move the readings by about a point or
more.

**Run 3f method, written before it runs (2026-10-06, about 12:10 UTC).** A change of known size:
lens set to 6.17 and Lock focus, 2 captures; set to 6.37 and Lock focus, 2 captures; set to 6.27
and Lock focus, 2 captures. From the central-error investigation, 0.1 of lens position moves the
central readings by about 1.2 points. These are test settings, not recommended positions; the
experimenter's 6.27 is restored at the end. Same quantities as run 3e, as changes against the
first 6.27 capture. Raw data: `/home/pi/scratch/lens-fix-check-2026-10-06/tag500-test-3f/`.

**Run 3f result** (12:07 to 12:08 UTC; every lock confirmed). Changes against the first 6.27
capture; calibration tags in points of area error:

| Capture | Tag 500 area | Tag 500 sharpness | Tags | All tags | North row | Central slots |
|---|---|---|---|---|---|---|
| 6.27, a | 0.00% | 28.5 | 341 | 0.00 | 0.00 | 0.00 |
| 6.27, b | -0.25% | 28.7 | 346 | -0.01 | -0.07 | -0.06 |
| 6.17, a | +0.27% | 49.2 | 355 | +0.58 | +0.67 | -0.09 |
| 6.17, b | +0.16% | 48.8 | 355 | +0.69 | +0.71 | +0.14 |
| 6.37, a | -0.41% | 22.5 | 274 | -0.97 | -1.03 | -0.90 |
| 6.37, b | -0.35% | 22.6 | 279 | -1.01 | -1.18 | -1.00 |
| 6.27 again, a | -0.26% | 28.6 | 346 | -0.00 | -0.04 | -0.12 |
| 6.27 again, b | -0.44% | 28.1 | 342 | -0.05 | -0.03 | -0.08 |

Reading: a lens change that moves the calibration tags by +0.6 to -1.0 points changes tag 500's
**sharpness** by +72% and -21%, against about 2% between repeated photographs at one position;
returning to 6.27 brought it back to within 1% (28.1 to 28.6). Tag 500's **area** changed by
only +0.2% and -0.4%, about as much as its repeat noise (0.25%), so its area is not a usable
signal. Tag 500's sharpness is a usable detector of a change in the lens landing. Not measured:
its relation to the readings is not a straight line, so it can say "changed", not by how many
points; the sharpness score also depends on
light, so a change of chamber lighting would show too.

**Run 3g (2026-10-06, 12:46 UTC): a case tag 500 does not show.** At 12:37 UTC the camera stopped
delivering frames ("Camera frontend has timed out") just after three app reloads in about a
minute (code edits) while the preview was being read; the app was restarted at 12:44. Then, with
nothing else changed, lights as before (exposure 3.4 ms, same mean brightness), the tag 500
reference was set (12:46:32) and the lens locked at 6.37 and back at 6.27, one capture each.
Sharpness per slot against the 2026-10-05 reference, and changes against the reference capture:

| Capture | North 3 / South 3 / South 4 | Tags found | Calibration tags, all / central | Tag 500 sharpness (app's check) |
|---|---|---|---|---|
| 12:07 (run 3f, 6.27, before the timeout) | 0.67 / 0.61 / 0.74 | 341 | | |
| 12:46:32, 6.27 (reference set) | 0.36 / 0.31 / 0.39 | 257 | 0.00 / 0.00 | 33.5 (reference) |
| 12:46:37, 6.27 | | 257 | -0.03 / +0.07 | +2.9%, OK |
| 12:46:44, 6.37 | 0.27 / 0.26 / 0.33 | 155 | -0.99 / -1.13 | +3.7%, OK |
| 12:46:50, 6.27 | | 264 | +0.05 / +0.21 | +1.1%, OK |

Reading: after that restart the central slots were about half as sharp as at 12:07, at the same
reported 6.27, and a lens change that moved the readings by -1.0 points did not change tag 500's
sharpness by more than 4%. So tag 500 at the north table edge does not reliably show a change in
the central trays; in run 3f it did. The reference set at 12:46 was taken in the blurred state and
is not a valid reference. Where a reference target sits matters: tag 500 is at tray height but at
the north edge of the frame, and its sharpness did not stand for the trays in the middle.
(Corrected 2026-10-06: an earlier version of this section said tag 500 sits at table height; it
sits at tray height.)

**Tag 500 focus sweep (2026-10-06, 13:38 to 13:39 UTC).** Can tag 500 serve as a focus target?
The app's focus-aid square was put on tag 500 (preview coordinates 719, 181; 64 px, about the
tag and a margin) and the lens stepped upward from 5.50 to 7.00 in steps of 0.05, approached from
5.2, 0.8 s after each step, focus score read 3 times per step (repeat readings within about 2%).
Afterwards the focus-aid square was put back and the lens locked at the experimenter's 6.27.

| Lens | 5.50 | 5.75 | 5.90 | 6.00 | 6.05 | 6.10 | 6.15 | 6.20 | 6.25 | 6.30 | 6.35 | 6.45 | 6.60 | 6.80 | 7.00 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Score (mean of 3) | 73 | 196 | 333 | 538 | 451 | 544 | 576 | 497 | 563 | 653 | 522 | 371 | 244 | 114 | 66 |

Result: tag 500's sharpness rises 10 times from the ends of the sweep to the top, so it is a
usable focus target. The top is broad and uneven: above half the highest score from 5.90 to 6.45,
the highest single step at 6.30, and lower steps at 6.05 and 6.20 inside the peak. A parabola fit
over 5.75 to 6.65 puts the peak at 6.20 (6.19 over 5.90 to 6.50). The lens position is reported on
the camera's 0 to 15 scale; it is not a calibrated distance, so no camera-to-tag distance follows
from it. One sweep; repeatability not measured. Raw data:
`/home/pi/scratch/lens-fix-check-2026-10-06/tag500-sweep.txt`.

**Run 3h method, written before it runs (2026-10-06, about 14:10 UTC): can the tray tags correct
a lens-landing change?** Every tray now carries an identity tag (IDs 1 to 12, nominal 30 mm,
east-west calliper readings of a sample 30.00, 29.96, 30.27, 29.99, 29.84, 30.01, 29.92, 30.01 mm,
mean 30.00, SD 0.12; a few mm above the tray surface; 9 of 12 found in a photograph at 14:07).
Lens locked at 6.27, 6.37, 6.17 and 6.27 again (test settings), 2 captures each. For each capture
and each tray with a found tray tag: the tray tag's side length in pixels against the first 6.27
capture gives a correction factor (old side / new side)², and the calibration tags in that tray
are compared with the first capture before and after multiplying their area by it. Question: does
the correction bring the calibration tags back to their 6.27 readings? Raw data:
`/home/pi/scratch/lens-fix-check-2026-10-06/traytag-test/`.

**Run 3h result** (14:08 UTC; the lens was locked at 6.17 before 6.37, the reverse of the order
written above, which does not change the comparison). 9 tray tags found in every capture (1, 2,
4, 5, 7, 8, 9, 10, 11; about 144 to 148 px across), each in its own slot. Mean absolute change of
the slot medians against the first capture, in points:

| Capture | Uncorrected | Each tray corrected by its own tag | All corrected by the median tray-tag factor | Median tray-tag area factor |
|---|---|---|---|---|
| 6.27, repeat | 0.18 | 0.46 | 0.23 | +0.16% |
| 6.17, a | 0.61 | 0.53 | 0.56 | -0.66% |
| 6.17, b | 0.67 | 0.72 | 0.69 | -0.95% |
| 6.37, a | 0.69 | 0.78 | 0.59 | +0.13% |
| 6.37, b | 0.56 | 0.66 | 0.27 | +0.41% |
| 6.27 again, a | 0.14 | 0.55 | 0.19 | -0.12% |
| 6.27 again, b | 0.12 | 0.65 | 0.13 | +0.07% |

Reading: **correction does not work with these tags.** Correcting each tray by its own tag made
the slots worse (0.18 to 0.46 even with nothing changed; South 3 was pushed off by about 1 to 2
points in every capture after the first), because a single 30 mm tag's size is too noisy for it.
One table-wide factor changed little, because a lens change does not move all trays the same way
(at 6.17 North 2 rose 1.0 point while North 4 fell 0.9). **Detection is one-sided:** the median
tray-tag factor moved -0.66% and -0.95% at 6.17 (repeat noise ±0.16%), but only +0.13% and
+0.41% at 6.37, while the calibration tags moved -0.6 to -0.8 points. One run.

**Run 3i method, written before it runs (2026-10-06, about 14:20 UTC): how far does an app
restart move the readings?** The remaining risk during an experiment is a restart or power cut,
after which the lens is driven back to the stored position but may land differently. Steps,
chamber closed and untouched, lens locked at 6.27: 2 reference captures; then 5 times: app
restart (server process killed and started again; at start-up it drives the lens to 6.27 the one
consistent way and restores the lock), 2 captures. For each capture, against the first reference
capture: median change of the calibration tags' area error (all, central slots North 3, North 4,
South 3, South 4, and the largest slot), tags found, and the median tray-tag area factor (11 tray
tags; tag 6 at the frame edge is not found). Raw data:
`/home/pi/scratch/lens-fix-check-2026-10-06/restart-test/`.

**Run 3i result** (14:20 to 14:21 UTC; 5 fresh server processes, each locked at 6.27 within about
3 s, no camera errors). Against the first reference capture, in points:

| Capture | Tags matched | All tags | Central slots | Largest slot | Tray-tag area factor |
|---|---|---|---|---|---|
| reference b | 337 | +0.00 | +0.01 | -0.15 (South 2) | -0.01% |
| restart 1 a / b | 339 / 339 | +0.05 / -0.02 | +0.09 / -0.01 | +0.18 / -0.23 | -0.08% / -0.38% |
| restart 2 a / b | 338 / 337 | -0.01 / +0.02 | +0.08 / +0.02 | -0.32 / -0.24 | -0.30% / -0.16% |
| restart 3 a / b | 340 / 340 | +0.02 / -0.03 | +0.08 / +0.05 | -0.38 / -0.22 | -0.12% / -0.40% |
| restart 4 a / b | 338 / 340 | +0.01 / +0.03 | +0.06 / +0.04 | +0.17 / -0.39 | -0.06% / -0.17% |
| restart 5 a / b | 337 / 338 | +0.01 / -0.02 | +0.02 / +0.04 | -0.30 / -0.21 | -0.08% / -0.14% |

Reading: **an app restart, with the camera warm, does not move the readings.** Across 5 restarts
the median stayed within ±0.05 points, the central slots within +0.09, and every slot within
±0.39, inside the change over time seen with nothing done (slots up to 0.52). This agrees with
the 2026-10-05 restart runs (+0.08, +0.09). The large changes of 2026-10-06 came with other
events: the cold start (-1.73, recovering over an hour), the camera frontend timeout at 12:37 UTC
followed by a restart (central slots about half as sharp), and the lens diagnosis with many full
sweeps (11:18). Which of those features (a cold camera, a stalled camera, many lens moves) causes
the shift is not separated; these tests show what is safe (restarts) and what is not (a cold
start, and a camera fault).

**Run 3j method, written before it runs (2026-10-06, about 19:10 UTC): do readings stay steady
over 2 hours of one photo a minute, when photos no longer reopen the camera or move the lens?**
Since commit `5f068bf` a photo switches the camera back to its preview setting and leaves the lens
alone; the camera is reopened only before a lens command (TODO.md, "Plan: nothing moves the lens
during an experiment", slice 1). This is the path every photo will take during an experiment,
unattended. Steps: chamber closed and untouched, calibration sheets on the trays as in run 3i,
lens locked at 6.27, server running `5f068bf` (restarted warm at 19:07 UTC). A script calls the
app's own `POST /capture` once a minute for 120 photos (2 hours) and records for each: UTC time,
capture duration, the lens position, exposure time and gain from the photo's record, and the focus
status. Comparison against the first photo, as in run 3i (`analyse.py` adapted): calibration tags
matched by ID and position (within 20 px), median change in area error for all tags, for the
central slots (North 3, North 4, South 3, South 4) and per slot; tags matched. Sharpness
(Laplacian variance, as the focus score) of a 500 px square at the centre of each slot box of the
2026-10-05 validation (`20261005T141310628479`), as a percentage of the first photo.
Judgement, fixed before any data: the photo path adds nothing detectable if every photo's all-tag
median stays within ±0.10 points and every slot within ±0.52 points of the first photo, the range
of Control B (45 minutes, nothing done), and no sharpness square falls by more than 20% (a decision,
not a measurement: the camera fault in run 3g halved the central sharpness). The reported lens
position is recorded but not judged: on this path a camera that ignores lens writes reports the
old position whatever happens, so it cannot show a change. Photos taken while focus is not locked
at 6.27 (someone unlocks it) are left out; a photo whose exposure time differs from the first by
more than a factor 2 (chamber lights changing) is flagged, and if the lights go off the run ends
there and is reported as shorter. Limits: there is no 2-hour control without photos, so a slow
drift could come from time and temperature, not from the photo path; this run can show the path
is safe, and a drift would not by itself show it is unsafe. One run, one lens position, chamber
lights on, warm camera; it does not cover a cold start or a camera fault. At the end the live
preview is checked for frames (on 2026-10-05 it stopped once after a calibration on this path).
Raw data: `/home/pi/scratch/lens-noreopen-2026-10-06/`.

**Run 3j result** (19:10:46 to 21:09:46 UTC; 120 of 120 photos, no errors, focus locked at 6.27 in
every photo, capture 2.66 to 2.94 s, live preview still streaming at the end). One change to the
method after the run started and before any result was looked at: auto exposure was off
(exposure time 3429 in every photo), so exposure time could not show the lights going out; the
mean brightness of each photo was used instead (below half the first photo's counts as dark).
Brightness stayed between 104.5 and 105.1, so the lights stayed on and no photo was left out.
Tags matched 328 to 337. Against the first photo, in points:

| Photos (10 a block) | Start (UTC) | All tags, median of block | All tags, range | Central slots, median | Largest slot | North 3 sharpness, median |
|---|---|---|---|---|---|---|
| 0 to 9 | 19:10 | +0.12 | -0.06 to +0.29 | +0.07 | 0.62 | +11% |
| 10 to 19 | 19:20 | +0.09 | -0.05 to +0.14 | +0.04 | 0.44 | +6% |
| 20 to 29 | 19:30 | +0.12 | -0.05 to +0.28 | +0.09 | 0.55 | +10% |
| 30 to 39 | 19:40 | +0.05 | -0.06 to +0.10 | +0.02 | 0.31 | +3% |
| 40 to 49 | 19:50 | +0.13 | -0.06 to +0.27 | +0.07 | 0.53 | +11% |
| 50 to 59 | 20:00 | +0.03 | -0.03 to +0.10 | +0.01 | 0.30 | +5% |
| 60 to 69 | 20:10 | +0.12 | +0.05 to +0.31 | +0.07 | 0.57 | +11% |
| 70 to 79 | 20:20 | +0.04 | -0.07 to +0.11 | +0.02 | 0.41 | +4% |
| 80 to 89 | 20:30 | +0.15 | +0.04 to +0.30 | +0.06 | 0.55 | +12% |
| 90 to 99 | 20:40 | +0.02 | -0.04 to +0.21 | +0.00 | 0.44 | +2% |
| 100 to 109 | 20:50 | +0.11 | +0.02 to +0.33 | +0.06 | 0.53 | +10% |
| 110 to 119 | 21:00 | +0.01 | -0.08 to +0.27 | +0.01 | 0.59 | +3% |

Judged against the limits fixed before the run: **not passed.** The all-tag median reached +0.33
(limit ±0.10) and the largest slot +0.62 (North 5; limit ±0.52). Sharpness passed: no square fell
by more than 5.2% (limit 20%).

What the excess is: **a repeating cycle of about 19 minutes**, not a drift. Six times in the 2
hours the all-tag median rose within 2 or 3 photos to about +0.25 to +0.33, then fell slowly over
about 16 minutes to about -0.05 (time shift with the highest correlation: 19 photos, 0.75). The
sharpness of the slot squares rose and fell with it (correlation 0.87 with the all-tag median;
North 3 up to +23%, South 3 up to +21%). The cycle did not grow: the peaks were +0.29 in the first
cycle and +0.27 in the last, the low points about -0.05 throughout, and the last 10 photos read
+0.01. The photo path does the same thing every minute, so it does not by itself explain a
19-minute cycle; the chamber's own log shows it goes with the chamber's temperature and humidity
cycle (see "Run 3j against the chamber's own record" below). The first photo fell near a low point of the
cycle, which is why the medians are mostly positive.

Reading: over 2 hours of unattended photos without reopening the camera, the readings did not
wander away; they returned to the same low point every cycle, and the lens did not lose
sharpness. But readings at a fixed lens position swing by about 0.35 points in the median and up
to about 0.6 points in a slot, with a period of about 19 minutes, more than the control range used
as the limit. The control (Control B, photos every 15 minutes) would not have shown a 19-minute
cycle as one. This is the same photo path the 2026-10-05 validation, the controls and the bands
were measured with: the camera was reopened per photo only from commit `a58e720` (2026-10-06,
11:20 UTC) until `5f068bf`, and that path was never run at one photo a minute. One run; whether the cycle is also there with the camera reopened per photo, at
other times of day, or with the chamber lights off was not measured.

**Run 3j against the chamber's own record, method written 2026-10-07 before the comparison.**
Does any chamber reading follow the 19-minute cycle? The chamber controller logs once a minute in
local time (Amsterdam, UTC+2): temperature, humidity and CO2 (set and actual), 9 light channels
and `Bath_H1` (export `/home/pi/scratch/D6_2026.09.07-2026.10.07.csv`, made 2026-10-07 about
10:00 local). The rows for run 3j's window (2026-10-06 21:10 to 23:10 local, 19:10 to 21:10 UTC)
are matched to each photo by the nearest minute after converting to UTC. For each chamber column:
its range in the window, the time shift (5 to 40 minutes) at which it best matches itself (its own
period), and its correlation with run 3j's all-tag median at shifts of -10 to +10 minutes (the
chamber may lead or lag the photos). A column is said to follow the cycle if its own period is 15
to 25 minutes and its best correlation with the all-tag median is above 0.5 in size (**decision**).
A column that does not change in the window is reported as constant. This only shows whether a
chamber reading moves with the cycle; it does not show that it causes it.

**Result** (149 chamber rows, 18:56 to 21:24 UTC; script and output
`/home/pi/scratch/lens-noreopen-2026-10-06/chamber_compare.py`, `chamber_compare.json`):

| Column | Range in the window | Own period | Best correlation with the all-tag median | Shift | Follows the cycle |
|---|---|---|---|---|---|
| T_Actual (air temperature) | 19.8 to 20.3 °C | 19 min (r 0.81) | +0.84 | chamber 1 min ahead | **yes** |
| RH_Actual (humidity) | 57 to 62% | 19 min (r 0.78) | -0.76 | chamber 1 min behind | **yes** |
| CO2_Actual | 430 to 460 ppm | 5 min | +0.29 | 0 | no |
| Bath_H1 | 0 to 100 | 37 min (r 0.20) | -0.22 | +4 min | no |
| T_Set, RH_Set, CO2_Set, all 9 light channels | constant (20 °C, 60%, 300 ppm; CoolWhite 25.02, others 0) | | | | constant |

Reading: **the 19-minute cycle in the readings goes with the chamber's own temperature and
humidity cycle.** When the air was warmer (by up to 0.5 °C) the areas read larger and the photos
were sharper; humidity moved the opposite way, as it does when air warms. The lights did not change.
This shows that the readings move with the chamber's climate cycle, not which part of it, or what
in the camera, causes the change. Since the chamber's cycle depends on the experiment and the air
handler (Aaron, 2026-10-07), the size and period of this swing may differ between experiments.

Raw data for runs 3 to 3c:
`/home/pi/scratch/lens-coldstart-2026-10-06/` (`log.txt`, `log3b.txt`, `watch3b.txt`, scripts).

Detailed results: `reference/lens-return-2026-10.md`.

### 8.2 Camera swap comparison (method written 2026-10-07, before any step runs)

**Why.** The Arducam used since the rebuild may have been damaged (Aaron, 2026-10-07): after a
full-res photo its lens stops following commands (section 8.1, run 3b and the diagnosis), a camera
fault on 2026-10-06 left the central trays about half as sharp, and the 2026-10-07 validation read
about 0.85 points lower than the 2026-10-05 one. A new camera of the same model is fitted and the
key tests are repeated, so each result can be compared with the old camera's. This compares the
two cameras; it does not look for causes.

**Before starting.** Record both cameras' serial numbers and the lens position the new camera is
locked at (the operator's choice). The old camera is kept untouched. Swapping means switching the
Pi off, so the first hour after power-on is a cold start (section 8, table): no step starts until
60 minutes after the Pi is switched on with the new camera. Same printed sheets (30.0 mm tags),
same trays and table, chamber door closed for every photograph, lights on. Raw data:
`/home/pi/scratch/camera-swap-2026-10/`.

**Steps and how each is judged** (limits fixed now; "different" means larger than the old camera
showed with nothing done):

| Step | What | Old camera | Judged |
|---|---|---|---|
| 0 | Swap, square, focus and lock (operator) | lens 6.27 | Recorded only |
| 1 | Calibrate with the wizard | tags found and fit as in section 5 | Recorded and compared; no pass or fail |
| 2 | Validate: 3 rounds, 10 minutes apart, door closed | 2026-10-07 validation above | Per slot: the band and median compared. A slot median differing by more than 0.62 points (the largest slot change with nothing done, run 3j) counts as different, but only if the lens position matches 6.27 within 0.01; otherwise the comparison is reported with the lens difference noted (the central error changes about 1.2 points per 0.1) |
| 3 | Photo-to-photo noise: 10 photos in a row, nothing touched | per-tag standard deviation 0.27 to 0.46 points | Different if the median per-tag standard deviation is outside 0.27 to 0.46 |
| 4 | Stuck lens: `reference/lens-unresponsive-2026-10-diagnose.py`, server stopped | after one photo, lens writes accepted and not followed; follows after a close and reopen | Follows or does not follow (yes or no); tells whether the fault belongs to the old camera or to the model |
| 5 | Restarts: 5 warm restarts, 2 photos each (as run 3i) | median within ±0.05 points, every slot within ±0.39 | Different if a median exceeds ±0.10 or a slot ±0.52 (Control B) |
| 6 | 2 hours unattended: one photo a minute (as run 3j) | a cycle of about 19 minutes, median swing about 0.35 points, largest slot 0.62 | Cycle present if the median's correlation with itself 15 to 25 photos later peaks above 0.5; swing and largest slot compared. Present again means it comes from the chamber, not the camera |

**Optional, only if Aaron asks for them:** a planned cold start (as run 3: Pi off about 30
minutes, photos at +0, +15, +30, +60 minutes), and the two-height test (section 9.1).

Each step's result is added here when it is done, with its date, times (UTC), session or capture
IDs and the raw data path.

**Step 0 result (2026-10-07, recorded only).** Old camera serial SN000 (kept untouched), new
camera serial SN001 (serials as given by Aaron). The Pi was switched on with the new camera at
11:20 UTC, so the cold start ended at 12:20 UTC. The server ran from the m2-camera-swap branch.
Aaron fitted, squared and focused the new camera and first locked it at 6.23. After the cold-start
data below, he unlocked, refocused and locked at **6.16** (between 11:59 and 12:22 UTC, server
log), and confirmed 6.16 as his chosen position for every remaining step. The old camera was at
6.27: a difference of 0.11, which at about 1.2 points of central error per 0.1 (step 2 above) is
about 1.3 points.

*Cold-start data, not used to judge any step:* a calibration made 25 minutes after power-on
(`20261007T114505498348`, 11:45 UTC, residual 0.50%, 30.0 mm tags, lens 6.23) and a validation
of it (session `20261007T114611264170`, rounds at 11:46 and 11:58 UTC). Both started inside the
first hour after power-on, so under the rule above they do not count; step 1 was repeated after
12:20 UTC.

**Step 1 result (2026-10-07, recorded and compared, no pass or fail).** Calibration
`20261007T122200583188`, 12:22 UTC (62 minutes after power-on), lens 6.16, focus locked, 30.0 mm
tags, 50 mm corner tags, table span 1494 x 1171 mm as entered. Calibration files:
`/var/lib/npec-rig/calibration/20261007T122200583188.json` and its `frames/` and `heatmaps/`.

| | Old camera SN000 (`20261005T141101923639`) | New camera SN001 (`20261007T122200583188`) |
|---|---|---|
| Calibration tags found | 355 | 355 |
| Corner tags found | 4 | 4 |
| Scale field residual | 0.52% | 0.49% |
| Holdout coverage error | 0.4% | 0.4% |
| Mean scale | 4.856 px/mm | 4.865 px/mm (+0.17%) |
| Lens position | 6.27 | 6.16 |

The new camera finds the same tags and the plane fits them as well as for the old camera. The
mean scale differs by 0.17%, which is expected when a camera is refitted and squared again; no
limit was set for it. The wizard also reported: scale varies 1% across the calibrated area, worst
top-left, 0.6% higher top-left than bottom-right; area-scale error 0.8% mean over 355 tags; shape
distortion 0.01% mean, worst tag 395 at -0.06%. The 11:45 cold-start calibration at lens 6.23 gave
4.864 px/mm and 0.50%, close to this one.

**Step 2 result (2026-10-07).** Validation session `20261007T122525038952` of calibration
`20261007T122200583188`, lens 6.16 locked, chamber door closed. Rounds at 12:26, 12:38 and
12:51 UTC (24.8 minutes first to last, shortest gap 11.8 minutes); 93%, 93% and 86% of tags
moved; 85 to 90 tags per slot. The rig's checks: validated, no problems, no flagged or
inconsistent slots; the largest move of a slot median between rounds 0.60 points (old camera
1.31). Raw data: `/home/pi/scratch/camera-swap-2026-10/step2/` (`validation_sessions.json`, all
sessions as the server reported them at 12:51 UTC, and `compare.py`, which makes the table below).

| Slot | Band, old | Band, new | Median, old | Median, new | Change |
|---|---|---|---|---|---|
| North 1 | ±3.3% | ±2.7% | -0.90 | +0.88 | +1.78 |
| North 2 | ±2.5% | ±1.7% | -0.80 | +0.51 | +1.31 |
| North 3 | ±2.9% | ±1.7% | -1.36 | -0.22 | +1.14 |
| North 4 | ±2.3% | ±2.1% | -0.25 | -0.38 | -0.13 |
| North 5 | ±2.4% | ±1.8% | -0.71 | -0.50 | +0.21 |
| North 6 | ±3.0% | ±1.9% | -0.91 | +0.33 | +1.24 |
| South 1 | ±2.8% | ±1.9% | -1.33 | -0.05 | +1.28 |
| South 2 | ±2.2% | ±1.3% | -0.76 | +0.22 | +0.98 |
| South 3 | ±1.5% | ±2.0% | -0.16 | -0.05 | +0.11 |
| South 4 | ±1.6% | ±2.5% | +0.11 | -0.58 | -0.69 |
| South 5 | ±3.1% | ±1.7% | -1.20 | -0.34 | +0.86 |
| South 6 | ±2.2% | ±1.9% | -0.37 | +0.64 | +1.01 |

*Against the limit fixed above.* The lens position (6.16) does not match the old camera's (6.27)
within 0.01; it differs by 0.11. So, as fixed beforehand, the 0.62-point limit is not applied and
no slot is called the same or different; the comparison is reported with the lens difference
noted (about 1.3 points of central error at 1.2 points per 0.1). For the record, 9 of 12 slot
medians changed by more than 0.62 points (from -0.69 to +1.78).

*What the comparison does show.* Bands: ±1.3% to ±2.7% on the new camera against ±1.5% to ±3.3%
on the old; 10 of 12 slots narrower, 2 wider (South 3, South 4). Median of the slot medians: -0.05
points against -0.78 (the old camera read +0.07 on 2026-10-05). This compares two cameras at two
lens positions; it does not say which of the two, if either, caused the change.

**Step 3 result (2026-10-07): different, lower.** 10 photos in a row through the app's
`POST /capture`, 12:57:31 to 12:57:58 UTC (2.7 to 2.8 s each), captures `2026-10-07/125733_446195`
to `2026-10-07/125758_010168`, nothing touched, chamber door closed, lens 6.16 locked in every
photo, exposure 3793 µs and gain 1.0 in every photo, calibration `20261007T122200583188`. Method:
each calibration tag matched by ID and position (within 20 px of the first photo); the standard
deviation (n-1) of its area error over the 10 photos; the median over tags. Raw data and scripts:
`/home/pi/scratch/camera-swap-2026-10/step3/` (`step3.py` took the photos, `analyse.py` makes
`results.json`).

| | Old camera SN000 | New camera SN001 |
|---|---|---|
| Median per-tag standard deviation | 0.27 to 0.46 points (2026-10-01; a different statistic, see the note below) | **0.15 points** |
| Tags followed through every photo | | 355 of 355 |
| Per-tag spread, middle half of tags | | 0.12 to 0.19 points |
| Largest tag | | 0.37 points |
| Per-slot medians | | 0.12 to 0.17 points |
| Whole-photo median error, photo to photo | | -0.09 to +0.00 points |

*Against the limit fixed above.* 0.15 is outside 0.27 to 0.46, so the new camera is different: its
photo-to-photo noise is about half the old camera's. One caution about the comparison itself: the
old figure came from the light-level test of 2026-10-01 (`reference/arducam-central-error-2026-10.md`,
test 6), with automatic exposure compensating three light levels, and its record does not give the
number of photos or how the standard deviation was summarised. Today's photos had fixed exposure.

*Note added 2026-10-08.* The old figure's method has since been found (section 8, first row): one
photo per light level, and 0.27 and 0.46 are standard deviations of the difference between two
photos, not of one photo, and each pair also differed in light level. For one photo that is at
most about 0.19 to 0.33 points. The new camera's 0.15 is still lower, but by less than half, and the two tests differ in exposure (automatic over three
light levels against fixed), so the size of the difference is not established.
So the difference may come partly from the conditions, not only from the camera. The limit was
applied as written, not changed.

**Step 4 result (2026-10-07): does not follow, as the old camera.** Server stopped 13:02 UTC,
`reference/lens-unresponsive-2026-10-diagnose.py` run with the camera-swap branch's code, one case
per process (a fresh camera each time), chamber door closed, lights on. Lens positions used: the
persisted 6.16 and 4.66 (1.5 below, chosen only for a large sharpness change). Each write watched
for 90 s: the position the camera reports, frames flowing, and the sharpness of the central third.
Raw data: `/home/pi/scratch/camera-swap-2026-10/step4/` (one `.csv` and `.json` per case).

| Case (UTC start) | Lens write | Reported position | Sharpness | Followed |
|---|---|---|---|---|
| No photo (13:03) | 6.16 to 4.66 | 4.66 in 0.58 s | 1067 to 19 | yes |
| | 4.66 to 6.16 | 6.16 in 0.57 s | 19 to 1103 | yes |
| After 1 full-res photo (13:07) | 6.16 to 4.66 | stayed 6.16 for 90 s | 1105 to 1104 | **no** |
| After 1 photo, camera closed and reopened (13:12) | 6.16 to 4.66 | 4.66 in 0.57 s | 1087 to 19 | yes |
| | 4.66 to 6.16 | 6.16 in 0.58 s | 19 to 1098 | yes |

Frames kept flowing in every case. The write after a photo was accepted without an error and not
followed, and the camera kept reporting the old position, exactly as the old camera did (section
8.1, run 3b and the diagnosis). A close and reopen cures it on both cameras. So the fault is not
peculiar to the old camera: it comes with this camera model or with the software shared by both
setups; this step does not separate those two. The app already works around it (photos do not move
the lens; the camera is reopened before any lens command, TODO "Plan: nothing moves the lens during
an experiment", slice 1). Every case ended with the lens driven back to 6.16. The server was
restarted at 13:18 UTC and reported focus locked at 6.16.

**Step 5 result (2026-10-07): same as the old camera.** As run 3i: 2 reference photos, then 5
times (warm app restart by killing the whole server process family, relaunch from the camera-swap
branch, wait until focus reports locked; 2 photos). 13:21:56 to 13:22:47 UTC, about 3.4 s per
restart (as in run 3i), lens 6.16 and locked after every restart and in every photo, chamber door
closed, calibration `20261007T122200583188`, slots from validation `20261007T122525038952`. Each
calibration tag compared with itself in the first reference photo (matched by ID and within
20 px). Raw data: `/home/pi/scratch/camera-swap-2026-10/step5/` (`step5.sh`, `log.txt`,
`photos.txt`, `analyse.py`, `results.json`).

| Photo | Tags | Median change | Central slots | Largest slot change |
|---|---|---|---|---|
| Reference b | 355 | -0.03 | -0.04 | North 5 -0.15 |
| Restart 1 a / b | 355 / 355 | +0.01 / -0.04 | +0.01 / -0.03 | South 4 -0.11 / North 5 -0.16 |
| Restart 2 a / b | 355 / 355 | +0.02 / -0.01 | +0.05 / +0.02 | North 3 +0.11 / North 6 -0.24 |
| Restart 3 a / b | 355 / 355 | +0.05 / -0.02 | +0.06 / +0.01 | North 3 +0.11 / North 5 -0.16 |
| Restart 4 a / b | 355 / 355 | +0.06 / +0.02 | +0.10 / +0.05 | South 5 +0.18 / North 3 +0.15 |
| Restart 5 a / b | 355 / 355 | +0.05 / -0.00 | +0.09 / +0.06 | North 3 +0.19 / South 5 +0.19 |

*Against the limits fixed above.* Median within -0.04 to +0.06 (limit ±0.10), every slot within
±0.24 (limit ±0.52): not different. The old camera gave a median within ±0.05 and every slot within
±0.39 (run 3i). A warm restart does not change the new camera's readings either.

**Extra check, asked for by Aaron (2026-10-07): is the central low reading there on the new
camera?** Not one of the steps above; no limit set, compared only. *Method (written before it
ran):* the same analysis as `reference/arducam-central-error-2026-10.md` section 4.1, on each
camera's 2026-10-07 validation. Every calibration tag in the 3 validation rounds, its area error
under that camera's own calibration (old: rounds `070505_471367`, `071439_917590`,
`072601_309111` with calibration `20261005T141101923639`; new: `122619_085413`, `123805_311325`,
`125109_812791` with `20261007T122200583188`), grouped by distance from the image centre (4576,
3472 px): median error per band, and the dip (median within 1500 px minus median beyond 2500 px,
as in that record's section 4.3, where the old camera gave about -2.6 points on 2026-10-01).
Saved data only; no photos. Raw data: `/home/pi/scratch/camera-swap-2026-10/centre-check/`.

*Result (run 13:27 UTC):*

| Distance from image centre (px) | Old camera SN000: tags, median error | New camera SN001: tags, median error |
|---|---|---|
| 0 to 1000 | 24, -2.42% | 10, -2.80% |
| 1000 to 1500 | 119, -0.88% | 123, -1.15% |
| 1500 to 2000 | 158, +0.17% | 173, -0.08% |
| 2000 to 2500 | 164, -0.07% | 138, +0.10% |
| 2500 to 3500 | 256, -1.11% | 271, +0.06% |
| 3500 to 4500 | 287, -0.77% | 332, +0.50% |
| 4500 and beyond | 29, -1.44% | 18, -0.55% |
| Dip (within 1500 minus beyond 2500) | -0.27 points | -1.50 points |

The central low reading is present on the new camera: tags within 1000 px of the image centre read
about 2.8% small and the reading returns to about zero beyond 1500 px, the same shape as on the old
camera. So it is not peculiar to the old camera, in line with its record (it belongs to the
Arducam). The old camera's dip on this day is only -0.27 because its outer bands also read low
(-0.77 to -1.44%), the whole-table shift of about -0.85 points noted in section 6; its innermost
band (-2.42%) is close to the new camera's. Cautions: the innermost band holds only 10 and 24
tags; the two cameras were at different lens positions (6.16 and 6.27), and the size of this
error follows the lens position. The North 4 slot median does not stand out on either camera
because only the slot's inner corner lies within 1500 px of the image centre; the per-slot band
from validation includes it.

**Packing foam found on the new camera (2026-10-07, during step 6).** Aaron found packing foam
left on the camera body over the lens, present for every photo since the swap (calibration,
validation, steps 2 to 5 and step 6 photos 0 to 12). He removed it with the door open 13:41 to
13:42 UTC (15:41 to 15:42 local), without touching the lens. Step 6 photos compared with photo 11
(13:40 UTC, the last before the door opened); raw data and script:
`/home/pi/scratch/camera-swap-2026-10/foam-check/` (`analyse.py`, `results.json`).

| Photo (UTC) | Exposure (µs) | Tags | Tag shift, median / largest (px) | Area change, median | Largest slot | North 4 sharpness |
|---|---|---|---|---|---|---|
| 0 (13:29) | 3793 | 355 | 0.97 / 1.64 | +0.19 | North 5 +0.46 | |
| 10 (13:39) | 3793 | 355 | 0.16 / 0.69 | +0.04 | North 5 +0.13 | |
| 13 (13:42, Aaron at the rig) | 3897 | 314 | 0.22 / 3.75 | -0.04 | | |
| 14 (13:43) | 3533 | 355 | 0.89 / 3.07 | -0.53 | North 5 -0.83 | -21.4% |
| 15 (13:44) | 3533 | 355 | 0.94 / 3.72 | -0.52 | North 5 -0.77 | -20.2% |
| 16 (13:45) | 3533 | 355 | 0.86 / 3.36 | -0.47 | North 1 -0.60 | -16.6% |
| 17 (13:46) | 3533 | 355 | 0.78 / 3.55 | -0.43 | North 3 -0.54 | -15.5% |

After the foam was removed, the camera's view moved by under 4 px, the exposure dropped by 7% (more
light reaching the sensor), the readings dropped by about 0.5 points (beyond the step 5 limits of
0.10 for the median and 0.52 for a slot) and the centre lost about a fifth of its sharpness; the
change was getting smaller each minute. Whether the readings return to their earlier level is not
known yet. Until that is known, the step 2 validation is not relied on.

*Later step 6 photos, same comparison (checked 16:30 UTC):*

| Photo (UTC) | Tag shift, median / largest (px) | Area change, median | Largest slot | Least sharp slot |
|---|---|---|---|---|
| 25 (13:54) | 0.94 / 3.19 | -0.62 | North 4 -0.81 | North 4 -25.6% |
| 35 (14:04) | 1.21 / 4.24 | -0.51 | North 4 -0.65 | North 4 -21.5% |
| 50 (14:19) | 1.05 / 3.63 | -0.85 | North 5 -1.17 | South 3 -39.2% |
| 70 (14:39) | 1.07 / 3.42 | -0.93 | North 4 -1.37 | South 3 -41.9% |
| 90 (14:59) | 0.96 / 3.51 | -0.85 | North 5 -1.13 | South 3 -40.0% |
| 105 (15:14) | 0.92 / 3.10 | -0.85 | North 4 -1.14 | South 3 -39.4% |
| 119 (15:28) | 0.91 / 2.86 | -0.69 | North 5 -0.92 | South 3 -31.3% |

The readings did not return within 1 hour 46 minutes. From about 14:19 UTC they settled about 0.7
to 0.9 points below their level before the foam was removed, with single slots up to 1.37 points
below, and the central slots about a third to two fifths less sharp. This is larger than every
change measured with nothing done on either camera (section 8, table). The calibration and the
step 2 validation therefore describe the camera as it was with the foam on, not as it is now. The
overnight run shows whether this changes further. Steps 1 to 5 and the
centre check were all taken with the foam in place; they compare the cameras as they were set up,
foam included. Step 6 is affected from photo 13: its photos 0 to 12 are 13 minutes only, and from
photo 14 on it includes the recovery, so it is reported with that noted.

**Overnight run (method written 2026-10-07 13:50 UTC, before it starts; agreed by Aaron).** Not
one of the steps above; recorded only, no limit. Purpose: does the reading return to its level
before the foam was removed, and does it drift over about 15 hours with nobody at the chamber.
Same script as run 3j (`/home/pi/scratch/camera-swap-2026-10/overnight/overnight.py`), started
automatically when step 6 ends (about 15:29 UTC), 916 photos, one a minute, to about 06:45 UTC on
2026-10-08 (08:45 local). Door closed, lights on (Aaron), lens 6.16 locked. Analysed as step 6:
each tag against itself in a reference photo, median and per-slot change, sharpness per slot;
reported against both step 6 photo 11 (before the foam came off) and the first overnight photo.
Raw data: `/home/pi/scratch/camera-swap-2026-10/overnight/`.
*Start as run:* the automatic start failed (the launcher waited for step 6 by looking for its name
among running processes, and a second waiter of Claude's own carried the same name, so it never
saw step 6 end). Started by hand at 16:26 UTC on Aaron's request, 858 photos to about 06:44 UTC.
No photos were taken from 15:28 to 16:26 UTC (58 minutes).

**Step 6, extra analysis of photos 14 to 119 (method written 2026-10-08 before it ran; agreed by
Aaron; information only, the as-written result stands).** The same analysis and chamber comparison
as step 6, on photos 14 to 119 only (after the foam came off), each tag against itself in photo 14
(`2026-10-07/134311_803312`). Reason: the foam step at photo 13 dominates the as-written series and
could hide a cycle of the old camera's size (0.35 points).

**Step 6 result (2026-10-07, 13:29 to 15:28 UTC, analysed 2026-10-08).** 120 photos, one a minute,
through `POST /capture` (`step6.py`, a copy of run 3j's script), no errors, lens 6.16 locked in
every photo, chamber door closed except 13:41 to 13:42 UTC (foam removal, above). Calibration
`20261007T122200583188`. Chamber record: Aaron's export
`/home/pi/scratch/Aaron-D6-2026.09.08-2026.10.08.csv` (1-minute rows, local time). Raw data and
scripts: `/home/pi/scratch/camera-swap-2026-10/step6/` and the shared `series_analyse.py` and
`chamber_compare.py` in `/home/pi/scratch/camera-swap-2026-10/` (adapted from run 3j's
`analyse.py` and `chamber_compare.py`).

| | Old camera, run 3j | New camera, as written (photos 0 to 119, against photo 0) | New camera, extra (photos 14 to 119, against photo 14) |
|---|---|---|---|
| Median's correlation with itself 15 to 25 photos later, peak | above 0.5, period about 19 | **0.20** (17 photos) | **0.67** (19 to 20 photos) |
| Median swing | about 0.35 points | 1.15 points | 0.57 points |
| Largest slot change | 0.62 | 1.85 (North 5) | 0.74 (North 5) |
| Least sharp slot | no loss | -53% | -31% |
| Chamber air temperature | 19.8 to 20.3 °C, period 19 min, r +0.84 | 19.7 to 20.3 °C, period 19 min, r -0.26 | 19.7 to 20.3 °C, period 19 min, r -0.59 (chamber 5 min ahead) |
| Chamber humidity | 57 to 62%, period 19 min, r -0.76 | 57 to 62%, period 19 min, r +0.33 | 57 to 62%, period 19 min, r -0.73 |

*Against the rule fixed above, as written:* the peak correlation is 0.20, under 0.5, so the cycle
counts as **not present**. This is the official step 6 result. The swing and the largest slot are
dominated by the foam removal and the settling after it, so they do not compare the cameras.

*Extra analysis (information only):* without the foam step, the cycle is there on the new camera:
peak correlation 0.67 at 19 to 20 photos, and the readings follow the chamber's 19-minute
humidity cycle (r -0.73, the same as the old camera's -0.76) and its temperature cycle (r -0.59;
the old camera's was +0.84, opposite in sign). The swing (0.57) still includes some settling after
the foam came off. In the terms of 8.2, a cycle present on both cameras comes from the chamber, not
the camera; this rests on the extra analysis, not on the as-written result. The opposite sign
against temperature is recorded, not explained. The chamber ran the same climate cycle on both
days (19.7 to 20.3 °C, 57 to 62%).

**Overnight run result (2026-10-07 16:26 to 23:14 UTC, analysed 2026-10-08).** 858 photos taken to
06:43 UTC, no errors, lens 6.16 locked in every photo. The chamber lights went off at photo 409
(23:15 UTC; exposure jumped from 3533 to about 66000 µs), so the run is analysed to photo 408:
409 photos, 6.8 hours. Every tag compared with itself in step 6 photo 11 (13:40 UTC, the last
photo before the foam came off). Same scripts as step 6; raw data:
`/home/pi/scratch/camera-swap-2026-10/overnight/` (`analysis_vs_before_foam.json`,
`chamber_compare.json`).

| Hour from (UTC) | Median change, hour median | Lowest / highest photo | Sharpness, median slot |
|---|---|---|---|
| 16:26 | -0.84 | -1.04 / -0.58 | -15.8% |
| 17:26 | -0.78 | -1.01 / -0.55 | -15.0% |
| 18:26 | -0.80 | -1.04 / -0.49 | -15.2% |
| 19:26 | -0.80 | -1.08 / -0.48 | -15.4% |
| 20:26 | -0.78 | -1.04 / -0.54 | -15.2% |
| 21:26 | -0.78 | -1.02 / -0.46 | -15.4% |
| 22:26 | -0.80 | -1.04 / -0.60 | -16.2% |

Largest slot change -1.57 points (North 5); largest swing of one slot 1.06 points. The median's
correlation with itself peaks at 0.83 at 20 photos. Against the chamber record over the same
window: air temperature 19.7 to 20.4 °C, period 20 min, r +0.61 (chamber 2 min behind); humidity
56 to 62%, period 20 min, r -0.86. Light level (CoolWhite) changed from 25.02 to 13 within the
window with no effect on the readings (r +0.04).

What it shows: (1) the readings did not return to their level before the foam came off: they sat
about 0.8 points lower, and the slots about 15% less sharp, for the whole 6.8 hours; so the foam's
removal changed the camera's readings lastingly, and the calibration of 2026-10-07 12:22 UTC and
its validation no longer describe the camera. (2) With nothing done for 6.8 hours, there was no
drift: each hour's median lay within 0.06 points of the others. (3) The 20-minute cycle is present,
swinging about 0.5 to 0.6 points, and follows the chamber's humidity and temperature cycle with the
same signs as the old camera's (humidity negative, temperature positive); the opposite temperature
sign in step 6's extra analysis came during the settling after the foam came off. Present on both
cameras, the cycle comes from the chamber, not the camera.

**Recalibration after the foam came off (2026-10-08).** Before it, Aaron moved the trays slightly,
moved the tray tags to inside each tray's boundary, and refocused: the lens was locked at **6.04**
(the operator's choice) when the calibration ran. Calibration `20261008T081832283098`, 08:18 UTC,
30.0 mm tags, 50 mm corner tags. Validation session `20261008T081846523784`, rounds at 08:20, 08:32
and 08:43 UTC (23.6 minutes first to last, shortest gap 11.8 minutes), 87%, 77% and 74% of tags
moved, 85 to 90 tags per slot, chamber door closed. Raw data: `/home/pi/scratch/camera-swap-2026-10/recal/`
(`validation_sessions.json` as the server reported it, `compare.py`).

| | With foam (step 1 and 2, lens 6.16) | Foam removed (lens 6.04) |
|---|---|---|
| Calibration tags | 355 | 355 |
| Scale field residual | 0.49% | 0.50% |
| Mean scale | 4.865 px/mm | 4.858 px/mm (-0.14%) |
| Validation | validated, no flags | validated, no flags |
| Largest move of a slot median between rounds | 0.60 | 0.76 |
| Bands | ±1.3% to ±2.7% | ±1.3% to ±2.7% |
| Median of the slot medians | -0.05 | -0.14 |

| Slot | Band, foam | Band, no foam | Median, foam | Median, no foam | Change |
|---|---|---|---|---|---|
| North 1 | ±2.7% | ±2.3% | +0.88 | +0.83 | -0.06 |
| North 2 | ±1.7% | ±2.5% | +0.51 | +0.26 | -0.25 |
| North 3 | ±1.7% | ±2.0% | -0.22 | -0.45 | -0.24 |
| North 4 | ±2.1% | ±2.5% | -0.38 | -0.43 | -0.04 |
| North 5 | ±1.8% | ±1.5% | -0.50 | -0.68 | -0.18 |
| North 6 | ±1.9% | ±1.6% | +0.33 | +0.17 | -0.15 |
| South 1 | ±1.9% | ±1.4% | -0.05 | -0.36 | -0.31 |
| South 2 | ±1.3% | ±1.4% | +0.22 | +0.34 | +0.12 |
| South 3 | ±2.0% | ±2.1% | -0.05 | -0.13 | -0.07 |
| South 4 | ±2.5% | ±2.7% | -0.58 | -0.86 | -0.28 |
| South 5 | ±1.7% | ±1.3% | -0.34 | -0.16 | +0.18 |
| South 6 | ±1.9% | ±2.4% | +0.64 | +0.77 | +0.13 |

The lens differs (6.04 against 6.16) and the trays and tray tags were moved, so by the step 2 rule
no slot is called the same or different. For the record, every slot median changed by less than
0.62 points (from -0.31 to +0.18). Compared with the 2026-10-07 calibration as it read after the
foam came off (about 0.8 points low, overnight run), a fresh calibration brings the camera back to
a validation as close to zero as before. This calibration and validation are the current ones for
the new camera and replace those of 2026-10-07.

## 9. M2 physical acceptance tests (2026-10-05)

The four tests PLAN.md lists for M2, run in the chamber on 2026-10-05 (times UTC; the chamber is
UTC+2). The two-baseline test was run earlier (2026-09-25, section 8 table).

| Test | Pass criterion | Result |
|---|---|---|
| 9.1 Two heights | Scale field shapes at two heights agree within the residual | **Pass**: largest difference 0.16%, residuals 0.52% and 1.10% |
| 9.2 Tape measure | App agrees with a tape within 2% | **Pass**: +1.6% to +1.7% (tag to tag), about +1.4% (tape in the photo, after height correction); both read long |
| 9.3 Roll and knock | Roll read correctly; a hard knock gives FAIL | **Pass**: -3.01 deg read against about -3.0 to -3.1 deg measured; knock gave FAIL |
| 9.4 Claimed against actual error | The calibration's claimed uncertainty matches the measured error | **Fail for the claim, which is removed**; no corner pattern |

### 9.1 Two-height test

**Question.** Does the shape of the scale field (how scale changes across the image) stay the same
at a different height, so one paper calibration covers every tray height?

**Method.** Two calibrations, same camera position, 30.0 mm tags, 355 tags and 4 corner tags each:

| Run | Sheets on | File | Lens | Centre scale | Residual |
|---|---|---|---|---|---|
| A | the table surface | `20261005T140433441775` (14:04), not made current | 6.07 | 4.522 px/mm | 1.10% |
| B | trays at experiment height | `20261005T141101923639` (14:11), current | 6.27 | 4.852 px/mm | 0.52% |

For each run, the scale at each corner of the calibrated area (pixels (1000, 1000), (8150, 1000),
(1000, 5950), (8150, 5950)) is divided by the same run's scale at the image centre (4576, 3472).
This removes the overall change of scale with height and leaves the shape.

| Position | Table | Trays | Difference (points) |
|---|---|---|---|
| Top-left | -1.15% | -1.16% | +0.01 |
| Top-right | -0.82% | -0.66% | -0.15 |
| Bottom-left | +0.83% | +0.67% | +0.16 |
| Bottom-right | +1.18% | +1.19% | -0.01 |

**Result.** The shapes agree within 0.16 points, below both runs' residuals. One paper calibration
covers every tray height: a new tray height needs no new paper calibration for its shape. The
residual on the table (1.10%) is twice that on the trays, possibly because sheets lie less flat on
the table surface; it makes this test less strict, not more.

**Covers.** Table surface to tray top (about 100 mm, derived from the centre scale change, 15.1% in
area, and 0.145% of area per mm, not taped). Lens moved between runs (6.07 and 6.27), as in a real change of height.

### 9.2 Tape-measure check

**Question.** The scale rests on the tag size typed in (30.0 mm). If that were wrong, every reading
would be wrong by the same proportion, and validation would not notice, because it checks against
the same number. A tape measure is an independent instrument.

**Instrument.** Steel tape, 1 mm divisions. It reads 180 mm on a sheet's 180 mm scale bar
(callipers 179.93 and 180.03 mm), so it shows no fixed offset and no 1.6% scale error over that
length.

**Method A, tag to tag.** Tape from the western (outer) edge of a tag on the South 1 sheet to the
eastern (outer) edge of a tag on the South 6 sheet, on the tray tops. The app's distance is
computed from the tags' detected corners and the current scale field, integrated along the line.
Tag numbers repeat across sheets, so the tag is identified by position as well as number.

| Tags | Photo | Tape | App | App reads long by |
|---|---|---|---|---|
| 355 (S1) to 329 (S6) | 12:59:40 | 1720 to 1721 mm | 1750.1 mm | 1.7% |
| 380 (S1) to 354 (S6) | 13:07:52 | 1713 mm | 1741.0 mm | 1.6% |

**Method B, tape in the photo** (13:12:53). The tape lay along the north edge of the South trays,
zero at the edge of South 1, and was photographed. The app's distance between the centres of the
red 10 cm boxes printed on the tape (found by colour, about 5 px per mm) was computed with the
scale field:

| Span | Tape | App | App reads long by |
|---|---|---|---|
| 10 to 180 cm | 1700 mm | 1736.7 mm | 2.16% |
| 20 to 170 cm | 1500 mm | 1531.3 mm | 2.09% |
| 30 to 160 cm | 1300 mm | 1325.0 mm | 1.92% |

Near the frame centre, Aaron measured 4.8504 px/mm along the tape in ImageJ; the app's field
gives 4.844 px/mm there (0.1%). Toward both ends of the row the app reads the tape about 3% long
(10 to 50 cm: 2.99%; 140 to 180 cm: 2.92%).

**Height correction.** The tape lay on the tray lips, about 10 mm above the sheets. The height
effect, 0.145% per mm (section 4, derived from the camera height and checked by one test), is for
area; for a length it is half, about 0.072% per mm. 10 mm is
therefore about +0.72% in length, so the full 1700 mm span corrected is about +1.4% (about ±0.15%
for "about 10 mm"; 20 to 170 cm about +1.4%, 30 to 160 cm about +1.2%). Method A needs no
correction: the tags lie on the sheets.

**Result.** Pass against 2% by both methods, which agree within about 0.3 points: over about
1700 mm the app reads distances 1.4% to 1.7% long. The pattern along the tape (centre about -0.6%
after correction, ends about +2.2%) fits the known central error (section 7). **Open point:** in
the same photos the tags at the ends of the row read 29.4 to 30.1 mm, slightly small or correct,
while distances spanning the row read long. The reason is not known.

*Correction, 2026-10-05:* a first version of this section applied the area figure (0.145% per mm)
to lengths, which gave +0.7% and a false 1% disagreement between the two methods. Found in review.

**Covers.** Left to right along the South row only, about 1700 mm, at tray-top height. Not front to
back. Not the North row.

### 9.3 Roll and knock (tripwire)

**Question.** After calibration, the app compares the 4 corner tags in each photo with the
calibration's (the tripwire). Does it read a camera roll correctly, and does a knock give FAIL?

**Limits** (code, marked provisional): roll DRIFT at 1 deg, FAIL at 10 deg; corner scale DRIFT at
3%, FAIL at 8%; any corner tag missing gives FAIL.

**Independent reference.** The table's aluminium rails, fixed to the chamber. The angle of a rail
edge is fitted with a straight line over x = 1500 to 7600 px (RANSAC, about 1000 edge points),
standard error 0.003 to 0.004 deg per photo. A camera that tips as well as rolls makes lines
above and below the image centre lean in opposite directions, so the top and bottom rails are
both measured and their change interpolated to the image centre.

| Step | App (Check tripwire now) | Photo |
|---|---|---|
| Baseline | OK, roll 0.00 deg | 13:31:08 |
| Knock on the camera mount | FAIL: corner tag 452 missing (pushed to the bottom edge of the frame) | 13:32:54 |
| Camera re-framed by hand | DRIFT: rolled 3.0 deg counterclockwise, near corner tag 455 7% closer (roll -3.01 deg) | 13:35:04 |

| Rail | Before | After | Change |
|---|---|---|---|
| Top (image y about 1100 to 1330) | +0.27 deg | -4.02 deg | -4.28 deg |
| Bottom (image y about 5940 to 6160) | -0.37 deg | -2.05 deg | -1.68 deg |
| Interpolated to the image centre | | | about -3.0 to -3.1 deg |

**Result.** Pass. The app's roll (-3.01 deg) agrees with the rails within 0.06 deg (criterion
0.2 deg, set for this test). The knock gave FAIL, through the lost corner tag; the roll and scale
FAIL limits were not reached by this knock.

**Observation, not acted on.** Each rail edge bends about 0.5 deg between its left and right halves,
in both photos: straight lines near the top and bottom of the frame are slightly curved.

**Covers.** One roll of about 3 deg, not 5 deg. The camera can only be nudged by hand, with no
measure of its own, which is why the rails are the reference.

### 9.4 Claimed uncertainty against actual error (honesty plot)

**Question.** The calibration claims an uncertainty at each position: the spread of the 5 nearest
tags about the fitted field. Is that claim honest, that is, does it match the error actually
found on targets it was not fitted to? And is the error worse toward the corners (the evidence
gate for a lens distortion model, section 10)?

**Method.** Instead of 6 positions, all 12 slots, using validation session `20261005T071549445423`
(calibration of 07:11 UTC; 3 counted rounds of moved tags, 85 to 90 tags per slot). Three further
photographs in that session (07:35, 07:49, 08:05) were a lens-drift check with nothing moved and
were not counted. Claimed: the calibration's local uncertainty at the slot centre, a length
percentage. Actual: root mean square of the slot's area errors, halved to give a length
percentage (area error is about twice length error).

| Slot | Claimed | Actual | Slot | Claimed | Actual |
|---|---|---|---|---|---|
| North 1 | 0.36% | 0.52% | South 1 | 0.49% | 0.49% |
| North 2 | 0.56% | 0.55% | South 2 | 0.58% | 0.43% |
| North 3 | 0.52% | 0.66% | South 3 | 0.42% | 0.63% |
| North 4 | 0.50% | 0.84% | South 4 | 0.78% | 0.64% |
| North 5 | 0.31% | 0.38% | South 5 | 0.28% | 0.41% |
| North 6 | 0.32% | 0.61% | South 6 | 0.50% | 0.46% |

**Result.** The claim is lower than the actual error in 7 of 12 slots, about equal in 1, higher in
4; the median slot's actual error is 1.25 times its claim, the worst 1.9 times (North 6). The
claim is overconfident because it is judged against the same tags it was fitted to. **Decision
(Aaron, 2026-10-05):** remove the claimed uncertainty, the confidence heatmap and the honesty-plot
panel from what the operator sees. The validation band is the uncertainty.

**Corners.** The 4 outer corner slots average 0.52% actual error, the 4 central slots 0.69%. The
error is not worse toward the corners; the central excess is the known central error (section 7).
The lens distortion gate stays closed. The trays do not reach the extreme frame corners; plants
only sit on trays.

## 10. Techniques deliberately not used, and what would justify them

| Technique | Adopt when | Evidence so far |
|---|---|---|
| Lens distortion model (intrinsic calibration) | Errors are structured, worse toward the corners, not random | Radial fit R² 0.33 to 0.45 on repeat runs (2026-09-22). 2026-10-05: validation errors are not worse at the corner slots (section 9.4), so the gate stays closed. Rail edges near the frame top and bottom bend about 0.5 deg (section 9.3), noted only |
| Correction for height above the plane | A measured depth source exists | None |
| Orthophoto, second camera | A second viewpoint exists, and in-plane accuracy proves insufficient | Canon used once, as a check only |
| Learned tray identification | Tag identity measurably fails often enough to matter | Not measured |

## 11. Not yet measured, and open inconsistencies

**Not yet measured:** whether driving the lens to both ends of its range before focusing changes
sharpness (run 3b could not test it, section 8.1). The M2 acceptance tests are
done (section 9).

**Open points from the acceptance tests:**

1. Tape check: distances across the South row read 1.4% to 1.7% long by both methods, while the
   tags at its ends read 29.4 to 30.1 mm (section 9.2). Not explained.
2. Tripwire: a knock gave FAIL only through a lost corner tag; the roll (10 deg) and scale (8%)
   FAIL limits are still provisional (section 9.3).
3. Lens control stops responding after a full-res capture (calibration, capture or tripwire
   check) until the app is restarted. Seen twice on 2026-10-05. Lens commands return success while
   the lens does not move. A measurement-relevant risk: the lens position recorded with a capture
   may not be the actual one. Tracked as a bug, not a measurement. Since 2026-10-06 photos do not
   move the lens and the camera is reopened before any lens command. The replacement camera shows
   the same fault (2026-10-07, section 8.2, step 4), so it is not peculiar to one unit.

**Inconsistencies found between project files, to be checked and resolved:**

1. Median-movement limit: 1.5 points in TODO.md, 2.5 in the code.
2. *Resolved 2026-10-08.* Calliper tolerance: "within 0.5 mm" (TODO.md, 2026-09-27) described a
   frame covered with tags, not a calliper tolerance; ±0.1 mm stands. Calliper date: the readings
   were made on or before 2026-09-21; 2026-09-29 is when they were given again (section 3).
3. Camera height: about 1482 mm, measured by Aaron with a tape measure on 2026-10-01 without
   touching the camera (section 4); the "not yet measured" note was written earlier the same
   morning. *Still open:* it is a best estimate, not a precise value, with no stated uncertainty,
   and it has not been re-measured since the camera swap.
4. Tray height: about 100 mm in some notes, a survey of 50 to 56 mm in another (the reference
   point of the survey is not stated). The 2026-10-05 two-height test implies about 100 mm from
   table surface to tray top (derived from scale, not taped), matching the 100 mm notes.
   *Resolved 2026-10-09:* the 4x5 tray's growing medium is 100 mm above the table (callipers) and
   its lip 5 mm higher (105 mm by tape, section 3). The 100 mm notes and the two-height test refer
   to the growing medium. For the other trays the top edge is the growing medium (Aaron, same day).
5. *Resolved 2026-10-08.* Central error size: "up to about 4%" (CLAUDE.md) is the ring 1000 to
   1500 px (-3.63 points at 6.10, the lowest lens position tested); -5.27 is the ring 0 to 1000 px,
   which holds only 5 tags (section 7).
6. Image width: 9152 px (configuration) and 9248 px (hardware probe, sensor size).

## 12. Terms

- **Area error:** (area read − true area) / true area, in percent.
- **Point:** a difference between two percentages (1.00% to 1.03% is 0.03 points).
- **Median:** the middle value when sorted; not pulled by a few odd values.
- **Standard deviation (SD):** how far values typically sit from the middle. About 2 in 3 values
  lie within one SD, about 19 in 20 within two.
- **95th percentile, band:** the distance from the true value that 95% of tags fall within.
- **Lens position:** the focus setting reported by the camera (dioptres).
- **Root mean square (RMS):** the square root of the average squared error; a typical size of the
  error, sign ignored. About 2 in 3 values lie within it.
- **Roll:** rotation of the camera about its viewing direction, seen as the whole image turning.
- **Tripwire:** the check of the 4 corner tags against the calibration, giving OK, DRIFT or FAIL.

## 13. Which results cover the current camera (SN001)

The camera was replaced on 2026-10-07 (section 8.2). Most tests were run on the old camera SN000.
This table says, for each result, whether it has been repeated on SN001.

| Result | Section | SN000 | SN001 |
|---|---|---|---|
| Tag and sheet sizes | 3 | | Property of the printed sheets, not of the camera; applies |
| Camera height, about 1482 mm | 4 | Tape-measure best estimate, not precise | Not re-measured |
| Height effect, 0.145% per mm | 4 | One test, 3 slots | Not repeated. Depends on camera height, not on the camera unit |
| Calibration residual | 5 | 8 calibrations, 0.516% to 0.700% | 3 calibrations, 0.491% to 0.503% |
| Validation bands | 6 | 3 sessions | 8 sessions; repeat on another day passes (14.1); current bands from 2026-10-14, lens 6.05 (14.6) |
| Validation checks and their limits | 6 | Limits set from SN000 sessions | Both SN001 validations passed with no flags; limits not re-derived |
| Central error against lens position | 7 | Sweep, 5 positions, one photo each | Checked once at lens 6.16 with foam on; not against lens position |
| Photo-to-photo noise | 8, 8.2 step 3 | 3 photos at 3 light levels | 10 photos, fixed exposure, foam on |
| Lens moved and driven back | 8 | One run | Not repeated |
| Control (nothing done, 45 to 60 min) | 8 | Two series | Covered by the 6.8 hour overnight run |
| App restart | 8, 8.2 step 5 | 2 attempts, then 5 restarts | 5 restarts, foam on |
| Power cut, cold start | 8 | One run | One run, 14.3: recovered by +15 min |
| One photo a minute, the chamber cycle | 8.1 run 3j, 8.2 | 2 hours | 2 hours (step 6) and 6.8 hours (overnight) |
| Lens ignores commands after a full-resolution photo | 11 | Seen twice | Seen (step 4) |
| Two-height test | 9.1 | Pass | Pass, 14.4 |
| Tape-measure check | 9.2 | Pass | Pass, 14.2 |
| Roll and knock | 9.3 | Pass | Pass (signed off): roll within 0.03 deg; knocks read DRIFT; covered corner tag gave FAIL, 14.5 |
| Claimed uncertainty against actual error | 9.4 | Fail; the claim was removed | Not repeated (the claim is no longer shown) |

Removing packing foam from SN001 changed its readings by about 0.8 points (section 8.2), so the
SN001 results taken with the foam on (noise, restarts, the step 2 validation) describe the camera
before that change. The current calibration and bands were made after it.

## 14. M2 acceptance tests on the current camera SN001 (method written 2026-10-09, before any test runs)

**Status:** method agreed with Aaron, 2026-10-09. No test in this section has run yet.

**Why.** The section 9 tests ran on the old camera SN000. Section 13 lists them as not repeated on
SN001, so M2 cannot close on them. PLAN.md's M2 *You verify* also asks for a repeat validation on
another day (added 2026-10-09). This section repeats each section 9 method unchanged, so each
result compares directly with the old camera's.

**Order.** Each test is run before the tests that disturb what it measures:

| Step | Test | Disturbs |
|---|---|---|
| 1 | 14.1 Repeat validation | Nothing |
| 2 | 14.2 Tape measure | Nothing |
| 3 | 14.3 Two calibrations with a cold start between | The whole rig (switched off and on) |
| 4 | 14.4 Two heights | The lens, the sheets |
| 5 | 14.5 Roll and knock | The camera |
| 6 | 14.6 Closing calibration and validation | Leaves the rig with current bands |

**Common conditions.** Camera SN001. Lens wherever Aaron focuses it; the value is recorded, never
chosen by the rig. Same printed sheets (30.0 mm tags), trays and table; chamber door closed for
every photograph; lights on. No step starts within 60 minutes of the Pi being switched on (cold
start, section 8). Camera faults are listed from `camera_events` in `rig.db` for the whole test
period. Raw data and scripts: `/home/pi/scratch/m2-acceptance-2026-10/`.

### 14.1 Repeat validation

**Question.** A slot's band is measured in one validation session. Does it still describe the
same calibration on another day?

**Method.** Two complete validation sessions (section 6 rules: 3 counted rounds, at least 20
minutes first to last, at least 10 minutes apart) of the same calibration, on different days.
Between them: no recalibration, no lens move, no cold start, no camera fault. The trays stay in
their slots; the small nudges from moving the sheets are part of every validation and so part of
this test. The first session's bands are the reference; the second session's tag errors are
checked against them.

**Which first session (decision, Aaron 2026-10-09).** A fresh validation on a day with no camera
fault, repeated on a later day. Not the newest complete session, `20261009T073553378279`
(calibration `20261009T073108292325`, lens 6.04, rounds at 07:37, 07:48 and 07:58 UTC, 21.2
minutes, 78% to 83% of tags moved, 85 to 90 tags per slot): that calibration and validation were
run to check interface changes, with nothing physical changed (Aaron), and two camera faults
followed the same day (`capture_full_res` did not finish within 30 s, 08:29 and 09:25 UTC, each
followed by an automatic restart, lens 6.04).

**Pass rule (decision, Aaron 2026-10-09).** At least 90% of all the second session's tags fall
inside their slot's first-session band, and no slot below 75%. Reported in full whatever the
outcome: each slot's fraction inside, and each slot's change in band and median. If it fails, the
bands drift between days by more than they show, and how to include that drift becomes its own
task. Weak point: the basis below is from the old camera, and the conditions between some of its
sessions were not recorded. Why 90% and not 95%: each band is itself estimated from about 90 tags,
so a new session is expected to fall somewhat short of 95% even when the band is right. Basis, measured on the old camera SN000 (pairs of
consecutive complete sessions of the same calibration, read from the stored session files; the
conditions between sessions are not all recorded):

| First session | Second session | Whole table inside | Lowest slot |
|---|---|---|---|
| 2026-09-30 10:02 | 10:11 | 94.1% | 89% |
| 2026-09-30 10:11 | 11:35 | 94.1% | 78% |
| 2026-09-30 11:35 | 14:21 | 84.4% | 56% |
| 2026-09-30 14:21 | 2026-10-01 08:11 | 95.2% | 89% |
| 2026-10-01 08:11 | 08:14 | 86.6% | 59% |
| 2026-10-01 08:14 | 08:20 | 94.0% | 83% |
| 2026-10-01 08:20 | 08:54 | 95.5% | 87% |
| 2026-10-05 14:13 | 2026-10-07 07:04 (cold start, fault and lens tests between) | 89.4% | 76% |

The 2026-09-30 and 10-01 sessions predate the 20-minute rule. Under this rule 5 of the 8
pass. A rule per slot (at least 90% in at least 11 of 12 slots) would fail 6 of the 8, including
two sessions 3 and 6 minutes apart, so it is not proposed.

**First session, done 2026-10-12.** Pi on since 2026-10-07 (no cold start); app restarted at
06:54 UTC, before the session (a warm restart, section 8); no camera events on 2026-10-12. Lens
locked at 5.97 at 07:05 UTC, a focus point Aaron chose deliberately slightly different from the
previous one (6.04); the images stayed sharp. Calibration `20261012T070607812512` (07:06 UTC, made
current, 30.0 mm tags, all 4 corner tags, residual 0.66%: higher than SN001's previous four,
0.49% to 0.54%, inside SN000's 0.52% to 0.70%). Validation session `20261012T070703613469`: rounds
at 07:08, 07:18 and 07:29 UTC, 21.0 minutes first to last, shortest gap 10.1 minutes, door closed;
93.5%, 96.9% and 79.2% of tags moved; 85 to 90 tags per slot.

| Slot | Band | Median error | Slot | Band | Median error |
|---|---|---|---|---|---|
| North 1 | ±2.9% | +0.67 | South 1 | ±1.4% | -0.07 |
| North 2 | ±1.5% | -0.03 | South 2 | ±3.0% | +0.52 |
| North 3 | ±2.7% | -0.58 | South 3 | ±2.8% | -0.42 |
| North 4 | ±2.4% | -0.40 | South 4 | ±3.4% | -0.95 |
| North 5 | ±1.4% | -0.31 | South 5 | ±1.3% | +0.15 |
| North 6 | ±1.8% | +0.12 | South 6 | ±2.6% | +1.14 |

Median of the slot medians -0.05 points. These are the reference bands for the second session.

**Between the sessions.** Camera events: the camera failed to open twice, 2026-10-12 08:27 and
08:28 UTC ("Camera __init__ sequence did not complete"), and opened at 08:29. Whether an app
restart caused the failed opens is not recorded. Warm app restarts known (app only, page-only
code): 2026-10-12 13:40, 14:07, 14:27 and 19:09 UTC, and 2026-10-13 07:42 UTC (the last four
reported on #116 by the tasks that borrowed the hardware label, each with focus locked at 5.97
after it). No lens move, no recalibration, no cold start
(Pi on since 2026-10-07). Trays and sheets were nudged and the tape measure removed (allowed).

**Second session, 2026-10-13: recorded two ways (decision, Aaron 2026-10-13).** Because of the
failed camera opens, the "no camera fault" condition was not met. The session is therefore (1) the
repeat of the 2026-10-12 session, with that deviation stated, and (2) the first session of a
clean pair, repeated on 2026-10-14 before any test that disturbs the rig.

Session `20261013T074951947771`, same calibration `20261012T070607812512`, lens 5.97 locked; rounds
at 07:54, 08:04 and 08:15 UTC, 21.2 minutes first to last, shortest gap 10.1 minutes, door closed;
92.7%, 85.6% and 51.5% of tags moved; 85 to 90 tags per slot.

| Slot | 10-12 band | Inside it on 10-13 | 10-13 band | 10-12 median | 10-13 median |
|---|---|---|---|---|---|
| North 1 | ±2.9% | 98% (88 of 90) | ±2.4% | +0.67 | +0.64 |
| North 2 | ±1.5% | 96% (86 of 90) | ±1.4% | -0.03 | +0.11 |
| North 3 | ±2.7% | 95% (81 of 85) | ±2.5% | -0.58 | -0.62 |
| North 4 | ±2.4% | 92% (78 of 85) | ±2.9% | -0.40 | -0.62 |
| North 5 | ±1.4% | 88% (79 of 90) | ±3.1% | -0.31 | +0.25 |
| North 6 | ±1.8% | 88% (79 of 90) | ±2.1% | +0.12 | +0.36 |
| South 1 | ±1.4% | 99% (89 of 90) | ±1.2% | -0.07 | +0.19 |
| South 2 | ±3.0% | 98% (88 of 90) | ±1.9% | +0.52 | +0.58 |
| South 3 | ±2.8% | 97% (87 of 90) | ±2.4% | -0.42 | -0.22 |
| South 4 | ±3.4% | 96% (82 of 85) | ±3.0% | -0.95 | -0.86 |
| South 5 | ±1.3% | 97% (87 of 90) | ±1.1% | +0.15 | +0.22 |
| South 6 | ±2.6% | 82% (74 of 90) | ±5.7% | +1.14 | +1.29 |

Median of the slot medians +0.21 points (2026-10-12: -0.05).

**Result as the repeat: pass, with the deviation above.** 93.7% of the whole table (998 of 1065
tags) fell inside the first session's bands (rule: at least 90%); lowest slot South 6, 82% (rule:
no slot below 75%). Bands changed by -1.1 to +3.1 points.

**South 6 and North 5, observed.** South 6's wider band comes from round 1 alone (photo
`rig/2026-10-13/075436_099643`): 6 of its 30 tags read +5.6% to +9.4%, all in the sheet's
south-east corner, growing down the last column (tags 329 to 354: 0.0, +0.3, +2.1, +5.6, +7.9,
+9.4%). That corner looks less sharp than the rest of the sheet, which fits a sheet not lying flat
there; a scrap of tape sits on the tray edge beside it. Rounds 2 and 3 in that slot stayed within
2.8%. North 5's wider band comes from round 2 (5 tags at +3.3% to +4.3%). Neither was flagged by
the validation checks (section 6). Script: `/home/pi/scratch/m2-acceptance-2026-10/slot_tags.py`.

**Change of reference for the clean pair (decision, Aaron 2026-10-13, written at 08:19 UTC,
before the session it names exists).** In round 1 of `20261013T074951947771` the South 6 sheet
was not lying flat (confirmed by Aaron), which widened that slot's band to ±5.7%, so it is not a
fair reference. A third session of the same calibration is run on 2026-10-13 after it, with every
sheet pressed flat and the tape scrap removed from the South 6 tray edge. That third session is
the first session of the clean pair; its repeat on 2026-10-14 is judged against its bands with the
same rule. It is also compared with `20261013T074951947771` as a same-day pair, for information.
The morning session stays the repeat of 2026-10-12, with its deviation.

**Third session, 2026-10-13: the first session of the clean pair.** Session
`20261013T081945572660`, same calibration, lens 5.97 locked; every sheet pressed flat and its
corners checked, tape scrap removed; rounds at 08:22, 08:32 and 08:50 UTC, 28.1 minutes first to
last, shortest gap 10.6 minutes, door closed; 100%, 90.4% and 69.0% of tags moved; 85 to 90 tags
per slot. No camera events since the morning session.

| Slot | Band | Median error | Slot | Band | Median error |
|---|---|---|---|---|---|
| North 1 | ±2.8% | +0.73 | South 1 | ±1.5% | +0.01 |
| North 2 | ±1.5% | -0.03 | South 2 | ±2.0% | +0.58 |
| North 3 | ±2.6% | -0.47 | South 3 | ±2.6% | -0.24 |
| North 4 | ±2.6% | -0.34 | South 4 | ±3.3% | -1.21 |
| North 5 | ±1.2% | +0.00 | South 5 | ±1.1% | +0.27 |
| North 6 | ±2.1% | +0.42 | South 6 | ±2.7% | +1.36 |

Median of the slot medians 0.00 points. These are the reference bands for the 2026-10-14 repeat.

Checked round by round before the session was closed (Aaron asked whether any round should be
redone): none. South 4 in round 1 read lower than in rounds 2 and 3 (median -1.81 against -0.90
and -0.89, 7 tags beyond 3%), but its tags read smoothly lower toward the image centre (from about
0% at the sheet's far corner to -4.8% at the corner nearest the centre), the known central error
(section 7) with the sheet sitting nearer the centre than usual, not a sheet off the tray.

**Same-day pair, for information** (this session against the morning session's bands, the same
rule): 93.6% of the whole table (997 of 1065) inside; lowest slot South 1, 86%. It would pass. The
morning bands of North 5 (±3.1%) and South 6 (±5.7%) were widened by single rounds, so those two
slots hold 100% here and say little.

**Clean repeat, 2026-10-14: pass.** Between the reference session (ended 2026-10-13 08:52 UTC)
and this one: no camera events; no lens move, recalibration or cold start (Pi on since
2026-10-07); warm app restarts, all reported on #116 with focus locked at 5.97 after each:
2026-10-13 11:49, 11:51 and later during the #139 loan (shutdown change only), 12:04 (main pulled
to `1df69c7`), 13:05, 13:52 and 14:12 UTC (#134 loans, page and plot code only). A second server
from another task ran on port 8134 with the synthetic camera and its own data folders; it did not
hold the camera.

Session `20261014T070107213176`, same calibration `20261012T070607812512`, lens 5.97 locked; sheets
pressed flat; rounds at 07:05, 07:16 and 07:27 UTC, 22.6 minutes first to last, shortest gap 11.0
minutes, door closed; 97.7%, 77.7% and 74.4% of tags moved; 85 to 90 tags per slot.

| Slot | Reference band (10-13) | Inside it on 10-14 | 10-14 band | 10-13 median | 10-14 median |
|---|---|---|---|---|---|
| North 1 | ±2.8% | 99% (84 of 85) | ±2.3% | +0.73 | +0.46 |
| North 2 | ±1.5% | 97% (87 of 90) | ±1.3% | -0.03 | -0.19 |
| North 3 | ±2.6% | 97% (87 of 90) | ±2.1% | -0.47 | -0.66 |
| North 4 | ±2.6% | 98% (88 of 90) | ±2.1% | -0.34 | -0.42 |
| North 5 | ±1.2% | 81% (73 of 90) | ±1.4% | +0.00 | -0.38 |
| North 6 | ±2.1% | 100% (90 of 90) | ±1.6% | +0.42 | +0.30 |
| South 1 | ±1.5% | 93% (79 of 85) | ±1.8% | +0.01 | -0.22 |
| South 2 | ±2.0% | 95% (81 of 85) | ±1.9% | +0.58 | +0.45 |
| South 3 | ±2.6% | 96% (86 of 90) | ±2.2% | -0.24 | -0.12 |
| South 4 | ±3.3% | 97% (87 of 90) | ±3.1% | -1.21 | -0.81 |
| South 5 | ±1.1% | 82% (74 of 90) | ±1.2% | +0.27 | -0.01 |
| South 6 | ±2.7% | 96% (86 of 90) | ±2.6% | +1.36 | +1.32 |

**Result: pass.** 94.1% of the whole table (1002 of 1065 tags) fell inside the reference bands
(rule: at least 90%); lowest slot North 5, 81% (rule: no slot below 75%). Median of the slot
medians -0.16 points (reference 0.00). Bands changed by -0.5 to +0.3 points. A slot's band
measured on one day still described the same calibration on the next day.

The two narrowest slots, North 5 (±1.2%) and South 5 (±1.1%), had the lowest fractions inside
(81%, 82%): a narrow band leaves little room for a day-to-day shift of a few tenths of a point
(North 5's median moved -0.38). Each slot's band comes from about 90 tags, so the narrowest ones
are the least certain; this is the kind of result the per-slot floor (75%) was set to allow.

**South 6, observed again.** In round 3 (photo `rig/2026-10-14/072749_451484`) three tags at the
sheet corner in the south-east of the slot read +3.4%, +4.1% and +6.8%; the rest of the sheet read
-0.0% to +2.6%. It was a different sheet from 2026-10-13's, at the same spot, so the tray may be
lifting sheets there (not checked). It did not change the result: South 6 kept 96% inside.

### 14.2 Tape measure

Section 9.2 method A unchanged: steel tape from the outer edge of a tag on the South 1 sheet to the
outer edge of a tag on the South 6 sheet, two tag pairs, against the app's distance along the same
line. **Pass:** the app agrees with the tape within 2% (PLAN.md). Optional, to close a gap in 9.2:
the same along the North row, and one span front to back.

**As run (Aaron, 2026-10-12, written before the run).** The sheets are placed for convenience and
the western-most and eastern-most sheets are taped down at their edges (no tag covered) so laying
the measuring tape does not move them. The steel tape runs from the outer edge of the
eastern-most tag to the outer edge of the western-most tag in one row, read looking straight down
at each edge, and is left in place, as close to the tag edges as it lies, for one photograph. The
tape sits a few mm above the sheets (the tray construction); Aaron measures that height, ±2 mm.
The same photograph also gives section 9.2 method B (the tape's own marks read in the photo, with
the height correction of 0.072% of length per mm, so ±2 mm is about ±0.15%).

**Result, 2026-10-12: pass by both methods.** Calibration `20261012T070607812512`, lens 5.97
locked. The sheets were placed for convenience, so they do not sit in their validation slots; the
end sheets were taped down. Photos (full resolution, saved in the test experiment's folder
`experiments/2026-10-09_68cdf210/stills/2026-10-12/`): `074846_006450` with the tape in place,
`075738_490795` with the tape lifted. Scripts: `/home/pi/scratch/m2-acceptance-2026-10/tape_a.py`
and `tape_b.py`.

*Method A* (photo 07:57:38 UTC, tape lifted; with the tape in place the tape hid the west end tag
and its row). Tag 325, top row of the western-most sheet, to tag 359, same row of the
eastern-most sheet (centres 20 px apart in height over 8400 px), outer edge to outer edge:

| Tape | App | App reads long by | Old camera (9.2) |
|---|---|---|---|
| 1736 mm | 1759.0 mm | **1.3%** | 1.6% and 1.7% |

*Method B* (photo 07:48:46 UTC). The tape's red boxes at 10 to 170 cm were found by colour (the
180 cm box is next to the tape case and was not found). The tape is curved across its width; its
marks lie about 3 to 5 mm (centre line) to 10 to 12 mm (edges) above the tray top, so 3 to 12 mm
is used (Aaron; the centre could not be measured directly). The height correction is therefore
0.22% to 0.86% of length; the middle, 0.54%, is applied, with ±0.32%.

| Span | Tape | App as read | Corrected |
|---|---|---|---|
| 10 to 170 cm | 1600 mm | +1.82% | **+1.3%** (+1.0% to +1.6%) |
| 20 to 160 cm | 1400 mm | +1.70% | +1.2% |
| 30 to 150 cm | 1200 mm | +1.54% | +1.0% |

Each 10 cm step, as read, west to east: +3.0, +3.2, +2.6, +2.7, +2.4, +1.7, +1.2, +0.3, -0.3,
+0.1, +0.6, +2.4, +2.6, +1.9, +2.2, +2.3% (subtract about 0.54 for height). Near the centre the
app reads about 0.5% short to correct, toward both ends about 2% long: the known central error
(section 7), as on the old camera.

The two methods agree within 0.1 points: over about 1600 to 1740 mm the app reads distances about
1.3% long on SN001 (old camera SN000: 1.4% to 1.7%). The open point of 9.2 remains: measured by
the app, the end tags themselves read 29.87 mm (west) and 30.85 mm (east), while the distance
across the row reads long.

**Covers.** The South row only, west to east, at tray-top height. The North row and a span front
to back cannot be reached without moving the table (Aaron, 2026-10-12), so they are not covered,
as on the old camera.

### 14.3 Two calibrations with a cold start between

**Question.** Two independent calibrations of the same unmoved table: how far apart are their
scale fields, compared with the validation bands? And, in the same hour, how do readings change
after a cold start on SN001?

**Method (decision, Aaron 2026-10-09: cold start, as PLAN.md asks, run while Aaron is at the
chamber, weekdays 8:30 to 16:30 local).** The sheets lie on the trays and are not touched from
calibration A to calibration B; the chamber stays closed.

1. Calibration A, with "Set as current" off.
2. Reference photograph (section 8.1, step 2).
3. Pi shut down and left off about 30 minutes to cool (as run 3, section 8.1), then switched on.
4. Settling-hour photographs at +0, +15, +30 and +60 minutes after the app opens the camera
   (section 8.1, steps 4 and 5), compared with the reference. This repeats the power-cut test on
   SN001 and measures the 60-minute cold-start window, which is a placeholder until then
   (section 8, *Cold-start window*).
5. Calibration B, at least 60 minutes after power-on, with "Set as current" off.

*Photo method as run (written 2026-10-14 before the run).* The reference and settling-hour photos
are full-resolution photos taken through the app (`POST /capture`, the same `take_photo` path as a
validation round) instead of validation rounds, because no validation session is open across a
power cut. The settling photos are taken by
`/home/pi/scratch/m2-acceptance-2026-10/settling_photos.sh`, started by Aaron once the server is up
after power-on (nothing starts the server automatically); it takes the +0 photo as soon as the
server answers and the others 15, 30 and 60 minutes after it, and logs the times, focus status
and Pi uptime to `settling_log.txt`. The comparison is section 8.1 step 5 (each calibration tag
matched to itself in the reference photo, same ID within 20 px), with the sheets untouched from
the reference photo to the +60 photo.

**Pass (calibrations):** at each of the 12 slot centres, the difference between the two fields'
scales, doubled to give area (area error is about twice length error), is smaller than that slot's
band from 14.1. **Settling hour:** no pass or fail; the result is compared with the old camera's
run 3 (section 8 table), and says when the readings return to within the control range.

**Run, 2026-10-14 (part A, before the power cut).** Calibration A `20261014T073752589144`
(07:38 UTC, "Set as current" off, lens 5.97 locked, 30.0 mm tags, residual 0.55%); the current
calibration stayed `20261012T070607812512`. Reference photo 07:39:09 UTC,
`experiments/2026-10-12_631bb6b5/stills/2026-10-14/073909_652339` (saved in a test experiment's
folder), no flags; Pi up 591512 s. Sheets pressed flat and not touched from calibration A on.

**Run, parts B and C.** Pi shut down by Aaron after the reference photo and unplugged, off about
30 minutes (Aaron); table untouched. The app's own record gives 2132 s (35.5 min) from its last run
before the shutdown to its next start. Power on: Pi booted 08:17:19 UTC (boot
`de439e0f-5bb8-4db1-8348-efad2a5a7513`). Nothing started automatically; at 08:18:50 UTC the server
(the usual command) and `settling_photos.sh` were started from this session. The +0 photo was
taken at 08:18:59 UTC, Pi up 99 s, app up 5 s, lens check passed (reported 5.97, locked 5.97),
photo flagged "inside the 60 min cold-start window". No camera events. Photos are saved in the
test experiment's folder `experiments/2026-10-12_631bb6b5/stills/2026-10-14/`. Comparison script:
`/home/pi/scratch/m2-acceptance-2026-10/settling_compare.py` (area errors with calibration A's
scale field; slot boxes from session `20261014T070107213176`; calibration sheet tags only).

| Photo | Time (UTC) | Tags found, matched (of 359 in the reference) | Median change | Spread (SD) | Ring 1000 to 1500 px | Largest slot median |
|---|---|---|---|---|---|---|
| +0 | 08:18:59 | 331, 331 | -2.73 | 1.03 | -1.80 | -3.69 (North 1, North 5) |
| +15 | 08:34:03 | 359, 359 | +0.08 | 0.22 | +0.10 | +0.31 (South 1) |
| +30 | 08:49:06 | 359, 359 | +0.10 | 0.25 | +0.00 | +0.28 (South 1) |
| +60 | 09:19:05 | 359, 359 | +0.07 | 0.25 | -0.01 | +0.27 (South 1) |

Focus read locked at 5.97 at every photo; no camera events in the hour.

**Settling hour result.** Right after the cold start the readings were 2.73 points low on average
(every slot low, -1.02 to -3.69), and 28 of 359 tags were not found. By +15 minutes they were back:
median +0.08, every slot within 0.31 of the reference, all tags found; +30 and +60 stayed there
(medians +0.10 and +0.07, slots within 0.28). From +15 on the changes are inside the range of
undisturbed photos (old camera control B: median within ±0.10, slots up to 0.52; new camera, 5 app
restarts: largest slot 0.29, section 8). Against the old camera's run 3 (+0 -1.73, +15 -0.41,
+30 -0.38, +60 -0.14), SN001 starts lower and recovers sooner. One run.

For the 60-minute cold-start window (section 8, *Cold-start window*, a placeholder from one old
camera run): on SN001 the readings had recovered somewhere between +0 (100 s after power-on) and
+15 minutes; this run does not say exactly when within that time. The 60-minute window covers it
with room to spare. Whether to shorten it is a decision, not made here.


**Calibration B and the comparison.** Calibration B `20261014T092907984792` (09:29 UTC, 70 minutes
after power-on, "Set as current" off, lens 5.97 locked, 30.0 mm tags, residual 0.58%; A 0.55%);
the current calibration stayed `20261012T070607812512`. Sheets untouched since calibration A.
Script: `/home/pi/scratch/m2-acceptance-2026-10/two_cal.py`. Difference in area (B against A,
twice the scale difference) at each slot centre, against the clean pair's reference bands
(session `20261013T081945572660`):

| Slot | B against A | Band | Slot | B against A | Band |
|---|---|---|---|---|---|
| North 1 | +0.19 | ±2.8% | South 1 | +0.06 | ±1.5% |
| North 2 | +0.17 | ±1.5% | South 2 | +0.04 | ±2.0% |
| North 3 | +0.13 | ±2.6% | South 3 | -0.00 | ±2.6% |
| North 4 | +0.11 | ±2.6% | South 4 | -0.02 | ±3.3% |
| North 5 | +0.09 | ±1.2% | South 5 | -0.05 | ±1.1% |
| North 6 | +0.06 | ±2.1% | South 6 | -0.08 | ±2.7% |

**Result: pass.** Every slot's difference is smaller than its band; the largest is about 0.11 of
its band (North 2, 0.17 against ±1.5%). Two calibrations of the same table with a cold start
between them agree far inside the validation bands, so the bands are not too narrow on this
account. Old camera, 2026-09-25, without a cold start: 0.02% to 0.16% (section 8 table).

### 14.4 Two heights

Section 9.1 unchanged: one calibration with the sheets on the table surface, one on the trays at
experiment height, lens refocused by Aaron for each. **Pass:** the scale-field shape (each corner's
scale divided by the centre scale) differs between the two by less than both runs' residuals.

**Result, 2026-10-14: pass.** Two calibrations, same camera position, 30.0 mm tags, 359
calibration tags and 4 corner tags each; lens focused and locked by Aaron for each height:

| Run | Sheets on | Calibration | Lens | Centre scale | Residual |
|---|---|---|---|---|---|
| A | the table surface (trays moved as needed) | `20261014T094151646606` (09:41 UTC), not made current | 5.99 | 4.535 px/mm | 0.66% |
| B | trays at experiment height, pressed flat | `20261014T095016381511` (09:50 UTC), made current | 6.05 | 4.859 px/mm | 0.50% |

Each run's scale at the corners of the calibrated area divided by its own scale at the image centre
(points and method as section 9.1; script `/home/pi/scratch/m2-acceptance-2026-10/two_heights.py`):

| Position | Table | Trays | Difference (points) |
|---|---|---|---|
| Top-left | +0.70% | +0.30% | +0.39 |
| Top-right | -0.26% | -0.30% | +0.03 |
| Bottom-left | +0.27% | +0.30% | -0.04 |
| Bottom-right | -0.69% | -0.30% | -0.39 |

The largest difference (0.39 points, top-left and bottom-right) is below both residuals (0.50%
and 0.66%): one paper calibration's shape covers the tray height. Less margin than the old camera
(largest 0.16). The centre scale changed by 7.14% in length, 14.78% in area (old camera 15.1%),
about 100 mm of height at 0.145% per mm (derived, not taped). The lens moved between runs (5.99,
6.05), as in a real change of height. Run B is the tripwire baseline for 14.5.

### 14.5 Roll and knock

Section 9.3 unchanged: tripwire baseline, a knock on the camera mount, then the camera rolled by
hand, measured against the table rails. To reach the camera Aaron climbs on the table, so contact with
the table is expected (Aaron, 2026-10-14, written before the run). Disturbed sheets and trays do
not matter for this test; a shifted table or corner tag would show as a disagreement between the
app's roll and the rails', and is then written up as a disturbed run.

**Run, 2026-10-14.** Baseline: calibration `20261014T095016381511` (14.4 run B, current, lens
6.05). The app returns the verdict to the browser and saves only the photo, so each verdict is
recomputed from the saved photo with the app's own `check_tripwire`
(`/home/pi/scratch/m2-acceptance-2026-10/tripwire_replay.py`).

| Step | Photo (UTC) | Verdict | Roll | Corner scale changes |
|---|---|---|---|---|
| Baseline | `rig/2026-10-14/095152_652234`, 09:51:52 | OK, "no significant drift detected" | 0.00 deg | -0.06% to +0.05% |
| Knock on the camera mount (one firm knock by hand) | `rig/2026-10-14/095420_606701`, 09:54:20 | DRIFT, "rolled 5.9 deg clockwise" | 5.86 deg | -0.46% to +0.44% |
| Second, harder knock (Aaron) | `rig/2026-10-14/095610_032904`, 09:56:10 | DRIFT, "rolled 6.9 deg clockwise" | 6.85 deg | -1.35% to +1.21% |

Each knock rolled the camera; neither moved a corner tag out of view. The FAIL limits (roll 10 deg,
corner scale 8%, a missing corner tag) were not reached, so both knocks read DRIFT. Aaron decided
to stop there rather than knock harder (risk to the mount) and to use the two knock photos as the
roll test, which PLAN.md sets at about 5 deg (2026-10-14).

Rail angles (script `/home/pi/scratch/m2-acceptance-2026-10/rail_angles.py`: the strongest
near-horizontal edge in each rail's region found by a Hough search, then fitted by least squares
to its edge points over x = 1500 to 7600 px, about 3800 to 4300 points per rail, standard error
0.0004 to 0.0007 deg; top and bottom rails interpolated to the image centre as in section 9.3):

| Photo | Top rail | Bottom rail | At the image centre | Change from baseline | App's roll | Difference |
|---|---|---|---|---|---|---|
| Baseline | +0.228 deg | -0.396 deg | -0.082 deg | | 0.00 deg | |
| First knock | +6.007 deg | +5.539 deg | +5.773 deg | +5.86 deg | 5.86 deg | 0.00 deg |
| Second knock | +6.919 deg | +6.563 deg | +6.734 deg | +6.82 deg | 6.85 deg | 0.03 deg |

**Result.** Roll: **pass**, the app's roll agrees with the rails within 0.03 deg at about 5.9 and
6.9 deg (criterion 0.2 deg). Knock: **detected, but not FAIL**: both knocks were flagged DRIFT and
neither was passed as OK; PLAN.md's wording asks for FAIL, which the tripwire gives only at a 10
deg roll, an 8% corner scale change or a missing corner tag. On the old camera FAIL came from a
corner tag pushed out of view. Whether a knock of this size should read FAIL is a question about
the tripwire's provisional limits, not about the camera, and is not decided.

**Missing corner tag, checked after the closing calibration (Aaron, 2026-10-14).** Against
calibration `20261014T111147292361`, verdicts recomputed as above:

| Step | Photo (UTC) | Verdict |
|---|---|---|
| Baseline | `rig/2026-10-14/115539_140848`, 11:55:39 | OK, roll 0.00 deg |
| Corner tag 455 covered by hand | `rig/2026-10-14/115707_089824`, 11:57:07 | FAIL, "corner tag(s) [455] present at calibration are missing now" |
| Tag uncovered | `rig/2026-10-14/115721_414161`, 11:57:21 | OK, roll 0.00 deg |

**Decision (Aaron, 2026-10-14): roll and knock signed off.** The knocks were detected (DRIFT) and
the missing-corner-tag path gives FAIL; a harder knock was not tried, being costly and a risk to
the mount. PLAN.md's M2 line was changed to match: a hard knock is flagged (DRIFT or FAIL, never
OK), and a missing corner tag gives FAIL.

**Covers.** Rolls of about 5.9 and 6.9 deg, both clockwise, produced by knocks. No table contact
was reported.
 PLAN.md asks for about 5 deg (section 9.3 reached about
3). **Pass:** the app's roll agrees with the rails within 0.2 deg, and the knock gives FAIL.

### 14.6 Closing calibration and validation

After 14.5 the camera has moved. A new calibration at experiment height, made current, and a
complete validation give the bands the rig then runs with. Not a pass or fail test.

**Run, 2026-10-14.** Aaron turned the camera back by hand after 14.5; the rails then read +0.64 deg
at the image centre, against -0.08 deg at the 14.5 baseline, so the camera ended about 0.7 deg from
its morning position (a new calibration follows, so this does not matter). Lens 6.05, Aaron's
choice. Calibration `20261014T111147292361` (11:11 UTC, made current, 30.0 mm tags, residual
0.48%). Validation session `20261014T111253582634`: counted rounds at 11:14, 11:35 and 11:47 UTC,
33.5 minutes first to last, shortest gap 12.7 minutes; a round at 11:45 was not counted (49.6% of
tags moved, under the 50% rule); 84.2%, 75.8% and 63.9% of tags moved in the counted rounds; 85 to
90 tags per slot; no camera events.

| Slot | Band | Median error | Slot | Band | Median error |
|---|---|---|---|---|---|
| North 1 | ±2.5% | +0.05 | South 1 | ±1.8% | +0.42 |
| North 2 | ±1.6% | +0.56 | South 2 | ±1.5% | +0.13 |
| North 3 | ±2.0% | -0.22 | South 3 | ±2.1% | -0.09 |
| North 4 | ±2.6% | -0.62 | South 4 | ±2.6% | -0.55 |
| North 5 | ±1.3% | -0.04 | South 5 | ±1.5% | -0.51 |
| North 6 | ±1.9% | +0.40 | South 6 | ±2.2% | +0.90 |

Median of the slot medians 0.00 points. **These are the current bands of SN001** (lens 6.05). Two
small groups of high readings look like sheet corners not lying flat: North 1 in round 1 (2 tags,
up to +6.1%) and South 6 in round 3 (3 tags, up to +5.5%, the third time at that slot in three
days). Neither was flagged by the validation checks, and neither widened its slot's band much.
The tray at South 6 has not been checked.

### 14.7 Summary

| Test | Pass criterion | Result on SN001 | SN000 (section 9) |
|---|---|---|---|
| 14.1 Repeat validation | Whole table at least 90% inside the first day's bands, no slot below 75% | **Pass**: 94.1%, lowest slot 81% (clean pair, 2026-10-13 and 10-14); also 93.7%, lowest 82% with a stated deviation (10-12 and 10-13) | Not run |
| 14.2 Tape measure | App within 2% of the tape | **Pass**: about 1.3% long, both methods | Pass: 1.4% to 1.7% long |
| 14.3 Two calibrations, cold start between | Difference at every slot centre smaller than its band | **Pass**: -0.08 to +0.19 points, at most 0.11 of a band | 0.02% to 0.16%, no cold start |
| 14.3 Settling hour | None (measurement) | -2.73 points at +0, back within 0.31 by +15 min | -1.73 at +0, -0.41 at +15, -0.14 at +60 |
| 14.4 Two heights | Shape difference below both residuals | **Pass**: 0.39 points against 0.50% and 0.66% | Pass: 0.16 |
| 14.5 Roll | App within 0.2 deg of the rails | **Pass**: within 0.03 deg at 5.9 and 6.9 deg | Pass: 0.06 deg at 3.0 deg |
| 14.5 Knock | A hard knock is flagged (PLAN.md as changed 2026-10-14; was "gives FAIL") | **Signed off**: both knocks read DRIFT (rolls of 5.9 and 6.9 deg); a covered corner tag gave FAIL | FAIL, through a corner tag pushed out of view |
| 14.6 Closing calibration and validation | None | Bands ±1.3% to ±2.6%, lens 6.05 | |

Every result that has a pass criterion passed. The knock read DRIFT, not FAIL; Aaron signed it off
on 2026-10-14 with the covered-corner-tag check, and PLAN.md's wording was changed to match.

## 15. CRISP-DM round 1: trays, tags and green area on the benchmark (method written 2026-10-15, before the photo session)

**Status:** method agreed with Aaron, 2026-10-15. The 15 October photo session has not run yet.
Issue #153. The plan behind the rounds is summarised in issue #153 and PLAN.md (to be added).

**Why.** The academic supervisor recommended running the whole loop (photo, segmentation, area,
review) early, with loose targets, so problems with the setup and the expectations show up early
(CRISP-DM). PLAN.md expects segmentation to be the largest error source, and it has not been
measured. This round is the first look.

**Bar for this round (decision, Aaron 2026-10-14).** The pipeline runs end to end and gives a
number per tray. Everything is recorded; nothing is judged against a target yet. Targets for
round 2 are set in the round 1 review at the end of this section.

### 15.1 The benchmark "Benchy Yellow-4"

A 3D-printed plant benchmark. Its design file is not available, so its true leaf area is not
known. Measured by Aaron on 2026-10-15 with vernier callipers (not trusted beyond 0.1 mm).
Number of readings per figure: to be recorded. Heights were taken with the callipers' depth rod
from the surface of the yellow base; the base is 4.27 mm thick and sits on the blue tray top, so
height above the tray = h + 4.27 mm.

| Feature | Colour | Measured | Area seen from above (computed) | Height above tray |
|---|---|---|---|---|
| Circle, embedded, NE corner | red | ⌀ 10 mm, h 0 | 78.5 mm² | 4.27 mm |
| Sphere, SE corner | red | ⌀ 8.85 mm, h 6.78 mm | 61.5 mm² | widest outline about 6.6 mm |
| Cylinder, SW corner | red | ⌀ 8.39 mm, h 7.73 mm | 55.3 mm² | 12.00 mm |
| Rectangular prism, NW corner | red | 6.34 x 8.14 mm, h 10.77 mm | 51.6 mm² | 15.04 mm |
| Rosette NW | green | h-max 21.88, h-centre 14.12, ⌀-max 50.87 mm | at most 2032 mm² | top 26.15 mm |
| Rosette NE | green | h-max 28.00, h-centre at least 19.05, ⌀-max 67.20 mm | at most 3547 mm² | top 32.27 mm |
| Rosette SW | green | h-max 19.35, h-centre 12.78, ⌀-max 38.68 mm | at most 1175 mm² | top 23.62 mm |
| Rosette SE | green | h-max 24.21, h-centre at least 15.41, ⌀-max 59.64 mm | at most 2794 mm² | top 28.48 mm |

The solid areas are computed from the calliper dimensions (π r² for the round solids, X x Y for the
prism). The sphere's outline seen from above is its widest circle, at h minus the radius. The
rosette limits are a full circle of the widest diameter; the leaves cover less, so these are upper
limits, not areas.

*Correction, 2026-10-15:* the SE and SW rosette diameters were first written the wrong way round; the stills showed it and Aaron confirmed (SW 38.68 mm, SE 59.64 mm; the table above is corrected). The rosette diameters are vernier calliper estimates with no check of their accuracy (Aaron), so the upper limits made from them are estimates too.

**What it can and cannot show.** The red solids are known areas at known heights, but small: at 50
to 80 mm² most of their pixels lie near an edge, so edge pixels will dominate their error. The
rosettes show repeatability (the same object in every slot and rotation should read the same) and
plant-like colour on a blue tray, not accuracy. Plastic is shinier and a different green than
leaves. Expected effect of height alone (0.145% of area per mm, section 4): 0.6% to 2.2% on the
solids, 3.4% to 4.7% at the rosette tops.

### 15.2 Data

- About 36 gallery stills of the benchmark taken on 15 October (part of the two most recent
  experiments), moved through the frame and rotated on each tray. Capture names recorded with the
  results.
- The 15 October photo session (15.3).
- Tray tag designs in the chamber, all 36h11, IDs 1 to 12 (the 4x5 series; IDs 1 to 3 are the 20 mm tags by their size in the image), tag in cell A1 of a 4x5 tray, trays at mixed
  orientations: 3 x 30 mm black on white paper extending past the tray corner, 3 x 20 mm black on
  white paper extending past the tray corner, 6 x 30 mm green 3D-printed on white inside the tray.

Photos in `/var/lib/npec-rig/rig/`; scripts in `experiments/round1/`. Calibration, validation and
lens position of every still are read from `rig.db` and recorded with the results.

### 15.3 The 15 October photo session

Aaron is in the chamber on 15 October only, so every photo that needs a move is taken then. Door
closed and lights on for every photograph. In this order:

| Step | Stills | What |
|---|---|---|
| a | 10 | Nothing moved (repeatability of tag detection and area); taken 07:57 to 07:58 UTC, experiment "tag-testing" |
| b1 | 1 | Every tray turned 180° in its own slot (trays fit their slots at 0° or 180° only) |
| b2 | 1 | Trays swapped between the North and South rows, orientation kept from b1 (optional) |
| b3 | 1 | Trays moved to other slots in their row, so each tag design reaches the frame centre and both ends (optional) |
| c | 1 | Trays pushed as close together as they go (worst case for splitting trays) |
| d | up to 12 | Benchmark on each slot, filling slots the gallery stills miss, frame centre and corners at least |
| e | 5 | Benchmark on one slot, nothing moved (area repeatability) |
| f | 1 | Trays without the benchmark (background) |

### 15.3a Session 1 outcome and the second tag round (method written 2026-10-15, before the second round)

**Session 1 (steps 1 to 6, 34 stills, record in `experiments/round1/session-2026-10-15.csv`).**
Steps 7 (benchmark repeated on one slot) and 8 (trays without the benchmark) were dropped: step 1
already repeats the benchmark on one slot 10 times, and in every still 11 of 12 trays carry no
benchmark (Aaron). Tray tags found: 399 of 408 sightings. Misses: tag 1 (20 mm paper) 5 of 34,
tag 2 (20 mm paper) 3 of 34, tag 5 (30 mm green) 1 of 34. Tag 1 was prepared without an adequate
quiet zone (Aaron) and is replaced.

**Why a second round.** The final tray tags must be about 20 mm, 3D printed, on the outside edge
of the tray: the hard clearance at the tray side is 27 mm, and 30 mm edge tags collide with
equipment elsewhere in the lab (Aaron, 2026-10-15). Three 20 mm tags, one badly prepared and all
on the right half of the frame when missed, are too few to judge the size. The supervisor is open
to changing the design given good evidence of a problem.

**Design (paired).** Each of the 6 green-tag trays keeps its 30 mm green tag and gains a 20 mm
paper tag on its outside edge, IDs 13 and up (one ID per tag, never a duplicate in the frame).
Pairs recorded by Aaron before the photos (green 30 mm : 20 mm paper): 4:0, 5:14, 6:16, 7:17, 8:13, 11:15. So the green 30 mm tags are 4, 5, 6, 7, 8 and 11; the black 30 mm reference tags are 9, 10 and 12; the 20 mm tags are 0, 1, 2, 3, 13, 14, 15, 16 and 17. Tag 1 is replaced by a properly
prepared print with the same ID; the old print leaves the chamber. The 3 black 30 mm trays stay
as a reference. Steps, stills taken by the agent through the rig's capture API: nothing moved
(10), North and South rows swapped (3), trays swapped within rows (3), trays pushed together (3).

**Decision rule (accepted by Aaron, 2026-10-15, before the photos).** A *pair* is the 20 mm and the
30 mm tag on the same tray in the same still; a *position* is one layout step of at least 3 stills
with nothing moved. 20 mm has a problem if either:

- **A. Persistent miss (main rule).** A properly prepared 20 mm tag is missed in every still of a
  position while the 30 mm tag on the same tray is read in at least one of them.
- **B. Higher miss rate (supporting rule).** In at least 5% of pairs the 20 mm tag is missed while
  its partner is read, and the reverse happens less than a fifth as often.

Otherwise: no problem shown. The 5% and the fifth are decisions, not measurements. Every miss is
listed with its still name and position. A tag found badly prepared afterwards is reported
separately with the reason, never dropped. Limit: paper tags, not 3D prints; the 3D-printed tag
needs its own check (issue #70).

### 15.3b Result of the paired 20 mm round (2026-10-15, 09:06 to 09:28 UTC)

19 stills, experiment "tag-testing", steps R2-1 to R2-4 in `experiments/round1/session-2026-10-15.csv`:
nothing moved (10), North and South rows swapped (3), trays swapped within rows (3), trays pushed
together (3). Detector: `npec_rig.tags.detect_tags`, unchanged. Stills taken through `POST /capture`;
no lens flag on any.

**Rule A (persistent miss): met, 4 cases.** A 20 mm tag missed in every still of a position while its
30 mm partner on the same tray was read:

| Step | 20 mm tag | 30 mm partner | Stills |
|---|---|---|---|
| R2-1 nothing moved | 14 | 5 | 10 |
| R2-2 rows swapped | 0 | 4 | 3 |
| R2-3 swapped within rows | 14 | 5 | 3 |
| R2-3 swapped within rows | 15 | 11 | 3 |

**Rule B (miss rate): met.** In 40 of 114 pairs (35%) the 20 mm tag was missed while its partner was
read; the reverse happened 0 times.

**Misses per tag in 19 stills.** 20 mm: tag 0 11, tag 1 (new print) 0, tag 2 5, tag 3 1, tag 13 1,
tag 14 15, tag 15 7, tag 16 0, tag 17 7. 30 mm: tag 5 1, all others 0. So 48 misses in 171 20 mm
sightings against 1 in 171 30 mm sightings.

**What it does and does not show.** Under the rule agreed before the photos, 20 mm paper tags have a
problem on this rig: some are missed persistently at positions where a 30 mm tag on the same tray is
read. Every tag that was missed persistently was read at some other position (tag 14 in R2-2, tag 0 in
R2-3 and R2-4, tag 15 in R2-2 and R2-4), so the prints are readable and the misses depend on where the
tag sits. The tags were prepared that morning by Aaron; no tag has been found badly prepared. Not
shown: the cause (position in the frame, light, how the paper lies, or detector settings), or how
3D-printed 20 mm tags behave (issue #70).

### 15.3c Detector settings on the same 19 stills (2026-10-15, from saved photos)

**Question.** Are the 20 mm misses in 15.3b caused by the tags, or by the detector settings? The
rig's settings (`npec_rig.tags._detector_parameters`) were tuned for calibration tags and are
frozen; this test ran a copy with one change at a time, in a scratch script, without changing
`tags.py`. Same 19 stills, OpenCV 4.10.0 ArUco detector, AprilTag 36h11, images read as grayscale
by OpenCV. Also counted: any tag ID that is not on the table (IDs other than 0 to 17 and the corner
tags 450 to 499), since looser settings can report tags that are not there.

| Setting | 20 mm missed (of 171) | 30 mm missed (of 171) | Persistent misses (rule A) | IDs not on the table |
|---|---|---|---|---|
| A the rig's settings | 50 | 0 | 4 | none |
| B error correction rate 1.0 | 50 | 0 | 4 | none |
| C bit sampling 8 px per cell, ignored margin 0.2 | **0** | **0** | **0** | none |
| D threshold windows 3 to 53 px, constant 5 | 39 | 0 | 3 | none |
| E polygon accuracy 0.05 | 50 | 0 | 4 | none |
| F B, C, D and E together | 0 | 1 | 0 | none |

Setting A gives 50 and 0 here against 48 and 1 in 15.3b: 15.3b converted colour to grey with the
rig's own conversion (`camera.to_grayscale`), this test with OpenCV's. The difference is 3
sightings in 342.

**What it shows.** On these 19 stills the 20 mm paper tag misses come from how the detector reads
the tag's pattern (OpenCV's default reads each pattern square from 4 x 4 pixels after removing
perspective; setting C uses 8 x 8 and ignores more of each square's edge), not from the tag size.
With setting C, rules A and B of 15.3a are not met.

**What it does not show.** Whether setting C changes the calibration corner positions (it should
not: it affects only how the pattern is read, but that is not measured, so the calibration keeps
its frozen settings); whether it holds on other stills (session 1, calibration frames) and on
3D-printed 20 mm tags (issue #70).

### 15.3d One-hour unattended run (method written 2026-10-15, before the run)

**Question.** With nothing moved for an hour, how steady are tag detection and the benchmark's
green and red areas from one still to the next, and does anything drift? **Setup.** The layout of
round 2 step 4 (trays pushed together, 20 mm tags on the 6 green trays, benchmark on its tray), door
closed, nobody in the chamber (Aaron at lunch). **Method.** One still every 15 seconds, start to
start, for 60 minutes, about 240 stills, taken by the agent through `POST /capture` into experiment
"tag-testing", step R3 in `experiments/round1/session-2026-10-15.csv`. Every sidecar records lens
position, exposure and colour gains, so drift in those is read from the stills. **Analysed:**
tag detection per still with the rig's settings and with setting C (15.3c); benchmark areas through
issue #154's method. Not covered: the chamber light cycle (the run is shorter than it).

**As run.** Stopped early by decision (Aaron back early; 30 minutes judged enough for round 1): 123 stills, 10:01:50 to 10:32:19 UTC, no capture error, no lens flag.

**Results.** Script `experiments/round1/run_analysis.py`, per still in `experiments/round1/run-2026-10-15-tags.csv`. Grey from the rig's own conversion (`camera.to_grayscale`); setting A is the rig's detector, setting C is A with finer bit sampling (15.3c).

| | Setting A (rig) | Setting C |
|---|---|---|
| 20 mm tags missed (9 tags x 123 stills) | 165 of 1107 (14.9%): tag 14 55, tag 2 46, tag 3 42, tag 15 22 | 0 of 1107 |
| 30 mm tags missed | 1 of 1107 (tag 11, once) | 1 of 1107 (the same) |
| Detection time per still, mean (SD), min to max | 4.20 s (0.23), 3.99 to 6.33 | 4.17 s (0.11), 3.86 to 4.57 |

With nothing moved, the rig's settings missed 4 of the 9 20 mm tags in many stills, tag 14 in 55 of 123; setting C missed none. Detection time is the same within its spread, so setting C costs no measurable time (one pass per still on the Pi 5, grey image already made; issue #156 repeats the timing).

**Steadiness over the 30 minutes.** Exposure 6651 microseconds, analogue gain 1.0 and lens 6.05 did not change in any still. The colour gains moved slightly: red 1.994 to 2.012 (0.9%), blue 1.620 to 1.633 (0.8%). Their effect on the green and red areas is not measured here.

**A tag that was not a tray tag.** Both settings read ID 29, which is in the tray ID range, in 3 (A) and 4 (C) stills. It is a real printed tag: an offcut of a tag sheet in a yellow waste bin at the bottom edge of the frame (about x 7047, y 6688). So a tag print lying anywhere in view is read as a tray. Discarded prints must leave the chamber, or the app must ignore tags outside the table.

### 15.4 What is measured

Each tray is one region; tags give identity only (decision, Aaron 2026-10-14). Trays are found by
their blue, the benchmark's leaves by a green threshold (excess green), its solids by a red
threshold; tag areas are masked out from the detected tag corners. Pixel areas become mm² through
the calibration homography. Recorded:

- per tag design: detected or not, per slot and rotation, with the detector's confidence margin
- trays separated and matched to a tag: how many of 12, per still
- green area per tray, in mm²
- red solids: area per still against the computed area above
- rosettes: area per slot and rotation, the spread, and that it stays below each upper limit

### 15.5 Results: red and green area on the benchmark (issue #154)

From the #154 session; full record in `experiments/round1-benchy/NOTES.md` and `results.csv` (main, commit 68ea0ad, PR #155), script `experiments/round1-benchy/benchy.py`.

**Data.** 92 stills of the benchmark, 15 October: experiment `2026-10-12_631bb6b5` (12),
`2026-10-15_83acd97d` (27), `2026-10-15_44a9e96e` tag-testing (53, session 1 and the second tag
round). All under calibration `20261014T111147292361`, validation `20261014T111253582634`, lens
6.05, no capture flags. The benchmark is in all 92. Leaving out the 19 second tag round stills
changes the rosette means by at most 3.5 mm² and the mean solid errors by at most 1.7 points.

**Method.** Fixed thresholds, nothing trained, picked on one probe still and not tuned against
the results (decisions): red in HSV (hue 0 to 8 or 170 to 180, saturation at least 120, value at
least 80), green by normalised excess green above 0.1 with green above red. Only colour inside
the benchmark's yellow base (its hull grown by 20 px) counts; tray tags masked from
`detect_tags` corners. Orientation from the largest rosette (NE); pieces go to their nearest
corner. Area = pixel count over the square of the calibration scale field's local px/mm at the
piece's centre (as `certainty_map.py`); the app has no pixel to mm homography. No height
correction.

**Rosettes.** Spread across all 92 stills (all slots and turns), SD as a share of the mean:
NE 1.5% (mean 1823.8 mm²), SE 1.9% (1123.6), NW 3.2% (619.4), SW 3.6% (298.2). Within 9 groups of
3 to 11 stills with nothing moved: 0.02% to 0.79%. Between slot means: NE 3.8%, SE 5.7%, NW 9.8%,
SW 13.1% (lowest to highest slot, as a share of the mean). All 4 below their upper limits in all
92 stills (they cover 25% to 51% of them). The true leaf area is not known, so this is
repeatability, not accuracy.

**Red solids** (known area, mean error, range over 92 stills): prism 51.6 mm², +39.4%, -14.7% to
+83.2%; circle 78.5 mm², -20.7%, -32.1% to -11.5%; sphere 61.5 mm², -16.4%, -23.0% to -9.4%;
cylinder 55.3 mm², +18.6%, -22.3% to +44.4%. Prism and cylinder are close in the middle slots
(North 3, North 4, South 3, South 4: -6.8% to +20.2%) and up to +75.5% at the row ends, where
their sides are seen as well as their tops; height alone predicts 1.7% to 2.2%. The flat circle
and the sphere read small in every slot. Likely cause, not measured: the red threshold leaves out
the blurred edge (cut-off hue 8, solids at hue 4, base at 27). Per slot table in NOTES.md.

**Visual check.** Aaron looked at all 92 overlays on 2026-10-15: masks, outlines and corner names
correct in every one. One person, one pass; confirms what was found and named, not the areas.

**Covers / does not cover.** The plastic benchmark on blue trays at tray-top height, one
calibration, one lens position, one day. Not real leaves, not other lighting, not the accuracy of
the rosette areas. The red solid errors mix edge pixels, sides seen at an angle and height, which
this round does not separate.

### 15.6 Round 1 review

Not yet written. Covers what was found, what surprised us, which step it sends work back to, and
the targets for round 2.
