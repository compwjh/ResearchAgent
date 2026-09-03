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
    { key: "ttft", value: row.ttft ?? null },
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

  const insights = api.ollamaInsights.list.useQuery(
    {
      projectId,
      from: timeRange.from,
      to: timeRange.to,
      limit: 100,
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

        {insights.isLoading ? (
          <div className="rounded-md border p-4" aria-label="Loading Ollama insights">
            <div className="mb-4 text-sm">Loading Ollama insights…</div>
            <Skeleton className="h-8 w-full" />
          </div>
        ) : insights.isError ? (
          <div
            className="rounded-md border border-destructive/50 p-4 text-destructive"
            role="alert"
          >
            Unable to load Ollama insights: {insights.error.message}
          </div>
        ) : insights.data?.rows.length ? (
          <>
            <LatencyDistribution
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
                    <th className="whitespace-nowrap px-4 py-3 font-medium">Time</th>
                    <th className="whitespace-nowrap px-4 py-3 font-medium">Model</th>
                    <th className="whitespace-nowrap px-4 py-3 font-medium">Route</th>
                    <th className="whitespace-nowrap px-4 py-3 font-medium">Chain type</th>
                    <th className="whitespace-nowrap px-4 py-3 font-medium">Success</th>
                    <th className="whitespace-nowrap px-4 py-3 font-medium">TTFT</th>
                    <th className="whitespace-nowrap px-4 py-3 font-medium">Total</th>
                    <th className="whitespace-nowrap px-4 py-3 font-medium">Throughput</th>
                    <th className="whitespace-nowrap px-4 py-3 font-medium">Cold start</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {insights.data.rows.map((row) => {
                    const stages = getStageTimelineStages(row);
                    const totalDuration = getTotalStageDuration(stages);

                    return (
                      <Fragment key={row.id}>
                        <tr>
                          <td className="whitespace-nowrap px-4 py-3">
                            {formatDate(row.timestamp)}
                          </td>
                          <td
                            className="max-w-64 truncate px-4 py-3"
                            title={row.model ?? undefined}
                          >
                            {row.model ?? "—"}
                          </td>
                          <td className="whitespace-nowrap px-4 py-3">
                            {row.route ?? "—"}
                          </td>
                          <td className="whitespace-nowrap px-4 py-3">
                            {row.chainType ?? "—"}
                          </td>
                          <td className="whitespace-nowrap px-4 py-3">
                            {formatBoolean(row.success)}
                          </td>
                          <td className="whitespace-nowrap px-4 py-3">
                            {formatMilliseconds(row.ttft)}
                          </td>
                          <td className="whitespace-nowrap px-4 py-3">
                            {formatMilliseconds(totalDuration)}
                          </td>
                          <td className="whitespace-nowrap px-4 py-3">
                            {formatThroughput(row.tokens_per_sec)}
                          </td>
                          <td className="whitespace-nowrap px-4 py-3">
                            {formatBoolean(row.is_cold_start)}
                          </td>
                        </tr>
                        <tr>
                          <td className="bg-muted/20 px-4 py-3" colSpan={9}>
                            <div className="space-y-2">
                              <div className="flex items-baseline justify-between gap-2">
                                <span className="font-medium">Stage timing</span>
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
