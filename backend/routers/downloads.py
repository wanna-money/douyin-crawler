from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from backend.database import get_session
from backend.models import DownloadRecord

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


@router.get("")
def list_downloads(session: Session = Depends(get_session)):
    return session.exec(select(DownloadRecord).order_by(DownloadRecord.created_at.desc()).limit(200)).all()
