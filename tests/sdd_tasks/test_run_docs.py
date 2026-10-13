import copy
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.sdd_tasks.run_docs import build_summary, write_summary
from scripts.sdd_tasks.summaries import _MB, _ME, _RB, _RE, SummaryError, scan_summaries
from tests.sdd_tasks.test_result_schema import valid_result
from tests.sdd_tasks.test_run_owner import _claimed


def _result(task, claim):
    data = copy.deepcopy(valid_result())
    data.update(run_id=claim.run_id, task_id=task.metadata["task_id"],
                task_hash=task.task_hash, prompt_hash=task.prompt_hash,
                started_at=claim.claimed_at,
                ended_at=(datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat().replace(
                    "+00:00", "Z"), model="fixture-model")
    data["artifacts"][0]["path"] = "docs/sdd/runs/{}/task-{}/{}.md".format(
        task.metadata["spec_id"], task.metadata["task_id"][-2:], claim.run_id)
    data["token_usage"] = {"input": 8, "output": None, "total": None,
                           "source": "fixture telemetry"}
    return data


def _tree(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file() and
            not {".git", ".worktrees", ".sdd"}.intersection(path.relative_to(root).parts)}


def _block(content, begin, end):
    return content.split(begin + "\n", 1)[1].split("\n" + end, 1)[0]


class RunDocsTests(unittest.TestCase):
    def test_builder_is_pure_deterministic_and_preserves_unknown_metrics(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, canonical, _, _, _, owner, claim = state
            task, result = claim.task, _result(claim.task, claim)
            original = copy.deepcopy(result)
            before = _tree(root)
            content = build_summary(task, claim, result)
            self.assertEqual(content, build_summary(task, claim, result))
            self.assertEqual(_tree(root), before)
            self.assertFalse((canonical / "docs/sdd/runs").exists())
            self.assertEqual(result, original)
            parsed_result = __import__("json").loads(_block(content, _RB, _RE))
            metadata = __import__("json").loads(_block(content, _MB, _ME))
            self.assertEqual(parsed_result, result)
            self.assertEqual(metadata["model"], result["model"])
            self.assertEqual(metadata["run_id"], claim.run_id)
            self.assertEqual(metadata["task_hash"], task.task_hash)
            self.assertEqual(metadata["prompt_hash"], task.prompt_hash)
            self.assertEqual(metadata["executor_id"], owner.executor_id)
            self.assertEqual(result["token_usage"], {
                "input": 8, "output": None, "total": None, "source": "fixture telemetry"})
            self.assertNotIn(owner.token, content)

    def test_writer_uses_registered_canonical_worktree_and_reader_accepts_it(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, canonical, _, _, _, _, claim = state
            task, result = claim.task, _result(claim.task, claim)
            relative = Path("docs/sdd/runs/{}/task-{}/{}.md".format(
                task.metadata["spec_id"], task.metadata["task_id"][-2:], claim.run_id))
            target = canonical / relative
            before = _tree(root)
            with self.assertRaises(SummaryError) as caught:
                write_summary(task, claim, result, root)
            self.assertEqual(caught.exception.code, "SUMMARY_WRITE_FAILED")
            self.assertFalse(target.parent.exists())
            self.assertEqual(_tree(root), before)
            target.parent.mkdir(parents=True)
            content = build_summary(task, claim, result)
            self.assertEqual(write_summary(task, claim, result, root), target)
            self.assertEqual(target.read_text(encoding="utf-8"), content)
            self.assertFalse((root / relative).exists())
            self.assertEqual(_tree(root), before)
            records = scan_summaries((canonical,), (task,))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["run_id"], claim.run_id)
            self.assertEqual(records[0]["model"], result["model"])
            self.assertEqual(records[0]["owner_json"], "{}")

    def test_builder_rejects_bad_bindings_sensitive_text_and_private_token(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            _, _, _, _, _, owner, claim = state
            task = claim.task
            cases = (
                ("task hash", lambda data: data.update(task_hash="f" * 64)),
                ("claimed time", lambda data: data.update(started_at="2026-10-10T00:00:00Z")),
                ("model type", lambda data: data.update(model=7)),
                ("sensitive narrative", lambda data: data.update(
                    summary="Authorization: Bearer unsafe")),
                ("private owner token", lambda data: data["main_agent_actions"].append(owner.token)),
            )
            for label, edit in cases:
                with self.subTest(case=label):
                    data = _result(task, claim)
                    edit(data)
                    with self.assertRaises(SummaryError):
                        build_summary(task, claim, data)
            with self.assertRaises(SummaryError):
                build_summary(task, replace(claim, task_hash="e" * 64), _result(task, claim))

    def test_writer_rejects_symlink_parent_without_touching_its_target(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, canonical, _, _, _, _, claim = state
            task, result = claim.task, _result(claim.task, claim)
            relative = Path("docs/sdd/runs/{}/task-{}".format(
                task.metadata["spec_id"], task.metadata["task_id"][-2:]))
            link = canonical / relative
            outside = Path(temp) / "outside"
            outside.mkdir()
            link.parent.mkdir(parents=True)
            link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(SummaryError) as caught:
                write_summary(task, claim, result, root)
            self.assertEqual(caught.exception.code, "SUMMARY_WRITE_FAILED")
            self.assertEqual(tuple(outside.iterdir()), ())
            self.assertTrue(link.is_symlink())


if __name__ == "__main__":
    unittest.main()
