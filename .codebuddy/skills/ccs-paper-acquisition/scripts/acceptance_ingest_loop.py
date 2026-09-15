#!/usr/bin/env python3
"""spec-032 验收最后一步：发现 -> 富化 -> 下载 -> **入库**。

前面的验收只走到"下载成功"，没有验证下载的 PDF 能否交到知识库侧。
这里驱动真实 `import_candidate()`，注入一个 in-memory 的 `PaperImportPort` 桩，
把受信任的本地 PDF 路径交给它，从而闭环整条链路，且不触碰真实 Qdrant。

用法：
    python3 scripts/acceptance_ingest_loop.py /tmp/ndss_2024_enriched.jsonl \
        --host www.ndss-symposium.org --limit 5
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# scripts/ -> ccs-paper-acquisition/ -> skills/ -> .codebuddy/ -> ResearchAgent/
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.paper_discovery.application.paper_import import import_candidate  # noqa: E402
from app.platform.ports import (  # noqa: E402
    ImportIndexStatus,
    ImportResourceCapability,
    PaperImportResult,
)


class StubKbPort:
    """in-memory 知识库桩：记录每次入库，验证幂等与文件路径真实性。"""

    def __init__(self) -> None:
        self.imported: list[dict] = []
        self._names: set[str] = set()

    def find_existing(self, snapshot):  # noqa: ANN001
        return None

    def existing_names(self) -> set[str]:
        return set(self._names)

    def import_paper(self, request) -> PaperImportResult:  # noqa: ANN001
        pdf = Path(request.trusted_pdf_path)
        exists = pdf.exists()
        size = pdf.stat().st_size if exists else 0
        magic = pdf.read_bytes()[:4] if exists else b""
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()[:16] if exists else ""
        snap = dict(request.candidate_snapshot)
        name = f"{snap.get('doi', 'unknown').replace('/', '_')}.pdf"
        self._names.add(name)
        self.imported.append(
            {
                "doi": snap.get("doi"),
                "title": (snap.get("title") or "")[:60],
                "file": str(pdf),
                "exists": exists,
                "size": size,
                "is_pdf": magic == b"%PDF",
                "sha256_16": digest,
            }
        )
        return PaperImportResult(
            paper_id=f"stub-{len(self.imported)}",
            index_status=ImportIndexStatus.INDEXED,
            error_code=None,
            stored_name=name,
            source_sha256=digest or None,
        )

    def compensate_import(self, capability: ImportResourceCapability) -> str:
        return "cleanup_done"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl")
    parser.add_argument("--host", action="append", default=[], help="allowed host (repeatable)")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    records = [json.loads(line) for line in Path(args.jsonl).open(encoding="utf-8") if line.strip()]
    hosts = tuple(args.host) or ("www.ndss-symposium.org",)
    # 只挑目标主机（或 DOI 解析器）的记录，别把 gated 的 dl.acm.org 混进来
    picked = [
        r
        for r in records
        if r.get("pdf_url")
        and not r.get("pdf_gated")
        and (r["pdf_url"].split("//", 1)[-1].split("/", 1)[0] in hosts or "doi.org" in r["pdf_url"])
    ][: args.limit]
    if not picked:
        print("没有匹配 allowed_hosts 的记录")
        return 1

    print(f"候选 {len(records)}，取 {len(picked)} 条；allowed_hosts={hosts}\n")

    port = StubKbPort()
    ok = 0
    for record in picked:
        try:
            result = import_candidate(record, allowed_hosts=hosts, paper_import_port=port)
        except Exception as exc:  # noqa: BLE001
            print(f"  异常 {type(exc).__name__}: {str(exc)[:70]}  <- {record.get('doi')}")
            continue
        entry = port.imported[-1] if port.imported else {}
        good = bool(result.paper_id) and entry.get("is_pdf") and entry.get("size", 0) > 1024
        ok += 1 if good else 0
        flag = "OK  " if good else "FAIL"
        print(
            f"  {flag} {record.get('doi','')[:38]:<38} paper_id={result.paper_id:<10} "
            f"{entry.get('size',0):>9,}B pdf={entry.get('is_pdf')} sha={entry.get('sha256_16')}"
        )

    print(f"\n入库闭环结果: {ok}/{len(picked)}")
    print(f"知识库侧记录数: {len(port.imported)}")
    return 0 if ok == len(picked) else 2


if __name__ == "__main__":
    raise SystemExit(main())
