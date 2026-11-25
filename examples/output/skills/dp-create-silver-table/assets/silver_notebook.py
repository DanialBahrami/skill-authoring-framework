# Databricks notebook source
# Silver merge notebook for <source>_<table>.
# TODO (meta-skill): replace this skeleton with the distilled structure of
# Databricks/Silver/crm_customer and the real merge_table_silver signature
# from Common/silver_lib/merge_template. Keep widgets; never hardcode catalogs.

# COMMAND ----------

# MAGIC %run ../Common/silver_lib/merge_template

# COMMAND ----------

# Widgets supply environment and region; see the repo AGENTS.md for widget names.
# TODO (meta-skill): widget definitions.

# COMMAND ----------

# TODO (meta-skill): read the Bronze table with the incremental filter and call merge_table_silver.
