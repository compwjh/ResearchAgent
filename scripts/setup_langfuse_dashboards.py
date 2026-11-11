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
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import httpx

try:  # POSIX 文件锁；非 POSIX 平台降级为无锁（仅本地脚本使用）
    import fcntl
except ImportError:  # pragma: no cover - 本项目运行于 macOS / Linux
    fcntl = None

logger = logging.getLogger("setup_langfuse_dashboards")

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

# widget 清单分页：vendor 的 listPublicDashboardWidgets 只按 projectId 分页、默认 limit=50，
# 必须按 meta.totalPages 循环翻页（limit 保守取 100），不能假设单页能取全。
WIDGETS_PAGE_LIMIT = 100

# 脚本自记录「本次创建的 widget_id」清单（本地文件，非 DB），跨 --force 重跑保留。
DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs/sdd/plans/047/runs/task-02/widget-manifest.json"
)


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

    def list_widgets(self) -> List[Dict[str, Any]]:
        """只读枚举项目内全部 widget，按 meta.totalPages 翻页（异常 fail-open 不抛）。

        仅用于 --force 前的只读清单备份 / 重建后总数校验；绝不作为删除依据
        （vendor 无 createdBy/来源过滤，无法区分用户手工 widget）。
        """
        widgets: List[Dict[str, Any]] = []
        page = 1
        while True:
            try:
                response = httpx.get(
                    self._url("/dashboard-widgets"),
                    auth=self.auth,
                    params={"page": page, "limit": WIDGETS_PAGE_LIMIT},
                    timeout=30,
                )
                response.raise_for_status()
                payload = response.json()
                chunk = payload.get("data", [])
                meta = payload.get("meta", {})
                total_pages = int(meta.get("totalPages", 1) or 1)
            except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
                logger.warning(
                    "列举 widget 失败（fail-open，已取 %d 个，page=%d）：%s",
                    len(widgets), page, exc,
                )
                break
            widgets.extend(chunk)
            if page >= total_pages or not chunk:
                break
            page += 1
        return widgets

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

    def delete_widget(self, widget_id: str) -> None:
        """按 ID 删除单个 widget（404 视为已不存在，fail-open 记日志不抛）。"""
        response = httpx.delete(
            self._url(f"/dashboard-widgets/{widget_id}"), auth=self.auth, timeout=30
        )
        if response.status_code == 404:
            logger.warning("widget「%s」已不存在，跳过删除", widget_id)
            return
        if response.status_code >= 400:
            raise RuntimeError(
                f"删除 widget「{widget_id}」失败：{response.status_code} {response.text[:200]}"
            )


# ---------------------------------------------------------------- widget manifest
# 本地文件、非 DB。只记录「本脚本 create_widget 返回的 ID」，--force 只按这些 ID 删/复用。
# 原子写（临时文件 + os.replace）+ 进程间文件锁，对齐 backend/eval_042/report.py 的纪律。


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_manifest(project_id: str = "") -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "project_id": project_id,
        "created_at": _utc_now(),
        "source": "setup_langfuse_dashboards.py",
        "widgets": [],
    }


def load_manifest(path: Path) -> Dict[str, Any]:
    """读取 manifest；缺失 / 损坏 / 结构异常一律降级为空清单（不抛、不创建文件）。"""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _empty_manifest()
    except (OSError, ValueError) as exc:
        logger.warning("读取 widget manifest 失败（降级为空清单）：%s", exc)
        return _empty_manifest()
    if not isinstance(data, dict) or not isinstance(data.get("widgets"), list):
        logger.warning("widget manifest 结构异常（降级为空清单）：%s", path)
        return _empty_manifest()
    return data


def _atomic_write(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            tmp = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
        os.replace(tmp, path)
    except BaseException:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
        raise


def _mutate_manifest(path: Path, mutate: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
    """在同一把文件锁内完成 read-modify-atomic-write，避免并发重跑丢写。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with open(lock_path, "a", encoding="utf-8") as lock:
        if fcntl is not None:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            data = load_manifest(path)
            mutate(data)
            _atomic_write(path, data)
            return data
        finally:
            if fcntl is not None:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def record_widgets(
    path: Path, entries: List[Dict[str, Any]], project_id: str = ""
) -> Dict[str, Any]:
    """每次 create_widget 成功后立即追加写盘（先于 create_dashboard / add_placement）。"""
    def mutate(data: Dict[str, Any]) -> None:
        if not data.get("project_id") and project_id:
            data["project_id"] = project_id
        known = {w.get("id") for w in data["widgets"] if isinstance(w, dict)}
        for item in entries:
            if item["id"] not in known:
                data["widgets"].append(item)
                known.add(item["id"])

    return _mutate_manifest(path, mutate)


def remove_widgets(path: Path, widget_ids: Any) -> Dict[str, Any]:
    """从 manifest 移除指定 ID（--force 删掉旧 widget 后同步）。"""
    ids = set(widget_ids)

    def mutate(data: Dict[str, Any]) -> None:
        data["widgets"] = [
            w for w in data["widgets"]
            if not (isinstance(w, dict) and w.get("id") in ids)
        ]

    return _mutate_manifest(path, mutate)


def _build_one(
    builder: "DashboardBuilder",
    spec: Dict[str, Any],
    index: int,
    manifest_path: Path,
    width: int,
    height: int,
    project_id: str,
) -> None:
    name = spec["name"]
    widget_ids: List[str] = []
    for widget in spec["widgets"]:
        widget_id = builder.create_widget(widget)
        widget_ids.append(widget_id)
        record_widgets(
            manifest_path,
            [{
                "id": widget_id,
                "name": widget["name"],
                "dashboard": name,
                "dashboard_index": index,
                "created_at": _utc_now(),
            }],
            project_id=project_id,
        )
    dashboard_id = builder.create_dashboard(name, spec["description"])
    for widget_id in widget_ids:
        builder.add_placement(dashboard_id, widget_id, width, height)

    print(f"[完成] {name} —— {len(widget_ids)} 个 widget")
    print(f"       {builder.host}/project/local-proj/dashboards/{dashboard_id}")


def run(
    *,
    force: bool,
    builder: "DashboardBuilder",
    manifest_path: Path,
    width: int = 3,
    height: int = 2,
) -> int:
    """创建 / 重建六组看板；manifest_path 可注入，便于契约测试用 tmp_path 隔离。"""
    existing = {item["name"]: item["id"] for item in builder.list_dashboards()}
    project_id = os.getenv("LANGFUSE_PROJECT_ID", "")
    created = 0
    skipped = 0

    if force:
        # 只读清单快照（fail-open），仅供备份 / 日志；绝不作为删除依据。
        snapshot = builder.list_widgets()
        print(f"[重建] 只读 widget 清单：{len(snapshot)} 个（仅备份，不用于删除）")
        manifest = load_manifest(manifest_path)

        # 阶段 1：先删同名 dashboard —— 清掉 placement，避免随后 DELETE widget 触发 409。
        for spec in DASHBOARDS:
            name = spec["name"]
            if name in existing:
                print(f"[重建] {name}")
                builder.delete_dashboard(existing[name])

        # 阶段 2：只按 manifest 内脚本自记录的 ID 删旧 widget（禁止按名称 / 全量删）。
        old_ids = [
            w["id"] for w in manifest.get("widgets", [])
            if isinstance(w, dict) and w.get("id")
        ]
        for widget_id in old_ids:
            builder.delete_widget(widget_id)
        if old_ids:
            remove_widgets(manifest_path, old_ids)

        # 阶段 3：重建全部 6 组；成功创建 widget 后立即更新 manifest。
        for index, spec in enumerate(DASHBOARDS):
            _build_one(builder, spec, index, manifest_path, width, height, project_id)
            created += 1
    else:
        for index, spec in enumerate(DASHBOARDS):
            name = spec["name"]
            if name in existing:
                print(f"[跳过] {name}（已存在，用 --force 重建）")
                skipped += 1
                continue
            _build_one(builder, spec, index, manifest_path, width, height, project_id)
            created += 1

    print(f"\n新建 {created} 个，跳过 {skipped} 个。")
    print(
        "提醒：思考占比 / 成功率 / 错误率依赖自定义 metadata，原生看板无法聚合；"
        "真散点与阶段甘特图也无对应图表类型 —— 这些已列入任务 07 自研视图。"
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="创建 spec-013 任务 06 的六组原生 Dashboard")
    parser.add_argument("--force", action="store_true", help="同名 dashboard 先删除再重建")
    parser.add_argument("--width", type=int, default=3, help="widget 网格宽度")
    parser.add_argument("--height", type=int, default=2, help="widget 网格高度")
    args = parser.parse_args(argv)

    host = os.getenv("LANGFUSE_HOST", "http://127.0.0.1:3000")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    if not public_key or not secret_key:
        print("错误：请先设置 LANGFUSE_PUBLIC_KEY 与 LANGFUSE_SECRET_KEY", file=sys.stderr)
        return 1

    builder = DashboardBuilder(host, public_key, secret_key)
    return run(
        force=args.force,
        builder=builder,
        manifest_path=DEFAULT_MANIFEST_PATH,
        width=args.width,
        height=args.height,
    )


if __name__ == "__main__":
    raise SystemExit(main())
