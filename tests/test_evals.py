import json
from pathlib import Path

from skillkit.evals import parse_json, report_markdown, run_evals, score_answer
from skillkit.model import load_skills, load_standard


class FakeLLM:
    """Routes PR prompts to the PR skill; answers mention 'impact' only when the skill is loaded."""

    def complete(self, endpoint, system, user, max_tokens):
        if "select skills" in system:
            if "PR" in user.split("User request:")[-1]:
                return '{"skill": "dp-prepare-pr"}'
            return '{"skill": "none"}'
        if "grade an answer" in system:
            rubric = [line[2:] for line in user.split("Rubric:\n")[-1].splitlines() if line.startswith("- ")]
            passed = "hotfix branch" in user.split("Answer:")[-1]
            return json.dumps({"items": [{"item": r, "pass": passed, "reason": ""} for r in rubric]})
        if "Skill loaded" in system:
            return "I will write the impact analysis and use the hotfix branch."
        return "I will open a PR."


def test_parse_json_tolerates_prose():
    assert parse_json('Sure:\n{"skill": "x"}\nthanks') == {"skill": "x"}
    assert parse_json("no json") == {}


def test_score_answer_regexes():
    case = {"prompt": "p", "must_include": ["impact"], "must_not_include": [r"\blakehouse_prd\b"]}
    assert score_answer("the impact is small", case, None, "j", 100) == (True, [])
    ok, notes = score_answer("deploy to lakehouse_prd", case, None, "j", 100)
    assert not ok and len(notes) == 2


def test_run_evals_with_baseline(repo: Path):
    std = load_standard(repo)
    skills = load_skills(repo)
    results, verdicts, warnings = run_evals(repo, std, skills, skills, FakeLLM(), log=lambda *_: None)
    by_id = {r.case_id: r for r in results}
    assert by_id["pr-01"].routing_pass and by_id["pr-02"].routing_pass
    assert by_id["pr-nm-01"].routing_pass  # near miss routed elsewhere
    assert by_id["pr-01"].with_skill_pass and not by_id["pr-01"].baseline_pass
    assert verdicts[0].verdict == "ADDS VALUE"
    md = report_markdown(results, verdicts, warnings, std)
    assert "ADDS VALUE" in md and "pr-nm-01" in md


def test_no_effect_verdict(repo: Path):
    class AlwaysRight(FakeLLM):
        def complete(self, endpoint, system, user, max_tokens):
            if "select skills" in system or "grade an answer" in system:
                return super().complete(endpoint, system, user, max_tokens)
            return "impact analysis on the hotfix branch"

    std = load_standard(repo)
    skills = load_skills(repo)
    _, verdicts, _ = run_evals(repo, std, skills, skills, AlwaysRight(), log=lambda *_: None)
    assert verdicts[0].verdict == "NO EFFECT"


def test_runs_use_trigger_rate(repo: Path):
    class Flaky(FakeLLM):
        n = 0

        def complete(self, endpoint, system, user, max_tokens):
            if "select skills" in system:
                Flaky.n += 1
                return '{"skill": "dp-prepare-pr"}' if Flaky.n % 3 else '{"skill": "none"}'
            return super().complete(endpoint, system, user, max_tokens)

    std = load_standard(repo)
    skills = load_skills(repo)
    results, _, _ = run_evals(repo, std, skills, skills, Flaky(), mode="routing", runs=3, log=lambda *_: None)
    r = {x.case_id: x for x in results}["pr-01"]
    assert abs(r.routing_rate - 2 / 3) < 1e-9 and r.routing_pass


def test_token_delta_reported(repo: Path):
    class Counting(FakeLLM):
        last_tokens = None

        def complete(self, endpoint, system, user, max_tokens):
            self.last_tokens = 300 if "Skill loaded" in system else 100
            return super().complete(endpoint, system, user, max_tokens)

    std = load_standard(repo)
    skills = load_skills(repo)
    _, verdicts, _ = run_evals(repo, std, skills, skills, Counting(), log=lambda *_: None)
    assert verdicts[0].token_delta == "+200"


def test_context_evals(repo: Path, tmp_path: Path):
    from skillkit.evals import run_context_evals

    repos = tmp_path / "repos" / "data-platform"
    repos.mkdir(parents=True)
    (repos / "AGENTS.md").write_text("Technical columns: _load_date, _is_active.")
    cases = tmp_path / "data-platform.json"
    cases.write_text('{"name": "data-platform AGENTS.md", "evals": [{"id": "c1", "prompt": "Which technical columns?", '
                     '"agents": ["data-platform/AGENTS.md"], "must_include": ["_load_date"]}]}')

    class Echo:
        last_tokens = None

        def complete(self, endpoint, system, user, max_tokens):
            return "_load_date" if "_load_date" in system else "no idea"

    results, summary, _ = run_context_evals(repo, load_standard(repo), cases, Echo(), repos_root=tmp_path / "repos")
    assert summary.verdict == "ADDS VALUE" and results[0].with_skill_pass and not results[0].baseline_pass
