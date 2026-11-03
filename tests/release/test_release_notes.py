"""Release notes: made from git and CHANGELOG.md by the build, shown once per person."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.web.routes import version as routes
from lib.database.connection import DatabaseConnection
from lib.system import release_notes
from lib.system.release_notes import (
    MAX_ITEMS_PER_SECTION,
    build_notes,
    notes_from_commits,
    parse_changelog,
    unseen_releases,
)
from scripts import release as release_script


@pytest.fixture(autouse=True)
def _every_version_announced(monkeypatch) -> None:
    """Most tests use small version numbers; the start has tests of its own."""

    monkeypatch.setattr(release_notes, "FIRST_VERSION", (0, 0, 0))


def _git(tags: dict, dates: dict | None = None):
    """A git with `tags`: {tag or "HEAD": commit subjects since the tag before}."""

    def run(arguments):
        if arguments[0] == "tag":
            return "\n".join(name for name in tags if name != "HEAD")
        revisions = arguments[-1]
        if "-1" in arguments:
            return (dates or {}).get(revisions, "2026-01-01")
        return "\n".join(tags.get(revisions.split("..")[-1], []))

    return run


@pytest.mark.parametrize(
    ("subject", "section", "text"),
    [
        ("feat(auth): last sign-in", "New", "Last sign-in"),
        ("feat: add thing", "New", "Add thing"),
        ("feat(api)!: breaking thing", "New", "Breaking thing"),
        ("fix(ui): broken button", "Fixed", "Broken button"),
        ("perf: faster list", "Improved", "Faster list"),
        ("security: patch library", "Security", "Patch library"),
        ("fix(security): token leak", "Security", "Token leak"),
    ],
)
def test_user_facing_commits_become_notes(subject, section, text) -> None:
    sections, _ = notes_from_commits([subject])

    assert sections == [{"title": section, "items": [text]}]


@pytest.mark.parametrize(
    "subject",
    [
        "chore: tidy",
        "docs: words",
        "test: more",
        "refactor(x): move",
        "build(deps): bump",
        "ci: fix pipeline",
        "Merge branch 'main'",
        "no convention at all",
    ],
)
def test_other_commits_are_not_news(subject) -> None:
    assert notes_from_commits([subject])[0] == []


def test_security_comes_first_and_repeats_are_dropped() -> None:
    sections, _ = notes_from_commits(["fix: a", "feat: b", "fix: a", "security: c"])

    assert [item["title"] for item in sections] == ["Security", "New", "Fixed"]
    assert sections[2]["items"] == ["A"]


def test_a_long_section_is_cut_and_says_how_much_was_left_out() -> None:
    subjects = [f"fix: item {n}" for n in range(MAX_ITEMS_PER_SECTION + 7)]

    sections, left_out = notes_from_commits(subjects)

    assert len(sections[0]["items"]) == MAX_ITEMS_PER_SECTION and left_out == 7


def test_many_features_do_not_hide_the_fixes() -> None:
    subjects = [f"feat: item {n}" for n in range(100)] + ["fix: a bug"]

    sections, _ = notes_from_commits(subjects)

    assert [item["title"] for item in sections] == ["New", "Fixed"]
    assert sections[1]["items"] == ["A bug"]


def test_security_items_are_never_cut() -> None:
    subjects = [f"security: item {n}" for n in range(MAX_ITEMS_PER_SECTION + 7)]

    sections, left_out = notes_from_commits(subjects)

    assert len(sections[0]["items"]) == MAX_ITEMS_PER_SECTION + 7 and left_out == 0


def test_the_changelog_is_understood() -> None:
    parsed = parse_changelog(
        "# Changelog\n\nignored\n- ignored\n\n"
        "## 1.2.0 - 2026-11-03\n### Fixed\n- One\n* Two\n### New\n- Three\n"
        "## [v1.1.0]\n- Under no heading\n"
    )

    assert parsed["1.2.0"]["date"] == "2026-11-03"
    assert parsed["1.2.0"]["items"] == {"Fixed": ["One", "Two"], "New": ["Three"]}
    assert parsed["1.1.0"]["items"] == {"New": ["Under no heading"]}


def test_one_generated_line_can_be_reworded_or_dropped() -> None:
    changelog = "## Reworded\n- Long old text => Short\n- Internal thing =>\n"
    run = _git({"v1.0.0": ["perf: long old text", "feat: internal thing", "fix: kept as is"]})

    [release] = build_notes("1.0.0", run, changelog=changelog)

    assert release["sections"] == [
        {"title": "Improved", "items": ["Short"]},
        {"title": "Fixed", "items": ["Kept as is"]},
    ]


def test_rewording_is_not_read_as_part_of_a_version() -> None:
    parsed = parse_changelog("## 1.0.0\n- Real\n## Reworded\n- Old => New\n")

    assert parsed["1.0.0"]["items"] == {"New": ["Real"]}


def test_an_untagged_version_takes_what_came_since_the_newest_tag() -> None:
    run = _git({"v1.0.0": ["feat: old"], "v1.1.0": ["feat: older"], "HEAD": ["fix: fresh"]})

    releases = build_notes("1.2.0", run, changelog="", today=date(2026, 11, 3))

    assert [item["version"] for item in releases] == ["1.2.0", "1.1.0", "1.0.0"]
    assert releases[0]["date"] == "2026-11-03"
    assert releases[0]["sections"] == [{"title": "Fixed", "items": ["Fresh"]}]


def test_tags_sort_by_version_not_as_text() -> None:
    run = _git({"v1.9.0": ["feat: nine"], "v1.10.0": ["feat: ten"], "not-a-version": ["feat: x"]})

    releases = build_notes("1.10.0", run, changelog="")

    assert [item["version"] for item in releases] == ["1.10.0", "1.9.0"]


def test_each_tag_only_has_its_own_commits(monkeypatch) -> None:
    asked = []

    def run(arguments):
        if arguments[0] == "tag":
            return "v1.0.0\nv1.1.0"
        if "-1" not in arguments:
            asked.append(arguments[-1])
        return "feat: x"

    build_notes("1.1.0", run, changelog="")

    assert asked == ["v1.0.0..v1.1.0", "v1.0.0"]


def test_a_written_section_replaces_what_git_would_say() -> None:
    run = _git({"v1.0.0": ["feat: from git"]})

    [release] = build_notes("1.0.0", run, changelog="## 1.0.0 - 2026-01-01\n### New\n- By hand\n")

    assert release["sections"] == [{"title": "New", "items": ["By hand"]}]
    assert release["date"] == "2026-01-01"


def test_a_version_with_nothing_for_users_is_left_out() -> None:
    run = _git({"v1.0.0": ["feat: real"], "HEAD": ["chore: tidy"]})

    assert [item["version"] for item in build_notes("1.1.0", run, changelog="")] == ["1.0.0"]


def test_notes_start_at_the_first_version_and_then_stack(monkeypatch) -> None:
    monkeypatch.setattr(release_notes, "FIRST_VERSION", (3, 3, 0))
    tags = {"v1.0.0": ["feat: old"], "v1.1.7": ["feat: older"], "HEAD": ["fix: fresh"]}

    # Before its tag, 3.3.0 holds everything since the last tag.
    [first] = build_notes("3.3.0", _git(tags), changelog="")
    assert first["version"] == "3.3.0"
    assert first["sections"] == [{"title": "Fixed", "items": ["Fresh"]}]

    # Once tagged, the next version stacks on top of it.
    tags["v3.3.0"] = ["fix: fresh"]
    tags["HEAD"] = ["feat: next"]
    releases = build_notes("3.3.1", _git(tags), changelog="")
    assert [item["version"] for item in releases] == ["3.3.1", "3.3.0"]


def test_a_version_before_the_first_has_no_notes(monkeypatch) -> None:
    monkeypatch.setattr(release_notes, "FIRST_VERSION", (3, 3, 0))

    assert build_notes("1.0.2", _git({"v1.0.0": ["feat: old"]}), changelog="") == []


def test_no_version_is_dropped_for_being_old(monkeypatch) -> None:
    tags = {f"v3.{n}.0": ["feat: x"] for n in range(3, 40)}
    monkeypatch.setattr(release_notes, "FIRST_VERSION", (3, 3, 0))

    assert len(build_notes("3.39.0", _git(tags), changelog="")) == 37


def test_no_git_and_no_changelog_is_not_an_error() -> None:
    assert build_notes("1.0.0", lambda arguments: None, changelog="") == []


# ----------------------------------------------------------------------
# The build
# ----------------------------------------------------------------------


def test_the_build_ships_a_small_notes_file(tmp_path, monkeypatch) -> None:
    root = tmp_path / "source"
    for name in ("core/version.py", "lib/x.py", "resources/y.txt", "entropy.py", "pyproject.toml"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("x\n")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>")
    monkeypatch.setattr(release_script, "PROJECT_ROOT", root)
    monkeypatch.setattr(
        release_notes,
        "build_notes",
        lambda version: [{"version": version, "date": None, "sections": []}],
    )
    application = tmp_path / "stage" / "application"

    release_script.copy_application(application, "linux-x86_64", "9.9.9", dist, upgrade_only=True)

    text = (application / "resources" / "release_notes.json").read_text()
    assert json.loads(text)["releases"][0]["version"] == "9.9.9"
    assert "\n" not in text


def test_a_package_reads_its_file_and_needs_no_git(tmp_path, monkeypatch) -> None:
    notes = tmp_path / "release_notes.json"
    notes.write_text(json.dumps({"releases": [{"version": "1.0.0", "sections": []}]}))
    monkeypatch.setattr(release_notes, "NOTES_FILE", notes)
    monkeypatch.setattr(release_notes, "_git", lambda arguments: pytest.fail("git was used"))
    release_notes._read_file.cache_clear()

    try:
        assert release_notes.load_releases("1.0.0")[0]["version"] == "1.0.0"
    finally:
        release_notes._read_file.cache_clear()


# ----------------------------------------------------------------------
# Who is told
# ----------------------------------------------------------------------


RELEASES = [{"version": "1.3.0"}, {"version": "1.2.0"}, {"version": "1.1.0"}]


def _versions(items) -> list:
    return [item["version"] for item in items]


def test_someone_up_to_date_is_told_nothing() -> None:
    assert unseen_releases(RELEASES, "1.3.0", "1.3.0") == []


def test_after_an_upgrade_they_see_what_they_missed() -> None:
    assert _versions(unseen_releases(RELEASES, "1.3.0", "1.2.0")) == ["1.3.0"]
    assert _versions(unseen_releases(RELEASES, "1.3.0", "1.1.0")) == ["1.3.0", "1.2.0"]


def test_someone_who_has_seen_nothing_gets_the_current_version_only() -> None:
    assert _versions(unseen_releases(RELEASES, "1.3.0", None)) == ["1.3.0"]


def test_a_version_without_notes_announces_nothing_to_them() -> None:
    assert unseen_releases(RELEASES, "1.4.0", None) == []


@pytest.fixture()
def world(tmp_path, monkeypatch) -> SimpleNamespace:
    connection = DatabaseConnection(tmp_path / "entropy.db")
    with connection.transaction():
        connection.execute(
            "CREATE TABLE user_web_settings (user_id INTEGER PRIMARY KEY, settings TEXT,"
            " updated_at TEXT)"
        )
    context = SimpleNamespace(database_manager=SimpleNamespace(connection=connection))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(entropy_context=context)))
    pending = {"tour": False}
    monkeypatch.setattr(routes, "VERSION", "1.3.0")
    monkeypatch.setattr(routes, "load_releases", lambda version: RELEASES)
    monkeypatch.setattr(
        routes,
        "Onboarding",
        lambda connection: SimpleNamespace(pending=lambda user: pending["tour"]),
    )
    record = ("t", MagicMock(), SimpleNamespace(id=1, username="me"))
    return SimpleNamespace(request=request, record=record, pending=pending)


def _notes(world) -> dict:
    return routes.release_notes(world.request, SimpleNamespace(headers={}), world.record)


def test_it_shows_once_until_seen(world) -> None:
    assert _versions(_notes(world)["unseen"]) == ["1.3.0"]
    assert _versions(_notes(world)["unseen"]) == ["1.3.0"]

    routes.mark_release_notes_seen(world.request, world.record)

    notes = _notes(world)
    assert notes["unseen"] == [] and _versions(notes["releases"]) == ["1.3.0", "1.2.0", "1.1.0"]


def test_the_next_upgrade_shows_it_again(world, monkeypatch) -> None:
    monkeypatch.setattr(routes, "VERSION", "1.2.0")
    routes.mark_release_notes_seen(world.request, world.record)
    monkeypatch.setattr(routes, "VERSION", "1.3.0")

    assert _versions(_notes(world)["unseen"]) == ["1.3.0"]


def test_a_new_account_starts_with_the_tour_not_news(world) -> None:
    world.pending["tour"] = True

    assert _notes(world)["unseen"] == []

    # Nor is it news after the tour.
    world.pending["tour"] = False
    assert _notes(world)["unseen"] == []


def test_each_person_has_their_own_record(world) -> None:
    routes.mark_release_notes_seen(world.request, world.record)
    other = ("t", MagicMock(), SimpleNamespace(id=2, username="you"))

    notes = routes.release_notes(world.request, SimpleNamespace(headers={}), other)

    assert _versions(notes["unseen"]) == ["1.3.0"]
