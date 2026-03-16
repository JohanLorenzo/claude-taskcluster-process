# Coding Preferences

## Code Clarity
- No redundant comments - use clear variable/function names instead
- Break complex logic into smaller, well-named functions
- No docstrings

## Git Best Practices
- Use concise one-liner commit messages
- Never use `git commit --no-verify` - Fix underlying issues instead of bypassing hooks
- Plan commits during the planning phase, not as an afterthought - decide upfront what logical units of work warrant separate commits
- Make commits atomic - each commit should represent one logical change that could be reverted independently
- In plans, explicitly list each commit with its description and the files it touches
- In plans, always include an end-to-end test that you will execute yourself before each commit
- Tests belong in the same commit as the code they cover, not in a separate commit
- Commit immediately after completing each step — never batch all commits at the end

## GitHub Pull Requests
- Rebase on the base branch of the upstream repository before creating a PR
- Push the branch (`git push -u`) before running `gh pr create`
- Set `--base` explicitly — don't assume the default branch
- Always use `--draft` when creating PRs
- Reference related GitHub issues or Bugzilla bugs in the PR body

## API Interaction Rules
- NEVER assume an API endpoint exists. Always verify endpoints work (via curl or equivalent) before writing implementation code around them.
- When an API call returns 404 or unexpected results, stop and report findings rather than trying more unverified endpoints.
- Document verified API endpoints as you discover them.
- If a GitHub API call fails due to rate limiting (HTTP 403/429) or authentication issues, STOP and ask the user to provide a GitHub developer token (`gh auth login`). Do not retry, ignore the failure, or attempt to work around the limit.

## Test Safety
- Tests MUST operate on temporary directories or fixtures, NEVER on production/real data directories.
- Always verify test setup creates isolated environments before running destructive operations.

## Problem Solving Approach
- When a first approach fails, STOP and reassess rather than trying many variations of the same broken idea.
- If you're unsure what to do next, ASK the user rather than exploring tangential paths.
- When the user narrows scope, strictly follow — do not re-expand to include extra cases.
