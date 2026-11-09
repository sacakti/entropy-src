"""
Time ranges for pod logs: the window the user picked, and the lines of a log inside it.

A line's time is the first timestamp near its start (ISO 8601, "2026-11-08 10:00:00,123",
or the access-log form "08/Nov/2026:10:00:00 +0000"). Lines without one (stack traces,
continuation lines) follow the line above them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional, Tuple

from .exceptions import PodLogsException

EVERYTHING = "Everything"
BETWEEN = "Between"
RANGES = {
    EVERYTHING: None,
    "Last 15 minutes": timedelta(minutes=15),
    "Last hour": timedelta(hours=1),
    "Last 6 hours": timedelta(hours=6),
    "Last 24 hours": timedelta(hours=24),
    "Last 7 days": timedelta(days=7),
    BETWEEN: None,
}

# Only the start of a line is searched: a timestamp later in a message is not its time.
_LEAD = 64
_ISO = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})[T ](?P<time>\d{2}:\d{2}:\d{2})"
    r"(?:[.,](?P<fraction>\d{1,9}))?\s?(?P<zone>Z|[+-]\d{2}:?\d{2})?"
)
_ACCESS = re.compile(
    r"(?P<day>\d{2})/(?P<month>[A-Z][a-z]{2})/(?P<year>\d{4}):(?P<time>\d{2}:\d{2}:\d{2})"
    r"\s(?P<zone>[+-]\d{4})"
)
_MONTHS = {
    name: number
    for number, name in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
        start=1,
    )
}
_INPUT_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M")


@dataclass(frozen=True)
class Window:
    """From `start` to `end` (either open); both None is everything."""

    start: Optional[datetime] = None
    end: Optional[datetime] = None

    @property
    def everything(self) -> bool:
        return self.start is None and self.end is None

    def contains(self, moment: datetime) -> bool:
        return (self.start is None or moment >= self.start) and (
            self.end is None or moment <= self.end
        )

    def describe(self, zone: tzinfo) -> str:
        if self.everything:
            return "everything"

        def text(moment: Optional[datetime]) -> str:
            return moment.astimezone(zone).strftime("%Y-%m-%d %H:%M:%S") if moment else "…"

        return f"{text(self.start)} to {text(self.end)}"


def _zone(text: Optional[str], default: tzinfo) -> tzinfo:
    if not text:
        return default
    if text == "Z":
        return timezone.utc
    sign = 1 if text[0] == "+" else -1
    digits = text[1:].replace(":", "")
    return timezone(sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:4])))


def parse_input(text: str, zone: tzinfo, label: str) -> Optional[datetime]:
    """A time typed on the page; naive times are in `zone`. Blank is None."""

    value = (text or "").strip()
    if not value:
        return None
    for pattern in _INPUT_FORMATS:
        try:
            return datetime.strptime(value, pattern).replace(tzinfo=zone)
        except ValueError:
            continue
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise PodLogsException(
            f"{label} '{value}' is not a time: use YYYY-MM-DD HH:MM (or HH:MM:SS)."
        ) from None
    return moment if moment.tzinfo else moment.replace(tzinfo=zone)


def window(
    choice: str,
    start_text: str,
    end_text: str,
    zone: tzinfo,
    now: Optional[datetime] = None,
) -> Window:
    """The window for the range picked on the page."""

    if choice not in RANGES:
        raise PodLogsException(f"Time range '{choice}' is not one of {', '.join(RANGES)}.")
    if choice == EVERYTHING:
        return Window()
    if choice == BETWEEN:
        start = parse_input(start_text, zone, "From")
        end = parse_input(end_text, zone, "To")
        if start and end and start > end:
            raise PodLogsException("From is later than To.")
        return Window(start, end)
    length = RANGES[choice]
    assert length is not None
    return Window((now or datetime.now(timezone.utc)) - length, None)


def line_time(line: str, zone: tzinfo) -> Optional[datetime]:
    """The time at the start of a line, or None; naive times are in `zone`."""

    lead = line[:_LEAD]
    match = _ISO.search(lead)
    if match:
        fraction = (match["fraction"] or "0")[:6].ljust(6, "0")
        try:
            moment = datetime.strptime(
                f"{match['date']} {match['time']}.{fraction}", "%Y-%m-%d %H:%M:%S.%f"
            )
        except ValueError:
            return None
        return moment.replace(tzinfo=_zone(match["zone"], zone))
    match = _ACCESS.search(lead)
    if match and match["month"] in _MONTHS:
        try:
            moment = datetime.strptime(
                f"{match['year']}-{_MONTHS[match['month']]:02d}-{match['day']} {match['time']}",
                "%Y-%m-%d %H:%M:%S",
            )
        except ValueError:
            return None
        return moment.replace(tzinfo=_zone(match["zone"], zone))
    return None


def filter_lines(text: str, span: Window, zone: tzinfo) -> Tuple[str, int, int, bool]:
    """
    The lines inside the window: (text, lines kept, lines in all, whether any line
    had a timestamp). Without timestamps nothing can be judged, so all is kept.
    """

    lines = text.splitlines()
    if span.everything:
        return text, len(lines), len(lines), True
    kept = []
    inside = True
    dated = False
    for line in lines:
        moment = line_time(line, zone)
        if moment is not None:
            dated = True
            inside = span.contains(moment)
        if inside:
            kept.append(line)
    if not dated:
        return text, len(lines), len(lines), False
    return "\n".join(kept), len(kept), len(lines), True
