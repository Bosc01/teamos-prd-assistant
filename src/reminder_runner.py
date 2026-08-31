"""Run pending approval reminders — designed to be executed on a cron schedule."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import approval_tracker, notifier
from .storage import days_until_deadline, locked, parse_deadline


def run_reminders(dry_run: bool = False, request_id: Optional[str] = None, digest: bool = False) -> None:
    """Process all pending reminders for open approval requests.

    Parameters
    ----------
    dry_run:
        When True, print what would be sent without actually calling notifier functions.
    request_id:
        When provided, only process the request with this ID (or prefix).
    digest:
        When True, batch reminders by approver handle and send one digest message per person.
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
    if digest:
        pending_by_handle: dict[str, list[dict]] = defaultdict(list)
        for req, approver in pending_pairs:
            handle = approver["handle"]
            deadline_str = req.get("deadline", "")
            days_until = days_until_deadline(deadline_str, now=now)
            pending_by_handle[handle].append(
                {
                    "request_id": req["id"],
                    "title": req["title"],
                    "doc_url": req["doc_url"],
                    "deadline": deadline_str,
                    "days_until": days_until,
                    "status": approver.get("status", "pending"),
                    "urgency_note": _digest_urgency_note(days_until, approver),
                }
            )

        for handle, items in pending_by_handle.items():
            if dry_run:
                titles = ", ".join(item["title"] for item in items)
                print(f"[dry-run] Would send digest to {handle} for: {titles}")
                continue

            # send_digest degrades to stdout when SLACK_WEBHOOK_URL is unset,
            # so we always record the notifications regardless of the return value.
            notifier.send_digest(handle, items)
            for item in items:
                approval_tracker.record_notification(item["request_id"], handle)
            reminder_count += len(items)
    else:
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
        deadline_dt = parse_deadline(req.get("deadline"))
        if deadline_dt is None or now <= deadline_dt:
            continue

        has_pending = any(
            a["status"] != "approved" for a in req.get("approvers", [])
        )
        if not has_pending:
            continue

        if _overdue_alert_on_cooldown(req, now):
            continue

        if dry_run:
            print(f"[dry-run] Would send overdue alert for '{req['title']}'")
        else:
            notifier.send_overdue_alert(req)
            approval_tracker.record_overdue_notice(req["id"])
            overdue_count += 1

    # --- completion notices ---
    # A request that completed via update_approver_status has status "complete",
    # so look beyond open requests here.
    completion_count = 0
    completed_or_open = [r for r in all_requests if r.get("status") in ("open", "complete")]
    for req in completed_or_open:
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


def _overdue_alert_on_cooldown(req: dict, now: datetime) -> bool:
    """True while a previously sent overdue alert is still within its cooldown.

    The cooldown reuses the request's reminder interval so a stalled request
    re-alerts at the same cadence as reminders, instead of every cron run.
    """
    last_sent_raw = req.get("overdue_notice_sent_at")
    if not last_sent_raw:
        return False
    try:
        last_sent = datetime.fromisoformat(last_sent_raw)
    except (ValueError, TypeError):
        return False
    if last_sent.tzinfo is None:
        last_sent = last_sent.replace(tzinfo=timezone.utc)
    cooldown_days = int(req.get("reminder_interval_days", 2))
    return (now - last_sent) < timedelta(days=cooldown_days)


def _mark_completion_notice_sent(request_id: str) -> None:
    """Persist the completion_notice_sent flag on the request."""
    with locked(approval_tracker.APPROVALS_FILE):
        all_requests = approval_tracker.load_all()
        for req in all_requests:
            if req["id"] == request_id:
                req["completion_notice_sent"] = True
                break
        approval_tracker.save_all(all_requests)


def _digest_urgency_note(days_until: int | None, approver: dict) -> str:
    count = approver.get("notification_count", 0) + 1
    if count == 1:
        return "A friendly nudge — your review would really help move this forward."
    if count == 2:
        return "This is getting time-sensitive."
    if days_until is None:
        return "⚠️ Urgent — please review as soon as possible."
    if days_until <= 0:
        return "⚠️ This is urgent — the deadline has passed and your approval is still needed."
    return f"⚠️ Urgent — only {days_until} day{'s' if days_until != 1 else ''} left until the deadline."


def main() -> None:
    parser = argparse.ArgumentParser(description="Send pending approval reminders.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be sent without sending.")
    parser.add_argument("--id", default=None, help="Only process the request with this ID (or prefix).")
    parser.add_argument("--digest", action="store_true", help="Batch reminders by approver handle.")
    args = parser.parse_args()
    run_reminders(dry_run=args.dry_run, request_id=args.id, digest=args.digest)


if __name__ == "__main__":
    main()
