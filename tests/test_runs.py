"""Run folders: `init` starts a run from the templates and shows what earlier runs left;
`check` checks the run's skills and writes the results into its report.md."""

import json
from pathlib import Path

import pytest

from skillkit import evals
from skillkit.cli import main
from skillkit.runs import BEGIN, END, backlog, decisions, demote, read_tables, run_skills

from test_evals import FakeLLM


def _init(repo: Path, scope: str = "pr process") -> Path:
    assert main(["--root", str(repo), "init", "--scope", scope]) == 0
    runs = sorted((repo / "authoring" / "runs").iterdir())
    return next(p for p in runs if p.name.endswith("pr-process"))


def _plan(run: Path, this_run: str = "updated: pr-01") -> None:
    path = run / "decisions.md"
    path.write_text(path.read_text().replace(
        "| Skill | Task | Owner | Uses | This run | Why it is a skill |\n| --- | --- | --- | --- | --- | --- |\n",
        "| Skill | Task | Owner | Uses | This run | Why it is a skill |\n| --- | --- | --- | --- | --- | --- |\n"
        f"| `dp-prepare-pr` | Prepare a PR | data-platform | | {this_run} | People ask for it |\n"))


@pytest.fixture
def fake_llm(monkeypatch):
    monkeypatch.setattr(evals, "ServingLLM", lambda profile=None: FakeLLM())


def test_init_creates_the_run_files_and_keeps_them(repo: Path, capsys):
    run = _init(repo)
    assert sorted(p.name for p in run.iterdir()) == ["decisions.md", "inventory.md", "proposals.md", "report.md"]
    assert "# Report: pr process" in (run / "report.md").read_text()
    assert "dp-prepare-pr" in capsys.readouterr().out
    (run / "inventory.md").write_text("my notes")
    _init(repo)
    assert (run / "inventory.md").read_text() == "my notes"
    assert "existing files kept" in capsys.readouterr().out


def test_init_shows_decisions_and_backlog_of_earlier_runs(repo: Path, capsys):
    earlier = repo / "authoring" / "runs" / "2026-10-01-silver"
    earlier.mkdir(parents=True)
    (earlier / "decisions.md").write_text(
        "## Conflicts\n\n| # | Topic | Approach A (source) | Approach B (source) | Breaks the contract? | Decision | Why "
        "| Skills affected | Reviewed by |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| 1 | PII tag name | `pii` | `pii_level` | Yes | Align to A | Masking reads pii | dp-tag-pii | Ana |\n"
        "| 2 | Merge helper | platform | team | No | Variant | Both used | dp-create-silver | |\n")
    (earlier / "report.md").write_text(
        "## Backlog\n\n| Task | Where | Why not now | Needed first | Owner |\n| --- | --- | --- | --- | --- |\n"
        "| Backfill a table | jobs/ | names only | read jobs/ | data-platform |\n")
    _init(repo)
    out = capsys.readouterr().out
    assert "#1 PII tag name: Align to A (reviewed by Ana)" in out
    assert "#2 Merge helper: Variant (not reviewed yet)" in out
    assert "Backfill a table: names only" in out and "review: end" in out


def test_runs_made_before_decisions_md_are_still_read(tmp_path: Path):
    old = tmp_path / "2026-09-01-gold"
    old.mkdir()
    (old / "conflicts.md").write_text("| # | Task or topic | Decision | Decided by |\n| --- | --- | --- | --- |\n"
                                      "| 1 | Tag name | Align to A | Ana |\n")
    (old / "backlog.md").write_text("| Task (verb + object) | Why not generated |\n| --- | --- |\n"
                                    "| <task> | <why> |\n| Backfill | open conflict |\n")
    assert decisions(old)[0]["decision"] == "Align to A"
    assert [r["task (verb + object)"] for r in backlog(old)] == ["Backfill"]   # placeholder rows are skipped


def test_run_skills_are_the_changed_rows_of_the_family(repo: Path):
    run = _init(repo)
    assert run_skills(run) == []
    _plan(run, "unchanged")
    assert run_skills(run) == []
    _plan(run)
    assert run_skills(run) == ["dp-prepare-pr"]


def test_check_writes_the_report_and_keeps_the_agents_text(repo: Path, tmp_path: Path, fake_llm, capsys):
    run = _init(repo)
    _plan(run)
    report = run / "report.md"
    report.write_text(report.read_text().replace("<Two or three lines", "Made dp-prepare-pr better. <Two or three lines"))
    src = tmp_path / "source"
    src.mkdir()
    assert main(["--root", str(repo), "check", str(run), "--repo", str(src), "--runs", "1"]) == 0
    text = report.read_text()
    assert "Made dp-prepare-pr better." in text and "## For you to review" in text
    assert "### Lint" in text and "#### Skill eval report" not in text and "### Skill eval report" in text
    assert "**ADDS VALUE**" in text and "### Skill map: " in text and "updated: pr-01" in text
    assert "### Agent check" in text and "Write the PR description" in text
    assert json.loads((run / "eval.json").read_text())["verdicts"][0]["verdict"] == "ADDS VALUE"
    assert "nothing to do" in capsys.readouterr().out

    assert main(["--root", str(repo), "check", str(run), "--no-eval"]) == 0
    text = report.read_text()
    assert text.count(BEGIN) == 1 and text.count(END) == 1 and "Not run (`--no-eval`)" in text


def test_check_lists_what_to_do(repo: Path, monkeypatch, capsys):
    run = _init(repo)
    _plan(run)

    class AlwaysRight(FakeLLM):
        def complete(self, endpoint, system, user, max_tokens):
            if "select skills" in system or "grade an answer" in system:
                return super().complete(endpoint, system, user, max_tokens)
            return "impact analysis on the hotfix branch"

    monkeypatch.setattr(evals, "ServingLLM", lambda profile=None: AlwaysRight())
    assert main(["--root", str(repo), "check", str(run), "--runs", "1"]) == 1
    out = capsys.readouterr().out
    assert "dp-prepare-pr has NO EFFECT" in out and "Not checked: give `--repo" in (run / "report.md").read_text()


def test_check_skips_evals_on_lint_errors_and_reports_endpoint_errors(repo: Path, monkeypatch, capsys):
    run = _init(repo)
    _plan(run)
    md = repo / "skills" / "dp-prepare-pr" / "SKILL.md"
    original = md.read_text()
    md.write_text(original.replace("## Verify", "## Before you start\n\nx\n\n## Verify"))
    assert main(["--root", str(repo), "check", str(run)]) == 1
    assert "Not run: fix the lint errors first" in (run / "report.md").read_text()

    md.write_text(original)

    def broken(profile=None):
        raise RuntimeError("endpoint databricks-claude-sonnet-4-5 not found")

    monkeypatch.setattr(evals, "ServingLLM", broken)
    assert main(["--root", str(repo), "check", str(run)]) == 1
    assert "Did not run: endpoint databricks-claude-sonnet-4-5 not found" in (run / "report.md").read_text()
    assert "evals did not run" in capsys.readouterr().out


def test_check_needs_a_run_folder(repo: Path, capsys):
    assert main(["--root", str(repo), "check", str(repo / "authoring" / "runs" / "nope")]) == 2
    assert "init --scope" in capsys.readouterr().err


def test_read_tables_and_demote():
    path_text = "| A | B |\n| --- | --- |\n| `x` | y |\n\ntext\n\n| C |\n| --- |\n| z |\n"
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.md"
        p.write_text(path_text)
        assert read_tables(p) == [(["a", "b"], [{"a": "`x`", "b": "y"}]), (["c"], [{"c": "z"}])]
    assert demote("# T\n```\n# not a heading\n```\n## S", 2) == "### T\n```\n# not a heading\n```\n#### S"
