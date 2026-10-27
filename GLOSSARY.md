# NPEC camera rig

The words this project uses for its own way of working and for the kinds of evidence behind its
numbers. Each term has one meaning here; the words under _Avoid_ are not used for it.

## Planning

**Round**:
A fixed period of about 2 weeks that takes the whole pipeline, from photo to a number per tray,
one step further, and ends with a written review (PLAN.md, *Rounds*).
_Avoid_: iteration, sprint, phase

## Kinds of result

Every result in `docs/metrology-log.md` is one of these three.

**Development check**:
A test made while building something, to see whether it works well enough to keep going.
_Avoid_: validation, experiment

**Validation**:
The routine check of a calibration with printed targets of known size placed in each slot, which
gives each slot's 95% band.
_Avoid_: test, verification, check (on its own)

**Reference comparison**:
A comparison of the rig's measurement with an independent measurement of the same real thing, such
as callipers on a printed target or a photogrammetry mesh of the benchmark.
_Avoid_: validation, ground truth

## The rig and its targets

Agreed with Aaron on 2026-10-26 (#286).

**Tag sheet**:
A paper sheet of AprilTags, each 30 mm, printed from a print layout file (`reference/calibration-
sheets/`) that fixes where every tag sits on its page, and checked with callipers. Used for
calibration and validation.
_Avoid_: calibration sheet (on its own), printed scale

**Corner tag**:
A 3D-printed tag at a corner of the table. Marks the table's corners and is used to check and
adjust how level the table is against the camera during setup.

**Tray tag**:
The tag of about 40 mm in cell A1 of a tray, which says which tray it is and where it lies.

**Green test square**:
A 3D-printed green square of known size, measured with callipers, used by the developers to
check how the green threshold reads area. Not part of a researcher's setup.
_Avoid_: green calibration square, green target (for the small squares)

**Slot**:
One of the 12 tray positions on the table, North 1 to 6 and South 1 to 6.

**Scale**:
Pixels per millimetre at a point on the table.

**Tag edge**:
The length of a tag's side, measured in a photo.

**Tag spacing**:
The distance between the centres of two tags on one tag sheet, as printed. The rig's scale comes
from tag spacing, not from tag edges, which read short in its photos (metrology log 18).

**Mask**:
The pixels the rig counts as plant.

**Error band**:
The range reported with each area, within which the true area is expected to lie.

**Automatic test**:
A check the computer runs on the code, with no chamber and no physical object; its inputs are
numbers written into the test.
_Avoid_: test sheet, test target

## Plant areas

**Exclusion**:
A stored reason that a photo's plant areas are left out of averages and exports: lights off,
light changing, light disturbed, light off norm, or a visit (#288). The areas themselves are kept,
never deleted, so an exclusion can be shown, reviewed or worked out again.
_Avoid_: mark, flag (a photo's flags say why the validation bands do not cover it)
