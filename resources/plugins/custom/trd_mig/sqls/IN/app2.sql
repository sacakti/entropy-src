-- Placeholder: replace with the real IN insert for app2.
-- The dblink, country and product placeholders (see README) are replaced before it runs.
-- End statements with ';' and PL/SQL blocks with '/'. Do not COMMIT or EXIT:
-- the plugin commits after the script succeeds.

INSERT INTO APP2_TRD
SELECT *
FROM APP2_TRD@{dblink};
