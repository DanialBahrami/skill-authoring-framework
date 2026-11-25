# Proposals: {{scope}}

For their owners. The meta-skill applies none of them.

## AGENTS.md candidate lines (repo and folder owners)

Only what an agent cannot infer from the code and docs it can already read: vocabulary, conventions, contract rules, non-obvious commands. No overviews. A person writes the file from these lines, using `assets/templates/AGENTS.repo.md` (repo root) and `AGENTS.team.md` (team folder). Generated context files measurably lower agent success; short human-written ones help. If the user asks for drafts, write them to `<run folder>/agents-md/<repo>/<folder>/AGENTS.md`, marked as drafts; `eval-context --agents-drafts <run folder>/agents-md` must show ADDS VALUE before a person merges them.

| Candidate line | For (repo or folder) | Evidence (source) | Why the agent cannot infer it |
| --- | --- | --- | --- |

## Always-on instructions (platform team)

Loaded in every response for every user. Propose a line only if it must hold outside any repo, or a wrong answer would be harmful.

| # | Change | Proposed text | Replaces (current text, or "new") | Evidence (source) | Why not AGENTS.md or a skill |
| --- | --- | --- | --- | --- | --- |

## Catalog comments (data owners)

What the data is (meaning, grain, source system, PII), not how to use it. One statement per fact, each with its source; the catalog through a variable.

```sql
-- Source: <repo path or doc page>
COMMENT ON TABLE ${catalog}.<schema>.<table> IS '<One row per ... .>';
```

## Forbidden patterns (owner of the output folder's standard.yaml)

Environment-specific names found in the code (catalogs, storage accounts, hosts), so skills never contain them. Never put these in a shared or public copy of the framework.

| Name | Regex | Example (source) |
| --- | --- | --- |
