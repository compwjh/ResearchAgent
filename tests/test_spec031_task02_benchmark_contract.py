"""Spec031 Task02 benchmark artifact/contract checks.

These tests are intentionally offline.  The real Ollama run is recorded in
``docs/sdd/plans/031/artifacts/task-02/benchmark-raw.json``; CI must not turn a
missing service into fabricated benchmark data.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
ARTIFACT_DIR = ROOT / "docs/sdd/plans/031/artifacts/task-02"


def test_raw_benchmark_covers_all_worker_counts_and_metrics():
    raw = json.loads((ARTIFACT_DIR / "benchmark-raw.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] == "spec031-task02-benchmark-v2"
    assert raw["model"] == "qwen3.5:9b"
    assert raw["worker_counts"] == [1, 2, 3, 4]
    assert raw["warm_waves"] >= 1
    assert len(raw["blocks"]) == 4
    for block in raw["blocks"]:
        assert block["worker_count"] in {1, 2, 3, 4}
        assert block["cold"]["failures"] == 0
        assert block["warm"]["failures"] == 0
        assert block["warm"]["throughput_completion_tokens_per_s"] > 0
        assert block["warm"]["median_ttft_ms"] is not None
        assert block["peak_size_vram_bytes"] > 0
        assert block["ps_after_warm"]["ok"] is True
        probe = block["resource_probe_after_prewarm"]
        assert probe["status"] in {"ok", "RESOURCE_PROBE_FAILED"}
        assert "available_memory_bytes" in probe
        assert "model_footprint_bytes" in probe
        assert "max_safe_workers" in probe
        for sample in block["samples"]:
            assert sample["response_json_valid"] is True
            assert sample["response_text"] == '{"ok":true}'
            assert sample["quality_error"] is None

    provenance = raw["provenance"]
    for field in (
        "script",
        "python_version",
        "platform",
        "system",
        "machine",
        "git",
        "fixed_prompt_sha256",
    ):
        assert provenance.get(field)
    assert provenance["git"]["revision"]
    assert raw["listener_probe"]["base_port"] == 11434
    assert raw["listener_probe"]["candidate_backup_ports"] == [11435, 11436, 11437, 11438]
    assert len(raw["listener_probe"]["port_probes"]) == 5
    assert raw["listener_probe"]["port_probes"][0]["url"].endswith(":11434")


def test_benchmark_harness_is_bounded_and_uses_existing_http_contract():
    source = (ARTIFACT_DIR / "ollama-topology-benchmark.py").read_text(encoding="utf-8")
    assert "/api/chat" in source
    assert "/api/ps" in source
    assert '"think": False' in source
    assert '"format": "json"' in source
    assert "trust_env=False" in source
    assert '"num_predict": PREDICT_TOKENS' in source
    assert 'keep_alive=0' in source
    assert 'QUALITY_ASSERTION_FAILED' in source
    assert 'response_json_valid' in source
    assert '_resource_probe' in source
    assert '_listener_probe' in source
    assert 'fixed_prompt_sha256' in source
    assert "backend.app" not in source
