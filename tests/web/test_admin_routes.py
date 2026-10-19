"""Tests for administration route helpers."""

from __future__ import annotations

from core.web.routes.admin import _sync


def test_sync_adds_and_removes_differences() -> None:
    added, removed = [], []

    _sync(["a", "b"], ["b", " c ", ""], added.append, removed.append)

    assert added == ["c"]
    assert removed == ["a"]


def test_sync_is_a_no_op_when_equal() -> None:
    calls = []

    _sync(["x"], ["x"], calls.append, calls.append)

    assert calls == []
