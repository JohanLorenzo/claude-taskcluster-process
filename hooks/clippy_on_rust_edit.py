#!/usr/bin/env python3
"""Hook: run cargo clippy after editing a Rust file (PostToolUse)."""

import json
import subprocess
import sys
from pathlib import Path


def check(tool_input, cwd=None):
    file_path = tool_input.get("file_path", "")
    if not file_path.endswith(".rs"):
        return
    work_dir = str(Path(file_path).parent) if file_path else cwd
    result = subprocess.run(
        [
            "cargo",
            "clippy",
            "--quiet",
            "--",
            "-W",
            "clippy::pedantic",
            "-D",
            "warnings",
        ],
        capture_output=True,
        text=True,
        cwd=work_dir,
    )
    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()
        print(output[:2000], file=sys.stderr)


def main():
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input", {})
    cwd = data.get("cwd")
    check(tool_input, cwd=cwd)


if __name__ == "__main__":
    main()
