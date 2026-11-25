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


def test_added_columns_and_yaml_excerpts_and_bare_widgets():
    from skillkit.execute import SqlChecker, substitute

    def runner(st):
        if st.startswith("EXPLAIN") and "contract_end_date" in st:
            return True, ("Error occurred during query planning: [UNRESOLVED_COLUMN.WITH_SUGGESTION] A column with "
                          "name `contract_end_date` cannot be resolved.")
        return True, "== Physical Plan =="

    added = ("```sql\nALTER TABLE dev.s.t ADD COLUMNS (contract_end_date DATE COMMENT 'end');\n"
             "SELECT id, contract_end_date FROM dev.s.t\n```")
    report = SqlChecker(runner, {"catalog": "dev"}).check(added)
    assert not report.invalid and any("added by the answer" in c.detail for c in report.checks)
    invented = "```sql\nSELECT id, contract_end_date FROM dev.s.t\n```"
    assert SqlChecker(runner, {"catalog": "dev"}).check(invented).invalid
    assert not SqlChecker(runner, {"catalog": "dev"}).check(invented, new_columns=["contract_end_date"]).invalid

    excerpt = "```yaml\n   pause_status:\n    default: PAUSED\n\ntargets:\n  prod: {}\n```"
    checks = SqlChecker(runner).check(excerpt).checks
    assert checks[0].status == "skipped" and "excerpt" in checks[0].detail
    assert substitute("SELECT * FROM $catalog.s.t WHERE x = '${catalog}'", {"catalog": "dev"}) == \
        "SELECT * FROM dev.s.t WHERE x = 'dev'"


def test_finish_reason_enum_and_unverifiable_assertions(repo: Path):
    import enum
    import types

    from skillkit.evals import ServingLLM

    class Reason(enum.Enum):
        LENGTH = "length"

    llm = ServingLLM.__new__(ServingLLM)
    resp = types.SimpleNamespace(usage=None, choices=[types.SimpleNamespace(
        finish_reason=Reason.LENGTH, message=types.SimpleNamespace(content="partial"))])
    llm.w = types.SimpleNamespace(serving_endpoints=types.SimpleNamespace(query=lambda **kw: resp))
    llm.last_tokens, llm.last_truncated = None, False
    assert llm.complete("ep", "sys", "user", 10) == "partial" and llm.last_truncated

    evals = repo / "skills" / "dp-prepare-pr" / "evals" / "evals.json"
    data = json.loads(evals.read_text())
    data["evals"][0]["assertions"] = ["Names the latest release branch", "Lists the existing downstream tables",
                                      "Uses the real merge helper", "Gives the query that lists downstream tables"]
    evals.write_text(json.dumps(data))
    warned = [f.message for f in lint.lint_skill(load_skill(repo / "skills" / "dp-prepare-pr"), load_standard(repo))
              if f.code == "SK023"]
    assert len(warned) == 2 and "latest release branch" in warned[0]


def test_check_names_ignore_assets_and_globs(repo: Path, tmp_path: Path, capsys):
    src = tmp_path / "source"
    (src / "Deployment").mkdir(parents=True)
    (src / "Deployment" / "add_column.sql").write_text("-- x\n")
    folder = repo / "skills" / "dp-prepare-pr"
    (folder / "assets").mkdir(exist_ok=True)
    (folder / "assets" / "checklist.md").write_text("Use `asset_only_helper` and `Deployment/*.sql`.\n")
    md = folder / "SKILL.md"
    md.write_text(md.read_text().replace("2. Fill", "2. Ask the user for `ticket_key_from_user`. Fill"))
    main(["--root", str(repo), "check-names", "--repo", str(src)])
    out = capsys.readouterr().out
    assert "asset_only_helper" in out and "ticket_key_from_user" in out and "Deployment/*.sql" not in out
    main(["--root", str(repo), "check-names", "--repo", str(src), "--ignore", "ticket_key_from_user"])
    assert "ticket_key_from_user" not in capsys.readouterr().out.split("\n\n")[0]


def test_journey_regex_is_checked(repo: Path):
    (repo / "evals").mkdir(exist_ok=True)
    (repo / "evals" / "journeys.json").write_text(json.dumps({"journeys": [
        {"id": "j", "prompt": "p", "skills": ["dp-prepare-pr", "dp-prepare-pr"], "must_include": ["(unclosed"]}]}))
    assert any("bad regex" in f.message for f in lint.lint_journeys(repo, load_skills(repo)))


def test_tables_created_by_pyspark_are_not_invented():
    from skillkit.execute import SqlChecker

    def runner(st):
        if st.startswith("DESCRIBE TABLE") and "contracts_daily" in st:
            return False, "[TABLE_OR_VIEW_NOT_FOUND] The table or view `dev`.`gold`.`contracts_daily` cannot be found."
        return True, "== Physical Plan =="

    answer = ('```python\ndf.write.mode("overwrite").saveAsTable(f"{catalog}.gold.contracts_daily")\n'
              '@dlt.table(name="contracts_stream")\ndef s():\n    return spark.readStream.table("x")\n```\n'
              "```sql\nSELECT * FROM dev.gold.contracts_daily\n```")
    report = SqlChecker(runner, {"catalog": "dev"}).check(answer)
    assert not report.invalid


def test_check_names_skips_flags_urls_and_assignments_but_checks_calls(repo: Path, tmp_path: Path, capsys):
    src = tmp_path / "source"
    src.mkdir()
    (src / "lib.py").write_text("def real_helper(df, keys):\n    pass\n")
    md = repo / "skills" / "dp-prepare-pr" / "SKILL.md"
    md.write_text(md.read_text().replace("2. Fill", "2. Run with `--runs`, see `https://example.org/x`, set "
                                         "`load_type=full`, call `real_helper(df, keys)` and `fake_helper(df, keys)`. Fill"))
    main(["--root", str(repo), "check-names", "--repo", str(src)])
    report = capsys.readouterr().out.split("\n\n")[0]
    assert "fake_helper" in report
    for skipped in ("--runs", "example.org", "load_type", "real_helper"):
        assert skipped not in report, skipped


def test_path_spans_match_whole_segments(tmp_path: Path):
    from skillkit.names import _found, index_repo

    src = tmp_path / "source"
    (src / "Databricks" / "lib").mkdir(parents=True)
    (src / "Databricks" / "lib" / "merge.py").write_text("def merge_table_silver(): ...\n")
    (src / "Setup" / "Silver").mkdir(parents=True)
    (src / "Setup" / "Silver" / "setup.py").write_text("# notebook\n")
    (src / "README.md").write_text("Run %run ../Common/helpers first.\n")
    idx = [index_repo(src)]
    for ok in ("lib/merge.py", "Databricks/lib/merge.py", "Setup/Silver/setup", "Common/helpers"):
        assert _found(ok, idx), ok
    for bad in ("ib/merge.py", "other/merge.py", "Silver/setu", "mmon/helpers"):
        assert not _found(bad, idx), bad


def test_journey_without_skills_is_reported(repo: Path):
    from skillkit.evals import load_journeys, run_journeys

    class Easy(FakeLLM):
        def complete(self, endpoint, system, user, max_tokens):
            if "select skills" in system:
                return '{"skill": "dp-prepare-pr"}'
            return "impact"          # passes with and without skills

    (repo / "evals").mkdir(exist_ok=True)
    _add_skill(repo, "dp-follow-up", desc="Follows up a PR. Use when the user asks to follow up a pull request.")
    (repo / "evals" / "journeys.json").write_text(json.dumps({"journeys": [
        {"id": "easy", "prompt": "Prepare the PR then follow up", "skills": ["dp-prepare-pr", "dp-follow-up"],
         "must_include": ["impact"]}]}))
    results, warnings = run_journeys(repo, load_standard(repo), load_skills(repo), load_journeys(repo), Easy(),
                                     log=lambda *_: None)
    assert results[0].with_skill_pass and results[0].baseline_pass
    assert any("passes without any skill" in w for w in warnings)


def test_deprecated_target_stays_routable(repo: Path):
    meta = repo / "skills" / "dp-prepare-pr" / "skill.yaml"
    meta.write_text(meta.read_text().replace("status: active", "status: deprecated"))
    seen = []

    class Capture(FakeLLM):
        def complete(self, endpoint, system, user, max_tokens):
            if "select skills" in system:
                seen.append(user)
            return super().complete(endpoint, system, user, max_tokens)

    skills = load_skills(repo)
    run_evals(repo, load_standard(repo), skills, skills, Capture(), mode="routing", log=lambda *_: None)
    assert "dp-prepare-pr" in seen[0].split("User request:")[0]
