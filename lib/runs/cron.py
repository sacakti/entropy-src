"""
Five-field cron expressions (minute hour day-of-month month day-of-week).

Supports `*`, lists, ranges, steps (`*/5`, `1-10/2`), month and weekday
names, `7` as Sunday and the `@hourly`/`@daily`/`@weekly`/`@monthly`/
`@yearly` shortcuts. Like Vixie cron, when both day-of-month and
day-of-week are restricted a time matches if either one does.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import FrozenSet, List, Optional, Tuple

MACROS = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}

MONTHS = {
    name: index + 1
    for index, name in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}

WEEKDAYS = {
    name: index for index, name in enumerate(["sun", "mon", "tue", "wed", "thu", "fri", "sat"])
}

# (name, low, high, names)
FIELDS = (
    ("minute", 0, 59, {}),
    ("hour", 0, 23, {}),
    ("day of month", 1, 31, {}),
    ("month", 1, 12, MONTHS),
    ("day of week", 0, 7, WEEKDAYS),
)

# Searching further than this means the expression never matches
# (for example 30 February).
SEARCH_LIMIT = timedelta(days=366 * 5)


class CronError(ValueError):
    """The expression is not valid cron syntax."""


def _value(text: str, low: int, high: int, names: dict, field: str) -> int:
    lowered = text.lower()
    if lowered in names:
        return names[lowered]
    if not text.isdigit():
        raise CronError(f"Invalid {field} value '{text}'.")
    value = int(text)
    if not low <= value <= high:
        raise CronError(f"{field.capitalize()} value {value} is outside {low}-{high}.")
    return value


def _field(text: str, low: int, high: int, names: dict, field: str) -> Tuple[FrozenSet[int], bool]:
    """Return the allowed values and whether the field was `*`."""

    values = set()
    wildcard = False

    for part in text.split(","):
        if not part:
            raise CronError(f"Empty item in {field}.")

        base, _, step_text = part.partition("/")
        step = 1
        if step_text:
            if not step_text.isdigit() or int(step_text) == 0:
                raise CronError(f"Invalid step '{step_text}' in {field}.")
            step = int(step_text)

        if base == "*":
            start, end = low, high
            if not step_text:
                wildcard = True
        elif "-" in base:
            first, _, last = base.partition("-")
            start = _value(first, low, high, names, field)
            end = _value(last, low, high, names, field)
            if start > end:
                raise CronError(f"Range {base} in {field} is reversed.")
        else:
            start = _value(base, low, high, names, field)
            end = high if step_text else start

        values.update(range(start, end + 1, step))

    return frozenset(values), wildcard


class CronExpression:
    """A parsed cron expression."""

    def __init__(self, expression: str) -> None:
        text = " ".join((expression or "").split())
        text = MACROS.get(text.lower(), text)
        parts = text.split(" ")

        if len(parts) != 5:
            raise CronError("Use five fields: minute hour day-of-month month day-of-week.")

        parsed = [
            _field(part, low, high, names, name)
            for part, (name, low, high, names) in zip(parts, FIELDS)
        ]

        self.expression = text
        self.minutes = parsed[0][0]
        self.hours = parsed[1][0]
        self.days = parsed[2][0]
        self.months = parsed[3][0]
        # Cron weekdays: 0 and 7 are Sunday. Python: Monday is 0.
        self.weekdays = frozenset((value - 1) % 7 for value in parsed[4][0])
        self._day_wildcard = parsed[2][1]
        self._weekday_wildcard = parsed[4][1]

    def _day_matches(self, moment: datetime) -> bool:
        day = moment.day in self.days
        weekday = moment.weekday() in self.weekdays

        if self._day_wildcard or self._weekday_wildcard:
            return day and weekday
        return day or weekday

    def matches(self, moment: datetime) -> bool:
        return (
            moment.minute in self.minutes
            and moment.hour in self.hours
            and moment.month in self.months
            and self._day_matches(moment)
        )

    def next_after(self, moment: datetime) -> Optional[datetime]:
        """The first matching minute strictly after `moment`."""

        candidate = moment.replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = moment + SEARCH_LIMIT

        while candidate <= limit:
            if candidate.month not in self.months:
                year = candidate.year + (candidate.month == 12)
                month = candidate.month % 12 + 1
                candidate = candidate.replace(year=year, month=month, day=1, hour=0, minute=0)
                continue

            if not self._day_matches(candidate):
                candidate = candidate.replace(hour=0, minute=0) + timedelta(days=1)
                continue

            if candidate.hour not in self.hours:
                candidate = candidate.replace(minute=0) + timedelta(hours=1)
                continue

            if candidate.minute not in self.minutes:
                candidate += timedelta(minutes=1)
                continue

            return candidate

        return None

    def upcoming(self, moment: datetime, count: int = 5) -> List[datetime]:
        result: List[datetime] = []
        current: Optional[datetime] = moment
        while current is not None and len(result) < count:
            current = self.next_after(current)
            if current is not None:
                result.append(current)
        return result
