## D2 on ARADEEPOPSIS photos (seen in training, information only)

D2 was pre-trained on ARADEEPOPSIS: every one of its 1899 photos gave one tile (nearly the whole photo at x0.45) to the pre-training, so D2's rows are **seen in training** and say only how well the network learned purple rosettes it was shown, not how it does on unseen plants. The other rows are D1u's (none of those networks saw ARADEEPOPSIS). Same reading as D1u: mean of the 5 fold models, x0.45, tiles 256 stride 192 middle kept, threshold 0.5, labelled pixels only; our labels (healthy and purple = plant, senescent = not plant).

| Photos (n) | Method | Pooled IoU | Mean IoU | Mean abs(area ratio - 1) | Pooled area ratio |
|---|---|---|---|---|---|
| anthoSet, purple-rich (class 3 > 25% of plant) (444) | grow from leaf cores | 0.352 | 0.351 | 0.448 | 0.682 |
| anthoSet, purple-rich (class 3 > 25% of plant) (444) | current best (no public data) | 0.407 | 0.402 | 0.537 | 0.467 |
| anthoSet, purple-rich (class 3 > 25% of plant) (444) | D1 (6 public sets, then ours) | 0.428 | 0.424 | 0.536 | 0.500 |
| anthoSet, purple-rich (class 3 > 25% of plant) (444) | D2 (all 7 public sets, then ours): SEEN IN TRAINING | 0.453 | 0.451 | 0.509 | 0.528 |
| anthoSet, not purple-rich (class 3 <= 25%) (1134) | grow from leaf cores | 0.513 | 0.456 | 7.745 | 1.628 |
| anthoSet, not purple-rich (class 3 <= 25%) (1134) | current best (no public data) | 0.766 | 0.694 | 1.054 | 0.968 |
| anthoSet, not purple-rich (class 3 <= 25%) (1134) | D1 (6 public sets, then ours) | 0.770 | 0.671 | 1.873 | 1.049 |
| anthoSet, not purple-rich (class 3 <= 25%) (1134) | D2 (all 7 public sets, then ours): SEEN IN TRAINING | 0.786 | 0.692 | 1.873 | 1.047 |
| all photos (each once) (1899) | grow from leaf cores | 0.396 | 0.406 | 7.563 | 1.348 |
| all photos (each once) (1899) | current best (no public data) | 0.591 | 0.617 | 0.926 | 0.714 |
| all photos (each once) (1899) | D1 (6 public sets, then ours) | 0.610 | 0.612 | 1.461 | 0.772 |
| all photos (each once) (1899) | D2 (all 7 public sets, then ours): SEEN IN TRAINING | 0.627 | 0.627 | 1.443 | 0.782 |

Per-image scores `results/d2u_per_image.csv`; masks `analysis/train/pred/d2u/`.
