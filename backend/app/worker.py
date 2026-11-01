"""In-process job queue and re-check scheduler.

Good enough for a single-instance deployment. To scale out, swap the queue for
a real broker (e.g. Redis + arq/RQ); execute_run() is already self-contained.
"""

import asyncio
import logging

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Business, Run, utcnow
from app.pipeline.engines import get_engines
from app.pipeline.runner import execute_run

log = logging.getLogger(__name__)

_queue: asyncio.Queue[int] | None = None
_tasks: list[asyncio.Task] = []


def enqueue(run_id: int) -> None:
    if _queue is not None:
        _queue.put_nowait(run_id)


def create_run(db, business: Business, trigger: str = "manual", engines: list[str] | None = None,
               samples: int | None = None) -> Run:
    available = list(get_engines())
    chosen = [e for e in (engines or available) if e in available]
    if not chosen:
        raise ValueError("No AI engines are configured. Add OPENAI_API_KEY / GEMINI_API_KEY / "
                         "PERPLEXITY_API_KEY, or set GEO_MOCK=1 to try the product offline.")
    run = Run(business_id=business.id, trigger=trigger, engines=chosen,
              samples_per_query=samples or get_settings().samples_per_query)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


async def _worker() -> None:
    assert _queue is not None
    while True:
        run_id = await _queue.get()
        try:
            await execute_run(run_id)
        except Exception:  # noqa: BLE001
            log.exception("worker crashed on run %s", run_id)
        finally:
            _queue.task_done()


async def _scheduler() -> None:
    s = get_settings()
    while True:
        try:
            with SessionLocal() as db:
                due = db.scalars(
                    select(Business).where(Business.recheck_enabled.is_(True), Business.next_run_at <= utcnow())
                ).all()
                for b in due:
                    busy = db.scalar(select(Run.id).where(Run.business_id == b.id, Run.status.in_(("queued", "running"))))
                    b.next_run_at = None  # set again when the run finishes
                    db.commit()
                    if busy:
                        continue
                    try:
                        run = create_run(db, b, trigger="scheduled")
                        enqueue(run.id)
                        log.info("scheduled re-check for business %s (run %s)", b.id, run.id)
                    except ValueError as e:
                        log.warning("cannot schedule business %s: %s", b.id, e)
        except Exception:  # noqa: BLE001
            log.exception("scheduler tick failed")
        await asyncio.sleep(s.scheduler_poll_s)


def recover_runs() -> list[int]:
    """Requeue runs left queued by a restart; fail ones that were mid-flight."""
    with SessionLocal() as db:
        for run in db.scalars(select(Run).where(Run.status == "running")):
            run.status, run.stage, run.error = "failed", "failed", "Interrupted by a server restart."
            run.finished_at = utcnow()
        db.commit()
        return list(db.scalars(select(Run.id).where(Run.status == "queued").order_by(Run.id)))


async def start(concurrency: int = 2) -> None:
    global _queue
    _queue = asyncio.Queue()
    for rid in recover_runs():
        _queue.put_nowait(rid)
    _tasks.extend(asyncio.create_task(_worker()) for _ in range(concurrency))
    if get_settings().scheduler_enabled:
        _tasks.append(asyncio.create_task(_scheduler()))


async def stop() -> None:
    for t in _tasks:
        t.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    _tasks.clear()
