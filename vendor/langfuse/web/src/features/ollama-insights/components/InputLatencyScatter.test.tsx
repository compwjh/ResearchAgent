// @vitest-environment node

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  InputLatencyScatter,
  normalizeInputLatencyScatterRows,
  type InputLatencyScatterRow,
} from "./InputLatencyScatter";

function render(rows: readonly InputLatencyScatterRow[]) {
  return renderToStaticMarkup(<InputLatencyScatter rows={rows} />);
}

describe("InputLatencyScatter", () => {
  it("renders finite points with an accessible point list", () => {
    const html = render([
      { input_chars: 10, prompt_tokens: 2, ttft: 20, total_ms: 40, model: "qwen", route: "direct" },
      { input_chars: 20, prompt_tokens: 4, ttft: 0, total_ms: 10 },
    ]);

    expect(html).toContain('data-testid="input-latency-scatter"');
    expect(html).toContain('data-testid="input-latency-scatter-plot"');
    expect(html).toContain('data-testid="input-latency-scatter-points"');
    expect(html).toContain('data-point-count="2"');
    expect(html).toContain("Input size vs TTFT");
    expect(html).toContain("0 ms");
    expect(html).toContain("qwen");
    expect(html).toContain("direct");
  });

  it("prioritizes input_chars over prompt_tokens", () => {
    const data = normalizeInputLatencyScatterRows([
      { input_chars: 120, prompt_tokens: 12, ttft: 8, total_ms: 9 },
    ]);
    const html = render([
      { input_chars: 120, prompt_tokens: 12, ttft: 8, total_ms: 9 },
    ]);

    expect(data.points[0]?.inputSize).toBe(120);
    expect(data.points[0]?.inputSizeSource).toBe("input_chars");
    expect(html).toContain('data-input-size="120"');
    expect(html).toContain('data-input-size-source="input_chars"');
  });

  it("falls back to prompt_tokens when input_chars is unavailable or invalid", () => {
    const data = normalizeInputLatencyScatterRows([
      { input_chars: null, prompt_tokens: 7, ttft: 11, total_ms: 12 },
      { input_chars: -1, prompt_tokens: 9, ttft: 13, total_ms: 14 },
    ]);

    expect(data.points.map((point) => point.inputSize)).toEqual([7, 9]);
    expect(data.points.every((point) => point.inputSizeSource === "prompt_tokens")).toBe(true);
  });

  it("renders every row in mixed-metric data, choosing the available y metric per row", () => {
    const data = normalizeInputLatencyScatterRows([
      { input_chars: 10, ttft: 20 },
      { input_chars: 20, total_ms: 40 },
    ]);
    const html = render([
      { input_chars: 10, ttft: 20 },
      { input_chars: 20, total_ms: 40 },
    ]);

    expect(data.points).toHaveLength(2);
    expect(data.points.map((point) => point.latencyMetric)).toEqual([
      "ttft",
      "total_ms",
    ]);
    expect(data.metric).toBe("mixed");
    expect(html).toContain('data-point-count="2"');
    expect(html).toContain('data-latency-metric="ttft"');
    expect(html).toContain('data-latency-metric="total_ms"');
    expect(html).toContain('data-latency-ms="20"');
    expect(html).toContain('data-latency-ms="40"');
  });

  it("falls back per row and preserves zero latency values in mixed data", () => {
    const data = normalizeInputLatencyScatterRows([
      { input_chars: 10, ttft: 0 },
      { input_chars: 20, total_ms: 0 },
    ]);
    const html = render([
      { input_chars: 10, ttft: 0 },
      { input_chars: 20, total_ms: 0 },
    ]);

    expect(data.points).toHaveLength(2);
    expect(data.points.every((point) => point.latencyMs === 0)).toBe(true);
    expect(data.invalidRows).toBe(0);
    expect(data.missingRows).toBe(0);
    expect(html).toContain('data-point-count="2"');
    expect(html).toContain('data-latency-ms="0"');
    expect(html).toContain("0 ms");
  });

  it("shows the empty state when every row is missing both y metrics", () => {
    const data = normalizeInputLatencyScatterRows([
      { input_chars: 10 },
      { input_chars: 20, total_ms: null },
    ]);
    const html = render([
      { input_chars: 10 },
      { input_chars: 20, total_ms: null },
    ]);

    expect(data.points).toHaveLength(0);
    expect(data.missingRows).toBe(2);
    expect(html).not.toContain('data-point-count="2"');
    expect(html).toContain("No finite input-size and latency points available.");
  });

  it("reports empty and invalid data without rendering non-finite values", () => {
    const invalidHtml = render([
      { input_chars: -1, prompt_tokens: null, ttft: 3, total_ms: 4 },
      { input_chars: Number.NaN, prompt_tokens: Number.POSITIVE_INFINITY, ttft: null, total_ms: -2 },
    ]);
    const emptyHtml = render([]);

    expect(invalidHtml).toContain("No finite input-size and latency points available.");
    expect(invalidHtml).toContain("null, negative, or non-finite");
    expect(invalidHtml).not.toContain("NaN");
    expect(invalidHtml).not.toContain("Infinity");
    expect(emptyHtml).toContain("No input latency data available.");
  });
});
