"""论文原件与元数据的本地存储（spec-011）。

元数据落在 `data/kb/papers.json`，原件落在 `data/kb/papers/{paper_id}.pdf`。
所有写操作用同一把锁串行化，避免并发上传/删除产生半截状态。
"""

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

from backend.app.core.config import KB_META_PATH, KB_PAPERS_DIR

STATUS_PENDING = "pending"
STATUS_INDEXING = "indexing"
STATUS_INDEXED = "indexed"
STATUS_PARTIAL = "indexed_partial"
STATUS_FAILED = "failed"

# 切分版本（spec-012）：上传时 v1 同步、v2 异步，两版各自维护状态与进度。
CHUNKER_V1 = "v1"
CHUNKER_V2 = "v2"
CHUNKERS = (CHUNKER_V1, CHUNKER_V2)

_lock = threading.RLock()

# 用于区分"不更新 error"与"把 error 置为 None"
_UNSET = object()


def default_chunkers() -> Dict[str, Any]:
    """双版本初始状态：v1 立即开始，v2 排队等待异步任务。"""
    return {
        CHUNKER_V1: {"status": STATUS_INDEXING, "chunk_count": 0, "progress": 0, "error": None},
        CHUNKER_V2: {"status": STATUS_PENDING, "chunk_count": 0, "progress": 0, "error": None},
    }


def default_chunker_state(status: str = STATUS_PENDING) -> Dict[str, Any]:
    return {"status": status, "chunk_count": 0, "progress": 0, "error": None}


@dataclass
class PaperRecord:
    paper_id: str
    file_name: str
    status: str = STATUS_INDEXING
    page_count: int = 0
    chunk_count: int = 0
    uploaded_at: str = ""
    error: Optional[str] = None
    # spec-012：双版本状态。顶层 status/chunk_count 保留以兼容既有接口与前端。
    chunkers: Dict[str, Any] = field(default_factory=default_chunkers)
    # spec-015：论文检索导入的可选元数据。None 保持旧上传记录兼容。
    title: Optional[str] = None
    authors: Optional[List[str]] = None
    year: Optional[int] = None
    conference_id: Optional[str] = None
    conference_name: Optional[str] = None
    doi: Optional[str] = None
    dblp_key: Optional[str] = None
    source_url: Optional[str] = None
    import_source: Optional[str] = None
    stored_name: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def ensure_dirs(papers_dir: Optional[Path] = None, meta_path: Optional[Path] = None) -> None:
    Path(papers_dir or KB_PAPERS_DIR).mkdir(parents=True, exist_ok=True)
    meta = Path(meta_path or KB_META_PATH)
    meta.parent.mkdir(parents=True, exist_ok=True)


def load_papers(meta_path: Optional[Path] = None) -> List[dict]:
    """读取全部论文元数据。

    spec-012：对**缺少 `chunkers` 字段的旧记录**在内存中补齐双版本状态，
    使所有读取路径（列表接口、单条查询、状态更新）都无需各自处理兼容问题。
    仅改内存，不即刻写盘。
    """
    meta = Path(meta_path or KB_META_PATH)
    if not meta.exists():
        return []
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    for item in data:
        if isinstance(item, dict):
            ensure_chunkers(item)
    return data


def save_papers(papers: List[dict], meta_path: Optional[Path] = None) -> None:
    meta = Path(meta_path or KB_META_PATH)
    ensure_dirs(meta_path=meta)
    with _lock:
        meta.write_text(
            json.dumps(papers, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def upsert_paper(record: PaperRecord, meta_path: Optional[Path] = None) -> PaperRecord:
    with _lock:
        papers = load_papers(meta_path)
        payload = record.to_dict()
        for index, item in enumerate(papers):
            if item.get("paper_id") == record.paper_id:
                papers[index] = payload
                break
        else:
            papers.append(payload)
        save_papers(papers, meta_path)
    return record


def get_paper(paper_id: str, meta_path: Optional[Path] = None) -> Optional[dict]:
    for item in load_papers(meta_path):
        if item.get("paper_id") == paper_id:
            return item
    return None


def resolve_paper_path(
    paper: Union[str, Mapping[str, Any], PaperRecord],
    papers_dir: Optional[Path] = None,
) -> Path:
    """Resolve a paper's physical path with legacy filename compatibility.

    New imports may store a readable basename in ``stored_name``. Records
    written before spec-015 have no such field and continue using the legacy
    ``{paper_id}.pdf`` layout. Invalid path-like metadata is ignored rather
    than allowing a record to escape the configured papers directory.
    """
    if isinstance(paper, str):
        paper_id = paper
        stored_name = None
    elif isinstance(paper, Mapping):
        paper_id = str(paper.get("paper_id") or "")
        stored_name = paper.get("stored_name")
    else:
        paper_id = str(getattr(paper, "paper_id", "") or "")
        stored_name = getattr(paper, "stored_name", None)

    candidate = str(stored_name or "").strip()
    if candidate:
        candidate_path = Path(candidate)
        if candidate_path.name == candidate and candidate not in {".", ".."}:
            return Path(papers_dir or KB_PAPERS_DIR) / candidate
    return Path(papers_dir or KB_PAPERS_DIR) / f"{paper_id}.pdf"


def remove_paper(paper_id: str, meta_path: Optional[Path] = None, papers_dir: Optional[Path] = None) -> bool:
    """删除元数据与原件；返回是否命中。"""
    with _lock:
        papers = load_papers(meta_path)
        record = next((item for item in papers if item.get("paper_id") == paper_id), None)
        remaining = [item for item in papers if item.get("paper_id") != paper_id]
        if len(remaining) == len(papers):
            return False
        save_papers(remaining, meta_path)
        target = resolve_paper_path(record or paper_id, papers_dir)
        try:
            if target.exists():
                target.unlink()
        except OSError:
            pass
    return True


def save_upload(
    file_name: str,
    content: bytes,
    papers_dir: Optional[Path] = None,
    paper_id: Optional[str] = None,
) -> tuple:
    """落盘上传文件，返回 (paper_id, 文件路径)。同名文件各自独立，不互相覆盖。"""
    directory = Path(papers_dir or KB_PAPERS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    identifier = paper_id or uuid.uuid4().hex
    target = directory / f"{identifier}.pdf"
    target.write_bytes(content)
    return identifier, target


def new_record(
    file_name: str,
    uploaded_at: Optional[str] = None,
    *,
    title: Optional[str] = None,
    authors: Optional[List[str]] = None,
    year: Optional[int] = None,
    conference_id: Optional[str] = None,
    conference_name: Optional[str] = None,
    doi: Optional[str] = None,
    dblp_key: Optional[str] = None,
    source_url: Optional[str] = None,
    import_source: Optional[str] = None,
    stored_name: Optional[str] = None,
) -> PaperRecord:
    return PaperRecord(
        paper_id=uuid.uuid4().hex,
        file_name=file_name,
        uploaded_at=uploaded_at or datetime.now().isoformat(timespec="seconds"),
        title=title,
        authors=authors,
        year=year,
        conference_id=conference_id,
        conference_name=conference_name,
        doi=doi,
        dblp_key=dblp_key,
        source_url=source_url,
        import_source=import_source,
        stored_name=stored_name,
    )


# ---------------------------------------------------------------------------
# 双版本切分状态（spec-012）
# ---------------------------------------------------------------------------


def ensure_chunkers(item: dict) -> Dict[str, Any]:
    """补齐旧记录（无 chunkers 字段）的双版本状态，返回规范化后的 dict。

    **对 spec-011 遗留记录必须沿用其顶层 `status`**：
    若一律按 `indexing` 补 v1，启动时的 `mark_interrupted_tasks` 会把这些
    本已 `indexed` 的论文误判为"中断任务"并标记 failed，导致旧论文全部失效。
    v2 一律 `pending`——旧数据没有 v2，需由用户点「重建索引」补建。
    """
    states = item.get("chunkers") if isinstance(item, dict) else None
    if not isinstance(states, dict):
        states = {}

    if isinstance(item, dict):
        legacy_status = item.get("status") or STATUS_INDEXING
        legacy_count = int(item.get("chunk_count", 0) or 0)
    else:
        legacy_status = STATUS_INDEXING
        legacy_count = 0

    merged = {
        CHUNKER_V1: {
            "status": legacy_status,
            "chunk_count": legacy_count,
            "progress": 100 if legacy_status in (STATUS_INDEXED, STATUS_PARTIAL) else 0,
            "error": (item.get("error") if isinstance(item, dict) else None),
        },
        CHUNKER_V2: default_chunker_state(),
    }

    # 记录里已有的显式状态优先，逐字段覆盖
    for name in CHUNKERS:
        current = states.get(name)
        if isinstance(current, dict):
            base = dict(merged[name])
            base.update({key: current[key] for key in base if key in current})
            merged[name] = base

    if isinstance(item, dict):
        item["chunkers"] = merged
    return merged


def get_chunker_state(paper_id: str, chunker: str, meta_path: Optional[Path] = None) -> Optional[dict]:
    """读取某论文某切分版本的状态；论文不存在返回 None。"""
    for item in load_papers(meta_path):
        if item.get("paper_id") == paper_id:
            return ensure_chunkers(item).get(chunker)
    return None


def update_chunker_state(
    paper_id: str,
    chunker: str,
    *,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    chunk_count: Optional[int] = None,
    error: Any = _UNSET,
    meta_path: Optional[Path] = None,
) -> Optional[dict]:
    """局部更新某论文某切分版本的状态，返回更新后的状态；论文不存在返回 None。

    同时维护顶层 `status` / `chunk_count` 兼容字段（取 v1 的值），
    使既有接口与前端无需改动即可继续工作。
    """
    with _lock:
        papers = load_papers(meta_path)
        for item in papers:
            if item.get("paper_id") != paper_id:
                continue
            states = ensure_chunkers(item)
            state = dict(states.get(chunker) or default_chunker_state())
            if status is not None:
                state["status"] = status
            if progress is not None:
                state["progress"] = max(0, min(100, int(progress)))
            if chunk_count is not None:
                state["chunk_count"] = max(0, int(chunk_count))
            if error is not _UNSET:
                state["error"] = error
            states[chunker] = state
            item["chunkers"] = states
            # 顶层兼容字段跟随 v1
            primary = states.get(CHUNKER_V1) or {}
            item["status"] = primary.get("status", item.get("status"))
            item["chunk_count"] = primary.get("chunk_count", item.get("chunk_count", 0))
            save_papers(papers, meta_path)
            return state
    return None


def mark_interrupted_tasks(meta_path: Optional[Path] = None, reason: str = "服务重启导致中断") -> int:
    """启动时把仍为 `indexing` 的版本标记失败，返回被标记的数量。

    异步任务无法跨进程存活，残留的 `indexing` 会永远卡住进度条，
    因此启动时统一置为 `failed`，由用户点「重建索引」重新触发。
    """
    marked = 0
    with _lock:
        papers = load_papers(meta_path)
        changed = False
        for item in papers:
            states = ensure_chunkers(item)
            for name in CHUNKERS:
                state = states.get(name)
                if isinstance(state, dict) and state.get("status") == STATUS_INDEXING:
                    state["status"] = STATUS_FAILED
                    state["progress"] = 0
                    state["error"] = reason
                    marked += 1
                    changed = True
            item["chunkers"] = states
            if isinstance(states.get(CHUNKER_V1), dict):
                item["status"] = states[CHUNKER_V1].get("status", item.get("status"))
        if changed:
            save_papers(papers, meta_path)
    return marked
