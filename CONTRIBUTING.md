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

## Review before merging

1. Run the `code-review` skill (`/code-review`) on the PR's diff.
2. Deal with every finding: fix it, or record it in an issue with the reason it is deferred. Post
   what was done as one combined PR comment. Do not let a finding disappear silently.
3. Run `pytest` (unit tier) again after any fixes.

## Merging

**Only Aaron approves and merges.** Agents stop at "ready for you to merge". He squash merges, so
the PR title becomes the commit on `main` and the PR description becomes its message: write it as
a summary of what shipped, what was verified and what is deferred, not a log of commits.

## Everything else

Test discipline, the governing anti-metrology principle and day-to-day working rules are in
`CLAUDE.md`. They are not repeated here.
