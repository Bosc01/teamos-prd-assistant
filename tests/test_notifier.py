"""Unit tests for src/notifier.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import notifier


def _make_request(deadline: str = "2099-12-31") -> dict:
    return {
        "id": "abc12345-0000-0000-0000-000000000000",
        "title": "Terraform Actions PRD v2",
        "doc_url": "https://hermes.example.com/docs/abc123",
        "requester": "@harekas",
        "deadline": deadline,
        "approvers": [
            {"handle": "@steve", "status": "pending", "status_note": None, "notification_count": 0},
            {"handle": "@garvita", "status": "approved", "status_note": None, "notification_count": 1},
        ],
    }


def _make_approver(status: str = "pending", count: int = 0, note: str | None = None) -> dict:
    return {
        "handle": "@steve",
        "status": status,
        "status_note": note,
        "notification_count": count,
        "last_notified_at": None,
    }


class TestSendReminderNoWebhook(unittest.TestCase):
    def test_send_reminder_without_webhook_prints_to_stdout_and_returns_false(self) -> None:
        req = _make_request()
        approver = _make_approver()

        with mock.patch.dict("os.environ", {"SLACK_WEBHOOK_URL": ""}):
            with mock.patch("builtins.print") as mock_print:
                result = notifier.send_reminder(req, approver)

        self.assertFalse(result)
        # Should have printed something
        self.assertTrue(mock_print.called)


class TestSendReminderWithWebhook(unittest.TestCase):
    def test_send_reminder_calls_requests_post_with_json(self) -> None:
        req = _make_request()
        approver = _make_approver(count=0)

        mock_response = mock.MagicMock()
        mock_response.raise_for_status.return_value = None

        with mock.patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
            with mock.patch("notifier._requests") as mock_requests_mod:
                mock_requests_mod.post.return_value = mock_response
                result = notifier.send_reminder(req, approver)

        self.assertTrue(result)
        mock_requests_mod.post.assert_called_once()
        call_kwargs = mock_requests_mod.post.call_args
        self.assertIn("json", call_kwargs.kwargs if call_kwargs.kwargs else {})
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        self.assertIn("text", payload)
        self.assertIn("Reminder #1", payload["text"])

    def test_send_reminder_returns_false_on_http_error(self) -> None:
        req = _make_request()
        approver = _make_approver()

        import requests as real_requests

        with mock.patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
            with mock.patch("notifier._requests") as mock_requests_mod:
                mock_requests_mod.post.side_effect = real_requests.exceptions.HTTPError("500 error")
                with mock.patch("builtins.print"):
                    result = notifier.send_reminder(req, approver)

        self.assertFalse(result)


class TestSendReminderUrgency(unittest.TestCase):
    def _get_message_text(self, count: int, deadline: str = "2099-12-31") -> str:
        req = _make_request(deadline=deadline)
        approver = _make_approver(count=count)
        mock_response = mock.MagicMock()
        mock_response.raise_for_status.return_value = None

        with mock.patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
            with mock.patch("notifier._requests") as mock_requests_mod:
                mock_requests_mod.post.return_value = mock_response
                notifier.send_reminder(req, approver)
                call_kwargs = mock_requests_mod.post.call_args
                payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
                return payload["text"]

    def test_count_1_message_contains_reminder_1(self) -> None:
        text = self._get_message_text(count=0)  # count+1 = 1
        self.assertIn("Reminder #1", text)

    def test_count_3_message_contains_urgent(self) -> None:
        text = self._get_message_text(count=2)  # count+1 = 3
        self.assertIn("Urgent", text)

    def test_count_2_message_shows_deadline(self) -> None:
        text = self._get_message_text(count=1)  # count+1 = 2
        self.assertIn("2099-12-31", text)


class TestSendCompletionNotice(unittest.TestCase):
    def test_sends_completion_notice(self) -> None:
        req = _make_request()
        req["approvers"] = [
            {"handle": "@steve", "status": "approved"},
            {"handle": "@garvita", "status": "approved"},
        ]
        mock_response = mock.MagicMock()
        mock_response.raise_for_status.return_value = None

        with mock.patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
            with mock.patch("notifier._requests") as mock_requests_mod:
                mock_requests_mod.post.return_value = mock_response
                result = notifier.send_completion_notice(req)

        self.assertTrue(result)
        call_kwargs = mock_requests_mod.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        self.assertIn("All approvals received", payload["text"])
        self.assertIn("@steve", payload["text"])


class TestSendOverdueAlert(unittest.TestCase):
    def test_sends_overdue_alert_with_pending_approvers(self) -> None:
        req = _make_request(deadline="2000-01-01")
        req["approvers"] = [
            {"handle": "@steve", "status": "pending", "status_note": None, "notification_count": 3},
            {"handle": "@garvita", "status": "blocked", "status_note": "waiting on security", "notification_count": 2},
        ]
        mock_response = mock.MagicMock()
        mock_response.raise_for_status.return_value = None

        with mock.patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
            with mock.patch("notifier._requests") as mock_requests_mod:
                mock_requests_mod.post.return_value = mock_response
                result = notifier.send_overdue_alert(req)

        self.assertTrue(result)
        call_kwargs = mock_requests_mod.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        self.assertIn("Overdue", payload["text"])
        self.assertIn("@steve", payload["text"])
        self.assertIn("@garvita", payload["text"])


if __name__ == "__main__":
    unittest.main()
