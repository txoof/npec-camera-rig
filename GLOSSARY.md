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
