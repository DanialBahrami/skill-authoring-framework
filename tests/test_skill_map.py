"""The skill map: table and diagram from the actual skills, journeys and eval verdicts."""

import json
from pathlib import Path

from skillkit.cli import main

from test_lint import _add_skill


def _family(repo: Path) -> None:
    _add_skill(repo, "dp-tag-pii-columns", desc="Tags PII columns in a table. Use when the user asks to tag "
               "or classify personal data columns.")
    _add_skill(repo, "dp-onboard-new-source", " Then follow dp-tag-pii-columns and dp-prepare-pr.",
               uses=["dp-tag-pii-columns", "dp-prepare-pr"], status="draft",
               desc="Onboards a new source system end to end. Use when the user asks to onboard a source.")
    _add_skill(repo, "dp-review-notebook", desc="Reviews a notebook for style. Use when the user asks for a review.")
    (repo / "evals").mkdir(exist_ok=True)
    (repo / "evals" / "journeys.json").write_text(json.dumps({"journeys": [
        {"id": "onboard-to-pr", "prompt": "Onboard CRM and open the PR",
         "skills": ["dp-onboard-new-source", "dp-prepare-pr"], "must_include": ["impact"]}]}))


def test_map_from_files(repo: Path, tmp_path: Path):
    _family(repo)
    results = tmp_path / "eval.json"
    results.write_text(json.dumps({"verdicts": [{"skill": "dp-prepare-pr", "verdict": "ADDS VALUE"}], "cases": []}))
    out = tmp_path / "skill-map.md"
    assert main(["--root", str(repo), "catalog", "--map", "--eval-json", str(results), "--scope", "silver",
                 "--out", str(out)]) == 0
    md = out.read_text()
    assert md.startswith("# Skill map: silver")
    row = next(line for line in md.splitlines() if line.startswith("| `dp-onboard-new-source`"))
    assert "`dp-prepare-pr`, `dp-tag-pii-columns`" in row or "`dp-tag-pii-columns`, `dp-prepare-pr`" in row
    assert "| draft |" in row and "not evaluated" in row
    pr_row = next(line for line in md.splitlines() if line.startswith("| `dp-prepare-pr`"))
    assert "`dp-onboard-new-source`" in pr_row and "ADDS VALUE" in pr_row
    assert "```mermaid" in md and "-.->|onboard-to-pr|" in md and md.count(" --> ") == 2
    assert '(["dp-onboard-new-source"])' in md                      # drafts are rounded
    assert "Standalone skills: `dp-review-notebook`" in md


def test_map_notes_skills_that_use_others_without_a_journey(repo: Path, capsys):
    _family(repo)
    (repo / "evals" / "journeys.json").write_text(json.dumps({"journeys": [
        {"id": "pr-only", "prompt": "p", "skills": ["dp-prepare-pr", "dp-review-notebook"], "must_include": ["x"]}]}))
    assert main(["--root", str(repo), "catalog", "--map"]) == 0
    assert "appear in no journey: `dp-onboard-new-source`" in capsys.readouterr().out


def test_generated_map_keeps_this_run_from_the_planned_map(repo: Path, tmp_path: Path):
    _family(repo)
    out = tmp_path / "skill-map.md"
    out.write_text("# Skill map: gold (planned)\n\n"
                   "| Skill | Task (from inventory.md) | Owner | Uses | Used by | Team variants | This run |\n"
                   "| --- | --- | --- | --- | --- | --- | --- |\n"
                   "| `<prefix>-<verb>-<object>` | <task> | <team> | | | | new |\n"
                   "| `dp-onboard-new-source` | Onboard a source | data-platform | | | | new |\n"
                   "| `dp-prepare-pr` | Prepare a PR | data-platform | | | | updated: gold release step |\n")
    assert main(["--root", str(repo), "catalog", "--map", "--out", str(out)]) == 0
    md = out.read_text()
    rows = {line.split("|")[1].strip(): line for line in md.splitlines() if line.startswith("| `")}
    assert rows["`dp-onboard-new-source`"].endswith("| new |")
    assert rows["`dp-prepare-pr`"].endswith("| updated: gold release step |")
    assert rows["`dp-review-notebook`"].endswith("| unchanged |")
    assert "This run |" in md and "<prefix>" not in md
