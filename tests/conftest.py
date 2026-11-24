import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

GOOD_SKILL_MD = """---
name: dp-prepare-pr
description: >-
  Prepares a pull request for the data-platform repo: branch, title code, description,
  impact analysis and the files each change type requires. Use when the user asks
  to open, create or describe a PR, run an impact analysis, or ship a hotfix.
---

# Prepare a PR

Produces a PR description and checklist.

## Steps

1. Branch from the day's release branch.
2. Fill the description from the template.

## Verify

- The bundle validates.

## References

- [Title codes](references/title-codes.md): open when choosing the title code.
"""

GOOD_SKILL_YAML = """owner: data-platform
status: active
last_reviewed: 2026-11-01
sources:
  - repo: data-platform
    paths:
      - pull_request_template.md
      - CI_CD_Pipeline/**
  - confluence:
      page_id: "1001"
      title: Create a PR
      version: 7
"""

GOOD_EVALS = """{
  "skill_name": "dp-prepare-pr",
  "evals": [
    {"id": "pr-01", "type": "trigger", "prompt": "Write the PR description for my gold schema change",
     "must_include": ["impact"]},
    {"id": "pr-02", "type": "trigger", "prompt": "Open a hotfix PR", "assertions": ["Uses the hotfix branch"]},
    {"id": "pr-nm-01", "type": "near_miss", "prompt": "Review this notebook for code style"}
  ]
}
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal genie-context repo with one valid active skill."""
    shutil.copy(REPO / "standard.yaml", tmp_path / "standard.yaml")
    shutil.copytree(REPO / "context-authoring", tmp_path / "context-authoring")
    (tmp_path / "context").mkdir()
    (tmp_path / "context" / "workspace-instructions.md").write_text("# Workspace\n\n- Rule one.\n")
    skill = tmp_path / "skills" / "dp-prepare-pr"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text(GOOD_SKILL_MD)
    (skill / "references" / "title-codes.md").write_text("# Title codes\n\n- FEAT: feature\n")
    (skill / "skill.yaml").write_text(GOOD_SKILL_YAML)
    (skill / "evals").mkdir()
    (skill / "evals" / "evals.json").write_text(GOOD_EVALS)
    return tmp_path
