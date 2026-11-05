"""JPEG quality against tags and plant areas (metrology log 26, #355). Run on the rig, one still
per process (64MP: about 1.1 GiB for a tag search):

    python analyse.py RUN_DIR trays        # tray outlines from frame0 at setting B, saved once
    python analyse.py RUN_DIR frame <i>    # every setting of frame<i>: tags and plant areas

Writes only inside RUN_DIR: the JPEGs, trays.json, frame<i>_results.json. Reads rig.db read-only
for the calibration the experiment's newest still was read with.
"""
import gc
import io
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from npec_rig import images, segmentation, tags, tray_readings
from npec_rig.calibration_store import calibration_for_photos, load_saved_calibration
from npec_rig.camera import array_to_jpeg
from npec_rig.tray_placement import find_outlines, name_trays

SETTINGS = {  # name: Pillow save options; None = the uncompressed array
    "A uncompressed": None,
    "B today (75, half colour)": {"quality": 75, "subsampling": 2},
    "C 85 half colour": {"quality": 85, "subsampling": 2},
    "D 95 half colour": {"quality": 95, "subsampling": 2},
    "E 95 full colour": {"quality": 95, "subsampling": 0},
    # Added after the first results (log 26.1): which of quality and colour resolution matters.
    "F 75 full colour": {"quality": 75, "subsampling": 0},
    "G 85 full colour": {"quality": 85, "subsampling": 0},
    "H 90 full colour": {"quality": 90, "subsampling": 0},
}
SLUG = {name: name[0] for name in SETTINGS}

run = Path(sys.argv[1])
mode = sys.argv[2]


def calibration():
    db = sqlite3.connect("file:/var/lib/npec-rig/rig.db?mode=ro", uri=True)
    (stem,) = db.execute(
        "select calibration from capture where calibration is not null and experiment_id = 3 order by id desc limit 1"
    ).fetchone()
    used = calibration_for_photos(stem)
    return stem, used, load_saved_calibration(used).scale_field


def jpeg_path(i, name):
    return run / f"frame{i}_{SLUG[name]}.jpg"


def frame_at(i, name, raw):
    """The still as the app would read it back at this setting."""
    if SETTINGS[name] is None:
        return raw
    path = jpeg_path(i, name)
    if not path.exists():
        buf = io.BytesIO()
        Image.fromarray(raw).save(buf, format="JPEG", **SETTINGS[name])
        data = buf.getvalue()
        if SLUG[name] == "B":
            assert data == array_to_jpeg(raw), "setting B is not what the app writes"
        path.write_bytes(data)
    return images.decode_full(path)


stem, used, scale_field = calibration()

if mode == "trays":
    raw = np.load(run / "frame0.npy")
    name = "B today (75, half colour)"
    frame = frame_at(0, name, raw)
    del raw
    detections = tags.detect_tags(frame)
    del frame
    gc.collect()
    with Image.open(jpeg_path(0, name)) as image:  # as tray_readings._small_copy does
        width = image.size[0]
        f = tray_readings.FINDER_FACTOR
        image.draft("RGB", (image.size[0] // f, image.size[1] // f))
        small = np.asarray(image.convert("RGB"))
    outlines = find_outlines(small, scale_field, width / small.shape[1])
    placed = [p for p in name_trays(outlines, detections) if p.outline is not None]
    out = {"calibration_of_newest_still": stem, "calibration_used": used,
           "trays": [{"tray_id": p.tray_id, "centre": list(p.centre),
                      "outline": [list(c) for c in p.outline]} for p in placed]}
    (run / "trays.json").write_text(json.dumps(out, indent=1))
    print(len(placed), "trays", [p.tray_id for p in placed])
    sys.exit()

i = int(sys.argv[3])
trays = json.loads((run / "trays.json").read_text())["trays"]
pairs = [(tuple(map(tuple, t["outline"])), tuple(t["centre"])) for t in trays]
raw = np.ascontiguousarray(np.load(run / f"frame{i}.npy")[..., :3])
results = {"frame": i, "calibration_used": used, "settings": {}}
for name in SETTINGS:
    frame = frame_at(i, name, raw)
    detections = tags.detect_tags(frame)
    mask = tray_readings.SEGMENTER.segment(frame)
    measures = segmentation.measure_trays(mask, pairs, scale_field)
    results["settings"][name] = {
        "file_bytes": None if SETTINGS[name] is None else jpeg_path(i, name).stat().st_size,
        "segmenter": tray_readings.SEGMENTER.name,
        "tags": {str(d.tag_id): [list(c) for c in d.corners] for d in detections},
        "trays": [{"tray_id": t["tray_id"], "plant_px": m.plant_px, "area_mm2": m.area_mm2}
                  for t, m in zip(trays, measures, strict=True)],
        "mask_px_total": int(mask.sum()),
    }
    print(i, name, len(detections), "tags", int(mask.sum()), "plant px", flush=True)
    del frame, mask
    gc.collect()
(run / f"frame{i}_results.json").write_text(json.dumps(results, indent=1))
