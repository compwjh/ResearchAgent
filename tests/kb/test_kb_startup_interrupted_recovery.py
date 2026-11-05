"""服务重启后残留 `indexing` 的收敛与重排语义。

覆盖两类真实事故：
- 启动收敛函数已实现却从未被 lifespan 调用，残留 `indexing 0%` 永久卡住；
- `submit_document_reindex()` 先写 `indexing` 再提交任务，提交被去重
  拒绝或抛异常时同样留下永久 `indexing`。

全部使用临时 meta_path / papers_dir，不触碰真实 `data/kb/papers.json`。
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.knowledge_base import application
from backend.app.knowledge_base.infrastructure import store as store_module
from backend.app.knowledge_base.infrastructure.store import (
    AUTO_REQUEUED_CHUNKERS,
    CHUNKER_V1,
    CHUNKER_V2,
    STATUS_FAILED,
    STATUS_INDEXED,
    STATUS_INDEXING,
)

SCHEMA = "knowledge-document-v1"
RESTART_REASON = "服务重启导致中断"
MARKED_AT = "2026-11-05T15:47:39+00:00"


def _state(status: str, error=None) -> dict:
    return {
        "status": status,
        "chunk_count": 0,
        "progress": 100 if status == STATUS_INDEXED else 0,
        "error": error,
    }


def _write_doc(meta: Path, document_id: str, chunkers: dict, extra: dict | None = None) -> None:
    papers = store_module.load_papers(meta)
    record = {
        "schema_version": SCHEMA,
        "document_id": document_id,
        "file_name": f"{document_id}.md",
        "chunkers": chunkers,
    }
    record.update(extra or {})
    papers.append(record)
    store_module.save_papers(papers, meta)


def _reindex_fixture(tmp_path: Path) -> tuple[dict, Path, Path]:
    meta = tmp_path / "data" / "kb" / "papers.json"
    papers = tmp_path / "data" / "kb" / "papers"
    document = application.create_uploaded_document(
        "reindex.md", "text/markdown", b"# reindex\n", meta_path=meta, papers_dir=papers
    )["document"]
    # 提交重建需要已提交的索引代次（否则被 INDEX_REBUILD_REQUIRED 拦下）。
    finalizer = application.FinalizeBundleStore(tmp_path)
    finalizer.stage(
        "generation-test",
        candidate_collection="papers_rebuild_live",
        metadata=[document],
        manifests={},
        collection_fingerprint="a" * 64,
    )
    finalizer.commit("generation-test")
    return document, meta, papers


class MarkInterruptedClearsRequeueMarkerTests(unittest.TestCase):
    """收敛残留 indexing 时必须让一次性重排机会重新可用，真失败不得复活。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.meta = self.tmp / "papers.json"

    def test_interrupted_indexing_is_failed_and_marker_cleared(self):
        _write_doc(
            self.meta,
            "d1",
            {"v1": _state(STATUS_INDEXED), "v2": _state(STATUS_INDEXING)},
            {AUTO_REQUEUED_CHUNKERS: {CHUNKER_V2: MARKED_AT}},
        )
        marked = store_module.mark_interrupted_tasks(meta_path=self.meta, reason=RESTART_REASON)
        self.assertEqual(marked, 1)
        state = store_module.get_chunker_state("d1", CHUNKER_V2, self.meta)
        self.assertEqual(state["status"], STATUS_FAILED)
        self.assertEqual(state["error"], RESTART_REASON)
        self.assertFalse(
            store_module.is_chunker_auto_requeued("d1", CHUNKER_V2, self.meta),
            "被重启打断的版本必须清掉 auto_requeued 标记，否则自愈无法重排",
        )
        # 未被收敛的其它版本标记不受影响
        self.assertFalse(store_module.is_chunker_auto_requeued("d1", CHUNKER_V1, self.meta))

    def test_true_failed_record_keeps_requeue_marker(self):
        _write_doc(
            self.meta,
            "d1",
            {"v1": _state(STATUS_INDEXED), "v2": _state(STATUS_FAILED, "embedding OOM")},
            {AUTO_REQUEUED_CHUNKERS: {CHUNKER_V1: MARKED_AT, CHUNKER_V2: MARKED_AT}},
        )
        marked = store_module.mark_interrupted_tasks(meta_path=self.meta, reason=RESTART_REASON)
        self.assertEqual(marked, 0)
        # 真失败不动状态、不动标记，防重启风暴语义保留
        failed_state = store_module.get_chunker_state("d1", CHUNKER_V2, self.meta)
        self.assertEqual(failed_state["status"], STATUS_FAILED)
        self.assertEqual(failed_state["error"], "embedding OOM")
        self.assertTrue(store_module.is_chunker_auto_requeued("d1", CHUNKER_V2, self.meta))

    def test_marker_of_other_chunker_survives_convergence(self):
        _write_doc(
            self.meta,
            "d1",
            {"v1": _state(STATUS_INDEXING), "v2": _state(STATUS_INDEXING)},
            {AUTO_REQUEUED_CHUNKERS: {CHUNKER_V1: MARKED_AT, CHUNKER_V2: MARKED_AT}},
        )
        # 只把 v1 的标记清掉，v2 为真失败场景下的历史标记应保留
        store_module.mark_interrupted_tasks(meta_path=self.meta, reason=RESTART_REASON)
        self.assertFalse(store_module.is_chunker_auto_requeued("d1", CHUNKER_V1, self.meta))
        self.assertFalse(store_module.is_chunker_auto_requeued("d1", CHUNKER_V2, self.meta))

    def test_converged_document_is_requeued_once_by_startup_recovery(self):
        """收敛 + 自愈接线：重启打断的版本会被自动重排一次，仅一次。"""
        _write_doc(
            self.meta,
            "d1",
            {"v1": _state(STATUS_INDEXED), "v2": _state(STATUS_INDEXING)},
            {AUTO_REQUEUED_CHUNKERS: {CHUNKER_V2: MARKED_AT}},
        )
        store_module.mark_interrupted_tasks(meta_path=self.meta, reason=RESTART_REASON)
        submitted = []
        kw = {"meta_path": self.meta, "papers_dir": self.tmp / "papers"}
        with patch.object(
            application, "submit_document_reindex",
            side_effect=lambda did, ch, **k: submitted.append((did, ch)) or {"submitted": {ch: True}},
        ):
            self.assertEqual(application.recover_failed_reindexes(**kw), 1)
        self.assertEqual(submitted, [("d1", CHUNKER_V2)])
        with patch.object(application, "submit_document_reindex", side_effect=AssertionError("不得二次排队")):
            self.assertEqual(application.recover_failed_reindexes(**kw), 0)


class ReindexSubmissionRaceTests(unittest.TestCase):
    """`submit_document_reindex()` 不得在任务未被接受时留下 `indexing`。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.document, self.meta, self.papers = _reindex_fixture(self.tmp)

    def _submit(self, chunker: str, **kwargs):
        return application.submit_document_reindex(
            self.document["document_id"],
            chunker,
            meta_path=self.meta,
            papers_dir=self.papers,
            **kwargs,
        )

    def _state(self, chunker: str) -> dict:
        return store_module.get_chunker_state(self.document["document_id"], chunker, self.meta)

    def test_rejected_submission_keeps_state_and_marks_not_submitted(self):
        before = self._state(CHUNKER_V2)
        self.assertNotEqual(before["status"], STATUS_INDEXING)
        with patch.object(application, "submit_index_task", return_value=False):
            result = self._submit(CHUNKER_V2)
        self.assertEqual(result["submitted"], {CHUNKER_V2: False})
        after = self._state(CHUNKER_V2)
        self.assertNotEqual(after["status"], STATUS_INDEXING, "任务未被接受时不得写 indexing")
        self.assertEqual(after["status"], before["status"])
        self.assertEqual(after["progress"], before["progress"])

    def test_accepted_submission_marks_indexing(self):
        with patch.object(application, "submit_index_task", return_value=True):
            result = self._submit(CHUNKER_V2)
        self.assertEqual(result["submitted"], {CHUNKER_V2: True})
        state = self._state(CHUNKER_V2)
        self.assertEqual(state["status"], STATUS_INDEXING)
        self.assertEqual(state["progress"], 0)
        self.assertIsNone(state["error"])

    def test_submit_exception_rolls_back_to_failed_with_reason(self):
        """提交抛异常时回滚为 failed（固定文案），不得残留 indexing。"""
        prepared = self._state(CHUNKER_V2)
        with patch.object(application, "submit_index_task", side_effect=RuntimeError("executor down")):
            result = self._submit(CHUNKER_V2)
        self.assertEqual(result["submitted"], {CHUNKER_V2: False})
        state = self._state(CHUNKER_V2)
        self.assertEqual(state["status"], STATUS_FAILED)
        self.assertEqual(state["progress"], 0)
        self.assertEqual(state["error"], "索引任务提交失败")
        self.assertNotIn("executor down", state["error"])
        # 前置状态不是 failed，说明下面的「failed 不被覆盖」不是因为这里本来就失败
        self.assertNotEqual(prepared["status"], STATUS_FAILED)

    def test_task_finishing_before_indexing_write_keeps_terminal_state(self):
        """提交后瞬间落盘「与提交前不同」的终态时，提交方不得覆盖。

        守卫语义从「当前不是 failed」改为「当前与提交前一致」：runner 只要写过任何
        新状态都不覆盖，因此这里用一个非 failed 的瞬间终态（indexed）同样受保护。
        """

        def instant_terminal(paper_id, chunker, runner):
            # 模拟工作线程在 `submit_index_task()` 返回后、提交方写 indexing 前
            # 就跑完并落盘终态（`before` 是 pending，写入的 indexed 与之不同）。
            store_module.update_chunker_state(
                paper_id, chunker, status=STATUS_INDEXED, progress=100,
                chunk_count=3, error=None, meta_path=self.meta,
            )
            return True

        before = self._state(CHUNKER_V2)["status"]
        self.assertNotEqual(before, STATUS_INDEXED)
        with patch.object(application, "submit_index_task", side_effect=instant_terminal):
            result = self._submit(CHUNKER_V2)
        # 契约不变：任务确实被接受（路由依赖此布尔值判定 409）
        self.assertEqual(result["submitted"], {CHUNKER_V2: True})
        state = self._state(CHUNKER_V2)
        self.assertEqual(state["status"], STATUS_INDEXED, "runner 写入的终态不得被覆盖回 indexing")
        self.assertEqual(state["progress"], 100)

    def test_task_finishing_instantly_failed_after_submit_is_not_overwritten(self):
        """A-2 窄窗口保留：提交后瞬间失败（写入 failed）时提交方不得再写任何状态。"""

        def instant_failure(paper_id, chunker, runner):
            store_module.update_chunker_state(
                paper_id, chunker, status=STATUS_FAILED, progress=0,
                error="源文件在提交后被删除", meta_path=self.meta,
            )
            return True

        before = self._state(CHUNKER_V2)["status"]
        self.assertNotEqual(before, STATUS_FAILED)
        with patch.object(application, "submit_index_task", side_effect=instant_failure):
            result = self._submit(CHUNKER_V2)
        self.assertEqual(result["submitted"], {CHUNKER_V2: True})
        state = self._state(CHUNKER_V2)
        self.assertEqual(state["status"], STATUS_FAILED, "终态不得被覆盖回 indexing")
        self.assertEqual(state["progress"], 0)
        self.assertEqual(state["error"], "源文件在提交后被删除")

    def test_retry_from_failed_marks_indexing_when_runner_writes_nothing(self):
        """失败态点「重试」：提交成功且 runner 未写状态时，必须立刻变 indexing。

        这是真实回归修复点 —— 旧守卫只看「当前是否 failed」，会把提交前的陈旧 failed
        也一起保留，导致排队期间用户仍看到「索引失败」。
        """
        store_module.update_chunker_state(
            self.document["document_id"], CHUNKER_V2, status=STATUS_FAILED, progress=0,
            error="embedding OOM", meta_path=self.meta,
        )
        self.assertEqual(self._state(CHUNKER_V2)["status"], STATUS_FAILED)
        with patch.object(application, "submit_index_task", return_value=True):
            self.assertEqual(self._submit(CHUNKER_V2)["submitted"], {CHUNKER_V2: True})
        state = self._state(CHUNKER_V2)
        self.assertEqual(state["status"], STATUS_INDEXING, "陈旧 failed 重试后必须立刻进入 indexing")
        self.assertEqual(state["progress"], 0)
        self.assertIsNone(state["error"], "进入 indexing 必须清掉旧的失败原因")

    def test_retry_from_failed_keeps_indexed_written_by_runner(self):
        """陈旧 failed 重试，但 runner 已瞬间跑完写 indexed → 保留 indexed。"""

        def instant_indexed(paper_id, chunker, runner):
            store_module.update_chunker_state(
                paper_id, chunker, status=STATUS_INDEXED, progress=100,
                chunk_count=7, error=None, meta_path=self.meta,
            )
            return True

        store_module.update_chunker_state(
            self.document["document_id"], CHUNKER_V2, status=STATUS_FAILED, progress=0,
            error="embedding OOM", meta_path=self.meta,
        )
        self.assertEqual(self._state(CHUNKER_V2)["status"], STATUS_FAILED)
        with patch.object(application, "submit_index_task", side_effect=instant_indexed):
            self.assertEqual(self._submit(CHUNKER_V2)["submitted"], {CHUNKER_V2: True})
        state = self._state(CHUNKER_V2)
        self.assertEqual(state["status"], STATUS_INDEXED, "runner 已写终态时不得写回 indexing")
        self.assertEqual(state["progress"], 100)

    def test_all_chunkers_partial_rejection_is_reported_per_chunker(self):
        with patch.object(application, "submit_index_task", side_effect=[True, False]):
            result = self._submit("all")
        self.assertEqual(result["submitted"], {CHUNKER_V1: True, CHUNKER_V2: False})
        self.assertEqual(self._state(CHUNKER_V1)["status"], STATUS_INDEXING)
        self.assertNotEqual(self._state(CHUNKER_V2)["status"], STATUS_INDEXING)


class InterruptedTaskLifespanOrderTests(unittest.TestCase):
    """启动收敛必须先于自愈，否则自愈看不到被收敛的 failed。"""

    def test_lifespan_converges_interrupted_before_recover_failed(self):
        from fastapi.testclient import TestClient

        from backend.app.main import app

        order = []

        class FakeBundle:
            def require_generation(self, *args, **kwargs):
                return {}

        with patch("backend.app.main.tasks.mark_interrupted_on_startup",
                   side_effect=lambda *a, **k: order.append("mark_interrupted") or 0), \
                patch("backend.app.main.recover_failed_reindexes",
                      side_effect=lambda *a, **k: order.append("recover_failed") or 0), \
                patch("backend.app.main.recover_paper_catalog_searches", return_value=0), \
                patch("backend.app.api.common.recover_research_tasks", return_value=0), \
                patch("backend.app.main.FinalizeBundleStore", return_value=FakeBundle()), \
                patch("backend.app.main.start_warmup"), \
                patch("backend.app.main.start_capability_scheduler"), \
                patch("backend.app.main.stop_capability_scheduler"), \
                TestClient(app):
            pass  # 启动期若抛异常，上下文管理器会向上传播
        self.assertEqual(order, ["mark_interrupted", "recover_failed"])

    def test_convergence_failure_does_not_block_startup(self):
        from fastapi.testclient import TestClient

        from backend.app.main import app

        calls = []

        class FakeBundle:
            def require_generation(self, *args, **kwargs):
                return {}

        with patch("backend.app.main.tasks.mark_interrupted_on_startup",
                   side_effect=RuntimeError("metadata corrupt")), \
                patch("backend.app.main.recover_failed_reindexes",
                      side_effect=lambda *a, **k: calls.append("recover_failed") or 0), \
                patch("backend.app.main.recover_paper_catalog_searches", return_value=0), \
                patch("backend.app.api.common.recover_research_tasks", return_value=0), \
                patch("backend.app.main.FinalizeBundleStore", return_value=FakeBundle()), \
                patch("backend.app.main.start_warmup"), \
                patch("backend.app.main.start_capability_scheduler"), \
                patch("backend.app.main.stop_capability_scheduler"), \
                TestClient(app):
            pass
        # 收敛失败不得中断 lifespan，也不得阻断其后的自愈
        self.assertEqual(calls, ["recover_failed"])

    def test_lifespan_converges_real_interrupted_task_end_to_end(self):
        """端到端：真实 `tasks.mark_interrupted_on_startup()`（不 patch）走完 lifespan 收敛。

        只把默认元数据路径指向临时文件（两层模块各自按默认名查找 `meta_path`），
        其余接线保持真实；启动自愈被替换为桩，避免真的触发重排。
        """
        from fastapi.testclient import TestClient

        from backend.app.knowledge_base.infrastructure import tasks as tasks_module
        from backend.app.main import app

        tmp = Path(tempfile.mkdtemp())
        meta = tmp / "papers.json"
        _write_doc(
            meta,
            "d-real",
            {"v1": _state(STATUS_INDEXED), "v2": _state(STATUS_INDEXING)},
            {AUTO_REQUEUED_CHUNKERS: {CHUNKER_V2: MARKED_AT}},
        )
        self.assertEqual(
            store_module.get_chunker_state("d-real", CHUNKER_V2, meta)["status"], STATUS_INDEXING
        )

        class FakeBundle:
            def require_generation(self, *args, **kwargs):
                return {}

        with patch.object(store_module, "KB_META_PATH", meta), \
                patch.object(tasks_module.store, "KB_META_PATH", meta), \
                patch("backend.app.main.recover_failed_reindexes", return_value=0) as recover, \
                patch("backend.app.main.recover_paper_catalog_searches", return_value=0), \
                patch("backend.app.api.common.recover_research_tasks", return_value=0), \
                patch("backend.app.main.FinalizeBundleStore", return_value=FakeBundle()), \
                patch("backend.app.main.start_warmup"), \
                patch("backend.app.main.start_capability_scheduler"), \
                patch("backend.app.main.stop_capability_scheduler"), \
                TestClient(app):
            pass

        state = store_module.get_chunker_state("d-real", CHUNKER_V2, meta)
        self.assertEqual(state["status"], STATUS_FAILED)
        self.assertEqual(state["progress"], 0)
        self.assertEqual(state["error"], RESTART_REASON)
        # 被重启打断的版本必须重新获得一次性重排机会（标记清除），否则自愈不会接手
        self.assertFalse(store_module.is_chunker_auto_requeued("d-real", CHUNKER_V2, meta))
        # 收敛早于自愈：接线顺序仍由真实调用顺序保证
        recover.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
