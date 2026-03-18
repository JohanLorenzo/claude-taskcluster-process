import json
import logging
import os
import re
import sys
from pathlib import Path

from .constants import LOCAL_CONFIG_FILE, REQUIRED_REPOS
from .utils import unified_diff

logger = logging.getLogger(__name__)

_SKIP_DIRS = frozenset(
    {".venv", ".tox", "__pycache__", "site-packages", "node_modules"}
)


def _find_files(root, relative_pattern):
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


def matches_pyproject_name(text, name):
    return f'name = "{name}"' in text or f"name = '{name}'" in text


def scan_pyprojects(root):
    taskgraph, fxci, mozilla_taskgraph = [], [], []
    for pyproject in _find_files(root, "pyproject.toml"):
        try:
            text = pyproject.read_text()
        except OSError:
            continue
        if matches_pyproject_name(text, "taskgraph"):
            candidate = _repo_root(pyproject.parent)
            if candidate not in taskgraph:
                taskgraph.append(candidate)
        if matches_pyproject_name(text, "fxci-config") and pyproject.parent not in fxci:
            fxci.append(pyproject.parent)
        if (
            matches_pyproject_name(text, "mozilla-taskgraph")
            and pyproject.parent not in mozilla_taskgraph
        ):
            mozilla_taskgraph.append(pyproject.parent)
    return taskgraph, fxci, mozilla_taskgraph


def scan_package_jsons(root):
    taskcluster = []
    for pkg_json in _find_files(root, "package.json"):
        try:
            data = json.loads(pkg_json.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("name") == "taskcluster" and data.get("private") is True:
            candidate = _repo_root(pkg_json.parent)
            if candidate not in taskcluster:
                taskcluster.append(candidate)
    return taskcluster


def find_repo_candidates(root):
    taskgraph, fxci, mozilla_taskgraph = scan_pyprojects(root)
    for init in _find_files(root, "taskgraph/__init__.py"):
        candidate = _repo_root(init.parent.parent)
        if candidate not in taskgraph:
            taskgraph.append(candidate)
    taskcluster = scan_package_jsons(root)
    return taskgraph, fxci, mozilla_taskgraph, taskcluster


def parse_github_slugs(fxci_config_repo):
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


def discover_tracked_repos(fxci_config_repo, search_root):
    slugs = parse_github_slugs(fxci_config_repo)
    slug_map = {tuple(slug.split("/", 1)): slug for slug in slugs}
    found = {}
    for dirpath, dirnames, _ in os.walk(search_root):
        dirnames[:] = [
            d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
        ]
        if (Path(dirpath) / ".git").exists():
            dirnames.clear()
            continue
        parent = Path(dirpath).name
        for child in dirnames:
            slug = slug_map.get((parent, child))
            if slug and slug not in found:
                found[slug] = str(Path(dirpath) / child)
    return [{"name": slug, "path": path} for slug, path in sorted(found.items())]


def build_repos_list(
    taskgraph_repo,
    mozilla_taskgraph_repo,
    fxci_config_repo,
    taskcluster_repo,
    search_root,
):
    tg_slug = "/".join(taskgraph_repo.parts[-2:])
    repos = [{"name": tg_slug, "path": str(taskgraph_repo)}]
    mtg_slug = "/".join(mozilla_taskgraph_repo.parts[-2:])
    if {"name": mtg_slug, "path": str(mozilla_taskgraph_repo)} not in repos:
        repos.append({"name": mtg_slug, "path": str(mozilla_taskgraph_repo)})
    fxci_slug = "/".join(fxci_config_repo.parts[-2:])
    if {"name": fxci_slug, "path": str(fxci_config_repo)} not in repos:
        repos.append({"name": fxci_slug, "path": str(fxci_config_repo)})
    tc_slug = "/".join(taskcluster_repo.parts[-2:])
    if {"name": tc_slug, "path": str(taskcluster_repo)} not in repos:
        repos.append({"name": tc_slug, "path": str(taskcluster_repo)})
    existing = {r["name"] for r in repos}
    for r in discover_tracked_repos(fxci_config_repo, search_root):
        if r["name"] not in existing:
            repos.append(r)
            existing.add(r["name"])
    return repos


def parse_local_config_content(text):
    def get_path(key):
        m = re.search(rf"^{key}:\s*(.+)$", text, re.MULTILINE)
        return Path(m.group(1).strip()) if m else None

    return {
        "taskgraph_repo": get_path("taskgraph_repo"),
        "mozilla_taskgraph_repo": get_path("mozilla_taskgraph_repo"),
        "fxci_config_repo": get_path("fxci_config_repo"),
        "taskcluster_repo": get_path("taskcluster_repo"),
        "repo_paths": re.findall(r"^\s+path:\s*(.+)$", text, re.MULTILINE),
    }


def render_local_config(
    taskgraph_repo, mozilla_taskgraph_repo, fxci_config_repo, taskcluster_repo, repos
):
    repo_lines = "".join(
        f"  - name: {r['name']}\n    path: {r['path']}\n" for r in repos
    )
    return (
        "# Local configuration — DO NOT COMMIT\n\n"
        f"## Required paths\ntaskgraph_repo: {taskgraph_repo}\n"
        f"mozilla_taskgraph_repo: {mozilla_taskgraph_repo}\n"
        f"fxci_config_repo: {fxci_config_repo}\n"
        f"taskcluster_repo: {taskcluster_repo}\n"
        f"\n## Tracked repositories\nrepos:\n{repo_lines}"
    )


def compute_local_config_update():
    if not LOCAL_CONFIG_FILE.exists():
        return [], None, []
    old_content = LOCAL_CONFIG_FILE.read_text()
    config = parse_local_config_content(old_content)
    taskgraph_repo = config["taskgraph_repo"]
    if not taskgraph_repo:
        return [], None, []
    mozilla_taskgraph_repo = config["mozilla_taskgraph_repo"]
    fxci_config_repo = config["fxci_config_repo"]
    taskcluster_repo = config["taskcluster_repo"]
    root = get_search_root()
    _, fxci_candidates, mtg_candidates, tc_candidates = find_repo_candidates(root)
    if not mozilla_taskgraph_repo:
        mozilla_taskgraph_repo = pick_repo(
            mtg_candidates,
            "mozilla-taskgraph",
            required=True,
            hint=f"Clone it first:\n  git clone {REQUIRED_REPOS['mozilla-taskgraph']}",
        )
    if not fxci_config_repo:
        fxci_config_repo = pick_repo(
            fxci_candidates,
            "fxci-config",
            required=True,
            hint=f"Clone it first:\n  git clone {REQUIRED_REPOS['fxci-config']}",
        )
    if not taskcluster_repo:
        taskcluster_repo = pick_repo(
            tc_candidates,
            "taskcluster",
            required=True,
            hint=f"Clone it first:\n  git clone {REQUIRED_REPOS['taskcluster']}",
        )
    for label, path in [
        ("taskgraph", taskgraph_repo),
        ("mozilla-taskgraph", mozilla_taskgraph_repo),
        ("fxci-config", fxci_config_repo),
        ("taskcluster", taskcluster_repo),
    ]:
        if not path.is_dir():
            logger.error(
                "ERROR: %s not found at %s\n%s",
                label,
                path,
                f"Clone it first:\n  git clone {REQUIRED_REPOS[label]}",
            )
            sys.exit(1)
    repos = build_repos_list(
        taskgraph_repo, mozilla_taskgraph_repo, fxci_config_repo, taskcluster_repo, root
    )
    new_content = render_local_config(
        taskgraph_repo,
        mozilla_taskgraph_repo,
        fxci_config_repo,
        taskcluster_repo,
        repos,
    )
    diff = unified_diff(
        old_content,
        new_content,
        str(LOCAL_CONFIG_FILE),
        str(LOCAL_CONFIG_FILE) + " (new)",
    )
    return diff, new_content, repos


def get_search_root():
    root_input = input("Enter root path to search for repos (e.g., ~/git): ").strip()
    root = Path(root_input).expanduser().resolve()
    if not root.is_dir():
        logger.error("ERROR: %s is not a directory.", root)
        sys.exit(1)
    return root


def pick_repo(candidates, label, *, required, hint=None):
    if not candidates:
        if required:
            msg = f"ERROR: Could not find a {label} checkout."
            if hint:
                msg += f"\n{hint}"
            logger.error(msg)
            sys.exit(1)
        logger.info("%s not found — skipping.", label)
        return None
    if len(candidates) == 1:
        logger.info("Found %s: %s", label, candidates[0])
        return candidates[0]
    logger.info("Multiple %s candidates found:", label)
    for i, c in enumerate(candidates):
        logger.info("  %d. %s", i + 1, c)
    return candidates[int(input("Pick one (number): ").strip()) - 1]


def generate_local_config():
    logger.info("\n--- CLAUDE.local.md setup ---")
    root = get_search_root()
    logger.info("\nSearching for repos under %s...", root)
    (
        taskgraph_candidates,
        fxci_candidates,
        mozilla_taskgraph_candidates,
        taskcluster_candidates,
    ) = find_repo_candidates(root)
    taskgraph_repo = pick_repo(
        taskgraph_candidates,
        "taskgraph",
        required=True,
        hint=f"Clone it first:\n  git clone {REQUIRED_REPOS['taskgraph']}",
    )
    mozilla_taskgraph_repo = pick_repo(
        mozilla_taskgraph_candidates,
        "mozilla-taskgraph",
        required=True,
        hint=f"Clone it first:\n  git clone {REQUIRED_REPOS['mozilla-taskgraph']}",
    )
    fxci_config_repo = pick_repo(
        fxci_candidates,
        "fxci-config",
        required=True,
        hint=f"Clone it first:\n  git clone {REQUIRED_REPOS['fxci-config']}",
    )
    taskcluster_repo = pick_repo(
        taskcluster_candidates,
        "taskcluster",
        required=True,
        hint=f"Clone it first:\n  git clone {REQUIRED_REPOS['taskcluster']}",
    )
    repos = build_repos_list(
        taskgraph_repo, mozilla_taskgraph_repo, fxci_config_repo, taskcluster_repo, root
    )
    content = render_local_config(
        taskgraph_repo,
        mozilla_taskgraph_repo,
        fxci_config_repo,
        taskcluster_repo,
        repos,
    )
    logger.info("\n--- Generated CLAUDE.local.md ---")
    logger.info(content)
    if input("Write CLAUDE.local.md? [y/N]: ").strip().lower() != "y":
        logger.info("Aborted.")
        sys.exit(0)
    LOCAL_CONFIG_FILE.write_text(content)
    logger.info("Written: %s", LOCAL_CONFIG_FILE)
