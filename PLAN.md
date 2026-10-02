# NPEC Camera Rig — Plant Growth Monitoring Application

## Context

An environmental chamber grows plants on a table holding **12 growth trays**. Trays are removed for
measurement, randomised, and returned — at any position, at any rotation 0–359°. Trays come in
three standardised heights, **but a single experiment uses one height throughout**. Experimenters
need to know how much leaf area each tray has grown over time, where each tray spent its time, and
— critically — **how much to trust those numbers**.

A Raspberry Pi 5 with a single top-down **Arducam 64MP** camera and a **Hailo AI accelerator** is
mounted in the chamber. This will be **deployed to ~15 rigs**, so every procedure must be
repeatable by someone who didn't build it.

**Two physical constraints shape everything:**

1. **Nothing on the table surface survives an experiment** — soil, water, foliage. The only
   permanent fiducials are four AprilTags on the table's outer edge (NE/NW/SE/SW, reserved 36h11
   IDs, always in frame) and a **fixed 30 mm tag on each tray**, flat and within 1.5 mm of tray-top
   height.
2. **Experimenter participation is a design requirement.** Add too many steps and the rig won't get
   used. Per-experiment manual work must be near zero, and the app must *ask* for a step at the
   moment it's needed rather than rely on someone remembering a procedure.

Three previous attempts collapsed into camera metrology and never produced a working application.
This plan is built to prevent that. Deadline: **mid-December 2026** (~12 weeks from 2026-09-19).

---

## The architecture in one page

### The measurement plane is the focus slab, not the table

Since one experiment uses one tray height, and the experimenter focuses on the tray-top region,
**that slab is where we measure**. We calibrate there. There is no table-plane-to-plant-plane
conversion, no camera height term, no height-bias caveat — we simply start in the right plane.

The in-focus slab defines it physically: **if it's sharp, it's in the plane.** That's a definition
an experimenter can see rather than compute.

### Calibration runs at two speeds

| | **Paper sheets** | **Tray tags** |
|---|---|---|
| **When** | Once at chamber setup; again only when the app says so | Every capture, automatically |
| **What it establishes** | Lens distortion, full-frame geometry, corner coverage | Scale + perspective |
| **Coverage** | Dense, reaches all four frame corners | 12 points, accumulating as trays roam |
| **Experimenter effort** | ~5 min, rare | **Zero** |

Paper sheets of AprilTags laid on top of every tray — sheets are reusable, so there's no reason
not to cover all 12, and it reaches all four frame corners without having to pick a pattern that
does. The 12 fixed tray tags then carry scale forever after,
**including across refocusing for a different tray height**, which is why changing tray height
costs the experimenter nothing but the focus step.

**Why 30 mm tray tags are sufficient** — and why not to "improve" them:

Numbers below are derived from the **previous rig's measured calibration** (camera 1526 mm from the
table, ~4.4 px/mm at 64MP). **The rig has since been rebuilt, so re-derive the scale at M2** — but
the *ratios* between these error sources are what matter here, and those hold:

| Error source | Magnitude |
|---|---|
| 30 mm tag, scale precision (~130 px across at 4.4 px/mm) | **~0.15%** |
| 1.5 mm tag height offset from tray top, at 1526 mm | **~0.1%** in area |
| **Using nominal 30 mm when the old rig's tags actually measured 29.31 mm** | **~4.7%** in area |
| **Deciding where a leaf edge stops in the mask** | **several %** |

Two things fall out of this table. First, the tags are ~20× more precise than the thing they feed —
enlarging them optimises a term that is already invisible. *That is the metrology trap in
miniature: improving what isn't the bottleneck.* Second, the **largest geometric error in the whole
system is simply believing a tag is the size printed on the box.** Measure the tags. That one act
is worth more than every other geometric refinement combined.

### Trust is maintained by a tripwire

The four corner tags are in general position, so they define a planar homography. Compare today's
against the one recorded at calibration:

| Observation | Means |
|---|---|
| All four shifted together | Rig translated |
| Corner line angles changed | Camera rolled |
| Sizes changed uniformly | Camera height changed |
| Quadrilateral shape changed | Camera tilted / pitched |
| A tag missing | Something is very wrong — refuse |

They sit on the table edge, a different plane from the measurement slab — which doesn't matter,
because they are a **tripwire, not a ruler**. They answer only "did the rig move?"

Output: a plain-language delta *and* a **binary trust verdict stamped on every reading**, so
untrustworthy data stays identifiable forever, not just alerted on once.

**We do not auto-correct a detected bump.** We flag it and ask for recalibration. Silently
compensating hides from the experimenter that their rig was knocked — the opposite of what a
measuring instrument should do.

> **Certainty is measured, never derived.** If a number can't be demonstrated with a ruler, a
> printed target, or a repeated observation, it doesn't ship.

---

## Deferred, with evidence gates

Not banned on technical merit — **deferred until a measurement says they're needed.** Each has a
concrete trigger. This replaces a blanket prohibition, which was dishonest: most of these are
sound techniques that are simply not the current bottleneck.

| Deferred | Unbanned when |
|---|---|
| **Intrinsic camera calibration** (`calibrateCamera`, distortion coefficients) | The honesty plot shows **structured** residuals — systematically worse toward frame corners — rather than random scatter. Random residuals mean distortion isn't the problem and calibration buys nothing. |
| **Out-of-plane parallax correction** | A measured depth source exists. With one camera there is no per-point height, and an invented height produces a confident wrong number. (Perspective modelling *within* the plane is **not** deferred — the homography is exactly that, and we use it throughout.) |
| **True orthophoto / photogrammetry** | A second viewpoint exists. Orthorectification needs a surface model, which needs multiple views. Same decision as the second camera, not a separate one. |
| **Second camera / height data** | M1–M6 land with time to spare, *and* the measured in-plane accuracy proves insufficient. |
| **Per-plant cell tracking** | Could-Have; only after the Must-Haves are verified. |
| **YOLO tray identification** | Tag-based identity proves insufficient in practice — measured by how often tags go unreadable. |
| **Second AprilTag family for corner/reference tags** (e.g. `41h12`, separate from trays/sheets on `36h11`) | Single-family ID range collisions — misdetection, or an experimenter mounting the wrong physically-valid sheet — prove to be a real problem in practice. Reserved ID ranges within one family are the current approach; a second family would add a structural (and visually distinct) namespace on top, at the cost of a second detector pass per frame. |

**Hard exclusions for v1** (scope, not merit): no ML training or Hailo model compilation (we
integrate a supplied `.hef`); no RAW/DNG or colour calibration; no cloud sync, remote hosting or
user accounts (LAN-only, trusted network); no species/health/disease classification.

### On edge accuracy specifically

Measurements near the frame edges *are* worse — steeper viewing angle and more distortion. Two
responses, both cheap:

1. **Frame to avoid it.** You have 64MP and need maybe 12. If the table doesn't reach the sensor's
   extreme corners, and you crop the rest, you trade unneeded resolution for better geometry. No
   maths — just aiming the camera slightly differently at install. The install report flags framing
   that's too tight.
2. **Report it honestly.** The scale field already yields *spatially varying* uncertainty: corner
   tags disagree with their neighbours more. Per-tray confidence that's worse for edge trays isn't
   extra work — it falls out of the design.

---

## Technical decisions (made, not up for survey)

| Area | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | picamera2 and Hailo runtime are Python-first |
| Env | venv with `--system-site-packages` | picamera2 is apt-only, cannot pip-install |
| Web | FastAPI + uvicorn, single process | Only one process may hold the camera |
| Frontend | HTML + HTMX + vanilla JS + `<canvas>` overlays | **No npm, no build step on a Pi** |
| Storage | SQLite (WAL) + JPEG on disk | Single-file, no server, fine for 12 trays |
| Paths | `/var/lib/npec-rig/`, config `/etc/npec-rig/config.yaml` | User-specified |
| Process | systemd, restart-on-failure | Must survive reboot mid-experiment |
| Repo | `git init` in `/home/pi/npec_camera_rig` (empty today) | — |

**Multi-rig deployment is first-class:** per-rig config; standard reserved tag-ID ranges (corner /
tray / calibration sheets never overlap); calibration output is a **versioned, exportable artifact**
so a rig's state can be archived, compared or restored.

---

## Data model and export

One SQLite file at `/var/lib/npec-rig/rig.db` (WAL mode). Images live on disk; the DB holds
everything else.

| Table | One row per | Key columns |
|---|---|---|
| `experiment` | experiment run | name, started_at, ended_at, tray_height_mm, notes |
| `calibration` | calibration event | created_at, lens_position, scale_field, uncertainty_field, corner_baseline, coverage_report, method (`sheets`/`tray_tags`) |
| `tray` | physical tray | tag_id, label, tray_type, height_mm |
| `validation` | validation session (built in M2, stored as JSON today) | calibration_id, started_at, ended_at, per-slot 95% band and median, consistent or not |
| `capture` | photograph | experiment_id, calibration_id, **validation_id**, timestamp, file_path, mask_dir, exposure, gain, awb, lens_position, **focus_locked**, sharpness, **trust_verdict**, drift_delta |
| `detection` | tray seen in a capture | capture_id, tray_id, tag_id, centroid_x_mm, centroid_y_mm, rotation_deg, **region**, scale_residual, identity_confidence |
| `measurement` | tray's canopy in a capture | capture_id, tray_id, **slot**, **area_mm2**, **area_uncertainty_95_pct** (the slot's validation band, see below), mask_area_px, confidence, edge_fraction, segmenter_name, segmenter_version, flags |
| `alert` | alert raised | timestamp, kind, severity, message, capture_id, acknowledged_at |

Dwell time isn't stored — it's a `GROUP BY` over `detection` joined to `capture` timestamps, so it
can never drift out of sync with the readings it summarises.

**Four rules that make the data survivable:**

1. **Every derived row carries its provenance** — which calibration, which segmenter version, what
   trust verdict. An experimenter can re-filter a finished experiment without re-deriving anything.
2. **Nothing is ever deleted, only flagged.** Untrusted readings stay in the table with a `FAIL`
   verdict. Removing them would hide that the rig was knocked.
3. **Store the segmentation masks** (PNG alongside each capture — they compress to almost nothing).
   Area is a function of mask × scale field, so if a calibration later turns out to be wrong, every
   historical area can be **recomputed without re-running inference**. There's a **Reprocess**
   action in the UI for exactly this. This is the difference between a bad calibration costing an
   afternoon and costing the experiment.
4. **Append-only readings**, so a crash mid-write can't corrupt history.

### CSV export

An **Export** page, delivered in M3 and extended as tables appear. All exports are filtered by
experiment and date range.

| File | Contents |
|---|---|
| `measurements.csv` | **The main one.** One row per tray per capture: timestamp, tray label, region (slot), `area_mm2`, `area_uncertainty_95_pct`, calibration, lens position, validation, confidence, trust verdict, segmenter version, flags |
| `dwell.csv` | Tray × region × minutes, for the whole experiment |
| `captures.csv` | Capture log with camera settings, sharpness and trust verdict |
| `calibration.json` | The full calibration artifact, for archiving or transferring between rigs |

### Per-slot area uncertainty (from validation)

Decided 2026-10-02; the evidence is in `reference/arducam-central-error-2026-10.md` (section 10 has
the full explanation and an example row). Every area measurement carries the 95% band its slot
had in the validation of the calibration and focus lock it was taken under.

- **Per slot, not per tray.** The band belongs to the table position. A tray gets the band of the
  slot it sat on when photographed. A refocus or recalibration means a new validation and new bands.
- **A 95% band, not a standard deviation.** 95% of the reference targets on that slot read within
  that percentage of their true area. Column names and exports say "95%".
- **Flat objects at tray-top height only.** It is the camera and calibration part of the
  uncertainty. Plant height (about 0.145% of area per mm above the tray top) and segmentation add
  to it, so it is a lower limit for a plant's area, and exports say what it covers.
- **Recorded, not corrected.** Each band mixes a steady per-slot offset (measured, so correcting it
  would be allowed) and scatter (not correctable). For now the band is recorded and no offset is
  subtracted. If that changes, corrected values and their narrower bands are stored as such.
- **The focus position is the experimenter's input.** The central slots carry wider bands with this
  camera, by an amount that depends on the focus position chosen for the setup. Validation measures
  it; nothing in the rig chooses or tunes the position.

### A sizing warning worth knowing now

The database is trivial — 30 days at 60 captures/hour is ~43k captures and ~520k measurement rows,
which SQLite does not notice. **The images are the problem.** At 4624×3472 JPEG (~4 MB), that same
month is **~170 GB**; at 10/hour it's ~29 GB. So: capture rate, retention policy and an external
SSD are a single connected decision, and the app must show disk headroom prominently rather than
discovering the problem when the card fills mid-experiment.

---

### Test discipline (M1 infrastructure, not a later milestone)

A named failure of the previous attempt: **expensive tests ran on every single change, including
documentation edits.** The fix is mostly *defaults*, not willpower — make the cheap thing automatic
and the expensive thing opt-in, so even a careless invocation costs nothing.

```
pytest                    # ONLY `unit` — no hardware, HARD BUDGET <10s
pytest -m hardware        # needs the camera
pytest -m hailo           # needs the accelerator
pytest -m integration     # full pipeline against fixture images
pytest -m slow            # soak / long-running
```

`pyproject.toml` sets `addopts = -m unit`. **The expensive tiers are never reachable by accident** —
a bare `pytest`, a stray hook, or an over-eager agent all land in the cheap tier by construction.
Hardware tests **skip, not fail**, when hardware is absent.

**What runs when — the rule, written down so it isn't re-litigated:**

| Change | Run |
|---|---|
| Docs, markdown, comments | **Nothing** |
| HTML templates, CSS, copy | **Nothing** — look at it in a browser |
| One logic module | That module's unit tests only |
| Logic across modules | `pytest` (unit tier, <10 s) |
| Camera / capture code | Unit tier, then **one** manual check against the real camera |
| Before a commit | `pytest` (unit tier) |
| Milestone sign-off | Full suite **plus** the physical acceptance tests |

**Budget enforcement:** the unit tier fails if it exceeds its time budget. A slow test in the fast
tier gets caught the day it lands, not six weeks later when nobody runs the suite any more.

**No pre-commit hook that runs tests.** Hooks are how "run the fast tier before committing" quietly
becomes "run everything on every save." Formatting and linting hooks are fine; test hooks are not.

**A synthetic camera backend is M1 infrastructure, not a nicety.** The old rig had one, and it's
why almost its entire suite ran with no hardware attached. Without it, "fast unit tier" is
impossible and every test becomes a hardware test.

**Concrete evidence this is the right fix:** in the old suite, the heavyweight tier (marked
`benchphotos`, decoding 64MP frames) took **223 seconds of a 303-second run** — 74% of the time in
5 of 22 test files. The markers existed; the *default* didn't. That's precisely the gap this
section closes.

Every module ships fixture images — we have 33 real Arducam frames to draw on — so the unit tier
stays real rather than mock-heavy.

---

## Milestones

Each ends with **acceptance tests you run in the chamber**. Nothing is done on a passing unit test
alone.

### M0 — Probe the hardware (30 min, before any code)

The Arducam 64MP on this OS build (Trixie, kernel 6.18) is the riskiest unknown. **We do not plan
against a datasheet.** You run:

```bash
rpicam-hello --list-cameras
python3 -c "from picamera2 import Picamera2; p=Picamera2(); \
  print(p.sensor_modes); print(p.camera_controls)"
hailortcli fw-control identify
```

`camera_controls` is the discriminator — **M1's control list is generated from it, not hardcoded.**
We specifically want **manual** focus (`AfMode: Manual` + `LensPosition`); continuous AF is actively
harmful here. The old rig recorded a working lens position of **6.3 dioptres** — a useful starting
point, not a substitute for the probe.

**Also in M0: rescue the assets from the old repo** (see *Salvaged code*). The calibration JSONs in
`/var/lib/npec-camera/` and the 362 MB of bench frames are outside version control and one `rm`
away from gone. Copy them somewhere safe before any other work starts.

**Fallback decided in advance so M0 can't become a driver hunt:** if `LensPosition` is absent, focus
is set on the physical ring and the console shows the sharpness trace as a **read-only focus aid**.
We do not go hunting for out-of-tree Arducam drivers.

---

### M1 — Camera console (~1.5 weeks) · *your stated first demo*

- `CameraManager` singleton wrapping picamera2 — the only code touching the camera.
- **MJPEG live preview** from the low-res stream.
- **Controls built from probed `camera_controls`:** exposure, analogue gain, AWB, AE on/off (auto
  preferred), and manual lens position.
- **Guided focus (the one real per-experiment step — make it 30 seconds, not a chore):** live
  sharpness score (Laplacian variance) on a selectable ROI, shown as a number and a trace,
  alongside a **magnified 1:1 ROI crop stream** — the old rig built exactly this and it's the right
  idea. Turn the ring or move the slider until it peaks; app says **locked** and **records the lens
  position**. Focus must not drift mid-experiment — the health check watches it.
- **Synthetic camera backend**, so the suite and the UI both run with no hardware attached. This is
  load-bearing for the fast test tier, not a nicety.
- **Capture** → full-res JPEG + sidecar JSON (all control values, timestamp, sensor mode) into
  `/var/lib/npec-rig/captures/YYYY-MM-DD/`.
- **Settings persistence** — the old UI's known gap. Camera settings live in the database and
  survive restart; the console loads the last-used values rather than defaults.
- Recent-captures gallery; systemd unit; logging; pytest marker infrastructure.
- **`CLAUDE.md` encoding the working rules** so they bind future sessions, not just this one: the
  test-tier table above, the anti-metrology evidence gates, and "questions are questions — don't
  run tests or shell commands to answer one."

**You verify:** browser on your laptop → live feed ≥5 fps → change exposure, see it → sweep focus,
watch the score peak → capture → file + sidecar on disk → reboot the Pi, service returns unaided →
`pytest` green in under 10 s.

---

### M2 — Calibration + rig health check (~3 weeks) · *the heart of the project*

Ahead of timelapse deliberately: scale feeds every area number, so capturing first just piles up
images we'd reprocess.

**Detector: start with `cv2.aruco`, `DICT_APRILTAG_36h11`, `CORNER_REFINE_SUBPIX`.** The previous
rig already established this works on your hardware, and that **tuned `DetectorParameters` beat
stock — 20 tags detected versus 12** on a hard frame. That evidence stands; don't re-run the
bake-off from scratch. Only if measured corner jitter proves inadequate do we evaluate
`pupil-apriltags`, and then on the bench frames we already have.

**A. Setup calibration (rare — chamber initiation, or when the app asks)**
- Paper AprilTag sheets laid on every tray at the experiment's tray height, reaching all four
  frame corners.
- Produces the **scale field** (mm/px across the measurement plane) and the **uncertainty field**
  (local scatter among neighbouring tags), plus roll, tilt and framing coverage.
- **Coverage sufficiency is measured, not guessed — a holdout test.** Build the field from half the
  tags, predict the other half, measure the error. The install report then says *"coverage
  sufficient"* or *"add coverage in the top-left."* ~15 lines of code, and it turns "how many tags
  do we need?" into a number.
- Records the four corner tags' positions, sizes and homography as the **health baseline**, and the
  locked lens position.
- **Install report** — blunt and actionable, not statistical:
  > "Camera rolled 1.8° clockwise." · "Table's left edge is out of frame." · "Framing is too tight —
  > the table reaches the sensor corners where distortion is worst." · "Scale varies 6% across the
  > table, worst top-right." · "Coverage insufficient: add a sheet at back-left."
- Calibration is **frozen, versioned, exportable**. Sheets come off.

**B. Per-capture, automatic (zero experimenter effort)**
- **The 12 tray tags re-fit scale *on top of* the frozen field — they do not rebuild it.** The
  frozen field supplies the spatial **shape** (how scale varies across the frame, including the
  distortion at the edges that only the paper sheets can see); the tray tags supply the current
  **scale factor** and a mild perspective correction. This matters: all 12 trays sit in the table's
  interior, where distortion is smallest, so a fresh 12-point fit each capture would silently throw
  away the edge information the paper calibration exists to provide.
- This absorbs refocusing between experiments at no operator cost — **with the residual measured at
  M2** (see below). Refocus changes focal length, which shifts distortion *magnitude*, not just
  scale, so the frozen shape is strictly valid only at the lens position it was captured at. The
  excursion between three tray heights is probably minor. "Probably" is why we measure it.
- The four corner tags run the tripwire: compare to baseline homography → **plain-language delta**
  ("rolled 1.2°, near edge 3% closer") plus a **trust verdict** (`OK`/`DRIFT`/`FAIL`) written to the
  DB with every reading. Missing tag → `FAIL`, loud. Conservative thresholds; **default to refusing,
  not guessing**.
- Focus-drift check from the sharpness score against the locked value.
- **The app tells the experimenter when recalibration is needed.** They never have to remember.

**You verify:**
- Tape-measure two tags → app agrees within 2%.
- Roll the camera ~5° → reported as ~5°; knock it hard → verdict flips to `FAIL`.
- Known target at 6 positions → plot **claimed uncertainty vs actual error**. Is the indicator
  *honest*? Are the residuals random (fine) or structured toward the corners (→ the intrinsics
  evidence gate just opened)?
- **The two-baseline test — do this first; it's the one that says whether M2 works.** The
  6-position plot can pass while the certainty map is meaningless, because every position is
  measured against the *same* calibration; a systematically wrong one yields low scatter, high
  claimed confidence, and a plot that still looks fine. So run the **sheet calibration twice
  independently** (power-cycle and re-focus between), build a field from each, and diff them. **That
  disagreement is the floor on achievable certainty.** If two calibrations of the same static scene
  disagree by more than the uncertainty we claim, the claimed number is fiction. Twenty minutes, and
  the single most informative test in the project.
- **The two-height test — this one proves the architecture's central claim.** Run the sheet
  calibration at two different tray heights (refocusing between) and diff the resulting fields. If
  the *shapes* match within your uncertainty, the two-speed scheme is validated: one rare paper
  calibration really does cover every experiment, and we can stop thinking about it. If they don't
  match, paper calibration becomes **per-tray-height** — still rare, still acceptable, but we need
  to know that before promising the operator otherwise. Ten minutes.

---

### M3 — Scheduled capture, storage, timelapse (~1.5 weeks)

- Interval scheduler, 1–6 min configurable (your 10–60/hour), trust verdict stamped per capture.
- Survives reboot; logs and recovers from failures; never silently stops.
- **Full schema created here** (see *Data model and export*), plus experiment create/start/stop in
  the UI — every capture must belong to an experiment and a calibration from the outset, because
  retro-fitting provenance onto existing rows is miserable. Each capture also records the locked
  lens position and the validation it falls under; a capture taken with focus unlocked, or at a
  lens position other than the calibration's, is marked "not covered by a validation" (a flag, not
  a block). See *Per-slot area uncertainty*.
- **Export page with CSV download**, covering whatever tables exist at each stage.
- Disk monitoring + retention policy, with **headroom shown prominently** — at 60/hour a month is
  ~170 GB, and the card must not fill mid-experiment.
- **Timelapse** with scrub, play and mp4 export.

**You verify:** unattended 24 h at exactly the expected image count · reboot mid-run, it resumes ·
scrub the timelapse · download `captures.csv` and open it in Excel · disk headroom readout matches
`df`.

---

### M4 — Tray identity, pose, regions, dwell time (~2 weeks)

- Tray 30 mm tag → **identity, centroid, rotation 0–359°**, and a scale sample in the measurement
  plane. No height arithmetic — the tag is already in the plane we measure.
- **Regions: 2 rows × 6 = 12**, defined **in measurement-plane coordinates** (from the corner tags),
  not image pixels, so a bumped camera can't silently shift every boundary. Rendered as an overlay.
- Each reading writes tray ID, centroid, rotation, region, trust verdict, timestamp to SQLite →
  **dwell time per region per tray** is a `GROUP BY`.
- **Dirty-tag degradation (it will happen):** unreadable tray tag → still measure the tray, flag
  identity `unknown`, carry last-known ID forward with a confidence penalty, and drop that tag from
  the scale solve. Frequency of this is the measurement that opens the YOLO evidence gate.

**You verify:** 12 trays at random positions and rotations → all 12 identified, centroids within
tape-measure tolerance, rotations correct · remove one, return it rotated 180° in a new region →
dwell table reflects the move · smear a tag with soil → degrades gracefully, doesn't crash or lie.

---

### M5 — Canopy area (~2 weeks)

- **`Segmenter` interface defined first**, two implementations behind it:
  1. **`ExGSegmenter`** — classical excess-green threshold. No ML, runs anywhere, ships now,
     testable today, and becomes the permanent baseline the real model must beat.
  2. **`HailoSegmenter`** — stub with an identical signature, filled in when the `.hef` arrives.
     Swapping it must require zero changes elsewhere.
- Mask → pixel area → mm² via the **per-pixel scale field**, not one global number.
- Per-tray attribution from M4.
- **Confidence per measurement**, from measured quantities only: local uncertainty from the field at
  that position (naturally worse at frame edges), the trust verdict, agreement among nearby tray
  tags, and the mask fraction touching a frame edge or tray boundary.
- **Expect segmentation edge ambiguity to dominate** — several percent, against ~0.1% from the
  tags. Quantify it, and let that ratio govern where effort goes next.
- **Each measurement carries its slot's validation band** (`area_uncertainty_95_pct`), the measured
  camera and calibration part for a flat object at tray-top height. Height and segmentation are
  stated on top of it, never folded into it silently. See *Per-slot area uncertainty*.

- Writes `measurement` rows and **stores each mask to disk**, so areas can be recomputed against a
  corrected calibration later without re-running inference.

**You verify:** printed known-area target at 6 positions → report the error *and* whether the stated
confidence band actually contains the truth · when the real model lands, run the identical suite
against the ExG baseline · download `measurements.csv` and plot a growth curve in Excel · change
the calibration, hit **Reprocess**, confirm historical areas update without re-inference.

---

### M6 — Alerts and hardening (~1.5 weeks) · *Should-Have*

- Alerts on: implausible area jumps, `DRIFT`/`FAIL` verdicts, tag detection dropping off, focus
  drift, scheduler stalls.
- Daily/weekly digest (Could-Have) if time allows.
- Soak test, docs, **deployment runbook for rigs 2–15**.

**Remaining ~1 week: buffer.** It will be used.

---

## Salvaged code

`/home/pi/npec_camera_rig` is **empty**. The prior attempt lives at:

- **`/home/pi/old/npec_OLD/npec-camera`**

**User's own assessment, which governs:** *"USE THE CODE AND DOCS WITH CAUTION. It devolves into the
minutia of metrology. The web interface is OK, but not adequate and lacks a method for saving
settings. The preview and capture are acceptable, but should NOT be taken as finished."*

**Decision: code is REFERENCE ONLY.** We read it to learn what worked on this hardware, then write
fresh. No file is imported. Assets and measured values *are* harvested.

### The old project is FROZEN

**`/home/pi/old/npec_OLD/npec-camera` is not to be modified, moved or deleted.** Read it, don't
touch it.

**The rig has since been physically rebuilt into an entirely new setup.** This matters more than it
first appears — it splits the rescued values into two groups:

| Still valid (properties of objects) | **Stale (properties of the old geometry)** |
|---|---|
| AprilTag size: a property of each print, so measure every new print with callipers (current sheets **30.0 mm**; the old rig's 29.3106 mm does not apply) | Camera distance 1526.4 mm |
| Tray height **99.89 mm** stated | Table tilt 2.76° |
| Sensor 9152 × 6944, Arducam behaviour notes | Lens position 6.3 dioptres |
| | Intrinsics and distortion coefficients |

Only the left column becomes a **pre-filled config default that the app makes you confirm during
calibration**. Everything in the right column describes a rig that no longer exists and must be
re-measured. Carrying those forward would be exactly the silently-inherited stale value the
confirm-at-setup rule exists to prevent.

The calibration records themselves are already rescued to `reference/old-calibration/` and pushed;
`/var/lib/npec-camera` has been removed.

### Bench frames — available, not rescued

**`/home/pi/old/npec_OLD/npec-camera/tests/data/bench-2026-09-15/`** holds 33 real Arducam 64MP
frames (362 MB; 28 board, 5 chamber table) with known-good outputs recorded in its `README.md`.

**These are from the previous rig iteration and are deliberately NOT being copied into this
project.** They are available at that path if a specific need arises — detector tuning, a
regression fixture, sanity-checking a decoder — but the geometry in them no longer matches the
chamber. New fixture images get captured from the current rig during M1.

> **The single most valuable number in that pile: the old rig's tags measured 29.31 mm, not the
> nominal 30 mm.** That is a **2.3% linear, ~4.7% area** systematic error, larger than every other
> geometric term in this plan combined. It is also the entire argument for "measured, never
> nominal," already proven on your own hardware. The current sheets measure 30.0 mm: the number
> does not carry over, the habit of measuring every print does.

### What the survey found

**The metrology package is a clean leaf** — `metrology/` (2,453 lines) imports only numpy/cv2/scipy
and itself. Inbound references come *only* from `cli.py` and tests. **Nothing in `web/`,
`service.py`, `pipeline.py`, `cameras/` or `stills.py` touches it.** The rot never spread, which is
why the camera core is worth reading.

**But there is a second metrology zone under another name, and it *is* entangled.**
`sweep.py` + `characterisation.py` + `noise.py` + `sweep_job.py` (~2,650 lines of noise/SNR/
hot-pixel characterisation) are imported by `web/routes/pages.py`, `web/deps.py` and `web/app.py`.
Recognise this shape if it starts growing back — it is the same failure wearing a different label.

**No Hailo code, no `.hef`, no segmentation of any kind exists.** The stub-first approach in M5
isn't a compromise; it's the only option.

### Reference-only reading list, ranked by what it saves

| Read for | Where | Why it matters |
|---|---|---|
| **Exposure control gotcha** | `cameras/picamera2_backend.py` → `exposure_controls()` | Raises `FrameDurationLimits` alongside `ExposureTime` and toggles the mode flags. Fixes silently-trimmed exposures — a bug we would otherwise rediscover painfully. |
| **Hardware-free testing** | `cameras/synthetic.py` (258 lines) | A full fake backend. The reason their suite and UI run with no camera attached. Directly serves our fast-test goal. |
| **Dual-stream capture** | `pipeline.py`, `service.py` | One `create_video_configuration` with simultaneous full-res `main` + `lores` preview from the same sensor frame; single-camera manager with a reservation context. **No `switch_mode_and_capture`** — stills come off the already-running full-res stream. |
| **Preview approach** | `web/routes/stream.py` | MJPEG via `multipart/x-mixed-replace` into a plain `<img>`, plus a magnified 1:1 ROI crop stream **for focusing** — exactly the guided-focus aid M1 needs. |
| **Settings persistence** | `metrology/record.py` save pattern, `docs/persistence.md` | Schema-versioned timestamped JSON + `current.json` pointer, written atomically. The pattern the old UI never applied to settings. We put settings in SQLite instead, but the versioning discipline transfers. |
| **AprilTag detection** | `metrology/survey.py`, `board.py` | `cv2.aruco`, `DICT_APRILTAG_36h11`, `CORNER_REFINE_SUBPIX`, with **tuned `DetectorParameters` that measurably beat stock — 20 tags detected vs 12.** |
| **Measured hardware behaviour** | Comments throughout `picamera2_backend.py` | 9152×6944, 10-bit (not 12 like IMX477), `SRGGB16` Bayer order, 370 ms minimum frame, 2.8 s DNG encode. |
| **Decisions & real measurements** | `docs/chamber-setup.md`, `architecture.md`, `persistence.md`, `autofocus-integration.md` | Measured values and a frank "reads 16 mm too high" defect note. |

**Ignore entirely:** `docs/accuracy-map.md`, `camera-calibration.md`, `orthophoto-correction.md`,
`stereo-plant-height-estimation.md`, `camera-setup-wizard.md` — ~2,000 lines of theory for features
never built. Plus `cli.py` (1,753 lines, mostly metrology subcommands) and `.claude/worktrees/`
(three stale copies that triple any naive LOC count).

**One honest cost note:** `synthetic.py` and `exposure_controls()` are small, self-contained, and
encode hardware behaviour that took real bench time to discover. Rewriting them from reading costs
perhaps a day or two more than lifting them. Your call stands — reference only — but the trade is
worth knowing rather than discovering in week three.

## Verification strategy (the whole point)

1. **`pytest`** — unit tier, under 10 s, run constantly.
2. **Fixture-image integration tests** — real captures in the repo, so the pipeline regression-tests
   without hardware.
3. **Physical acceptance tests per milestone** — run in the chamber with a tape measure and printed
   targets. A milestone isn't done until these pass.
4. **The honesty plot** — at M2 and again at M5, plot *claimed confidence* against *actual measured
   error*. If the app says ±3% and is routinely off by 10%, that's the most important kind of bug,
   and this is how we catch it. Its residual *structure* is also what opens or keeps shut the
   intrinsic-calibration gate.

## Remaining open questions

- **Segmentation model** — stubbed behind the `Segmenter` interface; revisit before M5. Nothing
  exists in the old repo, so this is genuinely new work whenever it lands.
- **Capture rate vs storage** — 10/hour is ~29 GB/month, 60/hour is ~170 GB. Decide alongside
  retention policy and whether an external SSD is needed.
- **Calibration sheet layout** — the old repo has an A4 sheet of 25 tags (ids 0–24) at 29.31 mm
  measured (that print only); tray tags were ids 40–43. Confirm the ID allocation for 12 trays plus 4 corner tags.
- **Digest delivery** — email, or render in the web UI only.
