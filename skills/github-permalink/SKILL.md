---
name: Convert Github Permalink
description: Convert local file references to GitHub permalinks using main/master branch SHA
context: fork
agent: general-purpose
---

# Convert Github Permalink Skill

Convert local file:line references in documents to immutable GitHub permalinks pointing to the main/master branch HEAD.

## When to Use

Use this skill when the user:
- Asks to "add GitHub permalinks"
- Requests "convert to permalinks"
- Says "add github links"
- Wants to convert file references to GitHub URLs
- Needs permanent links to specific lines of code

## How to Use

Run the script with the file to modify:

```bash
~/.claude/skills/github-permalink/scripts/add_permalinks.sh <file_to_modify>
```

### Script Behavior

The script:
- Saves your current branch
- Detects the default branch (main or master)
- Temporarily switches to the default branch
- Gets the HEAD commit SHA
- Switches back to your original branch
- Gets repo owner/name from GitHub
- Scans the file for file reference patterns
- Replaces them with permalinks: `https://github.com/{owner}/{repo}/blob/{sha}/{file}#L{line}`
- Modifies the file in-place

### Supported Input Patterns

The script detects various file reference formats:
- `src/main.rs:42`
- `` `file.py:123` ``
- `path/to/file.js:line`
- And other common patterns

### Output Format

Generates immutable permalinks:
```
https://github.com/owner/repo/blob/abc123def456.../src/main.rs#L42
```

## Important Notes

- Uses SHA from main/master branch HEAD for true immutable permalinks
- Works from any branch (temporarily switches to get SHA)
- Modifies file in-place
- Requires `gh` CLI to be installed and authenticated
- Must be run from within a git repository
