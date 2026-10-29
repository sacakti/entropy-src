-- Placeholder: replace with the real SG insert for app1.
-- The dblink, country and product placeholders (see README) are replaced before it runs.
-- End statements with ';' and PL/SQL blocks with '/'. Do not COMMIT or EXIT:
-- the plugin commits after the script succeeds.

INSERT INTO APP1_TRD
SELECT *
FROM APP1_TRD@{dblink};
