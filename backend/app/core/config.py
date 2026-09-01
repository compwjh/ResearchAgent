import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[3]
FRONTEND_DIR = BASE_DIR / "frontend"
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen3.8:27b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

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
# 留空表示不启用重排（本机 reranker 模型暂不可用，自动降级为 RRF 结果）
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "")
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
