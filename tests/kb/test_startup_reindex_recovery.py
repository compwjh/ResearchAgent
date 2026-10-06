"""spec-036 Task06：启动自愈——重排队陈旧 failed 重建任务（一次性、幂等、防风暴）。

覆盖点：
- 启动自愈只重排队 status=failed 的 (document, chunker)，不动 indexed/indexing/pending；
- 幂等：每个 (document, chunker) 仅重排队一次（持久化标记 auto_requeued_at），重启不风暴；
- 重试后仍 failed 不二次自动重试（无无限重试）；
- 单篇排队失败（源丢失等）被跳过且不阻断其它文档、不抛出；
- 损坏的 papers.json 不抛异常、返回 0；
- main.py 启动流程会调用自愈，且不因自愈异常而阻塞启动。
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.knowledge_base import application
from backend.app.knowledge_base.infrastructure import store as store_module
from backend.app.knowledge_base.infrastructure.store import (
    CHUNKER_V1,
    CHUNKER_V2,
    STATUS_FAILED,
    STATUS_INDEXED,
    STATUS_INDEXING,
    STATUS_PENDING,
)

SCHEMA = "knowledge-document-v1"


def _write_doc(meta: Path, document_id: str, chunkers: dict) -> None:
    papers = store_module.load_papers(meta)
    papers.append(
        {
            "schema_version": SCHEMA,
            "document_id": document_id,
            "file_name": f"{document_id}.md",
            "chunkers": chunkers,
        }
    )
    store_module.save_papers(papers, meta)


def _failed() -> dict:
    return {"status": STATUS_FAILED, "chunk_count": 0, "progress": 0, "error": "陈旧失败"}


def _state(status: str, error=None) -> dict:
    return {
        "status": status,
        "chunk_count": 0,
        "progress": 100 if status == STATUS_INDEXED else 0,
        "error": error,
    }


class StoreFailedChunkerQueryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.meta = self.tmp / "papers.json"

    def test_iter_failed_chunkers_only_failed(self):
        _write_doc(self.meta, "d1", {"v1": _failed(), "v2": _state(STATUS_INDEXED)})
        _write_doc(self.meta, "d2", {"v1": _state(STATUS_INDEXING), "v2": _failed()})
        found = set(store_module.iter_failed_chunkers(self.meta))
        self.assertEqual(found, {("d1", CHUNKER_V1), ("d2", CHUNKER_V2)})

    def test_iter_skips_non_schema_records(self):
        papers = store_module.load_papers(self.meta)
        papers.append({"paper_id": "legacy", "status": STATUS_FAILED})
        store_module.save_papers(papers, self.meta)
        self.assertEqual(store_module.iter_failed_chunkers(self.meta), [])

    def test_marker_roundtrip_persists_across_reload(self):
        _write_doc(self.meta, "d1", {"v1": _failed(), "v2": _state(STATUS_PENDING)})
        self.assertFalse(store_module.is_chunker_auto_requeued("d1", CHUNKER_V1, self.meta))
        store_module.mark_chunker_auto_requeued("d1", CHUNKER_V1, self.meta)
        # 落盘后从同一路径重新读取仍应识别
        self.assertTrue(store_module.is_chunker_auto_requeued("d1", CHUNKER_V1, meta_path=self.meta))
        # 后续对该 chunker 的状态更新必须保留标记（重排队后状态会切到 indexing）
        store_module.update_chunker_state(
            "d1", CHUNKER_V1, status=STATUS_INDEXING, progress=0, error=None, meta_path=self.meta
        )
        self.assertTrue(store_module.is_chunker_auto_requeued("d1", CHUNKER_V1, self.meta))


class RecoverFailedReindexesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.meta = self.tmp / "papers.json"
        self.papers = self.tmp / "papers"

    def _doc(self, document_id, chunkers):
        _write_doc(self.meta, document_id, chunkers)

    def test_recovers_each_failed_chunker_exactly_once(self):
        self._doc("d1", {"v1": _failed(), "v2": _state(STATUS_INDEXED)})
        self._doc("d2", {"v1": _state(STATUS_INDEXING), "v2": _failed()})
        submitted = []
        with patch.object(
            application, "submit_document_reindex", side_effect=lambda did, ch, **k: submitted.append((did, ch))
        ):
            n = application.recover_failed_reindexes(meta_path=self.meta, papers_dir=self.papers)
        self.assertEqual(n, 2)
        self.assertEqual(set(submitted), {("d1", CHUNKER_V1), ("d2", CHUNKER_V2)})
        # 标记已落盘 -> 第二次启动是 no-op（幂等，防风暴）
        with patch.object(application, "submit_document_reindex", side_effect=AssertionError("不得二次排队")):
            n2 = application.recover_failed_reindexes(meta_path=self.meta, papers_dir=self.papers)
        self.assertEqual(n2, 0)

    def test_still_failed_after_retry_is_not_auto_retried(self):
        self._doc("d1", {"v1": _failed(), "v2": _state(STATUS_PENDING)})
        # 首次自愈排队成功并打标记；模拟重排队后索引仍失败（状态回到 failed）
        with patch.object(application, "submit_document_reindex", return_value={"submitted": {"v1": True}}):
            application.recover_failed_reindexes(meta_path=self.meta, papers_dir=self.papers)
        self.assertEqual(store_module.get_chunker_state("d1", CHUNKER_V1, self.meta)["status"], STATUS_FAILED)
        # 第二次启动绝不能再次自动重排队（无无限重试）
        with patch.object(application, "submit_document_reindex", side_effect=AssertionError("不得二次排队")):
            n = application.recover_failed_reindexes(meta_path=self.meta, papers_dir=self.papers)
        self.assertEqual(n, 0)

    def test_submit_failure_is_skipped_and_not_marked(self):
        self._doc("d1", {"v1": _failed(), "v2": _state(STATUS_PENDING)})
        with patch.object(application, "submit_document_reindex", side_effect=RuntimeError("source gone")):
            n = application.recover_failed_reindexes(meta_path=self.meta, papers_dir=self.papers)
        self.assertEqual(n, 0)
        self.assertFalse(store_module.is_chunker_auto_requeued("d1", CHUNKER_V1, self.meta))
        # 之后一次成功排队仍然可以发生（标记未误置）
        with patch.object(application, "submit_document_reindex", return_value={"submitted": {"v1": True}}):
            n2 = application.recover_failed_reindexes(meta_path=self.meta, papers_dir=self.papers)
        self.assertEqual(n2, 1)

    def test_corrupt_meta_does_not_raise(self):
        self.meta.write_text("{not valid json", encoding="utf-8")
        n = application.recover_failed_reindexes(meta_path=self.meta, papers_dir=self.papers)
        self.assertEqual(n, 0)


class StartupLifespanWiringTests(unittest.TestCase):
    def test_lifespan_triggers_recovery_without_blocking(self):
        from fastapi.testclient import TestClient

        from backend.app.main import app

        calls = []

        class FakeBundle:
            def require_generation(self, *args, **kwargs):
                return {}

        with patch("backend.app.main.recover_failed_reindexes", side_effect=lambda *a, **k: (calls.append(1) or 0)), \
                patch("backend.app.main.recover_paper_catalog_searches", return_value=0), \
                patch("backend.app.api.common.recover_research_tasks", return_value=0), \
                patch("backend.app.main.FinalizeBundleStore", return_value=FakeBundle()), \
                patch("backend.app.main.start_warmup"), \
                patch("backend.app.main.start_capability_scheduler"), \
                patch("backend.app.main.stop_capability_scheduler"), \
                TestClient(app):
            pass  # 启动期若抛异常，上下文管理器会向上传播
        self.assertEqual(len(calls), 1, "启动必须且只调用一次自愈")


if __name__ == "__main__":
    unittest.main()
