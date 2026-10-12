import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.sdd_tasks.newdoctor import doctor
from tests.sdd_tasks.test_catalog import _git, _repo


def _legacy_repo(directory):
    root = Path(directory) / "legacy"
    task = root / "docs/sdd/plans/016/task-01-legacy.md"
    task.parent.mkdir(parents=True)
    task.write_text("# Legacy task\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "legacy fixture")
    return root


class DoctorTests(unittest.TestCase):
    def test_import_and_doctor_do_not_create_runtime_files(self):
        with tempfile.TemporaryDirectory() as td:
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2]),
                       PYTHONDONTWRITEBYTECODE="1")
            subprocess.run([sys.executable, "-c", "import scripts.sdd_tasks.newdoctor"],
                           cwd=td, env=env, check=True, capture_output=True, text=True)
            self.assertEqual(list(Path(td).iterdir()), [])
            root, _, _, _ = _repo(td)
            before = (root / ".sdd").exists()
            result = doctor(root)
            self.assertEqual((before, (root / ".sdd").exists()), (False, False))
            self.assertTrue(result["healthy"])
            self.assertEqual(result["ledger"]["schema_check"], "not_initialized")

    def test_legacy_only_repository_is_healthy_with_warning(self):
        with tempfile.TemporaryDirectory() as td:
            result = doctor(_legacy_repo(td))
            codes = {item["code"] for item in result["diagnostics"]}
            self.assertTrue(result["healthy"])
            self.assertEqual(result["legacy_task_count"], 1)
            self.assertTrue({"legacy_tasks_ignored", "no_protocol_tasks"} <= codes)

    def test_bad_metadata_or_prompt_is_reported(self):
        for kind in ("metadata", "prompt"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as td:
                root, paths, _, task = _repo(td)
                source = paths[task["task_id"]]
                text = source.read_text(encoding="utf-8")
                if kind == "metadata":
                    text = text.replace('{"schema_version": 1', "{broken", 1)
                else:
                    text = text.replace("Role: backend-dev", "Role: other", 1)
                source.write_text(text, encoding="utf-8")
                result = doctor(root)
                self.assertFalse(result["healthy"])
                self.assertTrue(result["diagnostics"])

    def test_existing_regular_db_is_not_schema_checked(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, _, _ = _repo(td)
            db = root / ".sdd/runtime/task-ledger.sqlite3"
            db.parent.mkdir(parents=True)
            db.write_bytes(b"not a SQLite database")
            before = db.read_bytes()
            result = doctor(root)
            self.assertEqual(result["ledger"], {"present": True, "schema_check": "not_run_requires_status"})
            self.assertEqual(db.read_bytes(), before)

    def test_database_symlink_is_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, _, _ = _repo(td)
            db = root / ".sdd/runtime/task-ledger.sqlite3"
            db.parent.mkdir(parents=True)
            target = Path(td) / "outside.db"
            target.write_bytes(b"preserve")
            db.symlink_to(target)
            result = doctor(root)
            codes = {item["code"] for item in result["diagnostics"]}
            self.assertFalse(result["healthy"])
            self.assertIn("DATABASE_PATH_UNSAFE", codes)
            self.assertEqual(target.read_bytes(), b"preserve")
            self.assertTrue(db.is_symlink())


if __name__ == "__main__":
    unittest.main()
