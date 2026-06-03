from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from backend.database import get_session
from backend.models import AppSetting
from backend.schemas import SettingUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])

_DEFAULT_KEYS = ["douyin_cookie", "feishu_webhook", "download_dir"]
_DEFAULT_VALUES = {"download_dir": "downloads"}


@router.get("")
def get_settings(session: Session = Depends(get_session)):
    settings = session.exec(select(AppSetting)).all()
    existing = {s.key: s for s in settings}
    for key in _DEFAULT_KEYS:
        if key not in existing:
            s = AppSetting(key=key, value=_DEFAULT_VALUES.get(key, ""))
            session.add(s)
    session.commit()
    return session.exec(select(AppSetting)).all()


@router.put("/{key}")
def update_setting(key: str, payload: SettingUpdate, session: Session = Depends(get_session)):
    stmt = select(AppSetting).where(AppSetting.key == key)
    setting = session.exec(stmt).first()
    if not setting:
        setting = AppSetting(key=key, value=payload.value)
    else:
        setting.value = payload.value
    session.add(setting)
    session.commit()
    session.refresh(setting)
    return setting
