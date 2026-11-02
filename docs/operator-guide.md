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
   before. Lay each sheet inside the tray rim, not over it. Press it down along all four edges.
   Check that all four corners touch the tray and nothing is under the sheet. A sheet that was not
   flat read up to 9.4% large and widened its slot's error band by up to 0.9 points (metrology
   log 6.1). Step out of view, **close the chamber door**, tick "The sheets are pressed flat and
   the chamber door is closed", then press **Capture round**. Spread the 3 rounds over at least 20
   minutes, first to last, at least 10 minutes apart; a countdown next to Capture round shows when
   the next round is due, and capturing earlier asks first. Readings rise and
   fall on a cycle of about 19 minutes, so rounds taken close together miss part of the real
   spread; a validation with rounds closer together still counts, but its status says so. When
   3 rounds have counted, the status reads **Validated**, or **Not consistent** with the slots
   that disagreed between rounds and a red "Problem" note naming the sheet, tray or round to check.
   A round taken within 60 minutes of the Pi starting is held back, not counted: a cold camera reads
   low for up to about an hour. Wait, or press **Count it anyway** next to the round.

The validation result is a map with one number per tray position (slot), for example "North 2:
±2.1%". That number is the uncertainty attached to every area measured at that position.

Photos are given the newest **complete** validation, the one with 3 counted rounds. Starting a
new validation does not change that until the new one completes: the status line then reads, for
example, "Validated 2026-10-14; a newer validation is in progress, 1 of 3 rounds". So a validation
started by mistake, or ended early, costs nothing. If the newest complete validation reads **Not
consistent**, photos taken from then on are flagged as not covered by the bands. To go back to
the previous validation after one was finished by mistake, delete the mistaken one from the
history on the Validation page (a way to set one aside without deleting it is planned, #196).

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

## Keep spare tag prints out of view

The rig reads every printed tag it can see. A spare or cut-off tag print anywhere in the photo, even
in a waste bin at the edge of the frame, is read as a tray (this happened in a test on 2026-10-15,
metrology log section 15.3d). Take spare prints and offcuts out of the chamber. The app is planned to
ignore tags outside the table (#207); until it does, this is the only protection.

## Why validation takes 20 minutes, with the door closed

Validation exists to show how far an area measured in each tray position can be trusted. Its
numbers are only as good as the photographs it is built from, so how the rounds are taken matters.

**Take your time.** With nothing touched, the rig's readings rise and fall on a repeating cycle of
about 19 minutes, by up to about 0.35 percentage points across the table and about 0.6 in a single
tray position (measured 2026-10-06). The cycle goes with the chamber's own climate control: in the
same 2 hours the air temperature rose and fell between 19.8 and 20.3 °C every 19 minutes, and the
readings followed it. What exactly causes the change is not known, and the chamber's cycle depends
on the experiment, so the swing can differ from one experiment to the next. During an experiment, photographs are taken at every point of that cycle. If the 3
rounds are taken within a few minutes, they all see one point of it, and the validation misses
part of the real spread. Spreading the rounds over at least 20 minutes, at least 10 minutes apart,
lets the validation see the cycle, so its numbers describe the photographs an experiment will
actually take. The countdown next to Capture round shows when the next round is due.

**Close the door.** An open door changes the air and light in the chamber. In an earlier test,
readings taken with people working and the door open changed more than readings with the chamber
closed. Closing the door before every round keeps each round to the conditions of an experiment.

What this does to the numbers: they become more trustworthy, not necessarily smaller. A
validation taken over time may show slightly wider ranges than a rushed one, because it includes
the swing a rushed one hides. A rushed validation still counts, but its status says "rounds
spread over N min, under the recommended 20" or "rounds N min apart, under the recommended 10", so
anyone using its numbers can see it.

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

## When a tray stays too long in one table location

Light, temperature and airflow differ across the table, so trays are moved around during an
experiment. The rig follows each tray by its tag and warns when one has stayed in one table
location too long.

- **The table locations.** The table is cut into 6 locations: NW, NM, NE along the top of the
  photo, SW, SM, SE along the bottom. A tray's centre decides its location. These are a decision, not a measurement.
- **What counts as a move.** A tray counts as moved only after 1 hour in another location. A
  tray nudged aside, or missing from a few photos, stays in its location.
- **The warning.** While an experiment runs, a tray in one location for longer than the limit
  is listed with a warning sign and the words "too long in", its location and the days, for example
  "Tray 7: too long in NW, 4.2 days". It shows on the Experiments page and in the Gallery. Move
  the tray to another location; the warning clears 1 hour after the move. A tray not found for 48
  hours is taken as removed and is not warned for.
- **The setting.** On the Experiments page, tap Table locations on the experiment, set "Too
  long in one location after" in whole days (default 4) and tap Save. It can be changed while the experiment
  runs.
- **Table locations** also shows, per tray, its hours in each location, where it is now, its
  moves as numbered arrows, and a strip across the experiment named by location. The export
  holds the same hours in `time-in-table-location.csv`.
- **Hide.** A tray that is not a real tray, such as a misread tag, can be hidden with its Hide
  button. It then shows as one line, "Tray 12, hidden", and gives no warning, on every PC, until
  Show is tapped. Its hours stay in the export.

## Why it is done this way

The project rule is that every certainty is measured, never derived: if a number cannot be shown
with a ruler, a printed target or a repeated observation, it does not ship. The background to the
wider central numbers is in `reference/arducam-central-error-2026-10.md`.
