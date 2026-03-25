---
name: taskcluster-submit-task
description: >-
  Directly submit a task to Taskcluster (Step 5 direct submission path).
  TRIGGER when: a task needs to be submitted directly to staging or production
  without going through a full CI push cycle — e.g. iterating on a failing task,
  testing a new kind, or submitting from taskgraph output. Do NOT trigger for
  normal PR pushes.
allowed-tools: Bash
argument-hint: "<TC_ROOT_URL> (--task-id <TASK_ID> | taskgraph-label)"
---

# Submit Taskcluster Task (Direct Submission)

The user's argument: **$ARGUMENTS**

The TC root URL is the first word of the argument. The rest identifies the task
source (a live task ID or a taskgraph label to generate from).

## Process

### Step 1 — Prepare: fetch/generate and write task JSON

If the source is a live task ID:
```bash
uv run ~/.claude/skills/taskcluster-submit-task/scripts/taskcluster_submit_task.py \
  prepare <TC_ROOT_URL> --task-id <TASK_ID>
```

If the source is a taskgraph label (generate from local params):
```bash
uv run --with-editable '<taskgraph_repo>' taskgraph target-graph \
  --root taskcluster -p <params_file> --json 2>/dev/null \
  | python3 -c "import sys,json; g=json.load(sys.stdin); print(json.dumps(g['<label>']['task']))" \
  | uv run ~/.claude/skills/taskcluster-submit-task/scripts/taskcluster_submit_task.py \
    prepare <TC_ROOT_URL> -
```

The script prints the temp file path and the required scopes.

### Step 2 — Edit the task file (Step 5b)

Read the temp file. Resolve any `{"task-reference": "<name>"}` values to actual
task IDs, adjust the payload, fix level (use level-1 for forks). Edit in place.

### Step 3 — Sign in with the required scopes

Using the scopes printed in Step 1:
```bash
TASKCLUSTER_ROOT_URL=<TC_ROOT_URL> taskcluster signin \
  -n 'mozilla-auth0/ad|Mozilla-LDAP|jlorenzo/claude-code-client-<RANDOM>' \
  --expires 1h \
  --scope '<scope-1>' \
  --scope '<scope-2>' \
  ... \
  > /tmp/tc-creds.sh
```
```bash
source /tmp/tc-creds.sh
```

### Step 4 — Submit

```bash
uv run ~/.claude/skills/taskcluster-submit-task/scripts/taskcluster_submit_task.py \
  submit <TC_ROOT_URL> <TASK_FILE>
```

Report the task URL to the user.
