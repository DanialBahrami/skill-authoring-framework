"""Build the deployable bundle and deploy it to a Databricks workspace."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import yaml

from skillkit.model import REPO_ONLY, Skill, Standard, parse_skill_md, workspace_instructions_path


def _git_sha(root: Path) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp_skill_md(text: str, owner: str, commit: str) -> str:
    """Add owner and source commit to the spec's `metadata` field of a deployed SKILL.md,
    so anyone reading the skill in the workspace can see who owns it and which commit it is."""
    front, body, errors = parse_skill_md(text)
    if errors:
        return text
    metadata = {str(k): str(v) for k, v in (front.get("metadata") or {}).items()}
    metadata.update({"owner": owner, "source-commit": commit})
    front["metadata"] = metadata
    header = yaml.safe_dump(front, sort_keys=False, allow_unicode=True, width=1000).strip()
    return f"---\n{header}\n---\n{body}"


def build(root: Path, skills: list[Skill], out: Path) -> dict:
    """Copy active skills (without repo-only files) and workspace instructions into `out`."""
    if out.exists():
        shutil.rmtree(out)
    (out / "skills").mkdir(parents=True)
    commit = _git_sha(root)
    deployed = []
    for skill in skills:
        if skill.status != "active":
            continue
        target = out / "skills" / skill.name
        for path in skill.runtime_files():
            dest = target / path.relative_to(skill.path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if path.name == "SKILL.md" and path.parent == skill.path:
                dest.write_text(stamp_skill_md(path.read_text(encoding="utf-8"), skill.owner, commit),
                                encoding="utf-8")
            else:
                shutil.copy2(path, dest)
        deployed.append(skill.name)
    instructions = workspace_instructions_path(root)
    if instructions.is_file():
        shutil.copy2(instructions, out / "workspace-instructions.md")
    checksums = {p.relative_to(out).as_posix(): _sha256(p) for p in sorted(out.rglob("*")) if p.is_file()}
    manifest = {
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "git_sha": commit,
        "skills": deployed,
        "has_workspace_instructions": instructions.is_file(),
        "sha256": checksums,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for name in REPO_ONLY:
        assert not list((out / "skills").rglob(name)), f"{name} leaked into the build"
    return manifest


def verify_build(build_dir: Path) -> list[str]:
    """Return files whose checksum no longer matches the manifest (tampering or a partial copy)."""
    manifest = json.loads((build_dir / "manifest.json").read_text(encoding="utf-8"))
    bad = []
    for rel, digest in manifest.get("sha256", {}).items():
        path = build_dir / rel
        if not path.is_file() or _sha256(path) != digest:
            bad.append(rel)
    return bad


def deploy(build_dir: Path, std: Standard, *, dry_run: bool, prune: bool, profile: str | None = None) -> list[str]:
    """Upload the build to the workspace. Returns the list of actions taken (or planned)."""
    bad = verify_build(build_dir)
    if bad:
        raise SystemExit(f"build does not match its manifest checksums: {', '.join(bad)}")
    manifest = json.loads((build_dir / "manifest.json").read_text(encoding="utf-8"))
    skills_path = std.workspace["skills_path"].rstrip("/")
    instructions_path = std.workspace["instructions_path"]
    actions: list[str] = []

    from databricks.sdk import WorkspaceClient  # lazy: only deploy and eval need the SDK
    from databricks.sdk.errors import NotFound
    from databricks.sdk.service.workspace import ImportFormat, ObjectType

    w = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
    fmt = getattr(ImportFormat, "RAW", ImportFormat.AUTO)

    try:
        existing = {Path(o.path).name for o in w.workspace.list(skills_path) if o.object_type == ObjectType.DIRECTORY}
    except NotFound:
        existing = set()
        actions.append(f"mkdir {skills_path}")
        if not dry_run:
            w.workspace.mkdirs(skills_path)

    wanted = set(manifest["skills"])
    for name in sorted(wanted):
        remote = f"{skills_path}/{name}"
        if name in existing:
            actions.append(f"replace {remote}")
            if not dry_run:
                w.workspace.delete(remote, recursive=True)
        else:
            actions.append(f"create {remote}")
        local = build_dir / "skills" / name
        if not dry_run:
            folders = {remote} | {f"{remote}/{d.relative_to(local).as_posix()}" for d in local.rglob("*") if d.is_dir()}
            for folder in sorted(folders):
                w.workspace.mkdirs(folder)
            for path in sorted(p for p in local.rglob("*") if p.is_file()):
                rel = path.relative_to(local).as_posix()
                w.workspace.upload(f"{remote}/{rel}", path.read_bytes(), format=fmt, overwrite=True)

    if prune:
        for name in sorted(existing - wanted):
            actions.append(f"delete {skills_path}/{name} (not in repo or not active)")
            if not dry_run:
                w.workspace.delete(f"{skills_path}/{name}", recursive=True)

    if manifest.get("has_workspace_instructions"):
        actions.append(f"upload {instructions_path}")
        if not dry_run:
            data = (build_dir / "workspace-instructions.md").read_bytes()
            w.workspace.upload(instructions_path, data, format=fmt, overwrite=True)

    actions.append(f"upload {std.manifest_path} (commit {manifest['git_sha']})")
    if not dry_run:
        w.workspace.upload(std.manifest_path, (build_dir / "manifest.json").read_bytes(), format=fmt, overwrite=True)
    return actions
