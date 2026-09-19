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
| Believing tags are the 30 mm printed on the box (they measure 29.3106 mm) | ~4.7% |
| Tag corner-finding precision | ~0.15% |
| Segmentation edge ambiguity | several % |

The largest geometric error in the system was fixed with callipers. Work on the biggest error
source, not the most interesting one.

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

## Facts not to rediscover

- **AprilTags measure 29.3106 mm**, not the nominal 30 mm. Measured with callipers. 36h11 family.
- **The rig has been physically rebuilt.** Every geometry value from the old calibration is dead:
  camera distance, table tilt, lens position, intrinsics. Re-measure them. Tag size and tray height
  survive, because they are properties of objects and not of the setup.
- **`/home/pi/old/npec_OLD/npec-camera` is frozen.** Read it, do not modify, move or delete it.
  Its `metrology/` package is a clean leaf with no inbound dependencies from the camera or web
  layers. Its `sweep.py` / `characterisation.py` (~2650 lines) is the same failure under another
  name and is entangled with the web routes.
- **Old code is reference only.** Read it to learn what worked on this hardware, then write fresh.
- **No Hailo code, no `.hef`, no segmentation exists anywhere.** M5 starts from nothing, behind a
  `Segmenter` interface with a classical excess-green fallback.
- **362 MB of bench frames** sit at `/home/pi/old/npec_OLD/npec-camera/tests/data/`. From the previous rig,
  so the geometry no longer matches. Available if needed, not copied in.

## Where things live

| Path | What |
|---|---|
| `PLAN.md` | Full plan. Read the relevant milestone only |
| `TODO.md` | Actionable items, linked to plan milestones |
| `reference/old-calibration/` | Rescued measured values from the previous rig |
| `/var/lib/npec-rig/` | Runtime data: captures, masks, `rig.db` |
| `/etc/npec-rig/config.yaml` | Per-rig configuration. Planned (PLAN.md's Technical decisions table), not yet implemented — current settings live in env vars and SQLite only |

## Definition of done

A slice is done when you can **see it working in a browser**, not when its tests pass. If a slice
cannot be demonstrated, it is not a slice — split it differently.

Milestones are done when the physical acceptance tests in `PLAN.md` pass, run in the chamber with a
tape measure and printed targets.
