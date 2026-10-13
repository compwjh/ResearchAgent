import tempfile
import unittest
from contextlib import closing

from scripts.sdd_tasks.metrics_filters import METRIC_COLUMNS, METRIC_SCHEMA
from scripts.sdd_tasks.store import connect
from tests.sdd_tasks.test_catalog import _repo
from tests.sdd_tasks.test_cli import _invoke
from tests.sdd_tasks.test_result_query import _files, _finish
from tests.sdd_tasks.test_run_owner import _claimed, _rows


class ReadOnlyResultCliTests(unittest.TestCase):
    def test_result_and_metrics_emit_read_only_json_envelopes_and_csv_content(self):
        with tempfile.TemporaryDirectory() as temp, _claimed(temp) as state:
            root, canonical, task, database, _, owner, claim = state
            expected, _ = _finish(root, canonical, task, database, claim)
            with closing(connect(database)) as conn:
                before = _rows(conn)
            files = _files(canonical)
            code, result, raw, err = _invoke([
                "--repo", str(root), "result", "--json", "--run-id", claim.run_id])
            self.assertEqual((code, result["ok"], result["code"], err), (0, True, "OK", ""))
            self.assertEqual(result["data"], expected)
            self.assertNotIn(owner.token, raw)
            code, metrics, raw, err = _invoke(["--repo", str(root), "metrics", "--format", "json"])
            self.assertEqual((code, metrics["ok"], metrics["code"], err), (0, True, "OK", ""))
            self.assertEqual(metrics["data"]["schema"], METRIC_SCHEMA)
            self.assertEqual(metrics["data"]["columns"], list(METRIC_COLUMNS))
            self.assertEqual(len(metrics["data"]["rows"]), 1)
            self.assertNotIn(owner.token, raw)
            code, csv_data, raw, err = _invoke(["--repo", str(root), "metrics", "--format", "csv"])
            self.assertEqual((code, csv_data["ok"], csv_data["code"], err), (0, True, "OK", ""))
            self.assertEqual(csv_data["data"]["format"], "csv")
            self.assertEqual(tuple(csv_data["data"]["content"].splitlines()[0].split(",")),
                             METRIC_COLUMNS)
            self.assertIn(claim.run_id, csv_data["data"]["content"])
            self.assertNotIn(owner.token, raw)
            with closing(connect(database)) as conn:
                self.assertEqual(_rows(conn), before)
            self.assertEqual(_files(canonical), files)

    def test_missing_runtime_database_refuses_without_creating_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _, _, _ = _repo(temp)
            runtime = root / ".sdd/runtime"
            self.assertFalse(runtime.exists())
            for command in (("result", "--json", "--run-id",
                             "123e4567-e89b-12d3-a456-426614174000"),
                            ("metrics", "--format", "json"),
                            ("metrics", "--format", "csv")):
                with self.subTest(command=command):
                    code, body, _, err = _invoke(["--repo", str(root), *command])
                    self.assertEqual((code, body["ok"], body["code"], body["data"], err),
                                     (3, False, "CATALOG_NOT_REBUILT", None, ""))
                    self.assertFalse(runtime.exists())

if __name__ == "__main__":
    unittest.main()
