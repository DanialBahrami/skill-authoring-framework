from pathlib import Path

from skillkit import lint
from skillkit.model import load_skill, load_skills, load_standard

from conftest import REPO


def codes(findings, severity="error"):
    return {f.code for f in findings if f.severity == severity}


def test_good_skill_has_no_errors(repo: Path):
    std = load_standard(repo)
    skill = load_skill(repo / "skills" / "dp-prepare-pr")
    assert codes(lint.lint_skill(skill, std)) == set()


def test_spec_optional_frontmatter_allowed(repo: Path):
    md = repo / "skills" / "dp-prepare-pr" / "SKILL.md"
    md.write_text(md.read_text().replace("name: dp-prepare-pr", "name: dp-prepare-pr\nlicense: Proprietary\n"
                                         "compatibility: Databricks Genie Code\nmetadata:\n  team: data-platform"))
    assert codes(lint.lint_skill(load_skill(md.parent), load_standard(repo))) == set()


def test_frontmatter_extra_keys_and_name_mismatch(repo: Path):
    md = repo / "skills" / "dp-prepare-pr" / "SKILL.md"
    md.write_text(md.read_text().replace("name: dp-prepare-pr", "name: dp-prepare-pr-x\nversion: 2"))
    found = codes(lint.lint_skill(load_skill(md.parent), load_standard(repo)))
    assert {"SK002", "SK003"} <= found


def test_unregistered_prefix_and_owner(repo: Path):
    src = repo / "skills" / "dp-prepare-pr"
    dst = repo / "skills" / "xyz-prepare-pr"
    src.rename(dst)
    md = dst / "SKILL.md"
    md.write_text(md.read_text().replace("name: dp-prepare-pr", "name: xyz-prepare-pr"))
    found = codes(lint.lint_skill(load_skill(dst), load_standard(repo)))
    assert "SK004" in found


def test_description_needs_use_when_and_length(repo: Path):
    md = repo / "skills" / "dp-prepare-pr" / "SKILL.md"
    text = md.read_text()
    start = text.index("description:")
    end = text.index("---", start)
    md.write_text(text[:start] + "description: Prepares PRs.\n" + text[end:])
    found = codes(lint.lint_skill(load_skill(md.parent), load_standard(repo)))
    assert {"SK005", "SK006"} <= found


def test_sections_required_in_order_and_no_unknown(repo: Path):
    md = repo / "skills" / "dp-prepare-pr" / "SKILL.md"
    text = md.read_text().replace("## Steps", "## BEFORE YOU START\n\nx\n\n## Steps")
    text = text.replace("## Verify\n\n- The bundle validates.\n", "")
    md.write_text(text)
    findings = lint.lint_skill(load_skill(md.parent), load_standard(repo))
    messages = " ".join(f.message for f in findings if f.code == "SK009")
    assert "Verify" in messages and "BEFORE YOU START" in messages


def test_body_too_long(repo: Path):
    md = repo / "skills" / "dp-prepare-pr" / "SKILL.md"
    md.write_text(md.read_text() + "\n".join(f"- line {i}" for i in range(250)))
    assert "SK007" in codes(lint.lint_skill(load_skill(md.parent), load_standard(repo)))


def test_forbidden_patterns(repo: Path):
    md = repo / "skills" / "dp-prepare-pr" / "SKILL.md"
    md.write_text(md.read_text() + "\nRun it in lakehouse_prd and mail jane.doe@example.com.\n"
                  "Since March 2026 we use the new template.\n")
    findings = [f for f in lint.lint_skill(load_skill(md.parent), load_standard(repo)) if f.code == "SK013"]
    labels = " ".join(f.message for f in findings)
    assert "environment catalog" in labels and "email" in labels and "dated" in labels


def test_reference_links_and_toc(repo: Path):
    ref = repo / "skills" / "dp-prepare-pr" / "references" / "title-codes.md"
    ref.write_text("# Title codes\n\nSee [other](other.md).\n" + "\n".join(f"- {i}" for i in range(120)))
    found = codes(lint.lint_skill(load_skill(ref.parents[1]), load_standard(repo)))
    assert {"SK011", "SK012"} <= found


def test_broken_link(repo: Path):
    md = repo / "skills" / "dp-prepare-pr" / "SKILL.md"
    md.write_text(md.read_text() + "\nSee [missing](references/missing.md).\n")
    assert "SK010" in codes(lint.lint_skill(load_skill(md.parent), load_standard(repo)))


def test_skill_yaml_and_evals_rules(repo: Path):
    folder = repo / "skills" / "dp-prepare-pr"
    (folder / "skill.yaml").write_text("owner: forecasting\nstatus: live\nsources: []\n")
    (folder / "evals" / "evals.json").write_text('{"evals": [{"id": "a", "type": "trigger", "prompt": "x"}]}')
    findings = lint.lint_skill(load_skill(folder), load_standard(repo))
    assert {"SK014", "SK015"} <= codes(findings)


def test_todo_blocked_only_when_active(repo: Path):
    folder = repo / "skills" / "dp-prepare-pr"
    md = folder / "SKILL.md"
    md.write_text(md.read_text() + "\nTODO: finish.\n")
    assert "SK017" in codes(lint.lint_skill(load_skill(folder), load_standard(repo)))
    meta = folder / "skill.yaml"
    meta.write_text(meta.read_text().replace("status: active", "status: draft"))
    assert "SK017" not in codes(lint.lint_skill(load_skill(folder), load_standard(repo)))


def test_catalog_budget(repo: Path):
    std = load_standard(repo)
    std.raw["limits"]["catalog_max_tokens"] = 10
    assert "CT001" in codes(lint.lint_catalog(load_skills(repo), std))


def test_workspace_instructions_limits(repo: Path):
    std = load_standard(repo)
    path = repo / "context" / "workspace-instructions.md"
    path.write_text("x" * 21000)
    assert {"WI001", "WI002"} <= codes(lint.lint_workspace_instructions(path, std))


def test_shipped_templates_lint_clean(tmp_path: Path):
    """The meta-skill's AGENTS.md templates pass lint with the defaults."""
    std = load_standard(tmp_path)
    templates = REPO / "context-authoring" / "assets" / "templates"
    findings = [f for name in ("AGENTS.repo.md", "AGENTS.team.md") for f in lint.lint_agents_md(templates / name, std)]
    assert [str(f) for f in findings if f.severity == "error"] == []


def test_gotchas_section_allowed(repo: Path):
    md = repo / "skills" / "dp-prepare-pr" / "SKILL.md"
    md.write_text(md.read_text().replace("## References", "## Gotchas\n\n- The release branch is cut at noon.\n\n## References"))
    assert "SK009" not in codes(lint.lint_skill(load_skill(md.parent), load_standard(repo)))


def test_security_warnings(repo: Path):
    folder = repo / "skills" / "dp-prepare-pr"
    (folder / "scripts").mkdir()
    (folder / "scripts" / "post.py").write_text("import requests\nrequests.post('https://example.com')\n")
    findings = lint.lint_skill(load_skill(folder), load_standard(repo))
    warns = [f for f in findings if f.code == "SK020"]
    assert warns and all(f.severity == "warning" for f in warns)


def _add_skill(repo: Path, name: str, body_extra: str = "", uses=(), status="active", owner="data-platform",
               desc="Adds a thing to another thing in the platform. Use when the user asks to add the thing."):
    folder = repo / "skills" / name
    (folder / "evals").mkdir(parents=True)
    import json
    (folder / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {json.dumps(desc)}\n---\n\n## Steps\n\n1. Do it.{body_extra}\n\n## Verify\n\n- Check.\n")
    (folder / "skill.yaml").write_text(f"owner: {owner}\nstatus: {status}\nlast_reviewed: 2026-11-01\n"
                                       f"sources:\n  - note: test\nuses: [{', '.join(uses)}]\n")
    from conftest import GOOD_EVALS
    (folder / "evals" / "evals.json").write_text(GOOD_EVALS)
    return folder


def test_uses_must_match_body_and_exist(repo: Path):
    _add_skill(repo, "dp-onboard-new-source", " Then follow dp-prepare-pr.", uses=["dp-prepare-pr", "dp-missing-skill"])
    skills = load_skills(repo)
    by_name = {s.name: s for s in skills}
    msgs = [f.message for f in lint.lint_uses(by_name["dp-onboard-new-source"], by_name)]
    assert any("unknown skill 'dp-missing-skill'" in m for m in msgs)
    _add_skill(repo, "dp-other-flow-thing", " Then follow dp-prepare-pr.")
    skills = load_skills(repo)
    by_name = {s.name: s for s in skills}
    msgs = [f.message for f in lint.lint_uses(by_name["dp-other-flow-thing"], by_name)]
    assert any("does not list it in uses" in m for m in msgs)


def test_active_skill_cannot_use_draft(repo: Path):
    _add_skill(repo, "dp-draft-block-thing", status="draft")
    _add_skill(repo, "dp-flow-using-draft", " Follow dp-draft-block-thing.", uses=["dp-draft-block-thing"])
    by_name = {s.name: s for s in load_skills(repo)}
    assert any("which is draft" in f.message for f in lint.lint_uses(by_name["dp-flow-using-draft"], by_name))


def test_dependency_cycle_depth_and_direction(repo: Path):
    _add_skill(repo, "dp-aaa-one-thing", " Use dp-bbb-two-thing.", uses=["dp-bbb-two-thing"])
    _add_skill(repo, "dp-bbb-two-thing", " Use dp-aaa-one-thing.", uses=["dp-aaa-one-thing"])
    _add_skill(repo, "fc-team-only-thing", owner="forecasting")
    _add_skill(repo, "dp-uses-team-thing", " Use fc-team-only-thing.", uses=["fc-team-only-thing"])
    msgs = [f.message for f in lint.lint_catalog(load_skills(repo), load_standard(repo)) if f.code == "CT004"]
    assert any("cycle" in m for m in msgs)
    assert any("depends on team skill fc-team-only-thing" in m for m in msgs)


def test_description_overlap_warning(repo: Path):
    _add_skill(repo, "dp-write-pr-description", desc="Prepares a pull request for the data-platform repo: branch, title code, "
               "description, impact analysis. Use when the user asks to open, create or describe a PR.")
    found = [f for f in lint.lint_catalog(load_skills(repo), load_standard(repo)) if f.code == "CT003"]
    assert found and found[0].severity == "warning"


def test_doc_source_accepted(repo: Path):
    meta = repo / "skills" / "dp-prepare-pr" / "skill.yaml"
    meta.write_text(meta.read_text() + "  - doc:\n      url: https://wiki.example.org/pr-process\n      title: PR process\n")
    assert "SK014" not in codes(lint.lint_skill(load_skill(meta.parent), load_standard(repo)))


def test_workspace_hosts_on_all_clouds_rejected(repo: Path):
    md = repo / "skills" / "dp-prepare-pr" / "SKILL.md"
    for host in ("dbc-1a2b3c4d-5e6f.cloud.databricks.com", "adb-123.4.azuredatabricks.net", "1234.5.gcp.databricks.com"):
        original = md.read_text()
        md.write_text(original + f"\nOpen https://{host}/ to check.\n")
        found = [f.message for f in lint.lint_skill(load_skill(md.parent), load_standard(repo)) if f.code == "SK013"]
        assert any("workspace host" in m for m in found), host
        md.write_text(original)
