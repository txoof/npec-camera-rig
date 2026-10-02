# North 4 low reading: investigation record

NPEC camera rig, 2026-09-30 to 2026-10-01. Written for readers who are not imaging specialists.

All times are UTC, as the rig records them (local time is UTC+2), except where marked local.

## 1. The question

The rig measures area from a top-down photograph. Printed AprilTag targets of known size (30.0 mm
square, checked with callipers) are used to check how accurately it does that in each of the 12
tray positions ("slots", North 1 to 6 and South 1 to 6). Every target's measured area is compared
with its true area (900 mm²); the difference, in percent, is its "error".

Slot **North 4 reads low**: targets placed there measure smaller than they are. The table gives
North 4's steady reading (median over rounds) minus the median of all 12 slots, so sessions under
different calibrations compare on the same basis.

| Calibration | Validation sessions (3 or more counted rounds) | North 4 against the other slots |
|---|---|---|
| 20260930T094710 | 9 sessions, 2026-09-30 and 10-01 | -1.57 to -2.15 points in 8 of them; not distinct in 1 (20260930T113557, see 4.6) |
| 20261001T091727 (recalibrated from scratch) | 20261001T091851 | -1.82 points |

North 3, South 3 and South 4 (the other slots nearest the middle of the table) also read lower
than the outer slots. A spot reading about -3.2% near the table centre was also noted on
2026-09-29, under an earlier calibration.

## 2. How the rig turns pixels into millimetres

The calibration photographs about 30 targets on each tray and fits one smooth model of scale
across the image: in effect, a flat, possibly tilted, plane at tray height. That model can follow
a table that is tilted, but it cannot follow a bump, a dip, or any effect concentrated in one area
of the image. Whatever it cannot follow shows up as error in the affected slots. No lens model
(distortion correction) is used; this is deliberate, and one is only to be added when a
measurement shows a structured pattern the plane cannot follow.

## 3. What was tried, and what each showed

| # | Tried | Result | Ruled out? |
|---|---|---|---|
| 1 | Recalibrated from scratch | North 4 unchanged: -1.82 points against the other slots, inside the earlier range | Yes: not a bad calibration |
| 2 | Moved trays and sheets between rounds (every validation round shuffles them) | The low area stays at the same place in the image while the sheets move through it | Yes: not a particular sheet or tray |
| 3 | Sheet print size | Sheets checked with callipers; a deliberately mis-printed sheet (89%) was detected wherever it went | Yes |
| 4 | Tray height survey (string line over the tray tops, rolling tape) | North 4 and North 5 both 53 mm, yet read -1.07% and +0.90%. All 12 trays within 6 mm (50 to 56 mm), worth at most 0.9 points; North 4 would need to sit 10 to 14 mm low. The 0.145% per mm used here is measured: a 75 mm taller tray was predicted from the geometry to read 11.8% large and measured 11.2% to 12.0%. One point was measured per tray, at the middle of a tray edge; the low area sits at the trays' inner corners | Yes, at the points measured: not table sag or tray height |
| 5 | Corner tags (table edge markers, shown as stop-lights) | They do not enter the scale model at all. Current readings SW +0.1%, NE -0.4%, NW +1.2%, SE -1.2%: a plain tilt, all within tolerance | Yes |
| 6 | Light intensity at 12.5%, 25%, 50% of maximum, scene unchanged | Inconclusive: the camera's automatic exposure compensated (exposure 7119, 3377, 1714 µs), so the photographs were equally bright (paper white 216 to 220). It did measure repeatability: the same tag reads within 0.27 to 0.46 points between photographs (standard deviation) | Not tested |
| 7 | Focus (centre slightly out of focus) | The centre is the sharpest part of the image: see 4.2 | Yes |
| 8 | Reflection of the ceiling lights off the glossy toner | A flat mirror on the table shows the same reflection everywhere (the ceiling is evenly covered with LED strips), so nothing singles out the centre; and measuring the target edges independently of the detector gives the same low reading (4.4) | Yes |
| 9 | The target detector misplacing edges where the image is brighter | Same independent edge measurement: same low reading | Yes |
| 10 | Anything on the table (sheets, trays, surface, lighting) | A second camera (Canon) sees no low area at the same table spot (4.8) | Yes |
| 11 | Lens distortion | A one-term smooth model fits poorly (4.1), but a radial pattern explains about half of the target-to-target variation and repeats closely between two sessions (4.5, 4.6) | Not ruled out: see 5 |
| 12 | The camera being dropped (2026-09-30, about 08:27 UTC) | Photographs from 29 September, before the drop, at similar lens positions show a similar dip to the sweep after it (4.7, 4.9) | Not the cause, as far as the data show |
| 13 | Focus lens position | A sweep with nothing else changed: the dip deepens steadily as the lens position goes down (4.9) | No: this is the controlling variable |

The lighting is professional chamber lighting, independently verified as homogeneous. All sheets
are laser printed on matte paper.

## 4. Evidence gathered

From saved photographs only; the camera was not touched. Unless stated, from the three counted
rounds of validation 20261001T091851 (1064 target readings).

### 4.1 The low area is local and centred on the image centre

Median error by distance from the centre of the image (the image is 9152 x 6944 pixels):

| Distance from image centre (px) | Targets | Median error |
|---|---|---|
| 0 to 1000 | 21 | -3.55% |
| 1000 to 1500 | 131 | -1.78% |
| 1500 to 2000 | 165 | +0.20% |
| 2000 to 4500 | 735 | +0.15% to +0.93% |
| 4500 and beyond | 12 | -0.98% |

The error is concentrated within about 1500 px of the image centre. The low area falls on the
inner corners of North 3, North 4, South 3 and South 4, because the image centre lies in the gap
between the two rows of trays; North 4 reads worst because its sheet sits nearest that point. The
innermost band holds only 21 targets and the outermost 12, so their medians are the least certain.

The map `north4_tag_error_map.jpg` shows every target reading at its position (blue reads small,
red reads large): the blue cluster sits at the middle of the image.

### 4.2 Focus is best at the centre

Edge sharpness, measured as the distance over which a target's black edge goes from 10% to 90% of
its brightness step (smaller is sharper): 4.5 to 5.0 px near the centre, 5.6 to 5.9 px at the
outside. Sharpness barely relates to error (correlation -0.10).

### 4.3 The blacks are lifted at the centre, but this does not cause the low reading

| Distance from image centre (px) | Median error | Target black (grey level) | Paper white (grey level) | White / black |
|---|---|---|---|---|
| 0 to 1000 | -3.54% | 76 | 240 | 3.2 |
| 1000 to 1500 | -1.78% | 70 | 237 | 3.4 |
| 2500 to 4500 | +0.16% to +0.83% | 52 to 54 | 218 to 222 | 4.1 to 4.2 |

The centre is brighter and its black is lifted proportionally more than its white. Targets whose
black reads above 65 have a median error of -1.41%; all others read +0.15% to +0.59%. This first
looked like a cause. Section 4.4 shows it is not: the lifted blacks and the low readings are in the
same place, but the edges are not moved by the brightness.

### 4.4 An independent edge measurement gives the same low reading

On each side of every target, brightness profiles were taken across the edge at five points. The
edge was placed where brightness is halfway between the local black and white. This does not use
the target detector.

| Distance from image centre (px) | Detector error | Independent edge error |
|---|---|---|
| 0 to 1000 | -3.54% | -3.11% |
| 1000 to 1500 | -1.78% | -1.29% |
| 2500 to 4500 | +0.44% to +0.64% | +1.09% to +1.32% |
| Dip (within 1500 px, minus beyond 2500 px) | -2.58 points | -2.69 points |

The detector places every edge about 0.23 px inside the halfway point, by the same amount at
every distance from the centre. So the low reading is not a detector effect: targets near the
image centre really are imaged smaller. The independent method reads about 0.6 points higher
everywhere because of that constant 0.23 px; the calibration absorbs a constant offset.

### 4.5 A radial pattern explains about half of the target-to-target variation

How much of the target-to-target variation (standard deviation 1.42 points) each model of
"error as a function of distance from the image centre" explains:

| Model | Variation explained |
|---|---|
| One smooth term (r²) | 4% |
| Two terms (r² and r⁴), the shape of a "wavy" lens distortion | 36% |
| Three terms (r², r⁴, r⁶) | 42% |
| Any radial shape (median in each 250 px ring) | 57% |

Distance from the image centre accounts for about half of the target-to-target variation. The
low-order models explain less than the free ring fit because the central dip is steeper than they
can follow. The ring fit has 24 free values, so its 57% is somewhat optimistic; the 49% in 4.6
comes from a different fit (7 rings plus a tilted plane). This is a structured pattern, not random
scatter, but a specific distortion shape is not established.

### 4.6 The pattern repeats between days, with one exception

For three sessions, a tilted plane and a radial ring profile were fitted together, so that a
different table tilt cannot be mistaken for a radial change. Ring values are relative to the
2500 to 3500 px ring. The ± is the spread from resampling whole sheet placements (tags on one
sheet are not independent measurements); each session has 36 sheet placements, of which 5 to 10
touch the innermost ring and about 12 the next.

| Ring (px) | 20260930T101124 | 20261001T091851 | 20260930T113557 |
|---|---|---|---|
| 0 to 1000 | -4.44 ±0.50 | -4.32 ±0.26 | -2.26 ±0.12 |
| 1000 to 1500 | -2.58 ±0.21 | -2.45 ±0.23 | -0.77 ±0.12 |
| 1500 to 2000 | -0.45 ±0.11 | -0.45 ±0.12 | +0.81 ±0.13 |
| 2000 to 2500 | +0.33 ±0.12 | +0.41 ±0.10 | +0.99 ±0.17 |
| 3500 to 4500 | -0.14 ±0.13 | -0.31 ±0.15 | -0.26 ±0.15 |
| 4500 and beyond | -2.06 ±0.18 | -1.98 ±0.28 | -1.44 ±0.32 |

- **101124 and 091851 agree within 0.2 points in every ring**, within their uncertainty, although they used different
  calibrations, on different days, and the camera had been adjusted between them (the corner tags
  moved up to 87 px in the image). Lens position was 6.18 in every photograph.
- **113557 differs in the radial pattern itself, not only in tilt**: its central dip is about half
  as deep. It used the same calibration and nearly the same camera position as 101124 (corner tags
  within 6 px), 84 minutes later. The difference is well outside the uncertainty (in the 1000 to
  1500 px ring, -0.77 ±0.12 against -2.58 ±0.21). Its exposure was also identical in all three
  rounds (3637 µs), where the other sessions varied slightly. What else differed that day is not
  yet known.
- **Not explained by which sheets sat near the centre.** Two sheets that both measure 30.0 mm with
  callipers can differ by up to about 0.7% in area. The six printed pages carry different ID
  ranges, so each page can be traced. After removing the plane and the rings, every page's mean
  residual is within ±0.32 points in every session: no page reads consistently high or low.
- A fourth session, 20260930T142152, was left out: it contained the deliberately mis-printed
  sheet, which distorts the fit.

### 4.7 The depth of the dip varies between photographs

Every saved photograph from 2026-09-28 on (88 photographs, 76 usable) was fitted the same way as in
4.6, one photograph at a time, with any sheet reading more than 4 points off on its own left out
(the mis-printed sheets and the tall tray), and each photograph's recorded focus lens position was
added. The 1000 to 1500 px ring holds 22 to 63 targets in every photograph:

| Period (UTC) | Layout | Lens position | Ring 0 to 1000 px | Ring 1000 to 1500 px |
|---|---|---|---|---|
| 29 Sep 12:25 to 13:49 (before the drop) | 17 sheets | 6.24 | -2.4 to -3.1 | -0.5 to -0.9 |
| 29 Sep 14:34 to 14:37 (before the drop) | 12 trays | 6.36 | -1.0 to -1.7 | -0.2 to 0.0 |
| 30 Sep 09:47 to 10:13 | 12 trays | 6.18 | -4.0 to -5.0 | -2.45 to -2.97 |
| 30 Sep 11:22 to 11:24 | 12 trays | 6.43 to 6.44 | too few targets | +0.45 to +0.98 |
| 30 Sep 11:35 to 11:38 | 12 trays | 6.18, minutes after being at 6.44 | -2.1 to -2.4 | -0.63 to -0.93 |
| 30 Sep 14:19 to 1 Oct 11:31 | 12 trays | 6.18 | -3.5 to -5.2 | -1.8 to -3.1 |

The camera was dropped at about 08:27 UTC (10:27 local) on 30 September, so all the 30 September
rows above are after the drop. The windows with less dip were at higher lens positions. This
pointed to lens position, which the sweep in 4.9 then tested directly. The 28 September
photographs (a 19-sheet layout including the 96% sheets) are left out.

### 4.8 A second camera does not see it

The supervisor photographed the table on 2026-10-01 between 13:03 and 13:16 (the Canon's own clock) with a Canon EOS R5
Mark II and an RF 10-20mm lens at 18 mm (12 photographs, 8192 x 5464, taken at a slant, not
straight down). Each photograph was treated exactly like an Arducam photograph: a tilted plane
fitted to its own targets, then the residual of each target. Targets were placed in table
coordinates with the corner tags, so both cameras can be compared at the same spot on the table.

| Camera | Targets in the table region under the Arducam dip | Region minus the rest of the table |
|---|---|---|
| Arducam (2026-10-01 11:30 photograph) | 35 | -2.79 points |
| Canon, each of the 12 photographs | 26 to 36 | -0.01 to -0.48 points |

On the targets that could be matched one to one between the two cameras (up to 177 of 355 in the
first four Canon photographs; the sheets appear to have been moved after about 13:09), the Arducam
reads 1.90 points lower inside 1500 px of its image centre than beyond 2500 px; the Canon reads the
same targets only 0.26 lower. The two cameras do agree on which individual targets read somewhat
high or low elsewhere (correlation +0.5 per target), which is consistent with small real size
differences between printed targets. The Canon's scatter is also smaller (0.73 to 0.87 points,
against 1.33).

So the low area is not on the table: a different camera looking at the same spot does not see it.
It is in the Arducam camera.

### 4.9 Lens position sweep: the dip follows focus

On 2026-10-01 from 14:28 UTC, with the chamber closed and nothing on the table moved, the rig took
one photograph at each lens position, then returned to 6.18 twice. Every photograph recorded
exactly the lens position commanded. (An earlier attempt the same afternoon was invalid: a
software fault, since fixed, kept the lens at 6.10 after the first capture.)

| Lens position | Ring 0 to 1000 px | Ring 1000 to 1500 px | Targets found (of 355) | Edge rise (px, larger is softer) |
|---|---|---|---|---|
| 6.10 | -5.27 | -3.63 | 354 | 5.0 |
| 6.18 | -3.73 | -2.20 | 355 | 5.0 |
| 6.26 | -2.71 | -1.10 | 355 | 5.2 |
| 6.36 | -1.23 | -0.05 | 347 | 5.0 |
| 6.44 | -0.56 | +0.49 | 296 | 6.5 |

- **The dip follows the lens position, smoothly and in one direction**: about 1.2 points shallower
  per 0.1 step in the 1000 to 1500 px ring. With nothing else changed, this establishes lens
  position as the variable.
- **The positions with little dip are less sharp at tray height**: at 6.44, 59 targets could no
  longer be read and the edges are softer; 6.36 lost 8.
- **The 29 September photographs taken before the drop agree with this**: at 6.24 they read -2.4
  to -3.1 and -0.5 to -0.9, against -2.71 and -1.10 at 6.26 here; at 6.36, -0.2 to 0.0 against
  -0.05 here. The drop does not appear to have changed the relation.

This explains why the central error differs between setups: each experiment is focused at the
position that suits it, and the central error comes with that position. It is not a setting to
tune for accuracy; the focus point is chosen by whoever sets up the experiment (section 6).

Back at 6.18, the dip did not return to its first value, and kept getting shallower over time,
whichever side the lens came back from:

| Time (UTC) | Arrived at 6.18 from | Ring 1000 to 1500 px |
|---|---|---|
| 14:29 | 6.10 | -2.20 |
| 14:32 | 6.44 | -1.99 |
| 14:37 | (5 minutes later) | -1.45 |
| 14:47 | (15 minutes later) | -1.18 |
| 14:48 | 6.10 | -1.18 |
| 14:54 | (5 minutes later) | -1.02 |
| 15:04 | (15 minutes later) | -0.87 |

So at a fixed reported lens position the dip drifted by 1.3 points in 35 minutes, as if the
lens were slowly moving toward a higher position. What drives the drift (for example warming
of the camera or of the focus mechanism) is not known. The half-depth session 113557 fits this:
it was taken after the lens had been moved.

## 5. What the evidence supports

The low reading at North 4 is a real difference in how large things are imaged near the image
centre of the Arducam camera. A second camera looking at the same spot does not see it (4.8). It
is not the calibration, the sheets, the trays, the table height, the corner tags, reflection, or
the target detector.

Its depth is controlled by the focus lens position (4.9): the lower the position, the deeper the
dip, from about -3.6 points at 6.10 to none at 6.44 in the 1000 to 1500 px ring. In other words,
how the lens images the centre relative to mid-field changes as it is focused. The positions with
little dip are less sharp at tray height. At a fixed reported position the dip also drifts slowly
(1.3 points in 35 minutes after the lens was moved), so the lens does not stay exactly where it
reports. The drop does not appear to have changed this.

## 6. How the error is managed

The focus position is chosen by whoever sets up the rig and runs the experiment, for their setup.
The rig does not choose or recommend one. Its job is to reach the chosen position the same way
every time, and to measure and report honestly the error that comes with it. The cause is known
well enough for that: it is in the Arducam's focus mechanism, its size is set by the lens
position, and it changes when the lens is moved. No further investigation of the camera is
planned.

1. **One consistent way to drive the lens** (built 2026-10-01). Locking focus and restoring it after
   a restart both step the lens to 0.3 below the target, pause, set the target, and wait until the
   camera reports it there (up to 60 s; otherwise focus is not locked). Captures never move the
   lens. Checked on the rig: the lock survives a restart, the first capture after a restart is at
   the locked position, and a lock taken right after a capture waits for the camera (24 s) instead
   of recording a stale position. Two software faults found on the way were fixed: lens settings
   were ignored after any full-resolution capture until a restart, and the first capture after a
   restart would have used the default lens position.
2. **Calibrate and validate at the locked position.** The calibration is taken with focus locked,
   and validation refuses rounds whose lens position differs from the calibration's. The per-slot
   certainty map then states how far area can be trusted in each slot, including the central
   slots, from measured targets, for that setup.
3. **Validate again after anything moves the lens.** A move changes the central error, so a new
   lock means a new calibration and validation.

One decision remains for the project lead, and it is not needed to proceed: **the evidence gate
for lens modelling.** The pattern is structured and radial, but it depends on the lens position,
so any correction would belong to one locked position and would have to be re-measured after
every move. Validation already measures the error at that position.

## 7. Practical impact

Whatever the cause, the validation already measures it. In validation 20261001T091851 (current
calibration, no fault sheets), the per-slot certainty map gives North 4 the widest band: 95% of
targets within ±4.3%, then South 4 ±3.6% and North 3 ±3.2%, against ±2.0% to ±2.7% for the other
nine slots. Area measured in the middle of the table carries that wider stated uncertainty for
that setup; another setup focused elsewhere will have its own, measured the same way. Keeping focus
fixed matters: a 0.1 change in lens position moves the central
slots by about 1.2 points. Before 2026-10-01 a server restart moved the lens; it now drives it back
to the locked position and confirms it (section 6). Validation holds back rounds taken at a
different lens position from the calibration.

## 8. Draft conclusion, for Aaron to agree

The low reading at North 4 comes from the Arducam camera, not the table: targets within about
1500 px of its image centre are imaged up to about 4% smaller in area than targets in mid-field,
and a second camera photographing the same table does not see this. It is not caused by the
calibration, the sheets, the trays, the table height, the corner tags, reflection, the target
detector, or the camera being dropped. Its size is set by the focus lens position (about -3.6
points at 6.10, -2.2 at 6.18 and none at 6.44 in a sweep with nothing else changed) and it changes
when the lens is moved. The focus position is the experimenter's choice for their setup. The rig
now drives the lens to the locked position the same way every time and confirms it, and validation
measures the resulting error per slot at that position, so area measured in the central slots
carries a stated, measured uncertainty rather than a hidden one.

## 9. Recommendations for moving forward

1. **Review and merge the camera changes first.** They fix faults that affected every session so
   far: after the first full-resolution capture the lens ignored every later setting, and a restart
   lost the focus lock. They are on branch `m2-validation-drift` with the validation work, need a
   code review, and are merged only with the project lead's approval.
2. **Recalibrate and validate the current setup under the new lens drive.** The existing
   calibrations were taken before it existed. One calibration and one validation (3 rounds) give
   the certainty map for the current setup.
3. **Make validation part of every setup.** After calibration, the setup pages and the site menu
   show whether the current calibration has been validated and whether it was consistent, and the
   calibration wizard leads on to validation. Shown as a status with an explicit override, not a
   hard block. This is the next planned slice.
4. **Treat a focus change as ending the current validation.** When focus is unlocked or the lens
   position differs from the calibration's, the pages say plainly that measurements are no longer
   covered by a validation, until the setup is recalibrated and validated. Validation rounds already
   do this; captures and measurements should too.
5. **Store with every plant measurement the calibration, the locked lens position and the
   validation it was taken under, and report each area with the certainty band of its slot.** This
   belongs in the M3 storage design, so that every number carries how far it can be trusted. How
   the band is used, and what it does and does not cover, is set out in section 10.
6. **Let validation watch for drift.** The slow drift seen at a fixed lens position is exactly what
   the round-to-round check flags. If validation reports a slot that is not consistent while
   nothing was moved, look at the camera again then; otherwise no further camera work.
7. **Write a one-page operator guide** for the scientists running experiments: focus for your
   setup, lock focus, calibrate, validate, and redo all three after any refocus; and, briefly, why
   the central slots may carry a wider uncertainty with this camera.
8. **Close the investigation scripts as a record, not as code.** They stay in `~/scratch/` with this
   report; none of the exploratory analysis goes into the rig's source.

## 10. Using the per-slot uncertainty with plant data

This section is the reference for how a validation result is attached to plant measurements.

**What validation provides.** For each slot (table position North 1 to 6, South 1 to 6), a
validation gives a number such as "North 2: ±2.1%". Every area measured on that slot, under the
same calibration and the same focus lock, is recorded with that number as its uncertainty, for the
researcher to carry into their analysis.

**1. It belongs to the slot, not to the tray.** Trays move between positions. The number describes
the table position, so a tray sitting on North 2 when it is photographed gets North 2's number,
and the same tray photographed later on South 5 gets South 5's. The numbers hold only for the
calibration and focus lock they were measured under. After a refocus or a recalibration, the
setup is validated again and the new numbers apply from then on.

**2. It is a 95% band, not a standard deviation.** "±2.1%" means that 95% of the reference targets
measured on that slot read within 2.1% of their true area. It is not one standard deviation; if the
errors were normally distributed it would be about two. The data column should say this, for
example "area uncertainty (95%): ±2.1%", so that it is not mistaken for a standard deviation in
later statistics.

**3. It covers flat objects at tray-top height only.** The reference targets lie flat on the tray,
so the number is the uncertainty of the camera and calibration for a flat object at that height.
It does not include:

- **Height above the tray.** Measured area changes by about 0.145% per mm of height (measured on
  the rig, section 3, row 4): a leaf 50 mm above the tray top reads about 7% larger than the same
  leaf at tray-top height. Plants stand above the tray top, so this applies to every plant.
- **Segmentation.** Deciding which pixels are plant adds its own error, typically several percent
  at the plant's edges.

So the slot number is the lower limit of the uncertainty of a plant area, not all of it. The
record should state what it covers: "camera and calibration, flat object at tray-top height".

**4. Part of it could be corrected; for now it is recorded, not corrected.** Each slot's number
mixes two things:

- **A steady offset**: the slot reads consistently a little high or low. In validation
  20261001T091851, for example, North 2's median reading was +0.82% and North 4's was -1.07%.
- **Scatter** around that offset, from target to target and photograph to photograph.

The offset is measured, so subtracting it would be a correction based on measurement, which the
project allows, and it would narrow the bands. The scatter cannot be corrected. The current
choice is to record the uncertainty and not correct for the offset: simpler, and easier to defend.
Correcting the offset can be decided later; if it is done, the corrected values and the narrower
bands must be recorded as such.

**Example of one recorded measurement**

| Field | Example |
|---|---|
| Capture | 2026-10-01/091930_507614 |
| Tray | (tray tag ID) |
| Slot at capture | North 2 |
| Plant area | (measured, mm²) |
| Area uncertainty (95%), camera and calibration, flat at tray-top height | ±2.1% |
| Calibration | 20261001T091727374749 |
| Focus lock (lens position) | 6.18 |
| Validation | 20261001T091851502649 |

## Files

All in `~/scratch/`: `north4_checks.py` (brightness and per-sheet gradients), `radial_and_sharpness.py`
(4.1, 4.2; rows in `radial_and_sharpness.csv`), `black_level_test.py` and `black_within_band.py`
(4.3; rows in `black_level_test.csv`), `edge_test.py` (4.4), `radial_r4_fit.py` (4.5),
`session_compare.py` and `plane_plus_radial.py` (4.6), `intensity_test.py` (row 6 of section 3), `canon_recon.py`, `canon_compare.py` and `canon_region.py` (4.8),
`drop_timeline.py` and `timeline_lens.py` (4.7; rows in `drop_timeline.csv`), `run_sweep.py`, `sweep_check.py` and `sweep_log.txt` (4.9), `slot_offset_noise.py` and `session_results.py` (sections 1 and 7), `north4_tag_error_map.jpg`.
