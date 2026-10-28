"""Exclusions (#288, `GLOSSARY.md`): stored reasons a photo's plant areas are left out of averages
and exports. The areas themselves are kept.

The light exclusions come from each photo's exposure times analogue gain (E), which the camera's
auto-exposure raises as the scene gets darker (metrology log 17.7 and 17.8). No light program is
assumed: the researcher chooses it.
"""

import bisect
import statistics
from datetime import UTC, datetime, timedelta

from npec_rig import database

# A photo whose E is at least this was taken with the lights off: the camera at its auto-exposure
# ceiling (64 ms at gain 4.0, about 256,000), against under 10,000 lit (experiments 16 and 18,
# metrology log 17.7). A decision, not a measurement (#288), checked in #293.
LIGHTS_OFF_E = 200_000

# The norm: the median E of the experiment's first full day of steady photos, lit and more than
# NEAR_LIGHTS_OFF from any lights-off photo (all lit photos when the day has none). A photo is off
# the norm when its E differs from it by more than LIMIT_FACTOR times the largest steady swing of
# that day, so each experiment sets its own limit. A stretch away from the norm in which E moves,
# from one photo to the next, more than the day's largest steady step (median over the stretch) is
# the light still changing: a ramp. Decisions (Aaron, 2026-10-26, metrology log
# 17.8), revisited in #296.
FIRST_DAY = timedelta(hours=24)
NEAR_LIGHTS_OFF = timedelta(minutes=60)
LIMIT_FACTOR = 3

# A stretch of this many photos or fewer off the norm, followed by a photo on it: "light
# disturbed", someone at the table or a door (Aaron, 2026-10-26, 17.8). Revisited in #296.
SHORT_RUN = 3

# The light warning: more than this much "light off norm" within WARNING_WINDOW raises it. Light
# changing, light disturbed and lights off never do. A decision (Aaron, 2026-10-23, #288).
WARNING_HOURS = timedelta(hours=2)
WARNING_WINDOW = timedelta(hours=24)

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
    `exposure_us`, `analogue_gain`, oldest first): `exclusions`, one name or None per photo, and
    the `norm` (E) and `limit` (a fraction of the norm) they were worked out with, both None until
    the experiment has a full first day. Only photos taken as captures count: a calibration,
    validation or tripwire photo (its `purpose`) gets None and is left out of the norm."""
    own = [i for i, p in enumerate(photos) if p.get("purpose", "capture") == "capture"]
    result = _light_exclusions([photos[i] for i in own])
    names: list[str | None] = [None] * len(photos)
    for i, name in zip(own, result["exclusions"]):
        names[i] = name
    return {**result, "exclusions": names}


def _light_exclusions(photos: list[dict]) -> dict:
    times = [datetime.fromisoformat(p["taken_at"]) for p in photos]
    es = [_e(p) for p in photos]
    off = [e is not None and e >= LIGHTS_OFF_E for e in es]
    norm, limit, step = _norm_and_limit(times, es, off)
    names: list[str | None] = ["lights off" if o else None for o in off]
    if norm is not None:
        away = [e is not None and not o and abs(e / norm - 1) > limit for e, o in zip(es, off)]
        for start, end in _runs(away):
            returned = end + 1 < len(es) and not away[end + 1] and not off[end + 1] and es[end + 1] is not None
            steps = [abs(es[i] / es[i - 1] - 1) for i in range(start + 1, end + 1)]
            if (start > 0 and off[start - 1]) or (end + 1 < len(es) and off[end + 1]):
                name = "light changing"  # a fade into or out of lights off
            elif returned and end - start + 1 <= SHORT_RUN:
                name = "light disturbed"
            elif steps and statistics.median(steps) > step:
                name = "light changing"  # a ramp
            else:
                name = "light off norm"
            names[start:end + 1] = [name] * (end - start + 1)
    return {"exclusions": names, "norm": norm, "limit": limit}


def _near(dark: list[datetime], t: datetime) -> bool:
    """Whether time `t` is within NEAR_LIGHTS_OFF of a lights-off photo (`dark`, in time order)."""
    i = bisect.bisect_left(dark, t)
    return any(abs(dark[j] - t) <= NEAR_LIGHTS_OFF for j in (i - 1, i) if 0 <= j < len(dark))


def _runs(flags: list[bool]) -> list[tuple[int, int]]:
    """Each stretch of True in `flags`, as (first, last) index."""
    out, start = [], None
    for i, flag in enumerate([*flags, False]):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            out.append((start, i - 1))
            start = None
    return out


def _norm_and_limit(
    times: list[datetime], es: list[float | None], off: list[bool]
) -> tuple[float | None, float | None, float | None]:
    """The first day's norm, the off-norm limit and the largest steady step (both fractions)."""
    if not times or times[-1] < times[0] + FIRST_DAY:
        return None, None, None
    day = [i for i, t in enumerate(times) if t < times[0] + FIRST_DAY and es[i] is not None and not off[i]]
    dark = [times[i] for i, o in enumerate(off) if o]  # in time order
    steady = [i for i in day if not _near(dark, times[i])] or day
    if not steady:
        return None, None, None
    norm = statistics.median(es[i] for i in steady)
    in_steady = set(steady)
    steps = [abs(es[i] / es[i - 1] - 1) for i in steady if i - 1 in in_steady]
    return norm, LIMIT_FACTOR * max(abs(es[i] / norm - 1) for i in steady), max(steps, default=0.0)


def light_warning(experiment_id: int) -> dict | None:
    """The experiment's light warning, None when there is none: the `hours` of light off norm
    and the `first` and `last` times (UTC) of the photos that raise it. Each photo off norm counts
    from its own time to the next photo's, at most the experiment's usual gap between photos (the
    median), so a pause is not counted. Hours up to the last dismissal's `covers_until` are
    not counted again, later ones are, also in a stretch that was still going on."""
    rows = database.experiment_exclusions(experiment_id)
    dismissed = [datetime.fromisoformat(d["covers_until"]) for d in database.light_warning_dismissals(experiment_id)]
    covered = max(dismissed) if dismissed else None
    times = [datetime.fromisoformat(r["taken_at"]) for r in rows]
    usual = statistics.median(b - a for a, b in zip(times, times[1:])) if len(times) > 1 else timedelta()
    spans = []  # (start, end) of each photo off norm, in time order
    for i in range(len(rows) - 1):
        if rows[i]["name"] != "light off norm":
            continue
        start, end = times[i], min(times[i + 1], times[i] + usual)
        if covered is not None:
            start = max(start, covered)
        if end > start:
            spans.append((start, end))
    raising: set[int] = set()
    j, total = 0, timedelta()  # spans[i:j] start inside the window from spans[i]; total their time
    for i, (window_start, _end) in enumerate(spans):
        window_end = window_start + WARNING_WINDOW
        while j < len(spans) and spans[j][0] < window_end:
            total += spans[j][1] - spans[j][0]
            j += 1
        overshoot = max(spans[j - 1][1] - window_end, timedelta())  # only the last can reach past it
        if total - overshoot > WARNING_HOURS:
            raising.update(range(i, j))
        total -= spans[i][1] - spans[i][0]
    if not raising:
        return None
    counted = [spans[k] for k in sorted(raising)]
    return {
        "hours": round(sum((end - start for start, end in counted), timedelta()) / timedelta(hours=1), 2),
        "first": counted[0][0].isoformat(),
        "last": counted[-1][1].isoformat(),
    }


def visits(photos: list[dict]) -> list[bool]:
    """Whether each of one experiment's photos (dicts with `taken_at` and `areas`, each tray's
    plant area by tray ID, oldest first, and optionally `shared_slot`) is a visit: a tray's area
    more than VISIT_JUMP_MM2 and more than VISIT_JUMP_RATIO times away from its usual level, up or
    down, or two trays placed in one slot (`shared_slot`: a tray carried over the table or a loose
    tag on a tray, too abnormal to measure; Aaron, 2026-10-28, #315). The usual level is the
    median of the same tray's areas in the VISIT_USUAL photos before; a tray with fewer is not
    judged. The photos between two visits at most VISIT_GAP photos apart are visits too."""
    history: dict[int, list[float]] = {}
    marks = []
    for photo in photos:
        mark = bool(photo.get("shared_slot"))
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


def dismiss_light_warning(experiment_id: int, *, now: str, until: str) -> None:
    """Dismiss the experiment's light warning at time `now` (UTC), as the researcher saw it:
    hours up to `until` (the `last` it showed) are not counted again, later ones are. Nothing is
    saved when there is no warning."""
    if light_warning(experiment_id) is not None:
        datetime.fromisoformat(until)  # a time, or ValueError
        database.record_light_warning_dismissal(experiment_id, dismissed_at=now, covers_until=until)


def update(capture: dict) -> None:
    """Work out again, and save, the exclusions of photo `capture`'s experiment (its rig.db row):
    a new photo can change earlier ones (a short run returns, the first day ends). A photo in no
    experiment has no norm and no neighbours, so only lights off. A light exclusion wins over a
    visit (metrology log 17.9)."""
    experiment_id = capture.get("experiment_id")
    photos = database.captures_for_experiment(experiment_id) if experiment_id else [capture]
    result = light_exclusions(photos)
    names = result["exclusions"]
    if experiment_id:
        areas = database.experiment_tray_areas(experiment_id)
        shared = database.experiment_shared_slot_photos(experiment_id)
        # Lit photos taken as captures with their trays read only, as in the review: a light
        # exclusion's areas would move the usual level, and a photo not read has none to judge.
        own = [i for i, p in enumerate(photos)
               if p.get("purpose", "capture") == "capture" and names[i] is None and p["id"] in areas]
        seen = visits([
            {"taken_at": photos[i]["taken_at"], "areas": areas[photos[i]["id"]], "shared_slot": photos[i]["id"] in shared}
            for i in own
        ])
        for i, visit in zip(own, seen):
            if visit:
                names[i] = "visit"
    database.record_exclusions(
        [{"capture_id": p["id"], "name": name, "norm_e": result["norm"], "limit_fraction": result["limit"]}
         for p, name in zip(photos, names)],
        worked_out_at=datetime.now(UTC).isoformat(),
    )
