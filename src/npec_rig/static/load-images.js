// Load diagnostic images and wait until every one has loaded or failed, so the button that asked
// for them stays busy until the pictures are on screen, and a second press cannot start a second
// batch (issue #57). Shared by the calibration page's Step 5 and the calibration history
// diagnostics page.
//
// `items` is a list of [img, url]. Resolves to the number of images that failed. A failed image
// stays hidden. `.diagnostic-image` is `display: none` in the shared style.css, so these images
// are shown with style.display rather than the hidden attribute.
//
// Two buttons on one page can load the same images. A new load or a hide settles the earlier,
// still pending load of that image first, so no button waits forever on an image that was
// taken over.
function settlePending(img) {
  if (img._settlePending) img._settlePending(0);
}

window.loadDiagnosticImages = function (items) {
  return Promise.all(
    items.map(
      ([img, url]) =>
        new Promise((resolve) => {
          settlePending(img);
          const settle = (failed) => {
            img.onload = null;
            img.onerror = null;
            img._settlePending = null;
            resolve(failed);
          };
          img._settlePending = settle;
          img.onload = () => {
            img.style.display = "block";
            settle(0);
          };
          img.onerror = () => {
            img.style.display = "none";
            settle(1);
          };
          img.src = url;
        })
    )
  ).then((failures) => failures.reduce((a, b) => a + b, 0));
};

window.hideDiagnosticImages = function (imgs) {
  for (const img of imgs) {
    settlePending(img);
    img.style.display = "none";
  }
};
