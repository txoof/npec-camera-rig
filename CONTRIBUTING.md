# Contributing

> M1 (the camera console) was built and merged to `main` directly, before this policy existed.
> Starting with M2, every milestone follows the process below.

## Branching and PRs

- **One pull request per milestone** (M1, M2, M3, ... — see `PLAN.md`). Slices within a
  milestone are commits on that milestone's branch, not separate PRs.
- Branch names: `m<N>-<short-description>`, e.g. `m2-calibration-rig-health`.
- **Squash merge into `main`.** The PR description is what becomes the commit message — write it
  as a summary of the milestone (what shipped, what was verified, what's deferred), not a
  commit-by-commit log.
- Don't push directly to `main`. Even solo, the branch + PR is what gives the review step
  something to run against.

## Review before merging

Every milestone PR goes through Claude Code review before merging — this is what "several
Claude agents" means in practice, not a manual ritual:

1. Run the `code-review` skill (`/code-review`) against the full diff, at `high` or `xhigh`
   effort for a milestone-sized PR (higher effort broadens coverage across more review
   dimensions and runs more verification passes).
2. Triage every finding: fix it, or record it explicitly in `TODO.md` with a reason it's
   deferred. Don't let a finding disappear silently.
3. Re-run `pytest` (unit tier) after any fixes from the review.

For a milestone with distinct, separable concerns (e.g. M2's detection code vs. its calibration
math vs. its health-check tripwire), it's fine to run `/code-review` more than once against
different parts of the diff rather than one pass over everything.

## Everything else

Test discipline, the governing anti-metrology principle, and how to work day-to-day are in
`CLAUDE.md` — this file only covers the PR/branching workflow, not repeated here.
