#!/usr/bin/env python3
"""spec-047 追加范围三：生成三份内置标注集（只读 KB，只写三份 gold）。

真实性硬约束：
- rag-retrieval / chat-quality 的每条 ``paper_id`` / ``chunk_index`` / ``page``
  在首次生成时来自运行中主服务 ``POST /api/kb/ask`` 的 SSE ``citations`` 事件
  （由 ``hybrid_search`` 生成的当前 KB 真实命中身份），``derived_chunk_excerpt`` 与 chat
  ``output`` 取自真实 ``Hit.text``；这些身份随 gold 冻结。复跑只用只读
  ``GET /api/kb/health`` + ``GET /api/kb/papers`` 校验身份仍属于当前 KB，
  不重新检索、不触发任何写副作用；KB 不可用或身份失效一律回传阻塞并退出，
  **绝不编造 chunk 身份**。冻结集缺失时才以少量 citations 调用从零派生。
- intent-classification 的 ``expected_intent`` 只使用
  ``backend/app/skills/registry.py::build_default_tool_registry()`` 的真实 Tool 名或 ``none``。
- 不含任何分数字段、不写死 value / score；确定性（固定问题列表 / 固定排序 /
  不依赖当前时间生成随机内容），复跑三份文件逐字节一致（sha256 可复核）。

用法（仓库根目录、已激活 .venv、主服务已启动）：
    python scripts/generate_evaluation_samples.py            # 写三份 gold
    python scripts/generate_evaluation_samples.py --check    # 只算 sha256，不写文件
    python scripts/generate_evaluation_samples.py --base-url http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

GOLD_DIR = BASE / "docs" / "sdd" / "plans" / "047" / "gold"
FROZEN_PATH = BASE / "docs" / "sdd" / "plans" / "042" / "task-02-eval-dataset.json"
GENERATOR = "scripts/generate_evaluation_samples.py"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"

RAG_BASELINE_ITEMS = 8      # 追加范围二冻结的 8 条 + kb_alignment 结论逐字保留
INTENT_BASELINE_ITEMS = 16  # 原有 16 条逐字保留
TARGET_TOTAL_ITEMS = 120    # 三份集各 >=100 条
FROZEN_TRACE_COUNT = 20     # 042 的 20 条 status=scored && synthetic=false
KB_CHUNK_COUNT = 100        # chat 集 KB 派生条目数
DEFAULT_ASK_MODEL = "qwen3.5:9b"   # 仅冻结集缺失、需从零派生时使用
BOOTSTRAP_QUESTIONS = 20            # 从零派生时的固定问题数（避免 Ollama 队列堆积）
ASK_TOP_K = 10
EXCERPT_CHARS = 100
CHUNK_OUTPUT_CHARS = 400

RAG_DERIVATION_RULE = (
    "保留追加范围二冻结的 8 条（含 kb_alignment 结论）逐字不变；新增条目在首次生成时对运行中的"
    "主服务以固定英文问题调用 POST /api/kb/ask(question, top_k=10, chunker='v1')，只读解析 SSE "
    "citations 事件（由 hybrid_search 生成），登记真实命中的 (paper_id, chunker='v1', chunk_index, page) "
    "为 relevant_doc_ids，derived_chunk_excerpt 取自真实 Hit.text。不编造 paper_id / chunk_index。"
    "身份随 gold 冻结，复跑以只读 health/papers 校验仍属于当前 KB；derivation_rank 是脚本轮换的"
    "确定性派生序号（1..10），不是 hybrid_search 实时排名；打分时命中与否完全由 hybrid_search "
    "真实检索决定，baseline(top_k=5) 与 topk-10(top_k=10) 因此产生真实可复算的 recall/precision/mrr 差异。"
)
INTENT_DERIVATION_RULE = (
    "保留原有 16 条逐字不变；新增正例 = 指令性动词后紧跟 registry.py 中真实存在的 7 个 Tool 名"
    "（14 个固定模板 x 7 个技能），expected_intent 即该名称；负例 = 不存在的拼写、否定式与无关表达，"
    "expected_intent='none'。为让 100 条打分不触发 detect_skill 的 LLM 第二跳，负例不点名任何已注册"
    "技能名、也不含 ASCII 连字符 token，全部走确定性规则第一跳；不复用过时 USENIX 技能名。"
)
CHAT_DERIVATION_RULE = (
    "唯一数据源为本文档 items 数组：20 条来自 docs/sdd/plans/042/task-02-eval-dataset.json 的冻结"
    "真实 trace（status=scored && synthetic=false，条目级 synthetic:false + reference_source:"
    "'frozen-042-trace'），100 条从当前 KB 真实 citations chunk 构造 input、以真实 Hit.text 摘录作"
    "output（条目级 synthetic:true + reference_source:'kb-chunk' + kb_source 身份）；两类条目按「1 冻结 + 5 KB」交错排列，避免批量首屏全是超长冻结对话。文档级 "
    "synthetic:true 表示内置 fixture 集（load_dataset 强制校验、不冒充人工标注），条目级 synthetic "
    "只表示来源，两层语义不矛盾；output 是真实片段摘录，不是人工摘要、不是模型生成答案。"
)

# 14 个固定正例模板：动词在技能名之前、技能名后接 CJK「技能」保证词边界。
INTENT_TEMPLATES = (
    "请使用 {tool} 技能，检索 2024 年 USENIX Security 的模糊测试论文。",
    "帮我调用 {tool} 技能，把选中的候选论文导入知识库。",
    "运行 {tool} 技能，读取这篇论文的官方详情页摘要。",
    "请用 {tool} 技能回答：什么是稠密向量与稀疏检索的混合召回？",
    "请使用 {tool} 技能，在知识库中检索关于 RAG 切分的片段。",
    "帮我用 {tool} 技能，找出上次关于离线评测的会话记录。",
    "调用 {tool} 技能，查一下知识库里关于重排模型的段落。",
    "请使用 {tool} 技能，列出 DBLP 中关于侧信道攻击的论文目录。",
    "启用 {tool} 技能，把近期的安全研究候选整理成清单。",
    "执行 {tool} 技能，核对当前批次论文的元数据字段。",
    "帮我调用 {tool} 技能，重新检索上一轮命中的片段。",
    "请使用 {tool} 技能，按年份筛选已发表的系统论文。",
    "运行 {tool} 技能，检查本地索引中是否存在重复文档。",
    "请用 {tool} 技能，导出本次会话里提到的所有引用编号。",
)
# 负例不含任何已注册技能名、不含 ASCII 连字符 token -> 不触发 LLM 第二跳。
INTENT_NEGATIVES = (
    "papper_discovery 是什么，听说很好用？",
    "请不要调用任何技能，直接回答我的问题。",
    "你好，请总结一下今天的天气。",
    "帮我写一个把列表倒序输出的 Python 函数。",
    "请解释一下 TCP 三次握手的过程。",
    "今天有什么值得关注的安全研究？",
)

QUESTION_TEMPLATES = (
    "In the paper '{title}', what problem do the authors address?",
    "Summarize the main contribution and method of '{title}'.",
)


class GenerationBlocked(RuntimeError):
    """KB 不可用 / 缺真实 chunk 身份：如实回传阻塞，绝不编造。"""


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_of(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _kb_snapshot(snapshot: dict) -> dict:
    health = snapshot["health"]
    return {
        "source": "首次生成 POST /api/kb/ask 的 citations 事件；复跑只读 GET /api/kb/health + GET /api/kb/papers 校验冻结身份",
        "papers": health.get("papers"),
        "chunks": health.get("chunks"),
        "qdrant": health.get("qdrant"),
        "embedding": health.get("embedding"),
        "paper_ids": list(snapshot["paper_ids"]),
    }


def _build_rag(baseline: dict, snapshot: dict, generated_at: str) -> dict:
    document = dict(baseline)
    items = list(baseline["items"][:RAG_BASELINE_ITEMS])
    for case in snapshot["retrieval_cases"]:
        items.append({
            "id": f"rag-{len(items) + 1:03d}",
            "question": case["question"],
            "relevant_doc_ids": [{
                "paper_id": case["paper_id"],
                "chunker": case["chunker"],
                "chunk_index": case["chunk_index"],
                "page": case["page"],
            }],
            "derivation_rank": case["rank"],
            "derived_chunk_excerpt": str(case["excerpt"])[:EXCERPT_CHARS],
        })
    document["items"] = items
    document["item_count"] = len(items)
    document["generated_at"] = generated_at
    document["generator"] = GENERATOR
    document["derivation_rule"] = RAG_DERIVATION_RULE
    document["kb_snapshot"] = _kb_snapshot(snapshot)
    return document


def _build_intent(baseline: dict, snapshot: dict, generated_at: str) -> dict:
    document = dict(baseline)
    items = list(baseline["items"][:INTENT_BASELINE_ITEMS])
    for template in INTENT_TEMPLATES:
        for tool in snapshot["tool_names"]:
            items.append({
                "id": f"intent-{len(items) + 1:03d}",
                "message": template.format(tool=tool),
                "expected_intent": tool,
            })
    for negative in INTENT_NEGATIVES:
        items.append({
            "id": f"intent-{len(items) + 1:03d}",
            "message": negative,
            "expected_intent": "none",
        })
    document["items"] = items
    document["item_count"] = len(items)
    document["registry_tool_names"] = list(snapshot["tool_names"])
    document["generated_at"] = generated_at
    document["generator"] = GENERATOR
    document["derivation_rule"] = INTENT_DERIVATION_RULE
    document["kb_snapshot"] = _kb_snapshot(snapshot)
    return document


def _build_chat(baseline: dict, snapshot: dict, generated_at: str) -> dict:
    document = dict(baseline)
    frozen_items: list[dict] = []
    for index, trace in enumerate(snapshot["frozen_traces"][:FROZEN_TRACE_COUNT], start=1):
        frozen_items.append({
            "id": f"chat-frozen-{index:02d}",
            "trace_id": trace["trace_id"],
            "task": "chat_quality",
            "status": "scored",
            "input": trace["input"],
            "output": trace["output"],
            "synthetic": False,
            "reference_source": "frozen-042-trace",
            "prior_context": None,
        })
    kb_items: list[dict] = []
    for index, chunk in enumerate(snapshot["kb_chunks"][:KB_CHUNK_COUNT], start=1):
        output = str(chunk["text"])[:CHUNK_OUTPUT_CHARS].strip()
        if not output:
            continue
        kb_items.append({
            "id": f"chat-kb-{index:03d}",
            "task": "chat_quality",
            "status": "scored",
            "input": (
                f"Based on the knowledge base excerpt from {chunk['file_name']}, "
                "summarize the key point of this passage."
            ),
            "output": output,
            "synthetic": True,
            "reference_source": "kb-chunk",
            "prior_context": None,
            "kb_source": {
                "paper_id": chunk["paper_id"],
                "chunk_index": chunk["chunk_index"],
                "page": chunk["page"],
                "chunker": "v1",
            },
        })
    # 交错：每 1 条冻结 trace 后跟 5 条 KB 派生条目。冻结 trace 的 input 是完整
    # 多轮对话记录（可达数千字符），交错可避免 B=20 第 1 批全是超长文本拖垮本地模型。
    items: list[dict] = []
    kb_cursor = 0
    for frozen_item in frozen_items:
        items.append(frozen_item)
        for _ in range(5):
            if kb_cursor < len(kb_items):
                items.append(kb_items[kb_cursor])
                kb_cursor += 1
    items.extend(kb_items[kb_cursor:])
    document["items"] = items
    document["item_count"] = len(items)
    document["scoreable_item_count"] = len(items)
    document["generated_at"] = generated_at
    document["generator"] = GENERATOR
    document["derivation_rule"] = CHAT_DERIVATION_RULE
    document["label_source"] = "kb-chunk-derived + frozen-042-trace"
    document["label_source_note"] = (
        "文档级 synthetic:true 表示内置 fixture 集（load_dataset 强制校验，不冒充人工标注、不冒充真实业务对话）；"
        "条目级 synthetic 只表示来源：20 条冻结 042 trace 为 false、100 条 KB 派生为 true。"
        "output 是真实 Hit.text 摘录 / 冻结 trace，不是人工标注答案，也不写死任何分数。"
    )
    document["items_source"] = "self#items（load_chat_items 的唯一数据源）"
    document["source_path_note"] = "source_path 仅记录 042 冻结 trace 的溯源出处，不再是加载源。"
    document["known_limitation"] = (
        f"{len(items)} 条全部为 chat_quality 且无 prior_context / memory_correctness 标注，"
        "故 memory_correctness 维度只能标 needs_ground_truth + reason，绝不占位出分；"
        "判官评分对象是所选被测模型的实时生成回答，不是集内冻结 output。"
    )
    document["kb_snapshot"] = _kb_snapshot(snapshot)
    return document


def build_documents(snapshot: dict, generated_at: str) -> dict[str, dict]:
    """纯函数：从确定性 KB 快照构造三份文档；同输入必得同输出（幂等）。

    ``snapshot`` 键：health / paper_ids / retrieval_cases / kb_chunks /
    frozen_traces / tool_names / baseline（三份现有文档）。第二次运行以第一次产物
    为 baseline 时，rag/intent 只取前 8/16 条冻结基线、chat 完全重建，不会累积重复条目。
    """
    baseline = snapshot["baseline"]
    documents = {
        "rag-retrieval": _build_rag(baseline["rag-retrieval"], snapshot, generated_at),
        "intent-classification": _build_intent(baseline["intent-classification"], snapshot, generated_at),
        "chat-quality": _build_chat(baseline["chat-quality"], snapshot, generated_at),
    }
    for dataset_id, document in documents.items():
        if len(document["items"]) < 100:
            raise GenerationBlocked(f"{dataset_id}: only {len(document['items'])} items, need >=100")
        if document["item_count"] != len(document["items"]):
            raise GenerationBlocked(f"{dataset_id}: item_count mismatch")
        for item in document["items"]:
            if "value" in item or "score" in item:
                raise GenerationBlocked(f"{dataset_id}: item must not carry a score field")
    return documents


def _frozen_traces() -> list[dict]:
    """只读 042 冻结集：20 条 status=scored && synthetic=false 且 output 非空。"""
    try:
        raw = json.loads(FROZEN_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise GenerationBlocked(f"042 frozen traces unreadable: {exc}") from None
    if not isinstance(raw, list):
        raise GenerationBlocked("042 frozen traces must be a JSON array")
    traces = [
        {"trace_id": item["trace_id"], "input": item["input"], "output": item["output"]}
        for item in raw
        if isinstance(item, dict)
        and item.get("status") == "scored"
        and item.get("synthetic") is False
        and isinstance(item.get("input"), str)
        and isinstance(item.get("output"), str)
        and item["output"].strip()
    ]
    if len(traces) < FROZEN_TRACE_COUNT:
        raise GenerationBlocked(f"only {len(traces)} frozen traces, need {FROZEN_TRACE_COUNT}")
    return traces[:FROZEN_TRACE_COUNT]


def _tool_names() -> list[str]:
    try:
        from backend.app.skills.registry import build_default_tool_registry
    except Exception as exc:  # noqa: BLE001 - 只读能力缺失即阻塞
        raise GenerationBlocked(f"tool registry unavailable: {type(exc).__name__}") from None
    names = [entry.name for entry in build_default_tool_registry()]
    if len(names) != 7:
        raise GenerationBlocked(f"expected 7 registered tools, got {len(names)}")
    return names


def _deterministic_generated_at() -> str:
    """不依赖当前时间：取 042 冻结集文件的 UTC mtime（只读输入的确定性属性）。"""
    stamp = datetime.fromtimestamp(FROZEN_PATH.stat().st_mtime, tz=timezone.utc)
    return stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _frozen_identities(baseline: dict, paper_ids: set[str]) -> tuple[list[dict], list[dict]]:
    """复跑：从 gold 已冻结的真实 chunk 身份读取，并校验 paper_id 仍在当前 KB。

    身份在首次生成时由 /api/kb/ask 的 citations（hybrid_search 真实命中）派生并冻结；
    复跑不再重新检索、不触发任何写副作用，用只读 papers 列表核验身份未失效。
    """
    retrieval_cases: list[dict] = []
    for item in baseline["rag-retrieval"]["items"][RAG_BASELINE_ITEMS:]:
        refs = item.get("relevant_doc_ids") or []
        if not refs or not isinstance(refs[0], dict):
            raise GenerationBlocked("frozen rag item has no real chunk identity")
        ref = refs[0]
        if ref.get("paper_id") not in paper_ids:
            raise GenerationBlocked(f"frozen paper_id {ref.get('paper_id')} is absent from current KB")
        retrieval_cases.append({
            "question": item["question"], "paper_id": ref["paper_id"],
            "chunker": "v1", "chunk_index": int(ref["chunk_index"]), "page": int(ref["page"]),
            "excerpt": item.get("derived_chunk_excerpt", ""),
            "rank": int(item.get("derivation_rank", 1)),
        })
    kb_chunks: list[dict] = []
    prefix = "Based on the knowledge base excerpt from "
    suffix = ", summarize the key point of this passage."
    for item in baseline["chat-quality"]["items"]:
        if item.get("reference_source") != "kb-chunk":
            continue
        src = item.get("kb_source") or {}
        if src.get("paper_id") not in paper_ids:
            raise GenerationBlocked(f"frozen chat paper_id {src.get('paper_id')} is absent from current KB")
        raw_input = str(item.get("input", ""))
        file_name = (
            raw_input[len(prefix):-len(suffix)]
            if raw_input.startswith(prefix) and raw_input.endswith(suffix)
            else "knowledge-base-document"
        )
        kb_chunks.append({
            "paper_id": src["paper_id"], "chunk_index": int(src["chunk_index"]),
            "page": int(src["page"]), "file_name": file_name, "text": item.get("output", ""),
        })
    return retrieval_cases, kb_chunks


def _ask_citations(client, base_url: str, question: str) -> list[dict]:
    """从零生成时只读解析 SSE citations；拿到即断开，绝不在服务运行时另起进程内检索。"""
    import httpx

    try:
        with client.stream(
            "POST", f"{base_url}/api/kb/ask",
            json={"question": question, "model": DEFAULT_ASK_MODEL, "top_k": ASK_TOP_K, "chunker": "v1"},
            timeout=60.0,
        ) as response:
            if response.status_code != 200:
                return []
            for line in response.iter_lines():
                if not isinstance(line, str) or not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                except ValueError:
                    continue
                if event.get("type") == "citations":
                    return event.get("citations") or []
    except httpx.HTTPError:
        return []
    return []


def _question_for(chunk: dict) -> str:
    excerpt = str(chunk["text"])[:EXCERPT_CHARS].replace('"', "'").replace("\n", " ").strip()
    return (
        f"In the knowledge base document '{chunk['file_name']}', what does the passage "
        f"beginning with \"{excerpt[:70]}\" describe?"
    )


def _bootstrap_identities(client, base_url: str, papers: list[dict], paper_ids: set[str]) -> list[dict]:
    """冻结集缺失时的从零派生：少量问题 x 真实 citations，去重后返回真实 chunk 池。"""
    titles = [
        str(paper.get("file_name") or "knowledge-base-document")
        for paper in sorted(papers, key=lambda i: str(i.get("paper_id") or i.get("document_id") or ""))
    ][:BOOTSTRAP_QUESTIONS]
    questions = [
        f"In the paper '{title}', what problem do the authors address and what evidence supports it?"
        for title in titles
    ]
    pool: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for question in questions:
        for citation in _ask_citations(client, base_url, question):
            if not isinstance(citation, dict) or citation.get("paper_id") not in paper_ids:
                continue
            try:
                chunk_index = int(citation.get("chunk_index"))
                page = int(citation.get("page"))
            except (TypeError, ValueError):
                continue
            chunk_text = citation.get("text")
            if chunk_index < 0 or page <= 0 or not isinstance(chunk_text, str) or not chunk_text.strip():
                continue
            key = (str(citation["paper_id"]), chunk_index)
            if key in seen:
                continue
            seen.add(key)
            pool.append({
                "paper_id": citation["paper_id"], "chunk_index": chunk_index, "page": page,
                "file_name": str(citation.get("file_name") or "knowledge-base-document"),
                "text": chunk_text,
            })
    return pool


def fetch_snapshot(base_url: str = DEFAULT_BASE_URL) -> dict:
    """只读主服务 health/papers 校验当前 KB；身份优先取 gold 冻结值，缺失才从零派生。"""
    import httpx

    try:
        from backend.app.skills.registry import build_default_tool_registry  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        raise GenerationBlocked(f"backend import unavailable: {type(exc).__name__}") from None

    try:
        with httpx.Client(timeout=30.0) as client:
            health = client.get(f"{base_url}/api/kb/health").json()
            papers_payload = client.get(f"{base_url}/api/kb/papers").json()
            papers = papers_payload.get("papers") if isinstance(papers_payload, dict) else None
            if not isinstance(health, dict) or not health.get("qdrant") or not health.get("embedding"):
                raise GenerationBlocked("KB qdrant/embedding not ready; refusing to invent chunk identities")
            if not isinstance(papers, list) or not papers:
                raise GenerationBlocked("KB has no papers; refusing to invent chunk identities")
            paper_ids = sorted({
                str(paper.get("paper_id") or paper.get("document_id"))
                for paper in papers
                if isinstance(paper, dict) and (paper.get("paper_id") or paper.get("document_id"))
            })
            if not paper_ids:
                raise GenerationBlocked("KB papers have no stable paper_id; refusing to invent identities")

            baseline: dict[str, dict] = {}
            for dataset_id in ("rag-retrieval", "intent-classification", "chat-quality"):
                path = GOLD_DIR / f"builtin-{dataset_id}.json"
                try:
                    document = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError, UnicodeError) as exc:
                    raise GenerationBlocked(f"baseline gold unreadable: {path.name}: {exc}") from None
                if not isinstance(document, dict) or not isinstance(document.get("items"), list):
                    raise GenerationBlocked(f"baseline gold invalid: {path.name}")
                baseline[dataset_id] = document

            retrieval_cases, kb_chunks = _frozen_identities(baseline, set(paper_ids))
            if len(retrieval_cases) < TARGET_TOTAL_ITEMS or len(kb_chunks) < KB_CHUNK_COUNT:
                pool = _bootstrap_identities(client, base_url, papers, set(paper_ids))
                if len(pool) < TARGET_TOTAL_ITEMS:
                    raise GenerationBlocked(
                        f"only {len(pool)} real KB chunks from live citations, need {TARGET_TOTAL_ITEMS}; "
                        "KB 不可用或语料不足，绝不编造 chunk 身份"
                    )
                retrieval_cases = [
                    {
                        "question": _question_for(chunk), "paper_id": chunk["paper_id"],
                        "chunker": "v1", "chunk_index": chunk["chunk_index"], "page": chunk["page"],
                        "excerpt": chunk["text"][:EXCERPT_CHARS], "rank": 1 + (index % 10),
                    }
                    for index, chunk in enumerate(pool[:TARGET_TOTAL_ITEMS])
                ]
                kb_chunks = pool[:KB_CHUNK_COUNT]
    except (httpx.HTTPError, ValueError) as exc:
        raise GenerationBlocked(f"KB read-only HTTP unavailable: {type(exc).__name__}") from None

    if len(retrieval_cases) < TARGET_TOTAL_ITEMS or len(kb_chunks) < KB_CHUNK_COUNT:
        raise GenerationBlocked("frozen identities incomplete; refusing to invent chunk identities")
    return {
        "health": health, "paper_ids": paper_ids,
        "retrieval_cases": retrieval_cases[:TARGET_TOTAL_ITEMS],
        "kb_chunks": kb_chunks[:KB_CHUNK_COUNT],
        "frozen_traces": _frozen_traces(), "tool_names": _tool_names(), "baseline": baseline,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--check", action="store_true", help="只计算 sha256，不写 gold 文件")
    args = parser.parse_args(argv)
    try:
        snapshot = fetch_snapshot(args.base_url)
        documents = build_documents(snapshot, _deterministic_generated_at())
    except GenerationBlocked as exc:
        print(f"BLOCKED: {exc}")
        print("KB 不可用或缺少真实 chunk 身份：未写任何 gold 文件，绝不编造 paper_id / chunk_index。")
        return 2
    for dataset_id, document in documents.items():
        print(f"{dataset_id}: items={len(document['items'])} sha256={sha256_of(document)}")
    if args.check:
        print("--check: 未写文件")
        return 0
    for dataset_id, document in documents.items():
        path = GOLD_DIR / f"builtin-{dataset_id}.json"
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"WROTE {path.relative_to(BASE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
