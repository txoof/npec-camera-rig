// Fills every element with a data-validation-status attribute with the active calibration's
// validation status (GET /validation/status), for the Setup and Calibration pages. A status,
// not a block: nothing on those pages is disabled by it.
(function () {
  async function refreshValidationStatus() {
    const targets = document.querySelectorAll("[data-validation-status]");
    if (!targets.length) return;
    let status;
    try {
      const resp = await fetch("/validation/status");
      if (!resp.ok) throw new Error(resp.statusText);
      status = await resp.json();
    } catch (err) {
      status = { state: "error", text: `Validation status could not be read: ${err.message}` };
    }
    targets.forEach((el) => {
      el.dataset.validationState = status.state;
      el.querySelector(".validation-status-text").textContent = `${status.text}.`;
    });
  }
  window.refreshValidationStatus = refreshValidationStatus;
  document.addEventListener("DOMContentLoaded", refreshValidationStatus);
})();
