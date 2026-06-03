import pytest
from sqlmodel import Session, select
from backend.database import init_db, get_engine
from backend.models import SearchConfig, TaskRecord


def test_create_search_config():
    engine = get_engine(":memory:")
    init_db(engine)
    with Session(engine) as session:
        config = SearchConfig(
            name="美食探店",
            query="美食探店",
            search_type="search",
            sort_type=2,
            publish_time=7,
            content_type=0,
            limit=50,
            enabled=True,
            cron="0 9 * * *",
            feishu_webhook="https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
        )
        session.add(config)
        session.commit()
        session.refresh(config)
        assert config.id is not None
        assert config.name == "美食探店"


def test_create_task_record():
    engine = get_engine(":memory:")
    init_db(engine)
    with Session(engine) as session:
        record = TaskRecord(config_id=1, status="running", total=0, downloaded=0)
        session.add(record)
        session.commit()
        session.refresh(record)
        assert record.id is not None
        assert record.status == "running"
