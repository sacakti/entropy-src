"""
Workflow event persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any

from lib.database.repository import Repository


@dataclass(frozen=True)
class WorkflowEvent:
    """
    Persisted workflow event.
    """

    id: int | None

    job_id: int

    execution_id: str

    event_type: str

    source: str | None

    level: str | None

    message: str | None

    node_type: str | None

    node_id: str | None

    node_name: str | None

    payload: dict[str, Any] | None

    created_at: datetime | None = None


class WorkflowEventRepository(Repository):
    """
    Persists workflow execution events.
    """

    def create(
        self,
        event: WorkflowEvent,
    ) -> WorkflowEvent:
        """
        Store a workflow event.
        """

        import json

        with self.connection.transaction():

            cursor = self.execute(
                """
                INSERT INTO workflow_events
                (
                    job_id,
                    execution_id,
                    event_type,
                    source,
                    level,
                    message,
                    node_type,
                    node_id,
                    node_name,
                    payload,
                    created_at
                )
                VALUES
                (
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    datetime('now')
                )
                """,
                (
                    event.job_id,
                    event.execution_id,
                    event.event_type,
                    event.source,
                    event.level,
                    event.message,
                    event.node_type,
                    event.node_id,
                    event.node_name,
                    (
                        json.dumps(
                            event.payload,
                        )
                        if event.payload is not None
                        else None
                    ),
                ),
            )

            event_id = cursor.lastrowid

        assert event_id is not None

        return self.get(
            event_id,
        )

    def get(
        self,
        event_id: int,
    ) -> WorkflowEvent:
        """
        Return a workflow event.
        """

        import json

        row = self.connection.fetchone(
            """
            SELECT *
            FROM workflow_events
            WHERE id = ?
            """,
            (event_id,),
        )

        if row is None:

            raise KeyError(
                f"Workflow event '{event_id}' was not found.",
            )

        return self._from_row(
            row,
            json,
        )

    def list(
        self,
        job_id: int,
        *,
        after: int | None = None,
        limit: int | None = 500,
    ) -> list[WorkflowEvent]:
        """
        Return events for a job.

        When ``after`` is supplied, only events with a greater
        event ID are returned.

        When ``limit`` is ``None``, all matching events are returned.
        """

        import json

        if after is None:

            sql = """
                SELECT *
                FROM workflow_events
                WHERE job_id = ?
                ORDER BY id
            """

            parameters: tuple = (job_id,)

        else:

            sql = """
                SELECT *
                FROM workflow_events
                WHERE job_id = ?
                AND id > ?
                ORDER BY id
            """

            parameters = (
                job_id,
                after,
            )

        if limit is not None:

            sql += "\nLIMIT ?"

            parameters += (limit,)

        rows = self.connection.fetchall(
            sql,
            parameters,
        )

        return [
            self._from_row(
                row,
                json,
            )
            for row in rows
        ]

    @classmethod
    def _from_row(
        cls,
        row,
        json,
    ) -> WorkflowEvent:

        payload = row["payload"]

        return WorkflowEvent(
            id=row["id"],
            job_id=row["job_id"],
            execution_id=row["execution_id"],
            event_type=row["event_type"],
            source=row["source"],
            level=row["level"],
            message=row["message"],
            node_type=row["node_type"],
            node_id=row["node_id"],
            node_name=row["node_name"],
            payload=(json.loads(payload) if payload else None),
            created_at=(
                datetime.fromisoformat(
                    row["created_at"],
                )
                if row["created_at"]
                else None
            ),
        )
