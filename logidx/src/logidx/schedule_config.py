"""Editable schedule (stored in settings_kv). Times are local Australia/Melbourne wall-clock times."""

from __future__ import annotations

import re

from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from logidx.models import SettingKV

SCHEDULE_KEY = "schedule"


class ScheduleConfig(BaseModel):
    enabled: bool = True
    slots: list[str] = ["06:00", "14:00", "20:00"]
    report_slot: str = "20:00"  # the run that generates and sends the daily report
    ai_enabled: bool = True

    @field_validator("slots")
    @classmethod
    def _valid_slots(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("at least one slot is required")
        for slot in v:
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", slot):
                raise ValueError(f"invalid time {slot!r}; use HH:MM 24-hour")
        return sorted(set(v))

    def slot_index(self, slot: str | None) -> int:
        return self.slots.index(slot) if slot in self.slots else 0


def get_schedule(session: Session) -> ScheduleConfig:
    row = session.get(SettingKV, SCHEDULE_KEY)
    return ScheduleConfig.model_validate(row.value) if row else ScheduleConfig()


def save_schedule(session: Session, cfg: ScheduleConfig) -> None:
    row = session.get(SettingKV, SCHEDULE_KEY)
    if row is None:
        session.add(SettingKV(key=SCHEDULE_KEY, value=cfg.model_dump()))
    else:
        row.value = cfg.model_dump()
