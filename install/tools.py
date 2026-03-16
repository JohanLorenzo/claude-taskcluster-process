import shutil
import sys

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


def check_tools():
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
