import { describe, expect, it } from "vitest";

import {
   eventsObservationsView,
} from "../../../../../packages/shared/src/features/query/dataModel";

// spec-013 / task-07: Ollama numeric insight measures must reject negative and
// non-finite metadata values BEFORE quantile()/avg() aggregation, otherwise bad
// rows pollute P50/P95/P99 and averages before being mapped to NULL downstream.
//
// We assert the generated measure SQL string directly. The imported view comes
// from shared source (a pure SQL-string graph with no Prisma dependency).
const GUARD_OPEN = "if(isFinite(";
const GUARD_NONNEG = ">= 0";
const GUARD_NULL = "CAST(NULL AS Nullable(Float64))";

const numericMeasures = [
   "ttft",
   "load",
   "prompt_eval",
   "eval",
   "overhead",
   "tokens_per_sec",
   "is_cold_start",
   "input_chars",
   "prompt_tokens",
   "total_ms",
] as const;

describe(
   "eventsObservationsView numeric measures reject non-finite/negative metadata (spec-013)",
   () => {
    it("guards every numeric measure SQL with isFinite + non-negative + NULL", () => {
      for (const measure of numericMeasures) {
        const sql = eventsObservationsView.measures[measure]?.sql;
        expect(typeof sql, `measure '${measure}' should be declared`).toBe(
           "string",
        );
        expect(sql).toContain("toFloat64OrNull(");
        expect(sql).toContain(GUARD_OPEN);
        expect(sql).toContain(GUARD_NONNEG);
        expect(sql).toContain(GUARD_NULL);
       }
     });

    it("wraps the parsed value inside the guard and preserves the metadata source", () => {
      const ttft = eventsObservationsView.measures.ttft!.sql;
       // The guarded value X reads the parallel metadata arrays.
      const x =
        "toFloat64OrNull(nullIf(arrayElement(events_observations.metadata_values, " +
         "indexOf(events_observations.metadata_names, 'ttft_ms')), ''))";
       // Guard shape, wrapped in the @@AGG@@ template so the query builder can
      // resolve it to any(...) in the two-level inner SELECT:
      // @@AGG@@(if(isFinite(X) AND X >= 0, X, CAST(NULL AS Nullable(Float64))))
      expect(ttft).toBe(
        `@@AGG@@(if(isFinite(${x}) AND ${x} >= 0, ${x}, CAST(NULL AS Nullable(Float64))))`,
       );
      expect(ttft).toContain("events_observations.metadata_values");
      expect(ttft).toContain("events_observations.metadata_names");
      expect(ttft).toContain("'ttft_ms'");
     });

    it("does not carry the numeric guard onto the cold-start boolean dimension", () => {
      const isColdStart = eventsObservationsView.dimensions.isColdStart?.sql;
      expect(typeof isColdStart).toBe("string");
       // Boolean dimension must stay a tri-state mapping (true/false/null).
      expect(isColdStart).not.toContain(GUARD_OPEN);
      expect(isColdStart).not.toContain(GUARD_NONNEG);
      expect(isColdStart).toContain("multiIf(");
      expect(isColdStart).toContain("NULL");
     });

    it("declares aggs on every numeric measure so @@AGG@@ is substituted", () => {
      // Regression: without `aggs`, the query builder emits `measure.sql`
      // verbatim into the inner SELECT of a two-level query. That SELECT is
      // grouped by (project_id, span_id), so the bare `metadata_values`
      // reference is rejected by ClickHouse with "Column ... is not under
      // aggregate function and not in GROUP BY keys" (surfaced to the UI as a
      // masked tRPC internal error).
      for (const measure of numericMeasures) {
        const declared = eventsObservationsView.measures[measure];
        expect(declared, `measure '${measure}' should be declared`).toBeDefined();
        expect(declared?.sql).toContain("@@AGG@@(");
        expect(
          declared?.aggs,
          `measure '${measure}' must declare aggs, else @@AGG@@ is never substituted`,
        ).toEqual({ agg: "any" });
       }
     });
   },
);
