"""spec-023 Task04 — Tool 注册表（唯一事实源 = 代码）。

这里只声明「执行层原子动作」，每个 Tool 的 ``entry`` 都必须指向后端中
真实可定位的代码入口（模块.函数），禁止凭空发明。本任务只做注册/元信息/
启停，不做执行（执行见 Task07）。

已确认的既有能力入口：
- search_paper_catalog    → backend.app.paper_discovery.application.paper_discovery_search.PaperDiscoverySearchService.search
- download_and_import_paper → backend.app.paper_discovery.application.paper_import.import_candidate
- kb_search               → backend.app.knowledge_base.infrastructure.retrieve.hybrid_search
- kb_ask                  → backend.app.api.routes_kb.kb_ask（hybrid_search + run_chat 编排）
"""

from __future__ import annotations

from backend.app.skills.models import ToolEntry


def build_default_tool_registry() -> list[ToolEntry]:
    """返回进程默认 Tool 注册表（代码即事实源）。"""
    return [
        ToolEntry(
            name="search_paper_catalog",
            description=(
                "检索 USENIX Security / DBLP 论文目录元数据（标题、作者、摘要、关键词、年份），"
                "返回候选论文列表，不下载 PDF。参数：source（会议来源，如 usenix/dblp 枚举）、"
                "query（关键词）、years（年份列表）、limit（每源上限）、publication_scope（published/accepted/all）。"
            ),
            entry=(
                "backend.app.paper_discovery.application.paper_discovery_search"
                ".PaperDiscoverySearchService.search"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["usenix", "dblp", "all"],
                        "description": "会议来源：usenix=USENIX Security 官方；dblp=DBLP 书目；all=两者并行",
                    },
                    "query": {"type": "string", "description": "检索关键词"},
                    "years": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "年份列表，如 [2023, 2024]",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "description": "每个来源返回的候选上限",
                    },
                    "publication_scope": {
                        "type": "string",
                        "enum": ["published", "accepted", "all"],
                        "description": "published=已发表；accepted=accepted/prepublication；all=全部",
                    },
                },
                # RESULT.md 实证：必填字段必须写进 required，不能靠 description 暗示
                "required": ["source", "query"],
            },
        ),
        ToolEntry(
            name="download_and_import_paper",
            description=(
                "下载并安全校验单篇论文 PDF，再导入个人知识库索引（含去重与补偿）。"
                "参数：candidate（含 title/authors/year/doi/source_links 的候选记录）；"
                "下载主机由服务端白名单校验，不接受任意 URL（沿用既有 usenix 同源白名单）。"
            ),
            entry=(
                "backend.app.paper_discovery.application.paper_import.import_candidate"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "candidate": {
                        "type": "object",
                        "description": "待下载导入的候选论文记录（由 search_paper_catalog 结果选定）",
                        "properties": {
                            "title": {"type": "string"},
                            "authors": {"type": "array", "items": {"type": "string"}},
                            "year": {"type": "integer"},
                            "doi": {"type": "string"},
                            "source_links": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "候选 PDF 链接；实际下载主机由服务端白名单校验，非白名单一律拒绝",
                            },
                        },
                        "required": ["title"],
                    }
                },
                "required": ["candidate"],
            },
        ),
        ToolEntry(
            name="kb_search",
            description=(
                "在个人知识库执行混合检索（稠密 + sparse + RRF + 可选重排），"
                "返回与问题相关的文本片段与引用。参数：question、top_k（默认 5）、"
                "chunker（v1/v2，按切分版本隔离）。"
            ),
            entry=(
                "backend.app.knowledge_base.infrastructure.retrieve.hybrid_search"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "检索问题"},
                    "top_k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "description": "返回片段数，默认 5",
                    },
                    "chunker": {
                        "type": "string",
                        "enum": ["v1", "v2"],
                        "description": "切分版本隔离：v1 或 v2",
                    },
                },
                "required": ["question"],
            },
        ),
        ToolEntry(
            name="kb_ask",
            description=(
                "基于知识库检索结果调用本地生成模型回答用户问题，返回带引用的流式回答。"
                "参数：question、top_k、chunker（v1/v2）。"
            ),
            entry="backend.app.api.routes_kb.kb_ask",
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "要回答的问题"},
                    "top_k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "description": "检索片段数，默认 5",
                    },
                    "chunker": {
                        "type": "string",
                        "enum": ["v1", "v2"],
                        "description": "切分版本隔离：v1 或 v2",
                    },
                },
                "required": ["question"],
            },
        ),
    ]
