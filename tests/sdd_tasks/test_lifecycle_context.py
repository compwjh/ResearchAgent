import hashlib
import stat
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.sdd_tasks.lifecycle_context import LifecycleContextError, load_active_claim
from scripts.sdd_tasks.owners import OwnerIdentity
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_run_owner import _claimed, _rows


def _tree_state(root):
    state = []
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        relative = path.relative_to(root).as_posix()
        if stat.S_ISLNK(info.st_mode):
            value = ("link", path.readlink().as_posix())
        elif stat.S_ISREG(info.st_mode):
            value = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
        elif stat.S_ISDIR(info.st_mode):
            value = ("directory", None)
        else:
            value = ("other", info.st_mode)
        state.append((relative, stat.S_IMODE(info.st_mode), value))
    return tuple(state)


class LifecycleContextTests(unittest.TestCase):
    def test_active_claim_reads_from_main_or_exact_worktree_without_writes(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as fixture:
            root, canonical, task, database, _, owner, original_claim = fixture
            with closing(connect(database)) as conn:
                rows, files = _rows(conn), _tree_state(root)
                for supplied in (root, canonical):
                    with self.subTest(root=supplied):
                        live, claim, baseline = load_active_claim(
                            conn, original_claim.run_id, owner, supplied)
                        self.assertEqual((live.task_hash, live.prompt_hash),
                                         (task.task_hash, task.prompt_hash))
                        self.assertEqual((claim.run_id, claim.owner, claim.state),
                                         (original_claim.run_id, owner, "claimed"))
                        self.assertEqual(baseline.head, claim.base_commit)
                        self.assertIsNone(claim.recovery_of)
                        self.assertEqual(_rows(conn), rows)
                        self.assertEqual(_tree_state(root), files)

    def test_root_owner_gate_and_spec_refusals_preserve_database_and_files(self):
        cases = (("root", "LIFECYCLE_REPOSITORY_UNREGISTERED"),
                 ("owner", "LIFECYCLE_OWNER_MISMATCH"),
                 ("gate", "LIFECYCLE_GATES_UNSATISFIED"),
                 ("spec", "LIFECYCLE_SPEC_NOT_CLAIMABLE"))
        for case, expected in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp, _claimed(temp) as fixture:
                root, canonical, task, database, _, owner, claim = fixture
                supplied, identity = root, owner
                if case == "root":
                    supplied = Path(temp)
                elif case == "owner":
                    identity = OwnerIdentity(owner.executor_id, owner.host_id, owner.pid,
                                             owner.process_started_at, "wrong-token")
                elif case == "gate":
                    (canonical / "docs/sdd/gate-evidence.json").write_text(
                        '{"schema":"sdd-gates/v1","gates":[]}', encoding="utf-8")
                else:
                    spec = canonical / "docs/sdd/specs/016-portable-task-ledger.md"
                    source = spec.read_text(encoding="utf-8")
                    changed = source.replace("**当前状态：`已确认`**", "**当前状态：`待确认`**", 1)
                    self.assertNotEqual(source, changed)
                    spec.write_text(changed, encoding="utf-8")
                with closing(connect(database)) as conn:
                    rows, files = _rows(conn), _tree_state(root)
                    with self.assertRaises(LifecycleContextError) as caught:
                        load_active_claim(conn, claim.run_id, identity, supplied)
                    self.assertEqual(caught.exception.code, expected)
                    self.assertEqual(_rows(conn), rows)
                    self.assertEqual(_tree_state(root), files)


if __name__ == "__main__":
    unittest.main()
