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
# 上报内容截断阈值（字符）：避免超长输入/输出/思考过程撑爆单事件大小限制
OBS_MAX_INPUT_CHARS = int(os.getenv("OBS_MAX_INPUT_CHARS", "20000"))
OBS_MAX_OUTPUT_CHARS = int(os.getenv("OBS_MAX_OUTPUT_CHARS", "20000"))
