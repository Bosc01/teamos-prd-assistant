"""Unit tests for src/approval_tracker.py."""

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


def _make_request(**kwargs) -> dict:
    """Helper: build a minimal approval request dict via create_request with mocked I/O."""
    defaults = dict(
        title="Test PRD",
        doc_url="https://example.com/doc",
        requester="@pm",
        approvers=["@alice", "@bob"],
        deadline="2099-12-31",
        reminder_interval_days=2,
    )
    defaults.update(kwargs)

    with tempfile.TemporaryDirectory() as tmp:
        approvals_file = Path(tmp) / "approvals.json"
        with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
            return approval_tracker.create_request(**defaults)


class TestCreateRequest(unittest.TestCase):
    def test_create_request_produces_correct_schema(self) -> None:
        req = _make_request()
        self.assertIn("id", req)
        self.assertEqual(req["title"], "Test PRD")
        self.assertEqual(req["doc_url"], "https://example.com/doc")
        self.assertEqual(req["requester"], "@pm")
        self.assertEqual(req["status"], "open")
        self.assertEqual(req["reminder_interval_days"], 2)
        self.assertEqual(len(req["approvers"]), 2)
        for approver in req["approvers"]:
            self.assertEqual(approver["status"], "pending")
            self.assertIsNone(approver["last_notified_at"])
            self.assertEqual(approver["notification_count"], 0)
        self.assertTrue(len(req["audit_trail"]) >= 1)
        self.assertEqual(req["audit_trail"][0]["event"], "created")

    def test_create_request_persists_to_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                approval_tracker.create_request(
                    title="Persist Test",
                    doc_url="https://example.com",
                    requester="@pm",
                    approvers=["@carol"],
                    deadline="2099-12-31",
                )
                self.assertTrue(approvals_file.exists())
                data = json.loads(approvals_file.read_text())
                self.assertEqual(len(data), 1)
                self.assertEqual(data[0]["title"], "Persist Test")


class TestGetPendingReminders(unittest.TestCase):
    def _setup_file(self, requests_data, tmp_dir) -> Path:
        approvals_file = Path(tmp_dir) / "approvals.json"
        approvals_file.write_text(json.dumps(requests_data))
        return approvals_file

    def test_no_reminders_for_brand_new_request_just_notified(self) -> None:
        now = datetime.now(timezone.utc)
        req = _make_request()
        # Simulate that approver was just notified
        req["approvers"][0]["last_notified_at"] = now.isoformat()
        req["approvers"][0]["notification_count"] = 1
        req["approvers"][1]["last_notified_at"] = now.isoformat()
        req["approvers"][1]["notification_count"] = 1

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            approvals_file.write_text(json.dumps([req]))
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                pairs = approval_tracker.get_pending_reminders(now=now)
        self.assertEqual(pairs, [])

    def test_reminders_returned_after_interval_days_passed(self) -> None:
        now = datetime.now(timezone.utc)
        past = now - timedelta(days=3)
        req = _make_request(reminder_interval_days=2)
        req["approvers"][0]["last_notified_at"] = past.isoformat()

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            approvals_file.write_text(json.dumps([req]))
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                pairs = approval_tracker.get_pending_reminders(now=now)

        handles = [appr["handle"] for _, appr in pairs]
        self.assertIn("@alice", handles)

    def test_approved_approver_not_returned(self) -> None:
        now = datetime.now(timezone.utc)
        req = _make_request()
        req["approvers"][0]["status"] = "approved"
        # No last_notified_at so would normally be included

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            approvals_file.write_text(json.dumps([req]))
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                pairs = approval_tracker.get_pending_reminders(now=now)

        handles = [appr["handle"] for _, appr in pairs]
        self.assertNotIn("@alice", handles)

    def test_no_reminders_for_cancelled_or_complete_requests(self) -> None:
        now = datetime.now(timezone.utc)
        req_cancelled = _make_request()
        req_cancelled["status"] = "cancelled"
        req_complete = _make_request()
        req_complete["status"] = "complete"

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            approvals_file.write_text(json.dumps([req_cancelled, req_complete]))
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                pairs = approval_tracker.get_pending_reminders(now=now)

        self.assertEqual(pairs, [])

    def test_no_reminders_for_past_deadline(self) -> None:
        now = datetime.now(timezone.utc)
        req = _make_request(deadline="2000-01-01")

        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            approvals_file.write_text(json.dumps([req]))
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                pairs = approval_tracker.get_pending_reminders(now=now)

        self.assertEqual(pairs, [])


class TestUpdateApproverStatus(unittest.TestCase):
    def test_all_approved_sets_request_to_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                req = approval_tracker.create_request(
                    title="Complete Test",
                    doc_url="https://example.com",
                    requester="@pm",
                    approvers=["@alice"],
                    deadline="2099-12-31",
                )
                updated = approval_tracker.update_approver_status(
                    req["id"], "@alice", "approved"
                )
                self.assertEqual(updated["status"], "complete")

    def test_partial_approval_keeps_status_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                req = approval_tracker.create_request(
                    title="Partial Test",
                    doc_url="https://example.com",
                    requester="@pm",
                    approvers=["@alice", "@bob"],
                    deadline="2099-12-31",
                )
                updated = approval_tracker.update_approver_status(
                    req["id"], "@alice", "approved"
                )
                self.assertEqual(updated["status"], "open")

    def test_update_logs_to_audit_trail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                req = approval_tracker.create_request(
                    title="Audit Test",
                    doc_url="https://example.com",
                    requester="@pm",
                    approvers=["@alice"],
                    deadline="2099-12-31",
                )
                updated = approval_tracker.update_approver_status(
                    req["id"], "@alice", "reviewing", note="Reading now"
                )
                events = [entry["event"] for entry in updated["audit_trail"]]
                self.assertTrue(any("status_changed:@alice:reviewing" in e for e in events))


class TestRecordNotification(unittest.TestCase):
    def test_increments_count_and_updates_last_notified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                req = approval_tracker.create_request(
                    title="Notify Test",
                    doc_url="https://example.com",
                    requester="@pm",
                    approvers=["@alice"],
                    deadline="2099-12-31",
                )
                updated = approval_tracker.record_notification(req["id"], "@alice")
                approver = next(a for a in updated["approvers"] if a["handle"] == "@alice")
                self.assertEqual(approver["notification_count"], 1)
                self.assertIsNotNone(approver["last_notified_at"])

                # Second notification
                updated2 = approval_tracker.record_notification(req["id"], "@alice")
                approver2 = next(a for a in updated2["approvers"] if a["handle"] == "@alice")
                self.assertEqual(approver2["notification_count"], 2)


class TestSummaryTable(unittest.TestCase):
    def test_summary_table_returns_non_empty_string(self) -> None:
        req = _make_request()
        result = approval_tracker.summary_table([req])
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
        self.assertIn("Test PRD", result)

    def test_summary_table_empty_list(self) -> None:
        result = approval_tracker.summary_table([])
        self.assertIn("No approval requests", result)


class TestResetRequest(unittest.TestCase):
    def test_reset_sets_all_approvers_to_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                req = approval_tracker.create_request(
                    title="Reset Test",
                    doc_url="https://example.com",
                    requester="@pm",
                    approvers=["@alice", "@bob"],
                    deadline="2099-12-31",
                )
                approval_tracker.update_approver_status(req["id"], "@alice", "reviewing")
                approval_tracker.update_approver_status(req["id"], "@bob", "blocked", note="needs info")
                updated = approval_tracker.reset_request(req["id"])

        for approver in updated["approvers"]:
            self.assertEqual(approver["status"], "pending")

    def test_reset_reopens_completed_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                req = approval_tracker.create_request(
                    title="Complete Reset",
                    doc_url="https://example.com",
                    requester="@pm",
                    approvers=["@alice"],
                    deadline="2099-12-31",
                )
                approval_tracker.update_approver_status(req["id"], "@alice", "approved")
                completed = approval_tracker.get_request(req["id"])
                self.assertEqual(completed["status"], "complete")
                updated = approval_tracker.reset_request(req["id"])

        self.assertEqual(updated["status"], "open")

    def test_reset_clears_approver_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                req = approval_tracker.create_request(
                    title="Field Clear Test",
                    doc_url="https://example.com",
                    requester="@pm",
                    approvers=["@alice"],
                    deadline="2099-12-31",
                )
                approval_tracker.update_approver_status(req["id"], "@alice", "blocked", note="some block")
                approval_tracker.record_notification(req["id"], "@alice")
                updated = approval_tracker.reset_request(req["id"])

        approver = updated["approvers"][0]
        self.assertIsNone(approver["status_note"])
        self.assertIsNone(approver["last_notified_at"])
        self.assertEqual(approver["notification_count"], 0)
        self.assertIsNotNone(approver["status_updated_at"])

    def test_reset_sets_completion_notice_sent_to_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                req = approval_tracker.create_request(
                    title="Notice Reset",
                    doc_url="https://example.com",
                    requester="@pm",
                    approvers=["@alice"],
                    deadline="2099-12-31",
                )
                approval_tracker.update_approver_status(req["id"], "@alice", "approved")
                updated = approval_tracker.reset_request(req["id"])

        self.assertFalse(updated["completion_notice_sent"])

    def test_reset_appends_reset_event_to_audit_trail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                req = approval_tracker.create_request(
                    title="Audit Reset",
                    doc_url="https://example.com",
                    requester="@pm",
                    approvers=["@alice"],
                    deadline="2099-12-31",
                )
                updated = approval_tracker.reset_request(req["id"])

        events = [entry["event"] for entry in updated["audit_trail"]]
        self.assertIn("reset", events)

    def test_reset_nonexistent_id_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            approvals_file.write_text("[]")
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                with self.assertRaises(ValueError):
                    approval_tracker.reset_request("nonexistent-id-that-does-not-exist")


if __name__ == "__main__":
    unittest.main()
