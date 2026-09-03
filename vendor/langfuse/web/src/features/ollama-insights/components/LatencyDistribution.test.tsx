// @vitest-environment node

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  LatencyDistribution,
  calculatePercentile,
  summarizeLatencyDistribution,
  type LatencyDistributionRow,
} from "./LatencyDistribution";

function render(rows: readonly LatencyDistributionRow[]) {
  return renderToStaticMarkup(<LatencyDistribution rows={rows} />);
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
});
