import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.sdd_tasks import git_index
from scripts.sdd_tasks.git_index import GitIndexError, read_index_snapshot


def _git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _repo(directory, files):
    root = Path(directory) / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "config", "user.email", "fixture@example.invalid")
    for name, content in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(root, "add", "--", *[name for name, _ in files])
    _git(root, "commit", "-qm", "index fixture")
    return root


def _index(root):
    return Path(_git(root, "rev-parse", "--absolute-git-dir")) / "index"


def _entries(root):
    raw = subprocess.check_output(["git", "-C", str(root), "ls-files", "--stage", "-z"])
    result = []
    for record in raw.split(b"\0"):
        if record:
            header, path = record.split(b"\t", 1)
            mode, object_id, stage = header.decode("ascii").split(" ")
            result.append({"path": path.decode("utf-8"), "stage": int(stage),
                           "mode": mode, "object_id": object_id})
    return result


def _other_hash(entries, targets):
    others = sorted((entry for entry in entries if entry["path"] not in targets),
                    key=lambda entry: (entry["path"].encode("utf-8"), entry["stage"]))
    payload = json.dumps(others, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _blob(root, content):
    return subprocess.check_output(
        ["git", "-C", str(root), "hash-object", "-w", "--stdin"], input=content
    ).decode("ascii").strip()


def _set_unmerged_index(root, path):
    blobs = [_blob(root, value) for value in (b"base\n", b"ours\n", b"theirs\n")]
    zero = "0" * len(blobs[0])
    lines = [f"0 {zero} 0\t{path}"]
    lines.extend(f"100644 {oid} {stage}\t{path}" for stage, oid in enumerate(blobs, 1))
    subprocess.run(["git", "-C", str(root), "update-index", "--index-info"],
                   input="\n".join(lines) + "\n", text=True, check=True)


class GitIndexSnapshotTests(unittest.TestCase):
    def test_real_snapshot_preserves_staged_outsider_and_special_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            names = ["space dir/file name.txt", "line\nbreak.txt"]
            root = _repo(directory, [(names[0], "one"), (names[1], "two"), ("outsider.txt", "old")])
            (root / "outsider.txt").write_text("staged outsider", encoding="utf-8")
            _git(root, "add", "--", "outsider.txt")
            index_path, head = _index(root), _git(root, "rev-parse", "HEAD")
            before = index_path.read_bytes()
            entries = _entries(root)
            snapshot = read_index_snapshot(root, names, original_head=head)
            targets = set(names)
            committed = sorted((entry for entry in entries if entry["path"] in targets),
                               key=lambda entry: (entry["path"].encode("utf-8"), entry["stage"]))
            self.assertEqual(snapshot["committed_entries"], committed)
            self.assertEqual([entry["path"] for entry in committed], sorted(names, key=lambda x: x.encode("utf-8")))
            self.assertEqual(snapshot["other_entries_sha256"], _other_hash(entries, targets))
            self.assertEqual(snapshot["index_sha256"], hashlib.sha256(before).hexdigest())
            self.assertEqual(index_path.read_bytes(), before)
            self.assertFalse(index_path.with_name("index.lock").exists())

    def test_target_staged_change_is_refused_without_index_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = _repo(directory, [("target.txt", "base"), ("outsider.txt", "base")])
            (root / "target.txt").write_text("staged target", encoding="utf-8")
            _git(root, "add", "--", "target.txt")
            index_path = _index(root)
            before = index_path.read_bytes()
            head = _git(root, "rev-parse", "HEAD")
            with self.assertRaisesRegex(GitIndexError, "GIT_TARGET_PRESTAGED"):
                read_index_snapshot(root, ["target.txt"], original_head=head)
            self.assertEqual(index_path.read_bytes(), before)
            self.assertFalse(index_path.with_name("index.lock").exists())

    def test_unmerged_target_stages_are_refused_and_left_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = _repo(directory, [("target.txt", "base\n")])
            _set_unmerged_index(root, "target.txt")
            index_path = _index(root)
            before = index_path.read_bytes()
            head = _git(root, "rev-parse", "HEAD")
            with self.assertRaisesRegex(GitIndexError, "GIT_TARGET_UNMERGED"):
                read_index_snapshot(root, ["target.txt"], original_head=head)
            self.assertEqual(index_path.read_bytes(), before)
            self.assertEqual(_git(root, "rev-parse", "HEAD"), head)
            self.assertFalse(index_path.with_name("index.lock").exists())

    def test_unregistered_subdirectory_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = _repo(directory, [("target.txt", "base")])
            subdirectory = root / "nested"
            subdirectory.mkdir()
            head = _git(root, "rev-parse", "HEAD")
            with self.assertRaisesRegex(GitIndexError, "GIT_WORKTREE_UNREGISTERED"):
                read_index_snapshot(subdirectory, ["target.txt"], original_head=head)

    def test_fake_git_index_path_is_refused_without_mutating_real_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = _repo(directory, [("target.txt", "base")])
            index_path = _index(root)
            before = index_path.read_bytes()
            head = _git(root, "rev-parse", "HEAD")
            real_git = git_index._git
            fake_path = (Path(directory) / "fake-index").as_posix().encode() + b"\n"

            def fake_index_path(worktree, *args, **kwargs):
                if args == ("rev-parse", "--path-format=absolute", "--git-path", "index"):
                    return fake_path
                return real_git(worktree, *args, **kwargs)

            with patch("scripts.sdd_tasks.git_index._git", side_effect=fake_index_path), \
                    self.assertRaisesRegex(GitIndexError, "GIT_INDEX_PATH_MISMATCH"):
                read_index_snapshot(root, ["target.txt"], original_head=head)
            self.assertEqual(index_path.read_bytes(), before)

    def test_symlinked_index_is_refused_and_target_bytes_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = _repo(directory, [("target.txt", "base")])
            index_path = _index(root)
            outside = Path(directory) / "saved-index"
            before = index_path.read_bytes()
            outside.write_bytes(before)
            index_path.unlink()
            index_path.symlink_to(outside)
            head = _git(root, "rev-parse", "HEAD")
            with self.assertRaisesRegex(GitIndexError, "GIT_INDEX_PATH_MISMATCH"):
                read_index_snapshot(root, ["target.txt"], original_head=head)
            self.assertTrue(index_path.is_symlink())
            self.assertEqual(outside.read_bytes(), before)

    def test_head_race_after_real_index_query_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = _repo(directory, [("target.txt", "base")])
            head = _git(root, "rev-parse", "HEAD")
            branch = _git(root, "symbolic-ref", "HEAD")
            real_git = git_index._git
            changed = []

            def race_head(worktree, *args, **kwargs):
                result = real_git(worktree, *args, **kwargs)
                if args == ("ls-files", "--stage", "-z") and not changed:
                    tree = _git(root, "rev-parse", "HEAD^{tree}")
                    new_head = _git(root, "commit-tree", tree, "-p", head, "-m", "fixture race")
                    _git(root, "update-ref", branch, new_head, head)
                    changed.append(new_head)
                return result

            with patch("scripts.sdd_tasks.git_index._git", side_effect=race_head), \
                    self.assertRaisesRegex(GitIndexError, "GIT_INDEX_OR_HEAD_CHANGED"):
                read_index_snapshot(root, ["target.txt"], original_head=head)
            self.assertEqual(_git(root, "rev-parse", "HEAD"), changed[0])

    def test_index_race_after_real_index_query_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = _repo(directory, [("target.txt", "base")])
            head = _git(root, "rev-parse", "HEAD")
            index_path = _index(root)
            before = index_path.read_bytes()
            real_git = git_index._git
            changed = []

            def race_index(worktree, *args, **kwargs):
                result = real_git(worktree, *args, **kwargs)
                if args == ("ls-files", "--stage", "-z") and not changed:
                    oid = _blob(root, b"raced outsider\n")
                    _git(root, "update-index", "--add", "--cacheinfo", f"100644,{oid},raced.txt")
                    changed.append(oid)
                return result

            with patch("scripts.sdd_tasks.git_index._git", side_effect=race_index), \
                    self.assertRaisesRegex(GitIndexError, "GIT_INDEX_OR_HEAD_CHANGED"):
                read_index_snapshot(root, ["target.txt"], original_head=head)
            self.assertNotEqual(index_path.read_bytes(), before)
            self.assertIn({"path": "raced.txt", "stage": 0, "mode": "100644",
                           "object_id": changed[0]}, _entries(root))


if __name__ == "__main__":
    unittest.main()
