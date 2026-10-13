# Why the rig's area measurements can be trusted

**Status:** 2026-10-08. The camera was replaced on 2026-10-07 (old SN000, new SN001); the current
calibration and bands are SN001's, made 2026-10-08. The M2 physical acceptance tests were run in
the chamber on 2026-10-05, on SN000. The two-height, tape and roll tests passed. The check of the
calibration's own uncertainty claim failed, so that claim is no longer used (see *An independent
check, which sets the band*). Which results were repeated on SN001 is listed in
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

## An independent check, which sets the band

**What could go wrong.** A calibration always fits the targets it was made from. That says nothing
about how well it measures something else, somewhere else.

**What the rig does.** Validation tests the calibration on placements it was not made from. The
operator moves each sheet to a different tray, and the rig photographs again; this is repeated 3
times. A round counts only if at least half the tags actually moved, so the same layout is never
counted twice. The calibration photograph itself is never used. In each slot, the band is the
distance from the true area that 95% of the tags fall within, over all rounds.

**Evidence.** The current validation (SN001, 2026-10-08, lens 6.04): 3 rounds spread over 23.6
minutes, 74% to 87% of tags moved each round, 85 to 90 tags per slot, bands ±1.3% to ±2.7%. The
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
errors are not normal the band reports the spread the tags actually showed. Whether such a group
of tags should count is a separate question, not examined. No confidence level is attached: the
3 rounds are not independent samples.

**Why the calibration's own estimate is not used.** The calibration can also estimate its
uncertainty from how closely the tags fit the scale field. Checked against validation, that
estimate was slightly too small in 7 of 12 slots: typically 0.50% predicted against 0.54%
measured, in length, and at worst 0.32% against 0.61% (North 6). On a 36 mm leaf that is about
0.12 mm predicted against 0.22 mm measured. Both are small; the estimate was simply not a
reliable guide, because it is judged against the same tags it was fitted to. It has been
dropped from what the operator sees; only the validation band, which is measured directly, is
reported.

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
taken within 60 minutes of the Pi starting (a cold start; the 60 minutes is a decision until it is
measured). A camera fault during a run is not detected yet (`docs/metrology-log.md`, section 8).

## Independent checks of the whole chain

**What could go wrong.** Calibration and validation both rest on the same typed-in tag size. If
that number were wrong, every area would be wrong by the same proportion and validation would
still pass. And a camera that moves after calibration would make the calibration silently stale.

**What the rig does.** Two checks that do not depend on the tag size: a tape measure, and the
corner-tag tripwire, which compares every photo's 4 corner tags with the calibration's.

**Evidence (2026-10-05, in the chamber).**

- **Tape measure, about 1700 mm along the South row.** Tag to tag, the app read 1.6% and 1.7%
  long in two runs. With the tape itself photographed (lying 10 mm above the sheets, which by
  itself makes a length read about 0.72% long), the app read about 1.4% long. Both are inside the
  2% required, and they agree within about 0.3 points.
- **Camera roll.** The camera was rolled by hand. The app read -3.01°; the table's fixed rails,
  measured in the same photos, gave about -3.0° to -3.1°.
- **Knock.** A firm knock on the camera mount gave FAIL (a corner tag pushed out of view). After
  re-framing, the app reported DRIFT with the roll and the tilt.

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

## What the trust does not cover yet

- **Plant height and segmentation.** The bands are for flat targets at tray-top height. Telling
  plant from background (segmentation) has not been measured on this rig; it is planned for the
  canopy-area milestone (M5) and is expected to add several percent.
- **Other focus positions.** Each focus position needs its own calibration and validation.
- **The first minutes after a power cut.** Readings in roughly the first 15 minutes after a cold
  start are not covered by the bands (2026-10-06, one run). How long the warm-up takes in other
  conditions is not measured.
- **Long distances across several trays.** The tape check passed, but distances across the South
  row read 1.4% to 1.7% long while the tags at its ends read about right, which is not explained.
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
- **Tripwire limits.** The FAIL limits for roll (10°) and scale (8%) are provisional; the knock
  test reached FAIL through a lost corner tag, not through those limits.
- **One rig, two cameras, under three weeks of data.** The evidence above comes from this rig
  between 2026-09-21 and 2026-10-08, on camera SN000 until 2026-10-07 and SN001 after. Most of the
  acceptance tests (tape, roll, two heights, honesty plot) were run on SN000 only.

## Where the evidence is

- `docs/metrology-log.md`: every number, how it was measured, its date and source.
- `reference/arducam-central-error-2026-10.md`: the central-error investigation.
- `reference/lens-return-2026-10.md`: the lens-return, control and restart tests.
- Validation sessions and captures on the rig: `/var/lib/npec-rig/`.
