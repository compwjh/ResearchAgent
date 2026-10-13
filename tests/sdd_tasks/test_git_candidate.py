import copy
import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.sdd_tasks import git_candidate as candidate_module
from scripts.sdd_tasks.completion_journal import recover_expected_documents, write_journal
from scripts.sdd_tasks.git_candidate import create_candidate_commit
from scripts.sdd_tasks.git_candidate_index import build_candidate_tree
from scripts.sdd_tasks.git_candidate_objects import check_source_anchors, store_verified_blobs
from scripts.sdd_tasks.git_expected_entries import capture_expected_git_entries
from scripts.sdd_tasks.git_expected_entries_io import GitExpectedEntriesError
from scripts.sdd_tasks.git_index import read_index_snapshot
from scripts.sdd_tasks.git_index_lock import acquire_owned_index_lock
from scripts.sdd_tasks.journal_schema import validate_journal
from tests.sdd_tasks.test_completion_journal import _journal
from tests.sdd_tasks.test_git_index_lock import _git, _worktree_fixture


def _candidate_fixture(directory, *, with_link=False, with_exotic=False):
    root = _worktree_fixture(directory)
    old_path, new_path = "src/old ;$(literal)\nname.txt", "src/new ;$(literal)\nname.txt"
    if with_exotic:
        old_file = root / old_path
        old_file.write_bytes(b"renamed old bytes\n")
        old_oid = _git(root, "hash-object", "-w", "--stdin", input=b"renamed old bytes\n").decode().strip()
        _git(root, "update-index", "--add", "--cacheinfo", f"100644,{old_oid},{old_path}")
        tree = _git(root, "write-tree").decode().strip()
        head = _git(root, "commit-tree", tree, "-m", "exotic path baseline").decode().strip()
        _git(root, "update-ref", "refs/heads/main", head)
        old_file.unlink()
        target = root / new_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"renamed new bytes\n")
    head = _git(root, "rev-parse", "HEAD").decode().strip()
    (root / "src/change.py").write_bytes(b"candidate source\n")
    outsider = _git(root, "hash-object", "-w", "--stdin", input=b"outsider stage\n").decode().strip()
    _git(root, "update-index", "--add", "--cacheinfo", f"100644,{outsider},outsider.txt")
    journal = _journal()
    journal["base_commit"] = journal["original_head"] = head
    journal["changed_paths"][0].update(
        before_sha256=hashlib.sha256(b"before source\n").hexdigest(),
        after_sha256=hashlib.sha256(b"candidate source\n").hexdigest(),
    )
    if with_link:
        (root / "src/target-a").write_bytes(b"same resolved bytes\n")
        (root / "src/target-b").write_bytes(b"same resolved bytes\n")
        (root / "src/link").symlink_to("target-a")
        journal["allowed_paths"].append("src/link")
        journal["changed_paths"].append(
            {"path": "src/link", "before_sha256": "4" * 64, "after_sha256": "5" * 64}
        )
        journal["committed_paths"].append("src/link")
        journal["staged_paths"].append("src/link")
    if with_exotic:
        journal["allowed_paths"].extend((old_path, new_path))
        journal["changed_paths"].extend((
            {"path": old_path, "before_sha256": hashlib.sha256(b"renamed old bytes\n").hexdigest(),
             "after_sha256": None},
            {"path": new_path, "before_sha256": None,
             "after_sha256": hashlib.sha256(b"renamed new bytes\n").hexdigest()},
        ))
        journal["committed_paths"].extend((old_path, new_path))
        journal["staged_paths"].extend((old_path, new_path))
    paths = journal["committed_paths"]
    journal["index_before"] = read_index_snapshot(root, paths, original_head=head)
    journal["expected_git_entries"] = capture_expected_git_entries(
        root, paths, expected_docs=journal["expected_docs"], original_head=head
    )
    journal_path = root / ".sdd/runtime/runs" / journal["run_id"] / "completion.json"
    journal_path.parent.mkdir(parents=True)
    write_journal(journal_path, journal)
    recover_expected_documents(root, journal_path)
    locked = acquire_owned_index_lock(root, journal_path)
    return root, journal_path, journal, locked


def _replace_index(root, args, input_data=None):
    index = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip())
    alternate = index.with_name("index.qa-alternate")
    alternate.write_bytes(index.read_bytes())
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = str(alternate)
    subprocess.run(["git", "-C", str(root), *args], input=input_data, env=env,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    os.replace(alternate, index)
    return index, index.read_bytes()


def _candidate_state(journal):
    after = dict(journal["index_observed_before"])
    after["committed_entries"] = [
        {"path": item["path"], "stage": 0, "mode": item["mode"], "object_id": item["object_id"]}
        for item in journal["expected_git_entries"] if item["mode"] is not None
    ]
    # This is a shape-only J6 fixture: J6 has not yet built or durably recorded an index image.
    candidate = dict(journal, phase="index_after_prepared", index_after=after,
                     index_recovery_stage="lock_index_durable")
    return validate_journal(candidate)


def _object_exists(root, oid):
    return subprocess.run(["git", "-C", str(root), "cat-file", "-e", oid],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0


class GitCandidateTests(unittest.TestCase):
    def test_verified_blobs_tree_and_commit_exclude_staged_outsider(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, _, locked = _candidate_fixture(directory)
            state = _candidate_state(locked)
            head = _git(root, "rev-parse", "HEAD").decode().strip()
            refs = _git(root, "for-each-ref", "--format=%(refname) %(objectname)")
            index_path = Path(state["index_before"]["git_index_path"])
            index_bytes = index_path.read_bytes()
            lock_path = index_path.with_name("index.lock")
            lock_bytes = lock_path.read_bytes()
            object_ids = [item["object_id"] for item in state["expected_git_entries"]]
            self.assertTrue(all(not _object_exists(root, oid) for oid in object_ids))

            store_verified_blobs(root, state)
            tree = build_candidate_tree(root, state)
            commit = create_candidate_commit(root, state)
            self.assertTrue(all(_object_exists(root, oid) for oid in object_ids))
            listing = _git(root, "ls-tree", "-r", "-z", tree)
            for item in state["expected_git_entries"]:
                self.assertIn(f"{item['mode']} blob {item['object_id']}\t{item['path']}\0".encode(), listing)
            self.assertNotIn(b"outsider.txt", listing)
            changed = _git(root, "diff-tree", "--no-commit-id", "--no-renames", "-r", "--name-only", "-z",
                           head, tree).decode().rstrip("\0").split("\0")
            self.assertEqual(set(changed), set(state["committed_paths"]))
            raw_commit = _git(root, "cat-file", "commit", commit).decode()
            self.assertEqual(raw_commit.splitlines()[:2], [f"tree {tree}", f"parent {head}"])
            self.assertEqual(raw_commit.split("\n\n", 1)[1].rstrip("\n"), "feat: complete task")
            self.assertEqual(_git(root, "rev-parse", "HEAD").decode().strip(), head)
            self.assertEqual(_git(root, "for-each-ref", "--format=%(refname) %(objectname)"), refs)
            self.assertEqual(index_path.read_bytes(), index_bytes)
            self.assertEqual(lock_path.read_bytes(), lock_bytes)

    def test_object_storage_refuses_anchor_drift_and_active_attributes(self):
        cases = ("link", "mode", "document", "attributes")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root, _, _, locked = _candidate_fixture(directory, with_link=case == "link")
                state = _candidate_state(locked)
                if case == "link":
                    (root / "src/link").unlink()
                    (root / "src/link").symlink_to("target-b")
                    self.assertEqual((root / "src/link").read_bytes(), (root / "src/target-a").read_bytes())
                    error = "GIT_CANDIDATE_ANCHOR_MISMATCH"
                elif case == "mode":
                    (root / "src/change.py").chmod(0o755)
                    error = "GIT_CANDIDATE_ANCHOR_MISMATCH"
                elif case == "document":
                    (root / "docs/task.md").write_text("third document state\n", encoding="utf-8")
                    error = "GIT_CANDIDATE_DOCUMENT_CHANGED"
                else:
                    (root / ".gitattributes").write_text("src/change.py filter=upper\n", encoding="utf-8")
                    error = "GIT_EXPECTED_CONVERSION_ACTIVE"
                with self.assertRaisesRegex(GitExpectedEntriesError, error):
                    store_verified_blobs(root, state)

    def test_candidate_tree_handles_exotic_new_delete_and_rename_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, _, locked = _candidate_fixture(directory, with_exotic=True)
            state = _candidate_state(locked)
            head = state["original_head"]
            index = Path(state["index_before"]["git_index_path"])
            before = index.read_bytes()
            store_verified_blobs(root, state)
            tree = build_candidate_tree(root, state)
            entries = _git(root, "ls-tree", "-r", "-z", tree)
            tree_paths = {record.split(b"\t", 1)[1] for record in entries.split(b"\0") if record}
            for item in state["expected_git_entries"]:
                entry = f"{item['mode']} blob {item['object_id']}\t{item['path']}\0".encode()
                if item["mode"] is None:
                    self.assertNotIn(item["path"].encode("utf-8"), tree_paths)
                else:
                    self.assertIn(entry, entries)
            changed = _git(root, "diff-tree", "--no-commit-id", "--no-renames", "-r", "--name-only", "-z",
                           head, tree).decode().rstrip("\0").split("\0")
            self.assertEqual(set(changed), set(state["committed_paths"]))
            self.assertEqual(index.read_bytes(), before)
            self.assertEqual(_git(root, "rev-parse", "HEAD").decode().strip(), head)

    def test_candidate_tree_refuses_target_staged_and_unmerged_index_entries(self):
        for unmerged in (False, True):
            with self.subTest(unmerged=unmerged), tempfile.TemporaryDirectory() as directory:
                root, _, _, locked = _candidate_fixture(directory)
                state = _candidate_state(locked)
                if unmerged:
                    original = _git(root, "rev-parse", "HEAD:src/change.py").decode().strip()
                    other = _git(root, "hash-object", "-w", "--stdin", input=b"conflict side\n").decode().strip()
                    records = b"".join(f"100644 {oid} {stage}\tsrc/change.py\n".encode()
                                        for stage, oid in ((1, original), (2, other), (3, original)))
                    args, data = ("update-index", "--index-info"), records
                    error = "GIT_TARGET_UNMERGED"
                else:
                    other = _git(root, "hash-object", "-w", "--stdin", input=b"raced stage\n").decode().strip()
                    args, data = ("update-index", "--cacheinfo", f"100644,{other},src/change.py"), None
                    error = "GIT_TARGET_PRESTAGED"
                index, changed_index = _replace_index(root, args, data)
                lock = index.with_name("index.lock").read_bytes()
                with self.assertRaisesRegex(ValueError, error):
                    build_candidate_tree(root, state)
                self.assertEqual(index.read_bytes(), changed_index)
                self.assertEqual(index.with_name("index.lock").read_bytes(), lock)

    def test_candidate_refuses_bad_index_after_anchor_and_head_race_without_extra_ref(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, _, locked = _candidate_fixture(directory)
            state = _candidate_state(locked)
            bad = copy.deepcopy(state)
            bad["index_after"]["committed_entries"][0]["object_id"] = "f" * len(state["original_head"])
            with self.assertRaisesRegex(GitExpectedEntriesError, "GIT_CANDIDATE_INDEX_ANCHOR_MISMATCH"):
                build_candidate_tree(root, bad)

        with tempfile.TemporaryDirectory() as directory:
            root, _, _, locked = _candidate_fixture(directory)
            state = _candidate_state(locked)
            index = Path(state["index_before"]["git_index_path"])
            index_bytes, lock_path = index.read_bytes(), index.with_name("index.lock")
            builder = candidate_module.build_candidate_tree
            raced_refs = []

            def advance_after_tree(worktree, journal):
                tree = builder(worktree, journal)
                competitor = _git(root, "commit-tree", tree, "-m", "raced head").decode().strip()
                _git(root, "update-ref", "HEAD", competitor)
                raced_refs.append(_git(root, "for-each-ref", "--format=%(refname) %(objectname)"))
                return tree

            with (patch.object(candidate_module, "build_candidate_tree", side_effect=advance_after_tree),
                  self.assertRaisesRegex(ValueError, "GIT_HEAD_CHANGED")):
                create_candidate_commit(root, state)
            self.assertEqual(_git(root, "for-each-ref", "--format=%(refname) %(objectname)"), raced_refs[0])
            self.assertEqual(index.read_bytes(), index_bytes)
            self.assertTrue(lock_path.exists())

    def test_source_anchor_check_accepts_candidate_head_then_refuses_content_drift(self):
        for case in ("link", "mode", "source", "document"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root, _, _, locked = _candidate_fixture(directory, with_link=case == "link")
                state = _candidate_state(locked)
                index = Path(state["index_before"]["git_index_path"])
                original_index = index.read_bytes()
                candidate = create_candidate_commit(root, state)
                _git(root, "update-ref", "HEAD", candidate)
                self.assertEqual(index.read_bytes(), original_index)
                check_source_anchors(root, state)
                if case == "link":
                    (root / "src/link").unlink()
                    (root / "src/link").symlink_to("target-b")
                    error = "GIT_CANDIDATE_ANCHOR_MISMATCH"
                elif case == "mode":
                    (root / "src/change.py").chmod(0o755)
                    error = "GIT_CANDIDATE_ANCHOR_MISMATCH"
                elif case == "source":
                    (root / "src/change.py").write_bytes(b"changed source bytes\n")
                    error = "GIT_CANDIDATE_ANCHOR_MISMATCH"
                else:
                    (root / "docs/task.md").write_text("changed document bytes\n", encoding="utf-8")
                    error = "GIT_CANDIDATE_DOCUMENT_CHANGED"
                with self.assertRaisesRegex(GitExpectedEntriesError, error):
                    check_source_anchors(root, state)


if __name__ == "__main__":
    unittest.main()
