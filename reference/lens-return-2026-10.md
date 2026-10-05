# Returning to the same lens position: does the measurement come back?

**Status:** run 1 done (2026-10-05). Runs 2 (app restart) and 3 (power cut) not yet done.

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

For scale: the validation bands for this setup are about ±2.0% to ±4.3% per slot, and a 0.1
change in lens position moves the central slots by about 1.2 points.

## What run 1 shows

- **The measurement came back.** After autofocus had moved the lens 4 times, driving it back to
  6.15 gave the same tag areas as before, within photograph-to-photograph noise: median change
  -0.03 points, spread 0.28 points (noise measured before: 0.27 to 0.46).
- **It stayed within a fraction of the validation band for an hour.** Over 60 minutes the median
  moved by +0.09 points and the largest slot median by +0.35 points (North 1; South 1 +0.31,
  both on the same table edge). The narrowest validation band for this setup is ±2.0%, so the
  largest change was under a fifth of it. The change was not still growing: +30 and +60 read
  the same (+0.09 median).
- **The 2026-10-01 drift was not repeated at this size.** That day the central ring moved 1.3
  points in 35 minutes after a lens move; here the same ring (1000 to 1500 px) stayed within
  0.21 points. Why the two days differ is not known; the lens position was 6.18 then and 6.15
  now, and the moves themselves were different.

In plain terms: for this disturbance, at this lens position, returning to the locked number was
enough. No new calibration or validation would have been needed.

## Limits of run 1

- One disturbance type (autofocus, then re-lock), one lens position (6.15), one hour, one day.
- How far autofocus moved the lens is not recorded (the log has the button presses, not the
  positions). The disturbance may have been small. A restart drives the lens through the same
  full route every time, so run 2 has a known disturbance.
- No control run without a lens move, so the small +0.09 shift over the hour cannot be split
  between the lens move and ordinary change over time (for example, temperature).
- An app restart and a power cut have not been tested. A restart uses the same lens drive, but a
  power cut also cools the camera and the focus mechanism, which may matter if the drift is
  thermal.
- Area only at tray-top height; plant height and segmentation add their own uncertainty.

## Next runs

1. **Run 2, app restart:** same method, the restart replacing the autofocus moves.
2. **Run 3, power cut:** same method, with the Pi powered off at the rig for long enough to
   cool (for example, 30 minutes), then on again.
3. **Control:** the same 60-minute series with nothing moved at all, to measure change over time
   alone.

If runs 2 and 3 match run 1, a restart during an experiment needs no new calibration, and the
measured shift (here up to 0.35 points) can be stated alongside the validation bands.

## Raw data

- Validation session `20261005T071549445423`, rounds 4 onward (`/var/lib/npec-rig/calibration/validations/`).
- Round responses and log: `/home/pi/scratch/lens-return-2026-10-05/`.
- Analysis script: `reference/lens-return-2026-10-analyse.py` (reads stored tag detections, changes
  nothing). Run from the repo with `PYTHONPATH=src .venv/bin/python <script>`.
