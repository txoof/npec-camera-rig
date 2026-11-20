// The in-page dialog of _ask_dialog.html, shared by the Experiments and Data pages (#454).
// askDialog.open({ title, body, ok, danger, action, cancel }): `action()` runs on OK; if it
// throws, its message shows inside the dialog, which stays open so the user can correct and try
// again. `cancel` false: one button only, for a dialog that only shows something. What `action`
// returns, if a function, runs after the dialog closed: to open the next dialog. A page sets
// `askDialog.afterAction` to refresh itself after each action, and may keep a refresh timer in
// `askDialog.timer`, stopped whenever another dialog opens.
window.askDialog = (() => {
  const el = (id) => document.getElementById(id);
  const ask = {
    dialog: el("ask"), form: el("ask-form"), title: el("ask-title"), body: el("ask-body"),
    error: el("ask-error"), ok: el("ask-ok"), cancel: el("ask-cancel"),
    timer: null, afterAction: null,
  };
  let action = null;
  ask.open = ({ title, body, ok, danger = false, action: run, cancel = true }) => {
    clearInterval(ask.timer);  // a list's refresh must not draw over another dialog
    ask.body.onclick = null;
    ask.title.textContent = title;
    ask.body.innerHTML = body;
    ask.ok.textContent = ok;
    ask.ok.className = danger ? "stop" : "";
    ask.error.textContent = "";
    ask.cancel.hidden = !cancel;
    action = run;
    ask.dialog.showModal();
    ask.ok.focus();
  };
  ask.form.addEventListener("submit", async (event) => {
    event.preventDefault();
    ask.ok.disabled = true;
    try {
      const next = await action();
      ask.dialog.close();
      if (ask.afterAction) await ask.afterAction();
      if (typeof next === "function") await next();
    } catch (err) {
      ask.error.textContent = err.message;
    } finally {
      ask.ok.disabled = false;
    }
  });
  ask.cancel.addEventListener("click", () => ask.dialog.close());
  return ask;
})();
