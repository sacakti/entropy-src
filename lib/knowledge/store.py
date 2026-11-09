"""
Persistent, project-scoped knowledge base entries.

An entry records a piece of work so it can be found again: what was done (its title),
where (an environment, server or system), when (a date and optional time), how (a body
written with the task description editor, so with headings, lists, tables and images) and
who took part. Tags and a reference (a ticket, a change number) help finding it.

Every entry has a version number: 1 when written, one more with each save that changes it.
The version replaced is kept (MAX_REVISIONS of them), can be read and exported, and can be
restored, which saves it again as the newest version.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from lib.database.connection import DatabaseConnection
from lib.tasks.markup import plain_text

TAG = re.compile(r"^[a-z0-9][a-z0-9 ._/-]{0,39}$")
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_TAGS = 20
MAX_PEOPLE = 50
EXCERPT_CHARACTERS = 240
# Kept per entry; the oldest go first.
MAX_REVISIONS = 50


class KnowledgeError(ValueError):
    """Values an entry cannot hold."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def ensure_knowledge_schema(connection: DatabaseConnection) -> None:
    if getattr(connection, "_entropy_knowledge_ready", False):
        return
    with connection.transaction():
        connection.execute(
            "CREATE TABLE IF NOT EXISTS kb_entries ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,"
            "title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',"
            "location TEXT NOT NULL DEFAULT '', happened_on TEXT NOT NULL, happened_time TEXT,"
            "people TEXT NOT NULL DEFAULT '[]', tags TEXT NOT NULL DEFAULT '[]',"
            "reference TEXT NOT NULL DEFAULT '',"
            "created_by TEXT NOT NULL, created_at TEXT NOT NULL,"
            "updated_by TEXT NOT NULL, updated_at TEXT NOT NULL"
            ")"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS kb_entries_project ON kb_entries(project_id, happened_on)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS kb_attachments ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "entry_id INTEGER NOT NULL REFERENCES kb_entries(id) ON DELETE CASCADE,"
            "filename TEXT NOT NULL, content_type TEXT, size_bytes INTEGER NOT NULL DEFAULT 0,"
            "storage_name TEXT NOT NULL, uploaded_by TEXT NOT NULL, created_at TEXT NOT NULL"
            ")"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS kb_revisions ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "entry_id INTEGER NOT NULL REFERENCES kb_entries(id) ON DELETE CASCADE,"
            "snapshot TEXT NOT NULL, edited_by TEXT NOT NULL, edited_at TEXT NOT NULL"
            ")"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS kb_revisions_entry ON kb_revisions(entry_id, id)"
        )
        columns = {row["name"] for row in connection.fetchall("PRAGMA table_info(kb_entries)")}
        if "version" not in columns:
            connection.execute(
                "ALTER TABLE kb_entries ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
            )
        columns = {row["name"] for row in connection.fetchall("PRAGMA table_info(kb_revisions)")}
        if "version" not in columns:
            connection.execute("ALTER TABLE kb_revisions ADD COLUMN version INTEGER")
    connection._entropy_knowledge_ready = True  # type: ignore[attr-defined]


# ----------------------------------------------------------------------
# Values
# ----------------------------------------------------------------------


def clean_tags(values: Iterable[Any]) -> List[str]:
    tags: List[str] = []
    for value in values:
        tag = re.sub(r"\s+", " ", str(value or "").strip().lower())
        if not tag:
            continue
        if not TAG.match(tag):
            raise KnowledgeError(
                f"'{tag}' is not a tag: letters, digits, spaces and . _ / - (at most 40)."
            )
        if tag not in tags:
            tags.append(tag)
    if len(tags) > MAX_TAGS:
        raise KnowledgeError(f"Use at most {MAX_TAGS} tags.")
    return tags


def clean_people(values: Iterable[Any]) -> List[str]:
    people: List[str] = []
    for value in values:
        name = str(value or "").strip()[:200]
        if name and name.lower() not in [person.lower() for person in people]:
            people.append(name)
    if len(people) > MAX_PEOPLE:
        raise KnowledgeError(f"Name at most {MAX_PEOPLE} people.")
    return people


def clean_day(value: Any) -> str:
    try:
        return date.fromisoformat(str(value or "")).isoformat()
    except ValueError:
        raise KnowledgeError("When must be a date (YYYY-MM-DD).") from None


def clean_time(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if not TIME.match(str(value)):
        raise KnowledgeError("The time must be HH:MM.")
    return str(value)


def _like(text: str) -> str:
    """A LIKE pattern for `text` anywhere, its own % and _ taken literally."""

    escaped = text.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


# ----------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------


_FIELDS = (
    "title",
    "body",
    "location",
    "happened_on",
    "happened_time",
    "people",
    "tags",
    "reference",
)


class KnowledgeStore:
    def __init__(self, connection: DatabaseConnection) -> None:
        self.connection = connection
        ensure_knowledge_schema(connection)

    # Reading -----------------------------------------------------------

    def _summary(self, row: Any) -> Dict[str, Any]:
        item = dict(row)
        item["people"] = json.loads(item.get("people") or "[]")
        item["tags"] = json.loads(item.get("tags") or "[]")
        text = plain_text(item.pop("body", "") or "")
        item["excerpt"] = " ".join(text.split())[:EXCERPT_CHARACTERS]
        return item

    def list(
        self,
        project_id: int,
        *,
        query: Optional[str] = None,
        tag: Optional[str] = None,
        location: Optional[str] = None,
        person: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Entries, newest first, without their bodies (an excerpt instead)."""

        clauses = ["e.project_id = ?"]
        parameters: List[Any] = [project_id]
        if query:
            # Every word somewhere in the entry, in any order.
            for word in query.split()[:10]:
                clauses.append(
                    "LOWER(e.title || ' ' || e.body || ' ' || e.location || ' ' || e.tags"
                    " || ' ' || e.people || ' ' || e.reference) LIKE ? ESCAPE '\\'"
                )
                parameters.append(_like(word))
        if tag:
            clauses.append("LOWER(e.tags) LIKE ? ESCAPE '\\'")
            parameters.append(_like(json.dumps(tag.strip().lower())))
        if location:
            clauses.append("LOWER(e.location) = ?")
            parameters.append(location.strip().lower())
        if person:
            clauses.append("LOWER(e.people) LIKE ? ESCAPE '\\'")
            parameters.append(_like(json.dumps(person.strip())))
        if start:
            clauses.append("e.happened_on >= ?")
            parameters.append(clean_day(start))
        if end:
            clauses.append("e.happened_on <= ?")
            parameters.append(clean_day(end))
        rows = self.connection.fetchall(
            "SELECT e.*, (SELECT COUNT(*) FROM kb_attachments a WHERE a.entry_id = e.id)"
            " AS attachment_count FROM kb_entries e WHERE "
            + " AND ".join(clauses)
            + " ORDER BY e.happened_on DESC, COALESCE(e.happened_time, '') DESC, e.id DESC"
            f" LIMIT {int(max(1, min(limit, 2000)))}",
            tuple(parameters),
        )
        return [self._summary(row) for row in rows]

    def facets(self, project_id: int) -> Dict[str, List[str]]:
        """The tags, places and people used in the project, for filters and suggestions."""

        tags: Dict[str, None] = {}
        locations: Dict[str, None] = {}
        people: Dict[str, None] = {}
        for row in self.connection.fetchall(
            "SELECT tags, location, people FROM kb_entries WHERE project_id = ?", (project_id,)
        ):
            for tag in json.loads(row["tags"] or "[]"):
                tags[tag] = None
            if row["location"]:
                locations[row["location"]] = None
            for person in json.loads(row["people"] or "[]"):
                people[person] = None
        return {
            "tags": sorted(tags),
            "locations": sorted(locations, key=str.lower),
            "people": sorted(people, key=str.lower),
        }

    def get(self, entry_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone("SELECT * FROM kb_entries WHERE id = ?", (entry_id,))
        if row is None:
            return None
        item = dict(row)
        item["people"] = json.loads(item["people"] or "[]")
        item["tags"] = json.loads(item["tags"] or "[]")
        item["attachments"] = self.attachments(entry_id)
        item["revisions"] = [
            dict(revision)
            for revision in self.connection.fetchall(
                "SELECT id, version, edited_by, edited_at FROM kb_revisions WHERE entry_id = ?"
                " ORDER BY id DESC",
                (entry_id,),
            )
        ]
        return item

    def revision(self, revision_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone("SELECT * FROM kb_revisions WHERE id = ?", (revision_id,))
        if row is None:
            return None
        item = dict(row)
        item.update(json.loads(item.pop("snapshot")))
        return item

    # Writing -----------------------------------------------------------

    def _values(self, values: Dict[str, Any]) -> Dict[str, Any]:
        clean: Dict[str, Any] = {}
        if "title" in values:
            title = str(values["title"] or "").strip()
            if not title:
                raise KnowledgeError("Say what was done: the title is empty.")
            clean["title"] = title[:200]
        if "body" in values:
            clean["body"] = str(values["body"] or "")
        if "location" in values:
            clean["location"] = str(values["location"] or "").strip()[:120]
        if "happened_on" in values:
            clean["happened_on"] = clean_day(values["happened_on"])
        if "happened_time" in values:
            clean["happened_time"] = clean_time(values["happened_time"])
        if "people" in values:
            clean["people"] = json.dumps(clean_people(values["people"] or []))
        if "tags" in values:
            clean["tags"] = json.dumps(clean_tags(values["tags"] or []))
        if "reference" in values:
            clean["reference"] = str(values["reference"] or "").strip()[:200]
        return clean

    def create(self, project_id: int, values: Dict[str, Any], actor: str) -> Dict[str, Any]:
        clean = self._values({"happened_on": date.today().isoformat(), "title": "", **values})
        now = _now()
        columns = list(clean) + [
            "project_id",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
        ]
        row = [*clean.values(), project_id, actor, now, actor, now]
        with self.connection.transaction():
            cursor = self.connection.execute(
                f"INSERT INTO kb_entries ({', '.join(columns)})"
                f" VALUES ({', '.join('?' for _ in columns)})",
                tuple(row),
            )
        created = self.get(int(cursor.lastrowid))
        assert created is not None  # nosec B101 - just written
        return created

    def update(self, entry_id: int, values: Dict[str, Any], actor: str) -> Dict[str, Any]:
        current = self.connection.fetchone("SELECT * FROM kb_entries WHERE id = ?", (entry_id,))
        if current is None:
            raise KnowledgeError("The entry no longer exists.")
        clean = self._values(values)
        changed = {key: value for key, value in clean.items() if current[key] != value}
        if changed:
            snapshot = json.dumps(
                {
                    field: (
                        json.loads(current[field] or "[]")
                        if field in ("people", "tags")
                        else current[field]
                    )
                    for field in _FIELDS
                }
            )
            now = _now()
            version = int(current["version"] or 1)
            assignments = ", ".join(f"{key} = ?" for key in changed)
            with self.connection.transaction():
                # The version replaced, kept under its number, who wrote it and when.
                self.connection.execute(
                    "INSERT INTO kb_revisions (entry_id, version, snapshot, edited_by, edited_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (entry_id, version, snapshot, current["updated_by"], current["updated_at"]),
                )
                self.connection.execute(
                    f"UPDATE kb_entries SET {assignments}, version = ?, updated_by = ?,"
                    " updated_at = ? WHERE id = ?",
                    (*changed.values(), version + 1, actor, now, entry_id),
                )
                kept = self.connection.fetchall(
                    "SELECT id FROM kb_revisions WHERE entry_id = ? ORDER BY id DESC",
                    (entry_id,),
                )
                for row in kept[MAX_REVISIONS:]:
                    self.connection.execute("DELETE FROM kb_revisions WHERE id = ?", (row["id"],))
        updated = self.get(entry_id)
        assert updated is not None  # nosec B101 - just written
        return updated

    def set_imported_body(self, entry_id: int, body: str) -> Dict[str, Any]:
        """
        The body of an entry just imported, with its images placed: still the first
        version, as nobody has written anything yet.
        """

        with self.connection.transaction():
            self.connection.execute("UPDATE kb_entries SET body = ? WHERE id = ?", (body, entry_id))
        found = self.get(entry_id)
        assert found is not None  # nosec B101 - just written
        return found

    def restore(self, entry_id: int, revision_id: int, actor: str) -> Dict[str, Any]:
        """Save an earlier version again, as the newest one; the current one is kept."""

        revision = self.revision(revision_id)
        if revision is None or revision["entry_id"] != entry_id:
            raise KnowledgeError("That version is not kept.")
        return self.update(entry_id, {field: revision[field] for field in _FIELDS}, actor)

    def delete(self, entry_id: int) -> List[Dict[str, Any]]:
        """Remove an entry; returns its attachments, whose files the caller removes."""

        attachments = [
            dict(row)
            for row in self.connection.fetchall(
                "SELECT * FROM kb_attachments WHERE entry_id = ?", (entry_id,)
            )
        ]
        with self.connection.transaction():
            self.connection.execute("DELETE FROM kb_revisions WHERE entry_id = ?", (entry_id,))
            self.connection.execute("DELETE FROM kb_attachments WHERE entry_id = ?", (entry_id,))
            self.connection.execute("DELETE FROM kb_entries WHERE id = ?", (entry_id,))
        return attachments

    # Attachments -------------------------------------------------------

    def attachments(self, entry_id: int) -> List[Dict[str, Any]]:
        return [
            dict(row)
            for row in self.connection.fetchall(
                "SELECT id, entry_id, filename, content_type, size_bytes, uploaded_by, created_at"
                " FROM kb_attachments WHERE entry_id = ? ORDER BY id",
                (entry_id,),
            )
        ]

    def get_attachment(self, attachment_id: int) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone(
            "SELECT * FROM kb_attachments WHERE id = ?", (attachment_id,)
        )
        return dict(row) if row else None

    def add_attachment(
        self,
        entry_id: int,
        filename: str,
        content_type: Optional[str],
        size: int,
        storage_name: str,
        actor: str,
    ) -> Dict[str, Any]:
        with self.connection.transaction():
            cursor = self.connection.execute(
                "INSERT INTO kb_attachments (entry_id, filename, content_type, size_bytes,"
                " storage_name, uploaded_by, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (entry_id, filename, content_type, size, storage_name, actor, _now()),
            )
        found = self.get_attachment(int(cursor.lastrowid))
        assert found is not None  # nosec B101 - just written
        return found

    def delete_attachment(self, attachment_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute("DELETE FROM kb_attachments WHERE id = ?", (attachment_id,))
