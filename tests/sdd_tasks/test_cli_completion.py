import io
import json
import multiprocessing
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path

from scripts.sdd_tasks.cli import main
from scripts.sdd_tasks.completion_journal import read_journal
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_completion_crash_recovery import _crash_worker
from tests.sdd_tasks.test_completion_prepare import _claimed_with_command
from tests.sdd_tasks.test_completion_service import _draft


def _invoke(root, *args):
    output = io.StringIO()
    with redirect_stdout(output):
        code = main(["--repo", str(root), *args])
    raw = output.getvalue()
    if len(raw.splitlines()) != 1:
        raise AssertionError("CLI must emit one JSON line: " + raw)
    return code, json.loads(raw)


def _finish_args(claim, result):
    return ["--run-id", claim.run_id, "--executor", claim.owner.executor_id,
            "--owner-pid", str(claim.owner.pid), "--result", str(result)]


class CliCompletionTests(unittest.TestCase):
    def test_complete_result_metrics_then_replay_without_result_file(self):
        with tempfile.TemporaryDirectory() as temp, _claimed_with_command(temp) as state:
            root, _, task, _, _, _, claim = state
            draft = root / "draft.json"
            draft.write_text(json.dumps(_draft(task, claim)), encoding="utf-8")
            code, completed = _invoke(root, "complete", *_finish_args(claim, "draft.json"))
            self.assertEqual((code, completed["ok"], completed["code"]), (0, True, "OK"))
            code, result = _invoke(root, "result", "--json", "--run-id", claim.run_id)
            self.assertEqual((code, result["data"]["outcome"]), (0, "succeeded"))
            code, metrics = _invoke(root, "metrics", "--format", "json")
            row = next(item for item in metrics["data"]["rows"] if item["run_id"] == claim.run_id)
            self.assertEqual((code, row["state"], row["outcome"]), (0, "succeeded", "succeeded"))
            replay = _invoke(root, "complete", *_finish_args(claim, "missing.json"))
            self.assertEqual((replay[0], replay[1]["data"]), (0, completed["data"]))

    def test_fail_publishes_a_summary_without_changed_files(self):
        with tempfile.TemporaryDirectory() as temp, _claimed_with_command(temp) as state:
            root, _, task, _, _, _, claim = state
            draft = root / "failed.json"
            draft.write_text(json.dumps(_draft(task, claim, outcome="failed")), encoding="utf-8")
            code, body = _invoke(root, "fail", *_finish_args(claim, "failed.json"))
            self.assertEqual((code, body["ok"], body["code"]), (0, True, "OK"))
            self.assertEqual(body["data"]["outcome"], "failed")
            self.assertEqual(body["data"]["changed_files"], [])

    def test_result_symlink_and_oversize_are_rejected_without_finishing_run(self):
        for kind, expected in (("symlink", "COMPLETION_RESULT_FILE_INVALID"),
                               ("oversize", "COMPLETION_RESULT_FILE_TOO_LARGE")):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp, \
                    _claimed_with_command(temp) as state:
                root, _, _, database, _, _, claim = state
                path = root / "input.json"
                if kind == "symlink":
                    target = root / "target.json"
                    target.write_text("{}", encoding="utf-8")
                    path.symlink_to(target)
                else:
                    path.write_bytes(b"x" * (1024 * 1024 + 1))
                code, body = _invoke(root, "complete", *_finish_args(claim, "input.json"))
                self.assertEqual((code, body["ok"], body["code"]), (6, False, expected))
                self.assertFalse((root / ".sdd/runtime/runs" / claim.run_id / "completion.json").exists())
                with closing(connect(database)) as conn:
                    state = conn.execute("SELECT state FROM runs WHERE run_id=?",
                                          (claim.run_id,)).fetchone()[0]
                self.assertEqual(state, "claimed")

    def test_recover_cli_resumes_real_crash_journal(self):
        with tempfile.TemporaryDirectory() as temp:
            context = multiprocessing.get_context("fork")
            ready, request = context.Queue(), context.Queue()
            worker = context.Process(target=_crash_worker, args=(temp, ready, request))
            worker.start()
            try:
                message = ready.get(timeout=120)
                self.assertEqual(message[0], "ready", message)
                _, root, _, database, run_id = message
                request.put("documents")
                worker.join(120)
                self.assertEqual(worker.exitcode, 86)
                with closing(connect(Path(database))) as conn, maintenance_lock(Path(root)):
                    conn.execute("UPDATE leases SET expires_at=? WHERE run_id=?",
                                 ("2000-01-01T00:00:00Z", run_id))
                code, body = _invoke(Path(root), "recover", "--run-id", run_id)
                self.assertEqual((code, body["ok"], body["code"]), (0, True, "OK"))
                self.assertEqual(body["data"], {"run_id": run_id, "state": "succeeded",
                                                 "action": "completion_resumed"})
                path = Path(root) / ".sdd/runtime/runs" / run_id / "completion.json"
                self.assertEqual(read_journal(path)["phase"], "complete")
            finally:
                if worker.is_alive():
                    worker.terminate()
                worker.join(10)
                for queue in (ready, request):
                    queue.close()


if __name__ == "__main__":
    unittest.main()
