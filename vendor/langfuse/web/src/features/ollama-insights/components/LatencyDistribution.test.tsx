// @vitest-environment node

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  LatencyDistribution,
  calculatePercentile,
  summarizeLatencyDistribution,
  summarizeLatencyAggregates,
  type LatencyDistributionAggregate,
  type LatencyDistributionRow,
} from "./LatencyDistribution";

function render(
  rows: readonly LatencyDistributionRow[],
  aggregates?: readonly LatencyDistributionAggregate[],
) {
  return renderToStaticMarkup(
    <LatencyDistribution rows={rows} aggregates={aggregates} />,
  );
}

describe("LatencyDistribution", () => {
  it("separates cold and hot rows and reports their counts", () => {
    const html = render([
      { ttft: 100, tokens_per_sec: 10, is_cold_start: true },
      { ttft: 200, tokens_per_sec: 20, is_cold_start: true },
      { ttft: 50, tokens_per_sec: 30, is_cold_start: false },
    ]);

    expect(html).toContain('data-testid="latency-distribution"');
    expect(html).toContain('data-group="cold"');
    expect(html).toContain('data-group="hot"');
    expect(html).toContain("Count: 2");
    expect(html).toContain("Count: 1");
    expect(html).toContain("Cold starts");
    expect(html).toContain("Hot starts");
    expect(html).toContain("Average throughput");
  });

  it("computes linear-interpolated TTFT percentiles and mean throughput", () => {
    const summary = summarizeLatencyDistribution([
      { ttft: 1, tokens_per_sec: 10, is_cold_start: true },
      { ttft: 2, tokens_per_sec: 20, is_cold_start: true },
      { ttft: 3, tokens_per_sec: 30, is_cold_start: true },
      { ttft: 4, tokens_per_sec: 40, is_cold_start: true },
      { ttft: 5, tokens_per_sec: 50, is_cold_start: true },
    ]);

    expect(summary.cold.p50).toBe(3);
    expect(summary.cold.p95).toBeCloseTo(4.8);
    expect(summary.cold.p99).toBeCloseTo(4.96);
    expect(summary.cold.averageTokensPerSecond).toBe(30);
    expect(calculatePercentile([1, 2, 3, 4, 5], 50)).toBe(3);
  });

  it("excludes null, negative, and non-finite metrics without rendering them", () => {
    const html = render([
      { ttft: null, tokens_per_sec: null, is_cold_start: true },
      { ttft: -1, tokens_per_sec: -2, is_cold_start: true },
      { ttft: Number.NaN, tokens_per_sec: Number.POSITIVE_INFINITY, is_cold_start: false },
      { ttft: 25, tokens_per_sec: 5, is_cold_start: false },
      { ttft: 10, tokens_per_sec: 8, is_cold_start: null },
    ]);

    expect(html).toContain("TTFT data unavailable for this group");
    expect(html).toContain("Throughput data unavailable for this group");
    expect(html).toContain("Invalid negative or non-finite metric values were excluded");
    expect(html).toContain("1 row omitted because cold/hot classification is unavailable");
    expect(html).not.toContain("NaN");
    expect(html).not.toContain("Infinity");
    expect(html).not.toContain("-1.0 ms");
  });

  it("renders an explicit empty state", () => {
    const html = render([]);

    expect(html).toContain('data-testid="latency-distribution-empty"');
    expect(html).toContain("No latency distribution data available.");
    expect(html).toContain("Count: 0");
  });

  it("renders full aggregates by model, route, chain type, and cold/hot group", () => {
    const html = render(
      [
        {
          ttft: 999,
          tokens_per_sec: 999,
          is_cold_start: true,
        },
      ],
      [
        {
          model: "llama3.2",
          route: "direct",
          chainType: "chat",
          isColdStart: true,
          count: 42,
          ttft_p50: 100,
          ttft_p95: 150,
          ttft_p99: 180,
          load_p50: 10,
          load_p95: 20,
          load_p99: 30,
          tokens_per_sec_avg: 25,
        },
        {
          model: "llama3.2",
          route: "langchain",
          chainType: "kb",
          isColdStart: false,
          count: 7,
          ttft_p50: 40,
          ttft_p95: 60,
          ttft_p99: 80,
          load_p50: 1,
          load_p95: 2,
          load_p99: 3,
          tokens_per_sec_avg: 50,
        },
      ],
    );

    expect(html.match(/data-aggregate-group="true"/g)).toHaveLength(2);
    expect(html).toContain('data-group="cold"');
    expect(html).toContain('data-group="hot"');
    expect(html).toContain('data-model="llama3.2"');
    expect(html).toContain('data-route="direct"');
    expect(html).toContain('data-route="langchain"');
    expect(html).toContain('data-chain-type="chat"');
    expect(html).toContain('data-chain-type="kb"');
    expect(html).toContain("Count: 42");
    expect(html).toContain("Count: 7");
    expect(html).toContain("100.0 ms");
    expect(html).not.toContain("999.0 ms");
  });

  it("renders aggregate TTFT and load percentiles plus average throughput", () => {
    const aggregate: LatencyDistributionAggregate = {
      model: "qwen",
      route: "direct",
      chainType: "chat",
      isColdStart: true,
      count: 5,
      ttft_p50: 10,
      ttft_p95: 20,
      ttft_p99: 30,
      load_p50: 1.25,
      load_p95: 2.5,
      load_p99: 3.75,
      tokens_per_sec_avg: 40,
    };
    const summary = summarizeLatencyAggregates([aggregate])[0];
    const html = render([], [aggregate]);

    expect(summary.loadP50).toBe(1.25);
    expect(summary.loadP95).toBe(2.5);
    expect(summary.loadP99).toBe(3.75);
    expect(html).toContain("P50 Load");
    expect(html).toContain("1.3 ms");
    expect(html).toContain("P95 Load");
    expect(html).toContain("2.5 ms");
    expect(html).toContain("P99 Load");
    expect(html).toContain("3.8 ms");
    expect(html).toContain("40.00 tokens/s");
  });

  it("uses aggregate mode for empty and unknown groups and sanitizes invalid metrics", () => {
    const emptyHtml = render(
      [{ ttft: 999, tokens_per_sec: 999, is_cold_start: true }],
      [],
    );
    expect(emptyHtml).toContain('data-testid="latency-distribution-empty"');
    expect(emptyHtml).toContain("No latency distribution aggregates available.");
    expect(emptyHtml).not.toContain("999.0 ms");

    const unknownHtml = render([], [
      {
        model: null,
        route: null,
        chainType: null,
        isColdStart: null,
        count: 2,
        ttft_p50: -1,
        ttft_p95: Number.NaN,
        ttft_p99: Number.POSITIVE_INFINITY,
        load_p50: -2,
        load_p95: Number.NaN,
        load_p99: Number.POSITIVE_INFINITY,
        tokens_per_sec_avg: -3,
      },
    ]);
    expect(unknownHtml).toContain('data-group="unknown"');
    expect(unknownHtml).toContain("One or more aggregate groups have no cold/hot classification.");
    expect(unknownHtml).toContain("Invalid negative or non-finite aggregate metric values were excluded");
    expect(unknownHtml).not.toContain("NaN");
    expect(unknownHtml).not.toContain("Infinity");
    expect(unknownHtml).not.toContain("-1.0 ms");
  });
});
