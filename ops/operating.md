# Running the framework at scale

The meta-skill (`context-authoring/`) creates skills in an output folder; nothing here is needed for that. This guide is for the next step: when teams rely on their skills and want changes reviewed, deployed and kept current. The output folder becomes a **context repo** in Git (called `genie-context` here) with its own standard, CI pipelines (GitHub Actions or Azure DevOps) and the `skillkit-ops` commands for build, deploy and freshness.

**Contents**

1. [One-time setup](#1-one-time-setup)
2. [Authoring workflow](#2-authoring-workflow)
3. [Evals](#3-evals)
4. [Multi-team repositories](#4-multi-team-repositories)
5. [Skills that use other skills](#5-skills-that-use-other-skills)
6. [Deployment](#6-deployment)
7. [Keeping context current](#7-keeping-context-current)
8. [skillkit and skillkit-ops reference](#8-skillkit-and-skillkit-ops-reference)
9. [Configuration: standard.yaml](#9-configuration-standardyaml)
10. [Pipelines](#10-pipelines)
11. [Development](#11-development)

---

## 1. One-time setup

Done once by the platform team. Step 7 must happen before the first deploy, because the deploy removes workspace skills that are not in the repo.

1. **Create the context repo.** Create a repo from this framework (so `context-authoring/`, `ops/` and `pyproject.toml` come along and `pip install .` gives `skillkit` and `skillkit-ops`), then lay out the output folder at its root:
    - `skills/` and `evals/journeys.json`: move in the skills from your output folder.
    - `standard.yaml`: copy [`standard.example.yaml`](standard.example.yaml) and set `teams` (with their `codeowners` or `reviewers` groups), `prefixes`, your environment catalog regex in `forbidden_patterns` (the example uses `lakehouse_dev|stg|prd`), the eval endpoints, and `catalog.installed_skills` (`use` once the repo is the only source of workspace skills).
    - `context/workspace-instructions.md`: copy in your workspace's current instructions (`/Workspace/.assistant_workspace_instructions.md`). In a context repo this Git copy is the master: evals use it instead of the live file, and the pipeline deploys it.
    - `evals/decoys.yaml` (optional): the built-in skills present in your workspace, if they differ from the skill's defaults.
2. **Create a service principal** and add it to every target workspace. Give it an OAuth secret (Databricks OAuth machine-to-machine works on AWS, Azure and GCP). Only admins can create items at the workspace root, so an admin first creates `/Workspace/.assistant/` and an empty `/Workspace/.assistant_workspace_instructions.md`. Grant the service principal `CAN MANAGE` on both, and `CAN QUERY` on the eval endpoints. For the optional execution gate, also `CAN USE` on a development SQL warehouse and only `USE CATALOG`, `USE SCHEMA` and `SELECT` on the development catalog: the gate sends only `EXPLAIN`, and read-only access means a mistake still cannot change data.
3. **Lock the skills folder**: all users `CAN READ` on `/Workspace/.assistant/skills/` (Genie Code reads skills as the user); no other write grants.
4. **Store the secrets in your CI**, per workspace: `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`. If skills cite Confluence pages: `CONFLUENCE_BASE_URL`, `CONFLUENCE_TOKEN`, and `CONFLUENCE_EMAIL` for Confluence Cloud. If source repos are private: a read token for them.
    - GitHub Actions: environments `genie-context-dev` and `genie-context-prod` with these secrets, and required reviewers on prod.
    - Azure DevOps: variable groups `genie-context-dev`, `genie-context-prod`, `genie-context-confluence`, and environments with an approval check on prod.
    - On Azure, an Entra ID service principal can authenticate with `ARM_CLIENT_ID`, `ARM_CLIENT_SECRET` and `ARM_TENANT_ID` instead; the Databricks SDK accepts either.
5. **Add the pipelines** from [`ops/pipelines/github-actions/`](pipelines/github-actions/) (copy to `.github/workflows/`) or [`ops/pipelines/azure-devops/`](pipelines/azure-devops/), and replace the source repo names marked `TODO`. See [section 10](#10-pipelines).
6. **Protect `main`**: require pull requests and the PR validation check. Run `skillkit-ops reviewers` to get the owners per path:
    - GitHub: save the output as `.github/CODEOWNERS` and enable "Require review from Code Owners".
    - Azure DevOps: `skillkit-ops reviewers --format azure-devops` prints the required-reviewer path filters; also turn on "Prohibit the most recent pusher from approving their own changes".
7. **Import what exists**: merge the current workspace instructions into `context/workspace-instructions.md`; export the existing workspace skills, then bring each into `skills/`, merge it, move it to `AGENTS.md`, or retire it. Set `DEPLOY_FLAGS=--no-prune` until every legacy skill is decided.
8. **First deploy**: merge to `main` and check the plan step before approving prod.

## 2. Authoring workflow

The meta-skill (see the [README](../README.md)) drafts context; this is the review process around it in the `genie-context` repo.

1. Branch the context repo and run the meta-skill for a new scope, or for one skill and its trigger. It runs every step and ends with `skillkit check`, which writes lint, names, evals, the skill map and the Genie Code checklist into the run's `report.md`.
2. Review `report.md`: accept or change the decisions in `decisions.md`, spot-check `inventory.md`, and send `proposals.md` to its owners. Changed decisions are applied by a run about the affected skills.
3. As the owner, replace `TODO`s and narrow the `sources` globs to the files each skill really depends on; run `skillkit check <run folder> --repo <source checkout>` again after edits.
4. Try two prompts per skill in a real Genie Code Agent-mode chat with the skill in your user folder, from the checklist in `report.md`.
5. Set `status: active` for skills with an ADDS VALUE verdict; others can merge as `draft`.
6. Open the PR with `report.md` as its description; the pipeline posts lint results and the eval report. The owning team and the platform team review with the checklist in [the standard](../context-authoring/references/standard.md#8-review-checklist). The author cannot approve.
7. A person writes `AGENTS.md` from the candidate lines and checks it with `skillkit eval-context`; instruction changes go to the platform team, Unity Catalog comments to data owners.

A hand-written skill starts with `skillkit new <name>` and continues from step 3.

## 3. Evals

How evals work, how to write cases and journeys, the verdicts and the execution gate are in [references/evals.md](../context-authoring/references/evals.md). In a context repo, three things are added:

**Advisory or blocking.** During a pilot, run the PR gate in advisory mode (`EVAL_GATE=advisory`): failures show as warnings and reviewers decide. Switch to `blocking` once your eval cases are stable; then a FAILING, INCONCLUSIVE or NO EFFECT verdict fails the PR.

**Coexistence.** When any skill changes, the PR pipeline reruns routing for **every** active skill (`skillkit eval --mode routing`), so a new description cannot steal prompts from existing ones. `skillkit-ops changed` also returns every skill that uses a changed skill, so those are re-evaluated.

**`AGENTS.md` is evaluated too.** `skillkit eval-context --cases evals/agents.json --repos-root ~/repos` runs the same prompts with and without the `AGENTS.md` files (a cases file in the format of `evals.json`, with `agents` paths). Add `--agents-drafts <folder>` to evaluate drafts before they reach the source repo.

**Workspace instructions.** In a context repo, `context/workspace-instructions.md` is the master copy: evals inject it instead of the live file, and the pipeline deploys it. Evals and the build refuse to run while it still holds the framework's example.

Results are cached in `.skillkit-cache/` (git-ignored); `--refresh-failed` re-runs failed and inconclusive cases, `--no-cache` ignores the cache.

## 4. Multi-team repositories

The contract, team `AGENTS.md` files and variants are defined in [the standard](../context-authoring/references/standard.md#6-teams-variants-and-skills-that-use-skills). In a context repo, ownership is enforced by required reviewers per path: `skillkit-ops reviewers` prints a CODEOWNERS file or Azure DevOps filters, including variant reference files owned by another team.

## 5. Skills that use other skills

The rules (name the skill at the step, list it in `uses`, depth at most two, platform skills never use team skills) are in [the standard](../context-authoring/references/standard.md#6-teams-variants-and-skills-that-use-skills); lint enforces them.

**Test it in your pilot.** Genie Code does not document whether it loads a skill because another skill names it. Build one workflow two ways, referencing the skills it uses and self-contained, and compare them with `skillkit eval` and in a real chat: did Genie load the referenced skills, which version passes more cases, and which costs fewer tokens. If referencing loses, keep workflows self-contained and treat `uses` as documentation.

## 6. Deployment

A merge to `main` touching `skills/`, `context/` or `standard.yaml` runs `ops/pipelines/<ci>/deploy.yml`:

1. `skillkit-ops build` lints (refusing on errors), copies active skills without repo-only files, stamps owner and commit into each `SKILL.md`, and writes `manifest.json` with a SHA-256 per file.
2. The dev stage prints the plan (`create`, `replace`, `delete`, `upload`) and applies it.
3. The prod stage waits for approval, prints the plan and applies it.

`skillkit-ops deploy` verifies the checksums before uploading and writes the manifest to `/Workspace/.assistant/genie-context-manifest.json`, so what runs in a workspace can be traced to a commit. The deploy is authoritative: workspace skills not active in the repo are removed unless `--no-prune`.

**Rollback**: revert the PR, or set `status: deprecated`; the next deploy removes the skill.

## 7. Keeping context current

| Trigger | Detected by | Action |
| --- | --- | --- |
| Code or Git-hosted docs a skill was written from change | Source repo PR hook (`source-repo-freshness.yml`) comments with the affected skills and owners | Owner runs update mode with the changed paths |
| A cited Confluence page changes | Weekly run (`skillkit-ops confluence-check`) | Update mode, then `confluence-check <name> --write` |
| A cited page in another wiki changes | Not detected automatically; covered by the review period | Owner re-checks the page at review |
| Review period passes (120 days) | Weekly run (`skillkit-ops stale`) | Re-run evals; `skillkit-ops reviewed <name>`, update or deprecate |
| A wrong answer is reported | Users | Add the prompt as a failing eval case first, then fix |
| An eval regresses | Weekly regression run | Inspect the answer; fix the skill or the case |

**Update mode** edits only the lines that are no longer true, so earlier manual fixes survive:

> Use context-authoring in update mode for dp-create-silver-table; data-platform changed Databricks/Common/silver_lib/merge_template.py in commits abc123..def456.

## 8. skillkit and skillkit-ops reference

| Command | What it does |
| --- | --- |
| `init --scope S` | Starts a run: creates `authoring/runs/<date>-<scope>/` from the templates and lists the skills, decisions and backlog earlier runs left |
| `check <run folder> [skills] [--repo R] [--repos-root D] [--runs N] [--no-eval]` | Lint, name check, evals (with the execution gate when `eval.execution.warehouse_id` is set), skill map and agent checklist, written into the run's `report.md`; skills default to those `decisions.md` marks as changed |
| `lint [skills]` | Checks skills; with no names also catalog budget, overlap, dependencies and workspace instructions |
| `lint-agents <files>` | Checks `AGENTS.md` files (size, no emails or tokens) |
| `catalog [--installed DIR]` | Skills, status, owner, description tokens; active and planned (active + drafts, minus superseded) budget; with `--installed`, skills already in the workspace, their share of the budget and overlap with repo skills |
| `catalog --map [--eval-json F] [--scope S] [--out F]` | The skill map: table and Mermaid diagram of skills, `uses`, journeys, team variants and eval verdicts |
| `check-names [skills] --repo R [--repo R2] [--ignore N …] [--strict]` | Names in skills, their references and Markdown assets (inline code) that are not found in the source repos, as paths (globs allowed), file names or in contents |
| `agent-checklist [skills] [--prompts N] [--out F]` | Prompts to paste into the real agent (Genie Code) and what to look for, per skill and per journey, with a no-file-open prompt and a "read repo files?" check |
| `new <name> [--owner T]` | Scaffolds a draft skill; owner from the prefix, or `--owner` when no prefixes are configured |
| `eval [skills]` | Routing and answer tests with baseline. `--mode all\|routing\|answer`, `--runs N` (default `eval.runs`), `--threshold`, `--no-baseline`, `--require-value`, `--case-filter`, `--inspect ID`, `--repos-root`, `--agents-drafts DIR`, `--installed DIR`, `--no-cache`, `--refresh-failed`, `--no-journeys`, `--execute`, `--warehouse-id`, `--sql-var NAME=VALUE`, `--allow-example-instructions`, `--model`, `--judge`, `--out`, `--json` |
| `eval-context --cases F [--repos-root D] [--agents-drafts D] [--execute …]` | Evaluates `AGENTS.md` files with and without them; drafts in `--agents-drafts` are used where present |
| **skillkit-ops** | |
| `build [--out]` | Lints, then bundles active skills and instructions with checksums |
| `deploy [--build] [--dry-run] [--no-prune] [--profile]` | Verifies checksums, uploads skills, instructions and manifest |
| `freshness --repo R --changed … \| --changed-file F` | Skills whose sources match changed files (`--format text\|markdown\|json`) |
| `changed --base B` | Skills touched since `B`, plus the skills that use them (all, if shared context changed) |
| `stale` | Active skills past the review period |
| `reviewed <skills>` | Sets `last_reviewed` to today |
| `confluence-check [skills] [--write]` | Compares recorded Confluence versions with the live pages |
| `reviewers [--format codeowners\|azure-devops]` | Owners per path: a CODEOWNERS file (default) or Azure DevOps reviewer filters |

**Lint codes** are listed in [the standard](../context-authoring/references/standard.md#9-lint-rules).

## 9. Configuration: standard.yaml

| Key | Purpose |
| --- | --- |
| `platform_team`, `teams`, `prefixes` | Who owns which skill prefix; each team's `codeowners` (GitHub) or `reviewers` (Azure DevOps) group |
| `limits` | Description, body, catalog, instruction and `AGENTS.md` budgets |
| `review_period_days` | When an active skill counts as stale |
| `review` | `end` (the meta-skill runs every step) or `before-write` (it stops after identifying the skills, for a review) |
| `sections` | Required and optional `SKILL.md` sections |
| `catalog` | Overlap warning threshold; maximum dependency depth |
| `forbidden_patterns`, `forbidden_patterns_context` | Regexes rejected in skills / in instructions and `AGENTS.md` |
| `workspace` | `consumer` (the agent under test, as evals describe it), `output_folder`, `personal_skills_path`, and the deploy paths (skills, instructions, manifest) |
| `eval` | Model endpoint, judge endpoint, max tokens, runs, trigger threshold, `repos_root`, `execution` (warehouse and SQL variables for the execution gate) |

## 10. Pipelines

The same four jobs exist for GitHub Actions and Azure DevOps. Copy one set into your repos.

| Job | GitHub Actions | Azure DevOps | Runs | Does |
| --- | --- | --- | --- | --- |
| PR validation | `ops/pipelines/github-actions/pr-validation.yml` | `ops/pipelines/azure-devops/pr-validation.yml` | Every PR to the context repo | Unit tests, lint, evals with baseline for changed skills and the skills that use them (3 runs), routing for all skills, report posted on the PR |
| Deploy | `ops/pipelines/github-actions/deploy.yml` | `ops/pipelines/azure-devops/deploy.yml` | Merge to `main` | Build, deploy to dev, then prod after approval |
| Maintenance | `ops/pipelines/github-actions/maintenance.yml` | `ops/pipelines/azure-devops/maintenance.yml` | Mondays 05:00 UTC | Stale reviews, changed Confluence pages, regression eval, budget use; fails if an owner has work |
| Source-repo freshness | `ops/pipelines/github-actions/source-repo-freshness.yml` (copy into each source repo) | `ops/pipelines/azure-devops/templates/source-repo-freshness.yml` (include from each source repo) | Every PR to a source repo | Comments with the skills the change may affect, and their owners; never blocks |

Notes:

- GitHub Actions: the workflows post comments with `gh pr comment` and need `pull-requests: write`. Private source or context repos need a read token secret (`SOURCE_REPO_TOKEN`, `CONTEXT_REPO_TOKEN`).
- Azure DevOps: Azure Repos ignores `pr:` triggers in YAML, so add PR validation as a build validation branch policy. The build service needs "Contribute to pull requests" to post comments.

## 11. Development

```bash
pip install -e ".[dev]"
pytest -q          # lint rules, freshness, build and checksums, deploy (mocked), evals (fake model), a dry run of the installed skill
```

The code is plain Python with `pyyaml`, `requests` and (optionally) `databricks-sdk`. `deploy` and `eval` import the SDK lazily, so linting and building need no Databricks access.

To add a lint rule: add the check in `context-authoring/scripts/skillkit/lint.py` with a new code, document it in `context-authoring/references/standard.md` (section 9), and add a test in `tests/test_lint.py`.

