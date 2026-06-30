import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import chat, memory, novel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


def create_app() -> FastAPI:
    app = FastAPI(title="Novel Writing Agent")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(novel.router)
    app.include_router(chat.router)
    app.include_router(memory.router)

    static_dir = settings.base_dir / "static"

    @app.get("/")
    def home():
        return FileResponse(static_dir / "index.html")

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app


app = create_app()
