"""Unit tests for the interactive menu functions in src/approval_tracker.py."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import approval_tracker


def _write_open_request(approvals_file: Path, title: str = "Test PRD") -> dict:
    """Create and persist a minimal open request, return the dict."""
    with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
        return approval_tracker.create_request(
            title=title,
            doc_url="https://example.com/doc",
            requester="@pm",
            approvers=["@alice", "@bob"],
            deadline="2099-12-31",
        )


class TestMenuCreate(unittest.TestCase):
    def test_menu_create_creates_request_with_valid_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            approvals_file.write_text("[]")

            inputs = iter(["My Feature PRD", "https://docs.example.com", "@pm", "@alice @bob", "2099-12-31"])
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                with mock.patch("builtins.input", side_effect=inputs):
                    with mock.patch("builtins.print"):
                        approval_tracker._menu_create()

                reqs = approval_tracker.load_all()
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["title"], "My Feature PRD")

    def test_menu_create_prints_error_when_title_empty(self) -> None:
        printed: list[str] = []

        inputs = iter([""])  # empty title
        with mock.patch("builtins.input", side_effect=inputs):
            with mock.patch("builtins.print", side_effect=lambda *a, **k: printed.append(str(a[0]) if a else "")):
                approval_tracker._menu_create()

        self.assertTrue(any("required" in line.lower() for line in printed))

    def test_menu_create_prints_error_when_no_approvers(self) -> None:
        printed: list[str] = []

        inputs = iter(["My PRD", "https://example.com", "@pm", "   ", "2099-12-31"])
        with mock.patch("builtins.input", side_effect=inputs):
            with mock.patch("builtins.print", side_effect=lambda *a, **k: printed.append(str(a[0]) if a else "")):
                approval_tracker._menu_create()

        self.assertTrue(any("approver" in line.lower() for line in printed))


class TestMenuUpdate(unittest.TestCase):
    def test_menu_update_successfully_updates_approver_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            req = _write_open_request(approvals_file)

            # Input sequence: select request (1), select approver (1), select status (1 = reviewing)
            inputs = iter(["1", "1", "1"])
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                with mock.patch("builtins.input", side_effect=inputs):
                    with mock.patch("builtins.print"):
                        approval_tracker._menu_update()

                updated = approval_tracker.get_request(req["id"])

        alice = next(a for a in updated["approvers"] if a["handle"] == "@alice")
        self.assertEqual(alice["status"], "reviewing")

    def test_menu_update_handles_blocked_status_with_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            req = _write_open_request(approvals_file)

            # Select request (1), approver (1), status (3 = blocked), note
            inputs = iter(["1", "1", "3", "Need PLC input"])
            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                with mock.patch("builtins.input", side_effect=inputs):
                    with mock.patch("builtins.print"):
                        approval_tracker._menu_update()

                updated = approval_tracker.get_request(req["id"])

        alice = next(a for a in updated["approvers"] if a["handle"] == "@alice")
        self.assertEqual(alice["status"], "blocked")
        self.assertEqual(alice["status_note"], "Need PLC input")


class TestMenuReset(unittest.TestCase):
    def test_menu_reset_resets_request_when_user_confirms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            req = _write_open_request(approvals_file)

            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                # First set an approver to reviewing
                approval_tracker.update_approver_status(req["id"], "@alice", "reviewing")

                # Select request (1), confirm reset (y)
                inputs = iter(["1", "y"])
                with mock.patch("builtins.input", side_effect=inputs):
                    with mock.patch("builtins.print"):
                        approval_tracker._menu_reset()

                updated = approval_tracker.get_request(req["id"])

        for approver in updated["approvers"]:
            self.assertEqual(approver["status"], "pending")

    def test_menu_reset_does_nothing_when_user_cancels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            approvals_file = Path(tmp) / "approvals.json"
            req = _write_open_request(approvals_file)

            with mock.patch.object(approval_tracker, "APPROVALS_FILE", approvals_file):
                approval_tracker.update_approver_status(req["id"], "@alice", "reviewing")

                # Select request (1), cancel (n)
                inputs = iter(["1", "n"])
                with mock.patch("builtins.input", side_effect=inputs):
                    with mock.patch("builtins.print"):
                        approval_tracker._menu_reset()

                updated = approval_tracker.get_request(req["id"])

        alice = next(a for a in updated["approvers"] if a["handle"] == "@alice")
        self.assertEqual(alice["status"], "reviewing")


class TestRunInteractiveMenu(unittest.TestCase):
    def test_run_interactive_menu_exits_on_zero(self) -> None:
        printed: list[str] = []

        with mock.patch("builtins.input", return_value="0"):
            with mock.patch("builtins.print", side_effect=lambda *a, **k: printed.append(str(a[0]) if a else "")):
                approval_tracker.run_interactive_menu()

        self.assertTrue(any("Bye" in line or "bye" in line for line in printed))

    def test_run_interactive_menu_calls_dashboard_on_one(self) -> None:
        printed: list[str] = []

        # First iteration: choose 1 (dashboard), second: choose 0 (exit)
        inputs = iter(["1", "0"])
        with mock.patch("builtins.input", side_effect=inputs):
            with mock.patch("builtins.print", side_effect=lambda *a, **k: printed.append(str(a[0]) if a else "")):
                with mock.patch.object(approval_tracker, "dashboard", return_value="DASHBOARD OUTPUT") as mock_dashboard:
                    approval_tracker.run_interactive_menu()

        mock_dashboard.assert_called_once()


if __name__ == "__main__":
    unittest.main()
