"""
When a repeating task or reminder comes round next.

A task repeats from its due date and a reminder from its time, never from when someone
finished: a task closed late keeps its rhythm. Anything already past is skipped, so
nothing piles up after a holiday.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

REPEATS = ("daily", "weekdays", "weekly", "monthly", "yearly")


def _shift(moment: date, rule: str) -> date:
    """The next occurrence after `moment`. A date a month lacks becomes that month's last day."""

    if rule == "daily":
        return moment + timedelta(days=1)
    if rule == "weekdays":
        # Friday to Monday, Saturday to Monday, otherwise the next day.
        return moment + timedelta(days={4: 3, 5: 2}.get(moment.weekday(), 1))
    if rule == "weekly":
        return moment + timedelta(days=7)
    if rule == "monthly":
        month = moment.month % 12 + 1
        year = moment.year + (1 if moment.month == 12 else 0)
    elif rule == "yearly":
        month, year = moment.month, moment.year + 1
    else:
        raise ValueError(f"Unknown repeat '{rule}'.")
    return moment.replace(
        year=year, month=month, day=min(moment.day, calendar.monthrange(year, month)[1])
    )


def next_date(current: date, rule: str, today: date) -> date:
    """The first occurrence of `rule` after both `current` and `today`."""

    upcoming = _shift(current, rule)
    while upcoming <= today:
        upcoming = _shift(upcoming, rule)
    return upcoming


def next_moment(current: datetime, rule: str, now: datetime) -> datetime:
    """The first occurrence of `rule` after both `current` and `now`, at the same time of day."""

    upcoming = current
    while True:
        upcoming = datetime.combine(_shift(upcoming.date(), rule), upcoming.timetz())
        if upcoming > now:
            return upcoming
