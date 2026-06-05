from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select
from backend.database import get_engine
from backend.models import SearchConfig
from backend.task_runner import run_task

scheduler = AsyncIOScheduler()


def _make_job_id(config_id: int, index: int = 0) -> str:
    return f"config_{config_id}_{index}"


def _config_job_ids(config_id: int) -> list[str]:
    """返回该 config 所有已注册的子 job id"""
    prefix = f"config_{config_id}_"
    return [job.id for job in scheduler.get_jobs() if job.id.startswith(prefix)]


async def _run_config(config_id: int):
    await run_task(config_id=config_id)


def sync_jobs():
    engine = get_engine()
    with Session(engine) as session:
        rows = session.exec(select(SearchConfig)).all()
        configs = [
            {"id": c.id, "enabled": c.enabled, "cron": c.cron}
            for c in rows
        ]

    valid_job_ids: set[str] = set()

    for config in configs:
        config_id = config["id"]
        # 清掉旧的子 job，重新注册
        for old_id in _config_job_ids(config_id):
            scheduler.remove_job(old_id)

        if not config["enabled"]:
            continue

        segments = [s.strip() for s in config["cron"].split(";") if s.strip()]
        for idx, seg in enumerate(segments):
            parts = seg.split()
            if len(parts) != 5:
                continue
            minute, hour, day, month, day_of_week = parts
            trigger = CronTrigger(
                minute=minute, hour=hour, day=day,
                month=month, day_of_week=day_of_week,
            )
            job_id = _make_job_id(config_id, idx)
            scheduler.add_job(
                _run_config,
                trigger=trigger,
                id=job_id,
                args=[config_id],
                replace_existing=True,
            )
            valid_job_ids.add(job_id)

    # 清理已删除 config 的残留 job
    for job in scheduler.get_jobs():
        if job.id.startswith("config_") and job.id not in valid_job_ids:
            scheduler.remove_job(job.id)


def start_scheduler():
    scheduler.start()
    sync_jobs()
