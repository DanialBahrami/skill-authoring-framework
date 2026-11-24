"""skillkit command line. Run `skillkit <command> --help` for options."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

from . import build as build_mod
from . import freshness, lint
from .model import estimate_tokens, find_repo_root, load_skills, load_standard, workspace_instructions_path


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
        findings += lint.lint_workspace_instructions(workspace_instructions_path(root), std)
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
    total = 0
    print(f"{'skill':40} {'status':11} {'owner':20} tokens")
    for s in skills:
        tokens = estimate_tokens(f"{s.name}: {s.description}")
        if s.status == "active":
            total += tokens
        print(f"{s.name:40} {s.status:11} {s.owner:20} {tokens}")
    print(f"\nactive catalog: about {total} of {std.limit('catalog_max_tokens')} tokens")
    wi = workspace_instructions_path(root)
    if wi.is_file():
        print(f"workspace instructions: about {estimate_tokens(wi.read_text(encoding='utf-8'))} of "
              f"{std.limit('workspace_instructions_max_tokens')} tokens")
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
    shutil.copytree(root / "templates" / "skill", target)
    for path in target.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            text = (text.replace("{{name}}", name).replace("{{owner}}", team)
                    .replace("{{today}}", dt.date.today().isoformat()))
            path.write_text(text, encoding="utf-8")
    print(f"created {target.relative_to(root)} (owner {team}, status draft)")
    return 0


def cmd_build(args) -> int:
    root, std = _ctx(args)
    skills = load_skills(root)
    by_name = {s.name: s for s in skills}
    findings = [f for s in skills if s.status == "active" for f in lint.lint_skill(s, std) + lint.lint_uses(s, by_name)]
    findings += lint.lint_catalog(skills, std) + lint.lint_workspace_instructions(workspace_instructions_path(root), std)
    if any(f.severity == "error" for f in findings):
        _print_findings(findings)
        print("build refused: fix lint errors first", file=sys.stderr)
        return 1
    manifest = build_mod.build(root, skills, Path(args.out))
    print(json.dumps(manifest, indent=2))
    return 0


def cmd_deploy(args) -> int:
    _, std = _ctx(args)
    actions = build_mod.deploy(Path(args.build), std, dry_run=args.dry_run, prune=not args.no_prune,
                               profile=args.profile)
    prefix = "[dry run] " if args.dry_run else ""
    for action in actions:
        print(prefix + action)
    return 0


def cmd_freshness(args) -> int:
    root, _ = _ctx(args)
    changed = list(args.changed or [])
    if args.changed_file:
        changed += Path(args.changed_file).read_text(encoding="utf-8").splitlines()
    skills = load_skills(root)
    hits = freshness.affected_skills(skills, args.repo, changed)
    owners = {s.name: s.owner for s in skills}
    if args.format == "json":
        print(json.dumps({"repo": args.repo, "skills": hits}, indent=2))
    elif args.format == "markdown":
        if hits:
            print("### Genie Code skills that may need an update\n")
            print(f"This change touches files that these skills were written from (repo `{args.repo}`). "
                  "Check whether the skill still matches; if not, update it in `genie-context` "
                  "(the generator's update mode can draft the change).\n")
            print("| Skill | Owner | Changed files |\n| --- | --- | --- |")
            for name, paths in sorted(hits.items()):
                shown = ", ".join(f"`{p}`" for p in paths[:5]) + (" ..." if len(paths) > 5 else "")
                print(f"| `{name}` | {owners.get(name, '')} | {shown} |")
    else:
        for name, paths in sorted(hits.items()):
            print(f"{name}: {', '.join(paths)}")
    return 1 if (hits and args.fail_on_match) else 0


def cmd_changed(args) -> int:
    root, _ = _ctx(args)
    names = [s.name for s in load_skills(root) if s.status != "deprecated"]
    print(" ".join(freshness.changed_skills(root, args.base, names)))
    return 0


def cmd_stale(args) -> int:
    root, std = _ctx(args)
    stale = freshness.stale_skills(load_skills(root), std.review_period_days)
    for name, why in stale:
        print(f"STALE {name}: {why}")
    print(f"{len(stale)} skill(s) past the {std.review_period_days}-day review period")
    return 1 if stale else 0


def cmd_reviewed(args) -> int:
    root, _ = _ctx(args)
    for skill in load_skills(root, args.skills):
        freshness.mark_reviewed(skill)
        print(f"{skill.name}: last_reviewed set to today")
    return 0


def cmd_confluence(args) -> int:
    root, _ = _ctx(args)
    skills = load_skills(root, args.skills or None)
    changes = freshness.confluence_changes(skills)
    for c in changes:
        note = f" ({c['note']})" if c["note"] else ""
        print(f"CHANGED {c['skill']}: page {c['page_id']} '{c['title']}' recorded v{c['recorded']}, now v{c['current']}{note}")
    if args.write:
        by_skill: dict[str, dict[str, int]] = {}
        for c in changes:
            if c["current"] is not None:
                by_skill.setdefault(c["skill"], {})[str(c["page_id"])] = c["current"]
        for skill in skills:
            if skill.name in by_skill:
                freshness.write_confluence_versions(skill, by_skill[skill.name])
                print(f"{skill.name}: recorded versions updated")
        return 0
    print(f"{len(changes)} changed page(s)")
    return 1 if changes else 0


def cmd_eval(args) -> int:
    from .evals import ServingLLM, report_markdown, results_json, run_evals

    root, std = _ctx(args)
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
    llm = ServingLLM(profile=args.profile)
    print(f"evaluating {len(targets)} skill(s)")
    results, verdicts, warnings = run_evals(
        root, std, all_skills, targets, llm, mode=args.mode, baseline=not args.no_baseline,
        repos_root=Path(args.repos_root) if args.repos_root else None, case_filter=args.case_filter,
        runs=args.runs, threshold=args.threshold)
    md = report_markdown(results, verdicts, warnings, std)
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
    failing = any(v.verdict == "FAILING" for v in verdicts)
    no_effect = any(v.verdict == "NO EFFECT" for v in verdicts)
    return 1 if failing or (no_effect and args.require_value) else 0


def cmd_eval_context(args) -> int:
    from .evals import ServingLLM, report_markdown, run_context_evals

    root, std = _ctx(args)
    if args.model:
        std.raw.setdefault("eval", {})["model_endpoint"] = args.model
    llm = ServingLLM(profile=args.profile)
    results, summary, warnings = run_context_evals(root, std, Path(args.cases), llm,
                                                   repos_root=Path(args.repos_root), runs=args.runs)
    md = report_markdown(results, [summary], warnings, std).replace("Answers with skill", "With AGENTS.md") \
        .replace("Answers without skill", "Without AGENTS.md")
    print(md)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
    return 1 if summary.verdict == "FAILING" else 0


def cmd_reviewers(args) -> int:
    """Print the path filters to configure as automatically included reviewers in Azure DevOps."""
    _, std = _ctx(args)
    platform = std.teams.get(std.platform_team, {}).get("reviewers", std.platform_team)
    print("Branch policy > Automatically included reviewers (Required):\n")
    print(f"{platform:40} /skills/*; /context/*; /standard.yaml; /skillkit/*; /pipelines/*")
    for prefix, team in sorted(std.prefixes.items()):
        reviewers = std.teams.get(team, {}).get("reviewers", team)
        print(f"{reviewers:40} /skills/{prefix}-*")
    print("\nVariant reference files owned by another team: add that team for the specific path, e.g.")
    print("  /skills/dp-create-silver-table/references/forecasting.md")
    print("\nSeparation of duties: in the branch policy, require at least one reviewer, turn off")
    print("'Allow requestors to approve their own changes' and turn on 'Prohibit the most recent pusher")
    print("from approving their own changes'. Skill authors must not be their own reviewers.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="skillkit", description=__doc__)
    p.add_argument("--root", help="genie-context repo root (default: found from the current folder)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("lint", help="check skills, catalog budget and workspace instructions")
    s.add_argument("skills", nargs="*", help="only these skills (catalog checks run when none are given)")
    s.set_defaults(func=cmd_lint)

    s = sub.add_parser("lint-agents", help="check AGENTS.md files from a source repo")
    s.add_argument("files", nargs="+")
    s.set_defaults(func=cmd_lint_agents)

    s = sub.add_parser("catalog", help="list skills and token budgets")
    s.set_defaults(func=cmd_catalog)

    s = sub.add_parser("new", help="scaffold a skill from templates/skill")
    s.add_argument("name")
    s.set_defaults(func=cmd_new)

    s = sub.add_parser("build", help="build the deployable bundle (active skills + workspace instructions)")
    s.add_argument("--out", default="build")
    s.set_defaults(func=cmd_build)

    s = sub.add_parser("deploy", help="upload a build to the workspace")
    s.add_argument("--build", default="build")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--no-prune", action="store_true", help="keep workspace skills that are not in the build")
    s.add_argument("--profile", help="Databricks CLI profile (default: environment variables)")
    s.set_defaults(func=cmd_deploy)

    s = sub.add_parser("freshness", help="list skills whose sources match changed files")
    s.add_argument("--repo", required=True, help="source repo name as written in skill.yaml sources")
    s.add_argument("--changed", nargs="*", help="changed paths, relative to the source repo root")
    s.add_argument("--changed-file", help="file with one changed path per line")
    s.add_argument("--format", choices=["text", "markdown", "json"], default="text")
    s.add_argument("--fail-on-match", action="store_true")
    s.set_defaults(func=cmd_freshness)

    s = sub.add_parser("changed", help="skills touched since a git base (for PR evals)")
    s.add_argument("--base", default="origin/main")
    s.set_defaults(func=cmd_changed)

    s = sub.add_parser("stale", help="active skills past the review period")
    s.set_defaults(func=cmd_stale)

    s = sub.add_parser("reviewed", help="set last_reviewed to today")
    s.add_argument("skills", nargs="+")
    s.set_defaults(func=cmd_reviewed)

    s = sub.add_parser("confluence-check", help="compare recorded Confluence page versions with the live pages")
    s.add_argument("skills", nargs="*")
    s.add_argument("--write", action="store_true", help="record the current versions (after review)")
    s.set_defaults(func=cmd_confluence)

    s = sub.add_parser("eval", help="run routing and answer evals, with a no-skill baseline")
    s.add_argument("skills", nargs="*", help="skills to evaluate (default: all active)")
    s.add_argument("--mode", choices=["all", "routing", "answer"], default="all")
    s.add_argument("--no-baseline", action="store_true")
    s.add_argument("--require-value", action="store_true", help="fail when a skill shows NO EFFECT")
    s.add_argument("--case-filter", help="regex on case ids")
    s.add_argument("--repos-root", help="folder holding source repo checkouts, for AGENTS.md context")
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
    s.add_argument("--repos-root", required=True, help="folder holding source repo checkouts")
    s.add_argument("--runs", type=int, default=1)
    s.add_argument("--model"), s.add_argument("--profile"), s.add_argument("--out")
    s.set_defaults(func=cmd_eval_context)

    s = sub.add_parser("reviewers", help="print Azure DevOps required-reviewer path filters")
    s.set_defaults(func=cmd_reviewers)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
