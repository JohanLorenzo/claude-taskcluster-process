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
- Speed: for each commit, prefer local validation → local testing → direct submission
  → push to PR. Repeat steps 4–8 for every commit.
- One commit per changed taskgraph kind — start upstream dependencies, work toward
  leaf kinds.
- Reuse transforms from taskgraph and mozilla-taskgraph. Do not reimplement locally
  what already exists upstream.
- With run-task, tasks run as the `worker` user (non-root). Artifacts must be written
  to `/builds/worker/artifacts/` — the worker cannot write to `/` or other root paths.
- Tasks that access a secret via TC proxy (`taskcluster-proxy: true` + `TASKCLUSTER_SECRET`)
  must include `secrets:get:<secret-name>` in their own `scopes` field. No taskgraph
  transform adds this automatically.
- Shell state does not persist between Bash tool calls. Always inline env vars in the
  same command that uses them (e.g. `TASKCLUSTER_ROOT_URL=... taskcluster ...`) or
  `source` the creds file in the same command.
- `watch` requires a TTY and will fail in the Bash tool. Use a polling loop instead:
  ```bash
  until TASKCLUSTER_ROOT_URL=<url> taskcluster task status $TASK_ID | grep -qvE 'pending|running'; do sleep 15; done
  ```

## Taskcluster instances

- Production: `https://firefox-ci-tc.services.mozilla.com/`
- Staging: `https://stage.taskcluster.nonprod.webservices.mozgcp.net/`

## Process

**Planning requirement**: before implementation, the plan must specify for each
commit which Step 5 test method applies (load-task, direct submission, or local
worker) and the exact task label to test. Do not defer this decision to
implementation time.

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

**Verify worker pools exist** before writing `.taskcluster.yml`. Check that
`{trust-domain}-{1,3}/decision`, `{trust-domain}-{1,3}/linux-gcp`, and
`{trust-domain}-{1,3}/linux-gw-gcp` are present in `worker-pools.yml` in fxci-config.
If any are missing, add them to the fxci-config PR before proceeding.

### Step 3: Sign in

Replace `<RANDOM>` with a 7-letter random hash (e.g., `xk4mfqz`). Always split into
two separate commands (one approval each):

```bash
TASKCLUSTER_ROOT_URL=<url-from-step-1> taskcluster signin \
  -n 'mozilla-auth0/ad|Mozilla-LDAP|jlorenzo/claude-code-client-<RANDOM>' \
  --scope 'queue:get-artifact:public/*' --expires 1d \
  > /tmp/tc-creds.sh
```
```bash
source /tmp/tc-creds.sh
```

### Step 4: Validate locally

Repeat steps 4–8 for each commit.

Gate: must pass before proceeding to step 5.

```bash
uv run --with-editable "<taskgraph_repo>" taskgraph target-graph \
  --root taskcluster -p taskcluster/test/params/<event>.yml
```
On the Firefox repo: `./mach taskgraph target-graph -p <params>`

### Step 5: Test

Gate: must pass before proceeding to step 6.

Decision tree:

- Task runs in a Docker container → test locally with `load-task` (see recipe below).
- Scriptworker task → spawn a local worker against the staging environment.
- `load-task` fails or neither applies → direct task submission (steps 5a–5f below).

**`load-task` recipe for locally generated tasks**:

1. Create a local params file with the real fork URL and current HEAD rev:
   ```yaml
   head_repository: https://github.com/<fork>/code-review
   head_ref: <branch>
   head_rev: <git rev-parse HEAD>
   # ... other params
   ```

2. Generate the task definition:
   ```bash
   uv run --with-editable "<taskgraph_repo>" taskgraph target-graph \
     --root taskcluster -p /tmp/local-params.yml --json 2>/dev/null \
     | python3 -c "import sys,json; g=json.load(sys.stdin); print(json.dumps(g['<task-label>']['task']))" \
     > /tmp/task.json
   ```

3. Run the task locally, using the staging task ID of the in-tree Docker image:
   ```bash
   source /tmp/tc-staging-creds.sh
   DOCKER_DEFAULT_PLATFORM=linux/amd64 TASKCLUSTER_ROOT_URL=<staging-url> \
     uv run --with-editable "<taskgraph_repo>[load-image]" taskgraph load-task \
     --root taskcluster --image task-id=<docker-image-task-id> - < /tmp/task.json
   ```

   Mount the local checkout to skip the git clone (useful for fast iteration):
   ```bash
   --volume "<worktree-path>:/builds/worker/checkouts/vcs"
   ```

   **Note**: Compiled binaries (ruff, etc.) may segfault under qemu on Apple Silicon.
   For pre-commit/ruff checks, run `pre-commit run -a` natively instead of inside `load-task`.

**Direct task submission** (iterate without a full push cycle):

Always split into separate commands:

**Step 5a** — get the failed task definition:
```bash
taskcluster task def $FAILED_TASK_ID > /tmp/task.json
```

**Step 5b** — edit `/tmp/task.json` to fix the issue (payload, env, command, etc.)

If the task was generated from `taskgraph target-graph --json` (not fetched from a live
task), resolve any `{"task-reference": "<name>"}` values to actual task IDs, and add
those tasks to `dependencies`. In-tree Docker images are a common case: replace
`{"task-reference": "<docker-image>"}` with `{"taskId": "<actual-image-task-id>"}` and
add the image task ID to `t["dependencies"]`.

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
`provisionerId`, `workerType`, `priority`, `routes`, and `scopes` fields):
```bash
TASKCLUSTER_ROOT_URL=<url-from-step-1> taskcluster signin \
  -n 'mozilla-auth0/ad|Mozilla-LDAP|jlorenzo/claude-code-client-<RANDOM>' \
  --expires 1h \
  --scope 'queue:create-task:<priority>:<provisionerId>/<workerType>' \
  --scope 'queue:scheduler-id:<schedulerId>' \
  --scope 'queue:route:checks' \
  --scope '<any scope listed in the task definition>' \
  > /tmp/tc-creds.sh
```

Use the task's actual `priority` value (`low`, `very-low`, etc.), not `lowest`.
When a scope error occurs, read only the **"missing the following scopes"** section
of the error — not the full "requires" list. Add only what is listed as missing.
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

For every commit being pushed: the step 5 test for that commit must have passed
locally before pushing. For Docker-based tasks this means `load-task` must be green;
for other task types, the equivalent test (local worker, direct submission) must pass.
Never skip this — pushing to CI is not a substitute for local testing.

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
1. Poll the decision task first:
   ```bash
   until TASKCLUSTER_ROOT_URL=<url> taskcluster task status $DECISION_TASK_ID | grep -qvE 'pending|running'; do sleep 15; done
   ```
   On failure: `TASKCLUSTER_ROOT_URL=<url> taskcluster task log $DECISION_TASK_ID`
2. Poll each dependency task before polling the target task.
3. ALWAYS read the target task's logs (`taskcluster task log $TASK_ID`), even if green.
4. If the task produces artifacts, check those too.
5. Only after the target task succeeds, use `taskcluster group status $DECISION_TASK_ID`
   to validate the full graph.
6. If a task fails, use `taskcluster group list $DECISION_TASK_ID` to find what went wrong.

Other useful commands:
```bash
source /tmp/tc-creds.sh
TASKCLUSTER_ROOT_URL=<url> taskcluster task def $TASK_ID
TASKCLUSTER_ROOT_URL=<url> taskcluster task log $TASK_ID
TASKCLUSTER_ROOT_URL=<url> taskcluster download artifact $DECISION_TASK_ID public/task-graph.json /tmp/task-graph.json
```

Only use `gh api` to get the decision task ID. For everything else, use `gh pr list`,
local git commands, and the `taskcluster` CLI.

### Step 8: Update PR description with verification

After every push, update the PR description with what was verified for each commit.
Task links expire quickly, so the PR must capture the relevant log output directly.

Template:

~~~markdown
## Verification

### `<short-sha>` — `<commit-message>`
- [<task-name>](<taskcluster-task-url>)
  ```
  <relevant extract from task logs showing success or key output>
  ```

(Repeat for each commit. List all verified tasks per commit.)
~~~

## Reference: Taskcluster CLI credentials

Credentials are stored in `~/.config/taskcluster.yml`. To clear them:
```bash
taskcluster config reset --all
```
Never reset credentials one field at a time — removing `clientId` first breaks all
subsequent `taskcluster` commands (the CLI validates credentials before running anything,
including other `config reset` calls).

After clearing, public task artifacts (`task log`, `task status`, `group status`) work
without credentials — just set `TASKCLUSTER_ROOT_URL`. Only authenticated operations
(task creation, private artifacts) need `taskcluster signin`.

## Reference: fxci-config validation

```bash
cd <fxci_config_repo> && uv run ci-admin diff --environment firefoxci
```
where `<fxci_config_repo>` comes from `CLAUDE.local.md`.

## Reference: fxci-config staging deployment

Comment `/taskcluster apply-staging` on the PR (`/taskcluster` prefix required).
Merging to `main` auto-deploys to production.

When using a personal fork for staging validation, add a temporary project entry to
fxci-config (same PR, separate commit) with the fork's repo URL, the correct
trust domain, level-1 branches, and `github-taskgraph: true`. Remove it before merging.

## Reference: Scriptworker-specific guidance

- Use treeherder-cli to find a recent example of a similar task on `mozilla-release`.
- Avoid production scopes — only use them in the final test phases.
- Test against the staging scriptworker environment first.
