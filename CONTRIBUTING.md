# Contributing

> M1 was merged to `main` directly, and M2 began as one PR per milestone. From 2026-10-08 the
> work is split into tasks so several agents can work at once. The rules for claiming issues,
> worktrees, the board and the camera are in `CLAUDE.md`, *Parallel work*.

## Branches and PRs

- **One PR per task.** A task is one thing Aaron can try in the browser in one sitting. It may
  cover several small related issues in the same milestone and area. Keep a PR to about 500
  changed lines, not counting tests. Split a bigger task into PRs that each work on their own.
- Branch name: `<issue-number>-<short-name>`, e.g. `52-validation-wording`. A task that covers
  several issues uses the number of its main one.
- The PR body says `Closes #<n>` for each issue it finishes, or `Part of #<n>` for one part of a
  split task. Open it as a draft while it is unfinished.
- **Push after every commit.** A plain push to the task branch, never a force push. Use
  `git merge origin/main` to bring a branch up to date, not a rebase.
- Never push to `main`. Branch protection requires one approval from Aaron (`CODEOWNERS`).
- **A PR that migrates `rig.db` says so in its body**, on its own line near the top: "Migrates
  `rig.db` to version N. A rig that runs it cannot go back to an earlier app unless a copy of the
  database is restored with it." A migration is an entry appended to `MIGRATIONS` in
  `src/npec_rig/database.py` (CLAUDE.md, *A migration goes one way*).

## Review before opening the PR

Every PR that changes code is reviewed before it is opened. Docs-only PRs may skip it.

1. Run the `code-review` skill (`/code-review`) on the branch's diff against `main`.
2. Deal with every finding: fix it, or record it in an issue with the reason it is deferred. Post
   what was done as one combined PR comment, right after opening the PR. Do not let a finding
   disappear silently.
3. Run `pytest` (unit tier) again after any fixes.

## Merging

**Only Aaron approves and merges.** Agents stop at "ready for you to merge". He squash merges, so
the PR title becomes the commit on `main` and the PR description becomes its message: write it as
a summary of what shipped, what was verified and what is deferred, not a log of commits.

## Releases

Each promotion to production is a release (Aaron, 2026-11-16, #427). A release is a tag
`v0.MINOR.PATCH` on the `main` commit production is moved to, with a GitHub release. MINOR goes
up when the promotion adds features, PATCH when it holds only fixes. The rigs' Ansible setting
`npec_rig_version: latest` installs the newest release (txoof/ansible-npec#9), and the About page
shows the version and the commit together: `v0.1.0 (a6632d6)` on a release, `v0.1.0-5-g1a2b3c4`
for a commit 5 after it.

Made after Aaron has approved the promotion and production runs the commit (CLAUDE.md, *Restarting
the production server*). From the controller:

```bash
sha=$(ssh pi@d6-daylight 'git -C ~/npec_camera_rig rev-parse HEAD')
gh release list --limit 1                      # the last version
gh release create v0.2.0 --target "$sha" --generate-notes
```

**A release that migrates `rig.db` cannot be rolled back by moving production to the earlier
tag.** The older app refuses to start on the migrated file and systemd then restarts it every 5 s.
Going back needs a copy of `rig.db` taken before the promotion, restored with the older code, which
loses everything written since. So take that copy as part of every promotion that carries a
migration (CLAUDE.md, *A migration goes one way*; `docs/database.md`, *Upgrading and going back*).

`--generate-notes` lists the PRs merged since the last release. `pyproject.toml`'s `version` is not
used and is not bumped. A release tag is never moved or deleted: a mistake is fixed with the next
version.

## Everything else

Test discipline, the governing anti-metrology principle and day-to-day working rules are in
`CLAUDE.md`. They are not repeated here.
