import hashlib
import os
import subprocess
import tempfile
import unittest
from contextlib import closing
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from scripts.sdd_tasks.catalog import rebuild
from scripts.sdd_tasks.documents import parse_task
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.owners import current_owner
from scripts.sdd_tasks.results import validate_result
from scripts.sdd_tasks.selection import claim_next
from scripts.sdd_tasks.store import connect
from scripts.sdd_tasks.workspace import capture_snapshot
from tests.sdd_tasks._fixtures import task_markdown
from tests.sdd_tasks.test_result_schema import valid_result
from tests.sdd_tasks.test_selection import GATE, NOW, _fixture

ARTIFACT = "scripts/sdd_tasks/allowed.txt"


def _install_expected_artifact(root, canonical, db, task):
    metadata = dict(task.metadata, expected_artifacts=[ARTIFACT])
    relative = task.path.relative_to(root)
    for repository in (root, canonical):
        path = repository / relative
        path.write_text("# {}\n> 当前状态：`待执行`\n\n".format(metadata["title"]) +
                        task_markdown(metadata, prompt=task.prompt), encoding="utf-8")
        subprocess.run(["git", "-C", str(repository), "add", relative.as_posix()],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repository), "commit", "-qm", "add expected artifact"],
                       check=True, capture_output=True)
    rebuild(db, root)
    live = parse_task(canonical / relative)
    return live, capture_snapshot(root, live)


def _claim(root, db, task, snapshot):
    with closing(connect(db)) as conn, maintenance_lock(root):
        return claim_next(conn, [task], {GATE}, workspace_snapshots={
            task.metadata["task_id"]: snapshot}, ide="codex",
            owner=current_owner("result-tests", pid=os.getpid()), now=NOW)


def _valid_data(task, claim, file_hash):
    data = valid_result()
    data.update(run_id=claim.run_id, task_id=task.metadata["task_id"],
                task_hash=task.task_hash, prompt_hash=task.prompt_hash,
                started_at=claim.claimed_at, ended_at="2026-10-11T12:01:00Z")
    data["changed_files"] = [{"path": ARTIFACT, "change": "modified", "additions": 1,
                              "deletions": 1, "sha256": file_hash}]
    data["artifacts"] = [{"path": ARTIFACT, "kind": "expected-output", "sha256": file_hash,
                          "included_in_commit": False}]
    return data


def _scenario(temp):
    root, canonical, task, _, db = _fixture(temp)
    task, before = _install_expected_artifact(root, canonical, db, task)
    claim = _claim(root, db, task, before)
    target = canonical / ARTIFACT
    target.write_text("artifact result\n", encoding="utf-8")
    after = capture_snapshot(root, task)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return task, claim, before, after, target, _valid_data(task, claim, digest)


class ResultValidationTests(unittest.TestCase):
    def test_claim_result_validates_changed_file_artifact_and_command_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            task, claim, before, after, target, data = _scenario(temp)
            report = validate_result(data, task, claim, before, after)
            self.assertTrue(report.valid, report.errors)
            self.assertEqual(report.errors, ())
            self.assertEqual(report.changed_paths, (ARTIFACT,))
            self.assertEqual(report.result, data)
            self.assertEqual(target.read_text(encoding="utf-8"), "artifact result\n")
            self.assertEqual(data["commands"][0]["argv"], [
                "python3", "-m", "unittest", "tests.sdd_tasks.test_store"])

    def test_rejects_forged_run_task_and_file_artifact_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            task, claim, before, after, _, data = _scenario(temp)
            for field, value in (("run_id", "123e4567-e89b-12d3-a456-426614174001"),
                                 ("task_hash", "f" * 64)):
                forged = deepcopy(data)
                forged[field] = value
                report = validate_result(forged, task, claim, before, after)
                self.assertIn("RESULT_CLAIM_MISMATCH", report.errors)
            wrong_claim = replace(claim, task_hash="f" * 64)
            self.assertIn("RESULT_CLAIM_MISMATCH",
                          validate_result(data, task, wrong_claim, before, after).errors)
            wrong_file = deepcopy(data)
            wrong_file["changed_files"][0]["sha256"] = "f" * 64
            self.assertIn("RESULT_CHANGED_FILE_HASH_MISMATCH",
                          validate_result(wrong_file, task, claim, before, after).errors)
            wrong_artifact = deepcopy(data)
            wrong_artifact["artifacts"][0]["sha256"] = "f" * 64
            self.assertIn("RESULT_ARTIFACT_HASH_MISMATCH",
                          validate_result(wrong_artifact, task, claim, before, after).errors)

    def test_rejects_out_of_scope_changes_and_missing_success_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            root, canonical, task, _, db = _fixture(temp)
            task, before = _install_expected_artifact(root, canonical, db, task)
            claim = _claim(root, db, task, before)
            target = canonical / ARTIFACT
            target.write_text("artifact result\n", encoding="utf-8")
            data = _valid_data(task, claim, hashlib.sha256(target.read_bytes()).hexdigest())
            outside = canonical / "outside.txt"
            outside.write_text("out of scope\n", encoding="utf-8")
            after = capture_snapshot(root, task)
            self.assertIn("RESULT_WORKSPACE_OUT_OF_SCOPE",
                          validate_result(data, task, claim, before, after).errors)
            missing = deepcopy(data)
            missing["artifacts"] = []
            self.assertIn("RESULT_ARTIFACTS_MISMATCH",
                          validate_result(missing, task, claim, before, after).errors)

    def test_rejects_sensitive_content_and_future_completion_time(self):
        with tempfile.TemporaryDirectory() as temp:
            task, claim, before, after, _, data = _scenario(temp)
            secret = deepcopy(data)
            secret["summary"] = "API_SECRET=do_not_share"
            self.assertIn("RESULT_SENSITIVE_CONTENT",
                          validate_result(secret, task, claim, before, after).errors)
            future = deepcopy(data)
            future["ended_at"] = "2999-01-01T00:01:00Z"
            self.assertIn("RESULT_ENDED_IN_FUTURE",
                          validate_result(future, task, claim, before, after).errors)

    def test_failed_missing_artifact_needs_blocker_and_success_needs_executed_command(self):
        with tempfile.TemporaryDirectory() as temp:
            task, claim, before, after, target, data = _scenario(temp)
            skipped = deepcopy(data)
            skipped["commands"][0].update(status="skipped", exit_code=None,
                                          summary="not executed")
            self.assertIn("RESULT_VALIDATION_COMMAND_FAILED",
                          validate_result(skipped, task, claim, before, after).errors)

            target.unlink()
            after = capture_snapshot(before.repo_root, task)
            data.update(outcome="failed", summary="Expected output was not produced.",
                        blockers=["Expected artifact missing: " + ARTIFACT], artifacts=[])
            data["changed_files"] = [{"path": ARTIFACT, "change": "deleted", "additions": 0,
                                      "deletions": 1, "sha256": None}]
            report = validate_result(data, task, claim, before, after)
            self.assertTrue(report.valid, report.errors)
            self.assertEqual(report.changed_paths, (ARTIFACT,))
            untruthful = deepcopy(data)
            untruthful["blockers"] = []
            self.assertIn("RESULT_MISSING_ARTIFACT_BLOCKER",
                          validate_result(untruthful, task, claim, before, after).errors)

    def test_classifies_exact_added_deleted_renamed_and_ignored_file_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root, canonical, task, _, db = _fixture(temp)
            task, _ = _install_expected_artifact(root, canonical, db, task)
            script_dir = canonical / "scripts/sdd_tasks"
            for name, contents in (("delete-me.txt", "old\n"), ("rename-old.txt", "move\n")):
                (script_dir / name).write_text(contents, encoding="utf-8")
            subprocess.run(["git", "-C", str(canonical), "add",
                            "scripts/sdd_tasks/delete-me.txt", "scripts/sdd_tasks/rename-old.txt"],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", str(canonical), "commit", "-qm", "seed result paths"],
                           check=True, capture_output=True)
            before = capture_snapshot(root, task)
            claim = _claim(root, db, task, before)
            target = canonical / ARTIFACT
            target.write_text("artifact result\n", encoding="utf-8")
            (script_dir / "add-me.txt").write_text("new\n", encoding="utf-8")
            (script_dir / "delete-me.txt").unlink()
            subprocess.run(["git", "-C", str(canonical), "mv", "scripts/sdd_tasks/rename-old.txt",
                            "scripts/sdd_tasks/rename-new.txt"], check=True, capture_output=True)
            ignored = script_dir / "ignored.txt"
            ignored.write_text("ignored changed\n", encoding="utf-8")
            after = capture_snapshot(root, task)
            hashes = {path: hashlib.sha256((canonical / path).read_bytes()).hexdigest()
                      for path in (ARTIFACT, "scripts/sdd_tasks/add-me.txt",
                                   "scripts/sdd_tasks/rename-new.txt", "scripts/sdd_tasks/ignored.txt")}
            data = _valid_data(task, claim, hashes[ARTIFACT])
            changes = ((ARTIFACT, "modified", 1, 1, hashes[ARTIFACT]),
                       ("scripts/sdd_tasks/add-me.txt", "added", 1, 0,
                        hashes["scripts/sdd_tasks/add-me.txt"]),
                       ("scripts/sdd_tasks/delete-me.txt", "deleted", 0, 1, None),
                       ("scripts/sdd_tasks/rename-old.txt", "deleted", 0, 1, None),
                       ("scripts/sdd_tasks/rename-new.txt", "renamed", 0, 0,
                        hashes["scripts/sdd_tasks/rename-new.txt"]),
                       ("scripts/sdd_tasks/ignored.txt", "modified", 1, 1,
                        hashes["scripts/sdd_tasks/ignored.txt"]))
            data["changed_files"] = [{"path": path, "change": change, "additions": adds,
                                      "deletions": deletes, "sha256": digest}
                                     for path, change, adds, deletes, digest in changes]
            report = validate_result(data, task, claim, before, after)
            self.assertTrue(report.valid, report.errors)
            self.assertEqual(set(report.changed_paths), {item[0] for item in changes})

    def test_rejects_stale_baseline_after_snapshot_and_canonical_task(self):
        with tempfile.TemporaryDirectory() as temp:
            task, claim, before, after, _, data = _scenario(temp)
            wrong_before = replace(before, head="0" * 40)
            self.assertIn("RESULT_SNAPSHOT_MISMATCH",
                          validate_result(data, task, claim, wrong_before, after).errors)
            stale_after = replace(after, status_records=after.status_records +
                                  ("?? scripts/sdd_tasks/unobserved.txt",))
            self.assertIn("RESULT_AFTER_SNAPSHOT_STALE",
                          validate_result(data, task, claim, before, stale_after).errors)
            metadata = dict(task.metadata, title="Drifted canonical title")
            task.path.write_text("# Drifted canonical title\n> 当前状态：`待执行`\n\n" +
                                 task_markdown(metadata, prompt=task.prompt), encoding="utf-8")
            self.assertIn("RESULT_CANONICAL_TASK_STALE",
                          validate_result(data, task, claim, before, after).errors)

    def test_rejects_invalid_hash_shape_and_malformed_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            task, claim, before, after, _, data = _scenario(temp)
            malformed = deepcopy(data)
            malformed["prompt_hash"] = "not-a-hash"
            self.assertIn("RESULT_SCHEMA_INVALID",
                          validate_result(malformed, task, claim, before, after).errors)
            self.assertEqual(validate_result(data, None, claim, before, after).errors,
                             ("RESULT_INPUT_INVALID",))

    def test_validates_safe_artifact_symlink_and_rejects_escaping_artifact_link(self):
        with tempfile.TemporaryDirectory() as temp:
            task, claim, before, _, target, _ = _scenario(temp)
            target.unlink()
            target.symlink_to("ignored.txt")
            after = capture_snapshot(before.repo_root, task)
            digest = hashlib.sha256((target.parent / "ignored.txt").read_bytes()).hexdigest()
            data = _valid_data(task, claim, digest)
            self.assertEqual(after.allowed_hashes[ARTIFACT], digest)
            self.assertTrue(validate_result(data, task, claim, before, after).valid)

            target.unlink()
            outside = Path(temp) / "outside-artifact.txt"
            outside.write_text("outside\n", encoding="utf-8")
            target.symlink_to(outside)
            report = validate_result(data, task, claim, before, after)
            self.assertIn("workspace_path_unsafe", report.errors)


if __name__ == "__main__":
    unittest.main()
