"""#352, metrology log 24.5: SAM 2.1 small on the 15 outlined plant crops, against both passes."""
import sys, os, glob, csv, time
import numpy as np, cv2
import onnxruntime as ort
sys.path.insert(0, os.path.dirname(__file__))
from rois import read_zip, read_results, raster

T = '/home/pi/scratch/thr-352/'; MD = T + 'sam21/models/'; V = '/home/pi/scratch/sam297/352-sam/'
os.makedirs(V, exist_ok=True)
MEAN = np.float32([0.485, 0.456, 0.406]); STD = np.float32([0.229, 0.224, 0.225]); SAM = 1024


def sessions(enc):
    so = ort.SessionOptions(); so.intra_op_num_threads = 4; so.enable_cpu_mem_arena = False; so.enable_mem_pattern = False; p = ['CPUExecutionProvider']
    return ort.InferenceSession(MD + enc, so, providers=p), ort.InferenceSession(MD + 'prompt_encoder_mask_decoder.onnx', so, providers=p)


def grow(rgb):
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    exg = (2 * g - r - b) / (r + g + b + 1e-6)
    core = (exg > 0.1) & (g > r)
    low = ((exg > -0.045) & ~((b > r) & (b > g))).astype(np.uint8)
    n, lab = cv2.connectedComponents(low, connectivity=8, ltype=cv2.CV_32S)
    keep = np.zeros(n, bool); keep[np.unique(lab[core])] = True; keep[0] = False
    return keep[lab], lab, core


def load_pass(p):
    rs = read_zip(glob.glob(T + f'pass_{p}_*Results.roi.zip')[0]); res = read_results(glob.glob(T + f'pass_{p}_*Results.csv')[0])
    if p == 1:
        res = res[:15] + [res[16]]
    return {r['Label'].split(':')[0]: dict(area=int(r['Area']), poly=poly if typ == 0 else None) for (nm, typ, poly), r in zip(rs, res)}


P = {1: load_pass(1), 2: load_pass(2)}
STEM = '2026-11-03_105853_597207'
files = [f'{STEM}_t{t}_p{p}.tif'.replace('_t6_p1.tif', '_t6_p1b.tif') for t in (1, 3, 6) for p in range(1, 6)]
enc, dec = sessions('vision_encoder.onnx')
rows, tiles = [], []
for f in files:
    rgb = cv2.cvtColor(cv2.imread(T + 'imagej/' + f, cv2.IMREAD_UNCHANGED), cv2.COLOR_BGR2RGB); h, w = rgb.shape[:2]
    G, lab, core = grow(rgb)
    # Grow from cores' piece nearest the crop centre.
    gl = np.where(G, lab, 0); ids = [k for k in np.unique(gl) if k]
    cy, cx = h / 2, w / 2
    def dist(k):
        ys, xs = np.nonzero(gl == k); return np.min((ys - cy) ** 2 + (xs - cx) ** 2)
    k = min(ids, key=dist); piece = gl == k
    ys, xs = np.nonzero(piece); x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    px, py = max(0.25 * (x1 - x0), 12), max(0.25 * (y1 - y0), 12)
    box = [max(x0 - px, 0), max(y0 - py, 0), min(x1 + px, w), min(y1 + py, h)]
    bcx, bcy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    cand = piece & core if (piece & core).any() else piece
    cy_, cx_ = np.nonzero(cand); j = np.argmin((cy_ - bcy) ** 2 + (cx_ - bcx) ** 2); point = [cx_[j] + 0.5, cy_[j] + 0.5]
    sx, sy = SAM / w, SAM / h
    x = cv2.resize(rgb, (SAM, SAM), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255
    x = np.ascontiguousarray(((x - MEAN) / STD).transpose(2, 0, 1)[None])
    t0 = time.perf_counter(); out = enc.run(None, {'pixel_values': x}); t_enc = time.perf_counter() - t0
    t_enc8 = float('nan')
    emb = {f'image_embeddings.{i}': a for i, a in enumerate(out)}
    t0 = time.perf_counter()
    iou, masks, obj = dec.run(None, dict(emb, input_boxes=np.float32([[[box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy]]]),
                                         input_points=np.float32([[[[point[0] * sx, point[1] * sy]]]]), input_labels=np.ones((1, 1, 1), np.int64)))
    t_dec = time.perf_counter() - t0
    kbest = int(iou[0, 0].argmax())
    S = cv2.resize(masks[0, 0, kbest], (w, h), interpolation=cv2.INTER_LINEAR) > 0
    row = dict(plant=f[25:-4], sam_px=int(S.sum()), grow_px=int(piece.sum()), pred_iou=round(float(iou[0, 0, kbest]), 3),
               t_enc=round(t_enc, 2), t_enc8=round(t_enc8, 2), t_dec=round(t_dec, 3))
    for p in (1, 2):
        row[f'ratio{p}'] = round(S.sum() / P[p][f]['area'], 4); row[f'grow_ratio{p}'] = round(piece.sum() / P[p][f]['area'], 4)
        if P[p][f]['poly'] is not None:
            hm = raster(P[p][f]['poly'], w, h)
            row[f'iou{p}'] = round((S & hm).sum() / (S | hm).sum(), 4); row[f'grow_iou{p}'] = round((piece & hm).sum() / (piece | hm).sum(), 4)
            row[f'missed{p}'] = round((hm & ~S).sum() / hm.sum(), 4); row[f'extra{p}'] = round((S & ~hm).sum() / hm.sum(), 4)
    rows.append(row); print(row, flush=True)
    # Picture: crop, SAM (magenta) with pass 1 outline (white), grow from cores (magenta); box (yellow), point (cyan).
    def draw(m):
        im = rgb.copy(); im[m] = (0.4 * im[m] + 0.6 * np.array([255, 0, 255])).astype(np.uint8)
        if P[1][f]['poly'] is not None:
            hm = raster(P[1][f]['poly'], w, h); e = hm & ~cv2.erode(hm.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool); im[e] = 255
        return im
    a = draw(np.zeros_like(S)); cv2.rectangle(a, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), (255, 255, 0), 1)
    cv2.circle(a, (int(point[0]), int(point[1])), 2, (0, 255, 255), -1)
    tile = np.hstack([a, draw(S), draw(piece)]); tile = cv2.resize(tile, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
    tile = cv2.copyMakeBorder(tile, 30, 6, 0, 6, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    cv2.putText(tile, f'{row["plant"]}: SAM IoU {row.get("iou1", float("nan")):.2f}, grow from cores {row.get("grow_iou1", float("nan")):.2f}', (4, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    tiles.append(tile)
with open(T + 'sam21/per_plant.csv', 'w', newline='') as fh:
    keys = list(dict.fromkeys(k for r in rows for k in r)); wr = csv.DictWriter(fh, fieldnames=keys); wr.writeheader(); wr.writerows(rows)
Wd = max(t.shape[1] for t in tiles)
sheet = np.vstack([cv2.copyMakeBorder(t, 0, 0, 0, Wd - t.shape[1], cv2.BORDER_CONSTANT, value=(255, 255, 255)) for t in tiles])
sheet = cv2.copyMakeBorder(sheet, 0, 40, 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
cv2.putText(sheet, 'Left: crop, SAM box (yellow) and point (cyan). Middle: SAM 2.1 small. Right: grow from cores. White: hand outline pass 1. 2x', (4, sheet.shape[0] - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
cv2.imwrite(V + 'sam_vs_grow.png', cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR))


def st(k):
    v = np.array([r[k] for r in rows if k in r]); return f'{v.mean():.3f} (sd {v.std(ddof=1):.3f}, {v.min():.3f} to {v.max():.3f}, n {len(v)})'
for k in ('ratio1', 'ratio2', 'iou1', 'iou2', 'missed1', 'extra1', 'grow_ratio1', 'grow_iou1', 'grow_iou2', 'pred_iou'):
    print(k, st(k))
print('time per plant: encoder', st('t_enc'), 'decoder', st('t_dec'))
del enc
enc8, _ = sessions('vision_encoder_int8.onnx'); t8 = []
for f in files[:5]:
    rgb = cv2.cvtColor(cv2.imread(T + 'imagej/' + f, cv2.IMREAD_UNCHANGED), cv2.COLOR_BGR2RGB)
    x = cv2.resize(rgb, (SAM, SAM), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255
    x = np.ascontiguousarray(((x - MEAN) / STD).transpose(2, 0, 1)[None])
    t0 = time.perf_counter(); enc8.run(None, {'pixel_values': x}); t8.append(time.perf_counter() - t0)
print('int8 encoder, 5 plants:', ', '.join(f'{v:.2f}' for v in t8), 's')
