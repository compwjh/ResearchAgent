"""双版本状态与异步任务单测（spec-012）。

覆盖：双版本状态读写、旧记录兼容、重启残留标记、任务去重与进度回写。
全部用临时 meta_path 隔离，不触碰真实 `data/kb/papers.json`。
"""

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.knowledge_base.infrastructure import index as index_module
from backend.app.knowledge_base.infrastructure import store as store_module
from backend.app.knowledge_base.infrastructure import tasks as tasks_module
from backend.app.knowledge_base.infrastructure.parse import PdfParseError
from backend.app.knowledge_base.infrastructure.store import (
    CHUNKER_V1,
    CHUNKER_V2,
    STATUS_FAILED,
    STATUS_INDEXED,
    STATUS_INDEXING,
    STATUS_PENDING,
)


class StoreChunkerStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.meta = self.tmp / "papers.json"

    def test_new_record_has_both_versions(self):
        record = store_module.new_record("a.pdf")
        self.assertEqual(set(record.chunkers), {CHUNKER_V1, CHUNKER_V2})
        self.assertEqual(record.chunkers[CHUNKER_V1]["status"], STATUS_INDEXING)
        self.assertEqual(record.chunkers[CHUNKER_V2]["status"], STATUS_PENDING)

    def test_update_and_get_state(self):
        record = store_module.new_record("a.pdf")
        store_module.upsert_paper(record, meta_path=self.meta)
        store_module.update_chunker_state(
            record.paper_id, CHUNKER_V2, status=STATUS_INDEXING, progress=45,
            chunk_count=7, meta_path=self.meta,
        )
        state = store_module.get_chunker_state(record.paper_id, CHUNKER_V2, meta_path=self.meta)
        self.assertEqual(state["status"], STATUS_INDEXING)
        self.assertEqual(state["progress"], 45)
        self.assertEqual(state["chunk_count"], 7)

    def test_update_missing_paper_returns_none(self):
        self.assertIsNone(store_module.update_chunker_state("nope", CHUNKER_V1, meta_path=self.meta))

    def test_progress_is_clamped(self):
        record = store_module.new_record("a.pdf")
        store_module.upsert_paper(record, meta_path=self.meta)
        store_module.update_chunker_state(record.paper_id, CHUNKER_V2, progress=999, meta_path=self.meta)
        self.assertEqual(
            store_module.get_chunker_state(record.paper_id, CHUNKER_V2, meta_path=self.meta)["progress"],
            100,
        )

    def test_legacy_record_inherits_top_level_status(self):
        """旧记录无 chunkers：必须沿用顶层 status，不能一律按 indexing 补，

        否则启动扫描会把已索引的旧论文误判为中断任务并标记 failed。
        """
        legacy = {"paper_id": "old", "file_name": "o.pdf", "status": STATUS_INDEXED,
                  "chunk_count": 42, "error": None}
        states = store_module.ensure_chunkers(legacy)
        self.assertEqual(states[CHUNKER_V1]["status"], STATUS_INDEXED)
        self.assertEqual(states[CHUNKER_V1]["chunk_count"], 42)
        self.assertEqual(states[CHUNKER_V2]["status"], STATUS_PENDING)

    def test_mark_interrupted_skips_indexed_legacy(self):
        self.meta.write_text(
            '[{"paper_id":"old","file_name":"o.pdf","status":"indexed","chunk_count":42}]',
            encoding="utf-8",
        )
        self.assertEqual(store_module.mark_interrupted_tasks(meta_path=self.meta), 0)

    def test_mark_interrupted_flags_indexing(self):
        self.meta.write_text(
            '[{"paper_id":"p","file_name":"a.pdf","status":"indexed","chunk_count":0,'
            '"chunkers":{"v1":{"status":"indexing","chunk_count":0,"progress":30,"error":null},'
            '"v2":{"status":"indexing","chunk_count":0,"progress":10,"error":null}}}]',
            encoding="utf-8",
        )
        self.assertEqual(store_module.mark_interrupted_tasks(meta_path=self.meta), 2)
        self.assertEqual(
            store_module.get_chunker_state("p", CHUNKER_V1, meta_path=self.meta)["status"],
            STATUS_FAILED,
        )


class TaskSubmissionTests(unittest.TestCase):
    def setUp(self):
        tasks_module.shutdown(wait=True)

    def tearDown(self):
        tasks_module.shutdown(wait=False)

    def test_duplicate_submission_is_rejected(self):
        writes = []
        real_update = store_module.update_chunker_state
        store_module.update_chunker_state = lambda *a, **k: (
            writes.append(k.get("progress")), {"status": "indexing"}
        )[1]
        try:
            def slow_runner(progress):
                progress(10)
                time.sleep(0.6)
                progress(100)

            first = tasks_module.submit_index_task("px", CHUNKER_V2, slow_runner)
            second = tasks_module.submit_index_task("px", CHUNKER_V2, slow_runner)
            self.assertTrue(first)
            self.assertFalse(second, "同一任务重复提交必须去重")
            self.assertEqual(tasks_module.running_count(), 1)
            time.sleep(1.2)
            self.assertEqual(tasks_module.running_count(), 0)
            self.assertEqual(writes[-1], 100, "进度应被回写")
        finally:
            store_module.update_chunker_state = real_update

    def test_runner_exception_is_contained(self):
        """线程带异常退出时状态不能永远停在 indexing。"""
        updates = []
        real_update = store_module.update_chunker_state
        store_module.update_chunker_state = lambda *a, **k: updates.append((a, k))
        try:
            def boom(_progress):
                raise RuntimeError("ollama down")

            tasks_module.submit_index_task("px", CHUNKER_V2, boom)
            time.sleep(0.6)
            failed = [call for call in updates if call[1].get("status") == STATUS_FAILED]
            self.assertTrue(failed, "异常应被兜底并标记 failed")
        finally:
            store_module.update_chunker_state = real_update

    def test_run_index_task_sync_propagates_runner_result(self):
        """同步索引必须把 runner 结果原样交给调用方。

        `_guarded_run` 曾调用 runner 却不返回其结果，使 `run_index_task_sync`
        恒为 None；导入/上传把已经成功的索引读成失败（KB_IMPORT_FAILED）。
        """
        payload = {"status": STATUS_INDEXED, "chunk_count": 5}
        result = tasks_module.run_index_task_sync(
            "sync-ok", CHUNKER_V1, lambda _progress: payload
        )
        self.assertEqual(result, payload)

    def test_run_index_task_sync_reports_runner_failure(self):
        updates = []
        real_update = store_module.update_chunker_state
        store_module.update_chunker_state = lambda *a, **k: updates.append((a, k))
        try:
            def boom(_progress):
                raise RuntimeError("ollama down")

            result = tasks_module.run_index_task_sync("sync-boom", CHUNKER_V1, boom)
            self.assertIsInstance(result, dict)
            self.assertTrue(result.get("error"), "失败必须带给调用方可诊断的原因")
            self.assertTrue(
                any(call[1].get("status") == STATUS_FAILED for call in updates)
            )
        finally:
            store_module.update_chunker_state = real_update


class IndexPaperChunkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.meta = self.tmp / "papers.json"
        self.record = store_module.new_record("b.pdf")
        store_module.upsert_paper(self.record, meta_path=self.meta)
        self.pages = [
            (1, "正文内容。" * 60),
            (2, "References\n\n[1] A. Author, \"T,\" in ICML, 2023."),
        ]
        self.patched = [
            patch.object(index_module, "extract_pages_normalized", return_value=self.pages),
            patch.object(index_module, "upsert_chunks", return_value=3),
            patch.object(index_module, "delete_paper_chunker", lambda *a, **k: None),
        ]
        for item in self.patched:
            item.start()

    def tearDown(self):
        for item in self.patched:
            item.stop()

    def test_success_path(self):
        progressed = []
        result = index_module.index_paper_chunker(
            self.record, "b.pdf", CHUNKER_V2, progress=progressed.append,
            llm=lambda p: "[]", meta_path=self.meta,
            destination_collection=index_module.KB_COLLECTION,
        )
        state = result["chunkers"][CHUNKER_V2]
        self.assertEqual(state["status"], STATUS_INDEXED)
        self.assertEqual(state["chunk_count"], 3)
        self.assertEqual(state["progress"], 100)
        self.assertEqual(progressed[-1], 100)
        self.assertEqual(progressed, sorted(progressed))

    def test_deletes_old_points_before_upsert(self):
        """T3：重建前必须按 paper_id + chunker 先删旧点，否则残留污染检索。"""
        deleted = []
        with patch.object(index_module, "delete_paper_chunker",
                          lambda pid, ch, client=None, **kwargs: deleted.append((pid, ch))):
            index_module.index_paper_chunker(
                self.record,
                "b.pdf",
                CHUNKER_V1,
                meta_path=self.meta,
                destination_collection=index_module.KB_COLLECTION,
            )
        self.assertIn((self.record.paper_id, CHUNKER_V1), deleted)

    def test_parse_failure_is_recorded(self):
        with patch.object(index_module, "extract_pages_normalized",
                          side_effect=PdfParseError("PDF 已加密")):
            result = index_module.index_paper_chunker(self.record, "c.pdf", CHUNKER_V1,
                                                      meta_path=self.meta,
                                                      destination_collection=index_module.KB_COLLECTION)
        state = result["chunkers"][CHUNKER_V1]
        self.assertEqual(state["status"], STATUS_FAILED)
        self.assertIn("加密", state["error"] or "")

    def test_low_text_is_failed_with_reason(self):
        with patch.object(index_module, "extract_pages_normalized", return_value=[(1, "  ")]):
            result = index_module.index_paper_chunker(self.record, "d.pdf", CHUNKER_V1,
                                                      meta_path=self.meta,
                                                      destination_collection=index_module.KB_COLLECTION)
        state = result["chunkers"][CHUNKER_V1]
        self.assertEqual(state["status"], STATUS_FAILED)
        self.assertIn("扫描件", state["error"] or "")

    def test_embedding_failure_is_recorded(self):
        with patch.object(index_module, "upsert_chunks",
                          side_effect=index_module.EmbeddingError("OOM")):
            result = index_module.index_paper_chunker(self.record, "e.pdf", CHUNKER_V1,
                                                      meta_path=self.meta,
                                                      destination_collection=index_module.KB_COLLECTION)
        state = result["chunkers"][CHUNKER_V1]
        self.assertEqual(state["status"], STATUS_FAILED)
        self.assertIn("OOM", state["error"] or "")


if __name__ == "__main__":
    unittest.main()
