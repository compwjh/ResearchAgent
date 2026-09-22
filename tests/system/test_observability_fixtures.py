"""固定 Langfuse fixture 的离线契约测试（spec-013 Task 06）。"""

import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.generate_observability_fixtures import (
    REQUIRED_METADATA,
    build_fixture_plan,
    timestamp_is_not_future,
)


class ObservabilityFixtureTests(unittest.TestCase):
    def test_dry_run_matrix_has_expected_dimensions_and_count(self):
        samples = build_fixture_plan(fixture_id="spec013-task06-test")
        self.assertEqual(len(samples), 20)
        self.assertEqual(len({sample.sample_id for sample in samples}), 20)
        self.assertEqual(sum(sample.success for sample in samples), 16)
        self.assertEqual(sum(not sample.success for sample in samples), 4)
        self.assertEqual({sample.temperature for sample in samples}, {"cold", "hot"})
        self.assertEqual({sample.input_size for sample in samples}, {"short", "long"})
        self.assertEqual({sample.chain_type for sample in samples}, {"chat", "kb"})
        self.assertEqual({sample.route for sample in samples}, {"direct"})

    def test_every_sample_has_metadata_contract(self):
        samples = build_fixture_plan(fixture_id="spec013-task06-contract")
        for sample in samples:
            metadata = sample.metadata()
            self.assertTrue(all(metadata.get(key) for key in REQUIRED_METADATA), sample.sample_id)
            self.assertEqual(metadata["fixture_id"], "spec013-task06-contract")
            self.assertEqual(metadata["fixture_version"], "v1")
            self.assertEqual(metadata["sample_id"], sample.sample_id)
            self.assertIn("success", metadata)
            self.assertIn("error_type", metadata)

    def test_timestamps_are_current_and_future_values_are_rejected(self):
        now = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
        samples = build_fixture_plan(fixture_id="spec013-task06-time", now=now)
        for sample in samples:
            self.assertTrue(timestamp_is_not_future(sample.event_ts, now=now))
            self.assertTrue(timestamp_is_not_future(sample.completion_start_time, now=now))
        future = (now + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        self.assertFalse(timestamp_is_not_future(future, now=now))

    def test_command_defaults_to_dry_run_and_outputs_json(self):
        script = Path(__file__).parents[2] / "scripts" / "generate_observability_fixtures.py"
        completed = subprocess.run(
            [sys.executable, str(script)], capture_output=True, text=True, check=False
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["mode"], "dry-run")
        self.assertEqual(payload["sample_count"], 20)


if __name__ == "__main__":
    unittest.main()
