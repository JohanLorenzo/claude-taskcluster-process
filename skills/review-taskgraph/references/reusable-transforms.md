# Reusable Transforms and Utilities

## Conditional values

**`resolve_keyed_by`** — `taskgraph.util.schema:resolve_keyed_by`

Replaces: manual `if platform == "linux"` / `elif` chains that branch on task
attributes.

Use `by-<attribute>:` in YAML instead:
```yaml
worker-type:
  by-platform:
    linux: b-linux
    macosx: b-osx
```
Then in transforms: `resolve_keyed_by(task, "worker-type", task["name"])`.

## Dependency-based task creation

**`from_deps` transform** — `taskgraph.transforms.from_deps:transforms`

Replaces: custom loops over `config.kind_dependencies_tasks` that create one task per
dependency. Handles grouping, attribute copying, filtering, and naming.

```yaml
transforms:
  - taskgraph.transforms.from_deps
kind-dependencies:
  - build
from-deps:
  group-by: single
  copy-attributes: true
```

**`get_dependencies`** — `taskgraph.util.dependencies:get_dependencies`

Iterate all dependency `Task` objects for a given task dict.

**`get_primary_dependency`** — `taskgraph.util.dependencies:get_primary_dependency`

Get the single primary dependency for a from-deps-created task.

## Parameter substitution

**`task_context` transform** — `taskgraph.transforms.task_context:transforms`

Replaces: manual string formatting of parameters into task fields (f-strings,
`.format()`, `%` formatting).

```yaml
task-context:
  from-parameters:
    head_rev: head_rev
    head_repository: head_repository
  substitution-fields:
    - run.command
```

## Matrix splitting

**`matrix` transform** — `taskgraph.transforms.matrix:transforms`

Replaces: manual for-loops that create task variants for each platform/config.

```yaml
matrix:
  platform:
    - linux
    - macosx
  debug:
    - true
    - false
  exclude:
    - platform: macosx
      debug: true
```

## Parallel chunking

**`chunking` transform** — `taskgraph.transforms.chunking:transforms`

Replaces: manual for-loops splitting one task into N parallel chunks.

```yaml
chunking:
  total-chunks: 10
  substitution-fields:
    - run.command
```
Uses `{this_chunk}` and `{total_chunks}` placeholders.

## Notifications

**`notify` transform** — `taskgraph.transforms.notify:transforms`

Replaces: manual construction of notification routes
(`index.project.{trust-domain}...`).

```yaml
notify:
  email:
    subject: "Task {label} completed"
    content: "See {taskcluster_root_url}/tasks/{task_id}"
    recipients:
      - release-mgmt@mozilla.com
```

## Index-based caching

**`cached_tasks` transform** — `taskgraph.transforms.cached_tasks:transforms`

Replaces: manual index lookups and optimization setup. Used for docker-image and
toolchain kinds.

```yaml
cache:
  type: toolchains.v3
  resources:
    - scripts/build-toolchain.sh
```

## VCS checkout and caches

**`support_vcs_checkout`** — `taskgraph.transforms.run.common:support_vcs_checkout`

Replaces: manual env-var and cache setup for cloning repos in run-task tasks.

**`support_caches`** — `taskgraph.transforms.run.common:support_caches`

Replaces: manual cache configuration (name prefixing, mount point setup).

## Dict merging

**`merge`** — `taskgraph.util.templates:merge`

Replaces: custom dict-merge logic (`dict.update()` loops). Deep-merges nested dicts,
concatenates lists, handles `by-*` keyed values correctly.

```python
from taskgraph.util.templates import merge
result = merge(base_dict, override_dict)
```

## Attribute filtering

**`attrmatch`** — `taskgraph.util.attributes:attrmatch`

Replaces: custom attribute-matching loops with manual key/value comparisons.

```python
from taskgraph.util.attributes import attrmatch
if attrmatch(task.attributes, {"build-type": "opt", "platform": "linux"}):
    ...
```

## Artifact paths

**`get_artifact_prefix`** — `taskgraph.util.taskcluster:get_artifact_prefix`

Replaces: hardcoded `public/build` strings. Returns the correct prefix based on the
task's `artifact_prefix` attribute.

## mozilla-taskgraph extensions

**`release_artifacts` transform** —
`mozilla_taskgraph.transforms.scriptworker.release_artifacts:transforms`

Replaces: manual artifact setup for release builds. Automatically creates artifacts
under `public/build` and populates the `release-artifacts` attribute. Handles
docker-worker vs generic-worker path differences.

**`replicate` transform** — `mozilla_taskgraph.transforms.replicate:transforms`

Replaces: manual task replication from upstream decision tasks. Rewrites tasks from
another project's task graph for the current trust domain/level.

**Scriptworker payload builders** — `mozilla_taskgraph.worker_types`

Registered payload builders for scriptworker task types:
- `scriptworker-signing` — autograph code signing
- `scriptworker-beetmover-data` — artifact upload via beetmover
- `scriptworker-shipit` — Ship-It release management
- `scriptworker-lando` — merge day operations, tagging, version bumps
- `scriptworker-bitrise` — Bitrise CI integration
