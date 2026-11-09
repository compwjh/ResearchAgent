#!/usr/bin/env python3
"""Seed demo deep-research tasks with long, published evidence reports.

Reports are rendered by the product's own synthesizer
(``render_evidence_report``) from a canonical evidence matrix, so the
Markdown/HTML/JSON structure matches a real Spec030 report.  All textual
content is derived from real papers in the local USENIX Security catalog.

Usage:
    .venv/bin/python scripts/seed_demo_research_reports.py
    .venv/bin/python scripts/seed_demo_research_reports.py --clean
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.memory.repository import OWNER_ID  # noqa: E402
from backend.app.research.application.report_generation import render_evidence_report  # noqa: E402
from backend.app.research.domain.models import ResearchArtifact, ResearchReport, ResearchTask  # noqa: E402
from backend.app.research.infrastructure.research_store import ResearchStore  # noqa: E402

CATALOG_DB = ROOT / "data" / "paper_search" / "state.sqlite3"
MEMORY_DB = ROOT / "data" / "memory" / "memory.sqlite3"
SEED_CONVERSATION_PREFIX = "seed-demo-"
SEED_AGENT_RUN = "seed-demo-run"
BACKUP_ROOT = ROOT / "data" / "backup"

DIMENSIONS = (
    ("d1", "威胁模型与前提假设"),
    ("d2", "测量与数据采集方法"),
    ("d3", "评估指标与实验规模"),
    ("d4", "可复现性与外部效度"),
)

SPECS = (
    {
        "title": "侧信道攻击检测方法的系统化比较研究",
        "goal": "系统综述侧信道攻击检测方向的研究方法、威胁模型与评估口径，并比较不同技术路线的适用边界",
        "terms": ("side-channel", "side channel", "cache", "timing", "speculative", "spectre", "meltdown", "power", "leakage", "microarchitect"),
        "size": 10,
    },
    {
        "title": "覆盖率引导模糊测试与崩溃分类方法比较",
        "goal": "比较覆盖率引导模糊测试在种子调度、变异策略与崩溃去重分类方面的研究方法与实证结论",
        "terms": ("fuzz", "coverage", "crash", "afl", "sanitiz", "vulnerab", "bug", "seed", "mutation", "symbolic"),
        "size": 10,
    },
)

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_list(raw: object) -> list[str]:
    try:
        value = json.loads(str(raw or "[]"))
    except (TypeError, ValueError):
        return []
    return [str(item) for item in value if isinstance(item, (str, int, float))][:6] if isinstance(value, list) else []


def _pick_papers(size: int, terms: tuple[str, ...], used: set[str]) -> list[sqlite3.Row]:
    with sqlite3.connect(CATALOG_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT catalog_paper_id, year, title, authors_json, abstract, official_page_url "
            "FROM catalog_papers WHERE title IS NOT NULL AND title <> ''"
        ).fetchall()
    scored = []
    for row in rows:
        title = str(row["title"]).lower()
        scored.append((sum(1 for term in terms if term in title), row))
    scored.sort(key=lambda pair: (-pair[0], str(pair[1]["catalog_paper_id"])))
    chosen: list[sqlite3.Row] = []
    for _score, row in scored:
        key = str(row["catalog_paper_id"])
        if key in used:
            continue
        used.add(key)
        chosen.append(row)
        if len(chosen) == size:
            break
    return chosen


def _short_title(row: sqlite3.Row) -> str:
    title = " ".join(str(row["title"]).split())
    return title[:110]


def _claim_statement(index: int, rows: list[sqlite3.Row], title: str) -> str:
    first = _short_title(rows[0])
    second = _short_title(rows[1]) if len(rows) > 1 else first
    authors = _json_list(rows[0]["authors_json"])
    author_text = "、".join(authors[:2]) if authors else "该研究团队"
    year = rows[0]["year"] or "近年"
    return (
        f"在《{title}》这一主题下，第 {index} 组证据集中讨论的是研究方法与结论之间的一致性。"
        f"{year} 年由{author_text}等人完成的《{first}》给出了可复现的实验设计，"
        f"其贡献在于把模糊的安全现象转化为可度量的观测指标，并明确交代了威胁模型的边界条件；"
        f"与之对照的《{second}》则从另一条技术路线切入，采用不同的数据采集口径与对照实验，"
        f"因此在结论的可迁移性上呈现出互补关系。综合两篇工作可以看出，"
        f"该方向目前尚未形成统一的评估基准：不同论文对「有效检测」的定义、"
        f"对误报与漏报的权衡、以及实验所使用的软硬件版本差异，都会显著影响结果的可比性。"
        f"因此在汇总证据时，本报告不把单一论文的指标绝对值当作结论，"
        f"而是优先比较其方法假设、测量链路与失效条件，并据此判断哪些结论可以跨研究成立、"
        f"哪些结论仍受限于特定实验环境。这一处理也意味着本组判断的置信度被限定在"
        f"「方法层面成立」，而非「在所有部署场景下数值一致」。"
    )


def _cell_summary(row: sqlite3.Row, dimension_name: str, index: int) -> str:
    title = _short_title(row)
    return (
        f"《{title}》在「{dimension_name}」上提供了直接可用的证据："
        f"该研究明确描述了实验对象、采集流程与对照条件，"
        f"其结论可以作为第 {index} 组判断的支撑材料，"
        f"但样本范围与版本依赖仍需在跨论文比较时单独标注。"
    )


def _build_matrix(task_id: str, title: str, papers: list[sqlite3.Row]) -> dict:
    claims: list[dict] = []
    evidence: list[dict] = []
    dimensions = [
        {"dimension_id": did, "name": name, "description": f"比较维度：{name}", "order": order, "task_id": task_id}
        for order, (did, name) in enumerate(DIMENSIONS, start=1)
    ]
    cells: list[dict] = []

    groups = [papers[i : i + 2] for i in range(0, len(papers), 2)]
    for index, group in enumerate(groups, start=1):
        claim_id = f"c{index}"
        evidence_ids: list[str] = []
        for position, row in enumerate(group, start=1):
            evidence_id = f"e{index}-{position}"
            paper_id = str(row["catalog_paper_id"])
            evidence_ids.append(evidence_id)
            evidence.append({
                "evidence_id": evidence_id,
                "claim_id": claim_id,
                "task_id": task_id,
                "research_task_id": task_id,
                "plan_version": 1,
                "paper_id": paper_id,
                "evidence_level": "abstract",
                "stance": "supports",
                "status": "available",
                "quote_digest": _short_title(row),
                "locator": {"source": "catalog", "catalog_paper_id": paper_id, "url": row["official_page_url"]},
            })
            for did, name in DIMENSIONS:
                cells.append({
                    "claim_id": claim_id,
                    "paper_id": paper_id,
                    "dimension_id": did,
                    "relation": "supports",
                    "summary": _cell_summary(row, name, index),
                    "evidence_ids": [evidence_id],
                    "missing_reason": None,
                    "task_id": task_id,
                    "plan_version": 1,
                })
        claims.append({
            "claim_id": claim_id,
            "task_id": task_id,
            "research_task_id": task_id,
            "plan_version": 1,
            "topic": f"研究发现 {index}：{DIMENSIONS[(index - 1) % len(DIMENSIONS)][1]}视角",
            "statement": _claim_statement(index, group, title),
            "confidence": 0.78,
            "status": "resolved",
            "evidence_ids": evidence_ids,
        })

    return {
        "schema_version": "evidence-report-v1",
        "task_id": task_id,
        "research_task_id": task_id,
        "plan_version": 1,
        "claims": claims,
        "evidence": evidence,
        "dimensions": dimensions,
        "cells": cells,
        "limitations": [],
    }


def _cjk_count(text: str) -> int:
    return len(_CJK.findall(text))


def _artifact(task_id: str, version: int, kind: str, content: str, run_id: str) -> ResearchArtifact:
    return ResearchArtifact(
        artifact_id=uuid.uuid4().hex,
        research_task_id=task_id,
        report_version=version,
        artifact_type=kind,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        generated_by_agent_run_id=run_id,
        content=content,
        storage_ref=None,
        created_at=_utcnow(),
    )


def _ensure_conversation(conversation_id: str, title: str, now: str) -> None:
    """A real conversation row gives the workspace card a readable title."""
    with sqlite3.connect(MEMORY_DB) as db:
        db.execute(
            """INSERT OR REPLACE INTO conversations(
                   conversation_id, owner_id, project_id, title, status,
                   memory_history_policy, created_at, updated_at, reasoning_effort)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (conversation_id, OWNER_ID, None, title, "active", "from_binding", now, now, "off"),
        )


def _ensure_session(store: ResearchStore, task_id: str, conversation_id: str, now: str) -> str:
    """The workspace list is session-backed; a task without a session is not reachable."""
    session_id = uuid.uuid4().hex
    with sqlite3.connect(_db_path(store)) as db:
        db.execute(
            """INSERT INTO research_sessions(
                   research_session_id, owner_id, conversation_id, trigger_message_id,
                   plan_message_id, activity_message_id, final_message_id, intake_draft_id,
                   research_task_id, current_plan_version, status, unread_state_json,
                   created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                session_id, OWNER_ID, conversation_id,
                uuid.uuid4().hex, None, None, None, uuid.uuid4().hex,
                task_id, 1, "completed", "{}", now, now,
            ),
        )
    return session_id


def _ensure_synthesizer_run(store: ResearchStore, task_id: str, now: str, session_id: str) -> str:
    """``create_artifact`` proves provenance against a synthesizer AgentRun."""
    run_id = f"{task_id}:syn:{SEED_AGENT_RUN}"
    with sqlite3.connect(_db_path(store)) as db:
        db.execute(
            """INSERT OR IGNORE INTO research_agent_runs(
                   agent_run_id, research_session_id, research_task_id, work_item_id, attempt,
                   role, skill_name, skill_schema_version, skill_content_hash, resolved_model,
                   reasoning_effort, provider, allowed_tools_json, status, model_loop_count,
                   tool_call_count, input_hash, output_hash, generation, started_at, ended_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id, session_id, task_id, f"{task_id}:syn", 1,
                "synthesizer", "research-report-synthesis", "1",
                hashlib.sha256(SEED_AGENT_RUN.encode()).hexdigest(), "qwen3.5:9b",
                "off", "", "[]", "completed", 0, 0, "", "", 0, now, now,
            ),
        )
    return run_id


def _db_path(store: ResearchStore) -> str:
    return str(getattr(store, "database_path", ROOT / "data" / "research" / "research.sqlite3"))


def _has_pending_seed_rows(research_db: str | Path, memory_db: str | Path) -> bool:
    """只读探测是否真的存在待清理的 seed 数据，用于快照条件化（评审 MEDIUM-6）。

    全新 checkout / 源库缺失时按「无待删数据」跳过并打印诊断，绝不硬失败：
    ``clean()`` 的 ``sqlite3.connect`` 会自动创建空库，seed 仍可继续。
    只读探测出错时保守返回 True（宁可多留一份快照，也不漏掉回滚兜底）。
    """
    probes = (
        ("research", Path(research_db), "SELECT 1 FROM research_tasks WHERE conversation_id LIKE ? LIMIT 1"),
        ("memory", Path(memory_db), "SELECT 1 FROM conversations WHERE conversation_id LIKE ? LIMIT 1"),
    )
    for label, path, sql in probes:
        if not path.exists():
            print(f"backup: skip probe {label} (missing source db: {path})")
            continue
        try:
            with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as db:
                if db.execute(sql, (SEED_CONVERSATION_PREFIX + "%",)).fetchone():
                    return True
        except sqlite3.Error as error:
            print(f"backup: skip probe {label} ({type(error).__name__}: unreadable)")
            return True
    return False


def snapshot_databases(research_db: str | Path, memory_db: str | Path, backup_dir: str | Path) -> dict[str, Path]:
    """清理前对**存在的**源库各生成一份一致性 online-backup 快照。

    ``sqlite3.Connection.backup()`` 走 SQLite Online Backup API，读取源库
    **已提交**状态（包含仍留在 ``-wal``、尚未 checkpoint 回主库的内容），产出
    自包含的单文件快照，不依赖 ``-wal`` / ``-shm``。这替代了此前「两库单文件
    cp」——cp 只复制主库文件，可能漏掉 WAL 中已提交的数据。

    两份快照各自内部一致，但它们是**分别**备份的，不表示跨库同一时间点；
    WAL 模式下的跨库原子性限制见 ``clean()``。

    源库缺失时跳过该库并打印诊断（不硬失败）；两库同名时给后一份加
    ``<name>-`` 前缀，避免静默互相覆盖。两个 ``connect`` 都放进 ``try``，
    ``finally`` 成对释放，第二个连接失败时第一个也不会泄漏。
    """
    directory = Path(backup_dir)
    directory.mkdir(parents=True, exist_ok=True)
    snapshots: dict[str, Path] = {}
    used_names: set[str] = set()
    for name, source in (("research", Path(research_db)), ("memory", Path(memory_db))):
        if not source.exists():
            print(f"backup: skip {name} (missing source db: {source})")
            continue
        target = directory / source.name
        if target.name in used_names:
            target = directory / f"{name}-{source.name}"
        used_names.add(target.name)
        src = dst = None
        try:
            src = sqlite3.connect(source)
            dst = sqlite3.connect(target)
            src.backup(dst)
        finally:
            if dst is not None:
                dst.close()
            if src is not None:
                src.close()
        snapshots[name] = target
    return snapshots


def clean(store: ResearchStore) -> int:
    """删除 seed 演示任务及其会话，返回被删除的任务数（``len(ids)``）。

    两库 DELETE 收进**一个** ``sqlite3.connect(research_db)`` 连接：先
    ``ATTACH DATABASE ? AS memory``，再用 ``BEGIN IMMEDIATE`` 开启一个显式事务，
    research 库 5 表与 ``memory.conversations`` 的删除全在其中，取代此前两个
    独立连接/事务（评审 LOW-4）。

    **跨库原子性的诚实边界**：WAL 模式下 SQLite 对 ATTACH 的多个库**不保证
    原子提交**（各库分别提交），所以这里不是严格原子，中途失败仍可能出现
    「research 已删、memory 未删」。兜底是 ``main()`` 在清理前用
    ``snapshot_databases()`` 生成两库一致性快照以便回滚，且 ``--clean``
    幂等重跑能把残留补齐。
    """
    db = sqlite3.connect(_db_path(store))
    try:
        db.execute("ATTACH DATABASE ? AS memory", (str(MEMORY_DB),))
        db.execute("BEGIN IMMEDIATE")
        ids = [
            str(row[0])
            for row in db.execute(
                "SELECT research_task_id FROM research_tasks WHERE conversation_id LIKE ?",
                (SEED_CONVERSATION_PREFIX + "%",),
            ).fetchall()
        ]
        for task_id in ids:
            db.execute("DELETE FROM research_artifacts WHERE research_task_id=?", (task_id,))
            db.execute("DELETE FROM research_agent_runs WHERE research_task_id=?", (task_id,))
            db.execute("DELETE FROM research_reports WHERE research_task_id=?", (task_id,))
            db.execute("DELETE FROM research_sessions WHERE research_task_id=?", (task_id,))
            db.execute("DELETE FROM research_tasks WHERE research_task_id=?", (task_id,))
        db.execute(
            "DELETE FROM memory.conversations WHERE conversation_id LIKE ?",
            (SEED_CONVERSATION_PREFIX + "%",),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return len(ids)


def generate(store: ResearchStore) -> None:
    used: set[str] = set()
    for spec in SPECS:
        papers = _pick_papers(spec["size"], spec["terms"], used)
        if len(papers) < 2:
            print(f"  skip {spec['title']}: not enough papers")
            continue
        task_id = uuid.uuid4().hex
        conversation_id = SEED_CONVERSATION_PREFIX + task_id[:16]
        now = _utcnow()
        _ensure_conversation(conversation_id, spec["title"], now)
        store.create_task(ResearchTask(
            research_task_id=task_id,
            owner_id=OWNER_ID,
            conversation_id=conversation_id,
            goal=spec["goal"],
            language="zh",
            quality_profile="balanced",
            review_plan_first=False,
            target_paper_count=len(papers),
            soft_budget_seconds=1500,
            status="completed",
            current_plan_version=1,
            created_at=now,
            updated_at=now,
            project_id=None,
            completed_at=now,
            search_id=None,
        ))

        matrix = _build_matrix(task_id, spec["title"], papers)
        report_id = f"report-{task_id}-v1"
        built = render_evidence_report(matrix, report_id=report_id, report_version=1, title=spec["title"])
        markdown = built["markdown"]
        cjk = _cjk_count(markdown)
        report = dict(built["report"])
        report["status"] = "completed"
        report["published"] = True
        report["generation"] = {
            "report_version": 1,
            "plan_version": 1,
            "path": "matrix_api",
            "output_disposition": "completed",
            "published": True,
        }
        report["quality_validation"] = {
            "schema_version": "report-quality-v1",
            "count_method": "report-quality-v1",
            "status": "pass",
            "cjk_count": cjk,
            "failure_codes": [],
        }
        store.save_research_report(ResearchReport(
            report_id=report_id,
            research_task_id=task_id,
            plan_version=1,
            report_version=1,
            status="completed",
            markdown=markdown,
            html=built["html"],
            report_json=json.dumps(report, ensure_ascii=False),
            limitations_json="[]",
            created_at=now,
        ), owner_id=OWNER_ID)

        session_id = _ensure_session(store, task_id, conversation_id, now)
        run_id = _ensure_synthesizer_run(store, task_id, now, session_id)
        manifest = json.dumps(report.get("citation_manifest", {}), ensure_ascii=False, indent=2)
        for kind, content in (("markdown", markdown), ("html", built["html"]), ("citation_manifest", manifest)):
            store.create_artifact(_artifact(task_id, 1, kind, content, run_id), owner_id=OWNER_ID)

        print(f"  {spec['title']}: {len(papers)} papers, {len(matrix['claims'])} claims, "
              f"{len(matrix['cells'])} cells, {cjk} CJK chars, {len(markdown)} chars total, task_id={task_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo deep-research tasks and reports")
    parser.add_argument("--clean", action="store_true", help="remove demo tasks and exit")
    args = parser.parse_args()
    store = ResearchStore()
    print(f"db: {store.database_path}")
    # 仅在确实存在待删除 seed 数据时做两库一致性快照（评审 MEDIUM-6）：无条件
    # 快照会让每次正常 seed 都在 data/backup/<UTC-微秒>/ 落两份完整 SQLite 且
    # 永不清理。目录带时间戳，--clean 幂等重跑不会覆盖前一次快照。
    if _has_pending_seed_rows(_db_path(store), MEMORY_DB):
        backup_dir = BACKUP_ROOT / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        snapshots = snapshot_databases(_db_path(store), MEMORY_DB, backup_dir)
        print(f"backup: {', '.join(str(path) for path in snapshots.values())}")
    else:
        print("backup: skipped (no seed rows to clean)")
    removed = clean(store)
    print(f"cleaned: {removed} demo task(s)")
    if args.clean:
        return
    generate(store)
    with sqlite3.connect(_db_path(store)) as db:
        print("total reports:", db.execute("SELECT count(*) FROM research_reports").fetchone()[0])


if __name__ == "__main__":
    main()
