# Stage D1u: unseen species check on ARADEEPOPSIS

Written by `public_prep.py d1u` (2026-11-21 00:04 UTC). Development check, information only (not a decision). Neither network saw ARADEEPOPSIS: D1 was pre-trained on the other six public sets, then trained on our training cells; the current best was trained on our training cells only.

Networks: the mean of the five fold models' probabilities, plant where > 0.5 (D1: `runs/s2_f<k>_pt6`; current best: `runs/s2_f<k>`). Each image resized by x0.45 (the D0 ARADEEPOPSIS scale, so plants are about our half-resolution pixel size), tiles 256 stride 192 middle kept, probabilities back to native size. Grow from leaf cores: `grow_from_cores` on the native image, whole image as inside, no tags. Scored on labelled pixels only (truth 255 left out). Area ratio left out where the truth is empty.

Photos: 1899, each photo once (the three subsets overlap; see D0 and `results/public_ara_photos.csv`), grouped by which subset's labels it carries. Purple-rich: the authors' class 3 (anthocyanin-rich, purple) is more than 25% of their plant pixels; only anthoSet labels separate purple, so rosetteSet and senescentSet photos are not split this way. Neither grow from leaf cores nor our network has seen purple leaves.

## Against our labels

Our labels (Aaron, 2026-11-21): authors' class 1 healthy and 3 anthocyanin-rich = plant, 2 senescent = not plant, edge ring = ignore.

| Photos (n) | Method | Pooled IoU | Mean IoU | Mean abs(area ratio - 1) | Pooled area ratio | Photos with empty truth |
|---|---|---|---|---|---|---|
| labels of rosetteSet (class 1 only) (152) | grow from leaf cores | 0.448 | 0.429 | 6.401 | 0.923 | 0 |
| labels of rosetteSet (class 1 only) (152) | current best (no public data) | 0.555 | 0.567 | 1.794 | 0.610 | 0 |
| labels of rosetteSet (class 1 only) (152) | D1 (6 public sets, then ours) | 0.580 | 0.560 | 2.296 | 0.657 | 0 |
| labels of senescentSet (classes 1, 2) (169) | grow from leaf cores | 0.120 | 0.200 | 26.087 | 8.128 | 0 |
| labels of senescentSet (classes 1, 2) (169) | current best (no public data) | 0.689 | 0.713 | 0.313 | 0.969 | 0 |
| labels of senescentSet (classes 1, 2) (169) | D1 (6 public sets, then ours) | 0.782 | 0.758 | 0.384 | 1.090 | 0 |
| labels of anthoSet (classes 1, 2, 3) (1578) | grow from leaf cores | 0.445 | 0.426 | 5.689 | 1.152 | 2 |
| labels of anthoSet (classes 1, 2, 3) (1578) | current best (no public data) | 0.591 | 0.612 | 0.908 | 0.716 | 2 |
| labels of anthoSet (classes 1, 2, 3) (1578) | D1 (6 public sets, then ours) | 0.606 | 0.602 | 1.496 | 0.773 | 2 |
| anthoSet, purple-rich (class 3 > 25% of plant) (444) | grow from leaf cores | 0.352 | 0.351 | 0.448 | 0.682 | 0 |
| anthoSet, purple-rich (class 3 > 25% of plant) (444) | current best (no public data) | 0.407 | 0.402 | 0.537 | 0.467 | 0 |
| anthoSet, purple-rich (class 3 > 25% of plant) (444) | D1 (6 public sets, then ours) | 0.428 | 0.424 | 0.536 | 0.500 | 0 |
| anthoSet, not purple-rich (class 3 <= 25%) (1134) | grow from leaf cores | 0.513 | 0.456 | 7.745 | 1.628 | 2 |
| anthoSet, not purple-rich (class 3 <= 25%) (1134) | current best (no public data) | 0.766 | 0.694 | 1.054 | 0.968 | 2 |
| anthoSet, not purple-rich (class 3 <= 25%) (1134) | D1 (6 public sets, then ours) | 0.770 | 0.671 | 1.873 | 1.049 | 2 |
| all photos (each once) (1899) | grow from leaf cores | 0.396 | 0.406 | 7.563 | 1.348 | 2 |
| all photos (each once) (1899) | current best (no public data) | 0.591 | 0.617 | 0.926 | 0.714 | 2 |
| all photos (each once) (1899) | D1 (6 public sets, then ours) | 0.610 | 0.612 | 1.461 | 0.772 | 2 |

## Against the authors' masks, every leaf class as plant

Original: classes 1 to 3 (green, senescent, anthocyanin) all plant.

| Photos (n) | Method | Pooled IoU | Mean IoU | Mean abs(area ratio - 1) | Pooled area ratio | Photos with empty truth |
|---|---|---|---|---|---|---|
| labels of rosetteSet (class 1 only) (152) | grow from leaf cores | 0.448 | 0.429 | 6.401 | 0.923 | 0 |
| labels of rosetteSet (class 1 only) (152) | current best (no public data) | 0.555 | 0.567 | 1.794 | 0.610 | 0 |
| labels of rosetteSet (class 1 only) (152) | D1 (6 public sets, then ours) | 0.580 | 0.560 | 2.296 | 0.657 | 0 |
| labels of senescentSet (classes 1, 2) (169) | grow from leaf cores | 0.120 | 0.200 | 26.085 | 8.089 | 0 |
| labels of senescentSet (classes 1, 2) (169) | current best (no public data) | 0.688 | 0.713 | 0.315 | 0.965 | 0 |
| labels of senescentSet (classes 1, 2) (169) | D1 (6 public sets, then ours) | 0.782 | 0.758 | 0.385 | 1.085 | 0 |
| labels of anthoSet (classes 1, 2, 3) (1578) | grow from leaf cores | 0.428 | 0.419 | 5.689 | 0.958 | 0 |
| labels of anthoSet (classes 1, 2, 3) (1578) | current best (no public data) | 0.520 | 0.581 | 0.957 | 0.595 | 0 |
| labels of anthoSet (classes 1, 2, 3) (1578) | D1 (6 public sets, then ours) | 0.549 | 0.580 | 1.534 | 0.643 | 0 |
| anthoSet, purple-rich (class 3 > 25% of plant) (444) | grow from leaf cores | 0.336 | 0.342 | 0.516 | 0.570 | 0 |
| anthoSet, purple-rich (class 3 > 25% of plant) (444) | current best (no public data) | 0.354 | 0.363 | 0.598 | 0.390 | 0 |
| anthoSet, purple-rich (class 3 > 25% of plant) (444) | D1 (6 public sets, then ours) | 0.381 | 0.392 | 0.600 | 0.418 | 0 |
| anthoSet, not purple-rich (class 3 <= 25%) (1134) | grow from leaf cores | 0.497 | 0.450 | 7.714 | 1.347 | 0 |
| anthoSet, not purple-rich (class 3 <= 25%) (1134) | current best (no public data) | 0.680 | 0.666 | 1.097 | 0.801 | 0 |
| anthoSet, not purple-rich (class 3 <= 25%) (1134) | D1 (6 public sets, then ours) | 0.707 | 0.653 | 1.900 | 0.868 | 0 |
| all photos (each once) (1899) | grow from leaf cores | 0.386 | 0.401 | 7.561 | 1.145 | 0 |
| all photos (each once) (1899) | current best (no public data) | 0.528 | 0.591 | 0.967 | 0.606 | 0 |
| all photos (each once) (1899) | D1 (6 public sets, then ours) | 0.558 | 0.594 | 1.493 | 0.656 | 0 |

## Picture

`stage-D1u.png`: photo | our label | grow from leaf cores | current best | D1. Picked by these rules:

- ara_rosetteSet_215: rosetteSet labels: median truth size
- ara_rosetteSet_276: rosetteSet labels: smallest non-empty truth (seedling)
- ara_senescentSet_184: senescentSet labels: median share moved to not plant
- ara_anthoSet_943: anthoSet labels: median share moved to not plant
- ara_anthoSet_483: anthoSet labels: largest share moved to not plant (truth not empty)
- ara_anthoSet_465: purple-rich: median purple share
- ara_anthoSet_131: D1 worst IoU of all images
- ara_anthoSet_1178: largest IoU gap between D1 and the current best

Files: `experiments/round4-segmentation-nn/code/public_prep.py` (method in its docstring); per-image scores `results/d1u_per_image.csv`; masks `~/temp.nobackup/npec-406-nn/analysis/train/pred/d1u/`.
