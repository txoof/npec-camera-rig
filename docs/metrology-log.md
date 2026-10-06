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
those same tags.

**The band.** For each tray slot, the band is the 95th percentile of the absolute area error of
all tags in that slot over all counted rounds: 95% of the tags read within that distance of
their true area. Fewer than 10 tags in a slot gives "not measured" (**decision**).

**Current bands** (session `20261005T141310628479`, calibration `20261005T141101923639`, lens
6.27, 3 rounds at 14:13, 14:14 and 14:15 UTC, 92% to 96% of tags moved, 85 to 90 tags per slot):

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
0.96). So whether a sweep to both ends improves sharpness is still not known. Raw data:
`/home/pi/scratch/lens-coldstart-2026-10-06/` (`log.txt`, `log3b.txt`, `watch3b.txt`, scripts).

Detailed results: `reference/lens-return-2026-10.md`.

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
