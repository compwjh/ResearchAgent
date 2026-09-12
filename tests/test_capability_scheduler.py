"""spec-035 Bug3：模型能力 SQLite 持久化与每日调度探测测试。"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from backend.app.platform import capability_store, ollama
from backend.app.platform.capability_scheduler import run_capability_sweep
from backend.app.platform.ollama import ReasoningCapabilities


def _caps(model="m1", source="ollama_probe", efforts=("off", "medium")):
    return ReasoningCapabilities(
        model, tuple(efforts), "medium" if efforts else None, source, "2026-09-13T00:00:00+00:00", {}
    )


class CapabilityStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile_path()
        capability_store.set_db_path(self.tmp / "caps.sqlite3")

    def tearDown(self):
        capability_store.set_db_path(None)

    def test_upsert_then_get_roundtrip(self):
        capability_store.upsert_capabilities(
            "m1", supported_efforts=("off", "high"), default_effort="high",
            source="ollama_probe", evidence={"high": "E1"}, probed_at="2026-09-13T00:00:00+00:00",
        )
        stored = capability_store.get_capabilities("m1")
        self.assertEqual(stored["supported_efforts"], ("off", "high"))
        self.assertEqual(stored["default_effort"], "high")
        self.assertEqual(stored["evidence"], {"high": "E1"})

    def test_upsert_overwrites_previous(self):
        for efforts in (("off",), ("off", "low", "high")):
            capability_store.upsert_capabilities(
                "m1", supported_efforts=efforts, default_effort=efforts[-1],
                source="ollama_probe", evidence={}, probed_at="2026-09-13T00:00:00+00:00",
            )
        self.assertEqual(capability_store.get_capabilities("m1")["supported_efforts"], ("off", "low", "high"))

    def test_get_missing_returns_none(self):
        self.assertIsNone(capability_store.get_capabilities("nope"))

    def test_freshness_window(self):
        now = datetime.now(timezone.utc)
        self.assertTrue(capability_store.probed_at_is_fresh(now.isoformat(), max_age_seconds=86400))
        stale = (now - timedelta(seconds=86401)).isoformat()
        self.assertFalse(capability_store.probed_at_is_fresh(stale, max_age_seconds=86400))
        self.assertFalse(capability_store.probed_at_is_fresh("garbage", max_age_seconds=86400))


class GetReasoningCapabilitiesDbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile_path()
        capability_store.set_db_path(self.tmp / "caps.sqlite3")
        ollama.clear_reasoning_capability_cache()

    def tearDown(self):
        capability_store.set_db_path(None)
        ollama.clear_reasoning_capability_cache()

    def test_fresh_db_hit_skips_probe(self):
        capability_store.upsert_capabilities(
            "m1", supported_efforts=("off", "high"), default_effort="high",
            source="ollama_probe", evidence={}, probed_at=datetime.now(timezone.utc).isoformat(),
        )
        with patch.object(ollama, "probe_reasoning_capabilities") as probe:
            caps = ollama.get_reasoning_capabilities("m1")
        probe.assert_not_called()
        self.assertEqual(caps.supported_efforts, ("off", "high"))
        self.assertEqual(caps.source, "cache")

    def test_stale_db_row_triggers_probe_and_writes_back(self):
        capability_store.upsert_capabilities(
            "m1", supported_efforts=("off",), default_effort="off",
            source="ollama_probe", evidence={}, probed_at="2020-01-01T00:00:00+00:00",
        )
        with patch.object(ollama, "probe_reasoning_capabilities", return_value=_caps()) as probe:
            caps = ollama.get_reasoning_capabilities("m1")
        probe.assert_called_once_with("m1")
        self.assertEqual(caps.source, "ollama_probe")
        stored = capability_store.get_capabilities("m1")
        self.assertEqual(stored["supported_efforts"], ("off", "medium"))

    def test_refresh_bypasses_db_and_writes_back(self):
        capability_store.upsert_capabilities(
            "m1", supported_efforts=("off",), default_effort="off",
            source="ollama_probe", evidence={}, probed_at=datetime.now(timezone.utc).isoformat(),
        )
        with patch.object(ollama, "probe_reasoning_capabilities", return_value=_caps(efforts=("off", "low"))) as probe:
            caps = ollama.get_reasoning_capabilities("m1", refresh=True)
        probe.assert_called_once()
        self.assertEqual(caps.supported_efforts, ("off", "low"))
        self.assertEqual(capability_store.get_capabilities("m1")["supported_efforts"], ("off", "low"))

    def test_unknown_probe_keeps_four_state_semantics_and_db_value(self):
        """unknown 探测不改写 DB，也不新增 DB-stale 回退（四态契约不变，spec-026 B16）。"""
        capability_store.upsert_capabilities(
            "m1", supported_efforts=("off", "low"), default_effort="low",
            source="ollama_probe", evidence={}, probed_at="2020-01-01T00:00:00+00:00",
        )
        with patch.object(ollama, "probe_reasoning_capabilities", return_value=_caps(source="unknown", efforts=())):
            caps = ollama.get_reasoning_capabilities("m1")
        self.assertEqual(caps.source, "unknown")
        self.assertEqual(caps.supported_efforts, ())
        # 库中旧值未被覆盖
        self.assertEqual(capability_store.get_capabilities("m1")["supported_efforts"], ("off", "low"))


class CapabilitySchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile_path()
        capability_store.set_db_path(self.tmp / "caps.sqlite3")

    def tearDown(self):
        capability_store.set_db_path(None)

    def test_sweep_probes_all_models_and_upserts(self):
        models = [{"name": "a:latest"}, {"name": "b:latest"}]

        def fake_probe(model):
            if model == "a:latest":
                return _caps(model, efforts=("off", "high"))
            return _caps(model, source="unknown", efforts=())

        with (
            patch("httpx.get") as tags,
            patch("backend.app.platform.capability_scheduler.probe_reasoning_capabilities", side_effect=fake_probe),
        ):
            tags.return_value.json.return_value = {"models": models}
            updated = run_capability_sweep()
        self.assertEqual(updated, 1)  # unknown 的 b 不入库
        self.assertIsNotNone(capability_store.get_capabilities("a:latest"))
        self.assertIsNone(capability_store.get_capabilities("b:latest"))

    def test_sweep_unknown_does_not_overwrite_existing(self):
        capability_store.upsert_capabilities(
            "a:latest", supported_efforts=("off",), default_effort="off",
            source="ollama_probe", evidence={}, probed_at="2020-01-01T00:00:00+00:00",
        )

        def fake_probe(model):
            return _caps(model, source="unknown", efforts=())

        with (
            patch("httpx.get") as tags,
            patch("backend.app.platform.capability_scheduler.probe_reasoning_capabilities", side_effect=fake_probe),
        ):
            tags.return_value.json.return_value = {"models": [{"name": "a:latest"}]}
            self.assertEqual(run_capability_sweep(), 0)
        self.assertEqual(capability_store.get_capabilities("a:latest")["supported_efforts"], ("off",))

    def test_sweep_tags_failure_is_noop(self):
        import httpx

        with patch("httpx.get", side_effect=httpx.ConnectError("down")):
            self.assertEqual(run_capability_sweep(), 0)


def tempfile_path():
    import tempfile
    from pathlib import Path

    return Path(tempfile.mkdtemp())


if __name__ == "__main__":
    unittest.main()
