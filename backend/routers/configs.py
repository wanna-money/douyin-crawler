from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from datetime import datetime, timezone
from backend.database import get_session
from backend.models import SearchConfig
from backend.schemas import SearchConfigCreate, SearchConfigUpdate
from backend.scheduler import sync_jobs

router = APIRouter(prefix="/api/configs", tags=["configs"])


@router.get("")
def list_configs(session: Session = Depends(get_session)):
    return session.exec(select(SearchConfig)).all()


@router.post("")
def create_config(payload: SearchConfigCreate, session: Session = Depends(get_session)):
    config = SearchConfig(**payload.model_dump())
    session.add(config)
    session.commit()
    session.refresh(config)
    sync_jobs()
    return config


@router.put("/{config_id}")
def update_config(config_id: int, payload: SearchConfigUpdate, session: Session = Depends(get_session)):
    config = session.get(SearchConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Not found")
    for key, val in payload.model_dump(exclude_none=True).items():
        setattr(config, key, val)
    config.updated_at = datetime.now(timezone.utc)
    session.add(config)
    session.commit()
    session.refresh(config)
    sync_jobs()
    return config


@router.delete("/{config_id}")
def delete_config(config_id: int, session: Session = Depends(get_session)):
    config = session.get(SearchConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Not found")
    session.delete(config)
    session.commit()
    sync_jobs()
    return {"ok": True}
