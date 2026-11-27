import cv2, numpy as np
import hybrid, methods_blue, methods_ring as mr

def find(still):
    base = methods_blue.find_photo_only(still)
    rim = mr._evidence(still); H, W = rim.shape; F = 4
    ppm = still.px_per_mm(W * F / 2, H * F / 2) / F
    res = hybrid.core(rim, ppm, F, [np.asarray(f["outline"]) for f in base])
    warn = {id(f["outline"]): f["warnings"] for f in base}
    out = []
    for corners, how in res:
        src = next((f for f in base if np.array_equal(np.asarray(f["outline"]), corners)), None)
        out.append({"outline": np.asarray(corners), "tray_id": None, "how": how,
                    "warnings": (src or {"warnings": ["no tag"]})["warnings"]})
    return out
