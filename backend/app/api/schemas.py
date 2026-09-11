from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from backend.app.platform.config import MODEL_NAME


class ChatRequest(BaseModel):
    question: str
    mode: Literal["normal", "developer"] = "normal"
    model: str = MODEL_NAME


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    instructions: Optional[str] = Field(default=None, max_length=5000)


class ProjectPatchRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    instructions: Optional[str] = Field(default=None, max_length=5000)
    status: Optional[Literal["active", "archived", "deleted"]] = None


class ConversationMessageRequest(BaseModel):
    # ``question`` is accepted as a compatibility spelling for the existing
    # chat payload; the new contract uses ``content``.
    content: Optional[str] = Field(default=None, max_length=20000)
    question: Optional[str] = Field(default=None, max_length=20000)
    message: Optional[str] = Field(default=None, max_length=20000)
    project_id: Optional[str] = Field(default=None, max_length=100)
    model: str = MODEL_NAME
    mode: Literal["normal", "developer"] = "normal"


class ConversationPatchRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    project_id: Optional[str] = Field(default=None, max_length=100)
    status: Optional[Literal["active", "archived", "deleted"]] = None
    memory_history_policy: Optional[Literal["from_binding", "include_prior_history"]] = None
    confirm_move: bool = False


class MemoryCreateRequest(BaseModel):
    """A user-authorized memory write; owner identity is server controlled."""

    scope: Literal["global", "project"] = "global"
    project_id: Optional[str] = Field(default=None, max_length=100)
    category: Literal["user_preference", "stable_fact", "project_rule", "capability_method"] = "user_preference"
    statement: str = Field(min_length=1, max_length=1000)
    source_kind: Literal["explicit", "repeated", "verified_failure", "manual"] = "manual"
    confidence: float = Field(default=1.0, ge=0, le=1)
    status: Literal["candidate", "active"] = "active"


class MemoryPatchRequest(BaseModel):
    """Content edits create a superseding version; status changes govern it."""

    statement: Optional[str] = Field(default=None, min_length=1, max_length=1000)
    category: Optional[Literal["user_preference", "stable_fact", "project_rule", "capability_method"]] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    status: Optional[Literal["candidate", "active", "disabled", "deleted"]] = None


class MemoryAnalysisDecisionRequest(BaseModel):
    decision: Literal["save_project", "save_global", "ignore"]
    project_id: Optional[str] = Field(default=None, max_length=100)


class MemoryAnalysisBatchDecisionRequest(BaseModel):
    # ``save_suggested``/``ignore_all`` are the UI-level actions; the explicit
    # save_project/save_global spellings remain useful to API clients.
    decision: Literal["save_suggested", "save_all", "ignore_all", "ignore", "save_project", "save_global"] = "save_suggested"
    item_ids: Optional[List[str]] = Field(default=None, max_length=1000)
    project_id: Optional[str] = Field(default=None, max_length=100)


class KBAskRequest(BaseModel):
    """知识库问答请求（spec-011 / spec-012）。

    模型由用户从顶部 modelSelect 自选；`chunker` 为 spec-012 新增的切分版本
    选择，默认 `v1`，仅允许 `v1` / `v2`。
    """

    question: str
    model: str = MODEL_NAME
    top_k: int = 5
    chunker: Literal["v1", "v2"] = "v1"
    # Optional owner-scoped project context; legacy callers omit it and keep
    # the historical shared knowledge-base behavior.
    project_id: Optional[str] = Field(default=None, max_length=100)


class KBReindexRequest(BaseModel):
    """重建索引请求（spec-012）：不传 `chunker` 时重建全部版本。"""

    chunker: Literal["v1", "v2", "all"] = "all"


class ConferenceUpdateRequest(BaseModel):
    """受控会议配置更新；Task03 仅允许启停，不允许改写源身份。"""

    enabled: bool


class PaperSearchRequest(BaseModel):
    """论文检索请求的服务端边界。

    ``years`` 留空时由搜索服务按配置选择最近的完整年份；显式年份最多十个，
    实际年份范围和当前年份边界仍由领域服务统一校验。
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=500)
    conference_id: str = Field(min_length=1, max_length=100)
    years: Optional[List[StrictInt]] = Field(default=None, max_length=10)
    limit: Optional[StrictInt] = Field(default=None, ge=1, le=100)
    publication_scope: Literal["published", "accepted", "all"] = "published"


class AsyncPaperSearchRequest(BaseModel):
    """Task15 async catalog search: only server-controlled scope is accepted."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    conference_ids: List[str] = Field(min_length=1, max_length=1)
    years: List[StrictInt] = Field(min_length=1, max_length=10)


class PaperAcceptedRequest(BaseModel):
    """受控 accepted-paper 查询参数；来源 URL 只来自服务端会议配置。"""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    # Query parameters arrive as strings; unlike JSON body fields they must
    # use normal int coercion before the bounded Pydantic checks.
    year: Optional[int] = Field(default=None, ge=1900)
    cycle: Optional[str] = Field(default=None, min_length=1, max_length=20, pattern=r"^cycle[1-9][0-9]*$")
    q: Optional[str] = Field(default=None, min_length=1, max_length=500)
    limit: Optional[int] = Field(default=None, ge=1, le=100)


class PaperImportRequest(BaseModel):
    """Single-paper import request.

    URLs, titles, conference names, and other candidate metadata are not
    accepted from the client.  The route resolves both identifiers against
    the server-side search snapshot before invoking the importer.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    search_id: str = Field(min_length=1, max_length=200)
    candidate_id: str = Field(min_length=1, max_length=200)


class PaperImportResponse(BaseModel):
    """Stable result fields returned by the single-paper import endpoint."""

    paper_id: Optional[str] = None
    stored_name: Optional[str] = None
    status: str
    error_code: Optional[str] = None
    existing: bool = False


class PaperImportBatchRequest(BaseModel):
    """Create a batch from an opaque server-side search snapshot only."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    search_id: str = Field(min_length=1, max_length=200)
    # The durable store is the authority for the 20-item limit so an oversized
    # request receives the stable BATCH_LIMIT_EXCEEDED error rather than a
    # generic Pydantic validation response.
    candidate_ids: List[str] = Field(min_length=1)
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=200)


class PaperImportBatchResponse(BaseModel):
    """Public batch status payload shared by create/get/retry routes."""

    batch_id: str
    search_id: str
    status: str
    state: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    total_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    waiting_login_count: int = 0
    cancelled_count: int = 0
    items: List[dict] = Field(default_factory=list)


class PaperImportItemActionRequest(BaseModel):
    """Empty item action body; URLs and credentials are never client input."""

    model_config = ConfigDict(extra="forbid")


class PaperImportItemLoginResponse(BaseModel):
    status: str
    item_id: str
    site: Literal["acm", "ieee"]
