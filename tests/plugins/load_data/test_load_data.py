"""
Tests for the load_data plugin.
"""

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from lib.plugins.arguments import PluginArguments
from resources.plugins.custom.load_data.exceptions import LoadDataPluginException
from resources.plugins.custom.load_data.plugin import LoadDataPlugin
from resources.plugins.custom.load_data.resolver import LoadDataResolver


def _output(stdout="", success=True, error_message=None):
    return SimpleNamespace(
        success=success,
        stdout=stdout,
        stderr="",
        error_message=error_message,
    )


class TestLoadDataPlugin:

    def setup_method(self):
        self.context = Mock()
        self.context.outputs = {}
        self.context.artifacts = {}
        self.context.workspace = Path("/tmp/workspace")
        self.context.activity.return_value = nullcontext()
        self.context.filesystem.is_file.return_value = True
        self.context.filesystem.read_text.side_effect = lambda path: path.read_text(
            encoding="utf-8",
        )

        self.scripts = []

    def _plugin(self, **arguments):
        self.context.arguments = PluginArguments(
            {
                "connection": {"IP": "db", "PORT": 1521, "SID": "orcl"},
                "credentials": {"username": "load", "password": "secret"},
                "status_check": {"table": "LOAD_STATUS"},
                **arguments,
            },
        )

        return LoadDataPlugin(self.context)

    def _executor(self, executor_class, counts):
        counts = iter(counts)

        def execute(sqlhome, execution):
            name = execution.script.name
            body = self.context.filesystem.write_text.call_args[0][1]
            self.scripts.append((name, body))
            if name.endswith("_status.sql"):
                return _output(f"__ENTROPY_COUNT__|{next(counts)}\n")
            return _output("PL/SQL procedure successfully completed.\n")

        executor_class.return_value.execute.side_effect = execute

    @patch("resources.plugins.custom.load_data.plugin.SqlPlusExecutor")
    def test_runs_both_procedures_when_all_successful(self, executor_class):
        self._executor(executor_class, [0, 0])

        result = self._plugin().execute()

        assert result.success is True
        assert result.changed is True
        assert [name for name, _ in self.scripts] == [
            "1_procedure.sql",
            "1_status.sql",
            "2_procedure.sql",
            "2_status.sql",
        ]
        assert "BEGIN\n    LOAD_PKG.PROCEDURE1;\nEND;\n/" in self.scripts[0][1]
        assert "LOAD_PKG.PROCEDURE2;" in self.scripts[2][1]
        assert self.scripts[0][1].rstrip().endswith("/\n\nEXIT")
        assert "FROM LOAD_STATUS" in self.scripts[1][1]
        assert "STATUS IS NULL" in self.scripts[1][1]
        assert "STATUS <> 'SUCCESS'" in self.scripts[1][1]
        assert result.outputs["completed"] == 2

    @patch("resources.plugins.custom.load_data.plugin.SqlPlusExecutor")
    def test_stops_before_second_procedure_when_rows_not_successful(self, executor_class):
        self._executor(executor_class, [4])

        result = self._plugin().execute()

        assert result.success is False
        assert result.changed is True
        assert "4 row(s) in LOAD_STATUS" in result.errors[0]
        assert [name for name, _ in self.scripts] == ["1_procedure.sql", "1_status.sql"]
        assert result.outputs["completed"] == 0
        assert result.outputs["results"] == [
            {"sql": "procedure1.sql", "table": "LOAD_STATUS", "not_successful": 4},
        ]

    @patch("resources.plugins.custom.load_data.plugin.SqlPlusExecutor")
    def test_stops_after_second_procedure(self, executor_class):
        self._executor(executor_class, [0, 1])

        result = self._plugin().execute()

        assert result.success is False
        assert "after procedure2.sql" in result.errors[0]
        assert result.outputs["completed"] == 1

    @patch("resources.plugins.custom.load_data.plugin.SqlPlusExecutor")
    def test_procedure_failure_fails_step(self, executor_class):
        executor_class.return_value.execute.return_value = _output(
            success=False,
            error_message="ORA-06550: line 2",
        )

        result = self._plugin().execute()

        assert result.success is False
        assert "ORA-06550" in result.errors[0]
        assert result.changed is False

    def test_missing_sql_file_fails_before_running(self):
        self.context.filesystem.is_file.side_effect = lambda path: path.name != "procedure2.sql"

        with patch("resources.plugins.custom.load_data.plugin.SqlPlusExecutor") as executor_class:
            result = self._plugin().execute()

        assert result.success is False
        assert "SQL file does not exist" in result.errors[0]
        executor_class.return_value.execute.assert_not_called()
        assert result.changed is False

    @patch("resources.plugins.custom.load_data.plugin.SqlPlusExecutor")
    def test_per_procedure_status_check(self, executor_class):
        self._executor(executor_class, [0, 0])

        result = self._plugin(
            procedures=[
                "procedure1.sql",
                {
                    "sql": "procedure2.sql",
                    "status_check": {"table": "OTHER", "column": "STATE", "success_value": "DONE"},
                },
            ],
        ).execute()

        assert result.success is True
        assert "FROM OTHER" in self.scripts[3][1]
        assert "STATE <> 'DONE'" in self.scripts[3][1]


class TestLoadDataResolver:

    def test_requires_status_check(self):
        with pytest.raises(LoadDataPluginException):
            LoadDataResolver.procedures(["p.sql"], None)

    @pytest.mark.parametrize("name", ["../p.sql", "/etc/p.sql", "", 5])
    def test_rejects_sql_outside_the_sqls_folder(self, name):
        with pytest.raises(LoadDataPluginException):
            LoadDataResolver.procedures([name], {"table": "T"})

    def test_rejects_bad_status_table(self):
        with pytest.raises(LoadDataPluginException):
            LoadDataResolver.procedures(["p.sql"], {"table": "T; DROP TABLE X"})

    def test_quotes_success_value(self):
        check = LoadDataResolver.status_check({"table": "T", "success_value": "O'K"})

        assert check["success_value"] == "O''K"
