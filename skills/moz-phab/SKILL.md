---
name: moz-phab
description: Submit or update a Phabricator revision with moz-phab. Use before `moz-phab submit`.
---

# moz-phab

## Commit message

Follow the `firefox-commits` skill for message format and the `Differential
Revision:` trailer. This skill does not repeat that guidance.

## Stack numbering

Number commits in landing order: each commit is `Bug N - part K: `. A single
commit (no stack) keeps `Bug N - ` with no part number.

## Submitting

Each `moz-phab submit` amends the target commit, which changes its hash.
Always pass the current HEAD hash, read right before the call:

```bash
moz-phab submit --no-wip <commit-from-git-rev-parse-HEAD>
```

Never reuse a hash from an earlier step.

Before running any `git commit --amend -m`, read the existing message first
so the `Differential Revision:` trailer moz-phab added is not lost:

```bash
git log -1 --format=%B
```

## Setting the Test Plan field

`--test-plan` requires `--single` (it does not work on a stack range):

```bash
moz-phab submit --no-wip --single <commit> --test-plan "..."
```

`--message` creates a general comment (visible in the activity feed), not the
Summary field. The Summary comes from the commit body.

Write the `--test-plan` text with the `pr-description` skill's test plan
variant. This skill covers only the mechanics of the `moz-phab` call, not the
wording — repeat none of `pr-description`'s writing guidance here.

## Testing Policy tags

Firefox requires a Testing Policy project tag before landing. Set it via the
Phabricator web UI. Common choices:
- `testing-exception-elsewhere` — test coverage lives outside this repo
  (e.g. end-to-end staging verification)
- `testing-exception-unchanged` — docs-only or config-only, no behavior change
