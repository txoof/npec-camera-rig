"""Time lapses of one tray of experiment 18 and of two of its cells, with each rule's saved mask (#394).

Runs on production (ac-testing), so only the finished videos are copied off it:

    ssh pi@ac-testing 'ulimit -v 3000000; nice -n 15 /home/pi/npec_camera_rig/.venv/bin/python3 - OUT_DIR [N]' < timelapse.py

N: stop after N frames (a trial run).

Reads only: rig.db opened read-only (`mode=ro`), the photos and the saved masks (`<photo>.png`, fixed
green cutoff; `<photo>.grown.png`, grow from leaf cores, saved since the #410 Reprocess). Writes only
OUT_DIR (a new folder under /tmp): one JPEG per frame and clip, then an MP4 per clip (ffmpeg).

Frames: per UTC hour, the first photo that was read, has no exclusion, and has the tray `placed`
with an outline and none of the warnings of 16.9 rule 8. Every frame is turned so that cell A1
lies bottom left, D1 bottom right, D5 top right, A5 top left, whichever way the tray lies on the
table (from the stored cell centres), so a turn in a shuffle does not turn the picture. A cell
clip shows the cell's opening (stored corners) with half a cell's width around it, since leaves
spread over the neighbours. Marks: magenta, the mask's edge and a light magenta fill.
"""
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None
ROOT = Path("/var/lib/npec-rig")
DB = f"file:{ROOT / 'rig.db'}?mode=ro"
EXPERIMENT, TRAY, CELLS = 18, 4, ("C3", "B5")
BAD_WARN = {"no tag", "tag seen, tray not found in the photo", "two tags in one tray outline"}
TRAY_MM = (305.0, 366.0)          # tray_placement.TRAY_SIZE_MM: columns A to D across the 305 mm side
TRAY_PX_PER_MM = 2.0              # whole-tray frames: 610 x 732 px
CELL_PX, CELL_MARGIN = 300, 150   # cell clips: the opening 300 px across, 150 px around it
MAGENTA = np.array([255, 0, 255], dtype=np.float32)
FPS = 12
CHAMBER = ZoneInfo("Europe/Amsterdam")
BAND = 44                         # text band under each frame, px


def frames(db):
    """The chosen photos with tray TRAY's outline and its cells, in time order."""
    rows = db.execute(
        """select c.id, c.path, c.taken_at, t.outline, t.warnings, t.placement
           from capture c join tray_read r on r.capture_id = c.id
           join tray_reading t on t.capture_id = c.id and t.tray_id = ?
           left join exclusion e on e.capture_id = c.id
           where c.experiment_id = ? and r.status = 'read' and e.name is null
           order by c.taken_at""", (TRAY, EXPERIMENT)).fetchall()
    seen = set()
    for cid, path, taken, outline, warnings, placement in rows:
        hour = taken[:13]
        if hour in seen or placement != "placed" or not outline:
            continue
        if set(json.loads(warnings or "[]")) & BAD_WARN:
            continue
        cells = {r[0]: r[1:] for r in db.execute(
            """select cell, centre_x_px, centre_y_px, corners, area_mm2, grown_area_mm2
               from cell_reading where capture_id = ? and tray_id = ?""", (cid, TRAY))}
        if not {"A1", "D1", "D5", "A5", *CELLS} <= cells.keys():
            continue
        photo = ROOT / f"{path}.jpg"
        masks = {"fixed green cutoff": ROOT / "masks" / f"{path}.png",
                 "grow from leaf cores": ROOT / "masks" / f"{path}.grown.png"}
        if not photo.exists() or not all(m.exists() for m in masks.values()):
            continue
        seen.add(hour)
        yield dict(id=cid, path=path, taken=datetime.fromisoformat(taken), outline=json.loads(outline),
                   cells=cells, photo=photo, masks=masks)


def tray_homography(f):
    """Full-size pixels to the upright tray frame, A1 bottom left, or None when the outline's
    corners cannot be matched one to one with the corner cells."""
    corners = np.asarray(f["outline"], dtype=np.float64)
    order = []
    for name in ("A1", "D1", "D5", "A5"):
        cx, cy = f["cells"][name][0], f["cells"][name][1]
        order.append(int(np.argmin(np.hypot(corners[:, 0] - cx, corners[:, 1] - cy))))
    if len(set(order)) != 4:
        return None
    # Same handedness as the photo (y down): A1 to D1 then A1 to A5 turn the same way as right then
    # up, so the frame is turned, never mirrored. Checked on photos of 22 Oct to 17 Nov.
    (a1, d1, a5) = (np.asarray(f["cells"][k][:2], dtype=np.float64) for k in ("A1", "D1", "A5"))
    u, v = d1 - a1, a5 - a1
    if u[0] * v[1] - u[1] * v[0] >= 0:
        return None
    w, h = TRAY_MM[0] * TRAY_PX_PER_MM, TRAY_MM[1] * TRAY_PX_PER_MM
    dst = np.float32([[0, h], [w, h], [w, 0], [0, 0]])
    return cv2.getPerspectiveTransform(np.float32(corners[order]), dst), (int(w), int(h))


def cell_homography(f, cell, tray_h):
    """Full-size pixels to the upright cell clip, its corners ordered through the tray's turn."""
    c = np.asarray(json.loads(f["cells"][cell][2]), dtype=np.float32)
    up = cv2.perspectiveTransform(c.reshape(-1, 1, 2), tray_h).reshape(-1, 2)
    s, d = up.sum(axis=1), up[:, 0] - up[:, 1]
    # In the upright frame (y down): top left has the smallest x + y, bottom right the largest;
    # top right the largest x - y, bottom left the smallest.
    tl, br, tr, bl = c[np.argmin(s)], c[np.argmax(s)], c[np.argmax(d)], c[np.argmin(d)]
    m, n = CELL_MARGIN, CELL_MARGIN + CELL_PX
    dst = np.float32([[m, m], [n, m], [n, n], [m, n]])
    size = CELL_PX + 2 * CELL_MARGIN
    return cv2.getPerspectiveTransform(np.float32([tl, tr, br, bl]), dst), (size, size)


def overlay(rgb, mask):
    """Magenta edge and light magenta fill of `mask` on `rgb` (both the clip's size)."""
    out = rgb.astype(np.float32)
    out[mask] = 0.75 * out[mask] + 0.25 * MAGENTA
    m8 = mask.view(np.uint8)
    edge = cv2.dilate(m8 - cv2.erode(m8, np.ones((3, 3), np.uint8)), np.ones((2, 2), np.uint8)) > 0
    out[edge] = MAGENTA
    return out.astype(np.uint8)


def labelled(rgb, text, font):
    img = Image.new("RGB", (rgb.shape[1], rgb.shape[0] + BAND), "white")
    img.paste(Image.fromarray(rgb), (0, 0))
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(text.split("\n")):
        draw.text((8, rgb.shape[0] + 3 + 20 * i), line, fill=(20, 20, 20), font=font)
    return img


def main(out, limit=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    db = sqlite3.connect(DB, uri=True)
    try:  # DejaVu has the ² sign; the built-in font does not
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except OSError:
        font = ImageFont.load_default(size=16)
    clips = ["tray"] + [f"{c} {kind}" for c in CELLS for kind in ("photo", "fixed green cutoff", "grow from leaf cores")]
    dirs = {name: out / "frames" / name.replace(" ", "_") for name in clips}
    for d in dirs.values():
        d.mkdir(parents=True)
    log = open(out / "frames.csv", "w")
    log.write("frame,capture_id,path,taken_at_utc,C3 fixed green cutoff mm2,C3 grow from leaf cores mm2,"
              "B5 fixed green cutoff mm2,B5 grow from leaf cores mm2\n")
    n = 0
    for f in frames(db):
        homs = tray_homography(f)
        if homs is None:
            continue
        tray_h, tray_size = homs
        when = f"{f['taken']:%d %b %H:%M} UTC ({f['taken'].astimezone(CHAMBER):%H:%M} chamber)"
        with Image.open(f["photo"]) as image:
            rgb = np.asarray(image.convert("RGB"))
        tray = cv2.warpPerspective(rgb, tray_h, tray_size, flags=cv2.INTER_AREA)
        labelled(tray, f"Tray {TRAY}, experiment 18, A1 bottom left\n{when}", font).save(
            dirs["tray"] / f"{n:05d}.jpg", quality=90)
        cell_hs = {c: cell_homography(f, c, tray_h) for c in CELLS}
        crops = {c: cv2.warpPerspective(rgb, h, s, flags=cv2.INTER_AREA) for c, (h, s) in cell_hs.items()}
        del rgb
        areas = {}
        for c in CELLS:
            labelled(crops[c], f"Tray {TRAY} cell {c}, photo\n{when}", font).save(
                dirs[f"{c} photo"] / f"{n:05d}.jpg", quality=90)
        for rule, path in f["masks"].items():
            with Image.open(path) as image:
                mask = np.asarray(image.convert("L")) > 0
            for c, (h, s) in cell_hs.items():
                m = cv2.warpPerspective(mask.view(np.uint8), h, s, flags=cv2.INTER_NEAREST) > 0
                area = f["cells"][c][3] if rule == "fixed green cutoff" else f["cells"][c][4]
                areas[(c, rule)] = area
                shown = "no area" if not area else f"{area:.0f} mm²"
                labelled(overlay(crops[c], m), f"Tray {TRAY} cell {c}, {rule}: {shown}\n{when}", font).save(
                    dirs[f"{c} {rule}"] / f"{n:05d}.jpg", quality=90)
            del mask
        log.write(",".join(str(x) for x in (n, f["id"], f["path"], f["taken"].isoformat(),
                                             *(areas[(c, r)] for c in CELLS for r in f["masks"])) ) + "\n")
        log.flush()
        n += 1
        if limit and n >= limit:
            break
        if n % 25 == 0:
            print("frames", n, f["taken"].isoformat(), flush=True)
    print("frames", n, flush=True)
    for name, d in dirs.items():
        video = out / f"tray{TRAY}_{name.replace(' ', '_')}.mp4"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-framerate", str(FPS), "-i", str(d / "%05d.jpg"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", str(video)], check=True)
        print("video", video.name, video.stat().st_size, flush=True)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None)
