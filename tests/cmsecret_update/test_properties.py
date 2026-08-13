from cm_secret_update.properties import (
    PropertiesUpdater,
)


def _updater() -> PropertiesUpdater:
    return PropertiesUpdater()


def test_updates_equals_separator() -> None:
    content = (
        "application.name=old\n"
        "application.port=8080\n"
    )

    result = _updater().update(
        content,
        {
            "application.name": "entropy",
            "application.port": "8081",
        },
    )

    assert result == (
        "application.name=entropy\n"
        "application.port=8081\n"
    )


def test_updates_colon_separator() -> None:
    content = (
        "application.name:old\n"
        "application.port:8080\n"
    )

    result = _updater().update(
        content,
        {
            "application.name": "entropy",
            "application.port": "8081",
        },
    )

    assert result == (
        "application.name:entropy\n"
        "application.port:8081\n"
    )


def test_updates_whitespace_separator() -> None:
    content = (
        "application.name old\n"
        "application.port 8080\n"
    )

    result = _updater().update(
        content,
        {
            "application.name": "entropy",
            "application.port": "8081",
        },
    )

    assert result == (
        "application.name entropy\n"
        "application.port 8081\n"
    )


def test_preserves_comments() -> None:
    content = (
        "# Application configuration\n"
        "! Another comment\n"
        "application.name=old\n"
    )

    result = _updater().update(
        content,
        {
            "application.name": "entropy",
        },
    )

    assert result == (
        "# Application configuration\n"
        "! Another comment\n"
        "application.name=entropy\n"
    )


def test_preserves_blank_lines() -> None:
    content = (
        "application.name=old\n"
        "\n"
        "\n"
        "application.port=8080\n"
    )

    result = _updater().update(
        content,
        {
            "application.name": "entropy",
        },
    )

    assert result == (
        "application.name=entropy\n"
        "\n"
        "\n"
        "application.port=8080\n"
    )


def test_adds_missing_properties() -> None:
    content = (
        "application.name=old\n"
    )

    result = _updater().update(
        content,
        {
            "application.name": "entropy",
            "application.port": "8081",
        },
    )

    assert result == (
        "application.name=entropy\n"
        "application.port=8081\n"
    )


def test_does_not_duplicate_existing_property() -> None:
    content = (
        "application.name=old\n"
    )

    result = _updater().update(
        content,
        {
            "application.name": "entropy",
        },
    )

    assert result == (
        "application.name=entropy\n"
    )


def test_preserves_unmanaged_properties() -> None:
    content = (
        "application.name=old\n"
        "application.debug=true\n"
    )

    result = _updater().update(
        content,
        {
            "application.name": "entropy",
        },
    )

    assert result == (
        "application.name=entropy\n"
        "application.debug=true\n"
    )


def test_handles_crlf_newlines() -> None:
    content = (
        "application.name=old\r\n"
        "application.port=8080\r\n"
    )

    result = _updater().update(
        content,
        {
            "application.name": "entropy",
        },
    )

    assert result == (
        "application.name=entropy\r\n"
        "application.port=8080\r\n"
    )


def test_handles_line_without_trailing_newline() -> None:
    content = "application.name=old"

    result = _updater().update(
        content,
        {
            "application.name": "entropy",
        },
    )

    assert result == "application.name=entropy"


def test_adds_missing_property_with_newline() -> None:
    content = "application.name=old"

    result = _updater().update(
        content,
        {
            "application.port": "8081",
        },
    )

    assert result == (
        "application.name=old"
        "application.port=8081\n"
    )


def test_ignores_unparseable_lines() -> None:
    content = (
        "this-is-not-a-property\n"
        "application.name=old\n"
    )

    result = _updater().update(
        content,
        {
            "application.name": "entropy",
        },
    )

    assert result == (
        "this-is-not-a-property\n"
        "application.name=entropy\n"
    )


def test_handles_escaped_separator() -> None:
    content = (
        r"application\.name=old"
        "\n"
    )

    result = _updater().update(
        content,
        {
            r"application\.name": "entropy",
        },
    )

    assert result == (
        r"application\.name=entropy"
        "\n"
    )


def test_first_unescaped_separator_is_used() -> None:
    content = (
        "application.name=old=value\n"
    )

    result = _updater().update(
        content,
        {
            "application.name": "entropy",
        },
    )

    assert result == (
        "application.name=entropy\n"
    )


def test_empty_content_adds_properties() -> None:
    result = _updater().update(
        "",
        {
            "application.name": "entropy",
            "application.port": "8081",
        },
    )

    assert result == (
        "application.name=entropy\n"
        "application.port=8081\n"
    )


def test_empty_entries_preserves_content() -> None:
    content = (
        "# comment\n"
        "application.name=entropy\n"
    )

    result = _updater().update(
        content,
        {},
    )

    assert result == content
