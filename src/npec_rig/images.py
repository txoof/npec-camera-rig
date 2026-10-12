"""The one place large images are turned into something a page can show quickly.

Three layers (PLAN.md, *Images*):

1. **Originals**: full-resolution photographs on disk, never changed (captures.py).
2. **Analysis per photograph**: results that need the full image, chiefly tag detections, worked
   out once and kept in the `capture_analysis` table, so nothing decodes 64MP twice.
3. **Derived images**: anything drawn from originals (a validation map, a problem frame; later a
   gallery thumbnail or screen-sized view), made once by a named, versioned recipe and kept on disk
   under `derived_root()`, indexed in the `derived_image` table.

A derived image's key is a hash of the recipe name, its version and the exact inputs it is drawn
from, so a changed input is a new image: a stale one cannot be served. Derived images are
disposable: delete any of them, or all, and they are made again on the next request. The store is
capped by size, removing the least recently used.

Measured 2026-10-02 on the Pi: decoding a 64MP capture and finding its tags takes about 7 s, and
the validation page asked for 10 such images after a restart, one after another.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

from npec_rig.settings import db_path
from npec_rig.tags import TagDetection, detect_tags

# Bump when detect_tags changes what it finds: stored detections from an older detector are then
# worked out again rather than reused.
TAG_DETECTOR_VERSION = 1
DERIVED_MAX_BYTES = 2 * 1024**3
# One full-size decode at a time: each holds about 190MB, and the Pi has run out of memory before
# with several 64MP frames live at once (dmesg-confirmed, 2026-09-22).
_full_decode = threading.BoundedSemaphore(1)
_key_locks: dict[str, threading.Lock] = {}
_key_locks_guard = threading.Lock()
_recipes: dict[str, "Recipe"] = {}


def derived_root() -> Path:
    """Directory derived images are kept under. Read at call time, so tests can redirect it."""
    return Path(os.environ.get("NPEC_RIG_DERIVED_DIR", "/var/lib/npec-rig/derived"))


_prepared_dbs: set[Path] = set()
_prepare_guard = threading.Lock()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """A short-lived connection: committed and closed on exit (sqlite3's own `with` only
    commits). Never held while an image is being made."""
    path = db_path()
    with _prepare_guard:
        if path not in _prepared_dbs:
            path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(path, timeout=10)) as conn:
                # Switching to WAL needs the file to itself, so it is done once, not per request:
                # readers and the one writer then no longer block each other.
                conn.execute("PRAGMA journal_mode=WAL")
                _create_tables(conn)
                conn.commit()
            _prepared_dbs.add(path)
    conn = sqlite3.connect(path, timeout=10)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS derived_image ("
        " key TEXT PRIMARY KEY, recipe TEXT NOT NULL, version INTEGER NOT NULL,"
        " source TEXT NOT NULL, path TEXT NOT NULL, media_type TEXT NOT NULL,"
        " bytes INTEGER NOT NULL, created_at TEXT NOT NULL, last_used TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS capture_analysis ("
        " source TEXT NOT NULL, kind TEXT NOT NULL, version INTEGER NOT NULL,"
        " value TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (source, kind))"
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Layer 2: analysis per photograph ------------------------------------------------------------


def stored_tag_detections(source: str) -> list[TagDetection] | None:
    """The tags stored for `source` by the current detector, or None if not worked out yet. Needs
    no photograph: a derived image can be made again even if its capture was deleted."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT version, value FROM capture_analysis WHERE source = ? AND kind = 'tags'",
            (source,),
        ).fetchone()
    if row is not None and row[0] == TAG_DETECTOR_VERSION:
        return [_detection_from_json(d) for d in json.loads(row[1])]
    return None


def tag_detections(
    source: str,
    image_path: Path,
    detect: Callable[[np.ndarray], list[TagDetection]] = detect_tags,
) -> list[TagDetection]:
    """Every tag in the original at `image_path`, worked out once per photograph and detector
    version and then read from `capture_analysis`. `source` names the original (a capture
    reference such as "2026-10-01/091930_507614"). Raw detections only: anything that depends on
    a calibration is computed from them by the caller. `detect` is the detector to run when they
    are not stored yet. Two requests for the same photograph search it once."""
    stored = stored_tag_detections(source)
    if stored is not None:
        return stored
    with _key_lock(f"tags:{source}"):
        stored = stored_tag_detections(source)  # the other request may have just stored them
        if stored is not None:
            return stored
        with _full_decode:
            with Image.open(image_path) as image:
                image.load()
                # One full-size copy, not three: convert() and np.array() each copy ~190MB.
                frame = np.asarray(image if image.mode == "RGB" else image.convert("RGB"))
                detections = detect(frame)
                del frame
        _store_tags(source, detections)
    with _key_locks_guard:
        _key_locks.pop(f"tags:{source}", None)
    return detections


def _store_tags(source: str, detections: list[TagDetection]) -> None:
    value = json.dumps([_detection_to_json(d) for d in detections])
    with _connect() as conn:
        conn.execute(
            "INSERT INTO capture_analysis (source, kind, version, value, created_at)"
            " VALUES (?, 'tags', ?, ?, ?) ON CONFLICT(source, kind) DO UPDATE SET"
            " version = excluded.version, value = excluded.value, created_at = excluded.created_at",
            (source, TAG_DETECTOR_VERSION, value, _now()),
        )


def _detection_to_json(d: TagDetection) -> dict:
    return {"tag_id": d.tag_id, "corners": [list(c) for c in d.corners], "centre": list(d.centre)}


def _detection_from_json(d: dict) -> TagDetection:
    return TagDetection(
        tag_id=d["tag_id"],
        corners=tuple(tuple(c) for c in d["corners"]),
        centre=tuple(d["centre"]),
    )


def reduced_frame(image_path: Path, width: int) -> tuple[np.ndarray, float]:
    """The original at `image_path`, decoded straight to about `width` pixels wide, and its scale
    relative to the full-resolution pixel coordinates. JPEG "draft" decoding builds the image at
    1/2, 1/4 or 1/8 size without ever building the full 64MP one, a fraction of a full decode."""
    with Image.open(image_path) as image:
        full_width = image.width  # before draft() changes it
        image.draft("RGB", (width, round(width * image.height / image.width)))
        reduced = image.convert("RGB")
        if reduced.width > width:
            reduced = reduced.resize(
                (width, round(reduced.height * width / reduced.width)), Image.Resampling.LANCZOS
            )
        return np.array(reduced), reduced.width / full_width


# --- Layer 3: derived images ---------------------------------------------------------------------


@dataclass(frozen=True)
class Recipe:
    """How to make one kind of derived image. `render(inputs)` returns the encoded image bytes;
    `inputs` is everything the image is drawn from, and nothing else (it is what the key hashes).
    Bump `version` whenever `render` would draw the same inputs differently."""

    name: str
    version: int
    render: Callable[[dict], bytes]
    media_type: str = "image/jpeg"


def register(recipe: Recipe) -> Recipe:
    _recipes[recipe.name] = recipe
    return recipe


def key_for(recipe_name: str, inputs: dict) -> str:
    """The key `get` stores this image under: also usable in a URL, so a browser never reuses an
    image whose inputs have changed."""
    recipe = _recipes[recipe_name]
    blob = json.dumps({"r": recipe.name, "v": recipe.version, "i": inputs}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def get(recipe_name: str, source: str, inputs: dict) -> tuple[bytes, str]:
    """The derived image for `inputs`, as (bytes, media type): read from disk when already made,
    otherwise made once by the recipe and kept. `source` names what it was drawn from (a session,
    a capture), so it can be forgotten with it. Two requests for the same image make it once."""
    recipe = _recipes[recipe_name]
    key = key_for(recipe_name, inputs)
    _sweep_orphans_once()
    cached = _read(key)
    if cached is not None:
        return cached, recipe.media_type
    try:
        with _key_lock(key):
            cached = _read(key)
            if cached is not None:
                return cached, recipe.media_type
            content = recipe.render(inputs)
            path = derived_root() / recipe.name / f"{key}.bin"
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(content)
            tmp.replace(path)
            with _connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO derived_image"
                    " (key, recipe, version, source, path, media_type, bytes, created_at, last_used)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (key, recipe.name, recipe.version, source, str(path), recipe.media_type,
                     len(content), _now(), _now()),
                )
    finally:
        with _key_locks_guard:
            _key_locks.pop(key, None)  # stored (or failed): later requests start afresh
    prune()
    return content, recipe.media_type


_swept_roots: set[Path] = set()


def _sweep_orphans_once() -> None:
    """Once per process and folder: remove files the index does not know (a crash between writing
    a file and recording it, a half-written .tmp), which the size cap would never count."""
    root = derived_root()
    with _prepare_guard:
        if root in _swept_roots:
            return
        _swept_roots.add(root)
    if not root.exists():
        return
    with _connect() as conn:
        known = {row[0] for row in conn.execute("SELECT path FROM derived_image")}
    for path in root.rglob("*"):
        if path.is_file() and str(path) not in known:
            path.unlink(missing_ok=True)


def _key_lock(key: str) -> threading.Lock:
    with _key_locks_guard:
        return _key_locks.setdefault(key, threading.Lock())


def _read(key: str) -> bytes | None:
    """The stored image for `key`, or None if never made or its file is gone (pruned, deleted by
    hand): it is then simply made again."""
    with _connect() as conn:
        row = conn.execute("SELECT path FROM derived_image WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        try:
            content = Path(row[0]).read_bytes()
        except FileNotFoundError:
            conn.execute("DELETE FROM derived_image WHERE key = ?", (key,))
            return None
        conn.execute("UPDATE derived_image SET last_used = ? WHERE key = ?", (_now(), key))
    return content


def forget_source(source: str) -> None:
    """Remove every derived image drawn from `source` (a deleted session, a deleted capture)."""
    with _connect() as conn:
        rows = conn.execute("SELECT path FROM derived_image WHERE source = ?", (source,)).fetchall()
        conn.execute("DELETE FROM derived_image WHERE source = ?", (source,))
    for (path,) in rows:
        Path(path).unlink(missing_ok=True)


def prune(max_bytes: int | None = None) -> None:
    """Remove the least recently used derived images until the store is within `max_bytes`
    (default DERIVED_MAX_BYTES)."""
    limit = DERIVED_MAX_BYTES if max_bytes is None else max_bytes
    with _connect() as conn:
        # One sum first: the common case (within the cap) costs no scan of the whole table.
        if conn.execute("SELECT COALESCE(SUM(bytes), 0) FROM derived_image").fetchone()[0] <= limit:
            return
        rows = conn.execute(
            "SELECT key, path, bytes FROM derived_image ORDER BY last_used DESC, created_at DESC"
        ).fetchall()
        total, drop = 0, []
        for key, path, size in rows:
            total += size
            if total > limit:
                drop.append((key, path))
        conn.executemany("DELETE FROM derived_image WHERE key = ?", [(k,) for k, _ in drop])
    for _key, path in drop:
        Path(path).unlink(missing_ok=True)
