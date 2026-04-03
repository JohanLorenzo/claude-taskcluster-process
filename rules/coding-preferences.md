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

- When committing outside the primary working directory, use `git -C /path` instead of
  `cd /path && git ...`. `cd`-chained commands may not match allow rules, while
  `git -C /path add:*` and `git -C /path commit:*` do.

## GitHub Pull Requests
- Rebase on the base branch of the upstream repository before creating a PR
- Push the branch (`git push -u`) before running `gh pr create`
- Set `--base` explicitly — don't assume the default branch
- Always use `--draft` when creating PRs
- Reference related GitHub issues or Bugzilla bugs in the PR body
- When referencing a Bugzilla bug, use a hyperlink: `[Bug NNNNN](https://bugzilla.mozilla.org/show_bug.cgi?id=NNNNN)`
- Summary section is optional when the PR title already conveys the change

PR body template (use HEREDOC with `gh pr create --body`):

~~~markdown
## Summary

<1-3 bullet points describing what and why>

## Merge order

<Numbered list of merge sequence across repos. Omit section if single-repo change.>

## Verification

<How the change was tested — task links, log excerpts, local test output.>
~~~

## Environment Variables

- `GITHUB_TOKEN=$(gh auth token)` — use this to populate `GITHUB_TOKEN` for any
  command that needs GitHub API access (e.g., `ci-admin diff`, rate-limit avoidance).
  Some repos document additional setup in their README "Initial Setup" section.

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
