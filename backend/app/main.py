from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api import common
from backend.app.api.common import paper_request_validation_error_response, recover_paper_catalog_searches
from backend.app.api.routes import router
from backend.app.knowledge_base.application import (
    FinalizeBundleStore,
)
from backend.app.platform.config import FRONTEND_DIR, KB_DIR


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
        FinalizeBundleStore(KB_DIR.parents[1]).require_generation()
    except Exception as error:
        # The API generation gate returns the stable error; startup remains
        # available for upload/list/health and never mutates the old
        # collection as a side effect of boot.
        print(f"[kb] index generation gate not ready: {getattr(error, 'code', 'INDEX_REBUILD_REQUIRED')}")

    try:
        yield
    finally:
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


app = FastAPI(title="Research Agent", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")
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
    return FileResponse(FRONTEND_DIR / "index.html")
