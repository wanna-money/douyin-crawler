import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from backend.database import init_db, get_engine
from backend.routers import configs, tasks, downloads, settings, cookies, channels, logs, llm
from backend.scheduler import start_scheduler, scheduler

load_dotenv()


def create_app(engine=None) -> FastAPI:
    if engine:
        from backend import database
        database._engine = engine

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(engine)
        if engine is None:
            start_scheduler()
        yield
        if engine is None and scheduler.running:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="抖音内容采集系统", lifespan=lifespan)
    app.include_router(configs.router)
    app.include_router(tasks.router)
    app.include_router(downloads.router)
    app.include_router(settings.router)
    app.include_router(cookies.router)
    app.include_router(channels.router)
    app.include_router(logs.router)
    app.include_router(llm.router)

    frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
    if os.path.exists(frontend_dist):
        app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # API 路由不应走 SPA fallback
            if full_path.startswith("api/"):
                from fastapi import HTTPException
                raise HTTPException(status_code=404)
            return FileResponse(os.path.join(frontend_dist, "index.html"))

    return app


app = create_app()


def start():
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)


if __name__ == "__main__":
    start()
