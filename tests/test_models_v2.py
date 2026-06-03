# tests/test_models_v2.py
import pytest
from sqlmodel import Session, select
from backend.database import get_engine, init_db
from backend.models import CookieAccount, NotifyChannel, SearchConfig


@pytest.fixture
def engine():
    e = get_engine(":memory:")
    init_db(e)
    return e


def test_create_cookie_account(engine):
    with Session(engine) as s:
        acc = CookieAccount(name="主号", cookie="sid=abc", is_default=True)
        s.add(acc)
        s.commit()
        s.refresh(acc)
        assert acc.id is not None
        assert acc.is_default is True


def test_create_notify_channel(engine):
    with Session(engine) as s:
        ch = NotifyChannel(name="美食团队", app_id="cli_abc", app_secret="sec", chat_id="oc_123", is_default=True)
        s.add(ch)
        s.commit()
        s.refresh(ch)
        assert ch.id is not None
        assert ch.channel_type == "feishu_bot"
        assert ch.app_id == "cli_abc"
        assert ch.chat_id == "oc_123"


def test_search_config_has_channel_id(engine):
    with Session(engine) as s:
        cfg = SearchConfig(name="test", query="test", channel_id=None)
        s.add(cfg)
        s.commit()
        s.refresh(cfg)
        assert cfg.channel_id is None
