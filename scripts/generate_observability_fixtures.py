#!/usr/bin/env python3
"""Generate a reproducible Langfuse sample matrix for spec-013 Task 06.

The command is deliberately dry-run by default.  ``--send`` is the only mode
that imports the Langfuse SDK and sends observations.  Credentials are read
from the environment and are never included in the generated JSON summary.

Examples::

    .venv/bin/python scripts/generate_observability_fixtures.py
    LANGFUSE_PUBLIC_KEY=... LANGFUSE_SECRET_KEY=... \
      .venv/bin/python scripts/generate_observability_fixtures.py --send
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional


FIXTURE_VERSION = "v1"
DEFAULT_MODEL = "qwen3.8:27b-mlx"
SCORE_METRICS = (
    "ttft_ms",
    "load_ms",
    "prompt_eval_ms",
    "eval_ms",
    "overhead_ms",
    "tokens_per_sec",
    "is_cold_start",
)
REQUIRED_METADATA = ("fixture_id", "sample_id", "fixture_version", "route", "chain_type")


def utc_now() -> datetime:
    """Return an aware UTC timestamp for fixture creation."""

    return datetime.now(timezone.utc)


def _iso(timestamp: datetime) -> str:
    """Serialize an aware timestamp in UTC, with a stable millisecond format."""

    if timestamp.tzinfo is None:
        raise ValueError("fixture timestamps must be timezone-aware")
    return timestamp.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("fixture timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def timestamp_is_not_future(value: str, *, now: Optional[datetime] = None) -> bool:
    """Return whether a serialized fixture timestamp is no later than ``now``."""

    reference = (now or utc_now()).astimezone(timezone.utc)
    return _parse_timestamp(value) <= reference


@dataclass(frozen=True)
class FixtureSample:
    """Serializable description of one synthetic generation observation."""

    sample_id: str
    fixture_id: str
    fixture_version: str
    model: str
    route: str
    chain_type: str
    temperature: str
    input_size: str
    success: bool
    error_type: str
    event_ts: str
    completion_start_time: str
    input_chars: int
    output_chars: int
    thinking_chars: int
    ttft_ms: float
    load_ms: float
    prompt_eval_ms: float
    eval_ms: float
    overhead_ms: float
    tokens_per_sec: float
    is_cold_start: float
    prompt_tokens: int
    completion_tokens: int

    def metadata(self) -> Dict[str, Any]:
        """Return the metadata contract consumed by native dashboards."""

        return {
            "fixture_id": self.fixture_id,
            "sample_id": self.sample_id,
            "fixture_version": self.fixture_version,
            "route": self.route,
            "chain_type": self.chain_type,
            "temperature": self.temperature,
            "input_size": self.input_size,
            "success": self.success,
            "success_flag": 1 if self.success else 0,
            "error_type": self.error_type,
            "event_ts": self.event_ts,
            "input_chars": self.input_chars,
            "output_chars": self.output_chars,
            "thinking_chars": self.thinking_chars,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "ttft_ms": self.ttft_ms,
            "load_ms": self.load_ms,
            "prompt_eval_ms": self.prompt_eval_ms,
            "eval_ms": self.eval_ms,
            "overhead_ms": self.overhead_ms,
            "tokens_per_sec": self.tokens_per_sec,
            "is_cold_start": self.is_cold_start,
        }

    def summary(self) -> Dict[str, Any]:
        """Return a redacted item suitable for stdout and task evidence."""

        return {
            "sample_id": self.sample_id,
            "metadata": self.metadata(),
            "event_ts": self.event_ts,
            "completion_start_time": self.completion_start_time,
        }


def _sample(
    *,
    fixture_id: str,
    model: str,
    cold: bool,
    input_size: str,
    chain_type: str,
    success: bool,
    index: int,
    now: datetime,
) -> FixtureSample:
    # Keep event_ts and completion_start_time behind the current instant.  The
    # small index offset makes timestamps distinct while remaining reproducible.
    load_ms = 7000.0 if cold else 12.0
    prompt_eval_ms = 90.0 if input_size == "short" else 720.0
    eval_ms = 1000.0 if success else 200.0
    ttft_ms = load_ms + prompt_eval_ms + (120.0 if success else 70.0)
    total_ms = load_ms + prompt_eval_ms + eval_ms + 90.0
    event_time = now - timedelta(milliseconds=total_ms + index)
    completion_time = event_time + timedelta(milliseconds=ttft_ms)
    prompt_tokens = 24 if input_size == "short" else 512
    completion_tokens = 25 if success else 0
    output_chars = 96 if success else 0
    thinking_chars = 40 if success else 0
    input_chars = 320 if input_size == "short" else 6400
    return FixtureSample(
        sample_id=f"{ 'cold' if cold else 'hot' }-{input_size}-{chain_type}-"
        f"{ 'success' if success else 'failure' }-{index:02d}",
        fixture_id=fixture_id,
        fixture_version=FIXTURE_VERSION,
        model=model,
        route="direct",
        chain_type=chain_type,
        temperature="cold" if cold else "hot",
        input_size=input_size,
        success=success,
        error_type="fixture.synthetic_failure" if not success else "",
        event_ts=_iso(event_time),
        completion_start_time=_iso(completion_time),
        input_chars=input_chars,
        output_chars=output_chars,
        thinking_chars=thinking_chars,
        ttft_ms=ttft_ms,
        load_ms=load_ms,
        prompt_eval_ms=prompt_eval_ms,
        eval_ms=eval_ms,
        overhead_ms=90.0,
        tokens_per_sec=round(completion_tokens / (eval_ms / 1000.0), 3) if eval_ms else 0.0,
        is_cold_start=1.0 if cold else 0.0,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def build_fixture_plan(
    *,
    fixture_id: Optional[str] = None,
    model: Optional[str] = None,
    now: Optional[datetime] = None,
) -> List[FixtureSample]:
    """Build the fixed 20-sample matrix without network or SDK side effects.

    The eight successful cold/hot × short/long × chat/KB combinations are
    repeated twice.  Four balanced failure samples bring every primary
    dimension to ten samples and provide separate error-rate observations.
    """

    current = (now or utc_now()).astimezone(timezone.utc)
    run_id = fixture_id or f"spec013-task06-{current.strftime('%Y%m%dT%H%M%SZ')}"
    selected_model = model or os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
    samples: List[FixtureSample] = []
    index = 1
    for repeat in range(1, 3):
        for cold in (True, False):
            for input_size in ("short", "long"):
                for chain_type in ("chat", "kb"):
                    samples.append(
                        _sample(
                            fixture_id=run_id,
                            model=selected_model,
                            cold=cold,
                            input_size=input_size,
                            chain_type=chain_type,
                            success=True,
                            index=index + repeat,
                            now=current,
                        )
                    )
                    index += 1

    failures = ((True, "short", "chat"), (False, "long", "chat"), (True, "long", "kb"), (False, "short", "kb"))
    for cold, input_size, chain_type in failures:
        samples.append(
            _sample(
                fixture_id=run_id,
                model=selected_model,
                cold=cold,
                input_size=input_size,
                chain_type=chain_type,
                success=False,
                index=index,
                now=current,
            )
        )
        index += 1
    return samples


def _validate_plan(samples: Iterable[FixtureSample], *, now: Optional[datetime] = None) -> None:
    sample_list = list(samples)
    if len(sample_list) != 20:
        raise ValueError(f"fixture matrix must contain 20 samples, got {len(sample_list)}")
    ids = [sample.sample_id for sample in sample_list]
    if len(ids) != len(set(ids)):
        raise ValueError("fixture sample_id values must be unique")
    reference = (now or utc_now()).astimezone(timezone.utc)
    for sample in sample_list:
        metadata = sample.metadata()
        missing = [key for key in REQUIRED_METADATA if not metadata.get(key)]
        if missing:
            raise ValueError(f"{sample.sample_id} missing metadata: {missing}")
        for timestamp in (sample.event_ts, sample.completion_start_time):
            if not timestamp_is_not_future(timestamp, now=reference):
                raise ValueError(f"future fixture timestamp in {sample.sample_id}: {timestamp}")


def _summary(samples: List[FixtureSample], *, mode: str, generated_at: str) -> Dict[str, Any]:
    return {
        "fixture_id": samples[0].fixture_id if samples else "",
        "fixture_version": FIXTURE_VERSION,
        "mode": mode,
        "generated_at": generated_at,
        "sample_count": len(samples),
        "success_count": sum(sample.success for sample in samples),
        "failure_count": sum(not sample.success for sample in samples),
        "samples": [sample.summary() for sample in samples],
    }


def send_fixture(samples: List[FixtureSample], *, host: str, public_key: str, secret_key: str) -> Dict[str, Any]:
    """Send samples with Langfuse SDK and return a redacted result summary."""

    if not public_key or not secret_key:
        raise ValueError("--send requires LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY")
    try:
        from langfuse import Langfuse
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError("langfuse SDK is not installed in the active environment") from exc

    client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
    sent = 0
    for sample in samples:
        metadata = sample.metadata()
        with client.start_as_current_observation(
            as_type="generation",
            name="spec013-task06-fixture",
            model=sample.model,
            input=f"fixture {sample.sample_id}: {sample.input_size} {sample.chain_type}",
            metadata=metadata,
            completion_start_time=_parse_timestamp(sample.completion_start_time),
            usage_details={"input": sample.prompt_tokens, "output": sample.completion_tokens},
        ) as generation:
            generation.update(
                output="synthetic fixture failure" if not sample.success else "synthetic fixture output"
            )
            for metric_name in SCORE_METRICS:
                generation.score(
                    name=metric_name,
                    value=float(getattr(sample, metric_name)),
                    data_type="NUMERIC",
                )
        sent += 1
    client.flush()
    return {"sent_count": sent, "fixture_id": samples[0].fixture_id if samples else ""}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="生成 spec-013 Task 06 固定 Langfuse 样本矩阵")
    parser.add_argument("--send", action="store_true", help="通过 Langfuse SDK 发送；默认仅 dry-run")
    parser.add_argument("--fixture-id", default=None, help="可选的不可变 fixture_id")
    args = parser.parse_args(argv)

    generated_at = _iso(utc_now())
    samples = build_fixture_plan(fixture_id=args.fixture_id)
    _validate_plan(samples)
    result = _summary(samples, mode="send" if args.send else "dry-run", generated_at=generated_at)
    if args.send:
        result["send"] = send_fixture(
            samples,
            host=os.getenv("LANGFUSE_HOST", "http://127.0.0.1:3000"),
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
