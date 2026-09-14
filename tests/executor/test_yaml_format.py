from lib.executor.linux import LinuxExecutor


def test_yaml_preserves_string_values() -> None:
    executor = LinuxExecutor()

    document = {
        "data": {
            "literal_n": "N",
            "literal_y": "Y",
            "boolean": "true",
            "number": "123",
            "decimal": "1.5",
            "date": "2026-08-15",
            "normal": "hello",
        },
    }

    content = executor.serialize_yaml(
        document,
    )

    assert 'literal_n: "N"' in content
    assert 'literal_y: "Y"' in content
    assert 'boolean: "true"' in content
    assert 'number: "123"' in content
    assert 'decimal: "1.5"' in content
    assert 'date: "2026-08-15"' in content
    assert "normal: hello" in content


def test_yaml_serializes_multiline_strings_as_literal_blocks() -> None:
    executor = LinuxExecutor()

    document = {
        "data": {
            "application.properties": ("## TYPE\n" "APP_RATE=O\n" "NEXT_PROPS=Y\n"),
        },
    }

    content = executor.serialize_yaml(
        document,
    )

    assert "application.properties: |" in content
    assert "  ## TYPE" in content
    assert "  APP_RATE=O" in content
    assert "  NEXT_PROPS=Y" in content
    assert "\\n" not in content


def test_yaml_string_values_remain_strings() -> None:
    executor = LinuxExecutor()

    document = {
        "data": {
            "n": "N",
            "y": "Y",
            "true": "true",
            "false": "false",
            "number": "123",
            "decimal": "1.5",
            "date": "2026-08-15",
        },
    }

    content = executor.serialize_yaml(
        document,
    )

    parsed = executor.parse_yaml(
        content,
    )

    assert parsed["data"]["n"] == "N"
    assert parsed["data"]["y"] == "Y"
    assert parsed["data"]["true"] == "true"
    assert parsed["data"]["false"] == "false"
    assert parsed["data"]["number"] == "123"
    assert parsed["data"]["decimal"] == "1.5"
    assert parsed["data"]["date"] == "2026-08-15"


def test_yaml_quotes_time_like_strings() -> None:
    executor = LinuxExecutor()

    document = {
        "data": {
            "start_time": "10:00",
            "finish_time": "18:30:00",
        },
    }

    content = executor.serialize_yaml(
        document,
    )

    assert 'start_time: "10:00"' in content
    assert 'finish_time: "18:30:00"' in content
