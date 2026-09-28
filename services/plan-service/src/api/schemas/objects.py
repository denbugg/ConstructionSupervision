"""DTO объекта строительства. Это контракт наружу, а не модель БД."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.api.schemas.common import ObjectLifecycle, ObjectType


class ObjectCreate(BaseModel):
    """Создание объекта.

    Тип можно не указывать: по умолчанию объект — монолитный жилой дом.
    """

    name: str = Field(
        min_length=5,
        max_length=1000,
        examples=["Строительство монолитного жилого дома 17 этажей, г. Москва"],
    )
    object_type: ObjectType | None = None
    address: str | None = Field(default=None, max_length=1000)
    plan_start: date | None = Field(default=None, description="Плановая дата начала СМР")
    tep: dict = Field(
        default_factory=dict,
        description="Параметры для генератора графика: этажность, площадь, секции, сваи, сменность",
    )


class ObjectUpdate(BaseModel):
    """Частичное изменение: передаются только меняемые поля."""

    name: str | None = Field(default=None, min_length=5, max_length=1000)
    object_type: ObjectType | None = None
    address: str | None = Field(default=None, max_length=1000)
    plan_start: date | None = None
    tep: dict | None = None
    status: ObjectLifecycle | None = None


class ObjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    object_type: ObjectType
    address: str | None
    tep: dict
    plan_start: date | None
    status: ObjectLifecycle
    calendar_id: UUID | None = Field(
        description="Рабочий календарь; при создании — DEFAULT_CALENDAR"
    )
    plan_version: int = Field(
        description="Растёт при любой правке этапов, правил или календаря; 0 — план не заводился"
    )
    created_at: datetime
    updated_at: datetime
