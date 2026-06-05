import json
import re
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from dotenv import load_dotenv

from backend.database import init_db, get_engine
from backend.routers import configs, tasks, downloads, settings, cookies, channels, logs, llm
from backend.scheduler import start_scheduler, scheduler

load_dotenv()


def _setup_logging() -> None:
    """配置全局日志：带时区的时间戳，自动读取 TZ 环境变量。"""
    tz_name = os.getenv("TZ", "Asia/Shanghai")
    try:
        offset_hours = {
            "Asia/Shanghai": 8, "Asia/Beijing": 8, "Asia/Chongqing": 8,
            "Asia/Hong_Kong": 8, "Asia/Taipei": 8, "Asia/Tokyo": 9,
            "UTC": 0, "America/New_York": -5, "America/Los_Angeles": -8,
            "Europe/London": 0, "Europe/Berlin": 1,
        }.get(tz_name, 8)
        tz = timezone(timedelta(hours=offset_hours))
    except Exception:
        tz = timezone(timedelta(hours=8))

    class LocalFormatter(logging.Formatter):
        def formatTime(self, record, datefmt=None):
            dt = datetime.fromtimestamp(record.created, tz=tz)
            return dt.strftime("%Y-%m-%d %H:%M:%S %z")

    fmt = LocalFormatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
    handler = logging.StreamHandler()
    handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # 避免重复添加
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)

    # 降低噪音
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)


_setup_logging()

_CST = timezone(timedelta(hours=8))
# 匹配 ISO datetime 字符串，无时区后缀（如 "2026-06-05T03:27:29.131583"）
_NAIVE_DT_RE = re.compile(
    r'"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)"'
)


def _add_cst(m: re.Match) -> str:
    return f'"{m.group(1)}+08:00"'


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

    @app.middleware("http")
    async def inject_cst_timezone(request: Request, call_next):
        response = await call_next(request)
        if response.headers.get("content-type", "").startswith("application/json"):
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            body = _NAIVE_DT_RE.sub(_add_cst, body.decode()).encode()
            headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
            return Response(content=body, status_code=response.status_code,
                            headers=headers, media_type="application/json")
        return response


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
