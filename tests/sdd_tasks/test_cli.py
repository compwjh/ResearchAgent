import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from scripts.sdd_tasks.cli import main
from tests.sdd_tasks.test_catalog import _repo


def _invoke(args):
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(args)
    return code, json.loads(stdout.getvalue()), stdout.getvalue(), stderr.getvalue()


class CliTests(unittest.TestCase):
    def test_doctor_emits_json_envelope_without_owner_or_absolute_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, _, _ = _repo(td)
            code, body, raw, err = _invoke(["--repo", str(root), "doctor"])
            self.assertEqual(code, 0)
            self.assertEqual(set(body), {"ok", "code", "message", "data"})
            self.assertTrue(body["ok"])
            self.assertEqual(err, "")
            self.assertNotIn(str(root), raw)
            self.assertNotIn("owner", raw.lower())

    def test_status_without_db_refuses_and_does_not_create_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, _, _ = _repo(td)
            code, body, _, err = _invoke(["--repo", str(root), "status", "--json"])
            self.assertEqual((code, body["ok"], body["code"], err),
                             (3, False, "CATALOG_NOT_REBUILT", ""))
            self.assertFalse((root / ".sdd/runtime/task-ledger.sqlite3").exists())

    def test_help_is_a_json_envelope_and_succeeds(self):
        code, body, _, err = _invoke(["--help"])
        self.assertEqual((code, body["ok"], body["code"], err), (0, True, "OK", ""))
        self.assertIn("usage", body["data"]["usage"])


if __name__ == "__main__":
    unittest.main()
