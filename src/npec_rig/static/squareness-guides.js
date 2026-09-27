// Draggable squareness guide lines -- a straightening aid (drag the tabs onto real perpendicular
// edges in the scene to check the camera isn't rotated or badly tilted). Shared by the standalone
// Focus & Square page's Square mode and the calibration wizard's dedicated Step 2, so the drag
// math (and its pointer-capture-based touch handling) only needs fixing in one place.
//
// Not deferred -- loaded synchronously from <head> via base.html, since callers invoke
// initSquarenessGuides() from their own inline <script>, which runs while the document is still
// being parsed, before any deferred script would.
function initSquarenessGuides(squarenessGuides, previewImg) {
  function clampPct(value) {
    return Math.min(100, Math.max(0, value));
  }

  function syncHandlesForLine(line, axis, pct) {
    squarenessGuides.querySelectorAll(`.squareness-handle[data-for="${line.id}"]`).forEach((handle) => {
      handle.style[axis === "y" ? "top" : "left"] = pct + "%";
    });
  }

  function moveLineTo(line, axis, pct) {
    line.style[axis === "y" ? "top" : "left"] = pct + "%";
    syncHandlesForLine(line, axis, pct);
  }

  // Pointer capture keeps delivering move/up events to `handle` even once the pointer leaves it
  // mid-drag -- no separate document-level listeners (and cleanup) needed.
  function makeHandleDraggable(handle) {
    const line = document.getElementById(handle.dataset.for);
    const axis = handle.dataset.axis;
    handle.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      handle.setPointerCapture(event.pointerId);
    });
    handle.addEventListener("pointermove", (event) => {
      if (!handle.hasPointerCapture(event.pointerId)) return;
      const rect = previewImg.getBoundingClientRect();
      const pct = axis === "y"
        ? clampPct(((event.clientY - rect.top) / rect.height) * 100)
        : clampPct(((event.clientX - rect.left) / rect.width) * 100);
      moveLineTo(line, axis, pct);
    });
  }
  squarenessGuides.querySelectorAll(".squareness-handle").forEach(makeHandleDraggable);

  const DEFAULT_LINE_H_TOP_PCT = 50;

  // Handles start wherever their line already is (the HTML defaults, 33.33%/66.67%, or the
  // stylesheet default for the horizontal line).
  squarenessGuides.querySelectorAll(".squareness-line").forEach((line) => {
    const axis = line.classList.contains("squareness-line-h") ? "y" : "x";
    const inline = parseFloat(axis === "y" ? line.style.top : line.style.left);
    // Not `inline || DEFAULT...` -- a legitimate 0% position is falsy and would otherwise be
    // silently overridden.
    const pct = Number.isNaN(inline) ? DEFAULT_LINE_H_TOP_PCT : inline;
    syncHandlesForLine(line, axis, pct);
  });
}
