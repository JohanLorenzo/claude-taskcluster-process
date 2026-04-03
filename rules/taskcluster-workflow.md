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
  → push to PR. Repeat steps 3–8 for every commit.
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
commit the full per-commit gate sequence (Steps 3–8):
- Step 3: the exact param files to validate against and expected task labels
- Step 4: the review range
- Step 5: which test method applies (load-task, direct submission, or local
  worker) and the exact task label to test
- Step 6: push to PR and the TC_ROOT_URL to monitor against (staging or
  production, per Step 1)
- Step 7: monitor with /taskcluster-monitor-group
- Step 8: update PR description with verification

Do not defer these decisions to implementation time.

**Migration rule**: before writing any task command, read the existing CI/CD
configuration (whatever form it takes: `.taskcluster.yml`, `Jenkinsfile`,
GitHub Actions workflows, shell scripts called from CI, etc.) to understand what
each task is already doing. Do not reimplement logic that already exists in a
script — adapt the script for the new environment instead.

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

### Step 3: Validate locally

Repeat steps 3–8 for each commit.

Gate: must pass before proceeding to step 4.

```bash
uv run --with-editable "<taskgraph_repo>" taskgraph target-graph \
  --root taskcluster -p taskcluster/test/params/<event>.yml
```
On the Firefox repo: `./mach taskgraph target-graph -p <params>`

`--diff` compares the current state against HEAD. Run it only after committing —
an uncommitted working directory causes the command to abort.

### Step 4: Self-review

Gate: must be PASS or PASS-WITH-NOTES before proceeding to step 5.

```
/review-taskgraph <base>..<HEAD>
```

If NEEDS-CHANGES: fix all ERRORs and WARNINGs, re-run Step 3, then repeat.

### Step 5: Test

Gate: must pass before proceeding to step 6.

- Docker task → `/taskcluster-local-test <TC_ROOT_URL> <task-label> --params <file>`
- Scriptworker task → spawn a local worker against the staging environment.
- Needs TC proxy / secrets → `/taskcluster-submit-task <TC_ROOT_URL> --task-id <ID>`

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

Stream a task's live log:
```bash
TASKCLUSTER_ROOT_URL=<TC_ROOT_URL> taskcluster task log <task-id>
```

## Reference: fxci-config validation

Requires Taskcluster credentials with `auth:list-clients` scope and a GitHub token
to avoid rate limits. See fxci-config's README "Initial Setup" for details.

```bash
TASKCLUSTER_ROOT_URL=https://firefox-ci-tc.services.mozilla.com \
  taskcluster signin --scope auth:list-clients > $TMPDIR/tc-creds.sh
source $TMPDIR/tc-creds.sh
GITHUB_TOKEN=$(gh auth token) uv run ci-admin diff --environment firefoxci
```

## Reference: fxci-config staging deployment

Comment `/taskcluster apply-staging` on the PR (`/taskcluster` prefix required).
Merging to `main` auto-deploys to production.

When using a personal fork for staging validation, add a temporary project entry to
fxci-config (same PR, separate commit) with the fork's repo URL, the correct
trust domain, level-1 branches, and `github-taskgraph: true`. Remove it before merging.

## Reference: Known pitfalls when initializing taskgraph in a repo

**`taskcluster/` directory shadows the `taskcluster` PyPI package**

Creating the `taskcluster/` CI directory in a repo whose Python code imports the
`taskcluster` library causes mypy (and Python's import system) to treat the directory
as a namespace package, hiding the installed library. Symptoms: mypy reports
`Module has no attribute "Queue"` (or similar) on code that imports from `taskcluster`.

Fix — add to `pyproject.toml` at the repo root:
```toml
[tool.ruff.lint.isort]
known-third-party = ["taskcluster"]

[tool.mypy]
namespace_packages = false
```

**`head_ref` vs `short_head_ref` in parameters and test params**

The `.taskcluster.yml` passes `head_ref = event.ref` which is `refs/heads/master` for
push events. `decision_parameters` must NOT modify `head_ref` in place — instead, expose
a separate `short_head_ref` parameter with the prefix stripped. Transforms that need the
branch name (e.g. index routes) must use `short_head_ref`, not `head_ref`.

Test params files must keep `head_ref: refs/heads/master` (the raw value the decision
task receives). They must also set `short_head_ref: master` to reflect what
`decision_parameters` computes.

## Reference: Scriptworker-specific guidance

- Use treeherder-cli to find a recent example of a similar task on `mozilla-release`.
- Avoid production scopes — only use them in the final test phases.
- Test against the staging scriptworker environment first.

## Reference: Firefox release task testing

For `mach try release` commands and `--tasks` flag documentation, see the
[relengdocs staging release guide](https://mozilla-releng.net/relengdocs/how-to/releaseduty/desktop/staging-release.html).

**Getting the hg revision** after the push (needed for ShipIt staging):
```bash
curl -s "https://api.lando.services.mozilla.com/landing_jobs/<lando-job-id>"
```
The lando job ID is printed in the `./mach try release` output.

**Finding the decision task** once indexed:
```bash
TASKCLUSTER_ROOT_URL=https://firefox-ci-tc.services.mozilla.com \
  taskcluster api index findTask gecko.v2.try.revision.<hg-revision>.taskgraph.decision
```

**Listing tasks** spawned by a ship action task (they form their own task group,
separate from the decision task group):
```bash
TASKCLUSTER_ROOT_URL=https://firefox-ci-tc.services.mozilla.com \
  taskcluster group list <action-task-id> --all
```
