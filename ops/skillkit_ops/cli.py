"""skillkit-ops: build, deploy and keep skills current. For running the context repo at scale;
not needed to create skills. Run `skillkit-ops <command> --help` for options."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

from skillkit import lint
from skillkit.model import (EXAMPLE_INSTRUCTIONS_HELP, find_repo_root, is_example_instructions, load_skills,
                            load_standard, workspace_instructions_path)

from . import build as build_mod
from . import freshness


def _ctx(args):
    root = Path(args.root).resolve() if args.root else find_repo_root()
    return root, load_standard(root)


def _print_findings(findings) -> int:
    errors = [f for f in findings if f.severity == "error"]
    for f in findings:
        print(f)
    print(f"\n{len(errors)} error(s), {len(findings) - len(errors)} warning(s)")
    return 1 if errors else 0


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
    if is_example_instructions(root):
        print(f"build refused: {EXAMPLE_INSTRUCTIONS_HELP} Deploying it would replace the workspace's real "
              "instructions with the example.", file=sys.stderr)
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
                  "(the context-authoring meta-skill's update mode can draft the change).\n")
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
    skills = [s for s in load_skills(root) if s.status != "deprecated"]
    names = [s.name for s in skills]
    uses = {s.name: s.uses for s in skills}
    print(" ".join(freshness.changed_skills(root, args.base, names, uses)))
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


def cmd_reviewers(args) -> int:
    """Print who must review which paths: a GitHub CODEOWNERS file or Azure DevOps branch-policy filters."""
    _, std = _ctx(args)

    def owner(team: str, key: str) -> str:
        return str(std.teams.get(team, {}).get(key) or team)

    platform = std.platform_team
    if args.format == "codeowners":
        print("# Generated by `skillkit-ops reviewers --format codeowners`. Save as .github/CODEOWNERS,")
        print("# then require code-owner review in the branch protection rule for main.")
        print(f"*  {owner(platform, 'codeowners')}")
        for prefix, team in sorted(std.prefixes.items()):
            print(f"/skills/{prefix}-*/  {owner(team, 'codeowners')}")
        print("# Variant reference files owned by another team, for example:")
        print("# /skills/dp-create-silver-table/references/forecasting.md  @my-org/forecasting")
        print("\n# Separation of duties: require at least one approval and enable 'Require review from")
        print("# Code Owners'; authors cannot approve their own pull requests on GitHub.")
        return 0
    print("Branch policy > Automatically included reviewers (Required):\n")
    print(f"{owner(platform, 'reviewers'):40} /*")
    for prefix, team in sorted(std.prefixes.items()):
        print(f"{owner(team, 'reviewers'):40} /skills/{prefix}-*")
    print("\nVariant reference files owned by another team: add that team for the specific path, e.g.")
    print("  /skills/dp-create-silver-table/references/forecasting.md")
    print("\nSeparation of duties: require at least one reviewer, turn off 'Allow requestors to approve")
    print("their own changes' and turn on 'Prohibit the most recent pusher from approving their own changes'.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="skillkit-ops", description=__doc__)
    p.add_argument("--root", help="context repo root (default: found from the current folder)")
    sub = p.add_subparsers(dest="command", required=True)

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

    s = sub.add_parser("changed", help="skills touched since a git base, plus skills that use them (for PR evals)")
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

    s = sub.add_parser("reviewers", help="print who must review which paths (CODEOWNERS or Azure DevOps)")
    s.add_argument("--format", choices=["codeowners", "azure-devops"], default="codeowners")
    s.set_defaults(func=cmd_reviewers)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
