# Measurement accuracy of the NPEC camera rig

**Status:** first draft, 2026-10-05. Kept current as findings come in (CLAUDE.md, *Write up every
measurement*). Numbers marked **decision** are settings chosen by the project, not measurements.
Section 10 lists inconsistencies between project files that still need checking.

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
| Scale at tray height | 4.85 px/mm (mean over the image) | Today's calibration fit, 355 tags | 2026-10-05 | About 0.21 mm per pixel; earlier calibrations 4.5 to 4.8 |
| Height above tray top | about +0.145% area per mm | A 75 mm taller tray in 3 slots read 11.2% to 12.0% large; predicted 11.8% | 2026-10-01 | Bands cover flat objects at tray-top height only. Plant height adds to the uncertainty (section 7) |
| Perspective across the table | corrected by the scale field; positions mapped with a four-corner homography | Saved calibration frames | 2026-09-22 | Perspective within the table plane is modelled; lens distortion is not (section 9) |

## 5. Calibration

Today's calibration (2026-10-05 07:11:57 UTC, lens position 6.15, 30.0 mm tags): scale field
residual 0.52% (standard deviation of the tags' scale about the fitted field).

| Quantity | Value | Basis |
|---|---|---|
| Fitted scale field | a tilted plane over the image | **Decision**, simplest shape for a camera looking down at a slight angle |
| Local uncertainty | spread of the 5 nearest tags' residuals | **Decision** (k = 5); heatmap uses k = 40, chosen by comparing 5, 15, 40, 80, 150 on 352 tags |
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

**Today's bands** (session `20261005T071549445423`, lens 6.15, 3 rounds, 85 to 90 tags per slot):

| Slot | Band | Median error | Slot | Band | Median error |
|---|---|---|---|---|---|
| North 1 | ±2.12% | +0.13 | South 1 | ±1.89% | -0.01 |
| North 2 | ±1.94% | +0.71 | South 2 | ±1.63% | +0.45 |
| North 3 | ±2.69% | -0.18 | South 3 | ±2.25% | +0.52 |
| North 4 | ±3.36% | -0.48 | South 4 | ±2.38% | +0.38 |
| North 5 | ±1.43% | +0.00 | South 5 | ±1.51% | +0.09 |
| North 6 | ±2.98% | -0.53 | South 6 | ±1.78% | +0.04 |

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
| App restart | not yet measured (the lens is driven back and confirmed; whether area returns is untested) | | |
| Power cut | not yet measured | | |
| Two calibrations in a row | scale fields agreed within 0.02% to 0.16% | 332 and 340 tags, lens moved away and back, 2026-09-25 | Before the current lens-drive method |

On 2026-10-05, the change after moving the lens and driving it back was inside the ordinary change
over time measured by the control, so the return itself added nothing detectable. The 2026-10-01
drift (1.3 points) was about 5 times larger than anything seen on 2026-10-05. The reason is not
known.

## 9. Techniques deliberately not used, and what would justify them

| Technique | Adopt when | Evidence so far |
|---|---|---|
| Lens distortion model (intrinsic calibration) | Errors are structured, worse toward the corners, not random | Radial fit R² 0.33 to 0.45 on repeat runs (2026-09-22); undecided |
| Correction for height above the plane | A measured depth source exists | None |
| Orthophoto, second camera | A second viewpoint exists, and in-plane accuracy proves insufficient | Canon used once, as a check only |
| Learned tray identification | Tag identity measurably fails often enough to matter | Not measured |

## 10. Not yet measured, and open inconsistencies

**Acceptance tests not yet run** (PLAN.md M2): two-height test, tape-measure check within 2%, roll
of about 5° read as about 5°, honesty plot at 6 positions. Restart and power-cut repeatability
(section 8).

**Inconsistencies found between project files, to be checked and resolved:**

1. Median-movement limit: 1.5 points in TODO.md, 2.5 in the code.
2. Calliper tolerance: ±0.1 mm (CLAUDE.md) and "within 0.5 mm" (an older TODO.md note); calliper
   date 2026-09-29 and 2026-09-21.
3. Camera height: "not yet measured" and 1482 mm in different TODO.md notes; no method recorded.
4. Tray height: about 100 mm in some notes, a survey of 50 to 56 mm in another (the reference
   point of the survey is not stated).
5. Central error size: "up to about 4%" (CLAUDE.md) against ring values down to -5.27 at 6.10 in
   the investigation.
6. Image width: 9152 px (configuration) and 9248 px (hardware probe, sensor size).

## 11. Terms

- **Area error:** (area read − true area) / true area, in percent.
- **Point:** a difference between two percentages (1.00% to 1.03% is 0.03 points).
- **Median:** the middle value when sorted; not pulled by a few odd values.
- **Standard deviation (SD):** how far values typically sit from the middle. About 2 in 3 values
  lie within one SD, about 19 in 20 within two.
- **95th percentile, band:** the distance from the true value that 95% of tags fall within.
- **Lens position:** the focus setting reported by the camera (dioptres).
