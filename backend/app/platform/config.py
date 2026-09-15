import math
import os
import warnings
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[3]
FRONTEND_DIR = BASE_DIR / "frontend"
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen3.8:27b")
# Independent, low-cost semantic classifier used by the durable post-answer
# memory analysis worker.  It is configuration, not a business-logic literal.
MEMORY_ANALYSIS_MODEL = os.getenv("MEMORY_ANALYSIS_MODEL", "qwen3.5:9b").strip() or "qwen3.5:9b"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    warnings.warn(f"{name} must be a boolean; using {default}", RuntimeWarning, stacklevel=2)
    return default


def _env_positive_number(name: str, default, cast):
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = cast(raw)
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError
        if (cast is int and value < 1) or (cast is float and value <= 0):
            raise ValueError
        return value
    except (TypeError, ValueError, OverflowError):
        warnings.warn(
            f"{name} must be a positive {cast.__name__}; using {default}",
            RuntimeWarning,
            stacklevel=2,
        )
        return default


# ---------- 知识库 / RAG（spec-011）----------
KB_DIR = Path(os.getenv("KB_DIR", str(BASE_DIR / "data" / "kb")))
KB_PAPERS_DIR = KB_DIR / "papers"
KB_META_PATH = KB_DIR / "papers.json"
QDRANT_PATH = os.getenv("QDRANT_PATH", str(KB_DIR / "qdrant"))
KB_COLLECTION = os.getenv("KB_COLLECTION", "papers")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))
# ---------- 线上 embedding（OpenAI 兼容 /v1/embeddings，如阿里云 DataWorks）----------
# 默认仍走 Ollama（EMBED_PROVIDER=ollama）。设为非 ollama 值（如 online）即改用
# EMBED_BASE_URL 上的 OpenAI 兼容 embedding 服务，避免依赖本机 Ollama。
# Authorization 头**原样**发送 EMBED_API_KEY，兼容阿里云 `DW-xxx` 这类非 Bearer 形式
# （标准 OpenAI 则在 .env 写 `EMBED_API_KEY=Bearer sk-...`）。
EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "ollama").strip().lower()
EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", "").strip().rstrip("/")
EMBED_API_KEY = os.getenv("EMBED_API_KEY", "").strip()
# bge-m3 的 num_batch 有上下两个实测边界（详见 011-tech-review R1）：
#   下界——num_batch 小于「单条输入的 token 数」时（如 128 对 300 token 的片段），Ollama 日志报
#          "input (N tokens) is too large to process"，但 HTTP 仍返回 200，
#          向量实际只由前几个 token 算出 → 静默劣化，检索结果近乎随机；
#   上界——num_batch=2048（Ollama 默认值）在 36GB M3 Max 上触发 Metal OOM（HTTP 500 Compute error.）。
# 1024 经冷启动实测：33 条 1000 字符（含中文）文本全部正常，无截断、无 OOM。
KB_EMBED_NUM_BATCH = int(os.getenv("KB_EMBED_NUM_BATCH", "1024"))
KB_EMBED_BATCH_SIZE = int(os.getenv("KB_EMBED_BATCH_SIZE", "32"))
KB_TOP_K = int(os.getenv("KB_TOP_K", "5"))
KB_CANDIDATE_POOL = int(os.getenv("KB_CANDIDATE_POOL", "30"))
RERANKER_ENABLED = _env_bool("RERANKER_ENABLED", True)
_reranker_url = os.getenv("RERANKER_BASE_URL", "http://127.0.0.1:11435").strip()
RERANKER_BASE_URL = _reranker_url.rstrip("/") or "http://127.0.0.1:11435"
RERANKER_MODEL_PATH = os.getenv(
    "RERANKER_MODEL_PATH",
    str(BASE_DIR / "data" / "models" / "qwen3-reranker-0.6b-q8_0.gguf"),
).strip()
RERANKER_API_MODEL = os.getenv("RERANKER_API_MODEL", "").strip()
KB_RERANK_CANDIDATES = _env_positive_number("KB_RERANK_CANDIDATES", 20, int)
RERANKER_CONNECT_TIMEOUT_SECONDS = _env_positive_number(
    "RERANKER_CONNECT_TIMEOUT_SECONDS", 2.0, float
)
RERANKER_READ_TIMEOUT_SECONDS = _env_positive_number(
    "RERANKER_READ_TIMEOUT_SECONDS", 60.0, float
)
RERANKER_SERVER_BIN = os.getenv("RERANKER_SERVER_BIN", "").strip()
KB_MAX_UPLOAD_MB = int(os.getenv("KB_MAX_UPLOAD_MB", "50"))

# ---------- 知识库切分 v2（spec-012）----------
# v2 结构边界分析模型（用户 2026-09-01 拍板：量化 27B 换取更准的边界判定）。
# 它是 thinking 模型，调用必须 think:false，否则输出为空。
CHUNK_V2_LLM_MODEL = os.getenv("CHUNK_V2_LLM_MODEL", "qwen3.8-27b-q4")
# chunk 硬上限（字符）：上限内由 LLM 决定边界，超上限强制再切。
CHUNK_V2_MAX_CHARS = int(os.getenv("CHUNK_V2_MAX_CHARS", "1200"))
# 每批送给 LLM 判定的候选边界数量（越大调用越少，但单个 prompt 越长）。
CHUNK_V2_LLM_BATCH = int(os.getenv("CHUNK_V2_LLM_BATCH", "8"))
# 单次 LLM 调用超时（秒）；27B 较慢，超时即降级为纯规则切分，不阻塞上传。
CHUNK_V2_LLM_TIMEOUT = float(os.getenv("CHUNK_V2_LLM_TIMEOUT", "180"))

# ---------- 观测与评估（spec-013）----------
# Langfuse v4 自托管（本机非 Docker 部署，启停脚本见 deploy/langfuse/）。
# 默认关闭：未部署 Langfuse 时项目行为完全不变，埋点失败也不得影响业务。
LANGFUSE_ENABLED = os.getenv("LANGFUSE_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://127.0.0.1:3000")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
# 采样率：1.0 全量上报，0 全不上报。越界值（<0 或 >1 或非数字）回退到 1.0 并告警。
LANGFUSE_SAMPLE_RATE_RAW = os.getenv("LANGFUSE_SAMPLE_RATE", "1.0")
# 上报超时（秒）：观测不得拖慢业务，超时即放弃本次上报。
LANGFUSE_TIMEOUT = int(os.getenv("LANGFUSE_TIMEOUT", "5"))
# 对话链路：langchain（默认，保持既有行为）| direct（直连 Ollama 以采集原生 timings）
OLLAMA_ROUTE = os.getenv("OLLAMA_ROUTE", "langchain").strip().lower()
# 冷启动判定阈值（毫秒）：load_duration 超过该值即标记为冷启动
OBS_COLD_START_THRESHOLD_MS = float(os.getenv("OBS_COLD_START_THRESHOLD_MS", "200"))
# 对话内 Tool 执行（spec-023 Task07）：最大编排轮次、单次模型调用超时（秒）、重试次数。
# 均为可配置常量，默认 max_rounds=4（3~5 之间）、timeout=60s（≥ Task02 冷启动上限）、retry=1。
SKILL_TOOL_MAX_ROUNDS = int(os.getenv("SKILL_TOOL_MAX_ROUNDS", "4"))
SKILL_TOOL_TIMEOUT_SECONDS = float(os.getenv("SKILL_TOOL_TIMEOUT_SECONDS", "60"))
SKILL_TOOL_RETRY = int(os.getenv("SKILL_TOOL_RETRY", "1"))
# 上报内容截断阈值（字符）：避免超长输入/输出/思考过程撑爆单事件大小限制
OBS_MAX_INPUT_CHARS = int(os.getenv("OBS_MAX_INPUT_CHARS", "20000"))
OBS_MAX_OUTPUT_CHARS = int(os.getenv("OBS_MAX_OUTPUT_CHARS", "20000"))

# ---------- 会话上下文压缩与 token 预算（spec-025）----------
# 估算系数统一为「1 token ≈ 1.6 字符」（中英混排保守口径，见 token_budget.CHARS_PER_TOKEN），
# 替换 repository.py 旧有的 `token_budget * 4` 英文口径（与真实用量偏差可达 2 倍）。
# 真 token 只从 platform/ollama_direct.py 回读做观测，本模块不引入 tokenizer。
# 非法配置（≤0）：_env_positive_number 回退默认值并发 RuntimeWarning（spec-025 取安全默认值而非 fail-fast）。
# ---------- Ollama /api/tags 结果缓存（首屏就绪优化）----------
# OLLAMA_TAGS_CACHE_TTL_SECONDS：成功枚举结果的缓存秒数（默认 30）。
#   /api/tags 是同步 HTTP，且被 health/chat/conversations/kb/models 多路由复用；
#   不缓存时 Ollama 不可达会让每个请求都打满 timeout=5
#   （实测 /api/health 5050ms，见 docs/sdd/notes/startup-perf-baseline.md）。
OLLAMA_TAGS_CACHE_TTL_SECONDS = _env_positive_number("OLLAMA_TAGS_CACHE_TTL_SECONDS", 30, int)
# OLLAMA_TAGS_FAILURE_TTL_SECONDS：失败（负）缓存秒数（默认 5）。
#   必须远小于成功 TTL —— 否则一次网络抖动会把「模型列表为空」固化 30s。
#   负缓存只针对网络类 httpx.HTTPError，避免把偶发解析异常也固化。
OLLAMA_TAGS_FAILURE_TTL_SECONDS = _env_positive_number("OLLAMA_TAGS_FAILURE_TTL_SECONDS", 5, int)

# ---------- 启动预热（首屏就绪优化，spec 优化项 P1）----------
# WARMUP_ENABLED：是否启用后台预热（默认开启）。
#   关闭时 /api/kb/health 仍走短超时兜底探测，只是不再做启动预热。
WARMUP_ENABLED = _env_bool("WARMUP_ENABLED", True)
# KB_HEALTH_PROBE_TIMEOUT_SECONDS：/api/kb/health 的 embedding 探测短超时（秒）。
#   不可达时绝不阻塞上百秒（基线 155s 来自 timeout=180 × 2 重试）；优先复用预热注册表，
#   仅当注册表尚无结论时才做一次该时长上限的兜底探测。
KB_HEALTH_PROBE_TIMEOUT_SECONDS = _env_positive_number("KB_HEALTH_PROBE_TIMEOUT_SECONDS", 3, float)
# WARMUP_EMBEDDING_TIMEOUT_SECONDS：预热项「稠密向量化」整体挂起上限（秒）。
#   embed_texts 内部 timeout=180 且网络错误重试一次，不可达时会挂起很久；后台预热用该值
#   包裹，超时即记为 failed，让 /api/ready 尽快收敛到终态（后台线程仍跑完，不影响启动）。
WARMUP_EMBEDDING_TIMEOUT_SECONDS = _env_positive_number("WARMUP_EMBEDDING_TIMEOUT_SECONDS", 30, float)
# WARMUP_QDRANT_TIMEOUT_SECONDS：预热项「Qdrant 连通性」整体挂起上限（秒，默认 10）。
WARMUP_QDRANT_TIMEOUT_SECONDS = _env_positive_number("WARMUP_QDRANT_TIMEOUT_SECONDS", 10, float)
# CHAT_TOTAL_TOKEN_BUDGET：单次模型调用输入 token 硬上限（默认 20000，模型窗口 262144 的保守占比）。
# spec-038 P3：由 8000 上调到 20000（配合 L1/L2/L3 记忆分层后上下文更长），仍为 env 可配。
CHAT_TOTAL_TOKEN_BUDGET = _env_positive_number("CHAT_TOTAL_TOKEN_BUDGET", 20000, int)
# CHAT_COMPACT_TRIGGER_RATIO：装配后 used/budget ≥ 该比例即触发后台异步压缩（默认 0.8）。
CHAT_COMPACT_TRIGGER_RATIO = _env_positive_number("CHAT_COMPACT_TRIGGER_RATIO", 0.8, float)
# CHAT_RECENT_RAW_MESSAGES：压缩后保留的最近原文条数（默认 10，沿用现状）。
CHAT_RECENT_RAW_MESSAGES = _env_positive_number("CHAT_RECENT_RAW_MESSAGES", 10, int)
# CHAT_RAG_BUDGET_CHARS：知识库证据注入独立字符预算（默认 12000；spec-038 P3 由 6000 上调）。
CHAT_RAG_BUDGET_CHARS = _env_positive_number("CHAT_RAG_BUDGET_CHARS", 12000, int)
# CHAT_SUMMARY_BUDGET_CHARS：记忆/摘要段注入字符预算（默认 3000；spec-038 P3 由 1500 上调）。
CHAT_SUMMARY_BUDGET_CHARS = _env_positive_number("CHAT_SUMMARY_BUDGET_CHARS", 3000, int)
# CHAT_PROJECT_INSTR_CHARS：项目指令截断字符上限（默认 5000，沿用现状）。
CHAT_PROJECT_INSTR_CHARS = _env_positive_number("CHAT_PROJECT_INSTR_CHARS", 5000, int)

# ---------- L1 文件记忆层（spec-038 P1）----------
# 记忆真相源改为可编辑 Markdown 文件（USER.md / MEMORY.md / projects/<id>.md）。
# 注意：本阶段只新增配置，**不改** CHAT_TOTAL_TOKEN_BUDGET / CHAT_RAG_BUDGET_CHARS /
# CHAT_SUMMARY_BUDGET_CHARS 的默认值——调预算属 P3 范围。
# MEMORY_DIR：记忆文件根目录（相对仓库根；data/memory/ 已在 .gitignore 中忽略）。
MEMORY_DIR = Path(os.getenv("MEMORY_DIR", str(BASE_DIR / "data" / "memory")))
# MEMORY_INJECT_MAX_CHARS：单次会话启动注入的文件记忆快照字符预算（默认 6000）。
# USER.md 画像优先全量注入，不占该预算（见 markdown_store.load_snapshot）。
MEMORY_INJECT_MAX_CHARS = _env_positive_number("MEMORY_INJECT_MAX_CHARS", 6000, int)
# ---------- L2 会话检索（spec-038 P2 收尾接线）----------
# MEMORY_FTS_ENABLED：消息/记忆写入时是否同步维护 FTS5 会话检索索引（默认开启）。
# 关闭时写入路径完全不建索引也不报错，``session_search`` 仍可调用（返回空结果）。
# 该开关只控制「写入侧自动索引」；显式调用 reindex_all 重建仍可用。
MEMORY_FTS_ENABLED = _env_bool("MEMORY_FTS_ENABLED", True)

# ---------- L3 上下文压缩联动（spec-038 P3）----------
# 压缩前的 flush_memories：给 Agent 一次把重要信息写入 L1 的机会。
# 默认开启；关闭时压缩流程完全不变（不做任何抽取）。
FLUSH_MEMORIES_ENABLED = _env_bool("FLUSH_MEMORIES_ENABLED", True)
# 压缩摘要生成模式：
#   - "llm"  优先调用小模型做**重构式**摘要，超时/异常自动回落规则摘要（fail-open）；
#   - "rule" 只走确定性规则摘要（不触网、可复现）。
COMPACTION_SUMMARY_MODE = os.getenv("COMPACTION_SUMMARY_MODE", "llm").strip().lower() or "llm"
# LLM 摘要调用超时（秒）：超时即放弃本次 LLM 摘要并回落规则摘要。
COMPACTION_SUMMARY_TIMEOUT = _env_positive_number("COMPACTION_SUMMARY_TIMEOUT", 30.0, float)
# flush_memories 的**整体**超时（秒）：压缩前抽取记忆必须有限时，超时即放弃本次 flush
# （fail-open，绝不因模型不可达而拖住压缩 worker）。
COMPACTION_FLUSH_TIMEOUT = _env_positive_number("COMPACTION_FLUSH_TIMEOUT", 20.0, float)
# 装配时工具输出裁剪：最近 N 步保留原文，更早的步骤结构化塌缩为一行。
CHAT_TOOL_OUTPUT_KEEP_RECENT = _env_positive_number("CHAT_TOOL_OUTPUT_KEEP_RECENT", 3, int)

# ---------- 线上模型 provider（spec-035）----------
# 线上模型清单：逗号分隔的 provider:model；解析与注册见 platform/model_catalog.py。
# 非法项在解析时跳过 + warning，不 fail-fast（与上方「warn 后回退」风格一致）。
ONLINE_MODELS = os.getenv("ONLINE_MODELS", "")
