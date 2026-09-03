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
