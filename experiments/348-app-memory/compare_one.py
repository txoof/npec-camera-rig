"""Read one photo the way the app does and print its results and this process's peak memory (#348).

usage: PYTHONPATH=<src> python3 -I compare_one.py PHOTO.jpg
Imports whichever npec_rig is on PYTHONPATH (old main or the branch), so running it twice with
different src folders compares the two. Writes nothing; prints one JSON line.
"""
import hashlib
import json
import os
import resource
import sys
import time

sys.path.insert(0, os.environ["PYTHONPATH"])
# The rig's venv has npec_rig installed editable (a meta path finder that wins over sys.path).
sys.meta_path = [f for f in sys.meta_path if "editable" not in repr(f).lower()]

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from npec_rig import camera, images, tags  # noqa: E402
from npec_rig.tray_readings import SEGMENTER  # noqa: E402

photo = sys.argv[1]
if os.environ.get("CV_THREADS"):
    import cv2
    cv2.setNumThreads(int(os.environ["CV_THREADS"]))
new_code = hasattr(images, "decode_full")
if new_code and not os.environ.get("NO_ALLOC"):
    if os.environ.get("MMAP_BYTES"):
        images.ALLOCATOR_MMAP_BYTES = int(os.environ["MMAP_BYTES"])
    images.limit_allocator()


def peak_mb() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024


out = {"photo": os.path.basename(photo), "code": "branch" if new_code else "main",
       "module": tags.__file__, "cv_threads": os.environ.get("CV_THREADS", "default"),
       "alloc": "off" if os.environ.get("NO_ALLOC") else os.environ.get("MMAP_BYTES", "1MB")}
t = time.monotonic()

# Tags, as images.tag_detections does it.
if new_code and hasattr(tags, "grayscale_uint8"):
    frame = images.decode_full(photo)
    gray = tags.grayscale_uint8(frame)
    del frame
    detections = tags.detect_tags(gray)
    del gray
    frame = images.decode_full(photo)  # decoded again for the mask, as tray_readings does
elif new_code:
    frame = images.decode_full(photo)
    detections = tags.detect_tags(frame)
else:
    with Image.open(photo) as image:
        image.load()
        frame = np.asarray(image if image.mode == "RGB" else image.convert("RGB"))
        detections = tags.detect_tags(frame)
out["tag_seconds"] = round(time.monotonic() - t, 1)
out["tags"] = [[d.tag_id, np.asarray(d.corners).round(6).tolist()] for d in detections]
out["peak_after_tags_mb"] = peak_mb()

# Mask, as tray_readings._segment does it (same decoded frame: decoding is the same either way).
mask = SEGMENTER.segment(frame)
out["mask_sha256"] = hashlib.sha256(np.packbits(mask).tobytes()).hexdigest()
out["mask_px"] = int(mask.sum())
del mask
out["peak_after_mask_mb"] = peak_mb()

# Encode, as captures._save_photo does it: 3 channels, and 4 with a padding channel.
out["jpeg3_sha256"] = hashlib.sha256(camera.array_to_jpeg(frame)).hexdigest()
padded = np.empty(frame.shape[:2] + (4,), dtype=np.uint8)
padded[..., :3] = frame
padded[..., 3] = 255
del frame
out["jpeg4_sha256"] = hashlib.sha256(camera.array_to_jpeg(padded)).hexdigest()
del padded
out["peak_mb"] = peak_mb()
if new_code:
    images.release_freed_memory()
with open("/proc/self/status") as status:
    out["held_after_mb"] = next(int(l.split()[1]) // 1024 for l in status if l.startswith("VmRSS"))
out["seconds"] = round(time.monotonic() - t, 1)
print(json.dumps(out))
