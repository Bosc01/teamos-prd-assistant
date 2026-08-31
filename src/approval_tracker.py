"""Approval request tracking — create, manage, and query PRD/RFC approval requests.

Domain logic only; the interactive menu and argparse front end live in cli.py.
Running `python -m src.approval_tracker` delegates there: no arguments launches
the menu, a subcommand (create, status, dashboard, update, reset, cancel, audit)
runs scripted.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from . import notifier
from .storage import (
    STATUS_ICONS,
    days_until_deadline,
    load_json_list,
    locked,
    now_iso,
    parse_deadline,
    save_json_list_atomic,
)

ROOT = Path(__file__).resolve().parent.parent
APPROVALS_FILE = ROOT / "data" / "approvals" / "approvals.json"

_APPROVER_STATUSES = {"pending", "reviewing", "approved", "blocked"}
_REQUEST_STATUSES = {"open", "complete", "cancelled"}


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

def load_all() -> List[Dict]:
    """Load all approval requests from disk."""
    return load_json_list(APPROVALS_FILE)


def save_all(requests: List[Dict]) -> None:
    """Write all requests back to disk atomically."""
    save_json_list_atomic(APPROVALS_FILE, requests)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_request(
    title: str,
    doc_url: str,
    requester: str,
    approvers: List[str],
    deadline: str,
    reminder_interval_days: int = 2,
) -> Dict:
    """Create a new approval request, save to JSON, and return the record."""
    if parse_deadline(deadline) is None:
        raise ValueError(
            f"Invalid deadline format '{deadline}'. Use YYYY-MM-DD (e.g. 2026-06-20)."
        )

    now_str = now_iso()
    request: Dict = {
        "id": str(uuid.uuid4()),
        "title": title,
        "doc_url": doc_url,
        "requester": requester,
        "deadline": deadline,
        "created_at": now_str,
        "reminder_interval_days": reminder_interval_days,
        "status": "open",
        "completion_notice_sent": False,
        "overdue_notice_sent_at": None,
        "approvers": [
            {
                "handle": handle,
                "status": "pending",
                "status_note": None,
                "status_updated_at": None,
                "last_notified_at": None,
                "notification_count": 0,
            }
            for handle in approvers
        ],
        "audit_trail": [
            {
                "timestamp": now_str,
                "event": "created",
                "detail": f"Created by {requester} with approvers: {', '.join(approvers)}",
            }
        ],
    }
    with locked(APPROVALS_FILE):
        all_requests = load_all()
        all_requests.append(request)
        save_all(all_requests)

    # Notify each approver up front (the reminder cadence starts from here).
    # Webhook I/O stays outside the lock so it cannot block other writers.
    for approver in request["approvers"]:
        notifier.send_approval_request(request, approver)

    # Persist who was notified so the audit trail records it.
    notified_at = now_iso()
    with locked(APPROVALS_FILE):
        all_requests = load_all()
        for req in all_requests:
            if req["id"] != request["id"]:
                continue
            for approver in req["approvers"]:
                approver["last_notified_at"] = notified_at
                req["audit_trail"].append(
                    {
                        "timestamp": notified_at,
                        "event": f"approval_request_sent:{approver['handle']}",
                        "detail": None,
                    }
                )
            save_all(all_requests)
            return req
    return request


def get_request(request_id: str) -> Dict:
    """Fetch a single request by ID. Raise ValueError if not found."""
    for req in load_all():
        if req["id"] == request_id:
            return req
    raise ValueError(f"No approval request found with id: {request_id}")


def update_approver_status(
    request_id: str,
    approver_handle: str,
    new_status: str,
    note: Optional[str] = None,
) -> Dict:
    """Update a single approver's status and log to audit trail."""
    if new_status not in _APPROVER_STATUSES:
        raise ValueError(f"Invalid approver status '{new_status}'. Must be one of: {_APPROVER_STATUSES}")

    now_str = now_iso()

    with locked(APPROVALS_FILE):
        all_requests = load_all()

        for req in all_requests:
            if req["id"] != request_id:
                continue
            if req.get("status") == "cancelled":
                raise ValueError(
                    f"Request {request_id} is cancelled; updates are not allowed. "
                    "Create a new request instead."
                )
            for approver in req["approvers"]:
                if approver["handle"] == approver_handle:
                    approver["status"] = new_status
                    approver["status_note"] = note
                    approver["status_updated_at"] = now_str
                    req["audit_trail"].append(
                        {
                            "timestamp": now_str,
                            "event": f"status_changed:{approver_handle}:{new_status}",
                            "detail": note,
                        }
                    )
                    if new_status == "approved":
                        req["audit_trail"].append(
                            {
                                "timestamp": now_str,
                                "event": f"approved:{approver_handle}",
                                "detail": None,
                            }
                        )
                    break
            else:
                raise ValueError(f"Approver '{approver_handle}' not found in request {request_id}")

            _recompute_request_status(req, now_str)

            save_all(all_requests)
            return req

    raise ValueError(f"No approval request found with id: {request_id}")


def _recompute_request_status(req: Dict, now_str: str) -> None:
    """Derive request status from approver states. Cancelled is terminal;
    otherwise all-approved means complete and anything else reopens."""
    if req.get("status") == "cancelled":
        return

    all_approved = bool(req["approvers"]) and all(
        a["status"] == "approved" for a in req["approvers"]
    )

    if all_approved and req["status"] != "complete":
        req["status"] = "complete"
        req["audit_trail"].append(
            {
                "timestamp": now_str,
                "event": "complete",
                "detail": "All approvers have approved.",
            }
        )
    elif not all_approved and req["status"] == "complete":
        req["status"] = "open"
        # Allow a fresh completion notice if the request completes again.
        req["completion_notice_sent"] = False
        req["audit_trail"].append(
            {
                "timestamp": now_str,
                "event": "reopened",
                "detail": "An approver is no longer approved.",
            }
        )


def reset_request(request_id: str) -> Dict:
    """Reset all approvers on a request back to pending and reopen if complete."""
    now_str = now_iso()

    with locked(APPROVALS_FILE):
        all_requests = load_all()

        for req in all_requests:
            if req["id"] != request_id:
                continue

            for approver in req["approvers"]:
                approver["status"] = "pending"
                approver["status_note"] = None
                approver["status_updated_at"] = now_str
                approver["last_notified_at"] = None
                approver["notification_count"] = 0

            req["status"] = "open"
            req["completion_notice_sent"] = False
            req["overdue_notice_sent_at"] = None
            req["audit_trail"].append(
                {
                    "timestamp": now_str,
                    "event": "reset",
                    "detail": "All approvers reset to pending.",
                }
            )
            save_all(all_requests)
            return req

    raise ValueError(f"No approval request found with id: {request_id}")


def record_overdue_notice(request_id: str) -> Dict:
    """Mark that an overdue alert was sent for a request."""
    now_str = now_iso()

    with locked(APPROVALS_FILE):
        all_requests = load_all()

        for req in all_requests:
            if req["id"] == request_id:
                req["overdue_notice_sent_at"] = now_str
                req["audit_trail"].append(
                    {
                        "timestamp": now_str,
                        "event": "overdue_alert_sent",
                        "detail": None,
                    }
                )
                save_all(all_requests)
                return req

    raise ValueError(f"No approval request found with id: {request_id}")


def record_notification(request_id: str, approver_handle: str) -> Dict:
    """Mark that an approver was notified."""
    now_str = now_iso()

    with locked(APPROVALS_FILE):
        all_requests = load_all()

        for req in all_requests:
            if req["id"] != request_id:
                continue
            for approver in req["approvers"]:
                if approver["handle"] == approver_handle:
                    approver["last_notified_at"] = now_str
                    approver["notification_count"] = approver.get("notification_count", 0) + 1
                    req["audit_trail"].append(
                        {
                            "timestamp": now_str,
                            "event": f"reminder_sent:{approver_handle}",
                            "detail": f"Notification #{approver['notification_count']}",
                        }
                    )
                    save_all(all_requests)
                    return req
            raise ValueError(f"Approver '{approver_handle}' not found in request {request_id}")

    raise ValueError(f"No approval request found with id: {request_id}")


def get_pending_reminders(now: Optional[datetime] = None) -> List[tuple]:
    """Return (request, approver) pairs that are due for a reminder."""
    if now is None:
        now = datetime.now(timezone.utc)

    due: List[tuple] = []
    for req in load_all():
        if req["status"] != "open":
            continue
        deadline_dt = parse_deadline(req.get("deadline"))
        if deadline_dt is None:
            continue

        if now > deadline_dt:
            continue

        interval = int(req.get("reminder_interval_days", 2))
        for approver in req.get("approvers", []):
            if approver["status"] == "approved":
                continue
            if approver["status"] not in ("pending", "reviewing", "blocked"):
                continue

            last_notified = approver.get("last_notified_at")
            if last_notified is None:
                due.append((req, approver))
            else:
                last_dt = datetime.fromisoformat(last_notified)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                if (now - last_dt).days >= interval:
                    due.append((req, approver))

    return due


def cancel_request(request_id: str) -> Dict:
    """Set request status to 'cancelled'."""
    now_str = now_iso()

    with locked(APPROVALS_FILE):
        all_requests = load_all()

        for req in all_requests:
            if req["id"] == request_id:
                req["status"] = "cancelled"
                req["audit_trail"].append(
                    {
                        "timestamp": now_str,
                        "event": "cancelled",
                        "detail": None,
                    }
                )
                save_all(all_requests)
                return req

    raise ValueError(f"No approval request found with id: {request_id}")


def dashboard(now: Optional[datetime] = None) -> str:
    """Return a prioritized view of all open approval requests grouped by urgency."""
    if now is None:
        now = datetime.now(timezone.utc)

    all_requests = load_all()
    open_requests = [r for r in all_requests if r["status"] == "open"]

    if not open_requests:
        return "No open approval requests."

    overdue: List[Dict] = []
    due_soon: List[Dict] = []
    healthy: List[Dict] = []

    for req in open_requests:
        days_remaining = days_until_deadline(req.get("deadline"), now=now)
        if days_remaining is None:
            healthy.append(req)
            continue

        if days_remaining < 0:
            overdue.append(req)
        elif days_remaining <= 3:
            due_soon.append(req)
        else:
            healthy.append(req)

    for group in (overdue, due_soon, healthy):
        group.sort(key=lambda r: r.get("deadline", ""))

    lines: List[str] = []

    def _render_group(label: str, requests: List[Dict]) -> None:
        if not requests:
            return
        lines.append(f"\n{label} ({len(requests)})")
        lines.append("-" * 60)
        for req in requests:
            short_id = req["id"][:8]
            title = req["title"][:40] + "..." if len(req["title"]) > 40 else req["title"]
            deadline = req.get("deadline", "no deadline")[:10]
            requester = req.get("requester", "unknown")
            lines.append(f"  {short_id}  {title}")
            lines.append(f"           Requester: {requester}  Deadline: {deadline}")
            for approver in req.get("approvers", []):
                icon = STATUS_ICONS.get(approver["status"], "?")
                note = f" -- {approver['status_note']}" if approver.get("status_note") else ""
                pings = approver.get("notification_count", 0)
                ping_str = f" ({pings} reminder{'s' if pings != 1 else ''} sent)" if pings else ""
                lines.append(f"           {icon} {approver['handle']}  {approver['status']}{note}{ping_str}")
            lines.append("")

    lines.append("APPROVAL DASHBOARD")
    lines.append("=" * 60)
    _render_group("OVERDUE", overdue)
    _render_group("DUE SOON", due_soon)
    _render_group("HEALTHY", healthy)

    total_blocked = sum(
        1 for r in open_requests
        for a in r.get("approvers", [])
        if a["status"] == "blocked"
    )
    total_pending = sum(
        1 for r in open_requests
        for a in r.get("approvers", [])
        if a["status"] in ("pending", "reviewing")
    )
    lines.append("-" * 60)
    lines.append(f"  {len(open_requests)} open request(s)  |  {total_pending} awaiting response  |  {total_blocked} blocked")

    return "\n".join(lines)


def summary_table(requests: List[Dict]) -> str:
    """Return a human-readable ASCII table of all requests and approver statuses."""
    if not requests:
        return "No approval requests found."

    rows = []
    for req in requests:
        short_id = req["id"][:8]
        title = req["title"][:27] + "..." if len(req["title"]) > 28 else req["title"]
        status = req["status"]
        deadline = req.get("deadline", "")[:10]
        approver_parts = []
        for approver in req.get("approvers", []):
            icon = STATUS_ICONS.get(approver["status"], "?")
            approver_parts.append(f"{approver['handle']}{icon}")
        approvers_str = " ".join(approver_parts)
        rows.append((short_id, title, status, deadline, approvers_str))

    col_widths = [8, 27, 8, 10, 26]
    headers = ["ID", "Title", "Status", "Deadline", "Approvers"]
    sep = "  ".join("-" * w for w in col_widths)
    header_row = "  ".join(h.ljust(w) for h, w in zip(headers, col_widths))

    lines = [header_row, sep]
    for short_id, title, status, deadline, approvers_str in rows:
        line = "  ".join(
            v.ljust(w)
            for v, w in zip([short_id, title, status, deadline, approvers_str], col_widths)
        )
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _format_audit_trail(req: Dict) -> str:
    lines = [f"Audit trail for: {req['title']} ({req['id'][:8]})"]
    for entry in req.get("audit_trail", []):
        ts = entry.get("timestamp", "")[:19].replace("T", " ")
        event = entry.get("event", "")
        detail = entry.get("detail", "")
        if detail:
            lines.append(f"  {ts}  {event}  -- {detail}")
        else:
            lines.append(f"  {ts}  {event}")
    return "\n".join(lines)


if __name__ == "__main__":
    from .cli import main

    main()
