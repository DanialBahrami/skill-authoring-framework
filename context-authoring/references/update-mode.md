# Update mode: one skill, changed sources

Triggered by a freshness comment on a source-repo PR, a changed Confluence page, a failed eval, a review date, or a reported wrong answer.

1. Get the skill name and the trigger: changed paths with the commit range, changed page ids, the failing eval case, or the wrong answer with the prompt that caused it.
2. Read the skill folder and its `skill.yaml` sources. Read only the changed sources: `git diff <range> -- <paths>` in the source repo, the page versions in Confluence (compare recorded and current version).
3. Decide what changed for the agent: a renamed helper, a new step, a removed template, a new rule. If nothing the skill says is affected, change nothing except `last_reviewed`.
4. Edit the smallest set of lines that makes the skill true again. Keep everything else byte for byte: other lines may hold fixes people made after evals.
5. A reported wrong answer: first add it to `evals/evals.json` as a case that fails today, then change the skill until it passes.
6. Adjust `sources` if files moved. Run `skillkit reviewed <name>` and, for Confluence, `skillkit confluence-check <name> --write`.
7. Run `skillkit lint <name>` and `skillkit eval <name>`. All cases pass before the PR.
8. Open the PR with: trigger, what changed in the skill, eval report.
