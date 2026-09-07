"""双链路 A/B 基准入口（spec-013 task-05）。

独立脚本，**不进入默认请求路径**：正常聊天 / KB 请求仍只跑一次，
本脚本不会被 routes.py 调用，仅在被显式执行时跑。

对同一问题，按需依次跑 `langchain`（LangGraph + ChatOllama）与
`direct`（直连 Ollama /api/chat，可拿原生耗时分解），收集
`derive_metrics` 派生的指标、按链路取均值，并计算 `direct` 相对
`langchain` 的差值（langchain 减 direct），直观看出中间层
（LangChain / HTTP 封装）引入了多少额外开销。

可重复命令示例：
    .venv/bin/python scripts/bench_ollama_routes.py --runs 3
    .venv/bin/python scripts/bench_ollama_routes.py --json > bench.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

# 直接执行脚本时 sys.path[0] 是 scripts/，加入项目根使 `backend` 包可导入。
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 通过模块属性引用 run_chat，便于测试 patch `backend.app.chat.application.chat_runner.run_chat`。
from backend.app.chat.application import chat_runner
from backend.app.core.config import MODEL_NAME
from backend.app.platform.observability import derive_metrics

DEFAULT_QUESTION = "用一句话解释什么是向量数据库？"
DEFAULT_ROUTES: Sequence[str] = ("langchain", "direct")
# diff 固定语义：langchain - direct（正数表示 direct 更快 / 开销更小）。
DIFF_KEYS = ("ttft_ms", "client_wall_ms", "overhead_ms", "total_ms")
# avg / diff 统一保留 3 位小数，保证输出可重复、可读。
_ROUND = 3


def _average_metrics(samples: List[Dict[str, float]]) -> Dict[str, float]:
    """对一次链路的多轮指标取均值；空样本返回空 dict（不伪造）。"""
    if not samples:
        return {}
    keys = set()
    for sample in samples:
        keys.update(sample.keys())
    avg: Dict[str, float] = {}
    for key in keys:
        values = [float(sample[key]) for sample in samples if key in sample]
        if values:
            avg[key] = round(sum(values) / len(values), _ROUND)
    return avg


def _diff(routes_result: Dict[str, Dict[str, Dict]]) -> Dict[str, float]:
    """计算 direct 相对 langchain 的差值：langchain - direct。

    缺失（无成功样本）的指标按 0 处理，如实相减，不伪造。
    """
    langchain_avg = routes_result.get("langchain", {}).get("avg", {}) or {}
    direct_avg = routes_result.get("direct", {}).get("avg", {}) or {}
    diff: Dict[str, float] = {}
    for key in DIFF_KEYS:
        lc = float(langchain_avg.get(key, 0.0))
        dc = float(direct_avg.get(key, 0.0))
        diff[key] = round(lc - dc, _ROUND)
    return diff


def run_benchmark(
    question: str,
    model: str,
    routes: Sequence[str] = DEFAULT_ROUTES,
    runs: int = 1,
) -> Dict:
    """对每个 route 跑 `runs` 轮，收集指标并聚合。

    纯函数（仅依赖 `backend.app.chat.application.chat_runner.run_chat` 与 `derive_metrics`），
    便于测试 patch 后断言结构。单次异常记入该 route 的 `errors`，不中断整体。
    """
    routes_result: Dict[str, Dict[str, Dict]] = {}
    for route in routes:
        samples: List[Dict[str, float]] = []
        errors: List[str] = []
        for _ in range(runs):
            try:
                run = chat_runner.run_chat(question, model, route=route)
                # 必须把事件迭代完，.result 才会被填好。
                for _ in run:
                    pass
                metrics = derive_metrics(run.result)
                samples.append({key: round(float(value), _ROUND) for key, value in metrics.items()})
            except Exception as error:  # noqa: BLE001 - 基准要吞单次异常并继续
                errors.append(f"{type(error).__name__}: {error}")
        routes_result[route] = {
            "samples": samples,
            "avg": _average_metrics(samples),
            "errors": errors,
        }

    return {
        "question": question,
        "model": model,
        "runs": runs,
        "routes": routes_result,
        "diff": _diff(routes_result),
    }


def _format_summary(report: Dict) -> str:
    """人类可读摘要：每链路一行，含 TTFT/总墙钟/load/prefill/eval/tokens/s。"""
    lines: List[str] = []
    lines.append(f"question: {report['question']}")
    lines.append(f"model: {report['model']}  runs: {report['runs']}")
    lines.append("")
    header = f"{'route':<10}{'ttft_ms':>10}{'wall_ms':>12}{'load_ms':>10}{'prefill_ms':>11}{'eval_ms':>10}{'tok/s':>10}  errors"
    lines.append(header)
    for route, data in report["routes"].items():
        avg = data.get("avg", {})
        errors = data.get("errors", [])
        lines.append(
            f"{route:<10}"
            f"{avg.get('ttft_ms', 0.0):>10.1f}"
            f"{avg.get('client_wall_ms', 0.0):>12.1f}"
            f"{avg.get('load_ms', 0.0):>10.1f}"
            f"{avg.get('prompt_eval_ms', 0.0):>11.1f}"
            f"{avg.get('eval_ms', 0.0):>10.1f}"
            f"{avg.get('tokens_per_sec', 0.0):>10.1f}"
            f"   {'; '.join(errors) if errors else ''}"
        )
    lines.append("")
    lines.append("diff (langchain - direct，正数表示 direct 更快/开销更小):")
    for key, value in report["diff"].items():
        lines.append(f"   {key:<16}{value:>10.1f}")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="双链路 A/B 基准：对比 langchain 与 direct 的开销。",
    )
    parser.add_argument("--question", default=DEFAULT_QUESTION, help="待对比的问题。")
    parser.add_argument("--model", default=MODEL_NAME, help="模型名（默认取 config.MODEL_NAME）。")
    parser.add_argument("--runs", type=int, default=1, help="每个链路重复次数。")
    parser.add_argument(
        "--routes",
        default=",".join(DEFAULT_ROUTES),
        help="逗号分隔的链路名，默认 langchain,direct。",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="只输出 JSON（便于重定向到文件）。",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    routes = [r.strip() for r in args.routes.split(",") if r.strip()] or list(DEFAULT_ROUTES)

    report = run_benchmark(args.question, args.model, routes=routes, runs=args.runs)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_format_summary(report))
        print()
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
