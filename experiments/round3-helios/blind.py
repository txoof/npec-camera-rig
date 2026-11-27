"""Give every crop a blind name in a recorded random order, and write the key."""
import json, random, shutil, sys, os
SRC, DST, KEY, SEED = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
man = json.load(open(f'{SRC}/manifest.json'))
items = []
for m in man:
    for cam in ('rig', 'helios'):
        items.append({'tray_tag': m['tray_tag'], 'cell': m['cell'], 'camera': cam,
                      'real_file': m[f'{cam}_file'],
                      'px_per_mm': m['helios_px_per_mm'] if cam == 'helios' else None,
                      'mm2_per_px': m['rig_mm2_per_px'] if cam == 'rig' else None})
rng = random.Random(SEED)
# shuffle, then push apart any pair of the same plant that lands within 4 places
for _ in range(2000):
    rng.shuffle(items)
    pos = {}
    ok = True
    for i, it in enumerate(items):
        k = (it['tray_tag'], it['cell'])
        if k in pos and i - pos[k] < 5:
            ok = False
            break
        pos[k] = i
    if ok:
        break
else:
    raise SystemExit('could not separate the pairs')
os.makedirs(DST, exist_ok=True)
rows = ['blind_file,tray_tag,cell,camera,real_file,helios_px_per_mm,rig_mm2_per_px']
for i, it in enumerate(items, 1):
    blind = f'plant{i:02d}.png'
    shutil.copy(f'{SRC}/{it["real_file"]}', f'{DST}/{blind}')
    rows.append(f'{blind},{it["tray_tag"]},{it["cell"]},{it["camera"]},{it["real_file"]},'
                f'{it["px_per_mm"] if it["px_per_mm"] is not None else ""},'
                f'{it["mm2_per_px"] if it["mm2_per_px"] is not None else ""}')
open(KEY, 'w').write('\n'.join(rows) + '\n')
print(f'{len(items)} crops blinded, seed {SEED}')
print('closest same-plant pair:', min(
    abs(i - j) for i, a in enumerate(items) for j, b in enumerate(items)
    if i < j and (a['tray_tag'], a['cell']) == (b['tray_tag'], b['cell'])), 'places apart')
