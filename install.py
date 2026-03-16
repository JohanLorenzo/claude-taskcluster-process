#!/usr/bin/env python3
"""Install Claude Code hooks and rules symlinks from this repo."""

import difflib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
CLAUDE_DIR = Path.home() / ".claude"
RULES_DIR = CLAUDE_DIR / "rules"
SETTINGS_FILE = CLAUDE_DIR / "settings.json"
HOOKS_CONFIG_FILE = REPO_ROOT / "hooks-config.json"
LOCAL_CONFIG_FILE = REPO_ROOT / "CLAUDE.local.md"
LOCAL_CONFIG_TEMPLATE = REPO_ROOT / "CLAUDE.local.md.template"

REQUIRED_TOOLS = {
    "git": "Install via your system package manager (e.g., brew install git).",
    "gh": "Install from https://cli.github.com/",
    "uv": "Install from https://docs.astral.sh/uv/",
    "taskcluster": (
        "Install via: npm install -g @taskcluster/client-web or pip install taskcluster"
    ),
}
OPTIONAL_TOOLS = {
    "cargo": "Install Rust from https://rustup.rs/ (needed for clippy_on_rust_edit).",
}


def _check_tools():
    errors = []
    warnings = []
    for tool, instructions in REQUIRED_TOOLS.items():
        if not shutil.which(tool):
            errors.append(f"  Required tool missing: {tool}\n    {instructions}")
    for tool, instructions in OPTIONAL_TOOLS.items():
        if not shutil.which(tool):
            warnings.append(f"  Optional tool missing: {tool}\n    {instructions}")
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(w)
    if errors:
        print("ERRORS — install missing tools before running install.py:")
        for e in errors:
            print(e)
        sys.exit(1)


def _load_hooks_config():
    with HOOKS_CONFIG_FILE.open() as f:
        raw = json.load(f)

    def resolve_hooks(hooks_list):
        for entry in hooks_list:
            for hook in entry.get("hooks", []):
                if "command" in hook:
                    hook["command"] = str(REPO_ROOT / hook["command"])
        return hooks_list

    return {event: resolve_hooks(entries) for event, entries in raw.items()}


def _load_settings():
    if not SETTINGS_FILE.exists():
        print(f"ERROR: {SETTINGS_FILE} not found.", file=sys.stderr)
        sys.exit(1)
    try:
        with SETTINGS_FILE.open() as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: {SETTINGS_FILE} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)


def _parse_local_config(path):
    result = {"taskgraph_repo": None, "fxci_config_repo": None, "repo_paths": []}
    if not path.exists():
        return result
    in_repos = False
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("taskgraph_repo:"):
            result["taskgraph_repo"] = Path(stripped[len("taskgraph_repo:") :].strip())
        elif stripped.startswith("fxci_config_repo:"):
            result["fxci_config_repo"] = Path(
                stripped[len("fxci_config_repo:") :].strip()
            )
        elif stripped == "repos:":
            in_repos = True
        elif in_repos:
            if stripped.startswith("path:"):
                result["repo_paths"].append(stripped[len("path:") :].strip())
            elif (
                stripped
                and not stripped.startswith("#")
                and ":" in stripped
                and not stripped.startswith("-")
            ):
                in_repos = False
    return result


def _read_local_config_repos():
    return _parse_local_config(LOCAL_CONFIG_FILE)["repo_paths"]


def _compute_local_config_update():
    config = _parse_local_config(LOCAL_CONFIG_FILE)
    taskgraph_repo = config["taskgraph_repo"]
    fxci_config_repo = config["fxci_config_repo"]
    if not taskgraph_repo:
        return [], None
    search_root = taskgraph_repo.parent.parent
    tg_slug = "/".join(taskgraph_repo.parts[-2:])
    repos = [{"name": tg_slug, "path": str(taskgraph_repo)}]
    if fxci_config_repo:
        existing_names = {r["name"] for r in repos}
        for r in _discover_tracked_repos(fxci_config_repo, search_root):
            if r["name"] not in existing_names:
                repos.append(r)
                existing_names.add(r["name"])
    new_content = _render_local_config(taskgraph_repo, fxci_config_repo, repos)
    old_content = LOCAL_CONFIG_FILE.read_text()
    diff = list(
        difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=str(LOCAL_CONFIG_FILE),
            tofile=str(LOCAL_CONFIG_FILE) + " (new)",
        )
    )
    return diff, new_content


def _compute_new_settings(old_settings, hooks_config):
    new_settings = json.loads(json.dumps(old_settings))
    new_settings["hooks"] = hooks_config
    repo_paths = _read_local_config_repos()
    if repo_paths:
        perms = new_settings.setdefault("permissions", {})
        perms["additionalDirectories"] = repo_paths
    return new_settings


def _settings_diff(old, new):
    old_lines = json.dumps(old, indent=2).splitlines(keepends=True)
    new_lines = json.dumps(new, indent=2).splitlines(keepends=True)
    return list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=str(SETTINGS_FILE),
            tofile=str(SETTINGS_FILE) + " (new)",
        )
    )


def _compute_symlink_ops():
    ops = []
    rules_src_dir = REPO_ROOT / "rules"
    for src in sorted(rules_src_dir.glob("*.md")):
        src_resolved = src.resolve()
        target = RULES_DIR / src.name
        if not target.exists() and not target.is_symlink():
            ops.append(("create", src, target))
        elif target.is_symlink():
            current = Path(os.readlink(target))
            if current.resolve() == src_resolved:
                ops.append(("noop", src, target))
            else:
                ops.append(("update", src, target, current))
        else:
            ops.append(("replace_file", src, target))
    return ops


def _check_preflight_warnings(ops):
    warnings = []
    errors = []
    if SETTINGS_FILE.exists() and not os.access(SETTINGS_FILE, os.W_OK):
        warnings.append(f"WARNING: {SETTINGS_FILE} is read-only.")
    if RULES_DIR.exists() and not RULES_DIR.is_dir():
        errors.append(f"ERROR: {RULES_DIR} exists but is not a directory.")
    for op in ops:
        if op[0] == "replace_file":
            warnings.append(
                f"WARNING: {op[2]} is a regular file (not a symlink)"
                " — will be replaced."
            )
    old_hooks_dir = CLAUDE_DIR / "hooks"
    if old_hooks_dir.is_dir():
        for sh_file in old_hooks_dir.glob("*.sh"):
            py_replacement = (
                REPO_ROOT / "hooks" / (sh_file.stem.replace("-", "_") + ".py")
            )
            if py_replacement.exists():
                warnings.append(
                    f"NOTE: Old shell hook {sh_file} has a Python replacement. "
                    "Consider removing it after install."
                )
    for link in RULES_DIR.glob("*.md") if RULES_DIR.is_dir() else []:
        if link.is_symlink() and not link.resolve().exists():
            warnings.append(f"WARNING: Stale symlink: {link} → {os.readlink(link)}")
    return warnings, errors


def _print_symlink_ops(ops):
    for op in ops:
        if op[0] == "create":
            print(f"  + new symlink: {op[2]} → {op[1]}")
        elif op[0] == "update":
            print(f"  ~ update symlink: {op[2]} → {op[1]} (was → {op[3]})")
        elif op[0] == "replace_file":
            src_text = op[1].read_text()
            target_text = op[2].read_text()
            diff = list(
                difflib.unified_diff(
                    target_text.splitlines(keepends=True),
                    src_text.splitlines(keepends=True),
                    fromfile=str(op[2]),
                    tofile=str(op[1]),
                )
            )
            if diff:
                print(f"  ~ replace file with symlink: {op[2]}")
                print("".join(diff[:40]))
            else:
                print(f"  ~ replace file with symlink (same content): {op[2]}")
        elif op[0] == "noop":
            print(f"  = no change: {op[2]}")


_SKIP_DIRS = frozenset(
    {".venv", ".tox", "__pycache__", "site-packages", "node_modules"}
)


def _find_files(root, relative_pattern):
    """Walk root skipping venv/cache dirs, yield paths matching relative_pattern."""
    parts = Path(relative_pattern).parts
    filename = parts[-1]
    subdirs = parts[:-1]
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
        ]
        if filename in filenames:
            candidate = Path(dirpath) / filename
            if subdirs:
                ok = all(
                    candidate.parts[-(len(subdirs) + 1 + i)] == subdirs[i]
                    for i in range(len(subdirs))
                )
                if not ok:
                    continue
            yield candidate


def _repo_root(path):
    if path.name == "src" and (path.parent / ".git").is_dir():
        return path.parent
    return path


def _pick_repo(candidates, label, *, required):
    if not candidates:
        if required:
            print(f"ERROR: Could not find a {label} checkout.", file=sys.stderr)
            sys.exit(1)
        print(f"{label} not found — skipping.")
        return None
    if len(candidates) == 1:
        print(f"Found {label}: {candidates[0]}")
        return candidates[0]
    print(f"Multiple {label} candidates found:")
    for i, c in enumerate(candidates):
        print(f"  {i + 1}. {c}")
    return candidates[int(input("Pick one (number): ").strip()) - 1]


def _get_search_root():
    root_input = input("Enter root path to search for repos (e.g., ~/git): ").strip()
    root = Path(root_input).expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory.", file=sys.stderr)
        sys.exit(1)
    return root


def _find_repo_candidates(root):
    taskgraph_candidates = []
    fxci_candidates = []
    for pyproject in _find_files(root, "pyproject.toml"):
        try:
            text = pyproject.read_text()
        except OSError:
            continue
        if 'name = "taskgraph"' in text or "name = 'taskgraph'" in text:
            candidate = _repo_root(pyproject.parent)
            if candidate not in taskgraph_candidates:
                taskgraph_candidates.append(candidate)
        if (
            'name = "fxci-config"' in text or "name = 'fxci-config'" in text
        ) and pyproject.parent not in fxci_candidates:
            fxci_candidates.append(pyproject.parent)
    for init in _find_files(root, "taskgraph/__init__.py"):
        candidate = _repo_root(init.parent.parent)
        if candidate not in taskgraph_candidates:
            taskgraph_candidates.append(candidate)
    return taskgraph_candidates, fxci_candidates


def _render_local_config(taskgraph_repo, fxci_config_repo, repos):
    fxci_line = f"fxci_config_repo: {fxci_config_repo}\n" if fxci_config_repo else ""
    repo_lines = "".join(
        f"  - name: {r['name']}\n    path: {r['path']}\n" for r in repos
    )
    return (
        "# Local configuration — DO NOT COMMIT\n\n"
        f"## Required paths\ntaskgraph_repo: {taskgraph_repo}\n"
        f"{fxci_line}"
        f"\n## Tracked repositories\nrepos:\n{repo_lines}"
    )


def _generate_local_config():
    print("\n--- CLAUDE.local.md setup ---")
    root = _get_search_root()
    print(f"\nSearching for repos under {root}...")
    taskgraph_candidates, fxci_candidates = _find_repo_candidates(root)
    taskgraph_repo = _pick_repo(taskgraph_candidates, "taskgraph", required=True)
    fxci_config_repo = _pick_repo(fxci_candidates, "fxci-config", required=False)
    tg_slug = "/".join(taskgraph_repo.parts[-2:])
    repos = [{"name": tg_slug, "path": str(taskgraph_repo)}]
    if fxci_config_repo:
        existing_names = {r["name"] for r in repos}
        for r in _discover_tracked_repos(fxci_config_repo, root):
            if r["name"] not in existing_names:
                repos.append(r)
                existing_names.add(r["name"])
    content = _render_local_config(taskgraph_repo, fxci_config_repo, repos)
    print("\n--- Generated CLAUDE.local.md ---")
    print(content)
    if input("Write CLAUDE.local.md? [y/N]: ").strip().lower() != "y":
        print("Aborted.")
        sys.exit(0)
    LOCAL_CONFIG_FILE.write_text(content)
    print(f"Written: {LOCAL_CONFIG_FILE}")


def _parse_github_slugs(fxci_config_repo):
    projects_file = fxci_config_repo / "projects.yml"
    try:
        text = projects_file.read_text()
    except OSError:
        return set()
    slugs = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("repo:"):
            url = stripped[len("repo:") :].strip().rstrip("/").removesuffix(".git")
            if "github.com/" in url:
                slug = url.split("github.com/", 1)[1]
                if "/" in slug:
                    slugs.add(slug)
    return slugs


def _discover_tracked_repos(fxci_config_repo, search_root):
    slugs = _parse_github_slugs(fxci_config_repo)
    repos = []
    for slug in sorted(slugs):
        org, name = slug.split("/", 1)
        candidate = search_root / org / name
        if candidate.is_dir():
            repos.append({"name": slug, "path": str(candidate)})
    return repos


def main():
    os.chdir(REPO_ROOT)
    _check_tools()

    if not LOCAL_CONFIG_FILE.exists():
        _generate_local_config()

    settings = _load_settings()
    hooks_config = _load_hooks_config()
    new_settings = _compute_new_settings(settings, hooks_config)

    symlink_ops = _compute_symlink_ops()
    warnings, errors = _check_preflight_warnings(symlink_ops)

    for w in warnings:
        print(w)
    for e in errors:
        print(e, file=sys.stderr)
    if errors:
        sys.exit(1)

    local_config_diff, new_local_content = _compute_local_config_update()
    if local_config_diff:
        print(f"\n--- {LOCAL_CONFIG_FILE} ---")
        print("".join(local_config_diff))
    else:
        print(f"\n= no change: {LOCAL_CONFIG_FILE}")

    diff = _settings_diff(settings, new_settings)
    if diff:
        print(f"\n--- {SETTINGS_FILE} ---")
        print("".join(diff))
    else:
        print(f"\n= no change: {SETTINGS_FILE}")

    if symlink_ops:
        print("\n--- rules/ symlinks ---")
        _print_symlink_ops(symlink_ops)

    actionable_ops = [op for op in symlink_ops if op[0] != "noop"]
    if not local_config_diff and not diff and not actionable_ops:
        print("\nAlready up to date.")
        sys.exit(0)

    if input("\nApply changes? [y/N]: ").strip().lower() != "y":
        print("No changes made.")
        sys.exit(0)

    if local_config_diff:
        LOCAL_CONFIG_FILE.write_text(new_local_content)
        print(f"Updated: {LOCAL_CONFIG_FILE}")

    SETTINGS_FILE.write_text(json.dumps(new_settings, indent=2) + "\n")
    print(f"Updated: {SETTINGS_FILE}")

    RULES_DIR.mkdir(exist_ok=True)
    for op in actionable_ops:
        if op[0] in ("create", "update"):
            src, target = op[1], op[2]
            if target.is_symlink() or target.exists():
                target.unlink()
            target.symlink_to(src)
            print(f"Linked: {target} → {src}")
        elif op[0] == "replace_file":
            src, target = op[1], op[2]
            target.unlink()
            target.symlink_to(src)
            print(f"Replaced: {target} → {src}")

    print("\nDone.")
    if (
        subprocess.run(
            ["git", "remote", "get-url", "origin"], capture_output=True
        ).returncode
        == 0
    ):
        print(
            "Note: old ~/.claude/hooks/*.sh scripts can be removed if no longer needed."
        )


if __name__ == "__main__":
    main()
