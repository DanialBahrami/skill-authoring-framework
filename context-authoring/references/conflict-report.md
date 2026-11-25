# Conflict report template (conflicts.md)

One row per difference. Decisions are made by the platform team (who owns the shared conventions) and the owning team together; record who decided. The two rows below are examples.

| # | Task or topic | Where | Approach A (source) | Approach B (source) | Breaks the contract? | Suggested decision | Reason | Decision | Decided by |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Create a Silver table | Platform vs Forecasting folders | `Setup/Silver/setup` + `merge_table_silver` (`Databricks/Silver/...`) | Own helper, DDL in notebook (`<team path>`) | No | Variant | Both produce the same table contract; the team's helper is used in all 14 of its notebooks | Variant (accepted suggestion) | <name> |
| 2 | PII tag name | Code vs workspace guardrails | `pii` (`Bronze/autoloader`) | `pii_level` (workspace instructions) | Yes: tag names are contract | Align to A | Masking policies read `pii`; nothing reads `pii_level` | | |

## Suggesting, not deciding

Fill "Suggested decision" and "Reason" for every row, from evidence: which way the code uses more, which way the contract or docs require, which side is newer. Then show the list and stop. People decide, usually in one reply ("accept all except 3 and 7"); record "accepted suggestion" and who accepted it, or the decision they gave instead.

- A row that breaks the contract keeps its suggestion but is never treated as accepted by a blanket reply; ask for it by number.
- Without a reply, nothing is accepted: rows stay open, and only skills that depend on no open row are generated.
- Say in one sentence why you stop: generating from a guessed side gives the agent a rule that is wrong half the time.

Decision values:

- **Variant**: both are legitimate; generate the platform default in the skill and the team's way as `references/<team>.md`.
- **Align to A/B**: one way wins; the skill and `AGENTS.md` describe only that one; the other side gets a backlog item to migrate.
- **Fix code** or **Fix docs**: the skill follows the decision; the item goes to the owner's backlog.
- **Open**: no decision yet; do not generate content that depends on it, and list it in `summary.md`.

Contract-breaking differences are never a Variant.
