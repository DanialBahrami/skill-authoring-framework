import datetime as dt
import json
import subprocess
from pathlib import Path

from skillkit import cli
from skillkit.build import build
from skillkit.freshness import affected_skills, glob_to_regex, mark_reviewed, stale_skills, write_confluence_versions
from skillkit.model import load_skill, load_skills


def test_glob_matching():
    assert glob_to_regex("CI_CD_Pipeline/**").match("CI_CD_Pipeline/policy/rules.yml")
    assert glob_to_regex("Databricks/Config/**/autoloader_*_config.json").match(
        "Databricks/Config/fi_ms/autoloader_fi_ms_config.json")
    assert not glob_to_regex("Databricks/Silver/*").match("Databricks/Silver/sub/x.py")
    assert glob_to_regex("Databricks/Common/silver_lib/merge_template").match("Databricks/Common/silver_lib/merge_template.py") is None
    assert glob_to_regex("Databricks/Common/silver_lib").match("Databricks/Common/silver_lib/merge_template.py")
    assert glob_to_regex("Databricks/Common/silver_lib/merge_template*").match("Databricks/Common/silver_lib/merge_template.py")


def test_affected_skills(repo: Path):
    skills = load_skills(repo)
    hits = affected_skills(skills, "data-platform", ["CI_CD_Pipeline/DevPullRequestPipeline.yml", "README.md"])
    assert hits == {"dp-prepare-pr": ["CI_CD_Pipeline/DevPullRequestPipeline.yml"]}
    assert affected_skills(skills, "other-repo", ["CI_CD_Pipeline/x.yml"]) == {}


def test_stale_and_reviewed(repo: Path):
    skills = load_skills(repo)
    assert stale_skills(skills, 120, today=dt.date(2026, 11, 20)) == []
    assert stale_skills(skills, 10, today=dt.date(2026, 12, 31))[0][0] == "dp-prepare-pr"
    mark_reviewed(skills[0], today=dt.date(2026, 11, 23))
    assert load_skill(skills[0].path).last_reviewed == dt.date(2026, 11, 23)


def test_write_confluence_versions(repo: Path):
    skill = load_skills(repo)[0]
    write_confluence_versions(skill, {"1001": 9})
    page = load_skill(skill.path).sources[1]["confluence"]
    assert page["version"] == 9


def test_build_strips_repo_only_files(repo: Path, tmp_path: Path):
    out = tmp_path / "out"
    manifest = build(repo, load_skills(repo), out)
    assert manifest["skills"] == ["dp-prepare-pr"]
    assert (out / "skills" / "dp-prepare-pr" / "SKILL.md").is_file()
    assert (out / "skills" / "dp-prepare-pr" / "references" / "title-codes.md").is_file()
    assert not list(out.rglob("skill.yaml")) and not list(out.rglob("evals.json"))
    deployed = (out / "skills" / "dp-prepare-pr" / "SKILL.md").read_text()
    assert "owner: data-platform" in deployed and "source-commit:" in deployed
    assert (out / "workspace-instructions.md").is_file()
    assert json.loads((out / "manifest.json").read_text())["has_workspace_instructions"]


def test_build_skips_drafts(repo: Path, tmp_path: Path):
    meta = repo / "skills" / "dp-prepare-pr" / "skill.yaml"
    meta.write_text(meta.read_text().replace("status: active", "status: draft"))
    assert build(repo, load_skills(repo), tmp_path / "out")["skills"] == []


def test_cli_new_and_lint(repo: Path, capsys):
    assert cli.main(["--root", str(repo), "new", "fc-forecast-spot-price"]) == 0
    folder = repo / "skills" / "fc-forecast-spot-price"
    assert "owner: forecasting" in (folder / "skill.yaml").read_text()
    # A fresh scaffold is a valid draft; its TODO placeholders block activation.
    assert cli.main(["--root", str(repo), "lint", "fc-forecast-spot-price"]) == 0
    meta = folder / "skill.yaml"
    meta.write_text(meta.read_text().replace("status: draft", "status: active"))
    assert cli.main(["--root", str(repo), "lint", "fc-forecast-spot-price"]) == 1
    assert cli.main(["--root", str(repo), "lint", "dp-prepare-pr"]) == 0


def test_cli_freshness_markdown(repo: Path, capsys):
    cli.main(["--root", str(repo), "freshness", "--repo", "data-platform", "--changed",
              "pull_request_template.md", "--format", "markdown"])
    out = capsys.readouterr().out
    assert "dp-prepare-pr" in out and "data-platform" in out


def test_changed_skills(repo: Path):
    from skillkit.freshness import changed_skills

    def git(*args):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    git("init", "-b", "main")
    git("-c", "user.email=a@b.c", "-c", "user.name=t", "add", ".")
    git("-c", "user.email=a@b.c", "-c", "user.name=t", "commit", "-m", "init")
    git("checkout", "-b", "feature")
    md = repo / "skills" / "dp-prepare-pr" / "SKILL.md"
    md.write_text(md.read_text() + "\n")
    git("-c", "user.email=a@b.c", "-c", "user.name=t", "commit", "-am", "edit")
    assert changed_skills(repo, "main", ["dp-prepare-pr", "dp-other-thing"]) == ["dp-prepare-pr"]
    (repo / "context" / "workspace-instructions.md").write_text("# changed\n")
    git("-c", "user.email=a@b.c", "-c", "user.name=t", "commit", "-am", "ctx")
    assert changed_skills(repo, "main", ["dp-prepare-pr", "dp-other-thing"]) == ["dp-other-thing", "dp-prepare-pr"]


def test_deploy_plan_and_apply(repo: Path, tmp_path: Path, monkeypatch):
    """Deploy against a fake workspace: replaces kept skills, creates new ones, prunes the rest."""
    import databricks.sdk
    from databricks.sdk.service.workspace import ObjectInfo, ObjectType

    from skillkit.build import deploy
    from skillkit.model import load_standard

    calls = []

    class FakeWorkspace:
        def list(self, path):
            return [ObjectInfo(path=f"{path}/dp-prepare-pr", object_type=ObjectType.DIRECTORY),
                    ObjectInfo(path=f"{path}/manual-skill", object_type=ObjectType.DIRECTORY)]

        def mkdirs(self, path):
            calls.append(("mkdirs", path))

        def delete(self, path, recursive=False):
            calls.append(("delete", path))

        def upload(self, path, content, format=None, overwrite=False):
            calls.append(("upload", path))

    class FakeClient:
        def __init__(self, *a, **k):
            self.workspace = FakeWorkspace()

    monkeypatch.setattr(databricks.sdk, "WorkspaceClient", FakeClient)
    out = tmp_path / "out"
    build(repo, load_skills(repo), out)
    std = load_standard(repo)

    plan = deploy(out, std, dry_run=True, prune=True)
    assert calls == []
    assert any("delete" in a and "manual-skill" in a for a in plan)

    deploy(out, std, dry_run=False, prune=True)
    root = "/Workspace/.assistant/skills"
    assert ("delete", f"{root}/dp-prepare-pr") in calls
    assert ("upload", f"{root}/dp-prepare-pr/SKILL.md") in calls
    assert ("upload", f"{root}/dp-prepare-pr/references/title-codes.md") in calls
    assert ("delete", f"{root}/manual-skill") in calls
    assert ("upload", "/Workspace/.assistant_workspace_instructions.md") in calls
    assert ("upload", "/Workspace/.assistant/genie-context-manifest.json") in calls


def test_checksums_detect_changes(repo: Path, tmp_path: Path):
    from skillkit.build import verify_build

    out = tmp_path / "out"
    build(repo, load_skills(repo), out)
    assert verify_build(out) == []
    (out / "skills" / "dp-prepare-pr" / "SKILL.md").write_text("tampered")
    assert verify_build(out) == ["skills/dp-prepare-pr/SKILL.md"]
