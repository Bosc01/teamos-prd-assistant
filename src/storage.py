"""Shared plumbing for the approval tracker and doc store: JSON persistence,
cross-process locking, timestamps, status icons, and deadline parsing."""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms have no fcntl
    fcntl = None  # type: ignore[assignment]

STATUS_ICONS: Dict[str, str] = {
    "approved": "✓",
    "pending": "⏳",
    "reviewing": "🔍",
    "blocked": "🚫",
}

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json_list(path: Path) -> List[Dict]:
    """Load a list of records from a JSON file; missing file means empty."""
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_json_list_atomic(path: Path, records: List[Dict]) -> None:
    """Write records to path atomically (write to a sibling, then rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    tmp_path.replace(path)


@contextmanager
def locked(path: Path) -> Iterator[None]:
    """Hold an exclusive advisory lock for a load-modify-save cycle on path.

    Every mutation rewrites the whole JSON file, so a cron reminder run and an
    interactive session that interleave would silently drop each other's
    audit-trail entries. All writers must take this lock first.
    """
    if fcntl is None:  # pragma: no cover - degrade to unlocked on non-POSIX
        yield
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / (path.name + ".lock")
    with open(lock_path, "w", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


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
