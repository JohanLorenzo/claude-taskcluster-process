import logging
import os
import re
import sys
from pathlib import Path

from .constants import LOCAL_CONFIG_FILE
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
    taskgraph, fxci = [], []
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
    return taskgraph, fxci


def find_repo_candidates(root):
    taskgraph, fxci = scan_pyprojects(root)
    for init in _find_files(root, "taskgraph/__init__.py"):
        candidate = _repo_root(init.parent.parent)
        if candidate not in taskgraph:
            taskgraph.append(candidate)
    return taskgraph, fxci


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
        parent = Path(dirpath).name
        for child in dirnames:
            slug = slug_map.get((parent, child))
            if slug and slug not in found:
                found[slug] = str(Path(dirpath) / child)
    return [{"name": slug, "path": path} for slug, path in sorted(found.items())]


def build_repos_list(taskgraph_repo, fxci_config_repo, search_root):
    tg_slug = "/".join(taskgraph_repo.parts[-2:])
    repos = [{"name": tg_slug, "path": str(taskgraph_repo)}]
    if fxci_config_repo:
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
        "fxci_config_repo": get_path("fxci_config_repo"),
        "repo_paths": re.findall(r"^\s+path:\s*(.+)$", text, re.MULTILINE),
    }


def render_local_config(taskgraph_repo, fxci_config_repo, repos):
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


def compute_local_config_update():
    if not LOCAL_CONFIG_FILE.exists():
        return [], None, []
    old_content = LOCAL_CONFIG_FILE.read_text()
    config = parse_local_config_content(old_content)
    taskgraph_repo = config["taskgraph_repo"]
    fxci_config_repo = config["fxci_config_repo"]
    if not taskgraph_repo:
        return [], None, []
    root = get_search_root()
    repos = build_repos_list(taskgraph_repo, fxci_config_repo, root)
    new_content = render_local_config(taskgraph_repo, fxci_config_repo, repos)
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


def pick_repo(candidates, label, *, required):
    if not candidates:
        if required:
            logger.error("ERROR: Could not find a %s checkout.", label)
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
    taskgraph_candidates, fxci_candidates = find_repo_candidates(root)
    taskgraph_repo = pick_repo(taskgraph_candidates, "taskgraph", required=True)
    fxci_config_repo = pick_repo(fxci_candidates, "fxci-config", required=False)
    repos = build_repos_list(taskgraph_repo, fxci_config_repo, root)
    content = render_local_config(taskgraph_repo, fxci_config_repo, repos)
    logger.info("\n--- Generated CLAUDE.local.md ---")
    logger.info(content)
    if input("Write CLAUDE.local.md? [y/N]: ").strip().lower() != "y":
        logger.info("Aborted.")
        sys.exit(0)
    LOCAL_CONFIG_FILE.write_text(content)
    logger.info("Written: %s", LOCAL_CONFIG_FILE)
