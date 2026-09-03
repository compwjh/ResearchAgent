/* eslint-disable @repo/no-style-props */

export type StageTimelineName =
  | "load"
  | "prompt_eval"
  | "ttft"
  | "first_token"
  | "eval"
  | "overhead";

/** A stage duration is expressed in milliseconds. Unknown values are rendered as unavailable. */
export type StageTimelineStage = {
  key?: StageTimelineName | string;
  name?: StageTimelineName | string;
  stage?: StageTimelineName | string;
  label?: string;
  value?: number | null;
  durationMs?: number | null;
  duration?: number | null;
  duration_ms?: number | null;
  ms?: number | null;
};

export type StageTimelineProps = {
  stages: readonly StageTimelineStage[];
  className?: string;
  ariaLabel?: string;
};

type NormalizedStage = {
  key: string;
  label: string;
  value: number | null;
  status: "available" | "missing" | "invalid" | "clamped";
};

const STAGE_LABELS: Record<string, string> = {
  load: "Load",
  prompt_eval: "Prompt eval",
  ttft: "TTFT",
  first_token: "First token",
  eval: "Eval",
  overhead: "Overhead",
};

function stageKey(stage: StageTimelineStage, index: number): string {
  return stage.key ?? stage.name ?? stage.stage ?? `stage-${index + 1}`;
}

function stageValue(stage: StageTimelineStage): number | null | undefined {
  return (
    stage.durationMs ??
    stage.value ??
    stage.duration ??
    stage.duration_ms ??
    stage.ms
  );
}

function normalizeStage(stage: StageTimelineStage, index: number): NormalizedStage {
  const key = stageKey(stage, index);
  const rawValue = stageValue(stage);
  const label = stage.label ?? STAGE_LABELS[key] ?? key;

  if (rawValue === null || rawValue === undefined) {
    return { key, label, value: null, status: "missing" };
  }
  if (typeof rawValue !== "number" || !Number.isFinite(rawValue)) {
    return { key, label, value: null, status: "invalid" };
  }
  if (rawValue < 0) {
    return { key, label, value: 0, status: "clamped" };
  }
  return { key, label, value: rawValue, status: "available" };
}

export function formatStageDuration(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)} ms`;
}

/**
 * Render Ollama's stages on one shared, non-negative time scale.
 *
 * Labels are kept in a separate legend so a zero-width stage remains visible;
 * the colored segments themselves are strictly proportional to the total.
 */
export function StageTimeline({
  stages,
  className,
  ariaLabel = "Ollama stage timeline",
}: StageTimelineProps) {
  const normalizedStages = stages.map(normalizeStage);
  const totalMs = normalizedStages.reduce(
    (total, stage) => total + (stage.value ?? 0),
    0,
  );
  const safeTotalMs = Number.isFinite(totalMs) && totalMs > 0 ? totalMs : 0;

  return (
    <div
      className={className ? `space-y-2 ${className}` : "space-y-2"}
      data-testid="stage-timeline"
      role="group"
      aria-label={ariaLabel}
      data-total-ms={safeTotalMs}
    >
      <div
        className="bg-muted flex h-3 w-full overflow-hidden rounded"
        data-testid="stage-timeline-track"
        role="img"
        aria-label={`${ariaLabel}, total ${formatStageDuration(safeTotalMs)}`}
      >
        {normalizedStages.map((stage, index) => {
          const widthPercent =
            safeTotalMs > 0 && stage.value !== null
              ? Math.max(0, Math.min((stage.value / safeTotalMs) * 100, 100))
              : 0;

          return (
            <div
              key={`${stage.key}-${index}`}
              className="h-full shrink-0"
              data-testid="stage-timeline-segment"
              data-stage={stage.key}
              data-status={stage.status === "available" ? undefined : stage.status}
              role="img"
              aria-label={`${stage.label}: ${
                stage.value === null ? "missing" : formatStageDuration(stage.value)
              }`}
              style={{ width: `${widthPercent}%` }}
            />
          );
        })}
      </div>

      <div className="grid gap-x-4 gap-y-1 sm:grid-cols-2" data-testid="stage-timeline-legend">
        {normalizedStages.map((stage, index) => (
          <div
            key={`${stage.key}-legend-${index}`}
            className="flex items-center justify-between gap-2 text-xs"
            data-testid="stage-timeline-label"
            data-stage={stage.key}
            data-status={stage.status === "available" ? undefined : stage.status}
          >
            <span className="text-muted-foreground">{stage.label}</span>
            <span className="tabular-nums">
              {formatStageDuration(stage.value)}
              {stage.value === null ? (
                <span className="sr-only"> (missing)</span>
              ) : null}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
