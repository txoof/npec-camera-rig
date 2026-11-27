"""#406, log 44 measure 6: time and memory for one full photo on the development Pi 5 with the Hailo-10H.

  pi_time_photo.py HEF JPG OUT_NPY [REPEATS] [BATCH]

Runs on the rig, with the app's venv (`~/npec_camera_rig/.venv/bin/python`, PYTHONPATH=~/npec_camera_rig/src)
for `npec_rig.images.decode_full`, the decoder the app and the training used. Steps per repeat, each timed:
decode the JPEG on disk to RGB; scale to half resolution (cv2 INTER_AREA, as train_cv.scale_img); cut 256 px
tiles at stride 192 and run them on the Hailo (uint8 RGB in, float32 logits out, batches of BATCH); blend the
logits with the 32 px edge ramp (as train_cv.infer, read 'mid192'); threshold at logit 0; resize the mask back to
full size (cv2 INTER_LINEAR on the logits, as predict_crop_from_photo). Saves the half-resolution logits of the
last repeat to OUT_NPY, to compare with the float network on the work machine. Prints one JSON line.
Cell areas are not computed (counting a mask's pixels per cell is negligible against these steps).
"""
import json
import resource
import sys
import time

import cv2
import numpy as np
from hailo_platform import FormatType, VDevice

TILE, STRIDE, EDGE = 256, 192, 32


def positions(n):
    if n <= TILE:
        return [0]
    return list(range(0, n - TILE, STRIDE)) + [n - TILE]


def weight_map():
    r = np.ones(TILE, np.float32)
    ramp = (np.arange(EDGE, dtype=np.float32) + 1) / (EDGE + 1)
    r[:EDGE], r[-EDGE:] = ramp, ramp[::-1]
    return np.outer(r, r)


def main(hef, jpg, out_npy, repeats=3, batch=8):
    from npec_rig.images import decode_full
    repeats, batch = int(repeats), int(batch)
    wm = weight_map()
    runs = []
    with VDevice(VDevice.create_params()) as vd:
        im = vd.create_infer_model(hef)
        im.set_batch_size(batch)
        im.input().set_format_type(FormatType.UINT8)
        im.output().set_format_type(FormatType.FLOAT32)
        oshape = im.output().shape
        with im.configure() as cm:
            for _ in range(repeats):
                t = {}
                t0 = time.perf_counter()
                rgb = decode_full(jpg)
                t['decode'] = time.perf_counter() - t0
                H0, W0 = rgb.shape[:2]
                t0 = time.perf_counter()
                img = cv2.resize(rgb, (round(W0 / 2), round(H0 / 2)), interpolation=cv2.INTER_AREA)
                del rgb
                t['scale'] = time.perf_counter() - t0
                H, W = img.shape[:2]
                pos = [(y, x) for y in positions(H) for x in positions(W)]
                acc = np.zeros((H, W), np.float32)
                wsum = np.zeros((H, W), np.float32)
                t_npu = t_blend = 0.0
                t0 = time.perf_counter()
                for i in range(0, len(pos), batch):
                    pb = pos[i:i + batch]
                    a = time.perf_counter()
                    binds = []
                    for y, x in pb:
                        b = cm.create_bindings()
                        b.input().set_buffer(np.ascontiguousarray(img[y:y + TILE, x:x + TILE]))
                        b.output().set_buffer(np.empty(oshape, np.float32))
                        binds.append(b)
                    cm.run(binds, 10000)
                    c = time.perf_counter()
                    t_npu += c - a
                    for (y, x), b in zip(pb, binds):
                        o = b.output().get_buffer().reshape(TILE, TILE)
                        acc[y:y + TILE, x:x + TILE] += o * wm
                        wsum[y:y + TILE, x:x + TILE] += wm
                    t_blend += time.perf_counter() - c
                t['tiles_total'] = time.perf_counter() - t0
                t['hailo_run'] = t_npu
                t['blend'] = t_blend
                t0 = time.perf_counter()
                lg = acc / wsum
                full = cv2.resize(lg, (W0, H0), interpolation=cv2.INTER_LINEAR) > 0
                t['threshold_resize'] = time.perf_counter() - t0
                t['total'] = sum(t[k] for k in ('decode', 'scale', 'tiles_total', 'threshold_resize'))
                t['plant_share_full'] = float(full.mean())
                runs.append({k: round(v, 4) for k, v in t.items()})
                del full
    np.save(out_npy, lg.astype(np.float32))
    print(json.dumps(dict(jpg=jpg, size=[W0, H0], half=[W, H], tiles=len(pos), batch=batch, output_shape=list(oshape),
                          peak_rss_mb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
                          runs=runs)))


if __name__ == '__main__':
    main(*sys.argv[1:])
