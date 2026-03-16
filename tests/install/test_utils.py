from install import utils


def test_unified_diff_returns_diff_lines():
    diff = utils._unified_diff("old\n", "new\n", "a.txt", "b.txt")
    assert any("-old" in line for line in diff)
    assert any("+new" in line for line in diff)


def test_unified_diff_empty_when_identical():
    assert utils._unified_diff("same\n", "same\n", "a.txt", "b.txt") == []
