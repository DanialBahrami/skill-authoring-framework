-- Unity Catalog comment and tag proposals: <scope>
-- For the data owners to review and run. Nothing here is applied by the meta-skill.
-- One statement per fact; each with its source. Use the environment's catalog through a
-- variable or widget when running; the names below are placeholders.
-- Comments say what the data is (meaning, grain, source system, PII), not how to use it.

-- Source: <repo path or doc page>
COMMENT ON TABLE ${catalog}.<schema>.<table> IS '<One row per ... . Source: ... .>';

-- Source: <repo path or doc page>
ALTER TABLE ${catalog}.<schema>.<table> ALTER COLUMN <column> COMMENT '<meaning; unit; allowed values>';

-- Source: <repo path or doc page>
ALTER TABLE ${catalog}.<schema>.<table> ALTER COLUMN <column> SET TAGS ('<tag>' = '<value>');
