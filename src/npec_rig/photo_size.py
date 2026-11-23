"""Estimated photo size and measured plant-area change for a JPEG setting (#473).

The Setup page shows these for each choice. The sizes and area changes are measurements from
metrology log 26.1 (three stills, 9152 x 6944 px, each setting against the uncompressed still).

How a setting that was not measured is estimated. These are decisions, not measurements:

- Size per photo scales with the pixel count: the size at the measured setting times
  pixels / MEASURED_PIXELS. A different camera or scene may compress differently.
- Between two measured qualities of the same chroma, the size is interpolated linearly.
- Below the lowest measured quality (75), the size is the quality-75 size times quality / 75,
  and the estimate is marked as a guess.
- The plant-area change is given only at a measured setting; elsewhere it is unknown (None).

MB is 10**6 bytes and GB is 10**9 bytes.
"""

from dataclasses import dataclass

MEASURED_PIXELS = 9152 * 6944


@dataclass(frozen=True)
class Preset:
    """A named JPEG setting the Setup page offers."""

    key: str
    label: str
    quality: int
    chroma: str


PRESETS = (
    Preset("recommended", "Recommended", 85, "4:4:4"),
    Preset("smaller", "Smaller files", 75, "4:4:4"),
    Preset("detail", "Most detail", 95, "4:4:4"),
)
DEFAULT = PRESETS[0]

# Metrology log 26.1, "Summary over the 3 stills": quality -> (file MB, mean tray area change %).
_MEASURED = {
    "4:2:0": {75: (5.9, -1.37), 85: (8.5, -0.97), 95: (16.8, -0.72)},
    "4:4:4": {75: (7.4, -0.56), 85: (10.7, -0.36), 90: (14.0, -0.37), 95: (21.4, -0.31)},
}


@dataclass(frozen=True)
class Estimate:
    """Size and measured plant-area change for one JPEG setting."""

    mb_per_photo: float
    gb_per_day: float
    area_change_pct: float | None
    size_is_guess: bool


def estimate(quality: int, chroma: str, pixels: int, photos_per_day: float) -> Estimate:
    """Estimate a setting's photo size, daily volume and, where measured, plant-area change.

    Raises ValueError for quality outside 1 to 95, chroma not "4:2:0" or "4:4:4", pixels of 0
    or fewer, or a negative photos_per_day.
    """
    if not 1 <= quality <= 95:
        raise ValueError(f"JPEG quality must be 1 to 95, not {quality}")
    if chroma not in _MEASURED:
        raise ValueError(f"chroma must be 4:2:0 or 4:4:4, not {chroma!r}")
    if pixels <= 0:
        raise ValueError(f"pixels must be more than 0, not {pixels}")
    if photos_per_day < 0:
        raise ValueError(f"photos per day must be 0 or more, not {photos_per_day}")
    table = _MEASURED[chroma]
    lowest = min(table)
    area = None
    if quality in table:
        mb, area = table[quality]
    elif quality < lowest:
        mb = table[lowest][0] * quality / lowest
    else:
        low = max(q for q in table if q < quality)
        high = min(q for q in table if q > quality)
        share = (quality - low) / (high - low)
        mb = table[low][0] + share * (table[high][0] - table[low][0])
    mb = mb * pixels / MEASURED_PIXELS
    return Estimate(mb, mb * photos_per_day / 1000, area, quality < lowest)
