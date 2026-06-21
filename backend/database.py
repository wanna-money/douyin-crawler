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
    _migrate(engine)


def _migrate(engine):
    """补充新增列，保持向前兼容。"""
    from sqlalchemy import text
    from backend.models import _DEFAULT_PROMPT
    with engine.connect() as conn:
        # searchconfig 新增 llm_prompt_template
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(searchconfig)"))}
        if "llm_prompt_template" not in cols:
            conn.execute(text("ALTER TABLE searchconfig ADD COLUMN llm_prompt_template TEXT NOT NULL DEFAULT ''"))
            conn.execute(text("UPDATE searchconfig SET llm_prompt_template = :p WHERE llm_prompt_template = ''"),
                         {"p": _DEFAULT_PROMPT})
            conn.commit()
        if "llm_config_id" not in cols:
            conn.execute(text("ALTER TABLE searchconfig ADD COLUMN llm_config_id INTEGER REFERENCES llmconfig(id)"))
            conn.commit()

        # llmconfig 表存在旧的 prompt_template 列（NOT NULL 无默认值），导致新增时报错
        # 通过重建表去掉该列（SQLite 不支持 DROP COLUMN / ALTER COLUMN）
        llm_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(llmconfig)"))}
        if "prompt_template" in llm_cols:
            conn.execute(text("""
                CREATE TABLE llmconfig_new (
                    id INTEGER NOT NULL PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    base_url VARCHAR NOT NULL,
                    api_key VARCHAR NOT NULL DEFAULT '',
                    model VARCHAR NOT NULL DEFAULT 'gpt-4o-mini',
                    is_default BOOLEAN NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL
                )
            """))
            conn.execute(text("""
                INSERT INTO llmconfig_new (id, name, base_url, api_key, model, is_default, created_at)
                SELECT id, name, base_url, api_key, model, is_default, created_at FROM llmconfig
            """))
            conn.execute(text("DROP TABLE llmconfig"))
            conn.execute(text("ALTER TABLE llmconfig_new RENAME TO llmconfig"))
            conn.commit()


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
