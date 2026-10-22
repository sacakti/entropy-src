"""
EagleAPI collections: a project's tree of folders and saved requests.

Items are kept flat (id, parent_id, position); the web UI builds the tree.
A request's definition is JSON in `data` (see `normalize_request`).
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

KINDS = ("folder", "request")
MAX_NAME = 120
MAX_DATA_BYTES = 1024 * 1024
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")


class EagleStoreError(ValueError):
    """A refused change; the message is safe to show."""


class EagleItemNotFound(LookupError):
    pass


def ensure_schema(connection: Any) -> None:
    if getattr(connection, "_entropy_eagleapi_ready", False):
        return
    with connection.transaction():
        connection.execute("""
            CREATE TABLE IF NOT EXISTS eagleapi_items
            (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL,
                parent_id   INTEGER,
                kind        TEXT NOT NULL CHECK (kind IN ('folder', 'request')),
                name        TEXT NOT NULL,
                position    INTEGER NOT NULL DEFAULT 0,
                data        TEXT NOT NULL DEFAULT '{}',
                created_by  TEXT,
                updated_at  TEXT NOT NULL
            )
            """)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS eagleapi_items_project"
            " ON eagleapi_items (project_id, parent_id)"
        )
        # Project-wide settings: named TLS profiles and the default one.
        connection.execute("""
            CREATE TABLE IF NOT EXISTS eagleapi_settings
            (
                project_id  INTEGER PRIMARY KEY,
                data        TEXT NOT NULL DEFAULT '{}',
                updated_by  TEXT,
                updated_at  TEXT NOT NULL
            )
            """)
    connection._entropy_eagleapi_ready = True


# ----------------------------------------------------------------------
# Request definitions
# ----------------------------------------------------------------------


def _rows(value: Any) -> List[Dict[str, Any]]:
    """Key/value rows ({key, value, enabled}) from whatever the client sent."""

    rows = []
    for row in value if isinstance(value, list) else []:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "key": str(row.get("key") or ""),
                "value": str(row.get("value") or ""),
                "enabled": row.get("enabled", True) is not False,
            }
        )
    return rows


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _number(value: Any, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


TLS_MODES = ("inherit", "profile", "custom")


def normalize_tls(tls: Any) -> Dict[str, Any]:
    """TLS settings: verification, client certificate, CA bundle (vault references)."""

    tls = tls if isinstance(tls, dict) else {}
    cert_mode = _text(tls.get("client_cert") or "none")
    return {
        "verify": tls.get("verify", True) is not False,
        "client_cert": cert_mode if cert_mode in ("none", "pem", "pfx") else "none",
        "cert": _text(tls.get("cert")),
        "key": _text(tls.get("key")),
        "pfx": _text(tls.get("pfx")),
        "password": _text(tls.get("password")),
        "ca_bundle": _text(tls.get("ca_bundle")),
    }


def _tls_mode(tls: Dict[str, Any]) -> str:
    """
    How a request gets its TLS settings. Requests saved before TLS profiles
    existed keep their own settings when they had any (custom), else they
    follow the project default (inherit).
    """

    mode = _text(tls.get("mode"))
    if mode in TLS_MODES:
        return mode
    own = normalize_tls(tls)
    plain = own["verify"] and own["client_cert"] == "none" and not own["ca_bundle"]
    return "inherit" if plain else "custom"


def normalize_settings(data: Any) -> Dict[str, Any]:
    """Project settings: TLS profiles (unique ids and names) and the default profile."""

    data = data if isinstance(data, dict) else {}
    profiles: List[Dict[str, Any]] = []
    seen_ids: set = set()
    seen_names: set = set()
    raw = data.get("tls_profiles") if isinstance(data.get("tls_profiles"), list) else []
    for index, item in enumerate(raw[:100]):
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name")).strip()[:80]
        if not name:
            raise EagleStoreError("Every TLS profile needs a name.")
        if name.lower() in seen_names:
            raise EagleStoreError(f"There are two TLS profiles named '{name}'.")
        profile_id = _text(item.get("id")).strip()[:40] or f"tls-{index + 1}"
        while profile_id in seen_ids:
            profile_id += "-1"
        seen_ids.add(profile_id)
        seen_names.add(name.lower())
        profiles.append({"id": profile_id, "name": name, **normalize_tls(item)})
    default = _text(data.get("default_tls")).strip()
    return {
        "tls_profiles": profiles,
        "default_tls": default if default in seen_ids else "",
    }


def effective_tls(data: Dict[str, Any], settings: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """
    The TLS settings a request is sent with, and where they came from
    ("request", "profile <name>", "default <name>" or "none").
    """

    tls = data["tls"]
    if tls["mode"] == "custom":
        return normalize_tls(tls), "request"
    profiles = {profile["id"]: profile for profile in settings["tls_profiles"]}
    if tls["mode"] == "profile":
        profile = profiles.get(tls["profile"])
        if profile is None:
            raise EagleStoreError(
                "The request's TLS profile no longer exists; choose another in its TLS tab."
            )
        return normalize_tls(profile), f"profile {profile['name']}"
    profile = profiles.get(settings["default_tls"])
    if profile is None:
        return normalize_tls({}), "none"
    return normalize_tls(profile), f"default {profile['name']}"


def default_request() -> Dict[str, Any]:
    return normalize_request({})


def normalize_request(data: Any) -> Dict[str, Any]:
    """A complete request definition with every field present and in range."""

    data = data if isinstance(data, dict) else {}
    body = data.get("body") if isinstance(data.get("body"), dict) else {}
    auth = data.get("auth") if isinstance(data.get("auth"), dict) else {}
    tls = data.get("tls") if isinstance(data.get("tls"), dict) else {}
    options = data.get("options") if isinstance(data.get("options"), dict) else {}
    polling = data.get("polling") if isinstance(data.get("polling"), dict) else {}
    extract = polling.get("extract") if isinstance(polling.get("extract"), dict) else {}
    stop = polling.get("stop") if isinstance(polling.get("stop"), dict) else {}

    method = _text(data.get("method") or "GET").strip().upper()[:20] or "GET"
    body_mode = _text(body.get("mode") or "none")
    auth_type = _text(auth.get("type") or "none")
    source = _text(extract.get("source") or "json")
    stop_type = _text(stop.get("type") or "json")

    return {
        "method": method,
        "url": _text(data.get("url")),
        "params": _rows(data.get("params")),
        "headers": _rows(data.get("headers")),
        "body": {
            "mode": body_mode if body_mode in ("none", "json", "form", "raw") else "none",
            "json": _text(body.get("json")),
            "form": _rows(body.get("form")),
            "raw": _text(body.get("raw")),
            "content_type": _text(body.get("content_type") or "text/plain"),
        },
        "auth": {
            "type": (auth_type if auth_type in ("none", "basic", "bearer", "oauth2") else "none"),
            "username": _text(auth.get("username")),
            "password": _text(auth.get("password")),
            "token": _text(auth.get("token")),
            "token_url": _text(auth.get("token_url")),
            "client_id": _text(auth.get("client_id")),
            "client_secret": _text(auth.get("client_secret")),
            "scope": _text(auth.get("scope")),
            "client_auth": "basic" if auth.get("client_auth") == "basic" else "body",
        },
        "tls": {**normalize_tls(tls), "mode": _tls_mode(tls), "profile": _text(tls.get("profile"))},
        "options": {
            "timeout": _number(options.get("timeout"), 30, 1, 300),
            "follow_redirects": options.get("follow_redirects", True) is not False,
        },
        "polling": {
            "enabled": polling.get("enabled") is True,
            "extract": {
                "source": source if source in ("json", "header", "regex") else "json",
                "expression": _text(extract.get("expression")),
            },
            "method": _text(polling.get("method") or "GET").strip().upper()[:20] or "GET",
            "reuse_auth": polling.get("reuse_auth", True) is not False,
            "interval": _number(polling.get("interval"), 2, 0.5, 3600),
            "max_attempts": int(_number(polling.get("max_attempts"), 30, 1, 1000)),
            "stop": {
                "type": stop_type if stop_type in ("json", "status", "none") else "json",
                "path": _text(stop.get("path")),
                "values": _text(stop.get("values")),
                "status": int(_number(stop.get("status"), 202, 100, 599)),
                "on_error": stop.get("on_error", True) is not False,
            },
        },
    }


# ----------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_name(name: Any) -> str:
    cleaned = " ".join(str(name or "").split())
    if not cleaned:
        raise EagleStoreError("A name is required.")
    if len(cleaned) > MAX_NAME:
        raise EagleStoreError(f"Names can be at most {MAX_NAME} characters.")
    return cleaned


def _dump(data: Dict[str, Any]) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if len(text.encode("utf-8")) > MAX_DATA_BYTES:
        raise EagleStoreError("The request is too large to save (1 MB at most).")
    return text


class EagleStore:
    """Folders and requests of one database, always used per project."""

    def __init__(self, connection: Any) -> None:
        ensure_schema(connection)
        self.connection = connection

    # -- project settings ------------------------------------------------

    def settings(self, project_id: int) -> Dict[str, Any]:
        row = self.connection.fetchone(
            "SELECT data FROM eagleapi_settings WHERE project_id = ?", (project_id,)
        )
        try:
            data = json.loads(row["data"]) if row else {}
        except ValueError:
            data = {}
        try:
            return normalize_settings(data)
        except EagleStoreError:
            return normalize_settings({})

    def save_settings(self, project_id: int, data: Any, user: str) -> Dict[str, Any]:
        settings = normalize_settings(data)
        with self.connection.transaction():
            self.connection.execute(
                "INSERT OR REPLACE INTO eagleapi_settings"
                " (project_id, data, updated_by, updated_at) VALUES (?, ?, ?, ?)",
                (project_id, _dump(settings), user, _now()),
            )
        return settings

    def profile_users(self, project_id: int, profile_id: str) -> List[str]:
        """Names of the project's requests that use a TLS profile."""

        rows = self.connection.fetchall(
            "SELECT name, data FROM eagleapi_items WHERE project_id = ? AND kind = 'request'",
            (project_id,),
        )
        names = []
        for row in rows:
            try:
                tls = json.loads(row["data"]).get("tls") or {}
            except (ValueError, AttributeError):
                continue
            if tls.get("mode") == "profile" and tls.get("profile") == profile_id:
                names.append(row["name"])
        return names

    # -- reading -------------------------------------------------------

    def _row(self, project_id: int, item_id: int) -> Any:
        row = self.connection.fetchone(
            "SELECT * FROM eagleapi_items WHERE id = ? AND project_id = ?",
            (item_id, project_id),
        )
        if row is None:
            raise EagleItemNotFound(f"Item {item_id} not found in this project.")
        return row

    @staticmethod
    def _summary(row: Any) -> Dict[str, Any]:
        item = {
            "id": int(row["id"]),
            "parent_id": int(row["parent_id"]) if row["parent_id"] is not None else None,
            "kind": row["kind"],
            "name": row["name"],
            "position": int(row["position"]),
            "created_by": row["created_by"],
            "updated_at": row["updated_at"],
        }
        if row["kind"] == "request":
            try:
                data = json.loads(row["data"] or "{}")
            except ValueError:
                data = {}
            item["method"] = str(data.get("method") or "GET")
        return item

    def list(self, project_id: int) -> List[Dict[str, Any]]:
        rows = self.connection.fetchall(
            "SELECT * FROM eagleapi_items WHERE project_id = ?"
            " ORDER BY position, lower(name), id",
            (project_id,),
        )
        return [self._summary(row) for row in rows]

    def get(self, project_id: int, item_id: int) -> Dict[str, Any]:
        row = self._row(project_id, item_id)
        item = self._summary(row)
        if row["kind"] == "request":
            try:
                item["data"] = normalize_request(json.loads(row["data"] or "{}"))
            except ValueError:
                item["data"] = default_request()
        return item

    def _children(self, project_id: int, parent_id: Optional[int]) -> List[Any]:
        if parent_id is None:
            return self.connection.fetchall(
                "SELECT * FROM eagleapi_items WHERE project_id = ? AND parent_id IS NULL"
                " ORDER BY position, lower(name), id",
                (project_id,),
            )
        return self.connection.fetchall(
            "SELECT * FROM eagleapi_items WHERE project_id = ? AND parent_id = ?"
            " ORDER BY position, lower(name), id",
            (project_id, parent_id),
        )

    def _descendants(self, project_id: int, item_id: int) -> List[int]:
        found: List[int] = []
        pending = [item_id]
        while pending:
            current = pending.pop()
            for child in self._children(project_id, current):
                found.append(int(child["id"]))
                pending.append(int(child["id"]))
        return found

    def _check_parent(self, project_id: int, parent_id: Optional[int]) -> None:
        if parent_id is None:
            return
        try:
            parent = self._row(project_id, parent_id)
        except EagleItemNotFound:
            raise EagleStoreError("The target folder does not exist.") from None
        if parent["kind"] != "folder":
            raise EagleStoreError("Items can only be placed in folders.")

    # -- changes -------------------------------------------------------

    def create(
        self,
        project_id: int,
        *,
        kind: str,
        name: Any,
        parent_id: Optional[int] = None,
        data: Any = None,
        user: str = "",
    ) -> Dict[str, Any]:
        if kind not in KINDS:
            raise EagleStoreError("Kind must be 'folder' or 'request'.")
        cleaned = _clean_name(name)
        self._check_parent(project_id, parent_id)
        payload = _dump(normalize_request(data)) if kind == "request" else "{}"
        with self.connection.transaction():
            position = len(self._children(project_id, parent_id))
            cursor = self.connection.execute(
                "INSERT INTO eagleapi_items (project_id, parent_id, kind, name, position,"
                " data, created_by, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (project_id, parent_id, kind, cleaned, position, payload, user, _now()),
            )
            item_id = int(cursor.lastrowid)
        return self.get(project_id, item_id)

    def update(
        self,
        project_id: int,
        item_id: int,
        *,
        name: Any = None,
        data: Any = None,
    ) -> Dict[str, Any]:
        row = self._row(project_id, item_id)
        fields: Dict[str, Any] = {}
        if name is not None:
            fields["name"] = _clean_name(name)
        if data is not None:
            if row["kind"] != "request":
                raise EagleStoreError("Only requests have a definition.")
            fields["data"] = _dump(normalize_request(data))
        if fields:
            fields["updated_at"] = _now()
            assignments = ", ".join(f"{column} = ?" for column in fields)
            with self.connection.transaction():
                self.connection.execute(
                    f"UPDATE eagleapi_items SET {assignments} WHERE id = ? AND project_id = ?",
                    (*fields.values(), item_id, project_id),
                )
        return self.get(project_id, item_id)

    def move(
        self,
        project_id: int,
        item_id: int,
        *,
        parent_id: Optional[int],
        position: Optional[int] = None,
    ) -> Dict[str, Any]:
        self._row(project_id, item_id)
        if parent_id is not None and (
            parent_id == item_id or parent_id in self._descendants(project_id, item_id)
        ):
            raise EagleStoreError("A folder cannot be moved into itself.")
        self._check_parent(project_id, parent_id)

        siblings = [
            int(row["id"])
            for row in self._children(project_id, parent_id)
            if int(row["id"]) != item_id
        ]
        index = len(siblings) if position is None else max(0, min(int(position), len(siblings)))
        siblings.insert(index, item_id)
        with self.connection.transaction():
            for number, sibling in enumerate(siblings):
                self.connection.execute(
                    "UPDATE eagleapi_items SET parent_id = ?, position = ?"
                    " WHERE id = ? AND project_id = ?",
                    (parent_id, number, sibling, project_id),
                )
        return self.get(project_id, item_id)

    def duplicate(self, project_id: int, item_id: int, user: str = "") -> Dict[str, Any]:
        """A copy next to the original ("<name> copy"); folders with their content."""

        row = self._row(project_id, item_id)
        parent_id = int(row["parent_id"]) if row["parent_id"] is not None else None
        copy_id = self._copy(project_id, row, parent_id, f"{row['name']} copy"[:MAX_NAME], user)
        # Right after the original.
        return self.move(
            project_id, copy_id, parent_id=parent_id, position=int(row["position"]) + 1
        )

    def _copy(self, project_id: int, row: Any, parent_id: Optional[int], name: str, user: str):
        data = json.loads(row["data"] or "{}") if row["kind"] == "request" else None
        created = self.create(
            project_id,
            kind=row["kind"],
            name=name,
            parent_id=parent_id,
            data=copy.deepcopy(data),
            user=user,
        )
        if row["kind"] == "folder":
            for child in self._children(project_id, int(row["id"])):
                self._copy(project_id, child, created["id"], child["name"], user)
        return created["id"]

    def delete(self, project_id: int, item_id: int) -> int:
        """Delete an item (a folder with everything in it); returns how many went."""

        self._row(project_id, item_id)
        doomed = [item_id, *self._descendants(project_id, item_id)]
        with self.connection.transaction():
            for doomed_id in doomed:
                self.connection.execute(
                    "DELETE FROM eagleapi_items WHERE id = ? AND project_id = ?",
                    (doomed_id, project_id),
                )
        return len(doomed)

    def delete_project(self, project_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "DELETE FROM eagleapi_items WHERE project_id = ?", (project_id,)
            )
