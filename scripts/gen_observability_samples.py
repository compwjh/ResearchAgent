#!/usr/bin/env python3
"""生成任务 06 所需的固定观测样本（spec-013）。

任务 06 要在 Langfuse 原生 Dashboard 上验证六项统计，验证必须基于
**可复现、可分组**的真实样本，而不是随手发几个请求。

样本矩阵：冷/热各 N 次、短/长输入各 N 次、聊天/知识库各 N 次、真实失败 ≥2 次。

可重复运行：
    # 快速验证（每类 1 次、不卸载模型，几十秒内完成）
    .venv/bin/python scripts/gen_observability_samples.py --runs 1 --skip-cold
    # 全量（默认每类 5 次，会真正卸载模型来制造冷启动，较慢）
    .venv/bin/python scripts/gen_observability_samples.py --model qwen3.5:9b

注意：脚本会真正调用本机 Ollama 与知识库，默认请用一个快的小模型，不要用 27B。
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# 直接执行本脚本时，sys.path[0] 是 scripts/ 而不是项目根，需手动补上，
# 否则 `import backend` 找不到包。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx  # noqa: E402

from backend.app.chat.application.chat_runner import run_chat  # noqa: E402
from backend.app.knowledge_base.application import CHUNKER_V1, build_prompt, hybrid_search  # noqa: E402
from backend.app.platform.config import (  # noqa: E402
    LANGFUSE_ENABLED,
    MODEL_NAME,
    OLLAMA_BASE_URL,
)
from backend.app.platform.observability import (  # noqa: E402
    derive_metrics,
    end_trace,
    flush,
    record_ollama_generation,
    start_trace,
    utc_now,
)
from backend.app.platform.ollama_direct import (  # noqa: E402
    OllamaChatResult,
    OllamaTimings,
)

SHORT_QUESTION = "用一句话说明什么是向量检索。"

# 长输入样本：拼接成数千字符，用于观察输入规模与延迟的相关性。
_LONG_BASE = (
    "请结合下面这段背景材料回答问题。背景材料如下："
    "向量检索先把文本切成片段，再用嵌入模型把每个片段映射成高维向量，"
    "检索时把问题也映射成向量，在向量库里按余弦相似度或内积找出最接近的片段，"
    "最后把这些片段拼进 prompt 交给大模型生成答案。"
)

KB_QUESTION = "这些论文主要讨论了什么？"

# 冷/热标记互斥，不要让一条样本同时带两个标记。
TAG_COLD = "cold"
TAG_HOT = "hot"
TAG_SHORT = "short"
TAG_LONG = "long"
TAG_CHAT = "chat"
TAG_KB = "kb"
TAG_SAMPLE = "sample"


def build_long_question(target_chars: int = 4000) -> str:
    """拼出指定长度的长输入，用于输入规模相关性分析。"""
    question = SHORT_QUESTION
    while len(question) < target_chars:
        question += _LONG_BASE
    return question + "\n请回答：什么是向量检索？"


def unload_model(model: str, base_url: str, timeout: float = 120.0) -> Optional[str]:
    """让 Ollama 卸载模型，使下一次调用成为真正的冷启动。

    通过 `keep_alive: 0` 实现：Ollama 处理完该请求后立即把模型移出显存/内存。
    必须 `trust_env=False`，否则 macOS 系统代理会把指向 localhost 的请求截走返回 503。
    返回错误信息（成功时为 None）。
    """
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "keep_alive": 0,
    }
    try:
        response = httpx.post(url, json=payload, timeout=timeout, trust_env=False)
        if response.status_code != 200:
            return f"HTTP {response.status_code}: {response.text[:200]}"
    except Exception as error:  # noqa: BLE001 — 卸载失败只记录，不中断采样
        return f"{type(error).__name__}: {error}"
    return None


def _run_chat_once(
    *,
    model: str,
    question: str,
    route: str,
    tags: List[str],
    prompt: Optional[str] = None,
    name: str = "ollama-chat",
    extra_metadata: Optional[Dict[str, Any]] = None,
    think: bool = True,
) -> Dict[str, Any]:
    """跑一次聊天并在结束后上报。返回该样本的关键指标。"""
    started = utc_now()
    wall_start = time.perf_counter()

    run = run_chat(question, model, route=route, prompt=prompt, think=think)
    for _ in run.events:
        pass  # 必须迭代完，.result 才会被填好

    wall_ms = (time.perf_counter() - wall_start) * 1000.0
    result = run.result

    metadata = {"sample_client_wall_ms": round(wall_ms, 3), "think_enabled": think}
    if extra_metadata:
        metadata.update(extra_metadata)

    record_ollama_generation(
        model=model,
        prompt_messages=[{"role": "user", "content": prompt or question}],
        result=result,
        route=run.route,
        name=name,
        started_at=started,
        tags=tags,
        extra_metadata=metadata,
    )
    flush()

    metrics = derive_metrics(result)
    return {
        "route": run.route,
        "tags": list(tags),
        "name": name,
        "client_wall_ms": round(wall_ms, 3),
        **{key: round(value, 3) for key, value in metrics.items()},
    }


def _run_kb_once(
    *,
    model: str,
    question: str,
    route: str,
    tags: List[str],
    top_k: int,
    chunker: str,
    think: bool = True,
) -> Optional[Dict[str, Any]]:
    """跑一次知识库问答（真实检索 + 生成），同一 trace 下记录各阶段。"""
    utc_now()
    start_trace("kb-ask", tags=[TAG_KB, TAG_SAMPLE])
    try:
        hits = hybrid_search(question, top_k=top_k, chunker=chunker)
        if not hits:
            return {
                "route": route,
                "tags": list(tags),
                "name": "kb.generation",
                "skipped": "知识库未命中，未生成（保持早退语义，不上报 generation）",
                "hit_count": 0,
            }
        prompt = build_prompt(question, hits)
        return _run_chat_once(
            model=model,
            question=question,
            route=route,
            tags=tags,
            prompt=prompt,
            name="kb.generation",
            extra_metadata={
                "top_k": top_k,
                "chunker": chunker,
                "hit_count": len(hits),
                "question_chars": len(question),
                "prompt_chars": len(prompt),
            },
            think=think,
        )
    finally:
        end_trace()


def _run_failure_once(*, model: str, tags: List[str]) -> Dict[str, Any]:
    """产生一次**真实**的失败样本（不是伪造的）。

    做法：临时把 ollama_direct 模块里的 OLLAMA_BASE_URL 指向一个死端口，
    再走直连链路 —— httpx 会真实连接失败并抛异常。
    注意必须在 `chat_direct` 读取该模块全局变量的层面打补丁才有效
    （config 里的同名常量是导入期绑定，运行时改它无效）。
    """
    import backend.app.platform.ollama_direct as ollama_direct

    original = ollama_direct.OLLAMA_BASE_URL
    ollama_direct.OLLAMA_BASE_URL = "http://127.0.0.1:1"  # 死端口

    started = utc_now()
    wall_start = time.perf_counter()
    result: Optional[OllamaChatResult] = None
    error_type: Optional[str] = None
    try:
        run = run_chat("触发一次真实失败", model, route="direct")
        for _ in run.events:
            pass
        result = run.result
    except Exception as error:  # noqa: BLE001 — 失败样本就是要捕获真实异常
        error_type = type(error).__name__
    finally:
        ollama_direct.OLLAMA_BASE_URL = original

    wall_ms = (time.perf_counter() - wall_start) * 1000.0
    if result is None:
        # 连接阶段就失败，没有 result；墙钟用真实测量值，不要填 0。
        result = OllamaChatResult(
            content="",
            thinking="",
            timings=OllamaTimings(),
            timings_available=False,
            first_token_ms=0.0,
            client_wall_ms=wall_ms,
        )

    record_ollama_generation(
        model=model,
        prompt_messages=[{"role": "user", "content": "触发一次真实失败"}],
        result=result,
        route="direct",
        name="ollama-chat",
        started_at=started,
        tags=tags,
        success=False,
        error_type=error_type or "UnknownError",
    )
    flush()

    return {
        "route": "direct",
        "tags": list(tags),
        "name": "ollama-chat",
        "success": False,
        "error_type": error_type or "UnknownError",
        "client_wall_ms": round(wall_ms, 3),
    }


def generate(args: argparse.Namespace) -> Dict[str, Any]:
    """按矩阵生成样本，返回结构化结果。"""
    model = args.model
    routes = [item.strip() for item in args.routes.split(",") if item.strip()]
    runs = args.runs
    long_question = build_long_question(args.long_chars)

    # 思考开关：受控样本（冷/热/短/长）默认关闭思考 —— 实测思考模型一次简单问答
    # 就能先"想"30+ 秒，会把 load/prefill 的差异完全淹没，冷/热对比失去意义；
    # 聊天与 KB 样本默认保留思考，因为"思考占比"本身也是六项统计之一。
    controlled_think = args.think == "on"
    conversational_think = args.think != "off"

    samples: Dict[str, List[Dict[str, Any]]] = {
        "cold": [],
        "hot": [],
        "short": [],
        "long": [],
        "chat": [],
        "kb": [],
        "failure": [],
    }
    notes: List[str] = []

    for route in routes:
        # ---- 冷启动：每次前真正卸载模型 ----
        for index in range(runs):
            if args.skip_cold:
                notes.append("已用 --skip-cold，冷样本实际不是冷启动")
            else:
                error = unload_model(model, OLLAMA_BASE_URL)
                if error:
                    notes.append(f"卸载模型失败（第 {index + 1} 次）：{error}")
            samples["cold"].append(
                _run_chat_once(
                    model=model,
                    question=SHORT_QUESTION,
                    route=route,
                    tags=[TAG_SAMPLE, TAG_COLD, TAG_SHORT, TAG_CHAT, route],
                    think=controlled_think,
                )
            )

        # ---- 热调用：紧接着连续调用，不卸载 ----
        for _ in range(runs):
            samples["hot"].append(
                _run_chat_once(
                    model=model,
                    question=SHORT_QUESTION,
                    route=route,
                    tags=[TAG_SAMPLE, TAG_HOT, TAG_SHORT, TAG_CHAT, route],
                    think=controlled_think,
                )
            )

        # ---- 短输入 ----
        for _ in range(runs):
            samples["short"].append(
                _run_chat_once(
                    model=model,
                    question=SHORT_QUESTION,
                    route=route,
                    tags=[TAG_SAMPLE, TAG_SHORT, TAG_CHAT, route],
                    think=controlled_think,
                )
            )

        # ---- 长输入 ----
        for _ in range(runs):
            samples["long"].append(
                _run_chat_once(
                    model=model,
                    question=long_question,
                    route=route,
                    tags=[TAG_SAMPLE, TAG_LONG, TAG_CHAT, route],
                    think=controlled_think,
                )
            )

        # ---- 聊天链路（不带冷/热、长/短标记，保持维度干净）----
        for _ in range(runs):
            samples["chat"].append(
                _run_chat_once(
                    model=model,
                    question=SHORT_QUESTION,
                    route=route,
                    tags=[TAG_SAMPLE, TAG_CHAT, route],
                    think=conversational_think,
                )
            )

        # ---- 知识库问答 ----
        for _ in range(runs):
            samples["kb"].append(
                _run_kb_once(
                    model=model,
                    question=KB_QUESTION,
                    route=route,
                    tags=[TAG_SAMPLE, TAG_KB, route],
                    top_k=args.top_k,
                    chunker=args.chunker,
                    think=conversational_think,
                )
            )

    # ---- 真实失败：≥2 次 ----
    for _ in range(max(2, args.failures)):
        samples["failure"].append(
            _run_failure_once(model=model, tags=[TAG_SAMPLE, TAG_CHAT, "failure", "direct"])
        )

    return _summarize(model=model, routes=routes, runs=runs, samples=samples, notes=notes)


def _summarize(
    *,
    model: str,
    routes: List[str],
    runs: int,
    samples: Dict[str, List[Dict[str, Any]]],
    notes: List[str],
) -> Dict[str, Any]:
    """给每个类别算平均指标，便于快速核对样本是否真的产生了差异。"""
    summary: Dict[str, Any] = {}
    for name, items in samples.items():
        numeric = [item for item in items if isinstance(item.get("ttft_ms"), (int, float))]
        if not numeric:
            summary[name] = {"count": len(items), "note": "无可用数值指标"}
            continue
        summary[name] = {
            "count": len(items),
            "avg_ttft_ms": round(sum(item["ttft_ms"] for item in numeric) / len(numeric), 3),
            "avg_load_ms": round(sum(item["load_ms"] for item in numeric) / len(numeric), 3),
            "avg_client_wall_ms": round(
                sum(item.get("client_wall_ms", 0.0) for item in numeric) / len(numeric), 3
            ),
            "avg_tokens_per_sec": round(
                sum(item["tokens_per_sec"] for item in numeric) / len(numeric), 3
            ),
            "cold_start_hits": sum(1 for item in numeric if item.get("is_cold_start")),
        }

    return {
        "model": model,
        "routes": routes,
        "runs_per_category": runs,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "notes": notes,
        "summary": summary,
        "samples": samples,
    }


def _print_summary(result: Dict[str, Any]) -> None:
    print(f"\n模型 {result['model']} ｜ 链路 {','.join(result['routes'])}")
    header = f"{'类别':<10}{'次数':>6}{'平均TTFT':>12}{'平均加载':>12}{'平均墙钟':>12}{'tokens/s':>10}{'冷启动':>8}"
    print(header)
    print("-" * len(header.encode("utf-8")))
    for name, item in result["summary"].items():
        if "avg_ttft_ms" not in item:
            print(f"{name:<10}{item['count']:>6}  （{item.get('note', '无指标')}）")
            continue
        print(
            f"{name:<10}{item['count']:>6}{item['avg_ttft_ms']:>12.1f}"
            f"{item['avg_load_ms']:>12.1f}{item['avg_client_wall_ms']:>12.1f}"
            f"{item['avg_tokens_per_sec']:>10.2f}{item['cold_start_hits']:>8}"
        )
    for note in result["notes"]:
        print(f"[注意] {note}")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成任务 06 的固定观测样本")
    parser.add_argument("--model", default=MODEL_NAME, help="采样用的模型（建议用快的小模型）")
    parser.add_argument("--runs", type=int, default=5, help="每类样本次数")
    parser.add_argument("--routes", default="direct", help="逗号分隔，如 direct 或 langchain,direct")
    parser.add_argument("--skip-cold", action="store_true", help="跳过卸载（调试用，冷样本将不是真冷启动）")
    parser.add_argument("--failures", type=int, default=2, help="失败样本数量（至少 2）")
    parser.add_argument("--top-k", type=int, default=5, help="知识库检索条数")
    parser.add_argument("--chunker", default=CHUNKER_V1, help="知识库切分版本")
    parser.add_argument("--long-chars", type=int, default=4000, help="长输入的目标字符数")
    parser.add_argument(
        "--think",
        choices=["off", "chat-only", "on"],
        default="chat-only",
        help=(
            "思考开关：off=全部关闭；chat-only=受控样本(冷/热/短/长)关闭、聊天与 KB 保留（默认）；"
            "on=全部开启。受控样本必须关思考，否则几十秒的思考会淹没 load/prefill 差异。"
        ),
    )
    parser.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "artifacts" / "observability-samples.json"),
        help="JSON 结果输出路径",
    )
    args = parser.parse_args()

    if not LANGFUSE_ENABLED:
        print(
            "错误：LANGFUSE_ENABLED 未开启，样本不会上报，Dashboard 上看不到任何数据。\n"
            "请先设置 LANGFUSE_ENABLED=true 以及 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 再运行。",
            file=sys.stderr,
        )
        return 1

    result = generate(args)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    _print_summary(result)
    print(f"\nJSON 已写入：{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
