# Taskcluster Workflow

Read `CLAUDE.local.md` for local paths. The taskgraph command is:
```
uv run --with-editable "<taskgraph_repo>" taskgraph
```

## Sign in

Always split into two separate commands (one approval each):
```bash
taskcluster signin \
  -n 'mozilla-auth0/ad|Mozilla-LDAP|jlorenzo/claude-code-client-<RANDOM>' \
  --scope 'queue:get-artifact:public/*' --expires 1d \
  > /tmp/tc-creds.sh
```
```bash
source /tmp/tc-creds.sh
```
Replace `<RANDOM>` with a 7-letter random hash (e.g., `xk4mfqz`).

## Local validation

```bash
uv run --with-editable "<taskgraph_repo>" taskgraph target-graph \
  --root taskcluster -p taskcluster/test/params/<event>.yml
```
On the Firefox repo: `./mach taskgraph target-graph -p <params>`

## Local testing

If the task runs in a Docker container, test it locally before pushing:
```bash
DOCKER_DEFAULT_PLATFORM=linux/amd64 \
  uv run --with-editable "<taskgraph_repo>[load-image]" taskgraph load-task $TASK_ID
```
Some tasks can't be run locally (e.g., generic-worker tasks on macOS, scriptworker
tasks). If `load-task` fails, fall back to direct submission (see below).

For scriptworker tasks: spawn a local worker against the staging environment.

## Staging environment

When scope changes are required (new scopes, changed worker configs), use staging
instead of production for the first test cycles. Switch to production only in the
final verification phase.

## Direct task submission (iterate without a full push cycle)

Always split into separate commands:

**Step 1** — get the failed task definition:
```bash
taskcluster task def $FAILED_TASK_ID > /tmp/task.json
```

**Step 2** — edit `/tmp/task.json` to fix the issue (payload, env, command, etc.)

**Step 3** — update timestamps:
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

**Step 4** — sign in with the task's required scopes (extract from `schedulerId`,
`provisionerId`, `workerType`, `routes`, and `scopes` fields):
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

**Step 5** — generate a new task ID (separate command, save to variable):
```bash
TASK_ID=$(taskcluster slugid generate)
```

**Step 6** — submit:
```bash
taskcluster api queue createTask $TASK_ID < /tmp/task.json
```

Once the task is green, port the fix back to the local code and commit.

## Push to PR

Only push to a PR after:
1. Local validation passes.
2. Direct submission (or local testing) succeeds.

## Monitoring after a push

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

## Simulating non-PR events (release, push) from a PR

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

## fxci-config validation

```bash
cd <fxci_config_repo> && uv run ci-admin diff --environment firefoxci
```
where `<fxci_config_repo>` comes from `CLAUDE.local.md`.

## Scriptworker-specific guidance

- Use treeherder-cli to find a recent example of a similar task on `mozilla-release`.
- Avoid production scopes — only use them in the final test phases.
- Test against the staging scriptworker environment first.

## Speed: minimize the feedback loop

Pushing to a PR / try is slow. Always prefer:
1. Local validation (`taskgraph target-graph`)
2. Local testing (`load-task` or local worker)
3. Direct task submission (`createTask`)
4. Only then: push to PR

## Command hygiene

- No piped commands — use `--jq` flags and separate commands instead.
- No subshells — break multi-step operations into individually approvable commands.
- No `eval $(...)` patterns — redirect to a file and `source` it instead.

## PR completion

After a PR is merged (or ready for review), write a GitHub comment explaining what
was verified. Include links to tasks and relevant log extracts.

## On failures

Stop immediately and report findings to the user. Do not retry with the same broken
approach.
