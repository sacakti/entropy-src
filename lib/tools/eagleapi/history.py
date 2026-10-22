"""
Sent requests, per person and project: what was sent (secrets already
masked by the client) and what came back. Each person sees and purges only
their own history; the oldest entries go beyond `KEEP` per person.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

KEEP = 500
# Response bodies are kept up to this size; the rest is cut.
MAX_BODY = 512 * 1024


def ensure_schema(connection: Any) -> None:
    if getattr(connection, "_entropy_eagleapi_history_ready", False):
        return
    with connection.transaction():
        connection.execute("""
            CREATE TABLE IF NOT EXISTS eagleapi_history
            (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                item_id     INTEGER,
                item_name   TEXT,
                environment TEXT,
                method      TEXT NOT NULL,
                url         TEXT NOT NULL,
                status      INTEGER,
                error       TEXT,
                elapsed_ms  INTEGER,
                poll        INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL,
                data        TEXT NOT NULL
            )
            """)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS eagleapi_history_owner"
            " ON eagleapi_history (project_id, user_id, id)"
        )
    connection._entropy_eagleapi_history_ready = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trim(result: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(result)
    body = result.get("body")
    if isinstance(body, str) and len(body) > MAX_BODY:
        result["body"] = body[:MAX_BODY]
        result["history_truncated"] = True
    return result


def _summary(row: Any) -> Dict[str, Any]:
    return {
        "id": int(row["id"]),
        "item_id": int(row["item_id"]) if row["item_id"] is not None else None,
        "item_name": row["item_name"],
        "environment": row["environment"],
        "method": row["method"],
        "url": row["url"],
        "status": row["status"],
        "error": row["error"],
        "elapsed_ms": row["elapsed_ms"],
        "poll": bool(row["poll"]),
        "created_at": row["created_at"],
    }


class EagleHistory:
    def __init__(self, connection: Any) -> None:
        ensure_schema(connection)
        self.connection = connection

    def add(
        self,
        project_id: int,
        user_id: int,
        *,
        definition: Dict[str, Any],
        result: Dict[str, Any],
        item_id: Optional[int],
        item_name: Optional[str],
        environment: Optional[str],
        poll: bool,
    ) -> int:
        sent = result.get("request") or {}
        payload = json.dumps(
            {"definition": definition, "result": _trim(result)}, ensure_ascii=False
        )
        with self.connection.transaction():
            cursor = self.connection.execute(
                "INSERT INTO eagleapi_history (project_id, user_id, item_id, item_name,"
                " environment, method, url, status, error, elapsed_ms, poll, created_at, data)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    user_id,
                    item_id,
                    item_name,
                    environment,
                    str(sent.get("method") or definition.get("method") or "GET"),
                    str(sent.get("url") or definition.get("url") or ""),
                    result.get("status"),
                    result.get("error"),
                    int(result.get("elapsed_ms") or 0),
                    1 if poll else 0,
                    _now(),
                    payload,
                ),
            )
            entry_id = int(cursor.lastrowid)
            # Keep the newest KEEP entries of this person in this project.
            self.connection.execute(
                "DELETE FROM eagleapi_history WHERE project_id = ? AND user_id = ? AND id <= ("
                " SELECT id FROM eagleapi_history WHERE project_id = ? AND user_id = ?"
                " ORDER BY id DESC LIMIT 1 OFFSET ?)",
                (project_id, user_id, project_id, user_id, KEEP),
            )
        return entry_id

    def list(
        self, project_id: int, user_id: int, *, limit: int = 100, offset: int = 0, query: str = ""
    ) -> Dict[str, Any]:
        where = "project_id = ? AND user_id = ?"
        args: List[Any] = [project_id, user_id]
        if query:
            where += " AND (url LIKE ? OR item_name LIKE ? OR method LIKE ?)"
            like = f"%{query}%"
            args += [like, like, like]
        total = self.connection.fetchone(
            f"SELECT COUNT(*) AS n FROM eagleapi_history WHERE {where}", tuple(args)
        )["n"]
        rows = self.connection.fetchall(
            f"SELECT * FROM eagleapi_history WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            (*args, limit, offset),
        )
        return {"entries": [_summary(row) for row in rows], "total": int(total)}

    def get(self, project_id: int, user_id: int, entry_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone(
            "SELECT * FROM eagleapi_history WHERE id = ? AND project_id = ? AND user_id = ?",
            (entry_id, project_id, user_id),
        )
        if row is None:
            return None
        try:
            data = json.loads(row["data"])
        except ValueError:
            data = {}
        return {**_summary(row), "definition": data.get("definition"), "result": data.get("result")}

    def entries(
        self, project_id: int, user_id: int, ids: Optional[Iterable[int]] = None
    ) -> List[Dict[str, Any]]:
        """Full entries, newest first (all of them, or the given ids)."""

        rows = self.connection.fetchall(
            "SELECT id FROM eagleapi_history WHERE project_id = ? AND user_id = ? ORDER BY id DESC",
            (project_id, user_id),
        )
        wanted = None if ids is None else {int(i) for i in ids}
        found = []
        for row in rows:
            if wanted is None or int(row["id"]) in wanted:
                entry = self.get(project_id, user_id, int(row["id"]))
                if entry:
                    found.append(entry)
        return found

    def purge(self, project_id: int, user_id: int, ids: Optional[Iterable[int]] = None) -> int:
        with self.connection.transaction():
            if ids is None:
                cursor = self.connection.execute(
                    "DELETE FROM eagleapi_history WHERE project_id = ? AND user_id = ?",
                    (project_id, user_id),
                )
                return int(cursor.rowcount or 0)
            count = 0
            for entry_id in ids:
                cursor = self.connection.execute(
                    "DELETE FROM eagleapi_history WHERE id = ? AND project_id = ? AND user_id = ?",
                    (int(entry_id), project_id, user_id),
                )
                count += int(cursor.rowcount or 0)
            return count

    def delete_project(self, project_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "DELETE FROM eagleapi_history WHERE project_id = ?", (project_id,)
            )


def har(entries: List[Dict[str, Any]], creator_version: str = "") -> Dict[str, Any]:
    """History as HAR 1.2 (opens in browsers' dev tools, Postman, Insomnia, Charles…)."""

    from urllib.parse import parse_qsl, urlsplit

    items = []
    for entry in reversed(entries):
        result = entry.get("result") or {}
        sent = result.get("request") or {}
        definition = entry.get("definition") or {}
        url = str(sent.get("url") or entry.get("url") or "")
        headers = [{"name": str(k), "value": str(v)} for k, v in sent.get("headers") or []]
        request: Dict[str, Any] = {
            "method": entry.get("method") or "GET",
            "url": url,
            "httpVersion": "HTTP/1.1",
            "headers": headers,
            "queryString": [
                {"name": k, "value": v}
                for k, v in parse_qsl(urlsplit(url).query, keep_blank_values=True)
            ],
            "cookies": [],
            "headersSize": -1,
            "bodySize": -1,
        }
        body = definition.get("body") or {}
        if body.get("mode") == "json":
            request["postData"] = {"mimeType": "application/json", "text": body.get("json") or ""}
        elif body.get("mode") == "raw":
            request["postData"] = {
                "mimeType": body.get("content_type") or "text/plain",
                "text": body.get("raw") or "",
            }
        elif body.get("mode") == "form":
            request["postData"] = {
                "mimeType": "application/x-www-form-urlencoded",
                "params": [
                    {"name": row.get("key", ""), "value": row.get("value", "")}
                    for row in body.get("form") or []
                    if row.get("enabled", True)
                ],
            }
        response_headers = [
            {"name": str(k), "value": str(v)} for k, v in result.get("headers") or []
        ]
        content_type = next(
            (h["value"] for h in response_headers if h["name"].lower() == "content-type"), ""
        )
        content: Dict[str, Any] = {
            "size": int(result.get("size") or 0),
            "mimeType": content_type,
            "text": result.get("body") or "",
        }
        if result.get("is_base64"):
            content["encoding"] = "base64"
        items.append(
            {
                "startedDateTime": entry.get("created_at"),
                "time": int(entry.get("elapsed_ms") or 0),
                "request": request,
                "response": {
                    "status": int(result.get("status") or 0),
                    "statusText": result.get("reason") or result.get("error") or "",
                    "httpVersion": "HTTP/1.1",
                    "headers": response_headers,
                    "cookies": [],
                    "content": content,
                    "redirectURL": "",
                    "headersSize": -1,
                    "bodySize": int(result.get("size") or -1),
                },
                "cache": {},
                "timings": {"send": 0, "wait": int(entry.get("elapsed_ms") or 0), "receive": 0},
                "comment": entry.get("item_name") or "",
            }
        )
    return {
        "log": {
            "version": "1.2",
            "creator": {"name": "Entropy EagleAPI", "version": creator_version or "1"},
            "entries": items,
        }
    }
