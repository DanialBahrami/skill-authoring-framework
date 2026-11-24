---
name: dp-create-silver-table
description: >-
  Creates a new Silver table in the data-platform repo from an existing Bronze table:
  setup DDL, the per-table merge notebook on the shared notebook template, and the
  matching global table and view. Use when the user asks to add, create or build a
  silver table, a silver notebook or a merge from bronze to silver, including for
  Forecasting tables. Not for changing an existing silver table.
---

# Create a Silver table

Produces the DDL, the merge notebook and the global twin for one new Silver table, ready for a pull request. Changing an existing table is a different task (deployment scripts).

## Steps

1. Decide which conventions apply. If the target notebook is under the Forecasting folder or the table belongs to a Forecasting schema, follow [references/forecasting.md](references/forecasting.md) instead of steps 3-6. Otherwise continue; these are the platform defaults.
2. Confirm the Bronze table `<region>_bronze.<source>_<table>` exists and has rows with `_isActive` true. If it does not exist, stop and onboard the source table first; Silver reads only from Bronze.
3. Add the table DDL to `Databricks/Setup/Silver/setup`. Include the source columns, the Silver technical columns `_load_date TIMESTAMP, _is_deleted BOOLEAN, _is_active BOOLEAN`, and `COMMENT 'UQ'` on every merge key column. The merge helper finds the key from the `UQ` comments, so a missing comment breaks the merge.
4. If the source has PII columns, split them into `<source>_<table>_pii` with `_is_restricted BOOLEAN` and tag them `pii`. Consumers of the main table must not need the PII table.
5. Create the notebook `Databricks/Silver/<source>_<table>` from [assets/silver_notebook.py](assets/silver_notebook.py). It runs `%run ../Common/silver_lib/merge_template` and calls `merge_table_silver`; do not write a MERGE by hand, because the helper handles soft deletes and technical columns.
6. Add the global twin: a `global_silver.<table>` with `region_key STRING COMMENT 'UQ'` in `Databricks/Setup/Global/Silver/gl_silver_setup_tables`, partitioned by `region_key`, and a `v_<table>` view in `gl_silver_setup_views`. `update_global_table` overwrites by region partition, so the partitioning is required.
7. TODO (generator): how a new table is registered in the silver workflow (`bundle_resources/jobs/silver/`).
8. List the files changed for the pull request description.

## Verify

- Run the notebook in development with the `dev_build` bundle target and widgets for one region.
- Row count of the Silver table with `_is_deleted = false AND _is_active = true` equals the count of distinct merge keys among active Bronze rows.
- The merge key is unique: `SELECT <keys>, COUNT(*) FROM ... GROUP BY <keys> HAVING COUNT(*) > 1` returns no rows.
- `global_silver.<table>` has rows for the region you ran.

## Rules

- Read Bronze with `_UpdatedDate >= MaxLoadDate AND _isActive is true`; the template provides `MaxLoadDate`. Reading all of Bronze reprocesses history on every run.
- Use `CLUSTER BY` only for standalone tables; inside the global family keep `PARTITIONED BY (region_key)`.
