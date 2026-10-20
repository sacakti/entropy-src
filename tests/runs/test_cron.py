"""Tests for cron expressions and schedule timing."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from lib.runs.cron import CronError, CronExpression
from lib.runs.schedules import ScheduleError, next_run

START = datetime(2026, 10, 20, 10, 7, 30, tzinfo=timezone.utc)


def _next(expression: str, count: int = 3):
    return [moment.isoformat() for moment in CronExpression(expression).upcoming(START, count)]


def test_steps_and_ranges() -> None:
    assert _next("*/5 * * * *") == [
        "2026-10-20T10:10:00+00:00",
        "2026-10-20T10:15:00+00:00",
        "2026-10-20T10:20:00+00:00",
    ]
    assert _next("15 */6 * * *", 2) == [
        "2026-10-20T12:15:00+00:00",
        "2026-10-20T18:15:00+00:00",
    ]


def test_names_and_macros() -> None:
    assert _next("0 9 * * mon-fri", 4)[-1] == "2026-10-26T09:00:00+00:00"
    assert _next("@daily", 1) == ["2026-10-21T00:00:00+00:00"]
    assert _next("0 0 1 jan *", 1) == ["2027-01-01T00:00:00+00:00"]


def test_sunday_is_zero_and_seven() -> None:
    assert _next("0 0 * * 0", 1) == _next("0 0 * * 7", 1) == ["2026-10-25T00:00:00+00:00"]


def test_day_of_month_or_weekday_when_both_restricted() -> None:
    # Friday the 23rd comes before the 13th of November.
    assert _next("0 0 13 * fri", 1) == ["2026-10-23T00:00:00+00:00"]


def test_leap_day_and_impossible_dates() -> None:
    assert _next("30 2 29 2 *", 1) == ["2028-02-29T02:30:00+00:00"]
    assert _next("0 0 30 2 *") == []


@pytest.mark.parametrize(
    "expression",
    ["* * *", "61 * * * *", "*/0 * * * *", "5-1 * * * *", "x * * * *", "1,,2 * * * *"],
)
def test_invalid_expressions(expression: str) -> None:
    with pytest.raises(CronError):
        CronExpression(expression)


def test_next_run_uses_the_schedule_time_zone() -> None:
    # 09:00 in Kolkata (UTC+05:30) is 03:30 UTC.
    assert next_run("0 9 * * *", "Asia/Kolkata", START).isoformat() == "2026-10-21T03:30:00+00:00"
    assert next_run("0 9 * * *", "UTC", START).isoformat() == "2026-10-21T09:00:00+00:00"

    with pytest.raises(ScheduleError):
        next_run("0 9 * * *", "Mars/Olympus", START)
