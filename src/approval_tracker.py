"""Approval request tracking — create, manage, and query PRD/RFC approval requests.

Run with no arguments to launch the interactive menu.
Run with a subcommand for scripting (create, status, dashboard, update, reset, cancel, audit).
"""

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
    try:
        datetime.fromisoformat(deadline)
    except ValueError:
        raise ValueError(
            f"Invalid deadline format '{deadline}'. Use YYYY-MM-DD (e.g. 2026-06-20)."
        )

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
    """Update a single approver's status and log to audit trail."""
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


def reset_request(request_id: str) -> Dict:
    """Reset all approvers on a request back to pending and reopen if complete."""
    all_requests = load_all()
    now_str = _now_iso()

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
    """Return (request, approver) pairs that are due for a reminder.

    Only includes approvers in ``pending`` status. Approvers who are
    ``reviewing`` or ``blocked`` are excluded — use :func:`get_reviewing_requests`
    and :func:`get_blocked_requests` to surface those to the requester instead.
    """
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
            if approver["status"] != "pending":
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


def get_reviewing_requests(now: Optional[datetime] = None) -> List[tuple]:
    """Return (request, approver) pairs where an approver is actively reviewing."""
    if now is None:
        now = datetime.now(timezone.utc)

    reviewing: List[tuple] = []
    for req in load_all():
        if req["status"] != "open":
            continue
        for approver in req.get("approvers", []):
            if approver["status"] == "reviewing":
                reviewing.append((req, approver))
    return reviewing


def get_blocked_requests(now: Optional[datetime] = None) -> List[tuple]:
    """Return (request, approver) pairs where an approver is blocked, with blocker note."""
    if now is None:
        now = datetime.now(timezone.utc)

    blocked: List[tuple] = []
    for req in load_all():
        if req["status"] != "open":
            continue
        for approver in req.get("approvers", []):
            if approver["status"] == "blocked":
                blocked.append((req, approver))
    return blocked


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
        try:
            deadline_dt = datetime.fromisoformat(req["deadline"])
            if deadline_dt.tzinfo is None:
                deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
        except (ValueError, KeyError):
            healthy.append(req)
            continue

        days_remaining = (deadline_dt - now).days
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
                icon = _STATUS_ICONS.get(approver["status"], "?")
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
            lines.append(f"  {ts}  {event}  -- {detail}")
        else:
            lines.append(f"  {ts}  {event}")
    return "\n".join(lines)


def _pick_request(prompt: str = "Select a request") -> Optional[Dict]:
    """Show numbered list of open requests and return the one the user picks."""
    all_requests = load_all()
    open_requests = [r for r in all_requests if r["status"] == "open"]
    if not open_requests:
        print("No open requests found.")
        return None
    print(f"\n{prompt}:")
    for i, req in enumerate(open_requests, 1):
        short_id = req["id"][:8]
        title = req["title"][:40] + "..." if len(req["title"]) > 40 else req["title"]
        deadline = req.get("deadline", "")[:10]
        print(f"  {i}. {title}  (id: {short_id}  deadline: {deadline})")
    choice = input("\nEnter number: ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(open_requests):
            return open_requests[idx]
    except ValueError:
        pass
    print("Invalid selection.")
    return None


def _pick_approver(req: Dict, prompt: str = "Select an approver") -> Optional[str]:
    """Show numbered list of approvers on a request and return the chosen handle."""
    approvers = req.get("approvers", [])
    if not approvers:
        print("No approvers on this request.")
        return None
    print(f"\n{prompt}:")
    for i, a in enumerate(approvers, 1):
        icon = _STATUS_ICONS.get(a["status"], "?")
        note = f"  -- {a['status_note']}" if a.get("status_note") else ""
        print(f"  {i}. {a['handle']}  {icon} {a['status']}{note}")
    choice = input("\nEnter number: ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(approvers):
            return approvers[idx]["handle"]
    except ValueError:
        pass
    print("Invalid selection.")
    return None


# ---------------------------------------------------------------------------
# Interactive menu
# ---------------------------------------------------------------------------

def _menu_create() -> None:
    print("\n-- Create new approval request --")
    title = input("Document title: ").strip()
    if not title:
        print("Title is required.")
        return
    url = input("Document URL: ").strip()
    requester = input("Your Slack handle (e.g. @harekas): ").strip()
    approvers_raw = input("Approver handles, space-separated (e.g. @sarah @gerald): ").strip()
    approvers = [h.strip() for h in approvers_raw.split() if h.strip()]
    if not approvers:
        print("At least one approver is required.")
        return
    deadline = input("Deadline (YYYY-MM-DD): ").strip()
    try:
        req = create_request(
            title=title,
            doc_url=url,
            requester=requester,
            approvers=approvers,
            deadline=deadline,
        )
        print(f"\nCreated request: {req['id'][:8]}")
        print(summary_table([req]))
    except ValueError as e:
        print(f"Error: {e}")


def _menu_update() -> None:
    print("\n-- Update approver status --")
    req = _pick_request("Which request?")
    if req is None:
        return
    handle = _pick_approver(req, "Which approver?")
    if handle is None:
        return
    print("\nNew status:")
    print("  1. reviewing")
    print("  2. approved")
    print("  3. blocked")
    status_choice = input("\nEnter number: ").strip()
    status_map = {"1": "reviewing", "2": "approved", "3": "blocked"}
    new_status = status_map.get(status_choice)
    if not new_status:
        print("Invalid selection.")
        return
    note = None
    if new_status == "blocked":
        note = input("Blocker note (optional, press Enter to skip): ").strip() or None
    try:
        updated = update_approver_status(req["id"], handle, new_status, note)
        print(f"\nUpdated {handle} -> {new_status}")
        print(summary_table([updated]))
    except ValueError as e:
        print(f"Error: {e}")


def _menu_reset() -> None:
    print("\n-- Reset request --")
    req = _pick_request("Which request do you want to reset?")
    if req is None:
        return
    confirm = input(f"Reset all approvers on '{req['title']}' back to pending? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return
    try:
        updated = reset_request(req["id"])
        print("\nReset complete.")
        print(summary_table([updated]))
    except ValueError as e:
        print(f"Error: {e}")


def _menu_cancel() -> None:
    print("\n-- Cancel request --")
    all_requests = load_all()
    open_requests = [r for r in all_requests if r["status"] == "open"]
    if not open_requests:
        print("No open requests to cancel.")
        return
    print("\nSelect a request to cancel:")
    for i, req in enumerate(open_requests, 1):
        print(f"  {i}. {req['title']}  (id: {req['id'][:8]})")
    choice = input("\nEnter number: ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(open_requests):
            req = open_requests[idx]
            confirm = input(f"Cancel '{req['title']}'? (y/n): ").strip().lower()
            if confirm == "y":
                cancel_request(req["id"])
                print("Cancelled.")
            else:
                print("Aborted.")
            return
    except ValueError:
        pass
    print("Invalid selection.")


def _menu_audit() -> None:
    print("\n-- View audit trail --")
    all_requests = load_all()
    if not all_requests:
        print("No requests found.")
        return
    print("\nSelect a request:")
    for i, req in enumerate(all_requests, 1):
        print(f"  {i}. {req['title']}  ({req['status']})  id: {req['id'][:8]}")
    choice = input("\nEnter number: ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(all_requests):
            print("\n" + _format_audit_trail(all_requests[idx]))
            return
    except ValueError:
        pass
    print("Invalid selection.")


def run_interactive_menu() -> None:
    """Launch the interactive menu. Runs until the user exits."""
    print("\nAPPROVAL TRACKER")
    print("================")
    while True:
        print("\n1. View dashboard")
        print("2. Create new request")
        print("3. Update approver status")
        print("4. View audit trail")
        print("5. Reset a request")
        print("6. Cancel a request")
        print("0. Exit")
        choice = input("\nChoose an option: ").strip()

        if choice == "1":
            print("\n" + dashboard())
        elif choice == "2":
            _menu_create()
        elif choice == "3":
            _menu_update()
        elif choice == "4":
            _menu_audit()
        elif choice == "5":
            _menu_reset()
        elif choice == "6":
            _menu_cancel()
        elif choice == "0":
            print("Bye.")
            break
        else:
            print("Invalid option, try again.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage approval requests for PRDs, RFCs, and specs. Run with no arguments for interactive mode."
    )
    sub = parser.add_subparsers(dest="command")

    p_create = sub.add_parser("create", help="Create a new approval request.")
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--url", required=True)
    p_create.add_argument("--requester", required=True)
    p_create.add_argument("--approvers", nargs="+", required=True)
    p_create.add_argument("--deadline", required=True)
    p_create.add_argument("--reminder-days", type=int, default=2)

    p_status = sub.add_parser("status", help="Show status of approval requests.")
    p_status.add_argument("--id", help="Show a specific request by ID.")

    sub.add_parser("dashboard", help="Show open requests grouped by urgency.")

    p_update = sub.add_parser("update", help="Update an approver's status.")
    p_update.add_argument("--id", required=True)
    p_update.add_argument("--approver", required=True)
    p_update.add_argument("--status", required=True, choices=["reviewing", "approved", "blocked"])
    p_update.add_argument("--note", default=None)

    p_reset = sub.add_parser("reset", help="Reset all approvers on a request back to pending.")
    p_reset.add_argument("--id", required=True)

    p_cancel = sub.add_parser("cancel", help="Cancel an approval request.")
    p_cancel.add_argument("--id", required=True)

    p_audit = sub.add_parser("audit", help="Show audit trail for a request.")
    p_audit.add_argument("--id", required=True)

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

    # No subcommand — launch interactive menu
    if not args.command:
        run_interactive_menu()
        return

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

    elif args.command == "dashboard":
        print(dashboard())

    elif args.command == "update":
        full_id = _resolve_id(args.id)
        req = update_approver_status(
            request_id=full_id,
            approver_handle=args.approver,
            new_status=args.status,
            note=args.note,
        )
        print(f"Updated {args.approver} -> {args.status}")
        print(summary_table([req]))

    elif args.command == "reset":
        full_id = _resolve_id(args.id)
        req = reset_request(full_id)
        print("Reset complete.")
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
