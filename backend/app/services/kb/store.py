"""论文原件与元数据的本地存储（spec-011）。

元数据落在 `data/kb/papers.json`，原件落在 `data/kb/papers/{paper_id}.pdf`。
所有写操作用同一把锁串行化，避免并发上传/删除产生半截状态。
"""

import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from backend.app.core.config import KB_META_PATH, KB_PAPERS_DIR

STATUS_INDEXING = "indexing"
STATUS_INDEXED = "indexed"
STATUS_PARTIAL = "indexed_partial"
STATUS_FAILED = "failed"

_lock = threading.RLock()


@dataclass
class PaperRecord:
    paper_id: str
    file_name: str
    status: str = STATUS_INDEXING
    page_count: int = 0
    chunk_count: int = 0
    uploaded_at: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def ensure_dirs(papers_dir: Optional[Path] = None, meta_path: Optional[Path] = None) -> None:
    Path(papers_dir or KB_PAPERS_DIR).mkdir(parents=True, exist_ok=True)
    meta = Path(meta_path or KB_META_PATH)
    meta.parent.mkdir(parents=True, exist_ok=True)


def load_papers(meta_path: Optional[Path] = None) -> List[dict]:
    meta = Path(meta_path or KB_META_PATH)
    if not meta.exists():
        return []
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


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


def remove_paper(paper_id: str, meta_path: Optional[Path] = None, papers_dir: Optional[Path] = None) -> bool:
    """删除元数据与原件；返回是否命中。"""
    with _lock:
        papers = load_papers(meta_path)
        remaining = [item for item in papers if item.get("paper_id") != paper_id]
        if len(remaining) == len(papers):
            return False
        save_papers(remaining, meta_path)
        target = Path(papers_dir or KB_PAPERS_DIR) / f"{paper_id}.pdf"
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


def new_record(file_name: str, uploaded_at: Optional[str] = None) -> PaperRecord:
    return PaperRecord(
        paper_id=uuid.uuid4().hex,
        file_name=file_name,
        uploaded_at=uploaded_at or datetime.now().isoformat(timespec="seconds"),
    )
