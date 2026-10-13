import csv
import json
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta

from scripts.sdd_tasks.metrics import MetricsError, export_metrics
from scripts.sdd_tasks.metrics_filters import METRIC_COLUMNS, METRIC_SCHEMA, METRIC_SOURCES
from scripts.sdd_tasks.run_docs import write_summary
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_result_query import _files, _finish
from tests.sdd_tasks.test_run_owner import _claimed, _rows

_ACTIVE_ID = "ffffffff-ffff-4fff-8fff-ffffffffffff"
_EVENT_SENTINEL = "EVENT_PRIVATE_SENTINEL"


def _add_active(conn, claim):
    row = conn.execute("SELECT task_hash,prompt_hash,definition_json FROM tasks WHERE task_id=?",
                       ("spec-016-task-03",)).fetchone()
    metadata = json.loads(row["definition_json"])
    conn.execute("""INSERT INTO runs VALUES (?, ?, ?, 'running', 'codex', 'fixture', ?, ?, NULL,
        ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL)""",
        (_ACTIVE_ID, "spec-016-task-03", 1, '{"private":"RUN_PRIVATE_SENTINEL"}',
         metadata["agent_role"], metadata["worktree"]["path"], metadata["worktree"]["branch"],
         claim.base_commit, row["task_hash"], row["prompt_hash"], claim.claimed_at,
         claim.claimed_at))


class MetricsTests(unittest.TestCase):
    def test_json_csv_filters_order_sources_privacy_and_read_only(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, canonical, task, database, _, owner, claim = state
            expected, _ = _finish(root, canonical, task, database, claim)
            with closing(connect(database)) as conn:
                _add_active(conn, claim)
                conn.execute("INSERT INTO events VALUES (?, 99, ?, 'action', ?)",
                             (claim.run_id, claim.claimed_at,
                              json.dumps({"private": _EVENT_SENTINEL})))
                before, files = _rows(conn), _files(canonical)
                exported = json.loads(export_metrics(conn, filters={}, format="json"))
                self.assertEqual(exported["schema"], METRIC_SCHEMA)
                self.assertEqual(exported["columns"], list(METRIC_COLUMNS))
                terminal, active = exported["rows"]
                self.assertEqual([r["run_id"] for r in exported["rows"]],
                                 sorted((claim.run_id, _ACTIVE_ID)))
                self.assertEqual(terminal["token_input"], 8)
                self.assertEqual((terminal["token_output"], terminal["token_total"]), (None, None))
                self.assertEqual(terminal["token_usage_source"], "fixture telemetry")
                self.assertEqual((terminal["duration_source"], terminal["model_source"]),
                                 ("ledger", "ledger"))
                self.assertEqual((terminal["tool_call_count"], terminal["tool_call_source"]),
                                 (None, "unavailable"))
                self.assertEqual((terminal["changed_file_count"], terminal["additions"],
                                  terminal["deletions"], terminal["change_source"]),
                                 (1, 3, 1, "canonical_summary"))
                self.assertTrue({terminal["duration_source"], terminal["model_source"],
                                 terminal["tool_call_source"], terminal["change_source"]}
                                <= METRIC_SOURCES)
                self.assertEqual((active["state"], active["outcome"], active["model"]),
                                 ("running", None, None))
                self.assertEqual((active["token_input"], active["duration_ms"],
                                  active["model_source"], active["token_usage_source"]),
                                 (None, None, "unavailable", "unavailable"))
                text = export_metrics(conn, filters={}, format="csv")
                records = list(csv.DictReader(text.splitlines()))
                self.assertEqual(tuple(next(csv.reader(text.splitlines()))), METRIC_COLUMNS)
                self.assertEqual([r["run_id"] for r in records], [r["run_id"] for r in exported["rows"]])
                self.assertEqual(records[1]["token_input"], "")
                stamp = datetime.fromisoformat(claim.claimed_at.replace("Z", "+00:00"))
                start = stamp.isoformat(timespec="microseconds").replace("+00:00", "Z")
                end = (stamp + timedelta(microseconds=1)).isoformat(
                    timespec="microseconds").replace("+00:00", "Z")
                filters = {"spec_id": "016", "task_id": task.metadata["task_id"],
                           "agent_role": task.metadata["agent_role"], "model": expected["model"],
                           "outcome": "succeeded", "time_from": start, "time_to": end}
                filtered = json.loads(export_metrics(conn, filters=filters, format="json"))
                self.assertEqual(len(filtered["rows"]), 1)
                self.assertEqual(filtered["rows"][0]["run_id"], claim.run_id)
                self.assertEqual(filtered["filters"]["time_from"], start)
                exclusive = json.loads(export_metrics(
                    conn, filters={"time_to": start}, format="json"))
                self.assertEqual(exclusive["rows"], [])
                self.assertNotIn(owner.token, text + json.dumps(exported))
                self.assertNotIn(_EVENT_SENTINEL, text + json.dumps(exported))
                self.assertNotIn("owner_json", exported["columns"])
                self.assertEqual(_rows(conn), before)
                self.assertEqual(_files(canonical), files)
                expected["token_usage"]["source"] = None
                write_summary(task, claim, expected, root)
                files_without_source = _files(canonical)
                missing_source = json.loads(export_metrics(conn, filters={}, format="json"))
                self.assertEqual(missing_source["rows"][0]["token_usage_source"], "unavailable")
                self.assertEqual(_rows(conn), before)
                self.assertEqual(_files(canonical), files_without_source)

    def test_invalid_filters_and_format_refuse_without_writes(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            _, canonical, _, database, _, _, claim = state
            with closing(connect(database)) as conn:
                before, files = _rows(conn), _files(canonical)
                invalid = (None, {"unknown": "x"}, {"spec_id": "16"},
                           {"model": {"private": "x"}}, {"outcome": "running"},
                           {"time_from": "2026-10-13T00:00:00"},
                           {"time_from": "2026-10-14T00:00:00Z",
                            "time_to": "2026-10-13T00:00:00Z"})
                for filters in invalid:
                    with self.subTest(filters=filters), self.assertRaises(ValueError):
                        export_metrics(conn, filters=filters, format="json")
                with self.assertRaises(MetricsError):
                    export_metrics(conn, filters={}, format="xml")
                self.assertEqual(_rows(conn), before)
                self.assertEqual(_files(canonical), files)

    def test_unknown_change_counts_stay_null_and_empty_changes_are_zero(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, canonical, task, database, _, _, claim = state
            expected, _ = _finish(root, canonical, task, database, claim)
            with closing(connect(database)) as conn:
                expected["changed_files"][0].update(additions=None, deletions=None)
                write_summary(task, claim, expected, root)
                before, files = _rows(conn), _files(canonical)
                row = json.loads(export_metrics(conn, filters={}, format="json"))["rows"][0]
                self.assertEqual((row["additions"], row["deletions"], row["change_source"]),
                                 (None, None, "unavailable"))
                self.assertEqual((_rows(conn), _files(canonical)), (before, files))
                expected["changed_files"] = []
                write_summary(task, claim, expected, root)
                files = _files(canonical)
                row = json.loads(export_metrics(conn, filters={}, format="json"))["rows"][0]
                self.assertEqual((row["changed_file_count"], row["additions"],
                                  row["deletions"], row["change_source"]),
                                 (0, 0, 0, "canonical_summary"))
                self.assertEqual(_rows(conn), before)
                self.assertEqual(_files(canonical), files)

    def test_malformed_or_missing_terminal_summary_fails_whole_export_read_only(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, canonical, task, database, _, _, claim = state
            _, summary = _finish(root, canonical, task, database, claim)
            with closing(connect(database)) as conn:
                for content in ("partial summary", "<!-- sdd-run-result:v1:begin -->\n{}\n"):
                    summary.write_text(content, encoding="utf-8")
                    before, files = _rows(conn), _files(canonical)
                    with self.assertRaisesRegex(MetricsError, "METRICS_RESULT_UNAVAILABLE"):
                        export_metrics(conn, filters={}, format="json")
                    self.assertEqual(_rows(conn), before)
                    self.assertEqual(_files(canonical), files)
                summary.unlink()
                before, files = _rows(conn), _files(canonical)
                with self.assertRaisesRegex(MetricsError, "METRICS_RESULT_UNAVAILABLE"):
                    export_metrics(conn, filters={}, format="csv")
                self.assertEqual(_rows(conn), before)
                self.assertEqual(_files(canonical), files)


if __name__ == "__main__":
    unittest.main()
