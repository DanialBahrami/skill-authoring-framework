"""skillkit: the meta-skill's checks. Run `skillkit <command> --help` for options.

From a notebook or Genie Code, without installing anything:

    import sys; sys.path.insert(0, "<skill folder>/scripts")
    from skillkit.cli import main
    main(["--root", "<output folder>", "lint"])
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

from . import lint
from .model import (EXAMPLE_INSTRUCTIONS_HELP, estimate_tokens, find_repo_root,
                    instructions_for_evals, is_example_instructions, load_installed, load_skills, load_standard,
                    templates_dir, workspace_instructions_path)


def _ctx(args):
    root = Path(args.root).resolve() if args.root else find_repo_root()
    return root, load_standard(root)


def _print_findings(findings) -> int:
    errors = [f for f in findings if f.severity == "error"]
    for f in findings:
        print(f)
    print(f"\n{len(errors)} error(s), {len(findings) - len(errors)} warning(s)")
    return 1 if errors else 0


def cmd_lint(args) -> int:
    root, std = _ctx(args)
    skills = load_skills(root)
    targets = [s for s in skills if not args.skills or s.name in args.skills]
    by_name = {s.name: s for s in skills}
    findings = []
    for skill in targets:
        findings += lint.lint_skill(skill, std)
        findings += lint.lint_uses(skill, by_name)
    if not args.skills:
        findings += lint.lint_catalog(skills, std)
        if workspace_instructions_path(root).is_file():   # a Git copy exists only in a context repo (ops/)
            findings += lint.lint_workspace_instructions(workspace_instructions_path(root), std)
        findings += lint.lint_journeys(root, skills)
    return _print_findings(findings)


def cmd_lint_agents(args) -> int:
    _, std = _ctx(args)
    findings = []
    for path in args.files:
        findings += lint.lint_agents_md(Path(path), std)
    return _print_findings(findings)


def cmd_catalog(args) -> int:
    root, std = _ctx(args)
    skills = load_skills(root)
    budget = std.limit("catalog_max_tokens")
    superseded = {n for s in skills if s.status != "deprecated" for n in s.supersedes}
    active = planned = 0
    print(f"{'skill':40} {'status':11} {'owner':20} tokens")
    for s in skills:
        tokens = estimate_tokens(f"{s.name}: {s.description}")
        active += tokens if s.status == "active" else 0
        planned += tokens if s.status in ("active", "draft") and s.name not in superseded else 0
        note = "  (superseded)" if s.name in superseded else ""
        print(f"{s.name:40} {s.status:11} {s.owner:20} {tokens}{note}")
    installed = load_installed(Path(args.installed), {s.name for s in skills}) if args.installed else []
    kept = 0
    if installed:
        print(f"\ninstalled in {args.installed}, not from this repo:")
        for i in installed:
            tokens = estimate_tokens(f"{i.name}: {i.description}")
            retired = i.name in superseded
            kept += 0 if retired else tokens
            print(f"{i.name:40} {'superseded' if retired else 'installed':11} {'':20} {tokens}")
    print(f"\nactive catalog: about {active} of {budget} tokens")
    print(f"planned (active + drafts, minus superseded): about {planned} of {budget} tokens")
    if installed:
        print(f"planned + installed skills that stay: about {planned + kept} of {budget} tokens")
        _print_overlaps([s for s in skills if s.status != "deprecated" and s.name not in superseded],
                        [i for i in installed if i.name not in superseded], std)
    text, where = instructions_for_evals(root)
    if text:
        print(f"workspace instructions ({where}): about {estimate_tokens(text)} of "
              f"{std.limit('workspace_instructions_max_tokens')} tokens")
    return 0


def _print_overlaps(skills, installed, std) -> None:
    """Repo skills whose descriptions overlap installed ones: they compete for the same prompts."""
    threshold = float(std.raw.get("catalog", {}).get("overlap_warning", 0.5))

    def words(text: str) -> set[str]:
        return {w for w in lint.WORD_RE.findall(text.lower()) if w not in lint.STOPWORDS}

    hits = []
    for s in skills:
        ws = words(s.description)
        for i in installed:
            wi = words(i.description)
            if ws and wi and len(ws & wi) / len(ws | wi) >= threshold:
                hits.append((s.name, i.name, len(ws & wi) / len(ws | wi)))
    if hits:
        print("\noverlap with installed skills (add `supersedes:` to skill.yaml to plan their retirement):")
        for a, b, j in sorted(hits, key=lambda h: -h[2]):
            print(f"  {a} ~ {b} ({j:.0%})")


def cmd_check_names(args) -> int:
    from .names import check_skill, index_repo

    root, _ = _ctx(args)
    skills = load_skills(root)
    targets = [s for s in skills if not args.skills or s.name in args.skills]
    idxs = [index_repo(Path(r)) for r in args.repo]
    names = {s.name for s in skills}
    total = 0
    for skill in targets:
        missing = check_skill(skill, idxs, names, set(args.ignore or []))
        total += len(missing)
        for rel, name in missing:
            print(f"NOT FOUND {skill.name}/{rel}: `{name}`")
    print(f"\n{total} name(s) not found in {', '.join(args.repo)}. Check each: fix it, or keep it if it "
          "legitimately appears in no file (a value the user types, a workspace group).")
    return 1 if total and args.strict else 0


def cmd_genie_checklist(args) -> int:
    from .checklist import checklist_markdown

    root, _ = _ctx(args)
    skills = load_skills(root, args.skills or None)
    if not args.skills:
        skills = [s for s in skills if s.status != "deprecated"]
    from .evals import load_journeys

    names = {s.name for s in skills}
    journeys = [j for j in load_journeys(root) if set(j["skills"]) & names]
    md = checklist_markdown(skills, args.prompts, journeys)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(md)
    return 0


def cmd_new(args) -> int:
    root, std = _ctx(args)
    name = args.name
    team = std.team_for_prefix(name)
    if team is None:
        print(f"prefix of '{name}' is not registered in standard.yaml", file=sys.stderr)
        return 1
    target = root / "skills" / name
    if target.exists():
        print(f"{target} already exists", file=sys.stderr)
        return 1
    shutil.copytree(templates_dir() / "skill", target)
    for path in target.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            text = (text.replace("{{name}}", name).replace("{{owner}}", team)
                    .replace("{{today}}", dt.date.today().isoformat()))
            path.write_text(text, encoding="utf-8")
    print(f"created {target.relative_to(root)} (owner {team}, status draft)")
    return 0


def _refuse_example_instructions(root, args) -> None:
    if is_example_instructions(root) and not getattr(args, "allow_example_instructions", False):
        raise SystemExit(f"{EXAMPLE_INSTRUCTIONS_HELP}\nEvals inject this file into every answer, so their verdicts "
                         "would reflect the example. Use --allow-example-instructions only to try the framework itself.")


def _checker(args, std):
    """The execution gate, when --execute is given: EXPLAIN on a development SQL warehouse."""
    if not getattr(args, "execute", False):
        return None
    import os

    from .execute import SqlChecker, spark_runner, warehouse_runner

    conf = std.eval.get("execution", {}) or {}
    warehouse = args.warehouse_id or os.environ.get("DATABRICKS_WAREHOUSE_ID") or conf.get("warehouse_id")
    variables = {str(k): str(v) for k, v in (conf.get("variables", {}) or {}).items()}
    for pair in args.sql_var or []:
        key, _, value = pair.partition("=")
        variables[key.strip()] = value.strip()
    catalogs = conf.get("catalogs")
    runner = warehouse_runner(warehouse, profile=args.profile) if warehouse else spark_runner()
    signature = json.dumps({"warehouse": warehouse or "spark", "variables": variables, "catalogs": catalogs},
                           sort_keys=True)
    print(f"execution gate on ({'warehouse ' + warehouse if warehouse else 'Spark session'}): "
          "EXPLAIN and DESCRIBE TABLE only")
    return SqlChecker(runner, variables, signature, catalogs)


def cmd_eval(args) -> int:
    from .evals import (ServingLLM, journeys_failing, journeys_markdown, load_journeys, report_markdown,
                        results_json, run_evals, run_journeys)

    root, std = _ctx(args)
    _refuse_example_instructions(root, args)
    all_skills = load_skills(root)
    if args.skills:
        targets = [s for s in all_skills if s.name in set(args.skills)]
    else:
        targets = [s for s in all_skills if s.status == "active"]
    if not targets:
        print("no skills to evaluate")
        return 0
    if args.model:
        std.raw.setdefault("eval", {})["model_endpoint"] = args.model
    if args.judge:
        std.raw.setdefault("eval", {})["judge_endpoint"] = args.judge
    from .evals import load_cache, save_cache

    installed = load_installed(Path(args.installed), {s.name for s in all_skills}) if args.installed else []
    cache = None if args.no_cache else load_cache(root)
    checker = _checker(args, std)
    llm = ServingLLM(profile=args.profile)
    print(f"evaluating {len(targets)} skill(s); routing against {len(all_skills)} repo skill(s)"
          + (f" and {len(installed)} installed" if installed else ""))
    results, verdicts, warnings = run_evals(
        root, std, all_skills, targets, llm, mode=args.mode, baseline=not args.no_baseline,
        repos_root=Path(args.repos_root) if args.repos_root else None, case_filter=args.case_filter,
        runs=args.runs, threshold=args.threshold, installed=installed,
        drafts_root=Path(args.agents_drafts) if args.agents_drafts else None,
        cache=cache, refresh_failed=args.refresh_failed, checker=checker)
    journeys = [] if args.no_journeys else load_journeys(root)
    if args.skills:   # journeys that involve a skill under evaluation
        journeys = [j for j in journeys if set(j["skills"]) & set(args.skills)]
    journey_results = []
    if journeys and args.mode == "all":
        journey_results, jwarn = run_journeys(
            root, std, all_skills, journeys, llm, repos_root=Path(args.repos_root) if args.repos_root else None,
            drafts_root=Path(args.agents_drafts) if args.agents_drafts else None, runs=args.runs,
            threshold=args.threshold, installed=installed, cache=cache, refresh_failed=args.refresh_failed,
            checker=checker, baseline=not args.no_baseline)
        warnings += jwarn
    if cache is not None:
        save_cache(root, cache)
    md = report_markdown(results, verdicts, warnings, std) + journeys_markdown(journey_results)
    if checker is not None:
        md += "\nExecution gate: SQL in answers was planned with EXPLAIN on the development warehouse; " \
              "a statement that does not plan fails the run.\n"
    print(md)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(results_json(results, verdicts), encoding="utf-8")
    if args.inspect:
        for r in results:
            if r.case_id == args.inspect:
                print(f"\n=== {r.skill}/{r.case_id} with skill ===\n{r.with_skill_answer}")
                print(f"\n=== without skill ===\n{r.baseline_answer}")
    # INCONCLUSIVE also fails: nothing was verified, so it must not pass a blocking gate
    failing = any(v.verdict in ("FAILING", "INCONCLUSIVE") for v in verdicts) or journeys_failing(journey_results)
    no_effect = any(v.verdict == "NO EFFECT" for v in verdicts)
    return 1 if failing or (no_effect and args.require_value) else 0


def cmd_eval_context(args) -> int:
    from .evals import ServingLLM, report_markdown, run_context_evals

    root, std = _ctx(args)
    if args.model:
        std.raw.setdefault("eval", {})["model_endpoint"] = args.model
    if not args.repos_root and not args.agents_drafts:
        print("give --repos-root, --agents-drafts or both", file=sys.stderr)
        return 2
    _refuse_example_instructions(root, args)
    llm = ServingLLM(profile=args.profile)
    results, summary, warnings = run_context_evals(
        root, std, Path(args.cases), llm, repos_root=Path(args.repos_root) if args.repos_root else None,
        runs=args.runs, drafts_root=Path(args.agents_drafts) if args.agents_drafts else None,
        checker=_checker(args, std))
    md = report_markdown(results, [summary], warnings, std).replace("Answers with skill", "With AGENTS.md") \
        .replace("Answers without skill", "Without AGENTS.md")
    print(md)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
    return 1 if summary.verdict == "FAILING" else 0


def _execution_args(s) -> None:
    s.add_argument("--allow-example-instructions", action="store_true",
                   help="run although context/workspace-instructions.md is still the framework's example")
    s.add_argument("--execute", action="store_true",
                   help="execution gate: plan the SQL in each answer with EXPLAIN on a development SQL warehouse")
    s.add_argument("--warehouse-id", help="SQL warehouse for --execute (or DATABRICKS_WAREHOUSE_ID); "
                   "without one, the active Spark session is used (in a notebook)")
    s.add_argument("--sql-var", action="append", metavar="NAME=VALUE",
                   help="value for ${NAME}, {{NAME}}, {NAME} or :NAME in generated SQL, e.g. catalog=dev_catalog")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="skillkit", description=__doc__)
    p.add_argument("--root", help="output folder holding skills/ (default: found from the current folder)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("lint", help="check skills, catalog budget and workspace instructions")
    s.add_argument("skills", nargs="*", help="only these skills (catalog checks run when none are given)")
    s.set_defaults(func=cmd_lint)

    s = sub.add_parser("lint-agents", help="check AGENTS.md files from a source repo")
    s.add_argument("files", nargs="+")
    s.set_defaults(func=cmd_lint_agents)

    s = sub.add_parser("catalog", help="list skills and token budgets (active, planned, with installed skills)")
    s.add_argument("--installed", help="installed skills folder, e.g. /Workspace/.assistant/skills in a notebook "
                   "or a local export of it; counts its skills in the budget and checks overlap")
    s.set_defaults(func=cmd_catalog)

    s = sub.add_parser("check-names", help="report names in skills that are not found in the source repos")
    s.add_argument("skills", nargs="*", help="only these skills (default: all)")
    s.add_argument("--repo", action="append", required=True, help="source repo checkout; repeat for several")
    s.add_argument("--strict", action="store_true", help="exit 1 when a name is not found")
    s.add_argument("--ignore", nargs="*", help="names that legitimately appear in no file (from docs, typed by users)")
    s.set_defaults(func=cmd_check_names)

    s = sub.add_parser("genie-checklist", help="prompts to paste in Genie Code and what to look for, per skill")
    s.add_argument("skills", nargs="*", help="only these skills (default: all not deprecated)")
    s.add_argument("--prompts", type=int, default=2, help="trigger prompts per skill")
    s.add_argument("--out", help="write the checklist here, e.g. authoring/runs/<run>/genie-check.md")
    s.set_defaults(func=cmd_genie_checklist)

    s = sub.add_parser("new", help="scaffold a draft skill from the meta-skill's skill template")
    s.add_argument("name")
    s.set_defaults(func=cmd_new)

    s = sub.add_parser("eval", help="run routing and answer evals, with a no-skill baseline")
    s.add_argument("skills", nargs="*", help="skills to evaluate (default: all active)")
    s.add_argument("--mode", choices=["all", "routing", "answer"], default="all")
    s.add_argument("--no-baseline", action="store_true")
    s.add_argument("--require-value", action="store_true", help="fail when a skill shows NO EFFECT")
    s.add_argument("--case-filter", help="regex on case ids")
    s.add_argument("--repos-root", help="folder holding source repo checkouts, for AGENTS.md context")
    s.add_argument("--installed", help="installed skills folder; its skills join the routing catalog")
    s.add_argument("--agents-drafts", help="AGENTS.md drafts laid out like --repos-root (e.g. <run folder>/agents-md); "
                   "used instead of the repo's files where present")
    s.add_argument("--no-cache", action="store_true", help="ignore and do not update .skillkit-cache/")
    s.add_argument("--refresh-failed", action="store_true",
                   help="re-run cases that failed or were inconclusive, even if their inputs did not change")
    s.add_argument("--no-journeys", action="store_true", help="skip evals/journeys.json")
    _execution_args(s)
    s.add_argument("--model"), s.add_argument("--judge")
    s.add_argument("--runs", type=int, default=1, help="runs per case; routing uses the trigger rate, answers the majority")
    s.add_argument("--threshold", type=float, help="trigger rate threshold (default from standard.yaml, 0.5)")
    s.add_argument("--profile")
    s.add_argument("--out", help="write the markdown report here")
    s.add_argument("--json", help="write full results (including answers) here")
    s.add_argument("--inspect", help="print both answers for this case id")
    s.set_defaults(func=cmd_eval)

    s = sub.add_parser("eval-context", help="evaluate AGENTS.md files: cases with and without them")
    s.add_argument("--cases", required=True, help="cases file, e.g. context/evals/data-platform.json")
    s.add_argument("--repos-root", help="folder holding source repo checkouts")
    s.add_argument("--agents-drafts", help="AGENTS.md drafts laid out like --repos-root, e.g. <run folder>/agents-md")
    s.add_argument("--runs", type=int, default=1)
    _execution_args(s)
    s.add_argument("--model"), s.add_argument("--profile"), s.add_argument("--out")
    s.set_defaults(func=cmd_eval_context)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
