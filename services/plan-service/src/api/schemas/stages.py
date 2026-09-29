"""DTO этапа графика. Поля совпадают с этапом в контракте «весь план» (interservice.md, р. 1)."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.api.schemas.common import (
    ConstructionPhase,
    DependencyType,
    StageLabel,
    StageSource,
    ZoneType,
)
from src.api.schemas.rules import RuleRead


class PredecessorRead(BaseModel):
    stage_id: UUID
    type: DependencyType
    lag_days: int = Field(description="Лаг в рабочих днях")


class StageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    object_id: UUID
    code: str
    name: str
    phase: ConstructionPhase
    seq: int
    work_codes: list[str]
    zone_type: ZoneType
    visual_stage: StageLabel | None
    plan_start: date
    plan_end: date = Field(description="Последний рабочий день этапа, включительно")
    norm_duration_days: int
    predecessors: list[PredecessorRead]
    is_critical: bool
    total_float_days: int
    source: StageSource
    basis: str | None
    completed_on: date | None = Field(
        default=None, description="Отметка «этап выполнен»: последний день работ (ADR-0015)"
    )
    completed_by: str | None = Field(default=None, description="Кто поставил отметку")
    completion_note: str | None = Field(default=None, description="Комментарий к отметке")
    rule: RuleRead | None = Field(default=None, description="Правило «этап → техника»")
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, stage: object, rule: object | None) -> "StageRead":
        """Этап вместе с его правилом: правило живёт в своей таблице."""
        read = cls.model_validate(stage)
        read.rule = RuleRead.model_validate(rule) if rule is not None else None
        return read


class StageUpdate(BaseModel):
    """Частичное изменение. Связи здесь не правятся, критический путь пересчитывается."""

    plan_start: date | None = None
    plan_end: date | None = Field(default=None, description="Включительно")
    zone_type: ZoneType | None = Field(default=None, description="Только тип с ролью WORK")
    visual_stage: StageLabel | None = Field(default=None, description="null — снять стадию")
    norm_duration_days: int | None = Field(
        default=None, gt=0, description="Нормативная длительность в рабочих днях"
    )
    completed_on: date | None = Field(
        default=None,
        description="Отметка «этап выполнен» — последний день работ; автор — из `X-Actor`. "
        "null — снять отметку вместе с автором и комментарием",
    )
    completion_note: str | None = Field(
        default=None, max_length=2000, description="Комментарий к отметке: акт, кто принял"
    )
