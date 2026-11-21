"""#406 trial A: compile stage A's half-resolution plant network for both Hailo chips, CPU only, and measure
the 8-bit loss with Hailo's emulator. A dry run to find compiler problems early; not the final network.

Host steps (training env: `source /home/txoof/temp.nobackup/npec-406-nn/env.sh`):

    hailo_compile.py export      # model.pt -> ONNX (opset 13, 1x3x256x256, simplified); ORT vs torch check
    hailo_compile.py tiles       # calibration and check tiles (uint8 NHWC) + torch float logits of the check tiles
    hailo_compile.py report      # metrics.json / metrics.md from the emulator outputs of every chip and level

Container steps (one per process, in npec406/hailo-<chip> images; see run_hailo_trial.sh):

    hailo_compile.py parse    --arch hailo8 --level 0
    hailo_compile.py optimize --arch hailo8 --level 0      # 8-bit quantisation, calibration tiles
    hailo_compile.py emulate  --arch hailo8 --level 0      # SDK_FP_OPTIMIZED and SDK_QUANTIZED on the check tiles
    hailo_compile.py compile  --arch hailo8 --level 0      # HEF
    (profile: `hailo profiler <compiled.har> --hef <hef>` from the wrapper)

Network. Stage A, half resolution (scale 2), fold 1 as stage-A.md numbers folds (`runs/s2_f0`, held-out dates
2026-10-12, -19, -28, 11-04, -13, -18). smp 0.6.0 Unet, mobilenet_v2 encoder, 1 output logit. The ONNX holds the
plain network; the ImageNet normalisation of train_cv.normalise ((x/255 - mean) / std) is the DFC model
script's `normalization` layer (mean and std times 255), so the HEF takes uint8 RGB 0..255.

Tiles. Half-resolution photo patches of the stage A cache (`cache/s2/mm/*_img.npy`, 320 px), centre 256 px.
Only photos of fold 1's training dates. These photos are sorted by key and dealt alternately: even positions
give calibration tiles, odd positions give check tiles, so no photo gives both. 256 calibration tiles and
200 check tiles, drawn uniformly over the (photo, patch) pairs of each group with a fixed seed. The cache
holds plant patches (at most 150 per photo) and labelled no-plant patches (at most 60), so the draws carry
the same mix.

Loss figures. Over all pixels of the check tiles: mean absolute logit difference, and IoU of the masks
logit > 0 (probability 0.5). Quantised (SDK_QUANTIZED) against the torch float32 network (the reference), and
against the emulator's own float model (SDK_FP_OPTIMIZED) as a side figure.
"""
import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

import numpy as np

NN = Path('/home/txoof/temp.nobackup/npec-406-nn')
OUT = NN / 'hailo' / 'trial-A'
RUN = NN / 'analysis' / 'train' / 'runs' / 's2_f0'
CACHE = NN / 'analysis' / 'train' / 'cache' / 's2' / 'mm'
NAME = 'plantseg_s2f0'
SIZE = 256
N_CALIB, N_CHECK = 256, 200
SEED = 406
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]
END_NODE = '/segmentation_head/segmentation_head.0/Conv'


def alls(level, n_calib):
    m = ', '.join(f'{v * 255:.3f}' for v in MEAN)
    s = ', '.join(f'{v * 255:.3f}' for v in STD)
    return (f'normalization1 = normalization([{m}], [{s}])\n'
            f'model_optimization_flavor(optimization_level={level}, compression_level=0)\n'
            f'model_optimization_config(calibration, batch_size=8, calibset_size={n_calib})\n')


def peak_mib():
    return (round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
            round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024))


def record(d, step, t0, **extra):
    s, c = peak_mib()
    row = dict(step=step, seconds=round(time.time() - t0, 1), peak_rss_mib_self=s, peak_rss_mib_children=c,
               utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), **extra)
    print(json.dumps(row), flush=True)
    with open(d / 'steps.jsonl', 'a') as f:
        f.write(json.dumps(row) + '\n')


# ---------------------------------------------------------------- host steps

def load_torch():
    import torch
    import segmentation_models_pytorch as smp
    m = smp.Unet('mobilenet_v2', encoder_weights=None, in_channels=3, classes=1)
    m.load_state_dict(torch.load(RUN / 'model.pt', map_location='cpu'))
    return m.eval()


def torch_logits(model, tiles_u8, batch=16):
    """uint8 NHWC -> float32 logits NHW, exactly train_cv.infer's preprocessing, CPU float32."""
    import torch
    m = torch.tensor(MEAN).view(1, 3, 1, 1)
    sd = torch.tensor(STD).view(1, 3, 1, 1)
    out = []
    with torch.no_grad():
        for i in range(0, len(tiles_u8), batch):
            x = torch.from_numpy(np.ascontiguousarray(tiles_u8[i:i + batch])).permute(0, 3, 1, 2).float() / 255
            out.append(model((x - m) / sd)[:, 0].numpy())
    return np.concatenate(out).astype(np.float32)


def cmd_export(a):
    import torch
    import onnx
    import onnxruntime as ort
    from onnxsim import simplify
    OUT.mkdir(parents=True, exist_ok=True)
    model = load_torch()
    raw, sim = OUT / f'{NAME}_op13.onnx', OUT / f'{NAME}_op13_sim.onnx'
    torch.onnx.export(model, torch.zeros(1, 3, SIZE, SIZE), str(raw), opset_version=13, dynamo=False,
                      input_names=['input'], output_names=['logits'], do_constant_folding=True)
    m, ok = simplify(onnx.load(str(raw)))
    assert ok
    onnx.save(m, str(sim))
    ops = sorted({n.op_type for n in m.graph.node})
    ends = [n.name for n in m.graph.node if n.output[0] == 'logits']
    # ORT vs torch on 8 real tiles (the first 8 check tiles if they exist, else random cache patches)
    tiles = draw_tiles()[1][:8]
    ref = torch_logits(model, tiles)
    sess = ort.InferenceSession(str(sim), providers=['CPUExecutionProvider'])
    x = ((tiles.astype(np.float32) / 255 - np.array(MEAN, np.float32)) / np.array(STD, np.float32))
    got = np.concatenate([sess.run(None, {'input': x[i:i + 1].transpose(0, 3, 1, 2)})[0][:, 0]
                          for i in range(len(x))])
    d = np.abs(got - ref)
    res = dict(onnx=str(sim), opset=13, ops=ops, end_node=ends, nodes=len(m.graph.node),
               ort_vs_torch_max_abs=float(d.max()), ort_vs_torch_mean_abs=float(d.mean()),
               mask_agreement=float(((got > 0) == (ref > 0)).mean()), tiles=len(tiles))
    (OUT / 'export.json').write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


def train_photo_keys():
    sys.path.insert(0, str(Path(__file__).parent))
    import csv
    held = set(json.loads((RUN / 'meta.json').read_text())['held_out_dates'])
    res = Path(__file__).resolve().parent.parent / 'results' / 'labels_done.csv'
    keys = []
    with open(res, newline='') as f:
        for r in csv.DictReader(f):
            if r['steadiness_flag'] or r['day_utc'] in held:
                continue
            k = f"{r['rig']}_{r['capture_id']}"
            if (CACHE / f'{k}_img.npy').exists():
                keys.append(k)
    return sorted(keys)


def draw_tiles():
    keys = train_photo_keys()
    rng = np.random.default_rng(SEED)
    groups = (keys[0::2], keys[1::2])
    out = []
    for grp, n in zip(groups, (N_CALIB, N_CHECK)):
        mm = {k: np.load(CACHE / f'{k}_img.npy', mmap_mode='r') for k in grp}
        pairs = [(k, j) for k in grp for j in range(mm[k].shape[0])]
        pick = sorted(rng.choice(len(pairs), n, replace=False))
        o = (mm[grp[0]].shape[1] - SIZE) // 2
        out.append(np.stack([mm[pairs[i][0]][pairs[i][1], o:o + SIZE, o:o + SIZE] for i in pick]))
        out.append([pairs[i] for i in pick])
    return out[0], out[2], out[1], out[3], len(keys)


def cmd_tiles(a):
    OUT.mkdir(parents=True, exist_ok=True)
    calib, check, calib_src, check_src, nkeys = draw_tiles()
    assert not ({k for k, _ in calib_src} & {k for k, _ in check_src})
    np.save(OUT / 'calib_tiles.npy', calib)
    np.save(OUT / 'check_tiles.npy', check)
    ref = torch_logits(load_torch(), check)
    np.save(OUT / 'check_torch_logits.npy', ref)
    info = dict(train_photos=nkeys, calib_tiles=len(calib), calib_photos=len({k for k, _ in calib_src}),
                check_tiles=len(check), check_photos=len({k for k, _ in check_src}),
                check_plant_px_share=float((ref > 0).mean()), seed=SEED,
                calib_src=[f'{k}:{j}' for k, j in calib_src], check_src=[f'{k}:{j}' for k, j in check_src])
    (OUT / 'tiles.json').write_text(json.dumps(info, indent=1))
    print({k: v for k, v in info.items() if not k.endswith('_src')})


def metrics(q, ref):
    d = np.abs(q - ref)
    a, b = q > 0, ref > 0
    inter, union = int((a & b).sum()), int((a | b).sum())
    return dict(mean_abs_logit=float(d.mean()), p99_abs_logit=float(np.percentile(d, 99)),
                max_abs_logit=float(d.max()), iou=inter / union if union else 1.0,
                plant_px_ref=int(b.sum()), plant_px=int(a.sum()), area_ratio=float(a.sum() / max(1, b.sum())),
                pixel_agreement=float((a == b).mean()),
                per_tile_iou_min=float(min((((a[i] & b[i]).sum() / max(1, (a[i] | b[i]).sum()))
                                            if (a[i] | b[i]).any() else 1.0) for i in range(len(a)))))


def cmd_report(a):
    ref = np.load(OUT / 'check_torch_logits.npy')
    rows = []
    for d in sorted(OUT.glob('hailo*_L*')):
        r = dict(run=d.name)
        fp, q = d / 'check_fp_optimized.npy', d / 'check_quantized.npy'
        if fp.exists():
            fpv = np.load(fp)
            r['fp_optimized_vs_torch'] = metrics(fpv, ref)
        if q.exists():
            qv = np.load(q)
            r['quantized_vs_torch'] = metrics(qv, ref)
            if fp.exists():
                r['quantized_vs_fp_optimized'] = metrics(qv, fpv)
        st = d / 'steps.jsonl'
        if st.exists():
            r['steps'] = [json.loads(line) for line in st.read_text().splitlines()]
        rows.append(r)
    (OUT / 'metrics.json').write_text(json.dumps(rows, indent=1))
    lines = ['| Run | Compared | Mean abs logit diff | p99 | IoU (0.5) | Area ratio | Lowest tile IoU |',
             '|---|---|---|---|---|---|---|']
    for r in rows:
        for k in ('quantized_vs_torch', 'quantized_vs_fp_optimized', 'fp_optimized_vs_torch'):
            if k in r:
                m = r[k]
                lines.append(f"| {r['run']} | {k} | {m['mean_abs_logit']:.4f} | {m['p99_abs_logit']:.3f} | "
                             f"{m['iou']:.4f} | {m['area_ratio']:.4f} | {m['per_tile_iou_min']:.3f} |")
    (OUT / 'metrics.md').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))


# ---------------------------------------------------------------- container steps

def cmd_container(a):
    from hailo_sdk_client import ClientRunner, InferenceContext
    d = OUT / f'{a.arch}_L{a.level}'
    d.mkdir(parents=True, exist_ok=True)
    parsed, quant, comp = d / f'{NAME}_parsed.har', d / f'{NAME}_quantized.har', d / f'{NAME}_compiled.har'
    t0 = time.time()
    if a.step == 'parse':
        runner = ClientRunner(hw_arch=a.arch)
        runner.translate_onnx_model(str(OUT / f'{NAME}_op13_sim.onnx'), NAME, start_node_names=['input'],
                                    end_node_names=[END_NODE], net_input_shapes={'input': [1, 3, SIZE, SIZE]})
        runner.save_har(str(parsed))
        record(d, 'parse', t0, arch=a.arch)
    elif a.step == 'optimize':
        runner = ClientRunner(har=str(parsed), hw_arch=a.arch)
        script = alls(a.level, N_CALIB)
        (d / f'{NAME}.alls').write_text(script)
        runner.load_model_script(script)
        calib = np.load(OUT / 'calib_tiles.npy').astype(np.float32)
        runner.optimize(calib)
        runner.save_har(str(quant))
        record(d, 'optimize', t0, level=a.level, calib_tiles=len(calib))
    elif a.step == 'emulate':
        runner = ClientRunner(har=str(quant), hw_arch=a.arch)
        x = np.load(OUT / 'check_tiles.npy').astype(np.float32)
        for ctx_t, fn in ((InferenceContext.SDK_FP_OPTIMIZED, 'check_fp_optimized.npy'),
                          (InferenceContext.SDK_QUANTIZED, 'check_quantized.npy')):
            t1 = time.time()
            with runner.infer_context(ctx_t) as ctx:
                y = np.asarray(runner.infer(ctx, x, batch_size=8))
            print(fn, y.shape, round(time.time() - t1, 1), 's', flush=True)
            np.save(d / fn, y.reshape(len(x), SIZE, SIZE).astype(np.float32))
        record(d, 'emulate', t0, check_tiles=len(x))
    elif a.step == 'compile':
        runner = ClientRunner(har=str(quant), hw_arch=a.arch)
        hef = runner.compile()
        p = d / f'{NAME}_{a.arch}.hef'
        p.write_bytes(hef)
        runner.save_har(str(comp))
        record(d, 'compile', t0, hef=str(p), hef_bytes=len(hef))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('step', choices=['export', 'tiles', 'report', 'parse', 'optimize', 'emulate', 'compile'])
    ap.add_argument('--arch', choices=['hailo8', 'hailo10h'])
    ap.add_argument('--level', type=int, default=0)
    a = ap.parse_args()
    {'export': cmd_export, 'tiles': cmd_tiles, 'report': cmd_report}.get(a.step, cmd_container)(a)


if __name__ == '__main__':
    main()
