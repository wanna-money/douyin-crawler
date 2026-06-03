from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select
from backend.database import get_engine
from backend.models import SearchConfig
from backend.task_runner import run_task

scheduler = AsyncIOScheduler()


def _make_job_id(config_id: int) -> str:
    return f"config_{config_id}"


async def _run_config(config_id: int):
    await run_task(config_id=config_id)


def sync_jobs():
    engine = get_engine()
    # 在 session 内提取所有需要的字段，避免 session 关闭后的 DetachedInstanceError
    with Session(engine) as session:
        rows = session.exec(select(SearchConfig)).all()
        configs = [
            {
                "id": c.id,
                "enabled": c.enabled,
                "cron": c.cron,
            }
            for c in rows
        ]

    current_ids = {job.id for job in scheduler.get_jobs()}

    for config in configs:
        job_id = _make_job_id(config["id"])
        if not config["enabled"]:
            if job_id in current_ids:
                scheduler.remove_job(job_id)
            continue
        parts = config["cron"].split()
        if len(parts) != 5:
            continue
        minute, hour, day, month, day_of_week = parts
        trigger = CronTrigger(
            minute=minute, hour=hour, day=day,
            month=month, day_of_week=day_of_week,
        )
        if job_id in current_ids:
            scheduler.reschedule_job(job_id, trigger=trigger)
        else:
            scheduler.add_job(
                _run_config,
                trigger=trigger,
                id=job_id,
                args=[config["id"]],
                replace_existing=True,
            )

    valid_ids = {_make_job_id(c["id"]) for c in configs}
    for job_id in list(current_ids):
        if job_id.startswith("config_") and job_id not in valid_ids:
            scheduler.remove_job(job_id)


def start_scheduler():
    scheduler.start()
    sync_jobs()
