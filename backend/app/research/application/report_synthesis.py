"""Spec034 Task08 report synthesis and delivery contracts.

The synthesizer is intentionally deterministic at this boundary.  A model may
produce the validated input objects, but this module only accepts the verified
candidate/citation allowlists supplied by the Orchestrator.  It never reads a
conversation, prompt, credential, URL or filesystem path and it never invents
paper metadata.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.app.research.domain.models import ResearchArtifact, ResearchNotification

_FORBIDDEN_PARTS = (
    "prompt", "cot", "chain_of_thought", "reasoning", "credential", "password",
    "secret", "token", "cookie", "authorization", "api_key", "access_key", "url",
)
_ID_RE = re.compile(r"^[A-Za-z0-9:_-]{1,240}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_PATH_RE = re.compile(r"(?:^[/\\]|^[A-Za-z]:[/\\]|\.\.?[/\\]|[/\\]\.\.?[/\\])")
_FILE_NAME_RE = re.compile(r"(?:^|\s)(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:md|markdown|html|json|pdf|py|sqlite3)(?:$|\s)", re.I)


class ReportSynthesisError(ValueError):
    """Stable, user-safe synthesis failure."""

    code = "AGENT_OUTPUT_INVALID"

    def __init__(self, message: str = "", *, code: str | None = None) -> None:
        if code:
            self.code = code
        super().__init__(message or self.code)


REPORT_SYNTHESIS_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version", "report_version", "output_hash", "sections",
        "citation_manifest", "artifact_ids", "safe_summary", "source_refs",
    ],
    "properties": {
        "schema_version": {"type": "string", "minLength": 1, "maxLength": 32},
        "report_version": {"type": "integer", "minimum": 1},
        "output_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "sections": {"type": "array", "maxItems": 32},
        "citation_manifest": {"type": "array", "maxItems": 256},
        "artifact_ids": {"type": "array", "maxItems": 8},
        "safe_summary": {"type": "object"},
        "source_refs": {"type": "array", "maxItems": 256},
    },
}


class ReportSynthesisOutput(BaseModel):
    """Validated, model-facing hand-off; Markdown is a derived delivery field."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1, max_length=32)
    report_version: int = Field(ge=1)
    output_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    sections: list[dict[str, Any]] = Field(max_length=32)
    citation_manifest: list[dict[str, Any]] = Field(max_length=256)
    artifact_ids: list[str] = Field(max_length=8)
    safe_summary: dict[str, Any]
    source_refs: list[str] = Field(max_length=256)

    @field_validator("source_refs", "artifact_ids")
    @classmethod
    def _ids_only(cls, value: list[str]) -> list[str]:
        if any(not isinstance(item, str) or not _ID_RE.fullmatch(item) for item in value):
            raise ValueError("only stable IDs are allowed")
        return value


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def report_output_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical({k: v for k, v in payload.items() if k != "output_hash"})).hexdigest()


def _walk_safe(value: Any, depth: int = 0) -> None:
    if depth > 6:
        raise ReportSynthesisError("synthesis value is too deeply nested")
    if isinstance(value, Mapping):
        if len(value) > 64:
            raise ReportSynthesisError("synthesis object is too large")
        for key, child in value.items():
            lowered = str(key).casefold().replace("-", "_")
            if any(part in lowered for part in _FORBIDDEN_PARTS):
                raise ReportSynthesisError("unsafe synthesis field")
            _walk_safe(child, depth + 1)
    elif isinstance(value, (list, tuple)):
        if len(value) > 256:
            raise ReportSynthesisError("synthesis list is too large")
        for child in value:
            _walk_safe(child, depth + 1)
    elif isinstance(value, str):
        if len(value) > 12000 or re.search(r"(?:https?://|ftp://|www\.)", value, re.I):
            raise ReportSynthesisError("unsafe synthesis value")
        lowered = value.casefold()
        if any(marker in lowered for marker in ("authorization:", "bearer ", "password=", "token=", "api_key=")):
            raise ReportSynthesisError("unsafe synthesis value")
    elif value is not None and not isinstance(value, (int, float, bool)):
        raise ReportSynthesisError("unsupported synthesis value")


def validate_report_synthesis_output(payload: Any, *, expected_version: int | None = None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ReportSynthesisError("synthesis output must be an object")
    _walk_safe(payload)
    try:
        output = ReportSynthesisOutput.model_validate(payload)
    except ValidationError as exc:
        raise ReportSynthesisError("synthesis output schema validation failed") from exc
    if expected_version is not None and output.report_version != expected_version:
        raise ReportSynthesisError("report version does not match subject")
    if report_output_hash(payload) != output.output_hash:
        raise ReportSynthesisError("output_hash does not match normalized output")
    return output.model_dump(mode="json")


def render_markdown_html(markdown: str) -> str:
    """Render a deliberately small Markdown subset with all text escaped.

    Raw HTML, links and images are not interpreted.  This fixed renderer makes
    the HTML artifact a pure, reproducible derivative of the Markdown source.
    """
    if not isinstance(markdown, str) or len(markdown) > 500_000:
        raise ReportSynthesisError("markdown is missing or too large")
    out: list[str] = ["<!doctype html><html><head><meta charset=\"utf-8\"><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\"><title>Research report</title></head><body>"]
    in_code = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            if in_code:
                out.append("</code></pre>")
            else:
                out.append("<pre><code>")
            in_code = not in_code
            continue
        # Keep dangerous URI schemes out of the derived document altogether;
        # raw HTML/Markdown links are otherwise rendered as inert text.
        line = re.sub(r"(?i)javascript\s*:", "[blocked-scheme]:", line)
        escaped = html.escape(line, quote=True)
        # Numeric citation markers are the sole interactive-ish decoration in
        # the fixed renderer.  The visible text remains escaped and the
        # attribute is generated from the marker, never from raw HTML input.
        escaped = re.sub(
            r"\[(\d+)\]",
            lambda match: f'<sup data-citation-no="{match.group(1)}">[{match.group(1)}]</sup>',
            escaped,
        )
        if in_code:
            out.append(escaped + "\n")
        elif not line.strip():
            continue
        elif line.startswith("### "):
            out.append(f"<h3>{escaped[4:]}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{escaped[3:]}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{escaped[2:]}</h1>")
        elif line.startswith("- "):
            out.append(f"<p>• {escaped[2:]}</p>")
        elif line.startswith("> "):
            out.append(f"<blockquote>{escaped[2:]}</blockquote>")
        else:
            out.append(f"<p>{escaped}</p>")
    if in_code:
        out.append("</code></pre>")
    out.append("</body></html>")
    return "\n".join(out)


def _safe_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ReportSynthesisError(f"invalid {field}")
    return value


def _safe_text_input(value: Any, field: str, *, default: str = "", max_length: int = 200) -> str:
    """Validate user/model-facing report labels before they enter Markdown."""
    if value is None:
        value = default
    if not isinstance(value, str):
        raise ReportSynthesisError(f"invalid {field}")
    text = value.strip()
    if len(text) > max_length or _PATH_RE.search(text) or _FILE_NAME_RE.search(text) or re.search(r"(?:https?://|ftp://|www\.)", text, re.I):
        raise ReportSynthesisError(f"unsafe {field}")
    lowered = text.casefold()
    if any(part in lowered for part in _FORBIDDEN_PARTS) or any(
        marker in lowered for marker in ("authorization:", "bearer ", "password=", "token=", "api_key=")
    ):
        raise ReportSynthesisError(f"unsafe {field}")
    return text or default


def _safe_catalog_metadata(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Return only safe, bounded directory fields from a validated candidate.

    The evaluator proves the candidate and citation IDs; these fields are
    descriptive catalog facts carried alongside that proof.  They are never
    accepted from the Synthesizer model output itself.  Rejecting unsafe text
    here keeps URLs, prompt/CoT text and credentials out of both artifacts.
    """
    def safe_long_text(value: Any, field: str, limit: int) -> str:
        if not isinstance(value, str):
            raise ReportSynthesisError(f"invalid catalog {field}")
        text = value.strip()
        lowered = text.casefold()
        if (
            len(text) > 12000
            or _PATH_RE.search(text)
            or _FILE_NAME_RE.search(text)
            or re.search(r"(?:https?://|ftp://|www\.)", text, re.I)
            or any(part in lowered for part in _FORBIDDEN_PARTS)
            or any(marker in lowered for marker in ("authorization:", "bearer ", "password=", "token=", "api_key="))
        ):
            raise ReportSynthesisError(f"unsafe catalog {field}")
        return text[:limit]

    metadata: dict[str, Any] = {}
    for field, limit in (("title", 300), ("abstract", 6000), ("summary", 4000),
                         ("method", 500), ("methods", 1000), ("topic", 500),
                         ("topics", 1000), ("facets", 1000)):
        value = candidate.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ReportSynthesisError(f"invalid catalog {field}")
        metadata[field] = safe_long_text(value, field, limit)
    keywords = candidate.get("keywords")
    if keywords is not None:
        if isinstance(keywords, str):
            keywords = re.split(r"[,;，；|]", keywords)
        if not isinstance(keywords, (list, tuple)):
            raise ReportSynthesisError("invalid catalog keywords")
        clean_keywords: list[str] = []
        for value in keywords[:24]:
            clean = safe_long_text(value, "keyword", 160)
            if clean and clean not in clean_keywords:
                clean_keywords.append(clean)
        metadata["keywords"] = clean_keywords
    year = candidate.get("year")
    if year is not None:
        if isinstance(year, bool) or not isinstance(year, int) or year < 0 or year > 9999:
            raise ReportSynthesisError("invalid catalog year")
        metadata["year"] = year
    for field in ("source", "source_id"):
        value = candidate.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ReportSynthesisError(f"invalid catalog {field}")
        metadata[field] = safe_long_text(value, field, 200)
    source_kinds = candidate.get("source_kinds")
    if source_kinds is not None:
        if isinstance(source_kinds, str):
            source_kinds = [source_kinds]
        if not isinstance(source_kinds, (list, tuple)):
            raise ReportSynthesisError("invalid catalog source_kinds")
        metadata["source_kinds"] = [
            safe_long_text(value, "source_kind", 100)
            for value in source_kinds[:8]
            if isinstance(value, str) and value.strip()
        ]
    official_url = candidate.get("official_url", candidate.get("official_page_url"))
    if official_url is not None:
        if not isinstance(official_url, str):
            raise ReportSynthesisError("invalid catalog official_url")
        official_url = official_url.strip()
        # This value comes from the trusted catalog store, not model output.
        # Keep the report link useful while rejecting credentials, control
        # characters, and non-web schemes.
        if (
            len(official_url) > 2000
            or not re.fullmatch(r"https://[^\s<>\"']+", official_url, re.I)
            or "@" in official_url.split("/", 3)[2]
        ):
            raise ReportSynthesisError("unsafe catalog official_url")
        metadata["official_url"] = official_url
    return metadata


def _candidate_markdown_lines(candidate_id: str, candidate: Mapping[str, Any], refs: Iterable[str]) -> list[str]:
    """Render one verified catalog candidate with explicit missing-field labels."""
    metadata = _safe_catalog_metadata(candidate)
    title = metadata.get("title") or "官方未提供"
    lines = [f"#### {title}", "", f"- 证据对象 `{candidate_id}`（引用：{', '.join(f'[{ref}]' for ref in refs)}）"]
    abstract = metadata.get("abstract") or metadata.get("summary")
    lines.append(f"- 摘要：{abstract or '官方未提供'}")
    keywords = metadata.get("keywords") or []
    lines.append(f"- 关键词：{'、'.join(keywords) if keywords else '官方未提供'}")
    method = metadata.get("method") or metadata.get("methods")
    lines.append(f"- 研究方法：{method or '官方未提供'}")
    source = metadata.get("source") or metadata.get("source_id")
    if not source:
        source_kinds = metadata.get("source_kinds") or []
        source = "、".join(source_kinds)
    lines.append(f"- 来源：{source or '官方未提供'}")
    lines.append(f"- 年份：{metadata.get('year') or '官方未提供'}")
    lines.append(f"- 官方 URL：{metadata.get('official_url') or '官方未提供'}")
    lines.append("")
    return lines


@dataclass(frozen=True)
class SynthesisResult:
    output: ReportSynthesisOutput
    markdown: str
    html: str
    citation_manifest: tuple[dict[str, Any], ...]
    # Internal-only bridge payload.  ReportDeliveryService deliberately reads
    # only the public candidate-level fields above, so this optional value can
    # never enter the immutable artifact envelope.
    evidence_matrix: Mapping[str, Any] | None = None


class ReportSynthesizer:
    """Create report source only from verified candidates and citation IDs."""

    def synthesize_evidence_report(
        self, matrix: Mapping[str, Any], *, report_id: str, report_version: int,
        title: str = "深度研究报告",
    ) -> dict[str, Any]:
        """Parameterised Spec030 entry point over the canonical matrix.

        The implementation is kept in the evidence-report application module
        to avoid duplicating this legacy synthesizer's candidate contract.
        """
        from backend.app.research.application.report_generation import render_evidence_report
        return render_evidence_report(
            matrix, report_id=report_id, report_version=report_version, title=title,
        )

    synthesize_matrix = synthesize_evidence_report

    def synthesize(
        self,
        *,
        report_version: int,
        candidates: Iterable[Mapping[str, Any]] | None = None,
        citation_whitelist: Iterable[Mapping[str, Any] | str] | Mapping[str, Any] | None = None,
        validated_candidates: Iterable[Mapping[str, Any]] | None = None,
        citation_manifest: Iterable[Mapping[str, Any] | str] | Mapping[str, Any] | None = None,
        sections: Iterable[Mapping[str, Any]] | None = None,
        title: str = "研究报告",
    ) -> SynthesisResult:
        if int(report_version) < 1:
            raise ReportSynthesisError("report version must be positive")
        verified: dict[str, Mapping[str, Any]] = {}
        for candidate in (validated_candidates if validated_candidates is not None else (candidates or ())):
            marker = (
                isinstance(candidate, Mapping)
                and any(candidate.get(name) is True for name in ("verified", "validated", "evidence_validated"))
            )
            if not marker:
                raise ReportSynthesisError("candidate is not verified")
            candidate_id = candidate.get("catalog_paper_id", candidate.get("candidate_id"))
            candidate_id = _safe_identifier(candidate_id, "candidate_id")
            verified[candidate_id] = candidate
        allow: dict[str, dict[str, Any]] = {}
        raw_allowlist = citation_manifest if citation_manifest is not None else (citation_whitelist or ())
        if isinstance(raw_allowlist, Mapping):
            raw_allowlist = [
                {"citation_ref": value, "candidate_id": key}
                for key, values in raw_allowlist.items()
                for value in (values if isinstance(values, (list, tuple, set)) else (values,))
            ]
        for ref in raw_allowlist:
            if isinstance(ref, str):
                ref_id = _safe_identifier(ref, "citation_ref")
                candidate_id = ref_id.split(":", 1)[1] if ref_id.startswith("catalog:") else ref_id
                candidate_id = _safe_identifier(candidate_id, "candidate_id")
                if candidate_id not in verified:
                    raise ReportSynthesisError("citation references an unverified candidate")
                allow[ref_id] = {"citation_ref": ref_id, "candidate_id": candidate_id}
            elif isinstance(ref, Mapping):
                ref_id = ref.get("citation_ref", ref.get("evidence_ref", ref.get("candidate_id", ref.get("catalog_paper_id"))))
                ref_id = _safe_identifier(ref_id, "citation_ref")
                candidate_id = ref.get("candidate_id", ref.get("catalog_paper_id", ref_id))
                candidate_id = _safe_identifier(candidate_id, "candidate_id")
                if candidate_id not in verified:
                    raise ReportSynthesisError("citation references an unverified candidate")
                allow[ref_id] = {"citation_ref": ref_id, "candidate_id": candidate_id}
            else:
                raise ReportSynthesisError("invalid citation allowlist")
        if not allow and verified:
            raise ReportSynthesisError("verified candidates require citation references")
        manifest = tuple(sorted(allow.values(), key=lambda item: (item["candidate_id"], item["citation_ref"])))
        report_sections = []
        requested = list(sections or ())
        if not requested:
            requested = [{"heading": "证据与引用", "candidate_ids": list(verified)}]
        for section in requested:
            if not isinstance(section, Mapping):
                raise ReportSynthesisError("invalid report section")
            heading = _safe_text_input(section.get("heading", ""), "section heading", default="研究结果")
            ids = section.get("candidate_ids", list(verified))
            if not isinstance(ids, (list, tuple)):
                raise ReportSynthesisError("section candidate_ids must be a list")
            ids = [_safe_identifier(item, "candidate_id") for item in ids]
            if any(item not in verified for item in ids):
                raise ReportSynthesisError("section references an unverified candidate")
            report_sections.append({"heading": heading, "candidate_ids": ids})
        title = _safe_text_input(title, "title", default="研究报告")
        lines = [f"# {title}", "", "## 研究结果", ""]
        for section in report_sections:
            lines.extend([f"### {section['heading']}", ""])
            for candidate_id in section["candidate_ids"]:
                refs = [item["citation_ref"] for item in manifest if item["candidate_id"] == candidate_id]
                if not refs:
                    raise ReportSynthesisError("every reported candidate requires a citation")
                lines.extend(_candidate_markdown_lines(candidate_id, verified[candidate_id], refs))
            lines.append("")
        lines.extend(["## 引用清单", ""])
        for item in manifest:
            lines.append(f"- `{item['citation_ref']}` → `{item['candidate_id']}`")
        markdown = "\n".join(lines).strip() + "\n"
        safe_summary = {"candidate_count": len(verified), "citation_count": len(manifest), "renderer": "fixed-v1"}
        source_refs = [item["citation_ref"] for item in manifest]
        payload: dict[str, Any] = {
            "schema_version": "report-synthesis-v1", "report_version": int(report_version),
            "sections": report_sections, "citation_manifest": list(manifest), "artifact_ids": [],
            "safe_summary": safe_summary, "source_refs": source_refs,
        }
        payload["output_hash"] = report_output_hash(payload)
        output = ReportSynthesisOutput.model_validate({**payload, "output_hash": payload["output_hash"]})
        return SynthesisResult(output, markdown, render_markdown_html(markdown), manifest)

    def consume_validated_output(
        self,
        *,
        output: Mapping[str, Any],
        validated_candidates: Iterable[Mapping[str, Any]],
        title: str = "深度研究报告",
        evidence_matrix: Mapping[str, Any] | None = None,
    ) -> SynthesisResult:
        """Consume the actual Synthesizer Run output after semantic validation.

        The model supplies sections and the citation manifest; this boundary
        only renders them after checking every candidate and citation against
        evaluator evidence.  Artifact IDs must remain empty until delivery.
        """
        validated = validate_report_synthesis_output(output)
        if validated["artifact_ids"]:
            raise ReportSynthesisError("synthesizer must not preselect artifact IDs")
        title = _safe_text_input(title, "title", default="深度研究报告")
        validated_candidates = list(validated_candidates)
        allowed: dict[str, set[str]] = {}
        verified: set[str] = set()
        for candidate in validated_candidates:
            if not isinstance(candidate, Mapping) or not any(
                candidate.get(name) is True for name in ("verified", "validated", "evidence_validated")
            ):
                raise ReportSynthesisError("candidate is not verified")
            candidate_id = _safe_identifier(candidate.get("candidate_id", candidate.get("catalog_paper_id")), "candidate_id")
            refs = candidate.get("evidence_refs")
            if not isinstance(refs, (list, tuple)) or not refs:
                raise ReportSynthesisError("verified candidate has no validation evidence")
            verified.add(candidate_id)
            allowed[candidate_id] = {_safe_identifier(ref, "citation_ref") for ref in refs}
        manifest: list[dict[str, Any]] = []
        for item in validated["citation_manifest"]:
            if not isinstance(item, Mapping):
                raise ReportSynthesisError("invalid citation manifest")
            ref = _safe_identifier(item.get("citation_ref", item.get("evidence_ref")), "citation_ref")
            supplied_candidate_id = _safe_identifier(item.get("candidate_id"), "candidate_id")
            candidate_id = supplied_candidate_id
            if candidate_id not in verified or ref not in allowed[candidate_id]:
                # Small/local models occasionally copy the first candidate ID
                # onto every citation row while preserving the actual
                # ``catalog:<id>`` reference.  The citation reference is the
                # durable evidence key; when it belongs to exactly one
                # verified candidate, repair only that bookkeeping field.
                # Ambiguous or unknown references remain a hard failure.
                matches = [
                    verified_id for verified_id, refs in allowed.items()
                    if ref in refs
                ]
                if len(matches) != 1:
                    raise ReportSynthesisError("citation is outside evaluator evidence allowlist")
                candidate_id = matches[0]
            manifest.append({"citation_ref": ref, "candidate_id": candidate_id})
        if not verified or not manifest:
            raise ReportSynthesisError("report requires kept candidates and validation evidence")
        manifest.sort(key=lambda item: (item["candidate_id"], item["citation_ref"]))
        manifest_refs = {item["citation_ref"] for item in manifest}
        if set(validated["source_refs"]) != manifest_refs:
            raise ReportSynthesisError("source_refs must equal the evaluator citation manifest")
        manifest_by_candidate = {item["candidate_id"] for item in manifest}
        report_sections: list[dict[str, Any]] = []
        reported_ids: set[str] = set()
        for section in validated["sections"]:
            if not isinstance(section, Mapping):
                raise ReportSynthesisError("invalid report section")
            heading = _safe_text_input(section.get("heading", ""), "section heading", default="研究结果")
            ids = section.get("candidate_ids", ())
            if not isinstance(ids, (list, tuple)):
                raise ReportSynthesisError("section candidate_ids must be a list")
            clean_ids = [_safe_identifier(item, "candidate_id") for item in ids]
            if any(item not in verified or item not in manifest_by_candidate for item in clean_ids):
                raise ReportSynthesisError("section references an unverified candidate")
            summary = section.get("summary", "")
            if summary is not None and not isinstance(summary, str):
                raise ReportSynthesisError("section summary must be text")
            clean_summary = _safe_text_input(summary, "section summary", default="", max_length=4000) if summary else ""
            report_sections.append({"heading": heading, "candidate_ids": clean_ids, "summary": clean_summary})
            reported_ids.update(clean_ids)
        if not report_sections:
            raise ReportSynthesisError("synthesizer returned no report sections")
        # A model may return only a subset of the validated evidence set.  Keep
        # every verified candidate in the immutable report by adding a
        # deterministic metadata-only section; this never creates evidence or
        # copies claims from the model output.
        missing_ids = [candidate_id for candidate_id in sorted(verified) if candidate_id not in reported_ids]
        if missing_ids:
            for candidate_id in missing_ids:
                for ref in allowed[candidate_id]:
                    if not any(item["candidate_id"] == candidate_id and item["citation_ref"] == ref for item in manifest):
                        manifest.append({"citation_ref": ref, "candidate_id": candidate_id})
            manifest.sort(key=lambda item: (item["candidate_id"], item["citation_ref"]))
            report_sections.append({
                "heading": "目录证据补充",
                "candidate_ids": missing_ids,
                "summary": "以下论文已通过目录证据校验，但模型未单独分组；本节仅展示目录元数据，不代表全文结论。",
            })
            manifest_refs = {item["citation_ref"] for item in manifest}
        lines = [f"# {title}", "", "## 研究结果", ""]
        for section in report_sections:
            lines.extend([f"### {section['heading']}", ""])
            if section.get("summary"):
                lines.append(f"{section['summary']}\n")
            for candidate_id in section["candidate_ids"]:
                refs = [item["citation_ref"] for item in manifest if item["candidate_id"] == candidate_id]
                candidate = next((item for item in validated_candidates if _safe_identifier(item.get("candidate_id", item.get("catalog_paper_id")), "candidate_id") == candidate_id), None)
                if candidate is None:
                    raise ReportSynthesisError("reported candidate is missing")
                lines.extend(_candidate_markdown_lines(candidate_id, candidate, refs))
            lines.append("")
        lines.extend(["## 引用清单", ""])
        lines.extend(f"- `{item['citation_ref']}` → `{item['candidate_id']}`" for item in manifest)
        markdown = "\n".join(lines).strip() + "\n"
        clean = dict(validated)
        clean["sections"] = report_sections
        clean["citation_manifest"] = manifest
        clean["source_refs"] = sorted(manifest_refs)
        clean["artifact_ids"] = []
        clean["output_hash"] = report_output_hash({key: value for key, value in clean.items() if key != "output_hash"})
        clean_output = ReportSynthesisOutput.model_validate(clean)
        return SynthesisResult(
            clean_output,
            markdown,
            render_markdown_html(markdown),
            tuple(manifest),
            evidence_matrix,
        )


class ReportDeliveryService:
    """Persist immutable artifacts, write the final conversation message and notify.

    This is a replayable cross-database saga: research artifacts are committed
    first, then the idempotent MemoryRepository activity message is updated,
    and finally the independent notification fact is inserted.
    """

    def __init__(self, *, store, memory_repository, synthesizer: ReportSynthesizer | None = None) -> None:
        self.store = store
        self.memory_repository = memory_repository
        self.synthesizer = synthesizer or ReportSynthesizer()

    @staticmethod
    def _artifact_payload(artifact: ResearchArtifact) -> dict[str, Any]:
        return {
            "artifact_id": artifact.artifact_id, "report_version": artifact.report_version,
            "artifact_type": artifact.artifact_type, "content_hash": artifact.content_hash,
            "created_at": artifact.created_at,
        }

    def deliver(
        self,
        *,
        session,
        owner_id: str,
        generated_by_agent_run_id: str,
        result: SynthesisResult,
        notification_kind: str = "completed",
    ) -> dict[str, Any]:
        task_id = session.research_task_id
        if not task_id:
            raise ReportSynthesisError("report delivery requires a research task")
        if session.owner_id != owner_id:
            raise ReportSynthesisError("report owner binding is invalid")
        task = self.store.get_task(task_id, owner_id)
        if task is None or task.conversation_id != session.conversation_id:
            raise ReportSynthesisError("report task owner/session binding is invalid")
        version = result.output.report_version
        manifest_json = json.dumps(list(result.citation_manifest), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        contents = {
            "markdown": result.markdown,
            "html": result.html,
            "citation_manifest": manifest_json,
        }
        artifacts: list[ResearchArtifact] = []
        existing = {
            item.artifact_type: item
            for item in self.store.list_artifacts_for_task(task_id, owner_id, report_version=version)
        }
        for artifact_type, content in contents.items():
            artifact = existing.get(artifact_type)
            expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if artifact is not None and artifact.content_hash != expected_hash:
                raise ReportSynthesisError("artifact immutable conflict", code="ARTIFACT_IMMUTABLE_CONFLICT")
            if artifact is None:
                artifact = ResearchArtifact(
                    artifact_id=uuid.uuid4().hex,
                    research_task_id=task_id,
                    report_version=version,
                    artifact_type=artifact_type,
                    content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    generated_by_agent_run_id=generated_by_agent_run_id,
                    content=content,
                )
                try:
                    artifact = self.store.create_artifact(artifact, owner_id=owner_id)
                except Exception as exc:
                    # A concurrent retry may have won the immutable insert.
                    existing_after = {
                        item.artifact_type: item
                        for item in self.store.list_artifacts_for_task(task_id, owner_id, report_version=version)
                    }
                    artifact = existing_after.get(artifact_type)
                    if artifact is None:
                        raise ReportSynthesisError("artifact persistence failed") from exc
                    if artifact.content_hash != expected_hash:
                        raise ReportSynthesisError(
                            "artifact immutable conflict", code="ARTIFACT_IMMUTABLE_CONFLICT"
                        ) from exc
            artifacts.append(artifact)
        artifact_ids = [item.artifact_id for item in artifacts]
        payload = result.output.model_dump(mode="json")
        payload["artifact_ids"] = artifact_ids
        payload["output_hash"] = report_output_hash({key: value for key, value in payload.items() if key != "output_hash"})
        output = ReportSynthesisOutput.model_validate(payload)
        key = f"research-report:{task_id}:{version}"
        message_status = (
            "partial" if notification_kind == "partial"
            else "failed" if notification_kind == "failed" else "completed"
        )
        existing_message = self.memory_repository.get_activity_message(
            session.conversation_id, owner_id, key
        )
        if existing_message is not None and existing_message.content != result.markdown:
            raise ReportSynthesisError("final message immutable conflict", code="ARTIFACT_IMMUTABLE_CONFLICT")
        message = self.memory_repository.create_activity_message(
            session.conversation_id, owner_id, result.markdown,
            activity_idempotency_key=key,
            status=message_status,
            parent_message_id=session.activity_message_id,
        )
        message = self.memory_repository.update_message(
            message.message_id,
            owner_id,
            content=result.markdown,
            status=message_status,
        ) or message
        self.store.update_session_links(session.research_session_id, owner_id, final_message_id=message.message_id)
        notification = self.notify(
            owner_id=owner_id, research_session_id=session.research_session_id,
            research_task_id=task_id, notification_kind=notification_kind,
            subject_version=version, payload={"report_version": version, "artifact_ids": artifact_ids, "message_id": message.message_id},
            idempotency_key=key,
        )
        return {
            "output": output.model_dump(mode="json"),
            "artifacts": [self._artifact_payload(item) for item in artifacts],
            "message_id": message.message_id,
            "notification_id": notification.notification_id,
        }

    def notify(
        self, *, owner_id: str, notification_kind: str,
        subject_version: int, payload: Mapping[str, Any], idempotency_key: str,
        research_session_id: str | None = None, research_task_id: str | None = None,
    ) -> ResearchNotification:
        """Insert one owner-scoped notification fact; retries return the original."""
        _walk_safe(payload)
        encoded = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return self.store.create_notification(ResearchNotification(
            notification_id=uuid.uuid4().hex, owner_id=owner_id,
            notification_kind=notification_kind, status="unread",
            subject_version=int(subject_version), event_seq=0, payload_json=encoded,
            idempotency_key=idempotency_key, research_session_id=research_session_id,
            research_task_id=research_task_id,
        ))


class ResearchNotificationService:
    """Small facade for the five user-visible terminal/waiting facts."""

    KINDS = frozenset({"completed", "partial", "failed", "waiting_approval", "interrupted"})

    def __init__(self, *, store) -> None:
        self.store = store

    def emit(
        self, *, owner_id: str, notification_kind: str, subject_version: int,
        payload: Mapping[str, Any], idempotency_key: str,
        research_session_id: str | None = None, research_task_id: str | None = None,
    ) -> ResearchNotification:
        if notification_kind not in self.KINDS:
            raise ReportSynthesisError("invalid notification kind")
        _walk_safe(payload)
        return self.store.create_notification(ResearchNotification(
            notification_id=uuid.uuid4().hex, owner_id=owner_id,
            notification_kind=notification_kind, status="unread", subject_version=int(subject_version),
            event_seq=0, payload_json=json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            idempotency_key=idempotency_key, research_session_id=research_session_id,
            research_task_id=research_task_id,
        ))


Synthesizer = ReportSynthesizer
ReportSynthesisOutputSchema = ReportSynthesisOutput
validate_synthesis_output = validate_report_synthesis_output

__all__ = [
    "REPORT_SYNTHESIS_OUTPUT_SCHEMA", "ReportSynthesisOutput", "ReportSynthesisOutputSchema",
    "ReportSynthesisError", "ReportSynthesizer", "Synthesizer", "SynthesisResult",
    "ResearchNotificationService",
    "report_output_hash", "validate_report_synthesis_output", "validate_synthesis_output",
    "render_markdown_html",
]
