// Load diagnostic images and wait until every one has loaded or failed, so the button that asked
// for them stays busy until the pictures are on screen, and a second press cannot start a second
// batch (issue #57). Shared by the calibration page's Step 5 and the calibration history
// diagnostics page.
//
// `items` is a list of [img, url]. Resolves to the number of images that failed. A failed image
// stays hidden. `.diagnostic-image` is `display: none` in the shared style.css, so these images
// are shown with style.display rather than the hidden attribute.
window.loadDiagnosticImages = function (items) {
  return Promise.all(
    items.map(
      ([img, url]) =>
        new Promise((resolve) => {
          img.onload = () => {
            img.style.display = "block";
            resolve(0);
          };
          img.onerror = () => {
            img.style.display = "none";
            resolve(1);
          };
          img.src = url;
        })
    )
  ).then((failures) => failures.reduce((a, b) => a + b, 0));
};

window.hideDiagnosticImages = function (imgs) {
  for (const img of imgs) {
    img.onload = null;
    img.onerror = null;
    img.style.display = "none";
  }
};
