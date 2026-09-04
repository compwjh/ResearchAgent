import { describe, expect, it, vi } from "vitest";

// The router module wires into the full tRPC server context (createTRPCRouter,
// protectedProjectProcedure) and the query server (executeQuery). For unit
// testing the pure query-builders we stub those two modules so the module loads
// without booting the server/DB stack. The builders under test are plain
// functions that do not depend on the stubbed symbols.
vi.mock("@/src/server/api/trpc", () => ({
  createTRPCRouter: () => ({}),
  protectedProjectProcedure: { input: () => ({ query: () => ({}) }) },
}));
vi.mock("@langfuse/shared/query/server", () => ({
  executeQuery: vi.fn(),
}));

import { query as queryModel } from "@langfuse/shared/query";

import {
  OllamaInsightsFilterInput,
  OllamaInsightsListInput,
  buildFilters,
  buildObservationQuery,
  buildSummaryQuery,
  effectiveTo,
} from "./router";

const baseFilter = {
  projectId: "proj-1",
  from: new Date("2024-01-01T00:00:00Z"),
  to: new Date("2024-01-02T00:00:00Z"),
};

describe("OllamaInsights router query-builders (spec-013)", () => {
  it("rejects limit outside 1..100 (zod boundary)", () => {
    expect(OllamaInsightsListInput.safeParse({ ...baseFilter, limit: 0 }).success).toBe(false);
    expect(OllamaInsightsListInput.safeParse({ ...baseFilter, limit: 101 }).success).toBe(false);
    expect(OllamaInsightsListInput.safeParse({ ...baseFilter, limit: 1 }).success).toBe(true);
    expect(OllamaInsightsListInput.safeParse({ ...baseFilter, limit: 100 }).success).toBe(true);
    // default
    expect(OllamaInsightsListInput.safeParse(baseFilter).success).toBe(true);
  });

  it("always pins type=GENERATION regardless of input (never overridable)", () => {
    const f = buildFilters(baseFilter);
    const typeFilter = f.find((x) => x.column === "type");
    expect(typeFilter).toBeDefined();
    expect(typeFilter?.operator).toBe("=");
    expect(typeFilter?.value).toBe("GENERATION");
  });

  it("binds model/route/chainType/success filters only when provided", () => {
    const none = buildFilters(baseFilter);
    expect(none.find((x) => x.column === "providedModelName")).toBeUndefined();
    expect(none.find((x) => x.column === "route")).toBeUndefined();
    expect(none.find((x) => x.column === "chainType")).toBeUndefined();
    expect(none.find((x) => x.column === "success")).toBeUndefined();

    const all = buildFilters({
      ...baseFilter,
      model: "llama3",
      route: "direct",
      chainType: "chat",
      success: true,
    });
    expect(all.find((x) => x.column === "providedModelName" && x.value === "llama3")).toBeDefined();
    expect(all.find((x) => x.column === "route" && x.value === "direct")).toBeDefined();
    expect(all.find((x) => x.column === "chainType" && x.value === "chat")).toBeDefined();
    expect(all.find((x) => x.column === "success" && x.value === true)).toBeDefined();
  });

  it("bounds event time with timestamp <= now (future/delayed ingestion isolation)", () => {
    const f = buildFilters(baseFilter);
    const ts = f.find((x) => x.column === "timestamp");
    expect(ts).toBeDefined();
    expect(ts?.operator).toBe("<=");
    expect(ts?.type).toBe("datetime");
  });

  it("effectiveTo caps a future `to` to the current time", () => {
    const future = effectiveTo({
      ...baseFilter,
      to: new Date(Date.now() + 1000 * 60 * 60 * 24 * 365),
    });
    expect(future.getTime()).toBeLessThanOrEqual(Date.now() + 1000);
  });

  it("list query carries chartConfig.row_limit = limit (Top-100 pagination)", () => {
    const filters = buildFilters(baseFilter);
    const q = buildObservationQuery({ ...baseFilter, limit: 42 }, filters);
    expect(q.view).toBe("observations");
    expect((q.chartConfig as { row_limit: number } | undefined)?.row_limit).toBe(42);
  });

  it("summary query omits row_limit so it is not bounded by Top-100 (full aggregate)", () => {
    const filters = buildFilters(baseFilter);
    const q = buildSummaryQuery(baseFilter, filters);
    expect(q.view).toBe("observations");
    expect(q.chartConfig).toBeUndefined();
    const serialized = JSON.stringify(q);
    expect(serialized).not.toContain("row_limit");
  });

  it("built queries satisfy the query-engine zod schema (chartConfig.type is mandatory)", () => {
    const filters = buildFilters(baseFilter);
    for (const q of [
      buildObservationQuery({ ...baseFilter, limit: 100 }, filters),
      buildSummaryQuery(baseFilter, filters),
    ]) {
      const parsed = queryModel.safeParse(q);
      expect(
        parsed.success,
        parsed.success ? "" : JSON.stringify(parsed.error.issues),
      ).toBe(true);
    }
  });

  it("project isolation: built queries are project-agnostic; projectId is passed separately to executeQuery", () => {
    const filters = buildFilters(baseFilter);
    for (const q of [buildObservationQuery({ ...baseFilter, limit: 100 }, filters), buildSummaryQuery(baseFilter, filters)]) {
      const serialized = JSON.stringify(q);
      expect(serialized).not.toContain("proj-1");
      expect(serialized).not.toContain("projectId");
    }
    // The schema guarantees a projectId is required on every request.
    expect(OllamaInsightsFilterInput.safeParse({ from: baseFilter.from, to: baseFilter.to }).success).toBe(false);
  });
});
