from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

_IANA_TIMEZONES = frozenset(available_timezones())
_SYSTEM_DEPENDENT_TIMEZONE_KEYS = frozenset({"localtime", "posixrules"})


@dataclass(frozen=True, slots=True)
class CalendarPeriodBounds:
    """UTC bounds for an inclusive range of local calendar dates."""

    start_at: datetime
    end_at_exclusive: datetime


def resolve_iana_timezone(timezone: str) -> ZoneInfo:
    """Resolve a portable IANA timezone and reject host-dependent aliases."""

    if (
        timezone not in _IANA_TIMEZONES
        or timezone in _SYSTEM_DEPENDENT_TIMEZONE_KEYS
        or timezone.startswith(("posix/", "right/"))
    ):
        raise ValueError("timezone must be a valid IANA timezone")
    try:
        return ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc


def calendar_period_bounds(
    period_start: date, period_end: date, timezone: str
) -> CalendarPeriodBounds:
    """Convert inclusive local dates to a half-open UTC timestamp range."""

    if period_start > period_end:
        raise ValueError("period_start must be on or before period_end")
    if period_end == date.max:
        raise ValueError("period_end is outside the supported range")

    zone = resolve_iana_timezone(timezone)
    local_start = datetime.combine(period_start, time.min, tzinfo=zone)
    local_end_exclusive = datetime.combine(
        period_end + timedelta(days=1), time.min, tzinfo=zone
    )
    return CalendarPeriodBounds(
        start_at=local_start.astimezone(UTC),
        end_at_exclusive=local_end_exclusive.astimezone(UTC),
    )
