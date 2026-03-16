from hooks.require_local_config import check


def test_config_present_allowed(tmp_path):
    config = tmp_path / "CLAUDE.local.md"
    config.write_text("taskgraph_repo: /some/path\n")
    assert check(local_config_path=config) == (True, "")


def test_config_missing_blocked(tmp_path):
    missing = tmp_path / "CLAUDE.local.md"
    allowed, reason = check(local_config_path=missing)
    assert not allowed
    assert "CLAUDE.local.md" in reason
    assert "template" in reason.lower() or "install" in reason.lower()
