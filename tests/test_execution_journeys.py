"""Tests for the execution gate (EXPLAIN on generated SQL) and journeys across skills."""

import json
from pathlib import Path

from skillkit import lint
from skillkit.cli import main
from skillkit.evals import load_journeys, run_evals, run_journeys
from skillkit.execute import SqlChecker, classify, extract_sql, split_statements, substitute
from skillkit.model import load_skills, load_standard

from test_evals import FakeLLM
from test_lint import _add_skill

ANSWER = '''Steps:
```sql
-- set up
CREATE TABLE IF NOT EXISTS ${catalog}.silver.contracts (id BIGINT);
MERGE INTO ${catalog}.silver.contracts t USING ${catalog}.bronze.contracts s ON t.id = s.id
WHEN MATCHED THEN UPDATE SET *;
SELECT id, bogus FROM ${catalog}.bronze.contracts WHERE note = 'a;b';
GRANT SELECT ON TABLE x.y.z TO `readers`;
SELECT * FROM <table>;
```
```python
n = spark.sql(f"SELECT count(*) FROM {catalog}.bronze.contracts").first()[0]
```
'''


def plan(statement):
    assert statement.startswith("EXPLAIN ")
    if "bogus" in statement:
        return True, ("== Physical Plan ==\nError occurred during query planning: \n[UNRESOLVED_COLUMN.WITH_SUGGESTION] "
                      "A column with name `bogus` cannot be resolved.")
    if "forbidden" in statement:
        return False, "[INSUFFICIENT_PERMISSIONS] User does not have SELECT on table"
    return True, "== Physical Plan ==\n*(1) Scan"


def test_extract_and_split():
    stmts = extract_sql(ANSWER)
    assert len(stmts) == 6 and stmts[-1].startswith("SELECT count(*) FROM {catalog}")
    assert split_statements("SELECT ';' AS x; -- c\nSELECT 2 /* ; */") == ["SELECT ';' AS x", "SELECT 2"]


def test_substitute_forms():
    sql = "SELECT * FROM ${catalog}.a.b JOIN {{catalog}}.c.d JOIN IDENTIFIER(:tbl) WHERE x = {catalog}"
    out = substitute(sql, {"catalog": "dev", "tbl": "dev.e.f"})
    assert out == "SELECT * FROM dev.a.b JOIN dev.c.d JOIN dev.e.f WHERE x = dev"
    assert substitute("SELECT '12:30', a::int", {"a": "x"}) == "SELECT '12:30', a::int"


def test_checker_statuses():
    report = SqlChecker(plan, {"catalog": "dev"}).check(ANSWER)
    statuses = [(c.status, c.detail) for c in report.checks]
    assert statuses[0] == ("skipped", "DDL is not checked")
    assert statuses[1] == ("skipped", "uses a table created in this answer")
    assert statuses[2][0] == "invalid" and "UNRESOLVED_COLUMN" in statuses[2][1] and "bogus" in statuses[2][1]
    assert statuses[3] == ("skipped", "GRANT is not checked")
    assert statuses[4] == ("skipped", "unresolved placeholder")
    assert statuses[5] == ("ok", "")
    assert report.summary() == "1 ok, 1 invalid, 4 skipped" and len(report.notes()) == 1


def test_ctas_query_part_is_checked_and_permissions_are_inconclusive():
    answer = "```sql\nCREATE OR REPLACE TABLE dev.s.t AS SELECT * FROM dev.s.forbidden\n```"
    sent = []
    report = SqlChecker(lambda st: (sent.append(st), plan(st))[1]).check(answer)
    assert sent == ["EXPLAIN SELECT * FROM dev.s.forbidden"]
    assert report.checks[0].status == "inconclusive" and not report.invalid


def test_classify():
    assert classify("[TABLE_OR_VIEW_NOT_FOUND] The table `dev`.`s`.`t` cannot be found")[0] == "invalid"
    assert classify("[UNBOUND_SQL_PARAMETER] Found the unbound parameter: x") == ("inconclusive", "UNBOUND_SQL_PARAMETER")


class SqlLLM(FakeLLM):
    """With the skill the answer contains SQL with an invented column."""

    def complete(self, endpoint, system, user, max_tokens):
        if "Skill loaded" in system:
            return "I will write the impact analysis on the hotfix branch.\n```sql\nSELECT bogus FROM dev.a.b\n```"
        return super().complete(endpoint, system, user, max_tokens)


def test_execution_gate_fails_invented_column(repo: Path):
    std, skills = load_standard(repo), load_skills(repo)
    _, verdicts, _ = run_evals(repo, std, skills, skills, SqlLLM(), log=lambda *_: None)
    assert verdicts[0].verdict == "ADDS VALUE"          # without the gate it looks right
    results, verdicts, _ = run_evals(repo, std, skills, skills, SqlLLM(), checker=SqlChecker(plan),
                                     log=lambda *_: None)
    r = {x.case_id: x for x in results}["pr-01"]
    assert verdicts[0].verdict == "FAILING" and r.with_skill_sql == "1 invalid"
    assert any("UNRESOLVED_COLUMN" in n for n in r.with_skill_notes)


def _journey_repo(repo: Path) -> None:
    _add_skill(repo, "dp-onboard-new-source", " Then follow dp-prepare-pr.", uses=["dp-prepare-pr"],
               desc="Onboards a new source system end to end. Use when the user asks to onboard a source.")
    (repo / "evals").mkdir(exist_ok=True)
    (repo / "evals" / "journeys.json").write_text(json.dumps({"journeys": [
        {"id": "onboard-to-pr", "prompt": "Onboard the CRM source and open the PR",
         "skills": ["dp-onboard-new-source", "dp-prepare-pr"], "must_include": ["impact"]}]}))


class JourneyLLM(FakeLLM):
    def complete(self, endpoint, system, user, max_tokens):
        if "select skills" in system and "Onboard" in user.split("User request:")[-1]:
            return '{"skill": "dp-onboard-new-source"}'
        if "Skill loaded: dp-onboard-new-source" in system:
            return "Onboard, then the impact analysis for the PR."
        return super().complete(endpoint, system, user, max_tokens)


def test_journeys_run_and_lint(repo: Path):
    _journey_repo(repo)
    std, skills = load_standard(repo), load_skills(repo)
    assert not [f for f in lint.lint_journeys(repo, skills) if f.severity == "error"]
    results, warnings = run_journeys(repo, std, skills, load_journeys(repo), JourneyLLM(), log=lambda *_: None)
    assert results[0].routing_pass and results[0].with_skill_pass and not warnings

    (repo / "evals" / "journeys.json").write_text(json.dumps({"journeys": [
        {"id": "x", "prompt": "p", "skills": ["dp-prepare-pr"]}, {"id": "x", "prompt": "", "skills": ["nope", "dp-prepare-pr"]}]}))
    msgs = [f.message for f in lint.lint_journeys(repo, skills) if f.severity == "error"]
    assert any("at least two skills" in m for m in msgs) and any("unique id" in m for m in msgs)
    assert any("unknown skill 'nope'" in m for m in msgs) and any("prompt is missing" in m for m in msgs)


def test_checklist_has_journeys_read_files_and_no_file_open(repo: Path, tmp_path: Path):
    _journey_repo(repo)
    out = tmp_path / "check.md"
    assert main(["--root", str(repo), "genie-checklist", "--out", str(out)]) == 0
    text = out.read_text()
    assert "## Journeys" in text and "Used `dp-onboard-new-source` first" in text
    assert "Read repo files to answer?" in text and "**No file open**" in text


def test_execute_needs_a_warehouse(repo: Path, monkeypatch):
    import pytest

    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID", raising=False)
    with pytest.raises(SystemExit, match="warehouse"):
        main(["--root", str(repo), "eval", "--execute"])


def test_warehouse_runner_sends_only_explain(monkeypatch):
    import types

    import databricks.sdk
    from databricks.sdk.service.sql import StatementState

    from skillkit.execute import warehouse_runner

    sent = []

    def execute_statement(**kw):
        sent.append(kw)
        if "missing" in kw["statement"]:
            status = types.SimpleNamespace(state=StatementState.FAILED,
                                           error=types.SimpleNamespace(message="[TABLE_OR_VIEW_NOT_FOUND] `missing`"))
            return types.SimpleNamespace(status=status, result=None)
        return types.SimpleNamespace(status=types.SimpleNamespace(state=StatementState.SUCCEEDED, error=None),
                                     result=types.SimpleNamespace(data_array=[["== Physical Plan =="]]))

    class FakeClient:
        def __init__(self, *a, **k):
            self.statement_execution = types.SimpleNamespace(execute_statement=execute_statement)

    monkeypatch.setattr(databricks.sdk, "WorkspaceClient", FakeClient)
    run = warehouse_runner("wh-1")
    assert run("EXPLAIN SELECT 1") == (True, "== Physical Plan ==")
    assert run("EXPLAIN SELECT * FROM missing")[0] is False
    assert sent[0]["warehouse_id"] == "wh-1" and sent[0]["on_wait_timeout"].value == "CANCEL"
    import pytest
    with pytest.raises(ValueError):
        run("DROP TABLE x")
