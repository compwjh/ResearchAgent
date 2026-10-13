import copy
import hashlib
import json
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.sdd_tasks import atomic
from scripts.sdd_tasks.completion_journal import (
    JournalError,
    read_journal,
    recover_expected_documents,
    write_journal,
)
from scripts.sdd_tasks.journal_schema import validate_journal, validate_phase_transition
from tests.sdd_tasks.test_result_schema import valid_result


def _hash(char):
    return char * 64


def _journal():
    doc = "original task document\n"
    result = valid_result()
    result.update(task_id="spec-016-task-06", task_hash=_hash("2"), prompt_hash=_hash("3"))
    return {
        "schema": "sdd-completion-journal/v1", "run_id": "123e4567-e89b-12d3-a456-426614174000",
        "task_id": "spec-016-task-06",
        "owner": {"executor_id": "executor", "host_id": "host", "pid": 42,
                  "process_started_at": "2026-10-12T01:00:00Z", "token": "owner-token"},
        "base_commit": "1" * 40, "original_head": "1" * 40, "task_hash": _hash("2"),
        "prompt_hash": _hash("3"), "allowed_paths": ["src/change.py"],
        "expected_result": result, "terminal_outcome": "succeeded",
        "expected_git_entries": [
            {"path": "docs/task.md", "mode": "100644", "object_id": "8" * 40},
            {"path": "src/change.py", "mode": "100644", "object_id": "7" * 40}],
        "changed_paths": [{"path": "src/change.py", "before_sha256": _hash("4"),
                           "after_sha256": _hash("5")}],
        "expected_docs": [{"path": "docs/task.md", "before_sha256": hashlib.sha256(doc.encode()).hexdigest(),
                           "content": "completed task document\n",
                           "after_sha256": hashlib.sha256(b"completed task document\n").hexdigest()}],
        "committed_paths": ["src/change.py", "docs/task.md"],
        "staged_paths": ["docs/task.md", "src/change.py"],
        "index_before": {"git_index_path": "/tmp/fixture/.git/index", "index_sha256": _hash("6"),
                         "committed_entries": [
                             {"path": "src/change.py", "stage": 0, "mode": "100644", "object_id": "7" * 40},
                             {"path": "docs/task.md", "stage": 0, "mode": "100644", "object_id": "8" * 40}],
                         "other_entries_sha256": _hash("9")},
        "index_observed_before": None, "index_after": None, "index_lock_owner_token": _hash("a"),
        "index_lock_temp_path": None, "index_lock_identity": None, "index_recovery_stage": "not_acquired",
        "candidate_commit_hash": None, "commit_message": "feat: complete task", "phase": "prepared",
    }


def _document(path, before, after):
    before_hash = None if before is None else hashlib.sha256(before.encode()).hexdigest()
    return {"path": path, "before_sha256": before_hash, "content": after,
            "after_sha256": hashlib.sha256(after.encode()).hexdigest()}


def _prepared(root, specs, modes=None):
    journal = _journal()
    modes = modes or {}
    journal["expected_docs"] = [_document(*spec) for spec in specs]
    paths = ["src/change.py"] + [spec[0] for spec in specs]
    journal["committed_paths"] = paths
    journal["staged_paths"] = paths.copy()
    journal["expected_git_entries"] = [
        {"path": path, "mode": modes.get(path, "100644"), "object_id": "7" * 40}
        for path in sorted(paths, key=lambda item: item.encode("utf-8"))]
    for path, before, _ in specs:
        if before is not None:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(before, encoding="utf-8")
    journal_path = root / ".sdd/runtime/runs" / journal["run_id"] / "completion.json"
    journal_path.parent.mkdir(parents=True)
    write_journal(journal_path, journal)
    return journal, journal_path


class CompletionJournalTests(unittest.TestCase):
    def test_round_trip_and_prepared_write_leaves_expected_documents_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal_path, doc_path = root / "completion.json", root / "docs/task.md"
            doc_path.parent.mkdir()
            original = b"original task document\n"
            doc_path.write_bytes(original)
            value = _journal()
            write_journal(journal_path, value)
            self.assertEqual(read_journal(journal_path), validate_journal(value))
            self.assertEqual(doc_path.read_bytes(), original)
            self.assertEqual(list(root.glob(".sdd-atomic-*")), [])

    def test_exact_schema_rejects_duplicate_unknown_missing_and_bad_nested_fields(self):
        valid = _journal()
        cases = []
        unknown = copy.deepcopy(valid)
        unknown["extra"] = 1
        cases.append(unknown)
        missing = copy.deepcopy(valid)
        missing.pop("owner")
        cases.append(missing)
        nested = copy.deepcopy(valid)
        nested["owner"]["extra"] = 1
        cases.append(nested)
        entry = copy.deepcopy(valid)
        entry["index_before"]["committed_entries"][0]["extra"] = 1
        cases.append(entry)
        for case in cases:
            with self.subTest(case=list(case)), self.assertRaises(JournalError):
                validate_journal(case)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "completion.json"
            path.write_text(json.dumps(valid).replace('"schema": "sdd-completion-journal/v1"',
                                                     '"schema": "sdd-completion-journal/v1", "schema": "bad"'),
                            encoding="utf-8")
            with self.assertRaises(JournalError):
                read_journal(path)

    def test_invalid_schema_time_hash_and_expected_content_fail_closed(self):
        mutations = (
            lambda j: j.update(schema="sdd-completion-journal/v2"),
            lambda j: j["expected_result"].update(started_at="2026-10-12T01:00:00"),
            lambda j: j.update(terminal_outcome="failed"),
            lambda j: j.update(candidate_commit_hash="f" * 40),
            lambda j: j.update(task_hash="A" * 64),
            lambda j: j["expected_docs"][0].update(after_sha256=_hash("a")),
            lambda j: j["owner"].update(pid=True),
        )
        for mutate in mutations:
            case = copy.deepcopy(_journal())
            mutate(case)
            with self.subTest(mutate=mutate), self.assertRaises(JournalError):
                validate_journal(case)

    def test_expected_git_entries_are_complete_ordered_and_git_shaped(self):
        valid = _journal()
        self.assertEqual(validate_journal(valid)["expected_git_entries"], valid["expected_git_entries"])
        for mode in ("100644", "100755", "120000"):
            candidate = copy.deepcopy(valid)
            candidate["expected_git_entries"][0]["mode"] = mode
            with self.subTest(mode=mode):
                validate_journal(candidate)
        deleted = copy.deepcopy(valid)
        deleted["expected_git_entries"][0].update(mode=None, object_id=None)
        validate_journal(deleted)

        invalid = []
        missing_field = copy.deepcopy(valid)
        missing_field.pop("expected_git_entries")
        invalid.append(missing_field)
        for mutate in (
                lambda j: j["expected_git_entries"].reverse(),
                lambda j: j["expected_git_entries"][0].update(path="other.md"),
                lambda j: j["expected_git_entries"][0].update(extra=True),
                lambda j: j["expected_git_entries"][0].update(mode="160000"),
                lambda j: j["expected_git_entries"][0].update(object_id="A" * 40),
                lambda j: j["expected_git_entries"][0].update(mode=None),
                lambda j: j["expected_git_entries"][0].update(object_id=None),
        ):
            candidate = copy.deepcopy(valid)
            mutate(candidate)
            invalid.append(candidate)
        long_oid = copy.deepcopy(valid)
        long_oid["original_head"] = "f" * 64
        for entry in long_oid["expected_git_entries"]:
            entry["object_id"] = entry["object_id"][0] * 64
        validate_journal(long_oid)
        wrong_oid_length = copy.deepcopy(long_oid)
        wrong_oid_length["expected_git_entries"][0]["object_id"] = "b" * 40
        invalid.append(wrong_oid_length)
        for candidate in invalid:
            with self.subTest(entries=candidate.get("expected_git_entries")), self.assertRaises(JournalError):
                validate_journal(candidate)

    def test_phase_must_be_same_or_immediate_successor(self):
        for previous, current in (("prepared", "prepared"), ("prepared", "docs_writing"),
                                  ("docs_writing", "docs_written")):
            validate_phase_transition(previous, current)
        for previous, current in (("prepared", "docs_written"), ("docs_written", "prepared"),
                                  ("complete", "unknown"), ("prepared", "unknown")):
            with self.subTest(previous=previous, current=current), self.assertRaises(JournalError):
                validate_phase_transition(previous, current)

    def test_failed_temp_fsync_or_replace_preserves_previous_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "completion.json"
            old = _journal()
            write_journal(path, old)
            old_bytes = path.read_bytes()
            new = copy.deepcopy(old)
            new["phase"] = "docs_writing"
            for target in ("scripts.sdd_tasks.atomic.os.fsync", "scripts.sdd_tasks.atomic.os.replace"):
                with self.subTest(target=target), patch(target, side_effect=OSError("injected")):
                    with self.assertRaises(OSError):
                        write_journal(path, new, previous_phase="prepared")
                    self.assertEqual(path.read_bytes(), old_bytes)
                    self.assertEqual(read_journal(path), validate_journal(old))
                    self.assertEqual(list(Path(directory).glob(".sdd-atomic-*")), [])

    def test_missing_or_partial_journal_is_never_treated_as_initial_or_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "completion.json"
            with self.assertRaises(JournalError):
                read_journal(path)
            path.write_bytes(b"{partial")
            original = path.read_bytes()
            with self.assertRaises(JournalError):
                write_journal(path, _journal())
            self.assertEqual(path.read_bytes(), original)

    def test_updates_cannot_replace_run_result_or_document_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "completion.json"
            original = _journal()
            write_journal(path, original)
            original_bytes = path.read_bytes()
            for kind in ("run", "result", "document", "git_entries"):
                changed = copy.deepcopy(original)
                changed["phase"] = "docs_writing"
                if kind == "run":
                    changed["run_id"] = "123e4567-e89b-12d3-a456-426614174001"
                    changed["expected_result"]["run_id"] = changed["run_id"]
                elif kind == "result":
                    changed["expected_result"]["summary"] = "foreign result"
                else:
                    changed["expected_docs"][0]["path"] = "docs/other.md"
                    changed["committed_paths"] = ["src/change.py", "docs/other.md"]
                    changed["staged_paths"] = changed["committed_paths"]
                    changed["expected_git_entries"][0]["path"] = "docs/other.md"
                if kind == "git_entries":
                    changed["expected_git_entries"][0]["object_id"] = "d" * 40
                with self.subTest(kind=kind), self.assertRaises(JournalError):
                    write_journal(path, changed, previous_phase="prepared")
                self.assertEqual(path.read_bytes(), original_bytes)

    def test_all_docs_are_preflighted_before_a_third_hash_can_write_any(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, journal_path = _prepared(root, [("docs/a.md", "before-a", "after-a"),
                                               ("docs/b.md", "before-b", "after-b")])
            (root / "docs/b.md").write_text("third-state", encoding="utf-8")
            with self.assertRaisesRegex(JournalError, "JOURNAL_DOCUMENT_STATE_UNKNOWN"):
                recover_expected_documents(root, journal_path)
            self.assertEqual(read_journal(journal_path)["phase"], "docs_writing")
            self.assertEqual((root / "docs/a.md").read_text(encoding="utf-8"), "before-a")
            self.assertEqual((root / "docs/b.md").read_text(encoding="utf-8"), "third-state")

    def test_replay_recognizes_real_partial_atomic_replace_and_finishes_other_docs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, journal_path = _prepared(root, [("docs/a.md", "before-a", "after-a"),
                                               ("docs/b.md", "before-b", "after-b")])
            first = root / "docs/a.md"
            atomic_write = atomic.atomic_write

            def crash_after_replace(path, content, **kwargs):
                atomic_write(path, content, **kwargs)
                if Path(path) == first:
                    raise OSError("simulated process death")

            with patch("scripts.sdd_tasks.completion_journal.atomic.atomic_write", side_effect=crash_after_replace), \
                    self.assertRaises(OSError):
                recover_expected_documents(root, journal_path)
            self.assertEqual(read_journal(journal_path)["phase"], "docs_writing")
            self.assertEqual(first.read_text(encoding="utf-8"), "after-a")
            self.assertEqual((root / "docs/b.md").read_text(encoding="utf-8"), "before-b")
            result = recover_expected_documents(root, journal_path)
            self.assertEqual(result["phase"], "docs_written")
            self.assertEqual(first.read_text(encoding="utf-8"), "after-a")
            self.assertEqual((root / "docs/b.md").read_text(encoding="utf-8"), "after-b")

    def test_replay_restores_frozen_executable_task_and_spec_modes_repeatably(self):
        task_path, spec_path = "docs/sdd/plans/016/task-06.md", "docs/sdd/specs/016.md"
        for filemode in ("true", "false"):
            with self.subTest(core_filemode=filemode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
                subprocess.run(["git", "config", "core.filemode", filemode], cwd=str(root), check=True)
                _, journal_path = _prepared(
                    root, [(task_path, "old task", "new task"),
                           (spec_path, "old spec", "new spec")],
                    modes={task_path: "100755", spec_path: "100755"},
                )
                anchors = {item["path"]: item["mode"] for item in read_journal(journal_path)["expected_git_entries"]}
                self.assertEqual((anchors[task_path], anchors[spec_path]), ("100755", "100755"))
                result = recover_expected_documents(root, journal_path)
                self.assertEqual(result["phase"], "docs_written")
                for path, contents in ((task_path, "new task"), (spec_path, "new spec")):
                    target = root / path
                    self.assertEqual(target.read_text(encoding="utf-8"), contents)
                    self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)
                replay = recover_expected_documents(root, journal_path)
                self.assertEqual(replay["phase"], "docs_written")
                for path in (task_path, spec_path):
                    self.assertEqual(stat.S_IMODE((root / path).stat().st_mode), 0o700)

    def test_missing_document_parent_is_created_only_after_prepared(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = "docs/sdd/runs/016/task-06/summary.md"
            _, journal_path = _prepared(root, [(path, None, "summary")])
            self.assertFalse((root / path).parent.exists())
            self.assertEqual(read_journal(journal_path)["phase"], "prepared")
            result = recover_expected_documents(root, journal_path)
            self.assertEqual(result["phase"], "docs_written")
            self.assertEqual((root / path).read_text(encoding="utf-8"), "summary")

    def test_symlink_document_parent_is_refused_without_writing_outside_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, journal_path = _prepared(root, [("docs/summary.md", None, "summary")])
            outside = root / "outside"
            outside.mkdir()
            (root / "docs").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(JournalError, "JOURNAL_DOCUMENT_UNSAFE"):
                recover_expected_documents(root, journal_path)
            self.assertFalse((outside / "summary.md").exists())
            self.assertEqual(read_journal(journal_path)["phase"], "docs_writing")

    def test_docs_written_is_not_persisted_until_after_hashes_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, journal_path = _prepared(root, [("docs/a.md", "before", "after")])
            target = root / "docs/a.md"
            atomic_write = atomic.atomic_write

            def corrupt_after_replace(path, content, **kwargs):
                atomic_write(path, content, **kwargs)
                if Path(path) == target:
                    target.write_text("third-state", encoding="utf-8")

            with patch("scripts.sdd_tasks.completion_journal.atomic.atomic_write", side_effect=corrupt_after_replace), \
                    self.assertRaisesRegex(JournalError, "JOURNAL_DOCUMENT_AFTER_HASH_MISMATCH"):
                recover_expected_documents(root, journal_path)
            self.assertEqual(target.read_text(encoding="utf-8"), "third-state")
            self.assertEqual(read_journal(journal_path)["phase"], "docs_writing")


if __name__ == "__main__":
    unittest.main()
