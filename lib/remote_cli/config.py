"""
Saved servers ("contexts") and their tokens: ~/.entropy-cli/config.json,
or the file named by ENT_CONFIG. Readable by its owner only.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlsplit


class ConfigError(Exception):
    """A user-facing configuration problem."""


def config_path() -> Path:
    configured = os.environ.get("ENT_CONFIG")
    return (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".entropy-cli" / "config.json"
    )


def context_name(server: str) -> str:
    """A short default name for a server: its host and port."""

    parts = urlsplit(server)
    return parts.netloc or server


def normalize_server(server: str) -> str:
    server = server.strip().rstrip("/")
    if not server:
        raise ConfigError("Give the server URL, e.g. https://entropy.example.com")
    if "://" not in server:
        server = "https://" + server
    parts = urlsplit(server)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ConfigError(f"'{server}' is not an http(s) URL.")
    return server


class Config:
    """The contexts file: {"current": name, "contexts": {name: {...}}}."""

    def __init__(self, data: Optional[Dict[str, Any]] = None, path: Optional[Path] = None) -> None:
        self.path = path or config_path()
        self.data = data or {"current": None, "contexts": {}}
        self.data.setdefault("contexts", {})

    @classmethod
    def load(cls) -> Config:
        path = config_path()
        if not path.exists():
            return cls(path=path)
        try:
            return cls(json.loads(path.read_text(encoding="utf-8")), path)
        except ValueError as exc:
            raise ConfigError(f"{path} is not valid JSON: {exc}") from exc

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(self.path.parent, stat.S_IRWXU)
        temporary = self.path.with_suffix(".tmp")
        # Created private: it holds tokens.
        descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(self.data, handle, indent=2)
            handle.write("\n")
        temporary.replace(self.path)

    # -- contexts -----------------------------------------------------

    @property
    def contexts(self) -> Dict[str, Dict[str, Any]]:
        return self.data["contexts"]

    @property
    def current_name(self) -> Optional[str]:
        return self.data.get("current")

    def current(self, name: Optional[str] = None) -> Dict[str, Any]:
        """The context to use: --context NAME, ENT_CONTEXT, or the current one."""

        chosen = name or os.environ.get("ENT_CONTEXT") or self.current_name
        if not chosen:
            raise ConfigError("Not logged in to any server. Run: ent login <server-url>")
        if chosen not in self.contexts:
            raise ConfigError(f"No context named '{chosen}'. See: ent context list")
        context = dict(self.contexts[chosen])
        context["name"] = chosen
        return context

    def upsert(self, name: str, values: Dict[str, Any], make_current: bool = True) -> None:
        self.contexts.setdefault(name, {}).update(values)
        if make_current:
            self.data["current"] = name

    def find_server(self, server: str) -> Optional[str]:
        for name, context in self.contexts.items():
            if context.get("server") == server:
                return name
        return None
