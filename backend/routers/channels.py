# backend/routers/channels.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from backend.database import get_session
from backend.models import NotifyChannel
from backend.schemas import NotifyChannelCreate, NotifyChannelUpdate

router = APIRouter(prefix="/api/channels", tags=["channels"])


@router.get("")
def list_channels(session: Session = Depends(get_session)):
    return session.exec(select(NotifyChannel)).all()


@router.post("")
def create_channel(payload: NotifyChannelCreate, session: Session = Depends(get_session)):
    if payload.is_default:
        for ch in session.exec(select(NotifyChannel)).all():
            ch.is_default = False
        session.flush()
    ch = NotifyChannel(**payload.model_dump())
    session.add(ch)
    session.commit()
    session.refresh(ch)
    return ch


@router.put("/{channel_id}")
def update_channel(channel_id: int, payload: NotifyChannelUpdate, session: Session = Depends(get_session)):
    ch = session.get(NotifyChannel, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Not found")
    if payload.is_default:
        for c in session.exec(select(NotifyChannel)).all():
            c.is_default = False
        session.flush()
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(ch, k, v)
    session.add(ch)
    session.commit()
    session.refresh(ch)
    return ch


@router.delete("/{channel_id}")
def delete_channel(channel_id: int, session: Session = Depends(get_session)):
    ch = session.get(NotifyChannel, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Not found")
    session.delete(ch)
    session.commit()
    return {"ok": True}


@router.post("/{channel_id}/set-default")
def set_default_channel(channel_id: int, session: Session = Depends(get_session)):
    target = session.get(NotifyChannel, channel_id)
    if not target:
        raise HTTPException(status_code=404, detail="Not found")
    for c in session.exec(select(NotifyChannel)).all():
        c.is_default = (c.id == channel_id)
    session.commit()
    session.refresh(target)
    return target


@router.post("/{channel_id}/test")
async def test_channel(channel_id: int, session: Session = Depends(get_session)):
    ch = session.get(NotifyChannel, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Not found")
    # feishu_bot
    if not ch.app_id or not ch.app_secret or not ch.chat_id:
        return {"ok": False, "error": "app_id / app_secret / chat_id 未填写"}
    try:
        from backend.notify.feishu import get_tenant_token, _send
        import json
        token = await get_tenant_token(ch.app_id, ch.app_secret)
        ok = await _send(
            token, ch.chat_id, "text",
            json.dumps({"text": "[抖音采集] 通知渠道连通测试 ✅"})
        )
        return {"ok": ok}
    except Exception as e:
        import httpx
        err_msg = str(e)
        if not err_msg:
            err_type = type(e).__name__
            if "Connect" in err_type:
                err_msg = "无法连接飞书服务器，请检查网络或代理设置（ConnectError）"
            elif "Timeout" in err_type:
                err_msg = "请求飞书超时，请检查网络连接（Timeout）"
            elif "SSL" in err_type:
                err_msg = "SSL 证书错误（SSLError）"
            else:
                err_msg = f"网络请求失败（{err_type}）"
        return {"ok": False, "error": err_msg}


@router.get("/{channel_id}/chats")
async def list_channel_chats(channel_id: int, session: Session = Depends(get_session)):
    """查询该机器人所在的群列表"""
    ch = session.get(NotifyChannel, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Not found")
    if not ch.app_id or not ch.app_secret:
        raise HTTPException(status_code=400, detail="请先填写 app_id 和 app_secret")
    try:
        from backend.notify.feishu import list_bot_chats
        chats = await list_bot_chats(ch.app_id, ch.app_secret)
        return chats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
