# Returning to the same lens position: does the measurement come back?

**Status:** run 1 and the control done (2026-10-05). Runs 2 (app restart) and 3 (power cut) not yet done.

## Why this matters

The rig measures area at one locked focus position, and calibration and validation state how far
that area can be trusted at that position. If the Pi loses power or restarts during an
experiment, the app drives the lens back to the locked position. If the measurement does not
come back to the same values, every restart would need a new calibration and validation, which
would interrupt the experiment. This test measures whether it comes back.

What was already known (`reference/arducam-central-error-2026-10.md`, section 4.9):

- The rig drives the lens to the locked position one consistent way (0.3 below the target, a
  pause, then the target) and waits until the camera reports it there. A restart uses the same
  drive.
- The reported lens position is reached exactly. What was not known is whether the image scale
  returns with it: on 2026-10-01, after the lens was moved and returned to 6.18, the central dip
  read 1.3 points differently over the next 35 minutes.
- The same tag reads within 0.27 to 0.46 points between photographs with nothing changed.

## Method

The table is not touched between photographs, so each tag can be compared with its own earlier
reading. That removes sheet, tray and position differences and leaves only the camera.

1. **Baseline:** calibration at lens 6.15 (2026-10-05 07:11:57 UTC), then three validation rounds
   07:16 to 07:17 UTC. The last round (07:17:42 UTC) is the reference for every later
   comparison.
2. **Disturbance:** the lens is moved away from 6.15 and driven back.
   - Run 1: autofocus run 4 times (the lens moved to wherever autofocus put it), then lens set to
     6.15 and Lock focus, finished by 07:34:41 UTC.
   - Run 2: app restart (planned).
   - Run 3: power cut at the rig (planned).
3. **Rounds:** one photograph at +0, +15, +30 and +60 minutes after the lock, taken through the
   app's own validation round, with nothing moved. The app holds them back as "not moved"; they
   are not counted into the validation, but their measurements are stored.
4. **Comparison:** every calibration tag matched to itself (same ID, within 20 px) in the
   reference round. Reported: the median change in area error and its spread, by distance from
   the image centre (the rings used in the central-error record), and per tray slot.

Times are UTC. The chamber's local time is UTC+2.

## Results, run 1 (autofocus moved the lens, re-locked at 6.15)

Change in area error against the reference round, in points of area (%):

| Round | Time (UTC) | Tags matched | Median change | Spread (SD) | Ring 1000 to 1500 px | Largest slot median |
|---|---|---|---|---|---|---|
| +0 min | 07:35:00 | 355 of 355 | -0.03 | 0.28 | -0.04 (41 tags) | -0.12 (North 3) |
| +15 min | 07:49:59 | 355 of 355 | +0.00 | 0.30 | -0.06 (41 tags) | +0.10 (South 6) |
| +30 min | 08:05:04 | 354 of 355 | +0.09 | 0.34 | -0.21 (41 tags) | +0.33 (North 1) |
| +60 min | 08:35:04 | 354 of 355 | +0.09 | 0.30 | -0.09 (41 tags) | +0.35 (North 1) |

For scale: this setup's validation (session `20261005T071549445423`, lens 6.15, 3 rounds, 85 to
90 tags per slot) gives bands from ±1.43% (North 5) to ±3.36% (North 4); a band is the range
that 95% of a slot's tags fall within. A 0.1 change in lens position moves the central slots by
about 1.2 points.

## What run 1 shows

- **The measurement came back.** After autofocus had moved the lens 4 times, driving it back to
  6.15 gave the same tag areas as before, within photograph-to-photograph noise: median change
  -0.03 points, spread 0.28 points (noise measured before: 0.27 to 0.46).
- **It stayed within a small fraction of each slot's band for an hour.** Over 60 minutes the
  median moved by +0.09 points and the largest slot median by +0.35 points (North 1, band
  ±2.12%; South 1 +0.31, band ±1.89%; both on the same table edge). Measured against each slot's
  own band, the largest change was about one sixth of it (North 1 0.35 / 2.12, South 1
  0.31 / 1.89). The slot with the tightest band, North 5 (±1.43%), moved +0.11. The change was
  not still growing: +30 and +60 read the same (+0.09 median).
- **The 2026-10-01 drift was not repeated at this size.** That day the central ring moved 1.3
  points in 35 minutes after a lens move; here the same ring (1000 to 1500 px) stayed within
  0.21 points. Why the two days differ is not known; the lens position was 6.18 then and 6.15
  now, and the moves themselves were different.

In plain terms: for this disturbance, at this lens position, returning to the locked number was
enough. No new calibration or validation would have been needed.

## Control: nothing moved, lens untouched

The same method with no lens move, to measure how much the readings change over time on their
own. Focus stayed locked at 6.15 throughout (last lens move 07:34 UTC). Two series:

**Control A, 09:02 to 10:02 UTC (disturbed).** A colleague worked in the chamber. Between 08:35
and 09:02 one sheet's worth of tags (31) moved, and 23 tags were hidden until some time between
09:32 and 10:02; the door was opened before 10:00 UTC. The camera and table were not moved: all
332 visible tags kept their positions. Only those 332 are compared, against the 09:02 photograph.

| Round | Time (UTC) | Tags matched | Median change | Spread (SD) | Ring 1000 to 1500 px | Largest slot median |
|---|---|---|---|---|---|---|
| +15 min | 09:17:28 | 332 | +0.17 | 0.36 | -0.19 (31 tags) | +0.31 (South 2) |
| +30 min | 09:32:33 | 332 | -0.01 | 0.39 | +0.01 (31 tags) | +0.55 (South 3) |
| +60 min | 10:02:32 | 332 | +0.17 | 0.31 | -0.05 (31 tags) | +0.38 (North 1, North 6) |

**Control B, 10:02 to 10:47 UTC (undisturbed, Aaron).** Against the 10:02 photograph:

| Round | Time (UTC) | Tags matched | Median change | Spread (SD) | Ring 1000 to 1500 px | Largest slot median |
|---|---|---|---|---|---|---|
| +15 min | 10:17:48 | 355 of 355 | -0.06 | 0.34 | +0.21 (40 tags) | -0.28 (North 6) |
| +30 min | 10:32:47 | 355 of 355 | -0.03 | 0.30 | +0.04 (40 tags) | -0.12 (South 3) |
| +45 min | 10:47:51 | 355 of 355 | -0.10 | 0.43 | +0.26 (41 tags) | -0.52 (North 1) |

**What the control shows**

- With nothing moved at all, the readings still change over time: median up to ±0.17 points,
  central ring up to ±0.26 points, single slots up to 0.52 points (North 1, about a quarter of
  its ±2.12% band). The changes go up and down; they do not grow steadily.
- Run 1's changes after the lens move (median +0.09, ring -0.21, largest slot +0.35) are inside
  this range. So the lens move and return added nothing this method can detect beyond ordinary
  change over time.
- North 1, at the west edge of the image, changed most in run 1 and in both control series.
  Why is not known.
- The cause of the change over time is not known (for example temperature, light, or the
  camera's automatic exposure).


- One disturbance type (autofocus, then re-lock), one lens position (6.15), one hour, one day.
- How far autofocus moved the lens is not recorded (the log has the button presses, not the
  positions). The disturbance may have been small. A restart drives the lens through the same
  full route every time, so run 2 has a known disturbance.
- The control (above) was run once, partly disturbed, on the same day.
- An app restart and a power cut have not been tested. A restart uses the same lens drive, but a
  power cut also cools the camera and the focus mechanism, which may matter if the drift is
  thermal.
- Area only at tray-top height; plant height and segmentation add their own uncertainty.

## Next runs

1. **Run 2, app restart:** same method, the restart replacing the autofocus moves.
2. **Run 3, power cut:** same method, with the Pi powered off at the rig for long enough to
   cool (for example, 30 minutes), then on again.

If runs 2 and 3 match run 1, a restart during an experiment needs no new calibration, and the
ordinary change over time (here up to 0.52 points in one slot, about a quarter of its band) can be
stated alongside the validation bands.

Correction, 2026-10-05: the first version of this report compared the shifts with bands of
±2.0% to ±4.3%. Those are the bands of the 2026-10-01 validation at lens 6.18, not this setup's.

## Raw data

- Validation session `20261005T071549445423`, rounds 4 onward (`/var/lib/npec-rig/calibration/validations/`).
- Round responses and logs: `/home/pi/scratch/lens-return-2026-10-05/` (run 1) and
  `/home/pi/scratch/lens-control-2026-10-05/` (control).
- Analysis script: `reference/lens-return-2026-10-analyse.py` (reads stored tag detections, changes
  nothing). Run from the repo with `PYTHONPATH=src .venv/bin/python <script>`.
