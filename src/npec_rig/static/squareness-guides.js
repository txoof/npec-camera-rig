// The squareness panel (templates/_squareness.html), shared by the calibration wizard's Step 3
// and Square mode on the Focus and Square page: three magenta guide lines over the live image,
// moved by large handles just outside it or by the keyboard, and the corner rings switch.
// A straightening aid: the lines are client-side only, never saved.
//
// Loaded from <head> without defer, since the pages call initSquareness() from their own inline
// scripts; everything that uses the shared components (ui.js, deferred) waits for the document.
function initSquareness({ isActive }) {
  const $ = (id) => document.getElementById(id);
  const image = $("sq-image");
  const ringsSwitch = $("corner-rings");
  const lines = { h: $("sq-line-h"), v1: $("sq-line-v1"), v2: $("sq-line-v2") };
  const axis = { h: "y", v1: "x", v2: "x" };
  const pos = { h: 50, v1: 18, v2: 82 };
  const handles = document.querySelectorAll(".sq-frame .handle");
  let selected = "h";
  let upright = "v1"; // the upright line left and right move: the last one picked

  const clamp = (pct) => Math.min(100, Math.max(0, pct));

  function place(name) {
    const edge = axis[name] === "y" ? "top" : "left";
    lines[name].style[edge] = pos[name] + "%";
    handles.forEach((h) => { if (h.dataset.line === name) h.style[edge] = pos[name] + "%"; });
  }

  function select(name) {
    selected = name;
    if (name !== "h") upright = name;
    handles.forEach((h) => h.classList.toggle("sel", h.dataset.line === name));
    Object.entries(lines).forEach(([n, line]) => line.classList.toggle("sel", n === name));
  }

  // Pointer capture keeps move events coming to the handle when the pointer leaves it mid-drag.
  handles.forEach((handle) => {
    const name = handle.dataset.line;
    handle.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      handle.setPointerCapture(e.pointerId);
      select(name);
    });
    handle.addEventListener("pointermove", (e) => {
      if (!handle.hasPointerCapture(e.pointerId)) return;
      const r = image.getBoundingClientRect();
      pos[name] = clamp(axis[name] === "y"
        ? ((e.clientY - r.top) / r.height) * 100
        : ((e.clientX - r.left) / r.width) * 100);
      place(name);
    });
    handle.addEventListener("click", () => select(name));
  });

  // Keyboard: 1, 2, 3 pick the across, left and right line; up and down (W, S) move the across
  // line, left and right (A, D) the picked upright line, 0.5% of the image a press. Only while the
  // panel is showing and no keypad, keyboard or panel is open over it.
  const KEYS = { w: -1, arrowup: -1, s: 1, arrowdown: 1, a: -1, arrowleft: -1, d: 1, arrowright: 1 };
  const VERTICAL = ["w", "s", "arrowup", "arrowdown"];
  document.addEventListener("keydown", (e) => {
    if (!isActive() || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.target.closest && e.target.closest("input, textarea, select, [contenteditable]")) return;
    if (document.querySelector(".keypad-layer, .kb-layer, .panel-layer")) return;
    const key = e.key.toLowerCase();
    if (key === "1" || key === "2" || key === "3") {
      select(["h", "v1", "v2"][Number(key) - 1]);
      e.preventDefault();
      return;
    }
    if (!(key in KEYS)) return;
    const name = VERTICAL.includes(key) ? "h" : upright;
    select(name);
    pos[name] = clamp(pos[name] + KEYS[key] * 0.5);
    place(name);
    e.preventDefault();
  });

  // --- The image: the corner rings overlay, or the plain live view ---
  // The rings come from /calibration/orientation/level.jpg, which finds the corner tags in a
  // fresh frame: real CPU on the Pi, so it is polled every 1.5 s (Aaron, 2026-09-28) and off by
  // default, which keeps the live view smooth while the lines are moved. Each frame loads into an
  // off-screen probe and is shown only once complete, and only if the rings are still wanted.
  const LEVEL_OVERLAY_POLL_MS = 1500;
  let showing = null; // "rings" | "preview" | null
  let inFlight = false;

  function refreshRings() {
    if (inFlight) return;
    inFlight = true;
    const probe = new Image();
    probe.onload = () => {
      inFlight = false;
      if (showing === "rings") image.src = probe.src;
    };
    probe.onerror = () => { inFlight = false; };
    probe.src = `/calibration/orientation/level.jpg?t=${Date.now()}`;
  }

  const ringsOn = () => ringsSwitch.getAttribute("aria-checked") === "true";

  // Call when the panel is shown or hidden (a wizard step, a mode change).
  function update() {
    if (!isActive()) {
      if (showing !== null) image.removeAttribute("src");
      showing = null;
      return;
    }
    if (ringsOn()) {
      if (showing !== "rings") { showing = "rings"; refreshRings(); }
    } else if (showing !== "preview") {
      showing = "preview";
      image.src = "/preview.mjpg";
    }
  }

  (function poll() {
    if (isActive() && ringsOn() && !document.hidden) refreshRings();
    setTimeout(poll, LEVEL_OVERLAY_POLL_MS);
  })();

  Object.keys(lines).forEach(place);
  select("h");
  const bind = () => ui.bindSwitch(ringsSwitch, update);
  if (window.ui) bind(); else document.addEventListener("DOMContentLoaded", bind);
  update();
  return { update };
}
