"""Grow from leaf cores (#363) against the reference set of #402 (metrology log 33).

The drafts in `experiments/round3-classifier/data/drafts/` were drawn by the reference
implementation (`experiments/round3-classifier/code/ruleg402.py`) on each whole tray and then cut
to the cell's crop; `manifest.csv` column `cut_h` is the lower cutoff each tray used. Given that
cutoff and the crop as its tray box, the app's method must draw the same mask, pixel for pixel.

The crops are chosen so that nothing outside them changes the answer: no tray tag and no white
paper (fewer than 5000 white pixels in the whole crop, so no piece large enough to be left out),
and each matches the draft exactly. Of the 60 cells, 56 match exactly. The other 4 differ only
along the crop's edge, from what lies outside it (checked 2026-11-10): B18 misses 800 px at its left
edge, a leaf whose cores are outside the crop; B06, B21 and B26 have 4541, 2597 and 251 px more at
one edge, pixels the draft left out for the tag's enlarged square, white paper or the tray outline
beyond the crop.
"""

import csv
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from npec_rig.segmentation import grow_from_cores

pytestmark = pytest.mark.integration

DATA = Path(__file__).resolve().parents[1] / "experiments" / "round3-classifier" / "data"
# Both rigs, the floor cutoff and cutoffs set from the soil, small and large plants, green soil
# and a blue mat.
CELLS = ("A03", "A12", "A21", "A29", "B12", "B15")


def _manifest() -> dict[str, dict]:
    with (DATA / "manifest.csv").open() as f:
        return {row["id"]: row for row in csv.DictReader(f)}


@pytest.mark.parametrize("cell", CELLS)
def test_grow_from_leaf_cores_draws_the_reference_draft_of_each_cell(cell: str) -> None:
    row = _manifest()[cell]
    name = row["file"].rsplit(".", 1)[0]
    rgb = np.asarray(Image.open(DATA / "crops" / f"{name}.png").convert("RGB"))
    draft = np.asarray(Image.open(DATA / "drafts" / f"{name}_draft.png").convert("L")) > 127
    assert draft.any()

    grown = grow_from_cores(rgb, np.ones(rgb.shape[:2], dtype=bool), lower_cutoff=float(row["cut_h"]))
    assert int((grown.mask != draft).sum()) == 0
