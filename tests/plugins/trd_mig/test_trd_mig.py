"""
Tests for the trd_mig plugin.
"""

import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from lib.plugins import contract
from lib.plugins.arguments import PluginArguments
from resources.plugins.custom.trd_mig.exceptions import TrdMigPluginException
from resources.plugins.custom.trd_mig.plugin import TrdMigPlugin, parse_count
from resources.plugins.custom.trd_mig.resolver import TrdMigResolver

PLUGIN_DIRECTORY = (
    Path(__file__).resolve().parents[3] / "resources" / "plugins" / "custom" / "trd_mig"
)

MAPPING = json.loads(
    (PLUGIN_DIRECTORY / "mapping.json").read_text(encoding="utf-8"),
)


def _output(count):
    return SimpleNamespace(
        success=True,
        stdout=f"__ENTROPY_COUNT__|{count}\n1 row selected.\n",
        stderr="",
        error_message=None,
    )


class TestTrdMigPlugin:

    def setup_method(self):
        self.context = Mock()
        self.context.outputs = {}
        self.context.artifacts = {}
        self.context.workspace = Path("/tmp/workspace")
        self.context.filesystem.is_file.return_value = True
        self.context.filesystem.read_json.return_value = MAPPING
        self.context.filesystem.read_text.side_effect = lambda path: path.read_text(
            encoding="utf-8",
        )
        self.context.activity.return_value = nullcontext()

        self.scripts = []

    def _plugin(self, **arguments):
        self.context.arguments = PluginArguments(
            {
                "connection": {"IP": "db", "PORT": 1521, "SID": "orcl"},
                "credentials": {"username": "trd", "password": "secret"},
                "country": "in",
                "product": "app1",
                **arguments,
            },
        )

        return TrdMigPlugin(self.context)

    def _executor(self, executor_class, counts):
        counts = iter(counts)

        def execute(sqlhome, execution):
            name = execution.script.name
            body = self.context.filesystem.write_text.call_args[0][1]
            self.scripts.append((name, body))
            if name.endswith("_count.sql"):
                return _output(next(counts))
            return _output(0)

        executor_class.return_value.execute.side_effect = execute

    @patch("resources.plugins.custom.trd_mig.plugin.SqlPlusExecutor")
    def test_truncate_insert_and_count(self, executor_class):
        self._executor(executor_class, [0, 42])

        result = self._plugin(truncate=True).execute()

        assert result.success is True
        assert result.changed is True
        assert [name for name, _ in self.scripts] == [
            "app1_truncate.sql",
            "app1_count.sql",
            "app1_insert.sql",
            "app1_count.sql",
        ]
        assert "TRUNCATE TABLE TRD_STAGE;\nTRUNCATE TABLE TRD_STAGE_DETAIL;" in self.scripts[0][1]
        assert "FROM APP1_TRD@TRD_IN_LINK;\nCOMMIT;" in self.scripts[2][1]
        assert result.outputs["truncated"] == ["TRD_STAGE", "TRD_STAGE_DETAIL"]
        assert result.outputs["sql_file"] == "IN/app1.sql"
        assert result.outputs["count_before"] == 0
        assert result.outputs["count_after"] == 42
        assert result.outputs["counts"] == {"app1": 42}
        self.context.ask.assert_not_called()

    @patch("resources.plugins.custom.trd_mig.plugin.SqlPlusExecutor")
    def test_truncate_skipped_when_false(self, executor_class):
        self._executor(executor_class, [0, 5])

        result = self._plugin().execute()

        assert result.success is True
        assert [name for name, _ in self.scripts] == [
            "app1_count.sql",
            "app1_insert.sql",
            "app1_count.sql",
        ]
        assert result.outputs["truncated"] == []

    @patch("resources.plugins.custom.trd_mig.plugin.SqlPlusExecutor")
    def test_non_empty_table_declined_stops(self, executor_class):
        self._executor(executor_class, [3])
        self.context.ask.return_value = "no"

        result = self._plugin().execute()

        assert result.success is False
        assert "not empty" in result.errors[0]
        assert [name for name, _ in self.scripts] == ["app1_count.sql"]

    @patch("resources.plugins.custom.trd_mig.plugin.SqlPlusExecutor")
    def test_non_empty_table_confirmed_proceeds(self, executor_class):
        self._executor(executor_class, [3, 10])
        self.context.ask.return_value = "yes"

        result = self._plugin().execute()

        assert result.success is True
        assert result.outputs["count_after"] == 10
        assert self.context.ask.call_args.kwargs["default"] == "no"

    @patch("resources.plugins.custom.trd_mig.plugin.SqlPlusExecutor")
    def test_sqlplus_failure_fails_step(self, executor_class):
        executor_class.return_value.execute.return_value = SimpleNamespace(
            success=False,
            stdout="",
            stderr="",
            error_message="ORA-00942: table or view does not exist",
        )

        result = self._plugin().execute()

        assert result.success is False
        assert "ORA-00942" in result.errors[0]

    @patch("resources.plugins.custom.trd_mig.plugin.SqlPlusExecutor")
    def test_truncate_tables_argument_overrides_profile(self, executor_class):
        self._executor(executor_class, [0, 1])

        result = self._plugin(truncate=True, truncate_tables=["MY_TABLE"]).execute()

        assert result.success is True
        assert self.scripts[0][1].count("TRUNCATE TABLE") == 1
        assert "TRUNCATE TABLE MY_TABLE;" in self.scripts[0][1]

    @patch("resources.plugins.custom.trd_mig.plugin.SqlPlusExecutor")
    def test_truncate_profile_argument(self, executor_class):
        self.context.filesystem.read_json.return_value = dict(
            MAPPING,
            truncate_profiles={"default": ["A"], "other": ["B"]},
        )
        self._executor(executor_class, [0, 1])

        result = self._plugin(truncate=True, truncate_profile="other").execute()

        assert result.success is True
        assert result.outputs["truncated"] == ["B"]

    @patch("resources.plugins.custom.trd_mig.plugin.SqlPlusExecutor")
    def test_profiles_not_needed_when_truncate_false(self, executor_class):
        mapping = {key: value for key, value in MAPPING.items() if key != "truncate_profiles"}
        self.context.filesystem.read_json.return_value = mapping
        self._executor(executor_class, [0, 1])

        result = self._plugin().execute()

        assert result.success is True

    def test_missing_sql_file_fails_before_running(self):
        self.context.filesystem.is_file.side_effect = lambda path: path.suffix == ".json"

        with patch("resources.plugins.custom.trd_mig.plugin.SqlPlusExecutor") as executor_class:
            result = self._plugin(truncate=True).execute()

        assert result.success is False
        assert "SQL file does not exist" in result.errors[0]
        executor_class.return_value.execute.assert_not_called()

    def test_unknown_product_fails_step(self):
        result = self._plugin(product="app9").execute()

        assert result.success is False
        assert "Unknown product 'app9'" in result.errors[0]


class TestTrdMigResolver:

    def test_mapping_selects_country_sql_file(self):
        settings = TrdMigResolver.mapping(
            MAPPING, country="sg", product="APP2", truncate_profile="default"
        )

        assert settings["sql_file"] == "SG/app2.sql"
        assert settings["dblink"] == "TRD_SG_LINK"
        assert settings["count_table"] == "APP2_TRD"
        assert settings["truncate_source"] == "profile:default"

    def test_mapping_single_sql_file_for_all_products(self):
        mapping = {
            "countries": {"IN": {"sql": "IN/all.sql"}},
            "products": {"p": {"count_table": "T"}},
        }

        settings = TrdMigResolver.mapping(mapping, country="IN", product="p")

        assert settings["sql_file"] == "IN/all.sql"
        assert settings["truncate"] == []

    def test_mapping_truncate_precedence(self):
        mapping = dict(MAPPING, truncate_profiles={"default": ["A"], "other": ["B"]})

        assert TrdMigResolver.mapping(mapping, country="IN", product="app1")["truncate"] == []
        assert TrdMigResolver.mapping(
            mapping, country="IN", product="app1", truncate_profile="default"
        )["truncate"] == ["A"]
        assert TrdMigResolver.mapping(
            mapping, country="IN", product="app1", truncate_profile="other"
        )["truncate"] == ["B"]
        assert TrdMigResolver.mapping(
            mapping,
            country="IN",
            product="app1",
            truncate_profile="other",
            truncate_tables=["C"],
        )["truncate"] == ["C"]

    @pytest.mark.parametrize(
        "mapping",
        [
            {"countries": {"IN": {"sql": "../x.sql"}}, "products": {"p": {"count_table": "T"}}},
            {"countries": {"IN": {"sql": "/etc/x.sql"}}, "products": {"p": {"count_table": "T"}}},
            {"countries": {"IN": {"sql": "a.sql"}}, "products": {"p": {"count_table": "T; DROP"}}},
        ],
    )
    def test_mapping_rejects_invalid_entries(self, mapping):
        with pytest.raises(TrdMigPluginException):
            TrdMigResolver.mapping(mapping, country="IN", product="p")

    def test_unknown_truncate_profile(self):
        with pytest.raises(TrdMigPluginException, match="Unknown truncate profile 'missing'"):
            TrdMigResolver.mapping(
                MAPPING, country="IN", product="app1", truncate_profile="missing"
            )

    def test_sql_requires_dblink_when_used(self):
        with pytest.raises(TrdMigPluginException):
            TrdMigResolver.sql(
                "INSERT INTO T SELECT * FROM T@{dblink};",
                country="IN",
                product="p",
                dblink=None,
                sql_file="IN/p.sql",
            )

    def test_credentials_accepts_json_string(self):
        credentials = TrdMigResolver.credentials('{"username": "u", "password": "p"}')

        assert credentials == {"username": "u", "password": "p"}


def test_parse_count_without_marker_raises():
    with pytest.raises(TrdMigPluginException):
        parse_count("no rows selected")


def test_dropdown_choices_come_from_mapping():
    arguments = {
        item["name"]: item for item in contract.plugin_contract(PLUGIN_DIRECTORY)["arguments"]
    }

    assert arguments["country"]["choices"] == list(MAPPING["countries"])
    assert arguments["product"]["choices"] == list(MAPPING["products"])


def test_truncate_profile_defaults_to_default():
    manifest = json.loads((PLUGIN_DIRECTORY / "plugin.json").read_text(encoding="utf-8"))
    arguments = {item["name"]: item for item in manifest["arguments"]}

    assert arguments["truncate_profile"]["default"] == "default"
    assert "default" in MAPPING["truncate_profiles"]
