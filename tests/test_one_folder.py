"""The meta-skill as one installable folder: defaults, live workspace instructions, asset lint,
and a dry run of every script from an installed copy of the skill."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from skillkit import lint
from skillkit.evals import load_decoys
from skillkit.model import instructions_for_evals, load_skill, load_standard

from conftest import GOOD_EVALS, GOOD_SKILL_MD, REPO


def _skill(folder: Path, name: str = "xy-prepare-pull-request") -> Path:
    skill = folder / "skills" / name
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text(GOOD_SKILL_MD.replace("dp-prepare-pr", name))
    (skill / "references" / "title-codes.md").write_text("# Title codes\n\n- FEAT: feature\n")
    (skill / "skill.yaml").write_text("owner: anyone\nstatus: draft\nlast_reviewed: 2026-11-01\n"
                                      "sources:\n  - repo: some-repo\n    paths: [x.py]\n")
    (skill / "evals").mkdir()
    (skill / "evals" / "evals.json").write_text(GOOD_EVALS.replace("dp-prepare-pr", name))
    return skill


def test_empty_output_folder_uses_the_skill_defaults(tmp_path: Path):
    std = load_standard(tmp_path)
    assert std.prefixes == {} and std.raw["catalog"]["installed_skills"] == "ignore"
    skill = load_skill(_skill(tmp_path))
    codes = {f.code for f in lint.lint_skill(skill, std) if f.severity == "error"}
    assert not codes & {"SK004", "SK014"}, codes          # any prefix and owner are fine without teams
    assert load_decoys(tmp_path)                           # the skill's default decoys


def test_output_folder_standard_overrides_only_what_it_sets(tmp_path: Path):
    (tmp_path / "standard.yaml").write_text("limits:\n  body_max_lines: 80\nprefixes:\n  dp: data-platform\n")
    std = load_standard(tmp_path)
    assert std.limit("body_max_lines") == 80 and std.limit("description_max_chars") == 600
    assert std.prefixes == {"dp": "data-platform"}


def test_evals_read_live_instructions_unless_there_is_a_git_copy(tmp_path: Path):
    live = tmp_path / "live-instructions.md"
    live.write_text("# Live\n- Use the dev catalog through ${catalog}.\n")
    (tmp_path / "standard.yaml").write_text(f"workspace:\n  instructions_path: {live}\n")
    text, where = instructions_for_evals(tmp_path)
    assert "Live" in text and where == live.as_posix()
    (tmp_path / "context").mkdir()
    (tmp_path / "context" / "workspace-instructions.md").write_text("# Git copy\n")
    text, where = instructions_for_evals(tmp_path)
    assert text == "# Git copy\n" and where.endswith("context/workspace-instructions.md")


def test_asset_lint(tmp_path: Path):
    skill = _skill(tmp_path)
    assets = skill / "assets"
    assets.mkdir()
    (assets / "ok_notebook.py").write_text("# Databricks notebook source\n%run ../setup\n"
                                           "df = spark.table('<source_table>')\n")
    (assets / "ok_job.yml").write_text("resources:\n  jobs:\n    load:\n      name: {{job_name}}\n")
    (assets / "broken.py").write_text("def f(:\n    pass\n")
    (assets / "broken.yml").write_text("jobs: [unclosed\n")
    (assets / "broken.json").write_text("{\"a\": }")
    msgs = [f.message for f in lint.lint_assets(load_skill(skill))]
    assert len(msgs) == 3 and {m.split()[0] for m in msgs} == {"Python", "YAML", "JSON"}


DRIVER = """
import json, sys
sys.path.insert(0, sys.argv[1])
from skillkit import evals
from skillkit.cli import main

class Fake:
    last_tokens = None
    last_truncated = False
    def complete(self, endpoint, system, user, max_tokens):
        if "select skills" in system:
            return json.dumps({"skill": "xy-prepare-pull-request" if "PR" in user.split("User request:")[-1] else "none"})
        if "grade an answer" in system:
            items = [l[2:] for l in user.split("Rubric:")[-1].splitlines() if l.startswith("- ")]
            return json.dumps({"items": [{"item": i, "pass": True, "reason": ""} for i in items]})
        return "impact analysis on the hotfix branch" if "Skill loaded" in system else "no idea"

evals.ServingLLM = lambda profile=None: Fake()
sys.exit(main(sys.argv[2:]))
"""


def test_dry_run_from_an_installed_copy(tmp_path: Path):
    """Copy the skill folder where Genie Code would load it and run every script from that copy."""
    installed = tmp_path / "Workspace" / "Users" / "me" / ".assistant" / "skills" / "context-authoring"
    shutil.copytree(REPO / "context-authoring", installed, ignore=shutil.ignore_patterns("__pycache__"))
    output = tmp_path / "Workspace" / "Users" / "me" / "genie-skills"
    output.mkdir(parents=True)
    source = tmp_path / "source-repo"
    source.mkdir()
    (source / "release.md").write_text("Use the hotfix branch and write an impact analysis.\n")
    live = tmp_path / "live-instructions.md"
    live.write_text("# Workspace\n- Rule one.\n")
    (output / "standard.yaml").write_text(f"workspace:\n  instructions_path: {live}\n")
    driver = tmp_path / "driver.py"
    driver.write_text(DRIVER)
    scripts = str(installed / "scripts")

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-I", str(driver), scripts, "--root", str(output), *args],
                              capture_output=True, text=True, cwd=tmp_path)

    new = run("new", "xy-prepare-pull-request")
    assert new.returncode == 0, new.stderr
    assert (output / "skills" / "xy-prepare-pull-request" / "SKILL.md").is_file()
    _skill_files = output / "skills" / "xy-prepare-pull-request"
    shutil.rmtree(_skill_files)
    _skill(output)                                        # a filled-in draft in place of the template

    assert run("lint").returncode == 0
    catalog = run("catalog")
    assert "xy-prepare-pull-request" in catalog.stdout and "live-instructions.md" in catalog.stdout
    assert run("check-names", "--repo", str(source)).returncode == 0
    check = run("genie-checklist", "--out", str(output / "genie-check.md"))
    assert check.returncode == 0 and "xy-prepare-pull-request" in (output / "genie-check.md").read_text()
    ev = run("eval", "xy-prepare-pull-request", "--no-cache", "--json", str(output / "eval.json"))
    assert ev.returncode == 0, ev.stdout + ev.stderr
    verdicts = json.loads((output / "eval.json").read_text())["verdicts"]
    assert verdicts[0]["verdict"] == "ADDS VALUE"
