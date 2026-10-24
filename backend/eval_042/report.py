"""Local JSON/Markdown reports for the spec-042 evaluation runner.

The report is deliberately a local filesystem artifact.  It never stores trace
payloads, prompts, completions, hidden reasoning, or credentials.  A runner
can checkpoint the same document after initialization and after each item;
both projections are written from that one sanitized document.  Each file is
published atomically on its own; the pair uses bounded rollback rather than
claiming a cross-file filesystem transaction.
"""
from __future__ import annotations

import html
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_SCHEMA_VERSION = "agent-evaluation-report-v1"
REPORT_JSON_NAME = "report.json"
REPORT_MARKDOWN_NAME = "report.md"

_SUMMARY_KEYS = (
    "scored",
    "skipped",
    "unavailable",
    "written",
    "verified",
    "failed",
    "no_prior_context",
)
_MAX_TEXT_CHARS = 600

# Do not persist payload-bearing fields in a reusable report.  These names are
# normalized before matching so both ``prior_context`` and ``priorContext``
# are covered.
_PRIVATE_FIELDS = {
    "a",
    "answer",
    "completion",
    "comment",
    "content",
    "ctx",
    "headers",
    "hiddenreasoning",
    "httpheaders",
    "input",
    "messages",
    "output",
    "priorcontext",
    "prompt",
    "question",
    "raw",
    "rawoutput",
    "rawresponse",
    "reference",
    "reasoning",
    "reasoningcontent",
    "q",
    "requestheaders",
    "responseheaders",
    "trajectory",
    "analysis",
    "thought",
    "key",
}
_SECRET_KEYS = {
    "apikey",
    "auth",
    "authorization",
    "credential",
    "langfusepk",
    "langfusesk",
    "password",
    "pk",
    "privatekey",
    "proxyurl",
    "publickey",
    "secret",
    "sk",
    "token",
}
_SECRET_MARKERS = (
    "accesskey",
    "accesstoken",
    "apikey",
    "authorization",
    "credential",
    "password",
    "privatekey",
    "proxyurl",
    "refreshtoken",
    "secret",
)
_REPORT_ATTESTATION_FIELDS = {
    "humanagreerate",
    "humanagreateratenote",
    "humanagreement",
    "humanannotation",
    "humanannotationstatus",
    "humannotated",
    "constructedgold",
    "constructedgoldonly",
    "constructedgoldnote",
    "gold",
    "goldonly",
    "goldnote",
}
_URL_USERINFO_RE = re.compile(
    r"(?P<prefix>[a-z][a-z0-9+.-]*://)(?P<userinfo>[^/\s@]+)@",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?P<key>authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"password|secret|credential)(?P<separator>\s*[:=]\s*)(?P<value>[^\s,;]+)",
    re.IGNORECASE,
)
_SENSITIVE_HEADER_RE = re.compile(
    r"(?P<key>authorization|proxy-authorization|cookie|set-cookie|"
    r"x-api-key|api-key|access-token|refresh-token)(?P<separator>\s*:\s*)"
    r"(?P<value>[^\r\n]*)",
    re.IGNORECASE,
)


class ReportWriteError(RuntimeError):
    """Raised when a local report cannot be written successfully."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized_key(key: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _is_private_key(key: object) -> bool:
    normalized = _normalized_key(key)
    return (
        normalized in _PRIVATE_FIELDS
        or normalized in _SECRET_KEYS
        or normalized in _REPORT_ATTESTATION_FIELDS
        or any(marker in normalized for marker in _SECRET_MARKERS)
    )


def _safe_text(value: object, *, limit: int = _MAX_TEXT_CHARS) -> str:
    """Make short, non-credential-bearing text suitable for report storage."""
    text = str(value)
    text = _URL_USERINFO_RE.sub(r"\g<prefix><redacted>@", text)
    text = _SENSITIVE_HEADER_RE.sub(
        lambda match: (
            f"{match.group('key')}{match.group('separator')}<redacted>"
        ),
        text,
    )
    text = _SECRET_ASSIGNMENT_RE.sub(
        lambda match: (
            f"{match.group('key')}{match.group('separator')}<redacted>"
        ),
        text,
    )
    if len(text) > limit:
        return f"{text[:limit]}…"
    return text


def _sanitize_value(value: object) -> Any:
    """Recursively retain only report-safe JSON-compatible values."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for key, child in value.items():
            if _is_private_key(key):
                continue
            safe[str(key)] = _sanitize_value(child)
        return safe
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_sanitize_value(child) for child in value]
    return _safe_text(value)


def _summary_defaults() -> dict[str, int]:
    return {key: 0 for key in _SUMMARY_KEYS}


def _sanitize_document(document: Mapping[str, object]) -> dict[str, Any]:
    if not isinstance(document, Mapping):
        raise TypeError("report document must be a mapping")

    safe = _sanitize_value(document)
    if not isinstance(safe, dict):  # defensive; _sanitize_value preserves mappings
        raise TypeError("report document must serialize to an object")

    safe["schema_version"] = REPORT_SCHEMA_VERSION
    safe.setdefault("status", "running")
    safe.setdefault("started_at", _utc_now())
    safe.setdefault("finished_at", None)
    safe.setdefault("items", [])
    safe.setdefault("errors", [])
    safe.setdefault("summary", {})
    if not isinstance(safe["summary"], dict):
        safe["summary"] = {}
    defaults = _summary_defaults()
    defaults.update(
        {
            str(key): value
            for key, value in safe["summary"].items()
            if str(key) not in _PRIVATE_FIELDS
        }
    )
    safe["summary"] = defaults
    if not isinstance(safe["items"], list):
        raise TypeError("report document items must be a list")
    if not isinstance(safe["errors"], list):
        raise TypeError("report document errors must be a list")

    # This report must not imply that automatic or constructed labels are
    # human truth.  Force the safe values even if a caller supplied something
    # else in metadata.
    safe["human_agree_rate"] = None
    safe["constructed_gold_only"] = True
    safe["constructed_gold_note"] = (
        "Task-03 gold is constructed gold only; human annotation was not run."
    )
    return safe


def make_report(metadata: Mapping[str, object] | None = None) -> dict[str, Any]:
    """Return a safe, writable report skeleton in ``running`` state."""
    return _sanitize_document(
        {
            "schema_version": REPORT_SCHEMA_VERSION,
            "status": "running",
            "items": [],
            "errors": [],
            "summary": _summary_defaults(),
            "human_agree_rate": None,
            "constructed_gold_only": True,
            "constructed_gold_note": (
                "Task-03 gold is constructed gold only; human annotation was not run."
            ),
            "started_at": _utc_now(),
            "finished_at": None,
            "metadata": dict(metadata or {}),
        }
    )


def _inline(value: object, fallback: str = "") -> str:
    text = fallback if value is None else _safe_text(value)
    return f"<code>{html.escape(text, quote=True)}</code>"


def _json_text(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return _safe_text(value)


def render_markdown(document: Mapping[str, object]) -> str:
    """Render Markdown from the same sanitized model persisted as JSON."""
    safe = _sanitize_document(document)
    summary = safe["summary"]
    lines = [
        "# Agent evaluation report",
        "",
        f"- Schema: {_inline(safe['schema_version'])}",
        f"- Status: {_inline(safe.get('status'))}",
        f"- Started at: {_inline(safe.get('started_at'))}",
        f"- Finished at: {_inline(safe.get('finished_at'), 'not finished')}",
        f"- Human agreement: {_inline(safe.get('human_agree_rate'), 'not evaluated')}",
        f"- Constructed gold only: {_inline(safe.get('constructed_gold_only'))}",
        "",
        "## Summary",
        "",
        "| metric | count |",
        "|---|---:|",
    ]
    for key in _SUMMARY_KEYS:
        lines.append(f"| {_inline(key)} | {_inline(summary.get(key, 0))} |")

    metadata = safe.get("metadata")
    if isinstance(metadata, Mapping) and metadata:
        lines.extend(["", "## Metadata", "", "| key | value |", "|---|---|"])
        for key in sorted(metadata, key=str):
            lines.append(f"| {_inline(key)} | {_inline(_json_text(metadata[key]))} |")

    errors = safe.get("errors", [])
    if errors:
        lines.extend(["", "## Errors", ""])
        for error in errors:
            lines.append(f"- {_inline(_json_text(error))}")

    items = safe.get("items", [])
    lines.extend(
        [
            "",
            "## Items",
            "",
            "| trace_id | status | model | score | score_id | requested | expected_value | post_status | verified_value | verified |",
            "|---|---|---|---:|---|---|---:|---|---:|---|",
        ]
    )
    for item in items:
        if not isinstance(item, Mapping):
            lines.append(f"| {_inline('<invalid>')} | {_inline('failed')} |  |  |  |  |")
            continue
        trace_id = item.get("trace_id", item.get("traceId", "<missing>"))
        model = item.get("judge_model", item.get("model", "<unknown>"))
        score = item.get("score")
        score_text = "" if score is None else _safe_text(score)
        score_id = item.get("score_id", item.get("scoreId", ""))
        requested = item.get("requested", "")
        expected_value = item.get("expected_value", "")
        expected_text = "" if expected_value is None else _safe_text(expected_value)
        post_status = item.get("post_status", item.get("post", item.get("written", "")))
        verified_value = item.get("verified_value", "")
        verified_value_text = "" if verified_value is None else _safe_text(verified_value)
        verified = item.get("verified", item.get("verification", ""))
        lines.append(
            "| "
            + " | ".join(
                (
                    _inline(trace_id),
                    _inline(item.get("status")),
                    _inline(model),
                    _inline(score_text),
                    _inline(score_id),
                    _inline(requested),
                    _inline(expected_text),
                    _inline(post_status),
                    _inline(verified_value_text),
                    _inline(verified),
                )
            )
            + " |"
        )
        item_error = item.get("error")
        if item_error:
            lines.append(f"  - Error: {_inline(_json_text(item_error))}")
        item_errors = item.get("errors")
        if item_errors:
            lines.append(f"  - Errors: {_inline(_json_text(item_errors))}")
        rationale = item.get("reason") or item.get("explanation")
        if rationale:
            lines.append(f"  - Judge rationale: {_inline(rationale)}")

    lines.extend(
        [
            "",
            "_Trace payloads, prompts, completions, hidden reasoning, and "
            "credentials are omitted._",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_output_dir(output_dir: str | Path) -> Path:
    if output_dir is None:
        raise ValueError("output_dir is required; no implicit report directory is used")
    raw = os.fspath(output_dir)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="strict")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("output_dir must be a non-empty local filesystem path")
    if re.match(r"^[a-z][a-z0-9+.-]*://", raw, re.IGNORECASE):
        raise ValueError("output_dir must be a local filesystem path, not a URL")
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError("output_dir must be a directory")
    return path


def _write_temp(path: Path, content: str) -> str:
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        return handle.name
    except OSError:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise


def _restore_snapshot(path: Path, snapshot: bytes | None) -> None:
    """Restore one report target, or remove it if it did not previously exist."""
    if snapshot is None:
        try:
            path.unlink()
        except FileNotFoundError:
            return
        return

    temporary = _write_temp(path, snapshot.decode("utf-8"))
    try:
        # Use a separate rename for compensation so a failure injected into
        # the publication ``os.replace`` calls cannot mask rollback itself.
        os.rename(temporary, path)
        temporary = ""
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


class ReportWriter:
    """Checkpoint a local JSON/Markdown report with bounded pair rollback."""

    def __init__(self, output_dir: str | Path, metadata: Mapping[str, object] | None = None):
        self.output_dir = _validate_output_dir(output_dir)
        self.json_path = self.output_dir / REPORT_JSON_NAME
        self.markdown_path = self.output_dir / REPORT_MARKDOWN_NAME
        self.document = make_report(metadata)
        # The skeleton is intentionally written immediately so malformed input
        # or a later runtime exception still has a local artifact to update.
        self.checkpoint(self.document)

    def checkpoint(self, document: dict[str, Any]) -> dict[str, Any]:
        """Write both projections, restoring the prior pair if publication fails."""
        safe_document = _sanitize_document(document)
        json_content = json.dumps(
            safe_document, ensure_ascii=False, indent=2, sort_keys=True
        ) + "\n"
        markdown_content = render_markdown(safe_document)
        json_tmp: str | None = None
        markdown_tmp: str | None = None
        previous_json: bytes | None = None
        previous_markdown: bytes | None = None
        json_replaced = False
        markdown_replaced = False
        try:
            previous_json = (
                self.json_path.read_bytes() if self.json_path.exists() else None
            )
            previous_markdown = (
                self.markdown_path.read_bytes()
                if self.markdown_path.exists()
                else None
            )
            json_tmp = _write_temp(self.json_path, json_content)
            markdown_tmp = _write_temp(self.markdown_path, markdown_content)
            os.replace(json_tmp, self.json_path)
            json_tmp = None
            json_replaced = True
            os.replace(markdown_tmp, self.markdown_path)
            markdown_tmp = None
            markdown_replaced = True
        except (OSError, TypeError, ValueError) as exc:
            rollback_error: BaseException | None = None
            try:
                if markdown_replaced:
                    _restore_snapshot(self.markdown_path, previous_markdown)
                if json_replaced:
                    _restore_snapshot(self.json_path, previous_json)
            except (OSError, TypeError, ValueError, UnicodeError) as restore_exc:
                rollback_error = restore_exc
            message = (
                "failed to write local evaluation report "
                f"({self.json_path.name}, {self.markdown_path.name}): {type(exc).__name__}"
            )
            if json_replaced or markdown_replaced:
                if rollback_error is None:
                    message += "; previous report pair restored"
                else:
                    message += (
                        "; rollback incomplete: "
                        f"{type(rollback_error).__name__}"
                    )
            raise ReportWriteError(message) from exc
        finally:
            for temporary in (json_tmp, markdown_tmp):
                if temporary:
                    try:
                        os.unlink(temporary)
                    except OSError:
                        pass
        self.document = safe_document
        return safe_document

    def finish(
        self,
        status: str,
        *,
        errors: Sequence[object] | None = None,
    ) -> dict[str, Any]:
        """Set terminal status and checkpoint; write failures remain exceptions."""
        document = dict(self.document)
        document["status"] = status
        document["finished_at"] = _utc_now()
        if errors:
            document["errors"] = [*document.get("errors", []), *errors]
        return self.checkpoint(document)


__all__ = [
    "REPORT_JSON_NAME",
    "REPORT_MARKDOWN_NAME",
    "REPORT_SCHEMA_VERSION",
    "ReportWriteError",
    "ReportWriter",
    "make_report",
    "render_markdown",
]
