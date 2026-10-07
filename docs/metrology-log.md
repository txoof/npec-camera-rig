# Metrology log of the NPEC camera rig

This is the log: every measurement, test method and result, with its source. For the case that
these measurements can be trusted, read `docs/measurement-trust.md` first.

**Status:** first draft, 2026-10-05. Kept current as findings come in (CLAUDE.md, *Write up every
measurement*). Numbers marked **decision** are settings chosen by the project, not measurements.
Section 11 lists inconsistencies between project files that still need checking. Section 9
holds the M2 physical acceptance tests, run 2026-10-05.

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
| Calibration tag side | 30.0 ± 0.1 mm (readings X 30.10, 30.11, 29.96; Y 30.04, 29.96, 29.94; mean 30.018) | Callipers, 6 readings, one print run | 2026-09-29 | That print run only. Every new print is measured again. ±0.1 mm on 30 mm is about ±0.67% in area |
| Corner tag side | 50.02 mm (mean) | Callipers | 2026-09-29 | Corner tags are used for the rig health check (tripwire) and table view, not for area |
| Sheet scale bars | 179.93 and 180.03 mm (nominal 180) | Callipers, 2 bars | 2026-09-29 | Confirms the sheets printed at 100% scale |
| Reference tag 500 side (60 mm, 36h11 ID 500, fixed at the north table edge) | 60.06 mm mean, SD 0.04 (Y 60.07, 60.05, 60.10, 60.05; X 60.01, 60.05, 60.00, 60.13) | Callipers, 8 readings, remeasured with care | 2026-10-06 | Supersedes a first set the same day (59.58 to 60.26, mean 59.94). Placed 2026-10-06 at the supervisor's suggestion as a static target |
| Calliper resolution trusted | 0.1 mm | **Decision** | | Readings are not used beyond 0.1 mm |
| Sheet-to-sheet difference | up to about 0.7% in area between sheets that both measure 30.0 mm | Fit residuals, 6 pages, 3 sessions | 2026-09-30 to 10-01 | `reference/arducam-central-error-2026-10.md` |

Why tag size matters most: on the previous rig, trusting the 30 mm printed on the box (the tags
measured 29.3106 mm) caused about 4.7% area error, larger than any other source. The lesson is to
measure every printed sheet.

## 4. Camera and geometry

| Quantity | Value | How measured | Date | Notes |
|---|---|---|---|---|
| Image size | 9152 × 6944 px | Camera configuration | | Arducam 64MP |
| Scale at tray height | 4.85 px/mm (at the image centre) | Calibration fit, 355 tags, 14:11 UTC calibration | 2026-10-05 | About 0.21 mm per pixel; earlier calibrations 4.5 to 4.8 |
| Scale on the table surface | 4.52 px/mm (at the image centre), 6.79% below tray height in length, 15.1% in area | Calibration fit, 355 tags on the table, same camera position | 2026-10-05 | At 0.145% of area per mm this corresponds to about 100 mm of height (derived, not taped) |
| Height above tray top | about +0.145% area per mm | A 75 mm taller tray in 3 slots read 11.2% to 12.0% large; predicted 11.8% | 2026-10-01 | Bands cover flat objects at tray-top height only. Plant height adds to the uncertainty (section 7) |
| Perspective across the table | corrected by the scale field; positions mapped with a four-corner homography | Saved calibration frames | 2026-09-22 | Perspective within the table plane is modelled; lens distortion is not (section 10) |

## 5. Calibration

Current calibration (`20261005T141101923639`, 2026-10-05 14:11 UTC, lens position 6.27, 30.0 mm
tags, 355 tags, 4 corner tags): scale field residual 0.52% (standard deviation of the tags' scale
about the fitted field), holdout coverage error 0.4%.

It replaced the 07:11 UTC calibration (lens 6.15, also 0.52%), which no longer fitted after the
camera was knocked and re-framed in the roll test (section 9.3).

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

**Current bands** (session `20261005T141310628479`, calibration `20261005T141101923639`, lens
6.27, 3 rounds at 14:13, 14:14 and 14:15 UTC, 92% to 96% of tags moved, 85 to 90 tags per slot;
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

One photograph per position, 2026-10-01, nothing else changed. On average about 1.2 points per 0.1
of lens position. The focus position is the experimenter's choice; the rig does not tune it for
accuracy. Validation measures the resulting error per slot, which is why central slots have wider
bands.

**Plant height.** About +0.145% area per mm above the tray top (section 4). Not included in the
bands.

**Segmentation** (separating plant from background). Not yet measured on this rig. Expected to be
several percent. Measured at milestone M5.

## 8. Repeatability and stability

| Quantity | Result | How measured | Date |
|---|---|---|---|
| Photograph-to-photograph noise | per-tag standard deviation 0.27 to 0.46 points | Repeated photographs, nothing changed (3 light levels, auto-exposure compensating) | 2026-10-01 |
| Lens moved and driven back to the same position | median change -0.03 points, spread 0.28, 355 of 355 tags; over 60 min largest slot change +0.35 points (about 1/6 of that slot's band) | Autofocus moved the lens, re-locked at 6.15, photographs at +0, +15, +30, +60 min, each tag compared with itself | 2026-10-05, `reference/lens-return-2026-10.md` |
| Drift at a fixed lens position after moves | central ring changed 1.3 points in 35 min | Lens sweep then return to 6.18 | 2026-10-01 |
| Change over time with nothing moved (control) | over 45 to 60 min: median within ±0.17 points, central ring within ±0.26, single slots up to 0.52 (about 1/4 of that slot's band); goes up and down, not a steady drift | Same method, lens untouched, two series (one partly disturbed by people in the chamber) | 2026-10-05, `reference/lens-return-2026-10.md` |
| One photo a minute for 2 hours, no reopen, lens locked (run 3j) | a repeating cycle of about 19 minutes: median swings by about 0.35 points (-0.08 to +0.33 against the first photo), largest slot 0.62; no drift (each cycle returns to the same low point); sharpness rises and falls with it; follows the chamber's air temperature (19.8 to 20.3 °C, every 19 min, correlation 0.84) and humidity cycle | Plain photos through the app, section 8.1 run 3j, compared with the chamber's 1-minute log | 2026-10-06 |
| App restart | right after: median +0.08 and +0.09 points (two attempts), 355 of 355 tags; over 60 min median within ±0.13, largest slot -0.29 (about 1/6 of its band); inside the control range | Server killed and restarted, lens driven back to 6.15 at start-up; repeat-photograph test (section 8.1) | 2026-10-05, `reference/lens-return-2026-10.md` |
| Power cut (cold start) | right after: median -1.73 points, 291 of 354 tags found, central slots blurrier; +15 min -0.41, +30 -0.38, +60 -0.14 (largest slot -0.62); recovers with no lens move | Pi off about 30 min, camera not opened until the run; repeat-photograph test (run 3) | 2026-10-06 |
| Two calibrations in a row | scale fields agreed within 0.02% to 0.16% | 332 and 340 tags, lens moved away and back, 2026-09-25 | Before the current lens-drive method |

On 2026-10-05, the changes after moving the lens and driving it back (run 1) and after an app
restart (run 2) were inside the ordinary change over time measured by the control, so neither
added anything detectable. The 2026-10-01
drift (1.3 points) was about 5 times larger than anything seen on 2026-10-05. The reason is not
known.

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

**Height correction.** The tape lay on the tray lips, about 10 mm above the sheets. The measured
height effect, 0.145% per mm, is for area; for a length it is half, about 0.072% per mm. 10 mm is
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
   may not be the actual one. Tracked as a bug, not a measurement.

**Inconsistencies found between project files, to be checked and resolved:**

1. Median-movement limit: 1.5 points in TODO.md, 2.5 in the code.
2. Calliper tolerance: ±0.1 mm (CLAUDE.md) and "within 0.5 mm" (an older TODO.md note); calliper
   date 2026-09-29 and 2026-09-21.
3. Camera height: "not yet measured" and 1482 mm in different TODO.md notes; no method recorded.
4. Tray height: about 100 mm in some notes, a survey of 50 to 56 mm in another (the reference
   point of the survey is not stated). The 2026-10-05 two-height test implies about 100 mm from
   table surface to tray top (derived from scale, not taped), matching the 100 mm notes.
5. Central error size: "up to about 4%" (CLAUDE.md) against ring values down to -5.27 at 6.10 in
   the investigation.
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
