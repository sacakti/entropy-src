"""
Tests for the quay.generic plugin: retention policy, Quay client, plugin.
"""

from __future__ import annotations

import io
import json
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import pytest

from lib.plugins import contract
from lib.plugins.arguments import PluginArguments
from resources.plugins.quay.generic.client import QuayClient
from resources.plugins.quay.generic.exceptions import QuayApiError, QuayRuleError
from resources.plugins.quay.generic.plugin import QuayGenericPlugin
from resources.plugins.quay.generic.policy import parse_rules, plan_repository

PLUGIN_DIRECTORY = (
    Path(__file__).resolve().parents[3] / "resources" / "plugins" / "quay" / "generic"
)
DAY = 86_400
NOW = 1_000 * DAY


def _tags(*names: str, age_days: int = 100) -> List[Dict[str, Any]]:
    """Tags oldest first: the last name is the newest."""

    return [
        {
            "name": name,
            "start_ts": NOW - (age_days + len(names) - i) * DAY,
            "manifest_digest": f"sha:{i}",
        }
        for i, name in enumerate(names)
    ]


def _deleted(decisions) -> List[str]:
    return [decision.tag for decision in decisions if not decision.keep]


# ----------------------------------------------------------------------
# Policy
# ----------------------------------------------------------------------


def test_keeps_the_newest_six_by_default() -> None:
    tags = _tags(*[f"1.{i}" for i in range(10)])
    decisions = plan_repository("orders", tags, keep=6, now=NOW)
    assert _deleted(decisions) == ["1.3", "1.2", "1.1", "1.0"]
    assert [d.tag for d in decisions][:6] == ["1.9", "1.8", "1.7", "1.6", "1.5", "1.4"]


def test_protected_tags_are_kept_and_not_counted() -> None:
    tags = _tags("latest", "a", "b", "c")
    decisions = plan_repository("orders", tags, keep=2, protect=["latest"], now=NOW)
    assert _deleted(decisions) == ["a"]
    assert next(d for d in decisions if d.tag == "latest").reason == "protected"


def test_rules_keep_their_own_newest_tags() -> None:
    rules = parse_rules(
        [
            {"name": "prs", "tags": "pr-*", "keep": 0},
            {"name": "releases", "tags": "re:^v\\d+$", "keep": 2},
            {"name": "hotfix", "tags": ["hotfix-*"]},
        ]
    )
    tags = _tags("v1", "pr-1", "hotfix-1", "v2", "dev-1", "v3", "pr-2", "dev-2")
    decisions = plan_repository("orders", tags, keep=1, rules=rules, now=NOW)
    assert sorted(_deleted(decisions)) == ["dev-1", "pr-1", "pr-2", "v1"]
    by_tag = {d.tag: d for d in decisions}
    assert by_tag["hotfix-1"].rule == "hotfix" and by_tag["hotfix-1"].keep
    assert by_tag["v3"].rule == "releases" and by_tag["dev-2"].rule == "default"


def test_rules_can_be_limited_to_repositories() -> None:
    rules = parse_rules([{"tags": "*", "keep": 1, "repositories": ["payments-*"]}])
    tags = _tags("a", "b", "c")
    assert _deleted(plan_repository("payments-api", tags, keep=6, rules=rules, now=NOW)) == [
        "b",
        "a",
    ]
    assert _deleted(plan_repository("orders", tags, keep=6, rules=rules, now=NOW)) == []


def test_young_tags_are_spared() -> None:
    tags = _tags("old", age_days=30) + _tags("new1", "new2", age_days=1)
    assert _deleted(plan_repository("r", tags, keep=1, min_age_days=7, now=NOW)) == ["old"]
    rules = parse_rules([{"tags": "*", "keep": 1, "min_age_days": 0}])
    assert sorted(
        _deleted(plan_repository("r", tags, keep=1, rules=rules, min_age_days=7, now=NOW))
    ) == [
        "new1",
        "old",
    ]


@pytest.mark.parametrize(
    "rules, message",
    [
        (["pr-*"], "must be an object"),
        ([{"keep": 1}], "'tags' is required"),
        ([{"tags": "x", "keep": -1}], "'keep'"),
        ([{"tags": "x", "keep": True}], "'keep'"),
        ([{"tags": "re:(", "keep": 1}], "invalid regular expression"),
        ([{"tags": "x", "older": 3}], "unknown field"),
    ],
)
def test_bad_rules_are_refused(rules: list, message: str) -> None:
    with pytest.raises(QuayRuleError, match=message):
        parse_rules(rules)


# ----------------------------------------------------------------------
# Client
# ----------------------------------------------------------------------


class _Response(io.BytesIO):
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_: Any) -> None:
        return None


def test_client_pages_and_authenticates() -> None:
    answers = [
        {"repositories": [{"name": "a"}], "next_page": "t2"},
        {"repositories": [{"name": "b"}]},
        {"tags": [{"name": "1"}], "has_additional": True, "page": 1},
        {"tags": [{"name": "2"}], "has_additional": False, "page": 2},
        None,
    ]
    requests: list = []

    def fake_urlopen(request, **_):
        requests.append(request)
        answer = answers[len(requests) - 1]
        return _Response(b"" if answer is None else json.dumps(answer).encode())

    with patch("resources.plugins.quay.generic.client.urlopen", fake_urlopen):
        client = QuayClient("https://quay.test/", "secret")
        assert client.repositories("ns") == ["a", "b"]
        assert [t["name"] for t in client.tags("ns", "a")] == ["1", "2"]
        client.delete_tag("ns", "a", "v1+build")

    assert requests[0].get_header("Authorization") == "Bearer secret"
    assert requests[1].full_url.endswith("namespace=ns&next_page=t2")
    assert "page=2" in requests[3].full_url
    assert requests[4].get_method() == "DELETE"
    assert requests[4].full_url == "https://quay.test/api/v1/repository/ns/a/tag/v1%2Bbuild"


def test_client_errors_carry_the_status() -> None:
    def fake_urlopen(request, **_):
        raise HTTPError(
            request.full_url, 403, "Forbidden", {}, io.BytesIO(b'{"error_message": "no"}')
        )

    with (
        patch("resources.plugins.quay.generic.client.urlopen", fake_urlopen),
        pytest.raises(QuayApiError, match="HTTP 403 no") as raised,
    ):
        QuayClient("https://quay.test", "t").tags("ns", "a")
    assert raised.value.status == 403


# ----------------------------------------------------------------------
# Plugin
# ----------------------------------------------------------------------


class TestQuayGenericPlugin:

    def setup_method(self) -> None:
        self.context = Mock()
        self.context.outputs = {}
        self.context.artifacts = {}
        self.context.activity.return_value = nullcontext()
        self.context.data_directory = Path("/data/quay.generic")
        # The executor's filesystem is mocked: nothing is written.
        self.context.filesystem.path.side_effect = Path

    def _html(self) -> str:
        return self.context.filesystem.write_text.call_args[0][1]

    def _run(self, client_class: Mock, **arguments: Any):
        client = client_class.return_value
        client.repositories.return_value = ["orders", "billing", "web"]
        client.tags.side_effect = lambda ns, repo: _tags(
            *[f"{repo}-{i}" for i in range(8)], "latest"
        )
        self.context.arguments = PluginArguments(
            {"url": "https://quay.test", "token": "s3cret", "namespace": "payments", **arguments}
        )
        with patch("resources.plugins.quay.generic.plugin.time.time", return_value=NOW):
            return QuayGenericPlugin(self.context).execute()

    def _messages(self) -> str:
        calls = [*self.context.message.method_calls, *self.context.log.method_calls]
        return "\n".join(str(call) for call in calls)

    @patch("resources.plugins.quay.generic.plugin.QuayClient")
    def test_dry_run_by_default_deletes_nothing(self, client_class: Mock) -> None:
        result = self._run(client_class)

        assert result.success is True and result.changed is False
        client_class.return_value.delete_tag.assert_not_called()
        assert result.outputs["dry_run"] is True
        assert result.outputs["deleted_count"] == 6  # 2 of 8 per repository, latest protected
        assert "orders:orders-0" in result.outputs["deleted"]
        assert result.outputs["tags_scanned"] == 27 and result.outputs["tags_kept"] == 21
        assert result.outputs["plan"]["orders"][0]["action"] == "keep"
        assert "s3cret" not in self._messages()

    @patch("resources.plugins.quay.generic.plugin.QuayClient")
    def test_deletes_selected_repositories_with_rules(self, client_class: Mock) -> None:
        result = self._run(
            client_class,
            dry_run=False,
            repositories=["orders", "bill*"],
            rules=[{"tags": "*-7", "keep": 0}],
        )

        assert result.success is True and result.changed is True
        assert result.outputs["repositories"] == ["billing", "orders"]
        deleted = [call.args for call in client_class.return_value.delete_tag.call_args_list]
        assert ("payments", "orders", "orders-7") in deleted
        assert ("payments", "orders", "orders-0") in deleted
        assert ("payments", "orders", "orders-1") not in deleted
        assert len(deleted) == 2 * 2  # the rule's "-7" and the oldest beyond 6, per repository
        client_class.assert_called_once_with("https://quay.test", "s3cret", verify_tls=True)

    @patch("resources.plugins.quay.generic.plugin.QuayClient")
    def test_a_failed_deletion_fails_the_step_but_others_run(self, client_class: Mock) -> None:
        client_class.return_value.delete_tag.side_effect = [QuayApiError("HTTP 403", 403)] + [
            None
        ] * 10

        result = self._run(client_class, dry_run=False)

        assert result.success is False
        assert len(result.errors) == 1 and "HTTP 403" in result.errors[0]
        assert result.outputs["deleted_count"] == 5

    @pytest.mark.parametrize(
        "arguments, message",
        [
            ({"keep": 0}, "'keep' must be 1 or more"),
            ({"url": "quay.test"}, "http(s) URL"),
            ({"rules": [{"keep": 2}]}, "'tags' is required"),
        ],
    )
    @patch("resources.plugins.quay.generic.plugin.QuayClient")
    def test_invalid_arguments_fail_cleanly(self, client_class: Mock, arguments, message) -> None:
        result = self._run(client_class, **arguments)

        assert result.success is False and message in result.errors[0]
        client_class.return_value.delete_tag.assert_not_called()

    # ------------------------------------------------------------------
    # list and the report
    # ------------------------------------------------------------------

    @patch("resources.plugins.quay.generic.plugin.QuayClient")
    def test_list_shows_tags_per_service_and_never_deletes(self, client_class: Mock) -> None:
        result = self._run(client_class, operation="list", dry_run=False)

        assert result.success is True and result.changed is False
        client_class.return_value.delete_tag.assert_not_called()
        assert result.outputs["operation"] == "list"
        assert result.outputs["tags"]["orders"][:3] == ["latest", "orders-7", "orders-6"]
        assert result.outputs["deleted"] == [] and result.outputs["deleted_count"] == 0
        assert result.outputs["plan"]["orders"][-1]["status"] == "delete"  # the policy preview

        report = Path("/data/quay.generic/reports/payments")
        path = self.context.artifacts["quay_report"]
        assert path.parent == report and path.name.startswith("quay-tags-")
        assert result.outputs["report"] == str(path)
        self.context.filesystem.mkdir.assert_called_with(report)
        html = self._html()
        assert "Quay tags — payments" in html and "orders-7" in html and "would delete" in html
        assert "s3cret" not in html

    @patch("resources.plugins.quay.generic.plugin.QuayClient")
    def test_cleanup_report_shows_deleted_and_failed_tags(self, client_class: Mock) -> None:
        client_class.return_value.delete_tag.side_effect = [
            QuayApiError("HTTP 403 denied", 403)
        ] + [None] * 10

        self._run(client_class, dry_run=False, repositories=["orders"])

        plan = self.context.outputs["plan"]["orders"]
        assert [row["status"] for row in plan if row["status"] != "keep"] == ["failed", "deleted"]
        assert self.context.artifacts["quay_report"].name.startswith("quay-cleanup-")
        html = self._html()
        assert 'class="badge deleted">deleted' in html and "HTTP 403 denied" in html

    @patch("resources.plugins.quay.generic.plugin.QuayClient")
    def test_report_can_be_turned_off_or_moved(self, client_class: Mock) -> None:
        result = self._run(client_class, report=False)
        assert result.outputs["report"] == "" and "quay_report" not in self.context.artifacts
        self.context.filesystem.write_text.assert_not_called()

        self._run(client_class, report_directory="/srv/reports")
        assert self.context.artifacts["quay_report"].parent == Path("/srv/reports")
        assert self.context.artifacts["quay_report"].name.startswith("quay-dry-run-")

    @patch("resources.plugins.quay.generic.plugin.QuayClient")
    def test_unknown_operation_is_refused(self, client_class: Mock) -> None:
        result = self._run(client_class, operation="purge")
        assert (
            result.success is False and "'operation' must be one of clean, list" in result.errors[0]
        )


def test_report_escapes_everything() -> None:
    from resources.plugins.quay.generic.report import build_report

    html = build_report(
        {
            "title": "<t>",
            "registry": "https://q",
            "namespace": "ns",
            "operation": "clean",
            "dry_run": True,
            "keep": 6,
            "protect": ["<p>"],
            "min_age_days": 0,
            "rules": [{"name": "<r>", "tags": ["<x>"], "keep": None, "repositories": []}],
            "generated": "now",
        },
        {
            "<repo>": [
                {
                    "tag": "<script>",
                    "status": "delete",
                    "reason": "r",
                    "rule": "default",
                    "start_ts": NOW - DAY,
                    "manifest_digest": "sha256:abc",
                    "size": 2048,
                }
            ]
        },
        NOW,
    )
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "<repo>" not in html and "<r>" not in html and "<p>" not in html
    assert "2.0 KB" in html and "(1d)" in html


def test_manifest_contract_matches_the_source() -> None:
    declared = contract.declared(contract.read_manifest(PLUGIN_DIRECTORY))
    assert declared is not None
    assert contract.check_source(PLUGIN_DIRECTORY, declared) == []
    defaults = contract.check_arguments(
        declared, {"url": "https://q", "token": "t", "namespace": "n"}
    )
    assert (
        defaults["keep"] == 6 and defaults["dry_run"] is True and defaults["protect"] == ["latest"]
    )
