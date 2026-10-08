# CLAUDE.md

## What this is

Plant growth monitoring for an environmental chamber. Raspberry Pi 5, one top-down Arducam 64MP
camera, Hailo AI accelerator. Measures canopy area per growth tray, tracks trays by AprilTag, and
reports how much to trust each number. Web UI served from the Pi.

`PLAN.md` is the reference. Read only the milestone you are working on, not all 568 lines.

## The governing principle

> **Certainty is measured, never derived.** If a number cannot be demonstrated with a ruler, a
> printed target, or a repeated observation, it does not ship.

This project has been attempted three times. Each time it collapsed into camera metrology — lens
models, distortion coefficients, uncertainty propagation — and never produced a working
application. The principle above is not a style preference. It is the thing that prevents a fourth
failure.

Worked example, from the previous attempt's own data:

| Error source | Magnitude in area |
|---|---|
| Believing the old rig's tags were the 30 mm printed on the box (they measured 29.3106 mm) | ~4.7% |
| Tag corner-finding precision | ~0.15% |
| Segmentation edge ambiguity | several % |

The largest geometric error in the system was fixed with callipers. Work on the biggest error
source, not the most interesting one. The lesson is "measure each printed sheet", not "tags are
29.3106 mm": the current sheets measure 30.0 mm (see Facts below).

## Evidence gates

These techniques are **deferred, not forbidden**. Each has a specific measurement that would
justify picking it up. Do not adopt one without that measurement.

| Deferred | Adopt when |
|---|---|
| Intrinsic calibration, distortion coefficients | The honesty plot shows residuals that are structured (worse toward frame corners), not random |
| Out-of-plane parallax correction | A measured depth source exists |
| Orthophoto / photogrammetry | A second viewpoint exists |
| Second camera | M1–M6 done, and measured in-plane accuracy proved insufficient |
| YOLO tray identification | Tag identity measurably fails often enough to matter |

Perspective modelling **within** the measurement plane is not deferred. The homography is exactly
that and we use it throughout.

If you find yourself about to write calibration maths, stop and check this table first.

## Test discipline

The previous attempt ran expensive tests on every change, including documentation edits: 223
seconds of every 303-second run went to five files decoding 64MP frames. The markers existed. The
default did not.

`pyproject.toml` sets `addopts = -m unit`. Expensive tiers are opt-in and unreachable by accident.

```
pytest                 # unit only, no hardware, budget <10s
pytest -m hardware     # needs the camera
pytest -m hailo        # needs the accelerator
pytest -m integration  # full pipeline against fixture images
pytest -m slow         # soak
```

| Change | Run |
|---|---|
| Docs, markdown, comments | Nothing |
| HTML, CSS, copy | Nothing. Look at it in a browser |
| One logic module | That module's unit tests |
| Logic across modules | `pytest` |
| Camera code | `pytest`, then one manual check on real hardware |
| Before a commit | `pytest` |
| Milestone sign-off | Full suite plus the physical acceptance tests |

No pre-commit hook that runs tests. Formatting and linting hooks are fine.

Hardware tests skip when hardware is absent, they do not fail. A synthetic camera backend is
required infrastructure, not a nicety.

## Working with Aaron

**Questions are questions.** When asked something, answer from context. Do not run tests, shell
commands, or long tool chains to answer. Reading a file or searching the web is fine when genuinely
needed.

**Statements are not instructions.** If told a fact, acknowledge it. Do not go update files to
reflect it unless asked.

**Minimize tool use.** Act when asked to do work, or after saying what you intend and getting
agreement.

**No parallel action on a pending question.** When a question is open for Aaron, do nothing else
in that turn — no installs, no file edits, no other tool calls — until he answers. A question is a
stop, not one branch of a parallel batch.

**Delegate noisy investigation.** Grep sweeps, log trawls, and broad file searches go through the
Explore agent or a fork, not inline in the main conversation. Keep only the findings, not the raw
search output, in context.

**Reply format.** Five headings, in this order. Skip any that are empty.

```
**Done** — what changed
**Needs you** — what is blocked and why
**Next** — the single recommended action
**Outstanding** — short list
**Session** — close now, or keep going
```

Plain language. No metaphors, no figures of speech. Numbers instead of adjectives. Under 150 words
by default. Longer only in answer to a direct question that needs it.

When using AskUserQuestion, always leave room for a free-text answer.

## Parallel work

Several agent sessions may work at once, each on its own task. The PR workflow is in
`CONTRIBUTING.md`. These are the rules for not getting in each other's way.

**Identity.** Agents act as `txoof-bot`. `.claude/settings.local.json` in `~/npec_camera_rig`
(not tracked) sets `GH_CONFIG_DIR`, `GIT_SSH_COMMAND` and the git author for every session started
there. Do not unset or override them. Check at the start: `gh auth status` says `txoof-bot`.
Start agent sessions in `~/npec_camera_rig`; a session started anywhere else acts as Aaron.

**A task** is one thing Aaron can try in the browser in one sitting. It may cover several small
related issues in the same milestone and area. It is one PR of about 500 changed lines or less,
not counting tests. A bigger task is split into PRs that each work on their own.

**Issues are the to-do list.** Every change starts from an issue made with the Task template,
in a milestone (M2 to M6). Repo `txoof/npec-camera-rig`, board
https://github.com/users/txoof/projects/5.

**Claiming.** Before starting, list what is taken:

```bash
gh issue list --label in-progress
```

Do not start an issue labelled `in-progress`, or one whose Area overlaps a claimed issue's Area.
Claim every issue the task covers, and release when the PR is merged or when stopping early:

```bash
gh issue edit <n> --add-label in-progress
gh issue comment <n> --body "claimed by <branch>"
gh issue edit <n> --remove-label in-progress
gh issue comment <n> --body "released: <reason>"
```

Other labels: `needs-decision` (waiting for Aaron), `blocked` (waiting for another issue or an
outside thing), `area:*` (filter by area).

**The camera and port 8000: the `hardware` label.** There is one camera and one live server. The
`hardware` label is a lock: at most one open issue has it. Only that task may use the camera,
restart the port 8000 server, or ask Aaron to try its work. Take it only when
`gh issue list --label hardware` is empty. In the claim comment, write the command line the
server was running with (`ps -eo args | grep uvicorn`). When Aaron has tried the work, put the
server back as it was and remove the label. Everyone else writes code and runs unit tests with the
synthetic camera, then waits for the label.

**Area map.** Which files a task may change. A test file goes with its module.

| Area | Files |
|---|---|
| camera | `camera.py`, `captures.py`, `settings.py` |
| calibration | `tags.py`, `calibration*.py`, `validation_store.py`, `tripwire.py`, `certainty_map.py` |
| web | `app.py`, `templates/`, `static/` |
| images | `images.py`, `text_render.py` |
| docs | `docs/` (except the shared files below), `reference/`, `README.md` |
| cad | `hardware/` |
| deploy | `deploy/` |
| ci | `.github/`, `pyproject.toml`, `uv.lock` |

Module files are in `src/npec_rig/`. A new module or folder is added to this map in the PR that
creates it.

**Shared files** may be changed by any task that needs to, after checking that no other open PR
changes them: `CLAUDE.md`, `PLAN.md`, `CONTRIBUTING.md`, `docs/metrology-log.md`,
`docs/measurement-trust.md`, `docs/operator-guide.md`, `pyproject.toml`, `uv.lock`,
`tests/conftest.py`, `tests/helpers.py`.

```bash
f=docs/metrology-log.md
for n in $(gh pr list --json number --jq '.[].number'); do
  gh pr diff "$n" --name-only | grep -qx "$f" && echo "#$n changes $f"
done
```

**Worktrees.** One per task, outside the repo, so the live server never sees the files change.
Do not use the EnterWorktree tool: it puts worktrees inside the repo.

```bash
git -C ~/npec_camera_rig fetch origin
git -C ~/npec_camera_rig worktree add -b <n>-<short-name> ~/wt/npec-<n>-<short-name> origin/main
```

The branch, the folder and the claim comment use the same name. Run tests there with
`PYTHONPATH="$(pwd)/src"`. Never work on `main`. Do not touch another session's worktree or PR.
After the merge, remove the worktree and the local branch.

**The board.** Columns Todo, In Progress, In Review, Done. Move the cards for the issue and its PR:
In Progress when claimed, In Review when the PR is opened, back to Todo when a claim is released
unfinished. Closing and merging move cards to Done by themselves. `item-add` on a card that is
already on the board returns its id, so always run both commands:

```bash
item=$(gh project item-add 5 --owner txoof --url <issue-or-PR-URL> --format json --jq .id)
gh project item-edit --project-id PVT_kwHOANmg6c4BmGmA --id "$item" \
  --field-id PVTSSF_lAHOANmg6c4BmGmAzhkw6FQ --single-select-option-id <column-id>
```

Column ids: Todo `2ddd622b`, In Progress `3d30af1f`, In Review `822c51c8`, Done `d284367f`.

**Email.** Every GitHub action emails Aaron. Push in batches, post one combined comment, and do not
switch labels, draft state or reviews back and forth.

## Facts not to rediscover

- **Current 30 mm AprilTags measure 30.0 ± 0.1 mm.** Callipers, 2026-09-29: 30 mm tag X 30.10 /
  30.11 / 29.96, Y 30.04 / 29.96 / 29.94 (mean 30.018); 50 mm tag mean 50.02; 180 mm sheet scale
  bars 179.93 and 180.03. Callipers are not trusted beyond 0.1 mm. 36h11 family. The 29.3106 mm
  figure in older docs and code belongs to the previous rig's printed tags and does not apply.
- **The rig has been physically rebuilt.** Every geometry value from the old calibration is dead:
  camera distance, table tilt, lens position, intrinsics. Re-measure them. Tray height survives.
  Tag size is a property of each printed sheet: measure every new print with callipers.
- **`/home/pi/old/npec_OLD/npec-camera` is frozen.** Read it, do not modify, move or delete it.
  Its `metrology/` package is a clean leaf with no inbound dependencies from the camera or web
  layers. Its `sweep.py` / `characterisation.py` (~2650 lines) is the same failure under another
  name and is entangled with the web routes.
- **Old code is reference only.** Read it to learn what worked on this hardware, then write fresh.
- **No Hailo code, no `.hef`, no segmentation exists anywhere.** M5 starts from nothing, behind a
  `Segmenter` interface with a classical excess-green fallback.
- **362 MB of bench frames** sit at `/home/pi/old/npec_OLD/npec-camera/tests/data/`. From the previous rig,
  so the geometry no longer matches. Available if needed, not copied in.
- **The central low reading (the "North 4 hot spot") is the Arducam's own, and it is closed.**
  Investigated 2026-09-30 to 10-02, record in `reference/arducam-central-error-2026-10.md`. Targets
  within about 1500 px of the image centre read up to about 4% small in area. A Canon photographing
  the same table does not see it, so it is not the table, sheets, trays, lighting or detector. Its
  size follows the focus lens position (about 1.2 points of area per 0.1) and shifts after the lens
  is moved. Do not reopen it; validation measures it per slot. Reopen only if validation flags a
  slot as not consistent while nothing was moved.
- **The focus position is the experimenter's choice, never ours.** The rig drives the lens there one
  consistent way and confirms it (`CameraManager._drive_lens`), then calibration and validation
  measure the error at that position. Never recommend or tune a lens position for accuracy.
- **Height above the tray top changes area by about 0.145% per mm** (measured: a 75 mm taller tray
  read 11.2% to 12.0% large, predicted 11.8%). Validation bands cover flat objects at tray-top height
  only; plant height and segmentation add to them (PLAN.md, *Per-slot area uncertainty*).
- **Rig timestamps (capture names, session IDs) are UTC; the chamber's local time is UTC+2.**
  Convert before matching them against anything a person reports.

## Where things live

| Path | What |
|---|---|
| `PLAN.md` | Full plan. Read the relevant milestone only |
| `TODO.md` | Actionable items, linked to plan milestones. Being moved to GitHub issues (see *Parallel work*) |
| `CONTRIBUTING.md` | Branches, PRs, review and merging |
| `reference/old-calibration/` | Rescued measured values from the previous rig |
| `reference/arducam-central-error-2026-10.md` | The central-error investigation: evidence, what was ruled out, how the error is managed |
| `docs/measurement-trust.md` | Why the rig's area measurements can be trusted, and the steps taken to build that trust. The case, for reports and a possible paper |
| `docs/metrology-log.md` | Log of every measurement, test method and result, with sources: the evidence behind `measurement-trust.md`. See *Write up every measurement* |
| `docs/operator-guide.md` | For the scientists running experiments: focus, lock, calibrate, validate, and what the uncertainty column means |
| `/var/lib/npec-rig/` | Runtime data: captures, masks, `rig.db` |
| `/var/lib/npec-rig/derived/` | Derived images (validation maps, problem frames; later thumbnails), made once by `images.py`, disposable. Every large image goes through `images.py` (PLAN.md, *Images*) |
| `/etc/npec-rig/config.yaml` | Per-rig configuration. Planned (PLAN.md's Technical decisions table), not yet implemented — current settings live in env vars and SQLite only |

## Write up every measurement

Every metrology finding and every validation result is written up in `docs/metrology-log.md`, in the
same change that produces it: what was measured, how, with what instrument, how many times, the
result with its spread, the date, where the raw data is, and what it does and does not cover.
Detailed investigations go in `reference/` and are linked from it. A number that is a decision or
a placeholder, not a measurement, says so. Written for a scientist without a metrology
background, formal enough to cite in a paper about the rig (Aaron, 2026-10-05).

A test's method is written into `docs/metrology-log.md` before the test is run, and its result is
added when it is done. When a finding adds to, strengthens or weakens a step of the case in
`docs/measurement-trust.md`, that document is updated in the same change. A measurement that is
not written up is not finished.

## Definition of done

A slice is done when you can **see it working in a browser**, not when its tests pass. If a slice
cannot be demonstrated, it is not a slice — split it differently.

Milestones are done when the physical acceptance tests in `PLAN.md` pass, run in the chamber with a
tape measure and printed targets, and their results are written up in `docs/metrology-log.md` and
reflected in `docs/measurement-trust.md`.
