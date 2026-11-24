"""Tests for AGENTS.md drafts in evals and the per-case eval cache."""

import json
from pathlib import Path

from skillkit.evals import load_cache, run_context_evals, run_evals, save_cache
from skillkit.model import load_skills, load_standard

from test_evals import FakeLLM


class Counting(FakeLLM):
    def __init__(self):
        self.calls = 0

    def complete(self, endpoint, system, user, max_tokens):
        self.calls += 1
        return super().complete(endpoint, system, user, max_tokens)


def _cases(tmp_path: Path) -> Path:
    cases = tmp_path / "agents-evals.json"
    cases.write_text(json.dumps({"name": "data-platform AGENTS.md", "evals": [
        {"id": "c1", "prompt": "Which technical columns?", "agents": ["data-platform/AGENTS.md"],
         "must_include": ["_load_date"]}]}))
    return cases


class Echo:
    last_tokens = None

    def complete(self, endpoint, system, user, max_tokens):
        return "_load_date" if "_load_date" in system else "no idea"


def test_context_evals_from_drafts_only(repo: Path, tmp_path: Path):
    drafts = tmp_path / "run" / "agents-md" / "data-platform"
    drafts.mkdir(parents=True)
    (drafts / "AGENTS.md").write_text("Technical columns: _load_date.")
    results, summary, warnings = run_context_evals(repo, load_standard(repo), _cases(tmp_path), Echo(),
                                                   repos_root=None, drafts_root=tmp_path / "run" / "agents-md")
    assert summary.verdict == "ADDS VALUE" and not warnings


def test_drafts_win_over_repo_files(repo: Path, tmp_path: Path):
    (tmp_path / "repos" / "data-platform").mkdir(parents=True)
    (tmp_path / "repos" / "data-platform" / "AGENTS.md").write_text("Nothing useful.")
    drafts = tmp_path / "drafts" / "data-platform"
    drafts.mkdir(parents=True)
    (drafts / "AGENTS.md").write_text("Technical columns: _load_date.")
    _, summary, _ = run_context_evals(repo, load_standard(repo), _cases(tmp_path), Echo(),
                                      repos_root=tmp_path / "repos", drafts_root=tmp_path / "drafts")
    assert summary.verdict == "ADDS VALUE"
    _, summary, _ = run_context_evals(repo, load_standard(repo), _cases(tmp_path), Echo(),
                                      repos_root=tmp_path / "repos")
    assert summary.verdict == "FAILING"


def test_cache_reuses_unchanged_cases_and_reruns_changed_ones(repo: Path):
    std = load_standard(repo)
    cache: dict = {}
    first = Counting()
    run_evals(repo, std, load_skills(repo), load_skills(repo), first, cache=cache, log=lambda *_: None)
    save_cache(repo, cache)
    assert first.calls > 0

    again = Counting()
    _, verdicts, warnings = run_evals(repo, std, load_skills(repo), load_skills(repo), again,
                                      cache=load_cache(repo), log=lambda *_: None)
    assert again.calls == 0 and verdicts[0].verdict == "ADDS VALUE"
    assert any(w.startswith("cache:") for w in warnings)

    md = repo / "skills" / "dp-prepare-pr" / "SKILL.md"
    md.write_text(md.read_text().replace("2. Fill the description", "2. Fill in the description"))
    changed = Counting()
    run_evals(repo, std, load_skills(repo), load_skills(repo), changed, mode="answer", cache=load_cache(repo),
              log=lambda *_: None)
    assert changed.calls > 0


def test_refresh_failed_reruns_only_failures(repo: Path):
    class NeverRoutes(FakeLLM):
        def complete(self, endpoint, system, user, max_tokens):
            return '{"skill": "none"}' if "select skills" in system else super().complete(endpoint, system, user, max_tokens)

    std = load_standard(repo)
    cache: dict = {}
    run_evals(repo, std, load_skills(repo), load_skills(repo), NeverRoutes(), mode="routing", cache=cache,
              log=lambda *_: None)
    plain = Counting()
    run_evals(repo, std, load_skills(repo), load_skills(repo), plain, mode="routing", cache=dict(cache),
              log=lambda *_: None)
    assert plain.calls == 0
    refresh = Counting()
    results, _, _ = run_evals(repo, std, load_skills(repo), load_skills(repo), refresh, mode="routing",
                              cache=dict(cache), refresh_failed=True, log=lambda *_: None)
    assert refresh.calls == 2   # the two trigger cases failed; the near miss passed and is reused
    assert all(r.routing_pass for r in results)
