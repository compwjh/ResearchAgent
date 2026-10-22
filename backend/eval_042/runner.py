"""Canonical offline evaluation runner for spec-042.

This module is deliberately independent of the historical ``docs/sdd`` script.
It owns input validation, skip semantics, judge orchestration, one-shot score
writes, bounded exact verification, and report checkpoints.  Report payloads
never contain trace input/output, prior context, prompts, raw model output, or
hidden reasoning.
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from . import judge_client, langfuse_export
from .config import FALLBACK_JUDGE, PRIMARY_JUDGE, REPEATS
from .report import ReportWriter

KNOWN_TASKS = frozenset(("chat_quality", "memory_correctness"))
_VALID_INPUT_STATUSES = frozenset(("scored", "skipped"))
_VERIFY_ATTEMPTS = 3
_VERIFY_BACKOFF_SECONDS = (0.05, 0.1)
_URL_USERINFO_RE = re.compile(r"(?P<prefix>https?://)(?P<userinfo>[^/\s@]+)@", re.IGNORECASE)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?P<key>authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"password|secret|credential)(?P<separator>\s*[:=]\s*)(?P<value>[^\s,;]+)",
    re.IGNORECASE,
)
_SOURCE_LABEL_RE = (
    r"(?:question|answer|q|a|ctx|context|prior[\s_-]*context|q\s*/\s*a)"
)
_EXPLANATION_SOURCE_MARKER_RE = re.compile(
    rf"(?ix)\b{_SOURCE_LABEL_RE}\s*(?:[:=：]|[-_–—])\s*\S"
)
_EXPLANATION_SOURCE_WHITESPACE_RE = re.compile(
    rf"(?ix)\b(?:question|answer|q|a|ctx|context|prior[\s_-]*context)\s+(?P<first>\S+)"
)
_SENSITIVE_SOURCE_TOKEN_RE = re.compile(
    r"\b(?:source|private)[_-](?:question|answer|context|prior[_-]?context|ctx|q|a)\b",
    re.IGNORECASE,
)
_SOURCE_ECHO_REASON = "reason_code=judge_explanation_source_echo_redacted"


def _compact_text(value: object) -> str:
    """Normalize spacing, case, and separators for source-echo detection."""
    return re.sub(r"[\W_]+", "", str(value).casefold(), flags=re.UNICODE)


def _has_source_marker(text: str) -> bool:
    if _EXPLANATION_SOURCE_MARKER_RE.search(text):
        return True
    whitespace_marker = _EXPLANATION_SOURCE_WHITESPACE_RE.search(text)
    if not whitespace_marker:
        return False
    # Keep ordinary short rationale such as ``Answer is relevant`` useful;
    # a whitespace-separated marker followed by a payload remains redacted.
    return whitespace_marker.group("first").casefold() not in {
        "is",
        "was",
        "seems",
        "appears",
        "should",
        "must",
        "can",
        "cannot",
        "looks",
        "remains",
    }


def _safe_error_text(
    value: object,
    *,
    question: object = None,
    answer: object = None,
    context: object = None,
    limit: int = 400,
) -> str:
    """Keep useful error text without persisting item source payloads."""
    text = str(value)
    text = _URL_USERINFO_RE.sub(r"\g<prefix><redacted>@", text)
    text = _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group('key')}{match.group('separator')}<redacted>",
        text,
    )
    text = _SENSITIVE_SOURCE_TOKEN_RE.sub("<redacted>", text)
    if _has_source_marker(text):
        return _SOURCE_ECHO_REASON
    folded_text = _compact_text(text)
    for source in (question, answer, context):
        if not isinstance(source, str):
            continue
        folded_source = _compact_text(source)
        if len(folded_source) >= 4 and folded_source in folded_text:
            return _SOURCE_ECHO_REASON
    if len(text) > limit:
        return f"{text[:limit]}…"
    return text


def _error_record(
    exc: object,
    *,
    stage: str | None = None,
    question: object = None,
    answer: object = None,
    context: object = None,
) -> dict[str, str]:
    record = {
        "type": type(exc).__name__,
        "message": _safe_error_text(
            exc,
            question=question,
            answer=answer,
            context=context,
        ),
    }
    if stage:
        record["stage"] = stage
    return record


def _safe_explanation(
    value: object,
    *,
    question: object = None,
    answer: object = None,
    context: object = None,
    limit: int = 600,
) -> str:
    """Retain a short rationale without allowing source-payload echoes."""
    if not isinstance(value, str):
        return ""
    text = _safe_error_text(" ".join(value.split()), limit=limit)
    if _has_source_marker(text):
        return _SOURCE_ECHO_REASON
    folded_text = _compact_text(text)
    for source in (question, answer, context):
        if not isinstance(source, str):
            continue
        folded_source = _compact_text(source)
        # Very short q/a values are covered by the explicit field-marker
        # checks above; substring matching them would reject ordinary prose.
        if len(folded_source) >= 4 and folded_source in folded_text:
            return _SOURCE_ECHO_REASON
    return text[:limit]


def _has_prior_context(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _as_item_mapping(item: object, index: int) -> dict[str, Any]:
    if isinstance(item, Mapping):
        return dict(item)
    if is_dataclass(item) and not isinstance(item, type):
        converted = asdict(item)
        if isinstance(converted, dict):
            return converted
    raise ValueError(f"dataset item {index} must be an object")


def _validate_items(raw_items: object, task: str | None) -> list[dict[str, Any]]:
    if isinstance(raw_items, (str, bytes, bytearray)) or not isinstance(raw_items, Sequence):
        raise ValueError("dataset must be a JSON array of item objects")

    normalized: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw_items):
        item = _as_item_mapping(raw_item, index)
        required = ("trace_id", "task", "input", "output", "status", "synthetic")
        missing = [key for key in required if key not in item]
        if missing:
            raise ValueError(f"dataset item {index} missing required fields: {','.join(missing)}")

        trace_id = item["trace_id"]
        if not isinstance(trace_id, str) or not trace_id.strip():
            raise ValueError(f"dataset item {index} trace_id must be a non-empty string")
        item_task = item["task"]
        if item_task not in KNOWN_TASKS:
            raise ValueError(f"dataset item {index} has unknown task: {item_task!r}")
        if task is not None and item_task != task:
            raise ValueError(
                f"dataset item {index} task {item_task!r} does not match requested task {task!r}"
            )
        if not isinstance(item["synthetic"], bool):
            raise ValueError(f"dataset item {index} synthetic must be boolean")
        if not isinstance(item["input"], str):
            raise ValueError(f"dataset item {index} input must be a string")
        if item["output"] is not None and not isinstance(item["output"], str):
            raise ValueError(f"dataset item {index} output must be a string or null")
        prior_context = item.get("prior_context")
        if prior_context is not None and not isinstance(prior_context, str):
            raise ValueError(f"dataset item {index} prior_context must be a string or null")
        status = item["status"]
        if not isinstance(status, str) or status.lower() not in _VALID_INPUT_STATUSES:
            raise ValueError(f"dataset item {index} has invalid status: {status!r}")
        item["status"] = status.lower()
        normalized.append(item)

    if not any(not item["synthetic"] for item in normalized):
        raise langfuse_export.EmptyTraceExportError(
            "dataset contains no real trace items; synthetic-only evaluation is refused"
        )
    return normalized


def _load_source(
    dataset_path: str | Path | None,
    items: Sequence[object] | None,
    export: Callable[[], object] | Sequence[object] | None,
) -> object:
    sources = sum(value is not None for value in (dataset_path, items, export))
    if sources != 1:
        raise ValueError("provide exactly one of dataset_path, items, or export")
    if items is not None:
        return items
    if export is not None:
        return export() if callable(export) else export
    with Path(dataset_path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _summary(items: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    summary = {
        "scored": 0,
        "skipped": 0,
        "unavailable": 0,
        "written": 0,
        "verified": 0,
        "failed": 0,
        "no_prior_context": 0,
    }
    for item in items:
        status = item.get("status")
        if status in summary:
            summary[status] += 1
        if item.get("written") is True:
            summary["written"] += 1
        if item.get("verified") is True:
            summary["verified"] += 1
        if item.get("skip_reason") == "no_prior_context":
            summary["no_prior_context"] += 1
    return summary


def _append_item(
    writer: ReportWriter,
    item: dict[str, Any],
    *,
    index: int | None = None,
) -> dict[str, Any]:
    document = dict(writer.document)
    items = [*document.get("items", [])]
    if index is not None and 0 <= index < len(items):
        items[index] = item
    else:
        items.append(item)
    document["items"] = items
    document["summary"] = _summary(document["items"])
    return writer.checkpoint(document)


def _skip_record(item: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "trace_id": item["trace_id"],
        "task": item["task"],
        "status": "skipped",
        "skip_reason": reason,
        "synthetic": item["synthetic"],
    }


def _judge_unavailable_record(
    item: Mapping[str, Any],
    model: str,
    calls: object,
    *,
    error: object | None = None,
) -> dict[str, Any]:
    question = item.get("input")
    answer = item.get("output") or ""
    context = item.get("prior_context")
    errors: list[dict[str, str]] = []
    if error is not None:
        errors.append(
            _error_record(
                error,
                stage="judge",
                question=question,
                answer=answer,
                context=context,
            )
        )
    if isinstance(calls, Sequence) and not isinstance(calls, (str, bytes, bytearray)):
        for call in calls:
            if isinstance(call, Mapping) and call.get("status") != "scored":
                if call.get("error"):
                    errors.append(
                        _error_record(
                            call["error"],
                            stage="judge",
                            question=question,
                            answer=answer,
                            context=context,
                        )
                    )
    return {
        "trace_id": item["trace_id"],
        "task": item["task"],
        "status": "unavailable",
        "synthetic": item["synthetic"],
        "judge_model": model,
        "score": None,
        "requested": False,
        "expected_value": None,
        "verified": False,
        "verified_value": None,
        "post_status": "not_requested",
        "verification_status": "not_requested",
        "written": False,
        "errors": errors or [{"type": "JudgeUnavailable", "message": "judge call unavailable"}],
    }


def _values_match(expected: float, actual: object) -> bool:
    return isinstance(actual, (int, float)) and not isinstance(actual, bool) and float(actual) == float(expected)


def _safe_verified_value(value: object) -> object:
    """Persist only the numeric score value returned by the service."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _verify_score_details(
    score_id: str,
    trace_id: str,
    name: str,
    expected_value: float,
    *,
    question: object = None,
    answer: object = None,
    context: object = None,
) -> tuple[bool, dict[str, str] | None, object, str]:
    last_error: dict[str, str] | None = None
    actual_value: object = None
    verification_status = "not_found"
    for attempt in range(_VERIFY_ATTEMPTS):
        try:
            score = langfuse_export.find_score_by_id(score_id, trace_id, limit=100)
            if score is None:
                verification_status = "not_found"
                last_error = {
                    "type": "ScoreVerificationError",
                    "message": "score id not found on trace",
                }
            else:
                actual_value = score.get("value")
                mismatches: list[str] = []
                if score.get("id") != score_id:
                    mismatches.append("id")
                if score.get("traceId") != trace_id:
                    mismatches.append("traceId")
                if score.get("name") != name:
                    mismatches.append("name")
                if not _values_match(expected_value, score.get("value")):
                    mismatches.append("value")
                if not mismatches:
                    return True, None, actual_value, "verified"
                verification_status = "mismatch"
                last_error = {
                    "type": "ScoreVerificationError",
                    "message": f"score field mismatch: {','.join(mismatches)}",
                }
        except Exception as exc:
            verification_status = "error"
            last_error = _error_record(
                exc,
                stage="score_verify",
                question=question,
                answer=answer,
                context=context,
            )
        if attempt + 1 < _VERIFY_ATTEMPTS:
            time.sleep(_VERIFY_BACKOFF_SECONDS[min(attempt, len(_VERIFY_BACKOFF_SECONDS) - 1)])
    return (
        False,
        last_error
        or {
            "type": "ScoreVerificationError",
            "message": "score verification failed",
        },
        actual_value,
        verification_status,
    )


def _verify_score(
    score_id: str,
    trace_id: str,
    name: str,
    expected_value: float,
) -> tuple[bool, dict[str, str] | None]:
    """Backward-compatible two-value verification helper."""
    verified, error, _actual_value, _status = _verify_score_details(
        score_id,
        trace_id,
        name,
        expected_value,
    )
    return verified, error


def _score_item(
    item: Mapping[str, Any],
    *,
    primary: str,
    repeats: int,
    checkpoint: Callable[[dict[str, Any]], object] | None = None,
) -> dict[str, Any]:
    question = item["input"]
    answer = item["output"] or ""
    context = item.get("prior_context")
    try:
        calls = judge_client.judge_repeats(
            primary,
            item["task"],
            question,
            answer,
            repeats,
            ctx=context,
        )
    except Exception as exc:
        return _judge_unavailable_record(item, primary, [], error=exc)

    if not isinstance(calls, list) or len(calls) != repeats:
        return _judge_unavailable_record(
            item,
            primary,
            calls,
            error=ValueError("judge_repeats returned an unexpected result shape"),
        )
    if any(
        not isinstance(call, Mapping)
        or call.get("status") != "scored"
        or not isinstance(call.get("label"), str)
        or not isinstance(call.get("score"), (int, float))
        or isinstance(call.get("score"), bool)
        or not 0.0 <= float(call["score"]) <= 1.0
        for call in calls
    ):
        return _judge_unavailable_record(item, primary, calls)

    labels = [call["label"] for call in calls]
    label = Counter(labels).most_common(1)[0][0]
    score = judge_client.enum_to_score(item["task"], label)
    if score is None or not 0.0 <= float(score) <= 1.0:
        return _judge_unavailable_record(
            item,
            primary,
            calls,
            error=ValueError("judge label has no valid score mapping"),
        )
    explanation = _safe_explanation(
        next(
            (call.get("explanation") for call in calls if call.get("label") == label),
            "",
        ),
        question=question,
        answer=answer,
        context=context,
    )
    record: dict[str, Any] = {
        "trace_id": item["trace_id"],
        "task": item["task"],
        "status": "scored",
        "synthetic": item["synthetic"],
        "judge_model": primary,
        "label": label,
        "score": float(score),
        "explanation": explanation,
        "requested": False,
        "expected_value": float(score),
        "written": False,
        "post_status": "not_requested",
        "verified": False,
        "verified_value": None,
        "verification_status": "not_started",
    }
    record["requested"] = True
    record["post_status"] = "requested"
    if checkpoint is not None:
        checkpoint(record)
    try:
        posted = langfuse_export.post_score(
            name=item["task"],
            value=float(score),
            trace_id=item["trace_id"],
            comment=f"Explanation: {explanation}; Label: {label}",
        )
        score_id = posted.get("id") if isinstance(posted, Mapping) else None
        if not isinstance(score_id, str) or not score_id.strip():
            raise langfuse_export.ScoreResponseError("score response id is missing")
        record["score_id"] = score_id
        record["written"] = True
        record["post_status"] = "written"
    except Exception as exc:
        record["status"] = "failed"
        record["post_status"] = "failed"
        record["errors"] = [
            _error_record(
                exc,
                stage="score_write",
                question=question,
                answer=answer,
                context=context,
            )
        ]
        return record

    record["verification_status"] = "pending"
    verified, verification_error, verified_value, verification_status = _verify_score_details(
        record["score_id"],
        item["trace_id"],
        item["task"],
        float(score),
        question=question,
        answer=answer,
        context=context,
    )
    record["verified"] = verified
    record["verified_value"] = _safe_verified_value(verified_value)
    record["verification_status"] = verification_status
    if not verified:
        record["status"] = "failed"
        record["errors"] = [verification_error or {
            "type": "ScoreVerificationError",
            "message": "score verification failed",
        }]
    return record


def _result(writer: ReportWriter, document: Mapping[str, Any]) -> dict[str, Any]:
    status = str(document.get("status", "failed"))
    exit_code = 0 if status == "completed" else 1
    json_path = getattr(writer, "json_path", None)
    markdown_path = getattr(writer, "markdown_path", None)
    paths = {
        "json": str(json_path) if json_path is not None else None,
        "markdown": str(markdown_path) if markdown_path is not None else None,
    }
    return {
        "exit_code": exit_code,
        "status": status,
        "report_json": paths["json"],
        "report_markdown": paths["markdown"],
        "report_paths": paths,
        "summary": document.get("summary", {}),
        "errors": document.get("errors", []),
        "document": document,
    }


def _failed_document(
    document: Mapping[str, Any] | object,
    errors: Sequence[object],
) -> dict[str, Any]:
    """Build a failed in-memory result when a terminal checkpoint cannot write."""
    base = dict(document) if isinstance(document, Mapping) else {}
    previous = base.get("errors")
    previous_errors = list(previous) if isinstance(previous, list) else []
    base["errors"] = [*previous_errors, *errors]
    base["status"] = "failed"
    return base


def _finish_failed(
    writer: ReportWriter,
    errors: Sequence[object],
) -> dict[str, Any]:
    """Attempt one failed terminal checkpoint, but never let it escape.

    If the filesystem remains unavailable, return the last successful document
    as an in-memory failed result with the report paths still exposed.  Those
    paths are not presented as a complete artifact; the caller receives a
    non-zero status and the write error instead.
    """
    try:
        return writer.finish("failed", errors=errors)
    except Exception as finish_error:
        return _failed_document(
            getattr(writer, "document", {}),
            [*errors, _error_record(finish_error, stage="report_finish")],
        )


def run(
    dataset_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    task: str | None = None,
    primary: str = PRIMARY_JUDGE,
    fallback: str | None = FALLBACK_JUDGE,
    repeats: int = REPEATS,
    max_items: int | None = None,
    *,
    items: Sequence[object] | None = None,
    export: Callable[[], object] | Sequence[object] | None = None,
) -> dict[str, Any]:
    """Run an offline evaluation and return status plus report paths.

    Exactly one input source is required: ``dataset_path``, ``items`` or
    ``export``.  ``export`` may be a zero-argument callable, allowing the CLI
    to connect the existing Langfuse exporter without importing the historical
    docs script.
    """
    if dataset_path is not None and not isinstance(dataset_path, (str, Path)):
        if items is None and export is None:
            items = dataset_path  # type: ignore[assignment]
            dataset_path = None
        else:
            raise ValueError("dataset_path must be a local path")

    source_name = "items" if items is not None else "export" if export is not None else "dataset"
    metadata = {
        "task": task or "mixed",
        "judge_model": primary,
        "fallback_judge": fallback,
        "repeats": repeats,
        "max_items": max_items,
        "source": source_name,
    }
    writer = ReportWriter(output_dir, metadata=metadata)
    document = writer.document
    overall_failed = False
    active_sources: tuple[object, object, object] = (None, None, None)
    try:
        if task is not None and task not in KNOWN_TASKS:
            raise ValueError(f"unknown task: {task!r}")
        if not isinstance(repeats, int) or isinstance(repeats, bool) or repeats < 1:
            raise ValueError("repeats must be a positive integer")
        if max_items is not None and (
            not isinstance(max_items, int) or isinstance(max_items, bool) or max_items < 1
        ):
            raise ValueError("max_items must be a positive integer when provided")

        raw_items = _load_source(dataset_path, items, export)
        normalized = _validate_items(raw_items, task)
        selected = normalized[:max_items] if max_items is not None else normalized
        if not any(not item["synthetic"] for item in selected):
            raise langfuse_export.EmptyTraceExportError(
                "selected dataset contains no real trace items; synthetic-only evaluation is refused"
            )

        for item in selected:
            active_sources = (
                item.get("input"),
                item.get("output") or "",
                item.get("prior_context"),
            )
            report_index = len(writer.document.get("items", []))
            item_task = item["task"]
            prior_context = item.get("prior_context")
            if item_task == "memory_correctness" and not _has_prior_context(
                prior_context
            ):
                record = _skip_record(item, "no_prior_context")
            else:
                skip_status, skip_reason = langfuse_export.classify_output(
                    item.get("output"),
                    task=item_task,
                    prior_context=prior_context,
                )
                if item["synthetic"]:
                    record = _skip_record(item, "synthetic_fixture")
                elif skip_status == "skipped":
                    record = _skip_record(item, skip_reason or "skipped")
                elif item["status"] == "skipped":
                    record = _skip_record(
                        item,
                        item.get("skip_reason") or "input_skipped",
                    )
                else:
                    record = _score_item(
                        item,
                        primary=primary,
                        repeats=repeats,
                        checkpoint=lambda pending: _append_item(
                            writer,
                            pending,
                            index=report_index,
                        ),
                    )
            if record["status"] in {"unavailable", "failed"}:
                overall_failed = True
                if record.get("errors"):
                    document = dict(writer.document)
                    document["errors"] = [
                        *document.get("errors", []),
                        {
                            "trace_id": record["trace_id"],
                            "errors": record["errors"],
                        },
                    ]
                    writer.checkpoint(document)
            document = _append_item(writer, record, index=report_index)

        if overall_failed:
            document = writer.finish("failed")
        else:
            document = writer.finish("completed")
        return _result(writer, document)
    except Exception as exc:
        error = _error_record(
            exc,
            stage="run",
            question=active_sources[0],
            answer=active_sources[1],
            context=active_sources[2],
        )
        document = _finish_failed(writer, [error])
        return _result(writer, document)


__all__ = ["KNOWN_TASKS", "run"]
