"""Eval runner: routing test, answer test with and without the skill (baseline), LLM judge.

The runner simulates Genie Code with a model serving endpoint. It does not execute
anything in the workspace: the model describes what it would do, and the answer is
scored with regexes and a rubric judged by a second model.

Routing: the model sees the catalog and picks the first skill to load, or none. The
catalog is every skill in the repo that is not deprecated (drafts included, so a near
miss can route to a sibling draft), skills already installed in the workspace when they
are given (minus those a repo skill supersedes), and decoys standing in for built-in
skills. Only the skills named in the run are scored.

Answer: the model gets the workspace instructions, the AGENTS.md files the case names,
the skills listed in the target's `uses` (they would be loaded on demand), and - in the
"with skill" arm - the target skill's body and reference files. The baseline arm is the
same without the target skill, so a workflow is measured against its building blocks alone.
A skill adds value when at least one trigger case passes with it and fails without it.

Each case can run several times (`runs`). Routing passes on a trigger rate threshold
(default 0.5, as the Agent Skills guide suggests); answers pass on a majority of runs.
Token usage is recorded when the endpoint reports it, to show what the skill costs.

`AGENTS.md` files a case lists are read from `--agents-drafts` first (drafts in a run
folder, laid out like the repos root) and otherwise from `--repos-root`.

Results are cached per case in `.skillkit-cache/evals.json`, keyed by everything that
can change them (prompts, skill text, context, catalog, model, judge, limits, runs), so a
repeat run re-runs only the cases whose inputs changed; `refresh_failed` also re-runs
cases that failed or were inconclusive.

An answer cut off at the token limit is not counted as a failure: it is reported as
truncated, and a case with only truncated failures makes the skill INCONCLUSIVE. Raise
`eval.max_tokens` in standard.yaml, or per skill in skill.yaml, and run again.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from .model import Skill, Standard, defaults_dir, instructions_for_evals

ROUTER_SYSTEM = """You select skills for Genie Code, the Databricks coding agent.
You get a user request and the list of installed skills (name: description).
Return the single skill that should be loaded first to handle the request, or "none"
if no skill fits. Answer with JSON only: {"skill": "<name or none>"}"""

AGENT_SYSTEM = """You are Genie Code in Agent mode in a Databricks workspace.
In this test you cannot run anything. Describe exactly what you would do: the files you
would create or change with their content, the SQL and code you would run, and the
questions you would ask the user before acting. Follow the instructions and skills below."""

JUDGE_SYSTEM = """You grade an answer from a coding agent against a rubric.
For each rubric item decide whether the answer satisfies it. Be strict: an item passes
only if the answer clearly does what it says. The agent could not run code, query data or
see the current date, so judge what it says it would do: do not fail an item for missing
results that only running something would produce (actual table lists, real dates, real
counts). A placeholder such as YYYY.MM.DD or <table_name> satisfies an item that asks for
a value of that shape. Answer with JSON only:
{"items": [{"item": "<rubric item>", "pass": true|false, "reason": "<short>"}]}"""


class LLM(Protocol):
    def complete(self, endpoint: str, system: str, user: str, max_tokens: int) -> str: ...


class ServingLLM:
    """Calls Databricks model serving endpoints through the SDK."""

    def __init__(self, profile: str | None = None):
        from databricks.sdk import WorkspaceClient

        self.w = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
        self.last_tokens: int | None = None
        self.last_truncated = False

    def complete(self, endpoint: str, system: str, user: str, max_tokens: int) -> str:
        from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

        resp = self.w.serving_endpoints.query(
            name=endpoint,
            messages=[ChatMessage(role=ChatMessageRole.SYSTEM, content=system),
                      ChatMessage(role=ChatMessageRole.USER, content=user)],
            max_tokens=max_tokens,
            temperature=0.0,
        )
        usage = getattr(resp, "usage", None)
        self.last_tokens = getattr(usage, "total_tokens", None) if usage else None
        reason = getattr(resp.choices[0], "finish_reason", None)   # a string or an enum, by SDK version
        self.last_truncated = str(getattr(reason, "value", reason) or "").lower().endswith("length")
        content = resp.choices[0].message.content
        if isinstance(content, list):  # some endpoints return content parts
            content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
        return content or ""


def parse_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from a model reply."""
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


@dataclass
class CaseResult:
    skill: str
    case_id: str
    case_type: str
    routing_expected: str = ""
    routing_got: str = ""
    routing_pass: bool | None = None
    with_skill_pass: bool | None = None
    baseline_pass: bool | None = None
    with_skill_notes: list[str] = field(default_factory=list)
    baseline_notes: list[str] = field(default_factory=list)
    with_skill_answer: str = ""
    baseline_answer: str = ""
    routing_rate: float | None = None
    with_skill_tokens: int | None = None
    baseline_tokens: int | None = None
    with_skill_truncated: int = 0      # runs cut off at the token limit
    baseline_truncated: int = 0
    max_tokens: int | None = None
    with_skill_sql: str = ""           # execution gate summary, e.g. "3 ok, 1 invalid"
    baseline_sql: str = ""


@dataclass
class SkillVerdict:
    skill: str
    routing: str
    answers: str
    baseline: str
    verdict: str
    token_delta: str = "-"


def score_answer(answer: str, case: dict[str, Any], judge: LLM | None, judge_endpoint: str,
                 max_tokens: int) -> tuple[bool, list[str]]:
    notes: list[str] = []
    ok = True
    for pattern in case.get("must_include", []) or []:
        if not re.search(pattern, answer, re.I | re.M):
            ok = False
            notes.append(f"missing /{pattern}/")
    for pattern in case.get("must_not_include", []) or []:
        match = re.search(pattern, answer, re.I | re.M)
        if match:
            ok = False
            notes.append(f"forbidden /{pattern}/ matched '{match.group(0)[:60]}'")
    rubric = case.get("rubric", []) or []
    if rubric and judge is not None:
        prompt = (f"Request:\n{case['prompt']}\n\nAnswer:\n{answer}\n\nRubric:\n"
                  + "\n".join(f"- {item}" for item in rubric))
        verdict = parse_json(judge.complete(judge_endpoint, JUDGE_SYSTEM, prompt, max_tokens))
        items = verdict.get("items", [])
        if len(items) != len(rubric):
            ok = False
            notes.append("judge reply could not be parsed")
        for item in items:
            if not item.get("pass"):
                ok = False
                notes.append(f"rubric failed: {item.get('item')} ({item.get('reason', '')})")
    return ok, notes


def _tokens(llm: LLM) -> int | None:
    return getattr(llm, "last_tokens", None)


def _truncated(llm: LLM) -> bool:
    return bool(getattr(llm, "last_truncated", False))


def _majority(results: list[tuple[bool, list[str]]], truncated: list[bool] | None = None
              ) -> tuple[bool | None, list[str]]:
    """Pass on a majority of runs. A failed run whose answer was cut off at the token limit
    is left out; if every run was left out the result is None (inconclusive)."""
    truncated = truncated or [False] * len(results)
    kept = [(ok, n) for (ok, n), cut in zip(results, truncated) if ok or not cut]
    if not kept:
        return None, ["answer cut off at the token limit in every run"]
    passed = sum(ok for ok, _ in kept)
    notes = next((n for ok, n in kept if not ok), [])
    return passed * 2 > len(kept), notes


def _arm(llm: LLM, model: str, system: str, case: dict[str, Any], judge_ep: str, max_tokens: int,
         runs: int, checker=None) -> tuple[bool | None, list[str], str, int | None, int, str]:
    """Run one arm (with or without the skill) `runs` times; return pass, notes, last answer,
    mean tokens, the number of truncated runs and the execution gate summary of the last run.
    With a checker (execution gate), a run also fails when its SQL does not plan."""
    scored, tokens, cuts, answer, sql = [], [], [], "", ""
    for _ in range(runs):
        answer = llm.complete(model, system, case["prompt"], max_tokens)
        tokens.append(_tokens(llm))
        cuts.append(_truncated(llm))
        ok, notes = score_answer(answer, case, llm, judge_ep, max(max_tokens, 1000))
        if checker is not None:
            report = checker.check(answer, case.get("exec_new_tables"), case.get("exec_new_columns"))
            sql = report.summary()
            if report.invalid:
                ok, notes = False, notes + report.notes()
        scored.append((ok, notes))
    ok, notes = _majority(scored, cuts)
    if any(cuts) and ok is not None:
        notes = notes + [f"{sum(cuts)} of {runs} answers cut off at {max_tokens} tokens"]
    return ok, notes, answer, _mean(tokens), sum(cuts), sql


def _context_block(root: Path, case: dict[str, Any], repos_root: Path | None,
                   drafts_root: Path | None = None) -> tuple[str, list[str]]:
    warnings = []
    parts = []
    text, _ = instructions_for_evals(root)
    if text:
        parts.append(f"# Workspace instructions\n{text}")
    for rel in case.get("agents", []) or []:
        draft = drafts_root / rel if drafts_root else None
        if draft is not None and draft.is_file():
            parts.append(f"# {rel}\n{draft.read_text(encoding='utf-8')}")
            continue
        if repos_root is None:
            where = f"--agents-drafts {drafts_root}" if drafts_root else "no --repos-root or --agents-drafts"
            warnings.append(f"case {case.get('id')}: agents file {rel} skipped ({where})")
            continue
        path = repos_root / rel
        if path.is_file():
            parts.append(f"# {rel}\n{path.read_text(encoding='utf-8')}")
        else:
            warnings.append(f"case {case.get('id')}: agents file {rel} not found under {repos_root}"
                            + (f" or {drafts_root}" if drafts_root else ""))
    return "\n\n".join(parts), warnings


CACHE_FILE = Path(".skillkit-cache") / "evals.json"
ROUTING_FIELDS = ("routing_expected", "routing_got", "routing_pass", "routing_rate")
ANSWER_FIELDS = ("with_skill_pass", "with_skill_notes", "with_skill_answer", "with_skill_tokens",
                 "with_skill_truncated", "baseline_pass", "baseline_notes", "baseline_answer",
                 "baseline_tokens", "baseline_truncated", "max_tokens", "with_skill_sql", "baseline_sql")


def _key(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def load_cache(root: Path) -> dict[str, Any]:
    path = root / CACHE_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(root: Path, cache: dict[str, Any]) -> None:
    path = root / CACHE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache), encoding="utf-8")


def _reuse(cache: dict[str, Any] | None, key: str, refresh_failed: bool, passed_field: str) -> dict | None:
    if cache is None or key not in cache:
        return None
    hit = cache[key]
    if refresh_failed and hit.get(passed_field) is not True:
        return None
    return hit


def _mean(values: list[int | None]) -> int | None:
    known = [v for v in values if v is not None]
    return round(sum(known) / len(known)) if known else None


def load_decoys(root: Path) -> list[dict[str, str]]:
    path = root / "evals" / "decoys.yaml"
    if not path.is_file():
        path = defaults_dir() / "decoys.yaml"    # the skill's default decoys
    if not path.is_file():
        return []
    return list((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("decoys", []))


def catalog_for_routing(root: Path, all_skills: list[Skill], installed: list | None = None,
                        targets: set[str] | None = None) -> str:
    """Everything a user could end up with: repo skills that are not deprecated (drafts included,
    and a deprecated skill while it is being evaluated), installed skills that no repo skill
    supersedes, and decoys for built-in skills."""
    catalog_skills = [s for s in all_skills if s.status != "deprecated" or s.name in (targets or set())]
    superseded = {name for s in catalog_skills for name in s.supersedes}
    repo_names = {s.name for s in all_skills}
    catalog = [f"{s.name}: {s.description}" for s in catalog_skills]
    catalog += [f"{i.name}: {i.description}" for i in (installed or [])
                if i.name not in superseded and i.name not in repo_names]
    catalog += [f"{d['name']}: {d['description']}" for d in load_decoys(root)]
    return "\n".join(f"- {line}" for line in catalog)


def run_evals(root: Path, std: Standard, all_skills: list[Skill], targets: list[Skill], llm: LLM, *,
              mode: str = "all", baseline: bool = True, repos_root: Path | None = None,
              case_filter: str | None = None, runs: int = 1, threshold: float | None = None,
              installed: list | None = None, drafts_root: Path | None = None,
              cache: dict[str, Any] | None = None, refresh_failed: bool = False, checker=None, log=print) -> tuple[list[CaseResult], list[SkillVerdict], list[str]]:
    model = std.eval.get("model_endpoint")
    judge_ep = std.eval.get("judge_endpoint", model)
    max_tokens = int(std.eval.get("max_tokens", 2000))
    threshold = float(threshold if threshold is not None else std.eval.get("trigger_threshold", 0.5))
    runs = max(1, int(runs))
    by_name = {s.name: s for s in all_skills}
    warnings: list[str] = []

    catalog_text = catalog_for_routing(root, all_skills, installed, {t.name for t in targets})
    pattern = re.compile(case_filter) if case_filter else None

    results: list[CaseResult] = []
    reused = 0
    for skill in targets:
        for case in skill.cases:
            if pattern and not pattern.search(str(case.get("id", ""))):
                continue
            ctype = case.get("type", "trigger")
            res = CaseResult(skill=skill.name, case_id=str(case.get("id")), case_type=ctype)
            log(f"  {skill.name} / {res.case_id}")

            routing_key = _key("routing", model, ROUTER_SYSTEM, catalog_text, skill.name, case, runs, threshold)
            hit = _reuse(cache, routing_key, refresh_failed, "routing_pass") if mode in ("all", "routing") else None
            if hit:
                for name in ROUTING_FIELDS:
                    setattr(res, name, hit.get(name))
                reused += 1
            elif mode in ("all", "routing"):
                expected = case.get("expect_skill") or (skill.name if ctype == "trigger" else None)
                picks = []
                for _ in range(runs):
                    reply = parse_json(llm.complete(model, ROUTER_SYSTEM,
                                                    f"Installed skills:\n{catalog_text}\n\nUser request:\n{case['prompt']}",
                                                    200))
                    picks.append(str(reply.get("skill", "")).strip() or "unparsed")
                res.routing_got = max(set(picks), key=picks.count)
                if ctype == "trigger":
                    res.routing_expected = expected
                    res.routing_rate = picks.count(expected) / runs
                    res.routing_pass = res.routing_rate >= threshold
                elif expected:
                    res.routing_expected = expected
                    res.routing_rate = picks.count(expected) / runs
                    res.routing_pass = res.routing_rate >= threshold
                else:
                    res.routing_expected = f"not {skill.name}"
                    res.routing_rate = picks.count(skill.name) / runs   # false-trigger rate
                    res.routing_pass = res.routing_rate < threshold
                if cache is not None:
                    cache[routing_key] = {name: getattr(res, name) for name in ROUTING_FIELDS}

            if mode in ("all", "answer") and ctype == "trigger":
                context, warn = _context_block(root, case, repos_root, drafts_root)
                warnings += warn
                deps = ""
                for dep in skill.uses:
                    if dep in by_name:
                        deps += f"\n\n# Skill available: {dep}\n{by_name[dep].reference_text()}"
                    else:
                        warnings.append(f"{skill.name}: uses unknown skill {dep}")
                base_context = context + deps
                with_skill = f"{base_context}\n\n# Skill loaded: {skill.name}\n{skill.reference_text()}"
                limit = skill.eval_max_tokens or max_tokens
                res.max_tokens = limit
                answer_key = _key("answer", model, judge_ep, AGENT_SYSTEM, JUDGE_SYSTEM, with_skill, base_context,
                                  case, limit, runs, baseline, getattr(checker, "signature", None))
                hit = _reuse(cache, answer_key, refresh_failed, "with_skill_pass")
                if hit:
                    for name in ANSWER_FIELDS:
                        setattr(res, name, hit.get(name))
                    reused += 1
                    results.append(res)
                    continue
                (res.with_skill_pass, res.with_skill_notes, res.with_skill_answer, res.with_skill_tokens,
                 res.with_skill_truncated, res.with_skill_sql) = _arm(llm, model, AGENT_SYSTEM + "\n\n" + with_skill,
                                                                      case, judge_ep, limit, runs, checker)
                if baseline:
                    (res.baseline_pass, res.baseline_notes, res.baseline_answer, res.baseline_tokens,
                     res.baseline_truncated, res.baseline_sql) = _arm(llm, model, AGENT_SYSTEM + "\n\n" + base_context,
                                                                      case, judge_ep, limit, runs, checker)
                if cache is not None:
                    cache[answer_key] = {name: getattr(res, name) for name in ANSWER_FIELDS}
            results.append(res)

    if reused:
        warnings.append(f"cache: {reused} routing or answer result(s) reused because nothing they depend on "
                        "changed; use --no-cache for fresh samples")
    verdicts = []
    for skill in targets:
        rows = [r for r in results if r.skill == skill.name]
        routed = [r for r in rows if r.routing_pass is not None]
        answered = [r for r in rows if r.with_skill_pass is not None]
        based = [r for r in rows if r.baseline_pass is not None]
        r_ok = sum(r.routing_pass for r in routed)
        a_ok = sum(r.with_skill_pass for r in answered)
        b_ok = sum(r.baseline_pass for r in based)
        lift = any(r.with_skill_pass and r.baseline_pass is False for r in based)
        cut_off = any(r.case_type == "trigger" and r.with_skill_pass is None and r.with_skill_truncated
                      for r in rows)
        if (routed and r_ok < len(routed)) or (answered and a_ok < len(answered)):
            verdict = "FAILING"
        elif cut_off:
            verdict = "INCONCLUSIVE"
        elif based and not lift:
            verdict = "NO EFFECT"
        elif based:
            verdict = "ADDS VALUE"
        else:
            verdict = "PASSING (no baseline)"
        with_t = [r.with_skill_tokens for r in based if r.with_skill_tokens is not None]
        base_t = [r.baseline_tokens for r in based if r.baseline_tokens is not None]
        delta = f"{round(sum(with_t) / len(with_t) - sum(base_t) / len(base_t)):+d}" if with_t and base_t else "-"
        verdicts.append(SkillVerdict(
            skill=skill.name,
            routing=f"{r_ok}/{len(routed)}" if routed else "-",
            answers=f"{a_ok}/{len(answered)}" if answered else "-",
            baseline=f"{b_ok}/{len(based)}" if based else "-",
            verdict=verdict,
            token_delta=delta,
        ))
    return results, verdicts, warnings


def report_markdown(results: list[CaseResult], verdicts: list[SkillVerdict], warnings: list[str],
                    std: Standard) -> str:
    lines = [
        "## Skill eval report",
        "",
        f"Model `{std.eval.get('model_endpoint')}`, judge `{std.eval.get('judge_endpoint')}`.",
        "",
        "| Skill | Routing | Answers with skill | Answers without skill | Tokens per answer vs baseline | Verdict |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines += [f"| `{v.skill}` | {v.routing} | {v.answers} | {v.baseline} | {v.token_delta} | **{v.verdict}** |"
              for v in verdicts]
    lines += ["", "### Cases", "", "| Case | Type | Routing | With skill | Without skill | Notes |",
              "| --- | --- | --- | --- | --- | --- |"]

    def mark(value: bool | None, cut: int = 0) -> str:
        if value is None:
            return "cut off" if cut else "-"
        return ("pass" if value else "FAIL") + (" (cut off)" if cut else "")

    for r in results:
        rate = f", rate {r.routing_rate:.2f}" if r.routing_rate is not None else ""
        routing = "-" if r.routing_pass is None else f"{mark(r.routing_pass)} ({r.routing_got}{rate})"
        notes = "; ".join(([f"SQL: {r.with_skill_sql}"] if r.with_skill_sql else []) + r.with_skill_notes[:3])
        notes = notes.replace("|", "\\|")
        lines.append(f"| `{r.skill}/{r.case_id}` | {r.case_type} | {routing} | "
                     f"{mark(r.with_skill_pass, r.with_skill_truncated)} | "
                     f"{mark(r.baseline_pass, r.baseline_truncated)} | {notes} |")
    if warnings:
        lines += ["", "### Warnings", ""] + [f"- {w}" for w in warnings]
    lines += ["", "Verdicts: ADDS VALUE = passes, and at least one case passes only with the skill. "
              "NO EFFECT = the model already gets it right without the skill; do not merge. "
              "FAILING = a routing or answer case fails. INCONCLUSIVE = answers were cut off at the token limit; "
              "raise `max_tokens` (standard.yaml `eval`, or `eval: max_tokens` in the skill's skill.yaml) and run again. Verdicts can vary between runs; read a failing answer "
              "(`--inspect <case-id>`) before changing a skill."]
    return "\n".join(lines) + "\n"


def results_json(results: list[CaseResult], verdicts: list[SkillVerdict]) -> str:
    return json.dumps({"verdicts": [v.__dict__ for v in verdicts], "cases": [r.__dict__ for r in results]},
                      indent=2, default=str)


def run_context_evals(root: Path, std: Standard, cases_file: Path, llm: LLM, *, repos_root: Path | None,
                      runs: int = 1, drafts_root: Path | None = None, checker=None, log=print) -> tuple[list[CaseResult], SkillVerdict, list[str]]:
    """Evaluate AGENTS.md files the way skills are evaluated: each case runs with the AGENTS.md
    files it lists and without them (workspace instructions in both arms, no skills).
    Research on context files found that generated, redundant ones cost tokens without helping,
    so an AGENTS.md has to show it changes outcomes too."""
    import json as _json

    data = _json.loads(cases_file.read_text(encoding="utf-8"))
    model = std.eval.get("model_endpoint")
    judge_ep = std.eval.get("judge_endpoint", model)
    max_tokens = int(std.eval.get("max_tokens", 2000))
    text, _ = instructions_for_evals(root)
    base = f"# Workspace instructions\n{text}" if text else ""
    results, warnings = [], []
    for raw in data.get("evals", []):
        case = dict(raw)
        case["id"] = str(case.get("id", ""))
        case["rubric"] = list(case.get("assertions", []) or [])
        res = CaseResult(skill=data.get("name", cases_file.stem), case_id=case["id"], case_type="context")
        log(f"  {res.skill} / {res.case_id}")
        context, warn = _context_block(root, case, repos_root, drafts_root)
        warnings += warn
        for arm, ctx in (("with", context), ("without", base)):
            ok, notes, answer, tokens, cuts, sql = _arm(llm, model, AGENT_SYSTEM + "\n\n" + ctx, case, judge_ep,
                                                        max_tokens, max(1, runs), checker)
            if arm == "with":
                (res.with_skill_pass, res.with_skill_notes, res.with_skill_answer, res.with_skill_tokens,
                 res.with_skill_truncated, res.with_skill_sql) = ok, notes, answer, tokens, cuts, sql
            else:
                (res.baseline_pass, res.baseline_notes, res.baseline_answer, res.baseline_tokens,
                 res.baseline_truncated, res.baseline_sql) = ok, notes, answer, tokens, cuts, sql
        results.append(res)
    a_ok = sum(bool(r.with_skill_pass) for r in results)
    b_ok = sum(bool(r.baseline_pass) for r in results)
    lift = any(r.with_skill_pass and r.baseline_pass is False for r in results)
    failed = any(r.with_skill_pass is False for r in results)
    cut_off = any(r.with_skill_pass is None for r in results)
    verdict = ("FAILING" if failed else "INCONCLUSIVE" if cut_off
               else "ADDS VALUE" if lift else "NO EFFECT")
    with_t = [r.with_skill_tokens for r in results if r.with_skill_tokens is not None]
    base_t = [r.baseline_tokens for r in results if r.baseline_tokens is not None]
    delta = f"{round(sum(with_t) / len(with_t) - sum(base_t) / len(base_t)):+d}" if with_t and base_t else "-"
    summary = SkillVerdict(skill=results[0].skill if results else cases_file.stem, routing="-",
                           answers=f"{a_ok}/{len(results)}", baseline=f"{b_ok}/{len(results)}",
                           verdict=verdict, token_delta=delta)
    return results, summary, warnings


JOURNEYS_FILE = Path("evals") / "journeys.json"


def load_journeys(root: Path) -> list[dict[str, Any]]:
    """Journeys: tasks that span several skills, kept as a standing regression suite."""
    path = root / JOURNEYS_FILE
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for raw in data.get("journeys", []) or []:
        j = dict(raw)
        j["id"] = str(j.get("id", ""))
        j["skills"] = [str(x) for x in (j.get("skills") or [])]
        j["rubric"] = list(j.get("assertions", []) or [])
        out.append(j)
    return out


def run_journeys(root: Path, std: Standard, all_skills: list[Skill], journeys: list[dict[str, Any]], llm: LLM, *,
                 repos_root: Path | None = None, drafts_root: Path | None = None, runs: int = 1,
                 threshold: float | None = None, installed: list | None = None,
                 cache: dict[str, Any] | None = None, refresh_failed: bool = False, checker=None,
                 baseline: bool = True, log=print) -> tuple[list[CaseResult], list[str]]:
    """Run each journey: routing must pick its first skill; the answer, with every skill of the
    journey loaded, must pass its checks. With `baseline`, the journey also runs without any skill:
    if it passes then too, its checks do not test the skills (reported, not failed). This tests that the skills hand over to each other
    (names, tables and parameters line up). It cannot test whether Genie Code loads a skill
    named in another skill's steps; the Genie Code checklist covers that."""
    model = std.eval.get("model_endpoint")
    judge_ep = std.eval.get("judge_endpoint", model)
    threshold = float(threshold if threshold is not None else std.eval.get("trigger_threshold", 0.5))
    runs = max(1, int(runs))
    by_name = {s.name: s for s in all_skills}
    catalog_text = catalog_for_routing(root, all_skills, installed)
    results, warnings = [], []
    for j in journeys:
        missing = [n for n in j["skills"] if n not in by_name]
        res = CaseResult(skill="journey", case_id=j["id"], case_type="journey")
        log(f"  journey / {j['id']}")
        if missing or not j["skills"]:
            warnings.append(f"journey {j['id']}: unknown skill(s) {', '.join(missing) or '(none listed)'}")
            results.append(res)
            continue
        entry = j["skills"][0]
        skills = [by_name[n] for n in j["skills"]]
        limit = max([s.eval_max_tokens or 0 for s in skills] + [int(std.eval.get("max_tokens", 2000))])

        routing_key = _key("journey-routing", model, ROUTER_SYSTEM, catalog_text, j, runs, threshold)
        hit = _reuse(cache, routing_key, refresh_failed, "routing_pass")
        if hit:
            for name in ROUTING_FIELDS:
                setattr(res, name, hit.get(name))
        else:
            picks = []
            for _ in range(runs):
                reply = parse_json(llm.complete(model, ROUTER_SYSTEM,
                                                f"Installed skills:\n{catalog_text}\n\nUser request:\n{j['prompt']}", 200))
                picks.append(str(reply.get("skill", "")).strip() or "unparsed")
            res.routing_expected = entry
            res.routing_got = max(set(picks), key=picks.count)
            res.routing_rate = picks.count(entry) / runs
            res.routing_pass = res.routing_rate >= threshold
            if cache is not None:
                cache[routing_key] = {name: getattr(res, name) for name in ROUTING_FIELDS}

        context, warn = _context_block(root, j, repos_root, drafts_root)
        warnings += warn
        loaded = "".join(f"\n\n# Skill loaded: {s.name}\n{s.reference_text()}" for s in skills)
        answer_key = _key("journey-answer", model, judge_ep, AGENT_SYSTEM, JUDGE_SYSTEM, context, loaded, j, limit,
                          runs, getattr(checker, "signature", None), baseline)
        hit = _reuse(cache, answer_key, refresh_failed, "with_skill_pass")
        if hit:
            for name in ANSWER_FIELDS:
                setattr(res, name, hit.get(name))
        else:
            res.max_tokens = limit
            (res.with_skill_pass, res.with_skill_notes, res.with_skill_answer, res.with_skill_tokens,
             res.with_skill_truncated, res.with_skill_sql) = _arm(llm, model, AGENT_SYSTEM + "\n\n" + context + loaded,
                                                                  j, judge_ep, limit, runs, checker)
            if baseline:
                (res.baseline_pass, res.baseline_notes, res.baseline_answer, res.baseline_tokens,
                 res.baseline_truncated, res.baseline_sql) = _arm(llm, model, AGENT_SYSTEM + "\n\n" + context,
                                                                  j, judge_ep, limit, runs, checker)
            if cache is not None:
                cache[answer_key] = {name: getattr(res, name) for name in ANSWER_FIELDS}
        if res.with_skill_pass and res.baseline_pass:
            warnings.append(f"journey {j['id']}: passes without any skill too, so it does not test the skills; "
                            "check something only the skills provide (a helper, a table name, a hand-over)")
        results.append(res)
    return results, warnings


def journeys_markdown(results: list[CaseResult]) -> str:
    if not results:
        return ""
    lines = ["", "### Journeys", "",
             "Each journey loads all its skills; it shows whether they hand over to each other. Whether Genie Code "
             "loads a skill named in another skill's steps is checked with `skillkit genie-checklist`.", "",
             "| Journey | Routing to first skill | Answer | Without skills | Notes |", "| --- | --- | --- | --- | --- |"]
    for r in results:
        routing = "-" if r.routing_pass is None else ("pass" if r.routing_pass else "FAIL") + f" ({r.routing_got})"
        answer = "-" if r.with_skill_pass is None else ("pass" if r.with_skill_pass else "FAIL")
        if r.with_skill_pass is None and r.with_skill_truncated:
            answer = "cut off"
        notes = "; ".join(([f"SQL: {r.with_skill_sql}"] if r.with_skill_sql else []) + r.with_skill_notes[:3])
        without = "-" if r.baseline_pass is None else ("pass (no effect)" if r.baseline_pass and r.with_skill_pass
                                                      else "pass" if r.baseline_pass else "FAIL")
        lines.append(f"| `{r.case_id}` | {routing} | {answer} | {without} | {notes.replace('|', chr(92) + '|')} |")
    return "\n".join(lines) + "\n"


def journeys_failing(results: list[CaseResult]) -> bool:
    return any(r.routing_pass is False or r.with_skill_pass is False for r in results)
