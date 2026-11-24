"""Execution gate: check the code in an eval answer against a real (development) workspace.

Evals score what the model says it would do; a column that does not exist in the table
still looks right. This gate checks the answer's code without running it:

- SQL (```sql blocks and spark.sql("...") calls): every query and DML statement is planned
  with `EXPLAIN`, so unknown tables, columns, functions and syntax errors show up. The query
  part of CREATE ... AS SELECT (and of temp views) is planned on its own.
- Every fully qualified table in a configured catalog (the target of a MERGE, ALTER or
  INSERT too) gets `DESCRIBE TABLE`, unless the answer creates it or the case says it is new.
- Python blocks are compiled (syntax only, nothing runs) and YAML blocks are parsed, locally.

Safety:
- Only statements that start with `EXPLAIN ` or `DESCRIBE TABLE ` are ever sent; the runners
  refuse anything else. Both read metadata, never rows, so the gate is safe on PII tables.
- Other DDL, GRANT, OPTIMIZE and similar are reported as not checked.
- Run it as an identity that can only read the development catalog, so even a mistake in
  this code cannot change data.

Not checked: PySpark DataFrame code beyond syntax, and the tables a DataFrame reads.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import yaml

FENCE_RE = re.compile(r"```[ \t]*([\w+-]*)[^\n]*\n(.*?)```", re.S)
SPARK_SQL_RE = re.compile(r"spark\.sql\(\s*[fr]?(\"\"\"|'''|\"|')(.*?)\1", re.S)
CREATE_RE = re.compile(r"^\s*create\s+(?:or\s+replace\s+)?(?:global\s+)?(?:temporary\s+|temp\s+)?(?:table|view|"
                       r"materialized\s+view|streaming\s+table)\s+(?:if\s+not\s+exists\s+)?([`\w.${}\-]+)", re.I)
CTAS_RE = re.compile(r"\bas\s*\(?\s*((?:select|with)\b.*)$", re.I | re.S)
EXPLAINABLE = ("select", "with", "insert", "merge", "update", "delete", "values", "from", "table")
PLACEHOLDER_RE = re.compile(r"\$\{[^}]*\}|\{\{[^}]*\}\}|<[A-Za-z_][\w-]*>|\bTODO\b|\.\.\.")
PY_PLACEHOLDER_RE = re.compile(r"<[A-Za-z_][\w -]*>|\bTODO\b")
ERROR_CODE_RE = re.compile(r"\[([A-Z][A-Z0-9_]+)(?:\.[A-Z0-9_]+)?\]")
STRING_RE = re.compile(r"'(?:[^'\\]|\\.)*'")
QUALIFIED_RE = re.compile(r"(?<![\w.`])(`?[A-Za-z_][\w-]*`?)\.(`?[\w-]+`?)\.(`?[\w-]+`?)(?![\w.`]|\s*\()")
DOTTED_RE = re.compile(r"[`\w]+(?:\.[`\w]+){1,2}")
UNQUALIFIED_RE = re.compile(r"(?i)\b(?:from|join|into|using|update|table)\s+(`?[A-Za-z_]\w*`?)(?![\w`]*\.)(?!\s*\()")
MISSING_NAME_RE = re.compile(r"TABLE_OR_VIEW_NOT_FOUND\].*?(`[^`]+`(?:\.`[^`]+`)*)", re.S)
ALLOWED_PREFIXES = ("EXPLAIN ", "DESCRIBE TABLE ")

INVALID_CODES = {
    "UNRESOLVED_COLUMN", "UNRESOLVED_FIELD", "TABLE_OR_VIEW_NOT_FOUND", "SCHEMA_NOT_FOUND",
    "CATALOG_NOT_FOUND", "UNRESOLVED_ROUTINE", "PARSE_SYNTAX_ERROR", "PARSE_EMPTY_STATEMENT",
    "DATATYPE_MISMATCH", "AMBIGUOUS_REFERENCE", "AMBIGUOUS_COLUMN_OR_FIELD", "WRONG_NUM_ARGS",
    "INVALID_IDENTIFIER", "MISSING_GROUP_BY", "MISSING_AGGREGATION", "NOT_A_PARTITIONED_TABLE",
    "INSERT_COLUMN_ARITY_MISMATCH", "INCOMPATIBLE_DATA_FOR_TABLE", "DELTA_MERGE_UNRESOLVED_EXPRESSION",
    "FIELD_NOT_FOUND",
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
            return "no code"
        counts = {s: sum(c.status == s for c in self.checks) for s in ("ok", "invalid", "skipped", "inconclusive")}
        return ", ".join(f"{n} {s}" for s, n in counts.items() if n)

    def notes(self) -> list[str]:
        return [f"{c.detail} in `{c.excerpt()}`" for c in self.invalid]


def guard(statement: str) -> None:
    """Refuse anything but EXPLAIN and DESCRIBE TABLE."""
    if not statement.lstrip().upper().startswith(ALLOWED_PREFIXES):
        raise ValueError("the execution gate only sends EXPLAIN and DESCRIBE TABLE statements")


def code_blocks(answer: str) -> list[tuple[str, str]]:
    return [(lang.lower(), body) for lang, body in FENCE_RE.findall(answer)]


def extract_sql(answer: str) -> list[str]:
    """SQL statements from ```sql blocks and spark.sql(...) string literals, in order."""
    chunks: list[str] = []
    for lang, body in code_blocks(answer):
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
    """(status, detail) for an EXPLAIN or DESCRIBE error message."""
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


def _clean_python(code: str) -> str:
    """Notebook source to plain Python: dedent, drop magics (%run, %pip) and shell lines."""
    lines = [ln for ln in textwrap.dedent(code).splitlines() if not ln.lstrip().startswith(("%", "!"))]
    return "\n".join(lines)


Runner = Callable[[str], tuple[bool, str]]
"""Runs one EXPLAIN or DESCRIBE TABLE statement; returns (succeeded, text): the result, or the error."""


class SqlChecker:
    def __init__(self, runner: Runner, variables: dict[str, str] | None = None, signature: str = "",
                 catalogs: Iterable[str] | None = None):
        self.runner = runner
        self.variables = dict(variables or {})
        self.signature = signature    # part of the eval cache key: warehouse and variables
        # Catalogs whose fully qualified tables get DESCRIBE TABLE; default: the variable values,
        # so `${catalog}.s.t` filled with the dev catalog is described, `alias.struct.field` is not.
        self.catalogs = {c.lower() for c in (catalogs if catalogs is not None else self.variables.values()) if c}

    def _run(self, statement: str) -> tuple[bool, str]:
        guard(statement)
        return self.runner(statement)

    def check(self, answer: str, new_tables: Iterable[str] | None = None) -> SqlReport:
        report = SqlReport()
        new = [re.compile(p, re.I) for p in (new_tables or [])]
        statements = [substitute(raw, self.variables) for raw in extract_sql(answer)]
        created: set[str] = set()
        for stmt in statements:
            match = CREATE_RE.match(stmt)
            if match:
                name = _norm(match.group(1))
                created |= {name, name.split(".")[-1], ".".join(name.split(".")[-2:])}

        def is_new(name: str) -> bool:
            name = _norm(name)
            parts = name.split(".")
            return (name in created or ".".join(parts[-2:]) in created or (len(parts) == 1 and name in created)
                    or any(p.search(name) for p in new))

        described: set[str] = set()
        for stmt in statements:
            if PLACEHOLDER_RE.search(stmt):
                report.checks.append(SqlCheck(stmt, "skipped", "unresolved placeholder"))
                continue
            self._describe_tables(stmt, report, described, is_new)
            self._explain(stmt, report, is_new)
        for lang, body in code_blocks(answer):
            if lang in ("python", "py", "pyspark"):
                self._compile_python(body, report)
            elif lang in ("yaml", "yml"):
                self._parse_yaml(body, report)
        return report

    def _describe_tables(self, stmt: str, report: SqlReport, described: set[str], is_new) -> None:
        create = CREATE_RE.match(stmt)
        target = _norm(create.group(1)) if create else ""
        for parts in QUALIFIED_RE.findall(STRING_RE.sub("''", stmt)):
            name = ".".join(_norm(p) for p in parts)
            if parts[0].replace("`", "").lower() not in self.catalogs or name in described or name == target:
                continue
            described.add(name)
            if is_new(name):
                report.checks.append(SqlCheck(f"table {name}", "skipped", "created by the answer or expected to be new"))
                continue
            ok, text = self._run(f"DESCRIBE TABLE {name}")
            if ok:
                report.checks.append(SqlCheck(f"table {name}", "ok"))
            else:
                status, detail = classify(text)
                report.checks.append(SqlCheck(f"table {name}", status, detail))

    def _explain(self, stmt: str, report: SqlReport, is_new) -> None:
        target = stmt
        create = CREATE_RE.match(stmt)
        if create:
            ctas = CTAS_RE.search(stmt)
            if not ctas:
                report.checks.append(SqlCheck(stmt, "skipped", "DDL is not checked"))
                return
            target = ctas.group(1).rstrip(") \n")
        first = re.match(r"\s*\(?\s*(\w+)", target)
        keyword = first.group(1).lower() if first else ""
        if keyword not in EXPLAINABLE:
            report.checks.append(SqlCheck(stmt, "skipped", f"{keyword.upper() or 'statement'} is not checked"))
            return
        refs = set(DOTTED_RE.findall(target)) | set(UNQUALIFIED_RE.findall(target))
        if any(is_new(r) for r in refs):
            report.checks.append(SqlCheck(stmt, "skipped", "uses a table created in this answer or expected to be new"))
            return
        ok, text = self._run("EXPLAIN " + target)
        # A failed analysis often comes back as a plan row, not as a failed statement.
        planning_error = re.search(r"Error occurred during query planning|AnalysisException", text) or \
            any(code in INVALID_CODES for code in ERROR_CODE_RE.findall(text))
        if ok and not planning_error:
            report.checks.append(SqlCheck(stmt, "ok"))
            return
        status, detail = classify(text)
        missing = MISSING_NAME_RE.search(text)
        if status == "invalid" and missing:
            name = _norm(missing.group(1))
            if is_new(name):
                report.checks.append(SqlCheck(stmt, "skipped", f"{name} does not exist yet (expected)"))
                return
            if "." not in name:
                report.checks.append(SqlCheck(stmt, "inconclusive",
                                              f"unqualified {name}: may be a temp view or table defined elsewhere"))
                return
        report.checks.append(SqlCheck(stmt, status, detail))

    @staticmethod
    def _compile_python(body: str, report: SqlReport) -> None:
        code = _clean_python(body)
        if not code.strip():
            return
        if PY_PLACEHOLDER_RE.search(code):
            report.checks.append(SqlCheck(code, "skipped", "python with placeholders"))
            return
        try:
            compile(code, "<answer>", "exec")
            report.checks.append(SqlCheck(code, "ok", "python syntax"))
        except SyntaxError as exc:
            report.checks.append(SqlCheck(code, "invalid", f"python syntax: {exc.msg} (line {exc.lineno})"))

    @staticmethod
    def _parse_yaml(body: str, report: SqlReport) -> None:
        if "{{" in body or PY_PLACEHOLDER_RE.search(body):
            report.checks.append(SqlCheck(body, "skipped", "yaml with placeholders"))
            return
        try:
            yaml.safe_load(body)
            report.checks.append(SqlCheck(body, "ok", "yaml"))
        except yaml.YAMLError as exc:
            report.checks.append(SqlCheck(body, "invalid", f"yaml: {str(exc).splitlines()[0]}"))


def warehouse_runner(warehouse_id: str, profile: str | None = None, timeout: str = "30s") -> Runner:
    """A runner that sends statements to a SQL warehouse through the Statement Execution API."""
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.sql import ExecuteStatementRequestOnWaitTimeout

    w = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
    cancel = ExecuteStatementRequestOnWaitTimeout.CANCEL   # never leave a statement running

    def run(statement: str) -> tuple[bool, str]:
        guard(statement)
        resp = w.statement_execution.execute_statement(statement=statement, warehouse_id=warehouse_id,
                                                       wait_timeout=timeout, on_wait_timeout=cancel)
        state = str(getattr(getattr(resp.status, "state", None), "value", resp.status.state if resp.status else ""))
        if state != "SUCCEEDED":
            err = getattr(resp.status, "error", None)
            return False, getattr(err, "message", "") or state
        rows: Any = getattr(getattr(resp, "result", None), "data_array", None) or []
        return True, "\n".join(str(cell) for row in rows for cell in row)

    return run


def spark_runner() -> Runner:
    """A runner on the notebook's active Spark session, for running the gate from Genie Code
    without a SQL warehouse. Statements run as the notebook user."""
    try:
        from pyspark.sql import SparkSession
    except ImportError as exc:
        raise SystemExit("--execute without --warehouse-id needs an active Spark session (run it in a notebook)") from exc
    spark = SparkSession.getActiveSession()
    if spark is None:
        raise SystemExit("--execute without --warehouse-id needs an active Spark session (run it in a notebook)")

    def run(statement: str) -> tuple[bool, str]:
        guard(statement)
        try:
            rows = spark.sql(statement).collect()
        except Exception as exc:  # analysis errors arrive as exceptions here
            return False, str(exc)
        return True, "\n".join(" ".join(str(c) for c in row) for row in rows)

    return run
