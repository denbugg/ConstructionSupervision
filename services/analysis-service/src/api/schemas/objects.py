"""Схемы выводов по объекту: статус для дашборда, прогресс этапов для Ганта, загрузка техники."""

import datetime as dt
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.dal.models import DailyActivity, DailyEquipment, ObjectStatus, StageFact


class ObjectStatusRead(BaseModel):
    object_id: UUID
    computed_at: dt.datetime
    as_of: dt.datetime
    status: str
    delay_days: int | None
    spi: float | None
    confidence: str
    stages: dict[str, int] = Field(description="Этапы по статусам и `total`")
    deviations: dict[str, int] = Field(description="Открытые отклонения по серьёзности")
    blind_areas: int = Field(description="Участки, не видимые в последней рабочей сессии")
    stages_at_risk: list[dict[str, Any]]
    facts: dict[str, Any] = Field(description="Числа статуса: дни наблюдений, видимость")

    @classmethod
    def of(cls, row: ObjectStatus, deviations: dict[str, int]) -> "ObjectStatusRead":
        return cls(
            object_id=row.object_id,
            computed_at=row.computed_at,
            as_of=row.as_of,
            status=row.status,
            delay_days=row.delay_days,
            spi=row.spi,
            confidence=row.confidence,
            stages=row.counters.get("stages", {}),
            deviations=deviations,
            blind_areas=row.counters.get("blind_areas", 0),
            stages_at_risk=row.stages_at_risk,
            facts=row.counters.get("facts", {}),
        )


class ActivityDay(BaseModel):
    date: dt.date
    sessions_total: int
    sessions_working: int
    # null — участок этапа за день ни разу не был виден: «не знаем», а не ноль.
    activity_index: float | None
    blind_sessions: int

    @classmethod
    def of(cls, row: DailyActivity) -> "ActivityDay":
        return cls(
            date=row.day,
            sessions_total=row.sessions_total,
            sessions_working=row.sessions_working,
            activity_index=row.activity_index,
            blind_sessions=row.blind_sessions,
        )


class StageProgress(BaseModel):
    stage_id: UUID
    actual_start: dt.date | None
    last_activity_at: dt.datetime | None
    effective_days: float
    progress: float
    planned_progress: float
    spi: float | None
    forecast_end: dt.date | None
    delay_days: int | None
    status: str
    confidence: str
    facts: dict[str, Any]
    activity: list[ActivityDay]

    @classmethod
    def of(cls, row: StageFact, activity: list[DailyActivity]) -> "StageProgress":
        return cls(
            stage_id=row.stage_id,
            actual_start=row.actual_start,
            last_activity_at=row.last_activity_at,
            effective_days=row.effective_days,
            progress=row.progress,
            planned_progress=row.planned_progress,
            spi=row.spi,
            forecast_end=row.forecast_end,
            delay_days=row.delay_days,
            status=row.status,
            confidence=row.confidence,
            facts=row.facts,
            activity=[ActivityDay.of(a) for a in activity],
        )


class ProgressRead(BaseModel):
    """Названия и плановые даты этапов — в plan-service; здесь только факт и прогноз."""

    object_id: UUID
    as_of: dt.datetime
    stages: list[StageProgress]


class EquipmentDay(BaseModel):
    date: dt.date
    equipment_class: str
    sessions_seen: int
    max_count: int

    @classmethod
    def of(cls, row: DailyEquipment) -> "EquipmentDay":
        return cls(
            date=row.day,
            equipment_class=row.equipment_class,
            sessions_seen=row.sessions_seen,
            max_count=row.max_count,
        )


class EquipmentRead(BaseModel):
    object_id: UUID
    as_of: dt.datetime
    items: list[EquipmentDay]
