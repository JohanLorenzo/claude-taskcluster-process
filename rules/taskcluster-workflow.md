# Taskcluster Workflow

Read `CLAUDE.local.md` for local paths. The taskgraph command is:
```
uv run --with-editable "<taskgraph_repo>" taskgraph
```

## Rules (apply to every step)

- Command hygiene: no piped commands (use `--jq` flags and separate commands instead),
  no subshells, no `eval $(...)` patterns (redirect to a file and `source` it instead).
- On failures: stop immediately and report findings to the user. Do not retry with the
  same broken approach.
- Speed: prefer local validation → local testing → direct submission → push to PR.

## Taskcluster instances

- Production: `https://firefox-ci-tc.services.mozilla.com/`
- Staging: `https://stage.taskcluster.nonprod.webservices.mozgcp.net/`

## Process

### Step 1: Determine environment

- Changing scopes, worker configs, or fxci-config? → staging
- For scriptworker tasks: always start with staging
- Otherwise → production

### Step 2: Ensure taskgraph is initialized

Check whether `.taskcluster.yml` in the repo root creates a single decision task that
runs `taskgraph decision`. If it does, taskgraph is already set up — skip this step.

Otherwise (`.taskcluster.yml` missing, or it exists but doesn't use taskgraph), the
repo needs initialization. Prerequisites: must be in a git repo with a GitHub remote.

If `.taskcluster.yml` exists but doesn't use taskgraph, pass `--force` to overwrite:
```bash
uv run --with-editable "<taskgraph_repo>" taskgraph init --force
```

If `.taskcluster.yml` doesn't exist:
```bash
uv run --with-editable "<taskgraph_repo>" taskgraph init
```

This generates `.taskcluster.yml`, `taskcluster/config.yml`, kind definitions, a
sample Dockerfile, and a sample transform module. Review and commit the generated
files before proceeding.

### Step 3: Sign in

Replace `<RANDOM>` with a 7-letter random hash (e.g., `xk4mfqz`). Always split into
three separate commands (one approval each):

```bash
export TASKCLUSTER_ROOT_URL=<url-from-step-1>
```
```bash
taskcluster signin \
  -n 'mozilla-auth0/ad|Mozilla-LDAP|jlorenzo/claude-code-client-<RANDOM>' \
  --scope 'queue:get-artifact:public/*' --expires 1d \
  > /tmp/tc-creds.sh
```
```bash
source /tmp/tc-creds.sh
```

### Step 4: Validate locally

Gate: must pass before proceeding to step 5.

```bash
uv run --with-editable "<taskgraph_repo>" taskgraph target-graph \
  --root taskcluster -p taskcluster/test/params/<event>.yml
```
On the Firefox repo: `./mach taskgraph target-graph -p <params>`

### Step 5: Test

Gate: must pass before proceeding to step 6.

Decision tree:

- Task runs in a Docker container → test locally:
  ```bash
  DOCKER_DEFAULT_PLATFORM=linux/amd64 \
    uv run --with-editable "<taskgraph_repo>[load-image]" taskgraph load-task $TASK_ID
  ```
- Scriptworker task → spawn a local worker against the staging environment.
- `load-task` fails or neither applies → direct task submission (steps 5a–5f below).

**Direct task submission** (iterate without a full push cycle):

Always split into separate commands:

**Step 5a** — get the failed task definition:
```bash
taskcluster task def $FAILED_TASK_ID > /tmp/task.json
```

**Step 5b** — edit `/tmp/task.json` to fix the issue (payload, env, command, etc.)

**Step 5c** — update timestamps:
```bash
python3 -c "
import json, datetime
t = json.load(open('/tmp/task.json'))
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
t['created'] = now
t['deadline'] = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()
t['expires'] = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)).isoformat()
json.dump(t, open('/tmp/task.json', 'w'), indent=2)
"
```

**Step 5d** — sign in with the task's required scopes (extract from `schedulerId`,
`provisionerId`, `workerType`, `routes`, and `scopes` fields):
```bash
export TASKCLUSTER_ROOT_URL=<url-from-step-1>
```
```bash
taskcluster signin \
  -n 'mozilla-auth0/ad|Mozilla-LDAP|jlorenzo/claude-code-client-<RANDOM>' \
  --expires 1h \
  --scope 'queue:create-task:lowest:<provisionerId>/<workerType>' \
  --scope 'queue:scheduler-id:<schedulerId>' \
  --scope '<any scope listed in the task definition>' \
  > /tmp/tc-creds.sh
```
```bash
source /tmp/tc-creds.sh
```

**Step 5e** — generate a new task ID (separate command, save to variable):
```bash
TASK_ID=$(taskcluster slugid generate)
```

**Step 5f** — submit:
```bash
taskcluster api queue createTask $TASK_ID < /tmp/task.json
```

Once the task is green, port the fix back to the local code and commit.

### Step 6: Push to PR

Only push to a PR after steps 4 and 5 pass.

**Simulating non-PR events (release, push) from a PR:**

Add `try_task_config.json` to repo root (temporary commit, do NOT merge):
```json
{"version": 2, "parameters": {"tasks_for": "github-release", "head_ref": "v1.0.0"}}
```
After testing, remove from history:
```bash
git reset --hard HEAD~1
```
```bash
git push fork <branch> --force-with-lease
```

### Step 7: Monitor

Gate: target task must be green before proceeding to step 8.

**Getting the decision task ID** (the only allowed `gh api` call):
```bash
HEAD_SHA=$(git rev-parse HEAD)
DECISION_TASK_ID=$(gh api "repos/<org/repo>/commits/$HEAD_SHA/check-runs" \
  --jq '[.check_runs[] | select(.name | contains("Decision Task"))][0].external_id')
```

**Monitoring protocol** (follow this order strictly):
1. Watch the decision task first:
   ```bash
   watch --no-title --errexit taskcluster task status $DECISION_TASK_ID
   ```
   On failure: `taskcluster task log $DECISION_TASK_ID`
2. Watch each dependency task before watching the target task. Do NOT jump straight to
   `taskcluster group list` or `taskcluster group status` — they give false assurance.
3. ALWAYS read the target task's logs (`taskcluster task log $TASK_ID`), even if green.
4. If the task produces artifacts, check those too.
5. Only after the target task succeeds, use `taskcluster group status $DECISION_TASK_ID`
   to validate the full graph.

Other useful commands:
```bash
taskcluster task def $TASK_ID
taskcluster task log $TASK_ID
taskcluster download artifact $DECISION_TASK_ID public/task-graph.json /tmp/task-graph.json
```

Only use `gh api` to get the decision task ID. For everything else, use `gh pr list`,
local git commands, and the `taskcluster` CLI.

### Step 8: Complete

After a PR is merged (or ready for review), write a GitHub comment explaining what
was verified. Include links to tasks and relevant log extracts.

## Reference: fxci-config validation

```bash
cd <fxci_config_repo> && uv run ci-admin diff --environment firefoxci
```
where `<fxci_config_repo>` comes from `CLAUDE.local.md`.

## Reference: Scriptworker-specific guidance

- Use treeherder-cli to find a recent example of a similar task on `mozilla-release`.
- Avoid production scopes — only use them in the final test phases.
- Test against the staging scriptworker environment first.
