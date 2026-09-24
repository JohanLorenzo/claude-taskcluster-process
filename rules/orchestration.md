# Orchestration

The main session runs Opus and only plans, dispatches, reviews and talks to
the user. All file edits, shell commands, test runs, git/gh operations and
non-trivial searches are delegated. `hooks/enforce_orchestrator.py` and
`hooks/route_skills_to_subagents.py` back this with a hard block; this rule is
about doing it well, not just avoiding the block.

## Delegation

- Use `Explore` for searches, `Plan` for design, and `general-purpose` for
  everything else: implementation, tests, commits, pushes, monitoring.
- Never use `subagent_type: "fork"` and never pass `model: opus` or
  `model: fable` to the Agent tool. Forks and those models run on the main
  model, which defeats the point.
- When a hook redirects a skill (model-invoked or a typed `/command`),
  dispatch a `general-purpose` subagent right away with the exact skill name
  and args from the block reason or `additionalContext`. Don't try the skill
  again in the main session first.
- Give each subagent a self-contained prompt: the files it touches, the exact
  test command and expected outcome, the commit message, and which rules
  apply (`planning-discipline`, `taskcluster-workflow`, etc.).
- Run independent subagents in parallel — a single message with multiple
  `Agent` calls.

## What stays in the main session

- Reading small files to check a subagent's claims, or to write the plan
  file itself.
- Plan mode and memory writes (`~/.claude/plans/`,
  `~/.claude/projects/*/memory/`) — the hook allows these paths directly.
- Reference-only skills that just load instructions (`workflow-authoring`,
  `claude-api`, `update-config`, `keybindings-help`, `loop`,
  `fewer-permission-prompts`) — see `INLINE_SKILLS` in
  `hooks/route_skills_to_subagents.py`.

## Escape hatch

`CLAUDE_MAIN_SESSION_WORK=1 claude` disables both hooks for one session, for
emergencies. Don't reach for it as a routine workaround — if a skill keeps
needing it, add it to `INLINE_SKILLS` instead.
