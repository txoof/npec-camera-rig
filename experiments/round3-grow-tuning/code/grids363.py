"""#363, log 34: grids of settings. `oat OUT`: each setting varied alone around the present one.
`combo OUT JSON`: the full product of the values given per setting (JSON: {name: [values]})."""
import itertools
import json
import sys

PRESENT = dict(core=0.1, gr=True, gap=0.07, floor=-0.045, blue=0, edge=0, fill=False, sigma=0.0)
R = lambda a, b, st: [round(a + st * i, 3) for i in range(int(round((b - a) / st)) + 1)]  # noqa: E731
RANGES = dict(core=R(0.06, 0.14, 0.01), gr=[True, False], gap=R(0.03, 0.12, 0.01),
              floor=R(-0.08, 0, 0.01) + [-0.045], blue=R(0, 30, 5), edge=[0, 1], fill=[False, True],
              sigma=[0.0, 0.7])


def oat(out):
    grid = [dict(PRESENT, varied='present')]
    for k, vals in RANGES.items():
        for v in vals:
            if v != PRESENT[k]:
                grid.append(dict(PRESENT, **{k: v}, varied=k))
    for c in R(0.06, 0.14, 0.01):  # core without G > R at every cutoff
        if c != PRESENT['core']:
            grid.append(dict(PRESENT, core=c, gr=False, varied='core, no G > R'))
    json.dump(grid, open(out, 'w'), indent=0)
    print(len(grid))


def combo(out, spec):
    spec = json.loads(spec)
    keys = list(spec)
    grid = [dict(PRESENT, varied='present')]
    for vals in itertools.product(*(spec[k] for k in keys)):
        s = dict(PRESENT, **dict(zip(keys, vals)), varied='combination')
        if {k: s[k] for k in PRESENT} != PRESENT:
            grid.append(s)
    json.dump(grid, open(out, 'w'), indent=0)
    print(len(grid))


if __name__ == '__main__':
    cmd, *a = sys.argv[1:]
    dict(oat=oat, combo=combo)[cmd](*a)
