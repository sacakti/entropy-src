"""
Plugin runner.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from lib.models.plugin import PluginResult
from lib.plugins.contract import (
    ContractError,
    check_arguments,
    check_outputs,
    declared,
    read_manifest,
)
from lib.plugins.exceptions import (
    PluginDisabledError,
    PluginExecutionError,
    PluginValueError,
)

from .context import PluginContext
from .loader import PluginLoader
from .mode import PluginMode

if TYPE_CHECKING:
    from core.runtime.context import ExecutionContext
    from lib.database.connection import DatabaseConnection
    from lib.plugins.base import BasePlugin


class PluginRunner:
    """
    Loads and executes plugins.
    """

    def __init__(
        self,
        loader: PluginLoader,
    ) -> None:

        self._loader = loader

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        context: ExecutionContext,
        qualified_name: str,
        mode: PluginMode = PluginMode.WORKFLOW,
    ) -> PluginResult:
        """
        Load and execute a plugin.
        """

        plugin = self._create_plugin(
            context=context,
            qualified_name=qualified_name,
            mode=mode,
        )

        if mode is PluginMode.CLI:

            context.start_plugin_scope(
                qualified_name,
            )

        try:

            from lib.git_repositories.store import checkout_assigned_repositories

            context.repositories.update(checkout_assigned_repositories(context, qualified_name))

            result = self._lifecycle(
                plugin,
                qualified_name,
            )

            self._capture_artifacts(context, plugin, qualified_name)

        except Exception:

            self._close_app(plugin)

            if mode is PluginMode.CLI:

                context.finish_plugin_scope(
                    success=False,
                )

            raise

        else:

            self._close_app(plugin)

            if mode is PluginMode.CLI:

                context.finish_plugin_scope(
                    success=True,
                )

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _lifecycle(
        plugin: BasePlugin,
        name: str,
    ) -> PluginResult:
        """
        validate -> prepare -> execute -> cleanup (always), then check the
        result and that its outputs are declared.
        """

        contract = getattr(
            plugin,
            "_entropy_contract",
            None,
        )

        try:

            plugin.validate()

            plugin.prepare()

            result = plugin.execute()

        finally:

            plugin.cleanup()

        if not isinstance(
            result,
            PluginResult,
        ):

            raise PluginExecutionError(
                f"Plugin '{name}' returned "
                f"'{type(result).__name__}', "
                "expected PluginResult.",
            )

        if contract is not None:

            problems = check_outputs(
                contract,
                dict(result.outputs or {}),
            )

            if problems:

                raise PluginExecutionError(
                    f"Plugin '{name}': " + "; ".join(problems) + ".",
                )

        return result

    @staticmethod
    def _contract_arguments(
        context: ExecutionContext,
        directory: Path,
        name: str,
    ) -> tuple:
        """
        (contract, checked arguments) when the plugin declares a contract;
        (None, None) for plugins that predate contracts.
        """

        try:

            contract = declared(
                read_manifest(
                    directory,
                ),
            )

        except ContractError as exc:

            raise PluginExecutionError(
                f"Plugin '{name}' has an invalid contract in plugin.json: {exc}",
            ) from None

        # Arguments given as ${ask} / ${ask:secret} are asked for now, with
        # or without a contract; the answers replace the markers.
        context.set_arguments(
            PluginRunner._ask_marked(
                context,
                contract,
                dict(context.arguments or {}),
                name,
            ),
        )

        if contract is None:

            return None, None

        values = PluginRunner._prompt_missing(
            context,
            contract,
            dict(context.arguments or {}),
            name,
        )

        try:

            arguments = check_arguments(
                contract,
                values,
            )

        except ContractError as exc:

            raise PluginValueError(
                f"Plugin '{name}': {exc}.",
            ) from None

        return contract, arguments

    @staticmethod
    def _prompt_missing(
        context: ExecutionContext,
        contract: dict,
        values: dict,
        name: str,
    ) -> dict:
        """
        In interactive runs, ask only for what the plugin cannot run without:
        required arguments the run left empty, plus optional arguments the
        plugin explicitly marks "prompt": true (those may be skipped). Other
        empty optional arguments keep their defaults and are not asked.
        Answers may be JSON (objects, lists) or vault references. Automated
        runs leave all of this to the usual checks.
        """

        import os

        from lib.runs.prompts import RUN_MODE_ENV, PromptError, prompts_for

        if os.environ.get(RUN_MODE_ENV) != "interactive":

            return values

        wanted = [
            item
            for item in contract["arguments"]
            if values.get(item["name"]) in (None, "") and (item["required"] or item.get("prompt"))
        ]

        if not wanted:

            return values

        store = prompts_for(context._entropy)
        node = context.node

        for item in wanted:

            optional = not item["required"]
            choices = item.get("choices")
            if item["type"] == "boolean":
                choices = ["true", "false"]
            hints = [item.get("description") or ""]
            if item["type"] in ("dictionary", "list"):
                hints.append(f"Answer with JSON ({item['type']}) or a vault reference.")
            if optional:
                if choices:
                    hints.append(f"One of: {', '.join(map(str, choices))}.")
                hints.append("Optional: leave empty to skip.")

            prompt = store.ask(
                context.job_id,
                name=item["name"],
                label=item.get("label") or item["name"],
                step=getattr(node, "name", None),
                description=" ".join(hint for hint in hints if hint),
                secret=item.get("secret", False),
                default=None if item["default"] is None else str(item["default"]),
                # An optional question may be left empty, so it takes free text.
                choices=[str(choice) for choice in choices] if choices and not optional else None,
            )

            try:

                answer = store.wait(prompt).strip()

            except PromptError as exc:

                raise PluginValueError(
                    f"Plugin '{name}': '{item['name']}': {exc}",
                ) from None

            if answer == "":

                continue

            values[item["name"]] = PluginRunner._typed_answer(
                context,
                answer,
                item["type"],
                item["name"],
                name,
            )

        return values

    @staticmethod
    def _typed_answer(
        context: ExecutionContext,
        answer: str,
        kind: str,
        argument: str,
        name: str,
    ) -> object:
        """An answer as its argument's type: a vault reference, JSON, or text."""

        import json

        if "${" in answer:

            return PluginRunner._resolve_answer(context, answer)

        if kind in ("dictionary", "list", "any"):

            try:

                return json.loads(answer)

            except ValueError:

                if kind != "any":

                    raise PluginValueError(
                        f"Plugin '{name}': '{argument}' must be JSON "
                        f"({kind}) or a vault reference.",
                    ) from None

        return answer

    @staticmethod
    def _ask_marked(
        context: ExecutionContext,
        contract: dict | None,
        values: dict,
        name: str,
    ) -> dict:
        """
        Ask for the arguments given as ${ask} (or ${ask:secret}), required or
        not. Interactive runs ask on the run screen (every question at once);
        `ent` asks in the terminal. Automated runs cannot ask, so they fail.
        An empty answer leaves an optional argument out; a required one
        needs a value.
        """

        import os
        import sys

        from lib.runs.prompts import RUN_MODE_ENV, PromptError, prompts_for
        from lib.workflow.variables.ask import ask_marker

        specs = {item["name"]: item for item in (contract or {}).get("arguments", [])}
        marked = {
            argument: bool(ask_marker(value)) or bool(specs.get(argument, {}).get("secret"))
            for argument, value in values.items()
            if ask_marker(value) is not None
        }

        if not marked:

            return values

        mode = os.environ.get(RUN_MODE_ENV)
        answers: dict = {}

        if mode == "interactive" and context.job_id is not None:

            store = prompts_for(context._entropy)
            node = context.node
            prompts = {}

            for argument, secret in marked.items():

                spec = specs.get(argument, {})
                choices = spec.get("choices")
                if spec.get("type") == "boolean":
                    choices = ["true", "false"]
                hints = [spec.get("description") or ""]
                if not spec.get("required"):
                    hints.append("Optional: leave empty to skip.")

                prompts[argument] = store.ask(
                    context.job_id,
                    name=argument,
                    label=spec.get("label") or argument,
                    step=getattr(node, "name", None),
                    description=" ".join(hint for hint in hints if hint),
                    secret=secret,
                    choices=(
                        [str(choice) for choice in choices]
                        if choices and spec.get("required")
                        else None
                    ),
                )

            for argument, prompt in prompts.items():

                try:

                    answers[argument] = store.wait(prompt).strip()

                except PromptError as exc:

                    raise PluginValueError(
                        f"Plugin '{name}': '{argument}': {exc}",
                    ) from None

        elif mode is None and sys.stdin.isatty():

            import getpass

            for argument, secret in marked.items():

                label = f"{specs.get(argument, {}).get('label') or argument}: "
                answers[argument] = (getpass.getpass(label) if secret else input(label)).strip()

        else:

            raise PluginValueError(
                f"Plugin '{name}': {', '.join(marked)} "
                f"{'is' if len(marked) == 1 else 'are'} set to ${{ask}}, "
                "which only an interactive run (or `ent` in a terminal) can answer. "
                "Start the run in interactive mode, or give the value.",
            )

        for argument, answer in answers.items():

            if answer == "":

                if specs.get(argument, {}).get("required"):

                    raise PluginValueError(
                        f"Plugin '{name}': '{argument}' needs a value.",
                    )

                values.pop(argument, None)

                continue

            values[argument] = PluginRunner._typed_answer(
                context,
                answer,
                specs.get(argument, {}).get("type", "any"),
                argument,
                name,
            )

        return values

    @staticmethod
    def _resolve_answer(
        context: ExecutionContext,
        answer: str,
    ) -> object:
        """A typed-in vault reference, read with the run user's access."""

        from lib.workflow.exceptions import VariableNotFoundError
        from lib.workflow.variables.resolver import WorkflowVariableResolver

        entropy = context._entropy
        session = entropy.session_manager.require()
        resolver = WorkflowVariableResolver(
            entropy.vault_manager,
            session.user_id,
            getattr(context, "secrets", None),
        )

        try:

            return resolver.resolve(answer, {})

        except VariableNotFoundError as exc:

            raise PluginValueError(str(exc)) from exc

    def _create_context(
        self,
        context: ExecutionContext,
        mode: PluginMode,
        arguments: dict | None = None,
        name: str | None = None,
    ) -> PluginContext:
        """
        Create the public plugin context.
        """

        return PluginContext(
            context=context,
            mode=mode,
            arguments=arguments,
            name=name,
        )

    def _instantiate(
        self,
        plugin_class: type,
        context: ExecutionContext,
        mode: PluginMode,
        directory: Path,
        name: str,
    ) -> BasePlugin:
        """A plugin instance with its arguments checked against its contract."""

        contract, arguments = self._contract_arguments(
            context,
            directory,
            name,
        )

        plugin = plugin_class(
            self._create_context(
                context=context,
                mode=mode,
                arguments=arguments,
                name=name,
            ),
        )

        plugin._entropy_contract = contract
        plugin._entropy_app = self._app_definition(directory, name)

        return plugin

    @staticmethod
    def _app_definition(directory: Path, name: str) -> dict | None:
        """The plugin's declared app page, if it is an app plugin."""

        from lib.plugins.app import app_definition

        try:
            return app_definition(read_manifest(directory))
        except ContractError as exc:
            raise PluginExecutionError(
                f"Plugin '{name}' has an invalid app in plugin.json: {exc}",
            ) from None

    @staticmethod
    def _close_app(plugin: BasePlugin) -> None:
        """An app plugin that ends leaves its page finished."""

        session = getattr(plugin, "_entropy_app_session", None)
        if session is not None:
            try:
                session.close()
            except Exception as error:  # noqa: BLE001 - the page state must not fail the step
                plugin.log.warning(f"Unable to close the app page: {error}")

    def _create_plugin(
        self,
        context: ExecutionContext,
        qualified_name: str,
        mode: PluginMode,
    ) -> BasePlugin:
        """
        Load and instantiate a plugin.
        """

        plugin = self._loader.get(
            qualified_name,
        )

        if not plugin.enabled:

            raise PluginDisabledError(
                qualified_name,
            )

        plugin_class = self._loader.load(
            qualified_name,
        )

        return self._instantiate(
            plugin_class,
            context,
            mode,
            plugin.path,
            qualified_name,
        )

    def execute_local(
        self,
        context: ExecutionContext,
        directory: Path,
        mode: PluginMode = PluginMode.CLI,
    ) -> PluginResult:
        """
        Load and execute a plugin from a local directory.
        """

        plugin_class = self._loader.load_local(
            directory,
        )

        plugin = self._instantiate(
            plugin_class,
            context,
            mode,
            directory,
            str(directory),
        )

        identifier = str(
            directory,
        )

        if mode is PluginMode.CLI:

            context.start_plugin_scope(
                identifier,
            )

        try:

            from lib.git_repositories.store import checkout_assigned_repositories

            context.repositories.update(checkout_assigned_repositories(context, identifier))

            result = self._lifecycle(
                plugin,
                str(directory),
            )

            self._capture_artifacts(context, plugin, identifier)

        except Exception:

            self._close_app(plugin)

            if mode is PluginMode.CLI:

                context.finish_plugin_scope(
                    success=False,
                )

            raise

        else:

            self._close_app(plugin)

            if mode is PluginMode.CLI:

                context.finish_plugin_scope(
                    success=True,
                )

        return result

    @staticmethod
    def _run_execution_id(context: ExecutionContext, connection: DatabaseConnection) -> str:
        """The execution id of the run's job, as the run screen knows it.

        A run worker attaches to a job the server created and starts its own
        execution with a new id; artifacts must name the job's id to be found.
        """
        job_id = getattr(context, "job_id", None)
        if job_id is not None:
            row = connection.fetchone(
                "SELECT execution_id FROM workflow_jobs WHERE id = ?", (job_id,)
            )
            if row is not None and row["execution_id"]:
                return str(row["execution_id"])
        return context.execution.id

    @staticmethod
    def _current_step(context: ExecutionContext) -> str | None:
        """Name of the workflow step running now (None outside a workflow step)."""
        from core.models.runtime import RuntimeNodeType

        node = context.node
        while node is not None:
            if node.type is RuntimeNodeType.STEP:
                return node.name
            node = node.parent
        return None

    @staticmethod
    def _capture_artifacts(context: ExecutionContext, plugin: BasePlugin, origin: str) -> None:
        """Expose plugin artifacts to the runtime and register existing files."""
        produced = dict(plugin.artifacts)
        context.artifacts.update(produced)
        if not produced:
            return

        # Artifact inventory is an optional integration: a bad/missing output
        # should be visible in the run log without turning a successful plugin
        # execution into a failure.
        try:
            for name, raw_path in produced.items():
                PluginRunner.register_artifact(context, raw_path, origin, name=str(name))
        except Exception as error:
            context.logger.warning("plugin", f"Unable to register generated artifacts: {error}")

    @staticmethod
    def register_artifact(
        context: ExecutionContext,
        raw_path: Any,
        origin: str,
        name: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Register one generated file in the artifact inventory of the run's project
        and return its record; None when it is not a file. Raises when it cannot.
        """
        import hashlib
        import json

        from lib.artifacts.store import ArtifactStore, ensure_artifacts_schema
        from lib.authorization.projects import default_project_id
        from lib.vault.projects import run_project

        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = context.workspace / path
        path = path.resolve(strict=True)
        if not path.is_file():
            return None
        connection = context.database.connection
        ensure_artifacts_schema(connection)
        project_id = run_project() or default_project_id(connection)
        run_id = PluginRunner._run_execution_id(context, connection)
        run_tag = "run:" + hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16]
        return ArtifactStore(connection).create(
            project_id,
            path.name or str(name),
            "server_path",
            path.stat().st_size,
            context.user,
            server_path=str(path),
            tags=json.dumps([run_tag]),
            classification="generated",
            origin=origin,
            run_id=run_id,
            step_name=PluginRunner._current_step(context),
        )
