# Round 3: plant area against a Helios scan (issue #411)

Method and results: `docs/metrology-log.md` section 35. Read that first. This folder holds the
scripts and the small outputs; the photographs are too large for the repository and their
locations are given below.

**Label: reference comparison.** Helios is a second instrument, not a known answer
(metrology log 35). The known answer is a person's outline on each photo.

## Order of work (metrology log 35, *Order*)

1. the scan — done, 6 and 12 November 2026;
2. the plants are chosen and two crops made per plant — **this folder, done**;
3. a person outlines each crop in ImageJ from nothing, before seeing any mask, area or ratio;
4. the comparison is run only after the outlines are saved.

Step 3 has not been done. **Nothing in this folder shows a mask, an area or a ratio**, on
purpose: an outline drawn after seeing one is pulled toward it.

## Where the raw data is

| What | Where |
|---|---|
| Helios export | `wout_potato_RGB2_4.7z`, from the lab, 26 November 2026. 14 scans: 7 trays on each of 2 dates, each as `_Original` and `_FishEyeCorrected`, 4112 x 3006 px PNG. Not in the repository |
| Rig photos and `rig.db` | the old production Pi `ac-testing`, recovered with `ddrescue` to `ac-testing-rootfs.img` on the `NPEC_DATA` drive. Read with `debugfs`, never mounted and never written |
| The 20 crops for the outlines | `crops/manifest.json` here names every one; the images themselves are on the scratch viewer, `411-helios/crops/` |

## The scripts

Each takes its inputs as arguments and writes next to them. They need `opencv`, `numpy` and
Python's `sqlite3`; they import nothing from `src/npec_rig/`.

| Script | What it does |
|---|---|
| `detect_tag.py` | lists the AprilTags in any photo, with each tag's side in pixels. Used to match the Helios tray numbers to the rig's tray tags |
| `pair.py` | for each scan, the rig photo it pairs with: the last lit, not excluded photo before the tray's tag stops being seen. Writes `pairs.json` |
| `cellframe.py` | each cell's centre in its tray tag's own frame, measured from a rig photo. Gives the cell spacing in tag sides |
| `helios_grid.py` | places the 4 x 5 cell grid on a Helios tray photo from its tag, and draws it for checking |
| `make_crops.py` | the crop pairs for the outlines, one from each camera per plant, with `crops/manifest.json` |
| `blind.py` | gives every crop a blind name in a recorded shuffled order and writes `crops/blind_key.csv` |

## The handoff for the outlines (step 3)

`handoff/README.md` is what goes to the person doing the outlining: what counts as plant, the zoom
for each camera, and the output to send back. With the 20 images it is `npec-411-outlines.zip` on
the scratch viewer, under `411-helios/`.

The crops are named `plant01.png` to `plant20.png` in a shuffled order (`blind.py`, seed 411), with
the two crops of one plant at least five places apart, so the person cannot tell which crops are
pairs. **`crops/blind_key.csv` holds the mapping. Do not open it until the outlines are saved**; it
is in the repository so the comparison can be checked afterwards, not so it can be read before.

## Running them

```bash
python detect_tag.py <photo> [<photo> ...]
python pair.py rig.db > pairs.json
python cellframe.py rig.db <rig photo> <capture id> cellframe.json
python helios_grid.py <helios photo> grid.json check.png
python make_crops.py rig.db <helios folder> <rig photo folder> crops/
```

## What is still open

- The rim-to-tag-face depth, so the height difference between the tag and the leaves can be
  turned into a figure (Aaron is measuring it).
- The leaf dry weight from the researcher, and whether a known dry weight to area conversion
  exists (issue #411).
- This export holds no point cloud, so no plant height. Section 35 expected one.
