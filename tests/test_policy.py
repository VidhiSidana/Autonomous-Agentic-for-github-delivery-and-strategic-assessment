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

