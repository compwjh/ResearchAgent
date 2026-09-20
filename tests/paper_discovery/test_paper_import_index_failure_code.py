"""论文导入失败的可诊断性契约。

背景：此前「向量索引失败」「索引代次漂移」「下载产物异常」在 port 边界都被压成同一个
``KB_IMPORT_FAILED``，服务端也没有任何日志，只剩一句「论文导入失败」，无法判断该去
修 Ollama、重建索引还是重下 PDF。本次把「索引没建起来」单独拆成 ``KB_INDEX_FAILED``，
并保证真实原因至少留在服务端日志里。
"""

import logging
from pathlib import Path

from backend.app.knowledge_base.application import create_paper_import_port
from backend.app.paper_discovery.application.paper_import import (
    KB_IMPORT_FAILED,
    KB_INDEX_FAILED,
    safe_import_error_code,
    safe_import_error_message,
)
from backend.app.platform.ports import PaperImportRequest

PDF = b"%PDF-1.7\nindex-failure-fixture"

# 索引器自己报告的真实原因；这正是过去被吞掉、只能靠读 papers.json 才能看到的那段文本。
INDEX_ERROR = "索引失败：无法连接 Ollama：timed out"

FAILED_INDEX_RESULT = {
    "status": "failed",
    "chunk_count": 0,
    "chunkers": {
        "v1": {"status": "failed", "chunk_count": 0, "progress": 100, "error": INDEX_ERROR},
        "v2": {"status": "failed", "chunk_count": 0, "progress": 100, "error": INDEX_ERROR},
    },
}


def _port(tmp_path: Path, indexer):
    papers = tmp_path / "papers"
    meta = tmp_path / "papers.json"
    source = tmp_path / "download.pdf"
    source.write_bytes(PDF)
    port = create_paper_import_port(papers_dir=papers, meta_path=meta, indexer=indexer)
    return port, source


def test_index_failure_uses_dedicated_error_code_not_kb_import_failed(tmp_path):
    port, source = _port(tmp_path, lambda _record, _path: FAILED_INDEX_RESULT)

    result = port.import_paper(
        PaperImportRequest(
            {"title": "Index Failure", "year": 2026, "conference_id": "ccs", "doi": "10/index-fail"},
            source,
        )
    )

    assert result.index_status.value == "failed"
    assert result.error_code.value == KB_INDEX_FAILED
    assert result.error_code.value != KB_IMPORT_FAILED


def test_index_failure_code_is_stable_and_has_its_own_message():
    """新错误码必须进安全表，否则会在边界被归一化回 KB_IMPORT_FAILED。"""
    assert safe_import_error_code(KB_INDEX_FAILED) == KB_INDEX_FAILED
    message = safe_import_error_message(KB_INDEX_FAILED)
    assert message != safe_import_error_message(KB_IMPORT_FAILED)
    assert "索引" in message


def test_index_failure_logs_the_real_cause(tmp_path, caplog):
    """真实原因（如 Ollama 超时）必须出现在服务端日志里，否则运维无从下手。"""
    port, source = _port(tmp_path, lambda _record, _path: FAILED_INDEX_RESULT)

    with caplog.at_level(logging.ERROR, logger="backend.app.knowledge_base.application"):
        port.import_paper(
            PaperImportRequest(
                {"title": "Logged", "year": 2026, "conference_id": "ccs", "doi": "10/logged"},
                source,
            )
        )

    assert INDEX_ERROR in caplog.text


def test_indexer_exception_also_returns_kb_index_failed(tmp_path):
    """索引器直接抛异常（而非返回 failed）时，同样归类为索引失败。"""

    def boom(_record, _path):
        raise RuntimeError("embedding backend unreachable")

    port, source = _port(tmp_path, boom)

    result = port.import_paper(
        PaperImportRequest(
            {"title": "Raised", "year": 2026, "conference_id": "ccs", "doi": "10/raised"},
            source,
        )
    )

    assert result.error_code.value == KB_INDEX_FAILED
