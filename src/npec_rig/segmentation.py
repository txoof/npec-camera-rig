"""Plant masks: which pixels of a photo are plant (#74, PLAN.md M5).

Every segmenter takes an RGB image (channels R, G, B in that order, as `images.reduced_frame`
gives) and returns a boolean mask of the same height and width, True where it sees plant. Code
that turns masks into areas depends only on that, so a model can replace the green threshold
without changes elsewhere.
"""

from typing import Protocol

import numpy as np

# Normalised excess green (2g - r - b) / (r + g + b) above which a pixel is plant, with green
# above red so yellow does not pass. Carried over from round 1 (experiments/round1-benchy, metrology
# log 15.6a), where it took flat leaves on blue trays within 10% of their scanned area, 27 of 27.
# A choice that worked, not a measured optimum.
EXG_MIN = 0.1


class Segmenter(Protocol):
    def segment(self, rgb: np.ndarray) -> np.ndarray:
        """True where `rgb` (H x W x 3, R G B) shows plant, as an H x W boolean array."""
        ...


class ExGSegmenter:
    """Excess-green threshold. No model: the permanent baseline any model has to beat."""

    def __init__(self, exg_min: float = EXG_MIN) -> None:
        self.exg_min = exg_min

    def segment(self, rgb: np.ndarray) -> np.ndarray:
        r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
        exg = (2 * g - r - b) / (r + g + b + 1e-6)
        return (exg > self.exg_min) & (g > r)


class SegmenterUnavailable(RuntimeError):
    """The segmenter cannot run on this rig."""


class HailoSegmenter:
    """A model on the Hailo-8, behind the same call as the green threshold. A stub: no model is
    chosen yet, and one is adopted only if it beats `ExGSegmenter` by a margin Aaron sets first
    (PLAN.md, Rounds)."""

    def segment(self, rgb: np.ndarray) -> np.ndarray:
        raise SegmenterUnavailable("no Hailo segmentation model is installed; use the green threshold")
