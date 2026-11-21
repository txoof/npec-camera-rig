"""#406, log 44 step 1: copy the TRAINING cells of the reference set (and nothing else) to a staging
folder, so the later scripts cannot load a test cell.
  stage_ref.py OUT        (OUT = analysis/labels on the work machine)
Reads ../../round3-grow-tuning/data/manifest_train.csv (training rows only) and copies, per row,
crops/<name>.png, truth/<name>_truth.png and drafts/<name>_draft.png from
../../round3-classifier/data/ to OUT/ref/, with the manifest and truth index."""
import csv
import hashlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.normpath(os.path.join(HERE, '..', '..'))
DATA = os.path.join(EXP, 'round3-classifier', 'data')
TUNE = os.path.join(EXP, 'round3-grow-tuning', 'data')


def main(out):
    ref = os.path.join(out, 'ref')
    for d in ('crops', 'truth', 'drafts'):
        os.makedirs(os.path.join(ref, d), exist_ok=True)
    rows = list(csv.DictReader(open(os.path.join(TUNE, 'manifest_train.csv'))))
    assert rows and all(r['split'] == 'train' for r in rows)
    idx = list(csv.DictReader(open(os.path.join(TUNE, 'truth_index_train.csv'))))
    assert {r['id'] for r in idx} == {r['id'] for r in rows} and all(r['split'] == 'train' for r in idx)
    # cross-check against the full manifest: every staged id is train there too
    full = {r['id']: r['split'] for r in csv.DictReader(open(os.path.join(DATA, 'manifest.csv')))}
    assert all(full[r['id']] == 'train' for r in rows)
    sums = []
    for r in rows:
        name = r['file'][:-4]
        for d, suf in (('crops', ''), ('truth', '_truth'), ('drafts', '_draft')):
            src = os.path.join(DATA, d, f'{name}{suf}.png')
            dst = os.path.join(ref, d, f'{name}{suf}.png')
            shutil.copyfile(src, dst)
            sums.append((hashlib.sha256(open(dst, 'rb').read()).hexdigest(), f'{d}/{name}{suf}.png'))
    shutil.copyfile(os.path.join(TUNE, 'manifest_train.csv'), os.path.join(ref, 'manifest_train.csv'))
    shutil.copyfile(os.path.join(TUNE, 'truth_index_train.csv'), os.path.join(ref, 'truth_index_train.csv'))
    with open(os.path.join(ref, 'SHA256SUMS'), 'w') as fh:
        fh.writelines(f'{h}  {p}\n' for h, p in sums)
    print(f'staged {len(rows)} training cells ({sum(r["rig"] == "prod" for r in rows)} prod, '
          f'{sum(r["rig"] == "dev" for r in rows)} dev), {len(sums)} files')


if __name__ == '__main__':
    main(sys.argv[1])
