IMPORTANT: If `CLAUDE.local.md` does not exist in this directory, STOP. Do not
proceed with any task. Tell the user to run `./install.py` first.

# Claude configuration for this repo

Read `rules/*.md` for full coding and workflow instructions.
Read `CLAUDE.local.md` for local paths (taskgraph repo, tracked repos).

The taskgraph command is built from `CLAUDE.local.md`:
```
uv run --with-editable "<taskgraph_repo>" taskgraph
```
where `<taskgraph_repo>` is the `taskgraph_repo` value in `CLAUDE.local.md`.
