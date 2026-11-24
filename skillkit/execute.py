"""Execution gate: check the SQL in an eval answer against a real (development) warehouse.

Evals score what the model says it would do; a column that does not exist in the table
still looks right. This gate takes the SQL from the answer and asks a SQL warehouse to
plan it, so unknown tables, columns, functions and syntax errors show up.

Safety:
- Only `EXPLAIN <statement>` is ever sent. EXPLAIN plans a statement without running it.
- Only queries and DML (SELECT, WITH, INSERT, MERGE, UPDATE, DELETE) are explained; the
  query part of CREATE ... AS SELECT is explained on its own. Other DDL, GRANT, OPTIMIZE,
  Python and anything else is reported as not checked.
- Run it as an identity that can only read the development catalog, so even a mistake in
  this code cannot change data.

Covers SQL in ```sql blocks and in spark.sql("...") calls. PySpark DataFrame code is not
checked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

FENCE_RE = re.compile(r"```[ \t]*(\w*)[^\n]*\n(.*?)```", re.S)
SPARK_SQL_RE = re.compile(r"spark\.sql\(\s*[fr]?(\"\"\"|'''|\"|')(.*?)\1", re.S)
CREATE_RE = re.compile(r"^\s*create\s+(?:or\s+replace\s+)?(?:temporary\s+|temp\s+)?(?:table|view|materialized\s+view|"
                       r"streaming\s+table)\s+(?:if\s+not\s+exists\s+)?([`\w.${}\-]+)", re.I)
CTAS_RE = re.compile(r"\bas\s*\(?\s*((?:select|with)\b.*)$", re.I | re.S)
EXPLAINABLE = ("select", "with", "insert", "merge", "update", "delete", "values", "from", "table")
PLACEHOLDER_RE = re.compile(r"\$\{[^}]*\}|\{\{[^}]*\}\}|<[A-Za-z_][\w-]*>|\bTODO\b|\.\.\.")
ERROR_CODE_RE = re.compile(r"\[([A-Z][A-Z0-9_]+)(?:\.[A-Z0-9_]+)?\]")

INVALID_CODES = {
    "UNRESOLVED_COLUMN", "UNRESOLVED_FIELD", "TABLE_OR_VIEW_NOT_FOUND", "SCHEMA_NOT_FOUND",
    "CATALOG_NOT_FOUND", "UNRESOLVED_ROUTINE", "PARSE_SYNTAX_ERROR", "PARSE_EMPTY_STATEMENT",
    "DATATYPE_MISMATCH", "AMBIGUOUS_REFERENCE", "AMBIGUOUS_COLUMN_OR_FIELD", "WRONG_NUM_ARGS",
    "INVALID_IDENTIFIER", "MISSING_GROUP_BY", "MISSING_AGGREGATION", "NOT_A_PARTITIONED_TABLE",
    "INSERT_COLUMN_ARITY_MISMATCH", "INCOMPATIBLE_DATA_FOR_TABLE", "DELTA_MERGE_UNRESOLVED_EXPRESSION",
}


@dataclass
class SqlCheck:
    statement: str
    status: str            # ok | invalid | skipped | inconclusive
    detail: str = ""

    def excerpt(self, n: int = 70) -> str:
        flat = " ".join(self.statement.split())
        return flat if len(flat) <= n else flat[: n - 3] + "..."


@dataclass
class SqlReport:
    checks: list[SqlCheck] = field(default_factory=list)

    @property
    def invalid(self) -> list[SqlCheck]:
        return [c for c in self.checks if c.status == "invalid"]

    def summary(self) -> str:
        if not self.checks:
            return "no SQL"
        counts = {s: sum(c.status == s for c in self.checks) for s in ("ok", "invalid", "skipped", "inconclusive")}
        return ", ".join(f"{n} {s}" for s, n in counts.items() if n)

    def notes(self) -> list[str]:
        return [f"SQL {c.detail} in `{c.excerpt()}`" for c in self.invalid]


def extract_sql(answer: str) -> list[str]:
    """SQL statements from ```sql blocks and spark.sql(...) string literals, in order."""
    chunks: list[str] = []
    for lang, body in FENCE_RE.findall(answer):
        lang = lang.lower()
        if lang == "sql":
            chunks.append(body)
        elif lang in ("python", "py", "pyspark", ""):
            chunks += [m.group(2) for m in SPARK_SQL_RE.finditer(body)]
    statements = []
    for chunk in chunks:
        statements += [s for s in split_statements(chunk) if s.strip()]
    return statements


def split_statements(sql: str) -> list[str]:
    """Split on semicolons outside quotes and comments; comments are removed."""
    out, buf, i, quote = [], [], 0, ""
    while i < len(sql):
        ch, nxt = sql[i], sql[i + 1] if i + 1 < len(sql) else ""
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
        elif ch in ("'", '"', "`"):
            quote = ch
            buf.append(ch)
        elif ch == "-" and nxt == "-":
            while i < len(sql) and sql[i] != "\n":
                i += 1
            continue
        elif ch == "/" and nxt == "*":
            end = sql.find("*/", i + 2)
            i = len(sql) if end < 0 else end + 2
            continue
        elif ch == ";":
            out.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    out.append("".join(buf).strip())
    return [s for s in out if s]


def substitute(sql: str, variables: dict[str, str]) -> str:
    """Replace ${name}, {{name}}, {name} (f-strings) and :name / IDENTIFIER(:name) with known values."""
    for name, value in variables.items():
        n = re.escape(name)
        sql = re.sub(rf"\$\{{\s*{n}\s*\}}|\{{\{{\s*{n}\s*\}}\}}|(?<![{{\w])\{{\s*{n}\s*\}}(?!\}})", value, sql)
        sql = re.sub(rf"IDENTIFIER\(\s*:{n}\s*\)", value, sql, flags=re.I)
        sql = re.sub(rf"(?<![:\w]):{n}\b", value, sql)
    return sql


def _norm(name: str) -> str:
    return name.replace("`", "").strip().lower()


def classify(message: str) -> tuple[str, str]:
    """(status, detail) for an EXPLAIN error message."""
    codes = ERROR_CODE_RE.findall(message)
    code = codes[0] if codes else ""
    if code in INVALID_CODES or (not code and re.search(r"cannot resolve|not found|syntax error", message, re.I)):
        detail = code or "error"
        name = re.search(r"`[^`]+`(?:\.`[^`]+`)*", message)
        return "invalid", f"{detail} {name.group(0)}" if name else detail
    if code:
        return "inconclusive", code
    first_line = message.strip().splitlines()[0][:80] if message.strip() else "unknown error"
    return "inconclusive", first_line


Runner = Callable[[str], tuple[bool, str]]
"""Runs one EXPLAIN statement; returns (succeeded, text): the plan, or the error message."""


class SqlChecker:
    def __init__(self, runner: Runner, variables: dict[str, str] | None = None, signature: str = ""):
        self.runner = runner
        self.variables = dict(variables or {})
        self.signature = signature    # part of the eval cache key: warehouse and variables

    def check(self, answer: str) -> SqlReport:
        report = SqlReport()
        created: set[str] = set()
        for raw in extract_sql(answer):
            stmt = substitute(raw, self.variables)
            create = CREATE_RE.match(stmt)
            target = stmt
            if create:
                created.add(_norm(create.group(1)))
                ctas = CTAS_RE.search(stmt)
                if not ctas:
                    report.checks.append(SqlCheck(stmt, "skipped", "DDL is not checked"))
                    continue
                target = ctas.group(1).rstrip(") \n")
            first = re.match(r"\s*\(?\s*(\w+)", target)
            keyword = first.group(1).lower() if first else ""
            if keyword not in EXPLAINABLE:
                report.checks.append(SqlCheck(stmt, "skipped", f"{keyword.upper() or 'statement'} is not checked"))
                continue
            if PLACEHOLDER_RE.search(target):
                report.checks.append(SqlCheck(stmt, "skipped", "unresolved placeholder"))
                continue
            refs = {_norm(m) for m in re.findall(r"[`\w]+(?:\.[`\w]+){1,2}", target)}
            if refs & created or any(r.split(".", 1)[-1] in {c.split(".", 1)[-1] for c in created} for r in refs):
                report.checks.append(SqlCheck(stmt, "skipped", "uses a table created in this answer"))
                continue
            ok, text = self.runner("EXPLAIN " + target)
            # A failed analysis often comes back as a plan row, not as a failed statement.
            planning_error = re.search(r"Error occurred during query planning|AnalysisException", text) or \
                any(code in INVALID_CODES for code in ERROR_CODE_RE.findall(text))
            if ok and not planning_error:
                report.checks.append(SqlCheck(stmt, "ok"))
            else:
                status, detail = classify(text)
                report.checks.append(SqlCheck(stmt, status, detail))
        return report


def warehouse_runner(warehouse_id: str, profile: str | None = None, timeout: str = "30s") -> Runner:
    """A runner that sends EXPLAIN statements to a SQL warehouse through the Statement Execution API."""
    from databricks.sdk import WorkspaceClient

    from databricks.sdk.service.sql import ExecuteStatementRequestOnWaitTimeout

    w = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
    cancel = ExecuteStatementRequestOnWaitTimeout.CANCEL   # never leave a statement running

    def run(statement: str) -> tuple[bool, str]:
        if not statement.upper().startswith("EXPLAIN "):
            raise ValueError("only EXPLAIN statements may be sent")
        resp = w.statement_execution.execute_statement(statement=statement, warehouse_id=warehouse_id,
                                                       wait_timeout=timeout, on_wait_timeout=cancel)
        state = str(getattr(getattr(resp.status, "state", None), "value", resp.status.state if resp.status else ""))
        if state != "SUCCEEDED":
            err = getattr(resp.status, "error", None)
            return False, getattr(err, "message", "") or state
        rows: Any = getattr(getattr(resp, "result", None), "data_array", None) or []
        return True, "\n".join(str(cell) for row in rows for cell in row)

    return run
