from datetime import datetime, timezone

import pytest

from openrpa.scheduling import next_cron_time, parse_cron, validate_timezone


def test_cron_uses_five_fields_and_next_utc_minute():
    after = datetime(2026, 10, 22, 12, 34, 12, tzinfo=timezone.utc)
    assert next_cron_time("35 12 * * *", "UTC", after=after) == "2026-10-22T12:35+00:00"


def test_weekday_cron_and_sunday_alias():
    after = datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc)  # Friday
    assert next_cron_time("0 9 * * 1-5", "UTC", after=after) == "2026-10-26T09:00+00:00"
    after = datetime(2026, 10, 24, 23, 59, tzinfo=timezone.utc)  # Saturday
    assert next_cron_time("0 0 * * 7", "UTC", after=after) == "2026-10-25T00:00+00:00"


def test_day_of_month_and_weekday_follow_cron_or_semantics():
    after = datetime(2026, 10, 22, 0, 0, tzinfo=timezone.utc)
    # November 1 is a Sunday, so the next match is Monday November 2.
    assert next_cron_time("0 0 1 * 1", "UTC", after=after) == "2026-10-26T00:00+00:00"


@pytest.mark.parametrize("expression", ["@daily", "0 0 * *", "60 * * * *", "*/0 * * * *", "1-5-7 * * * *"])
def test_rejects_unsupported_or_invalid_cron(expression):
    with pytest.raises(ValueError):
        parse_cron(expression)


def test_rejects_unknown_timezone():
    with pytest.raises(ValueError, match="Unknown IANA timezone"):
        validate_timezone("Not/A_Real_Zone")
