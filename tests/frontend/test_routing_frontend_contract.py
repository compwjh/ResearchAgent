"""Spec031 Task05 frontend routing-insights and benchmark view contracts."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "frontend/research-tasks.js"
INDEX = ROOT / "frontend/index.html"
STYLES = ROOT / "frontend/styles.css"


def test_frontend_contracts_and_safe_projection():
    probe = r'''
const assert = require('assert');
const api = require('./frontend/research-tasks.js');

const insight = api.routingInsightText({
  model_tier: 'fast', resolved_model: 'qwen3.5:9b', reason: '规则优先',
  worker_grant: 1, resource_reason: 'RESOURCE_PROBE_FAILED',
  from_tier: 'fast', to_tier: 'strong', prompt: 'PRIVATE_PROMPT',
});
assert.match(insight, /模型：qwen3\.5:9b/);
assert.match(insight, /档位：fast/);
assert.match(insight, /额度：1/);
assert.match(insight, /资源：资源探针不可用/);
assert.match(insight, /升级：fast → strong/);
assert.doesNotMatch(insight, /PRIVATE_PROMPT|prompt/);
for (const value of [null, undefined, '', false, Infinity, ' 1 ', '1e3']) {
  assert.equal(api.boundedNumber(value, 0, 100), null);
}
assert.equal(api.boundedNumber(0, 0, 100), 0);
assert.equal(api.boundedNumber('0.25', 0, 1), 0.25);
for (const value of ['/srv/models/qwen', '/Applications/Ollama', '/data/cache', '/root/.cache', '/usr/local/bin', '/opt/models/qwen', '/mnt/cache', '/workspace/project', '/var/tmp/x', '/private/tmp/x', '/Users/wjh/x', '/a/b', '~/models/x', '../models/x', './models/x', 'foo/../bar', 'foo\\\\bar', 'C:\\\\models\\\\x', '\\\\\\\\server\\\\share', 'file:///tmp/x', 'localhost:11434', '127.0.0.1:11434']) {
  assert.equal(api.routingInsightText({ resolved_model: value, reason: value }), '', value);
}
assert.match(api.routingInsightText({ reason: 'fast output invalid after one retry' }), /说明：fast output invalid after one retry/);

const benchmark = api.normalizeBenchmarkSummary({
  policy: { status: 'shadow' },
  warm: { median_ttft_ms: 761.619, throughput_completion_tokens_per_s: 16.012 },
  cold: { median_ttft_ms: 4362.848, throughput_completion_tokens_per_s: 4.508 },
  unknown_metric: 999,
});
assert.equal(benchmark.policy_status, 'shadow');
assert.equal(benchmark.warm.median_ttft_ms, 761.619);
  assert.equal(benchmark.cold.throughput_completion_tokens_per_s, 4.508);
  assert.equal(benchmark.unknown_metric, undefined);
  assert.equal(api.benchmarkMetricText('failure_rate', 0.25), '失败率：25 %');
assert.equal(api.normalizeBenchmarkSummary({ warm: { median_ttft_ms: -1 } }).warm?.median_ttft_ms, undefined);
for (const value of [null, undefined, '', false, ' 1 ', '1e3']) {
  const invalid = api.normalizeBenchmarkSummary({ warm: { median_ttft_ms: value, throughput: value, failure_rate: value, peak_memory_bytes: value } });
  assert.equal(invalid.warm, undefined, String(value));
}
assert.equal(api.normalizeBenchmarkSummary(null), null);
assert.equal(api.safeSelectionId('catalog:paper-1'), 'catalog:paper-1');
assert.equal(api.safeSelectionId('../private'), '');
assert.equal(api.safeSelectionId('https://example.invalid/paper'), '');
const selections = api.selectionProjectionValues([
  { catalog_paper_id: 'paper-1', relevance: 0.82, evidence_level: 'catalog', facets: ['agent safety'] },
  { catalog_paper_id: 'paper-1', relevance: 0.1 },
  { catalog_paper_id: 'paper-2', relevance: 4, evidence_level: 'invalid', title: 'must not render' },
]);
assert.deepEqual(selections[0], { catalog_paper_id: 'paper-1', relevance: 0.82, evidence_level: 'catalog', facets: ['agent safety'] });
assert.deepEqual(selections[1], { catalog_paper_id: 'paper-2' });
console.log('Spec031 frontend routing/benchmark contract: PASS');
'''
    result = subprocess.run(["node", "-e", probe], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr or result.stdout


def test_frontend_dom_and_security_contracts():
    research = RESEARCH.read_text(encoding="utf-8")
    index = INDEX.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")
    assert "research-benchmark-section" in index
    assert "research-benchmark-metrics" in index
    assert "/assets/research-tasks.js?v=11" in index
    assert "routingInsightText" in research
    assert "normalizeBenchmarkSummary" in research
    assert "loadSelectionSnapshot" in research
    assert "acquisition-preview" in research
    assert "research-benchmark" in styles
    assert "innerHTML" not in research
    for forbidden in ("payload.prompt", "payload.answer", "payload.thought", "payload.chain_of_thought", "payload.owner_token", "payload.host_path"):
        assert forbidden not in research
