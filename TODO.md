# TODO

Actionable items. Each block names its section in [PLAN.md](PLAN.md) — read that section before
starting, not the whole document.

Status: `[ ]` not started · `[~]` in progress · `[x]` done · `[?]` needs Aaron

---

## Needs Aaron — blocking nothing yet, will block later

- [?] **Segmentation model** — what form is it in? Blocks M5, nothing before it.
- [?] **Capture rate vs storage** — 10/hr is ~29 GB/month, 60/hr is ~170 GB. Decide with retention
      policy and whether an external SSD is needed. Blocks M3.
- [x] **Tag ID allocation — decided 2026-09-20 (Aaron), supersedes the 2026-09-19 allocation.**
      One family, 36h11, for everything; ranges kept configurable rather than hardcoded. **These
      ranges are arbitrary** — chosen to be simple for future users, not measured or derived from
      anything:
        - **0–299** — tray tags, for experimenters to 3D-print their own (per Aaron's supervisor)
        - **300–449** — calibration sheets
        - **450–499** — corner/reference tags (4 mounted, one currently partially obscured; exact
          IDs to be confirmed by reading them back once detection is built, rather than
          transcribed by eye)
        - **500–586** — unallocated buffer, for any future fixed rig-level role. 36h11 has 587
          IDs total (0–586) — verified against both cv2's dictionary size and moms_apriltag's
          `TagGenerator2` (see `~/apriltag-gen`), not trusted from memory.
      **Uniqueness only needs to hold within a chamber**, not across the fleet — up to 15
      experiments of 12 trays each may run across different chambers using IDs from the same
      pool with no coordination required between them. Duplicate-tray-ID detection within one
      chamber is its own TODO item, under M4.
      A second tag family for corners (structural, not just numeric, separation) was considered
      and deferred — see PLAN.md's "Deferred, with evidence gates" table.
      **New follow-up:** 3D-printed tray tags are a different physical object from the paper
      calibration/corner sheets — the 29.3106 mm figure in CLAUDE.md was measured on paper and
      does not carry over. Needs its own calliper measurement, and a check of detectability
      (embossed relief vs. flat ink, under the chamber's grow lighting) once a printed sample
      exists.
- [x] **Corner tag placement — confirmed 2026-09-19 (Aaron).** Four corner tags mounted on the
      rebuilt rig's table corners and in frame; one is currently partially obscured.
- [?] **Digest delivery** — email or web UI only. Blocks M6 only.
- [?] **Hailo accelerator** — no `hailortcli`, no PCIe device, no package installed on this OS
      build. Needs HailoRT install and physical seating confirmed. Blocks M5 only, and M5 ships
      with a classical fallback regardless.
- [x] **Color swap bug, actually fixed 2026-09-21** — the 2026-09-19 "lighting spectrum"
      conclusion below was wrong; this was a real, reproducible software bug the whole time, in
      `camera.py`, unrelated to any of: chamber lighting, system packages
      (`libcamera0.7`/`libcamera-ipa` were briefly and wrongly suspected — real version skew,
      side-loaded 2026-09-03, but 16 days before either the good or bad capture, so it can't
      explain the timing), and `python3-opencv` (installed hours after the bug already showed).
      **Root cause:** explicitly keying `"format"` on a `create_video_configuration`/
      `create_still_configuration` stream puts this picamera2/libcamera build on a different
      internal path that delivers the wrong channel order — true for *either* `"RGB888"` or
      `"BGR888"`, confirmed both ways. Left unconstrained, `main` and the still config negotiate
      their own default (logged as `"BGR888"`/`"XBGR8888"`) and the array comes back genuinely
      R,G,B(,padding) — **despite that log name**, which is misleading on this build, not
      descriptive. `lores` still needs a format pinned (or it negotiates broken YUV420 planar,
      the original 2026-09-19 bug this pinning existed for) — pinned to `"XBGR8888"`
      specifically, the one explicit format confirmed to still come out right.
      **Two false fixes before this one landed, both instructive:**
      1. 2026-09-19: tried `"BGR888"`, reverted it as "wrong" on the strength of a channel-swap
         test *without* checking against a real known-color object — the test passed, the real
         bug (triggered by explicit-format-keying itself, not by which string) was still there.
      2. 2026-09-21 (this session, first attempt): assumed the `"BGR888"` log name was accurate
         and added a channel reversal to `array_to_jpeg`/`to_grayscale` — reported as fixed
         from a single glance at a wide scene shot, without checking the specific known-color
         object. Aaron caught it with a direct crop comparison against the confirmed-good/bad
         references; the reversal was backwards and made it worse.
      **What actually settled it:** numeric + visual comparison of the *same* tote-region crop
      across the confirmed-good (2026-09-19 11:19) and confirmed-bad (2026-09-19 12:17)
      references, `rpicam-still` (bypasses picamera2 entirely — ground truth), and every
      candidate fix, at the same pixel coordinates each time. Verified again afterward through
      the actual `/capture` and `/snapshot.jpg` endpoints, live. **Lesson for next time:** "the
      report says colors are correct" is not verification unless the report is about the
      specific object being checked, at the same crop, compared against a reference taken the
      same way — a wide scene glance is not that.
- [?] **Minimum-gain policy** — Aaron's supervisor requires minimal `AnalogueGain` at all times.
      Default is already 1.0 (satisfied as-is). Not yet decided: whether to *enforce* this
      further — e.g. cap the gain slider's usable max, or bias auto-exposure toward longer
      exposure time over gain (`AeExposureMode`, unverified whether picamera2 exposes a "long
      exposure preferred" mode — would need checking against real hardware before building
      anything, same as the format-string lesson from M1 slice 3). Not built; needs a decision
      on how strict this should be before doing more than the current default. *(Aaron,
      2026-09-19)*

---

## M0 — Probe the hardware · *PLAN.md § M0*

30 minutes. Do this before writing any code; it can change M1's shape.

- [x] `rpicam-hello --list-cameras`
- [x] `python3 -c "from picamera2 import Picamera2; p=Picamera2(); print(p.sensor_modes); print(p.camera_controls)"`
- [x] `hailortcli fw-control identify` — not found; no Hailo device/package detected anywhere.
      New `[?]` below.
- [x] Confirm whether `AfMode` / `LensPosition` are present. Present. Focus is
      software-controllable; M1 slices 4/5 proceed as planned.
- [x] Record findings in `reference/hardware-probe.md`

---

## M1 — Camera console · *PLAN.md § M1*

Sliced so each piece ends with something visible in a browser.

### Slice 1 — Skeleton
- [x] `git`-tracked project layout, `pyproject.toml`, venv with `--system-site-packages`
- [x] FastAPI + uvicorn serving one page
- [x] pytest with marker infrastructure and `addopts = -m unit`
- [x] systemd unit, restart-on-failure *(unit file written, not installed/enabled — manual start for now)*
- [ ] Install/enable the systemd unit and run the reboot-survival checks in PLAN.md's M1 "you
      verify" line and M3's acceptance bullet. **Deferred, low priority.** Aaron has no physical
      access to the device right now; a failed reboot is an unrecoverable round trip until he
      does. Pick this up later, at whichever milestone is testing reboot survival anyway (M3),
      not as a standalone task. *(Aaron, 2026-09-19)*
- [x] **Demo:** page loads (verified via curl, 200 OK) and `pytest` runs in 0.44s. Unit file written
      to `deploy/npec-rig.service` but not copied to `/etc/systemd/system` or enabled, per this
      slice's manual-start instruction — reboot survival not tested yet.

### Slice 2 — One still
- [x] `CameraManager` singleton wrapping picamera2
- [x] Synthetic camera backend so tests and UI run with no hardware
- [x] Single-JPEG snapshot endpoint
- [x] **Demo:** confirmed via `curl` against the running server — real 9152x6944 JPEG from the
      real camera, viewable in the browser at `/`. Frame is out of focus, as expected: manual
      focus control is slice 5, not built yet.

### Slice 3 — Live preview
- [x] Dual-stream config: `main` (1536x1152) + `lores` (320x240) preview from the same sensor
      frame. Note: `main` is not full sensor resolution — full-sensor stills top out at ~3 fps
      per M0, so `/snapshot.jpg` now serves `main` instead. True full-res capture-to-disk is
      slice 5's job, as a deliberate mode switch, not this continuous stream.
- [x] MJPEG via `multipart/x-mixed-replace` into a plain `<img>`
- [x] **Bug fix (2026-09-19):** live preview was black-and-white with a garbled band in the
      bottom third. Root cause: `lores` stream was left format-unspecified and negotiated
      YUV420 planar (Y rows, then subsampled U/V rows packed below — that packed section is
      exactly a third of the total buffer height, matching where the artifact showed up); our
      code treated that buffer as interleaved RGB. Root cause of *that*: `encode="lores"` was
      left over from assuming we'd use picamera2's own hardware encoder, which we never do (we
      PIL-encode ourselves) — removed it and pinned `format: "RGB888"` on both `main` and
      `lores` explicitly instead of trusting the negotiated default. Verified: fresh preview
      frame is correct color, no artifact; snapshot/capture/focus-score still work.
- [x] **Demo:** measured 30 frames in 3s against real hardware = steady 10 fps (our configured
      cap), comfortably over 5 fps. Confirmed real frames, correct `Content-Length` framing.
- [x] **Investigated (2026-09-19):** Aaron reported a known-yellow object rendering blue in the
      preview. Checked directly against picamera2 rather than guessing — a channel-swap test
      (capturing the same scene as `RGB888` and `BGR888`, comparing each against the other
      reversed) confirms `RGB888` genuinely returns R,G,B channel order (not swapped, despite an
      initial wrong assumption on my part that it was — reverted a `BGR888` change that would
      have made this worse, not better). A known-neutral white paper sheet in the same frame
      also reads back neutral, ruling out a global white-balance cast. The object itself
      measures blue-dominant (B > G > R) in the raw data either way.
      **Conclusion: not a software bug as far as this checks** — most likely the chamber's
      grow lighting has a spectrum narrow enough that a genuinely yellow object doesn't reflect
      the wavelengths a normal camera expects, which auto white-balance can't fully correct.
      **Needs Aaron:** confirm by looking at the same object under the camera in normal room
      light vs. the chamber's grow light. If it still looks blue under the chamber light with
      the naked eye, this isn't a camera problem to fix at all.
- [x] Pulled a minimal lens-position slider in from slice 4/5 (Aaron asked to see live preview
      with focusing together) — POST/GET `/controls/lens-position`, no persistence yet. Verified
      against real hardware: write then read-back matches after ~0.5 s settle (camera pipeline
      latency, not a bug — metadata reflects the frame in flight, not instant on write).
      Full sharpness-score focus aid and settings persistence remain slice 4/5, not built.
- [x] Responsive layout (viewport meta, fluid width, larger touch controls) for mobile/small
      low-res displays — written but **not yet visually confirmed in an actual browser**. Please
      eyeball it on the target display and at phone width before calling this done.
- [x] Focus zoom sits to the right of the live preview above 800px width, stacks vertically
      below it (plain CSS flexbox + one media query, no JS) — same visual-confirmation caveat
      as above. *(Aaron, 2026-09-19)*

### Slice 4 — Controls and persistence
- [x] Control list generated from probed `camera_controls`, not hardcoded. Good thing it isn't:
      probed live, `LensPosition`'s max read 15.0, then 32.0, then 15.0 again across different
      probes in the same session; `ExposureTime`'s max varied by two orders of magnitude
      (66666 vs 122582952) and `AnalogueGain`'s max read both 16.0 and 64.0 — these ranges are
      config/mode-dependent, not fixed hardware facts. A hardcoded range would have been wrong
      at least once. Frontend renders whatever `/controls` reports, generically — a checkbox
      for boolean controls, a slider for numeric ones — so a different camera or firmware
      changes the UI without a code change.
- [x] Exposure time, analogue gain, AWB on/off (`AwbEnable`), AE on/off (`AeEnable`); manual
      lens position (already had dedicated coarse/fine/autofocus UI from slice 5 — its range is
      now also pulled from this same probe instead of a hardcoded 0–15).
- [x] Settings persist in SQLite (`/var/lib/npec-rig/rig.db`, table `camera_settings`) and load
      on startup instead of defaults.
      **Real bug found and fixed:** `AnalogueGain`/`ExposureTime` writes are silently
      overridden by the auto-exposure algorithm until `AeEnable` is off — confirmed on real
      hardware, not assumed. Loading persisted settings in dict order occasionally applied
      `AnalogueGain` before `AeEnable`, so the gain got immediately overwritten by AE before AE
      was turned off. Fixed by applying `AeEnable`/`AwbEnable` first, always.
- [x] **Demo:** verified against real hardware. Set gain 3.5, AWB off, AE off, lens 6.3; stopped
      and restarted the *application* (not the Pi — Aaron doesn't want reboot tests, a failed
      one is a 3-hour round trip); after restart, `/controls` showed all four correctly
      restored, not defaults.
- Note: while testing this, Aaron was independently using the new controls live in his own
  browser tab — real concurrent usage, which is a better signal than my own curl checks. Took
  that as confirmation the UI works, not as noise to filter out.
- [?] One exposure-time value from testing (11.6 seconds) didn't reapply on restart — likely
      clamped because it exceeds what the *current streaming mode's* frame duration allows,
      even though the probed range's max is much larger (that max may be a still-mode-only
      figure). Not chased further; flagging in case exposure control feels unreliable near the
      top of its reported range. *(2026-09-19)*
- [x] UI polish on Camera settings (2026-09-19, Aaron): moved below Focus aid, collapsed by
      default (native `<details>`/`<summary>`, no custom widget); AWB and AE checkboxes shown
      on one line; exposure time displayed as a fraction of a second (`1/147 s`) instead of raw
      microseconds — the API still speaks microseconds underneath, this is display-only. Reset
      the live rig to the stated default policy: auto exposure on, auto white balance on,
      analogue gain 1.0.

### Slice 5 — Focus aid
*(Built ahead of slice 4 at Aaron's request, 2026-09-19 — not the plan order.)*
- [x] Laplacian-variance sharpness score on a selectable ROI (click the live preview to place it)
- [x] Magnified 1:1 ROI crop stream (`/focus/roi.mjpg`, 5 fps, no interpolation — genuine pixels,
      not resized, so the score and the display agree)
- [x] Lock and record lens position (`/focus/lock`, in-memory only — no persistence yet, that's
      still slice 4)
- [x] Full-res capture to `/var/lib/npec-rig/captures/YYYY-MM-DD/` with JSON sidecar. Created
      `/var/lib/npec-rig/captures` (root-owned parent, chowned to `pi`) since it didn't exist.
- [x] Recent-captures gallery on the main page
- [x] **Demo:** verified against real hardware — swept lens position 1.0 to 10.0, sharpness score
      peaked at 6.3 (score 1105–1119, vs. single digits elsewhere), matching the old rig's known
      focus position from the M0 probe notes. Captured, got a real JPEG + sidecar JSON on disk,
      listed in `/api/captures`.
- [x] Removed the "Full snapshot" link from the page — Aaron didn't want a manual full-snapshot
      click in the final UI, and the magnified crop now does that job.
- Note: found and killed two stray leftover processes (from an earlier hung test run) that were
  holding the camera device open, which had made the server silently fall back to the synthetic
  backend without erroring. Logged as a real gap: **slice 6/M6 candidate — surface backend choice
  (synthetic vs. real) somewhere visible in the UI**, so a silent fallback like this doesn't go
  unnoticed again.
- [x] One-shot hardware autofocus (`AfMode=Auto` + `AfTrigger`, via picamera2's
      `autofocus_cycle`), always returning to `Manual` afterward so it can't hunt or drift
      mid-experiment. Verified on real hardware: landed at 5.71 (score 324) in 0.7 s, manual
      control confirmed still working right after. *(Aaron, 2026-09-19)*
- [x] Replaced the single full-range lens slider with: an **Autofocus** button, a **coarse**
      `<input type="number">` (whole dioptres, native spinner + free digit entry — no custom
      widget needed), and a **fine** slider with a fixed `.00`-`.99` range (no recentering).
      Coarse (whole number) + fine (fraction) simply add together. Typing "6.8" into coarse
      splits into coarse=6, fine=.80 (slider jumps to 80%) — same mapping every time, so the
      slider position is always predictable from the number. Revised from an earlier
      ±1.0-dioptre-recentering design after Aaron pointed out unpredictable slider position was
      the actual problem — this version has *less* logic than that one (no dynamic range to
      recompute), not more. *(Aaron, 2026-09-19)*
- [ ] When the attached lens has no autofocus (some lenses are manual-only), gray out the
      Autofocus button with a note explaining why, instead of letting it fail silently or throw.
      Deferred until a manual-only lens is actually in use. *(Aaron, 2026-09-19)*
- [ ] Camera selector in the UI for when multiple cameras are detected. Not needed on the
      current single-camera rig; for a future project/rig with additional cameras.
      *(Aaron, 2026-09-19)*
- [ ] Optional suffix/label on a capture (filename and/or sidecar field), so a specific capture
      can be told apart from the rest without relying on timestamp alone. *(Aaron, 2026-09-19)*
- [x] Focus peaking: toggle with a description, highlights high-contrast edges in the magnified
      crop in magenta. Reuses the existing Laplacian machinery (one shared helper function, one
      boolean flag, no new modules) rather than a separate subsystem. Verified on real hardware
      at lens=6.3: dense magenta on the AprilTag edges, matching the 1130 sharpness score at the
      same position. *(Aaron, 2026-09-19)*

---

## M2 — Calibration and rig health · *PLAN.md § M2*

The heart of the project. Do not start before M1 slice 5.

- [x] Hardware-test skip infrastructure in `tests/conftest.py`: `pytest_collection_modifyitems`
      probes for the real camera (`Picamera2.global_camera_info()`, no open/lock) and Hailo
      (`hailortcli` on `PATH`), skipping `hardware`/`hailo`-marked tests when absent instead of
      hard-failing. Registered `trylast` so it only probes hardware that a `hardware`/`hailo`-
      marked test actually survived `-m` filtering to need — a plain `pytest` (unit tier, the
      default) never touches the camera, so it can't collide with a live server using it.
      **Real incident (2026-09-19):** an earlier, unconditional version of this probe did touch
      the camera on every `pytest` run, and collided with Aaron's live session mid-conversation
      (transient `V4L2 ... Device or resource busy`, plus an unrelated file-write triggering
      uvicorn's `--reload` to hang on "waiting for connections to close" until he refreshed the
      stuck browser tab). Fixed; noted so the same mistake isn't repeated.
- [x] AprilTag detection: `src/npec_rig/tags.py` — `cv2.aruco`, `DICT_APRILTAG_36h11`, tuned
      `DetectorParameters` (`CORNER_REFINE_SUBPIX`, `minMarkerPerimeterRate=0.005`, adaptive
      threshold window 11–91 step 10), reused from the previous rig rather than re-derived.
      `detect_tags()` returns sorted `TagDetection` (id, corners); `draw_overlay()` for a visual
      check. Unit tests in `tests/test_tags.py` use `cv2.aruco.generateImageMarker` (known IDs,
      multi-tag, rotation) — synthetic-but-exact, not a photo, so they test our wrapper code
      rather than the detector's own algorithm — plus one narrow real-photo smoke test (a small
      crop with one genuine tag) proving real camera/JPEG output decodes.
      **Note on process:** an earlier version of this work built four tests against a full bench
      photo Aaron had left on the table as orientation reference, not curated test data —
      including an `xfail` encoding a tuned-vs-stock count reversal specific to that photo's
      unusually dense tag sheets (325+ real tags, per Aaron: 9×25 + 2×20 + 6×9 sheets + corners +
      stray "garbage" tags). Redone at Aaron's correction: don't treat an incidental scene as
      ground truth, and don't assert things about detector algorithm quality that aren't ours to
      test. The full photo was removed from the repo; only the minimal crop remains.
- [x] **Calibration mode UI** — `POST /calibration/run` in `app.py` (plus the "Calibration"
      section in `static/index.html`): captures a full-res still, detects tags, builds the scale
      field + install report via `build_calibration_report()`, and shows the operator the result
      in the browser. Also builds the corner baseline (`build_corner_baseline()`) and records the
      current lens position into the saved `CalibrationArtifact` — this was the "needs bench
      access" gap noted below in the health-baseline entry; both are now populated from a real
      capture, not just plumbed as optional fields. Saves the full-res frame alongside the
      artifact (`calibration_store.save_calibration_frame()`, same timestamp stem) so a bad or
      disputed field can be re-processed later without redoing the physical paper-sheet setup —
      every M2 acceptance test below is a diff between two calibrations. Smoke-tested against
      real hardware 2026-09-21 (no sheets on the table yet, so 0 tags — exercised the "not enough
      tags" path cleanly, ~8.5s round trip for a 64MP capture + detect at 0 tags; expect longer
      with real sheets present). **Tag size caveat, resolved 2026-09-21:** `tags.py`'s
      `ASSUMED_CALIBRATION_TAG_SIZE_MM` (29.3106mm) was a placeholder for whoever hadn't measured
      a given print run yet, not a substitute for measuring it -- reusing it as a hardcoded
      constant was wrong, since a reprint isn't guaranteed to come out the same size. Aaron
      calliper-measured the *2026-09-20 print* of IDs 300-449 (`reference/calibration-sheets/`)
      directly: ~30.02mm average across 6 measurements (30.1, 30.11, 29.96mm X; 30.04, 29.96,
      29.94mm Y), not 29.3106mm. Fixed by making it a per-run input instead of a constant --
      `calibration_tag_size_mm` on `POST /calibration/run`, UI field pre-filled from the last
      calibration's own recorded value, stored on `CalibrationArtifact` (schema version 1 -> 2)
      so a saved artifact records what it actually assumed rather than depending on a global that
      can drift. This was the largest error source in the project if wrong, and neither the
      holdout test nor the two-baseline test can catch a wrong constant applied identically both
      times -- only a real measurement, entered per run, closes it. *(2026-09-21)*
- [x] **Manual tripwire trigger** — `POST /calibration/tripwire/check` plus the "Check tripwire
      now" button: runs `check_tripwire()` against the saved baseline on demand. Decided this
      session not to wait for M3's scheduler (see the per-capture tripwire entry below) — without
      some trigger, the roll/knock acceptance test has no way to invoke a tripwire check at all.
      Automatic per-capture wiring is still M3 scope. *(2026-09-21)*
- [x] **`promote` flag so a comparison run can't silently swap the live baseline** —
      `save_calibration(artifact, promote=...)` in `calibration_store.py`; `POST
      /calibration/run?promote=false` (UI: "Set as current baseline" checkbox, unchecked) writes
      the timestamped artifact + frame without touching `current.json`. Without this, the
      two-baseline test's own second run would silently replace the baseline
      `/calibration/tripwire/check` reads mid-test — caught before it shipped, not after Aaron
      hit it in the chamber. *(2026-09-21)*
- [x] **Calibration export** — `GET /calibration/list` plus a `/calibration/files/` static mount
      (same pattern as `/captures`) serving every saved artifact JSON and its frame; the
      "Saved calibrations (download)" panel in the UI. PLAN.md M2 section A says calibration is
      "frozen, versioned, **exportable**" — this is the export; before this, artifacts only
      existed on the Pi's filesystem, reachable over SSH. *(2026-09-21)*
- [x] **Scale field** — `src/npec_rig/calibration.py`, `build_scale_field()`: fits a single
      tilted-plane model (relative depth linear in image x, y) from `TagDetection`s plus a
      tag_id -> size_mm lookup. `ScaleField.px_per_mm(x, y)` / `.mm_per_px(x, y)` give local
      scale anywhere in the frame; `residual_std_pct` is a *global* plane-fit diagnostic.
      Validated against the real 2026-09-19 capture (reproduces the one-off analysis exactly:
      1.82% residual). Unit-tested with synthetic detections, no photos as ground truth.
      *(2026-09-20)*
- [x] **Uncertainty field (local scatter)** — `UncertaintyField`/`build_uncertainty_field()` in
      the same module: at a query position, RMS-about-zero (not std about the neighbours' own
      mean) of the k image-plane-nearest tags' residuals against the fitted plane. k-nearest by
      distance, not a fixed grid — a real calibration sheet's tags are scattered irregularly.
      RMS-about-zero matters: a cluster of tags that all agree with *each other* but are all
      biased the same way off the plane has ~zero scatter about their own mean but a real
      systematic error — std would report false maximum confidence there, exactly the
      honesty-plot failure mode M2's acceptance tests exist to catch. Unit-tested with synthetic
      detections including a deliberately biased local cluster. *(2026-09-20)*
- [x] **Holdout coverage test** — `holdout_coverage_test()` in the same module: fits on a random
      half of usable tags, predicts the other half, reports mean/max % error. Real-capture
      sanity check: 1.48% mean, 4.29% max. *(2026-09-20)*
- [x] **Regional coverage (spatial attribution)** — `regional_coverage_test()`: fits on three
      quadrants, predicts the fourth, for each of the frame's four quadrants (split at the
      *frame's* midpoint, not the tag cloud's own median — a median split can never produce an
      empty quadrant, which would hide the strongest possible "add coverage here" signal).
      `describe_regional_coverage()` turns that into "add a sheet in the top-left" /
      "coverage weak in the bottom-left" lines, wired into `build_install_report()`. This is what
      turns the coverage check into "add coverage in the top-left" rather than just a percentage.
      Unit-tested with synthetic detections. *(2026-09-20)*
- [~] **Install report** — `describe_scale_variation()`, `describe_coverage()`,
      `build_install_report()` in `calibration.py`. Scale variation is evaluated over the
      *observed tag cloud's* bounding box, never the frame -- extrapolating the fitted plane past
      where tags were actually seen would be the report lying about its own coverage.
      Coverage verdict defaults to PLAN.md's 2% tape-measure acceptance target as the
      sufficient/insufficient threshold. **Roll, tilt and framing lines are not built** -- a
      roll/tilt angle isn't recoverable from a single photo without a physical standoff-distance
      measurement Aaron has ruled out (rig is fragile), and framing needs a real capture's
      corner-tag/frame-edge check. `build_calibration_report()` is the entry point a real caller
      should use — it builds the field, positions, and global/regional coverage from one
      consistent set of detections before assembling the report lines, so a field from one
      capture can't get paired with coverage from another (`build_install_report()`'s own
      parameters aren't cross-checked, by design — useful for testing each line in isolation).
      Unit-tested with synthetic detections. *(2026-09-20)*
- [x] **Live reorientation guidance** — `POST /calibration/orientation/zero` (freezes the current
      preview frame's corner tags as an in-memory zero point) + `GET
      /calibration/orientation/live` (roll/scale reading against that zero point) in `app.py`,
      plus the "Live reorientation aid" panel in `static/index.html`, polled every 500ms. Reuses
      `check_tripwire` rather than deriving roll/tilt from raw single-frame geometry (e.g. "corner
      tags should form an axis-aligned rectangle," "corner tags are the same physical size") —
      neither assumption is established anywhere in this repo, and a wrong one would be a derived
      number presented as measured. Zero point is in-memory only, not persisted, separate from the
      real calibration baseline. Smoke-tested against real hardware 2026-09-21 (no corner tags on
      the table yet, so both endpoints 409 cleanly on "no corner tags detected" / "no zero point
      set") — **not yet exercised end to end with real corner tags in frame**, that needs bench
      access. *(Aaron, 2026-09-19; built 2026-09-21)*
- [x] **Health baseline** — `CornerBaseline`/`build_corner_baseline()` in
      `src/npec_rig/tripwire.py`: corner tag corners keyed by tag id, built from whatever subset
      of the (up to 4) mounted corner tags a real calibration actually detects — not assumed to
      be exactly 4, since one is currently partially obscured (TODO.md). Lens-position
      capture/recording is now wired up too, via `POST /calibration/run` (see the calibration
      mode UI entry above). **Still not built:** a homography matrix — nothing in M2 consumes one
      yet (the tripwire uses Procrustes rotation + per-tag size ratio instead), so it stays
      deferred until something needs it.
- [x] **Per-capture tripwire** — `check_tripwire()` in `tripwire.py`: `OK`/`DRIFT`/`FAIL` against
      a `CornerBaseline`, from Procrustes-fit roll (all 4 corners of each matched corner tag, not
      just centres) and per-tag size ratio ("near corner tag N is 5% closer"). Missing baseline
      tag -> `FAIL`, loud; missing a tag the baseline never had -> not a failure (handles the
      currently-obscured corner tag). Refuses (`FAIL`) rather than computing a roll figure from
      fewer than 2 matched corner tags — one tag's own 4 corners measure that tag's own
      orientation, not the cross-tag geometry a roll/drift check needs. Roll here is an in-image
      rotation between two frames of the *same* rig, not the absolute-tilt angle CLAUDE.md rules
      out measuring from one photo — no standoff-distance measurement needed, see the module
      docstring. Thresholds are provisional
      parameters (default: 1 deg drift / 10 deg fail, 3%/8% scale) set so a deliberate ~5 deg test
      roll lands as `DRIFT` per PLAN.md's acceptance wording, not tuned to real data yet -- the
      chamber acceptance tests are the actual measurement. Unit-tested with synthetic baselines
      and known rotations/scale changes. Wired into a manual trigger, `POST
      /calibration/tripwire/check` (see the manual tripwire trigger entry above) — **not into an
      automatic per-capture pipeline** (writing a verdict to the DB on every reading), which still
      needs the recurring capture loop M3's scheduler builds. *(2026-09-20, updated 2026-09-21)*
- [x] **Tray tags re-fit scale on top of the frozen field** — `ScaleFactorRefit`/
      `refit_scale_factor()` in `calibration.py`: keeps the frozen field's shape (plane tilt
      coefficients) fixed, refits only the multiplicative scale factor from new (e.g. tray-tag)
      detections. Given a frozen shape, a uniform scale correction is the *only* well-posed
      degree of freedom left to fit from interior-only points — refitting the tilt too would be
      degenerate with rescaling, not an independent "perspective correction" (see the docstring
      for the full argument; re-read PLAN.md's M2 section B paragraph before changing this).
      Returns `interior_scatter_pct` — how much the new detections disagree with each other —
      as its own field, distinct from the frozen field's own `residual_std_pct` (which stays
      untouched, since it describes the *paper-sheet* fit, not this refit). Unit-tested with
      synthetic detections, including a uniform-rescale case and a disagreeing-tags case.
      *(2026-09-20)*
- [x] **Calibration artifact: versioned, exportable** — `CalibrationArtifact` +
      `calibration_artifact_to_dict()`/`_from_dict()` in `calibration.py` (owns `ScaleField`'s
      private fields, so the codec lives there rather than in a separate module). Plain versioned
      dict (`version` field, currently 1) bundling the scale field, corner baseline and locked
      lens position — kept deliberately simple, no schema library, per CLAUDE.md's "don't build
      more than that without a concrete reason." `from_dict` rejects an unrecognised version
      rather than guessing at its shape. Round-trip unit-tested, with and without a baseline.
      *(2026-09-20)*
- [x] **Calibration data lives in its own storage location** — new
      `src/npec_rig/calibration_store.py`: `NPEC_RIG_CALIBRATION_DIR`, defaulting to
      `/var/lib/npec-rig/calibration/`, separate from `NPEC_RIG_CAPTURES_DIR` — same
      env-var-with-a-default convention as `settings.py`'s `db_path()` and `captures.py`'s
      `captures_root()`. Schema-versioned timestamped JSON files plus a `current.json` pointer
      (both written atomically, write-then-rename), the persistence pattern PLAN.md notes
      approvingly from the old project (`docs/persistence.md`) — appropriate here since
      calibration is explicitly "frozen, versioned, exportable," unlike camera settings, which
      use SQLite instead. Unit-tested (round-trip, current-pointer tracking, listing, isolation
      from the captures dir). *(2026-09-20)*

### M2 — area-scale shape check, built 2026-09-21

- [x] **Direct area-scale field from tag shape, not trigonometry.** Aaron asked whether tag
      squareness + trigonometry could give surface-area error moving out from centre; that
      version needs lens intrinsics and a camera-to-table distance we can't safely get (same
      standoff-distance wall as the tilt-angle problem, see `m2_calibration_progress.md`
      memory). The version that avoids this entirely: every calibration tag's real area is
      `size_mm²` (already calliper-verified); its *pixel* area is computable right now from its
      four already-detected corners (shoelace formula on the quadrilateral -- exact, no
      assumptions, `tags.tag_area_px`). `pixel_area / size_mm²` compared to
      `(ScaleField.px_per_mm at that position)²` gives `area_error_pct` per tag
      (`calibration.area_scale_samples`), surfaced as a report line
      (`describe_area_scale_shape`) and a heatmap (`calibration_viz.render_area_shape_heatmap`),
      the same way scale variation and coverage are.
      **Built, but not the number it looks like:** `area_error_pct` decomposes exactly into
      `100 * (kappa - 1) + 2 * residual_pct` (see `AreaScaleSample`'s docstring for the algebra),
      where `kappa = pixel_area / tag_side_px² <= 1` (a square is the max-area quad for a given
      mean side length) is the actually-new shape signal and `residual_pct` is the *already-
      plotted* length-scale residual, doubled. On this rig's real geometry `residual_pct`
      dominates by roughly two orders of magnitude (measured, reprocessing all 17 real
      calibration frames from 2026-09-21 offline: `shape_factor_pct = 100*(kappa-1)` maxed at
      -0.45% and averaged -0.05% over 2104 tags, versus `area_error_pct` averaging 3.1% and
      peaking at 14.5%) -- reading `area_error_pct` alone and seeing it grow toward the corners
      would just re-discover the known bottom-right coverage gap below, not evidence area needs
      its own fit. `shape_factor_pct` is kept on `AreaScaleSample` and is what the heatmap
      actually plots (own measured 0-0.5% range, `AREA_SHAPE_HEATMAP_MAX_PCT`), specifically so
      that question can be answered without the confound. *(Aaron asked 2026-09-21; built and
      verified against real hardware frames the same day)*
- [?] **`shape_factor_pct` itself is structured toward the corners on real data -- is that real
      distortion or a corner-precision artifact?** Before trusting the 0.005%-centre-to-0.12%-
      corner spread above as real geometry, checked the obvious confound: corner-refinement
      noise on a tag of side `s` biases `kappa` down by `~1/s²`, and tag size is itself weakly
      position-dependent, so a pure noise floor could *look* like corner structure without being
      any. Same 17-frame/2104-tag reprocess, this time regressing `abs(shape_factor_pct)`
      against `1/tag_side_px²` and against distance from frame centre separately: `1/side²`
      explains almost nothing (R²=0.03, corr=0.16, and binning by tag size isn't even monotonic),
      while distance from centre is strongly and monotonically correlated (corr=0.74; mean
      `abs(shape_factor_pct)` goes 0.005% → 0.012% → 0.073% → 0.119% across distance quartiles
      whose mean tag size barely moves, 131→132→130→129px) and stays just as correlated
      (corr=0.71) after regressing out `1/side²`. Reads as real, position-structured shape
      distortion, not a tag-size artifact -- i.e. exactly the pattern this check's own decision
      rule calls "real evidence area needs its own fit before M5." Not acted on: that's a real
      scope decision (an area-specific fit is calibration maths, CLAUDE.md's evidence-gate
      table), not something to start on the strength of one diagnostic without Aaron's sign-off.
      *(2026-09-21, offline reprocess, no bench time)*

### M2 — known issues, not yet fixed

- [ ] **Live reorientation aid never actually works** — `POST /calibration/orientation/zero`
      refused twice on real hardware (2026-09-21) with "no corner tags detected." The corner
      tags are 50mm on `CORNER_ID_RANGE`; the preview stream (`LORES_SIZE`, far below full-res)
      is apparently too low-resolution for `detect_tags` to pick them up at all, so the feature
      as built is unusable in practice, not just imprecise. Full-res captures detect all 4 corner
      tags reliably every time -- this is specific to the preview resolution. Needs either a
      higher-resolution preview specifically for this check, or a detector-sensitivity change for
      it; not attempted yet. *(Aaron, 2026-09-21)*
- [ ] **Calibration capture immediately followed by autofocus wedges the whole camera pipeline**
      — reproduced on real hardware 2026-09-21: run a calibration, then hit "Autofocus," and
      every camera-touching endpoint (preview, snapshot, focus score) hangs for an extended
      period; the non-camera index page stays responsive throughout, which isolates it to
      `CameraManager._call_lock`/the picamera2 backend, not the web layer. Likely cause, not yet
      fixed: `Picamera2Backend.autofocus()` calls `autofocus_cycle(wait=True)`, which has **no
      timeout parameter** in the installed picamera2 version (checked via
      `inspect.signature`/`inspect.getsource` directly, not assumed) -- it blocks on AF-state
      metadata that may never arrive if the hardware AF search stalls, holding `_call_lock`
      indefinitely and starving every other camera call behind it. A real fix (bounded wait via
      `autofocus_cycle(wait=False)` + `Picamera2.wait(job, timeout=...)`, plus deciding what state
      to leave the camera/`AfMode` in in that case) is nontrivial and camera-reliability-critical
      enough to want sign-off before attempting, not guessed at. Recovery for now: kill the full
      uvicorn process family (see project memory on why `pkill -f uvicorn` doesn't work) and
      relaunch. *(Aaron, 2026-09-21)*
- [ ] **Regional coverage weakness: bottom-left explained, bottom-right not yet** — checked
      against all 7 real calibration frames saved 2026-09-21 (reprocessed offline, no bench time
      needed -- this is exactly why frames are saved alongside artifacts). Two hypotheses tested
      and ruled out: (1) refitting `ppm` directly linear in (x,y) instead of the current
      `relative_depth = mean_ppm/ppm` gives near-identical holdout/regional error in every run
      (e.g. run 1: 2.18% vs 2.11% bottom-right) -- the reciprocal-vs-direct functional-form
      difference is real but too small (~0.2-0.4% at this tilt magnitude) to be the cause; (2) the
      plane coefficients visibly jump between two runs taken 2 minutes apart with unchanged
      `lens_position` (6.3 both times) -- not a refocus artifact either. What the data does show:
      bottom-left is the *sparsest* quadrant in all 7 runs (n=4-24 tags, always the frame's lowest
      count) -- its weakness is plain undersampling, fixed by adding coverage there. Bottom-right
      is a different story: comparable tag count to the best-performing quadrant (top-right,
      n=42-86 both) but consistently ~1.5-2x its error regardless -- sparsity doesn't explain it.
      That's a real, sample-size-independent, consistently-located residual -- the honesty plot
      (claimed uncertainty vs actual error, PLAN.md M2 acceptance) is the next real measurement,
      not another guess. *(2026-09-21)*

### M2 — UI usability, not yet done

- [ ] **Calibration page has grown into one long page — break it into a sequential set of steps**
      instead. It's accumulated run calibration, tripwire check, live reorientation aid, and the
      honesty plot all stacked on one page this session; needs restructuring into a guided
      step-by-step flow rather than one scroll. *(Aaron, 2026-09-21)*
- [ ] **Move calibration history into a gallery** — the current "Saved calibrations (download)"
      `<details>` list (filenames + text links) should become a proper gallery: preview
      thumbnails plus a download action per entry, not a plain link list. *(Aaron, 2026-09-21)*
- [ ] **Zoomed focus preview (`/focus/roi.mjpg`) is awful quality** — Aaron: looks like a zoom of
      a reduced-quality image. Should be much higher quality to actually help focus by eye.
      `CameraManager.roi_crop_jpeg` (`camera.py`) crops from the continuous `main` video stream
      at `MAIN_SIZE` (1536×1152), not the 320×240 `lores` preview and not a full-res still --
      so it's not literally re-zooming the low-res preview, but 1536×1152 is still a small
      fraction of the 64MP sensor, and a small ROI crop of that gets magnified a lot in the
      browser. Not investigated further -- worth checking whether a dedicated higher-res crop
      (e.g. a still capture, or a larger/different stream config) is feasible without breaking
      the continuous preview or `focus_score`'s own use of the same stream. *(Aaron, 2026-09-22)*

### M2 acceptance — run in the chamber
- [ ] **Two-baseline test** *(do first)* — two independent calibrations of the same static scene,
      diff the fields. That disagreement is the floor on achievable certainty.
- [ ] **Two-height test** — calibrate at two tray heights, diff the field shapes. Proves whether one
      rare paper calibration covers every experiment.
- [ ] Tape-measure two tags → app agrees within 2%
- [ ] Roll the camera ~5° → reported as ~5°; knock it hard → verdict flips to `FAIL`
- [ ] **Honesty plot** — claimed uncertainty vs actual error at 6 positions. Check whether residuals
      are random or structured (structured opens the intrinsics evidence gate). **Tooling built
      2026-09-21, physical measurement still outstanding:** `GET
      /calibration/current/uncertainty?x=&y=` returns the claimed value at a pixel;
      `POST /calibration/honesty-plot` takes `{x, y, actual_error_pct}` points and renders the
      scatter with a y=x reference line (a "Honesty plot" panel in the UI feeds it). Also built,
      same session: a confidence heatmap (`calibration_viz.render_uncertainty_heatmap`) blending
      `UncertaintyField.local_uncertainty_pct` over the calibration frame, computed and saved on
      every `/calibration/run`, shown inline in the UI -- answers "where is confidence high/low on
      the table" visually, which is a different question from the honesty plot's "is the claimed
      number trustworthy" but was asked for alongside it. Both verified end-to-end on real
      hardware (85 real tag detections, a real heatmap over the actual bench photo). Persisting
      `UncertaintyField` needed a `CalibrationArtifact` schema bump (2 -> 3, no legacy shim) so a
      saved calibration's confidence can be queried/rendered later without re-detecting tags from
      the frame each time; also added `frame_stem` to the artifact, fixing a real gap --
      `current.json` previously had no way back to which `frames/{stem}.jpg` it came from.
      *(2026-09-21)*

---

## M3 — Capture, storage, export · *PLAN.md § M3*

- [ ] Full SQLite schema (`experiment`, `calibration`, `tray`, `capture`, `detection`,
      `measurement`, `alert`) — created here so every row has provenance from the start
- [ ] Experiment create/start/stop in the UI
- [ ] Experiment storage laid out so a whole experiment is easy to identify and remove as a unit
      (e.g. one directory per experiment, named/indexed so it's obvious which is which) — not
      commingled with calibration data or other experiments. *(Aaron, 2026-09-19)*
- [ ] Interval scheduler, 1–6 min, trust verdict per capture
- [ ] Survives reboot; recovers from failures; never silently stops
- [ ] Disk monitoring with headroom shown prominently
- [ ] Retention policy
- [ ] Storage tier: keep a significantly reduced/compressed version of each capture for long-term
      storage; full-resolution data is for the processing pipeline (segmentation, calibration,
      calculations — see M5), not for archival. RAW is captured only on explicit on-demand
      request, never automatically. *(Aaron, 2026-09-19)*
- [ ] Timelapse: scrub, play, mp4 export
- [ ] CSV export page: `measurements.csv`, `dwell.csv`, `captures.csv`, `calibration.json`
- [ ] Nice-to-have, not important: a fuller gallery for browsing captured photos (the slice-5
      "recent captures" strip only shows the latest few — this would be full browsing/paging).
      *(Aaron, 2026-09-19)*
- [ ] Nice-to-have, not important: download captures, single or as a batch. *(Aaron, 2026-09-19)*
- [ ] Nice-to-have, not important: clear/delete previously captured photos.
      *(Aaron, 2026-09-19)*
- [ ] **Acceptance:** 24 h unattended at exactly the expected count · reboot mid-run, resumes ·
      download a CSV and open it · headroom matches `df`

---

## M4 — Tray tracking · *PLAN.md § M4*

- [ ] Tray tag → identity, centroid, rotation 0–359°
- [ ] **Alert on duplicate tray tags within a chamber** — uniqueness only needs to hold within one
      chamber, not across the fleet (TODO.md's tag ID allocation entry), so nothing stops two
      trays being 3D-printed with the same ID by mistake. Detect it and tell the experimenter
      loudly rather than silently merging or misattributing readings. *(Aaron, 2026-09-20)*
- [ ] Regions: 2 × 6, defined in measurement-plane coordinates, not image pixels
- [ ] Dwell time per region per tray as a query, not a stored table
- [ ] Dirty-tag degradation: measure anyway, flag identity unknown, drop from scale solve
- [ ] **Acceptance:** 12 trays at random positions and rotations all identified · move one, dwell
      table reflects it · smear a tag with soil, degrades without crashing or lying

---

## M5 — Canopy area · *PLAN.md § M5*

- [ ] `Segmenter` interface defined first
- [ ] `ExGSegmenter` — classical excess-green, no ML, ships now, permanent baseline
- [ ] `HailoSegmenter` — stub with identical signature
- [ ] Mask → pixel area → mm² via the per-pixel scale field
- [ ] Segmentation runs against full-resolution captures, not the reduced storage copy
      (see M3 storage tier note) — resolution loss here is a measurement error, not a
      storage decision. *(Aaron, 2026-09-19)*
- [ ] Store masks to disk so areas can be recomputed without re-inference
- [ ] **Reprocess** action in the UI
- [ ] Per-measurement confidence from measured quantities only
- [ ] **Acceptance:** known-area target at 6 positions — report error *and* whether the confidence
      band contains the truth · change calibration, hit Reprocess, areas update without re-inference

---

## M6 — Alerts and hardening · *PLAN.md § M6*

- [ ] Alerts: area jumps, `DRIFT`/`FAIL`, tag detection dropping, focus drift, scheduler stalls
- [ ] Daily/weekly digest *(Could-Have)*
- [ ] Soak test
- [ ] Deployment runbook for rigs 2–15
- [ ] Each rig has an addressable name, shown in the interface *(added 2026-09-19, fleet mgmt)*
- [ ] Rig health status over an API (out of focus, experiment running, idle, etc.) for fleet
      monitoring *(added 2026-09-19, fleet mgmt)*

---

## Could-Have — only if M1–M6 land early

- [ ] Per-plant tracking within tray cells
- [ ] YOLO tray identification *(needs the evidence gate to open)*
- [ ] Height data / second camera *(needs the evidence gate to open)*
