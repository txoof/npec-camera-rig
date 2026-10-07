"""Validation sessions: the measured check of a calibration (certainty_map.py).

A session belongs to one calibration. Each round is one capture taken after the operator moved
each sheet to a different tray, leaving the trays where they were; the calibration frame itself
is never a round,
because its scale field was fitted to those very tags. A session is complete once
`ROUNDS_REQUIRED` rounds have counted, and it records when.

Each round's per-slot errors and tag centres are stored in the session file, so pooled results
and the next round's movement check read the file instead of re-decoding 64MP captures (about
6s each on the Pi), and nothing is lost across a server restart.

Stored as one JSON file per session under the calibration directory, next to the calibrations
they check. Sessions are history: they are never overwritten by a new session, only deleted on
request (or with the calibration they belong to).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from npec_rig.calibration_store import _write_json_atomically, calibration_root
from npec_rig.certainty_map import slot_results_from_errors

VALIDATIONS_DIRNAME = "validations"
ROUNDS_REQUIRED = 3
# A slot whose median error moves by more than this across counted rounds is flagged as
# inconsistent: something changed between rounds (a mis-printed sheet, a tray at the wrong
# height, the camera or table moving), not only where the slot is. The three real validations
# of 2026-09-30 with no known fault moved slot medians by at most 0.71, 1.48 and 1.96 points; a
# 96%-scale sheet reads about 7.8 points small, so 2.5 separates the two (Aaron, 2026-09-30).
MEDIAN_DISAGREEMENT_PCT = 2.5
# A round in which at least this fraction of measured slots read off the same way, by more than
# MEDIAN_DISAGREEMENT_PCT, is reported as the whole round shifting (camera or table moved), not as
# one bad sheet per slot.
WHOLE_ROUND_FRACTION = 0.5
# A slot whose steady reading (the median of its per-round medians) sits more than this from the
# median of all slots' steady readings is flagged, though it never moved: a bad sheet or tray that
# stayed on one slot, or the slot itself. In 8 real sessions (2026-09-30 and 10-01) normal slots
# sat at most 2.15 points from the all-slot median (always North 4, steady at -1.6 to -2.2); an
# 89% sheet left on North 2 for every round sat 20.5 away (Aaron, 2026-10-01).
SLOT_OFFSET_PCT = 3.0
# The all-slot median more than this from 0: every slot reads off since the calibration, so the
# camera or table moved. In the same 8 sessions it was at most 0.66 points.
TABLE_OFFSET_PCT = 2.5
# The counted rounds should be spread over at least this long, first to last. A decision, not a
# measurement (Aaron, 2026-10-07): with one photo a minute and nothing touched, readings rose and
# fell on a repeating cycle of about 19 minutes (metrology-log section 8.1, run 3j: about 0.35
# points in the median, up to 0.6 in a slot), so rounds taken within a few minutes all see one
# point of that cycle and the bands miss it. Shorter sessions are not blocked: the result says so.
MIN_SPAN_MINUTES = 20.0
# Counted rounds should be at least this far apart: the page counts down to the next round, asks
# before a sooner one, and a completed session with a shorter gap says so (rounds close together see
# about the same point of the cycle above). A decision, not a measurement (Aaron, 2026-10-07:
# encourage the operator not to rush). Not a block.
MIN_ROUND_GAP_MINUTES = 6.0
SESSION_VERSION = 1
_SESSION_ID = re.compile(r"^\d{8}T\d{12}$")


class SessionNotFoundError(LookupError):
    pass


def validations_root() -> Path:
    return calibration_root() / VALIDATIONS_DIRNAME


def _session_path(session_id: str) -> Path:
    if not _SESSION_ID.match(session_id):
        raise SessionNotFoundError(f"not a validation session id: {session_id!r}")
    return validations_root() / f"{session_id}.json"


def new_session(calibration_stem: str, slots: list[dict], calibration_centres: list) -> dict:
    now = datetime.now(timezone.utc)
    session = {
        "version": SESSION_VERSION,
        "id": now.strftime("%Y%m%dT%H%M%S%f"),
        "calibration_stem": calibration_stem,
        "started_at": now.isoformat(),
        "completed_at": None,
        "ended_at": None,
        "slots": slots,
        "calibration_centres": [list(c) for c in calibration_centres],
        "rounds": [],
        "results": [],
    }
    save_session(session)
    return session


def save_session(session: dict) -> None:
    path = _session_path(session["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomically(path, session)


def load_session(session_id: str) -> dict:
    path = _session_path(session_id)
    if not path.exists():
        raise SessionNotFoundError(f"validation session {session_id} not found")
    return json.loads(path.read_text())


def list_sessions() -> list[dict]:
    """Every saved session, newest first. Unreadable files are skipped, not fatal."""
    root = validations_root()
    if not root.exists():
        return []
    sessions = []
    for path in sorted(root.glob("*.json"), reverse=True):
        try:
            sessions.append(json.loads(path.read_text()))
        except json.JSONDecodeError:
            continue
    return sessions


def delete_session(session_id: str) -> None:
    path = _session_path(session_id)
    if not path.exists():
        raise SessionNotFoundError(f"validation session {session_id} not found")
    path.unlink()


def delete_sessions_for_calibration(calibration_stem: str) -> int:
    """Remove every session of a calibration being deleted, so none is left pointing at a
    calibration that no longer exists. Returns how many were removed."""
    removed = 0
    for session in list_sessions():
        if session.get("calibration_stem") == calibration_stem:
            _session_path(session["id"]).unlink(missing_ok=True)
            removed += 1
    return removed


SLOT_LAYOUTS_DIRNAME = "slot-layouts"


def _slot_layout_path(calibration_stem: str) -> Path:
    if not _SESSION_ID.match(calibration_stem):
        raise SessionNotFoundError(f"not a calibration stem: {calibration_stem!r}")
    return validations_root() / SLOT_LAYOUTS_DIRNAME / f"{calibration_stem}.json"


def save_slot_layout(calibration_stem: str, slots: list[dict], calibration_centres: list) -> None:
    """A calibration's tray slots and tag centres, worked out once from its 64MP frame (about 15 s
    to decode and detect) and kept on disk, so starting a validation after a restart does not
    have to do it again."""
    path = _slot_layout_path(calibration_stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomically(
        path, {"slots": slots, "calibration_centres": [list(c) for c in calibration_centres]}
    )


def load_slot_layout(calibration_stem: str) -> dict | None:
    """{"slots", "calibration_centres"} saved by `save_slot_layout`, or None if not saved yet or
    unreadable (it is then simply worked out again)."""
    path = _slot_layout_path(calibration_stem)
    if not path.exists():
        return None
    try:
        layout = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    return layout if {"slots", "calibration_centres"} <= layout.keys() else None


def delete_slot_layout(calibration_stem: str) -> None:
    _slot_layout_path(calibration_stem).unlink(missing_ok=True)


def is_ended(session: dict) -> bool:
    """Ended sessions take no more rounds. A session saved before End validation existed has no
    `ended_at` key at all and counts as ended: otherwise every old session would read as open,
    and the page would offer "End validation" on load (Aaron, 2026-09-30)."""
    return "ended_at" not in session or session["ended_at"] is not None


def end_session(session: dict) -> None:
    if not is_ended(session):
        session["ended_at"] = datetime.now(timezone.utc).isoformat()


def end_open_sessions(calibration_stem: str) -> None:
    """End every still-open session of `calibration_stem`: one validation runs at a time."""
    for session in list_sessions():
        if session.get("calibration_stem") == calibration_stem and not is_ended(session):
            end_session(session)
            save_session(session)


def counted_rounds(session: dict) -> list[dict]:
    return [r for r in session["rounds"] if r["counted"]]


def round_span_minutes(session: dict) -> float | None:
    """Minutes from the first to the last counted round, by capture time. None with fewer than 2
    counted rounds that have a capture time (store-level test rounds have none)."""
    times = [
        datetime.fromisoformat(r["captured_at"]) for r in counted_rounds(session) if r.get("captured_at")
    ]
    if len(times) < 2:
        return None
    return (max(times) - min(times)).total_seconds() / 60


def _counted_times(session: dict) -> list[datetime]:
    return sorted(
        datetime.fromisoformat(r["captured_at"]) for r in counted_rounds(session) if r.get("captured_at")
    )


def shortest_gap_minutes(session: dict) -> float | None:
    """The shortest time between two consecutive counted rounds, in minutes. None with fewer than 2
    counted rounds that have a capture time."""
    times = _counted_times(session)
    if len(times) < 2:
        return None
    return min((b - a).total_seconds() for a, b in zip(times, times[1:])) / 60


def short_gap(session: dict) -> bool:
    """Complete, but two counted rounds are closer together than MIN_ROUND_GAP_MINUTES."""
    gap = shortest_gap_minutes(session)
    return (
        len(counted_rounds(session)) >= ROUNDS_REQUIRED
        and gap is not None
        and gap < MIN_ROUND_GAP_MINUTES
    )


def short_span(session: dict) -> bool:
    """Complete, but the counted rounds span less than MIN_SPAN_MINUTES."""
    span = round_span_minutes(session)
    return (
        len(counted_rounds(session)) >= ROUNDS_REQUIRED
        and span is not None
        and span < MIN_SPAN_MINUTES
    )


def span_text(minutes: float) -> str:
    return f"{minutes:.1f}" if minutes < 10 else f"{minutes:.0f}"


def round_slot_results(round_: dict) -> dict[str, dict] | None:
    """One round's own per-slot figures, as `refresh_results` reports the pooled ones."""
    if round_["slot_errors"] is None:
        return None
    return {
        r.name: {"n": r.n, "p95_abs_pct": r.p95_abs_pct, "median_pct": r.median_pct}
        for r in slot_results_from_errors(round_["slot_errors"])
    }


def median_ranges(session: dict) -> dict[str, float | None]:
    """How far each slot's median error moved across counted rounds (max minus min), or None
    before two counted rounds have measured it."""
    medians: dict[str, list[float]] = {slot["name"]: [] for slot in session["slots"]}
    for round_ in counted_rounds(session):
        for name, result in (round_slot_results(round_) or {}).items():
            if result["median_pct"] is not None:
                medians[name].append(result["median_pct"])
    return {name: (max(v) - min(v) if len(v) >= 2 else None) for name, v in medians.items()}


def inconsistent_slots(session: dict) -> list[str]:
    """Slots, in layout order, whose median moved more than `MEDIAN_DISAGREEMENT_PCT` across
    counted rounds."""
    ranges = median_ranges(session)
    return [
        slot["name"]
        for slot in session["slots"]
        if ranges[slot["name"]] is not None and ranges[slot["name"]] > MEDIAN_DISAGREEMENT_PCT
    ]


def _steady_readings(session: dict) -> dict[str, float]:
    """Each slot's median over counted rounds of its per-round medians: one odd round (a sheet
    that moved through) does not move it. Only slots measured in at least 3 counted rounds."""
    medians: dict[str, list[float]] = {}
    for round_ in counted_rounds(session):
        for name, result in (round_slot_results(round_) or {}).items():
            if result["median_pct"] is not None:
                medians.setdefault(name, []).append(result["median_pct"])
    return {name: float(np.median(v)) for name, v in medians.items() if len(v) >= 3}


def offset_problems(session: dict) -> list[dict]:
    """Steady offsets, which `round_problems` cannot see because nothing changed between rounds.

    {"slot": None, ...} when the all-slot median is more than `TABLE_OFFSET_PCT` from 0 (every
    slot reads off since the calibration); then one {"slot": name, ...} per slot, in layout order,
    whose steady reading is more than `SLOT_OFFSET_PCT` from the all-slot median. Measured against
    the other slots, not 0, so a whole-table offset does not also flag every slot."""
    steady = _steady_readings(session)
    if not steady:
        return []
    table = float(np.median(list(steady.values())))
    problems = []
    if abs(table) > TABLE_OFFSET_PCT:
        problems.append({"slot": None, "offset_pct": table})
    problems += [
        {"slot": slot["name"], "offset_pct": steady[slot["name"]] - table}
        for slot in session["slots"]
        if slot["name"] in steady and abs(steady[slot["name"]] - table) > SLOT_OFFSET_PCT
    ]
    return problems


def flagged_slots(session: dict) -> list[str]:
    """Slots, in layout order, that moved between rounds or read steadily off the others."""
    flagged = set(inconsistent_slots(session)) | {
        p["slot"] for p in offset_problems(session) if p["slot"] is not None
    }
    return [slot["name"] for slot in session["slots"] if slot["name"] in flagged]


def is_validated(session: dict) -> bool:
    """Complete and consistent: no slot moved between rounds, none reads steadily off the others,
    and the table as a whole does not read off since the calibration. Judged from the rounds every
    time, not from `completed_at`: a later round can take the status away again. A status, not a
    block."""
    return (
        session["completed_at"] is not None
        and not inconsistent_slots(session)
        and not offset_problems(session)
    )


def status(session: dict) -> dict:
    """The session's status, one of "validated", "not_consistent" or "not_validated", and the
    label the pages and the map caption show for it. Not consistent wins over everything else:
    it can show from the second round on, before the session is complete."""
    counted = len(counted_rounds(session))
    flagged = flagged_slots(session)
    table_off = any(p["slot"] is None for p in offset_problems(session))
    if flagged or table_off:
        if table_off or len(flagged) == len(session["slots"]):
            slots = "all slots"
        else:
            slots = ", ".join(flagged)
        return {"state": "not_consistent", "label": f"Not consistent: {slots}"}
    if is_validated(session):
        label = f"Validated {session['completed_at'][:10]}"
        if short_span(session):
            label += (
                f", rounds spread over {span_text(round_span_minutes(session))} min, under the "
                f"recommended {MIN_SPAN_MINUTES:.0f}"
            )
        if short_gap(session):
            label += (
                f", rounds {span_text(shortest_gap_minutes(session))} min apart, under the "
                f"recommended {MIN_ROUND_GAP_MINUTES:.0f}"
            )
        return {"state": "validated", "label": label}
    state = "Ended before completion" if session.get("ended_at") else "Provisional"
    return {"state": "not_validated", "label": f"{state}: {counted} of {ROUNDS_REQUIRED} rounds"}


def round_problems(session: dict) -> list[dict]:
    """Which round made a slot inconsistent, and whether it was one sheet or the whole round.

    Each slot's reference is the median of its per-round medians over all counted rounds; a round
    whose median sits more than `MEDIAN_DISAGREEMENT_PCT` from it is a problem there. The median of
    all rounds, not of the other rounds: with 3 rounds and one bad, the other two's midpoint would
    sit halfway to the bad one and flag the good rounds too. Needs 3 counted rounds: with 2, both
    sit equally far from any reference, so the odd one out cannot be told.

    A round in which at least `WHOLE_ROUND_FRACTION` of measured slots are off the same way is
    reported once as a whole-round shift (the camera or table moved), not as one sheet per slot.

    What this cannot see: a bad sheet (or tray) that stays on one slot every round reads the same
    each time. `offset_problems` catches that one, against the other slots, but cannot tell the
    sheet from the slot; moving sheets between trays every round is what tells them apart.

    Returns dicts in round order: {"round": number as the page counts rounds (1-based, all
    rounds), "slot": name or None for a whole-round shift, "offset_pct": signed points}.
    """
    counted = [(i + 1, r) for i, r in enumerate(session["rounds"]) if r["counted"]]
    if len(counted) < 3:
        return []
    medians = {
        number: {
            name: result["median_pct"]
            for name, result in (round_slot_results(round_) or {}).items()
            if result["median_pct"] is not None
        }
        for number, round_ in counted
    }
    reference = {}
    for slot in session["slots"]:
        values = [m[slot["name"]] for m in medians.values() if slot["name"] in m]
        if len(values) >= 3:
            reference[slot["name"]] = float(np.median(values))

    problems = []
    for number, _round in counted:
        offsets = {
            name: medians[number][name] - ref
            for name, ref in reference.items()
            if name in medians[number]
        }
        off = {name: d for name, d in offsets.items() if abs(d) > MEDIAN_DISAGREEMENT_PCT}
        signs = {d > 0 for d in off.values()}
        if offsets and len(off) >= WHOLE_ROUND_FRACTION * len(offsets) and len(signs) == 1:
            problems.append(
                {"round": number, "slot": None, "offset_pct": float(np.median(list(offsets.values())))}
            )
            continue
        problems += [
            {"round": number, "slot": slot["name"], "offset_pct": off[slot["name"]]}
            for slot in session["slots"]
            if slot["name"] in off
        ]
    return problems


def refresh_results(session: dict) -> None:
    """Recompute pooled per-slot results from the counted rounds, and stamp `completed_at` the
    first time `ROUNDS_REQUIRED` rounds have counted (it is never cleared or moved later)."""
    pooled: dict[str, list[float]] = {slot["name"]: [] for slot in session["slots"]}
    for round_ in counted_rounds(session):
        for name, errors in round_["slot_errors"].items():
            pooled[name].extend(errors)
    session["results"] = [
        {"name": r.name, "n": r.n, "p95_abs_pct": r.p95_abs_pct, "median_pct": r.median_pct}
        for r in slot_results_from_errors(pooled)
    ]
    if session["completed_at"] is None and len(counted_rounds(session)) >= ROUNDS_REQUIRED:
        session["completed_at"] = datetime.now(timezone.utc).isoformat()
    # Recorded with the result, so the session file itself says how spread out the rounds were.
    session["round_span_minutes"] = round_span_minutes(session)
    session["short_span"] = short_span(session)
    session["shortest_gap_minutes"] = shortest_gap_minutes(session)
    session["short_gap"] = short_gap(session)
