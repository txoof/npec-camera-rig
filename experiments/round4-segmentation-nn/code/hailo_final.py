"""#406 stage G: compile the final plant network (stage F) for both Hailo chips, and measure the 8-bit loss on the
training truth cells by cross-validation, with the 5 stage E fold models quantised the same way. CPU only, no chip:
Hailo's emulator (SDK_QUANTIZED). Method written before it was run (2026-11-21).

Host steps (training env: `source /home/txoof/temp.nobackup/npec-406-nn/env.sh`):

    hailo_final.py prep  --model final       # ONNX + ORT check, calibration tiles, 200 check tiles + torch logits
    hailo_final.py prep  --model f0 .. f4    # ONNX + ORT check, calibration tiles, held-out cell tiles + torch logits,
                                             # and the check that stitching the torch tiles gives E's saved masks
    hailo_final.py score --model fK --arch hailo8|hailo10h   # stitch the quantised tiles, score against the truth
    hailo_final.py check --model final --arch ...            # final network: quantised against float on check tiles

Container steps (one docker run each, image npec406/hailo-<chip>, see run_fg.sh):

    hailo_final.py parse    --model M --arch A
    hailo_final.py optimize --model M --arch A   # level 1, CALIB tiles (1024, or 256 if the CPU time is too long)
    hailo_final.py emulate  --model M --arch A   # SDK_QUANTIZED on the cell tiles (folds) or check tiles (final)
    hailo_final.py compile  --model M --arch A   # HEF (final network only; the fold models are not compiled)

Models. 'final' = runs/s2_final_e40 (stage F, every training day; the network that ships; HEFs in hailo/final/).
'fK' = runs/s2_fK_e40 (stage E fold K, K = 0..4 as run folders number them, "fold K+1" in the stage tables).
All: smp 0.6.0 Unet, mobilenet_v2 encoder, 1 logit, input 1x3x256x256. ONNX opset 13 (legacy exporter), simplified;
end node /segmentation_head/segmentation_head.0/Conv. ImageNet normalisation in the model script (mean and std x 255),
so the HEF takes uint8 RGB. Model script as trial A except the level and the calibration size:
optimization_level=1, compression_level=0, calibration batch 8, calibset_size = number of calibration tiles.

Calibration tiles. Centre 256 px of the 320 px half-resolution photo patches of the stage A cache (`cache/s2/mm`),
only photos of the model's training dates (its meta.json `held_out_dates` excluded: a fold model never sees a
held-out date, not even in calibration; the final network uses every training photo). Never a truth crop. Half the
tiles are 'plant' patches (some labelled plant pixel in the 256 centre), half 'no plant'. Within each half, the
quota is shared equally over the UTC dates that have such patches (dates with too few give what they have; the
rest is shared over the others), and within a date the tiles are drawn uniformly over (photo, patch) pairs.
Seed 406 + model number. Default 1024 tiles (the DFC's own suggestion); the count used is in calib.json.

Cell tiles (fold models). The fold's held-out training cells, read exactly as train_cv scores them: production
cells from the whole photo at half resolution (decode_full, area-averaged to 4576 x 3472), development cells from the
crop at half resolution reflect-padded to >= 256 px; 256 px tiles at stride 192 (train_cv.positions). The torch float32
logits of the same tiles are kept; stitching them (logits blended with the 32 px edge ramp, bilinear resize to full
size, logit > 0) must give back E's saved masks (pred/s2_e40) - the check that the quantised path is the float path
with only the network swapped. The quantised logits are stitched the same way and scored against the current truth
files: per cell IoU and area ratio, then per rig pooled IoU, mean IoU, mean |area ratio - 1|, as train_cv.

Check tiles (final network). 200 more tiles, the same stratification, patches not used for calibration; quantised
against the torch float logits (mean |logit difference|, IoU at 0.5), as trial A. Seen in training, so not a score
against the truth.
"""
import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
NN = Path('/home/txoof/temp.nobackup/npec-406-nn')
TRAIN = NN / 'analysis' / 'train'
CACHE = TRAIN / 'cache' / 's2' / 'mm'
HROOT = NN / 'hailo'
SIZE = 256
SEED = 406
N_CHECK = 200
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]
END_NODE = '/segmentation_head/segmentation_head.0/Conv'
LEVEL = 1
MODELS = ['final'] + [f'f{k}' for k in range(5)]


def run_dir(model):
    return TRAIN / 'runs' / ('s2_final_e40' if model == 'final' else f's2_{model}_e40')


def out_dir(model):
    return HROOT / 'final' if model == 'final' else HROOT / 'stage-G' / model


def net_name(model):
    return 'plantseg_s2_final_e40' if model == 'final' else f'plantseg_s2_{model}_e40'


def calib_n():
    """Calibration tile count: hailo/stage-G/calib_n.txt if present (set by the driver), else 1024."""
    f = HROOT / 'stage-G' / 'calib_n.txt'
    return int(f.read_text().strip()) if f.exists() else 1024


def alls(level, n_calib):
    m = ', '.join(f'{v * 255:.3f}' for v in MEAN)
    s = ', '.join(f'{v * 255:.3f}' for v in STD)
    return (f'normalization1 = normalization([{m}], [{s}])\n'
            f'model_optimization_flavor(optimization_level={level}, compression_level=0)\n'
            f'model_optimization_config(calibration, batch_size=8, calibset_size={n_calib})\n')


def record(d, step, t0, **extra):
    s = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    c = round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024)
    row = dict(step=step, seconds=round(time.time() - t0, 1), peak_rss_mib_self=s, peak_rss_mib_children=c,
               utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), **extra)
    print(json.dumps(row), flush=True)
    with open(d / 'steps.jsonl', 'a') as f:
        f.write(json.dumps(row) + '\n')


# ---------------------------------------------------------------- host: network, tiles

def load_torch(model, device='cpu'):
    import torch
    import segmentation_models_pytorch as smp
    m = smp.Unet('mobilenet_v2', encoder_weights=None, in_channels=3, classes=1)
    m.load_state_dict(torch.load(run_dir(model) / 'model.pt', map_location='cpu'))
    return m.eval().to(device)


def torch_logits(net, tiles_u8, batch=16, device='cpu'):
    """uint8 NHWC -> float32 logits NHW, train_cv.infer's preprocessing, float32."""
    import torch
    m = torch.tensor(MEAN, device=device).view(1, 3, 1, 1)
    sd = torch.tensor(STD, device=device).view(1, 3, 1, 1)
    out = []
    with torch.no_grad():
        for i in range(0, len(tiles_u8), batch):
            x = torch.from_numpy(np.ascontiguousarray(tiles_u8[i:i + batch])).to(device).permute(0, 3, 1, 2).float() / 255
            out.append(net((x - m) / sd)[:, 0].float().cpu().numpy())
    return np.concatenate(out).astype(np.float32)


def export(model, d):
    import torch
    import onnx
    import onnxruntime as ort
    from onnxsim import simplify
    net = load_torch(model)
    raw, sim = d / f'{net_name(model)}_op13.onnx', d / f'{net_name(model)}_op13_sim.onnx'
    torch.onnx.export(net, torch.zeros(1, 3, SIZE, SIZE), str(raw), opset_version=13, dynamo=False,
                      input_names=['input'], output_names=['logits'], do_constant_folding=True)
    m, ok = simplify(onnx.load(str(raw)))
    assert ok
    onnx.save(m, str(sim))
    tiles = np.load(d / 'calib_tiles.npy', mmap_mode='r')[:8]
    ref = torch_logits(net, tiles)
    sess = ort.InferenceSession(str(sim), providers=['CPUExecutionProvider'])
    x = ((tiles.astype(np.float32) / 255 - np.array(MEAN, np.float32)) / np.array(STD, np.float32))
    got = np.concatenate([sess.run(None, {'input': x[i:i + 1].transpose(0, 3, 1, 2)})[0][:, 0] for i in range(len(x))])
    dd = np.abs(got - ref)
    res = dict(onnx=str(sim), opset=13, ops=sorted({n.op_type for n in m.graph.node}), nodes=len(m.graph.node),
               end_node=[n.name for n in m.graph.node if n.output[0] == 'logits'],
               ort_vs_torch_max_abs=float(dd.max()), ort_vs_torch_mean_abs=float(dd.mean()),
               mask_agreement=float(((got > 0) == (ref > 0)).mean()), tiles=len(tiles))
    (d / 'export.json').write_text(json.dumps(res, indent=1))
    return res


def patch_pool(model):
    """[(date, key, patch index, plant)] over the cached photos of the model's training dates."""
    sys.path.insert(0, str(HERE))
    import train_cv
    held = set(json.loads((run_dir(model) / 'meta.json').read_text())['held_out_dates'])
    pool = []
    o = (320 - SIZE) // 2
    for p in train_cv.photos():
        if p['day_utc'] in held or not (CACHE / f'{p["key"]}_tgt.npy').exists():
            continue
        t = np.load(CACHE / f'{p["key"]}_tgt.npy', mmap_mode='r')[:, o:o + SIZE, o:o + SIZE]
        plant = ((t > 0) & (t != 255)).reshape(len(t), -1).any(1)
        pool += [(p['day_utc'], p['key'], j, bool(plant[j])) for j in range(len(t))]
    return pool, sorted(held)


def stratified(pool, n, rng, exclude=frozenset()):
    """n patches: half plant, half no plant; each half shared equally over dates (water-filling); uniform within."""
    from collections import defaultdict
    pick = []
    for cls, quota in ((True, n // 2), (False, n - n // 2)):
        by = defaultdict(list)
        for i, (day, key, j, pl) in enumerate(pool):
            if pl == cls and i not in exclude:
                by[day].append(i)
        days = sorted(by)
        give = {d: 0 for d in days}
        left = quota
        while left > 0:
            open_ = [d for d in days if give[d] < len(by[d])]
            if not open_:
                break
            share = max(1, left // len(open_))
            for d in open_:
                g = min(share, len(by[d]) - give[d], left)
                give[d] += g
                left -= g
                if left == 0:
                    break
        for d in days:
            if give[d]:
                pick += list(rng.choice(by[d], give[d], replace=False))
    return sorted(int(i) for i in pick)


def load_patches(pool, idx):
    o = (320 - SIZE) // 2
    mm, out = {}, []
    for i in idx:
        _, key, j, _ = pool[i]
        if key not in mm:
            mm[key] = np.load(CACHE / f'{key}_img.npy', mmap_mode='r')
        out.append(np.asarray(mm[key][j, o:o + SIZE, o:o + SIZE]))
    return np.stack(out)


def tile_positions(H, W):
    """train_cv.infer's tile grid (stride 192, mid192): returns padded size and the (y, x) list."""
    sys.path.insert(0, str(HERE))
    import train_cv
    Hp, Wp = max(H, SIZE), max(W, SIZE)
    return Hp, Wp, [(y, x) for y in train_cv.positions(Hp, 192) for x in train_cv.positions(Wp, 192)]


def stitch(logits, H, W, pos):
    """train_cv.infer's 'mid192' blend: logits weighted by the 32 px edge ramp, cut back to H x W."""
    sys.path.insert(0, str(HERE))
    import train_cv
    Hp, Wp = max(H, SIZE), max(W, SIZE)
    acc = np.zeros((Hp, Wp), np.float32)
    wsum = np.zeros((Hp, Wp), np.float32)
    wm = train_cv.weight_map('ramp')
    for (y, x), o in zip(pos, logits):
        acc[y:y + SIZE, x:x + SIZE] += o * wm
        wsum[y:y + SIZE, x:x + SIZE] += wm
    return (acc / wsum)[:H, :W]


def cell_inputs(k):
    """The held-out cells of fold k as train_cv.cmd_score reads them: [(kind, key or id, rects or cell)]."""
    sys.path.insert(0, str(HERE))
    import train_cv
    fold = train_cv.folds()
    held = [r for r in train_cv.cells() if fold[r['day']] == k]
    ins = []
    photos = {}
    for r in held:
        if r['rig'] == 'prod':
            photos.setdefault(f"production_{r['capture_id']}", []).append(r)
    for key, rs in sorted(photos.items()):
        ins.append(('photo', key, rs))
    for r in held:
        ins.append(('crop', r['id'], [r]))
    return ins, held


def build_cell_tiles(model, d, device):
    """Tiles of every input of fold k, an index to stitch them back, torch float logits, and the stitch check."""
    import cv2
    sys.path.insert(0, str(HERE))
    sys.path.insert(0, '/home/txoof/temp.nobackup/wt/npec-406-label-sources/src')
    import train_cv
    from npec_rig.images import decode_full
    k = int(model[1:])
    ins, held = cell_inputs(k)
    jpg = {p['key']: p['jpg'] for p in train_cv.photos()}
    net = load_torch(model, device)
    tiles, index, logits = [], [], []
    n0 = 0
    for kind, key, rs in ins:
        if kind == 'photo':
            rgb = decode_full(f'{train_cv.DATA}/{jpg[key]}')
            full = rgb.shape[:2]
            img = train_cv.scale_img(rgb, 2)
            del rgb
        else:
            rgb, _ = train_cv.load_crop(rs[0]['name'])
            full = rgb.shape[:2]
            img = train_cv.scale_img(rgb, 2)
        H, W = img.shape[:2]
        if H < SIZE or W < SIZE:
            img = cv2.copyMakeBorder(img, 0, max(0, SIZE - H), 0, max(0, SIZE - W), cv2.BORDER_REFLECT_101)
        _, _, pos = tile_positions(H, W)
        t = np.stack([img[y:y + SIZE, x:x + SIZE] for y, x in pos])
        tiles.append(t)
        logits.append(torch_logits(net, t, batch=32, device=device))
        index.append(dict(kind=kind, key=key, full=list(full), scaled=[H, W], pos=pos, start=n0, n=len(pos),
                          cells=[dict(id=r['id'], name=r['name'], rig=r['rig'], day=r['day'],
                                      rect=[int(r['crop_x0']), int(r['crop_y0']), int(r['crop_w']), int(r['crop_h'])])
                                 for r in rs]))
        n0 += len(pos)
    tiles, logits = np.concatenate(tiles), np.concatenate(logits)
    np.save(d / 'cell_tiles.npy', tiles)
    np.save(d / 'cell_torch_logits.npy', logits)
    (d / 'cell_index.json').write_text(json.dumps(index))
    # stitch check against E's saved float predictions
    masks = masks_from_logits(logits, index)
    diff = {}
    for (cid, mode), m in masks.items():
        ref = cv2.imread(f'{TRAIN}/pred/s2_e40/{cid}_{mode}.png', 0) > 0
        diff[f'{cid}_{mode}'] = int((ref != m).sum())
    res = dict(model=model, fold=k, cells=len(held), inputs=len(index), tiles=int(len(tiles)),
               photo_tiles=int(sum(x['n'] for x in index if x['kind'] == 'photo')),
               stitch_vs_saved_E_masks_px_differing=diff, total_px_differing=int(sum(diff.values())))
    (d / 'cell_tiles.json').write_text(json.dumps(res, indent=1))
    return res


def masks_from_logits(logits, index):
    """{(cell id, mode): bool mask at full crop size}: mode 'photo' for cells cut from a photo, 'crop' otherwise."""
    import cv2
    out = {}
    for x in index:
        H, W = x['scaled']
        lg = stitch(logits[x['start']:x['start'] + x['n']], H, W, [tuple(p) for p in x['pos']])
        if x['kind'] == 'photo':
            lg = cv2.resize(lg, (x['full'][1], x['full'][0]), interpolation=cv2.INTER_LINEAR)
            for c in x['cells']:
                cx, cy, cw, ch = c['rect']
                out[(c['id'], 'photo')] = lg[cy:cy + ch, cx:cx + cw] > 0
        else:
            lg = cv2.resize(lg, (x['full'][1], x['full'][0]), interpolation=cv2.INTER_LINEAR)
            out[(x['cells'][0]['id'], 'crop')] = lg > 0
    return out


def cmd_prep(a):
    model = a.model
    d = out_dir(model)
    d.mkdir(parents=True, exist_ok=True)
    n = calib_n()
    info_f = d / 'calib.json'
    if not (info_f.exists() and json.loads(info_f.read_text())['calib_tiles'] == n):
        pool, held = patch_pool(model)
        rng = np.random.default_rng(SEED + (0 if model == 'final' else 1 + int(model[1:])))
        cidx = stratified(pool, n, rng)
        np.save(d / 'calib_tiles.npy', load_patches(pool, cidx))
        info = dict(model=model, run=str(run_dir(model)), calib_tiles=len(cidx), held_out_dates=held,
                    pool_patches=len(pool), pool_photos=len({p[1] for p in pool}),
                    calib_photos=len({pool[i][1] for i in cidx}), calib_dates=len({pool[i][0] for i in cidx}),
                    calib_plant=sum(pool[i][3] for i in cidx),
                    per_date={dd: sum(1 for i in cidx if pool[i][0] == dd) for dd in sorted({p[0] for p in pool})},
                    held_out_dates_in_calib=sorted({pool[i][0] for i in cidx} & set(held)),
                    calib_src=[f'{pool[i][1]}:{pool[i][2]}' for i in cidx])
        assert not info['held_out_dates_in_calib']
        if model == 'final':
            kidx = stratified(pool, N_CHECK, rng, exclude=frozenset(cidx))
            check = load_patches(pool, kidx)
            np.save(d / 'check_tiles.npy', check)
            np.save(d / 'check_torch_logits.npy', torch_logits(load_torch(model), check))
            info.update(check_tiles=len(kidx), check_plant=sum(pool[i][3] for i in kidx),
                        check_src=[f'{pool[i][1]}:{pool[i][2]}' for i in kidx])
        info_f.write_text(json.dumps(info, indent=1))
        print({k: v for k, v in info.items() if not k.endswith('_src') and k != 'per_date'})
    if not (d / 'export.json').exists():
        print(export(model, d))
    if model != 'final' and not (d / 'cell_tiles.json').exists():
        r = build_cell_tiles(model, d, a.device)
        print({k: v for k, v in r.items() if k != 'stitch_vs_saved_E_masks_px_differing'})


def cmd_score(a):
    """Quantised fold model on its held-out cells: stitched masks (pred/s2_e40_q_<arch>/) and score rows."""
    import cv2
    sys.path.insert(0, str(HERE))
    import train_cv
    d = out_dir(a.model)
    cd = d / f'{a.arch}_L{LEVEL}'
    index = json.loads((d / 'cell_index.json').read_text())
    q = np.load(cd / 'cell_quantized.npy')
    masks = masks_from_logits(q, index)
    pdir = TRAIN / 'pred' / f's2_e40_q_{a.arch}'
    pdir.mkdir(parents=True, exist_ok=True)
    names = {c['id']: c['name'] for c in train_cv.cells()}
    meta = {c['id']: c for x in index for c in x['cells']}
    rows = []
    for (cid, mode), m in sorted(masks.items()):
        _, truth = train_cv.load_crop(names[cid])
        assert m.shape == truth.shape
        cv2.imwrite(str(pdir / f'{cid}_{mode}.png'), m.astype(np.uint8) * 255)
        rows.append(dict(arch=a.arch, model=a.model, fold=int(a.model[1:]), mode=mode, id=cid, rig=meta[cid]['rig'],
                         day=meta[cid]['day'], inter=int((m & truth).sum()), union=int((m | truth).sum()),
                         method_px=int(m.sum()), truth_px=int(truth.sum())))
    train_cv.write_csv(str(cd / 'cell_scores.csv'), rows)
    print(f'{a.model} {a.arch}: {len(rows)} rows')


def metrics(qv, ref):
    dd = np.abs(qv - ref)
    a_, b_ = qv > 0, ref > 0
    inter, union = int((a_ & b_).sum()), int((a_ | b_).sum())
    return dict(mean_abs_logit=float(dd.mean()), p99_abs_logit=float(np.percentile(dd, 99)), max_abs_logit=float(dd.max()),
                iou=inter / union if union else 1.0, plant_px_float=int(b_.sum()), plant_px_quantized=int(a_.sum()),
                area_ratio=float(a_.sum() / max(1, b_.sum())), pixel_agreement=float((a_ == b_).mean()))


def cmd_check(a):
    d = out_dir('final')
    cd = d / f'{a.arch}_L{LEVEL}'
    res = metrics(np.load(cd / 'check_quantized.npy'), np.load(d / 'check_torch_logits.npy'))
    (cd / 'check_metrics.json').write_text(json.dumps(res, indent=1))
    print(res)


# ---------------------------------------------------------------- container steps

def cmd_container(a):
    from hailo_sdk_client import ClientRunner, InferenceContext
    model, name = a.model, net_name(a.model)
    d = out_dir(model)
    cd = d / f'{a.arch}_L{LEVEL}'
    cd.mkdir(parents=True, exist_ok=True)
    parsed, quant, comp = cd / f'{name}_parsed.har', cd / f'{name}_quantized.har', cd / f'{name}_compiled.har'
    t0 = time.time()
    if a.step == 'parse':
        runner = ClientRunner(hw_arch=a.arch)
        runner.translate_onnx_model(str(d / f'{name}_op13_sim.onnx'), name, start_node_names=['input'],
                                    end_node_names=[END_NODE], net_input_shapes={'input': [1, 3, SIZE, SIZE]})
        runner.save_har(str(parsed))
        record(cd, 'parse', t0, arch=a.arch, model=model)
    elif a.step == 'optimize':
        runner = ClientRunner(har=str(parsed), hw_arch=a.arch)
        calib = np.load(d / 'calib_tiles.npy').astype(np.float32)
        script = alls(LEVEL, len(calib))
        (cd / f'{name}.alls').write_text(script)
        runner.load_model_script(script)
        runner.optimize(calib)
        runner.save_har(str(quant))
        record(cd, 'optimize', t0, level=LEVEL, calib_tiles=len(calib), model=model)
    elif a.step == 'emulate':
        runner = ClientRunner(har=str(quant), hw_arch=a.arch)
        src, dst = ('check_tiles.npy', 'check_quantized.npy') if model == 'final' else ('cell_tiles.npy', 'cell_quantized.npy')
        tiles = np.load(d / src, mmap_mode='r')
        out = np.zeros((len(tiles), SIZE, SIZE), np.float32)
        CH = 256
        with runner.infer_context(InferenceContext.SDK_QUANTIZED) as ctx:
            for i in range(0, len(tiles), CH):
                t1 = time.time()
                x = np.asarray(tiles[i:i + CH]).astype(np.float32)
                y = np.asarray(runner.infer(ctx, x, batch_size=8))
                out[i:i + len(x)] = y.reshape(len(x), SIZE, SIZE)
                print(f'emulate {model} {a.arch}: tiles {i + len(x)} of {len(tiles)}, {time.time() - t1:.1f} s', flush=True)
        np.save(cd / (dst + '.tmp.npy'), out)
        os.replace(cd / (dst + '.tmp.npy'), cd / dst)
        record(cd, 'emulate', t0, tiles=len(tiles), seconds_per_tile=round((time.time() - t0) / len(tiles), 3), model=model)
    elif a.step == 'compile':
        runner = ClientRunner(har=str(quant), hw_arch=a.arch)
        hef = runner.compile()
        p = cd / f'{name}_{a.arch}.hef'
        p.write_bytes(hef)
        runner.save_har(str(comp))
        record(cd, 'compile', t0, hef=str(p), hef_bytes=len(hef), model=model)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('step', choices=['prep', 'score', 'check', 'parse', 'optimize', 'emulate', 'compile'])
    ap.add_argument('--model', choices=MODELS, required=True)
    ap.add_argument('--arch', choices=['hailo8', 'hailo10h'])
    ap.add_argument('--device', default='cuda', help='prep: torch device for the cell-tile logits')
    a = ap.parse_args()
    {'prep': cmd_prep, 'score': cmd_score, 'check': cmd_check}.get(a.step, cmd_container)(a)


if __name__ == '__main__':
    main()
