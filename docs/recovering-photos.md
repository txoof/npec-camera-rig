# Recovering photos that have no record

The Purge dialog says "N photos have no record" when the rig has photo files on its disk that its
database does not list. Purge deletes the whole experiment folder, so these photos are lost with it.
This page says what those files are, how to read them and how to copy them off the rig first.

Purge is not blocked by this warning. It is your decision whether the photos are worth copying.

## Why a photo has no record

The rig saves a photo to disk first and writes its row in the database (`rig.db`) after. If the
database is busy for longer than the rig waits, the photo is kept and its row is added later. The
rig adds missing rows when it starts, when an experiment is stopped, before an export and before a
Purge. A photo is still without a row after all of these when its info file cannot be read: it is
empty or damaged, as after a power cut.

Photos without a row are not in the Gallery and not in an export.

## What the rig keeps for each photo

Two files with the same name, in the experiment's folder on the rig:

```
/var/lib/npec-rig/experiments/<folder>/stills/<YYYY-MM-DD>/<HHMMSS_microseconds>.jpg
/var/lib/npec-rig/experiments/<folder>/stills/<YYYY-MM-DD>/<HHMMSS_microseconds>.json
```

The `.jpg` is the full-size photo. The `.json` is its info file. The folder name is the day and the
file name is the time of day, both in UTC. The chamber keeps Dutch local time: add 1 hour in winter
and 2 in summer.

## What an info file holds

It is a text file. Open it in any text editor. The main fields:

| Field | Meaning |
|---|---|
| `timestamp` | When the photo was taken, UTC |
| `purpose` | `capture` for an experiment photo |
| `experiment` | The experiment's id, name and folder |
| `schedule` | For a scheduled photo: when its schedule started (`since`), its slot number and when it was due (`due_at`). A photo taken by hand has none |
| `calibration` | The calibration the photo is measured with, or null for none |
| `focus` and `lens_position` | The lens lock and where the lens was |
| `sensor_metadata` | Exposure time, gain and lens position the camera reported |
| `flags` | Reasons the photo is not covered by the validation bands, if any |
| `clock` | Whether the clock had the network time |
| `photo_quality` | The JPEG setting the photo was saved at |

An older photo may lack some fields. The meaning of every field in an export is in the export's
`README.txt`.

If the file is empty or damaged, the `.jpg` is still good: the time it was taken is in its file name.

## Copy the photos off the rig

Copy the experiment's whole `stills` folder. It holds the photos with a record as well, so nothing
needs sorting before the copy.

From a Mac or Linux computer, or from Windows PowerShell:

```
scp -r pi@<rig address>:/var/lib/npec-rig/experiments/<folder>/stills ./<folder>-stills
```

or, to resume after an interruption:

```
rsync -av pi@<rig address>:/var/lib/npec-rig/experiments/<folder>/stills/ ./<folder>-stills/
```

`<folder>` is the experiment's folder name, shown on the Experiments page and in the Purge dialog.
The copy leaves the rig's files where they are.

## Which photos are the ones without a record

An export's `captures.csv` has one line for each photo with a record, in its `path` column. A photo
in the copied `stills` folder whose name is not in `captures.csv` is one without a record.

## Then

Check that the copy opens, then Purge. Purge deletes the folder on the rig, and nothing brings it back.
