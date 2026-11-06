"""App memory over time, main vs the #348 branch, from the 1 s logs (log.sh columns:
epoch pid main_rss_mb main_hwm_mb cam_rss_mb cam_hwm_mb mem_available_mb).
usage: python plot_mem.py MAIN.log MAIN_END_EPOCH BRANCH.log OUT.png
"""
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

main_log, main_end, branch_log, out = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]


def read(path, end=None, skip_s=60):
    rows = [list(map(int, line.split())) for line in open(path) if len(line.split()) == 7]
    t0 = rows[0][0]
    rows = [r for r in rows if r[0] - t0 >= skip_s and (end is None or r[0] < end) and r[2] > 0]
    s0 = rows[0][0]
    return [(r[0] - s0) / 60 for r in rows], [(r[2] + r[4]) / 1024 for r in rows]


mx, my = read(main_log, end=main_end, skip_s=0)
bx, by = read(branch_log)
bx, by = zip(*[(x, y) for x, y in zip(bx, by) if x <= 10])

SURFACE, INK, MUTED, GRID = "#fcfcfb", "#1f1f1d", "#5f5e58", "#e4e3de"
MAIN, BRANCH = "#2a78d6", "#eb6834"

fig, ax = plt.subplots(figsize=(9, 4.6), dpi=130, facecolor=SURFACE)
ax.set_facecolor(SURFACE)
ax.plot(mx, my, color=MAIN, lw=2, label=f"main cf4c1dd (peak {max(my):.2f} GiB)")
ax.plot(bx, by, color=BRANCH, lw=2, label=f"branch fd3852e (peak {max(by):.2f} GiB)")
for y, text in ((3.9, "4 GB Pi: about 3.9 GiB in all"), (2.5, "target: 2.5 GiB")):
    ax.axhline(y, color=MUTED, lw=1, ls=(0, (4, 3)))
    ax.text(10, y + 0.06, text, color=MUTED, ha="right", va="bottom", fontsize=9)
ax.text(mx[-1] + 0.1, my[-1], "main", color=INK, va="center", fontsize=9)
ax.text(10.1, by[-1], "branch", color=INK, va="center", fontsize=9)
ax.set_xlim(0, 10.8)
ax.set_ylim(0, 5.2)
ax.set_xlabel("minutes (one photo a minute, experiment 2)", color=INK)
ax.set_ylabel("app memory, GiB (main + camera process)", color=INK)
ax.set_title("npec-rig-01, 2 Nov 2026: app memory, main vs #348 branch", color=INK, loc="left")
ax.grid(axis="y", color=GRID, lw=0.8)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
for side in ("left", "bottom"):
    ax.spines[side].set_color(GRID)
ax.tick_params(colors=MUTED)
ax.legend(loc="upper center", frameon=False, labelcolor=INK, ncols=2, bbox_to_anchor=(0.5, -0.16))
fig.tight_layout()
fig.savefig(out, facecolor=SURFACE)
print(out, "main", len(mx), "branch", len(bx))
