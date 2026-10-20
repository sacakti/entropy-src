"""
Entropy node agent.

Runs on a remote node as the SSH user it was installed for. It pulls
runs from the main node, executes them with Entropy's own workflow
engine against a node-local Entropy home, and streams their events,
console output and final state back. A heartbeat carries resource
metrics and returns stop requests.

The agent keeps no credentials except its revocable node token. When
the main node revokes it, the agent exits.
"""

from __future__ import annotations

import faulthandler
import hashlib
import io
import json
import logging
import os
import signal
import tarfile
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict

from lib.system.install import scratch_directory

from .client import AgentClient, AgentRevokedError, AgentTransientError

AGENT_VERSION = "1"

HEARTBEAT_SECONDS = 15
CLAIM_WAIT_SECONDS = 20
FORWARD_SECONDS = 1.0
# A quiet run still reports this often, to pick up stop requests.
KEEPALIVE_SECONDS = 3.0
LOG_CHUNK = 256_000
EVENT_BATCH = 500

FINISHED = ("completed", "failed", "cancelled")

LOGGER = logging.getLogger("entropy.agent")


def _event_payload(event: Any) -> Dict[str, Any]:
    created = event.created_at
    return {
        "type": event.event_type,
        "source": event.source,
        "level": event.level,
        "message": event.message,
        "node_type": event.node_type,
        "node_id": event.node_id,
        "node_name": event.node_name,
        "payload": event.payload,
        "created_at": created.isoformat() if created else None,
    }


class Agent:
    """One agent process for one node."""

    def __init__(self, config_file: Path) -> None:
        config = json.loads(config_file.read_text(encoding="utf-8"))
        self.config_file = config_file
        self.directory = config_file.parent
        self.node = config["node"]
        self.max_jobs = int(config.get("max_jobs", 2))
        self.client = AgentClient(
            config["server_url"],
            config["token"],
            verify_tls=bool(config.get("verify_tls", True)),
            ca_file=config.get("ca_file") or None,
            version=AGENT_VERSION,
        )

        self.state_file = self.directory / "state.json"
        self.jobs_directory = self.directory / "jobs"
        self.plugin_cache = self.directory / "cache" / "plugins"
        self.jobs_directory.mkdir(parents=True, exist_ok=True)
        self.plugin_cache.mkdir(parents=True, exist_ok=True)

        # main job id (str) -> {local, cursor, offset}
        self.active: Dict[str, Dict[str, Any]] = self._load_state()
        self.stop_event = threading.Event()
        self.revoked = False
        self.lock = threading.Lock()
        self.context: Any = None
        self.metrics: Any = None

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def _load_state(self) -> Dict[str, Dict[str, Any]]:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_state(self) -> None:
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.active), encoding="utf-8")
        temporary.replace(self.state_file)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def build_context(self) -> None:
        from core.context_factory import ContextFactory
        from lib.runs.nodes import LocalMetrics

        factory = ContextFactory(interactive=False)
        self.context = factory.build()
        factory.discover()
        self.metrics = LocalMetrics(Path(self.context.bootstrap.home))

    def run(self) -> int:
        signal.signal(signal.SIGTERM, lambda *_: self.stop_event.set())
        signal.signal(signal.SIGINT, lambda *_: self.stop_event.set())
        # `kill -USR1 <pid>` writes every thread's stack to agent.out.
        faulthandler.register(signal.SIGUSR1, all_threads=True)

        lock = self._single_instance()
        if lock is None:
            LOGGER.error("Another agent is already running from %s.", self.directory)
            return 1

        self.build_context()
        LOGGER.info("Agent for node '%s' started.", self.node)

        for target, name in (
            (self._heartbeat_loop, "heartbeat"),
            (self._forward_loop, "forward"),
            (self._claim_loop, "claim"),
        ):
            threading.Thread(target=target, name=name, daemon=True).start()

        # Daemon threads may sit in a long poll; exit as soon as asked.
        while not self.stop_event.wait(1):
            pass

        # Runs keep going in their own processes; a restarted agent resumes them.
        LOGGER.info("Agent stopped.")
        lock.close()
        return 0

    def _single_instance(self) -> Any:
        import fcntl

        handle = (self.directory / "agent.lock").open("w")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return None
        return handle

    def _claim_loop(self) -> None:
        """Take new runs while there is capacity; claims long-poll."""

        backoff = 1.0
        while not self.stop_event.is_set() and not self.revoked:
            try:
                with self.lock:
                    busy = len(self.active) >= self.max_jobs
                if busy:
                    self.stop_event.wait(FORWARD_SECONDS)
                else:
                    self._claim()
                backoff = 1.0
            except AgentRevokedError as exc:
                LOGGER.error("%s Stopping.", exc)
                self.revoked = True
                self.stop_event.set()
            except AgentTransientError as exc:
                LOGGER.warning("%s", exc)
                self.stop_event.wait(backoff)
                backoff = min(backoff * 2, 60)
            except Exception:  # noqa: BLE001 - keep the agent alive
                LOGGER.exception("Unexpected agent error.")
                self.stop_event.wait(5)

    def _forward_loop(self) -> None:
        """Stream events, output and state of active runs every second."""

        backoff = FORWARD_SECONDS
        while not self.stop_event.is_set() and not self.revoked:
            try:
                self._forward_all()
                backoff = FORWARD_SECONDS
            except AgentRevokedError as exc:
                LOGGER.error("%s Stopping.", exc)
                self.revoked = True
                self.stop_event.set()
                return
            except AgentTransientError as exc:
                LOGGER.warning("Forwarding failed: %s", exc)
                backoff = min(backoff * 2, 30)
            except Exception:  # noqa: BLE001
                LOGGER.exception("Forwarding error.")
                backoff = 5
            self.stop_event.wait(backoff)

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    def _heartbeat_loop(self) -> None:
        from lib.runs.nodes import local_info

        while not self.stop_event.is_set() and not self.revoked:
            try:
                metrics = self.metrics.collect()
                with self.lock:
                    running = list(self.active)
                metrics["running_jobs"] = len(running)
                metrics["agent_up"] = True
                info = {**local_info(), "agent_dir": str(self.directory)}
                response = self.client.request(
                    "POST",
                    "/api/agent/heartbeat",
                    {
                        "version": AGENT_VERSION,
                        "metrics": metrics,
                        "info": info,
                        "running": running,
                    },
                )
                self.max_jobs = int(response.get("max_jobs", self.max_jobs))
                for job_id in response.get("stop", []):
                    self._stop(str(job_id))
            except AgentRevokedError as exc:
                LOGGER.error("%s Stopping.", exc)
                self.revoked = True
                self.stop_event.set()
                return
            except AgentTransientError as exc:
                LOGGER.warning("Heartbeat failed: %s", exc)
            except Exception:  # noqa: BLE001
                LOGGER.exception("Heartbeat error.")
            self.stop_event.wait(HEARTBEAT_SECONDS)

    # ------------------------------------------------------------------
    # Claim and start
    # ------------------------------------------------------------------

    def _claim(self) -> None:
        response = self.client.request(
            "POST",
            "/api/agent/jobs/claim",
            {"wait": CLAIM_WAIT_SECONDS},
            timeout=CLAIM_WAIT_SECONDS + 15,
        )
        spec = response.get("job")
        if spec:
            self._start(spec)

    def _report_failure(self, job_id: int, message: str) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
        self.client.request(
            "POST",
            f"/api/agent/jobs/{job_id}/events",
            {
                "events": [
                    {
                        "type": "message",
                        "source": "entropy.agent",
                        "level": "error",
                        "message": message,
                        "node_type": "workflow",
                        "created_at": now,
                    }
                ],
                "log": f"{message}\n",
                "state": "failed",
                "exit_code": 1,
                "final": True,
            },
        )

    def _ensure_plugins(self, plugins: list) -> None:
        manager = self.context.plugin_manager

        for plugin in plugins:
            name = plugin["qualified_name"]
            digest = plugin["digest"]
            marker = self.plugin_cache / f"{name}.sha256"

            if manager.exists(name) and marker.exists() and marker.read_text().strip() == digest:
                continue

            data = self.client.download(f"/api/agent/plugins/{name}")
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError(
                    f"Plugin '{name}' changed while it was being fetched; retry the run."
                )

            with tempfile.TemporaryDirectory(prefix="entropy-plugin-") as directory:
                target = Path(directory) / name.split(".", 1)[1]
                target.mkdir()
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                    for member in archive.getmembers():
                        resolved = (target / member.name).resolve()
                        if (
                            not str(resolved).startswith(str(target.resolve()))
                            or not member.isfile()
                        ):
                            raise RuntimeError(f"Plugin '{name}' archive contains an unsafe entry.")
                    archive.extractall(target)
                manager.install(target, reinstall=manager.exists(name))
            marker.write_text(digest)

    def _start(self, spec: Dict[str, Any]) -> None:
        from lib.auth.manager import SESSION_TOKEN_ENV
        from lib.models.workflow import WorkflowExecutionOptions

        job_id = int(spec["job_id"])
        with self.lock:
            if str(job_id) in self.active:
                return  # handed out again after a lost acknowledgement

        # Acknowledge the claim at once; plugin syncing may take a while.
        acknowledged = self.client.request(
            "POST",
            f"/api/agent/jobs/{job_id}/events",
            {"state": "starting"},
        )
        if acknowledged.get("stop"):
            self.client.request(
                "POST",
                f"/api/agent/jobs/{job_id}/events",
                {"state": "cancelled", "exit_code": 130, "final": True},
            )
            return

        try:
            self._ensure_plugins(spec.get("plugins", []))

            path = self.jobs_directory / f"{job_id}.json"
            path.write_text(spec["definition"], encoding="utf-8")

            user = spec["user"]
            sessions = self.context.session_manager
            session = sessions.issue(
                int(user["id"] or 0), user["username"], user.get("full_name"), hours=72
            )
            try:
                local = self.context.workflow_manager.start(
                    file=path,
                    options=WorkflowExecutionOptions(variables=spec.get("variables") or {}),
                    session=session,
                    environment={SESSION_TOKEN_ENV: session.token},
                )
            except Exception:
                sessions.revoke(session.token)
                raise
        except (AgentRevokedError, AgentTransientError):
            raise
        except Exception as exc:  # noqa: BLE001 - report every start failure
            LOGGER.exception("Run #%s could not start.", job_id)
            self._report_failure(job_id, f"The node could not start this run: {exc}")
            return

        with self.lock:
            self.active[str(job_id)] = {"local": local.require_id(), "cursor": None, "offset": 0}
            self._save_state()
        LOGGER.info("Run #%s started as local job %s.", job_id, local.require_id())

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------

    def _log_path(self, local_id: int) -> Path:
        root = scratch_directory(self.context.bootstrap.project_root)
        return root / f"workflow-worker-{local_id}.log"

    def _forward_all(self) -> None:
        with self.lock:
            items = list(self.active.items())
        for job_id, entry in items:
            self._forward(job_id, entry)

    def _forward(self, job_id: str, entry: Dict[str, Any]) -> None:
        from lib.runs.service import _pid_alive

        jobs = self.context.workflow_job_manager
        local = jobs.get(entry["local"])
        state = local.state.value

        # A worker that died without recording its end failed.
        if state not in FINISHED and local.pid and not _pid_alive(local.pid):
            time.sleep(0.5)
            local = jobs.get(entry["local"])
            if local.state.value not in FINISHED:
                jobs.fail(entry["local"], 1)
                local = jobs.get(entry["local"])
            state = local.state.value

        events = jobs.events(entry["local"], after=entry["cursor"], limit=EVENT_BATCH)

        log = ""
        path = self._log_path(entry["local"])
        if path.exists():
            with path.open("rb") as handle:
                handle.seek(entry["offset"])
                chunk = handle.read(LOG_CHUNK)
            log = chunk.decode("utf-8", errors="replace")
            new_offset = entry["offset"] + len(chunk)
        else:
            new_offset = entry["offset"]

        final = state in FINISHED and len(events) < EVENT_BATCH and len(log) < LOG_CHUNK
        quiet = time.monotonic() - entry.get("posted", 0.0) < KEEPALIVE_SECONDS
        if not events and not log and not final and state == entry.get("sent_state") and quiet:
            return

        response = self.client.request(
            "POST",
            f"/api/agent/jobs/{job_id}/events",
            {
                "events": [_event_payload(event) for event in events],
                "log": log,
                "state": state,
                "exit_code": local.exit_code,
                "final": final,
            },
        )

        with self.lock:
            entry["cursor"] = events[-1].id if events else entry["cursor"]
            entry["offset"] = new_offset
            entry["sent_state"] = state
            entry["posted"] = time.monotonic()
            if final:
                self.active.pop(job_id, None)
                (self.jobs_directory / f"{job_id}.json").unlink(missing_ok=True)
                path.unlink(missing_ok=True)
            self._save_state()

        # Each report answers whether the run should stop.
        if response.get("stop") and not final:
            self._stop(job_id)

    # ------------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------------

    def _stop(self, job_id: str) -> None:
        from lib.runs.service import _pid_alive

        with self.lock:
            entry = self.active.get(job_id)
            # Interrupt once; the worker then winds down on its own.
            if entry is None or entry.get("stopping"):
                return
            entry["stopping"] = True

        jobs = self.context.workflow_job_manager
        local = jobs.get(entry["local"])
        if local.state.value in FINISHED:
            return
        if local.pid and _pid_alive(local.pid):
            # SIGINT: the worker records the cancellation itself.
            jobs.stop(local.pid)
        else:
            jobs.cancel(entry["local"])
        LOGGER.info("Stop requested for run #%s.", job_id)


def configure_logging(directory: Path) -> None:
    handler = logging.FileHandler(directory / "agent.log")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    if os.isatty(2):
        root.addHandler(logging.StreamHandler())
