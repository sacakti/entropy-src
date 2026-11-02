from cm_secret_update.properties import (
    PropertiesUpdater,
)


def _updater() -> PropertiesUpdater:
    return PropertiesUpdater()


def test_updates_equals_separator() -> None:
    content = "application.name=old\n" "application.port=8080\n"

    result, _ = _updater().update(
        content,
        {
            "application.name": "entropy",
            "application.port": "8081",
        },
    )

    assert result == ("application.name=entropy\n" "application.port=8081\n")


def test_updates_colon_separator() -> None:
    content = "application.name:old\n" "application.port:8080\n"

    result, _ = _updater().update(
        content,
        {
            "application.name": "entropy",
            "application.port": "8081",
        },
    )

    assert result == ("application.name:entropy\n" "application.port:8081\n")


def test_updates_whitespace_separator() -> None:
    content = "application.name old\n" "application.port 8080\n"

    result, _ = _updater().update(
        content,
        {
            "application.name": "entropy",
            "application.port": "8081",
        },
    )

    assert result == ("application.name entropy\n" "application.port 8081\n")


def test_preserves_comments() -> None:
    content = "# Application configuration\n" "! Another comment\n" "application.name=old\n"

    result, _ = _updater().update(
        content,
        {
            "application.name": "entropy",
        },
    )

    assert result == (
        "# Application configuration\n" "! Another comment\n" "application.name=entropy\n"
    )


def test_preserves_blank_lines() -> None:
    content = "application.name=old\n" "\n" "\n" "application.port=8080\n"

    result, _ = _updater().update(
        content,
        {
            "application.name": "entropy",
        },
    )

    assert result == ("application.name=entropy\n" "\n" "\n" "application.port=8080\n")


def test_adds_missing_properties() -> None:
    content = "application.name=old\n"

    result, _ = _updater().update(
        content,
        {
            "application.name": "entropy",
            "application.port": "8081",
        },
    )

    assert result == ("application.name=entropy\n" "application.port=8081\n")


def test_does_not_duplicate_existing_property() -> None:
    content = "application.name=old\n"

    result, _ = _updater().update(
        content,
        {
            "application.name": "entropy",
        },
    )

    assert result == ("application.name=entropy\n")


def test_preserves_unmanaged_properties() -> None:
    content = "application.name=old\n" "application.debug=true\n"

    result, _ = _updater().update(
        content,
        {
            "application.name": "entropy",
        },
    )

    assert result == ("application.name=entropy\n" "application.debug=true\n")


def test_handles_crlf_newlines() -> None:
    content = "application.name=old\r\n" "application.port=8080\r\n"

    result, _ = _updater().update(
        content,
        {
            "application.name": "entropy",
        },
    )

    assert result == ("application.name=entropy\r\n" "application.port=8080\r\n")


def test_handles_line_without_trailing_newline() -> None:
    content = "application.name=old"

    result, _ = _updater().update(
        content,
        {
            "application.name": "entropy",
        },
    )

    assert result == "application.name=entropy"


def test_adds_missing_property_with_newline() -> None:
    content = "application.name=old"

    result, _ = _updater().update(
        content,
        {
            "application.port": "8081",
        },
    )

    assert result == ("application.name=old\n" "application.port=8081\n")


def test_ignores_unparseable_lines() -> None:
    content = "this-is-not-a-property\n" "application.name=old\n"

    result, _ = _updater().update(
        content,
        {
            "application.name": "entropy",
        },
    )

    assert result == ("this-is-not-a-property\n" "application.name=entropy\n")


def test_handles_escaped_separator() -> None:
    content = r"application\.name=old" "\n"

    result, _ = _updater().update(
        content,
        {
            r"application\.name": "entropy",
        },
    )

    assert result == (r"application\.name=entropy" "\n")


def test_first_unescaped_separator_is_used() -> None:
    content = "application.name=old=value\n"

    result, _ = _updater().update(
        content,
        {
            "application.name": "entropy",
        },
    )

    assert result == ("application.name=entropy\n")


def test_empty_content_adds_properties() -> None:
    result, _ = _updater().update(
        "",
        {
            "application.name": "entropy",
            "application.port": "8081",
        },
    )

    assert result == ("application.name=entropy\n" "application.port=8081\n")


def test_empty_entries_preserves_content() -> None:
    content = "# comment\n" "application.name=entropy\n"

    result, _ = _updater().update(
        content,
        {},
    )

    assert result == content


def test_preserves_spaced_separators() -> None:
    content = "a.b = old\n" "c.d : old\n" "e.f=   old\n"

    result, _ = _updater().update(
        content,
        {
            "a.b": "new",
            "c.d": "new",
            "e.f": "new",
        },
    )

    assert result == ("a.b = new\n" "c.d : new\n" "e.f=   new\n")


def test_updates_indented_property_without_duplicating() -> None:
    result, changes = _updater().update(
        "  a.b=old\n",
        {
            "a.b": "new",
        },
    )

    assert result == "  a.b=new\n"
    assert changes == [{"key": "a.b", "status": "updated"}]


def test_commented_property_is_left_and_active_property_added() -> None:
    result, _ = _updater().update(
        "#a.b=old\n" "! a.c=old\n",
        {
            "a.b": "new",
        },
    )

    assert result == ("#a.b=old\n" "! a.c=old\n" "a.b=new\n")


def test_formats_yaml_scalars() -> None:
    result, _ = _updater().update(
        "on=false\n",
        {
            "on": True,
            "off": False,
            "port": 8080,
            "empty": None,
        },
    )

    assert result == ("on=true\n" "off=false\n" "port=8080\n" "empty=\n")


def test_update_replaces_continuation_lines() -> None:
    result, _ = _updater().update(
        "a.b=one,\\\n" "  two\n" "c.d=keep\n",
        {
            "a.b": "new",
        },
    )

    assert result == ("a.b=new\n" "c.d=keep\n")


def test_continuation_text_is_not_treated_as_property() -> None:
    content = "a.b=one,\\\n" "  c.d=two\n"

    result, changes = _updater().update(
        content,
        {
            "c.d": "new",
        },
    )

    assert result == (content + "c.d=new\n")
    assert changes == [{"key": "c.d", "status": "added"}]


def test_comment_ending_in_backslash_does_not_continue() -> None:
    result, _ = _updater().update(
        "# note \\\n" "a.b=old\n",
        {
            "a.b": "new",
        },
    )

    assert result == ("# note \\\n" "a.b=new\n")


def test_delete_handles_spacing_comments_and_continuations() -> None:
    content = "# keep\n" "a.b = 1\n" "  c.d=2\n" "e.f=one,\\\n" "  two\n" "g.h=3\n"

    result, changes = _updater().delete(
        content,
        [
            "a.b",
            "c.d",
            "e.f",
            "missing",
        ],
    )

    assert result == ("# keep\n" "g.h=3\n")
    assert changes[-1] == {"key": "missing", "status": "unchanged_missing"}


def test_plain_mapping_adds_no_comments() -> None:
    result, _ = _updater().update(
        "# keep\n" "a.b=old\n",
        {
            "a.b": "new",
        },
    )

    assert result == ("# keep\n" "a.b=new\n")
