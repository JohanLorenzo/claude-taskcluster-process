from install import utils


def test_unified_diff_returns_diff_lines():
    diff = utils.unified_diff("old\n", "new\n", "a.txt", "b.txt")
    assert any("-old" in line for line in diff)
    assert any("+new" in line for line in diff)


def test_unified_diff_empty_when_identical():
    assert utils.unified_diff("same\n", "same\n", "a.txt", "b.txt") == []


def test_format_diff_colors_lines_when_color_enabled():
    diff = utils.unified_diff("old\n", "new\n", "a.txt", "b.txt")
    formatted = utils.format_diff(diff, color=True)
    assert f"{utils.RED}-old{utils.RESET}" in formatted
    assert f"{utils.GREEN}+new{utils.RESET}" in formatted
    assert f"{utils.CYAN}@@" in formatted
    assert f"{utils.BOLD}---" in formatted
    assert f"{utils.BOLD}+++" in formatted


def test_format_diff_plain_when_color_disabled():
    diff = utils.unified_diff("old\n", "new\n", "a.txt", "b.txt")
    assert utils.format_diff(diff, color=False) == "".join(diff)


def test_format_diff_defaults_to_plain_when_not_a_tty(monkeypatch):
    monkeypatch.setattr(utils.sys.stdout, "isatty", lambda: False)
    diff = utils.unified_diff("old\n", "new\n", "a.txt", "b.txt")
    assert utils.format_diff(diff) == "".join(diff)


def test_format_diff_defaults_to_plain_when_no_color_env_set(monkeypatch):
    monkeypatch.setattr(utils.sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("NO_COLOR", "1")
    diff = utils.unified_diff("old\n", "new\n", "a.txt", "b.txt")
    assert utils.format_diff(diff) == "".join(diff)
