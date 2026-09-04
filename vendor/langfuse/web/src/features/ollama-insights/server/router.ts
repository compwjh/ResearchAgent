import { TRPCError } from "@trpc/server";
import { z } from "zod";
import { executeQuery } from "@langfuse/shared/query/server";
import { type QueryType } from "@langfuse/shared/query";
import {
  createTRPCRouter,
  protectedProjectProcedure,
} from "@/src/server/api/trpc";

const OllamaInsightsListInput = z
  .object({
    projectId: z.string(),
    from: z.coerce.date(),
    to: z.coerce.date(),
    model: z.string().trim().min(1).optional(),
    route: z.string().trim().min(1).optional(),
    chainType: z.string().trim().min(1).optional(),
    success: z.boolean().optional(),
    limit: z.coerce.number().int().positive().lte(100).default(100),
  })
  .refine((input) => input.from < input.to, {
    message: "from must be before to",
    path: ["from"],
  });

type OllamaInsightsRow = {
  id: string;
  name: string;
  timestamp: string | null;
  model: string | null;
  route: string | null;
  chainType: string | null;
  success: boolean | null;
  ttft: number | null;
  load: number | null;
  prompt_eval: number | null;
  eval: number | null;
  overhead: number | null;
  tokens_per_sec: number | null;
  is_cold_start: boolean | null;
  input_chars: number | null;
  prompt_tokens: number | null;
  total_ms: number | null;
};

const toNumberOrNull = (value: unknown): number | null => {
  if (value === null || value === undefined || value === "") return null;
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
};

const toStringOrNull = (value: unknown): string | null => {
  if (value === null || value === undefined || value === "") return null;
  return String(value);
};

const toBooleanOrNull = (value: unknown): boolean | null => {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    if (["true", "1", "yes"].includes(value.toLowerCase())) return true;
    if (["false", "0", "no"].includes(value.toLowerCase())) return false;
  }
  const numberValue = toNumberOrNull(value);
  return numberValue === null ? null : numberValue !== 0;
};

const effectiveTo = (input: z.infer<typeof OllamaInsightsListInput>): Date => {
  const now = new Date();
  return input.to < now ? input.to : now;
};

const buildFilters = (input: z.infer<typeof OllamaInsightsListInput>) => {
  const to = effectiveTo(input);
  if (input.from >= to) {
    throw new TRPCError({
      code: "BAD_REQUEST",
      message: "from must be before the current time",
    });
  }

  const filters: QueryType["filters"] = [];
  filters.push({
    column: "type",
    operator: "=",
    value: "GENERATION",
    type: "string",
  });
  if (input.model) {
    filters.push({
      column: "providedModelName",
      operator: "=",
      value: input.model,
      type: "string",
    });
  }
  if (input.route) {
    filters.push({
      column: "route",
      operator: "=",
      value: input.route,
      type: "string",
    });
  }
  if (input.chainType) {
    filters.push({
      column: "chainType",
      operator: "=",
      value: input.chainType,
      type: "string",
    });
  }
  if (input.success !== undefined) {
    filters.push({
      column: "success",
      operator: "=",
      value: input.success,
      type: "boolean",
    });
  }
  // The v2 view ranges rows by start_time; explicitly bound event_ts as well
  // so delayed/future ingestion records never enter the Insights result.
  filters.push({
    column: "timestamp",
    operator: "<=",
    value: new Date(),
    type: "datetime",
  });
  return filters;
};

const buildObservationQuery = (
  input: z.infer<typeof OllamaInsightsListInput>,
  filters: QueryType["filters"],
): QueryType => ({
  view: "observations",
  dimensions: [
    { field: "id" },
    { field: "name" },
    { field: "timestamp" },
    { field: "startTime" },
    { field: "providedModelName" },
    { field: "route" },
    { field: "chainType" },
    { field: "success" },
  ],
  metrics: [
    { measure: "ttft", aggregation: "avg" },
    { measure: "load", aggregation: "avg" },
    { measure: "prompt_eval", aggregation: "avg" },
    { measure: "eval", aggregation: "avg" },
    { measure: "overhead", aggregation: "avg" },
    { measure: "tokens_per_sec", aggregation: "avg" },
    { measure: "is_cold_start", aggregation: "avg" },
    { measure: "input_chars", aggregation: "avg" },
    { measure: "prompt_tokens", aggregation: "avg" },
    { measure: "total_ms", aggregation: "avg" },
  ],
  filters,
  timeDimension: null,
  fromTimestamp: input.from.toISOString(),
  toTimestamp: effectiveTo(input).toISOString(),
  orderBy: [{ field: "avg_ttft", direction: "desc" }],
  // `type` is required by the query-engine zod schema. QueryBuilder itself only
  // reads `bins`/`row_limit`, but omitting `type` fails schema validation with
  // `Invalid query: [{"path":["chartConfig","type"],...}]`.
  chartConfig: { type: "TABLE", row_limit: input.limit },
});

const buildCountQuery = (
  input: z.infer<typeof OllamaInsightsListInput>,
  filters: QueryType["filters"],
): QueryType => ({
  view: "observations",
  dimensions: [],
  metrics: [{ measure: "count", aggregation: "sum" }],
  filters,
  timeDimension: null,
  fromTimestamp: input.from.toISOString(),
  toTimestamp: effectiveTo(input).toISOString(),
  orderBy: null,
});

const mapRow = (row: Record<string, unknown>): OllamaInsightsRow => ({
  id: String(row.id ?? ""),
  name: String(row.name ?? ""),
  timestamp: toStringOrNull(row.timestamp ?? row.startTime),
  model: toStringOrNull(row.providedModelName),
  route: toStringOrNull(row.route),
  chainType: toStringOrNull(row.chainType),
  success: toBooleanOrNull(row.success),
  ttft: toNumberOrNull(row.avg_ttft),
  load: toNumberOrNull(row.avg_load),
  prompt_eval: toNumberOrNull(row.avg_prompt_eval),
  eval: toNumberOrNull(row.avg_eval),
  overhead: toNumberOrNull(row.avg_overhead),
  tokens_per_sec: toNumberOrNull(row.avg_tokens_per_sec),
  is_cold_start: toBooleanOrNull(row.avg_is_cold_start),
  input_chars: toNumberOrNull(row.avg_input_chars),
  prompt_tokens: toNumberOrNull(row.avg_prompt_tokens),
  total_ms: toNumberOrNull(row.avg_total_ms),
});

export const ollamaInsightsRouter = createTRPCRouter({
  list: protectedProjectProcedure
    .input(OllamaInsightsListInput)
    .query(async ({ input }) => {
      const filters = buildFilters(input);
      const [rows, countRows] = await Promise.all([
        executeQuery(input.projectId, buildObservationQuery(input, filters), "v2"),
        executeQuery(input.projectId, buildCountQuery(input, filters), "v2"),
      ]);

      return {
        rows: rows.map(mapRow),
        total: toNumberOrNull(countRows[0]?.sum_count) ?? 0,
      };
    }),
});
