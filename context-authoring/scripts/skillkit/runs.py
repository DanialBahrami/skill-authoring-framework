"""Run folders: `authoring/runs/<date>-<scope>/` in the output folder, one per run, holding
inventory.md, decisions.md, proposals.md and report.md.

`init` creates a run folder from the skill's templates and reads what earlier runs left (standing
decisions, the backlog). `check` writes its results into report.md between two markers, so the
text the meta-skill wrote around them is kept.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .model import templates_dir

RUNS_DIR = Path("authoring") / "runs"
BEGIN, END = "<!-- skillkit:check -->", "<!-- /skillkit:check -->"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "run"


def init_run(root: Path, scope: str, today: dt.date | None = None) -> tuple[Path, list[str]]:
    """Create (or reuse) today's run folder for `scope`; copy the run templates that are not there yet."""
    run = root / RUNS_DIR / f"{(today or dt.date.today()).isoformat()}-{slug(scope)}"
    run.mkdir(parents=True, exist_ok=True)
    created = []
    for template in sorted((templates_dir() / "run").glob("*.md")):
        target = run / template.name
        if target.exists():
            continue
        text = template.read_text(encoding="utf-8").replace("{{scope}}", scope).replace("{{run}}", run.name)
        target.write_text(text, encoding="utf-8")
        created.append(template.name)
    return run, created


def previous_runs(root: Path, exclude: Path | None = None) -> list[Path]:
    """Earlier run folders, oldest first."""
    base = root / RUNS_DIR
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and p.resolve() != (exclude.resolve() if exclude else None))


def read_tables(path: Path) -> list[tuple[list[str], list[dict[str, str]]]]:
    """Markdown tables in a file: (lower-case header, rows keyed by it). Rows whose first cell is a
    `<placeholder>` are left out."""
    if not path.is_file():
        return []
    tables: list[tuple[list[str], list[dict[str, str]]]] = []
    header: list[str] | None = None
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines() + [""]:
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if header is None:
                header = [c.lower() for c in cells]
            elif set("".join(cells)) <= set("-: "):
                continue
            elif cells and cells[0] and not cells[0].startswith("<"):
                rows.append(dict(zip(header, cells)))
        elif header is not None:
            tables.append((header, rows))
            header, rows = None, []
    return tables


def table_with(path: Path, column: str) -> list[dict[str, str]]:
    """Rows of the first table in `path` that has `column` (lower case) in its header."""
    for header, rows in read_tables(path):
        if column in header:
            return rows
    return []


def decisions(run: Path) -> list[dict[str, str]]:
    """Conflict rows of a run (decisions.md; conflicts.md in runs made before it existed)."""
    return table_with(run / "decisions.md", "decision") or table_with(run / "conflicts.md", "decision")


def backlog(run: Path) -> list[dict[str, str]]:
    """Backlog rows of a run (report.md; backlog.md in runs made before it existed)."""
    return table_with(run / "report.md", "why not now") or table_with(run / "backlog.md", "why not generated")


def run_skills(run: Path) -> list[str]:
    """Skills this run changed: the Skill family rows in decisions.md not marked unchanged."""
    rows = table_with(run / "decisions.md", "this run")
    return [r["skill"].strip("` ") for r in rows
            if r.get("skill") and not r.get("this run", "").strip().lower().startswith("unchanged")]


def write_check(report: Path, markdown: str) -> None:
    """Put `markdown` between the check markers in report.md, replacing what an earlier check wrote."""
    text = report.read_text(encoding="utf-8") if report.is_file() else ""
    block = f"{BEGIN}\n{markdown.strip()}\n{END}"
    if BEGIN in text and END in text:
        start, end = text.index(BEGIN), text.index(END) + len(END)
        text = text[:start] + block + text[end:]
    else:
        text = (text.rstrip() + "\n\n" if text.strip() else "") + block + "\n"
    report.write_text(text, encoding="utf-8")


def demote(markdown: str, levels: int) -> str:
    """Push every heading down `levels` levels (outside code fences), to nest a report in report.md."""
    out, fenced = [], False
    for line in markdown.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        out.append("#" * levels + line if line.startswith("#") and not fenced else line)
    return "\n".join(out)
