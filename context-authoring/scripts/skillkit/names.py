"""Check that the names a skill mentions exist in the source repos.

Every inline code span in SKILL.md and the skill's reference files (`merge_table_silver`,
`Setup/Silver/setup`, `_loaded_at`) is looked up in the source repos, both as a file or
folder name and in file contents. Spans that are placeholders (`<table>`, `${catalog}`,
`YYYY.MM.DD`), commands with arguments, or skills in this repo are skipped.

The result is a report for the author, not a gate: some names legitimately appear in no
file (a widget value a user types, a group name in the workspace).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .model import Skill

SPAN_RE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
FENCE_RE = re.compile(r"^```.*?^```", re.S | re.M)
PLACEHOLDER_RE = re.compile(r"[<>{}$]|\bTODO\b|\b[YMDH]{2,4}\b|\.\.\.|^[A-Z_]{2,}$")
CALL_RE = re.compile(r"^([A-Za-z_][\w.]*)\s*\(")
TOKEN_RE = re.compile(r"[A-Za-z_][\w.\-]*")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".idea", ".vscode"}
TEXT_LIMIT = 1_000_000          # bytes; larger files are only indexed by name
MIN_LEN = 3


@dataclass
class RepoIndex:
    paths: set[str] = field(default_factory=set)       # relative file and folder paths, lower case
    names: set[str] = field(default_factory=set)       # file and folder names and stems, lower case
    tokens: set[str] = field(default_factory=set)      # identifiers found in file contents
    text: list[str] = field(default_factory=list)      # contents, for spans that are not single tokens


def index_repo(root: Path) -> RepoIndex:
    idx = RepoIndex()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        rel_dir = Path(dirpath).relative_to(root)
        if str(rel_dir) != ".":
            idx.paths.add(rel_dir.as_posix().lower())
            idx.names.add(rel_dir.name.lower())
        for name in filenames:
            rel = (rel_dir / name).as_posix().lower().lstrip("./")
            idx.paths.add(rel)
            idx.names.add(name.lower())
            idx.names.add(Path(name).stem.lower())
            path = Path(dirpath) / name
            try:
                if path.stat().st_size > TEXT_LIMIT:
                    continue
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            idx.tokens.update(TOKEN_RE.findall(text))
            idx.text.append(text)
    return idx


def candidate(span: str) -> str | None:
    """The name to look up for a code span, or None to skip it."""
    span = span.strip().strip("\"'")
    if len(span) < MIN_LEN or PLACEHOLDER_RE.search(span):
        return None
    call = CALL_RE.match(span)
    if call:
        return call.group(1)
    if span.startswith("-") or "://" in span or re.search(r"[=,|\"']", span):
        return None                    # a CLI flag, a URL, an assignment or a list of values
    if re.search(r"\s", span):
        return None                    # a command, an expression or prose
    return span.rstrip("/")


def _strip_suffix(path: str) -> str:
    """`a/b/setup.py` -> `a/b/setup`; a path without an extension is returned unchanged."""
    head, _, last = path.rpartition("/")
    stem = last.rsplit(".", 1)[0] if "." in last.lstrip(".") else last
    return f"{head}/{stem}" if head else stem


def _found(name: str, idxs: list[RepoIndex]) -> bool:
    low = name.lower().lstrip("./")
    for idx in idxs:
        if "/" in low and "*" in low:   # a glob such as Deployment/*.sql
            glob = re.compile("(^|/)" + re.escape(low).replace(r"\*\*", ".*").replace(r"\*", "[^/]*") + "$")
            if any(glob.search(p) for p in idx.paths):
                return True
            continue
        if "/" in low:
            # A path matches whole segments, and notebooks are named without their extension
            # (`%run ../Common/setup` is setup.py). Never fall back to the file name alone:
            # `ib/merge.py` must not be found because `lib/merge.py` or any `merge.py` exists.
            if any(c == low or c.endswith("/" + low) for p in idx.paths for c in (p, _strip_suffix(p))):
                return True
            mention = re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w/-])")
            if any(mention.search(text) for text in idx.text):
                return True
            continue
        if low in idx.names or Path(low).stem in idx.names:
            return True
        if name in idx.tokens:
            return True
        if any(name in text for text in idx.text):
            return True
    return False


def spans(skill: Skill) -> list[tuple[str, str]]:
    """(file, span) for every inline code span in SKILL.md, references/*.md and Markdown in assets/,
    outside fenced blocks."""
    files = [("SKILL.md", skill.body)]
    for folder in ("references", "assets"):
        base = skill.path / folder
        if base.is_dir():
            files += [(p.relative_to(skill.path).as_posix(), p.read_text(encoding="utf-8"))
                      for p in sorted(base.rglob("*.md"))]
    out = []
    for rel, text in files:
        for match in SPAN_RE.finditer(FENCE_RE.sub("", text)):
            out.append((rel, match.group(1)))
    return out


def check_skill(skill: Skill, idxs: list[RepoIndex], skill_names: set[str],
                ignore: set[str] | None = None) -> list[tuple[str, str]]:
    """Return (file, name) for names not found in any source repo."""
    own = {p.relative_to(skill.path).as_posix().lower() for p in skill.path.rglob("*") if p.is_file()}
    missing, seen = [], set()
    for rel, span in spans(skill):
        name = candidate(span)
        if not name or name in seen or name in skill_names or name in (ignore or set()):
            continue
        seen.add(name)
        if name.lower().lstrip("./") in own:
            continue                   # a file shipped with the skill (assets/, references/)
        if not _found(name, idxs):
            missing.append((rel, name))
    return missing
