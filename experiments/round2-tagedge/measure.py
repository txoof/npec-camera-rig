"""Tag edges against tag spacing in the stored calibration and validation photos, metrology log 18.
Read only: rig.db is opened read-only and nothing under /var/lib/npec-rig/ is written.

    PYTHONPATH=src python experiments/round2-tagedge/measure.py OUT_DIR [--only STEM_OR_CAPTURE ...]

Writes OUT_DIR/sheets.csv (one row per photo and sheet) and OUT_DIR/skipped.csv, and prints them.
Per pair of tags on one sheet and one manifest page, 30 to 90 mm apart by design:
edge scale = mean side px / 30.0 mm, spacing scale = centre distance px / designed mm,
ratio = edge / spacing.
"""

import argparse
import csv
import json
import math
import sqlite3
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from npec_rig import calibration_store, validation_store
from npec_rig.calibration import scale_field_from_dict
from npec_rig.certainty_map import SlotLayoutError, group_sheets, sheets_by_slot, slot_layout_from_dict
from npec_rig.tags import TagDetection, detect_tags, tag_side_px

DATA = Path("/var/lib/npec-rig")
DB = DATA / "rig.db"
MANIFEST = Path(__file__).resolve().parents[2] / "reference/calibration-sheets/apriltags-36h11-30mm-a4-300-449.manifest.json"
TAG_MM = 30.0  # calliper value of the current sheets (CLAUDE.md Facts)
IMAGE_CENTRE = (4576.0, 3472.0)
PAIR_MM = (30.0, 90.0)
# 17.6: experiment 18 stills with two sheets laid in, under DATA (prefixes)
EXTRA_PHOTOS = ["experiments/2026-10-22_df206967/stills/2026-10-23/141653", "experiments/2026-10-22_df206967/stills/2026-10-23/141753"]


def load_manifest():
    tags = json.loads(MANIFEST.read_text())["tags"]
    return {t["id"]: (t["page"], t["center_x_mm"], t["center_y_mm"]) for t in tags}


def stem_time(stem):
    return datetime.strptime(stem, "%Y%m%dT%H%M%S%f").replace(tzinfo=timezone.utc)


def capture_time(capture):
    return datetime.strptime("/".join(capture.split("/")[-2:]), "%Y-%m-%d/%H%M%S_%f").replace(tzinfo=timezone.utc)


def calibrations():
    """{stem: (created_at, artifact)} for every saved calibration."""
    out = {}
    for path in calibration_store.list_calibrations():
        if path.name == "current.json":
            continue
        try:
            out[path.stem] = calibration_store.load_calibration(path)
        except ValueError:  # an older artifact version: only the parts used here
            data = json.loads(path.read_text())
            out[path.stem] = SimpleNamespace(
                scale_field=scale_field_from_dict(data["scale_field"]),
                lens_position=data.get("lens_position"),
                calibration_tag_size_mm=data.get("calibration_tag_size_mm"),
            )
    return out


def photos(db, cals):
    """[(kind, capture or stem, image path, sidecar path or None, calibration stem)] in time order."""
    found = {}
    for stem in cals:
        jpg = DATA / "calibration/frames" / f"{stem}.jpg"
        if jpg.exists():
            found[stem] = ("calibration (old folder)", stem, jpg, None, stem)
        path = calibration_store.calibration_frame_path(stem)
        if path is not None and path.exists() and DATA / "rig" in path.parents:
            capture = f"{path.parent.name}/{path.stem}"
            found[capture] = ("calibration", capture, path, path.with_suffix(".json"), stem)
    session_cal = {}
    for session in validation_store.list_sessions():
        for round_ in session.get("rounds", []):
            session_cal[round_["capture"]] = session["calibration_stem"]
    rows = db.execute(
        "SELECT path, purpose, calibration FROM capture WHERE purpose IN ('calibration', 'validation')"
    ).fetchall()
    captures = {r[0].removeprefix("rig/"): r[1] for r in rows}
    db_cal = {r[0].removeprefix("rig/"): r[2] for r in rows}
    for capture in session_cal:
        captures.setdefault(capture, "validation")
    for prefix in EXTRA_PHOTOS:
        for jpg in sorted(DATA.glob(f"{prefix}*.jpg")):
            captures[str(jpg.relative_to(DATA).with_suffix(""))] = "experiment still (17.6)"
    for capture, purpose in captures.items():
        if capture in found:
            continue
        jpg = DATA / f"{capture if capture.startswith('experiments/') else 'rig/' + capture}.jpg"
        if not jpg.exists():
            continue
        cal = session_cal.get(capture) or db_cal.get(capture) or latest_before(cals, capture_time(capture))
        if purpose == "calibration":
            match = [s for s in cals if calibration_store.calibration_frame_path(s) == jpg]
            cal = match[0] if match else latest_before(cals, capture_time(capture))
        found[capture] = (purpose, capture, jpg, jpg.with_suffix(".json"), cal)
    return sorted(found.values(), key=lambda p: "/".join(p[1].split("/")[-2:]).replace("/", "T").replace("-", ""))


def latest_before(cals, when):
    before = [s for s in cals if stem_time(s) <= when]
    return max(before, key=stem_time) if before else None


def stored_tags(db, capture):
    row = db.execute(
        "SELECT value FROM capture_analysis WHERE kind='tags' AND source=? ORDER BY version DESC LIMIT 1",
        (capture,),
    ).fetchone()
    if row is None:
        return None
    return [
        TagDetection(t["tag_id"], tuple(tuple(c) for c in t["corners"]), tuple(t["centre"]))
        for t in json.loads(row[0])
    ]


def fresh_tags(jpg):
    import cv2

    frame = cv2.imread(str(jpg), cv2.IMREAD_GRAYSCALE)
    return detect_tags(frame)


def sidecar_values(path):
    if path is None or not path.exists():
        return {}
    meta = json.loads(path.read_text()).get("sensor_metadata", {})
    gains = meta.get("ColourGains") or [None, None]
    return {
        "exposure_us": meta.get("ExposureTime"),
        "analogue_gain": meta.get("AnalogueGain"),
        "colour_gain_r": gains[0],
        "colour_gain_b": gains[1],
        "lens_position": meta.get("LensPosition"),
    }


def pair_ratios(tags, manifest):
    """[(ratio, inset px per edge, 'across' | 'down' | 'diagonal', edge scale, spacing scale)] for one
    sheet's tags; scales in px/mm."""
    out = []
    for i, a in enumerate(tags):
        for b in tags[i + 1 :]:
            pa, pb = manifest[a.tag_id], manifest[b.tag_id]
            if pa[0] != pb[0]:
                continue
            dx, dy = pb[1] - pa[1], pb[2] - pa[2]
            mm = math.hypot(dx, dy)
            if not PAIR_MM[0] <= mm <= PAIR_MM[1]:
                continue
            px = math.dist(a.centre, b.centre)
            side = (tag_side_px(a.corners) + tag_side_px(b.corners)) / 2
            spacing = px / mm
            direction = "across" if abs(dy) < 1 else "down" if abs(dx) < 1 else "diagonal"
            out.append(((side / TAG_MM) / spacing, (TAG_MM * spacing - side) / 2, direction, side / TAG_MM, spacing))
    return out


def quartiles(values):
    if len(values) < 2:
        return (values[0], values[0]) if values else (None, None)
    q = statistics.quantiles(values, n=4)
    return q[0], q[2]


def measure(entry, db, cals, manifest):
    kind, name, jpg, sidecar, cal_stem = entry
    tags = stored_tags(db, name)
    source = "stored v2"
    if tags is None:
        tags = fresh_tags(jpg)
        source = "detected again"
    tags = [t for t in tags if 300 <= t.tag_id <= 449]
    if cal_stem is None or cal_stem not in cals:
        return [], f"no calibration for the photo ({cal_stem})"
    artifact = cals[cal_stem]
    try:
        sheets = group_sheets(tags, artifact.scale_field, TAG_MM)
    except (SlotLayoutError, ValueError) as exc:
        return [], f"sheets not grouped: {exc}"
    by_id = {}
    for t in tags:
        by_id.setdefault(t.tag_id, []).append(t)
    layout = validation_store.load_slot_layout(cal_stem)
    names = {}
    note = ""
    if layout:
        try:
            placed = sheets_by_slot(sheets, slot_layout_from_dict(layout["slots"]), artifact.scale_field)
            names = {id(s): n for n, s in placed.items()}
        except SlotLayoutError as exc:
            note = f"slots not named: {exc}"
    else:
        note = "no slot layout"
    side = sidecar_values(sidecar)
    rows = []
    for sheet in sheets:
        ids = {e.tag_id for e in sheet.tags}
        members = [
            min(by_id[i], key=lambda t: math.dist(t.centre, (e.x, e.y)))
            for e in sheet.tags
            for i in [e.tag_id]
        ]
        pairs = pair_ratios(members, manifest)
        if not pairs:
            continue
        ratios = [p[0] for p in pairs]
        lo, hi = quartiles(ratios)
        split = {d: [p[0] for p in pairs if p[2] == d] for d in ("across", "down")}
        cx, cy = sheet.centre
        rows.append(
            {
                "photo": name,
                "kind": kind,
                "calibration": cal_stem,
                "tag_size_used_mm": getattr(artifact, "calibration_tag_size_mm", None),
                "slot": names.get(id(sheet), ""),
                "sheet_x": round(cx),
                "sheet_y": round(cy),
                "from_centre_px": round(math.dist((cx, cy), IMAGE_CENTRE)),
                "tags": len(ids),
                "pairs": len(pairs),
                "ratio_median": round(statistics.median(ratios), 5),
                "ratio_q1": round(lo, 5),
                "ratio_q3": round(hi, 5),
                "ratio_across": round(statistics.median(split["across"]), 5) if split["across"] else "",
                "ratio_down": round(statistics.median(split["down"]), 5) if split["down"] else "",
                "edge_scale_px_per_mm": round(statistics.median(p[3] for p in pairs), 4),
                "spacing_scale_px_per_mm": round(statistics.median(p[4] for p in pairs), 4),
                "inset_px_per_edge": round(statistics.median(p[1] for p in pairs), 3),
                "mean_side_px": round(statistics.mean(tag_side_px(t.corners) for t in members), 2),
                "lens_position_calibration": round(artifact.lens_position, 3) if artifact.lens_position else "",
                **side,
                "tags_from": source,
            }
        )
    return rows, note


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--only", nargs="*", help="photos (capture or stem) to measure, default all")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cals = calibrations()
    manifest = load_manifest()
    entries = photos(db, cals)
    if args.only:
        entries = [e for e in entries if e[1] in args.only]
    rows, skipped = [], []
    for entry in entries:
        found, note = measure(entry, db, cals, manifest)
        rows += found
        if note or not found:
            skipped.append({"photo": entry[1], "kind": entry[0], "sheets measured": len(found), "note": note or "no pairs"})
        print(f"{entry[1]:32} {entry[0]:24} sheets {len(found):3}  {note}", file=sys.stderr, flush=True)
    for name, table in (("sheets.csv", rows), ("skipped.csv", skipped)):
        if table:
            with open(args.out / name, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list({k: 0 for r in table for k in r}))
                writer.writeheader()
                writer.writerows(table)
    if rows:
        all_ratios = [r["ratio_median"] for r in rows]
        print(f"{len(rows)} sheets, median of sheet medians {statistics.median(all_ratios):.4f}")


if __name__ == "__main__":
    main()
