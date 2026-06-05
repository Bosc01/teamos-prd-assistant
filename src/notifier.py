"""Send Slack notifications for approval requests and reminders."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Dict, Optional

try:
    import requests as _requests
except ImportError:  # pragma: no cover
    _requests = None  # type: ignore[assignment]

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _days_until(deadline_str: str) -> Optional[int]:
    """Return days until deadline (negative means overdue)."""
    try:
        deadline = date.fromisoformat(deadline_str[:10])
        today = datetime.now(timezone.utc).date()
        return (deadline - today).days
    except (ValueError, TypeError):
        return None


def _deadline_label(deadline_str: str) -> str:
    days = _days_until(deadline_str)
    if days is None:
        return deadline_str
    if days < 0:
        return f"{deadline_str} (OVERDUE by {abs(days)} day{'s' if abs(days) != 1 else ''})"
    if days == 0:
        return f"{deadline_str} (TODAY)"
    return f"{deadline_str} ({days} day{'s' if days != 1 else ''} from now)"


def _status_icon(status: str) -> str:
    return {"approved": "✓", "pending": "⏳", "reviewing": "🔍", "blocked": "🚫"}.get(status, status)


def _post_to_slack(text: str) -> bool:
    """Send *text* to the configured Slack webhook. Return True on success."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        print("[notifier] SLACK_WEBHOOK_URL is not set — printing message to stdout instead.")
        print(text)
        return False

    if _requests is None:  # pragma: no cover
        print("[notifier] 'requests' package is not installed.")
        print(text)
        return False

    try:
        response = _requests.post(webhook_url, json={"text": text}, timeout=10)
        response.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[notifier] Failed to send Slack notification: {exc}")
        print(text)
        return False


def send_approval_request(request: Dict, approver: Dict) -> bool:
    """Send initial approval-request notification to a single approver."""
    req_id_short = request["id"][:8]
    handle = approver["handle"]
    deadline_label = _deadline_label(request.get("deadline", ""))

    text = (
        f"*Approval Request: {request['title']}*\n\n"
        f"*Requested by:* {request['requester']}\n"
        f"*Document:* {request['doc_url']}\n"
        f"*Deadline:* {deadline_label}\n\n"
        f"You've been added as an approver. Please review and reply with your decision.\n\n"
        f"To update your status, run:\n"
        f"  `python src/approval_tracker.py update --id {req_id_short} --approver {handle} --status reviewing`\n"
        f"  `python src/approval_tracker.py update --id {req_id_short} --approver {handle} --status approved`\n\n"
        f"Or reply in this thread with your status."
    )
    return _post_to_slack(text)


def send_reminder(request: Dict, approver: Dict) -> bool:
    """Send a reminder to a pending/reviewing/blocked approver."""
    req_id_short = request["id"][:8]
    handle = approver["handle"]
    count = approver.get("notification_count", 0) + 1
    status = approver.get("status", "pending")
    status_display = f"{_status_icon(status)} {status}"
    deadline_label = _deadline_label(request.get("deadline", ""))
    days = _days_until(request.get("deadline", ""))

    if count == 1:
        urgency_note = "A friendly nudge — your review would really help move this forward."
    elif count == 2:
        urgency_note = (
            f"This is getting time-sensitive. Deadline: {request.get('deadline', '')}."
        )
    else:
        if days is not None and days <= 0:
            urgency_note = "⚠️ This is urgent — the deadline has passed and your approval is still needed."
        elif days is not None:
            urgency_note = f"⚠️ Urgent — only {days} day{'s' if days != 1 else ''} left until the deadline."
        else:
            urgency_note = "⚠️ Urgent — please review as soon as possible."

    note_line = ""
    if approver.get("status_note"):
        note_line = f"*Your note:* {approver['status_note']}\n"

    text = (
        f"*⏰ Reminder #{count}: Approval needed — {request['title']}*\n\n"
        f"*Your status:* {status_display}\n"
        f"{note_line}"
        f"*Deadline:* {deadline_label}\n"
        f"*Document:* {request['doc_url']}\n\n"
        f"{urgency_note}\n\n"
        f"To update: `python src/approval_tracker.py update --id {req_id_short} --approver {handle} --status approved`"
    )
    return _post_to_slack(text)


def send_completion_notice(request: Dict) -> bool:
    """Send a notification to the requester that all approvals are in."""
    approver_list = "  ".join(
        f"{a['handle']} ✓" for a in request.get("approvers", [])
    )
    count = len(request.get("approvers", []))
    completed_date = datetime.now(timezone.utc).date().isoformat()

    text = (
        f"*✅ All approvals received: {request['title']}*\n\n"
        f"All {count} approver{'s' if count != 1 else ''} have approved. You're clear to proceed.\n\n"
        f"*Approvers:* {approver_list}\n"
        f"*Completed:* {completed_date}"
    )
    return _post_to_slack(text)


def send_overdue_alert(request: Dict) -> bool:
    """Send alert to requester when deadline passes with pending approvals."""
    pending_lines = []
    for approver in request.get("approvers", []):
        if approver["status"] != "approved":
            icon = _status_icon(approver["status"])
            note = approver.get("status_note")
            note_str = f' — "{note}"' if note else ""
            count = approver.get("notification_count", 0)
            pending_lines.append(
                f"- {approver['handle']}: {icon} {approver['status']} (notified {count} time{'s' if count != 1 else ''}){note_str}"
            )

    pending_str = "\n".join(pending_lines) if pending_lines else "  (none)"
    text = (
        f"*🚨 Overdue: {request['title']}*\n\n"
        f"Deadline was {request.get('deadline', 'unknown')}. Still waiting on:\n"
        f"{pending_str}"
    )
    return _post_to_slack(text)
