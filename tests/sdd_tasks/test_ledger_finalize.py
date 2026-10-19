import copy
import hashlib
import json
import os
import tempfile
import unittest
import uuid
from contextlib import closing, contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from scripts.sdd_tasks.catalog import rebuild
from scripts.sdd_tasks.completion_journal import read_journal
from scripts.sdd_tasks.completion_journal import write_journal as _write_journal
from scripts.sdd_tasks.completion_service import fail_run
from scripts.sdd_tasks.documents import parse_task
from scripts.sdd_tasks.journal_schema import validate_journal
from scripts.sdd_tasks.ledger_finalize import (
    LedgerFinalizeError,
    _target_task_status,
    _terminal_values,
    _validate_active_bindings,
    finalize_ledger,
)
from scripts.sdd_tasks.locks import maintenance_lock
from scripts.sdd_tasks.mirrors import render_status_update, validate_mirrors
from scripts.sdd_tasks.owners import OwnerStatus, current_owner
from scripts.sdd_tasks.result_query import result_for_run
from scripts.sdd_tasks.run_docs import build_summary
from scripts.sdd_tasks.selection import claim_next
from scripts.sdd_tasks.store import connect, transaction
from scripts.sdd_tasks.workspace import capture_snapshot
from tests.sdd_tasks._fixtures import task_markdown
from tests.sdd_tasks.test_catalog import _git
from tests.sdd_tasks.test_completion_journal import _document
from tests.sdd_tasks.test_completion_journal import _journal as _base_journal
from tests.sdd_tasks.test_completion_prepare import COMMAND, SOURCE
from tests.sdd_tasks.test_completion_service import _draft
from tests.sdd_tasks.test_run_docs import _result
from tests.sdd_tasks.test_run_owner import _claimed, _rows
from tests.sdd_tasks.test_selection import GATE, _fixture


def _stamp(value, seconds):
    instant = datetime.fromisoformat(value.replace("Z", "+00:00")) + timedelta(seconds=seconds)
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@contextmanager
def _claimed_with_expected_artifact(directory):
    root, canonical, task, _, database = _fixture(directory)
    ignore = root / ".gitignore"
    ignore.write_text(ignore.read_text(encoding="utf-8") + "\n.sdd/runtime/\n", encoding="utf-8")
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-qm", "ignore private runtime")
    tip = _git(root, "rev-parse", "HEAD")
    _git(canonical, "merge", "--ff-only", tip)
    metadata = dict(task.metadata, validation_commands=[COMMAND], expected_artifacts=[SOURCE])
    relative = task.path.relative_to(root)
    contents = "# {}\n> 当前状态：`待执行`\n\n".format(metadata["title"]) + task_markdown(metadata)
    for repository in (root, canonical):
        (repository / relative).write_text(contents, encoding="utf-8")
        _git(repository, "add", relative.as_posix())
        _git(repository, "commit", "-qm", "fixture validation command and evidence artifact")
    task = parse_task(canonical / relative)
    rebuild(database, root)
    os.chmod(database.parent, 0o700)
    before = capture_snapshot(root, task)
    owner = current_owner("ledger-finalize-fixture")
    with closing(connect(database)) as conn, maintenance_lock(root):
        claim = claim_next(conn, [task], {GATE}, workspace_snapshots={
            task.metadata["task_id"]: before}, ide="codex", owner=owner,
            now=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), lease_minutes=30)
    if claim is None:
        raise AssertionError("fixture Task was not claimed")
    yield root, canonical, task, database, before, owner, claim


def _journal_for(state, outcome="succeeded", claim_override=None):
    _, _, task, _, _, owner, claim = state
    if claim_override is not None:
        claim = claim_override
    result = _result(task, claim)
    result["outcome"] = outcome
    result["ended_at"] = _stamp(claim.claimed_at, 60)
    summary = "docs/sdd/runs/{}/task-{}/{}.md".format(
        task.metadata["spec_id"], task.metadata["task_id"][-2:], claim.run_id)
    if outcome == "failed":
        result["changed_files"] = []
        changed_paths, committed = [], [summary]
    else:
        changed = result["changed_files"][0]["path"]
        changed_paths, committed = [{"path": changed, "before_sha256": "a" * 64,
                                     "after_sha256": result["changed_files"][0]["sha256"]}], \
            sorted((summary, changed))
    journal = _base_journal()
    observed = {key: value for key, value in journal["index_before"].items()
                if key != "git_index_path"}
    journal.update(
        run_id=claim.run_id, task_id=task.metadata["task_id"],
        owner={"executor_id": owner.executor_id, "host_id": owner.host_id,
               "pid": owner.pid, "process_started_at": owner.process_started_at,
               "token": owner.token},
        base_commit=claim.base_commit, original_head=claim.base_commit,
        task_hash=task.task_hash, prompt_hash=task.prompt_hash,
        allowed_paths=["scripts/sdd_tasks"], expected_result=result,
        terminal_outcome=result["outcome"],
        changed_paths=changed_paths,
        expected_docs=[_document(summary, None, "validated summary\n")],
        committed_paths=committed, staged_paths=committed,
        expected_git_entries=[{"path": path, "mode": "100644", "object_id": "7" * 40}
                              for path in committed],
        phase="index_reconciled", index_observed_before=copy.deepcopy(observed),
        index_after=copy.deepcopy(observed), index_lock_temp_path="index.tmp",
        index_lock_identity={"device": 1, "inode": 2}, index_recovery_stage="index_installed",
        candidate_commit_hash="f" * 40,
    )
    return validate_journal(journal)


def _public_journal_for(state, target_status="completed", outcome="succeeded",
                        prior_failures=()):
    root, canonical, task, database, _, _, original_claim = state
    attempt = len(prior_failures) + 1
    claim = replace(original_claim, attempt=attempt) if prior_failures else original_claim
    journal = _journal_for(state, outcome, claim)
    if prior_failures:
        with closing(connect(database)) as conn:
            conn.execute("UPDATE runs SET attempt=? WHERE run_id=?", (attempt, claim.run_id))
            columns = [row[1] for row in conn.execute("PRAGMA table_info(runs)")]
            positions = {name: index for index, name in enumerate(columns)}
            template = list(conn.execute(
                "SELECT * FROM runs WHERE run_id=?", (claim.run_id,)).fetchone())
            for number, previous_state in enumerate(prior_failures, 1):
                row = template.copy()
                row[positions["run_id"]] = str(uuid.uuid4())
                row[positions["attempt"]] = number
                row[positions["state"]] = previous_state
                row[positions["ended_at"]] = _stamp(claim.claimed_at, number)
                conn.execute("INSERT INTO runs VALUES ({})".format(
                    ",".join("?" for _ in columns)), row)
    canonical_task = parse_task(canonical / task.path.relative_to(root))
    documents = (render_status_update(canonical_task, target_status, canonical)
                 if target_status != "pending" else {})
    summary_path = journal["expected_result"]["artifacts"][0]["path"]
    documents[summary_path] = build_summary(canonical_task, claim, journal["expected_result"])
    expected = []
    for relative, content in sorted(documents.items()):
        target = canonical / relative
        before = target.read_text(encoding="utf-8") if target.exists() else None
        expected.append(_document(relative, before, content))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    changed = {item["path"] for item in journal["changed_paths"]}
    committed = sorted(set(documents) | changed, key=lambda path: path.encode("utf-8"))
    journal.update(
        expected_docs=expected, committed_paths=committed, staged_paths=committed,
        expected_git_entries=[{"path": path, "mode": "100644", "object_id": "7" * 40}
                              for path in committed],
    )
    journal = validate_journal(journal)
    journal_path = root / ".sdd/runtime/runs" / claim.run_id / "completion.json"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.write_text(json.dumps(journal, sort_keys=True, ensure_ascii=False,
                                       separators=(",", ":")) + "\n", encoding="utf-8")
    return journal, journal_path, documents


class LedgerFinalizeBindingTests(unittest.TestCase):
    def test_complete_failed_result_stays_readable_during_new_claim_and_lease(self):
        with tempfile.TemporaryDirectory() as temp, _claimed_with_expected_artifact(temp) as state:
            root, canonical, task, database, _, _, first = state
            owner = first.owner
            run_dir = root / ".sdd/runtime/runs" / first.run_id
            draft = _draft(task, first, outcome="failed", changed_files=[])
            draft["artifacts"] = [{
                "path": SOURCE, "kind": "evidence",
                "sha256": hashlib.sha256((canonical / SOURCE).read_bytes()).hexdigest(),
                "included_in_commit": False,
            }]
            with closing(connect(database)) as conn, maintenance_lock(root):
                old_result = fail_run(
                    conn, root, first.run_id, owner.executor_id, owner.pid,
                    json.dumps(draft))
            journal_path = run_dir / "completion.json"
            journal = read_journal(journal_path)
            summaries = [path for path in journal["committed_paths"]
                         if path.startswith("docs/sdd/runs/")]
            self.assertEqual(len(summaries), 1)
            summary = summaries[0]
            old_summary = (canonical / summary).read_bytes()
            main_task = parse_task(root / task.path.relative_to(canonical))
            snapshot = capture_snapshot(root, main_task)
            with closing(connect(database)) as conn, maintenance_lock(root):
                retry = claim_next(
                    conn, [main_task], {"spec-016.cloud-stage-authorized"},
                    workspace_snapshots={main_task.metadata["task_id"]: snapshot}, ide="codex",
                    owner=owner, now=_stamp(first.claimed_at, 180), lease_minutes=120)
            self.assertIsNotNone(retry)
            self.assertEqual(retry.attempt, 2)
            self.assertEqual(retry.base_commit, snapshot.head)
            self.assertNotEqual(retry.base_commit, first.base_commit)
            self.assertIsNone(retry.recovery_of)
            with closing(connect(database)) as conn:
                old_row = tuple(conn.execute(
                    "SELECT state,attempt,result_doc,ended_at FROM runs WHERE run_id=?",
                    (first.run_id,)).fetchone())
                artifact = tuple(conn.execute(
                    "SELECT path,git_status,included_in_commit FROM artifacts WHERE run_id=?",
                    (first.run_id,)).fetchone())
                self.assertEqual(old_row[0:2], ("failed", 1))
                self.assertEqual(artifact, (SOURCE, "unchanged", 0))
                self.assertEqual(result_for_run(conn, first.run_id), old_result)
                self.assertEqual(tuple(conn.execute(
                    "SELECT state,attempt FROM runs WHERE run_id=?", (retry.run_id,)).fetchone()),
                    ("claimed", 2))
                self.assertEqual(tuple(conn.execute(
                    "SELECT task_id,run_id FROM leases WHERE task_id=?",
                    (task.metadata["task_id"],)).fetchone()),
                    (task.metadata["task_id"], retry.run_id))
                self.assertEqual(tuple(conn.execute(
                    "SELECT state,attempt,result_doc,ended_at FROM runs WHERE run_id=?",
                    (first.run_id,)).fetchone()), old_row)
                self.assertEqual(tuple(conn.execute(
                    "SELECT path,git_status,included_in_commit FROM artifacts WHERE run_id=?",
                    (first.run_id,)).fetchone()), artifact)
                self.assertEqual(result_for_run(conn, first.run_id), old_result)
                before_replay = _rows(conn)
                self.assertEqual(finalize_ledger(conn, journal_path, now=retry.claimed_at),
                                 old_result)
                self.assertEqual(_rows(conn), before_replay)
                self.assertEqual(result_for_run(conn, first.run_id), old_result)
            self.assertEqual((canonical / summary).read_bytes(), old_summary)

    def test_public_failed_finalize_with_summary_only_keeps_task_pending(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            journal, journal_path, _ = _public_journal_for(
                state, target_status="pending", outcome="failed")
            root, canonical, task, database, _, _, claim = state
            with closing(connect(database)) as conn:
                result = finalize_ledger(conn, journal_path,
                                         now=_stamp(claim.claimed_at, 120))
                run = conn.execute(
                    "SELECT attempt,state,result_doc FROM runs WHERE run_id=?", (claim.run_id,)
                ).fetchone()
                self.assertEqual(tuple(run), (
                    1, "failed", "docs/sdd/runs/016/task-04/{}.md".format(claim.run_id)))
                self.assertEqual(conn.execute(
                    "SELECT status FROM tasks WHERE task_id=?",
                    (task.metadata["task_id"],)).fetchone()[0], "pending")
                self.assertIsNone(conn.execute(
                    "SELECT 1 FROM leases WHERE run_id=?", (claim.run_id,)).fetchone())
                artifact = conn.execute(
                    "SELECT path,git_status,included_in_commit FROM artifacts WHERE run_id=?",
                    (claim.run_id,),
                ).fetchone()
                self.assertEqual(tuple(artifact), (
                    journal["expected_result"]["artifacts"][0]["path"], "committed", 1))
                self.assertEqual(result["changed_files"], [])
                self.assertEqual(result_for_run(conn, claim.run_id), result)
            validate_mirrors(parse_task(canonical / task.path.relative_to(root)), canonical)
            self.assertEqual(read_journal(journal_path)["phase"], "complete")

    def test_public_third_consecutive_failure_blocks_task_and_mirrors(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            journal, journal_path, _ = _public_journal_for(
                state, target_status="blocked", outcome="failed",
                prior_failures=("failed", "failed"))
            root, canonical, task, database, _, _, claim = state
            with closing(connect(database)) as conn:
                result = finalize_ledger(conn, journal_path,
                                         now=_stamp(claim.claimed_at, 120))
                current = conn.execute(
                    "SELECT attempt,state FROM runs WHERE run_id=?", (claim.run_id,)
                ).fetchone()
                self.assertEqual(tuple(current), (3, "failed"))
                self.assertEqual(conn.execute(
                    "SELECT status FROM tasks WHERE task_id=?",
                    (task.metadata["task_id"],)).fetchone()[0], "blocked")
                self.assertIsNone(conn.execute(
                    "SELECT 1 FROM leases WHERE run_id=?", (claim.run_id,)).fetchone())
                self.assertEqual(result_for_run(conn, claim.run_id), result)
            validate_mirrors(parse_task(canonical / task.path.relative_to(root)), canonical)
            self.assertEqual(read_journal(journal_path)["phase"], "complete")

    def test_failed_summary_only_fixtures_cover_pending_and_third_failure_blocked(self):
        cases = (("pending", ()), ("blocked", ("failed", "failed")))
        for target, prior in cases:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temp, \
                    _claimed(temp) as state:
                journal, _, documents = _public_journal_for(
                    state, target_status=target, outcome="failed", prior_failures=prior)
                root, canonical, task, database, _, _, claim = state
                self.assertEqual(journal["terminal_outcome"], "failed")
                self.assertEqual(journal["expected_result"]["changed_files"], [])
                self.assertEqual(journal["changed_paths"], [])
                summary = journal["expected_result"]["artifacts"][0]["path"]
                self.assertEqual(set(documents), {summary} | ({
                    "docs/sdd/plans/016/task-04-fixture.md",
                    "docs/sdd/specs/016-portable-task-ledger.md",
                    "docs/sdd/plans/016/README.md"} if target == "blocked" else set()))
                live_task = parse_task(canonical / task.path.relative_to(root))
                self.assertEqual(live_task.metadata["status"], target)
                validate_mirrors(live_task, canonical)
                with closing(connect(database)) as conn:
                    self.assertEqual(conn.execute(
                        "SELECT attempt FROM runs WHERE run_id=?", (claim.run_id,)).fetchone()[0],
                        len(prior) + 1)

    def test_public_finalize_commits_terminal_rows_and_closes_lease(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            journal, journal_path, _ = _public_journal_for(state)
            _, canonical, _, database, _, _, claim = state
            with closing(connect(database)) as conn:
                before = _rows(conn)
                actual = finalize_ledger(conn, journal_path,
                                         now=_stamp(claim.claimed_at, 120))
                self.assertEqual(actual, journal["expected_result"])
                run = conn.execute(
                    "SELECT state,model,result_doc FROM runs WHERE run_id=?", (claim.run_id,)
                ).fetchone()
                self.assertEqual(tuple(run), (
                    "succeeded", "fixture-model",
                    "docs/sdd/runs/016/task-04/{}.md".format(claim.run_id)))
                task = conn.execute(
                    "SELECT status,definition_json FROM tasks WHERE task_id=?",
                    (claim.task.metadata["task_id"],),
                ).fetchone()
                self.assertEqual(task["status"], "completed")
                self.assertEqual(json.loads(task["definition_json"])["status"], "completed")
                self.assertIsNone(conn.execute(
                    "SELECT 1 FROM leases WHERE run_id=?", (claim.run_id,)).fetchone())
                artifact = conn.execute(
                    "SELECT path,git_status,included_in_commit FROM artifacts WHERE run_id=?",
                    (claim.run_id,),
                ).fetchone()
                self.assertEqual(tuple(artifact), (
                    journal["expected_result"]["artifacts"][0]["path"], "committed", 1))
                self.assertEqual(result_for_run(conn, claim.run_id), actual)
                self.assertNotEqual(_rows(conn), before)
            self.assertEqual(read_journal(journal_path)["phase"], "complete")
            validate_mirrors(parse_task(canonical / state[2].path.relative_to(state[0])), canonical)

    def test_phase_write_failure_leaves_database_and_journal_unchanged(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            _, journal_path, _ = _public_journal_for(state)
            _, _, _, database, _, _, claim = state
            with closing(connect(database)) as conn:
                before = _rows(conn)
                with patch("scripts.sdd_tasks.ledger_finalize.write_journal",
                           side_effect=OSError("phase write failed")), self.assertRaisesRegex(
                        OSError, "phase write failed"):
                    finalize_ledger(conn, journal_path, now=_stamp(claim.claimed_at, 120))
                self.assertEqual(_rows(conn), before)
            self.assertEqual(read_journal(journal_path)["phase"], "index_reconciled")

    def test_malformed_summary_rolls_back_terminal_rows_and_retains_lease(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            journal, journal_path, _ = _public_journal_for(state)
            _, canonical, _, database, _, _, claim = state
            summary = journal["expected_result"]["artifacts"][0]["path"]
            malformed = "not a result summary\n"
            (canonical / summary).write_text(malformed, encoding="utf-8")
            replacement = _document(summary, None, malformed)
            journal["expected_docs"] = [
                replacement if item["path"] == summary else item
                for item in journal["expected_docs"]]
            journal = validate_journal(journal)
            journal_path.write_text(json.dumps(journal, sort_keys=True, ensure_ascii=False,
                                               separators=(",", ":")) + "\n", encoding="utf-8")
            with closing(connect(database)) as conn:
                before = _rows(conn)
                with self.assertRaisesRegex(
                        LedgerFinalizeError, "LEDGER_FINALIZE_CANONICAL_VIEW_INVALID"):
                    finalize_ledger(conn, journal_path, now=_stamp(claim.claimed_at, 120))
                self.assertEqual(_rows(conn), before)
                self.assertIsNotNone(conn.execute(
                    "SELECT 1 FROM leases WHERE run_id=?", (claim.run_id,)).fetchone())
            self.assertEqual(read_journal(journal_path)["phase"], "ledger_finalizing")

    def test_complete_phase_failure_replays_terminal_rows_without_owner_or_duplicate_writes(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            journal, journal_path, _ = _public_journal_for(state)
            _, _, _, database, child, _, claim = state
            def fail_complete(path, journal, *, previous_phase=None):
                if journal["phase"] == "complete":
                    raise OSError("complete phase write failed")
                return _write_journal(path, journal, previous_phase=previous_phase)

            with closing(connect(database)) as conn:
                with patch("scripts.sdd_tasks.ledger_finalize.write_journal",
                           side_effect=fail_complete), self.assertRaisesRegex(
                        OSError, "complete phase write failed"):
                    finalize_ledger(conn, journal_path, now=_stamp(claim.claimed_at, 120))
                committed = _rows(conn)
                self.assertEqual(read_journal(journal_path)["phase"], "ledger_finalizing")
                child.terminate()
                child.wait(timeout=10)
                result = finalize_ledger(conn, journal_path,
                                         now=_stamp(claim.claimed_at, 120))
                self.assertEqual(result, journal["expected_result"])
                self.assertEqual(_rows(conn), committed)
            self.assertEqual(read_journal(journal_path)["phase"], "complete")

    def test_expired_dead_owner_can_reconcile_and_finalize_index_reconciled_journal(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            journal, journal_path, _ = _public_journal_for(state)
            _, _, _, database, _, _, claim = state
            now = _stamp(claim.claimed_at, 120)
            with closing(connect(database)) as conn:
                conn.execute("UPDATE leases SET expires_at=? WHERE run_id=?",
                             (_stamp(claim.claimed_at, 60), claim.run_id))
                with patch("scripts.sdd_tasks.ledger_finalize.observe_owner",
                           return_value=OwnerStatus.DEAD):
                    result = finalize_ledger(conn, journal_path, now=now)
                self.assertEqual(result, journal["expected_result"])
                self.assertEqual(conn.execute(
                    "SELECT state FROM runs WHERE run_id=?", (claim.run_id,)).fetchone()[0],
                    "succeeded")
                self.assertIsNone(conn.execute(
                    "SELECT 1 FROM leases WHERE run_id=?", (claim.run_id,)).fetchone())
            self.assertEqual(read_journal(journal_path)["phase"], "complete")

    def test_public_finalizer_fixture_writes_canonical_task_mirrors_and_summary(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            journal, journal_path, documents = _public_journal_for(state)
            _, canonical, task, _, _, _, _ = state
            self.assertEqual(read_journal(journal_path), journal)
            self.assertEqual(set(documents), {item["path"] for item in journal["expected_docs"]})
            for relative, expected in documents.items():
                self.assertEqual((canonical / relative).read_text(encoding="utf-8"), expected)
            updated_task = parse_task(canonical / task.path.relative_to(state[0]))
            self.assertEqual(updated_task.metadata["status"], "completed")
            validate_mirrors(updated_task, canonical)

    def test_real_claim_journal_derives_terminal_model_path_and_artifact_row(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            journal = _journal_for(state)
            root, _, task, database, _, _, claim = state
            with closing(connect(database)) as conn:
                before = _rows(conn)
                with transaction(conn, immediate=True):
                    bindings = _validate_active_bindings(
                        conn, journal, _stamp(claim.claimed_at, 120))
                    self.assertIsNone(bindings["run"]["model"])
                    terminal = _terminal_values(conn, bindings, journal)
                self.assertEqual(terminal["run"][0], "succeeded")
                self.assertEqual(terminal["run"][1], "fixture-model")
                self.assertEqual(terminal["run"][5],
                                 "docs/sdd/runs/016/task-04/{}.md".format(claim.run_id))
                self.assertEqual(terminal["task_status"], "completed")
                artifact = terminal["artifacts"][0]
                self.assertEqual((artifact[1], artifact[4], artifact[5]),
                                 (journal["expected_result"]["artifacts"][0]["path"],
                                  "committed", 1))
                self.assertEqual(_rows(conn), before)

    def test_terminal_values_rejects_artifact_commit_membership_mismatch(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            journal = _journal_for(state)
            journal["expected_result"]["artifacts"][0]["included_in_commit"] = False
            journal = validate_journal(journal)
            _, _, _, database, _, _, claim = state
            with closing(connect(database)) as conn:
                before = _rows(conn)
                with transaction(conn, immediate=True):
                    bindings = _validate_active_bindings(
                        conn, journal, _stamp(claim.claimed_at, 120))
                    with self.assertRaisesRegex(
                            LedgerFinalizeError, "LEDGER_FINALIZE_ARTIFACT_MEMBERSHIP_MISMATCH"):
                        _terminal_values(conn, bindings, journal)
                self.assertEqual(_rows(conn), before)

    def test_expired_lease_requires_dead_owner_and_finalizing_phase(self):
        cases = (("index_reconciled", OwnerStatus.ALIVE, False),
                 ("index_reconciled", OwnerStatus.UNKNOWN, False),
                 ("index_reconciled", OwnerStatus.DEAD, False),
                 ("ledger_finalizing", OwnerStatus.ALIVE, False),
                 ("ledger_finalizing", OwnerStatus.UNKNOWN, False),
                 ("ledger_finalizing", OwnerStatus.DEAD, True))
        for phase, status, accepted in cases:
            with self.subTest(phase=phase, status=status), \
                    tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
                journal = _journal_for(state)
                journal["phase"] = phase
                journal = validate_journal(journal)
                _, _, _, database, _, _, claim = state
                now = _stamp(claim.claimed_at, 120)
                with closing(connect(database)) as conn:
                    conn.execute("UPDATE leases SET expires_at=? WHERE run_id=?",
                                 (_stamp(claim.claimed_at, 60), claim.run_id))
                    with patch("scripts.sdd_tasks.ledger_finalize.observe_owner",
                               return_value=status), transaction(conn, immediate=True):
                        if accepted:
                            self.assertIsNotNone(_validate_active_bindings(conn, journal, now))
                        else:
                            with self.assertRaisesRegex(
                                    LedgerFinalizeError, "LEDGER_FINALIZE_LEASE_EXPIRED"):
                                _validate_active_bindings(conn, journal, now)

    def test_owner_hash_and_worktree_binding_mismatches_refuse(self):
        for case in ("owner", "hash", "worktree"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp, \
                    _claimed(temp) as state:
                journal = _journal_for(state)
                expected = {"owner": "LEDGER_FINALIZE_OWNER_MISMATCH",
                            "hash": "LEDGER_FINALIZE_RUN_MISMATCH",
                            "worktree": "LEDGER_FINALIZE_TASK_MISMATCH"}[case]
                if case == "owner":
                    journal["owner"]["token"] = "different-owner-token"
                    journal = validate_journal(journal)
                _, _, _, database, _, _, claim = state
                with closing(connect(database)) as conn:
                    if case == "hash":
                        conn.execute("UPDATE runs SET task_hash=? WHERE run_id=?",
                                     ("e" * 64, claim.run_id))
                    elif case == "worktree":
                        conn.execute("UPDATE runs SET worktree='elsewhere' WHERE run_id=?",
                                     (claim.run_id,))
                    with transaction(conn, immediate=True), self.assertRaisesRegex(
                            LedgerFinalizeError, expected):
                        _validate_active_bindings(conn, journal, _stamp(claim.claimed_at, 120))

    def test_started_at_uses_first_public_event_instead_of_claim_time(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            journal = _journal_for(state)
            _, _, _, database, _, _, claim = state
            event_time = _stamp(claim.claimed_at, 30)
            with closing(connect(database)) as conn:
                conn.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                             (claim.run_id, 2, event_time, "action", "{}"))
                conn.execute("UPDATE runs SET started_at=? WHERE run_id=?",
                             (event_time, claim.run_id))
                journal["expected_result"]["started_at"] = event_time
                journal = validate_journal(journal)
                with transaction(conn, immediate=True):
                    _validate_active_bindings(conn, journal, _stamp(claim.claimed_at, 120))
                journal["expected_result"]["started_at"] = claim.claimed_at
                journal = validate_journal(journal)
                with transaction(conn, immediate=True), self.assertRaisesRegex(
                        LedgerFinalizeError, "LEDGER_FINALIZE_RESULT_TIME_MISMATCH"):
                    _validate_active_bindings(conn, journal, _stamp(claim.claimed_at, 120))

    def test_failed_streak_stops_at_first_nonfailed_attempt(self):
        for prior, expected in ((("failed", "succeeded"), "pending"),
                                (("failed", "failed"), "blocked")):
            with self.subTest(prior=prior), tempfile.TemporaryDirectory() as temp, \
                    _claimed(temp) as state:
                _, _, task, database, _, _, claim = state
                with closing(connect(database)) as conn:
                    conn.execute("UPDATE runs SET attempt=3 WHERE run_id=?", (claim.run_id,))
                    columns = [row[1] for row in conn.execute("PRAGMA table_info(runs)")]
                    positions = {name: index for index, name in enumerate(columns)}
                    template = list(conn.execute(
                        "SELECT * FROM runs WHERE run_id=?", (claim.run_id,)).fetchone())
                    with transaction(conn, immediate=True):
                        for attempt, outcome in enumerate(prior, 1):
                            row = template.copy()
                            row[positions["run_id"]] = "prior-{}-{}".format(attempt, outcome)
                            row[positions["attempt"]] = attempt
                            row[positions["state"]] = outcome
                            row[positions["ended_at"]] = _stamp(claim.claimed_at, attempt)
                            conn.execute("INSERT INTO runs VALUES ({})".format(
                                ",".join("?" for _ in columns)), row)
                        current = conn.execute(
                            "SELECT * FROM runs WHERE run_id=?", (claim.run_id,)).fetchone()
                        self.assertEqual(_target_task_status(
                            conn, current, task.metadata, "failed"), expected)


if __name__ == "__main__":
    unittest.main()
