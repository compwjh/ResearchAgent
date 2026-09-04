#!/usr/bin/env python3
"""通过 Langfuse public API 创建 spec-013 任务 06 的六组原生 Dashboard。

为什么用 API 而不是点界面：可重跑、可版本化、换机器能一键重建。

用法：
    LANGFUSE_HOST=http://127.0.0.1:3000 \
    LANGFUSE_PUBLIC_KEY=pk-lf-...  LANGFUSE_SECRET_KEY=sk-lf-... \
    .venv/bin/python scripts/setup_langfuse_dashboards.py

    --force  删除同名 dashboard 后重建（默认遇到同名则跳过）

## 已知能力边界（原生 Dashboard 做不到，转任务 07 自研视图）
1. 真散点图（输入规模 vs 延迟）——widget 图表类型只有时序/柱状/饼/数字/直方图/透视表，无散点。
2. 单次调用的阶段甘特图（load→prefill→first token→decode 同时间轴）——无此类图表。
3. 依赖我们自定义 metadata 的统计：thinking_chars / input_chars / output_chars /
   success / error_type 都不是可聚合 measure，原生无法算「思考占比」「成功率」「错误率」。
   （能聚合的只有 observations 的固定 measure，以及我们上报的 7 个 numeric score。）
这些缺口如实记录，不在原生看板里伪造。
"""

import argparse
import os
import sys
from typing import Any, Dict, List, Optional

import httpx

# ---------------------------------------------------------------- 基础定义
# 这些取值是探测 Langfuse v4.27.0 源码与 API 实测得到的，改前先重新探测。
SCORE_VIEW = "scores-numeric"
OBS_VIEW = "observations"

CHART_NUMBER = "NUMBER"
CHART_LINE = "LINE_TIME_SERIES"
CHART_BAR = "VERTICAL_BAR"

# 我们上报的 numeric score（见 backend/app/observability/spans.py 的 SCORE_METRICS）
SCORE_TTFT = "ttft_ms"
SCORE_LOAD = "load_ms"
SCORE_PREFILL = "prompt_eval_ms"
SCORE_EVAL = "eval_ms"
SCORE_OVERHEAD = "overhead_ms"
SCORE_TPS = "tokens_per_sec"
SCORE_COLD = "is_cold_start"

OBS_GENERATION_FILTER = {"column": "type", "operator": "=", "value": "GENERATION", "type": "string"}


def score_filter(score_name: str) -> List[Dict[str, Any]]:
    """按 numeric score 名称过滤（scores-numeric 视图的 name 列即 score 名）。"""
    return [{"column": "name", "operator": "=", "value": score_name, "type": "string"}]


def score_widget(
    name: str,
    score_name: str,
    agg: str,
    chart_type: str = CHART_NUMBER,
    description: str = "",
) -> Dict[str, Any]:
    """基于我们上报的 numeric score 建一个指标卡。"""
    return {
        "name": name,
        "description": description,
        "view": SCORE_VIEW,
        "dimensions": [],
        "metrics": [{"measure": "value", "agg": agg}],
        "filters": score_filter(score_name),
        "chartType": chart_type,
    }


def obs_widget(
    name: str,
    measure: str,
    agg: str,
    chart_type: str = CHART_NUMBER,
    description: str = "",
    filters: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """基于 Langfuse 原生 observations measure 建一个指标卡。"""
    return {
        "name": name,
        "description": description,
        "view": OBS_VIEW,
        "dimensions": [],
        "metrics": [{"measure": measure, "agg": agg}],
        "filters": filters if filters is not None else [OBS_GENERATION_FILTER],
        "chartType": chart_type,
    }


# ---------------------------------------------------------------- 六组看板
DASHBOARDS: List[Dict[str, Any]] = [
    {
        "name": "01 TTFT 分解与冷启动对比",
        "description": (
            "首 token 慢到底慢在哪：拆成模型加载(load)、输入预填充(prompt_eval)、"
            "解码(eval) 三段，并用 is_cold_start 的均值表示冷启动占比。"
            "冷/热对比看 load_ms：热调用通常 <20ms，冷启动可达数千毫秒。"
        ),
        "widgets": [
            score_widget("TTFT 平均", SCORE_TTFT, "avg", description="首 token 延迟均值"),
            score_widget("TTFT P95", SCORE_TTFT, "p95", description="首 token 延迟 95 分位"),
            score_widget("模型加载 load 平均", SCORE_LOAD, "avg", description="冷启动主要来源"),
            score_widget("模型加载 load 最大", SCORE_LOAD, "max", description="最慢一次模型加载"),
            score_widget("输入预填充 平均", SCORE_PREFILL, "avg", description="与输入长度强相关"),
            score_widget("解码 eval 平均", SCORE_EVAL, "avg", description="含思考过程时的耗时"),
            score_widget(
                "冷启动占比", SCORE_COLD, "avg",
                description="is_cold_start 的均值即冷启动比例（0~1）",
            ),
            score_widget("模型加载 时间趋势", SCORE_LOAD, "avg", chart_type=CHART_LINE),
        ],
    },
    {
        "name": "02 分位数与慢请求",
        "description": (
            "TTFT 与各阶段的 P50/P95/P99 与最慢值，用于判断长尾有多长。"
            "注：排序榜单需要维度支持，原生 widget 只能给聚合值；慢请求排行见任务 07。"
        ),
        "widgets": [
            score_widget("TTFT P50", SCORE_TTFT, "p50"),
            score_widget("TTFT P95", SCORE_TTFT, "p95"),
            score_widget("TTFT P99", SCORE_TTFT, "p99"),
            score_widget("TTFT 最慢", SCORE_TTFT, "max"),
            score_widget("加载 P95", SCORE_LOAD, "p95"),
            score_widget("预填充 P95", SCORE_PREFILL, "p95"),
            score_widget("解码 P95", SCORE_EVAL, "p95"),
            score_widget("网络+框架开销 P95", SCORE_OVERHEAD, "p95",
                         description="客户端墙钟 - 服务端总耗时；langchain 链路无原生 timings 时记为 0"),
        ],
    },
    {
        "name": "03 吞吐与生成速度",
        "description": "每秒生成 token 数、解码耗时与输出规模，用于判断生成速度是否成为瓶颈。",
        "widgets": [
            score_widget("tokens/s 平均（自报）", SCORE_TPS, "avg",
                         description="completion tokens / eval 秒"),
            score_widget("tokens/s P95（自报）", SCORE_TPS, "p95"),
            obs_widget("tokens/s 平均（原生）", "tokensPerSecond", "avg"),
            obs_widget("输出 token 平均", "outputTokens", "avg"),
            obs_widget("输出 token P95", "outputTokens", "p95"),
            score_widget("解码耗时 平均", SCORE_EVAL, "avg"),
        ],
    },
    {
        "name": "04 输入规模与延迟相关性",
        "description": (
            "输入多长会变慢：对比输入 token 规模与预填充/TTFT。"
            "注：真散点图原生不支持（缺口，见任务 07），这里用分位数侧面观察。"
        ),
        "widgets": [
            obs_widget("输入 token 平均", "inputTokens", "avg"),
            obs_widget("输入 token P95", "inputTokens", "p95"),
            obs_widget("整体延迟 P95（原生）", "latency", "p95"),
            obs_widget("TTFT P95（原生）", "timeToFirstToken", "p95",
                       description="Langfuse 原生 TTFT：依据埋点传的 completion_start_time 计算"),
            score_widget("预填充 平均", SCORE_PREFILL, "avg",
                         description="预填充随输入规模增长最明显"),
            score_widget("预填充 P95", SCORE_PREFILL, "p95"),
        ],
    },
    {
        "name": "05 耗时构成占比",
        "description": (
            "一次调用的耗时由哪几段构成：load / prompt_eval / eval / overhead。"
            "注：堆叠占比图需要维度支持，原生只能并列展示各段均值（缺口见任务 07）。"
        ),
        "widgets": [
            score_widget("构成-模型加载", SCORE_LOAD, "avg"),
            score_widget("构成-输入预填充", SCORE_PREFILL, "avg"),
            score_widget("构成-解码", SCORE_EVAL, "avg"),
            score_widget("构成-网络与框架开销", SCORE_OVERHEAD, "avg"),
            score_widget("解码 时间趋势", SCORE_EVAL, "avg", chart_type=CHART_LINE),
            score_widget("TTFT 时间趋势", SCORE_TTFT, "avg", chart_type=CHART_LINE),
        ],
    },
    {
        "name": "06 调用量与延迟趋势",
        "description": (
            "调用量、延迟与 TTFT 随时间的变化。"
            "注：成功率/错误率依赖我们自定义 metadata 里的 success / error_type，"
            "原生 widget 无法聚合自定义 metadata，属已知缺口（见任务 07）。"
        ),
        "widgets": [
            obs_widget("调用量趋势", "count", "sum", chart_type=CHART_LINE),
            obs_widget("延迟 平均趋势", "latency", "avg", chart_type=CHART_LINE),
            obs_widget("延迟 P95 趋势", "latency", "p95", chart_type=CHART_LINE),
            obs_widget("TTFT 平均趋势（原生）", "timeToFirstToken", "avg", chart_type=CHART_LINE),
            obs_widget("输入 token 趋势", "inputTokens", "avg", chart_type=CHART_LINE),
            obs_widget("输出 token 趋势", "outputTokens", "avg", chart_type=CHART_LINE),
        ],
    },
]


class DashboardBuilder:
    def __init__(self, host: str, public_key: str, secret_key: str) -> None:
        self.host = host.rstrip("/")
        self.auth = (public_key, secret_key)
        self.base = f"{self.host}/api/public/unstable"

    def _url(self, path: str) -> str:
        return f"{self.base}{path}"

    def list_dashboards(self) -> List[Dict[str, Any]]:
        response = httpx.get(self._url("/dashboards"), auth=self.auth, timeout=30)
        response.raise_for_status()
        return response.json()["data"]

    def create_widget(self, spec: Dict[str, Any]) -> str:
        response = httpx.post(
            self._url("/dashboard-widgets"), auth=self.auth, json=spec, timeout=30
        )
        if response.status_code >= 400:
            raise RuntimeError(f"创建 widget「{spec['name']}」失败：{response.status_code} {response.text[:300]}")
        return response.json()["id"]

    def create_dashboard(self, name: str, description: str) -> str:
        response = httpx.post(
            self._url("/dashboards"),
            auth=self.auth,
            json={"name": name, "description": description},
            timeout=30,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"创建 dashboard「{name}」失败：{response.status_code} {response.text[:300]}")
        return response.json()["id"]

    def add_placement(self, dashboard_id: str, widget_id: str, width: int, height: int) -> None:
        response = httpx.post(
            self._url(f"/dashboards/{dashboard_id}/placements"),
            auth=self.auth,
            json={"type": "widget", "widgetId": widget_id, "width": width, "height": height},
            timeout=30,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"挂载 widget 失败：{response.status_code} {response.text[:300]}")

    def delete_dashboard(self, dashboard_id: str) -> None:
        response = httpx.delete(
            self._url(f"/dashboards/{dashboard_id}"), auth=self.auth, timeout=30
        )
        if response.status_code >= 400:
            raise RuntimeError(f"删除 dashboard 失败：{response.status_code} {response.text[:200]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="创建 spec-013 任务 06 的六组原生 Dashboard")
    parser.add_argument("--force", action="store_true", help="同名 dashboard 先删除再重建")
    parser.add_argument("--width", type=int, default=3, help="widget 网格宽度")
    parser.add_argument("--height", type=int, default=2, help="widget 网格高度")
    args = parser.parse_args()

    host = os.getenv("LANGFUSE_HOST", "http://127.0.0.1:3000")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    if not public_key or not secret_key:
        print("错误：请先设置 LANGFUSE_PUBLIC_KEY 与 LANGFUSE_SECRET_KEY", file=sys.stderr)
        return 1

    builder = DashboardBuilder(host, public_key, secret_key)
    existing = {item["name"]: item["id"] for item in builder.list_dashboards()}

    created = 0
    skipped = 0
    for spec in DASHBOARDS:
        name = spec["name"]
        if name in existing:
            if args.force:
                print(f"[重建] {name}")
                builder.delete_dashboard(existing[name])
            else:
                print(f"[跳过] {name}（已存在，用 --force 重建）")
                skipped += 1
                continue

        widget_ids = [builder.create_widget(widget) for widget in spec["widgets"]]
        dashboard_id = builder.create_dashboard(name, spec["description"])
        for widget_id in widget_ids:
            builder.add_placement(dashboard_id, widget_id, args.width, args.height)

        print(f"[完成] {name} —— {len(widget_ids)} 个 widget")
        print(f"       {host}/project/local-proj/dashboards/{dashboard_id}")
        created += 1

    print(f"\n新建 {created} 个，跳过 {skipped} 个。")
    print(
        "提醒：思考占比 / 成功率 / 错误率依赖自定义 metadata，原生看板无法聚合；"
        "真散点与阶段甘特图也无对应图表类型 —— 这些已列入任务 07 自研视图。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
