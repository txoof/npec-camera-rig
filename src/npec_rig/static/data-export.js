// The Export tab of the Data page (#454): an experiment's export, moved from the Experiments
// page as it worked there (#65, #368, #430, #437). The export API routes are unchanged.
// dataExport.mount(root, experimentId) draws the tab for that experiment; it uses the shared
// dialog (_ask_dialog.html, static/ask-dialog.js).
window.dataExport = (() => {
  const ask = window.askDialog;
  const openAsk = ask.open;
  let experimentId = null;
  let e = null;  // the experiment, as /api/experiments gives it
  let poll = null;
  let root, status, exportButton, partsButton, message;

  function esc(text) {
    const div = document.createElement("div");
    div.textContent = text ?? "";
    return div.innerHTML;
  }
  const utc = (iso) => (iso ? `${iso.replace("T", " ").slice(0, 16)} UTC` : "");
  function displayName(x) {
    if (x.name) return x.name;
    if (x.periods.length) return `Experiment started ${utc(x.periods[0].started_at)}`;
    return `Experiment set up ${utc(x.created_at)}, not started`;
  }
  function size(bytes) {
    if (bytes < 1e6) return `${Math.max(1, Math.round(bytes / 1e3))} kB`;
    if (bytes < 1e9) return `${(bytes / 1e6).toFixed(1)} MB`;
    return `${(bytes / 1e9).toFixed(2)} GB`;
  }
  const preparing = (x) => Boolean(x.export && !x.export.finished_at);
  async function call(method, url, body) {
    const r = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await r.json();
    if (!r.ok) {
      const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join("; ") : data.detail;
      throw new Error(detail);
    }
    return data;
  }

  function completeText(x) {
    if (x.state !== "stopped") return "";
    return x.complete_export
      ? `<p>Complete export: yes, ${utc(x.complete_export.finished_at)}.</p>`
      : "<p>No complete export: no export holds every photo yet.</p>";
  }
  function exportText(x) {
    const ex = x.export;
    if (!ex) return "<p>No export yet.</p>" + completeText(x);
    if (!ex.finished_at) return `<p>Export: preparing data file, started ${utc(ex.started_at)}.</p>`;
    if (ex.error) return `<p>Export failed: ${esc(ex.error)}.</p>`;
    if (ex.removed_at) return "<p>No export on the rig.</p>" + completeText(x);
    const held = ex.photos && ex.data ? "" : ex.photos ? " (photos only)" : " (data only)";
    if (ex.photo_parts !== null) {
      return `<p>Export${held} ${utc(ex.started_at)}: ${1 + ex.photo_parts} parts.</p>` + completeText(x);
    }
    return `<p>Export${held} ${utc(ex.finished_at)}, ${ex.files} files, ${size(ex.bytes)}: `
      + `<a href="/api/exports/${ex.id}/download">Download</a></p>` + completeText(x);
  }

  function render() {
    if (!e || e.state === "purged") {
      status.innerHTML = e ? "<p>This experiment was purged: its photos and exports were deleted.</p>" : "";
      exportButton.hidden = true;
      partsButton.hidden = true;
      return;
    }
    status.innerHTML = exportText(e);
    // Export while none is being prepared; a running experiment exports the photos so far.
    exportButton.hidden = preparing(e) || e.state === "set up";
    exportButton.textContent = e.state === "running" ? "Export so far" : "Export";
    // While the data file is made (#437), Download parts shows how far it is and can stop it.
    const ex = e.export;
    partsButton.hidden = !(ex && (preparing(e) || ex.photo_parts !== null) && !ex.error);
  }

  async function refresh() {
    const all = await call("GET", "/api/experiments");
    e = all.find((x) => x.id === experimentId) || null;
    render();
    // While an export is being prepared, check again every 2 s.
    clearTimeout(poll);
    if (e && preparing(e)) poll = setTimeout(refresh, 2000);
  }

  // Export asks what goes in it (#65, #368): the data, the photos or both. Large rows, so the
  // whole row is the tap target (CLAUDE.md, Web pages). Only an export with the photos lets
  // Purge through.
  async function exportAsk(e) {
    // Expected download sizes, an order of magnitude only (Aaron, 2026-11-06): so the user
    // knows before starting whether the download takes minutes or hours. Nothing is stored on
    // the rig (#368), so there is no free space to check.
    let sizes = null;
    try {
      sizes = await call("GET", `/api/experiments/${e.id}/export-size`);
    } catch (err) {
      sizes = null;
    }
    // Rounded, as an estimate should read: "about 25 GB", "about 3.7 GB", "about 850 kB".
    const about = (bytes) => {
      const [unit, scale] = bytes >= 1e9 ? ["GB", 1e9] : bytes >= 1e6 ? ["MB", 1e6] : ["kB", 1e3];
      const n = bytes / scale;
      return `${n >= 10 ? Math.round(n) : Math.max(0.1, Math.round(n * 10) / 10)} ${unit}`;
    };
    const tick = (id, label, note) =>
      `<label for="${id}" style="display: flex; gap: 16px; align-items: center; min-height: 64px; margin-bottom: 24px; cursor: pointer">`
      + `<input type="checkbox" id="${id}" checked style="width: 32px; height: 32px; flex: none">`
      + `<span><strong>${label}</strong><br>${note}</span></label>`;
    const expected = (key) => (sizes ? ` (about ${about(sizes[key])})` : "");
    const minutes = e.interval_s ? Math.round(e.interval_s / 60) : 0;
    const taken = (e.state === "running" ? "taken so far" : "taken")
      + (minutes ? ` at ${minutes} minute intervals` : "");
    openAsk({
      title: `Export ${displayName(e)}`,
      body: "<p>What goes in the export?</p>"
        + tick("export-data", "Data", `CSV tables and data description${expected("data_bytes")}`)
        + tick("export-photos", "Photos", `Export every photo ${taken}${expected("photos_bytes")}.`)
        + "<p>To delete this experiment from the rig later (Purge), first export it with Photos "
        + "ticked, so a copy of every photo exists.</p>",
      ok: "Export",
      action: () => {
        const data = ask.body.querySelector("#export-data").checked;
        const photos = ask.body.querySelector("#export-photos").checked;
        if (!data && !photos) throw new Error("Tick Data, Photos or both.");
        return call("POST", `/api/experiments/${e.id}/export`, { data, photos })
          .then((made) => () => partsAsk(e, made.id));
      },
    });
  }

  // The parts of an export (#368): each a large download link, zipped on the rig while it
  // downloads, its size known so the browser shows progress. A tapped part shows Started at
  // once; while the dialog is open the list is read again every 2 s, and a part the rig sent to
  // its end shows Downloaded (Aaron, 2026-11-06: without a mark he downloaded parts twice and
  // missed one). Each status has a word and a symbol as well as its colour. The list scrolls,
  // with a lane on its right free of links (CLAUDE.md, Web pages).
  const partsStarted = {};  // export id -> set of part numbers tapped on this page
  async function partsAsk(e, exportId) {
    let x;
    try {
      x = await call("GET", `/api/exports/${exportId}`);
    } catch (err) {
      message.textContent = `Could not list the parts: ${err.message}`;
      return;
    }
    const started = (partsStarted[exportId] ||= new Set());
    const status = (p) => (p.sent
      ? { word: "&#10003; Downloaded", look: "background: #1f3d2b; border: 2px solid #3fb950" }
      : started.has(p.n)
        ? { word: "&#8675; Started", look: "background: #3d3416; border: 2px solid #d29922" }
        : { word: "", look: "background: #333; border: 2px solid #666" });
    const link = (p) => {
      const what = p.n === 0 ? (x.data ? "README and data" : "README") : `${p.photos} photos`;
      const st = status(p);
      return `<a href="/api/exports/${x.id}/parts/${p.n}" download data-part="${p.n}"`
        + ` style="display: flex; align-items: center; justify-content: space-between; min-height: 64px; margin-bottom: 24px; padding: 0 16px; text-decoration: none; color: #eee; border-radius: 6px; ${st.look}">`
        + `<span>Part ${p.n}: ${what}, ${size(p.bytes)}</span><strong style="white-space: nowrap; margin-left: 16px">${st.word}</strong></a>`;
    };
    // The data file is made on the rig before anything downloads (#437): the measurements of
    // every photo are read into the CSV tables. The count is of photos read, not photos sent.
    const makingText = (m) => {
      if (!m) return "Preparing data file.";
      const left = m.seconds_left === null ? ""
        : m.seconds_left < 60 ? " Less than a minute left." : ` ${Math.round(m.seconds_left / 60)} minutes left.`;
      return `Preparing data file: reading measurement ${m.photos_done.toLocaleString("en-US")} of `
        + `${m.photos.toLocaleString("en-US")}.${left}`;
    };
    const render = () => {
      if (x.error) {
        return `<p><strong>&#10007; This export did not finish:</strong> ${esc(x.error)}.</p>`
          + "<p>Close this window and tap Export to make a new one.</p>";
      }
      if (!x.finished_at) {
        const m = x.parts[0].making;
        const pct = m ? ` ${Math.floor(100 * m.photos_done / Math.max(1, m.photos))}%` : "";
        return `<p style="min-height: 64px; display: flex; align-items: center; padding: 0 16px; border-radius: 6px; background: #3d3416; border: 2px solid #d29922">`
          + `<strong>&#8987; Preparing data file${pct}</strong></p>`
          + `<p>${makingText(m)}</p>`
          + "<p>You can safely close this window or page while the export is prepared. "
          + "Tap Download parts on the Export tab to find and download the export."
          + (x.photos ? " The photo parts are listed then too." : "") + "</p>"
          + `<button type="button" class="stop" id="export-stop" style="min-height: 64px; margin-top: 24px">Stop preparation</button>`;
      }
      const done = x.parts.filter((p) => p.sent).length;
      return `<p>${x.parts.length} ${x.parts.length === 1 ? "part" : "parts"}, <strong>${done} downloaded</strong>. Download each one and unzip them all `
        + `into the same folder. A part that fails can be downloaded again on its own.</p>`
        + `<div id="parts-list" style="max-height: 300px; overflow-y: auto; padding-right: 64px">${x.parts.map(link).join("")}</div>`;
    };
    const redraw = () => {
      const list = ask.body.querySelector("#parts-list");
      const scroll = list ? list.scrollTop : 0;
      ask.body.innerHTML = render();
      const after = ask.body.querySelector("#parts-list");
      if (after) after.scrollTop = scroll;
    };
    openAsk({
      title: `Download ${displayName(e)}`,
      body: render(),
      ok: "Close",
      cancel: false,
      action: () => null,
    });
    ask.body.onclick = async (event) => {
      const stop = event.target.closest("#export-stop");
      if (stop) {
        stop.disabled = true;
        stop.textContent = "Stopping...";
        try {
          x = await call("POST", `/api/exports/${exportId}/stop`);
        } catch (err) {
          stop.textContent = `Could not stop it: ${err.message}`;
          return;
        }
        redraw();
        refresh();
        return;
      }
      const a = event.target.closest("a[data-part]");
      if (!a) return;
      started.add(Number(a.dataset.part));
      setTimeout(redraw, 0);  // after the browser has taken the link
    };
    clearInterval(ask.timer);
    ask.timer = setInterval(async () => {
      if (!ask.dialog.open) { clearInterval(ask.timer); ask.body.onclick = null; return; }
      try {
        const was = x.finished_at;
        x = await call("GET", `/api/exports/${exportId}`);
        redraw();
        if (!was && x.finished_at) refresh();
      } catch (err) {
        // Keep the list as it is; the next read may work.
      }
    }, 2000);
  }

  function mount(rootEl, id) {
    root = rootEl;
    experimentId = id;
    status = root.querySelector("#ex-status");
    exportButton = root.querySelector("#ex-export");
    partsButton = root.querySelector("#ex-parts");
    message = root.querySelector("#ex-message");
    ask.afterAction = () => refresh();
    exportButton.addEventListener("click", () => { message.textContent = ""; exportAsk(e); });
    partsButton.addEventListener("click", () => { message.textContent = ""; partsAsk(e, e.export.id); });
    refresh().catch((err) => { message.textContent = `Could not read the export: ${err.message}`; });
  }

  return { mount };
})();
