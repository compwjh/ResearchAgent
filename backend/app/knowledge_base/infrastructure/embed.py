"""稠密/稀疏向量编码（spec-011）。

稠密：Ollama `bge-m3`（dim=1024，已归一化）。
    注意：必须显式传 `options.num_batch`，默认 2048 会触发 Metal OOM（见 011-tech-review R1）。
稀疏：jieba 分词 + CRC32 稳定哈希（禁止用 Python 内置 hash，见 R3）。
"""

import math
import re
import time
import zlib
from typing import Dict, List, Optional, Sequence

import httpx
from qdrant_client import models

from backend.app.platform.config import (
    EMBED_MODEL,
    KB_EMBED_BATCH_SIZE,
    KB_EMBED_NUM_BATCH,
    OLLAMA_BASE_URL,
)
from backend.app.platform.observability import record_event
from backend.app.platform.observability.safe import safe_call

# 稀疏向量槽位数量（约 100 万），个人知识库量级下碰撞概率可忽略
SPARSE_DIM = 1 << 20

# 拉丁词/数字 或 连续中文片段
_SEGMENT_PATTERN = re.compile(r"[a-z0-9][a-z0-9\-_.]*|[\u4e00-\u9fff]+")

_jieba_module = None


class EmbeddingError(RuntimeError):
    """向量化失败（Ollama 不可达、返回结构异常、OOM 重试后仍失败）。"""


def _jieba():
    global _jieba_module
    if _jieba_module is None:
        import jieba  # 延迟导入：首次导入会构建前缀词典，避免影响启动与单测

        _jieba_module = jieba
    return _jieba_module


def tokenize(text: str) -> List[str]:
    """中英文混合分词：中文走 jieba，英文/数字按词提取，统一小写。"""
    tokens: List[str] = []
    for segment in _SEGMENT_PATTERN.findall((text or "").lower()):
        if segment.isascii():
            tokens.append(segment)
        else:
            tokens.extend(token for token in _jieba().cut(segment) if token.strip())
    return [token for token in tokens if token]


def sparse_index(token: str) -> int:
    """词 -> 稀疏维度的稳定映射（跨进程、跨重启一致）。

    必须用 crc32：Python 内置 hash(str) 受 PYTHONHASHSEED 随机化影响，
    重启后映射会变化，导致历史稀疏向量静默失效（011-tech-review R3）。
    """
    return zlib.crc32(token.encode("utf-8")) % SPARSE_DIM


def encode_sparse(text: str) -> models.SparseVector:
    """亚线性 tf 权重 `1 + ln(tf)`，IDF 由 Qdrant `Modifier.IDF` 在检索时补上（R4）。"""
    counts: Dict[int, float] = {}
    for token in tokenize(text):
        index = sparse_index(token)
        counts[index] = counts.get(index, 0.0) + 1.0
    if not counts:
        return models.SparseVector(indices=[], values=[])
    indices = sorted(counts)
    values = [round(1.0 + math.log(counts[index]), 6) for index in indices]
    return models.SparseVector(indices=indices, values=values)


def embed_texts(
    texts: Sequence[str],
    *,
    model: Optional[str] = None,
    num_batch: Optional[int] = None,
) -> List[List[float]]:
    """批量稠密向量化；内部按 KB_EMBED_BATCH_SIZE 分批。

    注意：`num_batch` 必须 ≥ 单条输入的 token 数，否则 Ollama 会静默截断（HTTP 200 但向量无效）。
    因此这里**不做**减半重试——降低 num_batch 只会让情况更糟；网络类错误才重试一次。
    """
    started_at = time.perf_counter()
    metadata = {"model": model or EMBED_MODEL, "text_count": len(texts)}
    try:
        vectors: List[List[float]] = []
        batch_size = max(1, KB_EMBED_BATCH_SIZE)
        for start in range(0, len(texts), batch_size):
            vectors.extend(_embed_batch(texts[start : start + batch_size], model, num_batch))
        safe_call(record_event,
            name="kb.embedding",
            metadata={**metadata, "status": "ok"},
            duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
        )
        return vectors
    except Exception as error:  # 记录后原样抛出，绝不吞、绝不改变异常类型
        safe_call(record_event,
            name="kb.embedding",
            metadata={**metadata, "status": "error", "error_type": type(error).__name__},
            duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
        )
        raise


def _embed_batch(
    batch: Sequence[str],
    model: Optional[str],
    num_batch: Optional[int],
) -> List[List[float]]:
    if not batch:
        return []
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/embed"
    payload = {
        "model": model or EMBED_MODEL,
        "input": list(batch),
        "options": {"num_batch": int(num_batch or KB_EMBED_NUM_BATCH)},
    }
    try:
        response = httpx.post(url, json=payload, timeout=180, trust_env=False)
    except httpx.HTTPError as error:
        # 仅网络抖动重试一次；参数类问题重试无意义
        try:
            response = httpx.post(url, json=payload, timeout=180, trust_env=False)
        except httpx.HTTPError:
            raise EmbeddingError(f"无法连接 Ollama：{error}") from error

    if response.status_code != 200:
        detail = ""
        try:
            detail = str(response.json().get("error", ""))
        except ValueError:
            detail = response.text[:200]
        raise EmbeddingError(f"Ollama 向量化失败（HTTP {response.status_code}）{detail}")

    vectors = response.json().get("embeddings") or []
    if len(vectors) != len(batch) or any(not vector for vector in vectors):
        raise EmbeddingError("Ollama 返回的向量数量与输入不一致或存在空向量")
    return [list(map(float, vector)) for vector in vectors]
