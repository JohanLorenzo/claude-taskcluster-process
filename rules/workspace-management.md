# Workspace Management

## Worktrees for tracked repositories

If you touch any repository listed in `CLAUDE.local.md`, create a worktree before
making changes. Use `EnterWorktree` to enter a new worktree.

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
