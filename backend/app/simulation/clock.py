"""Pure game-clock helpers. 24:00 rolls to the next day at 00:00."""

MINUTES_PER_DAY = 24 * 60


def parse_time(time_str: str) -> tuple[int, int]:
    hours_str, minutes_str = time_str.split(":")
    return int(hours_str), int(minutes_str)


def format_time(hours: int, minutes: int) -> str:
    return f"{hours:02d}:{minutes:02d}"


def advance_clock(day: int, time: str, minutes: int) -> tuple[int, str]:
    hours, mins = parse_time(time)
    total_minutes = hours * 60 + mins + minutes
    days_elapsed, remaining = divmod(total_minutes, MINUTES_PER_DAY)
    new_hours, new_mins = divmod(remaining, 60)
    return day + days_elapsed, format_time(new_hours, new_mins)
