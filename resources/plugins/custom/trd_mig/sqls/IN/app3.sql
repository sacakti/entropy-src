-- Placeholder: replace with the real IN insert for app3.
-- The dblink, country and product placeholders (see README) are replaced before it runs.
-- End statements with ';' and PL/SQL blocks with '/'. Do not COMMIT or EXIT:
-- the plugin commits after the script succeeds.

INSERT INTO APP3_TRD
SELECT *
FROM APP3_TRD@{dblink};
