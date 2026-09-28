"""DTO правила «этап → техника». Форма совпадает с `stages[].rule` контракта «весь план»."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.api.schemas.common import StageLabel


class RequiredGroup(BaseModel):
    """Группа «любой из»: выполнена, если суммарно единиц классов не меньше min."""

    any_of: list[str] = Field(min_length=1, examples=[["roller", "bulldozer"]])
    min: int = Field(ge=1)


class Signature(BaseModel):
    """Признак фактического старта этапа: техника одновременно и (или) стадия по фото."""

    equipment: list[str] = Field(default_factory=list)
    stage_label: StageLabel | None = Field(default=None, description="Стадия по фото не раньше")


class RuleCreate(BaseModel):
    stage_id: UUID = Field(description="У этапа не больше одного правила")
    required: list[RequiredGroup] = Field(default_factory=list)
    allowed: list[str] = Field(default_factory=list, description="Не вызывает D3")
    signature: Signature = Field(default_factory=Signature)
    min_sessions: int | None = Field(
        default=None,
        ge=1,
        description="Сколько рабочих сессий подряд держится условие; по умолчанию 2",
    )
    is_active: bool = True


class RuleUpdate(BaseModel):
    """Частичное изменение. Списки и сигнатура заменяются целиком."""

    required: list[RequiredGroup] | None = None
    allowed: list[str] | None = None
    signature: Signature | None = None
    min_sessions: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class RuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    stage_id: UUID
    version: int = Field(description="Растёт при каждой правке; попадает в отклонение")
    required: list[RequiredGroup]
    allowed: list[str]
    signature: Signature
    min_sessions: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
