"""DTO «фактов за период» (interservice.md, контракт 2) и окон наблюдения.

Факты — межсервисный контракт: поля здесь повторяют его один в один, добавлять можно,
убирать и переименовывать нельзя.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.api.schemas.images import ImageRead


class CameraFact(BaseModel):
    code: str
    images: int = Field(description="Распознанные снимки камеры в окне")
    usable: bool = Field(description="Есть ли среди них пригодный кадр")
    reason: str | None = Field(description="DARK, BLURRED, OCCLUDED или NO_IMAGES; null — пригоден")
    image_ids: list[UUID] = Field(
        description="Распознанные снимки камеры в окне — доказательство там, где рамок нет (D1)"
    )


class StageFact(BaseModel):
    stage_label: str
    conf: float
    scores: dict[str, float] = Field(description="Сумма уверенности по меткам за окно")


class Visibility(BaseModel):
    status: str = Field(description="OK — все камеры участка, PARTIAL — часть, BLIND — ни одна")
    cameras_total: int
    cameras_usable: int
    reason: str | None = Field(description="Главная причина непригодности для PARTIAL и BLIND")


class Evidence(BaseModel):
    image_id: UUID
    detection_id: UUID
    camera: str
    conf: float


class EquipmentFact(BaseModel):
    equipment_class: str
    count: int = Field(description="Максимум по камерам участка, а не сумма")
    static: int | None = Field(
        description="Сколько из count не сдвинулись с прошлого окна камеры; null — не с чем "
        "сравнить"
    )
    evidence: list[Evidence] = Field(description="Детекции, на которых стоит число")


class AreaFact(BaseModel):
    area: str = Field(description="Ключ участка `ТИП:Название`")
    zone_type: str
    name: str
    visibility: Visibility
    equipment: list[EquipmentFact] = Field(description="Только классы с count > 0")


class WindowFact(BaseModel):
    session_id: UUID
    window_start: datetime
    window_end: datetime
    updated_at: datetime = Field(description="Когда факт окна пересчитан последний раз")
    cameras: list[CameraFact] = Field(description="Все активные камеры объекта")
    stage_observation: StageFact | None
    areas: list[AreaFact] = Field(description="Все участки объекта, даже пустые и невидимые")
    outside_zones: list[EquipmentFact] = Field(description="Детекции вне всех зон")


class PeriodFacts(BaseModel):
    """Факты за период [from, to) по началу окна: только окна с распознанными снимками."""

    model_config = ConfigDict(populate_by_name=True)

    object_id: UUID
    period_from: datetime = Field(alias="from")
    period_to: datetime = Field(alias="to")
    zones_version: int = Field(description="Счётчик правок зон объекта")
    model_versions: list[str] = Field(description="Версии детектора, давшие детекции периода")
    pending_images: int = Field(
        description="Ещё не распознанные снимки периода; > 0 — факты неполные"
    )
    sessions: list[WindowFact]


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    object_id: UUID
    window_start: datetime
    window_end: datetime
    image_count: int = Field(description="Снимки окна в любом статусе")
    camera_count: int
    stage_label: str | None
    stage_conf: float | None
    updated_at: datetime


class CameraState(CameraFact):
    camera_id: UUID


class SessionDetail(SessionRead):
    """Окно целиком: камеры и пригодность кадров, факт окна, все его снимки."""

    cameras: list[CameraState]
    stage_observation: StageFact | None
    areas: list[AreaFact]
    outside_zones: list[EquipmentFact]
    images: list[ImageRead] = Field(description="Снимки окна в любом статусе, по времени съёмки")
