// Shared interface behavior (#128), drawn from reference/ui-mockup/rig-ui-mockup.html. Markup
// is in templates/_ui.html, styles in style.css, and every function is shown on /ui.
//
// Loaded on every page, so it attaches nothing at load: a page calls these functions for the
// components it uses. A layer listens for keys only while it is open. Only a clock redraws on a
// timer, and only its own text: a button under the stylus is never replaced.
(function () {
  "use strict";

  const esc = (t) => String(t).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const icon = (name) =>
    `<svg class="ui-icon" aria-hidden="true" focusable="false"><use href="/static/icons.svg#${name}"></use></svg>`;
  const chip = (kind, text) => `<span class="chip ${kind}">${icon(kind)}${esc(text)}</span>`;
  // Under 700px wide is a phone, which keeps its own keyboard (#128).
  const isPhone = () => window.matchMedia("(max-width: 700px)").matches;

  // A layer covers the screen, is a dialog, and gives focus back to what opened it on close.
  function openLayer(className, label, html, onKey) {
    const opener = document.activeElement;
    const el = document.createElement("div");
    el.className = className;
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.setAttribute("aria-label", label);
    el.innerHTML = html;
    document.body.appendChild(el);
    const keys = (e) => {
      if (onKey(e) !== false) { e.preventDefault(); e.stopPropagation(); }
    };
    document.addEventListener("keydown", keys, true);
    el.close = () => {
      document.removeEventListener("keydown", keys, true);
      el.remove();
      if (opener && opener.isConnected && opener.focus) opener.focus();
    };
    return el;
  }

  /* ---------- Toast: a short result, gone after 1.8 s ---------- */
  function toast(message) {
    const t = document.createElement("div");
    t.className = "toast";
    t.setAttribute("role", "status");
    t.textContent = message;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 1800);
  }

  /* ---------- Numeric keypad ----------
     options: label, help, value (string), unit, min, max, decimals, onSet(value string). */
  function openKeypad({ label, help = "", value = "", unit = "", min = null, max = null, decimals = 0, onSet }) {
    let val = String(value ?? "");
    const range = min != null && max != null ? ` Allowed: ${min} to ${max}${unit ? " " + unit : ""}.` : "";
    const el = openLayer("keypad-layer", label, `
      <div class="kp-info">
        <p class="kp-label">${esc(label)}</p>
        <p class="kp-help">${esc(help + range)}</p>
        <div class="kp-value" aria-live="polite"><span><span class="kp-v"></span><span class="cursor"></span></span><span class="unit">${esc(unit)}</span></div>
        <p class="kp-error"></p>
        <div class="spacer"></div>
        <div class="kp-actions">
          <button type="button" class="btn hit" data-act="cancel">Cancel</button>
          <button type="button" class="btn primary hit" data-act="set">Set</button>
        </div>
      </div>
      <div class="kp-keys">
        ${["7", "8", "9", "4", "5", "6", "1", "2", "3"].map((k) => `<button type="button" class="key hit" data-k="${k}">${k}</button>`).join("")}
        <button type="button" class="key hit" data-k="." ${decimals ? "" : "disabled"} aria-label="Decimal point">.</button>
        <button type="button" class="key hit" data-k="0">0</button>
        <button type="button" class="key fn hit" data-k="del" aria-label="Delete last digit">${icon("del")}</button>
        <button type="button" class="key fn wide hit" data-k="clear">Clear</button>
      </div>`, (e) => {
      if ((e.key >= "0" && e.key <= "9") || e.key === "." || e.key === ",") press(e.key === "," ? "." : e.key);
      else if (e.key === "Backspace") press("del");
      else if (e.key === "Enter") setNow();
      else if (e.key === "Escape") el.close();
      else return false;
    });
    const vEl = el.querySelector(".kp-v");
    const err = el.querySelector(".kp-error");
    const fail = (text) => { err.innerHTML = icon("fail") + esc(text); };
    const paint = () => { vEl.textContent = val; err.textContent = ""; };
    function press(k) {
      if (k === "." && !decimals) return;
      if (k === "del") val = val.slice(0, -1);
      else if (k === "clear") val = "";
      else if (k === ".") { if (!val.includes(".")) val = (val || "0") + "."; }
      else {
        const dec = val.split(".")[1];
        if (dec !== undefined && dec.length >= decimals) { fail(`At most ${decimals} decimal places.`); return; }
        val = (val === "0" ? "" : val) + k;
      }
      paint();
    }
    function setNow() {
      if (val !== "") {
        const n = Number(val);
        if (Number.isNaN(n) || (min != null && n < min) || (max != null && n > max)) {
          fail(`${val} is outside ${min} to ${max}${unit ? " " + unit : ""}.`);
          return;
        }
        val = String(n);
      }
      el.close();
      onSet(val);
    }
    el.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b || b.disabled) return;
      if (b.dataset.act === "cancel") el.close();
      else if (b.dataset.act === "set") setNow();
      else if (b.dataset.k) press(b.dataset.k);
    });
    paint();
    el.querySelector('[data-act="set"]').focus();
    return el;
  }

  /* ---------- Full keyboard ----------
     For names, labels and notes. On a phone the device's own keyboard is used instead: it is
     good there, and 10 keys across would be too small. options: label, value, max, onSet. */
  function openKeyboard({ label, value = "", max = 200, onSet }) {
    let val = String(value ?? "");
    let shift = val === "";
    const rows = [
      "1234567890".split(""),
      "qwertyuiop".split(""),
      "asdfghjkl-".split(""),
      ["shift", ..."zxcvbnm".split(""), ".", "del"],
      ["space"],
    ];
    const keyHtml = (k) => {
      if (k === "shift") return `<button type="button" class="key fn hit" data-k="shift" aria-pressed="${shift}">Shift</button>`;
      if (k === "del") return `<button type="button" class="key fn hit" data-k="del" aria-label="Delete last character">${icon("del")}</button>`;
      if (k === "space") return `<button type="button" class="key fn space hit" data-k=" ">Space</button>`;
      return `<button type="button" class="key hit" data-k="${k}">${shift && /[a-z]/.test(k) ? k.toUpperCase() : k}</button>`;
    };
    const el = openLayer("kb-layer", label, `
      <div class="kb-top">
        <p class="kp-label">${esc(label)}</p>
        <div class="kb-value" aria-live="polite"><span class="kb-v"></span><span class="cursor"></span><span class="count"></span></div>
        <button type="button" class="btn hit" data-act="cancel">Cancel</button>
        <button type="button" class="btn primary hit" data-act="set">Done</button>
      </div>
      <div class="kb-keys"></div>
      <div class="kb-native field"><span class="field-help">On a phone, the phone's own keyboard is used.</span>
        <input type="text" class="field-btn text" maxlength="${max}" autocomplete="off" aria-label="${esc(label)}"></div>`, (e) => {
      if (e.target === native) {
        if (e.key === "Enter") done();
        else if (e.key === "Escape") el.close();
        else return false;
        return;
      }
      if (e.key === "Enter") done();
      else if (e.key === "Escape") el.close();
      else if (e.key === "Backspace") val = val.slice(0, -1);
      else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { if (val.length < max) val += e.key; }
      else return false;
      native.value = val;
      paint();
    });
    const native = el.querySelector(".kb-native input");
    const paintKeys = () => {
      el.querySelector(".kb-keys").innerHTML = rows.map((r) => `<div class="kb-row">${r.map(keyHtml).join("")}</div>`).join("");
    };
    const paint = () => {
      el.querySelector(".kb-v").textContent = val;
      el.querySelector(".count").textContent = `${val.length} / ${max}`;
    };
    function done() { el.close(); onSet(val); }
    native.value = val;
    native.addEventListener("input", () => { val = native.value; paint(); });
    el.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.act === "cancel") { el.close(); return; }
      if (b.dataset.act === "set") { done(); return; }
      const k = b.dataset.k;
      if (k === undefined) return;
      if (k === "shift") { shift = !shift; paintKeys(); return; }
      if (k === "del") val = val.slice(0, -1);
      else if (val.length < max) {
        val += shift && /[a-z]/.test(k) ? k.toUpperCase() : k;
        if (shift) { shift = false; paintKeys(); }
      }
      native.value = val;
      paint();
    });
    paintKeys();
    paint();
    (isPhone() ? native : el.querySelector('[data-act="set"]')).focus();
    return el;
  }

  /* ---------- Dropdown list ----------
     Looks like one field, opens a list of large rows. A plain <select> opens the browser's own
     list, whose rows are too small on these screens. options: [{value, label, detail}]. */
  function openChoice({ label, options, value, onSet }) {
    const el = openLayer("kb-layer choice-layer", label, `
      <div class="kb-top"><p class="kp-label">${esc(label)}</p>
        <button type="button" class="btn hit" data-act="cancel">Cancel</button></div>
      <div class="choice-list" role="listbox" aria-label="${esc(label)}">${options.map((o) =>
        `<button type="button" class="choice hit" role="option" data-value="${esc(o.value)}" aria-selected="${o.value === value}" aria-pressed="${o.value === value}"><strong>${esc(o.label)}</strong>${o.detail ? `<span>${esc(o.detail)}</span>` : ""}</button>`).join("")}</div>`,
    (e) => {
      if (e.key === "Escape") el.close();
      else return false;
    });
    el.addEventListener("click", (e) => {
      if (e.target.closest('[data-act="cancel"]')) { el.close(); return; }
      const b = e.target.closest("[data-value]");
      if (b) { el.close(); onSet(b.dataset.value); }
    });
    (el.querySelector('[aria-pressed="true"]') || el.querySelector('[data-act="cancel"]')).focus();
    return el;
  }

  /* ---------- Panels ----------
     A panel covers the work area (not the rail), with the same head, scroll and action bar as a
     page, so the buttons that finish it are always on screen. body and actions are HTML the
     page writes; anything a person typed goes in through ui.esc. Returns the panel; call
     panel.close() to remove it. */
  function openPanel({ title, sub = "", body, actions }) {
    const opener = document.activeElement;
    const p = document.createElement("div");
    p.className = "panel-layer";
    p.setAttribute("role", "dialog");
    p.setAttribute("aria-modal", "true");
    p.setAttribute("aria-label", title);
    p.innerHTML = `<header class="work-head"><div style="min-width:0"><h1>${esc(title)}</h1>${sub ? `<p class="sub">${esc(sub)}</p>` : ""}</div></header>
      <div class="scroll"><div class="scroll-hint" aria-hidden="true"><span class="scroll-hint-body">${icon("scroll")}<span class="scroll-hint-label">Scroll here</span></span></div><div class="panel-body"></div></div>
      <div class="action-bar"></div>`;
    p.querySelector(".panel-body").innerHTML = body;
    p.querySelector(".action-bar").innerHTML = actions;
    (document.querySelector(".work") || document.body).appendChild(p);
    p.close = () => {
      p.remove();
      if (opener && opener.isConnected && opener.focus) opener.focus();
    };
    return p;
  }

  /* In-page confirmation, in place of confirm() and alert(), which a touch screen user can miss
     and which the page cannot style. The safe choice is on the left, the action on the right.
     typed: text the person must type to go ahead. check: a switch they must turn on. */
  function confirmPanel({ title, body, ok, danger = false, typed = null, typedLabel = "Type to confirm", check = null, onOk }) {
    const st = { typed: "", checked: false };
    const p = openPanel({
      title,
      body: `<div class="stack" style="max-width:680px">
        <div class="lead" style="color:var(--fg)">${body}</div>
        ${typed ? `<div class="field"><span class="field-label">To confirm, type exactly: <code class="confirm-text">${esc(typed)}</code></span>
          <button type="button" class="field-btn text hit" data-act="typed"><span class="empty">Tap to type</span>${icon("edit")}</button></div>` : ""}
        ${check ? `<button type="button" class="switch hit" role="switch" data-act="check" aria-checked="false"><span class="track"></span>
          <span class="txt"><strong>${esc(check)} <span class="state">Off</span></strong><span>Required to go ahead.</span></span></button>` : ""}
      </div>`,
      actions: `<button type="button" class="btn hit" data-act="cancel">Cancel</button><span class="grow"></span>
        <button type="button" class="btn ${danger ? "danger" : "primary"} hit" data-act="ok">${esc(ok)}</button>`,
    });
    const okBtn = p.querySelector('[data-act="ok"]');
    const ready = () => (!typed || st.typed.trim() === typed) && (!check || st.checked);
    const paint = () => { okBtn.disabled = !ready(); };
    const keys = (e) => {
      // While the keyboard is open over the panel, Escape is the keyboard's.
      if (e.key !== "Escape" || document.querySelector(".kb-layer, .keypad-layer")) return;
      e.preventDefault();
      e.stopPropagation();
      close();
    };
    const close = () => { document.removeEventListener("keydown", keys, true); p.close(); };
    document.addEventListener("keydown", keys, true);
    p.addEventListener("click", (e) => {
      const b = e.target.closest("[data-act]");
      if (!b) return;
      const act = b.dataset.act;
      if (act === "cancel") close();
      else if (act === "typed") {
        openKeyboard({
          label: typedLabel, value: st.typed, max: 200,
          onSet: (v) => {
            st.typed = v;
            const match = v.trim() === typed;
            b.classList.toggle("match", match);
            b.innerHTML = (v ? `<span>${esc(v)}</span>` : '<span class="empty">Tap to type</span>') + (match ? chip("ok", "Matches") : icon("edit"));
            paint();
          },
        });
      } else if (act === "check") {
        st.checked = b.getAttribute("aria-checked") !== "true";
        setSwitch(b, st.checked);
        paint();
      } else if (act === "ok" && ready()) {
        close();
        onOk();
      }
    });
    paint();
    p.querySelector('[data-act="cancel"]').focus();
    return p;
  }

  /* ---------- Bindings for the macros in _ui.html ---------- */
  function setSwitch(el, on) {
    el.setAttribute("aria-checked", String(on));
    const state = el.querySelector(".state");
    if (state) state.textContent = on ? "On" : "Off";
  }
  function bindSwitch(el, onChange) {
    el.addEventListener("click", () => {
      const on = el.getAttribute("aria-checked") !== "true";
      setSwitch(el, on);
      if (onChange) onChange(on);
    });
  }

  function bindChoices(el, onChange) {
    el.addEventListener("click", (e) => {
      const b = e.target.closest("[data-value]");
      if (!b) return;
      el.querySelectorAll("[data-value]").forEach((c) => c.setAttribute("aria-pressed", String(c === b)));
      if (onChange) onChange(b.dataset.value);
    });
  }

  // Shows a value on a field button, or the empty prompt.
  function showField(el, value, shown = value) {
    el.dataset.value = value;
    const unit = el.dataset.unit;
    const tail = el.querySelector(".ui-icon").outerHTML;
    el.innerHTML = (value === ""
      ? '<span class="empty">Not set, tap to enter</span>'
      : `<span><span class="value">${esc(shown)}</span>${unit ? ` <span class="unit">${esc(unit)}</span>` : ""}</span>`) + tail;
  }
  function bindField(el, onSet) {
    const num = (name) => (el.dataset[name] === undefined ? null : Number(el.dataset[name]));
    el.addEventListener("click", () => {
      const d = el.dataset;
      const label = d.label;
      const set = (v, shown) => { showField(el, v, shown); if (onSet) onSet(v); };
      if (d.kind === "text") {
        openKeyboard({ label, value: d.value, max: num("maxLength") || 200, onSet: (v) => set(v) });
      } else if (d.kind === "choice") {
        const options = JSON.parse(d.options || "[]").map(([value, text, detail]) => ({ value, label: text, detail }));
        openChoice({
          label, options, value: d.value,
          onSet: (v) => set(v, (options.find((o) => o.value === v) || { label: v }).label),
        });
      } else {
        openKeypad({
          label, help: d.help, value: d.value, unit: d.unit, min: num("min"), max: num("max"),
          decimals: num("decimals") || 0, onSet: (v) => set(v),
        });
      }
    });
  }

  function bindStepper(el, onChange) {
    const field = el.querySelector(".field-btn");
    const step = Number(el.dataset.step) || 1;
    const decimals = Number(field.dataset.decimals) || 0;
    const clamp = (n) => {
      if (field.dataset.min !== undefined) n = Math.max(Number(field.dataset.min), n);
      if (field.dataset.max !== undefined) n = Math.min(Number(field.dataset.max), n);
      return n;
    };
    el.addEventListener("click", (e) => {
      const b = e.target.closest("[data-step-by]");
      if (!b) return;
      const n = clamp((Number(field.dataset.value) || 0) + step * Number(b.dataset.stepBy));
      const v = String(Number(n.toFixed(decimals)));
      showField(field, v);
      if (onChange) onChange(v);
    });
    bindField(field, onChange);
  }

  /* ---------- Clock ----------
     The one thing that redraws on a timer, and only its own text. render(msLeft) returns the
     text; at zero, done is shown. Returns a function that stops it. */
  function countdown(el, untilMs, { render, done = "Ready" }) {
    const tick = () => {
      const left = Math.max(0, untilMs - Date.now());
      el.textContent = left ? render(left) : done;
      if (!left) clearInterval(timer);
    };
    const timer = setInterval(tick, 1000);
    tick();
    return () => clearInterval(timer);
  }
  const mmss = (ms) => `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}`;

  window.ui = {
    esc, icon, chip, isPhone, toast,
    openKeypad, openKeyboard, openChoice, openPanel, confirmPanel,
    setSwitch, bindSwitch, bindChoices, showField, bindField, bindStepper,
    countdown, mmss,
  };
})();
