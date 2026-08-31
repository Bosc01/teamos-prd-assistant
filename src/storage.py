"""Shared plumbing for the approval tracker and doc store: deadline parsing."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_deadline(raw: Optional[str]) -> Optional[datetime]:
    """Parse a deadline string into an aware UTC datetime.

    A bare date (YYYY-MM-DD) means end of that day: a request due today stays
    actionable until the day is over, instead of flipping overdue at midnight.
    Returns None for missing or unparseable values.
    """
    if not raw or not isinstance(raw, str):
        return None
    try:
        deadline = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if _DATE_ONLY_RE.match(raw.strip()):
        deadline = deadline.replace(hour=23, minute=59, second=59, microsecond=999999)
    return deadline


def days_until_deadline(raw: Optional[str], now: Optional[datetime] = None) -> Optional[int]:
    """Calendar days from now until the deadline (negative means overdue).

    Returns None when the deadline cannot be parsed.
    """
    deadline = parse_deadline(raw)
    if deadline is None:
        return None
    if now is None:
        now = datetime.now(timezone.utc)
    return (deadline.date() - now.date()).days
