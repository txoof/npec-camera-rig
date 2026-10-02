# Operator guide: focus, calibrate, validate

For the person setting up an experiment on the rig. No photography background is assumed.

The rig measures plant area from a photograph taken from above. How far each measured area can
be trusted depends on the setup, so every setup is checked with printed targets of known size
before plant data counts. This page explains the three steps, when to repeat them, and what the
uncertainty column in the exported data means.

## The three steps

1. **Focus, then confirm focus.** On *Setup / Focus & Square*, set the focus for your setup with the
   targets on the trays, until the picture is sharp at tray height. The focus point is your
   choice: pick what suits your plants and trays. Then press **Confirm focus**. The rig moves the
   lens to that position in one fixed way and waits until the camera confirms it, which can take up
   to a minute. The status then reads "confirmed".
2. **Calibrate.** Run the calibration wizard on *Setup / Calibration* with the calibration sheets
   on the trays. It works out how many pixels make a millimetre across the table, at this focus.
3. **Validate.** On *Setup / Validation*, press **Start validation**. For each of 3 rounds: move
   every sheet on its tray, shuffle the trays between positions, then press **Capture round**. When
   3 rounds have counted, the status reads **Validated**, or **Not consistent** with the slots
   that disagreed between rounds and a red "Problem" note naming the sheet, tray or round to check.

The validation result is a map with one number per tray position (slot), for example "North 2:
±2.1%". That number is the uncertainty attached to every area measured at that position.

## When to repeat

Repeat all three steps after any of these:

- **Refocusing**, even slightly. The error in the middle of the table depends on the focus
  position (with this camera, about 1.2 percentage points of area per 0.1 of lens position), so a
  new focus needs its own calibration and validation.
- **Moving or knocking the camera**, or changing the table or tray heights.
- **A validation that reads "Not consistent"** after you have fixed what it named.

If focus is no longer confirmed (for example the status reads "not confirmed" after someone moved
the lens), measurements are not covered by the validation until all three steps are done again.

## What the uncertainty column means

Each exported area comes with an uncertainty such as "±2.1% (95%)". Read it this way:

- **It belongs to the tray position, not the tray.** A tray photographed on North 2 gets North 2's
  number. The same tray photographed later on South 5 gets South 5's.
- **It is a 95% range, not a standard deviation.** 95% of the reference targets measured at that
  position read within 2.1% of their true area. If you need a standard deviation, it is roughly
  half the number, if the errors are normally distributed.
- **It covers a flat object at tray-top height.** It is the part of the uncertainty that comes from
  the camera and the calibration. Two things add to it for real plants:
  - **Height.** Area reads about 0.145% larger for every millimetre above the tray top: a leaf
    50 mm up reads about 7% larger than it would lying on the tray.
  - **Segmentation.** Deciding which pixels are plant adds its own error at the plant's edges.

  So treat the column as the smallest uncertainty the measurement can have, not the whole of it.
- **The middle of the table has wider numbers with this camera.** The positions nearest the centre
  of the picture (with the current layout, North 3, North 4, South 3, South 4) typically carry a
  wider range than the rest. This is a measured property of the camera, not a fault in your setup;
  how much wider depends on your focus position, and the validation measures it for you.

## Why it is done this way

The project rule is that every certainty is measured, never derived: if a number cannot be shown
with a ruler, a printed target or a repeated observation, it does not ship. The background to the
wider central numbers is in `reference/arducam-central-error-2026-10.md`.
