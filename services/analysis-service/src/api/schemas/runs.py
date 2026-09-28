"""Схемы прогона анализа (interservice.md, раздел 4)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

from src.dal.models import AnalysisRun


class RunCreate(BaseModel):
    object_id: UUID
    # Значения — analysis_trigger из enums.yaml; проверяет сценарий, а не схема.
    triggered_by: str = Field("MANUAL", examples=["FACTS_UPDATED"])
    as_of: AwareDatetime | None = Field(
        None,
        description="Момент, на который считается анализ. Пусто — конец последней сессии "
        "с фактами, а без фактов — момент запуска",
    )


class RunAccepted(BaseModel):
    run_id: UUID
    status: str
    # Прогон по объекту уже шёл, и сигнал схлопнулся с ним.
    coalesced: bool


class RunRead(BaseModel):
    run_id: UUID
    object_id: UUID
    triggered_by: str
    as_of: datetime | None
    plan_version: int | None
    zones_version: int | None
    status: str
    started_at: datetime
    finished_at: datetime | None
    stats: dict[str, Any]
    error: dict[str, Any] | None

    @classmethod
    def of(cls, run: AnalysisRun) -> "RunRead":
        return cls(
            run_id=run.id,
            object_id=run.object_id,
            triggered_by=run.triggered_by,
            as_of=run.as_of,
            plan_version=run.plan_version,
            zones_version=run.zones_version,
            status=run.status,
            started_at=run.created_at,
            # Конец прогона — последнее обновление строки завершённого прогона.
            finished_at=run.updated_at if run.status != "RUNNING" else None,
            stats=run.stats,
            error=run.error,
        )
