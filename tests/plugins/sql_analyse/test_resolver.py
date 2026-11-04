import json
from pathlib import Path

import pytest

from lib.plugins.contract import ContractError, check_arguments, normalize
from resources.plugins.sqlplus.analyse.exceptions import AnalysePluginException
from resources.plugins.sqlplus.analyse.resolver import AnalyseResolver

MANIFEST = Path(__file__).parents[3] / "resources/plugins/sqlplus/analyse/plugin.json"


@pytest.mark.parametrize("value", [None, ""])
def test_a_missing_path_is_reported_as_required(value) -> None:
    with pytest.raises(AnalysePluginException, match="'path' is required"):
        AnalyseResolver().resolve_path(value)


def test_a_path_of_the_wrong_type_is_still_rejected() -> None:
    with pytest.raises(AnalysePluginException, match="'path' must be a string"):
        AnalyseResolver().resolve_path(42)


def test_an_existing_directory_resolves(tmp_path) -> None:
    assert AnalyseResolver().resolve_path(str(tmp_path)) == tmp_path


def test_the_manifest_stops_a_run_without_path_before_the_plugin_starts() -> None:
    contract = normalize(json.loads(MANIFEST.read_text(encoding="utf-8")))

    with pytest.raises(ContractError, match="'path' is required"):
        check_arguments(contract, {})
