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
| `experiment` | One row per experiment, kept when it is purged; here only its dwell limit (#332) | `database.py` |
| `experiment_hidden_tray` | One row per tray hidden on an experiment's table locations panel (#332) | `database.py` |
| `scheduled_photo` | One row per scheduled photo of an experiment, taken or missed | `scheduler.py` |
| `tray_read` | One row per photo read for trays, with its status | `tray_readings.py` |
| `tray_reading` | One row per tray found in a photo: its centre and outline (its slot and A1 corner before version 14) | `tray_readings.py` |
| `exclusion` | One row per photo of an experiment: why its plant areas are left out, if they are | `exclusions.py` |
| `light_warning_dismissal` | One row per dismissal of an experiment's light warning | `exclusions.py` |
| `app_start` | One row each time the app starts | `scheduler.py` |
| `capture` | One row per photograph; here only whether its clock was set (#62) and the JPEG setting it was saved at (#359) | `captures.py` |
| `photo_quality_change` | One row per change of the JPEG setting photos are saved at (#359) | `settings.py` |
| `tray_layout` | One row per suggested tray layout of an experiment, and per check of the trays against one (#343) | `routes/randomize.py` |

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
`AwbEnable`, `LensPosition`), the focus lock (`FocusConfirmed`, `FocusConfirmedLensPosition`),
`LastTick` (the last time the app was known to be running, for the cold-start check), and
`PhotoQuality` (the JPEG setting full-size photos are saved at, `{"quality": 85, "chroma":
"4:4:4"}`; absent until first changed, which means the default, 85 with "4:4:4", #359). One row per
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

### `experiment`: the dwell limit

Version 15 (#332) adds one column. Its other columns are described where they are made, in
`database.py`'s migrations.

| Column | Type | Meaning |
|---|---|---|
| `dwell_limit_h` | real | Hours a tray may stay in one table location in a row before the experiment warns. Default 96 (4 days), also for experiments made before version 15. A decision, not a measurement (Aaron, 2026-10-30). Can be changed at any time but after a purge: the warning is worked out from the tray readings each time it is shown |

The table is divided into 6 table locations, 3 columns by 2 rows: NW, NM, NE in the north row, SW, SM, SE
in the south row (`dwell.py`). The rows meet halfway between the northern and the southern row of
corner tags, through the calibration's table frame (the homography of the four corner tags); the
columns are thirds of the photo's width along each row of the table. With no table frame (a
calibration without four corner tags, or a photo with no calibration), the photo itself is halved
and cut in thirds. A tray's centre decides its location. A tray is in a new location only after it has
been away from its location for over 1 hour (from its first to its last photo elsewhere, in any
other locations together), and then in the one it was in longest in that time; shorter stays,
misses and the tray taken off the table for up to 48 hours do not break its stay. A tray missing
for more than 48 hours (`NOT_SEEN_FOR`, as for trays not found) was taken away: its stay ends at
its last photo, it is not warned for, and when it is found again it starts a new stay, even in the
same location. The warning counts a stay from its first photo to the time it is shown. Nothing about table locations or
stays is stored: they are worked out from `tray_reading` each time.

### `experiment_hidden_tray`

Version 16 (#332). A tray hidden on an experiment's table locations panel, such as a misread tag
(Aaron, 2026-11-02). A hidden tray shows as one line on the panel and gives no warning anywhere;
its tray readings and the export are unchanged. Show deletes the row.

| Column | Type | Meaning |
|---|---|---|
| `experiment_id` | integer | The experiment (`experiment.id`) |
| `tray_id` | integer | The tray's tag ID |
| `hidden_at` | text | When it was hidden, UTC. Hiding it again keeps the first time |

One row per experiment and tray (the two together are the key). The rows of a discarded
experiment are deleted with it; a purge keeps them, with the experiment's record.

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
| `missed_reason` | text | Why it was not taken; NULL when taken. `the app was not running` when it was due before the app last started, `the previous photo took longer than the interval` when due since, otherwise the camera's error |

Photos missed in the running period:

```
SELECT due_at, missed_reason FROM scheduled_photo WHERE capture_id IS NULL ORDER BY due_at
```

### `capture`: whether the clock was set

From version 18 (#62). The Pis have no RTC battery: after a power cut with no network the clock
resumes from the shutdown time, so a photo taken before the network time arrives carries a time
that is too early by about as long as the power was off (11 min 35 s in test C of #62,
2026-11-02). The Gallery shows "Time may be wrong: clock not set" on such a photo, and the
column is in the export's `captures.csv`. The photo's JSON record holds the same as `clock`.

| Column | Type | Meaning |
|---|---|---|
| `clock_synced` | integer | 1 when the clock had the network time at the photo (`/run/systemd/timesync/synchronized` existed), 0 when it had not, NULL for photos from before version 18 |

```sql
SELECT taken_at, path FROM capture WHERE clock_synced = 0 ORDER BY taken_at
```

### `capture`: the JPEG setting the photo was saved at

From version 20 (#359). Every full-size photo is saved at the setting read and changed through
`GET` and `POST /api/photo-quality`; the default is 85 with full colour. Colour at half resolution ("4:2:0") reads plant area about
1.4% low on average and 2.6% low on small plants; full colour ("4:4:4") at 85 about 0.4% and 0.6%
(metrology log 26.1). The photo's JSON record holds the same as `photo_quality`.

| Column | Type | Meaning |
|---|---|---|
| `jpeg_quality` | integer | JPEG quality, 1 to 95. NULL for photos from before version 20, which were all saved at 75 |
| `jpeg_chroma` | text | Colour resolution: "4:2:0" (half both ways) or "4:4:4" (full). NULL for photos from before version 20, which were all "4:2:0" |

```sql
SELECT jpeg_quality, jpeg_chroma, count(*) FROM capture GROUP BY 1, 2
```

### `photo_quality_change`

One row each time the JPEG setting is changed (#359), through `POST /api/photo-quality`. Changes
are allowed during an experiment; each photo's row says what it was saved at. Rows are never
changed or deleted by the rig.

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Row number, increasing |
| `changed_at` | text | When the setting was changed, UTC (`isoformat()`) |
| `quality` | integer | The new JPEG quality, 1 to 95 |
| `chroma` | text | The new colour resolution, "4:2:0" or "4:4:4" |

### `app_start`

One row each time the app starts (#62), written when its scheduler starts. With the scheduled
photos it gives each time the app was down during a schedule: from the last photo taken before a
start until the start. When the app went down is not recorded. Rows are never changed or
deleted by the rig.

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Row number, increasing |
| `started_at` | text | When the app started, UTC (`isoformat()`) |

### `tray_layout`

Version 19 (#343). The Randomize page's suggested layouts and checks, saved with the experiment
(Aaron, 2026-11-02). Trays stand wherever the researcher puts them (Aaron, 2026-11-04): the trays
in the photo a suggestion was read from are grouped into rows and columns, and every crossing is a
place, empty ones too, so the empty spots move as well. Only the table's own edges are edges: the
north and south rows, the west and east columns. A suggestion is drawn by
restricted randomization: no row or column of plants is on an outside edge of the table two
rounds in a row (`randomization.py`). The page works on the newest suggestion until it is
cancelled or a check finds every tray in place, which ends the round (Aaron, 2026-11-04). The
places of the newest suggestion that are empty stay places in the next one, so a row or column
left empty keeps its edge.

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | The layout's number |
| `experiment_id` | integer | The experiment (`experiment.id`) |
| `kind` | text | `suggestion`, `check` or `cancel` (the page's Cancel: the suggestion is no longer worked on) |
| `made_at` | text | When it was made, UTC |
| `capture_id` | integer | A suggestion: the photo the places were read from (the experiment's latest still, or the latest check photo when newer). A check: its own photo. No reference to `capture`: a purge deletes the experiment's photo rows, these rows stay |
| `suggestion_id` | integer | A check or a cancel: its suggestion. NULL for a suggestion |
| `details` | text | JSON, below |

A suggestion's `details`: `seed` (the random seed), `rule_kept` (false when no layout kept the
rule and the one breaking it least was given), `photo` and `taken_at` (the photo read),
`references` (each 2 x 2 tray's tag angle in degrees in its first photo, carried from one
suggestion to the next), `places` (each place: `name`, row and column from the north-west, as
`2-3`; `label`, as people find it, "South row, 3rd from west"; `occupant`, the tray standing there,
null for an empty place; `centre`, full-size photo pixels; `sides`, the table edges it is on;
`px_per_mm`, the calibration's scale), and `trays`, one entry per tray: `tray_id`, `tray_type`
(from its tag ID: `4x5`, `2x2`, `1x1`, `black` or `other`), `place`, `place_label`, `heading`,
`edges` (the rows and columns of plants that place and heading put on a table edge, for example
`["column A", "row 1"]`), `last` (the place it stood in, with its heading, sides and edges, so
every round's edges are kept per tray), `breaks_rule` and `turn` (whether to turn the tray round
from how it lies now).

`heading` depends on the tray type: `SW` or `NE` (the corner of cell A1) for a 4 x 5 tray, read
from where its tag lies against the centre of its blue outline; `as first` or `turned` for a 2 x 2
tray, whose tag is fixed in its middle, read as the tag's angle against `references`; null for
every other tray, which gets a place only. `edges` is null where the heading is null. For a 2 x 2
tray, row 1 is the end that faced south in its first photo and column A the side that faced west.

A check's `details`: `photo` and `taken_at` (the check photo, a rig photo with purpose
`layout check`, never one of the experiment's stills), `places` (the suggestion's), and `trays`:
`tray_id`, `tray_type`, `status` (`in place`, `wrong place`, `turned`, `wrong place, turned`,
`heading not read`, `missing`, `not in layout`), `wanted` (place, label, heading), `found_at` (the place
whose centre is within 150 mm of the tray's, or null; a 4 x 5 tray whose own outline is not found
is matched by the nearer of its two possible centres), `heading`, `centre` (full-size photo
pixels), `edges` (of the place it is found in) and `breaks_rule`.

A cancel's `details` is empty: the row records when the suggestion was cancelled.

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
slot`, before version 14: a tray carried over the table, or a loose tag lying on a tray) make the
whole photo chamber activity (`exclusion` `visit`), and both trays show "2 trays in one place"
(#315; it named the slot before #332). Before version 13 the table allowed one row per tag in a photo, and
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
the same to the rig. It is shown with the table location it was last found in (#332). A tray
is listed as moved when its centre is in another table location than in the experiment's previous read
photo; a nudge within its location or a turn is not a move (#332). A tray with no tag is never listed
as not found or as moved: it cannot be followed from photo to photo. Only photos with the status `read` count, so a dark photo is not a tray
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
