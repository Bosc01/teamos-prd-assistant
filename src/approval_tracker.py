"""Approval request tracking — create, manage, and query PRD/RFC approval requests."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
APPROVALS_FILE = ROOT / "data" / "approvals" / "approvals.json"

_STATUS_ICONS: Dict[str, str] = {
    "approved": "✓",
    "pending": "⏳",
    "reviewing": "🔍",
    "blocked": "🚫",
}

_APPROVER_STATUSES = {"pending", "reviewing", "approved", "blocked"}
_REQUEST_STATUSES = {"open", "complete", "cancelled"}


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

def load_all() -> List[Dict]:
    """Load all approval requests from disk."""
    if not APPROVALS_FILE.exists():
        return []
    return json.loads(APPROVALS_FILE.read_text(encoding="utf-8"))


def save_all(requests: List[Dict]) -> None:
    """Write all requests back to disk atomically."""
    APPROVALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = APPROVALS_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(requests, indent=2), encoding="utf-8")
    tmp_path.replace(APPROVALS_FILE)


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
    now_str = _now_iso()
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
    all_requests = load_all()
    all_requests.append(request)
    save_all(all_requests)
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
    """Update a single approver's status and log to audit trail.

    If all approvers are now 'approved', set request status to 'complete'.
    """
    if new_status not in _APPROVER_STATUSES:
        raise ValueError(f"Invalid approver status '{new_status}'. Must be one of: {_APPROVER_STATUSES}")

    all_requests = load_all()
    now_str = _now_iso()

    for req in all_requests:
        if req["id"] != request_id:
            continue
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

        if all(a["status"] == "approved" for a in req["approvers"]):
            req["status"] = "complete"
            req["audit_trail"].append(
                {
                    "timestamp": now_str,
                    "event": "complete",
                    "detail": "All approvers have approved.",
                }
            )

        save_all(all_requests)
        return req

    raise ValueError(f"No approval request found with id: {request_id}")


def record_notification(request_id: str, approver_handle: str) -> Dict:
    """Mark that an approver was notified."""
    all_requests = load_all()
    now_str = _now_iso()

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
        try:
            deadline_dt = datetime.fromisoformat(req["deadline"])
            if deadline_dt.tzinfo is None:
                deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
        except (ValueError, KeyError):
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
    all_requests = load_all()
    now_str = _now_iso()

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


def summary_table(requests: List[Dict]) -> str:
    """Return a human-readable ASCII table of all requests and approver statuses."""
    if not requests:
        return "No approval requests found."

    rows = []
    for req in requests:
        short_id = req["id"][:8]
        title = req["title"][:27] + "…" if len(req["title"]) > 28 else req["title"]
        status = req["status"]
        deadline = req.get("deadline", "")[:10]
        approver_parts = []
        for approver in req.get("approvers", []):
            icon = _STATUS_ICONS.get(approver["status"], "?")
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

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_audit_trail(req: Dict) -> str:
    lines = [f"Audit trail for: {req['title']} ({req['id'][:8]})"]
    for entry in req.get("audit_trail", []):
        ts = entry.get("timestamp", "")[:19].replace("T", " ")
        event = entry.get("event", "")
        detail = entry.get("detail", "")
        if detail:
            lines.append(f"  {ts}  {event}  — {detail}")
        else:
            lines.append(f"  {ts}  {event}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage approval requests for PRDs, RFCs, and specs."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = sub.add_parser("create", help="Create a new approval request.")
    p_create.add_argument("--title", required=True, help="Title of the document.")
    p_create.add_argument("--url", required=True, help="Link to the document.")
    p_create.add_argument("--requester", required=True, help="Slack handle of the requester.")
    p_create.add_argument("--approvers", nargs="+", required=True, help="Slack handles of approvers.")
    p_create.add_argument("--deadline", required=True, help="Deadline date (YYYY-MM-DD).")
    p_create.add_argument("--reminder-days", type=int, default=2, help="Reminder interval in days.")

    # status
    p_status = sub.add_parser("status", help="Show status of approval requests.")
    p_status.add_argument("--id", help="Show a specific request by ID.")

    # update
    p_update = sub.add_parser("update", help="Update an approver's status.")
    p_update.add_argument("--id", required=True, help="Request ID (or prefix).")
    p_update.add_argument("--approver", required=True, help="Approver handle.")
    p_update.add_argument(
        "--status",
        required=True,
        choices=["reviewing", "approved", "blocked"],
        help="New status.",
    )
    p_update.add_argument("--note", default=None, help="Optional note.")

    # cancel
    p_cancel = sub.add_parser("cancel", help="Cancel an approval request.")
    p_cancel.add_argument("--id", required=True, help="Request ID (or prefix).")

    # audit
    p_audit = sub.add_parser("audit", help="Show audit trail for a request.")
    p_audit.add_argument("--id", required=True, help="Request ID (or prefix).")

    return parser


def _resolve_id(partial_id: str) -> str:
    """Resolve a partial (prefix) ID to a full UUID."""
    all_requests = load_all()
    matches = [r["id"] for r in all_requests if r["id"].startswith(partial_id)]
    if not matches:
        raise ValueError(f"No request found matching id prefix: {partial_id}")
    if len(matches) > 1:
        raise ValueError(f"Ambiguous id prefix '{partial_id}' matches: {matches}")
    return matches[0]


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "create":
        req = create_request(
            title=args.title,
            doc_url=args.url,
            requester=args.requester,
            approvers=args.approvers,
            deadline=args.deadline,
            reminder_interval_days=args.reminder_days,
        )
        print(f"Created request: {req['id']}")
        print(summary_table([req]))

    elif args.command == "status":
        if args.id:
            full_id = _resolve_id(args.id)
            req = get_request(full_id)
            print(summary_table([req]))
        else:
            all_requests = load_all()
            if not all_requests:
                print("No approval requests found.")
            else:
                print(summary_table(all_requests))

    elif args.command == "update":
        full_id = _resolve_id(args.id)
        req = update_approver_status(
            request_id=full_id,
            approver_handle=args.approver,
            new_status=args.status,
            note=args.note,
        )
        print(f"Updated {args.approver} → {args.status}")
        print(summary_table([req]))

    elif args.command == "cancel":
        full_id = _resolve_id(args.id)
        req = cancel_request(full_id)
        print(f"Cancelled request: {req['id']}")

    elif args.command == "audit":
        full_id = _resolve_id(args.id)
        req = get_request(full_id)
        print(_format_audit_trail(req))


if __name__ == "__main__":
    main()
