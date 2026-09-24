import subprocess
from pathlib import Path

_SCRIPT = Path(__file__).parents[2] / "skills/git-origin/scripts/trace_origin.sh"


def _git(repo, *args):
    return subprocess.run(  # noqa: S603
        [  # noqa: S607
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _make_repo(tmp_path, added_line):
    repo = tmp_path
    _git(repo, "init")
    (repo / "mod.py").write_text("import os\n")
    _git(repo, "add", "mod.py")
    _git(repo, "commit", "-m", "initial")

    with (repo / "mod.py").open("a") as f:
        f.write(added_line + "\n")
    _git(repo, "add", "mod.py")
    _git(repo, "commit", "-m", "add line")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, sha


def _trace(repo, spec):
    return subprocess.run(  # noqa: S603
        ["bash", str(_SCRIPT), spec],  # noqa: S607
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_traces_line_with_regex_metacharacters(tmp_path):
    added_line = "def compute_new_settings("
    repo, sha = _make_repo(tmp_path, added_line)
    result = _trace(repo, "mod.py:2")
    assert result.returncode == 0
    assert "Found meaningful change" in result.stderr
    assert "Reached maximum trace depth" not in result.stderr
    assert sha in result.stdout


def test_traces_plain_line(tmp_path):
    added_line = "value = 1"
    repo, sha = _make_repo(tmp_path, added_line)
    result = _trace(repo, "mod.py:2")
    assert result.returncode == 0
    assert "Found meaningful change" in result.stderr
    assert "Reached maximum trace depth" not in result.stderr
    assert sha in result.stdout
