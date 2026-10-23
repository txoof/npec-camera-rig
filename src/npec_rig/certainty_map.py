"""Per-slot area certainty: how much a measured area can be trusted in each tray slot.

Answers the supervisor's question directly ("if we measure an area in this part of the table, how
much can we depend on it?") with one number per slot, measured, not derived (CLAUDE.md): every
calibration tag is an object of known area, so its area error is observed directly, and a slot's
certainty is the 95th percentile of |error| over the tags that have sat in it.

The numbers only mean something for captures taken after the targets were moved. The calibration
frame itself flatters the rig -- its scale field was fitted to those very tags -- which is how a
-3.2% spot at the table centre and a batch of 96%-scale prints both stayed hidden until the sheets
were shuffled (2026-09-29). Callers pass validation captures, not the calibration frame.

Slots are fixed by the calibration frame: one calibration sheet sits on each tray, 2 rows
(North, South) of `columns` trays. A later capture's sheets are assigned to the nearest slot centre
as whole sheets, so one sheet's tags never split between two slots.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from npec_rig.calibration import ScaleField
from npec_rig.tags import CALIBRATION_ID_RANGE, TagDetection, tag_area_px
from npec_rig.tray_placement import TrayPlacement, place_trays

# Tags on one sheet sit ~40mm apart centre to centre; neighbouring trays' sheets are further apart
# than this. Measured on the 2026-09-29 tray and table layouts (300px at ~4.5-4.8 px/mm worked on
# both). In mm, not px, so it holds if the camera distance changes.
SHEET_LINK_MM = 65.0
MIN_TAGS_PER_SHEET = 5
DEFAULT_COLUMNS = 6
# Below this many tags a slot's 95th percentile is little more than its single worst tag.
MIN_TAGS_PER_SLOT = 10
ROW_NAMES = ("North", "South")
# A validation round counts only if most of its tags sit somewhere new: more than MOVED_MM from
# every tag of the calibration frame and of each earlier counted round, for at least
# MIN_MOVED_FRACTION of them. On 2026-09-29 a real shuffle moved 83-90% of tags; a repeat
# capture of an untouched layout moved none (sub-mm scene shift only).
MOVED_MM = 5.0
MIN_MOVED_FRACTION = 0.5

_FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
MAP_WIDTH_PX = 2000


@dataclass(frozen=True)
class TagError:
    tag_id: int
    x: float
    y: float
    error_pct: float  # signed: measured area vs the calliper-measured true area


@dataclass(frozen=True)
class Sheet:
    tags: tuple[TagError, ...]
    centre: tuple[float, float]
    box: tuple[float, float, float, float]  # x0, y0, x1, y1 over its tags' corners


@dataclass(frozen=True)
class Slot:
    name: str
    centre: tuple[float, float]
    box: tuple[float, float, float, float]


@dataclass(frozen=True)
class SlotResult:
    name: str
    n: int
    p95_abs_pct: float | None  # None when n < MIN_TAGS_PER_SLOT ("not measured")
    median_pct: float | None


class SlotLayoutError(ValueError):
    """The frame doesn't show the sheet layout the slots are defined by."""


def tag_errors(
    detections: list[TagDetection], scale_field: ScaleField, tag_size_mm: float
) -> tuple[list[TagError], dict[int, tuple[tuple[float, float], ...]]]:
    """Signed % area error of every calibration tag, plus each result's corners by list index
    (kept separate so `TagError` stays a small value type)."""
    true_area_mm2 = tag_size_mm**2
    errors, corners = [], {}
    for d in detections:
        if d.tag_id not in CALIBRATION_ID_RANGE:
            continue
        x, y = d.centre
        area_mm2 = tag_area_px(d.corners) / scale_field.px_per_mm(x, y) ** 2
        corners[len(errors)] = d.corners
        errors.append(TagError(d.tag_id, x, y, 100 * (area_mm2 / true_area_mm2 - 1)))
    return errors, corners


def group_sheets(
    detections: list[TagDetection], scale_field: ScaleField, tag_size_mm: float
) -> list[Sheet]:
    """Calibration tags grouped into printed sheets: tags within `SHEET_LINK_MM` of each other are
    on the same sheet. Tag IDs are unique within a sheet and repeat across sheets, so a repeated ID
    inside one group means two sheets are touching -- refused, rather than silently pooled."""
    errors, corners = tag_errors(detections, scale_field, tag_size_mm)
    if not errors:
        return []
    xy = np.array([(e.x, e.y) for e in errors])
    link_px = np.array([SHEET_LINK_MM * scale_field.px_per_mm(e.x, e.y) for e in errors])

    parent = list(range(len(errors)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(errors)):
        close = np.flatnonzero(np.hypot(*(xy[i + 1 :] - xy[i]).T) < link_px[i]) + i + 1
        for j in close:
            parent[find(int(j))] = find(i)

    groups: dict[int, list[int]] = {}
    for i in range(len(errors)):
        groups.setdefault(find(i), []).append(i)

    sheets = []
    for members in groups.values():
        if len(members) < MIN_TAGS_PER_SHEET:
            continue
        ids = [errors[i].tag_id for i in members]
        if len(set(ids)) != len(ids):
            cx, cy = xy[members].mean(axis=0)
            raise SlotLayoutError(
                f"two sheets are touching near pixel ({cx:.0f}, {cy:.0f}): move them apart so "
                "each tray's sheet is separate"
            )
        pts = np.array([p for i in members for p in corners[i]])
        cx, cy = xy[members].mean(axis=0)
        sheets.append(
            Sheet(
                tags=tuple(errors[i] for i in members),
                centre=(float(cx), float(cy)),
                box=(*map(float, pts.min(axis=0)), *map(float, pts.max(axis=0))),
            )
        )
    return sheets


def build_slot_layout(sheets: list[Sheet], columns: int = DEFAULT_COLUMNS) -> tuple[Slot, ...]:
    """Tray slots from the calibration frame's sheets: the `columns` northmost (smallest y) are the
    North row, the rest South, each numbered 1.. from west (smallest x)."""
    expected = len(ROW_NAMES) * columns
    if len(sheets) != expected:
        raise SlotLayoutError(
            f"found {len(sheets)} calibration sheets, expected {expected} (one per tray)"
        )
    by_y = sorted(sheets, key=lambda s: s.centre[1])
    slots = []
    for row, name in enumerate(ROW_NAMES):
        row_sheets = sorted(by_y[row * columns : (row + 1) * columns], key=lambda s: s.centre[0])
        slots += [Slot(f"{name} {i + 1}", s.centre, s.box) for i, s in enumerate(row_sheets)]
    return tuple(slots)


def _sheet_text(sheet: Sheet) -> str:
    ids = [t.tag_id for t in sheet.tags]
    return f"the sheet with tags {min(ids)} to {max(ids)}"


def _off_slot_text(
    sheet: Sheet, layout: tuple[Slot, ...], scale_field: ScaleField, trays: list[TrayPlacement]
) -> str:
    """Where an off-slot sheet is, in the chamber's words: its tag IDs, its offset in mm from the
    nearest slot centre (north is up the photo, west is left), the tray whose centre is nearest
    when tray tags are in the photo, and which slot it lies towards:
    the one in the direction it moved, not merely the second nearest (a sheet moved south of
    North 1 is nearer North 2 than South 1)."""
    centres = np.array([slot.centre for slot in layout])
    nearest = int(np.argmin(np.hypot(*(centres - sheet.centre).T)))
    offset = np.array(sheet.centre) - centres[nearest]
    others = [i for i in range(len(layout)) if i != nearest]
    directions = centres[others] - centres[nearest]
    distances = np.hypot(*directions.T)
    # Nearest slot within 45 degrees of the offset, if any.
    aligned = directions @ offset / (distances * np.hypot(*offset)) > np.cos(np.pi / 4)
    towards = others[int(np.argmin(np.where(aligned, distances, np.inf)))] if aligned.any() else None
    px_per_mm = scale_field.px_per_mm(*sheet.centre)
    east_mm, south_mm = offset / px_per_mm
    parts = [
        f"{abs(round(mm, -1)):.0f} mm {name}"
        for mm, name in ((south_mm, "south" if south_mm > 0 else "north"),
                         (east_mm, "east" if east_mm > 0 else "west"))
        if abs(round(mm, -1)) >= 10
    ]
    text = f"{_sheet_text(sheet)} is about {' and '.join(parts)} of {layout[nearest].name}"
    text += (
        ", outside the slots"
        if towards is None
        else f", between {layout[nearest].name} and {layout[towards].name}"
    )
    if trays:
        tray = min(trays, key=lambda t: np.hypot(*(np.array(t.centre) - sheet.centre)))
        text += f", nearest tray {tray.tray_id}"
    return text


def sheets_by_slot(
    sheets: list[Sheet],
    layout: tuple[Slot, ...],
    scale_field: ScaleField,
    trays: list[TrayPlacement] | None = None,
) -> dict[str, Sheet]:
    """Each sheet under the name of the slot whose centre is nearest the sheet's.

    Refused rather than guessed: a sheet more than half the closest slot spacing from every slot
    centre (it isn't on a tray slot), or two sheets on one slot in the same capture (one tray
    holds one sheet). Either would silently pool a sheet's tags into the wrong slot. An off-slot
    sheet is named by its nearest slot and its distance from it, not a pixel position, and by
    the nearest of `trays` (placed from the same photo's tray tags) when given (#257)."""
    centres = np.array([slot.centre for slot in layout])
    spacing = np.hypot(*(centres[:, None, :] - centres[None, :, :]).transpose(2, 0, 1))
    max_offset = np.min(spacing[spacing > 0]) / 2
    placed: dict[str, Sheet] = {}
    for sheet in sheets:
        distances = np.hypot(*(centres - sheet.centre).T)
        nearest = int(np.argmin(distances))
        name = layout[nearest].name
        if distances[nearest] > max_offset:
            raise SlotLayoutError(
                f"{_off_slot_text(sheet, layout, scale_field, trays or [])}, not on any tray slot: "
                "put it back on its tray"
            )
        if name in placed:
            raise SlotLayoutError(
                f"two sheets are on slot {name}, {_sheet_text(placed[name])} and "
                f"{_sheet_text(sheet)}: one sheet per tray"
            )
        placed[name] = sheet
    return placed


def assign_to_slots(
    detections: list[TagDetection], layout: tuple[Slot, ...], scale_field: ScaleField, tag_size_mm: float
) -> dict[str, list[TagError]]:
    """Each sheet's tags, whole, under its slot's name (see `sheets_by_slot`); [] for an empty slot."""
    placed = sheets_by_slot(
        group_sheets(detections, scale_field, tag_size_mm),
        layout,
        scale_field,
        place_trays(detections, scale_field, slot_layout_to_dict(layout)),
    )
    return {slot.name: list(placed[slot.name].tags) if slot.name in placed else [] for slot in layout}


def slot_results(assigned: dict[str, list[TagError]]) -> list[SlotResult]:
    return slot_results_from_errors({name: [t.error_pct for t in tags] for name, tags in assigned.items()})


def slot_results_from_errors(errors_by_slot: dict[str, list[float]]) -> list[SlotResult]:
    """`slot_results` from plain signed % errors per slot, e.g. pooled from a saved validation
    session rather than from live detections."""
    results = []
    for name, values in errors_by_slot.items():
        errs = np.array(values, dtype=float)
        if len(errs) < MIN_TAGS_PER_SLOT:
            results.append(SlotResult(name, len(errs), None, None))
        else:
            results.append(
                SlotResult(
                    name,
                    len(errs),
                    float(np.percentile(np.abs(errs), 95)),
                    float(np.median(errs)),
                )
            )
    return results


def certainty_by_slot(
    calibration_detections: list[TagDetection],
    capture_detections: list[list[TagDetection]],
    scale_field: ScaleField,
    tag_size_mm: float,
    columns: int = DEFAULT_COLUMNS,
) -> tuple[tuple[Slot, ...], list[SlotResult]]:
    """Slot layout from the calibration frame, and each slot's certainty pooled over `capture_
    detections` (one list per validation capture)."""
    layout = build_slot_layout(group_sheets(calibration_detections, scale_field, tag_size_mm), columns)
    pooled: dict[str, list[TagError]] = {slot.name: [] for slot in layout}
    for detections in capture_detections:
        for name, tags in assign_to_slots(detections, layout, scale_field, tag_size_mm).items():
            pooled[name].extend(tags)
    return layout, slot_results(pooled)


def calibration_centres(detections: list[TagDetection]) -> list[tuple[float, float]]:
    """Centres of the calibration tags in `detections` -- all a later round needs to tell whether
    the sheets have moved since."""
    return [d.centre for d in detections if d.tag_id in CALIBRATION_ID_RANGE]


def moved_fraction(
    centres: list[tuple[float, float]],
    references: list[list[tuple[float, float]]],
    scale_field: ScaleField,
) -> float:
    """Fraction of `centres` that moved more than `MOVED_MM` from every earlier position: a tag
    counts as moved only if it is far from all tags of every reference layout (the calibration
    frame and each earlier counted round). Judged per tag, not per reference, so a round that puts
    some sheets back where the calibration had them and others back where round 1 had them does
    not count as new."""
    if not centres:
        return 0.0
    xy = np.array(centres, dtype=float)
    limit = np.array([MOVED_MM * scale_field.px_per_mm(x, y) for x, y in xy])
    moved = np.ones(len(xy), dtype=bool)
    for reference in references:
        if not reference:
            continue
        ref = np.array(reference, dtype=float)
        nearest = np.min(np.hypot(*(xy[:, None, :] - ref[None, :, :]).transpose(2, 0, 1)), axis=1)
        moved &= nearest > limit
    return float(np.mean(moved))


def round_errors_by_slot(
    detections: list[TagDetection],
    layout: tuple[Slot, ...],
    scale_field: ScaleField,
    tag_size_mm: float,
) -> dict[str, list[float]]:
    """One validation round's signed % errors per slot. Every slot must hold exactly one sheet:
    a round with a sheet missing (or the camera seeing no tags at all) is refused, not pooled."""
    sheets = group_sheets(detections, scale_field, tag_size_mm)
    if len(sheets) != len(layout):
        raise SlotLayoutError(
            f"found {len(sheets)} calibration sheets, expected {len(layout)} (one per tray)"
        )
    return {
        name: [t.error_pct for t in tags]
        for name, tags in assign_to_slots(detections, layout, scale_field, tag_size_mm).items()
    }


def slot_layout_to_dict(layout: tuple[Slot, ...]) -> list[dict]:
    return [{"name": s.name, "centre": list(s.centre), "box": list(s.box)} for s in layout]


def slot_layout_from_dict(data: list[dict]) -> tuple[Slot, ...]:
    return tuple(Slot(d["name"], tuple(d["centre"]), tuple(d["box"])) for d in data)


def _font(size: int) -> ImageFont.ImageFont:
    if _FONT_PATH.exists():
        return ImageFont.truetype(str(_FONT_PATH), size)
    return ImageFont.load_default()


def render_certainty_map(
    frame: np.ndarray,
    layout: tuple[Slot, ...],
    results: list[SlotResult],
    caption: str,
    frame_scale: float = 1.0,
) -> np.ndarray:
    """The camera frame with each slot boxed and labelled "within +/-Z%" and its tag count, slots
    below `MIN_TAGS_PER_SLOT` greyed "not measured", and `caption` underneath. No axes or plots:
    the supervisor asked for one image with a number per zone.

    `frame` may already be downscaled; `frame_scale` is its size relative to the full-resolution
    pixel coordinates the slots are in. The result is `MAP_WIDTH_PX` wide.
    """
    s = MAP_WIDTH_PX / frame.shape[1]
    image = Image.fromarray(frame).resize(
        (MAP_WIDTH_PX, round(frame.shape[0] * s)), Image.Resampling.LANCZOS
    ).convert("RGBA")
    s *= frame_scale
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    big, small = _font(52), _font(26)
    by_name = {r.name: r for r in results}

    for slot in layout:
        result = by_name[slot.name]
        x0, y0, x1, y1 = (v * s for v in slot.box)
        box = (x0 - 12, y0 - 12, x1 + 12, y1 + 12)
        measured = result.p95_abs_pct is not None
        draw.rectangle(
            box,
            fill=(0, 0, 0, 110) if measured else (128, 128, 128, 170),
            outline=(255, 255, 0, 255),
            width=4,
        )
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        lines = [
            (slot.name, small, -100),
            ("within" if measured else "", small, -58),
            (f"±{result.p95_abs_pct:.1f}%" if measured else "not measured", big if measured else small, -14),
            (f"N = {result.n}", small, 34),
        ]
        for text, font, dy in lines:
            if text:
                draw.text(
                    (cx, cy + dy), text, font=font, fill="white", anchor="mm",
                    stroke_width=3 if font is big else 2, stroke_fill="black",
                )

    image = Image.alpha_composite(image, overlay).convert("RGB")
    canvas = Image.new("RGB", (image.width, image.height + 90), "white")
    canvas.paste(image, (0, 0))
    ImageDraw.Draw(canvas).text((20, image.height + 45), caption, font=_font(24), fill="black", anchor="lm")
    return np.asarray(canvas)


PROBLEM_RED = (220, 30, 30)


def render_problem_frame(
    frame: np.ndarray,
    boxes: dict[str, tuple[float, float, float, float]],
    labels: dict[str, str],
    caption: str,
    whole_frame: bool = False,
    frame_scale: float = 1.0,
) -> np.ndarray:
    """The full camera frame (never a crop, Aaron 2026-09-30), with a thick red border and label
    around each problem sheet in `boxes` (full-resolution pixel boxes, keyed like `labels`), or
    around the whole frame when `whole_frame`, and `caption` underneath. `MAP_WIDTH_PX` wide."""
    s = MAP_WIDTH_PX / frame.shape[1]
    image = Image.fromarray(frame).resize(
        (MAP_WIDTH_PX, round(frame.shape[0] * s)), Image.Resampling.LANCZOS
    ).convert("RGB")
    s *= frame_scale
    draw = ImageDraw.Draw(image)
    font = _font(40)
    for name, (x0, y0, x1, y1) in boxes.items():
        box = (x0 * s - 20, y0 * s - 20, x1 * s + 20, y1 * s + 20)
        draw.rectangle(box, outline=PROBLEM_RED, width=12)
        draw.text(
            ((box[0] + box[2]) / 2, box[1] - 12), labels[name], font=font, fill="white",
            anchor="md", stroke_width=6, stroke_fill=PROBLEM_RED,
        )
    if whole_frame:
        draw.rectangle((0, 0, image.width - 1, image.height - 1), outline=PROBLEM_RED, width=24)
    canvas = Image.new("RGB", (image.width, image.height + 90), "white")
    canvas.paste(image, (0, 0))
    ImageDraw.Draw(canvas).text((20, image.height + 45), caption, font=_font(28), fill=PROBLEM_RED, anchor="lm")
    return np.asarray(canvas)
