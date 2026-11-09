# Why the rig's area measurements can be trusted

**Status:** 2026-10-14. The camera was replaced on 2026-10-07 (old SN000, new SN001); the current
calibration and bands are SN001's, made 2026-10-14 at lens 6.05. The M2 physical acceptance tests
were run on SN000 on 2026-10-05 and repeated on SN001 from 2026-10-12 to 10-14
(`docs/metrology-log.md`, section 14): the repeat validation on another day, the tape, the two
calibrations with a cold start between them, the two-height and the roll tests passed; a knock
was detected but read DRIFT, not FAIL, and was signed off with a covered-corner-tag check. The check of the
calibration's own uncertainty claim failed, so that claim is no longer used (see *A check on
placements the calibration did not use, which sets the band*). Which results were repeated on SN001 is listed in
`docs/metrology-log.md`, section 13. The evidence for every number here, with its source, is in
`docs/metrology-log.md`.

## The claim

The rig photographs plant trays from above and reports, for each tray slot, an area in mm² and a
band: the range within which that area can be trusted.

The band has a precise meaning. **For flat objects at tray-top height, at the rig's locked focus,
95% of measured test targets in that slot read within the band of their true area.** In the
current setup (replacement camera, 2026-10-08, lens position 6.04) the bands run from ±1.3%
(South 5) to ±2.7% (South 4). The camera used before it (2026-10-05, lens 6.27) gave ±1.58% to
±2.93%, and an earlier setup that day (lens 6.15) ±1.43% to ±3.36%.

This document explains why that claim holds, and the steps taken to make it hold. Each step says
what could go wrong, what the rig does about it, and the evidence.

## The approach: measure, do not assume

The rig's accuracy is never worked out from a model of the camera or lens. It is measured, by
photographing printed targets of known size and checking how far the rig's readings of them are
off.

This was a deliberate choice. Three earlier attempts at this project modelled the camera (lens
distortion, uncertainty propagation) and never produced a working application. The rule since
then: if a number cannot be shown with a ruler, a printed target or a repeated photograph, it is
not used.

## A known reference

**What could go wrong.** The whole measurement rests on knowing the true size of the targets. A
target that is not the size it is believed to be shifts every area by the same proportion, and
nothing else in the system would notice.

**What the rig does.** Every printed batch of targets is measured with callipers, and the measured
size, not the printed label, is used.

**Evidence.**

- The current 30 mm tags measure 30.0 ± 0.1 mm (NEIKO callipers, 3 tags measured across and down,
  6 readings, mean 30.018 mm, 2026-09-21). The sheets' 180 mm scale bars measure 179.93 and
  180.03 mm (mean of 3 readings on each of 2 sheets), confirming they printed at full scale.
- ±0.1 mm on a 30 mm side is about ±0.67% in area, the limit of what the callipers can confirm.
- On the previous rig, the tags labelled 30 mm actually measured 29.3106 mm. Trusting the label
  caused about 4.7% area error, the largest single error that rig had. On 2026-09-29 a sheet
  printed at 96% scale was found mixed in with good sheets. Both were caught only by measuring.

## Calibration at the experiment's own focus

**What could go wrong.** The camera sees things nearer the lens as larger, and the focus setting
changes how large things look, especially near the image centre. A scale taken from one place
or one focus setting does not hold everywhere.

**What the rig does.** The experimenter chooses the focus and locks it. With focus locked and all
4 corner tags visible, the rig photographs calibration sheets spread across every tray. Each tag
gives the scale (pixels per millimetre) at its own position, and a smooth scale field is fitted
across the image. Area is then pixels divided by the square of the local scale.

**Evidence.** The current calibration (replacement camera, 2026-10-08, lens 6.04, 355 tags):
scale 4.86 px/mm on average (about 0.21 mm per pixel), and the tags sit within 0.50% of the fitted
field (standard deviation). The old camera's last calibration (lens 6.27) gave 0.52%. Calibration refuses to run without a lock and all 4 corner tags, unless the operator
overrides it.

**One calibration covers every tray height.** Calibrations with the sheets on the table surface
and on the trays (about 100 mm higher) gave the same shape of scale field within 0.16 points, below
either calibration's own residual. A change of tray height changes the overall scale (about
0.145% of area per mm), but not the shape.

## A check on placements the calibration did not use, which sets the band

**What could go wrong.** A calibration always fits the targets it was made from. That says nothing
about how well it measures something else, somewhere else.

**What the rig does.** Validation tests the calibration on placements it was not made from. The
operator moves each sheet to a different tray, and the rig photographs again; this is repeated 3
times. A round counts only if at least half the tags actually moved, so the same layout is never
counted twice. The calibration photograph itself is never used. In each slot, the band is the
distance from the true area that 95% of the tags fall within, over all rounds. Validation is
independent of the calibration photograph, not of the printed tags: it checks against the same tag
size the calibration used (metrology-log section 12, *Labels*). The next section covers that gap.

**Evidence.** The current validation (SN001, 2026-10-14, lens 6.05): 3 rounds spread over 33.5
minutes, 64% to 84% of tags moved each round, 85 to 90 tags per slot, bands ±1.3% to ±2.6%. The
previous SN001 validation (2026-10-08, lens 6.04) gave ±1.3% to ±2.7%. The
old camera's validation of 2026-10-05 (lens 6.27, rounds within 1.5 minutes) gave ±1.58% to
±2.93%. The band is therefore not an estimate: it is the observed spread of real measurements of
known targets, in that slot, at that focus. Each band comes from one validation session; how much
a band changes from one validation to the next is shown by the sessions of 2026-10-05 and
2026-10-07 on the same calibration (metrology-log section 6): single slots differed by up to 1.5
points (North 1, ±1.77% then ±3.3%), with a cold start, a camera fault and lens tests in between.

**Why a percentile, and not a normal-distribution estimate.** The usual metrology route to a 95%
interval is twice the standard uncertainty (the GUM's k = 2), which is about 95% only when the
errors are roughly normal. The band makes no such assumption. Compared on 7 validation sessions
(84 slot-sessions, metrology-log section 6.1), the band and twice the root mean square error
agree within 0.3 points in 70; across all 84 the band is a median of 0.95 times that normal
estimate, as normal errors would give. Where they differ by more, it goes both ways. In 9 the
normal estimate is wider, by more than 0.3 points, so there the band reports less than a normal
estimate would. In 5 the band is wider, by 0.37 to 0.86 points, each time because a group of 6
or 7 tags in one or two of the 3 photographs read off together, all on the same side; a normal
estimate would have reported less spread than those tags showed. So on this rig the choice of
method changes the band by 0.3 points or less in 5 of every 6 slot-sessions, and where the
errors are not normal the band reports the spread the tags actually showed. In 4 of those 5,
all on the current camera, the photographs show a sheet not lying flat (Aaron, by eye,
2026-10-13); the fifth, on the old camera, has no cause found. The validation checks did not flag
any of them, so a sheet not lying flat can widen a band without warning. This is a weak point in
the validation step, not yet addressed. No confidence level is attached: the
3 rounds are not independent samples.

**The band holds the next day.** On SN001 a validation was repeated the next day with nothing
recalibrated or moved (2026-10-13 and 10-14, metrology-log 14.1): 94.1% of the second day's tags
fell inside the first day's bands (rule, set before the test: at least 90%, no slot below 75%;
lowest slot 81%), and bands changed by -0.5 to +0.3 points. The narrowest bands (about ±1.2%) had
the fewest tags inside, because a day-to-day shift of a few tenths of a point uses more of them.

**Why the calibration's own estimate is not used.** The calibration can also estimate its
uncertainty from how closely the tags fit the scale field. Checked against validation, that
estimate was slightly too small in 7 of 12 slots: typically 0.50% predicted against 0.54%
measured, in length, and at worst 0.32% against 0.61% (North 6). On a 36 mm leaf that is about
0.12 mm predicted against 0.22 mm measured. Both are small; the estimate was simply not a
reliable guide, because it is judged against the same tags it was fitted to. It has been
dropped from what the operator sees; only the validation band, which is measured directly, is
reported.

**How a reading gets its band.** Since #76 (2026-11-05) every tray area carries the band of the
validation slot whose centre is nearest the tray's centre, in the Gallery and in the export's
`tray-readings.csv`, under the heading "Scale error at tray top". Trays are found anywhere on the
table (#331), so a tray between two slots takes the nearer one's band: a choice, not a
measurement (Aaron, 2026-11-05). No band is claimed when the photo has no complete validation,
when its validation is not consistent or its file is gone, when the photo is flagged as not
covered (a lens moved from its lock, for example), or when the slot had too few tags; the reading
then says which. The band covers flat objects at tray-top height only: plant height
(about 0.145% per mm) and how well the mask finds the plant are not in it, and the page says so.

## Faults are caught, not averaged in

**What could go wrong.** A bad sheet, a tray at the wrong height, or a knocked camera would make
some readings wrong. Pooled into a band, a fault would quietly widen it or shift it.

**What the rig does.** Each validation is checked for:

- a slot whose reading moves between rounds by more than 2.5 points (a sheet that does not match
  the others);
- a slot that reads off from all the others by more than 3.0 points, every round (a fault that
  stays in one place);
- the whole table reading off by more than 2.5 points (camera or table moved).

Each limit was set from real sessions: in validations with no known fault, slots moved by at
most 1.96 points and sat at most 2.15 points from the rest.

**Evidence (2026-10-01, in the chamber).**

- A sheet printed at 89% scale (measured with callipers, reading about 21% small) was moved
  through three slots. The rig named it in each round (-20.9, -20.9, -21.3 points) and flagged
  no good round.
- Left on one slot for all rounds, it was not flagged by the round-to-round check. That run is
  why the steady-offset check (the second check above) was added.
- A tray 75 mm taller than normal read 11.2% to 12.0% large, against 11.8% predicted from the
  camera height. The rig measures what is actually there; a wrong-height tray shows as a wrong
  area, which is why bands are stated for tray-top height only.

Conditions the bands do not cover are marked on each photo rather than averaged in. Since
2026-10-08 a photo is flagged when its lens position differs from the focus lock, or when it was
taken within 60 minutes of the Pi starting (a cold start; the 60 minutes is a decision: one run on
SN001 found the readings back within 15 minutes). A camera fault during a run is not detected yet (`docs/metrology-log.md`, section 8).

Which validation a photo is given is one rule, used for the photo's record and the status line
alike (2026-10-16, #183): the newest complete validation (3 counted rounds) of the active
calibration. A newer validation that is still running, or ended early, does not replace it. If
that validation is not consistent, the photo is flagged and its bands are not claimed; the record
still names it, so it says which validation the photo was taken under.

## Checks of the whole chain

**What could go wrong.** Calibration and validation both rest on the same typed-in tag size. If
that number were wrong, every area would be wrong by the same proportion and validation would
still pass. And a camera that moves after calibration would make the calibration silently stale.

**What the rig does.** Two checks that do not depend on the tag size: a tape measure, and the
corner-tag tripwire, which compares every photo's 4 corner tags with the calibration's. In the
metrology log's labels, the tape and the roll against the table's rails are reference
comparisons; the knocks, the two calibrations and the two heights are development checks.

**Evidence (2026-10-05, in the chamber).**

- **Tape measure, about 1700 mm along the South row.** Tag to tag, the app read 1.6% and 1.7%
  long in two runs. With the tape itself photographed (lying 10 mm above the sheets, which by
  itself makes a length read about 0.72% long), the app read about 1.4% long. Both are inside the
  2% required, and they agree within about 0.3 points.
- **Camera roll.** The camera was rolled by hand. The app read -3.01°; the table's fixed rails,
  measured in the same photos, gave about -3.0° to -3.1°.
- **Knock.** A firm knock on the camera mount gave FAIL (a corner tag pushed out of view). After
  re-framing, the app reported DRIFT with the roll and the tilt.

**Evidence, replacement camera SN001 (2026-10-12 to 10-14, metrology-log section 14).**

- **Tape measure**, about 1600 to 1740 mm along the South row: the app read about 1.3% long, tag
  to tag and with the tape photographed (corrected for the tape's 3 to 12 mm height); the two
  methods agree within 0.1 points. Inside the 2% required.
- **Two calibrations with a cold start between them**, the table untouched: at the 12 slot centres
  they differ by -0.08 to +0.19 points of area, at most about a ninth of that slot's band. So two
  separate calibrations agree far inside the bands.
- **Two heights**: the shape of the scale field on the table surface and on the trays (about 100 mm
  apart) differs by at most 0.39 points, below both calibrations' residuals (0.50% and 0.66%); one
  calibration's shape covers the tray height, with less margin than on SN000 (0.16).
- **Camera roll**: two knocks rolled the camera 5.9° and 6.9°; the app's roll agreed with the
  table's rails within 0.03°.
- **Knock**: both knocks were caught and read DRIFT, not FAIL: FAIL needs a 10° roll, an 8% corner
  scale change or a missing corner tag, and neither knock reached one. Covering one corner tag by
  hand gave FAIL, and uncovering it gave OK again. Signed off by Aaron on 2026-10-14.

## The band stays valid over time and after disturbance

**What could go wrong.** The band is measured at one moment. If the camera's readings shifted
later (with time, after a restart, or after a power cut), the band would no longer describe the
measurements.

**What the rig does.** After a restart or power cut, the app drives the lens back to the locked
position by one fixed route and waits until the camera reports it there; the lock is restored
only if that succeeds. Captures never move the lens.

**Evidence (2026-10-05, the repeat-photograph test).** The table was left untouched and each tag
was compared with its own earlier reading:

| Event | Change right after (median) | Largest slot change within an hour |
|---|---|---|
| Nothing done (control) | | up to 0.52 points (North 1) |
| Nothing done, one photo a minute for 2 hours (2026-10-06) | | a repeating 19-minute cycle: whole-table median up to +0.33 points, up to 0.62 points in one slot (North 5) |
| Nothing done, one photo a minute for 6.8 hours (replacement camera, 2026-10-07) | | the same 20-minute cycle, following the chamber's humidity and temperature, swinging about 0.5 to 0.6 points; no drift (each hour's median within 0.06 points of the others); metrology-log 8.2, overnight run |
| Lens moved by autofocus, driven back to 6.15 | -0.03 points | +0.35 points |
| App restart | +0.08 and +0.09 points (two attempts, 2026-10-05); within ±0.05 over 5 restarts (2026-10-06) | -0.29 points; every slot within ±0.39 over the 5 restarts |
| App restart, replacement camera (2026-10-07) | within -0.04 to +0.06 over 5 restarts | every slot within ±0.24 over the 5 restarts (metrology-log 8.2, step 5) |
| Power cut (cold start) | -1.73 points right after; -0.41 at +15 min; -0.14 at +60 min | -0.62 points at +60 min (South 1) |
| Power cut (cold start), replacement camera (2026-10-14, Pi off about 35 min) | -2.73 points right after (100 s after power-on); +0.08 at +15 min; +0.07 at +60 min | every slot within 0.31 points from +15 min on (metrology-log 14.3) |

Photographs of an unchanged scene differ anyway: on the old camera, two photos at different light
levels differed by 0.27 to 0.46 points (standard deviation over tags), at most about 0.2 to 0.3
points for one photo; on the replacement camera fitted 2026-10-07, 10 photos at fixed exposure varied by
0.15 points per tag (metrology-log section 8, and 8.2, step 3). Both
disturbances stayed inside the change seen with nothing done, and the largest change in any slot
was about a sixth of that slot's band. On this evidence, a restart does not require a new
calibration or validation. The replacement camera fitted on 2026-10-07 gave the same result.

A cold start is different. Right after a power cut, with the camera cold, the central trays
were blurrier and areas read about 1.7 points low, more than some slots' bands. Without any
lens move the readings returned over the next hour: most of the change was gone after 15
minutes, and after 60 minutes it was close to the change seen with nothing done. Readings taken in
roughly the first 15 minutes after the app opens a cold camera are not covered by the bands.
On the replacement camera the drop right after was larger (-2.73 points) but the readings were
back within 0.31 points of the reference at +15 minutes and stayed there (one run, 2026-10-14).

A camera fault is different too. On 2026-10-06 the camera once stopped delivering frames and the
app had to be restarted; afterwards, at the same reported lens position, the central trays were
about half as sharp and fewer tags were found. Neither a reference tag at the frame edge nor the
tray tags could reliably show or correct such a change in tests the same day. The plan is to
mark readings after a camera fault or a cold start as not covered by the bands, rather than to
correct them. The cold-start half is built (2026-10-08): photos taken within 60 minutes of the Pi
starting are flagged, a wider window than the 15 minutes above, chosen as a decision until a
cold-start run on the replacement camera measures it. The camera-fault half is built too
(2026-10-09): the camera runs in its own program, a camera call that does not finish in time ends
that program and a new one is started, and photos taken within 60 minutes after the camera is back are flagged
(the same window, also a decision). A fault that does not make a camera call hang, for example one
the camera software recovers from by itself, is not seen.

**Readings swing on a cycle of about 19 minutes.** On 2026-10-06 the rig took one photo a minute
for 2 hours with nothing touched (lens locked, lights on), to check that photos taken the way an
experiment takes them stay steady. Each tag's area reading was compared with the same tag in the
first photo. The limits were fixed before the run, from the earlier test with nothing done: the
whole-table median within ±0.10 points, and every slot within ±0.52 points.

The run **did not pass** those limits. The whole-table median reached +0.33 points, about three
times the limit, and one slot (North 5) reached +0.62 points.

The reason is a repeating cycle, not a drift. Every 19 minutes the readings rose by about 0.3
points within 2 or 3 minutes, then fell back over about 16 minutes. This happened 6 times, the
same size each time, and the readings returned to the same low point every cycle. Sharpness rose
and fell with them. The earlier test took a photo only every 15 minutes, too rarely to show a
19-minute cycle, so its limits were too tight for a test taken every minute. The first photo of
this run also fell at a low point of the cycle, so the run measured the full swing from bottom to
top.

What it means: depending on when in the cycle a photograph is taken, its reading can be up to about
0.35 points higher for the whole table and about 0.6 points higher in one slot. The chamber's own
log shows the cycle goes with its climate control: in the same 2 hours the air temperature rose and
fell between 19.8 and 20.3 °C every 19 minutes, and the readings followed it (correlation 0.84;
warmer air, larger and sharper readings), while the lights did not change. Which part of the
climate cycle, or what in the camera, causes the change is not known. The air handler runs outside
the operator's control and its cycle depends on the experiment, so the swing may differ between
experiments. The 2026-10-05 validation was taken with the same photo method, so the cycle was
already present then. Its 3 rounds were taken within 93 seconds, all at one point of the cycle, so
its bands do not include the cycle. From 2026-10-07 the validation rounds are to be spread over at
least 20 minutes, with the chamber door closed for every round; a validation with rounds closer
together still counts, but its status says so. For comparison, the 0.52-point slot change seen with nothing done was about a
quarter of that slot's band.

**Replacing the camera (2026-10-07).** The camera was replaced by a new one of the same model and
the key tests were repeated (metrology-log section 8.2). The new camera calibrated the same way
(355 tags, 0.49% against 0.52%), was less noisy from photo to photo (0.15 points against at most about
0.2 to 0.3, from tests run differently), behaved the same after restarts, showed the same lens fault after a full-resolution photo
and the same central low reading. The 19-minute cycle appeared on the new camera too and followed
the chamber's humidity and temperature, so it comes from the chamber, not from one camera. Over
6.8 hours with nothing done the readings did not drift (each hour within 0.06 points of the
others). One lesson from the swap: packing foam left on the camera body was removed during the
tests, and that lastingly changed the readings by about 0.8 points, more than anything else seen
with nothing moved. So any physical change to the camera, however small, is followed by a new
calibration and validation; the 2026-10-08 calibration was made for that reason.

**One open point.** On 2026-10-01, after a different series of lens moves, the central readings
drifted by 1.3 points in 35 minutes. That was not repeated on 2026-10-05, and the reason for the
difference is not known.

## Known error sources are found and stated

**The Arducam's central error.** Targets within about 1500 px of the image centre read up to a few
percent smaller in area than targets further out. It was investigated over several days: a
second camera (Canon) photographing the same table does not see it, so it belongs to the Arducam,
not to the table, sheets, trays, lighting or detection. Its size follows the focus position (about
1.2 points per 0.1 of lens position, measured on the old camera, one photograph per position). The
rig does not correct it with a model. Validation measures it in each slot. On the old camera the
central slot North 4 had the widest band (±2.93% at lens 6.27, ±3.36% at lens 6.15). On SN001
(lens 6.04) the widest band is the central slot South 4 (±2.7%), with North 4 and North 2 next
(±2.5%); the 4 central slots average ±2.3% and the 4 corner slots ±1.9%. SN001 shows the same
central low reading (metrology-log section 8.2), but its size against lens position has not been
measured on SN001.
The focus position is the experimenter's choice; the rig never tunes it for accuracy.

**Tag edges read short (found 2026-10-23, measured 2026-10-25).** The scale field is built from
the length of each tag's edges. Measured against the distance between tag centres on the same
printed sheet, which does not depend on where an edge is found, the edges read 1.1% to 1.9% short
in every calibration and validation photo since 8 October, and up to 4% short in older ones. Areas
measured with the calibration in use since 22 October therefore read 1.1% to 4.1% high from scale
alone, depending on the slot. Validation checks with the same edges, so its bands do not include this: **the bands
above are measured against tag edges, not against true size.** The shortfall changes between
photos, so a single correction factor would not hold. A flat green square of 150 mm by callipers
reads 6.1% high: 3.5% from scale and 2.2% from where the green mask puts its edge. Raised onto
the pots, at the calibration height, it reads 8.4% high: 4.9% from scale and 3.4% from the mask
edge, so the mask edge also depends on what lies around an object.

**The fix (2026-10-26, #286).** Calibration now fits the scale to tag spacing, and validation
scores each tag by its tag spacing against the calibration, so the bands are measured against the
printed distances, not against tag edges. Checked on stored photos (metrology log 18.6): against
tag sheets on the pots, the 22 October calibration refitted this way reads -1.6% to +1.5% in area
where the old one read +1.0% to +4.8%; its three validation rounds give a table median of +0.1% to
+0.6%. Calibrations made before the fix keep their edge-based scale until they are rebuilt from
their stored photos.

**The mask edge is not measured for plants.** Green test squares (metrology log 18.5) show the green
threshold reading the area of a flat green object anywhere from 27% low to 41% high on a 10 mm
square, depending on the background: it grows over dark backgrounds and shrinks on bright ones.
On black paper it adds a strip 0 to 1.1 mm wide at every edge. That is a property of the threshold
on those objects, not a band for plants: leaves and soil were not tested, and no band for plant
segmentation is claimed. With the scale taken out (metrology log 18.7), the scale part at each square
agrees with its slot's validation median within 0.5 points, while the mask edge is 6 to 30 times
larger and changes from slot to slot, mostly with the brightness around the object: the validation bands
are right for the scale and say nothing about the mask. Three other published green thresholds
(metrology log 18.8) leave the same strip of about 0.6 to 1.0 mm, so changing the threshold does not help.
The strip is a larger share of a smaller object: about +28% on a 10 mm square, and nothing below
10 mm was measured, so areas of plants smaller than that carry no measured error. Methods that place the
edge half way between object and background in linear light, instead of counting every tinted
pixel, remove most of the strip on the squares (metrology log 18.9: 10 mm squares -2.9% median,
single stills -8.6% to +6.6%). They are not yet tried on plants (#297), and the threshold in use
stays for now.

**Plant area against a person's outlines (metrology log 24 to 24.8, development checks, 2026-11-04
and 05).** Aaron outlined 15 potato plants on one production still twice, on two days, in ImageJ by
a written rulebook. His two passes agree to IoU 0.915 and differ by 6% in area (sd), the ceiling
any rule can be judged against. Against those outlines the green threshold in use counts 0.31 of
the leaf area on average and 0.07 on the smallest plant: the areas the rig stores read low by a
factor that changes with plant size, and the Gallery now says so. A rule that grows each piece of
leaf found by the threshold outward to a lower cutoff (-0.045) reads 0.96 of the outlines (IoU
0.87). That cutoff fits production's dark soil only: on the development rig's pale and greening
soil it counts whole soil cells as plant, so the cutoff has to follow each tray's own soil (24.7,
24.8), and on the greenest soil no colour rule separates soil from leaf, which the rig must report
instead of a number. A blue mat laid under green squares changes every rule's area at the edge,
13 to 24% on a 10 mm square (24.4). SAM 2.1 small, given each plant alone, does worse (IoU 0.77)
and takes 7 to 10 s a plant (24.5). These are one still and 15 plants of one person: they show
which rules fail and how, not a band for plant area.

**How photos are saved.** Until #359 every photo was saved as a JPEG at quality 75 with colour at
half resolution, a library default nobody chose. Against the same stills kept uncompressed
(metrology log 26.1, a development check: 3 stills, 9 trays of plants, one rig), that setting
reads plant area 1.4% low on average and 2.6% low on the 4 smallest plants, the same way on every
still: a bias, not scatter, because the soil's colour is spread over each leaf's edge and the
green threshold loses a rim 1 to 2 px wide. Full colour removes most of it (85 with full colour:
0.4% low on average, 0.6% on the small plants), and #359 makes that the setting. Tag corners and
scale do not change with the setting (tag sides within 0.13%), so the validation bands are not
affected. Photos saved before #359 keep the bias; its size on other plants and lighting is not
measured.

**Height above the tray.** About +0.145% of area per mm above the tray top. That figure comes from
the camera's height (about 1482 mm, a best estimate with a tape measure, not a precise value); one test, a
tray 75 mm taller in 3 slots on the old camera, read 11.2% to 12.0% large against 11.8% predicted,
in line with that prediction. 0.145% per mm holds for small heights; the effect grows nearer the
camera, so over 75 mm it averages about 0.157% per mm. Plants have height, so a plant's area
carries this on top of the band.

**Lens distortion.** Not modelled. The rule for adopting a distortion model is evidence that the
errors are structured (growing toward the image corners), not random. A radial trend has been
seen (R² 0.33 to 0.45 on repeat runs), but in the 2026-10-05 validation of the earlier setup
(lens 6.15) the errors in the 4 corner slots (0.52% in length) were no larger than in the 4 central slots (0.69%). The trays do not reach
the extreme frame corners, and plants only sit on trays. No model is adopted.

**Segmentation, first look (round 1, 2026-10-15).** On a 3D-printed benchmark measured 92
times across all 12 slots, fixed colour thresholds gave repeatable green areas (1.5% to 3.6%
spread for the four rosettes, under 0.8% for repeated photos with nothing moved). The small red
shapes of known area showed two error sources larger than anything in the geometry: edges
(a flat 10 mm circle read about 21% small) and sides seen at an angle toward the row ends (a
15 mm tall prism read up to 75% large). Segmentation is now the largest measured error source,
as PLAN.md expected. Metrology log section 15.5. A photogrammetry mesh of the same benchmark
(one capture, a second instrument) gives rosette areas 10% to 39% larger than the rig; which of the
two is closer to the truth is not known yet. Metrology log section 15.5e. The mesh is the least
reliable instrument, an order of size with very low precision (Aaron, 2026-10-28). A phone photo of
the same benchmark (2026-10-28), scaled by vernier calliper readings of its base and with the
phone's own, larger, height effect taken out using a measured spacing at rosette-centre height, is
the reference chosen by Aaron. Against it, the rig, in the potato run, reads the benchmark about 5%
small, at the edge of the 5% target. The phone application's leaf outline is unchecked, so whether
the gap is the rig's edge rule or the application's is not known; the ImageJ comparison (#297)
checks the edge. Metrology log section 17.13.

**Real leaves, first look (round 1, 2026-10-15).** Three garden leaves of known area (flatbed
scans scaled by printed tags), laid flat on the trays, read on average 2.5% smaller than their
scans (27 readings, SD 3.2%). The leaves shrank 4.6% to 7.5% between the scans taken before and
after the photos, so their true area at each photo is known less well than the rig's validation
bands (1.3% to 2.6%): this test cannot yet show whether the bands hold for leaves. The same
leaves read about 5 points larger on a black sheet than on the blue trays, only partly explained
by the sheet lifting them 3 to 10 mm. Metrology log section 15.5b.

## Limits of the evidence

What the rig cannot yet back with evidence. This list is updated at every round review (PLAN.md,
*Records kept for every round*); last updated at the round 1 review, 2026-10-19
(`docs/metrology-log.md`, 15.6). A claim leaves this list only when a measurement in the
metrology log backs it.

### Plant area (round 1, 2026-10-19)

- **Canopy area of living plants.** Not measured. The closest result is cut real leaves lying
  flat on blue trays: on average 2.49% small (SD 3.15, range -9.10% to +3.43%, 27 readings,
  15.5b). That covers neither living rosettes, nor leaves that overlap, nor soil or moss around
  them, and the known area of a cut leaf itself shrank 4.6% to 7.5% in 16 minutes.
- **Plant height.** The bands are for flat targets at tray-top height. Height alone makes an
  object read about 0.145% per mm larger (the rosette tops of the benchmark 3.4% to 4.7%), and
  tall objects toward the row ends show their sides (a prism read up to 75.5% large, 15.5).
  No correction is made; it needs a measured depth source (CLAUDE.md, *Evidence gates*).
- **Very small plants.** Flat red shapes of 50 to 80 mm² read 16% to 21% small on average, likely
  because most of their pixels are blurred edge pixels (not measured, 15.5). Young seedlings may
  be this small.
- **Colour drift.** With nothing moved, the camera's white balance gains drifted 0.8% to 0.9% in 30
  minutes (15.3d). What that does to green area is not measured.
- **One photo against the next, over a long run** (*added 2026-11-09*, metrology log 16.9, a
  development check, green threshold 0.1 only). On production over 18 days, with nothing moved, the
  benchmark's area changed by 0.26% (RMS) from one photo to the next on 26 Oct to 5 Nov, 0.58% on
  6 to 9 Nov and 2.18% on 22 to 25 Oct. A grown plant changed by 26 to 41 mm², a cell by a median
  of 3 to 4 mm² at every size, 100 to 300 times its growth per minute. The same benchmark read
  about 3.7% more per 1,000 px from the photo centre, and 17% less in one slot where the mask lost
  its pale pixels with no leaf over it. The worse periods are described, not explained, and leaf
  movement is not separated from the rig's error. The new rules of #352 are to be checked the same
  way (#395).

### Trays and tags (round 1, 2026-10-19)

- **Tray placement.** Placing each tray from its tag in cell A1 put 503 of 504 tray positions in
  the slot and corner known from a plan or from Aaron's check, gaps and touching, tags in any
  rotation: 215 of 216 in 18 stills (15.5j; the one miss a tag not found) and 288 of 288 in 24
  stills (15.5k). A further 22 stills (15.5h) were checked by eye only. That is one day,
  12 trays of 4 x 5 cells in portrait, paper 30 mm tags lying flat in an empty cell A1.
  With the 40 mm tags (20 October, 15.5l), the offset learned once from one layout, through 19
  random layouts on one day with scheduled stills every minute: 3181 of 3184 uncovered tray
  positions in the slot and corner as laid out, 0 wrong, 3 tags not found (blurred by movement);
  the rule also caught 3 layouts that differed from the plan (confirmed by Aaron from the
  pictures). Each placed centre held within 2.0 mm rms while nothing moved. 44 positions were
  hidden by people or objects in the chamber. Overnight with nothing moved (15.5l), all 12 tags
  were found in every lit still and each tray's centre returned within 0.65 mm of its evening
  position after 7.5 hours of darkness; with the lights off no tag is found, so night stills hold
  no tray data. Not shown: the tray outline against a measured tray edge; more than one night; an
  in-between light level; fewer than 12 trays; other tray types; cell A1 holding anything but
  the tag.
- **Tray tags over time.** No run with trays longer than one hour, so the chamber's light cycle,
  dust and condensation on tags are not covered. 3D-printed tags are not tested (#70). A tag print
  lying anywhere in view is read as a tray (15.3d, #207). *Added 2026-10-30:* on the potato run
  (12 trays in 2 x 6 slots, 8 days from 22 October through the light cycle), every tray was read
  in its planned slot, A1 corner and table location after each of 6 shuffles (72 of 72), each
  move dated from 5 minutes before to 1 minute after the recorded finish. Outside the shuffles
  the rig read 2 short changes and no move under the 1-hour rule: a duplicate tag laid on another
  tray for 5 photos (17.12) and a second tag 2 read in 1 photo, 6 of 95,482 tray readings
  (metrology log 22). Dust and condensation were not checked apart.
  *Added 2026-11-09:* over the whole run (18 days, 12 shuffles, 7 trays with growing potato
  plants) every tray was read in its planned slot after every shuffle (156 of 156; 209,001 of
  209,012 readings), with no move outside the shuffles, and tags were found in 97.0 to 100% of
  lit photos per tray per day (91.3% on the day of a 2-hour shuffle). The A1 corner was checked
  only for the last two maps, 34,101 of 34,101 readings, because it is not stored since #331
  (metrology log 22.1, #391).
- **Tray identity under plants.** Plants near or over a tag are not tested (the trays had no
  plants).

### Trays found from the photo (round 2, 2026-10-29)

- **Tray outlines from the blue plastic.** Outlining each tray from its lit blue rim, using the
  photo only, was right on 22 of 22 lit held-out stills (metrology log 20.1, judged by Aaron's
  inspection; 24 stills from 9 experiments on both rigs, 12 to 28 October, with pots, empty
  trays, calibration sheets on every tray, edge tags, cards, 4x5 and 2x2 trays), and found no
  tray in the 2 dark stills. The versions that also used tags were wrong on 9 and 10 of the 22,
  every time because a tag did not lie in cell A1 of a 4x5 tray; a rims method with tags hidden
  was wrong on 8, missing trays under sheets or at the frame edge. On the 44 tuning stills (20)
  the method met its target on every set. This method is what the app uses (21); placing a tray
  from its cell A1 tag, the round 1 step above, is no longer used. Not shown: an outline against
  a measured tray edge (outlines were judged by eye on quarter-size pictures); stills picked at
  random; 1x1 or black trays.

### Cells placed in each tray (round 3, 2026-11-06)

- **Area per cell.** Each 4x5 and 2x2 tray's cells are placed from its outline and tag, and each
  piece of plant is counted wholly for the cell holding most of it; a cell with no plant reads
  "missing", never 0, and cells whose leaves reach over a neighbour's say so (metrology log 27,
  #364). On one still of each rig the placed cells lie well centred on the real pots (2x2) and
  openings (4x5) and are named right, judged by eye by Aaron (27.4); two blue-score methods for
  the error in mm were rejected, wrong on 4x5 trays. Not shown: a placement error in mm; a turn
  of the grid; the change between photos. The 2x2 cell layout rests on one tray measured with a
  tape measure and calliper readings of its pots.
- **Wall fringe in the cells (round 3, 2026-11-07).** The green threshold finds a few pixels of
  the blue tray plastic along cell walls, so about a third of empty cells read "plant". In a cell
  that holds a plant they add at most about 0.1 mm2 (90th percentile of 3792 pictures, both rigs,
  metrology log 28), so plant areas are not changed by them and no rule is added. Not shown: an
  empty cell filled with soil (none existed in the data).

### Flat-target bands (M2, to 2026-10-14)

- **Segmentation.** Telling plant from background was not part of M2. Round 1 measured a green
  threshold on the benchmark and on cut leaves (above); it adds to the bands, by how much on
  living plants is not known. Since 23 October the rig reads a plant area for every tray with that
  threshold. A first look: trays holding only black pots read 25 to 109 mm² in one photo, which
  day-old potato sprouts could not be told apart from (metrology log 17.1); the review of the
  potato run (17.2) measures how steady these areas are and how much an empty tray reads.
- **Other focus positions.** Each focus position needs its own calibration and validation.
- **The first minutes after a power cut.** Readings in roughly the first 15 minutes after a cold
  start are not covered by the bands (one run on each camera, 2026-10-06 and 10-14; on SN001 the
  readings were back by +15 minutes, but when within those 15 minutes is not known). How long the
  warm-up takes in other conditions is not measured.
- **Long distances across several trays.** The tape check passed, but distances across the South
  row read 1.4% to 1.7% long on SN000 and about 1.3% on SN001, while the tags at its ends read
  about right, which is not explained. The North row cannot be reached without moving the table.
  Only the left-right direction of one row was checked. A plant is
  measured with the scale at its own slot, which validation checks directly; a distance spanning
  trays is not.
- **A software fault with focus, now fixed in code not yet merged.** After a full-res photo the
  lens ignored focus commands while the app reported success (diagnosed 2026-10-06). The fix
  reopens the camera so the lens obeys again; measurements made without touching focus were not
  affected.
- **After a camera fault.** A stalled camera followed by a restart left the central trays
  blurrier at the same reported focus (one case, 2026-10-06). Photos within 60 minutes after the
  camera comes back from a fault the rig detects (a camera call that does not finish in time) are
  flagged; a fault that does not
  make a call hang is not detected.
- **Tripwire limits.** The FAIL limits for roll (10°) and scale (8%) are provisional; on SN000 the
  knock test reached FAIL through a lost corner tag, not through those limits, and on SN001 two
  knocks that rolled the camera 5.9° and 6.9° read DRIFT. Whether a knock of that size should read
  FAIL is not decided.
- **One rig, two cameras, under four weeks of data.** The evidence above comes from this rig
  between 2026-09-21 and 2026-10-14 (round 1, to 2026-10-19, adds saved stills of one lens position
  and calibration), on camera SN000 until 2026-10-07 and SN001 after. The M2
  acceptance tests were run on both cameras (the honesty plot only on SN000; it was dropped with
  the claim it tested).

## Where the evidence is

- `docs/metrology-log.md`: every number, how it was measured, its date and source.
- `reference/arducam-central-error-2026-10.md`: the central-error investigation.
- `reference/lens-return-2026-10.md`: the lens-return, control and restart tests.
- Validation sessions and captures on the rig: `/var/lib/npec-rig/`.
