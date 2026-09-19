from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from npec_rig.camera import array_to_jpeg


def captures_root() -> Path:
    return Path(os.environ.get("NPEC_RIG_CAPTURES_DIR", "/var/lib/npec-rig/captures"))


def save_capture(image: np.ndarray, metadata: dict) -> dict:
    timestamp = datetime.now(timezone.utc)
    day_dir = captures_root() / timestamp.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)

    stem = timestamp.strftime("%H%M%S_%f")
    jpeg_path = day_dir / f"{stem}.jpg"
    json_path = day_dir / f"{stem}.json"

    jpeg_path.write_bytes(array_to_jpeg(image))
    record = {"timestamp": timestamp.isoformat(), **metadata}
    json_path.write_text(json.dumps(record, indent=2, default=str))

    return {
        "date": timestamp.strftime("%Y-%m-%d"),
        "filename": jpeg_path.name,
        "url": f"/captures/{timestamp.strftime('%Y-%m-%d')}/{jpeg_path.name}",
        **record,
    }


def list_recent_captures(limit: int = 12) -> list[dict]:
    root = captures_root()
    if not root.exists():
        return []

    entries: list[dict] = []
    for day_dir in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        for jpeg_path in sorted(day_dir.glob("*.jpg"), reverse=True):
            json_path = jpeg_path.with_suffix(".json")
            record = json.loads(json_path.read_text()) if json_path.exists() else {}
            entries.append(
                {
                    "date": day_dir.name,
                    "filename": jpeg_path.name,
                    "url": f"/captures/{day_dir.name}/{jpeg_path.name}",
                    **record,
                }
            )
            if len(entries) >= limit:
                return entries
    return entries
