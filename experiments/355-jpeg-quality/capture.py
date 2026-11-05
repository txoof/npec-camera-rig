"""Take N full-size stills with the app's camera settings and keep each as an uncompressed array
(metrology log 26, #355). Run on the rig with the app STOPPED (it holds the camera).

    python capture.py OUT_DIR [N]

Writes OUT_DIR/frame<i>.npy and OUT_DIR/frame<i>.json (sensor metadata, focus status, controls).
"""
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from npec_rig.camera import CameraManager, Picamera2Backend

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=False)  # a new folder per run, never overwrite
n = int(sys.argv[2]) if len(sys.argv) > 2 else 3

manager = CameraManager(Picamera2Backend())  # replays saved settings, drives the lens
print("focus", manager.focus_status(), flush=True)
print("controls", manager.get_controls(), flush=True)
try:
    for i in range(n):
        t = datetime.now(UTC).isoformat()
        array, meta = manager._capture_full_res()
        np.save(out / f"frame{i}.npy", array)
        record = {"taken_at": t, "shape": list(array.shape), "dtype": str(array.dtype),
                  "sensor_metadata": meta, "focus": manager.focus_status(),
                  "controls": manager.get_controls()}
        (out / f"frame{i}.json").write_text(json.dumps(record, indent=1, default=str))
        print(i, t, array.shape, meta, flush=True)
        del array
        time.sleep(2)
finally:
    manager._backend.close()
