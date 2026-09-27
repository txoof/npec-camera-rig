// Click-to-enlarge for any .diagnostic-image, shared across every page via base.html --
// event-delegated so it works on images added to the DOM after this script runs.
(() => {
  const overlay = document.createElement("div");
  overlay.className = "lightbox-overlay";
  overlay.innerHTML =
    '<button type="button" class="lightbox-close" aria-label="Close">✕</button>' +
    '<img class="lightbox-image" alt="">';
  document.body.appendChild(overlay);

  const overlayImage = overlay.querySelector(".lightbox-image");
  const closeBtn = overlay.querySelector(".lightbox-close");

  function closeLightbox() {
    overlay.classList.remove("open");
    overlayImage.src = "";
  }

  document.addEventListener("click", (event) => {
    const image = event.target.closest(".diagnostic-image");
    if (image && image.hasAttribute("src")) {
      overlayImage.src = image.src;
      overlayImage.alt = image.alt;
      overlay.classList.add("open");
      return;
    }
    if (event.target === overlay || event.target === closeBtn) {
      closeLightbox();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeLightbox();
  });
})();
