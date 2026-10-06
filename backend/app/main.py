import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from backend.app.api import common
from backend.app.api.common import paper_request_validation_error_response, recover_paper_catalog_searches
from backend.app.api.routes import router
from backend.app.knowledge_base.application import (
    FinalizeBundleStore,
    recover_failed_reindexes,
)
from backend.app.platform.capability_scheduler import (
    start_capability_scheduler,
    stop_capability_scheduler,
)
from backend.app.platform.config import FRONTEND_DIR, KB_DIR
from backend.app.platform.warmup import start_warmup


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动时做两件收尾工作（spec-012），任一失败都只记录、不阻塞服务启动。

    1. 把上次运行残留为 `indexing` 的切分版本标记为 `failed`
       —— 异步任务无法跨进程存活，否则进度条会永远卡住；
    2. 给 spec-011 遗留的索引点补齐 `chunker` 等字段
       —— 否则按版本过滤会让旧论文检索不到。
    """
    try:
        recovered = recover_paper_catalog_searches()
        if recovered:
            print(f"[paper-search] 已将 {recovered} 个中断任务恢复为 queued")
    except Exception as error:
        print(f"[paper-search] 启动恢复失败（已忽略）：{error}")

    try:
        recovered = common.recover_research_tasks()
        if recovered:
            print(f"[research] 已将 {recovered} 个运行中任务收敛为 interrupted")
    except Exception as error:
        print(f"[research] 启动收敛失败（已忽略）：{error}")

    try:
        FinalizeBundleStore(KB_DIR.parents[1]).require_generation()
    except Exception as error:
        # The API generation gate returns the stable error; startup remains
        # available for upload/list/health and never mutates the old
        # collection as a side effect of boot.
        print(f"[kb] index generation gate not ready: {getattr(error, 'code', 'INDEX_REBUILD_REQUIRED')}")

    # spec-036 Task06：把环境故障期遗留的陈旧 failed 重建任务重排队一次
    # （幂等标记防重启风暴；单个文档或整体异常都只记日志，绝不阻塞启动）。
    try:
        recovered = recover_failed_reindexes()
        if recovered:
            print(f"[kb] 启动自愈：已将 {recovered} 个陈旧失败重建任务重排队")
    except Exception as error:
        print(f"[kb] 启动自愈失败（已忽略）：{error}")

    # 首屏就绪优化：在既有索引代次收尾之后，后台（非阻塞 daemon 线程）做预热编排。
    # 任一预热项失败只记日志标 failed，绝不阻塞启动、绝不抛异常。
    try:
        start_warmup()
    except Exception as error:  # 即使预热编排本身异常，也绝不影响服务启动
        print(f"[warmup] 启动预热编排失败（已忽略）：{error}")
    # spec-035 Bug3：启动即全量探测一次模型能力入库，之后每 24h 一轮；
    # 失败只记录，不阻塞服务启动。
    try:
        start_capability_scheduler()
    except Exception as error:
        print(f"[capabilities] 调度器启动失败（已忽略）：{error}")

    try:
        yield
    finally:
        await stop_capability_scheduler()
        # Login pages hold both a site lock and the persistent profile lock.
        # Close the item-scoped handles before releasing the manager so a
        # graceful shutdown cannot leave a stale authenticated session behind.
        sessions = tuple(common.paper_browser_sessions.values())
        for session in sessions:
            try:
                session.close()
            except Exception as error:
                print(f"[paper-browser] 会话关闭失败（已忽略）：{error}")
        common.paper_browser_sessions.clear()
        manager = common.paper_browser_manager
        if manager is not None:
            try:
                manager.close()
            except Exception as error:
                print(f"[paper-browser] 管理器关闭失败（已忽略）：{error}")


NO_CACHE = "no-cache"


class NoCacheStaticFiles(StaticFiles):
    """静态资源允许缓存，但每次使用前必须回源做 ETag / Last-Modified 校验。

    这样前端就不必靠手工改 `?v=N` 令牌才能拿到新版本：命中校验时
    `StaticFiles` 仍会返回 304，不产生实际传输。
    """

    def file_response(
        self,
        full_path: os.PathLike,
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = NO_CACHE
        return response


app = FastAPI(title="Research Agent", lifespan=lifespan)
app.mount("/assets", NoCacheStaticFiles(directory=FRONTEND_DIR), name="assets")
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(request: Request, exc: RequestValidationError):
    """保持论文检索接口的错误体契约，同时不改变其他接口行为。"""
    response = paper_request_validation_error_response(request, exc)
    if response is not None:
        return response
    return await request_validation_exception_handler(request, exc)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": NO_CACHE})


@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
def spa_fallback(full_path: str) -> FileResponse:
    """SPA 兜底：`/c/{conversation_id}` 等前端路由在直接访问/刷新时必须回 index.html。

    前端靠 `window.location.pathname` 做客户端路由（``app.js`` 中 `/c/<id>` 的匹配），
    但服务端此前只注册了 ``/``，直接刷新深链会得到 JSON 404、页面打不开。
    ``/assets`` 挂载与 ``/api`` 路由注册在先，会先于本兜底命中；未命中的
    ``/api/*`` 仍须返回真正的 404，不能被伪装成 200 的 HTML。
    """
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")
    return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": NO_CACHE})
