import { describe, expect, it, vi } from "vitest";

import type { QueryType } from "../types";
import { QueryBuilder } from "./queryBuilder";

// QueryBuilder.build checks the OTEL FINAL optimization before compiling SQL.
// Mock it so these stay unit-level and do not need ClickHouse.
vi.mock("../../../server/queries/clickhouse-sql/query-options", () => ({
  shouldSkipObservationsFinal: vi.fn().mockResolvedValue(false),
}));

// Mirrors buildSummaryQuery() in
// web/src/features/ollama-insights/server/router.ts (spec-013).
const ollamaSummaryQuery = {
  view: "observations",
  dimensions: [
    { field: "providedModelName" },
    { field: "route" },
    { field: "chainType" },
  ],
  metrics: [
    { measure: "count", aggregation: "sum" },
    { measure: "ttft", aggregation: "p50" },
    { measure: "ttft", aggregation: "p95" },
    { measure: "ttft", aggregation: "p99" },
    { measure: "load", aggregation: "p50" },
    { measure: "load", aggregation: "p95" },
    { measure: "load", aggregation: "p99" },
    { measure: "tokens_per_sec", aggregation: "avg" },
  ],
  filters: [
    { column: "type", operator: "=", value: "GENERATION", type: "string" },
  ],
  timeDimension: null,
  fromTimestamp: "2025-01-01T00:00:00.000Z",
  toTimestamp: "2025-01-08T00:00:00.000Z",
  orderBy: null,
} as QueryType;

const buildSummarySql = async () =>
  (
    await new QueryBuilder(undefined, "v2").build(
      ollamaSummaryQuery,
      "test-project",
      false,
    )
  ).query;

describe("queryBuilder Ollama metadata measures (spec-013)", () => {
  it("aggregates metadata reads in the inner SELECT so they are legal under its GROUP BY", async () => {
    const query = await buildSummarySql();

    // The two-level inner SELECT groups by (project_id, span_id). A bare
    // `metadata_values` read there is rejected by ClickHouse with
    // "Column ... is not under aggregate function and not in GROUP BY keys",
    // which reaches the UI as a masked tRPC internal error.
    expect(query).toMatch(/any\(\s*if\(isFinite\(/);
    // The @@AGG@@ marker must always be substituted, never emitted verbatim.
    expect(query).not.toContain("@@AGG@@");
  });

  it("emits the aggregated outer aliases the router maps rows from", async () => {
    const query = await buildSummarySql();

    for (const alias of [
      "sum_count",
      "p50_ttft",
      "p95_ttft",
      "p99_ttft",
      "p50_load",
      "p95_load",
      "p99_load",
      "avg_tokens_per_sec",
    ]) {
      expect(query).toMatch(new RegExp(`as\\s+${alias}\\b`, "i"));
    }
  });
});
