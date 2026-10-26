"""
Questions a running plugin asks its user (interactive runs).

A plugin in an interactive run asks with `self.ask(...)`. The worker
records the question here and waits; the run screen shows it and posts
the answer. Secret answers are stored encrypted with the vault key and
deleted as soon as the plugin has read them.
"""

from __future__ import annotations

import base64
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from lib.database.connection import DatabaseConnection

# Set in a run's environment: "interactive" lets plugins ask for input.
RUN_MODE_ENV = "ENTROPY_RUN_MODE"
MODES = ("automated", "interactive")
# How long a plugin waits for an answer before the step fails.
ANSWER_TIMEOUT = 60 * 60

SCHEMA = """
CREATE TABLE IF NOT EXISTS run_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    step TEXT,
    name TEXT NOT NULL,
    label TEXT NOT NULL,
    description TEXT,
    secret INTEGER NOT NULL DEFAULT 0,
    default_value TEXT,
    choices TEXT,
    state TEXT NOT NULL DEFAULT 'waiting'
        CHECK(state IN ('waiting', 'answered', 'consumed', 'expired')),
    answer TEXT,
    answered_by TEXT,
    created_at TEXT NOT NULL,
    answered_at TEXT
)
"""


class PromptError(RuntimeError):
    """A question that cannot be asked or answered; the message says why."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_schema(connection: DatabaseConnection) -> None:
    connection.execute(SCHEMA)
    connection.execute("CREATE INDEX IF NOT EXISTS run_prompts_job ON run_prompts(job_id, state)")


def _public(row: Any) -> Dict[str, Any]:
    import json

    return {
        "id": row["id"],
        "step": row["step"],
        "name": row["name"],
        "label": row["label"],
        "description": row["description"] or "",
        "secret": bool(row["secret"]),
        # A secret's default is never shown.
        "default": None if row["secret"] else row["default_value"],
        "choices": json.loads(row["choices"]) if row["choices"] else None,
        "state": row["state"],
        "answered_by": row["answered_by"],
        "created_at": row["created_at"],
        "answered_at": row["answered_at"],
    }


class PromptStore:
    """Questions and answers of interactive runs."""

    def __init__(self, connection: DatabaseConnection, key: Optional[bytes] = None) -> None:
        ensure_schema(connection)
        self.connection = connection
        self._key = key

    # -- secrets --------------------------------------------------------

    def _cipher(self):
        if self._key is None:
            raise PromptError("The vault key is unavailable, so secret answers cannot be kept.")
        from lib.vault.cipher import VaultCipher

        return VaultCipher(self._key)

    def _seal(self, value: str) -> str:
        return base64.b64encode(self._cipher().encrypt(value.encode("utf-8"))).decode("ascii")

    def _open(self, value: str) -> str:
        return self._cipher().decrypt(base64.b64decode(value)).decode("utf-8")

    # -- worker side ----------------------------------------------------

    def ask(
        self,
        job_id: int,
        *,
        name: str,
        label: str,
        step: Optional[str] = None,
        description: str = "",
        secret: bool = False,
        default: Optional[str] = None,
        choices: Optional[Sequence[str]] = None,
    ) -> int:
        import json

        with self.connection.transaction():
            cursor = self.connection.execute(
                """
                INSERT INTO run_prompts
                (job_id, step, name, label, description, secret, default_value,
                 choices, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    step,
                    name,
                    label,
                    description,
                    int(secret),
                    default,
                    json.dumps(list(choices)) if choices else None,
                    _now(),
                ),
            )
        return int(cursor.lastrowid)

    def wait(
        self,
        prompt_id: int,
        *,
        timeout: float = ANSWER_TIMEOUT,
        poll: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> str:
        """The answer, once given; it is then deleted from the store."""

        deadline = time.monotonic() + timeout
        while True:
            row = self.connection.fetchone(
                "SELECT state, answer, secret FROM run_prompts WHERE id = ?", (prompt_id,)
            )
            if row is None:
                raise PromptError("The question was withdrawn.")
            if row["state"] == "answered":
                answer = self._open(row["answer"]) if row["secret"] else row["answer"]
                with self.connection.transaction():
                    self.connection.execute(
                        "UPDATE run_prompts SET state = 'consumed', answer = NULL WHERE id = ?",
                        (prompt_id,),
                    )
                return answer or ""
            if row["state"] == "expired":
                raise PromptError("The question was withdrawn.")
            if time.monotonic() >= deadline:
                self.expire_one(prompt_id)
                minutes = int(timeout // 60)
                raise PromptError(
                    f"No answer within {minutes} minute{'s' if minutes != 1 else ''}."
                )
            sleep(poll)

    def expire_one(self, prompt_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE run_prompts SET state = 'expired', answer = NULL "
                "WHERE id = ? AND state IN ('waiting', 'answered')",
                (prompt_id,),
            )

    # -- server side ----------------------------------------------------

    def list(self, job_ids: Sequence[int], waiting_only: bool = False) -> List[Dict[str, Any]]:
        if not job_ids:
            return []
        marks = ", ".join("?" for _ in job_ids)
        query = f"SELECT * FROM run_prompts WHERE job_id IN ({marks})"
        if waiting_only:
            query += " AND state = 'waiting'"
        rows = self.connection.fetchall(query + " ORDER BY id", tuple(job_ids))
        return [_public(row) for row in rows]

    def get(self, prompt_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone("SELECT * FROM run_prompts WHERE id = ?", (prompt_id,))
        return None if row is None else {**_public(row), "job_id": row["job_id"]}

    def answer(self, prompt_id: int, value: str, user: str) -> Dict[str, Any]:
        row = self.connection.fetchone(
            "SELECT state, secret, choices FROM run_prompts WHERE id = ?", (prompt_id,)
        )
        if row is None:
            raise PromptError("The question does not exist.")
        if row["state"] != "waiting":
            raise PromptError("The question was already answered or withdrawn.")
        if row["choices"]:
            import json

            if value not in json.loads(row["choices"]):
                raise PromptError("Choose one of the offered answers.")
        stored = self._seal(value) if row["secret"] else value
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE run_prompts SET state = 'answered', answer = ?, answered_by = ?, "
                "answered_at = ? WHERE id = ? AND state = 'waiting'",
                (stored, user, _now(), prompt_id),
            )
        return self.get(prompt_id) or {}

    def expire(self, job_ids: Sequence[int]) -> None:
        """Withdraw what is still open once a run has ended."""

        if not job_ids:
            return
        marks = ", ".join("?" for _ in job_ids)
        with self.connection.transaction():
            self.connection.execute(
                f"UPDATE run_prompts SET state = 'expired', answer = NULL "
                f"WHERE job_id IN ({marks}) AND state IN ('waiting', 'answered')",
                tuple(job_ids),
            )


def prompts_for(context: Any) -> PromptStore:
    """The prompt store of a running Entropy (with the vault key for secrets)."""

    key = None
    try:
        from lib.vault.key import VaultKeyProvider

        key = VaultKeyProvider(context.executor, context.bootstrap.vault.key).key()
    except Exception:  # noqa: BLE001 - secret answers then cannot be kept
        key = None
    return PromptStore(context.database_manager.connection, key)
