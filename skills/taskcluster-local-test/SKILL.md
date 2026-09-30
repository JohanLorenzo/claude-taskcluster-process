---
name: taskcluster-local-test
description: >-
  Test a Taskcluster task locally before pushing to CI (Step 5 of the workflow).
  TRIGGER when: a task needs to be validated locally — either via load-task
  (Docker tasks) or natively (pre-commit, unit tests). Do NOT trigger for tasks
  requiring TC proxy or secrets; use /taskcluster-submit-task instead.
allowed-tools: Bash
argument-hint: "<TC_ROOT_URL> <task-label> --params <params-file>"
---

# Local Task Test

The user's argument: **$ARGUMENTS**

Determine the test method, then run.

## Docker task — `load-task`

```bash
uv run ~/.claude/skills/taskcluster-local-test/scripts/taskcluster_local_test.py \
  <TC_ROOT_URL> <TASK_LABEL> \
  --params <PARAMS_FILE> \
  --taskgraph-root <taskgraph_repo>
```

Optional: add `--volume <worktree_path>:/builds/worker/checkouts/vcs` to skip
the git clone inside the container (faster iteration).

The script:
1. Generates the task definition via `taskgraph target-graph --json`
2. Looks up the cached docker image task ID from the TC index
3. Runs `taskgraph load-task` with that image

## Scriptworker task

Spawn a local worker against the staging environment. Out of scope for this
skill — refer to scriptworker documentation.
