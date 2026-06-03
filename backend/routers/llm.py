# backend/routers/llm.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
import httpx
from backend.database import get_session
from backend.models import LLMConfig
from backend.schemas import LLMConfigCreate, LLMConfigUpdate

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("")
def list_llm_configs(session: Session = Depends(get_session)):
    return session.exec(select(LLMConfig)).all()


@router.post("")
def create_llm_config(payload: LLMConfigCreate, session: Session = Depends(get_session)):
    if payload.is_default:
        for c in session.exec(select(LLMConfig)).all():
            c.is_default = False
        session.flush()
    cfg = LLMConfig(**payload.model_dump())
    session.add(cfg)
    session.commit()
    session.refresh(cfg)
    return cfg


@router.put("/{llm_id}")
def update_llm_config(llm_id: int, payload: LLMConfigUpdate, session: Session = Depends(get_session)):
    cfg = session.get(LLMConfig, llm_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Not found")
    if payload.is_default:
        for c in session.exec(select(LLMConfig)).all():
            c.is_default = False
        session.flush()
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(cfg, k, v)
    session.add(cfg)
    session.commit()
    session.refresh(cfg)
    return cfg


@router.delete("/{llm_id}")
def delete_llm_config(llm_id: int, session: Session = Depends(get_session)):
    cfg = session.get(LLMConfig, llm_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Not found")
    session.delete(cfg)
    session.commit()
    return {"ok": True}


@router.post("/{llm_id}/set-default")
def set_default_llm(llm_id: int, session: Session = Depends(get_session)):
    target = session.get(LLMConfig, llm_id)
    if not target:
        raise HTTPException(status_code=404, detail="Not found")
    for c in session.exec(select(LLMConfig)).all():
        c.is_default = (c.id == llm_id)
    session.commit()
    session.refresh(target)
    return target


@router.post("/{llm_id}/test")
async def test_llm_config(llm_id: int, session: Session = Depends(get_session)):
    cfg = session.get(LLMConfig, llm_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{cfg.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {cfg.api_key}"},
                json={
                    "model": cfg.model,
                    "messages": [{"role": "user", "content": "回复数字1"}],
                    "max_tokens": 5,
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            answer = resp.json()["choices"][0]["message"]["content"]
        return {"ok": True, "response": answer}
    except Exception as e:
        return {"ok": False, "error": str(e)}
