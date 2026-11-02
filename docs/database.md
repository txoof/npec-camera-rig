# The rig's database

The rig keeps one SQLite database, `/var/lib/npec-rig/rig.db` (a different path can be set with
the `NPEC_RIG_DB_PATH` environment variable). Photographs are not in it. They are JPEG files with a
JSON record beside each one, under `/var/lib/npec-rig/rig/<day>/`. The database holds settings,
camera events and indexes of work done on photographs.

Open it read-only to look around, so a running rig is never disturbed. The `sqlite3` command-line
tool is not installed on the rig; Python's own module works:

```
python3 - <<'PY'
import sqlite3
db = sqlite3.connect("file:/var/lib/npec-rig/rig.db?mode=ro", uri=True)
for row in db.execute("SELECT time_utc, kind, call, detail FROM camera_events ORDER BY id"):
    print(row)
PY
```

The queries below can be pasted into the `db.execute(...)` line.

## Times are UTC

Every time in the database is UTC, with its offset written out (`+00:00`). The chamber's local
time is UTC+2: 10:04 in the chamber is `08:04` in the database. Convert only for display, never
before storing.

In `camera_events`, times are written in one fixed format, always with microseconds:
`2026-10-09T08:04:44.736204+00:00`. Text in this format sorts in time order, so
`ORDER BY time_utc` and `time_utc >= '...'` work directly. The older tables use Python's
`isoformat()`, which leaves out the microseconds when they are zero; those are UTC too but
should be compared as times, not as text.

## Tables

| Table | What it holds | Written by |
|---|---|---|
| `camera_events` | One row per camera fault, restart, failed open, or program that cannot be ended | `health.py` |
| `camera_settings` | The last value of each camera setting, the focus lock, and a few small records | `settings.py` |
| `derived_image` | Index of images made from photographs (validation maps, problem frames) | `images.py` |
| `capture_analysis` | Results worked out once per photograph, for example its detected tags | `images.py` |
| `scheduled_photo` | One row per scheduled photo of an experiment, taken or missed | `scheduler.py` |
| `tray_read` | One row per photo read for trays, with its status | `tray_readings.py` |
| `tray_reading` | One row per tray found in a photo: its slot, A1 corner and centre | `tray_readings.py` |
| `exclusion` | One row per photo of an experiment: why its plant areas are left out, if they are | `exclusions.py` |
| `light_warning_dismissal` | One row per dismissal of an experiment's light warning | `exclusions.py` |

### `camera_events`

The history of the camera's health (#51). The camera runs in its own program, and every camera call
has a time limit. When a call does not finish in time, the program is ended and a new one started.
Each step is a row. Rows are never changed or deleted by the rig.

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Row number, increasing. Newest row has the highest `id` |
| `time_utc` | text | When it happened, UTC, fixed format (see above) |
| `boot_id` | text | Linux's ID for this boot of the Pi. A new value means the Pi rebooted in between |
| `uptime_s` | real | Seconds since the Pi booted, from the kernel's own clock (correct even if the wall clock is wrong after a power cut) |
| `kind` | text | `fault`, `restarted`, `open_failed` or `cannot_end` (below) |
| `call` | text | The camera call that did not finish, for example `capture_full_res`. `fault` rows only |
| `limit_s` | real | The time limit, in seconds, that ran out. Empty if the camera program ended by itself during the call |
| `detail` | text | What happened, in words |
| `rig` | text | The Pi's hostname |
| `camera` | text | Camera model and libcamera ID, as the camera reported them, for example `arducam_64mp /base/axi/...`. Shows a camera swap in the data. The serial number (SN001) is not reported by the camera |
| `app_version` | text | Git commit of the app that was running |
| `program_pid` | integer | Process ID of the camera program the row is about, to match against the server log |
| `lens_locked` | real | Focus lock at the time (lens position in dioptres). Empty if focus was not locked |
| `recovery_s` | real | `restarted` rows: seconds from the fault, or the first failed open, until the new camera was ready |
| `reboot_needed` | integer | 1 if the rig reported at that moment that the Pi needs a restart, else 0. The rig never restarts the Pi itself |
| `experiment_id` | text | The experiment running at the time. Empty until experiments exist (#55) |
| `purpose` | text | The photo that was being taken when the fault happened: `capture`, `validation`, `calibration` or `tripwire`. Empty if the fault was not during a photo (for example a live preview frame) |

Kinds of row:

- **`fault`**: a camera call did not finish within its time limit, or the camera program ended
  during a call. The program is ended and a new one started.
- **`restarted`**: a new camera program is ready after a fault or a failed open, with
  `recovery_s` saying how long that took. Photos taken in the 60 minutes after this row (the
  camera-fault window, a decision, see `docs/metrology-log.md`) are flagged as not covered by the
  validation bands. The window counts from the restart, not the fault: after a long outage the
  photos after the camera comes back still get the whole hour. The 24-hour restart count on the
  status line and for the fleet endpoint (#82) counts these rows.
- **`open_failed`**: a camera program could not open the camera. The rig tries again every
  60 seconds. From the third failure in a row, `reboot_needed` is 1.
- **`cannot_end`**: a stuck camera program would not end, which happens when it is stuck inside the
  camera driver. The camera cannot be reopened until the Pi restarts; `reboot_needed` is 1.

Time limits (decisions, see `docs/metrology-log.md`): 30 s for a full-resolution photo, 20 s to
reopen the camera, 90 s for autofocus, 10 s for every other call, 30 s to open the camera.

What the table does not see: a camera fault the camera software recovers from by itself, without a
call hanging.

Example questions:

```sql
-- Every fault in the last 7 days, newest first
SELECT time_utc, call, limit_s, purpose, detail FROM camera_events
WHERE kind = 'fault' AND time_utc >= strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now', '-7 days')
ORDER BY time_utc DESC;

-- Which camera calls hang most
SELECT call, COUNT(*) AS faults FROM camera_events WHERE kind = 'fault'
GROUP BY call ORDER BY faults DESC;

-- How long recovery takes
SELECT MIN(recovery_s), AVG(recovery_s), MAX(recovery_s) FROM camera_events
WHERE kind = 'restarted';

-- Photos lost to faults, by purpose
SELECT purpose, COUNT(*) FROM camera_events
WHERE kind = 'fault' AND purpose IS NOT NULL GROUP BY purpose;
```

### `camera_settings`

| Column | Type | Meaning |
|---|---|---|
| `name` | text, primary key | The setting's name |
| `value` | text | Its value, as JSON |

Holds the last value of each camera control (`ExposureTime`, `AnalogueGain`, `AeEnable`,
`AwbEnable`, `LensPosition`), the focus lock (`FocusConfirmed`, `FocusConfirmedLensPosition`), and
`LastTick` (the last time the app was known to be running, for the cold-start check). One row per
name; a new value replaces the old one, so there is no history here. Times inside values are UTC.

### `derived_image`

Index of images made once from photographs and kept in `/var/lib/npec-rig/derived/` (PLAN.md,
*Images*). Disposable: a missing image is made again.

| Column | Type | Meaning |
|---|---|---|
| `key` | text, primary key | Identifies one derived image |
| `recipe` | text | How it was made (which kind of image) |
| `version` | integer | Recipe version; a new version makes the image again |
| `source` | text | The photograph it was made from |
| `path` | text | File on disk |
| `media_type` | text | For example `image/jpeg` |
| `bytes` | integer | File size |
| `created_at` | text | When it was made, UTC (`isoformat()`) |
| `last_used` | text | When it was last shown, UTC (`isoformat()`) |

### `capture_analysis`

Results worked out once per photograph, so they are not worked out again on every page view.

| Column | Type | Meaning |
|---|---|---|
| `source` | text | The photograph |
| `kind` | text | What was worked out, for example `tags` |
| `version` | integer | Version of the method; a new version works it out again |
| `value` | text | The result, as JSON |
| `created_at` | text | When, UTC (`isoformat()`) |

Primary key: `source` and `kind` together.

### `scheduled_photo`

One row per slot of an experiment's photo schedule. The schedule's interval is
`experiment.interval_s` (seconds, NULL for no schedule), and slot *n* is due *n* intervals after
`experiment.schedule_since`: the latest start, resume, or change of the interval while running. A slot that passed without a photo (the app was down, or the
photo before it took longer than the interval) is recorded as missed. The rows stay when the
experiment is purged, as the record of the schedule.

| Column | Type | Meaning |
|---|---|---|
| `experiment_id` | integer | The experiment |
| `schedule_since` | text | The schedule start the slot is counted from, UTC |
| `slot` | integer | 1 for the first photo after the start |
| `due_at` | text | When the photo was due, UTC (`isoformat()`) |
| `capture_id` | integer | The photo's `capture` row; NULL when missed |
| `missed_reason` | text | Why it was not taken; NULL when taken |

Photos missed in the running period:

```
SELECT due_at, missed_reason FROM scheduled_photo WHERE capture_id IS NULL ORDER BY due_at
```

### `tray_read` and `tray_reading`

Readings per tray per photo (#222). The app reads each new photo taken as a capture in the
background, after it is saved, newest first: every photo taken since the app started and every
photo of the running experiment. Older photos are read when Show tags is tapped in the gallery
(Aaron, 2026-10-22). A reading: its tags are found once (`capture_analysis`), the trays are
found in the photo from their blue plastic and each is named by the tray tag whose centre lies
inside its outline, wherever the tag lies in the tray; a tray tag inside no outline is a tag
seen with no tray found, stored at the tag's centre with no outline and no area (#331,
`tray_placement.py`). Only a calibration is needed: trays can lie anywhere on the table, and
readings from version 14 on have no slot. Before version 14 each tray was placed from the tag in
its cell A1 and the nearest slot of the calibration's slot layout.
Validation, calibration and tripwire photos are not read in the background.

`tray_read` has one row per photo read, even when no tray was found:

| Column | Type | Meaning |
|---|---|---|
| `capture_id` | integer | The photo's `capture` row |
| `read_at` | text | When it was read, UTC |
| `status` | text | `read`; or why no tray was placed: `no trays found` (neither a tray nor a tag, as with the lights off; `no tags found` before version 14), `no calibration`, `no slot layout` (before version 14), `photo not found` (Reprocess with the photo gone and no outlines saved), `placement failed`, `read failed` |

`tray_reading` has one row per tray found in the photo or by its tag. Two trays in one photo may carry the same
tag (a misprint): both rows are kept, each with its own area, and neither area counts in that photo
("2 trays carry tag 1", #302). Two trays placed in one slot (`placement` is `two trays in one
slot`: a tray carried over the table, or a loose tag lying on a tray) make the whole photo chamber
activity (`exclusion` `visit`), and both trays show "2 trays in South 1" (#315). Before version 13 the table allowed one row per tag in a photo, and
such a photo was saved as `read failed` with no trays.

| Column | Type | Meaning |
|---|---|---|
| `capture_id` | integer | The photo |
| `tray_id` | integer | The tray tag's ID; twice in a photo when two trays carry it; NULL for a tray found in the photo with no tag inside it |
| `slot` | text | The nearest slot of the calibration's slot layout; NULL from version 14 on |
| `a1_corner` | text | `SW`, or `NE` for a tray turned 180; only for a tray placed from its tag, else NULL |
| `placement` | text | `placed`, `close call` or `two trays in one slot` (placed from the tag, before version 14), or `two tags in one outline`: neither tray counts and the photo is chamber activity, as for two trays in one slot (#315) |
| `centre_x_px`, `centre_y_px` | real | Tray centre in full-size photo pixels; for `tag only`, the tag's centre |
| `tilt_deg` | real | The tray's turn off the image axes, clockwise |
| `margin_mm` | real | How much nearer a slot the chosen corner is than the other; only for a tray placed from its tag, else NULL |
| `area_mm2` | real | NULL until segmentation (#74) |
| `outside_mm` | real | How far the tray's outline reaches past the photo edge at its farthest corner, mm; 0 inside. More than 13 mm shows "partly outside the photo" (#282). NULL for photos read before version 12 |
| `found` | text | How the tray was found: `photo + tag`, `photo, no tag` or `tag only` (a tag seen, its tray not found in the photo: no outline, no area). NULL for photos read before version 14 |
| `warnings` | text | JSON list of warnings: `no tag`, `two tags in one tray outline`, `tag seen, tray not found in the photo`, `partly outside the photo`. NULL before version 14 |
| `outline` | text | JSON list of the outline's four corners, `[x, y]` in full-size photo pixels. NULL for `tag only` and before version 14 |

A tray not found is never stored. When a photo's readings are shown, each tray found in an
earlier photo of the same experiment but not in this one is listed as not found since the first
photo it was missing from (Aaron, 2026-10-21): a removed tray, a swapped tag and a dirty tag look
the same to the rig. A tray with no tag is never listed as not found or as moved: it cannot be
followed from photo to photo. A tray with no slot is never listed as moved: a move without slots
is not worked out yet. Only photos with the status `read` count, so a dark photo is not a tray
missing. A purge deletes both tables' rows with the photos.

### `exclusion`

Exclusions (#288, `GLOSSARY.md`): why a photo's plant areas are left out of averages and
exports. The areas themselves are kept. Each time a photo is read, every photo of its
experiment is worked out again from its exposure times analogue gain (E) and saved, because a new
photo can change earlier ones. Only photos taken as captures get a name: validation, calibration
and tripwire photos get NULL and are left out of the norm. The rules and their values are in
`exclusions.py` and metrology log 17.8.

| Column | Type | Meaning |
|---|---|---|
| `capture_id` | integer | The photo's `capture` row |
| `name` | text | `lights off`, `light changing`, `light disturbed`, `light off norm` or `visit` (chamber activity, metrology log 17.9); NULL for none |
| `norm_e` | real | The experiment's norm (E) it was worked out with; NULL until the experiment has a full first day |
| `limit_fraction` | real | How far from the norm, as a fraction of it, counts as off it, for example 0.21 |
| `worked_out_at` | text | When it was worked out, UTC |

A photo read before this table existed has no row until its experiment is read again or
reprocessed; until then only lights off is shown, worked out from the photo itself. A purge
deletes the rows with the photos.

### `light_warning_dismissal`

The light warning (#288) is shown in the gallery when an experiment has more than 2 hours of
`light off norm` within 24 hours. It is worked out when shown, never stored. Dismissing it adds a
row; hours up to `covers_until`, the end of the warning the researcher saw, are not counted
again, later ones are, also in a stretch still going on.

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | The dismissal |
| `experiment_id` | integer | The experiment |
| `dismissed_at` | text | When the researcher dismissed it, UTC |
| `covers_until` | text | The end of the warning as shown when it was dismissed, UTC |

Kept when an experiment is purged, with its `experiment` row.

## Planned

The database schema for photographs, their provenance, calibration and validation is #54 (M3).
Until then, a photograph's checks and flags (lens check, cold start, camera fault) are in its JSON
record beside the JPEG, not in the database.
