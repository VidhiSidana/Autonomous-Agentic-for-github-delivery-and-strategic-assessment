"""
Tests for agent.policy (Samsung PRISM).
"""

import tempfile
import unittest
from pathlib import Path

from agent.policy import authorize_binary_path, redact_secrets, write_audit_event


class TestPolicyAndAudit(unittest.TestCase):

    def test_redact_secrets(self):
        text = "host=localhost\npassword=MySuperSecretPassword123\nport=5432"
        redacted = redact_secrets(text)
        self.assertNotIn("MySuperSecretPassword123", redacted)
        self.assertIn("password=[REDACTED]", redacted)
        self.assertIn("host=localhost", redacted)

    def test_authorize_empty_or_traversal_path(self):
        ok, msg = authorize_binary_path("")
        self.assertFalse(ok)
        self.assertIn("empty", msg.lower())

        ok, msg = authorize_binary_path("../../../etc/shadow")
        self.assertFalse(ok)
        self.assertIn("traversal", msg.lower())

    def test_reject_symlink_escaping_allowlist(self):
        with tempfile.TemporaryDirectory() as allowed_dir, tempfile.TemporaryDirectory() as outside_dir:
            allowed_path = Path(allowed_dir).resolve()
            outside_path = Path(outside_dir).resolve()

            # Create an outside file
            secret_file = outside_path / "secret.exe"
            secret_file.write_text("MZ...", encoding="utf-8")

            # Create a symlink inside allowed pointing to outside file
            symlink_file = allowed_path / "symlink.exe"
            symlink_file.symlink_to(secret_file)

            # Set allowed dirs to allowed_path
            import config.settings
            orig_allowed = config.settings.BINARY_ALLOWED_DIRS
            config.settings.BINARY_ALLOWED_DIRS = [allowed_path]

            try:
                ok, msg = authorize_binary_path(str(symlink_file))
                self.assertFalse(ok)
                self.assertIn("Access denied", msg)
            finally:
                config.settings.BINARY_ALLOWED_DIRS = orig_allowed

    def test_audit_event_logging(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "test_audit.log"
            # Monkeypatch log path for test
            import agent.policy
            orig_get = agent.policy._get_audit_log_path
            agent.policy._get_audit_log_path = lambda: log_path

            try:
                write_audit_event(
                    operation="test_op",
                    target_path="/test/file.exe",
                    authorized=True,
                    result_status="SUCCESS",
                    session_id="sess_123",
                    extra="token=secret123",
                )
                self.assertTrue(log_path.exists())
                content = log_path.read_text(encoding="utf-8")
                self.assertIn("test_op", content)
                self.assertIn("sess_123", content)
                self.assertNotIn("secret123", content)  # redacted extra
            finally:
                agent.policy._get_audit_log_path = orig_get


if __name__ == "__main__":
    unittest.main()

