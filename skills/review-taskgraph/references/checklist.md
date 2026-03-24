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

## Kind YAML correctness

- **kebab-case identifiers**: all YAML keys under `tasks:` must match
  `^[a-z$][a-z0-9-]*$`. No camelCase, no snake_case.
- **Loader/transform chain**: when using `taskgraph.loader.default:loader`, do NOT
  include `taskgraph.transforms.run:transforms` or
  `taskgraph.transforms.task:transforms` in the `transforms:` list — the default
  loader appends them automatically. Duplicating them causes errors.
- **`task-defaults`**: shared configuration across tasks in a kind belongs in
  `task-defaults:`, not duplicated in each task entry.
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

- **No `task_name` branching**: transforms must not branch on `task["name"]` (or
  `task_name`) to produce different behaviour per task. Task-specific configuration
  belongs in the kind YAML (as fields on each task entry, or via `task-defaults`);
  the transform reads those fields rather than switching on the name. Branching on
  name couples the transform to every task that uses it and forces a code change
  whenever a new task is added.

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
