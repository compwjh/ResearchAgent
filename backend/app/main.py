from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router
from backend.app.core.config import FRONTEND_DIR
from backend.app.services.kb import backfill_chunker_defaults, mark_interrupted_on_startup


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动时做两件收尾工作（spec-012），任一失败都只记录、不阻塞服务启动。

    1. 把上次运行残留为 `indexing` 的切分版本标记为 `failed`
       —— 异步任务无法跨进程存活，否则进度条会永远卡住；
    2. 给 spec-011 遗留的索引点补齐 `chunker` 等字段
       —— 否则按版本过滤会让旧论文检索不到。
    """
    try:
        interrupted = mark_interrupted_on_startup()
        if interrupted:
            print(f"[kb] {interrupted} 个中断的索引任务已标记为失败，可点「重建索引」重跑")
    except Exception as error:  # 启动清理失败不应阻止服务可用
        print(f"[kb] 启动清理失败（已忽略）：{error}")

    try:
        filled = backfill_chunker_defaults()
        if filled:
            print(f"[kb] 已为 {filled} 个旧索引点补齐切分版本字段（按 v1 语义）")
    except Exception as error:
        print(f"[kb] 旧索引数据迁移失败（已忽略）：{error}")

    yield


app = FastAPI(title="Research Agent", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")
app.include_router(router)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")
