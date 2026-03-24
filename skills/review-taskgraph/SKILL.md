---
name: review-taskgraph
description: Review taskgraph-related patches (transforms, kind YAML, worker config) for correctness, best practices, and reuse of existing upstream utilities
allowed-tools: Bash, Read, Grep, Glob
argument-hint: "[PR-URL | D<revision> | commit-range]"
---

# Review Taskgraph

Review taskgraph patches for correctness, best practices, and reuse of existing
upstream transforms and utilities.

## When to Use

Use this skill when the user invokes `/review-taskgraph` with one of:
- A GitHub PR URL (e.g., `https://github.com/org/repo/pull/42`)
- A Phabricator revision (e.g., `D12345` or full URL)
- A git commit range (e.g., `main..HEAD`)
- No argument (reviews uncommitted changes)

## Process

Note: if the user provided an argument, it is appended at the end of this skill
as `ARGUMENTS: <value>`. Use that value in step 1.

1. Get the diff. Check the `ARGUMENTS:` line at the bottom of this document.
   - If `ARGUMENTS` is non-empty, run:
     `python3 ~/.claude/skills/review-taskgraph/scripts/get_diff.py <ARGUMENTS_VALUE>`
   - If `ARGUMENTS` is absent or empty, run:
     `python3 ~/.claude/skills/review-taskgraph/scripts/get_diff.py`

2. From the diff, identify taskgraph-relevant files:
   - Python files under `transforms/` directories
   - Kind YAML files (`kind.yml` or `kind.yaml`)
   - `taskcluster/config.yml`
   - Dockerfiles under `taskcluster/docker/`
   - Parameter files and `__init__.py` with `register()`

3. Read each modified file in full (not just diff hunks) to understand context.

4. Load the review references:
   - @references/checklist.md
   - @references/reusable-transforms.md

5. For each potential reuse opportunity, verify the utility actually exists by reading
   the source at the paths from CLAUDE.local.md (`taskgraph_repo`,
   `mozilla_taskgraph_repo`).

6. Produce the structured report below.

## Output Format

```
## Taskgraph Review: <target description>

### Verdict: PASS | PASS-WITH-NOTES | NEEDS-CHANGES

### Findings

#### `<file-path>`

- **[ERROR]** `<category>` (line N): <description>
  - Fix: <concrete suggestion>

- **[WARNING]** `<category>` (line N): <description>
  - Fix: <concrete suggestion>

- **[SUGGESTION]** `<category>` (line N): <description>
  - Consider: <alternative approach>

### Reuse Opportunities

| Custom Code | Existing Utility | Import Path |
|---|---|---|
| <what the custom code does> | <utility name> | <import path> |
```

Severity levels:
- **ERROR**: will break at runtime, violates a hard constraint, or is a clear bug
- **WARNING**: works but violates conventions or misses a better approach
- **SUGGESTION**: style improvement or optional optimization

Categories: `transform-correctness`, `kind-yaml`, `worker-scope`, `general-quality`,
`reuse`

## Important Notes

- This is read-only analysis. Do not modify any files.
- When uncertain about a finding, use SUGGESTION rather than ERROR.
- Skip files that are not taskgraph-related (e.g., application code, CI configs).
- If the diff is empty or contains no taskgraph files, report "No taskgraph changes found."
