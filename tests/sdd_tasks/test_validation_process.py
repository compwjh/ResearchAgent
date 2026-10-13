import contextlib
import hashlib
import io
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.sdd_tasks.internalvalidation_process import (
    ValidationProcessError,
    run_one_validation,
)


class ValidationProcessTests(unittest.TestCase):
    def test_exit_startup_secret_isolation_and_private_exclusive_logs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out, err = root / "one.out", root / "one.err"
            stdout, stderr = io.StringIO(), io.StringIO()
            command = "import sys;print('private-sentinel');print('private-sentinel',file=sys.stderr)"
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                passed = run_one_validation([sys.executable, "-c", command], root, out, err, 3)
            self.assertEqual((passed.status, passed.exit_code, passed.summary),
                             ("executed", 0, "validation passed"))
            self.assertEqual(out.read_text().strip(), "private-sentinel")
            self.assertEqual(err.read_text().strip(), "private-sentinel")
            self.assertEqual((out.stat().st_mode & 0o777, err.stat().st_mode & 0o777), (0o600, 0o600))
            self.assertNotIn("private-sentinel", repr(passed) + stdout.getvalue() + stderr.getvalue())
            with self.assertRaises(ValidationProcessError) as caught:
                run_one_validation([sys.executable, "-c", "pass"], root, out, root / "two.err", 3)
            self.assertEqual(caught.exception.code, "VALIDATION_LOG_UNSAFE")
            self.assertEqual(out.read_text().strip(), "private-sentinel")

            failed = run_one_validation([sys.executable, "-c", "raise SystemExit(7)"],
                                        root, root / "fail.out", root / "fail.err", 3)
            self.assertEqual((failed.status, failed.exit_code, failed.summary),
                             ("executed", 7, "validation failed"))
            missing = run_one_validation([str(root / "missing-executable")], root,
                                         root / "missing.out", root / "missing.err", 3)
            self.assertEqual((missing.status, missing.exit_code, missing.summary),
                             ("skipped", None, "validation could not start"))

    def test_timeout_kills_grandchild_and_capped_logs_keep_full_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            child = "import pathlib,time;time.sleep(2);pathlib.Path('late').write_text('late')"
            parent = ("import pathlib,subprocess,sys,time;"
                      f"p=subprocess.Popen([sys.executable,'-c',{child!r}]);"
                      "pathlib.Path('child.pid').write_text(str(p.pid));time.sleep(30)")
            timed = run_one_validation([sys.executable, "-c", parent], root,
                                       root / "timeout.out", root / "timeout.err", 1)
            self.assertEqual((timed.status, timed.exit_code, timed.summary),
                             ("executed", -9, "validation timed out"))
            time.sleep(2.1)
            self.assertFalse((root / "late").exists())

            size = 1024 * 1024 + 17
            output = "import sys;sys.stdout.buffer.write(b'x'*%d);sys.stderr.buffer.write(b'y'*%d)" % (
                size, size + 3)
            record = run_one_validation([sys.executable, "-c", output], root,
                                        root / "large.out", root / "large.err", 5)
            self.assertEqual((record.stdout.truncated, record.stderr.truncated), (True, True))
            self.assertEqual(record.stdout.sha256, hashlib.sha256(b"x" * size).hexdigest())
            self.assertEqual(record.stderr.sha256, hashlib.sha256(b"y" * (size + 3)).hexdigest())
            self.assertEqual((root / "large.out").stat().st_size, 1024 * 1024)
            self.assertEqual((root / "large.err").stat().st_size, 1024 * 1024)

    def test_rejects_invalid_argv_and_timeout_types(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for argv, timeout in (([], 1), ("python", 1), ([sys.executable, "\x00"], 1),
                                  ([sys.executable], True), ([sys.executable], 1.5),
                                  ([sys.executable], 0), ([sys.executable], 3601)):
                with self.subTest(argv=argv, timeout=timeout):
                    with self.assertRaises(ValidationProcessError) as caught:
                        run_one_validation(argv, root, root / "bad.out", root / "bad.err", timeout)
                    self.assertEqual(caught.exception.code, "VALIDATION_PROCESS_INPUT_INVALID")

    def test_refuses_symlink_log_parent_with_stable_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "real-log-parent"
            target.mkdir()
            alias = root / "linked-log-parent"
            alias.symlink_to(target, target_is_directory=True)
            marker = root / "command-ran"
            command = "import pathlib;pathlib.Path(%r).write_text('ran')" % str(marker)

            with self.assertRaises(ValidationProcessError) as caught:
                run_one_validation([sys.executable, "-c", command], root,
                                   alias / "unsafe.out", root / "unsafe.err", 3)

            self.assertEqual(caught.exception.code, "VALIDATION_LOG_UNSAFE")
            self.assertFalse(marker.exists())
            self.assertFalse((target / "unsafe.out").exists())
            self.assertFalse((root / "unsafe.err").exists())

    def test_thread_start_and_log_write_failures_clean_up_without_leaking(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            child = "import pathlib,time;time.sleep(1.5);pathlib.Path('late-start').write_text('late')"
            parent = ("import pathlib,subprocess,sys,time;"
                      f"p=subprocess.Popen([sys.executable,'-c',{child!r}]);"
                      "pathlib.Path('child.pid').write_text(str(p.pid));time.sleep(30)")
            original_start = __import__("threading").Thread.start
            original_popen = subprocess.Popen
            pid_path = root / "child.pid"
            child_pids = []
            starts = [0]

            def fail_second(reader):
                starts[0] += 1
                if starts[0] == 2:
                    raise RuntimeError("private start error")
                return original_start(reader)

            def spawn_and_wait_for_child(*args, **kwargs):
                process = original_popen(*args, **kwargs)
                deadline = time.monotonic() + 2
                while not pid_path.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                if not pid_path.exists():
                    process.kill()
                    process.wait()
                    raise RuntimeError("grandchild did not start")
                child_pid = int(pid_path.read_text())
                os.kill(child_pid, 0)
                child_pids.append(child_pid)
                return process

            with patch("scripts.sdd_tasks.internalvalidation_process.subprocess.Popen",
                       side_effect=spawn_and_wait_for_child), \
                    patch("threading.Thread.start", fail_second), \
                    self.assertRaises(ValidationProcessError) as caught:
                run_one_validation([sys.executable, "-c", parent], root,
                                   root / "start.out", root / "start.err", 3)
            self.assertEqual(caught.exception.code, "VALIDATION_STREAM_START_FAILED")
            self.assertEqual(len(child_pids), 1)
            self.assertTrue(pid_path.is_file())
            time.sleep(1.7)
            self.assertFalse((root / "late-start").exists())

            public_out, public_err = io.StringIO(), io.StringIO()
            with patch("scripts.sdd_tasks.internalvalidation_process.os.write",
                       side_effect=OSError("private-sentinel")), \
                    contextlib.redirect_stdout(public_out), \
                    contextlib.redirect_stderr(public_err), \
                    self.assertRaises(ValidationProcessError) as caught:
                run_one_validation([sys.executable, "-c", "print('private-sentinel')"],
                                   root, root / "write.out", root / "write.err", 3)
            self.assertEqual(caught.exception.code, "VALIDATION_LOG_WRITE_FAILED")
            self.assertNotIn("private-sentinel", str(caught.exception))
            self.assertEqual(public_out.getvalue() + public_err.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
