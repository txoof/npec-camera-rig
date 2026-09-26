# Calibration history browser — handoff plan

Written 2026-09-26, for a fresh agent to pick up. Read `CLAUDE.md` first (the whole file is
short); this doc assumes you have. This is flagged in `TODO.md`'s M2 UI usability section as
"major feature, not started" — treat it as a real slice of work, plan-first, not a quick add.

## The problem

Aaron, verbatim, describing the actual scenario this needs to solve:

> I would like the option to undo a recent calibration and pick one from the past. For example,
> if I had a good calibration and accidentally ran and accepted a calibration over a running
> experiment table without tags. The accidental calibration would be useless and I would like to
> be able to step back to the previously known good calibration. The camera state hasn't changed
> and the last known good calibration would still be usable.

And, extending it after discussing a narrower "undo" mechanism:

> I want the option to browse saved history for exactly the situation of accidentally running
> multiple bad calibrations without changing anything in the physical setup.

The key physical fact underneath this: a calibration's validity depends on the camera/rig's
*physical* state, not on when it was captured. If nothing has physically moved since an old
calibration was taken, that old calibration is exactly as valid today as it was then — reaching
back into history and reactivating it is not a hack, it's using a real, still-true measurement.

## What was considered and rejected: an "Undo" button

A single-level `previous.json` snapshot (swap current/previous on every promotion) was proposed
and explicitly rejected. Aaron: "I don't want an undo button; it is not clear to the user what
undo means and how many steps back it takes things and what states change." It also can't handle
the "multiple bad calibrations in a row" case in the problem statement — a single undo level only
recovers one mistake back. Don't revisit this design; a full browsable history is both clearer
and strictly more capable.

## What to build instead

A history browser, not an undo action. Every saved calibration is already written as its own
timestamped JSON file plus a saved full-res frame (`calibration_store.py` — nothing is ever
deleted or overwritten except `current.json` itself), so the raw material already exists; this
is a UI + a handful of endpoints on top of it, not a new storage model.

Required pieces:

1. **Browse**: a list of every saved calibration, each entry showing:
   - A snapshot image of the table (the saved frame, or the table-view render — both already
     exist per-run, see "Already available" below).
   - A readout of a few critical stats: at minimum, how coplanar the table/camera system was
     (co-planarity, i.e. corner-tag scale spread) and how much error the calibration carries
     (residual/coverage). Aaron asked for these specifically as examples, not an exhaustive
     list — use judgement on what else is worth a line, but don't recreate the full "10 lines of
     everything" problem the diagnostics-tidy work (same day, see `TODO.md`) was just trying to
     get away from. This is a summary card, not the full report.
   - Color coding using the same red/amber/green (bad/ok/good) language already used on the
     traffic-light overlays elsewhere in the app. See "Thresholds" below — reuse what's
     established, don't invent new bands without evidence.
2. **Select / promote**: choosing an entry makes it the active calibration (`current.json`).
   **Required, explicit copy near this action**: selecting a saved calibration is **not** a
   substitute for running an end-to-end calibration. It reactivates an old *measurement*; it does
   not re-verify that the physical setup still matches it. State this plainly in the UI, not just
   in a tooltip.
3. **Delete**: an option to clear out old saved calibrations (disk hygiene — each one carries a
   full-res frame plus several heatmap JPEGs). Must refuse to delete whichever one is currently
   active (`current.json`'s own stem) — that would leave the rig with a dangling pointer.
   Destructive action: confirm before deleting, same as any other destructive UI action in this
   codebase.

## Already available (don't rebuild)

- `calibration_store.list_calibrations()` — every saved artifact file, oldest first.
- `calibration_store.load_calibration(path)` — load any specific one by path/stem.
- `calibration_store.save_calibration(artifact, stem=None, promote=True)` — the exact mechanism
  "promote" already uses; promoting from history is a call to this with an already-loaded
  artifact and no fresh capture, not new logic.
- `GET /calibration/list` (`app.py`) — already returns every saved artifact with its
  frame/heatmap URLs (`frame_url`, `heatmap_url`, `area_shape_heatmap_url`,
  `accuracy_shape_heatmap_url`, `table_view_url`, `table_view_shape_url`). The heatmap/table-view
  images are pre-rendered and saved to disk at capture time (`calibration_store.save_calibration_*`
  functions) — they do **not** need re-rendering to view an old run's snapshot.
- The existing "Saved calibrations (download)" `<details>` panel in `setup_calibration.html`
  (Step 5, "Read the report") is the current, much simpler version of this same idea (a plain
  link list) — this feature replaces/upgrades it, doesn't duplicate it. TODO.md's older item
  asking for "preview thumbnails plus a download action" is the same ask at smaller scope, folded
  into this one.

## Real gaps to fill

- **No per-entry stats in `/calibration/list` today** — it only has URLs and a filename. Some
  stats are cheap (already on the artifact, no recomputation): `residual_std_pct`
  (`ScaleField`), `calibration_tag_size_mm`, corner-tag count (`CornerBaseline`). Others are
  **not** persisted anywhere and need re-detecting tags from the saved frame to reconstruct
  (holdout coverage error, coplanarity direction/magnitude, area-scale error) — the same
  re-detection the rank-plot/best-worst-photo/radial-plot endpoints already do for the *current*
  run only. Re-detecting tags from every saved frame just to render a list could be slow with
  many saved runs (each is a full-res tag-detection pass) — **decide deliberately** whether the
  list view only shows the cheap stats (fast, always available) and defers the expensive ones to
  a per-entry "view full report" step, or whether it's fast enough in practice to just do it for
  every entry. Don't guess this without checking timing against a real saved-frame directory with
  more than a couple of entries.
- **No promote-from-history endpoint** — needs a new route, e.g. `POST
  /calibration/{stem}/promote`, that loads that stem's artifact and calls `save_calibration` with
  `promote=True`, no camera capture involved.
- **No delete endpoint** — needs a new route, e.g. `DELETE /calibration/{stem}`, removing the
  artifact JSON plus its frame and heatmap files. Guard against deleting the stem `current.json`
  currently points at.

## Thresholds — reuse, don't invent

- Co-planarity / corner-tag scale spread already has an established three-band scheme:
  `tripwire.py`'s `DEFAULT_SCALE_DRIFT_PCT = 3.0` (green/amber boundary) and
  `DEFAULT_SCALE_FAIL_PCT = 8.0` (amber/red boundary) — the same numbers Step 2's traffic-light
  overlay already uses. Reuse these for a coplanarity color, don't pick new numbers.
- Coverage/holdout error only has a **single** established bound: PLAN.md's 2% acceptance target
  (`calibration.py`'s `describe_coverage`, `threshold_pct: float = 2.0`) — a binary
  sufficient/insufficient, not a three-band scheme. If a three-color treatment is wanted for this
  metric too, that's a real, undocumented judgement call (where does "amber" start?) — surface it
  to Aaron rather than inventing a number, per CLAUDE.md's whole governing principle.
- Area-scale error and other metrics in the report have no color convention established at all
  yet. Don't invent one without checking whether it belongs on this card at all.

## Non-goals

- No "Undo" button (see above — considered and explicitly rejected).
- No automated retention policy (auto-delete oldest, "keep last N") — that's M3's storage-tier
  scope (`TODO.md`'s M3 section already tracks it), not this. This feature is manual, on-demand
  cleanup only.
- Not a redesign of the full calibration report's diagnostics layout — that's the separate
  "tidy up the calibration result messages" item in `TODO.md`, already planned (headline vs.
  "Diagnostics" panel split), agreed the same day as this doc. Don't conflate the two.

## Suggested approach

Follow this repo's established working pattern (CLAUDE.md, and the m2 project-memory log if you
have access to it): small slices, each one a worktree → edit → `pytest` → commit → merge into the
real checkout → verify against the live running server directly (never a temp server) → stop for
Aaron to look before the next slice. Given the scope here, propose your own slice breakdown and
confirm it with Aaron before writing code — this is exactly the kind of "fairly major change" he
asked to have planned first, not built in one pass.
