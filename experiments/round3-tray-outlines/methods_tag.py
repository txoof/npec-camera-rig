"""Method C, the baseline: each tray where its tag places it (the rig's place_trays), nothing
from the photo. Finds no untagged tray, so it scores 0 on the development rig."""

from harness import Still


def find(still: Still) -> list[dict]:
    return [{"outline": p.outline, "tray_id": p.tray_id, "how": "tag only", "warnings": []}
            for p in still.tag_placements]
