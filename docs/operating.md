# Running the framework at scale

The meta-skill (`context-authoring/`) drafts context. This guide covers stages 2–4 of adopting it: a central context repo (called `genie-context` here) with a standard, the `skillkit` CLI, and CI pipelines (GitHub Actions or Azure DevOps) that check, evaluate, deploy and keep that context current across teams and workspaces. Terms are defined in the [README](../README.md#2-key-terms).

**Contents**

1. [One-time setup](#1-one-time-setup)
2. [Authoring workflow](#2-authoring-workflow)
3. [Evals](#3-evals)
4. [Multi-team repositories](#4-multi-team-repositories)
5. [Skills that use other skills](#5-skills-that-use-other-skills)
6. [Deployment](#6-deployment)
7. [Keeping context current](#7-keeping-context-current)
8. [skillkit reference](#8-skillkit-reference)
9. [Configuration: standard.yaml](#9-configuration-standardyaml)
10. [Pipelines](#10-pipelines)
11. [Development](#11-development)

---

## 1. One-time setup

Done once by the platform team. Step 7 must happen before the first deploy, because the deploy removes workspace skills that are not in the repo.

1. **Create the context repo from this framework and replace the examples.** Everything organisation-specific is an example:
    - `standard.yaml`: `teams` (with their `codeowners` or `reviewers` groups), `prefixes`, the environment catalog regex in `forbidden_patterns` (the example uses `lakehouse_dev|stg|prd`), and the eval endpoints available in your workspace.
    - `context/workspace-instructions.md`: your environments and hard rules.
    - `skills/dp-create-silver-table/` and `examples/data-platform/`: fictional; delete them or keep them for reference until your first skills exist.
    - `evals/decoys.yaml`: the built-in skills present in your workspace.
2. **Create a service principal** and add it to every target workspace. Give it an OAuth secret (Databricks OAuth machine-to-machine works on AWS, Azure and GCP). Only admins can create items at the workspace root, so an admin first creates `/Workspace/.assistant/` and an empty `/Workspace/.assistant_workspace_instructions.md`. Grant the service principal `CAN MANAGE` on both, and `CAN QUERY` on the eval endpoints.
3. **Lock the skills folder**: all users `CAN READ` on `/Workspace/.assistant/skills/` (Genie Code reads skills as the user); no other write grants.
4. **Store the secrets in your CI**, per workspace: `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`. If skills cite Confluence pages: `CONFLUENCE_BASE_URL`, `CONFLUENCE_TOKEN`, and `CONFLUENCE_EMAIL` for Confluence Cloud. If source repos are private: a read token for them.
    - GitHub Actions: environments `genie-context-dev` and `genie-context-prod` with these secrets, and required reviewers on prod.
    - Azure DevOps: variable groups `genie-context-dev`, `genie-context-prod`, `genie-context-confluence`, and environments with an approval check on prod.
    - On Azure, an Entra ID service principal can authenticate with `ARM_CLIENT_ID`, `ARM_CLIENT_SECRET` and `ARM_TENANT_ID` instead; the Databricks SDK accepts either.
5. **Add the pipelines** from [`pipelines/github-actions/`](../pipelines/github-actions/) (copy to `.github/workflows/`) or [`pipelines/azure-devops/`](../pipelines/azure-devops/), and replace the source repo names marked `TODO`. See [section 10](#10-pipelines).
6. **Protect `main`**: require pull requests and the PR validation check. Run `skillkit reviewers` to get the owners per path:
    - GitHub: save the output as `.github/CODEOWNERS` and enable "Require review from Code Owners".
    - Azure DevOps: `skillkit reviewers --format azure-devops` prints the required-reviewer path filters; also turn on "Prohibit the most recent pusher from approving their own changes".
7. **Import what exists**: merge the current workspace instructions into `context/workspace-instructions.md`; export the existing workspace skills, then bring each into `skills/`, merge it, move it to `AGENTS.md`, or retire it. Set `DEPLOY_FLAGS=--no-prune` until every legacy skill is decided.
8. **First deploy**: merge to `main` and check the plan step before approving prod.

## 2. Authoring workflow

The meta-skill (see the [README](../README.md)) drafts context; this is the review process around it in the `genie-context` repo.

1. Branch the context repo and run the meta-skill in create or update mode.
2. Decide the conflicts it lists (README, "Deciding conflicts").
3. Review every generated file as the owner: replace `TODO`s, narrow the `sources` globs to the files the skill really depends on.
4. Run `skillkit lint` and `skillkit eval <names> --runs 3 --repos-root <folder with source checkouts>`.
5. Check two prompts in a real Genie Code Agent-mode chat with the skill installed in your user folder.
6. Set `status: active` for skills with an ADDS VALUE verdict; others can merge as `draft`.
7. Open the PR with `summary.md`; the pipeline posts lint results and the eval report; the owning team and the platform team review with the checklist in `docs/STANDARD.md`. The author cannot approve.
8. Send the proposals to their owners: a person writes `AGENTS.md` from the candidate lines and checks it with `skillkit eval-context`; instruction changes go to the platform team; Unity Catalog comments to data owners.

A hand-written skill starts with `skillkit new <name>` and continues from step 3.

## 3. Evals

`skillkit eval` decides whether a skill merges. It simulates Genie Code through Databricks model serving endpoints and runs nothing in the workspace.

**Case format** (`evals/evals.json`, the Agent Skills layout plus extensions):

```json
{
  "skill_name": "dp-create-silver-table",
  "evals": [
    {
      "id": "silver-01",
      "type": "trigger",
      "prompt": "Create the silver table and notebook for nordics_bronze.crm_contract_account",
      "agents": ["data-platform/AGENTS.md"],
      "must_include": ["merge_template", "COMMENT\\s+'UQ'"],
      "must_not_include": ["\\blakehouse_(dev|stg|prd)\\b", "(?m)^\\s*MERGE\\s+INTO"],
      "assertions": ["Creates the global_silver twin partitioned by region_key"]
    },
    { "id": "nm-01", "type": "near_miss", "prompt": "Add a column to an existing silver table" }
  ]
}
```

At least two `trigger` cases and one `near_miss`; more are expected for active skills.

**What runs:**

| Test | Model sees | Passes when |
| --- | --- | --- |
| Routing (every case) | All active skill names and descriptions, the skills under test, decoys for built-in skills | Trigger: picks this skill at a rate ≥ 0.5 over `--runs`. Near miss: does not |
| Answer with skill (trigger cases) | Workspace instructions, the case's `AGENTS.md` files, skills in `uses`, the skill | Every `must_include` matches, no `must_not_include` matches, the judge passes every assertion — on a majority of runs |
| Answer without skill | The same minus the skill | Same scoring: the baseline |

The judge is a second model from a different family (set in `standard.yaml`). The report also shows the extra tokens per answer each skill costs.

| Verdict | Meaning | Action |
| --- | --- | --- |
| **ADDS VALUE** | All cases pass, and at least one passes only with the skill | Activate and merge |
| **NO EFFECT** | The model already gets it right | Don't merge; move one useful rule to `AGENTS.md` or drop it |
| **FAILING** | A routing or answer case fails | Inspect with `--inspect <case-id>`; fix the skill, its description or the case |

**Advisory or blocking.** During a pilot, run the PR gate in advisory mode (`EVAL_GATE=advisory`): failures show as warnings and reviewers decide. Switch to `blocking` once your eval cases are stable; then a FAILING or NO EFFECT verdict fails the PR.

**Coexistence**: when any skill changes, the PR pipeline reruns routing for **every** active skill, so a new description cannot steal prompts from existing ones. The linter also warns when two descriptions overlap.

**`AGENTS.md` is evaluated too**: `skillkit eval-context --cases examples/data-platform/agents-evals.json --repos-root ~/repos` runs the same prompts with and without the `AGENTS.md` files. Research found generated context files slightly lowered agent success and raised cost by over 20%, while short human-written ones helped — so people write `AGENTS.md`, and it has to show it helps.

## 4. Multi-team repositories

- The platform team defines a short **contract** in the repo's root `AGENTS.md`: the few rules every team must follow, for example naming, required columns, PII tagging, how schema changes ship. It applies in every folder.
- Each team adds an `AGENTS.md` in its folder (template: `context-authoring/assets/templates/AGENTS.team.md`) that states its overrides explicitly.
- A shared task stays **one skill**. When a team does it differently, step 1 names the condition (folder or schema) and links `references/<team>.md`, declared under `variants` with its owner. Two skills for the same task would compete for the same prompts.
- A difference that breaks the contract is fixed in the code, never documented as a variant.
- Ownership is enforced by required reviewers per path; `skillkit reviewers` prints a CODEOWNERS file or Azure DevOps filters.

## 5. Skills that use other skills

Reuse is kept deliberately small. Most material shared between tasks is a convention, not a step, so it belongs in `AGENTS.md`, which loads once. The meta-skill decides shared material in this order:

1. A rule, convention or vocabulary goes to `AGENTS.md` (or workspace instructions if it must hold outside the repo).
2. A task people also ask for on its own is its own skill. Other skills name it at the step that needs it ("Ingest to Bronze: follow the `dp-configure-autoloader` skill with …") and list it in `uses`, without copying its steps.
3. Anything else stays inside each skill that needs it. A few repeated lines cost less than a skill that must always load alongside.

No skill exists only to be reused.

**Checks.** The linter requires every skill named in a body to be listed in `uses` and vice versa; used skills must exist and be active; no cycles; depth at most 2; platform skills never use team skills. Evals run a skill with the skills it uses present, so the baseline measures its own value. When a skill changes, `skillkit changed` also returns every skill that uses it, directly or through another skill, so the PR pipeline re-evaluates them.

**Test it in your pilot.** Genie Code does not document whether it loads a skill because another skill names it. Build one workflow two ways, referencing the skills it uses and self-contained, and compare them with `skillkit eval`: did Genie load the referenced skills, which version passes more cases, and which costs fewer tokens. If referencing loses, keep workflows self-contained and treat `uses` as documentation.

## 6. Deployment

A merge to `main` touching `skills/`, `context/` or `standard.yaml` runs `pipelines/deploy.yml`:

1. `skillkit build` lints (refusing on errors), copies active skills without repo-only files, stamps owner and commit into each `SKILL.md`, and writes `manifest.json` with a SHA-256 per file.
2. The dev stage prints the plan (`create`, `replace`, `delete`, `upload`) and applies it.
3. The prod stage waits for approval, prints the plan and applies it.

`skillkit deploy` verifies the checksums before uploading and writes the manifest to `/Workspace/.assistant/genie-context-manifest.json`, so what runs in a workspace can be traced to a commit. The deploy is authoritative: workspace skills not active in the repo are removed unless `--no-prune`.

**Rollback**: revert the PR, or set `status: deprecated`; the next deploy removes the skill.

## 7. Keeping context current

| Trigger | Detected by | Action |
| --- | --- | --- |
| Code or Git-hosted docs a skill was written from change | Source repo PR hook (`source-repo-freshness.yml`) comments with the affected skills and owners | Owner runs update mode with the changed paths |
| A cited Confluence page changes | Weekly run (`skillkit confluence-check`) | Update mode, then `confluence-check <name> --write` |
| A cited page in another wiki changes | Not detected automatically; covered by the review period | Owner re-checks the page at review |
| Review period passes (120 days) | Weekly run (`skillkit stale`) | Re-run evals; `skillkit reviewed <name>`, update or deprecate |
| A wrong answer is reported | Users | Add the prompt as a failing eval case first, then fix |
| An eval regresses | Weekly regression run | Inspect the answer; fix the skill or the case |

**Update mode** edits only the lines that are no longer true, so earlier manual fixes survive:

> Use context-authoring in update mode for dp-create-silver-table; data-platform changed Databricks/Common/silver_lib/merge_template.py in commits abc123..def456.

## 8. skillkit reference

| Command | What it does |
| --- | --- |
| `lint [skills]` | Checks skills; with no names also catalog budget, overlap, dependencies and workspace instructions |
| `lint-agents <files>` | Checks `AGENTS.md` files (size, no emails or tokens) |
| `catalog` | Skills, status, owner, description tokens, budget use |
| `new <name>` | Scaffolds a draft skill; owner from the prefix |
| `eval [skills]` | Routing and answer tests with baseline. `--mode all\|routing\|answer`, `--runs N`, `--threshold`, `--no-baseline`, `--require-value`, `--case-filter`, `--inspect ID`, `--repos-root`, `--model`, `--judge`, `--out`, `--json` |
| `eval-context --cases F --repos-root D` | Evaluates `AGENTS.md` files with and without them |
| `build [--out]` | Lints, then bundles active skills and instructions with checksums |
| `deploy [--build] [--dry-run] [--no-prune] [--profile]` | Verifies checksums, uploads skills, instructions and manifest |
| `freshness --repo R --changed … \| --changed-file F` | Skills whose sources match changed files (`--format text\|markdown\|json`) |
| `changed --base B` | Skills touched since `B`, plus the skills that use them (all, if shared context changed) |
| `stale` | Active skills past the review period |
| `reviewed <skills>` | Sets `last_reviewed` to today |
| `confluence-check [skills] [--write]` | Compares recorded Confluence versions with the live pages |
| `reviewers [--format codeowners\|azure-devops]` | Owners per path: a CODEOWNERS file (default) or Azure DevOps reviewer filters |

**Lint codes**

| Code | Checks |
| --- | --- |
| SK001–SK006 | `SKILL.md` exists; frontmatter fields; name pattern, folder match, registered prefix; description length and "Use when" |
| SK007–SK009 | Body size; required and allowed sections |
| SK010–SK012 | Links resolve; reference files don't link further; long references start with `## Contents` |
| SK013 | No catalog names, hosts, emails, GUIDs, tokens or dated notes in deployed files |
| SK014–SK016 | `skill.yaml` fields; `evals/evals.json` minimums; variants |
| SK017–SK019 | No `TODO` in active skills; no stray files; deprecated notice |
| SK020 | Security review warnings: scripts, network calls, external URLs, paths outside the skill |
| SK021 | `uses` matches the skills named in the body; dependencies exist and are active |
| CT001–CT004 | Catalog budget; duplicate names; description overlap; dependency cycles, depth and direction |
| WI001–WI003 | Workspace instructions size, token budget, no emails or tokens |
| AG001–AG002 | `AGENTS.md` size, no emails or tokens |

## 9. Configuration: standard.yaml

| Key | Purpose |
| --- | --- |
| `platform_team`, `teams`, `prefixes` | Who owns which skill prefix; each team's `codeowners` (GitHub) or `reviewers` (Azure DevOps) group |
| `limits` | Description, body, catalog, instruction and `AGENTS.md` budgets |
| `review_period_days` | When an active skill counts as stale |
| `sections` | Required and optional `SKILL.md` sections |
| `catalog` | Overlap warning threshold; maximum dependency depth |
| `forbidden_patterns`, `forbidden_patterns_context` | Regexes rejected in skills / in instructions and `AGENTS.md` |
| `workspace` | Skills path, instructions path, manifest path |
| `eval` | Model endpoint, judge endpoint, max tokens, trigger threshold |

## 10. Pipelines

The same four jobs exist for GitHub Actions and Azure DevOps. Copy one set into your repos.

| Job | GitHub Actions | Azure DevOps | Runs | Does |
| --- | --- | --- | --- | --- |
| PR validation | `pipelines/github-actions/pr-validation.yml` | `pipelines/azure-devops/pr-validation.yml` | Every PR to the context repo | Unit tests, lint, evals with baseline for changed skills and the skills that use them (3 runs), routing for all skills, report posted on the PR |
| Deploy | `pipelines/github-actions/deploy.yml` | `pipelines/azure-devops/deploy.yml` | Merge to `main` | Build, deploy to dev, then prod after approval |
| Maintenance | `pipelines/github-actions/maintenance.yml` | `pipelines/azure-devops/maintenance.yml` | Mondays 05:00 UTC | Stale reviews, changed Confluence pages, regression eval, budget use; fails if an owner has work |
| Source-repo freshness | `pipelines/github-actions/source-repo-freshness.yml` (copy into each source repo) | `pipelines/azure-devops/templates/source-repo-freshness.yml` (include from each source repo) | Every PR to a source repo | Comments with the skills the change may affect, and their owners; never blocks |

Notes:

- GitHub Actions: the workflows post comments with `gh pr comment` and need `pull-requests: write`. Private source or context repos need a read token secret (`SOURCE_REPO_TOKEN`, `CONTEXT_REPO_TOKEN`).
- Azure DevOps: Azure Repos ignores `pr:` triggers in YAML, so add PR validation as a build validation branch policy. The build service needs "Contribute to pull requests" to post comments.

## 11. Development

```bash
pip install -e ".[dev]"
pytest -q          # 42 tests: lint rules, freshness, build and checksums, deploy (mocked), evals (fake LLM)
```

The code is plain Python with `pyyaml`, `requests` and (optionally) `databricks-sdk`. `deploy` and `eval` import the SDK lazily, so linting and building need no Databricks access.

To add a lint rule: add the check in `skillkit/lint.py` with a new code, document it in `docs/STANDARD.md` and the table above, and add a test in `tests/test_lint.py`.

