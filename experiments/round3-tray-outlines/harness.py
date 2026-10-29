"""Issue #328: shared harness for the tray finders. Loads the test stills, gives each finder what
the rig knows (tags, scale, FastSAM objects), scores what it finds against the reference, and
writes pictures for the image viewer (~/scratch/sam297, http://testpi-02:8001/).

A finder is a function `find(still: Still) -> list[dict]`, each dict one tray:

    {"outline": [[x, y], ...] full-size px,  "tray_id": int | None,  "how": str,  "warnings": [str]}

Run one over every still:

    PYTHONPATH=~/wt/npec-328-tray-outlines/src .venv/bin/python run.py methods_blue:find --version v1

Reference (what a finder is scored against):
- production: each tray's placement from its A1 tag (`tray_placement.place_trays`), the rig's own
  answer, itself good to about 10 mm (metrology log 15.5l); 12 tagged 4x5 trays, touching in rows.
- development: tray top-rim corners marked by eye on full-size crops (ref/dev_reference.json);
  9 untagged 2x2 trays; N1 lies partly outside the frame (not scored), S1 touches the edge.
- hard: the 18 round 1 shuffle stills of 19 October (production, metrology log 15.5, "simple
  segmentation test"): 12 tagged 4x5 trays full of pots, with gaps (groups 1, 3) and touching
  within rows (2, 4). Reference: the tag placement with A1 at the corner the shuffle plan put it
  (the rig puts tray 6 in the wrong slot in every still, its tag lying the other way).

A tray is found when an outline's centre is within CENTRE_MM of the reference centre (decision 2
of #328) and the two outlines overlap by at least IOU_MIN (a guard against outlines of the wrong
size, such as two trays merged or half a tray). Good: 12 of 12 in production, at least 7 of 8
whole trays in development (Aaron, 2026-10-29: 7 with two partly outside; only one is), 12
of 12 on the hard stills.
"""

from __future__ import annotations

import csv
import functools
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

DATA = Path(os.environ.get("TRAY328_DATA", "/home/pi/.claude/jobs/44c5d2e5/tmp"))
VIEW = Path(os.environ.get("TRAY328_VIEW", "/home/pi/scratch/sam297"))
OBJECTS = Path(os.environ.get("TRAY328_OBJECTS", DATA / "objects-v1"))
CAL = {"prod": ("cal-ac-testing", "20261022T072523939958"),
       "dev": ("cal-npec-rig-01", "20261021T140121832677"),
       "hard": ("cal-ac-testing", "20261014T111147292361")}
RIGS = ("prod", "dev", "hard")
# "held": stills not used for tuning, each with its own calibration (held/calibrations.json:
# stem -> [calibration folder, calibration stem], from the photo's row in its rig's rig.db).
# No known answer: Aaron inspects the pictures.
TRAY_MM = (305.0, 366.0)  # outer size of every blue tray type, lip included (reference/trays.md)
CENTRE_MM = 30.0
IOU_MIN = 0.80
Q = 4  # quarter-size copies: full px = Q * quarter px
# Besides each rig's first and last still: the first still of development layout 2, and one still
# of each hard group (1 and 3 with gaps, 2 and 4 touching).
LAYOUT_PICTURES = {"123005_857835", "120843_746861", "121045_059986", "121231_081714", "121449_465196"}


def _cal(folder, stem):
    from npec_rig import calibration_store, validation_store
    from npec_rig.tray_readings import calibration_for_photos

    os.environ["NPEC_RIG_CALIBRATION_DIR"] = str(DATA / folder)  # read on every call
    s =calibration_for_photos(stem)
    art = calibration_store.load_saved_calibration(s)
    layout = validation_store.load_slot_layout(s) or validation_store.load_slot_layout(stem)
    return art.scale_field, layout["slots"]


_CALS: dict = {}


@functools.cache
def _held_cals():
    return json.loads((DATA / "held" / "calibrations.json").read_text())


@dataclass(frozen=True)
class Still:
    rig: str  # "prod", "dev" or "hard" (production, 19 October: the round 1 shuffles)
    stem: str

    @property
    def path(self) -> Path:
        return DATA / "stills" / self.rig / f"{self.stem}.jpg"

    def full(self) -> np.ndarray:
        """The 64MP still, BGR. About 190 MB: load only when needed."""
        return cv2.imread(str(self.path))

    @functools.cached_property
    def quarter(self) -> np.ndarray:
        """Quarter-size BGR copy (full px = 4 * quarter px)."""
        return cv2.imread(str(self.path.with_suffix(".q.png")))

    @property
    def size(self) -> tuple[int, int]:
        h, w = self.quarter.shape[:2]
        return w * Q, h * Q

    @functools.cached_property
    def tags(self) -> list[dict]:
        """Every AprilTag: {"id", "centre", "corners"} in full px (tray tags are IDs 0 to 299)."""
        return json.loads((DATA / "cache" / f"{self.rig}-{self.stem}-tags.json").read_text())

    def _calibration(self):
        key = tuple(CAL[self.rig]) if self.rig in CAL else tuple(_held_cals()[self.stem])
        if key not in _CALS:
            _CALS[key] = _cal(*key)
        return _CALS[key]

    @property
    def scale_field(self):
        return self._calibration()[0]

    def px_per_mm(self, x: float, y: float) -> float:
        """Full px per mm at tray-top height, at full-size pixel (x, y)."""
        return float(self.scale_field.px_per_mm(x, y))

    @functools.cached_property
    def tag_placements(self) -> list:
        """The rig's own placement of each tray tag (TrayPlacement: tray_id, centre, outline,
        tilt_deg, a1_corner, slot): every tray treated as a 4x5 placed from its A1 tag."""
        from npec_rig.tags import TagDetection
        from npec_rig.tray_placement import place_trays

        scale, slots = self._calibration()
        dets = [TagDetection(tag_id=t["id"], centre=tuple(t["centre"]), corners=[tuple(c) for c in t["corners"]])
                for t in self.tags if t["id"] < 300]
        return place_trays(dets, scale, slots)

    def fastsam(self, scale: str = "large") -> list[dict]:
        """FastSAM objects ("whole", "large" or "medium" tiles): score, area_px, box, contour (full px)."""
        rec = json.loads((OBJECTS / f"{self.stem}.json").read_text())
        return rec["scales"][scale]["objects"]


def stills(rig: str | None = None) -> list[Still]:
    out = []
    for r in RIGS if rig is None else (rig,):
        out += [Still(r, p.stem) for p in sorted((DATA / "stills" / r).glob("*.jpg"))]
    return out


@functools.cache
def _hard_truth():
    return json.loads((DATA / "ref" / "hard_truth.json").read_text())


def _flip(p, still):
    """Placement p with its A1 at the other corner: the other candidate centre of place_trays."""
    from npec_rig.tray_placement import _outline

    tag = next(t for t in still.tags if t["id"] == p.tray_id)
    c = (2 * tag["centre"][0] - p.centre[0], 2 * tag["centre"][1] - p.centre[1])
    return np.float64(_outline(c, p.tilt_deg, still.px_per_mm(*tag["centre"])))


@functools.cache
def _dev_reference():
    return json.loads((DATA / "ref" / "dev_reference.json").read_text())


def reference(still: Still) -> list[dict]:
    """[{"name", "outline" (4 x 2 full px), "partial", "tray_id"}]."""
    if still.rig == "prod":
        return [{"name": f"tray {p.tray_id}", "outline": np.float64(p.outline), "partial": False, "tray_id": p.tray_id}
                for p in still.tag_placements]
    if still.rig == "hard":  # tag placement, with A1 at the corner the shuffle plan put it
        truth = _hard_truth()[still.stem]
        return [{"name": f"tray {p.tray_id}", "partial": False, "tray_id": p.tray_id,
                 "outline": np.float64(p.outline) if truth[str(p.tray_id)]["planned_a1"] == p.a1_corner else _flip(p, still)}
                for p in still.tag_placements if str(p.tray_id) in truth]
    for lay in _dev_reference()["layouts"].values():
        if still.stem in lay["stills"]:
            return [{"name": t["name"], "outline": np.float64(t["corners"]), "partial": bool(t["partial"]), "tray_id": None}
                    for t in lay["trays"]]
    raise LookupError(f"{still.stem}: in no reference layout")


def _centre(poly):
    m = cv2.moments(np.float32(poly))
    return (m["m10"] / m["m00"], m["m01"] / m["m00"]) if m["m00"] else tuple(np.mean(poly, 0))


def _iou(a, b, shape):
    f = 1 / 16  # rasterised at 1/16 size, padded so outlines past the frame count
    pad = 200
    ma, mb = np.zeros(shape, np.uint8), np.zeros(shape, np.uint8)
    cv2.fillPoly(ma, [np.int32(np.asarray(a) * f + pad)], 1)
    cv2.fillPoly(mb, [np.int32(np.asarray(b) * f + pad)], 1)
    u = np.count_nonzero(ma | mb)
    return np.count_nonzero(ma & mb) / u if u else 0.0


def score(still: Still, found: list[dict]) -> dict:
    refs = reference(still)
    w, h = still.size
    shape = (int(h / 16) + 400, int(w / 16) + 400)
    fc = [_centre(f["outline"]) for f in found]
    pairs = []
    for i, r in enumerate(refs):
        rc = _centre(r["outline"])
        ppm = still.px_per_mm(*rc)
        for j, c in enumerate(fc):
            d = float(np.hypot(c[0] - rc[0], c[1] - rc[1])) / ppm
            if d < 150:
                pairs.append((d, i, j))
    used_r, used_f, match = set(), set(), {}
    for d, i, j in sorted(pairs):  # nearest first, one outline per tray
        if i in used_r or j in used_f:
            continue
        used_r.add(i), used_f.add(j)
        match[i] = (j, d)
    rows = []
    for i, r in enumerate(refs):
        row = {"tray": r["name"], "partial": r["partial"], "found": False, "centre_mm": None, "iou": None,
               "id_ok": None, "how": "", "warnings": ""}
        if i in match:
            j, d = match[i]
            f = found[j]
            iou = _iou(r["outline"], f["outline"], shape)
            id_ok = None if r["tray_id"] is None or f.get("tray_id") is None else f["tray_id"] == r["tray_id"]
            row.update(centre_mm=round(d, 1), iou=round(iou, 3), id_ok=id_ok, how=f.get("how", ""),
                       warnings="; ".join(f.get("warnings", [])),
                       found=d <= CENTRE_MM and iou >= IOU_MIN and id_ok is not False)
        rows.append(row)
    whole = [r for r in rows if not r["partial"]]
    return {"still": still.stem, "rig": still.rig, "rows": rows,
            "found": sum(r["found"] for r in whole), "of": len(whole),
            "partial_found": sum(r["found"] for r in rows if r["partial"]),
            "partial_of": sum(r["partial"] for r in rows),
            "extra": len(found) - len(used_f)}


def draw(still: Still, found: list[dict], sc: dict, path: Path, title: str = ""):
    """Quarter-size picture: reference outlines thin white, found outlines green when the tray is
    found, red otherwise, orange for outlines matching no tray; a label per tray."""
    im = still.quarter.copy()
    refs = reference(still)
    for r in refs:
        cv2.polylines(im, [np.int32(r["outline"] / Q)], True, (255, 255, 255), 2)
    by_how = {}
    fc = [_centre(f["outline"]) for f in found]
    for r, row in zip(refs, sc["rows"]):
        rc = np.array(_centre(r["outline"])) / Q
        ok = row["found"]
        txt = f"{r['name']}: " + ("FOUND" if ok else "MISSED" if row["centre_mm"] is None else "WRONG")
        if row["centre_mm"] is not None:
            txt += f" {row['centre_mm']:.0f}mm iou {row['iou']:.2f}"
        by_how[r["name"]] = ok
        org = (int(rc[0] - 150), int(rc[1]))
        for col, th in (((0, 0, 0), 6), ((255, 255, 255), 2)):
            cv2.putText(im, txt, org, cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, th)
    matched = set()
    for r, row in zip(refs, sc["rows"]):
        if row["centre_mm"] is None:
            continue
        rc = _centre(r["outline"])
        j = min(range(len(found)), key=lambda k: np.hypot(fc[k][0] - rc[0], fc[k][1] - rc[1]))
        matched.add(j)
        col = (0, 200, 0) if row["found"] else (0, 0, 255)
        cv2.polylines(im, [np.int32(np.asarray(found[j]["outline"]) / Q)], True, col, 4)
    for j, f in enumerate(found):
        if j not in matched:
            cv2.polylines(im, [np.int32(np.asarray(f["outline"]) / Q)], True, (0, 140, 255), 4)
    head = f"{still.rig} {still.stem}  {title}  found {sc['found']} of {sc['of']}" + (
        f" (+{sc['partial_found']} of {sc['partial_of']} partly outside)" if sc["partial_of"] else "") + (
        f", {sc['extra']} extra outlines" if sc["extra"] else "")
    cv2.rectangle(im, (0, 0), (im.shape[1], 44), (0, 0, 0), -1)
    cv2.putText(im, head, (10, 31), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    small = cv2.resize(im, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(path), small, [cv2.IMWRITE_JPEG_QUALITY, 85])


def run(name: str, find, version: str, notes: str = "", rigs=RIGS, pictures: str = "layouts") -> dict:
    """Run finder `find` over every still; write VIEW/328-<name>-<version>/ (notes.txt with the
    summary, results.csv, pictures) and return the summary. pictures: "layouts" draws the first
    and last still of each rig, "all" every still, "none" none."""
    out = VIEW / f"328-{name}-{version}"
    out.mkdir(parents=True, exist_ok=False)
    scores, secs = [], []
    for r in rigs:
        ss = stills(r)
        for k, s in enumerate(ss):
            t0 = time.perf_counter()
            found = find(s)
            secs.append(time.perf_counter() - t0)
            sc = score(s, found)
            scores.append(sc)
            if pictures == "all" or (pictures == "layouts" and (k in (0, len(ss) - 1) or s.stem in LAYOUT_PICTURES)):
                draw(s, found, sc, out / f"{r}-{s.stem}.jpg", f"{name} {version}")
    with open(out / "results.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["rig", "still", "tray", "partial", "found", "centre_mm", "iou", "id_ok", "how", "warnings"])
        for sc in scores:
            for row in sc["rows"]:
                wr.writerow([sc["rig"], sc["still"], row["tray"], row["partial"], row["found"], row["centre_mm"],
                             row["iou"], row["id_ok"], row["how"], row["warnings"]])
    summ = {"name": name, "version": version}
    for r in rigs:
        rs = [s for s in scores if s["rig"] == r]
        if not rs:
            continue
        summ[r] = {"stills": len(rs), "worst": min(s["found"] for s in rs), "of": rs[0]["of"],
                   "mean": round(float(np.mean([s["found"] for s in rs])), 2),
                   "partial_found_mean": round(float(np.mean([s["partial_found"] for s in rs])), 2),
                   "extra_mean": round(float(np.mean([s["extra"] for s in rs])), 2),
                   "centre_mm_median": round(float(np.median([row["centre_mm"] for s in rs for row in s["rows"]
                                                              if row["centre_mm"] is not None and not row["partial"]] or [np.nan])), 1)}
    summ["seconds_per_still"] = round(float(np.mean(secs)), 1)
    lines = [f"328 {name} {version}", notes.strip()] + [
        f"{r}: worst still {summ[r]['worst']} of {summ[r]['of']}, mean {summ[r]['mean']}, "
        f"partly outside found {summ[r]['partial_found_mean']}, extra outlines {summ[r]['extra_mean']}, "
        f"median centre error {summ[r]['centre_mm_median']} mm, {summ[r]['stills']} stills"
        for r in rigs if r in summ] + [f"{summ['seconds_per_still']} s per still on the controller",
                                       "white: reference; green: found; red: wrong size or place; orange: matches no tray"]
    (out / "notes.txt").write_text("\n".join(x for x in lines if x) + "\n")
    (out / "summary.json").write_text(json.dumps(summ, indent=1, default=float))
    print(json.dumps(summ, default=float))
    return summ
