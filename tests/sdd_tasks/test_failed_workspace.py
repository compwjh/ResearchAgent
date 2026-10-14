import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace

from scripts.sdd_tasks.failed_workspace import (
    FailedWorkspaceError,
    VerifiedFailedWorkspace,
    compare_verified_failed_workspace,
)
from scripts.sdd_tasks.failure_history import VerifiedFailureHistory
from tests.sdd_tasks.test_selection import _fixture

RUN_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OBSERVATION_TIP = "2" * 40
ACTIVE_TIP = "3" * 40
ROOT = "docs/sdd"
EXCLUDED = "docs/sdd/runs/016/report.md"


def _identity(snapshot):
    return (str(snapshot.repo_root), str(snapshot.common_dir), str(snapshot.worktree_path),
            snapshot.spec_id, snapshot.task_id, snapshot.task_hash, snapshot.prompt_hash,
            snapshot.branch)


def _task(task):
    return replace(task, metadata=dict(task.metadata, allowed_paths=[ROOT]))


def _proof(task, baseline, observation, excluded=(EXCLUDED,)):
    roots = tuple(task.metadata["allowed_paths"])
    history = VerifiedFailureHistory(((RUN_ID, OBSERVATION_TIP),), excluded, ACTIVE_TIP)
    return VerifiedFailedWorkspace(RUN_ID, _identity(baseline), baseline, observation, history,
                                   baseline.head, OBSERVATION_TIP, ACTIVE_TIP, roots, excluded)


class FailedWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        _, _, task, snapshot, _ = _fixture(self.temp.name)
        self.task = _task(task)
        self.baseline = replace(snapshot, allowed_hashes={ROOT: None})

    def tearDown(self):
        self.temp.cleanup()

    def test_excluded_document_markers_project_to_unchanged_without_mutation(self):
        baseline = replace(self.baseline, status_records=(), allowed_hashes={ROOT: None})
        hashes = {ROOT: None, "docs/sdd/runs": None, "docs/sdd/runs/016": None,
                  EXCLUDED: "c" * 64}
        observation = replace(baseline, head=OBSERVATION_TIP,
                              status_records=("?? " + EXCLUDED,), allowed_hashes=hashes)
        proof = _proof(self.task, baseline, observation)
        before = deepcopy((self.task.metadata, baseline, observation, proof))

        result = compare_verified_failed_workspace(proof, self.task)

        self.assertEqual((result.kind, result.changed_paths, result.out_of_scope_paths),
                         ("unchanged", (), ()))
        self.assertEqual(self.task.metadata, before[0])
        self.assertEqual(baseline.allowed_hashes, before[1].allowed_hashes)
        self.assertEqual(observation.allowed_hashes, before[2].allowed_hashes)
        self.assertEqual(proof, before[3])

    def test_root_marker_stays_and_other_descendant_is_partial_or_outside(self):
        path = ROOT + "/keep.txt"
        old = {ROOT: None, path: "a" * 64}
        new = {ROOT: None, path: "b" * 64}
        baseline = replace(self.baseline, allowed_hashes=old)
        observation = replace(baseline, head=OBSERVATION_TIP,
                              status_records=(" M " + path,), allowed_hashes=new)
        result = compare_verified_failed_workspace(_proof(self.task, baseline, observation), self.task)
        self.assertEqual((result.kind, result.changed_paths), ("partial", (path,)))

        outside = replace(observation, status_records=(" M " + path, "?? outside.txt"))
        result = compare_verified_failed_workspace(_proof(self.task, baseline, outside), self.task)
        self.assertEqual((result.kind, result.out_of_scope_paths),
                         ("out_of_scope", ("outside.txt",)))

    def test_rename_keeps_non_document_endpoint_visible(self):
        baseline = self.baseline
        observation = replace(baseline, head=OBSERVATION_TIP,
                              status_records=("R  " + EXCLUDED, "outside.txt"))
        result = compare_verified_failed_workspace(_proof(self.task, baseline, observation), self.task)
        self.assertEqual((result.kind, result.changed_paths, result.out_of_scope_paths),
                         ("out_of_scope", ("outside.txt",), ("outside.txt",)))

    def test_forged_head_hash_and_proof_are_rejected(self):
        baseline = self.baseline
        observation = replace(baseline, head=OBSERVATION_TIP)
        proof = _proof(self.task, baseline, observation)
        forged_hashes = replace(observation, allowed_hashes={ROOT: None, "outside.txt": "x"})
        cases = (
            replace(proof, observation_tip="f" * 40),
            replace(proof, observation=forged_hashes),
            replace(proof, task_identity=("forged",)),
        )
        for forged in cases:
            with self.subTest(proof=forged), self.assertRaises(FailedWorkspaceError):
                compare_verified_failed_workspace(forged, self.task)
