# Conflict report template (conflicts.md)

One row per difference. Decisions are made by the platform team and the owning team together; record who decided.

| # | Task or topic | Where | Approach A (source) | Approach B (source) | Breaks the contract? | Decision | Decided by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Create a Silver table | Platform vs Forecasting folders | `Setup/Silver/setup` + `merge_table_silver` (`Databricks/Silver/...`) | Own helper, DDL in notebook (`<team path>`) | No / Yes: <which contract rule> | Variant / Align to A / Align to B / Fix code | |
| 2 | PII tag name | Code vs workspace guardrails | `pii` (`Bronze/autoloader`) | `pii_level` (workspace instructions) | Yes | | |

Decision values:

- **Variant**: both are legitimate; generate the platform default in the skill and the team's way as `references/<team>.md`.
- **Align to A/B**: one way wins; the skill and `AGENTS.md` describe only that one; the other side gets a backlog item to migrate.
- **Fix code** or **Fix docs**: the skill follows the decision; the item goes to the owner's backlog.
- **Open**: no decision yet; do not generate content that depends on it, and list it in `summary.md`.

Contract-breaking differences are never a Variant.
