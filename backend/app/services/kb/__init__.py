"""个人论文知识库（RAG）服务包（spec-011）。"""

from backend.app.services.kb.index import (
    DENSE_VECTOR,
    SPARSE_VECTOR,
    count_points,
    delete_paper,
    ensure_collection,
    get_client,
    index_paper,
    reset_client,
)
from backend.app.services.kb.parse import Chunk, PdfParseError, build_chunks, extract_pages, split_text
from backend.app.services.kb.prompts import build_prompt, citation_payloads
from backend.app.services.kb.retrieve import Hit, hybrid_search, reranker_available, rrf_fuse
from backend.app.services.kb.store import (
    STATUS_FAILED,
    STATUS_INDEXED,
    STATUS_INDEXING,
    STATUS_PARTIAL,
    PaperRecord,
    get_paper,
    load_papers,
    new_record,
    remove_paper,
    save_upload,
    upsert_paper,
)

__all__ = [
    "DENSE_VECTOR",
    "SPARSE_VECTOR",
    "Hit",
    "PaperRecord",
    "STATUS_FAILED",
    "STATUS_INDEXED",
    "STATUS_INDEXING",
    "STATUS_PARTIAL",
    "Chunk",
    "PdfParseError",
    "build_chunks",
    "build_prompt",
    "citation_payloads",
    "count_points",
    "delete_paper",
    "ensure_collection",
    "extract_pages",
    "get_client",
    "get_paper",
    "hybrid_search",
    "index_paper",
    "load_papers",
    "new_record",
    "remove_paper",
    "reranker_available",
    "reset_client",
    "rrf_fuse",
    "save_upload",
    "split_text",
    "upsert_paper",
]
