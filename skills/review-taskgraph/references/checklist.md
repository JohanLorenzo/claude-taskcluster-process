# Taskgraph Review Checklist

## Transform correctness

- **Generators required**: every `@transforms.add` function must `yield`, never just
  `return`. A function that returns `None` causes `"Transform X is not a generator"`.
- **Schema-first**: call `transforms.add_validate(MySchema)` before any
  `@transforms.add` function. This ensures invalid input is caught early.
- **Use msgspec Schema**: new code should use
  `class MySchema(Schema, forbid_unknown_fields=False, kw_only=True)` from
  `taskgraph.util.schema`. `LegacySchema` (voluptuous) is for existing code only.
- **`forbid_unknown_fields=False`**: required when the schema allows pass-through
  fields (e.g., fields consumed by later transforms). If all fields are consumed by
  this transform, use the default (`True`).

## `.taskcluster.yml` correctness

- **Pin decision image by digest**: the `image:` field must include both the version
  tag and the manifest digest, e.g.
  `mozillareleases/taskgraph:decision-v20.0.0@sha256:<digest>`. A tag alone is
  mutable and can silently point to a different image after a push. Retrieve the
  digest with `docker buildx imagetools inspect <image>:<tag>`.

## Kind YAML correctness

- **Blank lines for readability**: separate top-level sections (`loader`,
  `transforms`, `kind-dependencies`, `task-defaults`, `tasks`) with a blank line,
  and separate individual task entries under `tasks` with a blank line.

- **kebab-case identifiers**: all YAML keys under `tasks:` must match
  `^[a-z$][a-z0-9-]*$`. No camelCase, no snake_case.
- **Loader/transform chain**: when using `taskgraph.loader.default:loader`, do NOT
  include `taskgraph.transforms.run:transforms` or
  `taskgraph.transforms.task:transforms` in the `transforms:` list — the default
  loader appends them automatically. Duplicating them causes errors.
- **`run-on-tasks-for` / `run-on-git-branches` at top level**: these must be
  top-level task fields, not nested under `attributes:`. At the top level,
  `task.py` converts them to `run_on_tasks_for` / `run_on_git_branches` (underscores)
  in attributes, which the built-in `default` target task reads. Nesting them under
  `attributes:` with hyphens silently breaks standard filtering and requires a custom
  target task function to compensate.

- **`task-defaults` + `task_context` as the default approach**: shared
  configuration belongs in `task-defaults:`, not repeated in each task entry. For
  any field whose value varies by parameter or by task name, use `task_context`
  with `from-parameters` and `substitution-fields` — declared once in
  `task-defaults.task-context` so it applies to all tasks automatically.
  `{name}` (the task's own name) is always available without listing it in
  `from-parameters`. A task entry should contain only what is genuinely unique
  to that task; everything else is a `task-defaults` + `task_context` candidate.
- **`kind-dependencies`**: must list every kind whose tasks are accessed via
  `config.kind_dependencies_tasks` or the `from_deps` transform. Missing entries
  cause empty dependency lookups.
- **Reserved names**: `"self"` and `"decision"` cannot be used as explicit dependency
  labels — they are reserved by taskgraph internals.

## Worker/scope correctness

- **Worker aliases**: use aliases from `config.yml`'s `workers.aliases` section
  (e.g., `b-linux`), not raw `<provisionerId>/<workerType>` strings. Aliases
  automatically parameterize by `{level}` and `{trust-domain}`.
- **`{level}` substitution**: use `{level}` in `worker-type` and `scopes` fields so
  tasks work at any trust level without hardcoding.
- **Artifact paths**: with `run-task` on docker-worker, artifacts must go under
  `/builds/worker/artifacts/`. On generic-worker, use `artifacts/` (relative).
- **`secrets:get:` scope**: when a task uses `taskcluster-proxy: true` and reads a
  secret via `TASKCLUSTER_SECRET`, it must include
  `secrets:get:<secret-name>` in its `scopes` field. No transform adds this
  automatically.
- **Cache volumes**: cache mount points in docker-worker tasks must be declared as
  Docker volumes in the image. Missing volumes cause silent data loss.
- **Cache name prefix**: cache names must start with
  `{trust_domain}-level-{level}-` to ensure isolation between projects and levels.

## Transform design

- **Name transforms precisely, keep them unitary**: function names like
  `add_build_config` or `add_task_config` are too vague. Use names that state
  exactly what the function does (`add_index_routes`, `set_taskcluster_secret`).
  Each `@transforms.add` function should do one thing; split functions that do
  multiple unrelated things into separate transforms.

- **Use `.setdefault()` for partial dict mutation**: if a transform must set one
  computed field inside a nested dict, navigate to the container and set the key —
  do not replace the whole parent dict (`task["run"] = {...}` clobbers every
  YAML-provided sibling). Use `task["run"].setdefault("key", value)` instead.

- **Parameter-derived values belong in YAML**: transforms must not construct field
  values via f-strings or string formatting of runtime parameters. Static templates
  with `{placeholder}` syntax belong in the kind YAML; use `task_context` with
  `from-parameters` to substitute values at graph-generation time. This applies to
  any field: `run.command`, `scopes`, `worker.env.*`, routes, etc.

- **No per-task conditional logic**: transforms must not branch on task identity or
  attributes (`task["name"]`, `task["label"]`, `if platform == "linux"`, etc.) to
  produce different per-task values. Varying configuration belongs in the kind YAML
  (as fields on each task entry, `task-defaults`, or `by-<attribute>:` keys resolved
  with `resolve_keyed_by`). The transform reads those fields; it does not decide what
  value each task gets.

## General quality

- **Deep copy for splits**: when a transform yields multiple tasks from one input,
  each output must be `copy.deepcopy()`'d to avoid shared-state mutation.
- **Max 100 dependencies**: Taskcluster enforces a hard limit of 100 dependencies per
  task. Kinds that fan in (e.g., signing, beetmover) are most at risk.
- **Unique treeherder symbols**: no two tasks in the same platform/collection may
  share a treeherder symbol. Violations cause UI confusion.
- **Tier ordering**: a task at tier N cannot depend on a task at tier > N. Lower tiers
  are higher priority — a tier-1 task depending on tier-2 is invalid.
- **No absolute release-artifact paths**: paths in the `release-artifacts` list must
  be relative. The mozilla-taskgraph `release_artifacts` transform enforces this.
- **`chain-of-trust: true`**: tasks producing artifacts consumed by scriptworker
  (signing, beetmover, etc.) must set `chain-of-trust: true` in their
  `extra.chainOfTrust` field.
