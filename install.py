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


def _read_local_config_repos():
    if not LOCAL_CONFIG_FILE.exists():
        return []
    repos = []
    in_repos = False
    with LOCAL_CONFIG_FILE.open() as f:
        for line in f:
            stripped = line.strip()
            if stripped == "repos:":
                in_repos = True
                continue
            if in_repos:
                if stripped.startswith("path:"):
                    repos.append(stripped[len("path:") :].strip())
                elif (
                    stripped
                    and not stripped.startswith("#")
                    and ":" in stripped
                    and not stripped.startswith("-")
                ):
                    in_repos = False
    return repos


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


def _generate_local_config():
    print("\n--- CLAUDE.local.md setup ---")
    root_input = input(
        "Enter root path to search for repositories (e.g., ~/git): "
    ).strip()
    root = Path(root_input).expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory.", file=sys.stderr)
        sys.exit(1)

    print(f"\nSearching for repos under {root}...")
    taskgraph_candidates = []
    fxci_candidates = []
    for pyproject in _find_files(root, "pyproject.toml"):
        try:
            text = pyproject.read_text()
        except OSError:
            continue
        if 'name = "taskgraph"' in text or "name = 'taskgraph'" in text:
            candidate = pyproject.parent
            if candidate.name == "src" and (candidate.parent / ".git").is_dir():
                candidate = candidate.parent
            if candidate not in taskgraph_candidates:
                taskgraph_candidates.append(candidate)
        if 'name = "fxci-config"' in text or "name = 'fxci-config'" in text:
            candidate = pyproject.parent
            if candidate not in fxci_candidates:
                fxci_candidates.append(candidate)
    for init in _find_files(root, "taskgraph/__init__.py"):
        candidate = init.parent.parent
        if candidate.name == "src" and (candidate.parent / ".git").is_dir():
            candidate = candidate.parent
        if candidate not in taskgraph_candidates:
            taskgraph_candidates.append(candidate)

    if not taskgraph_candidates:
        print("ERROR: Could not find a taskgraph checkout.", file=sys.stderr)
        sys.exit(1)

    if len(taskgraph_candidates) == 1:
        taskgraph_repo = taskgraph_candidates[0]
        print(f"Found taskgraph: {taskgraph_repo}")
    else:
        print("Multiple taskgraph candidates found:")
        for i, c in enumerate(taskgraph_candidates):
            print(f"  {i + 1}. {c}")
        choice = input("Pick one (number): ").strip()
        taskgraph_repo = taskgraph_candidates[int(choice) - 1]

    fxci_config_repo = None
    if not fxci_candidates:
        print("fxci-config not found — skipping tracked repo discovery.")
    elif len(fxci_candidates) == 1:
        fxci_config_repo = fxci_candidates[0]
        print(f"Found fxci-config: {fxci_config_repo}")
    else:
        print("Multiple fxci-config candidates found:")
        for i, c in enumerate(fxci_candidates):
            print(f"  {i + 1}. {c}")
        choice = input("Pick one (number): ").strip()
        fxci_config_repo = fxci_candidates[int(choice) - 1]

    repos = [{"name": "taskcluster/taskgraph", "path": str(taskgraph_repo)}]
    if fxci_config_repo:
        repos.extend(_discover_tracked_repos(fxci_config_repo, root))

    lines = ["# Local configuration — DO NOT COMMIT\n\n"]
    lines.append(f"## Required paths\ntaskgraph_repo: {taskgraph_repo}\n")
    if fxci_config_repo:
        lines.append(f"fxci_config_repo: {fxci_config_repo}\n")
    lines.append("\n## Tracked repositories\n")
    lines.append("repos:\n")
    for repo in repos:
        lines.append(f"  - name: {repo['name']}\n    path: {repo['path']}\n")

    content = "".join(lines)
    print("\n--- Generated CLAUDE.local.md ---")
    print(content)
    answer = input("Write CLAUDE.local.md? [y/N]: ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)
    LOCAL_CONFIG_FILE.write_text(content)
    print(f"Written: {LOCAL_CONFIG_FILE}")


def _discover_tracked_repos(fxci_config_repo, search_root):
    repos = []
    projects_dir = fxci_config_repo / "config" / "projects"
    if not projects_dir.is_dir():
        return repos
    known_names = set()
    for yml in projects_dir.glob("*.yml"):
        try:
            text = yml.read_text()
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("repo:") or line.startswith("- repo:"):
                    url = line.split(":", 1)[1].strip().rstrip("/")
                    if "github.com" in url:
                        parts = url.rstrip(".git").split("/")
                        if len(parts) >= 2:
                            slug = "/".join(parts[-2:])
                            known_names.add(slug)
        except OSError:
            pass
    for slug in sorted(known_names):
        org, name = slug.split("/", 1)
        for candidate in search_root.rglob(f"{name}/.git"):
            repos.append({"name": slug, "path": str(candidate.parent)})
            break
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

    diff = _settings_diff(settings, new_settings)
    if diff:
        print(f"\n--- {SETTINGS_FILE} ---")
        print("".join(diff))
    else:
        print(f"\n= no change: {SETTINGS_FILE}")

    if symlink_ops:
        print("\n--- rules/ symlinks ---")
        _print_symlink_ops(symlink_ops)

    answer = input("\nApply changes? [y/N]: ").strip().lower()
    if answer != "y":
        print("No changes made.")
        sys.exit(0)

    SETTINGS_FILE.write_text(json.dumps(new_settings, indent=2) + "\n")
    print(f"Updated: {SETTINGS_FILE}")

    RULES_DIR.mkdir(exist_ok=True)
    for op in symlink_ops:
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
