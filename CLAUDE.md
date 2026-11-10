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
| Intrinsic calibration, distortion coefficients | The radial plot (calibration step 5) shows error growing steadily toward the frame corners, beyond the known central low reading, not random scatter. "Structured" is Aaron's judgement, no numeric threshold |
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
pytest                 # unit only, no hardware, budget <15s, 4 workers in parallel (-n 0: serial)
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

### Test-first

Logic modules and bug fixes are built test-first. Pages, CSS and copy are not: look at them in a
browser. These rules apply to new tests. Older tests that break them are fixed only when a task
touches them anyway.

1. **Agree the seams first.** Before writing a test, list the public interfaces to test (a route's
   response, a module's public function), one line each on what it catches and what it misses.
   Aaron confirms the list. No test is written at an unconfirmed seam.
2. **One test, then one change.** Write one failing test, run it and see it fail, then write only
   enough code to pass it. Repeat. Do not write all the tests first.
3. **A bug fix starts with a test that reproduces the bug.**
4. **Expected values come from outside the code.** Calliper readings, worked examples, fixture
   images with known answers. Never recompute the expected value the way the code does.
5. **Test behaviour, not internals.** No tests of private (underscore) functions. Fake only at
   these points: tag detection (`detect_tags`, since real photos are hard to build), the synthetic
   camera backend and its subclasses, and timing constants. Do not replace any other project
   function.
6. Tidying the code comes after the tests pass, in review, not during the loop.

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

**Check-ins.** Between the ends of rounds, show progress as a picture or table in `~/scratch`
with 2 or 3 lines on what to look at, then wait for Aaron before going on (PLAN.md, *Rounds*).

**Pictures for Aaron.** Put them on the controller in `~/scratch/<branch>/` and link them as
`http://testpi-02:8001/<branch>/<file>`. That is the one scratch viewer (`imgview.service`, from
`~/ansible-npec`, `docs/12-scratch-viewer.md`); never start another one (Aaron, 2026-11-06).

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

## Development and production rigs

Since 2026-10-28 (#322), with the controller since 2026-10-29 (#324). The full rule is in
`~/ansible-npec/AGENTS.md`. Three devices in total:

| | Device | What runs there |
|---|---|---|
| **controller** | `testpi-02`, where agent sessions run | Agent sessions, worktrees, unit tests, `~/ansible-npec` |
| **development** | `npec-rig-01` (`10.248.49.102`), red leaf in the tab, Arducam 64MP | The app as the `npec-rig` service on port 8000, managed from `~/ansible-npec` |
| **production** | `ac-testing`, the chamber Pi | Running experiments: `~/npec_camera_rig` and its port 8000 server |

Reach the rigs from the controller with `ssh pi@npec-rig-01`. Agent
sessions run on the controller. They may run jobs on the development rig over ssh (scripts, Hailo
models, offline analysis of copied production photos), only while their task holds the `hardware`
label, with memory capped (`ulimit -v`). Production is read only, as before (Aaron, 2026-11-09,
#400).

A new app version runs on development first. It reaches production only after it has passed on
development (health OK and a live snapshot) **and** Aaron has approved that update.

- **Updating production** means changing the code in `~/npec_camera_rig` on `ac-testing` (pull,
  checkout, merge) or restarting its port 8000 server. After a PR is merged, leave production as
  it is and say in the reply that it can be promoted. Reading production (its API, logs, photos,
  a read-only look at `rig.db`) is fine; nothing else is done there without Aaron's approval.
- **A branch on development**, from `~/ansible-npec` on the controller:
  `make update-app HOST=npec-rig-01 ARGS="-e npec_rig_version=<branch>"`. It restarts the app.
  If `curl -s 10.248.49.102:8000/api/experiments` shows an experiment `"state": "running"`, ask
  Aaron first.

## Parallel work

Several agent sessions may work at once, each on its own task. The PR workflow is in
`CONTRIBUTING.md`. These are the rules for not getting in each other's way.

**Identity.** Agents act as `txoof-bot`. `.claude/settings.local.json` in `~/npec_camera_rig`
(not tracked) sets `GH_CONFIG_DIR`, `GIT_SSH_COMMAND` and the git author for every session started
there. Do not unset or override them. Check at the start: `gh auth status` says `txoof-bot`.
Start agent sessions in `~/npec_camera_rig` on the controller `testpi-02`; a session started
anywhere else acts as Aaron.

**A task** is one thing Aaron can try in the browser in one sitting. It may cover several small
related issues in the same milestone and area. It is one PR of about 500 changed lines or less,
not counting tests. A bigger task is split into PRs that each work on their own.

**Issues are the to-do list.** Every change starts from an issue made with the Task template.
Repo `txoof/npec-camera-rig`, board https://github.com/users/txoof/projects/5. Work is planned in
rounds of about 2 weeks (PLAN.md, *Rounds*); each card's *Round* field says which round it belongs
to. Milestones (M3 to M6) group issues by feature and do not set the order of work. Work only on
issues in the round Aaron names. If he names none, use the current round (the one whose dates
cover today). An issue with no Round is started only when Aaron asks for it.

**Picking an issue.** When Aaron names no issue ("pick the next task"), list the current round's
Todo cards, then read the milestone descriptions: they hold the triage and the order he decided.

```bash
gh project item-list 5 --owner txoof --limit 500 --format json \
  --jq '.items[] | select(.round != null and .status == "Todo")
    | select((.round.startDate | strptime("%Y-%m-%d") | mktime) as $s
        | now >= $s and now < $s + .round.duration * 86400)
    | [.round.title, .priority, .content.number, .title] | @tsv'
gh api repos/txoof/npec-camera-rig/milestones --jq '.[] | "\(.title)\n\(.description)\n"'
```

Take the unclaimed issue with the highest board Priority (High, Medium, Low) whose Area does not
overlap a claimed issue. Within one priority, follow the order in the milestone description, then
the lowest issue number. `TODO.md` is a frozen record: read it for the history of done items,
never add to it.

**Filing a new issue.** Every new issue gets a Priority, and a Round or the label
`Future development`, when it is put on the board, chosen by the table below. The reply that
creates it says which in one line, so Aaron only corrects it when it is wrong. Put a session's
follow-ups in one issue, not several (Aaron, 2026-10-16).

Rounds hold only work that can cause harm, blocks the current round, or is needed for the thesis
requirements: the acceptance tests in PLAN.md, the final target and the wrap-up. Every other
issue gets the label `Future development` and no Round. It is not closed for that reason
(Aaron, 2026-10-27).

| Kind of issue | Round | Priority |
|---|---|---|
| Can cause harm, new or old behaviour | Current | High |
| Blocks work in the current round | Current | High |
| Needed for the thesis requirements | Current or next | High or Medium |
| Changes what users see | `Future development` | Medium |
| Old behaviour, no harm possible | `Future development` | Low |

Harm is any of:

1. **Wrong numbers with no warning.** An area or uncertainty is wrong and nothing on the page
   says so.
2. **Lost data.** Photos, calibrations, validations or experiment records deleted or overwritten.
3. **A running experiment disturbed.** Its calibration replaced, or the lens moved, mid-experiment.
4. **An easy mistake with a bad result.** A control where one wrong tap causes 1, 2 or 3, with no
   confirmation.

When a round ends, the cards it did not finish move to the next round.

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

**The development rig: the `hardware` label.** Tasks use one camera and one server: those on
`npec-rig-01`. The `hardware` label is a lock: at most one open issue has it. Only that task may
use the development camera, put its branch on development, or ask Aaron to try its work there.
Take it only when `gh issue list --label hardware` is empty. In the claim comment, write the app
version development was running
(`ssh pi@npec-rig-01 'git -C ~/npec_camera_rig log --oneline -1'`). When Aaron has tried the
work, put development back on that version and remove the label. Everyone else writes code and
runs unit tests with the synthetic camera on the controller, then waits for the label. No task
uses the production camera or server.

**Restarting the production server.** Only on a promotion Aaron approved, on `ac-testing`, over
ssh. Stop it with SIGTERM, never SIGINT or Ctrl+C (a second
SIGINT makes uvicorn skip the app's shutdown, and the camera is not closed), and wait until the
old PID is gone before relaunching. Launch it with `--timeout-graceful-shutdown 5`, so open
browser tabs with a live view hold a restart for 5 s at most instead of until they are closed
(#139):

```bash
/home/pi/npec_camera_rig/.venv/bin/python3 /home/pi/npec_camera_rig/.venv/bin/uvicorn \
  npec_rig.app:app --app-dir /home/pi/npec_camera_rig/src --host 0.0.0.0 --port 8000 \
  --timeout-graceful-shutdown 5
```

**Area map.** Which files a task may change. A test file goes with its module.

| Area | Files |
|---|---|
| camera | `camera.py`, `camera_process.py`, `captures.py`, `health.py`, `settings.py`, `scheduler.py` |
| calibration | `tags.py`, `calibration*.py`, `validation_store.py`, `tripwire.py`, `certainty_map.py`, `photo_tags.py`, `validation.py` |
| web | `app.py`, `routes/__init__.py`, `routes/shell.py`, `routes/shared.py`, `templates/setup_index.html`, `templates/ui_reference.html`, `templates/_ui.html`, `templates/_camera_status.html`, `static/ui.js`, `static/icons.svg`, `static/lightbox.js`, `static/squareness-guides.js`, `static/validation-status.js`, `tests/web/conftest.py`, `tests/web/tag_scenes.py`, `tests/web/test_app.py` |
| web-focus | `routes/focus.py`, `templates/setup_focus.html`, `templates/_focus_controls.html`, `templates/_squareness.html`, `templates/_squareness_help.html` |
| web-gallery | `routes/gallery.py`, `templates/gallery.html` |
| web-experiments | `routes/experiments.py`, `templates/experiments.html` |
| web-calibration | `routes/calibration.py`, `templates/setup_calibration*.html`, `templates/setup_health_check.html` |
| web-validation | `routes/validation.py`, `templates/setup_validation.html` |
| web-photo-quality | `routes/photo_quality.py` (the JPEG setting of full-size photos through the API, #359), `tests/web/test_photo_quality_routes.py` |
| web-randomize | `routes/randomize.py`, `templates/randomize.html` (the Randomize page, #343) |
| web-about | `about.py` (the facts the About page shows, read when asked), `routes/about.py`, `templates/about.html` (the About page from the (i) button at the foot of the rail, later also manuals and links, #390) |
| images | `images.py`, `text_render.py` |
| segmentation | `segmentation.py` (plant masks: the `Segmenter` interface, the green threshold and the Hailo stub, #74) |
| randomization | `randomization.py` (restricted randomization of the tray layout and the check against it, #343) |
| database | `database.py` (the experiment's tables in `rig.db` and their migrations) |
| exports | `exports.py` (an experiment's export zip and its checksum manifest), `export_fields.yaml` (what every exported file and CSV column means, read at each export, #65) |
| trays | `tray_placement.py` (each tray's slot, A1 corner and outline, placed from its cell A1 tag), `tray_readings.py` (each photo read for its trays in the background, #222), `exclusions.py` (why a photo's plant areas are left out, from its exposure and gain, #288), `dwell.py` (each tray's table location, its stays there and the too-long warning, #332), `tests/fixtures/trays/` |
| docs | `docs/` (except the shared files below), `reference/`, `README.md`, `GLOSSARY.md` |
| cad | `hardware/` |
| deploy | `deploy/` |
| experiments | `experiments/<folder>/`, each folder its own area: research scripts for one investigation. They may import `src/npec_rig/`, never the reverse (`tests/test_experiments_boundary.py`), and are not deployed (`.gitattributes` leaves them out of release archives) |
| ci | `.github/`, `.gitattributes`, `pyproject.toml`, `uv.lock` |

Module files are in `src/npec_rig/`. A new module or folder is added to this map in the PR that
creates it: a new page joins the area of its route file, and a new route file gets its own row.

The web areas (#181):

- A route file's tests are `tests/web/test_<name>_routes.py`. The experiments routes are the
  exception: their tests are in `tests/test_experiments.py`, `test_exports.py` and
  `test_purge.py`, so web-experiments also overlaps database and exports.
- web holds what more than one page uses. `base.html` loads `squareness-guides.js` on every
  page, and `validation-status.js` is used by three pages, so both are in web.
- The Calibration page includes the focus and squareness panels: changing a panel is
  web-focus work even in a calibration task.
- An issue whose Area says only `web`, written before the split, overlaps every web area until
  its Area is narrowed to one.

**Shared files** may be changed by any task that needs to, after checking that no other open PR
changes them: `CLAUDE.md`, `PLAN.md`, `CONTRIBUTING.md`, `docs/metrology-log.md`,
`docs/measurement-trust.md`, `docs/operator-guide.md`, `pyproject.toml`, `uv.lock`,
`tests/conftest.py`, `tests/helpers.py`, `src/npec_rig/static/style.css`,
`src/npec_rig/templates/base.html`.

```bash
f=docs/metrology-log.md
for n in $(gh pr list --json number --jq '.[].number'); do
  gh pr diff "$n" --name-only | grep -qx "$f" && echo "#$n changes $f"
done
```

**Worktrees.** One per task, on the controller, outside the repo, so `~/npec_camera_rig` stays on
`main`. Do not use the EnterWorktree tool: it puts worktrees inside the repo.

```bash
git -C ~/npec_camera_rig fetch origin
git -C ~/npec_camera_rig worktree add -b <n>-<short-name> ~/wt/npec-<n>-<short-name> origin/main
```

**When the issue names an existing branch**, start from that branch instead of `origin/main`, or
the work it already holds (a spec, a mockup, an earlier slice) is missing and the push is
refused:

```bash
git -C ~/npec_camera_rig worktree add -b <branch> ~/wt/npec-<branch> origin/<branch>
```

Check `git ls-remote --heads origin <n>-*` before creating a branch: if one exists for the
issue, use it.

The branch, the folder and the claim comment use the same name. Run tests there with
`PYTHONPATH="$(pwd)/src"`. Never work on `main`. Do not touch another session's worktree or PR.
After the merge, remove the worktree and the local branch.

**The board.** Columns Todo, In Progress, In Review, Done. Move the cards for the issue and its PR:
In Progress when claimed, In Review when the PR is opened, back to Todo when a claim is released
unfinished. Closing and merging move cards to Done by themselves. The board may already hold the
card (it can add new issues on its own), and `item-add` then fails with "Content already exists".
So look the card up first and add it only when it is missing:

```bash
url=<issue-or-PR-URL>
item=$(gh project item-list 5 --owner txoof --limit 500 --format json \
  --jq ".items[] | select(.content.url==\"$url\") | .id")
[ -n "$item" ] || item=$(gh project item-add 5 --owner txoof --url "$url" --format json --jq .id)
gh project item-edit --project-id PVT_kwHOANmg6c4BmGmA --id "$item" \
  --field-id PVTSSF_lAHOANmg6c4BmGmAzhkw6FQ --single-select-option-id <column-id>
```

Column ids: Todo `2ddd622b`, In Progress `3d30af1f`, In Review `822c51c8`, Done `d284367f`.

Priority: field id `PVTSSF_lAHOANmg6c4BmGmAzhk3jzA`, option ids High `dc5dda64`, Medium `80dc29a9`,
Low `feb93a98`. Set it with the same `item-edit` command.

Round: field id `PVTIF_lAHOANmg6c4BmGmAzhl5GEo`, iteration ids Round 1 (15 to 22 Oct) `5fb3e246`,
Round 2 (23 Oct to 5 Nov) `6f459427`, Round 3 (6 to 19 Nov) `62ef7908`, Round 4 (20 Nov to 3 Dec)
`bc9ee329`. Set it with `item-edit` and `--iteration-id <id>` in place of
`--single-select-option-id`.

**Email.** Every GitHub action emails Aaron. Push in batches, post one combined comment, and do not
switch labels, draft state or reviews back and forth.

## Web pages

The pages are used on the chamber PCs: Windows touch screens at 1024x768, where the taskbar and
browser bar leave about 1024x600, worked with a stylus. Touch calibration is poor and differs
between the 15 screens. Aaron has checked one; its error says nothing about the others, so no page
is designed around a direction or size of touch error. The pages must also work on a phone. A
redesign of the whole interface is in progress (#125); until its components land, every new or
changed page follows these rules (Aaron, 2026-10-12). The numbers below are starting points, not
limits: where one does not work for a page, choose what does and say why in the PR.

- **Big targets, wide gaps.** Make tapped controls large, about 64px tall, with about 24px between
  them, so a missed tap lands on nothing instead of on a neighbor.
- **No hover, no small sliders, drag only where moving is the task.** Nothing is reachable only
  by hovering. Use buttons (a stepper) and a typed value instead of range inputs. Drag only with
  large handles, and only where moving something is the task itself, such as the squareness
  guides; every drag also has a keyboard alternative (for example W A S D or the arrow keys).
- **Scroll gutter.** Keep a lane on the right of scrolling content free of controls (about 64px on
  the chamber screen), so a stylus can scroll without pressing anything. Do not center wide
  content into it.
- **Fit the screen.** At 1024x600 the controls that finish a task (Submit, Next, Save) stay on
  screen without scrolling.
- **Never color alone.** Every status carries a word and a shape as well as its color. Text meets
  WCAG AA contrast (4.5:1).
- **Show and hide with `hidden`.** Start hidden with the `hidden` attribute and toggle
  `el.hidden`, not `style.display`.
- **Keep typing to a minimum.** The Windows on-screen keyboard is unusable on these screens. Prefer
  choices and steppers over free text. The redesign adds an on-page keypad.
- **Before and after pictures.** When developing a page, adding a feature to one or debugging
  one, take a picture of it before the change and after it, and save both in
  `~/development-snapshots/`. Log each pair in `~/development-snapshots/LOG.md`: the commit id,
  the date and time (UTC), what the picture shows and what was changed (Aaron, 2026-10-13).
  Picture the whole page, and the changed part closer where it helps.
  `~/development-snapshots/tools/snapshot.py PATH OUT.png [--js "goToStep(3)"]` takes a
  whole-page picture from a local copy of the page; its docstring says what it can not show.
- **Do not restyle the site.** Colors, navigation, `base.html` and the shared rules in `style.css`
  change only under the redesign issues. A feature page uses the classes that exist.

## Facts not to rediscover

- **Current 30 mm AprilTags measure 30.0 ± 0.1 mm.** NEIKO callipers, on or before 2026-09-21: 30 mm tag
  X 30.10 / 30.11 / 29.96, Y 30.04 / 29.96 / 29.94 (mean 30.018); 50 mm tag mean 50.02; 180 mm
  sheet scale bars 179.93 and 180.03 (each a mean of 3 readings). Source and method:
  `docs/metrology-log.md` section 3. Callipers are not trusted beyond 0.1 mm. 36h11 family. The 29.3106 mm
  figure in older docs and code belongs to the previous rig's printed tags and does not apply.
- **The rig has been physically rebuilt.** Every geometry value from the old calibration is dead:
  camera distance, table tilt, lens position, intrinsics. Re-measure them. Tray height survives.
  Tag size is a property of each printed sheet: measure every new print with callipers.
- **`/home/pi/old/npec_OLD/npec-camera` is frozen.** Read it, do not modify, move or delete it.
  Its `metrology/` package is a clean leaf with no inbound dependencies from the camera or web
  layers. Its `sweep.py` / `characterisation.py` (~2650 lines) is the same failure under another
  name and is entangled with the web routes.
- **Old code is reference only.** Read it to learn what worked on this hardware, then write fresh.
- **Segmentation is the green threshold only.** `segmentation.py` (#74) holds the `Segmenter`
  interface, round 1's green threshold (`experiments/round1-benchy/`) and a Hailo stub. No area
  is computed from masks yet (#75). FastSAM on the Hailo-8 was tried for tray splitting and
  dropped (`experiments/round1-trays/`); Hailo ships no plant model and SAM2 is not supported on
  the Hailo-8 (checked 2026-10-23).
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
- **Height above the tray top changes area by about 0.145% per mm** for small heights
  (model slope from a tape-measured best estimate of 1482 mm camera height; one test: a 75 mm taller tray read 11.2% to
  12.0% large, predicted 11.8%, about 0.157% per mm on average over that step). Validation bands cover flat objects at tray-top height
  only; plant height and segmentation add to them (PLAN.md, *Per-slot area uncertainty*).
- **Rig timestamps (capture names, session IDs) are UTC; the chamber keeps Dutch local time:**
  UTC+2 in summer time, UTC+1 from the last Sunday of October (25 October 2026) to the last
  Sunday of March. Convert before matching them against anything a person reports.
- **Tray tags.** The 15 October test trays use IDs 0 to 17 (1 to 12 original, 0 and 13 to 17 added
  for the paired 20 mm test). Round 2 tray tags are about 40 mm, lying roughly centred in cell A1,
  in any rotation (Aaron, 2026-10-19), replacing the 20 mm edge tag of 2026-10-15: edge tags could
  not be placed the same way on every tray. Each tray is placed from its tag and the slot grid
  (metrology log 15.5h to 15.5k, #220); cell A1 holds no plant. Tray
  tags (IDs 0 to 299) are read with finer bit sampling, calibration and corner tags with the frozen
  settings (`tags._tray_detector_parameters`, metrology log 15.3e, #192).
- **Corner tags (450 to 499) lie inside the table edge on development since 2026-11-03 09:22 UTC;
  production keeps them on the outer-edge mounts until Round 2 ends** (#349, metrology log 31).
  Keep trays off them; no distance is set, a calibration names any hidden tag (31.3). Moving a tag needs a new
  calibration: the old corner baseline means nothing after it. A calibration whose photo misses
  one is saved and names it (#397).
- **Trays touch.** Researchers will not reliably leave gaps, so tray splitting must work with trays
  touching (`reference/trays.md`).

## Where things live

| Path | What |
|---|---|
| `PLAN.md` | Full plan. Read the relevant milestone only |
| `TODO.md` | Frozen record, 2026-10-08. Done items and the decisions in them. Open work is in GitHub issues (see *Parallel work*). Do not add items |
| `CONTRIBUTING.md` | Branches, PRs, review and merging |
| `reference/old-calibration/` | Rescued measured values from the previous rig |
| `reference/trays.md` | Growth trays: measured size, the 4 x 5, 2 x 2 and 1 x 1 configurations, where the tags sit, the 12-tray layout rules, what is not yet known |
| `reference/arducam-central-error-2026-10.md` | The central-error investigation: evidence, what was ruled out, how the error is managed |
| `docs/measurement-trust.md` | Why the rig's area measurements can be trusted, and the steps taken to build that trust. The case, for reports and a possible paper |
| `docs/metrology-log.md` | Log of every measurement, test method and result, with sources: the evidence behind `measurement-trust.md`. See *Write up every measurement* |
| `docs/operator-guide.md` | For the scientists running experiments: focus, lock, calibrate, validate, and what the uncertainty column means |
| `/var/lib/npec-rig/` | On each rig, not the controller. Runtime data: `rig/` photos (every still, written by `captures.take_photo`), masks, `rig.db`. The old `captures/` and `calibration/frames/` folders are no longer read |
| `docs/database.md` | Every table in `rig.db`, its columns, and the rule that all times are UTC |
| `/var/lib/npec-rig/derived/` | Derived images (validation maps, problem frames; later thumbnails), made once by `images.py`, disposable. Every large image goes through `images.py` (PLAN.md, *Images*) |
| `/etc/npec-rig/config.yaml` | Per-rig configuration. Planned (PLAN.md's Technical decisions table), not yet implemented — current settings live in env vars and SQLite only |

## Agent skills

### Issue tracker

GitHub Issues in `txoof/npec-camera-rig`, under the rules in *Parallel work* above. See
`docs/agents/issue-tracker.md`.

### Triage labels

The five default labels, unchanged. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` at the root and `docs/adr/`, made only when needed. See
`docs/agents/domain.md`.

## Write up every measurement

Every metrology finding and every validation result is written up in `docs/metrology-log.md`, in the
same change that produces it: what was measured, how, with what instrument, how many times, the
result with its spread, the date, where the raw data is, and what it does and does not cover.
Detailed investigations go in `reference/` and are linked from it. Images that show a result
go in `docs/figures/<section>/`, linked from the section with a caption, in the same change
(`docs/figures/README.md`, Aaron, 2026-10-23); `~/scratch` is not kept. A number that is a decision or
a placeholder, not a measurement, says so. Written for a scientist without a metrology
background, formal enough to cite in a paper about the rig (Aaron, 2026-10-05).

Every result is labelled a *development check*, a *validation* or a *reference comparison*
(`GLOSSARY.md`).

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
