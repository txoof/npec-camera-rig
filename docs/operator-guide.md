# Operator guide: focus, calibrate, validate

For the person setting up an experiment on the rig. No photography background is assumed.

The rig measures plant area from a photograph taken from above. How far each measured area can
be trusted depends on the setup, so every setup is checked with printed targets of known size
before plant data counts. This page explains the three steps, when to repeat them, and what the
uncertainty column in the exported data means.

## The three steps

1. **Focus, then lock focus.** On *Setup / Focus & Square*, set the focus for your setup with the
   targets on the trays, until the picture is sharp at tray height. The focus point is your
   choice: pick what suits your plants and trays. Then press **Lock focus**. The rig moves the
   lens to that position in one fixed way and waits until the camera confirms it, which takes a
   few seconds. The status then reads "Focus is locked at" the lens position.
2. **Calibrate.** Run the calibration wizard on *Setup / Calibration* with the calibration sheets
   on the trays. It works out how many pixels make a millimetre across the table, at this focus.
3. **Validate.** On *Setup / Validation*, check that the page shows "Focus: locked" at the
   calibration's lens position, then press **Start validation**. For each of 3 rounds: leave the
   trays where they are, put each sheet on a different tray, 2 to 5 cm from where a sheet lay
   before, flat and fully on the tray, step out of view, **close the chamber door**, tick "The
   chamber door is closed", then press **Capture round**. Spread the 3 rounds over at least 20
   minutes, first to last; the page shows the earliest time for the last round. Readings rise and
   fall on a cycle of about 19 minutes, so rounds taken close together miss part of the real
   spread; a validation with rounds closer together still counts, but its status says so. When
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

While focus is locked the page reads "Focus is locked at" the lens position, and the lens controls
and Autofocus are greyed out: no one can change the focus without pressing Unlock focus first. If
focus is no longer locked (the status reads "Focus is unlocked"), measurements are not covered by
the validation until all three steps are done again.

If the page shows "Lens not responding: press Reset camera" in red, press the **Reset camera**
button next to it. It restarts the camera connection (about 2 seconds) and moves the lens back to
where it was; the focus stays locked if the camera confirms the position. The app has already
tried this once by itself before showing the message. If the reset does not help, the page says so,
and the app itself has to be restarted.

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
