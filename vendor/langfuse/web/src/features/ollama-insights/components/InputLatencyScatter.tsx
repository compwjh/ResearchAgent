/* eslint-disable @repo/no-style-props */

export type InputLatencyScatterMetric = "ttft" | "total_ms";

export type InputLatencyScatterRow = {
  input_chars?: number | null;
  prompt_tokens?: number | null;
  ttft?: number | null;
  total_ms?: number | null;
  model?: string | null;
  route?: string | null;
};

export type InputLatencyScatterPoint = {
  rowIndex: number;
  inputSize: number;
  inputSizeSource: "input_chars" | "prompt_tokens";
  latencyMs: number;
  latencyMetric: InputLatencyScatterMetric;
  model: string | null;
  route: string | null;
};

type InputLatencyScatterDisplayMetric = InputLatencyScatterMetric | "mixed";

export type InputLatencyScatterData = {
  points: InputLatencyScatterPoint[];
  metric: InputLatencyScatterDisplayMetric;
  invalidRows: number;
  missingRows: number;
};

export type InputLatencyScatterProps = {
  rows: readonly InputLatencyScatterRow[];
  /** Select a y-axis metric, or choose TTFT per row with total duration fallback. */
  yMetric?: InputLatencyScatterMetric | "auto";
  className?: string;
  ariaLabel?: string;
};

function isFiniteNonNegative(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function metricValue(
  row: InputLatencyScatterRow,
  metric: InputLatencyScatterMetric,
): number | null {
  const value = metric === "ttft" ? row.ttft : row.total_ms;
  return isFiniteNonNegative(value) ? value : null;
}

function getAutoMetric(row: InputLatencyScatterRow) {
  if (metricValue(row, "ttft") !== null) return "ttft";
  if (metricValue(row, "total_ms") !== null) return "total_ms";
  return null;
}

function getDisplayMetric(
  metrics: ReadonlySet<InputLatencyScatterMetric>,
): InputLatencyScatterDisplayMetric {
  if (metrics.has("ttft") && metrics.has("total_ms")) return "mixed";
  if (metrics.has("ttft")) return "ttft";
  if (metrics.has("total_ms")) return "total_ms";
  return "total_ms";
}

/**
 * Keep only finite, non-negative points while preserving zero values.
 * Input character counts take precedence over token counts on each row.
 */
export function normalizeInputLatencyScatterRows(
  rows: readonly InputLatencyScatterRow[],
  requestedMetric: InputLatencyScatterMetric | "auto" = "auto",
): InputLatencyScatterData {
  const safeRows = Array.isArray(rows) ? rows : [];
  const points: InputLatencyScatterPoint[] = [];
  const availableMetrics = new Set<InputLatencyScatterMetric>();
  safeRows.forEach((row) => {
    const autoMetric = getAutoMetric(row);
    if (autoMetric) availableMetrics.add(autoMetric);
  });
  const metric =
    requestedMetric === "auto"
      ? getDisplayMetric(availableMetrics)
      : requestedMetric;
  let invalidRows = 0;
  let missingRows = 0;

  safeRows.forEach((row, rowIndex) => {
    const inputChars = row.input_chars;
    const promptTokens = row.prompt_tokens;
    const inputSize = isFiniteNonNegative(inputChars)
      ? inputChars
      : isFiniteNonNegative(promptTokens)
        ? promptTokens
        : null;
    const inputSizeSource = isFiniteNonNegative(inputChars)
      ? "input_chars"
      : "prompt_tokens";
    const latencyMetric =
      requestedMetric === "auto" ? getAutoMetric(row) : requestedMetric;
    const latencyMs = latencyMetric ? metricValue(row, latencyMetric) : null;

    if (inputSize === null || latencyMetric === null || latencyMs === null) {
      const hasInvalidValue =
        (inputChars !== null &&
          inputChars !== undefined &&
          !isFiniteNonNegative(inputChars)) ||
        (promptTokens !== null &&
          promptTokens !== undefined &&
          !isFiniteNonNegative(promptTokens)) ||
        (latencyMetric === null &&
          ((row.ttft !== null && row.ttft !== undefined) ||
            (row.total_ms !== null && row.total_ms !== undefined))) ||
        (latencyMetric !== null && latencyMs === null);
      if (hasInvalidValue) invalidRows += 1;
      else missingRows += 1;
      return;
    }

    points.push({
      rowIndex,
      inputSize,
      inputSizeSource,
      latencyMs,
      latencyMetric,
      model: row.model ?? null,
      route: row.route ?? null,
    });
  });

  if (requestedMetric === "auto") {
    const pointMetrics = new Set(points.map((point) => point.latencyMetric));
    return {
      points,
      metric: getDisplayMetric(
        pointMetrics.size > 0 ? pointMetrics : availableMetrics,
      ),
      invalidRows,
      missingRows,
    };
  }

  return { points, metric, invalidRows, missingRows };
}

function formatNumber(value: number): string {
  return value === 0 ? "0" : value.toFixed(1);
}

function metricLabel(metric: InputLatencyScatterDisplayMetric): string {
  if (metric === "ttft") return "TTFT";
  if (metric === "total_ms") return "Total duration";
  return "Latency (TTFT / total duration)";
}

function metricLegend(metric: InputLatencyScatterDisplayMetric): string {
  if (metric === "mixed") {
    return "Y-axis: TTFT when available for a row; total duration otherwise.";
  }
  return `Y-axis: ${metricLabel(metric)}.`;
}

function percentage(value: number, min: number, max: number): number {
  if (min === max) return 50;
  const result = ((value - min) / (max - min)) * 100;
  return Number.isFinite(result) ? Math.max(0, Math.min(result, 100)) : 50;
}

function pointDescription(
  point: InputLatencyScatterPoint,
  index: number,
): string {
  const metadata = [point.model, point.route].filter(Boolean).join(", ");
  return `Point ${index + 1}: ${formatNumber(point.inputSize)} ${
    point.inputSizeSource === "input_chars"
      ? "input characters"
      : "prompt tokens"
  }, ${metricLabel(point.latencyMetric)} ${formatNumber(point.latencyMs)} ms${
    metadata ? ` (${metadata})` : ""
  }`;
}

export function InputLatencyScatter({
  rows,
  yMetric = "auto",
  className,
  ariaLabel = "Input size and latency scatter plot",
}: InputLatencyScatterProps) {
  const data = normalizeInputLatencyScatterRows(rows, yMetric);
  const wrapperClassName = className ? `space-y-3 ${className}` : "space-y-3";
  const label = `${ariaLabel} (${metricLabel(data.metric)} by input size)`;

  if (data.points.length === 0) {
    return (
      <section
        className={wrapperClassName}
        data-testid="input-latency-scatter"
        aria-label={ariaLabel}
      >
        <p
          className="text-muted-foreground text-sm"
          data-testid="input-latency-scatter-empty"
        >
          {rows.length === 0
            ? "No input latency data available."
            : "No finite input-size and latency points available."}
        </p>
        <p
          className="text-muted-foreground text-xs"
          data-testid="input-latency-scatter-legend"
        >
          {metricLegend(data.metric)}
        </p>
        {rows.length > 0 ? (
          <p
            className="text-muted-foreground text-xs"
            data-testid="input-latency-scatter-invalid"
          >
            Rows with null, negative, or non-finite values were omitted.
          </p>
        ) : null}
      </section>
    );
  }

  const inputSizes = data.points.map((point) => point.inputSize);
  const latencies = data.points.map((point) => point.latencyMs);
  const minInputSize = Math.min(...inputSizes);
  const maxInputSize = Math.max(...inputSizes);
  const minLatency = Math.min(...latencies);
  const maxLatency = Math.max(...latencies);

  return (
    <section
      className={wrapperClassName}
      data-testid="input-latency-scatter"
      role="group"
      aria-label={label}
      data-point-count={data.points.length}
      data-y-metric={data.metric}
    >
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="font-medium">
          Input size vs {metricLabel(data.metric)}
        </h3>
        <span className="text-muted-foreground text-sm">
          {data.points.length} point{data.points.length === 1 ? "" : "s"}
        </span>
      </div>
      <p
        className="text-muted-foreground text-xs"
        data-testid="input-latency-scatter-legend"
      >
        {metricLegend(data.metric)}
      </p>

      <div
        className="bg-muted/30 relative h-48 w-full rounded border"
        data-testid="input-latency-scatter-plot"
        role="img"
        aria-label={label}
      >
        <div className="absolute inset-0" aria-hidden="true">
          {data.points.map((point, index) => (
            <span
              key={`${point.rowIndex}-${index}`}
              className="bg-primary absolute h-3 w-3 -translate-x-1/2 translate-y-1/2 rounded-full"
              data-testid="input-latency-scatter-point"
              data-input-size={point.inputSize}
              data-input-size-source={point.inputSizeSource}
              data-latency-ms={point.latencyMs}
              data-latency-metric={point.latencyMetric}
              style={{
                left: `${percentage(point.inputSize, minInputSize, maxInputSize)}%`,
                bottom: `${percentage(point.latencyMs, minLatency, maxLatency)}%`,
              }}
            />
          ))}
        </div>
        <span className="text-muted-foreground absolute bottom-1 left-2 text-[10px]">
          {formatNumber(minInputSize)} input size
        </span>
        <span className="text-muted-foreground absolute top-1 right-2 text-[10px]">
          {formatNumber(maxLatency)} ms
        </span>
      </div>

      <ol
        className="sr-only"
        data-testid="input-latency-scatter-points"
        aria-label="Accessible scatter plot points"
      >
        {data.points.map((point, index) => (
          <li key={`${point.rowIndex}-description`}>
            {pointDescription(point, index)}
          </li>
        ))}
      </ol>

      {data.invalidRows + data.missingRows > 0 ? (
        <p
          className="text-muted-foreground text-xs"
          data-testid="input-latency-scatter-omitted"
        >
          {data.invalidRows + data.missingRows} row
          {data.invalidRows + data.missingRows === 1 ? "" : "s"} omitted because
          its input size or latency was unavailable or invalid.
        </p>
      ) : null}
    </section>
  );
}
