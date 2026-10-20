"""
Set up (or remove) the Entropy agent on a server over SSH.

The SSH password or key is used only while a setup runs and is never
stored or logged. Afterwards the agent authenticates to the main node
with its own revocable token; setting a node up again issues a new one.

Layout on the node (default ~/.entropy-agent):

    agent.json          node name, main node URL, token (mode 0600)
    bin/entropy-agent   launcher; bin/agent-ctl start|stop|status
    python/             bundled CPython, when the server has none usable
    runtime/            Entropy code and vendored wheels
    home/               the agent's Entropy home (config, job database)
    workspace/          run workspaces
"""

from __future__ import annotations

import json
import re
import secrets
import shlex
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from lib.database.connection import DatabaseConnection
from lib.runs.nodes import NodeStore, valid_node_name
from lib.runs.store import ensure_run_schema, utcnow

from .dispatch import token_hash
from .packaging import (
    CPYTHON_FULL_VERSION,
    PYTHON_VERSION,
    PackagingError,
    agent_requirements,
    cpython_archive,
    runtime_bundle,
)
from .ssh import SSHError, SSHSession, forget_host_key

HEARTBEAT_WAIT_SECONDS = 90
_INSTALL_DIR = re.compile(r"^(~|/)[A-Za-z0-9._/-]*$")

# One setup per node at a time.
_RUNNING: Dict[str, threading.Thread] = {}
_RUNNING_LOCK = threading.Lock()


class ProvisionError(Exception):
    """A setup step failed; the message is safe to show."""


@dataclass
class ProvisionRequest:
    """Everything a setup needs. Credentials live only in this object."""

    name: str
    host: str
    port: int
    ssh_user: str
    server_url: str
    password: Optional[str] = None
    private_key: Optional[str] = None
    passphrase: Optional[str] = None
    verify_tls: bool = True
    ca_cert: Optional[str] = None
    python: str = "auto"  # auto | system | bundled
    install_dir: str = "~/.entropy-agent"
    max_jobs: int = 2
    description: str = ""
    forget_host_key: bool = False

    def validate(self) -> None:
        if not valid_node_name(self.name) or self.name == "local":
            raise ProvisionError(
                "Node name must be lowercase letters, digits, '.', '_' or '-' (not 'local')."
            )
        if not re.match(r"^[A-Za-z0-9.:_-]{1,253}$", self.host or ""):
            raise ProvisionError("Enter a host name or IP address.")
        if not 1 <= int(self.port) <= 65535:
            raise ProvisionError("Port must be between 1 and 65535.")
        if not re.match(r"^[A-Za-z0-9._-]{1,64}$", self.ssh_user or ""):
            raise ProvisionError("Enter the SSH username.")
        if not re.match(r"^https?://[^\s/]+(/[^\s]*)?$", self.server_url or ""):
            raise ProvisionError("The main node URL must start with https:// (or http://).")
        if self.python not in ("auto", "system", "bundled"):
            raise ProvisionError("Python must be auto, system or bundled.")
        if not _INSTALL_DIR.match(self.install_dir or "") or ".." in self.install_dir:
            raise ProvisionError("Install directory must be an absolute path or start with ~.")
        if not 1 <= int(self.max_jobs) <= 64:
            raise ProvisionError("Concurrent runs must be between 1 and 64.")

    def forget_secrets(self) -> None:
        self.password = self.private_key = self.passphrase = None


def _q(value: str) -> str:
    return shlex.quote(value)


class Provisioner:
    """Runs one node setup or removal and records its progress."""

    def __init__(self, context: Any) -> None:
        self._context = context
        self.connection: DatabaseConnection = context.database_manager.connection
        ensure_run_schema(self.connection)
        self.nodes = NodeStore(self.connection)
        home = Path(context.bootstrap.home)
        self.known_hosts = home / "ssh" / "known_hosts"
        self.cache = home / "node-cache"
        self._record_id: Optional[int] = None
        self._log: List[Dict[str, str]] = []

    # ------------------------------------------------------------------
    # Records
    # ------------------------------------------------------------------

    def _begin(self, node: str, action: str, user: Any) -> int:
        with self.connection.transaction():
            cursor = self.connection.execute(
                "INSERT INTO node_provisioning"
                " (node, action, status, log, user_id, username, created_at)"
                " VALUES (?, ?, 'running', '[]', ?, ?, ?)",
                (
                    node,
                    action,
                    getattr(user, "id", None),
                    getattr(user, "username", None),
                    utcnow(),
                ),
            )
        return int(cursor.lastrowid)

    def log(self, message: str, level: str = "info") -> None:
        self._log.append({"at": utcnow(), "level": level, "message": message})
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE node_provisioning SET log = ? WHERE id = ?",
                (json.dumps(self._log), self._record_id),
            )

    def _finish(self, error: Optional[str]) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE node_provisioning SET status = ?, error = ?, finished_at = ? WHERE id = ?",
                ("failed" if error else "succeeded", error, utcnow(), self._record_id),
            )

    def record(self, record_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone("SELECT * FROM node_provisioning WHERE id = ?", (record_id,))
        if row is None:
            return None
        result = dict(row)
        result["log"] = json.loads(row["log"] or "[]")
        return result

    def latest(self, node: str) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone(
            "SELECT id FROM node_provisioning WHERE node = ? ORDER BY id DESC LIMIT 1",
            (node,),
        )
        return self.record(int(row["id"])) if row else None

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------

    def start(
        self,
        request: ProvisionRequest,
        user: Any,
        *,
        action: str = "install",
        on_done: Optional[Callable[[Optional[str]], None]] = None,
    ) -> int:
        """Start a setup (or removal) in the background; returns its record id."""

        request.validate()

        existing = self.nodes.get(request.name)
        if existing is not None and existing["kind"] == "local":
            raise ProvisionError("The main node cannot be set up over SSH.")

        with _RUNNING_LOCK:
            thread = _RUNNING.get(request.name)
            if thread is not None and thread.is_alive():
                raise ProvisionError(f"Node '{request.name}' is already being set up.")

            if action == "install":
                self.nodes.save_remote(
                    request.name,
                    host=request.host,
                    port=int(request.port),
                    ssh_user=request.ssh_user,
                    install_dir=request.install_dir,
                    server_url=request.server_url,
                    description=request.description,
                    max_jobs=int(request.max_jobs),
                )

            self._record_id = self._begin(request.name, action, user)
            record_id = self._record_id
            target = self._install if action == "install" else self._uninstall

            def work() -> None:
                error: Optional[str] = None
                try:
                    target(request)
                except (SSHError, PackagingError, ProvisionError) as exc:
                    error = str(exc)
                except Exception as exc:  # noqa: BLE001 - report any failure
                    error = f"Unexpected error: {exc.__class__.__name__}: {exc}"
                finally:
                    request.forget_secrets()
                if error:
                    self.log(error, "error")
                self._finish(error)
                if on_done is not None:
                    on_done(error)

            thread = threading.Thread(target=work, name=f"provision-{request.name}", daemon=True)
            _RUNNING[request.name] = thread
            thread.start()

        return record_id

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------

    def _connect(self, request: ProvisionRequest) -> SSHSession:
        if request.forget_host_key:
            forget_host_key(self.known_hosts, request.host, request.port)
            self.log("Forgot the previously saved host key.")

        auth = (
            "a private key"
            if request.private_key
            else "a password" if request.password else "the Entropy server's SSH keys"
        )
        self.log(f"Connecting to {request.ssh_user}@{request.host}:{request.port} with {auth}…")
        session = SSHSession(
            request.host,
            request.port,
            request.ssh_user,
            known_hosts=self.known_hosts,
            password=request.password,
            private_key=request.private_key,
            passphrase=request.passphrase,
        )
        session.open()
        # Connected: the credentials are no longer needed.
        request.forget_secrets()
        fingerprint = session.host_key_fingerprint()
        self.log(f"Connected. Host key {fingerprint or 'recorded'}.", "success")
        return session

    def _detect(self, ssh: SSHSession) -> Dict[str, Any]:
        script = r"""
echo "os=$(uname -s)"
echo "arch=$(uname -m)"
echo "home=$HOME"
for tool in tar gzip; do command -v "$tool" >/dev/null 2>&1 || echo "missing=$tool"; done
for candidate in python3.9 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    version=$("$candidate" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null)
    if "$candidate" -m pip --version >/dev/null 2>&1; then pip=pip; else pip=nopip; fi
    echo "python=$(command -v "$candidate") $version $pip"
  fi
done
if command -v systemctl >/dev/null 2>&1 \
  && systemctl --user show-environment >/dev/null 2>&1; then echo "systemd=user"; fi
if command -v crontab >/dev/null 2>&1; then echo "cron=yes"; fi
if command -v setsid >/dev/null 2>&1; then echo "setsid=yes"; fi
df -Pk "$HOME" 2>/dev/null | awk 'NR==2 {print "free_kb=" $4}'
"""
        facts: Dict[str, Any] = {"pythons": [], "missing": []}
        for line in ssh.check(script, what="Inspecting the server").splitlines():
            key, _, value = line.partition("=")
            if key == "python":
                parts = value.split()
                if len(parts) == 3 and re.match(r"^\d+\.\d+\.\d+$", parts[1]):
                    facts["pythons"].append(
                        {"path": parts[0], "version": parts[1], "pip": parts[2] == "pip"}
                    )
            elif key == "missing":
                facts["missing"].append(value)
            elif key:
                facts[key] = value.strip()
        return facts

    def _choose_python(self, request: ProvisionRequest, facts: Dict[str, Any]) -> Optional[str]:
        """The system Python to use, or None to ship the bundled one."""

        usable = [
            item
            for item in facts["pythons"]
            if item["pip"] and item["version"].startswith(PYTHON_VERSION + ".")
        ]
        any_modern = [
            item
            for item in facts["pythons"]
            if item["pip"] and tuple(int(x) for x in item["version"].split(".")[:2]) >= (3, 9)
        ]

        if request.python == "bundled":
            return None
        if usable:
            return usable[0]["path"]
        if request.python == "system":
            if any_modern:
                self.log(
                    f"Using {any_modern[0]['path']} {any_modern[0]['version']}; packages not "
                    f"vendored for it are installed from the network.",
                    "warning",
                )
                return any_modern[0]["path"]
            raise ProvisionError(
                "No Python 3.9 or newer with pip was found on the server. Install one or "
                "choose the bundled Python."
            )
        found = ", ".join(f"{item['version']}" for item in facts["pythons"]) or "none"
        self.log(
            f"No Python {PYTHON_VERSION} with pip on the server (found: {found}); shipping one."
        )
        return None

    def _install(self, request: ProvisionRequest) -> None:
        started = datetime.now(timezone.utc)
        ssh = self._connect(request)
        # Set once the previous agent is stopped, cleared once the new one starts.
        restart_previous: Optional[str] = None
        try:
            facts = self._detect(ssh)
            if facts["missing"]:
                raise ProvisionError(
                    f"The server lacks required tools: {', '.join(facts['missing'])}."
                )
            self.log(
                f"Server: {facts.get('os', '?')} {facts.get('arch', '?')}, "
                f"home {facts.get('home', '?')}, "
                f"{int(facts.get('free_kb', 0) or 0) // 1024} MB free."
            )
            if int(facts.get("free_kb", 0) or 0) < 400 * 1024:
                raise ProvisionError(
                    "At least 400 MB of free disk space is needed in the home directory."
                )

            base = request.install_dir.replace("~", facts["home"], 1)
            if not base.startswith("/"):
                raise ProvisionError("Could not resolve the install directory.")
            home = f"{base}/home"
            ctl = f"{base}/bin/agent-ctl"

            python = self._choose_python(request, facts)
            if python is None and facts.get("os") != "Linux":
                raise ProvisionError(
                    "The bundled Python is for Linux; install Python 3.9 with pip on this server."
                )

            rc, out, _ = ssh.run(f"[ -x {_q(ctl)} ] && {_q(ctl)} status")
            if rc == 0 and "running" in out:
                restart_previous = ctl
            ssh.check(
                f"mkdir -p {_q(base)}/bin {_q(base)}/cache {_q(home)} {_q(base)}/workspace && "
                f"chmod 700 {_q(base)} && "
                f"if [ -x {_q(ctl)} ]; then {_q(ctl)} stop >/dev/null 2>&1 || true; fi",
                what="Preparing the install directory",
            )
            self.log(f"Install directory {base} ready.")

            # Python
            if python is None:
                python = f"{base}/python/bin/python3"
                rc, out, _ = ssh.run(f"{_q(python)} -c 'import sys; print(sys.version.split()[0])'")
                if rc == 0 and out.strip() == CPYTHON_FULL_VERSION:
                    self.log(f"Bundled Python {CPYTHON_FULL_VERSION} already installed.")
                else:
                    self.log(f"Preparing Python {CPYTHON_FULL_VERSION} for {facts['arch']}…")
                    archive = cpython_archive(self.cache, facts["arch"])
                    self.log(f"Uploading Python ({archive.stat().st_size // (1 << 20)} MB)…")
                    ssh.upload(archive, f"{base}/cache/python.tar.gz", timeout=900)
                    ssh.check(
                        f"cd {_q(base)} && rm -rf python && tar -xzf cache/python.tar.gz && "
                        f"rm -f cache/python.tar.gz",
                        what="Unpacking Python",
                        timeout=600,
                    )
                    self.log(f"Python {CPYTHON_FULL_VERSION} installed.", "success")
            else:
                self.log(f"Using the server's Python at {python}.")

            # Runtime
            project_root = Path(self._context.bootstrap.project_root)
            archive, digest = runtime_bundle(project_root, self.cache)
            rc, out, _ = ssh.run(f"cat {_q(base)}/runtime/.digest 2>/dev/null")
            if rc == 0 and out.strip() == digest:
                self.log("Entropy runtime is up to date.")
            else:
                self.log(
                    f"Uploading the Entropy runtime ({archive.stat().st_size // (1 << 20)} MB)…"
                )
                ssh.upload(archive, f"{base}/cache/runtime.tar.gz", timeout=900)
                ssh.check(
                    f"cd {_q(base)} && rm -rf runtime.new && mkdir runtime.new && "
                    f"tar -xzf cache/runtime.tar.gz -C runtime.new && "
                    f"printf '%s\\n' {_q(digest)} > runtime.new/.digest && "
                    f"rm -rf runtime.old && if [ -d runtime ]; then mv runtime runtime.old; fi && "
                    f"mv runtime.new runtime && rm -rf runtime.old cache/runtime.tar.gz",
                    what="Unpacking the Entropy runtime",
                    timeout=600,
                )
                self.log("Entropy runtime installed.", "success")

            # Packages
            requirements = agent_requirements(project_root)
            marker = f"{python}\n{requirements}"
            rc, out, _ = ssh.run(f"cat {_q(home)}/site-packages/.entropy-requirements 2>/dev/null")
            if rc == 0 and out == marker:
                self.log("Python packages are up to date.")
            else:
                self.log("Installing Python packages…")
                ssh.write(requirements, f"{base}/cache/requirements.txt", mode="644")
                wheels = f"{base}/runtime/resources/wheels/linux"
                offline = facts.get("arch") in ("x86_64", "amd64") and facts.get("os") == "Linux"
                pip = (
                    f"{_q(python)} -m pip install --disable-pip-version-check "
                    "--no-warn-script-location --upgrade "
                    f"--target {_q(home)}/site-packages -r {_q(base)}/cache/requirements.txt"
                )
                rc, out, err = ssh.run(
                    f"{pip} --no-index --find-links {_q(wheels)}" if offline else pip, timeout=900
                )
                if rc != 0 and offline:
                    self.log(
                        "Vendored wheels did not fit this Python; trying the package index…",
                        "warning",
                    )
                    rc, out, err = ssh.run(pip, timeout=900)
                if rc != 0:
                    detail = (err.strip() or out.strip()).splitlines()
                    raise ProvisionError(
                        "Installing Python packages failed: "
                        + (detail[-1][:300] if detail else f"exit code {rc}")
                    )
                ssh.write(marker, f"{home}/site-packages/.entropy-requirements", mode="644")
                self.log("Python packages installed.", "success")

            # Agent home
            environment = (
                f"cd {_q(base)}/runtime && ENTROPY_HOME={_q(home)} "
                f"PYTHONPATH={_q(base)}/runtime:{_q(home)}/site-packages PYTHONDONTWRITEBYTECODE=1"
            )
            ssh.check(
                f"{environment} {_q(python)} -m lib.agent init --workspace {_q(base)}/workspace",
                what="Initialising the agent's Entropy home",
                timeout=300,
            )
            self.log("Agent home initialised.")

            # Token and configuration
            token = secrets.token_urlsafe(32)
            ca_file = None
            if request.ca_cert and request.ca_cert.strip():
                ca_file = f"{base}/ca.pem"
                ssh.write(request.ca_cert.strip() + "\n", ca_file, mode="644")
            config = {
                "node": request.name,
                "server_url": request.server_url.rstrip("/"),
                "token": token,
                "verify_tls": bool(request.verify_tls),
                "ca_file": ca_file,
                "max_jobs": int(request.max_jobs),
            }
            ssh.write(json.dumps(config, indent=2) + "\n", f"{base}/agent.json", mode="600")
            self.nodes.set_token(request.name, token_hash(token), ssh.host_key_fingerprint())
            del token
            self.log("Issued a new node token (any previous token is revoked).")

            # Launcher and supervisor
            unit = f"entropy-agent-{request.name}"
            launcher = (
                "#!/bin/sh\n"
                f"# Entropy agent for node '{request.name}'.\n"
                f"cd {_q(base)}/runtime || exit 1\n"
                f"export ENTROPY_HOME={_q(home)}\n"
                f"export PYTHONPATH={_q(base)}/runtime:{_q(home)}/site-packages\n"
                "export PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1\n"
                f"exec {_q(python)} -m lib.agent run --config {_q(base)}/agent.json\n"
            )
            detach = "setsid " if facts.get("setsid") else ""
            control = f"""#!/bin/sh
# Control the Entropy agent for node '{request.name}': start | stop | status
DIR={_q(base)}
UNIT={_q(unit)}
SERVICE="$HOME/.config/systemd/user/$UNIT.service"
running() {{ [ -f "$DIR/agent.pid" ] && kill -0 "$(cat "$DIR/agent.pid")" 2>/dev/null; }}
case "$1" in
  start)
    if [ -f "$SERVICE" ] && systemctl --user start "$UNIT" 2>/dev/null; then exit 0; fi
    running && exit 0
    {detach}nohup "$DIR/bin/entropy-agent" >> "$DIR/agent.out" 2>&1 < /dev/null &
    echo $! > "$DIR/agent.pid" ;;
  stop)
    if [ -f "$SERVICE" ]; then systemctl --user stop "$UNIT" 2>/dev/null; fi
    if running; then
      pid=$(cat "$DIR/agent.pid")
      kill "$pid" 2>/dev/null
      tries=0
      while kill -0 "$pid" 2>/dev/null && [ $tries -lt 20 ]; do sleep 1; tries=$((tries + 1)); done
      kill -9 "$pid" 2>/dev/null
    fi
    rm -f "$DIR/agent.pid" ;;
  status)
    if [ -f "$SERVICE" ] && systemctl --user is-active --quiet "$UNIT"; then
      echo running; exit 0
    fi
    if running; then echo running; else echo stopped; exit 3; fi ;;
  *) echo "usage: $0 start|stop|status" >&2; exit 2 ;;
esac
"""
            ssh.write(launcher, f"{base}/bin/entropy-agent", mode="755")
            ssh.write(control, ctl, mode="755")

            if facts.get("systemd") == "user":
                service = (
                    "[Unit]\n"
                    f"Description=Entropy agent (node {request.name})\n"
                    "After=network-online.target\n\n"
                    "[Service]\n"
                    f"ExecStart={base}/bin/entropy-agent\n"
                    "Restart=on-failure\n"
                    "RestartSec=10\n\n"
                    "[Install]\n"
                    "WantedBy=default.target\n"
                )
                ssh.check('mkdir -p "$HOME/.config/systemd/user"', what="Preparing systemd")
                ssh.write(
                    service, f"{facts['home']}/.config/systemd/user/{unit}.service", mode="644"
                )
                ssh.check(
                    "systemctl --user daemon-reload && "
                    f"systemctl --user enable {_q(unit)} >/dev/null 2>&1",
                    what="Enabling the agent service",
                )
                rc, out, _ = ssh.run(
                    'loginctl enable-linger "$USER" >/dev/null 2>&1; '
                    'loginctl show-user "$USER" -p Linger 2>/dev/null'
                )
                self.log(f"Installed systemd user service {unit}.")
                if "Linger=yes" not in out:
                    self.log(
                        "Lingering is off for this user, so the agent stops when they log out. "
                        "Ask an administrator to run 'loginctl enable-linger "
                        f"{request.ssh_user}'.",
                        "warning",
                    )
            elif facts.get("cron"):
                entry = f"@reboot {base}/bin/agent-ctl start # {unit}"
                ssh.check(
                    f"(crontab -l 2>/dev/null | grep -v {_q('# ' + unit)}; "
                    f"echo {_q(entry)}) | crontab -",
                    what="Registering the agent to start at boot",
                )
                self.log("Registered the agent to start at boot (cron).")
            else:
                self.log(
                    "Neither systemd user services nor cron are available: the agent will not "
                    "restart after a reboot. Run 'agent-ctl start' or set it up again.",
                    "warning",
                )

            ssh.check(f"{_q(ctl)} start", what="Starting the agent")
            restart_previous = None
            self.log("Agent started; waiting for it to connect to the main node…")

            deadline = time.monotonic() + HEARTBEAT_WAIT_SECONDS
            while time.monotonic() < deadline:
                node = self.nodes.get(request.name)
                seen = node and node.get("last_seen_at")
                if seen and datetime.fromisoformat(seen) >= started:
                    self.log(f"Node '{request.name}' is connected and ready.", "success")
                    return
                time.sleep(2)

            _, tail, _ = ssh.run(
                f"tail -n 15 {_q(base)}/agent.log {_q(base)}/agent.out 2>/dev/null"
            )
            raise ProvisionError(
                f"The agent started but did not reach {request.server_url} within "
                f"{HEARTBEAT_WAIT_SECONDS} seconds. Check that this URL is reachable from the node "
                f"and its TLS settings. Agent log:\n{tail.strip()[-1500:] or '(empty)'}"
            )
        except Exception:
            if restart_previous:
                # Leave the node as it was: the previous agent keeps its token.
                rc, _, _ = ssh.run(f"{_q(restart_previous)} start")
                if rc == 0:
                    self.log(
                        "Restarted the previous agent; the node keeps running as before.", "warning"
                    )
            raise
        finally:
            ssh.close()

    # ------------------------------------------------------------------
    # Uninstall
    # ------------------------------------------------------------------

    def _uninstall(self, request: ProvisionRequest) -> None:
        node = self.nodes.get(request.name)
        ssh = self._connect(request)
        try:
            facts = self._detect(ssh)
            base = (node or {}).get("install_dir") or request.install_dir
            base = base.replace("~", facts["home"], 1)
            unit = f"entropy-agent-{request.name}"

            rc, _, _ = ssh.run(f"test -f {_q(base)}/agent.json")
            if rc != 0:
                self.log(f"No agent installed at {base}; nothing to remove there.", "warning")
            else:
                ssh.run(f"{_q(base)}/bin/agent-ctl stop >/dev/null 2>&1")
                ssh.run(
                    f"systemctl --user disable {_q(unit)} >/dev/null 2>&1; "
                    f'rm -f "$HOME/.config/systemd/user/{unit}.service"; '
                    "systemctl --user daemon-reload >/dev/null 2>&1; "
                    f"(crontab -l 2>/dev/null | grep -v {_q('# ' + unit)}) "
                    "| crontab - 2>/dev/null; true"
                )
                ssh.check(f"rm -rf {_q(base)}", what="Removing the agent files")
                self.log(f"Agent stopped and {base} removed.", "success")
        finally:
            ssh.close()

        self.nodes.set_token(request.name, None)
        self.nodes.delete(request.name)
        self.log(f"Node '{request.name}' removed.", "success")
