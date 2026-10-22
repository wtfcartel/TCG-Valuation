"""In-process scheduler (APScheduler 3) in Australia/Melbourne time.

- Cron triggers are defined in local wall-clock time with the IANA zone, so 06:00 stays 06:00 across
  daylight-saving changes (UTC offset +10 in winter, +11 in summer).
- Overlap is prevented twice: APScheduler max_instances=1 within a process, and the database run lock
  across processes. A scheduled slot also carries an idempotency key ("scheduled:<date>:<slot>"), so a
  restart or a second worker cannot run the same slot twice.
- Misfires (process asleep at the slot time) run once on wake if within the grace period, coalesced.
"""

from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from logidx.db import session_scope
from logidx.schedule_config import ScheduleConfig, get_schedule
from logidx.service import run_scheduled_slot
from logidx.settings import get_settings

log = logging.getLogger(__name__)
MISFIRE_GRACE_SECONDS = 3 * 3600


def trigger_for(slot: str, tz_name: str) -> CronTrigger:
    hour, minute = map(int, slot.split(":"))
    return CronTrigger(hour=hour, minute=minute, timezone=tz_name)


def next_fire_times(cfg: ScheduleConfig, after: datetime, count: int = 6, tz_name: str | None = None) -> list[datetime]:
    tz_name = tz_name or get_settings().timezone
    times: list[datetime] = []
    for slot in cfg.slots:
        trig = trigger_for(slot, tz_name)
        prev, t = None, after
        for _ in range(count):
            nxt = trig.get_next_fire_time(prev, t)
            if nxt is None:
                break
            times.append(nxt)
            prev, t = nxt, nxt
    return sorted(times)[:count]


class Scheduler:
    def __init__(self) -> None:
        self.tz_name = get_settings().timezone
        self._sched = BackgroundScheduler(
            timezone=self.tz_name,
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": MISFIRE_GRACE_SECONDS},
        )

    def start(self) -> None:
        self.reload()
        self._sched.start()
        log.info("scheduler started", extra={"jobs": [j.id for j in self._sched.get_jobs()]})

    def reload(self) -> None:
        """(Re)build jobs from the stored schedule — called after the dashboard saves changes."""
        with session_scope() as session:
            cfg = get_schedule(session)
        for job in self._sched.get_jobs():
            job.remove()
        if not cfg.enabled:
            return
        for slot in cfg.slots:
            self._sched.add_job(
                run_scheduled_slot,
                trigger_for(slot, self.tz_name),
                args=[slot],
                id=f"discovery-{slot}",
                replace_existing=True,
            )

    def jobs(self) -> list[tuple[str, datetime | None]]:
        return [(j.id, j.next_run_time) for j in self._sched.get_jobs()]

    def shutdown(self) -> None:
        if self._sched.running:
            self._sched.shutdown(wait=False)
