"""Command-line and interactive-menu front end for the approval tracker.

Domain logic lives in approval_tracker; this module only collects input and
prints results, so the tracker itself stays testable without stdin.
"""

from __future__ import annotations

import argparse
from typing import Dict, List, Optional

from . import approval_tracker
from .storage import STATUS_ICONS

# ---------------------------------------------------------------------------
# Interactive pickers
# ---------------------------------------------------------------------------

def _pick_request(prompt: str = "Select a request") -> Optional[Dict]:
    """Show numbered list of open requests and return the one the user picks."""
    all_requests = approval_tracker.load_all()
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
        icon = STATUS_ICONS.get(a["status"], "?")
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
        req = approval_tracker.create_request(
            title=title,
            doc_url=url,
            requester=requester,
            approvers=approvers,
            deadline=deadline,
        )
        print(f"\nCreated request: {req['id'][:8]}")
        print(approval_tracker.summary_table([req]))
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
        updated = approval_tracker.update_approver_status(req["id"], handle, new_status, note)
        print(f"\nUpdated {handle} -> {new_status}")
        print(approval_tracker.summary_table([updated]))
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
        updated = approval_tracker.reset_request(req["id"])
        print("\nReset complete.")
        print(approval_tracker.summary_table([updated]))
    except ValueError as e:
        print(f"Error: {e}")


def _menu_cancel() -> None:
    print("\n-- Cancel request --")
    all_requests = approval_tracker.load_all()
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
                approval_tracker.cancel_request(req["id"])
                print("Cancelled.")
            else:
                print("Aborted.")
            return
    except ValueError:
        pass
    print("Invalid selection.")


def _menu_audit() -> None:
    print("\n-- View audit trail --")
    all_requests = approval_tracker.load_all()
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
            print("\n" + approval_tracker._format_audit_trail(all_requests[idx]))
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
            print("\n" + approval_tracker.dashboard())
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
# Argparse CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.approval_tracker",
        description="Manage approval requests for PRDs, RFCs, and specs. Run with no arguments for interactive mode.",
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
    all_requests = approval_tracker.load_all()
    matches = [r["id"] for r in all_requests if r["id"].startswith(partial_id)]
    if not matches:
        raise ValueError(f"No request found matching id prefix: {partial_id}")
    if len(matches) > 1:
        raise ValueError(f"Ambiguous id prefix '{partial_id}' matches: {matches}")
    return matches[0]


def main(argv: Optional[List[str]] = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # No subcommand — launch interactive menu
    if not args.command:
        run_interactive_menu()
        return

    if args.command == "create":
        req = approval_tracker.create_request(
            title=args.title,
            doc_url=args.url,
            requester=args.requester,
            approvers=args.approvers,
            deadline=args.deadline,
            reminder_interval_days=args.reminder_days,
        )
        print(f"Created request: {req['id']}")
        print(approval_tracker.summary_table([req]))

    elif args.command == "status":
        if args.id:
            full_id = _resolve_id(args.id)
            req = approval_tracker.get_request(full_id)
            print(approval_tracker.summary_table([req]))
        else:
            all_requests = approval_tracker.load_all()
            if not all_requests:
                print("No approval requests found.")
            else:
                print(approval_tracker.summary_table(all_requests))

    elif args.command == "dashboard":
        print(approval_tracker.dashboard())

    elif args.command == "update":
        full_id = _resolve_id(args.id)
        req = approval_tracker.update_approver_status(
            request_id=full_id,
            approver_handle=args.approver,
            new_status=args.status,
            note=args.note,
        )
        print(f"Updated {args.approver} -> {args.status}")
        print(approval_tracker.summary_table([req]))

    elif args.command == "reset":
        full_id = _resolve_id(args.id)
        req = approval_tracker.reset_request(full_id)
        print("Reset complete.")
        print(approval_tracker.summary_table([req]))

    elif args.command == "cancel":
        full_id = _resolve_id(args.id)
        req = approval_tracker.cancel_request(full_id)
        print(f"Cancelled request: {req['id']}")

    elif args.command == "audit":
        full_id = _resolve_id(args.id)
        req = approval_tracker.get_request(full_id)
        print(approval_tracker._format_audit_trail(req))


if __name__ == "__main__":
    main()
