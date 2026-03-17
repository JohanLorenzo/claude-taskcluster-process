# Planning Discipline

## Plan completeness

Plans must specify exactly what to change and test — no winging it during
implementation. Each commit must list:
- The files it touches
- The end-to-end test to run before committing. `target-graph` is necessary but
  not sufficient: in-tree Docker images also require `build-image` to pass.

Estimate token usage. If more than one context window is needed, make the plan
resumable (clear entry points, saved state).

## Commit discipline

- One commit per changed kind — start upstream dependencies, work toward leaf kinds.
- Commit immediately after completing each step — never batch all commits at the end.

## Handling CI failures

When CI failures are detected: do NOT create new commits. Absorb the fix into the
appropriate parent commit using `git absorb` or interactive rebase. Force push is
allowed when the fix only rewrites your own commits (the `check_force_push` hook
validates this).

## Test-driven bug fixes

Red/green TDD for bugs: write the failing test first, then fix the code.

For regressions: ask the user when it last worked, then use `git bisect` instead of
guessing the root cause. Fix with red/green TDD after identifying the culprit commit.

## When things go wrong

If something doesn't go according to plan: STOP and ask the user. Do not make
unilateral decisions to expand or change scope.

## Multi-repository work

When touching multiple repositories:
- Link PRs in descriptions, indicate dependencies and merge order.
- Merge in dependency order (upstream first).
- Create and push the upstream PR before the downstream PR.
