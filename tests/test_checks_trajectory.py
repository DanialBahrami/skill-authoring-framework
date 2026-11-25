"""Per-step checks, the Recovery section and trajectory assertions in evals."""

import json
from pathlib import Path

from skillkit import lint
from skillkit.checklist import checklist_markdown
from skillkit.evals import check_order, score_answer
from skillkit.model import load_skill, load_skills, load_standard


def _codes(repo: Path, severity: str = "error") -> set[str]:
    skill = load_skill(repo / "skills" / "dp-prepare-pr")
    return {f.code for f in lint.lint_skill(skill, load_standard(repo)) if f.severity == severity}


def _edit_md(repo: Path, old: str, new: str) -> None:
    md = repo / "skills" / "dp-prepare-pr" / "SKILL.md"
    text = md.read_text()
    assert old in text
    md.write_text(text.replace(old, new))


def _set_cases(repo: Path, cases: list[dict]) -> None:
    (repo / "skills" / "dp-prepare-pr" / "evals" / "evals.json").write_text(
        json.dumps({"skill_name": "dp-prepare-pr", "evals": cases}))


BASE_CASES = [
    {"id": "t1", "type": "trigger", "prompt": "Open a PR", "must_include": ["impact"]},
    {"id": "t2", "type": "trigger", "prompt": "Open a hotfix PR", "assertions": ["Uses the hotfix branch"]},
    {"id": "nm", "type": "near_miss", "prompt": "Review this notebook"},
]


# Recovery and Check: lines

def test_recovery_section_is_required(repo: Path):
    md = repo / "skills" / "dp-prepare-pr" / "SKILL.md"
    text = md.read_text()
    start, end = text.index("## Recovery"), text.index("## References")
    md.write_text(text[:start] + text[end:])
    findings = lint.lint_skill(load_skill(md.parent), load_standard(repo))
    assert any(f.code == "SK009" and "Recovery" in f.message for f in findings)


def test_recovery_needs_a_table(repo: Path):
    md = repo / "skills" / "dp-prepare-pr" / "SKILL.md"
    text = md.read_text()
    start, end = text.index("## Recovery"), text.index("## References")
    md.write_text(text[:start] + "## Recovery\n\nIf something fails, look at the error.\n\n" + text[end:])
    assert "SK025" in _codes(repo)


def test_recovery_fix_must_not_only_retry(repo: Path):
    _edit_md(repo, "| Branch from yesterday's release branch and say so in the description |", "| Try again. |")
    assert "SK025" in _codes(repo)


def test_step_that_runs_something_needs_a_check(repo: Path):
    _edit_md(repo, "2. Fill the description from the template.",
             "2. Validate with `databricks bundle validate -t dev`.")
    assert "SK026" in _codes(repo, "warning")
    _edit_md(repo, "`databricks bundle validate -t dev`.",
             "`databricks bundle validate -t dev`.\n   Check: the command exits 0.")
    assert "SK026" not in _codes(repo, "warning")


def test_step_with_code_block_needs_a_check(repo: Path):
    _edit_md(repo, "2. Fill the description from the template.",
             "2. Create the table:\n\n   ```sql\n   CREATE TABLE ${catalog}.bronze.x (id INT)\n   ```")
    assert "SK026" in _codes(repo, "warning")


def test_plain_steps_need_no_check(repo: Path):
    assert "SK026" not in _codes(repo, "warning")


# Trajectory: lint

def test_no_trajectory_warns(repo: Path):
    _set_cases(repo, BASE_CASES)
    assert "SK027" in _codes(repo, "warning")


def test_trajectory_shape_is_checked(repo: Path):
    cases = [dict(c) for c in BASE_CASES]
    cases[0]["trajectory"] = {"order": ["(unclosed", "deploy"], "steps": []}
    cases[2]["trajectory"] = {"avoid": ["reads the repo"]}
    _set_cases(repo, cases)
    messages = [f.message for f in lint.lint_skill(load_skill(repo / "skills" / "dp-prepare-pr"), load_standard(repo))
                if f.code == "SK015"]
    assert any("bad regex in trajectory order" in m for m in messages)
    assert any("keys not allowed: steps" in m for m in messages)
    assert any("near_miss" in m for m in messages)


def test_trajectory_alone_satisfies_a_trigger_case(repo: Path):
    cases = [dict(c) for c in BASE_CASES]
    cases[0] = {"id": "t1", "type": "trigger", "prompt": "Open a PR", "trajectory": {"avoid": ["reads the repo"]}}
    _set_cases(repo, cases)
    assert "SK015" not in _codes(repo) and "SK027" not in _codes(repo, "warning")


def test_journey_trajectory_is_checked(repo: Path):
    (repo / "evals").mkdir(exist_ok=True)
    (repo / "evals" / "journeys.json").write_text(json.dumps({"journeys": [
        {"id": "j1", "prompt": "Do it all", "skills": ["dp-prepare-pr", "dp-prepare-pr"],
         "trajectory": {"order": ["(bad"]}}]}))
    findings = lint.lint_journeys(repo, load_skills(repo))
    assert any(f.code == "JR001" and "bad regex in trajectory order" in f.message for f in findings)


# Trajectory: scoring

def test_check_order():
    answer = "First run bundle validate. Then bundle deploy -t dev."
    assert check_order(answer, ["validate", "deploy"]) is None
    assert "comes before" in check_order("deploy now, validate later", ["validate", "deploy"])
    assert "missing" in check_order(answer, ["validate", "grant"])
    # An early mention does not count against the order when the steps follow later in order.
    assert check_order("I will validate and deploy. 1. validate 2. deploy", ["validate", "deploy"]) is None


def test_order_failure_fails_the_answer():
    case = {"prompt": "p", "trajectory": {"order": ["validate", "deploy"]}}
    ok, notes = score_answer("deploy, then validate", case, None, "j", 100)
    assert not ok and notes[0].startswith("trajectory:")


def test_avoid_items_go_to_the_judge():
    seen = {}

    class Judge:
        def complete(self, endpoint, system, user, max_tokens):
            seen["system"], seen["user"] = system, user
            rubric = [line[2:] for line in user.split("Rubric:\n")[-1].splitlines() if line.startswith("- ")]
            return json.dumps({"items": [{"item": r, "pass": not r.startswith("Avoids:"), "reason": "read files"}
                                         for r in rubric]})

    case = {"prompt": "p", "rubric": ["Uses the template"], "trajectory": {"avoid": ["reads repository files"]}}
    ok, notes = score_answer("I read the repo, then use the template", case, Judge(), "j", 100)
    assert "Avoids: reads repository files" in seen["user"] and "Avoids:" in seen["system"]
    assert not ok and notes == ["trajectory failed: Avoids: reads repository files (read files)"]


def test_eval_run_fails_a_case_on_trajectory(repo: Path):
    from skillkit.evals import run_evals
    from test_evals import FakeLLM

    class WrongOrder(FakeLLM):
        def complete(self, endpoint, system, user, max_tokens):
            if "Skill loaded" in system and "grade an answer" not in system and "select skills" not in system:
                return "Use the hotfix branch, then write the impact analysis."
            return super().complete(endpoint, system, user, max_tokens)

    std = load_standard(repo)
    skills = load_skills(repo)
    results, verdicts, _ = run_evals(repo, std, skills, skills, WrongOrder(), log=lambda *_: None)
    r = {x.case_id: x for x in results}["pr-02"]
    assert r.with_skill_pass is False and any("trajectory" in n for n in r.with_skill_notes)
    assert verdicts[0].verdict == "FAILING"


def test_checklist_lists_trajectory(repo: Path):
    cases = [dict(c) for c in BASE_CASES]
    cases[0]["trajectory"] = {"order": ["validate", "deploy"], "avoid": ["reads repository files"]}
    _set_cases(repo, cases)
    text = checklist_markdown(load_skills(repo))
    assert "Did these in this order: `validate` → `deploy`" in text and "Did not: reads repository files" in text


# The consumer works from the skill alone

def test_pointing_at_the_source_warns(repo: Path):
    _edit_md(repo, "2. Fill the description from the template.",
             "2. Look at the other notebooks in the Silver folder and read the README for the conventions.")
    findings = [f for f in lint.lint_skill(load_skill(repo / "skills" / "dp-prepare-pr"), load_standard(repo))
                if f.code == "SK028"]
    assert findings and all(f.severity == "warning" for f in findings)
    assert "look at the other notebooks" in findings[0].message.lower()


def test_writing_or_calling_repo_paths_does_not_warn(repo: Path):
    _edit_md(repo, "2. Fill the description from the template.",
             "2. Write the notebook to `Databricks/Silver/<system>/` and run `%run ../Common/silver_lib`; check the "
             "result with `DESCRIBE TABLE`. Open the PR with the template below.\n\n   ```text\n   see the code\n   ```")
    assert "SK028" not in _codes(repo, "warning")


def test_reference_files_are_checked_too(repo: Path):
    ref = repo / "skills" / "dp-prepare-pr" / "references" / "title-codes.md"
    ref.write_text("# Title codes\n\nFor the full list, consult the wiki.\n")
    assert "SK028" in _codes(repo, "warning")
