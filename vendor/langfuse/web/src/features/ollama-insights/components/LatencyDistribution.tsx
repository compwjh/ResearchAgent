/* eslint-disable @repo/no-style-props */

export type LatencyDistributionRow = {
  ttft: number | null;
  tokens_per_sec: number | null;
  is_cold_start: boolean | null;
  model?: string | null;
  route?: string | null;
};

export type LatencyDistributionAggregate = {
  model: string | null;
  route: string | null;
  chainType: string | null;
  isColdStart: boolean | null;
  count: number;
  ttft_p50: number | null;
  ttft_p95: number | null;
  ttft_p99: number | null;
  load_p50: number | null;
  load_p95: number | null;
  load_p99: number | null;
  tokens_per_sec_avg: number | null;
};

export type LatencyDistributionGroupKey = "cold" | "hot" | "unknown";

export type LatencyDistributionGroup = {
  key: LatencyDistributionGroupKey;
  label: string;
  count: number;
  p50: number | null;
  p95: number | null;
  p99: number | null;
  averageTokensPerSecond: number | null;
};

export type LatencyDistributionSummary = {
  cold: LatencyDistributionGroup;
  hot: LatencyDistributionGroup;
  unknownCount: number;
  invalidTtftCount: number;
  invalidThroughputCount: number;
};

export type LatencyDistributionProps = {
  rows: readonly LatencyDistributionRow[];
  aggregates?: readonly LatencyDistributionAggregate[];
  className?: string;
  ariaLabel?: string;
};

const GROUP_LABELS: Record<LatencyDistributionGroupKey, string> = {
  cold: "Cold starts",
  hot: "Hot starts",
  unknown: "Unknown cold/hot classification",
};

const emptyGroup = (
  key: LatencyDistributionGroupKey,
): LatencyDistributionGroup => ({
  key,
  label: GROUP_LABELS[key],
  count: 0,
  p50: null,
  p95: null,
  p99: null,
  averageTokensPerSecond: null,
});

function validNonNegativeNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : null;
}

/** Linear-interpolated percentile over a numeric array. */
export function calculatePercentile(
  values: readonly number[],
  percentile: number,
): number | null {
  if (values.length === 0 || !Number.isFinite(percentile)) return null;

  const sorted = [...values].sort((a, b) => a - b);
  if (sorted.length === 1) return sorted[0];

  const rank =
    (Math.max(0, Math.min(percentile, 100)) / 100) * (sorted.length - 1);
  const lowerIndex = Math.floor(rank);
  const upperIndex = Math.ceil(rank);
  if (lowerIndex === upperIndex) return sorted[lowerIndex];

  const weight = rank - lowerIndex;
  return sorted[lowerIndex] * (1 - weight) + sorted[upperIndex] * weight;
}
function summarizeGroup(
  key: LatencyDistributionGroupKey,
  rows: readonly LatencyDistributionRow[],
): {
  group: LatencyDistributionGroup;
  invalidTtftCount: number;
  invalidThroughputCount: number;
} {
  const ttftValues: number[] = [];
  const throughputValues: number[] = [];
  let invalidTtftCount = 0;
  let invalidThroughputCount = 0;

  for (const row of rows) {
    const ttft = validNonNegativeNumber(row.ttft);
    const throughput = validNonNegativeNumber(row.tokens_per_sec);

    if (row.ttft !== null && row.ttft !== undefined && ttft === null) {
      invalidTtftCount += 1;
    } else if (ttft !== null) {
      ttftValues.push(ttft);
    }

    if (
      row.tokens_per_sec !== null &&
      row.tokens_per_sec !== undefined &&
      throughput === null
    ) {
      invalidThroughputCount += 1;
    } else if (throughput !== null) {
      throughputValues.push(throughput);
    }
  }

  return {
    group: {
      ...emptyGroup(key),
      count: rows.length,
      p50: calculatePercentile(ttftValues, 50),
      p95: calculatePercentile(ttftValues, 95),
      p99: calculatePercentile(ttftValues, 99),
      averageTokensPerSecond:
        throughputValues.length > 0
          ? throughputValues.reduce((sum, value) => sum + value, 0) /
            throughputValues.length
          : null,
    },
    invalidTtftCount,
    invalidThroughputCount,
  };
}

export type LatencyDistributionAggregateGroup = {
  key: LatencyDistributionGroupKey;
  label: string;
  model: string | null;
  route: string | null;
  chainType: string | null;
  count: number;
  p50: number | null;
  p95: number | null;
  p99: number | null;
  loadP50: number | null;
  loadP95: number | null;
  loadP99: number | null;
  averageTokensPerSecond: number | null;
  invalidMetricCount: number;
};

function validCount(value: unknown): { value: number; invalid: boolean } {
  if (value === null || value === undefined)
    return { value: 0, invalid: false };
  const count = validNonNegativeNumber(value);
  return count === null
    ? { value: 0, invalid: true }
    : { value: Math.floor(count), invalid: false };
}

function normalizeDimension(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function normalizedMetric(value: unknown): {
  value: number | null;
  invalid: boolean;
} {
  if (value === null || value === undefined)
    return { value: null, invalid: false };
  const metric = validNonNegativeNumber(value);
  return { value: metric, invalid: metric === null };
}

function aggregateKey(
  isColdStart: boolean | null,
): LatencyDistributionGroupKey {
  return isColdStart === true
    ? "cold"
    : isColdStart === false
      ? "hot"
      : "unknown";
}

export function summarizeLatencyAggregates(
  aggregates: readonly LatencyDistributionAggregate[],
): LatencyDistributionAggregateGroup[] {
  return aggregates.map((aggregate) => {
    const count = validCount(aggregate.count);
    const ttftP50 = normalizedMetric(aggregate.ttft_p50);
    const ttftP95 = normalizedMetric(aggregate.ttft_p95);
    const ttftP99 = normalizedMetric(aggregate.ttft_p99);
    const loadP50 = normalizedMetric(aggregate.load_p50);
    const loadP95 = normalizedMetric(aggregate.load_p95);
    const loadP99 = normalizedMetric(aggregate.load_p99);
    const throughput = normalizedMetric(aggregate.tokens_per_sec_avg);
    const invalidMetricCount = [
      count,
      ttftP50,
      ttftP95,
      ttftP99,
      loadP50,
      loadP95,
      loadP99,
      throughput,
    ].filter((metric) => metric.invalid).length;
    const key = aggregateKey(aggregate.isColdStart);

    return {
      key,
      label: GROUP_LABELS[key],
      model: normalizeDimension(aggregate.model),
      route: normalizeDimension(aggregate.route),
      chainType: normalizeDimension(aggregate.chainType),
      count: count.value,
      p50: ttftP50.value,
      p95: ttftP95.value,
      p99: ttftP99.value,
      loadP50: loadP50.value,
      loadP95: loadP95.value,
      loadP99: loadP99.value,
      averageTokensPerSecond: throughput.value,
      invalidMetricCount,
    };
  });
}

export function summarizeLatencyDistribution(
  rows: readonly LatencyDistributionRow[],
): LatencyDistributionSummary {
  const coldRows: LatencyDistributionRow[] = [];
  const hotRows: LatencyDistributionRow[] = [];
  let unknownCount = 0;

  for (const row of rows) {
    if (row.is_cold_start === true) coldRows.push(row);
    else if (row.is_cold_start === false) hotRows.push(row);
    else unknownCount += 1;
  }

  const cold = summarizeGroup("cold", coldRows);
  const hot = summarizeGroup("hot", hotRows);
  return {
    cold: cold.group,
    hot: hot.group,
    unknownCount,
    invalidTtftCount: cold.invalidTtftCount + hot.invalidTtftCount,
    invalidThroughputCount:
      cold.invalidThroughputCount + hot.invalidThroughputCount,
  };
}

function formatMilliseconds(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)} ms`;
}

function formatThroughput(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(2)} tokens/s`;
}

function formatDimension(value: string | null): string {
  return value ?? "Unknown";
}

function DistributionMetric({
  label,
  value,
  maxValue,
  formatter,
}: {
  label: string;
  value: number | null;
  maxValue: number;
  formatter: (value: number | null) => string;
}) {
  const width = value === null || maxValue <= 0 ? 0 : (value / maxValue) * 100;
  return (
    <div className="space-y-1" data-testid="latency-distribution-metric">
      <div className="flex items-center justify-between gap-2 text-xs">
        <dt className="text-muted-foreground">{label}</dt>
        <dd className="tabular-nums">{formatter(value)}</dd>
      </div>
      <div
        className="bg-muted h-1.5 overflow-hidden rounded"
        aria-hidden="true"
      >
        <div
          className="bg-primary h-full rounded"
          style={{ width: `${Math.max(0, Math.min(width, 100))}%` }}
        />
      </div>
    </div>
  );
}

function GroupSummary({
  group,
  maxP99,
  headingId,
}: {
  group: LatencyDistributionGroup;
  maxP99: number;
  headingId?: string;
}) {
  const id = headingId ?? `latency-distribution-${group.key}`;
  return (
    <section
      className="rounded-md border p-4"
      data-testid="latency-distribution-group"
      data-group={group.key}
      aria-labelledby={id}
    >
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h3 id={id} className="font-medium">
          {group.label}
        </h3>
        <span
          className="text-muted-foreground text-sm"
          data-testid="latency-distribution-count"
        >
          Count: {group.count}
        </span>
      </div>
      <dl className="space-y-3">
        <DistributionMetric
          label="P50 TTFT"
          value={group.p50}
          maxValue={maxP99}
          formatter={formatMilliseconds}
        />
        <DistributionMetric
          label="P95 TTFT"
          value={group.p95}
          maxValue={maxP99}
          formatter={formatMilliseconds}
        />
        <DistributionMetric
          label="P99 TTFT"
          value={group.p99}
          maxValue={maxP99}
          formatter={formatMilliseconds}
        />
        <div
          className="flex items-center justify-between gap-2 text-xs"
          data-testid="latency-distribution-throughput"
        >
          <dt className="text-muted-foreground">Average throughput</dt>
          <dd className="tabular-nums">
            {formatThroughput(group.averageTokensPerSecond)}
          </dd>
        </div>
      </dl>
      {group.count > 0 && group.p50 === null ? (
        <p
          className="text-muted-foreground mt-3 text-xs"
          data-testid="latency-distribution-missing-ttft"
        >
          TTFT data unavailable for this group.
        </p>
      ) : null}
      {group.count > 0 && group.averageTokensPerSecond === null ? (
        <p
          className="text-muted-foreground mt-1 text-xs"
          data-testid="latency-distribution-missing-throughput"
        >
          Throughput data unavailable for this group.
        </p>
      ) : null}
    </section>
  );
}

function AggregateGroupSummary({
  group,
  maxP99,
  maxLoadP99,
  index,
}: {
  group: LatencyDistributionAggregateGroup;
  maxP99: number;
  maxLoadP99: number;
  index: number;
}) {
  return (
    <section
      className="rounded-md border p-4"
      data-testid="latency-distribution-group"
      data-aggregate-group="true"
      data-group={group.key}
      data-model={group.model ?? "unknown"}
      data-route={group.route ?? "unknown"}
      data-chain-type={group.chainType ?? "unknown"}
      aria-labelledby={`latency-distribution-aggregate-${index}`}
    >
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <div>
          <h3
            id={`latency-distribution-aggregate-${index}`}
            className="font-medium"
          >
            {group.label}
          </h3>
          <p
            className="text-muted-foreground text-xs"
            data-testid="latency-distribution-dimensions"
          >
            Model: {formatDimension(group.model)} · Route:{" "}
            {formatDimension(group.route)} · Chain type:{" "}
            {formatDimension(group.chainType)}
          </p>
        </div>
        <span
          className="text-muted-foreground text-sm"
          data-testid="latency-distribution-count"
        >
          Count: {group.count}
        </span>
      </div>
      <dl className="space-y-3">
        <DistributionMetric
          label="P50 TTFT"
          value={group.p50}
          maxValue={maxP99}
          formatter={formatMilliseconds}
        />
        <DistributionMetric
          label="P95 TTFT"
          value={group.p95}
          maxValue={maxP99}
          formatter={formatMilliseconds}
        />
        <DistributionMetric
          label="P99 TTFT"
          value={group.p99}
          maxValue={maxP99}
          formatter={formatMilliseconds}
        />
        <DistributionMetric
          label="P50 Load"
          value={group.loadP50}
          maxValue={maxLoadP99}
          formatter={formatMilliseconds}
        />
        <DistributionMetric
          label="P95 Load"
          value={group.loadP95}
          maxValue={maxLoadP99}
          formatter={formatMilliseconds}
        />
        <DistributionMetric
          label="P99 Load"
          value={group.loadP99}
          maxValue={maxLoadP99}
          formatter={formatMilliseconds}
        />
        <div
          className="flex items-center justify-between gap-2 text-xs"
          data-testid="latency-distribution-throughput"
        >
          <dt className="text-muted-foreground">Average throughput</dt>
          <dd className="tabular-nums">
            {formatThroughput(group.averageTokensPerSecond)}
          </dd>
        </div>
      </dl>
      {group.count > 0 && group.p50 === null ? (
        <p
          className="text-muted-foreground mt-3 text-xs"
          data-testid="latency-distribution-missing-ttft"
        >
          TTFT data unavailable for this group.
        </p>
      ) : null}
      {group.count > 0 && group.loadP50 === null ? (
        <p
          className="text-muted-foreground mt-1 text-xs"
          data-testid="latency-distribution-missing-load"
        >
          Load data unavailable for this group.
        </p>
      ) : null}
      {group.count > 0 && group.averageTokensPerSecond === null ? (
        <p
          className="text-muted-foreground mt-1 text-xs"
          data-testid="latency-distribution-missing-throughput"
        >
          Throughput data unavailable for this group.
        </p>
      ) : null}
    </section>
  );
}

export function LatencyDistribution({
  rows,
  aggregates,
  className,
  ariaLabel = "Ollama latency distribution",
}: LatencyDistributionProps) {
  const summary = summarizeLatencyDistribution(rows);
  const aggregateMode = aggregates !== undefined;
  const aggregateGroups = aggregateMode
    ? summarizeLatencyAggregates(aggregates)
    : [];
  const groups = aggregateMode ? aggregateGroups : [summary.cold, summary.hot];
  const maxP99 = Math.max(...groups.map((group) => group.p99 ?? 0), 0);
  const maxLoadP99 = Math.max(
    ...aggregateGroups.map((group) => group.loadP99 ?? 0),
    0,
  );
  const classNames = className ? `space-y-3 ${className}` : "space-y-3";

  return (
    <div
      className={classNames}
      data-testid="latency-distribution"
      role="group"
      aria-label={ariaLabel}
    >
      {aggregateMode ? (
        <div className="grid gap-3 md:grid-cols-2">
          {aggregateGroups.map((group, index) => (
            <AggregateGroupSummary
              key={`${group.model ?? "unknown"}-${group.route ?? "unknown"}-${group.chainType ?? "unknown"}-${group.key}-${index}`}
              group={group}
              maxP99={maxP99}
              maxLoadP99={maxLoadP99}
              index={index}
            />
          ))}
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          <GroupSummary group={summary.cold} maxP99={maxP99} />
          <GroupSummary group={summary.hot} maxP99={maxP99} />
        </div>
      )}
      {aggregateMode && aggregates.length === 0 ? (
        <p
          className="text-muted-foreground rounded-md border p-4 text-sm"
          data-testid="latency-distribution-empty"
          role="status"
        >
          No latency distribution aggregates available.
        </p>
      ) : null}
      {!aggregateMode && rows.length === 0 ? (
        <p
          className="text-muted-foreground rounded-md border p-4 text-sm"
          data-testid="latency-distribution-empty"
          role="status"
        >
          No latency distribution data available.
        </p>
      ) : null}
      {aggregateMode &&
      aggregateGroups.some((group) => group.key === "unknown") ? (
        <p
          className="text-muted-foreground text-xs"
          data-testid="latency-distribution-missing-group"
          role="status"
        >
          One or more aggregate groups have no cold/hot classification.
        </p>
      ) : null}
      {!aggregateMode && summary.unknownCount > 0 ? (
        <p
          className="text-muted-foreground text-xs"
          data-testid="latency-distribution-missing-group"
          role="status"
        >
          {summary.unknownCount} row{summary.unknownCount === 1 ? "" : "s"}{" "}
          omitted because cold/hot classification is unavailable.
        </p>
      ) : null}
      {aggregateMode &&
      aggregateGroups.some((group) => group.invalidMetricCount > 0) ? (
        <p
          className="text-muted-foreground text-xs"
          data-testid="latency-distribution-invalid"
          role="status"
        >
          Invalid negative or non-finite aggregate metric values were excluded
          from the summary.
        </p>
      ) : null}
      {!aggregateMode &&
      (summary.invalidTtftCount > 0 || summary.invalidThroughputCount > 0) ? (
        <p
          className="text-muted-foreground text-xs"
          data-testid="latency-distribution-invalid"
          role="status"
        >
          Invalid negative or non-finite metric values were excluded from the
          summary.
        </p>
      ) : null}
    </div>
  );
}
