import { useRouter } from "next/router";
import { Fragment, useState } from "react";
import Page from "@/src/components/layouts/page";
import { Skeleton } from "@/src/components/ui/skeleton";
import {
  StageTimeline,
  type StageTimelineStage,
} from "@/src/features/ollama-insights/components/StageTimeline";
import { InputLatencyScatter } from "@/src/features/ollama-insights/components/InputLatencyScatter";
import { LatencyDistribution } from "@/src/features/ollama-insights/components/LatencyDistribution";
import { formatDetailValue } from "@/src/features/ollama-insights/lib/redact";
import { api } from "@/src/utils/api";

const RECENT_RANGE_MS = 24 * 60 * 60 * 1000;

function formatDate(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function formatMilliseconds(value: number | null) {
  return value === null ? "—" : `${value.toFixed(1)} ms`;
}

function formatThroughput(value: number | null) {
  return value === null ? "—" : `${value.toFixed(2)} tokens/s`;
}

function formatBoolean(value: boolean | null) {
  return value === null ? "—" : value ? "Yes" : "No";
}

function findThinking(value: unknown, depth = 0): unknown {
  if (depth > 5 || value === null || value === undefined) return undefined;
  if (typeof value === "string") {
    try {
      return findThinking(JSON.parse(value), depth + 1);
    } catch {
      return undefined;
    }
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const thinking = findThinking(item, depth + 1);
      if (thinking !== undefined) return thinking;
    }
    return undefined;
  }
  if (typeof value !== "object") return undefined;
  for (const [key, entryValue] of Object.entries(value)) {
    if (key.toLowerCase() === "thinking") return entryValue;
    const thinking = findThinking(entryValue, depth + 1);
    if (thinking !== undefined) return thinking;
  }
  return undefined;
}

function isNonNegativeFinite(
  value: number | null | undefined,
): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function getFirstTokenIncrement(row: {
  load?: number | null;
  prompt_eval?: number | null;
  ttft?: number | null;
}) {
  if (
    !isNonNegativeFinite(row.ttft) ||
    !isNonNegativeFinite(row.load) ||
    !isNonNegativeFinite(row.prompt_eval)
  ) {
    return null;
  }

  return Math.max(row.ttft - row.load - row.prompt_eval, 0);
}

function getStageTimelineStages(row: {
  load?: number | null;
  prompt_eval?: number | null;
  ttft?: number | null;
  eval?: number | null;
  overhead?: number | null;
}): StageTimelineStage[] {
  return [
    { key: "load", value: row.load ?? null },
    { key: "prompt_eval", value: row.prompt_eval ?? null },
    { key: "first_token", value: getFirstTokenIncrement(row) },
    { key: "eval", value: row.eval ?? null },
    { key: "overhead", value: row.overhead ?? null },
  ];
}

function getTotalStageDuration(stages: readonly StageTimelineStage[]) {
  return stages.reduce((total, stage) => {
    const value = stage.value;
    return typeof value === "number" && Number.isFinite(value) && value > 0
      ? total + value
      : total;
  }, 0);
}

export default function OllamaInsightsPage() {
  const router = useRouter();
  const projectId = router.query.projectId as string;
  const [timeRange] = useState(() => {
    const to = new Date();
    return {
      from: new Date(to.getTime() - RECENT_RANGE_MS),
      to,
    };
  });
  const [modelFilter, setModelFilter] = useState("");
  const [routeFilter, setRouteFilter] = useState("");
  const [chainTypeFilter, setChainTypeFilter] = useState("");
  const [successFilter, setSuccessFilter] = useState<
    "all" | "success" | "failure"
  >("all");
  const [selectedDetailId, setSelectedDetailId] = useState<string | null>(null);

  const hasActiveFilters =
    Boolean(modelFilter.trim()) ||
    Boolean(routeFilter.trim()) ||
    Boolean(chainTypeFilter.trim()) ||
    successFilter !== "all";

  const insights = api.ollamaInsights.list.useQuery(
    {
      projectId,
      from: timeRange.from,
      to: timeRange.to,
      model: modelFilter.trim() || undefined,
      route: routeFilter.trim() || undefined,
      chainType: chainTypeFilter.trim() || undefined,
      success:
        successFilter === "all" ? undefined : successFilter === "success",
      limit: 100,
    },
    {
      enabled: Boolean(projectId),
      staleTime: 30_000,
    },
  );

  const selectedDetailRow = insights.data?.rows.find(
    (row) => row.id === selectedDetailId,
  );
  const detailStartTime = selectedDetailRow?.startTime
    ? new Date(selectedDetailRow.startTime)
    : null;
  const observationDetail = api.observations.byId.useQuery(
    {
      observationId: selectedDetailRow?.id ?? "",
      traceId: selectedDetailRow?.traceId ?? "",
      projectId,
      startTime:
        detailStartTime && !Number.isNaN(detailStartTime.getTime())
          ? detailStartTime
          : null,
      verbosity: "truncated",
    },
    {
      enabled: Boolean(
        projectId && selectedDetailRow?.id && selectedDetailRow?.traceId,
      ),
      staleTime: 5 * 60 * 1000,
      meta: { silentHttpCodes: [404] },
    },
  );

  const summary = api.ollamaInsights.summary.useQuery(
    {
      projectId,
      from: timeRange.from,
      to: timeRange.to,
      model: modelFilter.trim() || undefined,
      route: routeFilter.trim() || undefined,
      chainType: chainTypeFilter.trim() || undefined,
      success:
        successFilter === "all" ? undefined : successFilter === "success",
    },
    {
      enabled: Boolean(projectId),
      staleTime: 30_000,
    },
  );

  return (
    <Page
      headerProps={{
        title: "Ollama Insights",
        help: {
          description:
            "Inspect recent Ollama generations and their latency, throughput, and cold-start metrics.",
        },
      }}
      scrollable
    >
      <div className="flex flex-col gap-4">
        <p className="text-muted-foreground text-sm">
          Showing the last 24 hours for this project.
        </p>

        <section
          className="rounded-md border p-4"
          aria-labelledby="ollama-insights-filters"
        >
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 id="ollama-insights-filters" className="font-medium">
              Filters
            </h2>
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground text-sm underline underline-offset-4 disabled:pointer-events-none disabled:opacity-50"
              onClick={() => {
                setModelFilter("");
                setRouteFilter("");
                setChainTypeFilter("");
                setSuccessFilter("all");
              }}
              disabled={!hasActiveFilters}
              aria-label="Clear Ollama insights filters"
            >
              Clear filters
            </button>
          </div>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
            <label
              className="flex flex-col gap-1 text-sm"
              htmlFor="ollama-filter-model"
            >
              <span className="font-medium">Model</span>
              <input
                id="ollama-filter-model"
                type="text"
                value={modelFilter}
                onChange={(event) => setModelFilter(event.target.value)}
                placeholder="Filter by model"
                aria-label="Filter Ollama insights by model"
                className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring h-9 rounded-md border px-3 py-1 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
              />
            </label>
            <label
              className="flex flex-col gap-1 text-sm"
              htmlFor="ollama-filter-route"
            >
              <span className="font-medium">Route</span>
              <input
                id="ollama-filter-route"
                type="text"
                value={routeFilter}
                onChange={(event) => setRouteFilter(event.target.value)}
                placeholder="Filter by route"
                aria-label="Filter Ollama insights by route"
                className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring h-9 rounded-md border px-3 py-1 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
              />
            </label>
            <label
              className="flex flex-col gap-1 text-sm"
              htmlFor="ollama-filter-chain-type"
            >
              <span className="font-medium">Chain type</span>
              <input
                id="ollama-filter-chain-type"
                type="text"
                value={chainTypeFilter}
                onChange={(event) => setChainTypeFilter(event.target.value)}
                placeholder="Filter by chain type"
                aria-label="Filter Ollama insights by chain type"
                className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring h-9 rounded-md border px-3 py-1 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
              />
            </label>
            <label
              className="flex flex-col gap-1 text-sm"
              htmlFor="ollama-filter-success"
            >
              <span className="font-medium">Success</span>
              <select
                id="ollama-filter-success"
                value={successFilter}
                onChange={(event) =>
                  setSuccessFilter(
                    event.target.value as "all" | "success" | "failure",
                  )
                }
                aria-label="Filter Ollama insights by success status"
                className="border-input bg-background ring-offset-background focus-visible:ring-ring h-9 rounded-md border px-3 py-1 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
              >
                <option value="all">All</option>
                <option value="success">Success</option>
                <option value="failure">Failure</option>
              </select>
            </label>
          </div>
        </section>

        {insights.isLoading ? (
          <div
            className="rounded-md border p-4"
            aria-label="Loading Ollama insights"
          >
            <div className="mb-4 text-sm">Loading Ollama insights…</div>
            <Skeleton className="h-8 w-full" />
          </div>
        ) : insights.isError ? (
          <div
            className="border-destructive/50 text-destructive rounded-md border p-4"
            role="alert"
          >
            Unable to load Ollama insights: {insights.error.message}
          </div>
        ) : insights.data?.rows.length ? (
          <>
            {summary.isLoading ? (
              <p
                className="text-muted-foreground rounded-md border p-3 text-sm"
                role="status"
              >
                Loading full latency distribution…
              </p>
            ) : summary.isError ? (
              <p
                className="text-muted-foreground border-destructive/50 rounded-md border p-3 text-sm"
                role="alert"
              >
                Full latency distribution unavailable; showing loaded rows.
              </p>
            ) : null}
            <LatencyDistribution
              aggregates={summary.isSuccess ? summary.data : undefined}
              rows={insights.data.rows.map((row) => ({
                ttft: row.ttft,
                tokens_per_sec: row.tokens_per_sec,
                is_cold_start: row.is_cold_start,
                model: row.model,
                route: row.route,
              }))}
            />
            <InputLatencyScatter
              rows={insights.data.rows.map((row) => ({
                input_chars: row.input_chars,
                prompt_tokens: row.prompt_tokens,
                ttft: row.ttft,
                total_ms: row.total_ms,
                model: row.model,
                route: row.route,
              }))}
            />
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Ollama Insights metrics</caption>
                <thead className="bg-muted/50 text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium whitespace-nowrap">
                      Time
                    </th>
                    <th className="px-4 py-3 font-medium whitespace-nowrap">
                      Model
                    </th>
                    <th className="px-4 py-3 font-medium whitespace-nowrap">
                      Route
                    </th>
                    <th className="px-4 py-3 font-medium whitespace-nowrap">
                      Chain type
                    </th>
                    <th className="px-4 py-3 font-medium whitespace-nowrap">
                      Success
                    </th>
                    <th className="px-4 py-3 font-medium whitespace-nowrap">
                      TTFT
                    </th>
                    <th className="px-4 py-3 font-medium whitespace-nowrap">
                      Total
                    </th>
                    <th className="px-4 py-3 font-medium whitespace-nowrap">
                      Throughput
                    </th>
                    <th className="px-4 py-3 font-medium whitespace-nowrap">
                      Cold start
                    </th>
                    <th className="px-4 py-3 font-medium whitespace-nowrap">
                      Details
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {insights.data.rows.map((row) => {
                    const stages = getStageTimelineStages(row);
                    const totalDuration = getTotalStageDuration(stages);

                    return (
                      <Fragment key={row.id}>
                        <tr>
                          <td className="px-4 py-3 whitespace-nowrap">
                            {formatDate(row.timestamp)}
                          </td>
                          <td
                            className="max-w-64 truncate px-4 py-3"
                            title={row.model ?? undefined}
                          >
                            {row.model ?? "—"}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            {row.route ?? "—"}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            {row.chainType ?? "—"}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            {formatBoolean(row.success)}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            {formatMilliseconds(row.ttft)}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            {formatMilliseconds(totalDuration)}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            {formatThroughput(row.tokens_per_sec)}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            {formatBoolean(row.is_cold_start)}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            <button
                              type="button"
                              className="text-primary underline underline-offset-4"
                              onClick={() =>
                                setSelectedDetailId((current) =>
                                  current === row.id ? null : row.id,
                                )
                              }
                              aria-expanded={selectedDetailId === row.id}
                              aria-controls={`ollama-detail-${row.id}`}
                            >
                              {selectedDetailId === row.id
                                ? "Hide details"
                                : "View details"}
                            </button>
                          </td>
                        </tr>
                        <tr>
                          <td className="bg-muted/20 px-4 py-3" colSpan={10}>
                            <div className="space-y-2">
                              <div className="flex items-baseline justify-between gap-2">
                                <span className="font-medium">
                                  Stage timing
                                </span>
                                <span className="text-muted-foreground text-xs">
                                  Total: {formatMilliseconds(totalDuration)}
                                </span>
                              </div>
                              <StageTimeline
                                stages={stages}
                                ariaLabel={`Stage timing for ${row.model ?? "Ollama generation"}`}
                              />
                            </div>
                          </td>
                        </tr>
                        {selectedDetailId === row.id ? (
                          <tr id={`ollama-detail-${row.id}`}>
                            <td className="px-4 py-4" colSpan={10}>
                              <section
                                className="space-y-4 rounded-md border p-4"
                                aria-label={`Details for ${row.name || "Ollama generation"}`}
                              >
                                <h3 className="font-medium">
                                  Generation details
                                </h3>
                                <p
                                  className="text-muted-foreground text-xs"
                                  data-testid="ollama-detail-truncated"
                                >
                                  Content may be truncated because this detail
                                  view uses a truncated response.
                                </p>
                                {observationDetail.isLoading ? (
                                  <p
                                    className="text-muted-foreground text-sm"
                                    role="status"
                                  >
                                    Loading generation details…
                                  </p>
                                ) : observationDetail.isError ? (
                                  <p
                                    className="text-destructive text-sm"
                                    role="alert"
                                  >
                                    Unable to load generation details:{" "}
                                    {observationDetail.error.message}
                                  </p>
                                ) : !observationDetail.data ? (
                                  <p
                                    className="text-muted-foreground text-sm"
                                    role="status"
                                  >
                                    No generation details are available.
                                  </p>
                                ) : (
                                  <div className="grid gap-4 lg:grid-cols-3">
                                    <div>
                                      <h4 className="mb-1 text-sm font-medium">
                                        Input / prompt
                                      </h4>
                                      <pre className="bg-muted/30 max-h-72 overflow-auto rounded-md p-3 text-xs break-words whitespace-pre-wrap">
                                        {formatDetailValue(
                                          observationDetail.data.input,
                                        )}
                                      </pre>
                                    </div>
                                    <div>
                                      <h4 className="mb-1 text-sm font-medium">
                                        Thinking
                                      </h4>
                                      <pre className="bg-muted/30 max-h-72 overflow-auto rounded-md p-3 text-xs break-words whitespace-pre-wrap">
                                        {formatDetailValue(
                                          findThinking(
                                            observationDetail.data.metadata,
                                          ),
                                        )}
                                      </pre>
                                    </div>
                                    <div>
                                      <h4 className="mb-1 text-sm font-medium">
                                        Output
                                      </h4>
                                      <pre className="bg-muted/30 max-h-72 overflow-auto rounded-md p-3 text-xs break-words whitespace-pre-wrap">
                                        {formatDetailValue(
                                          observationDetail.data.output,
                                        )}
                                      </pre>
                                    </div>
                                  </div>
                                )}
                              </section>
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <div className="rounded-md border p-8 text-center" role="status">
            <p className="font-medium">No Ollama insights found.</p>
            <p className="text-muted-foreground mt-1 text-sm">
              Try again after generating an Ollama response in this project.
            </p>
          </div>
        )}
      </div>
    </Page>
  );
}
