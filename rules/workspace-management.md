# Workspace Management

## Worktrees for tracked repositories

If you touch any repository listed in `CLAUDE.local.md`, create a worktree before
making changes.

### Determining upstream

Before creating a worktree, identify the upstream remote and its default branch:

1. Check if the repo is a fork:
   ```bash
   gh repo view --json parent --jq '.parent.nameWithOwner // empty'
   ```
2. If the output is non-empty the repo is a fork — run `git remote -v` and find
   which remote URL contains that owner/repo. That is the upstream remote.
   If empty, the repo is not a fork — use `origin`.
3. Get the default branch:
   ```bash
   gh repo view <owner/repo> --json defaultBranchRef --jq '.defaultBranchRef.name'
   ```
   where `<owner/repo>` is the parent (if fork) or the origin repo.
4. Fetch the upstream remote:
   ```bash
   git fetch <remote>
   ```

### Primary repo

Use `EnterWorktree` to create the worktree, then reset to the upstream ref:
```bash
git reset --hard <remote>/<default-branch>
```

### Secondary repos

`EnterWorktree` only works on the primary repo. For secondary repos, create the
worktree manually:
```bash
git worktree add <path> -b <branch> <remote>/<default-branch>
```

## Cleanup at plan start

When entering any tracked repository, list all existing worktrees:
```bash
git worktree list
```
If a worktree's corresponding PR was merged, delete the worktree:
```bash
git worktree remove <path>
```
This cleanup happens at the **start** of a plan, not the end. Do NOT delete
worktrees at the end of a plan — the user may still need them.
