# backend/routers/cookies.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from backend.database import get_session
from backend.models import CookieAccount
from backend.schemas import CookieAccountCreate, CookieAccountUpdate

router = APIRouter(prefix="/api/cookies", tags=["cookies"])


@router.get("")
def list_cookies(session: Session = Depends(get_session)):
    return session.exec(select(CookieAccount)).all()


@router.post("")
def create_cookie(payload: CookieAccountCreate, session: Session = Depends(get_session)):
    if payload.is_default:
        for acc in session.exec(select(CookieAccount)).all():
            acc.is_default = False
        session.flush()
    acc = CookieAccount(**payload.model_dump())
    session.add(acc)
    session.commit()
    session.refresh(acc)
    return acc


@router.put("/{cookie_id}")
def update_cookie(cookie_id: int, payload: CookieAccountUpdate, session: Session = Depends(get_session)):
    acc = session.get(CookieAccount, cookie_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Not found")
    if payload.is_default:
        for a in session.exec(select(CookieAccount)).all():
            a.is_default = False
        session.flush()
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(acc, k, v)
    session.add(acc)
    session.commit()
    session.refresh(acc)
    return acc


@router.delete("/{cookie_id}")
def delete_cookie(cookie_id: int, session: Session = Depends(get_session)):
    acc = session.get(CookieAccount, cookie_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Not found")
    session.delete(acc)
    session.commit()
    return {"ok": True}


@router.post("/{cookie_id}/set-default")
def set_default_cookie(cookie_id: int, session: Session = Depends(get_session)):
    target = session.get(CookieAccount, cookie_id)
    if not target:
        raise HTTPException(status_code=404, detail="Not found")
    for a in session.exec(select(CookieAccount)).all():
        a.is_default = (a.id == cookie_id)
    session.commit()
    session.refresh(target)
    return target
