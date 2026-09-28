"""Вход методики: «весь план» и «факты за период» (interservice.md, контракты 1 и 2).

Модели повторяют контракты поставщиков и игнорируют неизвестные поля: поставщик
вправе добавлять поля без согласования. Значения перечислений хранятся строками —
их списки живут в enums.yaml, а не в коде; проверяет их core/enums.py.
"""

from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _Input(BaseModel):
    """Общая настройка: чужие новые поля не ломают разбор, вход неизменяем."""

    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)


class PlanObject(_Input):
    id: UUID
    name: str
    object_type: str
    # Начало СМР: от него analysis запрашивает факты. Пусто — план ещё не заведён.
    plan_start: date | None = None


class WorkHours(_Input):
    """Рабочие часы в местном времени календаря."""

    start: time
    end: time


class WorkCalendar(_Input):
    code: str
    timezone: str
    # Выходные по ISO: понедельник = 1, воскресенье = 7.
    weekend_days: tuple[int, ...] = ()
    holidays: tuple[date, ...] = ()
    work_hours: WorkHours


class EquipmentClass(_Input):
    code: str
    name_ru: str
    group: str
    # Приезжает и уезжает рейсами: присутствие считается за окно сессий.
    transient: bool
    # Работает, не сдвигаясь с места: неподвижность на рабочем участке не простой.
    works_in_place: bool = False


class Predecessor(_Input):
    stage_id: UUID
    type: str
    lag_days: int = 0


class RequiredGroup(_Input):
    """Группа «любой из»: выполнена, если суммарно единиц классов не меньше min."""

    any_of: tuple[str, ...]
    min: int = Field(ge=1)


class Signature(_Input):
    """Признак фактического старта этапа."""

    equipment: tuple[str, ...] = ()
    stage_label: str | None = None


class StageRule(_Input):
    id: UUID
    version: int
    required: tuple[RequiredGroup, ...] = ()
    allowed: tuple[str, ...] = ()
    signature: Signature = Signature()
    min_sessions: int = Field(ge=1)


class Stage(_Input):
    id: UUID
    code: str
    name: str
    phase: str
    seq: int
    work_codes: tuple[str, ...] = ()
    zone_type: str
    visual_stage: str | None = None
    # Обе даты включительно: plan_end — последний рабочий день этапа.
    plan_start: date
    plan_end: date
    norm_duration_days: int = Field(gt=0)
    predecessors: tuple[Predecessor, ...] = ()
    is_critical: bool = False
    total_float_days: int = 0
    basis: str | None = None
    # null — по этапу не проверяются D1, D2, D8, D9.
    rule: StageRule | None = None
    # Отметка оператора «этап выполнен» — последний день работ (methodology.md, 10.3b).
    completed_on: date | None = None
    completed_by: str | None = None
    completion_note: str | None = None


class Plan(_Input):
    """Весь план объекта: одного ответа достаточно для прогона анализа."""

    object: PlanObject
    plan_version: int
    calendar: WorkCalendar
    equipment_classes: tuple[EquipmentClass, ...] = ()
    stages: tuple[Stage, ...] = ()


class CameraState(_Input):
    code: str
    images: int
    usable: bool
    reason: str | None = None
    # Снимки окна: доказательство там, где рамок нет (D1 по пустому участку).
    image_ids: tuple[UUID, ...] = ()


class StageObservation(_Input):
    """Стадия по фото за окно: метка с наибольшей суммой уверенности."""

    stage_label: str
    conf: float
    scores: dict[str, float] = Field(default_factory=dict)


class Visibility(_Input):
    status: str
    cameras_total: int
    cameras_usable: int
    reason: str | None = None


class Evidence(_Input):
    image_id: UUID
    detection_id: UUID
    camera: str
    conf: float


class EquipmentFact(_Input):
    """Класс на участке за окно: максимум по камерам, а не сумма."""

    equipment_class: str
    count: int = Field(gt=0)
    # Сколько из count не сдвинулись с прошлого окна; None — сравнивать не с чем.
    static: int | None = None
    evidence: tuple[Evidence, ...] = Field(min_length=1)


class AreaFact(_Input):
    """Участок `ТИП:Название` в окне — присутствует, даже если пуст или невидим."""

    area: str
    zone_type: str
    name: str
    visibility: Visibility
    equipment: tuple[EquipmentFact, ...] = ()


class SessionFact(_Input):
    session_id: UUID
    window_start: datetime
    window_end: datetime
    updated_at: datetime
    cameras: tuple[CameraState, ...] = ()
    stage_observation: StageObservation | None = None
    areas: tuple[AreaFact, ...] = ()
    outside_zones: tuple[EquipmentFact, ...] = ()


class Facts(_Input):
    """Факты за период [from, to) по началу окна сессии."""

    object_id: UUID
    period_from: datetime = Field(alias="from")
    period_to: datetime = Field(alias="to")
    zones_version: int
    model_versions: tuple[str, ...] = ()
    # Больше нуля — факты периода неполные.
    pending_images: int = 0
    sessions: tuple[SessionFact, ...] = ()
