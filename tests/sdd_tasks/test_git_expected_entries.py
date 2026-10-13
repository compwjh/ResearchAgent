import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.sdd_tasks.git_expected_entries as capture_module
from scripts.sdd_tasks.git_expected_entries import capture_expected_git_entries
from scripts.sdd_tasks.git_expected_entries_io import GitExpectedEntriesError


def _git(root, *args, input_data=None):
    return subprocess.check_output(["git", "-C", str(root), *args], input=input_data)


def _blob(root, payload):
    return _git(root, "hash-object", "--stdin", input_data=payload).decode().strip()


def _repository(directory, *, files=(), links=()):
    root = Path(directory) / "repo"
    root.mkdir()
    subprocess.run(["git", "-C", str(root), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Fixture"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "fixture@example.invalid"], check=True)
    for name, payload, file_mode in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        path.chmod(file_mode)
        blob = _git(root, "hash-object", "-w", "--stdin", input_data=payload).decode().strip()
        git_mode = "100755" if file_mode & 0o111 else "100644"
        _git(root, "update-index", "--add", "--cacheinfo", f"{git_mode},{blob},{name}")
    for name, target in links:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)
        blob = _git(root, "hash-object", "-w", "--stdin", input_data=os.fsencode(target)).decode().strip()
        _git(root, "update-index", "--add", "--cacheinfo", f"120000,{blob},{name}")
    tree = _git(root, "write-tree").decode().strip()
    head = _git(root, "commit-tree", tree, "-m", "expected-entry fixture").decode().strip()
    _git(root, "update-ref", "refs/heads/main", head)
    return root, head


class ExpectedGitEntriesTests(unittest.TestCase):
    def test_raw_symlink_doc_and_deletion_blobs_are_exact_and_sorted(self):
        with tempfile.TemporaryDirectory() as directory:
            files = (("target.bin", b"resolved artifact bytes\n", 0o644),
                     ("deleted.txt", b"old content\n", 0o644),
                     ("docs/summary.md", b"old document bytes\n", 0o644))
            root, head = _repository(directory, files=files, links=(("link.bin", "target.bin"),))
            (root / "deleted.txt").unlink()
            doc_content = "résumé from expected document\n"
            paths = ["link.bin", "deleted.txt", "docs/summary.md"]

            entries = capture_expected_git_entries(
                root, paths,
                expected_docs=[{"path": "docs/summary.md", "content": doc_content}],
                original_head=head,
            )
            self.assertEqual([entry["path"] for entry in entries], sorted(paths, key=lambda p: p.encode("utf-8")))
            indexed = {entry["path"]: entry for entry in entries}
            self.assertEqual(indexed["link.bin"], {
                "path": "link.bin", "mode": "120000", "object_id": _blob(root, b"target.bin")})
            self.assertNotEqual(indexed["link.bin"]["object_id"], _blob(root, b"resolved artifact bytes\n"))
            self.assertEqual(indexed["deleted.txt"], {"path": "deleted.txt", "mode": None, "object_id": None})
            self.assertEqual(indexed["docs/summary.md"]["object_id"], _blob(root, doc_content.encode("utf-8")))
            self.assertNotEqual(indexed["docs/summary.md"]["object_id"], _blob(root, b"old document bytes\n"))
            self.assertEqual((root / "docs/summary.md").read_bytes(), b"old document bytes\n")

    def test_filemode_false_preserves_tracked_mode_and_infers_new_executable_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root, head = _repository(directory, files=(("tracked.sh", b"#!/bin/sh\n", 0o755),))
            subprocess.run(["git", "-C", str(root), "config", "core.filemode", "false"], check=True)
            (root / "tracked.sh").chmod(0o644)
            new = root / "new.sh"
            new.write_bytes(b"#!/bin/sh\n")
            new.chmod(0o755)

            entries = capture_expected_git_entries(
                root, ["new.sh", "tracked.sh"], expected_docs=[], original_head=head
            )
            self.assertEqual(entries, [
                {"path": "new.sh", "mode": "100755", "object_id": _blob(root, b"#!/bin/sh\n")},
                {"path": "tracked.sh", "mode": "100755", "object_id": _blob(root, b"#!/bin/sh\n")},
            ])

    def test_active_conversion_attributes_and_autocrlf_are_refused(self):
        assignments = ("filter=upper", "working-tree-encoding=UTF-8", "text", "eol=lf",
                       "crlf=input", "ident")
        for assignment in assignments:
            with self.subTest(assignment=assignment), tempfile.TemporaryDirectory() as directory:
                root, head = _repository(directory, files=(("tracked.txt", b"raw bytes\n", 0o644),))
                (root / ".gitattributes").write_text(f"tracked.txt {assignment}\n", encoding="utf-8")
                with self.assertRaisesRegex(GitExpectedEntriesError, "GIT_EXPECTED_CONVERSION_ACTIVE"):
                    capture_expected_git_entries(root, ["tracked.txt"], expected_docs=[], original_head=head)
        with tempfile.TemporaryDirectory() as directory:
            root, head = _repository(directory, files=(("tracked.txt", b"raw bytes\n", 0o644),))
            subprocess.run(["git", "-C", str(root), "config", "core.autocrlf", "true"], check=True)
            with self.assertRaisesRegex(GitExpectedEntriesError, "GIT_EXPECTED_CONVERSION_ACTIVE"):
                capture_expected_git_entries(root, ["tracked.txt"], expected_docs=[], original_head=head)

    def test_disabled_attributes_are_allowed_and_autocrlf_input_or_invalid_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            root, head = _repository(directory, files=(("tracked.txt", b"raw bytes\n", 0o644),))
            (root / ".gitattributes").write_text("tracked.txt -text -filter -ident\n", encoding="utf-8")
            self.assertEqual(capture_expected_git_entries(
                root, ["tracked.txt"], expected_docs=[], original_head=head
            )[0]["object_id"], _blob(root, b"raw bytes\n"))
        for value in ("input", "invalid-bool"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                root, head = _repository(directory, files=(("tracked.txt", b"raw bytes\n", 0o644),))
                subprocess.run(["git", "-C", str(root), "config", "core.autocrlf", value], check=True)
                with self.assertRaises(ValueError):
                    capture_expected_git_entries(root, ["tracked.txt"], expected_docs=[], original_head=head)

    def test_link_text_and_file_mode_source_races_refuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root, head = _repository(
                directory, files=(("one", b"same target bytes", 0o644), ("two", b"same target bytes", 0o644)),
                links=(("link", "one"),),
            )
            read_source = capture_module.source
            changed = False

            def retarget_after_read(root_arg, path):
                nonlocal changed
                result = read_source(root_arg, path)
                if path == "link" and not changed:
                    (root / "link").unlink()
                    (root / "link").symlink_to("two")
                    changed = True
                return result

            with (patch.object(capture_module, "source", side_effect=retarget_after_read),
                  self.assertRaisesRegex(GitExpectedEntriesError, "GIT_EXPECTED_SOURCE_CHANGED")):
                capture_expected_git_entries(root, ["link"], expected_docs=[], original_head=head)

        with tempfile.TemporaryDirectory() as directory:
            root, head = _repository(directory, files=(("script", b"#!/bin/sh\n", 0o644),))
            read_source = capture_module.source
            changed = False

            def chmod_after_read(root_arg, path):
                nonlocal changed
                result = read_source(root_arg, path)
                if path == "script" and not changed:
                    (root / "script").chmod(0o755)
                    changed = True
                return result

            with (patch.object(capture_module, "source", side_effect=chmod_after_read),
                  self.assertRaisesRegex(GitExpectedEntriesError, "GIT_EXPECTED_SOURCE_CHANGED")):
                capture_expected_git_entries(root, ["script"], expected_docs=[], original_head=head)

    def test_index_head_and_config_races_refuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root, head = _repository(directory, files=(("tracked.txt", b"raw bytes\n", 0o644),))
            snapshot = capture_module.read_index_snapshot
            calls = 0

            def add_outsider_after_snapshot(*args, **kwargs):
                nonlocal calls
                result = snapshot(*args, **kwargs)
                calls += 1
                if calls == 1:
                    blob = _git(root, "hash-object", "-w", "--stdin", input_data=b"outsider").decode().strip()
                    _git(root, "update-index", "--add", "--cacheinfo", f"100644,{blob},outsider.txt")
                return result

            with (patch.object(capture_module, "read_index_snapshot", side_effect=add_outsider_after_snapshot),
                  self.assertRaisesRegex(GitExpectedEntriesError, "GIT_EXPECTED_INDEX_OR_HEAD_CHANGED")):
                capture_expected_git_entries(root, ["tracked.txt"], expected_docs=[], original_head=head)

        with tempfile.TemporaryDirectory() as directory:
            root, head = _repository(directory, files=(("tracked.txt", b"raw bytes\n", 0o644),))
            snapshot = capture_module.read_index_snapshot
            changed = False

            def advance_head_after_snapshot(*args, **kwargs):
                nonlocal changed
                result = snapshot(*args, **kwargs)
                if not changed:
                    tree = _git(root, "write-tree").decode().strip()
                    new_head = _git(root, "commit-tree", tree, "-m", "raced head").decode().strip()
                    _git(root, "update-ref", "HEAD", new_head)
                    changed = True
                return result

            with (patch.object(capture_module, "read_index_snapshot", side_effect=advance_head_after_snapshot),
                  self.assertRaisesRegex(ValueError, "GIT_HEAD_CHANGED")):
                capture_expected_git_entries(root, ["tracked.txt"], expected_docs=[], original_head=head)

        with tempfile.TemporaryDirectory() as directory:
            root, head = _repository(directory, files=(("tracked.txt", b"raw bytes\n", 0o644),))
            read_config = capture_module.config
            changed = False

            def change_filemode_after_read(root_arg, key, default):
                nonlocal changed
                result = read_config(root_arg, key, default)
                if key == "core.filemode" and not changed:
                    subprocess.run(["git", "-C", str(root), "config", "core.filemode", "false"], check=True)
                    changed = True
                return result

            with (patch.object(capture_module, "config", side_effect=change_filemode_after_read),
                  self.assertRaisesRegex(GitExpectedEntriesError, "GIT_EXPECTED_CONFIG_CHANGED")):
                capture_expected_git_entries(root, ["tracked.txt"], expected_docs=[], original_head=head)


if __name__ == "__main__":
    unittest.main()
