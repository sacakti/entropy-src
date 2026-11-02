"""
Tests for the YAML mapping comment helpers.
"""

from __future__ import annotations

from typing import Any, Dict, List

from lib.executor.filesystem import FileSystemMixin
from lib.executor.yaml_comments import mapping_with_comments, read_mapping_comments

SOURCE = """\
operations:
  - entries:
      # first
      # first again
      a: 1 # inline
      # own line

      # after blank
      b: 2
      # trailing
    # next operation
  - entries:
      c: 3
"""


def _entries(text: str = SOURCE) -> List[Dict[str, Any]]:
    document = FileSystemMixin().parse_yaml(text)

    return [operation["entries"] for operation in document["operations"]]


def test_reads_comments_onto_the_key_they_precede() -> None:
    comments, trailing = read_mapping_comments(_entries()[0])

    assert comments == {
        "a": ["# first", "# first again", "# inline"],
        "b": ["# own line", "# after blank"],
    }
    assert trailing == ["# trailing"]


def test_less_indented_comment_is_not_read() -> None:
    comments, trailing = read_mapping_comments(_entries()[1])

    assert comments == {"c": []}
    assert trailing == []


def test_plain_mapping_has_no_comments() -> None:
    assert read_mapping_comments({"a": 1}) == ({}, [])


def test_written_comments_read_back_unchanged() -> None:
    comments = {"a": ["# one", "#two"], "b": ["# three"], "c": []}
    trailing = ["# end"]

    mapping = mapping_with_comments({"a": 1, "b": 2, "c": 3}, comments, trailing, 4)

    filesystem = FileSystemMixin()

    text = filesystem.serialize_yaml({"operations": [{"entries": mapping}]})

    [entries] = _entries(text)

    assert dict(entries) == {"a": 1, "b": 2, "c": 3}
    assert read_mapping_comments(entries) == (comments, trailing)


def test_mapping_without_comments_is_returned_unchanged() -> None:
    mapping = {"a": 1}

    assert mapping_with_comments(mapping, {"a": []}, [], 4) is mapping
