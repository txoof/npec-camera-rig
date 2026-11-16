"""Exclusions (#288, `GLOSSARY.md`): stored reasons a photo's plant areas are left out of averages
and exports. The areas themselves are kept.

The light exclusions follow the camera, not a norm (#382, metrology log 29): a photo is "light
changing" while its auto-exposure is still moving one way (N-pad), and "lights off" when the
camera reports its auto-exposure still searching. The rig does not judge the lamps; no light
program, ramp length or light level is assumed (Aaron, 2026-11-07).
"""

import statistics
from datetime import UTC, datetime

from npec_rig import database

# Only for photos saved before the camera's auto-exposure state was recorded (#382, `capture`
# version 24): one whose E is at least this was taken with the lights off, the camera at its
# auto-exposure ceiling (64 ms at gain 4.0, about 256,000), against under 10,000 lit (experiments
# 16 and 18, metrology log 17.7). A decision, not a measurement (#288), checked in #293. Newer
# photos use the camera's own state.
LIGHTS_OFF_E = 200_000

# Visits: someone at the table, a whole photo left out (metrology log 17.9). Also every photo with
# two trays placed in one slot (#315, `visits`). A tray's area more
# than VISIT_JUMP_MM2 and VISIT_JUMP_RATIO times away from the median of its VISIT_USUAL photos
# before. Below these, tray 7 near the floor read up to 247 mm2 (more than 2 times) and the
# benchmark on tray 8 moved by up to 1,336 mm2 (under 2 times) with no one there. Decisions
# (Aaron, 2026-10-27), checked again in #296.
VISIT_JUMP_MM2 = 250
VISIT_JUMP_RATIO = 2
VISIT_USUAL = 10
# One visit's marks were up to 4 photos apart (the tray move of 26 October, 17.9): the photos
# between two marks at most this far apart are part of the same visit. A decision (Aaron).
VISIT_GAP = 4


def _e(photo: dict) -> float | None:
    """The photo's E, None when it has none: no exposure or gain recorded, or 0 (a camera fault)."""
    exposure, gain = photo.get("exposure_us"), photo.get("analogue_gain")
    e = None if exposure is None or gain is None else exposure * gain
    return e if e and e > 0 else None


def light_exclusions(photos: list[dict]) -> dict:
    """The light exclusion of each of one experiment's photos (dicts with `taken_at`,
    `exposure_us`, `analogue_gain` and, when recorded, `ae_state`, oldest first): `exclusions`,
    one name or None per photo. Only photos taken as captures count: a calibration, validation or
    tripwire photo (its `purpose`) gets None and is nobody's neighbour."""
    own = [i for i, p in enumerate(photos) if p.get("purpose", "capture") == "capture"]
    result = _light_exclusions([photos[i] for i in own])
    names: list[str | None] = [None] * len(photos)
    for i, name in zip(own, result["exclusions"]):
        names[i] = name
    return {"exclusions": names}


def _light_exclusions(photos: list[dict]) -> dict:
    es = [_e(p) for p in photos]
    off = [_lights_off(p, e) for p, e in zip(photos, es)]
    names: list[str | None] = ["lights off" if o else None for o in off]
    for i in _ramp(es):
        if not off[i]:
            names[i] = "light changing"
    return {"exclusions": names}


def _lights_off(photo: dict, e: float | None) -> bool:
    """Whether the photo was taken with the lights off: the camera's own auto-exposure state
    (`ae_state`, #382) says it was still searching, as every dark photo on the development rig
    did and no steady lit one (metrology log 29.3). A photo saved before the state was recorded
    falls back to E of at least LIGHTS_OFF_E."""
    state = photo.get("ae_state")
    if state is not None:
        return state == "searching"
    return e is not None and e >= LIGHTS_OFF_E


def _ramp(es: list[float | None]) -> set[int]:
    """N-pad (#382, metrology log 29.2): each photo whose E lies strictly between the E of the
    photo before and the photo after (the auto-exposure still moving one way), and the photo
    before and after it. No limit in minutes or percent: a ramp of any length is found, as long as
    it spans more than one gap between photos."""
    moving = {
        i for i in range(1, len(es) - 1)
        if None not in (es[i - 1], es[i], es[i + 1])
        and (es[i - 1] < es[i] < es[i + 1] or es[i - 1] > es[i] > es[i + 1])
    }
    return {j for i in moving for j in (i - 1, i, i + 1)}


def visits(photos: list[dict]) -> list[bool]:
    """Whether each of one experiment's photos (dicts with `taken_at` and `areas`, each tray's
    plant area by tray ID, oldest first, and optionally `shared_tray`) is a visit: a tray's area
    more than VISIT_JUMP_MM2 and more than VISIT_JUMP_RATIO times away from its usual level, up or
    down, or two trays in one place (`shared_tray`: a tray carried over the table or a loose
    tag on a tray, too abnormal to measure; Aaron, 2026-10-28, #315). The usual level is the
    median of the same tray's areas in the VISIT_USUAL photos before; a tray with fewer is not
    judged. The photos between two visits at most VISIT_GAP photos apart are visits too."""
    history: dict[int, list[float]] = {}
    marks = []
    for photo in photos:
        mark = bool(photo.get("shared_tray"))
        for tray, area in photo["areas"].items():
            before = history.setdefault(tray, [])[-VISIT_USUAL:]
            if len(before) == VISIT_USUAL:
                usual = statistics.median(before)
                ratio = area / usual if usual > 0 else float("inf")
                mark |= abs(area - usual) > VISIT_JUMP_MM2 and (ratio > VISIT_JUMP_RATIO or ratio < 1 / VISIT_JUMP_RATIO)
            history[tray].append(area)
        marks.append(mark)
    marked = [i for i, mark in enumerate(marks) if mark]
    for i, j in zip(marked, marked[1:]):
        if j - i <= VISIT_GAP:
            marks[i:j] = [True] * (j - i)
    return marks


def update(capture: dict) -> None:
    """Work out again, and save, the exclusions of photo `capture`'s experiment (its rig.db row):
    a new photo can change earlier ones (the photo before it joins a ramp). A photo in no
    experiment has no neighbours, so only lights off. A light exclusion wins over a
    visit (metrology log 17.9)."""
    experiment_id = capture.get("experiment_id")
    photos = database.captures_for_experiment(experiment_id) if experiment_id else [capture]
    result = light_exclusions(photos)
    names = result["exclusions"]
    if experiment_id:
        areas = database.experiment_tray_areas(experiment_id)
        shared = database.experiment_shared_tray_photos(experiment_id)
        # Lit photos taken as captures with their trays read only, as in the review: a light
        # exclusion's areas would move the usual level, and a photo not read has none to judge.
        own = [i for i, p in enumerate(photos)
               if p.get("purpose", "capture") == "capture" and names[i] is None and p["id"] in areas]
        seen = visits([
            {"taken_at": photos[i]["taken_at"], "areas": areas[photos[i]["id"]], "shared_tray": photos[i]["id"] in shared}
            for i in own
        ])
        for i, visit in zip(own, seen):
            if visit:
                names[i] = "visit"
    database.record_exclusions(
        # norm_e and limit_fraction belong to the norm of 17.8, gone since #382: saved empty, the
        # columns removed in #384.
        [{"capture_id": p["id"], "name": name, "norm_e": None, "limit_fraction": None}
         for p, name in zip(photos, names)],
        worked_out_at=datetime.now(UTC).isoformat(),
    )
