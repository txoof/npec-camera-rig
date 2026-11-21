"""Check the hand-labelled results of the handlabel_406 folder (Pillow and numpy only).

  python check_results.py [FOLDER]

FOLDER is the handlabel_406 folder (default: the folder this script is in). For every cells/<file>.tif
it looks in labelled/ for <file>_hand.roi.zip or <file>_none.txt, and <file>_hand_mask.png. It checks
that the mask is single-channel, holds only 0 and 255, and has the TIFF's width and height, then prints
the plant pixel count (mask = 255) per cell. It writes FOLDER/check_sheet.png: one row per cell, the
crop on the left and the crop with the mask overlaid in magenta (50%) on the right.

It only reads the TIFFs and masks; it writes nothing but check_sheet.png. Exit status 1 when a cell
is missing or a mask is wrong.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw


def main(folder):
    cells = os.path.join(folder, 'cells')
    lab = os.path.join(folder, 'labelled')
    names = sorted(f[:-4] for f in os.listdir(cells) if f.lower().endswith('.tif'))
    rows, problems = [], 0
    print(f'{"cell":32s} {"outlines":10s} {"size":>11s} {"plant px":>9s}  check')
    for n in names:
        rgb = np.asarray(Image.open(os.path.join(cells, n + '.tif')).convert('RGB'))
        h, w = rgb.shape[:2]
        has_zip = os.path.exists(os.path.join(lab, n + '_hand.roi.zip'))
        has_none = os.path.exists(os.path.join(lab, n + '_none.txt'))
        kind = 'roi.zip' if has_zip else ('none.txt' if has_none else '-')
        mpath = os.path.join(lab, n + '_hand_mask.png')
        note, mask = [], None
        if not (has_zip or has_none):
            note.append('no _hand.roi.zip or _none.txt')
        if has_zip and has_none:
            note.append('both _hand.roi.zip and _none.txt')
        if not os.path.exists(mpath):
            note.append('no _hand_mask.png')
        else:
            im = Image.open(mpath)
            m = np.asarray(im)
            if m.ndim != 2:
                note.append(f'mask is not single-channel (mode {im.mode})')
                m = m[..., 0]
            if m.shape != (h, w):
                note.append(f'mask is {m.shape[1]} x {m.shape[0]}, crop is {w} x {h}')
            vals = np.unique(m)
            if not set(vals.tolist()) <= {0, 255}:
                note.append(f'mask values {vals[:6].tolist()}{"..." if len(vals) > 6 else ""}, expected 0 and 255')
            mask = m == 255
            if has_none and mask.any():
                note.append('_none.txt but the mask has plant pixels')
            if has_zip and not mask.any():
                note.append('_hand.roi.zip but the mask is empty')
        px = int(mask.sum()) if mask is not None else 0
        ok = 'ok' if not note else 'PROBLEM: ' + '; '.join(note)
        problems += bool(note)
        print(f'{n:32s} {kind:10s} {f"{w} x {h}":>11s} {px:9d}  {ok}')
        rows.append((n, rgb, mask if mask is not None and mask.shape == (h, w) else None, px))
    sheet(rows, os.path.join(folder, 'check_sheet.png'))
    print(f'\n{len(names) - problems} of {len(names)} cells ok. Sheet: {os.path.join(folder, "check_sheet.png")}')
    return 1 if problems else 0


def sheet(rows, path):
    tile, pad, cap = 380, 12, 22
    W = 2 * tile + 3 * pad
    img = Image.new('RGB', (W, len(rows) * (tile + cap + pad) + pad), 'white')
    dr = ImageDraw.Draw(img)
    for i, (n, rgb, mask, px) in enumerate(rows):
        y = pad + i * (tile + cap + pad)
        over = rgb.astype(np.float32)
        if mask is not None:
            over[mask] = 0.5 * over[mask] + 0.5 * np.array([255, 0, 255], np.float32)
        txt = f'{n}: {px} plant px' if mask is not None else f'{n}: no usable mask'
        dr.text((pad, y), txt, fill='black')
        for k, a in enumerate((rgb, over.astype(np.uint8))):
            t = Image.fromarray(a)
            s = tile / max(t.size)
            t = t.resize((round(t.size[0] * s), round(t.size[1] * s)), Image.NEAREST)
            img.paste(t, (pad + k * (tile + pad), y + cap))
    img.save(path)


if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else here))
