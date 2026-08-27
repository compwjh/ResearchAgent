from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router
from backend.app.core.config import FRONTEND_DIR

app = FastAPI(title="Research Agent")
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")
app.include_router(router)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")
