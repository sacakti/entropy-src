"""
Tests for cache_refresh plugin orchestration.
"""

from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from resources.plugins.custom.cache_refresh.plugin import (
    CacheRefreshPlugin,
)
from resources.plugins.custom.cache_refresh.model import (
    CacheRefreshConfig,
)

from resources.plugins.custom.cache_refresh.exceptions import (
    CacheRefreshPluginException,
)

class TestCacheRefreshPlugin:

    def setup_method(self):
        self.context = Mock()

        self.context.arguments = Mock()
        self.context.outputs = {}
        self.context.artifacts = {}

        self.context.session_directory = Path(
            "/tmp/session",
        )

        self.context.filesystem = Mock()
        self.context.shell = Mock()
        self.context.log = Mock()
        self.context.message = Mock()

        self.context.activity.return_value = nullcontext()

        self.plugin = CacheRefreshPlugin(
            self.context,
        )

    def _config(self):
        return CacheRefreshConfig(
            kubeconfig=Path("/tmp/kubeconfig"),
            namespace="test",
            rebuild=True,
            stop_all_before_cache_rebuild=True,
            mode="force",
            services=("app1", "app2"),
            cache=Mock(),
            service_readiness=Mock(),
            parallel=False,
        )

    # ------------------------------------------------------------------
    # Success
    # ------------------------------------------------------------------

    @patch(
        "resources.plugins.custom.cache_refresh.plugin.CacheRefreshExecutor"
    )
    @patch(
        "resources.plugins.custom.cache_refresh.plugin.CacheRefreshResolver"
    )
    def test_execute_success(
        self,
        resolver_class,
        executor_class,
    ):
        config = self._config()

        resolver_class.return_value.resolve.return_value = config

        executor_class.return_value.execute.return_value = PluginResult(
            success=True,
            changed=True,
            outputs={},
            changes=[],
            errors=[],
            warnings=[],
            metadata={},
        )

        self.plugin._verify_access = Mock()

        result = self.plugin.execute()

        assert result.success is True
        assert result.changed is False

        resolver_class.return_value.resolve.assert_called_once_with(
            self.context.arguments,
        )

        self.plugin._verify_access.assert_called_once_with(
            config,
        )

        executor_class.return_value.execute.assert_called_once_with(
            config,
        )

        assert self.context.outputs["rebuild"] is True
        assert self.context.outputs["namespace"] == "test"

    # ------------------------------------------------------------------
    # Executor failure
    # ------------------------------------------------------------------

    @patch(
        "resources.plugins.custom.cache_refresh.plugin.CacheRefreshExecutor"
    )
    @patch(
        "resources.plugins.custom.cache_refresh.plugin.CacheRefreshResolver"
    )
    def test_execute_returns_executor_failure(
        self,
        resolver_class,
        executor_class,
    ):
        config = self._config()

        resolver_class.return_value.resolve.return_value = config

        expected = PluginResult(
            success=False,
            changed=True,
            outputs={},
            changes=[],
            errors=["execution failed"],
            warnings=[],
            metadata={},
        )

        executor_class.return_value.execute.return_value = expected

        self.plugin._verify_access = Mock()

        result = self.plugin.execute()

        assert result is expected

        self.plugin._verify_access.assert_called_once_with(
            config,
        )

    # ------------------------------------------------------------------
    # Access verification
    # ------------------------------------------------------------------

    @patch(
        "resources.plugins.custom.cache_refresh.plugin.CacheRefreshExecutor"
    )
    @patch(
        "resources.plugins.custom.cache_refresh.plugin.CacheRefreshResolver"
    )
    def test_access_is_verified_before_execution(
        self,
        resolver_class,
        executor_class,
    ):
        config = self._config()

        resolver_class.return_value.resolve.return_value = config

        executor_class.return_value.execute.return_value = PluginResult(
            success=True,
            changed=True,
            outputs={},
            changes=[],
            errors=[],
            warnings=[],
            metadata={},
        )

        calls = []

        def verify(_config):
            calls.append("verify")

        def execute(_config):
            calls.append("execute")

            return PluginResult(
                success=True,
                changed=True,
                outputs={},
                changes=[],
                errors=[],
                warnings=[],
                metadata={},
            )

        self.plugin._verify_access = Mock(
            side_effect=verify,
        )

        executor_class.return_value.execute.side_effect = execute

        result = self.plugin.execute()

        assert result.success is True
        assert calls == [
            "verify",
            "execute",
        ]

    # ------------------------------------------------------------------
    # Resolver failure
    # ------------------------------------------------------------------

    @patch(
        "resources.plugins.custom.cache_refresh.plugin.CacheRefreshResolver"
    )
    def test_resolver_failure_returns_failed_result(
        self,
        resolver_class,
    ):
        resolver_class.return_value.resolve.side_effect = (
            CacheRefreshPluginException("invalid configuration")
        )

        result = self.plugin.execute()

        assert result.success is False
        assert "invalid configuration" in result.errors

    # ------------------------------------------------------------------
    # Access failure
    # ------------------------------------------------------------------

    @patch(
        "resources.plugins.custom.cache_refresh.plugin.CacheRefreshExecutor"
    )
    @patch(
        "resources.plugins.custom.cache_refresh.plugin.CacheRefreshResolver"
    )
    def test_access_failure_prevents_execution(
        self,
        resolver_class,
        executor_class,
    ):
        config = self._config()

        resolver_class.return_value.resolve.return_value = config

        self.plugin._verify_access = Mock(
            side_effect=CacheRefreshPluginException("access denied"),
        )

        result = self.plugin.execute()

        assert result.success is False
        assert "access denied" in result.errors

        executor_class.return_value.execute.assert_not_called()
