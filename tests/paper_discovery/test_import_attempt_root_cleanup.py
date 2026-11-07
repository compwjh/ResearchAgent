"""Regression tests for _cleanup_attempt_root when shutil.rmtree is wrapped.

The production interpreter injects a sitecustomize shim that replaces
``shutil.rmtree`` with a wrapper not forwarding the ``avoids_symlink_attacks``
attribute.  The cleanup must still remove an import-owned attempt root when the
platform is fd-capable, and must stay fail-closed when it is not.
"""

import os
import shutil
import tempfile
from pathlib import Path

import backend.app.paper_discovery.application.paper_import as paper_import_module
from backend.app.paper_discovery.application.paper_import import _cleanup_attempt_root


def _make_attempt_root(tmp_path: Path) -> Path:
    root = Path(tempfile.mkdtemp(prefix="paper-import-", dir=str(tmp_path)))
    (root / "inner.txt").write_text("data", encoding="utf-8")
    return root


def test_cleanup_attempt_root_removes_tree_without_capability_marker(tmp_path, monkeypatch):
    """Marker missing (wrapped rmtree) but fd-capable platform still deletes."""
    real_rmtree = shutil.rmtree
    monkeypatch.setattr(paper_import_module.shutil, "_use_fd_functions", True)
    captured = {}

    def wrapper(path, *args, **kwargs):
        captured["called"] = True
        return real_rmtree(path, *args, **kwargs)

    # wrapper does not forward avoids_symlink_attacks -> marker is None
    monkeypatch.setattr(paper_import_module.shutil, "rmtree", wrapper)

    root = _make_attempt_root(tmp_path)
    token = (root.lstat().st_dev, root.lstat().st_ino)

    _cleanup_attempt_root(root, expected_token=token)

    assert captured.get("called", False) is True
    assert not root.exists()


def test_cleanup_attempt_root_fail_closed_without_fd_capability(tmp_path, monkeypatch):
    """No marker and no fd capability must keep the root (fail-closed)."""
    real_rmtree = shutil.rmtree
    monkeypatch.setattr(paper_import_module.shutil, "_use_fd_functions", False)
    captured = {}

    def wrapper(path, *args, **kwargs):
        captured["called"] = True
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(paper_import_module.shutil, "rmtree", wrapper)

    root = _make_attempt_root(tmp_path)
    token = (root.lstat().st_dev, root.lstat().st_ino)

    _cleanup_attempt_root(root, expected_token=token)

    assert not captured.get("called", False)
    assert root.exists()


def test_cleanup_attempt_root_refuses_token_mismatch(tmp_path, monkeypatch):
    """Capable platform still refuses a non-matching dev/ino token."""
    real_rmtree = shutil.rmtree
    captured = {}

    def wrapper(path, *args, **kwargs):
        captured["called"] = True
        return real_rmtree(path, *args, **kwargs)

    wrapper.avoids_symlink_attacks = True  # simulate a capable platform
    monkeypatch.setattr(paper_import_module.shutil, "rmtree", wrapper)

    root = _make_attempt_root(tmp_path)
    wrong_token = (root.lstat().st_dev, root.lstat().st_ino + 9999)

    _cleanup_attempt_root(root, expected_token=wrong_token)

    assert not captured.get("called", False)
    assert root.exists()


def test_rmtree_capability_detected_when_shim_replaces_unlink_rmdir(tmp_path, monkeypatch):
    """Shim swaps os.unlink/os.rmdir for new objects; detection must use names.

    The production sitecustomize shim replaces ``os.unlink`` / ``os.rmdir`` with
    brand-new function objects (different identity) while ``os.supports_dir_fd``
    still references the originals.  An identity-based ``issubset`` comparison
    would then falsely report no fd support and leave the attempt root behind.
    Capability must be judged by the function ``__name__`` taken from
    ``os.supports_dir_fd`` (which retains the original objects), so the
    detection stays True and ``_cleanup_attempt_root`` still removes the tree.
    """
    real_unlink = os.unlink
    real_rmdir = os.rmdir

    def shim_unlink(path, *args, **kwargs):
        return real_unlink(path, *args, **kwargs)

    def shim_rmdir(path, *args, **kwargs):
        return real_rmdir(path, *args, **kwargs)

    # The shim keeps the same public names but swaps the underlying objects,
    # exactly like the sitecustomize injection observed on the host.
    shim_unlink.__name__ = "unlink"
    shim_rmdir.__name__ = "rmdir"
    monkeypatch.setattr(paper_import_module.os, "unlink", shim_unlink)
    monkeypatch.setattr(paper_import_module.os, "rmdir", shim_rmdir)

    # rmtree wrapper without capability marker, platform fd-capable.
    real_rmtree = shutil.rmtree
    monkeypatch.setattr(paper_import_module.shutil, "_use_fd_functions", True)
    captured = {}

    def wrapper(path, *args, **kwargs):
        captured["called"] = True
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(paper_import_module.shutil, "rmtree", wrapper)

    # Non-trivial: this asserts the capability bit that the shim-identity bug
    # used to flip to False.
    assert paper_import_module._rmtree_is_symlink_attack_resistant() is True

    root = _make_attempt_root(tmp_path)
    token = (root.lstat().st_dev, root.lstat().st_ino)

    _cleanup_attempt_root(root, expected_token=token)

    assert captured.get("called", False) is True
    assert not root.exists()
