"""
Image tags and checksums of OpenShift workloads, from running pods or skopeo.
"""

from __future__ import annotations

import base64
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import SkopeoPluginException, SkopeoRuleError
from .images import (
    WORKLOAD_KINDS,
    ImageReference,
    Workload,
    digest_of,
    parse_rules,
    patterns,
    selected,
    workload_selected,
    workloads,
)


class SkopeoGenericPlugin(
    BasePlugin,
):
    """
    Find the full image (registry, repository, tag) and the checksum
    (digest) of each container of the selected workloads:

    - pod: from the running pods (the digest the node actually pulled);
    - skopeo: `skopeo inspect` of the workload's image;
    - auto: pods, and skopeo for workloads with no running pod.

    OpenShift is reached with the login session of oc.generic (the same
    `environment`); `images` are inspected with skopeo directly.
    """

    MODES = (
        "auto",
        "pod",
        "skopeo",
    )

    KUBECONFIG_DIRECTORY = ".kube"

    KUBECONFIG_FILENAME = "config"

    DEFAULT_TIMEOUT = 120

    def execute(
        self,
    ) -> PluginResult:
        """
        Collect image details.
        """

        self.message.info(
            "Collecting image tags and checksums.",
        )

        try:

            with self.activity(
                "skopeo-images",
            ):

                return self._execute()

        except SkopeoPluginException as exc:

            self.log.error(
                str(exc),
            )

            self.message.error(
                str(exc),
            )

            return self._result(
                success=False,
                errors=[
                    str(exc),
                ],
            )

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> PluginResult:

        mode = (self.arguments.string("mode", "auto") or "auto").strip().lower()
        environment = (self.arguments.string("environment", "") or "").strip()
        namespace = (self.arguments.string("namespace", "") or "").strip()
        kinds = self.arguments.list("kinds", ["deployment", "deploymentconfig"]) or []
        direct = self.arguments.list("images", []) or []
        exclude = patterns(self.arguments.get("exclude"), "'exclude'")
        include_init = bool(self.arguments.boolean("include_init_containers", False))
        fail_on_error = bool(self.arguments.boolean("fail_on_error", True))

        if mode not in self.MODES:
            raise SkopeoPluginException(
                f"'mode' must be one of {', '.join(self.MODES)}, not '{mode}'."
            )
        unknown = [kind for kind in kinds if kind not in WORKLOAD_KINDS]
        if unknown or not kinds:
            raise SkopeoPluginException(
                f"'kinds' must list some of {', '.join(WORKLOAD_KINDS)}"
                + (f"; unknown: {', '.join(map(str, unknown))}." if unknown else ".")
            )
        if not environment and not direct:
            raise SkopeoPluginException(
                "Give 'environment' (an oc.generic login) to read workloads, "
                "or 'images' to inspect with skopeo."
            )
        if mode == "pod" and not environment:
            raise SkopeoPluginException("Mode 'pod' needs 'environment' (an oc.generic login).")
        if not all(isinstance(image, str) and image.strip() for image in direct):
            raise SkopeoRuleError("'images' must be a list of image references.")

        rules = parse_rules(
            self.arguments.list("rules", []),
            deployments=self.arguments.get("deployments"),
            tags=self.arguments.get("tags"),
            containers=self.arguments.get("containers"),
        )

        rows: List[Dict[str, Any]] = []
        missing: List[str] = []
        errors: List[str] = []
        to_inspect: List[Tuple[Dict[str, Any], ImageReference]] = []
        matched: List[str] = []
        skipped = 0

        if environment:
            found = self._workloads(environment, namespace, kinds, include_init)
            for workload in found:
                if not workload_selected(rules, exclude, workload.name):
                    skipped += 1
                    continue
                before = len(rows) + len(to_inspect) + len(missing)
                self._collect(workload, mode, rules, rows, to_inspect, missing)
                if len(rows) + len(to_inspect) + len(missing) > before:
                    matched.append(workload.name)
            self.message.info(
                f"{len(found)} workload(s) in "
                f"{namespace or 'the current project'}; {len(matched)} selected "
                f"({skipped} filtered out by name).",
            )

        for image in direct:
            reference = ImageReference.parse(image)
            if selected(rules, None, None, reference.tag):
                to_inspect.append((self._row(None, None, reference, "skopeo"), reference))

        if to_inspect:
            self._inspect(to_inspect, rows, errors)

        for row in rows:
            self.log.info(
                f"{row['deployment'] or '-'}/{row['container'] or '-'}: "
                f"{row['image']} {row['digest'] or '(no digest)'} [{row['source']}]",
            )

        self.outputs.update(
            {
                "mode": mode,
                "namespace": namespace,
                "images": rows,
                "count": len(rows),
                "deployments": sorted(set(matched)),
                "digests": self._digests(rows),
                "missing": missing,
                "errors": errors,
                "file": "",
            },
        )

        if self.arguments.boolean("generate", False):
            self._generate(namespace, rows)

        for item in missing:
            self.message.warning(f"No running pod for {item}; not resolved (mode 'pod').")

        summary = f"{len(rows)} image(s) resolved"
        if errors:
            self.message.error(f"{summary}; {len(errors)} could not be inspected.")
        else:
            self.message.success(f"{summary}.")

        return self._result(
            success=not (errors and fail_on_error),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # OpenShift
    # ------------------------------------------------------------------

    def _kubeconfig(
        self,
        environment: str,
    ) -> Path:
        """
        The oc.generic login session of `environment` (never created here).
        """

        path = (
            self.session_directory
            / self.KUBECONFIG_DIRECTORY
            / environment
            / self.KUBECONFIG_FILENAME
        )

        if not self.filesystem.exists(
            path,
        ):

            raise SkopeoPluginException(
                f"No OpenShift session for environment '{environment}'. "
                "Log in first with oc.generic (operation 'login').",
            )

        return path

    def _workloads(
        self,
        environment: str,
        namespace: str,
        kinds: List[str],
        include_init: bool,
    ) -> List[Workload]:
        """
        The workloads and their running pods, in one `oc get`.
        """

        resources = list(dict.fromkeys(kinds))
        for kind in kinds:
            controller = WORKLOAD_KINDS[kind][1]
            if controller:
                resources.append(controller.lower())
        resources.append("pod")

        command = ["oc", "get", ",".join(resources), "-o", "json"]
        if namespace:
            command += ["-n", namespace]

        result = self._run(
            command,
            env={
                "KUBECONFIG": str(
                    self._kubeconfig(
                        environment,
                    ),
                ),
            },
        )

        if not result.success:
            raise SkopeoPluginException(
                f"oc get failed: {(result.stderr or result.stdout).strip()}",
            )

        try:
            items = json.loads(result.stdout or "{}").get("items") or []
        except ValueError as exc:
            raise SkopeoPluginException(f"oc get did not return JSON: {exc}") from exc

        return workloads(
            items,
            kinds,
            include_init=include_init,
        )

    def _collect(
        self,
        workload: Workload,
        mode: str,
        rules: List[Any],
        rows: List[Dict[str, Any]],
        to_inspect: List[Tuple[Dict[str, Any], ImageReference]],
        missing: List[str],
    ) -> None:
        """
        The images of one workload's containers: running ones, or to inspect.
        """

        for container in workload.containers:

            if mode != "skopeo":
                # One row per distinct image and digest (pods differ during a rollout).
                running: Dict[Tuple[str, Optional[str]], Dict[str, Any]] = {}
                for pod, name, image, image_id in workload.running:
                    if name != container.name:
                        continue
                    reference = ImageReference.parse(image)
                    if not selected(rules, workload.name, name, reference.tag):
                        continue
                    digest = digest_of(image_id) or reference.digest
                    key = (reference.tagged, digest)
                    if key not in running:
                        running[key] = self._row(workload, name, reference, "pod")
                        running[key].update(digest=digest, reference=reference.pinned(digest))
                        rows.append(running[key])
                    running[key]["pods"].append(pod)
                if running:
                    continue

            reference = ImageReference.parse(container.image)
            if not selected(rules, workload.name, container.name, reference.tag):
                continue
            if mode == "pod":
                missing.append(f"{workload.name}/{container.name}")
                continue
            to_inspect.append(
                (self._row(workload, container.name, reference, "skopeo"), reference),
            )

    # ------------------------------------------------------------------
    # Skopeo
    # ------------------------------------------------------------------

    def _inspect(
        self,
        to_inspect: List[Tuple[Dict[str, Any], ImageReference]],
        rows: List[Dict[str, Any]],
        errors: List[str],
    ) -> None:
        """
        `skopeo inspect` each image once; fill the rows.
        """

        tls_verify = bool(self.arguments.boolean("tls_verify", True))
        timeout = self.arguments.integer("timeout", self.DEFAULT_TIMEOUT) or self.DEFAULT_TIMEOUT
        authfile, temporary = self._authfile(
            {reference.registry for _, reference in to_inspect},
        )

        cache: Dict[str, Dict[str, Any]] = {}

        try:

            for row, reference in to_inspect:

                image = reference.pinned(reference.digest) or reference.tagged

                if image not in cache:

                    command = ["skopeo", "inspect", "--no-tags"]
                    if not tls_verify:
                        command.append("--tls-verify=false")
                    if authfile is not None:
                        command += ["--authfile", str(authfile)]
                    command.append(f"docker://{image}")

                    result = self._run(command, timeout=timeout)

                    if not result.success:
                        cache[image] = {"error": (result.stderr or result.stdout).strip()}
                    else:
                        try:
                            cache[image] = json.loads(result.stdout or "{}")
                        except ValueError:
                            cache[image] = {"error": "skopeo did not return JSON"}

                details = cache[image]

                if details.get("error"):
                    errors.append(f"{image}: {details['error']}")
                    continue

                digest = details.get("Digest")
                row.update(
                    digest=digest,
                    reference=reference.pinned(digest),
                    created=details.get("Created"),
                    architecture=details.get("Architecture"),
                )
                rows.append(row)

        finally:

            if temporary and authfile is not None and self.filesystem.exists(authfile):
                self.filesystem.remove(authfile)

    def _authfile(
        self,
        registries: set,
    ) -> Tuple[Optional[Path], bool]:
        """
        The skopeo auth file: `authfile`, or a temporary one (owner-only)
        written from `credentials`, so no password appears in a command line.
        """

        given = self.arguments.path("authfile")
        if given:
            return Path(self.filesystem.path(str(given))).expanduser(), False

        credentials = self.arguments.dictionary("credentials")
        if not credentials:
            return None, False

        username = str(credentials.get("username") or "")
        password = str(credentials.get("password") or credentials.get("token") or "")
        if not username or not password:
            raise SkopeoPluginException("'credentials' needs username and password (or token).")

        token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        path = Path(self.workspace) / f".skopeo-auth-{uuid.uuid4().hex}.json"
        self.filesystem.write_text(
            path,
            json.dumps({"auths": {registry: {"auth": token} for registry in sorted(registries)}}),
        )
        self.filesystem.chmod(path, 0o600)
        return path, True

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------

    def _generate(
        self,
        namespace: str,
        rows: List[Dict[str, Any]],
    ) -> None:
        """
        Write `<namespace>-<YYYYMMDD-HHMMSS>.txt`: one `image:checksum` line
        per distinct image (registry/repository:tag:sha256:...), kept in
        `output_directory` or the plugin's data folder, and published as a
        generated artifact.
        """

        lines = list(
            dict.fromkeys(f"{row['image']}:{row['digest']}" for row in rows if row["digest"])
        )
        unresolved = sum(1 for row in rows if not row["digest"])

        # The namespace read (the session's current project when none was given).
        found = sorted({row["namespace"] for row in rows if row["namespace"]})
        label = namespace or (found[0] if len(found) == 1 else "images")
        label = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip(".-") or "images"

        value = self.arguments.path("output_directory")
        directory = (
            Path(self.filesystem.path(str(value))).expanduser()
            if value
            else Path(self.data_directory) / "generated"
        )
        self.filesystem.mkdir(directory)

        path = directory / f"{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        self.filesystem.write_text(path, "".join(f"{line}\n" for line in lines))

        self.artifacts["image_checksums"] = path
        self.outputs["file"] = str(path)
        self.message.info(f"Wrote {len(lines)} image checksum(s) to {path}.")
        if unresolved:
            self.message.warning(f"{unresolved} image(s) without a checksum were left out.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run(
        self,
        command: List[str],
        **options: Any,
    ) -> Any:

        self.log.debug(
            "Executing: " + " ".join(command),
        )

        try:

            return self.shell.run(
                command,
                **options,
            )

        except FileNotFoundError as exc:

            raise SkopeoPluginException(
                f"'{command[0]}' was not found; install it and make sure it is in PATH.",
            ) from exc

        except OSError as exc:

            raise SkopeoPluginException(
                f"Unable to run {command[0]}: {exc}",
            ) from exc

    @staticmethod
    def _row(
        workload: Optional[Workload],
        container: Optional[str],
        reference: ImageReference,
        source: str,
    ) -> Dict[str, Any]:

        return {
            "namespace": workload.namespace if workload else None,
            "kind": workload.kind if workload else None,
            "deployment": workload.name if workload else None,
            "container": container,
            "image": reference.tagged,
            "registry": reference.registry,
            "repository": reference.repository,
            "tag": reference.tag or "latest",
            "digest": reference.digest,
            "reference": reference.pinned(reference.digest),
            "source": source,
            "pods": [],
        }

    @staticmethod
    def _digests(
        rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        deployment -> container -> {image, digest} (several when pods differ,
        e.g. during a rollout); direct images under their own name.
        """

        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            owner = row["deployment"] or row["image"]
            entry = {"image": row["image"], "digest": row["digest"]}
            containers = result.setdefault(owner, {})
            key = row["container"] or "image"
            if key in containers:
                existing = containers[key]
                containers[key] = (existing if isinstance(existing, list) else [existing]) + [entry]
            else:
                containers[key] = entry
        return result

    def _result(
        self,
        *,
        success: bool,
        errors: List[str] | None = None,
    ) -> PluginResult:
        """
        Build the standard plugin result (nothing is changed).
        """

        return PluginResult(
            success=success,
            changed=False,
            outputs=dict(
                self.outputs,
            ),
            changes=[],
            errors=errors or [],
            warnings=[],
            metadata={
                "artifacts": {name: str(path) for name, path in self.artifacts.items()},
            },
        )
