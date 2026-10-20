"""
Start, stop and inspect the Entropy web server.

When the installer registered a systemd user service, it is used, so the
server starts at boot and restarts on failure. Otherwise the server runs
as a detached background process tracked by a pid file.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from . import install

SERVICE_NAME = "entropy-web"


def service_file() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{SERVICE_NAME}.service"


def _pid_file() -> Path:
    return install.entropy_home() / "run" / "web.pid"


def log_file() -> Path:
    return install.entropy_home() / "logs" / "web.log"


def _systemd() -> bool:
    """The systemd user service is installed and usable."""

    if not service_file().exists() or shutil.which("systemctl") is None:
        return False
    result = subprocess.run(
        ["systemctl", "--user", "show-environment"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _pid() -> Optional[int]:
    try:
        pid = int(_pid_file().read_text().strip())
    except (OSError, ValueError):
        return None
    return pid if _alive(pid) else None


def url(record: Optional[Dict[str, Any]] = None) -> str:
    web = (record or install.load())["web"]
    host = web["host"]
    shown = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    return f"http://{shown}:{web['port']}"


def healthy(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{url()}/api/health", timeout=timeout) as response:
            return response.status == 200
    except OSError:
        return False


def status() -> Dict[str, Any]:
    record = install.load()
    if _systemd():
        result = subprocess.run(
            ["systemctl", "--user", "is-active", SERVICE_NAME],
            capture_output=True,
            text=True,
            check=False,
        )
        running = result.stdout.strip() == "active"
        pid = None
        supervisor = "systemd"
    else:
        pid = _pid()
        running = pid is not None
        supervisor = "process"
    return {
        "running": running,
        "healthy": healthy() if running else False,
        "pid": pid,
        "supervisor": supervisor,
        "url": url(record),
        "log": str(log_file()),
    }


def environment(record: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    record = record or install.load()
    variables = dict(os.environ)
    variables["ENTROPY_WEB_HOST"] = str(record["web"]["host"])
    variables["ENTROPY_WEB_PORT"] = str(record["web"]["port"])
    variables["PYTHONUNBUFFERED"] = "1"
    return variables


def start(wait: float = 30.0) -> Dict[str, Any]:
    record = install.load()

    if _systemd():
        subprocess.run(["systemctl", "--user", "start", SERVICE_NAME], check=True)
    elif _pid() is None:
        log = log_file()
        log.parent.mkdir(parents=True, exist_ok=True)
        _pid_file().parent.mkdir(parents=True, exist_ok=True)
        options: Dict[str, Any] = {}
        if os.name == "nt":
            options["creationflags"] = 0x00000008 | 0x00000200  # DETACHED | NEW_GROUP
        else:
            options["start_new_session"] = True
        with log.open("ab") as handle:
            process = subprocess.Popen(
                [record["python"], "-m", "core.web"],
                cwd=record["application"],
                env=environment(record),
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=subprocess.STDOUT,
                **options,
            )
        _pid_file().write_text(str(process.pid))

    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if healthy(1.0):
            break
        time.sleep(0.5)
    return status()


def stop(wait: float = 20.0) -> Dict[str, Any]:
    if _systemd():
        subprocess.run(["systemctl", "--user", "stop", SERVICE_NAME], check=False)
        return status()

    pid = _pid()
    if pid is not None:
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + wait
        while _alive(pid) and time.monotonic() < deadline:
            time.sleep(0.25)
        if _alive(pid) and hasattr(signal, "SIGKILL"):
            os.kill(pid, signal.SIGKILL)
    _pid_file().unlink(missing_ok=True)
    return status()


def restart() -> Dict[str, Any]:
    if _systemd():
        subprocess.run(["systemctl", "--user", "restart", SERVICE_NAME], check=False)
        return start()
    stop()
    return start()


def reexec_current_server(delay: float = 1.0) -> None:
    """
    Replace the running web server process with a fresh one, e.g. after an
    upgrade swapped the application. Same pid, so systemd, the pid file and
    foreground terminals keep tracking it.
    """

    record = install.load()

    def run() -> None:
        time.sleep(delay)
        os.chdir(record["application"])
        python = record["python"] if Path(record["python"]).exists() else sys.executable
        os.execve(python, [python, "-m", "core.web"], environment(record))

    import threading

    threading.Thread(target=run, name="entropy-restart", daemon=True).start()


def unit(record: Dict[str, Any]) -> str:
    """The systemd user unit for the web server."""

    return (
        "[Unit]\n"
        "Description=Entropy web server\n"
        "After=network-online.target\n\n"
        "[Service]\n"
        f"WorkingDirectory={record['application']}\n"
        f"Environment=ENTROPY_WEB_HOST={record['web']['host']}\n"
        f"Environment=ENTROPY_WEB_PORT={record['web']['port']}\n"
        "Environment=PYTHONUNBUFFERED=1\n"
        f"ExecStart={record['python']} -m core.web\n"
        "Restart=on-failure\n"
        "RestartSec=5\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )
