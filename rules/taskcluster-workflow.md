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
- `load-task` fails or neither applies → use `/taskcluster-submit-task` skill.

**`load-task` recipe for locally generated tasks**:

1. Create a local params file with the real fork URL and current HEAD rev.

2. Generate the task definition:
   ```bash
   uv run --with-editable "<taskgraph_repo>" taskgraph target-graph \
     --root taskcluster -p /tmp/local-params.yml --json 2>/dev/null \
     | python3 -c "import sys,json; g=json.load(sys.stdin); print(json.dumps(g['<task-label>']['task']))" \
     > /tmp/task.json
   ```

3. Run the task locally:
   ```bash
   source /tmp/tc-staging-creds.sh
   DOCKER_DEFAULT_PLATFORM=linux/amd64 TASKCLUSTER_ROOT_URL=<staging-url> \
     uv run --with-editable "<taskgraph_repo>[load-image]" taskgraph load-task \
     --root taskcluster --image task-id=<docker-image-task-id> - < /tmp/task.json
   ```

   **Note**: Compiled binaries (ruff, etc.) may segfault under qemu on Apple Silicon.
   For pre-commit/ruff checks, run `pre-commit run -a` natively instead of inside `load-task`.

**Direct task submission**: use the `/taskcluster-submit-task` skill.

### Step 6: Push to PR

For every commit being pushed: the step 5 test for that commit must have passed
locally before pushing. Never skip this — pushing to CI is not a substitute for
local testing.

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

**Monitoring protocol**: use the skill (single approval, blocks until done):
```
/taskcluster-monitor-group <TC_ROOT_URL> <DECISION_TASK_ID>
```

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
subsequent `taskcluster` commands.

After clearing, public task artifacts (`task log`, `task status`, `group status`) work
without credentials — just set `TASKCLUSTER_ROOT_URL`. Only authenticated operations
(task creation, private artifacts) need `taskcluster signin`.

## Reference: fxci-config validation

```bash
cd <fxci_config_repo> && uv run ci-admin diff --environment firefoxci
```

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
