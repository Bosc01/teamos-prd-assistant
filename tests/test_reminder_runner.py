"""Unit tests for src/reminder_runner.py."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import approval_tracker
import reminder_runner


def _write_approvals(tmp_dir: str, data: list) -> Path:
    approvals_file = Path(tmp_dir) / "approvals.json"
    approvals_file.write_text(json.dumps(data))
    return approvals_file


def _open_request(
    title: str = "Test PRD",
    deadline: str = "2099-12-31",
    approver_statuses: list | None = None,
    reminder_interval_days: int = 2,
    completion_notice_sent: bool = False,
) -> dict:
    """Build a minimal open request dict."""
    import uuid

    approver_statuses = approver_statuses or [("@alice", "pending")]
    return {
        "id": str(uuid.uuid4()),
        "title": title,
        "doc_url": "https://example.com/doc",
        "requester": "@pm",
        "deadline": deadline,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reminder_interval_days": reminder_interval_days,
        "status": "open",
        "completion_notice_sent": completion_notice_sent,
        "approvers": [
            {
                "handle": handle,
                "status": status,
                "status_note": None,
                "status_updated_at": None,
                "last_notified_at": None,
                "notification_count": 0,
            }
            for handle, status in approver_statuses
        ],
        "audit_trail": [],
    }


class TestDryRun(unittest.TestCase):
    def test_dry_run_prints_but_does_not_call_notifier(self) -> None:
        req = _open_request()

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = _write_approvals(tmp, [req])
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                with mock.patch("reminder_runner.notifier") as mock_notifier:
                    with mock.patch("builtins.print") as mock_print:
                        reminder_runner.run_reminders(dry_run=True)

        mock_notifier.send_reminder.assert_not_called()
        mock_notifier.send_overdue_alert.assert_not_called()
        mock_notifier.send_completion_notice.assert_not_called()
        mock_print.assert_called()

    def test_dry_run_prints_would_notify_message(self) -> None:
        req = _open_request(approver_statuses=[("@alice", "pending")])

        printed_lines: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = _write_approvals(tmp, [req])
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                with mock.patch("reminder_runner.notifier"):
                    with mock.patch("builtins.print", side_effect=lambda *a, **k: printed_lines.append(str(a[0]) if a else "")):
                        reminder_runner.run_reminders(dry_run=True)

        self.assertTrue(any("Would notify" in line for line in printed_lines))


class TestOverdueAlert(unittest.TestCase):
    def test_past_deadline_triggers_overdue_alert(self) -> None:
        past_deadline = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
        req = _open_request(deadline=past_deadline)

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = _write_approvals(tmp, [req])
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                with mock.patch("reminder_runner.notifier") as mock_notifier:
                    mock_notifier.send_reminder.return_value = True
                    mock_notifier.send_overdue_alert.return_value = True
                    mock_notifier.send_completion_notice.return_value = True
                    with mock.patch("builtins.print"):
                        reminder_runner.run_reminders()

        mock_notifier.send_overdue_alert.assert_called_once()

    def test_future_deadline_does_not_trigger_overdue_alert(self) -> None:
        req = _open_request(deadline="2099-12-31")

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = _write_approvals(tmp, [req])
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                with mock.patch("reminder_runner.notifier") as mock_notifier:
                    mock_notifier.send_reminder.return_value = True
                    mock_notifier.send_overdue_alert.return_value = True
                    mock_notifier.send_completion_notice.return_value = True
                    with mock.patch("builtins.print"):
                        reminder_runner.run_reminders()

        mock_notifier.send_overdue_alert.assert_not_called()


class TestCompletionNotice(unittest.TestCase):
    def test_all_approved_triggers_completion_notice(self) -> None:
        req = _open_request(approver_statuses=[("@alice", "approved"), ("@bob", "approved")])

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = _write_approvals(tmp, [req])
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                with mock.patch("reminder_runner.notifier") as mock_notifier:
                    mock_notifier.send_reminder.return_value = True
                    mock_notifier.send_overdue_alert.return_value = True
                    mock_notifier.send_completion_notice.return_value = True
                    with mock.patch("builtins.print"):
                        reminder_runner.run_reminders()

        mock_notifier.send_completion_notice.assert_called_once()

    def test_completion_notice_not_sent_twice(self) -> None:
        req = _open_request(
            approver_statuses=[("@alice", "approved")],
            completion_notice_sent=True,
        )

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = _write_approvals(tmp, [req])
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                with mock.patch("reminder_runner.notifier") as mock_notifier:
                    mock_notifier.send_completion_notice.return_value = True
                    with mock.patch("builtins.print"):
                        reminder_runner.run_reminders()

        mock_notifier.send_completion_notice.assert_not_called()


class TestFilterById(unittest.TestCase):
    def test_run_reminders_with_id_only_processes_that_request(self) -> None:
        req1 = _open_request(title="PRD One")
        req2 = _open_request(title="PRD Two")

        notified_titles: list[str] = []

        def fake_send_reminder(req, approver):
            notified_titles.append(req["title"])
            return True

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = _write_approvals(tmp, [req1, req2])
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                with mock.patch("reminder_runner.notifier") as mock_notifier:
                    mock_notifier.send_reminder.side_effect = fake_send_reminder
                    mock_notifier.send_overdue_alert.return_value = True
                    mock_notifier.send_completion_notice.return_value = True
                    with mock.patch("builtins.print"):
                        # Use first 8 chars of req1's id
                        reminder_runner.run_reminders(request_id=req1["id"][:8])

        self.assertIn("PRD One", notified_titles)
        self.assertNotIn("PRD Two", notified_titles)


class TestDigestMode(unittest.TestCase):
    def test_run_reminders_digest_groups_by_approver(self) -> None:
        req1 = _open_request(title="PRD One", approver_statuses=[("@alice", "pending"), ("@bob", "pending")])
        req2 = _open_request(title="PRD Two", approver_statuses=[("@alice", "pending")])

        digest_calls: list[tuple[str, list[dict]]] = []
        recorded_notifications: list[tuple[str, str]] = []

        def fake_send_digest(handle, items):
            digest_calls.append((handle, items))
            return True

        def fake_record_notification(request_id, handle):
            recorded_notifications.append((request_id, handle))
            return {}

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = _write_approvals(tmp, [req1, req2])
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                with mock.patch("reminder_runner.notifier") as mock_notifier:
                    mock_notifier.send_digest.side_effect = fake_send_digest
                    mock_notifier.send_reminder.return_value = True
                    mock_notifier.send_overdue_alert.return_value = True
                    mock_notifier.send_completion_notice.return_value = True
                    with mock.patch.object(approval_tracker, "record_notification", side_effect=fake_record_notification):
                        with mock.patch("builtins.print"):
                            reminder_runner.run_reminders(digest=True)

        self.assertEqual(len(digest_calls), 2)
        handles = {handle for handle, _ in digest_calls}
        self.assertEqual(handles, {"@alice", "@bob"})
        self.assertGreaterEqual(len(recorded_notifications), 3)

    def test_digest_dry_run_prints_grouped_output(self) -> None:
        req = _open_request(title="PRD Digest", approver_statuses=[("@alice", "pending"), ("@bob", "pending")])

        printed_lines: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = _write_approvals(tmp, [req])
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                with mock.patch("reminder_runner.notifier"):
                    with mock.patch("builtins.print", side_effect=lambda *a, **k: printed_lines.append(str(a[0]) if a else "")):
                        reminder_runner.run_reminders(dry_run=True, digest=True)

        self.assertTrue(any("Would send digest" in line for line in printed_lines))


class TestStateAwareReminders(unittest.TestCase):
    def test_reviewing_approver_not_in_pending_reminders(self) -> None:
        req = _open_request(approver_statuses=[("@alice", "reviewing")])

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = _write_approvals(tmp, [req])
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                with mock.patch("reminder_runner.notifier") as mock_notifier:
                    mock_notifier.send_reminder.return_value = True
                    mock_notifier.send_reviewing_notice.return_value = True
                    with mock.patch("builtins.print"):
                        reminder_runner.run_reminders()

        mock_notifier.send_reminder.assert_not_called()

    def test_blocked_approver_not_in_pending_reminders(self) -> None:
        req = _open_request(approver_statuses=[("@alice", "blocked")])

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = _write_approvals(tmp, [req])
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                with mock.patch("reminder_runner.notifier") as mock_notifier:
                    mock_notifier.send_reminder.return_value = True
                    mock_notifier.send_blocked_notice.return_value = True
                    with mock.patch("builtins.print"):
                        reminder_runner.run_reminders()

        mock_notifier.send_reminder.assert_not_called()

    def test_reviewing_dry_run_prints_requester_notice(self) -> None:
        req = _open_request(approver_statuses=[("@alice", "reviewing")])

        printed_lines: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = _write_approvals(tmp, [req])
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                with mock.patch("reminder_runner.notifier"):
                    with mock.patch("builtins.print", side_effect=lambda *a, **k: printed_lines.append(str(a[0]) if a else "")):
                        reminder_runner.run_reminders(dry_run=True)

        self.assertTrue(any("reviewing" in line for line in printed_lines))

    def test_blocked_dry_run_prints_requester_notice_with_note(self) -> None:
        req = _open_request(approver_statuses=[("@alice", "blocked")])
        req["approvers"][0]["status_note"] = "Need PLC guidance"

        printed_lines: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = _write_approvals(tmp, [req])
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                with mock.patch("reminder_runner.notifier"):
                    with mock.patch("builtins.print", side_effect=lambda *a, **k: printed_lines.append(str(a[0]) if a else "")):
                        reminder_runner.run_reminders(dry_run=True)

        self.assertTrue(any("blocked" in line for line in printed_lines))


if __name__ == "__main__":
    unittest.main()
