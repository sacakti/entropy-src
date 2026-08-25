"""
Image transfer plugin.

Prepares a release for deployment by:

    1. Extracting the supplied release ZIP beside the archive.
    2. Optionally removing an existing extracted release directory.
    3. Locating image_transfer.sh and apply_yaml.sh.
    4. Reading supported Docker commands from image_transfer.sh.
    5. Validating Docker command ordering.
    6. Validating Docker storage prerequisites.
    7. Executing Docker commands individually through Entropy.
    8. Preparing apply_yaml.sh without executing it.
    9. Removing git commands and positional credentials.
    10. Rewriting the configured release base path.
    11. Optionally validating every resulting YAML path.

The original ZIP archive is never modified or repackaged.
The extracted release directory is retained beside the ZIP.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin


class ImageTransferPlugin(BasePlugin):
    """
    Prepare a release and transfer its container images.
    """

    DOCKER_COMMAND_PATTERN = re.compile(
        r"^\s*docker\s+" r"(?P<operation>login|pull|tag|push)\b" r"(?P<arguments>.*)$"
    )

    OC_APPLY_PATTERN = re.compile(
        r"^(?P<indent>\s*)" r"oc\s+apply\s+-f\s+" r"(?P<path>\S+)" r"(?P<trailing>\s*)$",
        re.MULTILINE,
    )

    OC_LOGIN_PATTERN = re.compile(r"^\s*oc\s+login\b")

    SCRIPT_VARIABLE_PATTERN = re.compile(
        r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*=\s*\$[0-9]+\s*$",
    )

    CD_COMMAND_PATTERN = re.compile(
        r"^\s*cd(?:\s+.*)?\s*$",
    )

    YAML_SUFFIXES = {
        ".yaml",
        ".yml",
    }

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
    ) -> PluginResult:
        """
        Execute the image transfer workflow.
        """

        self.message.info(
            "Starting image transfer preparation.",
        )

        try:

            with self.activity(
                "image_transfer",
            ):

                self._execute()

        except Exception as exc:

            self.log.error(
                str(exc),
            )

            self.message.error(
                str(exc),
            )

            return PluginResult(
                success=False,
                changed=False,
                outputs=dict(
                    self.outputs,
                ),
                changes=[],
                errors=[
                    str(exc),
                ],
                warnings=[],
                metadata={
                    "artifacts": {
                        name: str(path)
                        for name, path in self.artifacts.items()
                    },
                },
            )

        self.message.success(
            "Image transfer preparation completed successfully.",
        )

        return PluginResult(
            success=True,
            changed=True,
            outputs=dict(
                self.outputs,
            ),
            changes=[],
            errors=[],
            warnings=[],
            metadata={
                "artifacts": {
                    name: str(path)
                    for name, path in self.artifacts.items()
                },
            },
        )

    # ------------------------------------------------------------------
    # Main workflow
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> None:
        """
        Execute the complete image transfer workflow.
        """

        release = self.arguments.path(
            "release",
            required=True,
        )

        assert release is not None

        release = self._resolve_release(
            release,
        )

        release_scripts_directory = self.arguments.string(
            "release_scripts_directory",
            default="scripts/deploy",
            required=True,
        )

        transfer_script_name = self.arguments.string(
            "transfer_script",
            default="image_transfer.sh",
            required=True,
        )

        apply_script_name = self.arguments.string(
            "apply_script",
            default="apply_yaml.sh",
            required=True,
        )

        release_base_path = self.arguments.path(
            "release_base_path",
            default="/home/devops",
            required=True,
        )

        assert release_base_path is not None

        min_free_storage_gb = self.arguments.number(
            "min_free_storage_gb",
            default=10,
            minimum=0.0,
        )

        assert min_free_storage_gb is not None

        if min_free_storage_gb <= 0:
            raise ValueError("Argument 'min_free_storage_gb' must be " "greater than zero.")

        old_image_pattern = self.arguments.string(
            "old_image_pattern",
            default="25.01.01.",
            required=True,
        )

        assert old_image_pattern is not None

        compiled_old_image_pattern = re.compile(
            old_image_pattern,
        )

        cleanup_builder_cache = self.arguments.boolean(
            "cleanup_builder_cache",
            default=False,
        )

        skip_docker = self.arguments.boolean(
            "skip_docker",
            default=False,
        )

        validate_yaml = self.arguments.boolean(
            "validate_yaml",
            default=True,
        )

        force_remove_processed = self.arguments.boolean(
            "force_remove_processed",
            default=False,
        )

        #
        # Record resolved configuration.
        #

        self.outputs["configuration"] = {
            "release_scripts_directory": (release_scripts_directory),
            "transfer_script": transfer_script_name,
            "apply_script": apply_script_name,
            "release_base_path": str(
                release_base_path,
            ),
            "min_free_storage_gb": (min_free_storage_gb),
            "old_image_pattern": old_image_pattern,
            "cleanup_builder_cache": (cleanup_builder_cache),
            "skip_docker": skip_docker,
            "validate_yaml": validate_yaml,
            "force_remove_processed": (force_remove_processed),
        }

        self.log.info("Image transfer configuration resolved.")

        #
        # Extract release.
        #

        extracted_release = self._extract_release(
            release,
            force_remove_processed,
        )

        #
        # Locate scripts.
        #

        transfer_script = self._locate_script(
            extracted_release,
            release_scripts_directory,
            transfer_script_name,
        )

        apply_script = self._locate_script(
            extracted_release,
            release_scripts_directory,
            apply_script_name,
        )

        #
        # Parse image transfer commands.
        #

        docker_commands = self._read_transfer_commands(
            transfer_script,
        )

        #
        # Docker operations.
        #

        if skip_docker:

            self.message.warning("Docker prerequisite checks and image " "transfer are skipped.")

            self.outputs["docker_skipped"] = True

        else:

            self._check_docker_storage(
                min_free_storage_gb,
                raise_on_insufficient=False,
            )

            self._cleanup_old_images_if_required(
                min_free_storage_gb,
                compiled_old_image_pattern,
            )

            self._check_docker_storage(
                min_free_storage_gb,
            )

            if cleanup_builder_cache:

                self._cleanup_builder_cache()

                self._check_docker_storage(
                    min_free_storage_gb,
                )

            self._execute_docker_commands(
                docker_commands,
            )

            self.outputs["docker_skipped"] = False

        #
        # Prepare apply_yaml.sh.
        #
        # IMPORTANT:
        #
        # The script is never executed.
        #
        # YAML validation happens only after the
        # /home/devops path has been replaced.
        #

        prepared_apply_script, yaml_paths = self._prepare_apply_script(
            apply_script,
            extracted_release,
            release_base_path,
            validate_yaml,
        )

        #
        # Outputs.
        #

        self.outputs["image_transfer"] = not skip_docker

        self.outputs["cleanup_performed"] = self.outputs.get(
            "cleanup_performed",
            False,
        )

        self.outputs["yaml_script_prepared"] = True

        self.outputs["yaml_validation_enabled"] = validate_yaml

        self.outputs["yaml_paths"] = [str(path) for path in yaml_paths]

        self.outputs["release_path"] = str(
            extracted_release,
        )

        #
        # Artifacts.
        #

        self.artifacts["release"] = extracted_release

        self.artifacts["apply_yaml_script"] = prepared_apply_script

        self.message.success(f"Prepared release directory: " f"{extracted_release}")

    # ------------------------------------------------------------------
    # Release
    # ------------------------------------------------------------------

    def _resolve_release(
        self,
        release: Path,
    ) -> Path:
        release = release.expanduser().resolve()

        if not self.filesystem.exists(
            release,
        ):
            raise FileNotFoundError("Release archive not found: " f"{release}")

        if not self.filesystem.is_file(
            release,
        ):
            raise ValueError("Release path is not a file: " f"{release}")

        if release.suffix.lower() != ".zip":
            raise ValueError("Release path must be a ZIP archive: " f"{release}")

        return release

    def _extract_release(
        self,
        release: Path,
        force_remove_processed: bool,
    ) -> Path:
        """
        Extract the release beside the ZIP archive.

        Example:

            /releases/H001.zip
                ->
            /releases/H001/

        If force_remove_processed is enabled,
        an existing extracted directory is removed
        before extraction.
        """

        destination = release.with_suffix("").resolve()

        if self.filesystem.exists(
            destination,
        ):

            if not force_remove_processed:

                raise FileExistsError(
                    "Release extraction directory " "already exists: " f"{destination}"
                )

            with self.activity(
                "Remove previous extracted release",
            ):

                self.filesystem.remove(
                    destination,
                )

            self.message.info("Removed previous extracted release: " f"{destination}")

        with self.activity(
            "Extract release",
        ):

            extracted = self.archive.extract(
                release,
                destination,
            )

        if not self.filesystem.is_directory(
            extracted,
        ):

            raise RuntimeError(f"Release extraction failed: " f"{extracted}")

        extracted = extracted.resolve()

        self.outputs["force_remove_processed"] = force_remove_processed

        self.message.info("Release extracted to: " f"{extracted}")

        return extracted

    def _locate_script(
        self,
        release_root: Path,
        scripts_directory: str,
        script_name: str,
    ) -> Path:
        """
        Locate a required deployment script.
        """

        scripts_root = release_root / Path(scripts_directory)

        script = scripts_root / script_name

        if not self.filesystem.exists(
            script,
        ):

            raise FileNotFoundError("Required release script not found: " f"{script}")

        if not self.filesystem.is_file(
            script,
        ):

            raise ValueError(f"Release script is not a file: " f"{script}")

        return script

    # ------------------------------------------------------------------
    # image_transfer.sh
    # ------------------------------------------------------------------

    def _read_transfer_commands(
        self,
        script: Path,
    ) -> list[list[str]]:
        """
        Read and validate Docker commands.
        """

        with self.activity(
            "Prepare image transfer script",
        ):

            content = self.filesystem.read_text(
                script,
            )

            commands = self._extract_docker_commands(
                content,
            )

            self._validate_docker_sequence(commands, script)

        self.message.info(f"Found {len(commands)} Docker " f"command(s) in '{script.name}'.")

        return commands

    def _extract_docker_commands(
        self,
        content: str,
    ) -> list[list[str]]:
        """
        Extract supported Docker commands without
        executing image_transfer.sh.
        """

        commands: list[list[str]] = []

        for (
            line_number,
            line,
        ) in self._logical_lines(
            content,
        ):

            stripped = line.strip()

            if not stripped or stripped.startswith("#"):

                continue

            if (
                self.DOCKER_COMMAND_PATTERN.match(
                    stripped,
                )
                is None
            ):

                continue

            try:

                command = shlex.split(
                    stripped,
                )

            except ValueError as exc:

                raise ValueError(
                    "Invalid shell syntax in " "image_transfer.sh at line " f"{line_number}: {exc}"
                ) from exc

            if len(command) < 2 or command[0] != "docker":

                continue

            operation = command[1]

            if operation not in {
                "login",
                "pull",
                "tag",
                "push",
            }:

                continue

            #
            # Docker login must not receive
            # positional script credentials.
            #
            # Example:
            #
            # docker login registry.example.com $1 $2
            #
            # becomes:
            #
            # docker login registry.example.com
            #

            if operation == "login":

                command = self._remove_docker_login_credentials(
                    command,
                    line_number,
                )

            commands.append(
                command,
            )

        return commands

    def _remove_docker_login_credentials(
        self,
        command: list[str],
        line_number: int,
    ) -> list[str]:
        """
        Remove username and password credentials from
        a Docker login command.

        Supported forms include:

            docker login REGISTRY -u USER -p PASSWORD
            docker login REGISTRY --username USER --password PASSWORD
            docker login REGISTRY -u USER --password PASSWORD

        The returned command contains only:

            docker login REGISTRY
        """

        result = [
            command[0],
            command[1],
        ]

        index = 2

        while index < len(command):

            argument = command[index]

            if argument in {
                "-u",
                "--username",
                "-p",
                "--password",
            }:

                if index + 1 >= len(command):

                    raise ValueError(
                        "Docker login option "
                        f"'{argument}' is missing its value "
                        f"at line {line_number}."
                    )

                index += 2

                continue

            #
            # Handle --username=value and
            # --password=value forms.
            #

            if argument.startswith(
                "--username=",
            ) or argument.startswith(
                "--password=",
            ):

                index += 1

                continue

            #
            # Keep the registry and any other
            # legitimate Docker login arguments.
            #

            result.append(
                argument,
            )

            index += 1

        if len(result) < 3:

            raise ValueError(
                "Docker login command is missing "
                "the registry at line "
                f"{line_number}."
            )

        return result

    @staticmethod
    def _logical_lines(
        content: str,
    ) -> list[tuple[int, str]]:
        """
        Join shell lines continued with a backslash.
        """

        result: list[tuple[int, str]] = []

        current = ""

        start_line = 0

        for (
            line_number,
            raw_line,
        ) in enumerate(
            content.splitlines(),
            start=1,
        ):

            line = raw_line.rstrip()

            if not current:

                start_line = line_number

            if line.endswith("\\"):

                current += line[:-1].rstrip() + " "

                continue

            current += line

            result.append(
                (
                    start_line,
                    current,
                )
            )

            current = ""

        if current:

            result.append(
                (
                    start_line,
                    current,
                )
            )

        return result

    def _validate_docker_sequence(self, commands: list[list[str]], script: str) -> None:
        """
        Validate broad Docker operation ordering.

        Multiple login, pull, tag and push operations
        are allowed.

        The exact number of operations is not fixed.
        """

        if not commands:

            raise ValueError("No supported Docker commands were found " f"in {script}.")

        operations = [command[1] for command in commands]

        required_operations = {
            "login",
            "pull",
            "tag",
            "push",
        }

        missing = required_operations - set(operations)

        if missing:

            raise ValueError(
                f"{script} is missing required "
                "Docker operation(s): "
                f"{', '.join(sorted(missing))}."
            )

        first_pull = operations.index("pull")

        first_tag = operations.index("tag")

        first_push = operations.index("push")

        #
        # Login must happen before the
        # first pull.
        #

        if "login" not in (operations[:first_pull]):

            raise ValueError("image_transfer.sh must contain " "a Docker login before Docker pull.")

        #
        # Tag must happen after pull.
        #

        if first_tag <= first_pull:

            raise ValueError("Docker tag must occur after " "Docker pull.")

        #
        # Push must happen after tag.
        #

        if first_push <= first_tag:

            raise ValueError("Docker push must occur after " "Docker tag.")

    # ------------------------------------------------------------------
    # Docker prerequisites
    # ------------------------------------------------------------------

    def _check_docker_storage(
        self,
        min_free_storage_gb: float,
        *,
        raise_on_insufficient: bool = True,
    ) -> int:
        """
        Check Docker's backing filesystem free storage.
        """

        with self.activity(
            "Check Docker storage",
        ):

            self._require_command(
                "docker",
            )

            df_result = self.shell.run(
                [
                    "docker",
                    "system",
                    "df",
                ],
            )

            if df_result.failed:

                raise RuntimeError(
                    "docker system df failed "
                    f"(exit code "
                    f"{df_result.exit_code}): "
                    f"{df_result.stderr or df_result.stdout}"
                )

            info_result = self.shell.run(
                [
                    "docker",
                    "info",
                    "--format",
                    "{{.DockerRootDir}}",
                ],
            )

            if info_result.failed:

                raise RuntimeError(
                    "Unable to determine Docker "
                    "root directory: "
                    f"{info_result.stderr or info_result.stdout}"
                )

            docker_root_text = info_result.stdout.strip()

            if not docker_root_text:

                raise RuntimeError("Docker returned an empty Docker " "root directory.")

            docker_root = Path(
                docker_root_text,
            )

            filesystem_result = self.shell.run(
                [
                    "df",
                    "-Pk",
                    str(docker_root),
                ],
            )

            if filesystem_result.failed:

                raise RuntimeError(
                    "Unable to determine free storage "
                    "for Docker: "
                    f"{filesystem_result.stderr or filesystem_result.stdout}"
                )

            free_bytes = self._parse_df_free_bytes(
                filesystem_result.stdout,
            )

            minimum_free_storage_bytes = int(min_free_storage_gb * 1024 * 1024 * 1024)

            self.outputs["docker_storage"] = {
                "docker_root": str(
                    docker_root,
                ),
                "free_bytes": free_bytes,
                "free_gb": (free_bytes / (1024**3)),
                "minimum_required_gb": (min_free_storage_gb),
            }

            if free_bytes < minimum_free_storage_bytes:

                message = (
                    "Docker filesystem has less than "
                    f"{min_free_storage_gb:g} GB "
                    "of free storage "
                    f"({free_bytes / (1024**3):.2f} "
                    "GB available)."
                )

                if raise_on_insufficient:

                    raise RuntimeError(
                        message,
                    )

                self.message.warning(
                    message,
                )

            return free_bytes

    @staticmethod
    def _parse_df_free_bytes(
        output: str,
    ) -> int:
        """
        Parse available bytes from POSIX df -Pk output.

        The available-space field is expressed
        in 1024-byte blocks.
        """

        lines = [line for line in output.splitlines() if line.strip()]

        if len(lines) < 2:

            raise ValueError(f"Unexpected df output: {output!r}")

        fields = lines[-1].split()

        if len(fields) < 4:

            raise ValueError(f"Unexpected df output: {output!r}")

        try:

            available_kib = int(
                fields[3],
            )

        except ValueError as exc:

            raise ValueError(
                "Invalid available-space value " "in df output: " f"{fields[3]!r}"
            ) from exc

        return available_kib * 1024

    def _cleanup_old_images_if_required(
        self,
        min_free_storage_gb: float,
        old_image_pattern: re.Pattern[str],
    ) -> None:
        """
        Remove matching old images when Docker storage
        is below the configured threshold.
        """

        storage = self.outputs.get(
            "docker_storage",
        )

        if not isinstance(
            storage,
            dict,
        ):

            raise RuntimeError("Docker storage state is unavailable.")

        free_bytes = storage.get(
            "free_bytes",
        )

        if not isinstance(
            free_bytes,
            int,
        ):

            raise RuntimeError("Docker storage state is unavailable.")

        minimum_free_storage_bytes = int(min_free_storage_gb * 1024 * 1024 * 1024)

        if free_bytes >= minimum_free_storage_bytes:

            self.outputs["cleanup_performed"] = False

            return

        with self.activity(
            "Cleanup old images",
        ):

            result = self.shell.run(
                [
                    "docker",
                    "images",
                    "--format",
                    "{{.Repository}}:{{.Tag}}",
                ],
            )

            if result.failed:

                raise RuntimeError(
                    "Unable to list Docker images: " f"{result.stderr or result.stdout}"
                )

            images = [
                image.strip()
                for image in result.stdout.splitlines()
                if (
                    image.strip()
                    and old_image_pattern.search(
                        image,
                    )
                )
            ]

            if not images:

                self.message.warning("No matching old Docker images " "were found for cleanup.")

                self.outputs["cleanup_performed"] = False

                return

            for image in images:

                remove_result = self.shell.run(
                    [
                        "docker",
                        "rmi",
                        image,
                    ],
                )

                if remove_result.failed:

                    raise RuntimeError(
                        "Failed to remove Docker "
                        f"image '{image}': "
                        f"{remove_result.stderr or remove_result.stdout}"
                    )

            self.outputs["cleanup_performed"] = True

            self.message.info(f"Removed {len(images)} old " "Docker image(s).")

    def _cleanup_builder_cache(
        self,
    ) -> None:
        """
        Remove unused Docker builder cache.
        """

        with self.activity(
            "Cleanup Docker builder cache",
        ):

            result = self.shell.run(
                [
                    "docker",
                    "builder",
                    "prune",
                    "-f",
                ],
            )

            if result.failed:

                raise RuntimeError(
                    "Docker builder cache cleanup failed "
                    f"(exit code "
                    f"{result.exit_code}): "
                    f"{result.stderr or result.stdout}"
                )

    # ------------------------------------------------------------------
    # Docker execution
    # ------------------------------------------------------------------

    def _execute_docker_commands(
        self,
        commands: list[list[str]],
    ) -> None:
        """
        Execute each extracted Docker command independently.

        Docker output is stored in workflow.log and is
        intentionally not displayed in the workflow UI.
        """

        for command in commands:

            activity_name = self._docker_activity_name(
                command,
            )

            with self.activity(
                activity_name,
            ):

                result = self.shell.run(
                    command,
                )

                if result.stdout:

                    self.log.info("Docker stdout:\n" f"{result.stdout}")

                if result.stderr:

                    self.log.warning("Docker stderr:\n" f"{result.stderr}")

                if result.failed:

                    raise RuntimeError(
                        "Docker command failed: "
                        f"{result.command} "
                        f"(exit code "
                        f"{result.exit_code}): "
                        f"{result.stderr or result.stdout}"
                    )

    def _docker_activity_name(
        self,
        command: list[str],
    ) -> str:
        """
        Build a descriptive activity name for
        a Docker command.
        """

        operation = command[1]

        if operation == "login":

            registry = command[2] if len(command) > 2 else "registry"

            return f"Docker login to {registry}"

        if operation == "pull":

            if len(command) < 3:

                return "Docker pull"

            image = command[2]

            return (
                f"Pulling "
                f"{self._docker_image_name(image)} "
                f"from "
                f"{self._docker_registry(image)}"
            )

        if operation == "tag":

            if len(command) < 4:

                return "Docker tag"

            source = command[2]
            destination = command[3]

            return f"Tagging " f"{self._docker_image_name(source)} " f"→ {destination}"

        if operation == "push":

            if len(command) < 3:

                return "Docker push"

            image = command[2]

            return (
                f"Pushing "
                f"{self._docker_image_name(image)} "
                f"to "
                f"{self._docker_registry(image)}"
            )

        return f"Docker {operation}"

    @staticmethod
    def _docker_image_name(
        image: str,
    ) -> str:
        """
        Return repository/image:tag without
        the registry.
        """

        without_digest = image.split(
            "@",
            1,
        )[0]

        parts = without_digest.split(
            "/",
        )

        if len(parts) <= 1:

            return without_digest

        first = parts[0]

        if "." in first or ":" in first or first == "localhost":

            return "/".join(
                parts[1:],
            )

        return without_digest

    @staticmethod
    def _docker_registry(
        image: str,
    ) -> str:
        """
        Return the registry portion of
        an image reference.
        """

        parts = image.split(
            "/",
        )

        if len(parts) <= 1:

            return "registry"

        first = parts[0]

        if "." in first or ":" in first or first == "localhost":

            return first

        return "registry"

    # ------------------------------------------------------------------
    # apply_yaml.sh
    # ------------------------------------------------------------------

    def _prepare_apply_script(
        self,
        script: Path,
        release_root: Path,
        release_base_path: Path,
        validate_yaml: bool,
    ) -> tuple[Path, list[Path]]:
        """
        Prepare apply_yaml.sh without executing it.

        Every:

            oc apply -f /home/devops/...

        command has its configured release base path
        replaced with the extracted release directory.

        Git commands are removed.

        An:

            oc login -u $1 -p $2

        command becomes:

            oc login

        YAML validation occurs only after the paths
        have been rewritten.
        """

        with self.activity(
            "Prepare deployment YAML script",
        ):

            original = self.filesystem.read_text(
                script,
            )

            prepared, yaml_paths = self._transform_apply_script(
                original,
                release_root,
                release_base_path,
            )

            if not yaml_paths:

                raise ValueError("Could not find any " "'oc apply -f' command " f"in '{script}'.")

            #
            # Validate the transformed script
            # before writing it.
            #

            self._validate_prepared_apply_script(
                prepared,
                release_root,
            )

            #
            # Validate the final paths only after
            # path replacement.
            #

            if validate_yaml:

                for yaml_path in yaml_paths:

                    self._validate_yaml_path(
                        yaml_path,
                    )

            else:

                self.message.info("Deployment YAML path " "validation skipped.")

            #
            # Use the Plugin SDK filesystem API.
            #

            self.filesystem.write_text(
                script,
                prepared,
            )

        self.message.info(
            f"Prepared '{script.name}' with " f"{len(yaml_paths)} deployment " "YAML path(s)."
        )

        return (
            script,
            yaml_paths,
        )

    def _transform_apply_script(
        self,
        content: str,
        release_root: Path,
        release_base_path: Path,
    ) -> tuple[str, list[Path]]:
        """
        Remove git commands and rewrite every
        oc apply path.
        """

        output: list[str] = []

        yaml_paths: list[Path] = []

        base = str(
            release_base_path,
        ).rstrip("/")

        for raw_line in content.splitlines(
            keepends=True,
        ):

            line = raw_line.rstrip(
                "\r\n",
            )

            newline = raw_line[len(line) :]

            stripped = line.strip()

            #
            # Remove git commands.
            #

            if self._is_git_command(
                stripped,
            ):

                continue

            #
            # Remove positional credential variable assignments.
            #
            # Example:
            #
            # a=$1
            # b=$2
            #
            # These values are no longer required because
            # authentication is handled by Entropy.
            #

            if self.SCRIPT_VARIABLE_PATTERN.match(
                stripped,
            ):

                continue

            #
            # Remove the legacy working directory change.
            #

            if self.CD_COMMAND_PATTERN.match(
                stripped,
            ):

                continue

            #
            # Remove positional credentials
            # from oc login.
            #

            if self.OC_LOGIN_PATTERN.match(
                stripped,
            ):

                indentation = line[: len(line) - len(line.lstrip())]

                try:

                    tokens = shlex.split(
                        stripped,
                    )

                except ValueError as exc:

                    raise ValueError("Invalid shell syntax in " "apply_yaml.sh: " f"{exc}") from exc

                tokens = [
                    token
                    for token in tokens
                    if token
                    not in {
                        "$1",
                        "$2",
                    }
                ]

                if tokens[:2] == [
                    "oc",
                    "login",
                ]:

                    output.append(f"{indentation}" f"{shlex.join(tokens)}" f"{newline}")

                    continue

            #
            # Rewrite oc apply paths.
            #

            match = self.OC_APPLY_PATTERN.match(
                line,
            )

            if match is None:

                output.append(
                    raw_line,
                )

                continue

            original_path = match.group("path")

            updated_path = self._rewrite_apply_path(
                original_path,
                release_root,
                base,
            )

            resolved_path = (
                Path(
                    updated_path,
                )
                .expanduser()
                .resolve()
            )

            output.append(
                f"{match.group('indent')}"
                "oc apply -f "
                f"{updated_path}"
                f"{match.group('trailing')}"
                f"{newline}"
            )

            yaml_paths.append(
                resolved_path,
            )

        return (
            "".join(output),
            yaml_paths,
        )

    def _rewrite_apply_path(
        self,
        original_path: str,
        release_root: Path,
        release_base_path: str,
    ) -> str:
        """
        Replace the configured release base path.

        Example:

            /home/devops/scripts/app-1/test-deployment/

        becomes:

            /releases/H001/scripts/app-1/test-deployment/
        """

        base = release_base_path.rstrip("/")
        normalized = original_path.rstrip("/")

        if normalized != base and not normalized.startswith(
            f"{base}/",
        ):
            raise ValueError(
                "Unexpected oc apply path. "
                "Expected it to start with "
                f"'{base}': {original_path}"
            )

        relative_part = normalized[len(base) :].lstrip("/")

        if not relative_part:
            raise ValueError("oc apply path points directly to " f"'{base}', which is not valid.")

        target = release_root / relative_part

        return str(target) + ("/" if original_path.endswith("/") else "")

    @staticmethod
    def _is_git_command(
        line: str,
    ) -> bool:
        """
        Return True for a standalone git command.
        """

        if not line or line.startswith("#"):

            return False

        try:

            tokens = shlex.split(
                line,
            )

        except ValueError:

            return False

        return bool(tokens and tokens[0] == "git")

    def _validate_prepared_apply_script(
        self,
        content: str,
        release_root: Path,
    ) -> None:
        """
        Validate the transformed apply_yaml.sh.

        All remaining oc apply paths must remain inside
        the extracted release.
        """

        if self._contains_git_command(
            content,
        ):

            raise ValueError("Prepared apply_yaml.sh still " "contains a git command.")

        matches = list(
            self.OC_APPLY_PATTERN.finditer(
                content,
            )
        )

        if not matches:

            raise ValueError("Prepared apply_yaml.sh does not " "contain an 'oc apply -f' command.")

        root = str(
            release_root.resolve(),
        )

        for match in matches:

            path = match.group(
                "path",
            ).rstrip("/")

            if path != root and not path.startswith(
                f"{root}/",
            ):

                raise ValueError(
                    "Prepared apply_yaml.sh "
                    "contains a path outside "
                    "the extracted release: "
                    f"{match.group('path')}"
                )

    def _contains_git_command(
        self,
        content: str,
    ) -> bool:
        """
        Return True when a standalone git command remains.
        """

        return any(
            self._is_git_command(
                line.strip(),
            )
            for line in content.splitlines()
        )

    # ------------------------------------------------------------------
    # YAML validation
    # ------------------------------------------------------------------

    def _validate_yaml_path(
        self,
        path: Path,
    ) -> None:
        """
        Validate an oc apply target.

        The target may be:

            1. A YAML file.
            2. A directory containing YAML files.
        """

        if not self.filesystem.exists(
            path,
        ):

            raise FileNotFoundError("Deployment YAML path not found: " f"{path}")

        if self.filesystem.is_file(
            path,
        ):

            if path.suffix.lower() not in self.YAML_SUFFIXES:

                raise ValueError("Deployment YAML file has an " "unsupported extension: " f"{path}")

            self.message.info(f"Validated YAML file: {path}")

            return

        if not self.filesystem.is_directory(
            path,
        ):

            raise ValueError("Deployment YAML path is neither " f"a file nor a directory: {path}")

        yaml_files = [
            file
            for file in self.filesystem.find(
                path,
                pattern="*",
                recursive=True,
            )
            if (
                self.filesystem.is_file(
                    file,
                )
                and file.suffix.lower() in self.YAML_SUFFIXES
            )
        ]

        if not yaml_files:

            raise FileNotFoundError(
                "Deployment YAML directory contains " "no .yaml or .yml files: " f"{path}"
            )

        self.message.info(f"Validated {len(yaml_files)} YAML " f"file(s) under '{path}'.")

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _require_command(
        self,
        command: str,
    ) -> None:
        """
        Verify that a required executable exists.
        """

        try:

            self.environment.which(
                command,
            )

        except FileNotFoundError as exc:

            raise RuntimeError(f"Required command '{command}' " "was not found in PATH.") from exc
