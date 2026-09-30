"""Validation sessions: the measured check of a calibration (certainty_map.py).

A session belongs to one calibration. Each round is one capture taken after the operator moved
every sheet on its tray and shuffled the trays; the calibration frame itself is never a round,
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


def is_validated(session: dict) -> bool:
    """Complete and consistent. Judged from the rounds every time, not from `completed_at`: a
    later round that moves a slot's median takes the status away again. A status, not a block."""
    return session["completed_at"] is not None and not inconsistent_slots(session)


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
    each time, so it looks like a bad slot, not a problem. Sheets must change trays every round.

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
