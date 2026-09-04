// @vitest-environment node

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { StageTimeline, type StageTimelineStage } from "./StageTimeline";

function render(stages: readonly StageTimelineStage[]) {
  return renderToStaticMarkup(<StageTimeline stages={stages} />);
}

describe("StageTimeline", () => {
  it("renders stages against one shared proportional scale", () => {
    const html = render([
      { key: "load", value: 20 },
      { key: "prompt_eval", value: 30 },
      { key: "eval", value: 50 },
    ]);

    expect(html).toContain('data-testid="stage-timeline"');
    expect(html).toContain('data-total-ms="100"');
    expect(html).toContain('data-stage="load"');
    expect(html).toContain('style="width:20%"');
    expect(html).toContain('style="width:30%"');
    expect(html).toContain('style="width:50%"');
    expect(html).toContain('aria-label="Ollama stage timeline"');
  });

  it("keeps a visible label for zero-value stages", () => {
    const html = render([
      { key: "load", value: 0 },
      { key: "eval", value: 10 },
    ]);

    expect(html).toContain('data-stage="load"');
    expect(html).toContain("Load");
    expect(html).toContain("0.0 ms");
    expect(html).toContain('style="width:0%"');
  });

  it("marks null values as missing and displays an em dash", () => {
    const html = render([{ key: "overhead", value: null }]);

    expect(html).toContain('data-status="missing"');
    expect(html).toContain("Overhead");
    expect(html).toContain("—");
    expect(html).toContain("missing");
  });

  it("cleans negative and non-finite values without invalid widths", () => {
    const html = render([
      { key: "load", value: -5 },
      { key: "eval", value: Number.NaN },
      { key: "overhead", value: Number.POSITIVE_INFINITY },
      { key: "ttft", value: 5 },
    ]);

    expect(html).toContain('data-stage="load"');
    expect(html).toContain('data-status="clamped"');
    expect(html).toContain('data-status="invalid"');
    expect(html).not.toContain("NaN");
    expect(html).not.toContain("Infinity");
    expect(html).not.toMatch(/width:-/);
  });

  it("uses zero widths while retaining all labels when total duration is zero", () => {
    const html = render([
      { key: "load", value: 0 },
      { key: "prompt_eval", value: 0 },
      { key: "ttft", value: null },
    ]);

    expect(html).toContain('data-total-ms="0"');
    expect(html.match(/style="width:0%"/g)).toHaveLength(3);
    expect(html).toContain("Load");
    expect(html).toContain("Prompt eval");
    expect(html).toContain("TTFT");
  });
});
