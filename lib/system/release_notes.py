"""
"What's new" for each Entropy version, kept cheap to produce: scripts/release.py writes a small
JSON file into the package from the git history, so a release needs no extra step. A section
in CHANGELOG.md ("## 1.2.0") replaces what git would say for that version, when wanted.

    feat: ...      New              fix: ...    Fixed
    perf: ...      Improved         security: ... or fix(security): ...    Security

Anything else (chore, docs, test, refactor, build, ci, merges) is not news to users.
"""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404 - git with an argument list, at build time and in development
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
NOTES_FILE = ROOT / "resources" / "release_notes.json"
CHANGELOG = ROOT / "CHANGELOG.md"

# The package stays small: older history is not worth carrying.
MAX_VERSIONS = 12
MAX_ITEMS_PER_SECTION = 10

SECTIONS = ("Security", "New", "Improved", "Fixed")

_COMMIT = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]*)\))?!?:\s*(?P<text>.+)$")
_TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_HEADING = re.compile(r"^##\s+\[?v?(?P<version>\d+\.\d+\.\d+)\]?(?:\s*[-–(]\s*(?P<date>[\d-]+))?")
_SECTION = re.compile(r"^###\s+(?P<title>.+?)\s*$")
_ITEM = re.compile(r"^[-*]\s+(?P<text>.+?)\s*$")

GitRunner = Callable[[Sequence[str]], Optional[str]]


def _section_of(subject: str) -> Optional[Tuple[str, str]]:
    match = _COMMIT.match(subject.strip())
    if match is None:
        return None
    kind = match["type"].lower()
    scope = (match["scope"] or "").lower()
    if kind in ("security", "sec") or (kind == "fix" and scope == "security"):
        section = "Security"
    elif kind in ("feat", "feature"):
        section = "New"
    elif kind == "perf":
        section = "Improved"
    elif kind == "fix":
        section = "Fixed"
    else:
        return None
    text = match["text"].strip()
    return section, text[:1].upper() + text[1:]


def _compact(items: Dict[str, List[str]]) -> Tuple[List[Dict[str, Any]], int]:
    """
    Sections in a fixed order; returns also how many items were left out.

    The limit is per section so that many features cannot hide the fixes, and
    security items are never cut.
    """

    sections = []
    left_out = 0
    for title in [*SECTIONS, *(name for name in items if name not in SECTIONS)]:
        lines = list(dict.fromkeys(items.get(title, [])))
        if not lines:
            continue
        kept = lines if title == "Security" else lines[:MAX_ITEMS_PER_SECTION]
        left_out += len(lines) - len(kept)
        sections.append({"title": title, "items": kept})
    return sections, left_out


def notes_from_commits(subjects: Sequence[str]) -> Tuple[List[Dict[str, Any]], int]:
    items: Dict[str, List[str]] = {}
    for subject in subjects:
        found = _section_of(subject)
        if found:
            items.setdefault(found[0], []).append(found[1])
    return _compact(items)


def parse_changelog(text: str) -> Dict[str, Dict[str, Any]]:
    """Written notes by version: "## 1.2.0 - 2026-11-03", "### Fixed", "- Item"."""

    releases: Dict[str, Dict[str, Any]] = {}
    version: Optional[str] = None
    title = "New"
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            version = heading["version"]
            title = "New"
            releases[version] = {"date": heading["date"], "items": {}}
            continue
        if version is None:
            continue
        section = _SECTION.match(line)
        if section:
            title = section["title"]
            continue
        item = _ITEM.match(line)
        if item:
            releases[version]["items"].setdefault(title, []).append(item["text"])
    return releases


def _git(arguments: Sequence[str]) -> Optional[str]:
    try:
        result = subprocess.run(  # nosec B603 B607 - an argument list, nothing from users
            ["git", *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _versions_of_tags(run: GitRunner) -> List[Tuple[Tuple[int, ...], str]]:
    tags = []
    for tag in (run(["tag", "--list"]) or "").split():
        match = _TAG.match(tag)
        if match:
            tags.append((tuple(int(part) for part in match.groups()), tag))
    return sorted(tags, reverse=True)


def _subjects(run: GitRunner, revisions: str) -> List[str]:
    return (run(["log", "--no-merges", "--format=%s", revisions]) or "").splitlines()


def build_notes(
    version: str,
    run: GitRunner = _git,
    changelog: Optional[str] = None,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """The releases to ship, newest first; empty without git and a changelog, which is no error."""

    if changelog is None:
        changelog = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.is_file() else ""
    written = parse_changelog(changelog)
    tags = _versions_of_tags(run)
    bare = [tag.lstrip("v") for _, tag in tags]

    # (version, commits from, commits up to). The current version may have no tag yet.
    ranges: List[Tuple[str, Optional[str], str]] = []
    if version not in bare:
        ranges.append((version, tags[0][1] if tags else None, "HEAD"))
    for index, (_, tag) in enumerate(tags):
        ranges.append((tag.lstrip("v"), tags[index + 1][1] if index + 1 < len(tags) else None, tag))

    releases = []
    for name, start, end in ranges[:MAX_VERSIONS]:
        when = None
        if name in written:
            sections, left_out = _compact(written[name]["items"])
            when = written[name]["date"]
        else:
            revisions = f"{start}..{end}" if start else end
            sections, left_out = notes_from_commits(_subjects(run, revisions))
        if end != "HEAD":
            when = when or (run(["log", "-1", "--format=%cs", end]) or "").strip() or None
        else:
            when = when or (today or date.today()).isoformat()
        if sections:
            release: Dict[str, Any] = {"version": name, "date": when, "sections": sections}
            if left_out:
                release["more"] = left_out
            releases.append(release)
    return releases


def write_notes(destination: Path, version: str) -> int:
    """For the release build: the notes of this version and those before it. Returns how many."""

    releases = build_notes(version)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # No indentation: it is read by a program and shipped in every package.
    destination.write_text(
        json.dumps({"releases": releases}, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    return len(releases)


@lru_cache(maxsize=1)
def _read_file() -> Optional[Tuple[Dict[str, Any], ...]]:
    try:
        data = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    releases = data.get("releases") if isinstance(data, dict) else None
    return tuple(releases) if isinstance(releases, list) else None


@lru_cache(maxsize=4)
def _from_git(version: str) -> Tuple[Dict[str, Any], ...]:
    return tuple(build_notes(version))


def load_releases(version: str) -> List[Dict[str, Any]]:
    """What a running Entropy shows: its package's file; from git when running from source."""

    packaged = _read_file()
    return list(packaged) if packaged is not None else list(_from_git(version))


def unseen_releases(
    releases: Sequence[Dict[str, Any]], current: str, seen: Optional[str]
) -> List[Dict[str, Any]]:
    """
    What to announce to someone who last saw `seen`. Someone who has seen nothing is told only
    of the current version, not all of history.
    """

    if seen == current:
        return []
    if seen is None:
        return [release for release in releases[:1] if release["version"] == current]
    unseen = []
    for release in releases:
        if release["version"] == seen:
            break
        unseen.append(release)
    return unseen
