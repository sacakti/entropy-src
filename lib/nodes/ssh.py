"""
SSH access to a server through the system OpenSSH client.

Credentials are held in memory for the life of one session only: a
password or key passphrase reaches `ssh` through a private askpass
helper, and a private key is written to a mode-0600 file in a private
temporary directory that is removed when the session closes. One
multiplexed connection (ControlMaster) serves every command, so a
password is asked for once.

Host keys are trusted on first use and pinned in Entropy's own
known_hosts file; a changed key fails the connection.
"""

from __future__ import annotations

import contextlib
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

SECRET_ENV = "ENTROPY_SSH_SECRET"

ASKPASS = """#!/bin/sh
printf '%s\\n' "$ENTROPY_SSH_SECRET"
"""


class SSHError(Exception):
    """SSH failed; the message is safe to show (no secrets)."""


def _explain(stderr: str) -> str:
    text = stderr.strip()
    lowered = text.lower()

    if "remote host identification has changed" in lowered:
        return (
            "The server's host key changed since Entropy last connected. If the server was "
            "rebuilt, choose 'Forget the saved host key' and try again; otherwise the "
            "connection may be intercepted."
        )
    if "permission denied" in lowered:
        return "Authentication failed: the server rejected the username, password or key."
    if "connection refused" in lowered:
        return "Connection refused: no SSH server is listening on that host and port."
    if "timed out" in lowered or "timeout" in lowered:
        return "The connection timed out. Check the host, port and firewall."
    if "could not resolve hostname" in lowered:
        return "The host name could not be resolved."
    if "no route to host" in lowered or "network is unreachable" in lowered:
        return "The host is unreachable from the Entropy server."

    # Last meaningful line, without any echo of the command.
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1][:300] if lines else "SSH failed."


class SSHSession:
    """A short-lived, multiplexed SSH connection to one server."""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        *,
        known_hosts: Path,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
        passphrase: Optional[str] = None,
        connect_timeout: int = 15,
    ) -> None:
        if shutil.which("ssh") is None:
            raise SSHError("The OpenSSH client (ssh) is not installed on the Entropy server.")

        if not re.match(r"^[A-Za-z0-9._-]+$", user or ""):
            raise SSHError("Invalid SSH username.")
        if not re.match(r"^[A-Za-z0-9.:_-]+$", host or ""):
            raise SSHError("Invalid host name.")

        self.host = host
        self.port = int(port)
        self.user = user
        self._known_hosts = known_hosts
        self._password = password
        self._private_key = private_key
        self._passphrase = passphrase
        self._connect_timeout = connect_timeout
        self._directory: Optional[str] = None
        self._options: list = []
        self._environment: dict = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __enter__(self) -> SSHSession:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def open(self) -> None:
        self._directory = tempfile.mkdtemp(prefix="entropy-ssh-")
        os.chmod(self._directory, 0o700)
        directory = Path(self._directory)

        self._known_hosts.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self._known_hosts.parent, 0o700)

        options = [
            "-p",
            str(self.port),
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={self._known_hosts}",
            "-o",
            "GlobalKnownHostsFile=/dev/null",
            "-o",
            f"ConnectTimeout={self._connect_timeout}",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=4",
            "-o",
            "ControlMaster=auto",
            "-o",
            f"ControlPath={directory / 'control'}",
            "-o",
            "ControlPersist=300",
            "-o",
            "LogLevel=ERROR",
        ]

        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in ("SSH_AUTH_SOCK",) or not (self._password or self._private_key)
        }
        secret = None

        if self._private_key:
            key_file = directory / "key"
            descriptor = os.open(str(key_file), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as handle:
                key = self._private_key.replace("\r\n", "\n").strip() + "\n"
                handle.write(key)
            options += [
                "-i",
                str(key_file),
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "PreferredAuthentications=publickey",
            ]
            secret = self._passphrase
        elif self._password:
            options += [
                "-o",
                "PreferredAuthentications=password,keyboard-interactive",
                "-o",
                "PubkeyAuthentication=no",
                "-o",
                "NumberOfPasswordPrompts=1",
            ]
            secret = self._password
        else:
            # The Entropy server's own keys (ssh-agent or ~/.ssh).
            options += ["-o", "BatchMode=yes"]

        if secret is not None:
            askpass = directory / "askpass"
            askpass.write_text(ASKPASS, encoding="utf-8")
            os.chmod(askpass, 0o700)
            environment.update(
                {
                    "SSH_ASKPASS": str(askpass),
                    "SSH_ASKPASS_REQUIRE": "force",
                    # OpenSSH before 8.4 uses askpass only with a display.
                    "DISPLAY": environment.get("DISPLAY") or ":0",
                    SECRET_ENV: secret,
                }
            )
        else:
            options += ["-o", "BatchMode=yes"] if "BatchMode=yes" not in options else []

        self._options = options
        self._environment = environment

        rc, _, err = self._ssh(["true"], timeout=self._connect_timeout + 20)
        if rc != 0:
            self.close()
            raise SSHError(_explain(err))

        # The secret is no longer needed once the master connection is up.
        self._environment.pop(SECRET_ENV, None)
        self._password = None
        self._passphrase = None

    def close(self) -> None:
        if self._directory is None:
            return
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                ["ssh", *self._options, "-O", "exit", self._target()],
                env=self._environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        shutil.rmtree(self._directory, ignore_errors=True)
        self._directory = None
        self._private_key = None

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _target(self) -> str:
        return f"{self.user}@{self.host}"

    def _ssh(
        self,
        command: list,
        *,
        stdin: Optional[object] = None,
        timeout: float = 120,
    ) -> Tuple[int, str, str]:
        try:
            process = subprocess.run(
                ["ssh", *self._options, self._target(), "--", *command],
                env=self._environment,
                stdin=stdin if stdin is not None else subprocess.DEVNULL,
                capture_output=True,
                timeout=timeout,
                check=False,
                # No controlling terminal: ssh must use askpass, never prompt.
                start_new_session=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise SSHError(f"The command did not finish within {int(timeout)} seconds.") from exc

        return (
            process.returncode,
            process.stdout.decode("utf-8", errors="replace"),
            process.stderr.decode("utf-8", errors="replace"),
        )

    def run(self, script: str, *, timeout: float = 120) -> Tuple[int, str, str]:
        """Run a POSIX shell script on the server."""

        return self._ssh(["sh", "-c", shlex.quote(script)], timeout=timeout)

    def check(self, script: str, *, timeout: float = 120, what: str = "command") -> str:
        """Run a script and return its output, raising on failure."""

        rc, out, err = self.run(script, timeout=timeout)
        if rc != 0:
            detail = (err.strip() or out.strip()).splitlines()
            raise SSHError(f"{what} failed: {detail[-1][:300] if detail else f'exit code {rc}'}")
        return out

    def upload(
        self, source: Path, destination: str, *, mode: str = "644", timeout: float = 600
    ) -> None:
        """Copy a local file to an absolute path on the server."""

        script = (
            f"umask 077 && cat > {shlex.quote(destination)}.part && "
            f"chmod {mode} {shlex.quote(destination)}.part && "
            f"mv -f {shlex.quote(destination)}.part {shlex.quote(destination)}"
        )
        with source.open("rb") as handle:
            rc, _, err = self._ssh(["sh", "-c", shlex.quote(script)], stdin=handle, timeout=timeout)
        if rc != 0:
            raise SSHError(f"Upload of {source.name} failed: {_explain(err)}")

    def write(self, content: str, destination: str, *, mode: str = "600") -> None:
        """Write text to a file on the server without it touching local disk."""

        with tempfile.TemporaryFile() as handle:
            handle.write(content.encode("utf-8"))
            handle.seek(0)
            script = (
                f"umask 077 && cat > {shlex.quote(destination)} && "
                f"chmod {mode} {shlex.quote(destination)}"
            )
            rc, _, err = self._ssh(["sh", "-c", shlex.quote(script)], stdin=handle, timeout=60)
        if rc != 0:
            raise SSHError(f"Writing {destination} failed: {_explain(err)}")

    def host_key_fingerprint(self) -> Optional[str]:
        """SHA256 fingerprint of the pinned host key, if recorded."""

        if shutil.which("ssh-keygen") is None:
            return None
        name = self.host if self.port == 22 else f"[{self.host}]:{self.port}"
        try:
            process = subprocess.run(
                ["ssh-keygen", "-l", "-F", name, "-f", str(self._known_hosts)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        for line in process.stdout.decode("utf-8", "replace").splitlines():
            # "<host> <type> SHA256:<hash>"
            match = re.search(r"(\S+)\s+(SHA256:\S+)", line)
            if match and not line.startswith("#"):
                return f"{match.group(1)} {match.group(2)}"
        return None


def forget_host_key(known_hosts: Path, host: str, port: int) -> None:
    """Remove a pinned host key, e.g. after the server was rebuilt."""

    if not known_hosts.exists() or shutil.which("ssh-keygen") is None:
        return
    name = host if int(port) == 22 else f"[{host}]:{port}"
    subprocess.run(
        ["ssh-keygen", "-R", name, "-f", str(known_hosts)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=False,
    )
