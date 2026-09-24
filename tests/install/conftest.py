from unittest.mock import patch

import pytest

from install import skills


@pytest.fixture(autouse=True)
def isolate_external_skill_config(tmp_path):
    with (
        patch.object(
            skills,
            "EXTERNAL_SKILLS_CONFIG_FILE",
            tmp_path / "missing-external-skills.json",
        ),
        patch.object(skills, "LOCAL_CONFIG_FILE", tmp_path / "missing-CLAUDE.local.md"),
    ):
        yield
