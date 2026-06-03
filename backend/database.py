from sqlmodel import SQLModel, create_engine, Session
from typing import Generator
import os
from pathlib import Path

_engine = None

# 项目根目录（backend/ 的上一级），确保不论从哪个目录启动服务，数据库始终在固定位置
_PROJECT_ROOT = Path(__file__).parent.parent
_DEFAULT_DB_PATH = str(_PROJECT_ROOT / "douyin.db")


def get_engine(url: str = None):
    global _engine
    if url:
        # Accept shorthand ":memory:" and plain file paths without scheme
        if url == ":memory:":
            from sqlalchemy.pool import StaticPool
            return create_engine(
                "sqlite:///:memory:",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        elif not url.startswith("sqlite://"):
            url = f"sqlite:///{url}"
        return create_engine(url, connect_args={"check_same_thread": False})
    if _engine is None:
        db_path = os.getenv("DB_PATH", _DEFAULT_DB_PATH)
        _engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
    return _engine


def init_db(engine=None):
    if engine is None:
        engine = get_engine()
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
