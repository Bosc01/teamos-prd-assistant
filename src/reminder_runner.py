"""Run pending approval reminders — designed to be executed on a cron schedule."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import approval_tracker  # noqa: E402
import notifier  # noqa: E402


def run_reminders(dry_run: bool = False, request_id: Optional[str] = None) -> None:
    """Process all pending reminders for open approval requests.

    Parameters
    ----------
    dry_run:
        When True, print what would be sent without actually calling notifier functions.
    request_id:
        When provided, only process the request with this ID (or prefix).
    """
    now = datetime.now(timezone.utc)

    all_requests = approval_tracker.load_all()

    if request_id:
        # Resolve prefix to full ID
        matches = [r for r in all_requests if r["id"].startswith(request_id)]
        if not matches:
            print(f"No request found with id prefix: {request_id}")
            return
        if len(matches) > 1:
            print(f"Ambiguous id prefix '{request_id}' matches: {[r['id'] for r in matches]}")
            return
        all_requests = matches

    open_requests = [r for r in all_requests if r.get("status") == "open"]

    # --- reminders for due approvers ---
    pending_pairs = approval_tracker.get_pending_reminders(now=now)
    if request_id:
        # Filter pairs to only the specified request
        full_id = all_requests[0]["id"]
        pending_pairs = [(req, appr) for req, appr in pending_pairs if req["id"] == full_id]

    reminder_count = 0
    for req, approver in pending_pairs:
        handle = approver["handle"]
        title = req["title"]
        if dry_run:
            print(f"[dry-run] Would notify {handle} on '{title}'")
        else:
            # send_reminder degrades to stdout when SLACK_WEBHOOK_URL is unset,
            # so we always record the notification regardless of the return value.
            notifier.send_reminder(req, approver)
            approval_tracker.record_notification(req["id"], handle)
            reminder_count += 1

    # --- overdue alerts ---
    overdue_count = 0
    for req in open_requests:
        deadline_str = req.get("deadline", "")
        try:
            deadline_dt = datetime.fromisoformat(deadline_str)
            if deadline_dt.tzinfo is None:
                deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        if now <= deadline_dt:
            continue

        has_pending = any(
            a["status"] != "approved" for a in req.get("approvers", [])
        )
        if not has_pending:
            continue

        if dry_run:
            print(f"[dry-run] Would send overdue alert for '{req['title']}'")
        else:
            notifier.send_overdue_alert(req)
            overdue_count += 1

    # --- completion notices ---
    completion_count = 0
    for req in open_requests:
        all_approved = req.get("approvers") and all(
            a["status"] == "approved" for a in req["approvers"]
        )
        if not all_approved:
            continue
        if req.get("completion_notice_sent"):
            continue

        if dry_run:
            print(f"[dry-run] Would send completion notice for '{req['title']}'")
        else:
            notifier.send_completion_notice(req)
            # Mark so we don't re-send on subsequent cron runs
            _mark_completion_notice_sent(req["id"])
            completion_count += 1

    if dry_run:
        print(
            f"[dry-run] Summary: {len(pending_pairs)} reminder(s) pending, "
            f"{overdue_count} overdue alert(s), {completion_count} completion notice(s)."
        )
    else:
        print(
            f"Sent {reminder_count} reminder(s), {overdue_count} overdue alert(s), "
            f"{completion_count} completion notice(s)."
        )


def _mark_completion_notice_sent(request_id: str) -> None:
    """Persist the completion_notice_sent flag on the request."""
    all_requests = approval_tracker.load_all()
    for req in all_requests:
        if req["id"] == request_id:
            req["completion_notice_sent"] = True
            break
    approval_tracker.save_all(all_requests)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send pending approval reminders.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be sent without sending.")
    parser.add_argument("--id", default=None, help="Only process the request with this ID (or prefix).")
    args = parser.parse_args()
    run_reminders(dry_run=args.dry_run, request_id=args.id)


if __name__ == "__main__":
    main()
