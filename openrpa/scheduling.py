"""Small, bounded five-field cron parser for local recurring workflows."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _field(text: str, minimum: int, maximum: int, *, sunday_alias: bool = False) -> tuple[set[int], bool]:
    if not text:
        raise ValueError("Cron fields cannot be empty")
    wildcard = text == "*" or text.startswith("*/")
    values: set[int] = set()
    for part in text.split(","):
        if not part:
            raise ValueError("Cron lists cannot contain empty items")
        base, slash, step_text = part.partition("/")
        if slash:
            if not step_text.isdigit() or int(step_text) < 1 or int(step_text) > maximum - minimum + 1:
                raise ValueError("Cron step must be a positive integer within the field range")
            step = int(step_text)
        else:
            step = 1
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            start_text, separator, end_text = base.partition("-")
            if not separator or not start_text.isdigit() or not end_text.isdigit():
                raise ValueError(f"Invalid cron range: {part}")
            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError("Cron ranges must ascend")
        elif base.isdigit():
            start = end = int(base)
        else:
            raise ValueError(f"Unsupported cron field item: {part}")
        if start < minimum or end > maximum:
            raise ValueError(f"Cron value must be between {minimum} and {maximum}")
        values.update(range(start, end + 1, step))
    if sunday_alias and 7 in values:
        values.discard(7)
        values.add(0)
    return values, wildcard


def parse_cron(expression: str) -> tuple[set[int], set[int], set[int], set[int], set[int], bool, bool]:
    if not isinstance(expression, str) or len(expression) > 128:
        raise ValueError("Cron expression must be a string up to 128 characters")
    parts = expression.split()
    if len(parts) != 5:
        raise ValueError("Use five cron fields: minute hour day-of-month month day-of-week")
    minute, _ = _field(parts[0], 0, 59)
    hour, _ = _field(parts[1], 0, 23)
    day, day_wild = _field(parts[2], 1, 31)
    month, _ = _field(parts[3], 1, 12)
    weekday, weekday_wild = _field(parts[4], 0, 7, sunday_alias=True)
    return minute, hour, day, month, weekday, day_wild, weekday_wild


def validate_timezone(name: str) -> ZoneInfo:
    if not isinstance(name, str) or not name or len(name) > 128:
        raise ValueError("A valid IANA timezone name is required")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown IANA timezone: {name}") from exc


def next_cron_time(expression: str, timezone_name: str, *, after: datetime | None = None) -> str:
    minute, hour, day, month, weekday, day_wild, weekday_wild = parse_cron(expression)
    zone = validate_timezone(timezone_name)
    moment = after or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("Cron search time must include a timezone")
    candidate = moment.astimezone(timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=1)
    # The one-year bound prevents hostile or impossible schedules from looping forever.
    for _ in range(527_040):
        local = candidate.astimezone(zone)
        day_match = local.day in day
        weekday_match = local.weekday() in {((value + 6) % 7) for value in weekday}
        if day_wild and weekday_wild:
            calendar_match = True
        elif day_wild:
            calendar_match = weekday_match
        elif weekday_wild:
            calendar_match = day_match
        else:
            calendar_match = day_match or weekday_match
        if local.minute in minute and local.hour in hour and local.month in month and calendar_match:
            return candidate.isoformat(timespec="minutes")
        candidate += timedelta(minutes=1)
    raise ValueError("Cron expression has no occurrence in the next 366 days")
