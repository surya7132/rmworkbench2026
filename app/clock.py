"""The demo clock.

All dates in the data are relative to 17 Nov 2026, 09:10 IST (the 'demo day').
The clock is FROZEN there, so the demo is repeatable: 'overdue' means the same thing
every time, however long the server stays up. It moves only when someone presses
'+1 day' (advance), and 'Reset demo' puts it back.
Set COMPASS_CLOCK=live to let it run in real time instead.
"""
import os
import time
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
DEMO_START = datetime(2026, 11, 17, 9, 10, tzinfo=IST)
LIVE = os.environ.get("COMPASS_CLOCK", "").lower() == "live"
_started = time.monotonic()
_offset = timedelta(0)


def restart():
    global _started, _offset
    _started = time.monotonic()
    _offset = timedelta(0)


def advance(hours=24):
    global _offset
    _offset += timedelta(hours=hours)


def now():
    run = timedelta(seconds=time.monotonic() - _started) if LIVE else timedelta(0)
    return DEMO_START + _offset + run


def parse(s):
    """ISO text (date or date-time, with or without offset) -> aware IST datetime."""
    if not s:
        return None
    d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=IST)
    return d.astimezone(IST)


def iso(d):
    return d.astimezone(IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")


def due_info(s, active=True):
    """Everything the screen needs to show a due date."""
    d = parse(s)
    if d is None:
        return dict(label="No due date", bucket="later", days=None)
    n = now()
    days = (d.date() - n.date()).days
    has_time = len(s) > 10
    clock_txt = d.strftime("%H:%M") if has_time else ""
    if not active:
        return dict(label=d.strftime("%d %b"), bucket="done", days=days)
    if d < n and (has_time or days < 0):
        late = (n.date() - d.date()).days
        return dict(label="Overdue" + (f" by {late} day{'s' if late != 1 else ''}" if late else " today"), bucket="overdue", days=days)
    if days == 0:
        return dict(label=f"Due today {clock_txt}".strip(), bucket="today", days=0)
    if days == 1:
        return dict(label=f"Due tomorrow {clock_txt}".strip(), bucket="week", days=1)
    if days <= 7:
        return dict(label=f"Due {d.strftime('%a %d %b')} {clock_txt}".strip(), bucket="week", days=days)
    return dict(label=f"Due {d.strftime('%d %b')}", bucket="later", days=days)
