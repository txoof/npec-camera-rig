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
        - **450–499** — corner/reference tags (4 mounted; exact IDs confirmed by reading them back
          once detection was built, rather than transcribed by eye. **Update, 2026-09-22:** the
          note below about one tag being partially obscured was stale — all 4 (450/451/452/455)
          are detected in every recent real run, verified directly against saved calibration
          artifacts, not assumed)
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
      rebuilt rig's table corners and in frame; one was initially partially obscured. **Update,
      2026-09-22:** no longer the case (or no longer a detection problem either way) — all 4 are
      detected in every recent real run, verified directly against saved calibration artifacts.
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

## Supervisor feedback, 2026-09-24 — not yet triaged into a milestone

**Future ideas suggested by the supervisor:**
- [ ] ROI selection — choose which part of the table to segment/measure, rather than always the
      whole frame *(likely M5 territory, once `Segmenter` exists)*
- [ ] A fiducial tag that marks a tray as "ignore this one" — a deliberate operator opt-out,
      distinct from the dirty-tag-degradation case already in M4 (which is a detection *failure*
      being handled gracefully, not an intentional exclusion) *(likely M4 territory)*

**Important next steps required by the supervisor:**
- [x] **Squareness guide lines — built 2026-09-24, made draggable same day (Aaron).** One fixed
      horizontal line, two fixed vertical lines (33.33%/66.67% width, all overridable by drag),
      overlaid on the live preview (`.preview-wrap`, same absolutely-positioned pattern as the
      existing ROI box). Aaron asked to drag them onto real objects in frame, which needs the
      preview's existing click-to-place-focus-ROI handler out of the way — added a **Focus /
      Square mode toggle** (two buttons above the preview) instead of overloading one click
      target: Focus mode is the preview exactly as before (click places the ROI); Square mode
      hides that handler, shows the guide lines, and makes each one draggable (Pointer Events API
      + `setPointerCapture`, so a drag started on the thin line keeps tracking even once the
      pointer leaves it — no document-level listeners to add/remove by hand). Each line's hit
      area is widened well past its visible 2px via a `::after` pseudo-element, since the visible
      line has to stay thin to read as a straightedge. Client-side only, no server round trip;
      dragged positions aren't persisted (reset to defaults on reload) — a straightening aid, not
      a measurement, so nothing to unit-test (CLAUDE.md: HTML/CSS/JS-only changes need a browser
      look, not pytest). **Not yet visually or interactively confirmed in an actual browser** — no
      browser access from this environment; please eyeball it and try dragging each line before
      calling this done, same caveat as slice 3's responsive-layout entry.
- [ ] Fix zoom quality — should be the highest quality available, not degraded
      *(likely M1 territory)*
- [x] **Feedback on whether the sensor is co-planar with the table — built 2026-09-24.** Checked
      CLAUDE.md's evidence-gate table first, per the note this item carried. Tripwire roll (in-
      image rotation between two frames) and the radial residual plot (lens-distortion signature)
      don't answer this question -- neither is a tilt-vs-table-plane measurement. What does: the
      scale field's own fitted plane already used for `describe_scale_variation()` is direct
      evidence of a gradient across the table, which co-planarity would make flat. Added
      `describe_coplanarity()` in `calibration.py` (wired into `build_install_report()`, so it
      shows up in the install report alongside scale variation): reports which corner of the
      observed tag cloud reads nearer the camera and by how much, from the same fit, no new
      measurement. Deliberately stops short of a tilt angle -- converting the gradient to degrees
      needs the camera-to-table standoff distance, which Aaron has ruled out measuring on this
      rig (fragile); the line says so explicitly rather than guessing. Unit-tested with synthetic
      detections (known tilt direction recovered; flat field reports ~0%). See the install-report
      entry above.

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
- [ ] **Autofocus, manual lens-position controls, focus peaking, and the sharpness readout should
      all be linked to the Focus/Square mode toggle** (the toggle built 2026-09-24 for the
      squareness guide lines, see M2's supervisor-feedback section) — only show them in Focus
      mode, hide them in Square mode, instead of always visible regardless of which mode is
      active. *(Aaron, 2026-09-25)*
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
- [~] **Install report** — `describe_scale_variation()`, `describe_coplanarity()`,
      `describe_coverage()`, `build_install_report()` in `calibration.py`. Scale variation is
      evaluated over the *observed tag cloud's* bounding box, never the frame -- extrapolating
      the fitted plane past where tags were actually seen would be the report lying about its
      own coverage. Coverage verdict defaults to PLAN.md's 2% tape-measure acceptance target as
      the sufficient/insufficient threshold. **Co-planarity feedback, built 2026-09-24** (see the
      supervisor-feedback section below): `describe_coplanarity()` reads the same fitted
      `ScaleField` scale-variation already reads and reports which corner of the tag cloud sits
      nearer the camera (higher px/mm) and by how much -- direction and magnitude only, no angle.
      **Roll and a tilt *angle* are still not built** -- a tilt angle isn't recoverable from a
      single photo without a physical standoff-distance measurement Aaron has ruled out (rig is
      fragile); **framing is also not built** -- it needs a real capture's corner-tag/frame-edge
      check. `build_calibration_report()` is the entry point a real caller should use — it builds
      the field, positions, and global/regional coverage from one consistent set of detections
      before assembling the report lines, so a field from one capture can't get paired with
      coverage from another (`build_install_report()`'s own parameters aren't cross-checked, by
      design — useful for testing each line in isolation). Unit-tested with synthetic detections.
      *(2026-09-20, updated 2026-09-24)*
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
      be exactly 4 (a corner tag could still be knocked loose or obstructed later; an earlier note
      here about one currently being partially obscured was stale and is corrected above).
      Lens-position capture/recording is now wired up too, via `POST /calibration/run` (see the
      calibration mode UI entry above).
      **Homography built, 2026-09-22:** `TableFrame`/`build_table_frame()` in `calibration.py` --
      pixel <-> table-fraction transform from the four corner tags' own centres (a hand-rolled
      4-point DLT, position-only, no `ScaleField` input so mm can't leak in). Completes this
      item's own previously-flagged gap ("nothing in M2 consumes a homography yet"). Backed by two
      homography tests run against real saved calibration frames (not just argued from docs): a
      single tag's own 4-corner homography does *not* generalize (~10% size error by the far side
      of the frame, r=0.72 with distance from the source tag); the four corner tags' wide-baseline
      homography does (~1-6% shape consistency, r=-0.05, essentially uncorrelated with distance
      from centre). Consumed by `calibration_viz.render_table_view()` -- the same scale-residual
      and area-shape fields the existing heatmaps draw, painted instead on a straightened,
      position-indexed table view, wired into `POST /calibration/run` (two new URLs,
      `table_view_url`/`table_view_shape_url`) and the calibration UI panel. Position only, never
      mm -- kept strictly separate from `ScaleField` (a different physical plane, tray height vs.
      table edge), per CLAUDE.md's evidence gate against inventing cross-plane corrections. The
      tray-height repeat of this same trust-field exercise (the actual measurement plane, per
      Aaron's supervisor) is real, separate future work, not started here.
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

- [x] **Lens position ignored after any full-res capture, fixed 2026-10-01.** `capture_full_res`
      reconfigures to a still configuration and back; `configure()` dropped manual AfMode and
      LensPosition, and from then on every LensPosition write was ignored until a server restart
      (measured: set 6.18, read 6.44; a lens sweep of 7 captures all came out at 6.10; autofocus
      never returned and held the camera lock). Fix: the still configuration carries
      `AfMode: 0` and the last set LensPosition, both are re-applied after switching back, and
      `set_lens_position` always sends manual AfMode. Verified on the rig: a capture after a
      move records the new position.
- [x] **One consistent lens drive, built 2026-10-01 (Aaron: drive the lens to the set distance in
      a sane way, then manage the error).** The central low reading depends on lens position and
      on how the lens got there (North 4 report, `~/scratch/north4-hotspot-report.md`). Locking
      focus and the startup restore now both go through `CameraManager._drive_lens`: step to 0.3
      below the target, pause 1 s, set the target, wait until the camera reports it (up to 60 s,
      else "focus is not locked"). The lock records the position set, not the preview's report.
      Verified on the rig: lock survives a restart (lens back at 6.18, locked); the first capture
      after a restart records 6.18 (it would have been 1.0: the startup replay bypassed the
      remembered position); a lock right after a capture waited 24 s for the camera and locked
      at the set 6.26. The page shows "waiting for the camera to confirm" meanwhile.
- [~] **After a full-res capture, the preview reports a new lens position about 45 s late
      (measured 2026-10-01, 44.8 s; later moves 0.5 s).** Captures are not affected, and Lock
      focus now waits for the camera instead of recording a stale value (above). Cause not found;
      only the live preview and its sharpness reading lag.
- [x] **Locked focus is lost on every server restart (Aaron, 2026-09-30).** Fixed 2026-10-01 by
      the consistent lens drive above: the saved lens position is driven back at startup and the
      lock restored once the camera confirms it.
- [ ] **Validation round should check focus before sheets (Aaron, 2026-09-30).** A round with
      the wrong focus usually also finds 0 sheets, and the sheet-placement check runs first and
      stops there, so the message blames the sheets and never mentions focus. Fix: in
      `capture_validation_round` (app.py), check focus lock and lens position against the
      calibration first and report that reason even when no sheets are found.
- [ ] **Focus lock wording and a visible status (Aaron, 2026-09-30).** Buttons read "Lock
      focus" and "Unlock focus". Next to them, a status line always shows the current state:
      "Focus status: UNLOCKED" or "Focus status: Locked 6.38" (the locked lens position). Found
      when a restart left focus locked at 6.50 while the calibration was taken at 6.18, and
      nothing on screen made the difference visible. Consider showing the active calibration's
      lens position next to it so a mismatch is obvious.

- [ ] **`/code-review --level high` findings, 2026-09-28, m2-wizard-order-and-focus-gate PR -- 5
      fixed same session (table-dims persisted before the readiness gate check, a stale
      in-flight level.jpg request could overwrite a just-toggled Corner check mode, the delta
      view silently dropped the tag-size row, /calibration/readiness polled at the old
      un-throttled rate, a stray em dash in newly authored text), 2 deferred here with reasons:**
  - **Wizard step identity is scattered as bare integer literals** (`step: 2`,
        `isActiveStep(3)`, `isActiveStep(4)`, etc. across `setup_calibration.html`) instead of
        one named mapping. Real -- this branch is itself a step reorder, and a future one (the
        Lock-focus gate's own step placement is already logged as undecided above) has to find
        and update every scattered literal by hand, with nothing catching a missed one. Not
        fixed now: introducing a named-step abstraction on the same PR that just finished
        stabilizing the step order is real regression risk for a refactor with no behavior bug
        behind it -- revisit the next time the step order actually changes.
  - **Three near-identical hand-rolled polling loops** (`pollScore` in `_focus_controls.html`,
        `pollLevelOverlay`, `pollCalibrationReadiness`) duplicate the same self-rescheduling
        `setTimeout` pattern with no shared helper, and this PR's own throttle fix (finding
        above) had to be applied to two of the three separately because they'd already drifted.
        Not extracted now: the third one's different shape (levelOverlayInFlight's guard, error
        swallowing) means a shared helper is a real design decision, not a mechanical extraction
        -- revisit if a fourth poll loop is ever added, which would be the point this
        duplication starts costing something.

- [x] **Auto exposure only fires once per tick, not continuously — fixed 2026-09-25.** Aaron,
      2026-09-22: ticking "Auto exposure" adjusts exposure once, then holds still even as real
      lighting changes; unticking and re-ticking forces one more adjustment. The 2026-09-22 note
      below (kept for the record) had ruled out this app fighting AE via any *repeated* write —
      correct as far as it went, but missed two real, independently confirmed causes: (1)
      `capture_full_res()`'s stop/reconfigure/start cycle silently dropped `AeEnable`/`AwbEnable`
      without updating this app's own cache, so a calibration run or "Capture" would leave the
      camera off AE/AWB while the UI still claimed both were on; (2) a stale persisted manual
      `ExposureTime`/`AnalogueGain` (found live in `rig.db`) replayed on top of `AeEnable=True` on
      every server restart, re-arming picamera2's `ExposureTimeMode`/`AnalogueGainMode` manual
      latch — confirmed directly against the installed picamera2 source
      (`CompletedRequest.release()`). Fixed by centralizing a single guard in
      `Picamera2Backend.set_control` (manual `ExposureTime`/`AnalogueGain` writes are ignored
      while `AeEnable` is on, mirrored in `SyntheticBackend` for testability) so the HTTP
      endpoint, the persisted-settings replay, and the post-full-res-capture restore are all
      covered by one rule. Verified live: a restart no longer replays the DB's stale
      `ExposureTime=3064701`, and Aaron confirmed the live preview looks correct afterward.
      `m2-auto-exposure-fix`, merged as #3. Deferred, separate gap logged below (manual
      exposure doesn't survive a full-res capture).
      **Original note, 2026-09-22:** ticking "Auto exposure" adjusts exposure once, then holds
      still even as real lighting changes; unticking and re-ticking forces one more adjustment.
      Checked this app's own code path (`camera.py`'s
      `Picamera2Backend.set_control`/`CameraManager.set_control`): it makes one
      `set_controls({"AeEnable": True})` call and never re-writes `ExposureTime`/`AnalogueGain`
      afterward, and the UI's controls panel (`index.html`) only reads `/controls` once at page
      load -- no polling loop that could be re-locking it by echoing a stale value back. So
      nothing in this app is fighting AE after it's enabled; if it's only converging once, that's
      either a picamera2/libcamera behaviour needing its own investigation, or something with the
      camera_controls read happening at a moment that freezes it. Not reproduced against real
      hardware by Claude (no camera access in this environment) -- needs an on-hardware check
      before guessing further.
- [x] **Live reorientation aid never actually works — fixed 2026-09-25.** `POST
      /calibration/orientation/zero` refused twice on real hardware (2026-09-21) with "no corner
      tags detected." Confirmed root cause directly on real hardware before changing anything:
      pulled a live frame from each stream and ran `detect_tags` on it -- the `lores` stream
      (320x240) found 0 corner tags, the `main` stream (1536x1152, the same continuous stream
      `/snapshot.jpg` and the focus ROI crop already use) found all 4 plus 272 tags total.
      **Fix:** added `CameraManager.capture_array()` (raw main-stream frame, mirroring the
      existing `capture_preview_array()`) and switched both orientation endpoints
      (`/calibration/orientation/zero` and `/calibration/orientation/live`) to it. No
      reconfigure, so no capture-then-autofocus hang risk and no full-res ~8.5s round trip --
      appropriate for a continuously-polled live aid. Verified end-to-end on real hardware after
      the fix: `zero` now returns `{"corner_tags": [450, 451, 452, 455]}` instead of 409, and
      `live` returns a real `OK` verdict with `roll_deg` ~0.006° against that zero point. 217/217
      unit tests still pass (all orientation tests monkeypatch `detect_tags` directly, so they
      didn't depend on which stream fed it -- verified the switch didn't remove real coverage of
      that method itself).
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
      **Update, 2026-09-24:** reproduced again on an abandoned experimental branch (a continuous
      full-res video mode, since dropped for unrelated reasons) via its own `stop`/`configure`/
      `start` reconfigure followed by autofocus -- confirms this isn't specific to a calibration
      capture, any pipeline reconfigure followed by autofocus can trigger the same hang. Still not
      fixed; still the same sign-off-gated change, not two separate bugs to design around.
- [x] **`/preview.mjpg` and `/focus/roi.mjpg` never noticed a disconnected client, and a stuck
      `_call_lock` (e.g. the wedge above) turned that into a full server hang, not just a leaked
      stream.** Found by Aaron, 2026-09-28, while testing a since-reverted focus-crop toggle on
      `m2-sharp-focus-toggle` (53 threads, most in `futex_do_wait`, full unresponsiveness
      including a plain `GET /`). Root cause confirmed 2026-09-29 by reading the installed
      Starlette/anyio source directly, not assumed: `_mjpeg_frames` was a sync generator, so
      Starlette ran each `next()` through `anyio.to_thread.run_sync` with
      `abandon_on_cancel=False` -- implemented as `CancelScope(shield=True)` -- meaning a client
      disconnect cannot interrupt a call already in flight, only stop the loop at the boundary
      before the *next* call starts. The old code's `time.sleep` FPS throttle ran inside that
      same shielded call (after the yield, before the next iteration's frame grab), so a live
      stream held its worker thread almost continuously, not briefly. Uvicorn here declares ASGI
      spec_version 2.3, so Starlette's disconnect signal is real (a task-group race against
      `receive()`, not silently dropped) and does cancel the outer task on a genuine disconnect --
      but every frame grab goes through the single `CameraManager._call_lock`, also used by
      `autofocus()`/reconfigure. If that lock is held a long time (the wedge bug above being the
      known way that happens), the shielded call blocks past the point where cancellation could
      ever reach it, pinning one of anyio's 40 pooled worker threads permanently; each reload
      opened a new stream whose first frame grab also blocked on the same lock, consuming another.
      Once the pool was exhausted, every other sync route -- including a plain page load --
      blocked waiting for a thread too. Whether the wedge bug specifically was the trigger during
      that session's toggling is not confirmed (no hardware access to reproduce this session),
      only that it is the mechanism that fits all the observed evidence and matches how the two
      bugs interact.
      **Fixed on `m2-mjpeg-stream-lifecycle`, not yet stress-tested on hardware:** (1)
      `_mjpeg_frames` is now an async generator that awaits `Request.is_disconnected()` before
      each frame and uses `asyncio.sleep` for the FPS throttle -- an ordinary, cancellable await,
      not a shielded one; only the actual blocking camera call goes through the threadpool now.
      (2) `CameraManager.preview_jpeg`/`roi_crop_jpeg` bound their `_call_lock` wait to
      `STREAM_LOCK_TIMEOUT` (2s) and raise `CameraBusyError`, which the generator treats as "skip
      this frame," so a contended lock now degrades one stream to occasional skipped frames
      instead of leaking a thread forever. Start/end/frame-count logging added per stream
      (`logger.info("mjpeg stream %s#%d: ...")`) as the observable for the stress test below.
      **Deliberately not fixed here (narrower scope, approved by Aaron):** every other
      `_call_lock` use (`focus_score`, `capture_array`, the controls routes, autofocus itself)
      is still an unbounded wait. None of those are long-running loops the way the streams are,
      so they don't self-reinforce into thread-pool exhaustion the same way, but a slow one could
      still make a request hang. Revisit if that's ever observed.
      **Stress-tested against the live server, 2026-09-29 (Aaron confirmed nobody else was using
      the rig first):** 80 rapid, overlapping, short-lived (curl `-m 0.25`, a clean TCP close --
      the same disconnect signal a closed browser tab produces) opens of both `/preview.mjpg` and
      `/focus/roi.mjpg` against the live worker (pid 86063). Thread count rose 14 -> 53 during the
      burst (anyio spinning up worker threads to service it, capped near its 40-token default
      limiter plus other process threads -- not itself a leak), then returned to the exact
      baseline of 14 once anyio's 10s idle-worker prune window had passed and a few follow-up
      requests triggered it, confirmed via `/proc/86063/task` counts before, during, and after.
      `curl -m 5 GET /` succeeded in under 10ms at every point in the storm and after -- the
      server was never unresponsive, unlike the original reproduction where a plain `GET /`
      timed out. `wchan` alone (`futex_do_wait`) could not distinguish a stuck lock wait from an
      idle anyio worker parked in `queue.get()` -- both are futex-based -- so the settle-back to
      baseline, not the wchan reading, is what confirms these were the benign kind. Not confirmed
      as a leak-proof guarantee for every possible contention pattern, only that this specific
      reproduction (the one that hung the server on 2026-09-28) no longer does.
      **Known gap found while testing, not fixed here:** the per-stream start/end log lines added
      for this test never appeared in `uvicorn.log` -- `logger = logging.getLogger(__name__)` in
      `app.py` has no configured handler/level (default root logger level is `WARNING`), so
      `logger.info(...)` calls are silently dropped; only uvicorn's own loggers are configured.
      The lines are harmless as written and will work once app-level logging is configured, but
      were not the evidence used above -- thread counts and response times were.
      **`/code-review --level high`, PR #15, 2026-09-29 -- 4 fixed same session (duplicated
      lock-acquire/release block between `preview_jpeg`/`roi_crop_jpeg` extracted into
      `CameraManager._stream_call_lock`; both now document that they can raise `CameraBusyError`;
      the busy-skip path in `_mjpeg_frames` no longer sleeps a full extra `min_interval` on top of
      the time already spent blocked in a failed acquire; the "succeeds once available again"
      test now actually contends the lock from another thread instead of calling into an
      uncontended manager), 2 deferred here with reasons:**
  - **`STREAM_LOCK_TIMEOUT` bounds only the wait to *acquire* `_call_lock`, not how long the
        backend capture call can hold it once acquired.** If `capture_preview_array()`/
        `capture_array()` itself hangs (the same class of driver-level hang already documented
        for autofocus+reconfigure above), the stream's `run_in_threadpool` call never returns and
        pins a worker thread exactly as the pre-fix bug did -- this fix guards the queue for the
        lock, not a hang while holding it. Not fixed now: bounding a call already in progress
        needs either abandoning the thread (anyio's `abandon_on_cancel=True`, which stops blocking
        the async side but leaves the thread, and whatever it's doing to the hardware, running
        unsupervised) or a lower-level timeout into the backend call itself -- the same
        design-needs-sign-off situation as the autofocus+reconfigure wedge bug, not a mechanical
        fix to slip into a review-response commit. Revisit together with that bug.
  - **No test exercises real `Request.is_disconnected()`/ASGI disconnect semantics** -- every
        `_mjpeg_frames` test drives it through a hand-written `_FakeRequest` returning a fixed
        bool, so a future Starlette/anyio behavior change here wouldn't be caught by `pytest`.
        Not fixed now: a real mid-stream disconnect needs an actual ASGI transport, which is
        exactly why the existing `_mjpeg_frames` test comment already excludes a full HTTP round
        trip from the unit tier. The live-server stress test above (a real TCP close via curl) is
        the actual verification for this mechanism, deliberately at the hardware tier, not
        pytest's.
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
- [ ] **`SyntheticBackend` emits 3-channel frames; real hardware now emits 4-channel (`XBGR8888`,
      per the color-swap fix above -- `f82f12c`).** Found by `/code-review` (2026-09-24), verified
      directly on real hardware, not trusted from the diff alone: `Picamera2Backend.capture_array()`
      genuinely returns `(H, W, 4)`, and every consumer (`array_to_jpeg`, `to_grayscale`,
      `detect_tags` via the calibration endpoints) handles it correctly -- confirmed by capturing a
      real frame through the actual pipeline and looking at the resulting JPEG, colors correct, not
      just checking it doesn't crash. So this is a **test-fixture gap, not a live bug**: the entire
      212-test unit suite exercises a frame shape real hardware hasn't produced since that fix
      landed, which means a future change to any consumer that only breaks on the 4th (padding)
      channel would pass every unit test and only surface on real hardware. Not fixed here --
      changing what `SyntheticBackend` emits changes what all 212 tests exercise, a call for Aaron,
      not something to slip in as a side effect of a review pass.
- [ ] **Several UI button handlers have `try`/`finally` but no `catch`** (`index.html`: run
      calibration, zero orientation, tripwire check, honesty plot) — found by `/code-review`
      2026-09-24. A `fetch()` rejection (network drop/timeout, plausible over Tailscale) silently
      re-enables the button via `finally` with no error shown -- indistinguishable from never
      having clicked. Needs a UX decision on how errors should surface (toast? inline message?),
      not a one-line fix.
- [ ] **Tag-size auto-prefill can launder a placeholder into "measured"** (`index.html` ~line 1045)
      — found by `/code-review` 2026-09-24. `/calibration/current`'s response has no `is_default`
      flag, so the UI can't tell "this number was calliper-measured" from "this is the unmeasured
      `ASSUMED_CALIBRATION_TAG_SIZE_MM` placeholder" when it prefills the tag-size input from the
      last run. If the operator doesn't notice and edit it, running calibration again sends the
      placeholder back as an explicit, user-entered value -- exactly the derived-not-measured
      failure CLAUDE.md's evidence gate exists to catch, just laundered through a form field
      instead of a hardcoded constant. Needs an API change (carry `is_default` through) plus a
      frontend change (warn or refuse to prefill from a default) -- not done here.
- [ ] **Honesty-plot form asks for raw pixel coordinates and a hand-computed error percentage**
      (`index.html` ~line 594) — found by `/code-review` 2026-09-24, and it's a direct hit on
      CLAUDE.md's "operator inputs must be physical actions" rule: the table headers are literally
      "x (px)", "y (px)", "actual error (%)", with instructions telling the operator to read a
      pixel position off the frame and type it in. This is existing, already-shipped M2 UI (the
      honesty-plot tooling, 2026-09-21), not something new -- flagging it now because a fresh
      review pass is what caught it, not because it just landed. Needs a product decision on which
      physical action replaces this (clicking the target on the displayed image? typing a calliper
      length and letting the app find the nearest detected feature?) before touching it.
- [ ] **`_outer_edge_span_to_centre_distance_mm` assumes corner tags are mounted axis-aligned with
      the table** (`app.py` ~line 276), stated as fact with no runtime check or `is_default`-style
      flag, unlike its sibling tag-size assumptions in the same function — found by `/code-review`
      2026-09-24. On the physically-rebuilt rig (CLAUDE.md: re-measure everything), if the corner
      tags are even slightly off-axis this silently under-subtracts the table span, and the UI
      still prints an unqualified "to scale: WxL mm" caption. A measurement-discipline call for
      Aaron, not something to guess a tolerance for.
- [ ] **A manually-set ExposureTime/AnalogueGain (AE off) doesn't survive a full-res capture** —
      found by `/code-review` 2026-09-25, reviewing the auto-exposure stuck-image fix (see
      `m2-auto-exposure-fix`). `Picamera2Backend`'s `_control_cache` only tracks `AwbEnable`/
      `AeEnable` (they're write-only — `capture_metadata()` doesn't echo them back), so
      `capture_full_res()`'s post-capture restore can only reapply those two. If AE is off and
      the operator has set a specific measured exposure/gain, a full-res capture (calibration or
      "Capture") silently drops it back to the tuning file's default afterward, with no UI
      indication anything changed. Deferred, not fixed alongside the AE-stuck bug: would need
      caching the last explicitly-set manual value too, a small but separate change.
- [ ] **`/code-review --level high` findings, 2026-09-26, PR #10 -- 4 fixed same day (see the PR),
      5 deferred here with reasons:**
  - **The "Diagnostics" `<details>` panel (Step 5) now also hides the Honesty plot and "Saved
        calibrations" list** — nested three sections deep behind one collapsed toggle, when the
        Honesty plot specifically is PLAN.md's own M2 acceptance-test tool and arguably shouldn't
        be hidden at all. Not fixed now: this exact area is about to be reworked twice over —
        the already-approved "tidy up the calibration result messages" split (headline vs.
        Diagnostics) above, and the calibration-history browser
        (`reference/plans/calibration-history-browser.md`), which replaces "Saved calibrations"
        entirely. Resolve the nesting depth as part of one of those, not as a standalone fix that
        would just get redone.
        **Resolved 2026-09-26**: the calibration history browser (below) moved to its own page
        (`/setup/calibration-history`), so "Saved calibrations" is no longer nested under
        Diagnostics at all. The Honesty plot is still one level deep under Diagnostics, unchanged
        by this fix -- the separate "tidy up calibration result messages" rework (above) is where
        that's addressed, still open.
  - **Step 2's live co-planarity overlay and `check_tripwire`'s baseline-relative drift reuse the
        same 3%/8% bands (`tripwire.py`'s `DEFAULT_SCALE_DRIFT_PCT`/`FAIL_PCT`), and neither has
        actually been measured yet** — both are explicitly marked "Provisional" in `tripwire.py`
        itself, pending the still-open M2 acceptance test below ("Roll the camera ~5° → reported
        as ~5°; knock it hard → verdict flips to FAIL"). Not a new problem, and not silently
        presented as measured in the code (the docstring says so) — the gap is that Step 2's UI
        copy states "green ≤3%, amber 3-8%, red >8%" with no such caveat visible to the operator.
        Whether these two different physical questions (has *this* corner changed since a
        baseline, vs. do different corners currently disagree with each other) should even share
        one threshold is a real question, not just a wording fix — surfacing it for Aaron rather
        than picking an answer. **Plan-doc cross-reference resolved 2026-09-26**: the shipped
        calibration history browser doesn't show coplanarity at all -- it was deferred (see the
        item below), so the plan doc's threshold-reuse recommendation was stale and has been
        corrected there. The underlying Step 2 UI caveat-visibility problem this bullet is
        actually about is untouched and still open.
  - **The per-tag detection cache (`_cached_frame_detections`/`_frame_detection_lock` in
        `app.py`) is a bandaid, not a fix** — it stops four simultaneous diagnostic requests from
        OOMing at once by caching one frame's detections, but every *new* view of a saved run's
        diagnostics still re-decodes the full-res frame and re-runs the whole tag detector from
        scratch, because `CalibrationArtifact` never persists per-tag scale-residual/
        shape-distortion data. The real fix is a schema change (persist per-tag data at
        calibration time, once), which is exactly the performance question flagged as an open
        decision in the calibration-history-browser plan doc ("re-detecting tags from every saved
        frame just to render a list could be slow") — resolve there, not as an isolated fix here.
  - **The whole camera-controls widget (~150-180 lines: labels, exposure-time formatting, control
        rendering, AE-dependent disabling) is duplicated verbatim between `setup_focus.html` and
        `setup_calibration.html`** — already a known, deliberate tradeoff from the Setup-pages
        redesign (no shared-include mechanism exists in this plain static-HTML codebase; see
        `m2_calibration_progress.md` memory: "the two copies must be kept in sync by hand"), not
        new. Logging the code-review hit here so it doesn't look unaddressed — no fix planned
        unless the duplication actually causes a real bug from the two copies drifting apart.
  - **Five near-identical "write a heatmap JPEG under a `{stem}_{suffix}.jpg` name" functions in
        `calibration_store.py`, each paired with a matching "does that file exist → build its URL"
        block repeated in three places in `app.py`** (`run_calibration`, `list_calibration_
        artifacts`, `current_calibration`) — real duplication, each new heatmap kind requires
        hand-copying both. Deferred: a refactor here touches every calibration-diagnostics
        endpoint at once, real regression risk for a DRY-only change with no behavior bug behind
        it; revisit if a sixth heatmap kind is ever added, which would be the point this
        duplication actually starts costing something.
- [ ] **`/code-review --level high` findings, 2026-09-26, calibration-history-browser PR -- 5
      fixed same session (corrupt-file 500s on promote/delete, delete's active-guard silently
      skipped when `current.json` is unreadable, `list_calibration_artifacts` missing `TypeError`
      alongside `ValueError`/`KeyError`, "Load diagnostics" firing the rank/best-worst/radial/dome
      plots without checking a frame exists, the history card missing a frame-view link), 5
      deferred here with reasons:**
  - **`is_current` is computed by comparing `created_at` string equality against `current.json`,
        not by recording which stem `current.json` was promoted from** — two saved artifacts
        sharing the same `created_at` (a hand-restored backup, a copied fixture) would both read
        as "Active," and promote/delete's identity checks would be ambiguous between them. Real,
        but requires an artifact-duplication path that nothing in normal operation produces
        (every write goes through `save_calibration`'s own timestamp-generated stems). Fixing it
        properly means `current.json` gaining a record of its own source stem -- a schema
        question, not a one-line fix; revisit if it's ever seen to actually happen.
  - **`_saved_calibration_path`'s traversal guard is hand-rolled (`resolve()` + parent comparison)
        instead of checking the stem against `list_calibrations()`'s own enumeration** — the
        current guard is correct and already tested (traversal, and the `current` pointer itself,
        both rejected); routing a stem through a full directory listing for every promote/delete
        call is a worse trade (an extra directory scan on every request) for the same safety
        property. Not changing it; if a second endpoint ever needs the same stem-to-path
        resolution, that's the point to extract a shared helper, not before.
  - **`delete_calibration`'s heatmap-suffix list is a third hardcoded copy of the same five
        filenames** already flagged above as duplicated between `calibration_store.py` and two
        places in `app.py` — same deferred reasoning applies: revisit together if a sixth heatmap
        kind is ever added.
  - **`list_calibration_artifacts` re-parses the active entry's JSON twice** (once via
        `load_current_calibration()`, again via `load_calibration(path)` in the loop) — real, but
        it's a small on-disk JSON file, not the 64MP re-detection this codebase actually watches
        the cost of; skipping the redundant parse needs a way to tell "is this loop iteration's
        stem the one `current.json` came from" without string-comparing `created_at` again, which
        is the same schema gap as the `is_current` item above. Fix together, not separately.
  - **`promote_calibration` rewrites the promoted stem's own JSON file** (a full atomic
        write-then-rename) even though its content is byte-identical to what was just read from
        that same path — only the `current.json` write actually changes anything. This is
        `save_calibration` used exactly as the plan doc asked ("a call to this with an
        already-loaded artifact... not new logic"); giving it a "skip the redundant write" mode
        would add a branch to a shared, already-tested function for a negligible cost on an
        infrequent action. Not worth it unless promote turns out to be hot enough to matter.

### M2 — UI usability, not yet done

- [ ] **Next slice: validation drift and suspect-sheet flags, with a fault test (planned
      2026-09-30, replaces the old slice 3 order).** The validation page should show when a
      slot's readings are not consistent between rounds, and name the sheet responsible.
  - **Status:** "Validated" only when no slot's median moved more than
        `MEDIAN_DISAGREEMENT_PCT` (1.5 points) across counted rounds; otherwise "Not
        consistent: North 2, South 5, ..." (a status, not a block).
  - **Suspect sheet, per round:** a sheet whose median differs from the same slot's median in
        the other rounds by more than the threshold is named: full-frame image with a red
        border around that slot and "the sheet on South 5 reads 7.8% small compared with other
        rounds: check it with callipers" (Aaron: full frame, not a crop).
  - **Fault test, in the chamber:** use a 30 mm sheet printed at the wrong scale (a 96% print
        reads about 7.8% small in area). (1) Control: 3 normal rounds, expect no flags (the
        2026-09-30 sessions moved at most 1.5 points). (2) Moving fault: the 96% sheet on a
        different slot each round (North 2, South 5, North 5), expect those slots flagged and
        the sheet named each round. (3) Stationary fault: the 96% sheet on North 2 all 3
        rounds, expect no drift flag, only a steady -7.8% there: documents the limit that a
        bad sheet which never moves looks like a bad slot, which is why sheets must change
        trays every round. (4) Wrong-height tray (Aaron, 2026-10-01): a normal sheet on one tray
        raised by a callipered spacer, the raised tray on North 2, South 5, North 5 in rounds
        1-3. Expect it to read large by about 2h/D (D, the camera height, not yet measured on
        the rebuilt rig; at about 1.5 m: 10 mm reads about 1.3% large, below the 2.5-point
        limit; 30 mm about 4%, flagged). Run at about 10 mm and about 30 mm to see where
        detection starts.
  - **Run 2026-10-01, all as expected** (89% sheet, callipered, reads about 21% small):
        (a) 20261001T081146 Validated, largest median move 1.02. (b) 081427 named R1 North 2
        -20.9, R2 South 5 -20.9, R3 North 5 -21.3, no good round named. (c) 082037 North 2
        steady -20.4 to -20.5, no round flag; this led to the steady-offset check below.
        (d) 082459, tray 175 mm against the normal 100 mm, camera 1482 mm above the table:
        predicted (1382/1307)^2 = 11.8% large, measured 11.2 to 12.0 at North 2, North 4,
        South 6. So about 0.145% of area per mm of tray height: 2.5 points is about 17 mm.
        Not explained: (c) round 1 "found 11 calibration sheets".
  - **Steady-offset check, built 2026-10-01 (Aaron: a consistently high or low slot is
        worth flagging).** A slot whose median of per-round medians sits more than 3.0 points
        from the all-slot median is "Not consistent"; the all-slot median more than 2.5 from 0
        is one "every slot reads off since the calibration" problem. In 8 real sessions normal
        slots sat at most 2.15 from the all-slot median (always North 4, steady -1.6 to -2.2,
        a real offset at that slot worth a look) and the table at most 0.66 from 0.
  - **Automated tests:** cases (2) and (3) with synthetic detections (`tests/helpers.py`
        tray builders, a scaled sheet as in `test_a_small_sheet_shows_in_its_own_slot_only`).
  - **Not usable as the fault:** the 50 mm sheets use IDs 450-499 (the corner range), which
        the validation map ignores; swapping one in for a 30 mm sheet only gives "found 11
        sheets". Its IDs 450-455 could also confuse the corner-tag checks. Confirm the IDs on
        the sheet at hand before using it.
  - Then the old slice 3: validation status on the Setup and calibration pages, the wizard's
        push to validate, and status in the site menu once a consistent menu exists.
- [ ] **No contractions on any web page (Aaron, 2026-09-30).** Write "cannot", "is not", "do not"
      in all page text, JS strings, and server messages the pages show. The validation page and
      its messages are done; still to do (count on 2026-09-30): setup_calibration.html 35,
      _focus_controls.html 4, setup_calibration_history_diagnostics.html 1,
      setup_health_check.html 1, plus server messages in app.py outside validation.

- [~] **Validation page needs too much scrolling on the target 1024x768 monitor (Aaron,
      2026-09-30).** Each round the operator has to scroll from the status line, past the
      full-width map and the 12-row per-round table, down to the Capture round button, then back
      up to read the result. Fix so that one round (read status, press Capture round, see what
      changed) works without scrolling at 1024x768: for example a smaller map with the table
      beside it, a more compact table, and the history list collapsed or moved below. Keep
      controls below the image they affect (see the controls-below-images rule). Check in a real
      browser at 1024x768 before calling it done.
      **Built 2026-09-30, awaiting Aaron's browser check:** Start/End validation and Capture
      round at the top, map and per-round table side by side, date above the map, help text
      collapsed. Headless Chromium at 1024x670 (768 minus browser toolbar) shows map, table and
      note without scrolling.

- [x] **Calibration wizard step order fixed, 2026-09-28.** Focus previously ran before any tray
      or tag was in frame (`data-step="1"`, before sheet placement at `data-step="4"`). Reordered
      to: 1 place calibration/corner sheets, 2 confirm focus, 3 check squareness, 4 confirm
      coplanarity, 5 run calibration, 6 report, 7 remove sheets. Two constraints decided the final
      order: sheets must be down before focus, since focus needs a real target at tray height,
      not the bare table; and focus must happen before squareness/coplanarity, since those are
      visual checks that need a sharp image to judge by eye. `m2-wizard-order-and-focus-gate`
      branch. Confirmed working end to end in the browser, 2026-09-28.
      **Note:** the two HIGH PRIORITY entries that originally raised this (wizard order, Lock
      focus gating) and the zoom-quality entry next to them existed only in
      `m2-ui-organization-and-text`'s uncommitted, since-stashed working tree -- never actually
      committed to `main`. This entry and the two below replace them as the real record.
- [ ] **Give "Lock focus" a real function -- design decided 2026-09-28, not yet built.** Traced
      the code: the locked state only fed the on-screen label and a manual capture's sidecar
      JSON; `/calibration/run` read the raw current lens position directly, never the lock.
      Decided: (1) any manual lens move or autofocus clears the lock (`_locked_lens_position`),
      no tolerance measurement needed; (2) `/calibration/run` and (3) the wizard both refuse to
      proceed unless focus is currently locked AND all 4 corner tags are detected in a live
      main-stream frame (all 4, not `check_tripwire`'s 2-tag minimum -- this gate answers "is the
      camera ready," `check_tripwire` answers a different question, whether something's changed
      since a good baseline). All 4, not a sharpness comparison, per Aaron: corner-tag
      readability is the minimum viable gate; sharpness comparison deferred, no threshold
      measured yet.
      **Open again after the step reorder above:** originally this was meant to block moving from
      Focus straight into Run calibration. Now there are two more steps (squareness, coplanarity)
      between them, both involving physical camera nudges that can leave the lens position
      technically "locked" while true focus has drifted. Needs a decision on where the gate
      actually sits -- right after Focus (step 2), or right before Run calibration (step 4 -> 5)
      -- not decided yet. *(Aaron, 2026-09-27/28.)*
- [ ] **Higher quality zoom for focusing (`/focus/roi.mjpg`), if possible.** Aaron: after
      spending a few minutes squinting at the zoomed focus crop to fine-tune it, a sharper zoom
      view would genuinely help. Acknowledged as possibly hard -- low priority, after the two
      items above. *(Aaron, 2026-09-27.)*
- [ ] **LOW PRIORITY. Step 2 (Confirm focus): move the "Camera settings" sub-panel up next to the
      other settings controls.** Discuss placement before acting. *(Aaron, 2026-09-28.)*
- [ ] **LOW PRIORITY. Step 7 (Remove sheets): "Done" button should be active and return to the
      main Setup menu, once it exists.** *(Aaron, 2026-09-28.)*
- [ ] **MEDIUM PRIORITY. Combine Step 3 (squareness) and Step 4 (coplanarity) into one display.**
      Positioning the camera currently means toggling back and forth between the two steps to see
      both sets of guides. Put both on the same live view. Also reconsider the coplanarity ring
      colors -- red/amber/green reads as a pass/fail verdict; a neutral color (e.g. blue) for the
      guides themselves would reduce confusion with that feedback. *(Aaron, 2026-09-28.)*
- [ ] **MEDIUM PRIORITY. After a calibration run, if a previous calibration exists, show a delta
      against it** -- how residuals and other metrics changed from the last run to this one.
      *(Aaron, 2026-09-28.)*
- [ ] **Rewrite the diagnostics explanatory text: too long, rambling, and difficult to
      understand. Needs to be concise.** Covers the pop-over help text on the
      calibration-history diagnostics page (`static/help/diagnostics.md`) and the equivalent
      always-visible copy on `/setup/calibration` Step 5 it was drawn from. *(Aaron,
      2026-09-27.)* **Found by code review 2026-09-27, worth folding into this pass:** the
      confidence-heatmap and area-shape legend text/gradient markup now exists in three places
      (Step 5 inline, `diagnostics.md`, and the drill-down page's own copy of the gradient
      block) -- a wording or colour-scale change to one won't propagate to the others unless
      this rewrite also picks one source of truth.
- [ ] **Drill-down page's "Load rank plots..." button re-enables and resets its label before the
      images actually finish loading** (it only sets `img.src`, with nothing for the button's
      `finally` to await) -- so the button looks idle again while a multi-second re-detection is
      still running, and a second click mid-load fires a duplicate batch of requests. Same
      fire-and-forget pattern as the existing Step 5 "Load diagnostics" button, so not a new
      regression, but worth fixing both together as part of the UI-organization pass. **Found by
      code review 2026-09-27.**
- [x] **Honesty plot moved to Health check, 2026-09-27.** Decided: it's PLAN.md's M2
      acceptance-test tool (place a known target, measure the actual error, check
      claimed-vs-actual), not something a day-to-day operator needs on the way through the
      wizard. `/setup/health-check` now shows the current calibration's raw frame (via
      `/calibration/current`'s `frame_url`) alongside the honesty-plot table/form. Step 6's
      diagnostics section links to it instead. **Gap found on first landing (Aaron, 2026-09-27):
      the frame image displayed but gave no actual way to measure a pixel position from it** --
      fixed same day: clicking the frame now adds a row pre-filled with that click's position,
      converted from on-screen percent to the full-res 9152x6944 space every `ScaleField`/
      `UncertaintyField` position is measured in (same conversion pattern the Focus ROI click
      already used, just a different frame size), and focuses the "actual error" field so the
      next step (measure with a ruler, type it in) is immediate. Click precision is only
      approximate (a scaled-down displayed image, not a full-res pointer), but the honesty
      plot's claimed-uncertainty lookup averages the 5 nearest tags, so being off by tens of
      pixels in a 9152px-wide frame shouldn't change which tags that is. *(Aaron, 2026-09-26
      raised the move; 2026-09-27 raised and fixed the measurement gap.)*
- [x] **"Back"/"Next" buttons now match the rest of the UI's button style, 2026-09-27** -- the
      wizard-nav-buttons size override was removed; they inherit the same base button look
      (min 48px touch target) as everywhere else. *(Aaron, 2026-09-26.)*
- [ ] **Tabled: what should the honesty plot's "actual error" input actually be? Aaron doesn't yet
      understand what the tool is supposed to do, and needs rig access to work it out.** He has
      a frame completely covered in AprilTags, each independently measured to ~30mm within
      0.5mm, and expected the app to compute error from that directly -- but there's a real
      circularity problem underneath this, not just a missing feature: if those tags are the
      same ones the live calibration was built from, "predicted size vs. known size" for them is
      exactly `scale_residual_samples()` in `calibration.py` -- the same number the confidence
      heatmap and scale-residual rank plot already show, produced by the very least-squares fit
      those tags built. That's the fit grading its own homework, not independent verification,
      and the honesty plot exists specifically to catch the app lying to itself -- CLAUDE.md's
      "certainty is measured, never derived" gate. Two honest paths once this is resolved with
      rig access: (1) if the tag-covered frame is a separate, held-out capture never used to fit
      the live calibration, auto-computing predicted-vs-known size per detected tag is legitimate
      and removes the need for a ruler entirely; (2) if it's the same frame, the real test needs
      a measurement outside the tag detections altogether -- e.g. a tape measure between two
      fixed points (the corner tags) compared against what the app reports for that distance.
      Do not implement either path without confirming which situation actually applies.
      *(Aaron, 2026-09-27.)*
- [ ] **The wizard is too wordy and conversational overall — slim it down.** Long paragraph
      explanations under most steps; consider expandable/pop-over info boxes instead of a large
      block of always-visible text, so the default view is short and detail is opt-in. Cuts
      across every step, not a single-page fix — needs its own pass once scoped.
      *(Aaron, 2026-09-26.)*
- [x] **Calibration wizard: real Next/Back step navigation, one step visible at a time — shipped
      2026-09-25 (#10, `68c01c6`), predates this TODO entry having been updated to say so.**
      Multi-page split (Setup menu, Focus & Square, Calibration, Gallery as separate
      pages/routes) also done 2026-09-25. `/setup/calibration` now pages one `.wizard-step` at a
      time via `wizardStep`/`renderWizardStep()`, grown to 7 steps as of this branch (M2 UI
      organization pass, 2026-09-27) with Step 2 added for the rotation/squareness check.
      *(Aaron, 2026-09-21; shipped 2026-09-25.)*
- [ ] **Calibration wizard: gate at each step, not just paging.** Distinct from the paging item
      above (done): at each step, check whether things look reasonable before moving on — e.g.
      leveling/squareness very off, or a run's residuals very high, caught right there instead of
      only surfacing in the final report. Needs real threshold values from measured runs, not
      guessed constants, plus a UX decision (warn vs. block progress) — a design question of its
      own, not a small addition. Distinct from M6's alerts item, which is about
      unattended-operation alerts, not interactive setup feedback. *(Aaron, 2026-09-21 and
      2026-09-25.)*
- [x] **Step 4 ("Confirm nothing moved") — removed entirely, 2026-09-25.** Superseded by the
      "fundamentally confusing" item below: the colored-rings redesign proposed here would have
      fixed the presentation but not the underlying problem, which turned out to be that the step
      had no real job. Its "Zero here" baseline was in-memory only (`_live_orientation_baseline`
      in `app.py`, never persisted) and distinct from the baseline `/calibration/tripwire/check`
      actually reads (the one `/calibration/run` builds and saves) -- so it could not do the thing
      Aaron wanted it for ("detect if the camera has been rotated in the future"). Traced through
      with the advisor: a fixed camera rotation, even a large one, adds no measurement error on
      its own (area is orientation-independent, and the scale field/homography are rebuilt fresh
      from wherever the corner tags actually are each calibration) -- what would catch a badly
      rotated camera during setup is the Step 1/2 squareness guide lines (a framing problem, tags
      falling out of frame), not a roll number. And a bump between Step 2 and Step 5 (e.g. while
      placing sheets) still gets calibrated correctly by Step 5, which is also where the real,
      persisted baseline gets built -- so removing Step 4 loses nothing. Endpoints
      `/calibration/orientation/zero` and `/calibration/orientation/live`, the module-level
      `_live_orientation_baseline`, and their 5 unit tests removed along with the wizard step;
      `/calibration/orientation/level.jpg` (Step 2's traffic light, a different, non-baseline
      check) is untouched. Wizard is now 6 steps.
- [x] **Step 3 ("Place calibration and corner sheets"): placement diagram — built 2026-09-25.**
      Inline SVG: every tray gets a sheet (not an alternating pattern -- see below), four corner
      dots labelled NW/NE/SW/SE (top = north, right = east, Aaron's stated convention).
- [x] **Step 3: download links for the calibration/corner sheet PDFs — built 2026-09-25.** New
      `/reference/calibration-sheets` static mount in `app.py`; linked as a `<ul>` (Aaron asked for
      a list over the original middot-joined links, for readability).
      **Real correction during this work:** the diagram's first version used PLAN.md's own
      "alternating trays" pattern, and the specific alternating (checkerboard) pattern chosen only
      put sheets on two of the four corner-most trays (NW, SE) -- Aaron caught this by inspection.
      Root question then: since sheets are already established as reusable, why alternate at all?
      No good answer -- switched to every tray, which also removes the "does this pattern reach
      all four corners" class of mistake entirely. Fixed the same stale "alternating trays"
      wording in PLAN.md (two spots) to match.
- [x] **New Setup page "Health check", and moved "Check tripwire now" onto it — built
      2026-09-25.** `/setup/health-check` (`setup_health_check.html`), linked from the Setup menu
      alongside Focus & Square and Calibration. Holds just the tripwire check for now (the other
      candidate, the wizard's old "confirm nothing moved" step, was removed outright rather than
      relocated -- see above). Button/JS moved verbatim from the wizard's Step 4 (now "Run
      calibration"); that step's own result panel and "Run calibration" button are untouched, and
      its "Set as current baseline" copy now links to the new page instead of saying "further
      down."
- [x] **Step 5/6: let the operator load a previous saved calibration's report instead of always
      requiring a fresh capture — shipped 2026-09-27, confirmed working by Aaron.** The
      calibration-history page's per-stem drill-down (`/setup/calibration-history/<stem>`) is
      the picker: browse `/calibration/list`'s saved artifacts and view an old run's stats and
      diagnostics without re-running calibration. Same underlying feature as the heatmaps/rank
      plots item below, applied to the whole report. *(Aaron, 2026-09-25; shipped and confirmed
      2026-09-27.)*
- [x] **Table width/length/corner-tag-size now persist between runs — built 2026-09-25.** Aaron:
      "the calibration doesn't remember the settings from the previous runs so I always get the
      NOT TO SCALE thing." All three stored via `settings.py`'s key/value store (the same one
      camera controls use) -- not the `CalibrationArtifact`, since these are operator-typed
      display convenience values, not measurements, and don't deserve a version bump that would
      strand every already-saved artifact on disk. Only a real, explicitly-given value is ever
      persisted; a blank field falls back to the last real value given, never to a guessed
      default. `/calibration/current` now echoes all three (even before any calibration exists)
      so the wizard can pre-fill the inputs, same pattern as the existing tag-size pre-fill.
      **Follow-up, same day: that persistence had no way to actually reach it.** Aaron: "There's
      no way to enter the table width and length in mm. There's no submit button." True -- the
      only thing that saved these three was clicking "Run calibration", a full physical capture +
      tag-detection cycle. Once the calibration sheets come off the table (Step 6), there's no way
      to fix a mistyped table dimension without redoing the whole physical setup. Fixed with a
      dedicated `POST /calibration/table-dims` (no camera access, no detection -- just
      `save_setting` on whichever of the three are given) and a "Save" button next to the inputs.
      **Separately, the "49 vs 50" report was the corner-tag-size input's placeholder text**
      (`"e.g. 49.87"`), not a functional default (`ASSUMED_CORNER_TAG_SIZE_MM` was already
      correctly `50.0`) -- and it was showing truncated as "49." because the box was too narrow
      for the native number-input spinner arrows to leave room for the full placeholder. Fixed
      the text to `"e.g. 50"` and widened the box (6rem -> 7rem, matching the width/length
      inputs). Real values from Aaron entered directly via the new endpoint: table width (E-W,
      the frame's long/X dimension) 1496mm, length (N-S, short/Y dimension) 1152mm, corner tag
      50mm.
- [ ] **Step 6: add a labeled diagram of what table width/length mean.** Using a fixed compass
      convention: top of the image is **north**, right side is **east** (matches how the camera
      looks down at the table) — the current text-only description (top-left to top-right =
      width, top-left to bottom-left = length) asks the operator to hold that mapping in their
      head instead of seeing it drawn. *(Aaron, 2026-09-25.)*
- [x] **Calibration history browser — done 2026-09-26.** See the handoff doc:
      `reference/plans/calibration-history-browser.md` (updated to match what shipped). Supersedes
      the "move calibration history into a gallery" item and the "load past reports" idea, both
      folded into this one. Shipped: `/calibration/list` carries per-entry cheap stats (residual,
      tag size, corner-tag count, which one is active) with no re-detection; `POST
      /calibration/{stem}/promote` and `DELETE /calibration/{stem}` (guarding path traversal and
      the active calibration); a compact list-row browser with thumbnail, stats, promote/delete,
      and load-more paging, at its own page (`/setup/calibration-history`, linked from the Setup
      menu) rather than nested in the wizard; an opt-in "Load diagnostics for the active
      calibration" button on `/setup/calibration` Step 5, so diagnostics can be viewed for
      whatever's active without a fresh run. No "undo" button -- rejected as unclear (how many
      steps back, what state changes).
      Deliberately deferred, not a gap: coplanarity/holdout/area-scale error per entry (need
      re-detecting tags from each saved frame) -- no saved-frame corpus existed yet to time this
      against, so the list only ever shows cheap stats; viewing those for an arbitrary *past* run
      (not just the active one) would need that re-detection plus a UI for it. *(Aaron, 2026-09-26.)*
- [ ] **Zoomed focus preview (`/focus/roi.mjpg`) is awful quality** — Aaron: looks like a zoom of
      a reduced-quality image. Should be much higher quality to actually help focus by eye.
      `CameraManager.roi_crop_jpeg` (`camera.py`) crops from the continuous `main` video stream
      at `MAIN_SIZE` (1536×1152), not the 320×240 `lores` preview and not a full-res still --
      so it's not literally re-zooming the low-res preview, but 1536×1152 is still a small
      fraction of the 64MP sensor, and a small ROI crop of that gets magnified a lot in the
      browser. Not investigated further -- worth checking whether a dedicated higher-res crop
      (e.g. a still capture, or a larger/different stream config) is feasible without breaking
      the continuous preview or `focus_score`'s own use of the same stream. *(Aaron, 2026-09-22)*
- [x] **Let the two heatmaps and the best-vs-worst-tag rank plots be viewed for a past
      calibration, not just whatever's live — shipped 2026-09-27.** New stem-scoped endpoints
      (`GET /calibration/{stem}/rank-plot`, `best-worst-photo`, `radial-plot`,
      `certainty-dome-plot`) alongside the existing `/calibration/current/*` ones, plus a new
      per-stem page (`/setup/calibration-history/<stem>`,
      `setup_calibration_history_diagnostics.html`) showing the pre-rendered heatmap/table-view
      images immediately and an opt-in "Load rank plots, radial plot, and dome of certainty"
      button for the re-detection-dependent ones.
      Every calibration-history card now links to it, not just the active entry. *(Aaron,
      2026-09-22; shipped 2026-09-27.)*
- [ ] **Tidy up the calibration result messages -- too much shown at once, agreed plan not yet
      built.** Aaron, 2026-09-25, on a real 10-line result: "This is waaaaaaaay too much
      information and not all of it is relevant to someone that has just set this up." Agreed
      split: stays visible immediately -- tag/corner detection counts; the coverage verdict
      (the one actionable line); the table-view scale note, but only when NOT TO SCALE; tag
      size/corner tag size, but only when still a placeholder default (a real measured value is
      just restating something already known). Moves into the existing "Diagnostics" `<details>`
      panel -- exact px/mm at centre + plane-fit residual %; scale variation % and direction;
      area-scale error/shape distortion including the worst-tag callout. Needs
      `build_calibration_report()` (or its caller in `app.py`) to return two groups instead of one
      flat list, so the frontend can route lines to two different places.
- [x] **Step 1 focus controls -- done 2026-09-27 (M2 UI organization pass), by way of several
      rounds of live feedback, not a single move.** "Below the images" alone (the original ask)
      turned out not to be the real requirement -- at 1024x768 it just meant scrolling between
      the image and the controls instead of scrolling between the controls and the image. Landed
      on: a full-width control panel below the image row (autofocus, lock, peaking, coarse/fine,
      sharpness, all in one bordered group), applied identically to `/setup/focus` and the
      wizard's Step 1 via a shared `templates/_focus_controls.html` partial (extracted the same
      day, so the two pages stop needing hand-sync). *(Aaron, 2026-09-25 raised; 2026-09-27
      shipped.)*
- [x] **Step 1 "Lock focus" explainer -- done 2026-09-27.** Checked against
      `CameraManager.lock_focus()`/`focus_status()` rather than assumed: it only records the
      lens position for the status display, nothing else in the app gates on it, so the copy
      says "a record, not a safeguard" rather than overstating what it does. *(Aaron, 2026-09-25
      raised; 2026-09-27 shipped.)*
- [x] **Step 3 Back/Next button style -- done 2026-09-27.** Duplicate of the entry above (the
      wizard-nav-buttons size override removed, same fix). *(Aaron, 2026-09-25/26.)*
- [ ] **(i) icons / pop-over pattern across the Setup pages -- partially done.** The pattern
      itself now exists in a reusable form (`<details>`/`<summary>`, no custom JS) and is used
      for: Step 1 and Step 2's "More about this step"/"What do these controls do?" panels, and
      the pre-existing Camera settings panel. Not yet applied to: Steps 3-7's always-visible
      paragraphs, or `static/help/diagnostics.md`/the drill-down page's (i) pop-overs (a
      different, JS-fetch-based implementation of the same idea) -- that consolidation is
      `m2-ui-organization-and-text`'s job, paused mid-branch. *(Aaron, 2026-09-25.)*

### M2 acceptance — run in the chamber
- [x] **Two-baseline test — run remotely 2026-09-25, clear pass.** Two calibrations of the same
      static scene (332 then 340 calibration tags, 4/4 corner tags both times), lens
      manually defocused to 5.0 and back to 6.33 between them (not a full power-cycle — Aaron was
      remote with no physical chamber access, and this app avoids autofocus right after a
      capture per the known pipeline-hang bug below). Both `promote=false`, so the live baseline
      was untouched.
      **Scale field disagreement:** 0.02-0.16% across centre + all 4 frame corners (evaluated
      from each run's own fitted plane coefficients) — an order of magnitude below the claimed
      uncertainty (`residual_std_pct` 1.68% vs 1.71%, holdout coverage error 1.3% vs 1.4%,
      area-scale error 2.6% vs 2.7%, all close between runs too).
      **Tripwire cross-check:** feeding run 2's corner detections against run 1's corner baseline
      through `check_tripwire()` gives `OK`, roll 0.006°, per-corner-tag scale delta -0.25% to
      +0.28%.
      **Reading this against PLAN.md's own bar** ("if two calibrations of the same static scene
      disagree by more than the uncertainty we claim, the claimed number is fiction"): they don't
      — actual disagreement is well inside claimed uncertainty on every metric checked. This is
      the strongest evidence so far that the claimed numbers are conservative, not fiction.
      **Caveat:** only a lens nudge, not a real power-cycle — worth re-running once with a full
      app restart between captures when there's bench access, to rule out any state the app
      itself might be silently carrying between runs that a fresh process wouldn't. Artifacts:
      `/var/lib/npec-rig/calibration/20260925T101036192864.json` and
      `.../20260925T101058109190.json`.
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
- [x] **Best-vs-worst-tag rank plot, built 2026-09-22.** Aaron wanted a plot of how far the worst
      calibration tag is from the best one -- the two heatmaps only ever show smoothed/averaged
      numbers. `GET /calibration/current/rank-plot?metric=scale_residual|shape_distortion`
      re-detects tags from the live calibration's saved frame (neither per-tag number is
      persisted in the artifact) and renders every tag's own residual or shape distortion,
      sorted best to worst, as a single line rather than one bar per tag -- with 400+ tags a bar
      chart is unreadable, and a sorted line shows the whole distribution's shape for free.
      Only the two ends are labelled, with the worst tag's ID and frame position so it can be
      found physically. Two `<img>`s in the UI, loaded automatically right after "Run
      calibration" -- no new operator input. New calibration.py types
      (`ScaleResidualSample`/`scale_residual_samples`) for the length-residual side, since
      `UncertaintyField` doesn't keep `tag_id`, only positions.
- [?] **Radial residual plot, built 2026-09-22 -- and its first real reading needs Aaron's/his
      supervisor's judgement call, not mine.** Aaron's supervisor (a lens/photogrammetry expert)
      read the confidence heatmap's spikiness as "that doesn't look right" and expected a
      parallax/lens-distortion signature instead. PLAN.md already defines the exact test for
      that: residuals *structured* (trending with distance from the image centre, consistently
      signed) vs. random is the specific measurement that unbans intrinsic camera calibration.
      That test had never actually been run in that shape -- only as an xy heatmap (position) or
      a sorted-rank plot (magnitude), never signed-value-vs-radius. Built:
      `GET /calibration/current/radial-plot?metric=scale_residual|shape_distortion` -- every
      tag's own **signed** residual (not `abs()` -- a real distortion trend has a sign, folding
      it to magnitude would hide the shape) plotted against distance from the image centre, with
      an unweighted linear fit and its R² baked in, no smoothing, no pre-judgement of the result.
      **First real run (`20260922T085145960485`, 371 tags) came back R²=0.34 (scale residual) and
      R²=0.41 (area-shape distortion), both with a clear visible downward trend** -- not
      obviously random scatter. Not acted on: one run's R² isn't a decision by itself (a
      different run two turns earlier showed only weak position correlation on the same rig), and
      "is this structured enough to open the gate" is exactly the judgement PLAN.md reserves for
      a human reading the plot, not a threshold in code.
      **Second run, lights on this time (`20260922T104517936034`, 431 tags): R²=0.33 / R²=0.45 --
      same shape, same rough magnitude, under different lighting.** That rules out "it's an
      exposure/lighting artifact" as the explanation for the earlier reading; it doesn't yet rule
      in "it's the lens" over some other repeatable geometric cause. Axis tick labels (actual
      px/percent numbers, and an explicit "0%" on the zero line) added the same day -- the first
      version had bare axis lines with no numbers on them, a real gap, not intentional.
      *(Aaron/supervisor to read the plot and decide; if confirmed across a few more runs, this
      is what unbans `calibrateCamera`.)*

---

## M3 — Capture, storage, export · *PLAN.md § M3*

- [ ] Full SQLite schema (`experiment`, `calibration`, `tray`, `capture`, `detection`,
      `measurement`, `alert`) — created here so every row has provenance from the start
- [ ] Experiment create/start/stop in the UI
- [ ] **Gallery thumbnails are slow and cannot be clicked (Aaron, 2026-10-01).** The gallery
      loads every capture's full-resolution 64MP JPEG and lets the browser shrink it
      (`gallery.html`, `<img src="${item.url}">`), so the page is very slow. Serve real
      thumbnails instead (made once per capture, for example at save time, and cached on disk).
      Clicking a thumbnail does nothing: the images have no click handler and are not
      `.diagnostic-image`, so the shared lightbox ignores them. Click should open the capture
      large (a screen-sized version, not the full 64MP file).
      **Use the image system built 2026-10-02 (`images.py`, PLAN.md *Images*):** add `thumb` and
      `screen` recipes on `images.reduced_frame` (0.11 s and 0.24 s per 64MP capture, measured),
      served through `images.get`. Do not build a separate thumbnail path.
- [ ] **Design the header/nav menu properly once experiment/report pages exist.** The Jinja
      base-layout work (M2 UI-organization pass) centralized the header/nav into one
      `templates/base.html` block, but its content is still just the same two links (Setup,
      Capture & Gallery) that existed before -- deferred designing the actual menu structure
      (flat list vs. grouped/dropdown) until M3's experiment list/detail/timelapse/report pages
      are real routes, since guessing the hierarchy now would be speculative. *(Aaron,
      2026-09-27.)*
- [ ] Experiment storage laid out so a whole experiment is easy to identify and remove as a unit
      (e.g. one directory per experiment, named/indexed so it's obvious which is which) — not
      commingled with calibration data or other experiments. *(Aaron, 2026-09-19)*
- [ ] Interval scheduler, 1–6 min, trust verdict per capture
- [ ] **Scheduled captures must not contend with live preview/setup streams for the camera.**
      Right now the Setup pages (Focus & Square, live leveling, live reorientation) all poll or
      stream from the camera whenever their step/page is open — fine while nothing else needs the
      camera, but once M3's scheduler is real, a scheduled sample and someone reviewing Setup at
      the same time would compete for the same hardware. Needs a real arbitration decision (lock
      out live preview during a scheduled capture? queue it? refuse Setup access mid-capture?),
      not guessed. *(Aaron, 2026-09-25, raised while gating Setup's live streams to only run on
      their own visible step.)*
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
- [ ] Low priority: a live preview alongside the Capture button on the new `/gallery` page, so
      you can see what you're about to capture instead of only the result afterward.
      *(Aaron, 2026-09-25)*
- [ ] Low priority: click a gallery thumbnail to view it larger. *(Aaron, 2026-09-25 — same request
      as the download/delete items above, reconfirmed on the new `/gallery` page.)*
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
