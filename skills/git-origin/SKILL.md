---
name: Git Origin Tracer
description: Trace any line of code back to its original introduction, following moves, renames, and copies, then extract the bug number
---

# Git Origin Tracer Skill

Find the original commit that introduced a specific line of code, ignoring formatting changes and following code movement.

## When to Use

Use this skill when the user:
- Asks where a line of code came from
- Wants to know who originally wrote specific code
- Needs the bug number that introduced a feature
- Asks about blame history or code origins
- Wants to trace code through refactors and moves

## How to Use

Run the `trace_origin.sh` script with one of these input formats:

### Input Formats

1. **File path + line number:**
```bash
~/.claude/skills/git-origin/scripts/trace_origin.sh src/main.rs:42
```

2. **File path only (will show blame for entire file):**
```bash
~/.claude/skills/git-origin/scripts/trace_origin.sh src/main.rs
```

3. **File path + search string:**
```bash
~/.claude/skills/git-origin/scripts/trace_origin.sh src/main.rs "function processData"
```

### Script Behavior

The script:
- Ignores whitespace-only changes (`-w`)
- Follows moves within and across files (`-M`)
- Detects copy-paste with maximum sensitivity (`-C -C -C`)
- Works with uncommitted changes
- Traces back to the first **meaningful** change (actual content modification)
- Extracts bug numbers from commit messages

### Output Format

The script outputs:
- **Commit SHA**: Full hash of the original commit
- **Bug Number**: Extracted from commit message (Bug XXXXXX format)
- **Author**: Original author name and email
- **Date**: When the line was introduced
- **File History**: Path changes if file was moved/renamed
- **Change Summary**: What changed in that commit

## Important Notes

- Always run from within a git repository
- Works with uncommitted changes in working tree
- Skips formatting-only commits to find meaningful changes
- If no bug number found, indicates commit has no bug reference
- For ambiguous search strings, shows multiple matches
