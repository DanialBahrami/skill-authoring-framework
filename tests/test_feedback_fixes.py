"""Tests for routing against the full catalog, truncated answers, installed skills,
supersedes, quoted %run, check-names and the Genie Code checklist."""

import json
from pathlib import Path

from skillkit import lint
from skillkit.cli import main
from skillkit.evals import run_evals
from skillkit.model import load_installed, load_skill, load_skills, load_standard

from test_evals import FakeLLM
from test_lint import _add_skill


def _near_miss_to_sibling(repo: Path) -> None:
    """dp-prepare-pr gets a near miss that belongs to a draft sibling skill."""
    evals = repo / "skills" / "dp-prepare-pr" / "evals" / "evals.json"
    data = json.loads(evals.read_text())
    data["evals"].append({"id": "pr-nm-02", "type": "near_miss", "prompt": "Review my notebook style",
                          "expect_skill": "dp-review-notebook"})
    evals.write_text(json.dumps(data))
    _add_skill(repo, "dp-review-notebook", status="draft",
               desc="Reviews a notebook for code style. Use when the user asks to review notebook style.")


class SiblingLLM(FakeLLM):
    def complete(self, endpoint, system, user, max_tokens):
        if "select skills" in system and "notebook style" in user.split("User request:")[-1]:
            catalog = user.split("User request:")[0]
            return '{"skill": "dp-review-notebook"}' if "dp-review-notebook" in catalog else '{"skill": "none"}'
        return super().complete(endpoint, system, user, max_tokens)


def test_routing_includes_draft_siblings_but_scores_only_targets(repo: Path):
    _near_miss_to_sibling(repo)
    std, skills = load_standard(repo), load_skills(repo)
    targets = [s for s in skills if s.name == "dp-prepare-pr"]
    results, verdicts, _ = run_evals(repo, std, skills, targets, SiblingLLM(), mode="routing", log=lambda *_: None)
    assert {r.case_id: r for r in results}["pr-nm-02"].routing_pass
    assert [v.skill for v in verdicts] == ["dp-prepare-pr"]


def test_installed_skills_join_routing_unless_superseded(repo: Path, tmp_path: Path):
    installed = tmp_path / "installed"
    (installed / "old-pr-helper").mkdir(parents=True)
    (installed / "old-pr-helper" / "SKILL.md").write_text("---\nname: old-pr-helper\ndescription: Opens PRs.\n---\n")
    (installed / "dp-prepare-pr").mkdir()
    (installed / "dp-prepare-pr" / "SKILL.md").write_text("---\nname: dp-prepare-pr\ndescription: deployed copy\n---\n")
    skills = load_skills(repo)
    found = load_installed(installed, {s.name for s in skills})
    assert [i.name for i in found] == ["old-pr-helper"]

    seen = []

    class Capture(FakeLLM):
        def complete(self, endpoint, system, user, max_tokens):
            if "select skills" in system:
                seen.append(user)
            return super().complete(endpoint, system, user, max_tokens)

    std = load_standard(repo)
    run_evals(repo, std, skills, skills, Capture(), mode="routing", installed=found, log=lambda *_: None)
    assert "old-pr-helper" in seen[0]
    meta = repo / "skills" / "dp-prepare-pr" / "skill.yaml"
    meta.write_text(meta.read_text() + "supersedes: [old-pr-helper]\n")
    seen.clear()
    run_evals(repo, std, load_skills(repo), load_skills(repo), Capture(), mode="routing", installed=found,
              log=lambda *_: None)
    assert "old-pr-helper" not in seen[0]


class CutOff(FakeLLM):
    """Answers with the skill are cut off at the limit unless the limit is at least 4000."""
    last_truncated = False

    def complete(self, endpoint, system, user, max_tokens):
        if "Skill loaded" in system:
            self.last_truncated = max_tokens < 4000
            return "I will write the" if self.last_truncated else "I will write the impact analysis on the hotfix branch."
        self.last_truncated = False
        return super().complete(endpoint, system, user, max_tokens)


def test_truncated_answers_are_inconclusive_not_failing(repo: Path):
    std, skills = load_standard(repo), load_skills(repo)
    results, verdicts, _ = run_evals(repo, std, skills, skills, CutOff(), log=lambda *_: None)
    r = {x.case_id: x for x in results}["pr-01"]
    assert r.with_skill_pass is None and r.with_skill_truncated == 1
    assert verdicts[0].verdict == "INCONCLUSIVE"


def test_per_skill_max_tokens(repo: Path):
    meta = repo / "skills" / "dp-prepare-pr" / "skill.yaml"
    meta.write_text(meta.read_text() + "eval:\n  max_tokens: 4000\n")
    std, skills = load_standard(repo), load_skills(repo)
    results, verdicts, _ = run_evals(repo, std, skills, skills, CutOff(), log=lambda *_: None)
    assert {x.case_id: x for x in results}["pr-01"].max_tokens == 4000
    assert verdicts[0].verdict == "ADDS VALUE"


def test_quoted_run_is_not_a_path_warning(repo: Path):
    folder = repo / "skills" / "dp-prepare-pr"
    md = folder / "SKILL.md"
    md.write_text(md.read_text().replace("2. Fill", '2. Run `%run "../Common/setup"` and `%run \'../x\'`. Fill'))
    warns = [f for f in lint.lint_skill(load_skill(folder), load_standard(repo)) if f.code == "SK020"]
    assert not any("path outside" in f.message for f in warns)


def test_planned_catalog_warns_before_drafts_are_activated(repo: Path):
    std = load_standard(repo)
    std.raw["limits"]["catalog_max_tokens"] = 120
    for i in range(3):
        _add_skill(repo, f"dp-draft-number-{'abc'[i]}", status="draft")
    msgs = [f.message for f in lint.lint_catalog(load_skills(repo), std) if f.code == "CT001"]
    assert any("active and draft" in m for m in msgs)


def test_supersedes_checks(repo: Path):
    _add_skill(repo, "dp-old-pr-thing")
    meta = repo / "skills" / "dp-prepare-pr" / "skill.yaml"
    meta.write_text(meta.read_text() + "supersedes: [dp-old-pr-thing, dp-prepare-pr]\n")
    std, skills = load_standard(repo), load_skills(repo)
    by_name = {s.name: s for s in skills}
    assert "SK022" in {f.code for f in lint.lint_skill(by_name["dp-prepare-pr"], std) if f.severity == "error"}
    assert any(f.code == "SK022" and "still active" in f.message for f in lint.lint_catalog(skills, std))


def test_catalog_command_with_installed(repo: Path, tmp_path: Path, capsys):
    installed = tmp_path / "installed" / "legacy-open-pr"
    installed.mkdir(parents=True)
    (installed / "SKILL.md").write_text(
        "---\nname: legacy-open-pr\ndescription: \"Prepares a pull request for the data-platform repo: branch, title code, "
        "description, impact analysis. Use when the user asks to open, create or describe a PR.\"\n---\n")
    assert main(["--root", str(repo), "catalog", "--installed", str(tmp_path / "installed")]) == 0
    out = capsys.readouterr().out
    assert "legacy-open-pr" in out and "planned + installed" in out and "overlap with installed" in out


def test_check_names(repo: Path, tmp_path: Path, capsys):
    src = tmp_path / "source"
    (src / "Databricks" / "Common").mkdir(parents=True)
    (src / "Databricks" / "Common" / "release.yml").write_text("steps: merge_table_silver\n")
    md = repo / "skills" / "dp-prepare-pr" / "SKILL.md"
    md.write_text(md.read_text().replace(
        "2. Fill", "2. Use `merge_table_silver(df, keys)`, `Common/release.yml`, `invented_helper`, "
        "`<table>`, `Development-Release-YYYY.MM.DD`, `git checkout -b x` and `references/title-codes.md`. Fill"))
    assert main(["--root", str(repo), "check-names", "--repo", str(src)]) == 0
    out = capsys.readouterr().out
    assert "`invented_helper`" in out
    for ok in ("merge_table_silver", "release.yml", "<table>", "YYYY", "git checkout", "title-codes"):
        assert ok not in out.split("\n\n")[0], ok
    assert main(["--root", str(repo), "check-names", "--repo", str(src), "--strict"]) == 1


def test_genie_checklist(repo: Path, tmp_path: Path):
    out = tmp_path / "genie-check.md"
    assert main(["--root", str(repo), "genie-checklist", "--out", str(out)]) == 0
    text = out.read_text()
    assert "## dp-prepare-pr" in text and "Write the PR description" in text
    assert "Matches `impact`" in text and "Uses the hotfix branch" in text
    assert "pr-nm-01" not in text
