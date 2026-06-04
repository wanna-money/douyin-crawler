from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from backend.database import get_session
from backend.models import TaskRecord, SearchConfig
from backend.task_runner import run_task

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class NoteUpdate(BaseModel):
    note: str


@router.get("")
def list_tasks(session: Session = Depends(get_session)):
    return session.exec(select(TaskRecord).order_by(TaskRecord.created_at.desc()).limit(100)).all()


@router.post("/trigger/{config_id}")
async def trigger_task(config_id: int, background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    config = session.get(SearchConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    background_tasks.add_task(run_task, config_id=config_id)
    return {"message": f"Task for config '{config.name}' started"}


@router.patch("/{task_id}/note")
def update_note(task_id: int, body: NoteUpdate, session: Session = Depends(get_session)):
    task = session.get(TaskRecord, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Not found")
    task.note = body.note
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.delete("/{task_id}")
def delete_task(task_id: int, session: Session = Depends(get_session)):
    task = session.get(TaskRecord, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Not found")
    session.delete(task)
    session.commit()
    return {"ok": True}


@router.delete("")
def clear_tasks(session: Session = Depends(get_session)):
    tasks = session.exec(select(TaskRecord)).all()
    for t in tasks:
        session.delete(t)
    session.commit()
    return {"ok": True, "deleted": len(tasks)}
