"""
Tests for agent.policy (Samsung PRISM).
Covers path authorization security, directory traversal defense, symlink
escape prevention, sibling directory isolation, secret redaction, and audit logging.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config.settings
from agent.policy import authorize_binary_path, authorize_rea_tool_call, redact_secrets, write_audit_event


class TestPolicyAndAudit(unittest.TestCase):

    def test_redact_secrets(self):
        text = "host=localhost\npassword=MySuperSecretPassword123\nport=5432"
        redacted = redact_secrets(text)
        self.assertNotIn("MySuperSecretPassword123", redacted)
        self.assertIn("password=[REDACTED]", redacted)
        self.assertIn("host=localhost", redacted)

    def test_authorized_directory(self):
        """A valid file within an authorized directory must be approved."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            allowed = Path(tmp_dir) / "authorized_binaries"
            allowed.mkdir()
            sample = allowed / "valid.exe"
            sample.write_text("MZ...", encoding="utf-8")

            orig = config.settings.BINARY_ALLOWED_DIRS
            config.settings.BINARY_ALLOWED_DIRS = [allowed]
            try:
                ok, msg = authorize_binary_path(str(sample))
                self.assertTrue(ok)
                self.assertIn("Authorized", msg)
            finally:
                config.settings.BINARY_ALLOWED_DIRS = orig

    def test_unauthorized_directory(self):
        """A file outside the approved directories must be rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            allowed = Path(tmp_dir) / "authorized"
            allowed.mkdir()
            unauthorized = Path(tmp_dir) / "unauthorized"
            unauthorized.mkdir()
            sample = unauthorized / "evil.exe"
            sample.write_text("MZ...", encoding="utf-8")

            orig = config.settings.BINARY_ALLOWED_DIRS
            config.settings.BINARY_ALLOWED_DIRS = [allowed]
            try:
                ok, msg = authorize_binary_path(str(sample))
                self.assertFalse(ok)
                self.assertIn("Access denied", msg)
            finally:
                config.settings.BINARY_ALLOWED_DIRS = orig

    def test_directory_traversal(self):
        """Paths containing traversal sequences must be rejected immediately."""
        ok, msg = authorize_binary_path("")
        self.assertFalse(ok)
        self.assertIn("empty", msg.lower())

        ok, msg = authorize_binary_path("../../../etc/shadow")
        self.assertFalse(ok)
        self.assertIn("traversal", msg.lower())

        with tempfile.TemporaryDirectory() as tmp_dir:
            allowed = Path(tmp_dir) / "allowed"
            allowed.mkdir()
            orig = config.settings.BINARY_ALLOWED_DIRS
            config.settings.BINARY_ALLOWED_DIRS = [allowed]
            try:
                # Path with embedded ..
                ok, msg = authorize_binary_path(f"{allowed}/../secret.exe")
                self.assertFalse(ok)
                self.assertIn("traversal", msg.lower())
            finally:
                config.settings.BINARY_ALLOWED_DIRS = orig

    
    def test_symlink_escape(self):
        """Symlinks inside approved dirs pointing outside must be strictly rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            allowed_path = (Path(tmp_dir) / "allowed").resolve()
            allowed_path.mkdir()

            outside_path = (Path(tmp_dir) / "outside").resolve()
            outside_path.mkdir()

            secret_file = outside_path / "secret.exe"
            secret_file.write_text("MZ...", encoding="utf-8")

            symlink_file = allowed_path / "symlink.exe"

            try:
                symlink_file.symlink_to(secret_file)
            except (OSError, NotImplementedError) as exc:
                if isinstance(exc, OSError) and getattr(exc, "winerror", None) != 1314:
                    raise

                self.skipTest(
                    "Symbolic link creation requires Windows Developer Mode "
                    "or elevated privileges."
                )

            orig = config.settings.BINARY_ALLOWED_DIRS
            config.settings.BINARY_ALLOWED_DIRS = [allowed_path]

            try:
                ok, msg = authorize_binary_path(str(symlink_file))

                self.assertFalse(ok)
                self.assertIn("Access denied", msg)
            finally:
                config.settings.BINARY_ALLOWED_DIRS = orig


    def test_sibling_directory_rejection(self):
        """A sibling directory with a matching prefix must never be authorized."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            allowed = (Path(tmp_dir) / "allowed").resolve()
            allowed.mkdir()
            # Sibling directory whose name starts with allowed directory name
            sibling = (Path(tmp_dir) / "allowed_sibling").resolve()
            sibling.mkdir()
            sample = sibling / "sample.exe"
            sample.write_text("MZ...", encoding="utf-8")

            orig = config.settings.BINARY_ALLOWED_DIRS
            config.settings.BINARY_ALLOWED_DIRS = [allowed]
            try:
                ok, msg = authorize_binary_path(str(sample))
                self.assertFalse(ok)
                self.assertIn("Access denied", msg)
            finally:
                config.settings.BINARY_ALLOWED_DIRS = orig

    def test_case_differing_sibling_paths(self):
        """Verify that case differences cannot escape authorization boundary."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            allowed = (Path(tmp_dir) / "AllowedArea").resolve()
            allowed.mkdir()
            good_bin = allowed / "target.exe"
            good_bin.write_text("MZ...", encoding="utf-8")

            orig = config.settings.BINARY_ALLOWED_DIRS
            config.settings.BINARY_ALLOWED_DIRS = [allowed]
            try:
                # Sibling with different case or suffix
                bad_sibling = Path(tmp_dir) / "allowedarea_extra"
                bad_sibling.mkdir()
                bad_bin = bad_sibling / "target.exe"
                bad_bin.write_text("MZ...", encoding="utf-8")

                ok, msg = authorize_binary_path(str(bad_bin))
                self.assertFalse(ok)
                self.assertIn("Access denied", msg)
            finally:
                config.settings.BINARY_ALLOWED_DIRS = orig

    def test_audit_event_logging(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "test_audit.log"
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
                self.assertNotIn("secret123", content)
            finally:
                agent.policy._get_audit_log_path = orig_get

    def test_rea_path_authorization_allowed(self):
        """REA tool calls on allowed binary paths must be approved and audited."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            allowed = (Path(tmp_dir) / "allowed_bin").resolve()
            allowed.mkdir()
            target = allowed / "sample.exe"
            target.write_text("MZ...", encoding="utf-8")

            log_path = Path(tmp_dir) / "audit.log"
            import agent.policy
            orig_dirs = config.settings.BINARY_ALLOWED_DIRS
            orig_get = agent.policy._get_audit_log_path
            config.settings.BINARY_ALLOWED_DIRS = [allowed]
            agent.policy._get_audit_log_path = lambda: log_path

            try:
                ok, msg = authorize_rea_tool_call("open_binary", {"path": str(target)})
                self.assertTrue(ok)
                self.assertEqual(msg, "Authorized")
                self.assertTrue(log_path.exists())
                log_data = log_path.read_text(encoding="utf-8")
                self.assertIn("rea_open_binary", log_data)
                self.assertIn("AUTHORIZED", log_data)
            finally:
                config.settings.BINARY_ALLOWED_DIRS = orig_dirs
                agent.policy._get_audit_log_path = orig_get

    def test_rea_path_authorization_denied(self):
        """REA tool calls on paths outside allowed directories must be strictly denied."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            allowed = (Path(tmp_dir) / "allowed").resolve()
            allowed.mkdir()
            outside = (Path(tmp_dir) / "outside").resolve()
            outside.mkdir()
            target = outside / "evil.exe"
            target.write_text("MZ...", encoding="utf-8")

            log_path = Path(tmp_dir) / "audit.log"
            import agent.policy
            orig_dirs = config.settings.BINARY_ALLOWED_DIRS
            orig_get = agent.policy._get_audit_log_path
            config.settings.BINARY_ALLOWED_DIRS = [allowed]
            agent.policy._get_audit_log_path = lambda: log_path

            try:
                ok, msg = authorize_rea_tool_call("open_binary", {"path": str(target)})
                self.assertFalse(ok)
                self.assertIn("Access Denied", msg)
                self.assertTrue(log_path.exists())
                log_data = log_path.read_text(encoding="utf-8")
                self.assertIn("rea_open_binary", log_data)
                self.assertIn("DENIED", log_data)
            finally:
                config.settings.BINARY_ALLOWED_DIRS = orig_dirs
                agent.policy._get_audit_log_path = orig_get

    def test_rea_path_authorization_traversal(self):
        """REA tool calls containing directory traversal must fail-closed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            allowed = (Path(tmp_dir) / "allowed").resolve()
            allowed.mkdir()

            log_path = Path(tmp_dir) / "audit.log"
            import agent.policy
            orig_dirs = config.settings.BINARY_ALLOWED_DIRS
            orig_get = agent.policy._get_audit_log_path
            config.settings.BINARY_ALLOWED_DIRS = [allowed]
            agent.policy._get_audit_log_path = lambda: log_path

            try:
                ok, msg = authorize_rea_tool_call("inspect_binary_layout", {"path": f"{allowed}/../../etc/passwd"})
                self.assertFalse(ok)
                self.assertIn("Access Denied", msg)
                self.assertIn("traversal", msg.lower())
                self.assertTrue(log_path.exists())
                log_data = log_path.read_text(encoding="utf-8")
                self.assertIn("rea_inspect_binary_layout", log_data)
                self.assertIn("DENIED", log_data)
            finally:
                config.settings.BINARY_ALLOWED_DIRS = orig_dirs
                agent.policy._get_audit_log_path = orig_get

    def test_rea_path_authorization_symlink(self):
        """REA tool calls on symlinks escaping allowed directory must be denied."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            allowed = (Path(tmp_dir) / "allowed").resolve()
            allowed.mkdir()
            outside = (Path(tmp_dir) / "outside").resolve()
            outside.mkdir()

            secret = outside / "secret.exe"
            secret.write_text("MZ...", encoding="utf-8")
            symlink_target = allowed / "symlink.exe"
            symlink_target.symlink_to(secret)

            log_path = Path(tmp_dir) / "audit.log"
            import agent.policy
            orig_dirs = config.settings.BINARY_ALLOWED_DIRS
            orig_get = agent.policy._get_audit_log_path
            config.settings.BINARY_ALLOWED_DIRS = [allowed]
            agent.policy._get_audit_log_path = lambda: log_path

            try:
                ok, msg = authorize_rea_tool_call("open_binary", {"path": str(symlink_target)})
                self.assertFalse(ok)
                self.assertIn("Access Denied", msg)
                self.assertTrue(log_path.exists())
                log_data = log_path.read_text(encoding="utf-8")
                self.assertIn("rea_open_binary", log_data)
                self.assertIn("DENIED", log_data)
            finally:
                config.settings.BINARY_ALLOWED_DIRS = orig_dirs
                agent.policy._get_audit_log_path = orig_get


if __name__ == "__main__":
    unittest.main()
