"""Вход отчёта: выводы последнего прогона, план, факты периода и снимки (README, раздел 5).

Отчёт ничего не считает заново. Сюда приходят уже посчитанные выводы в виде простых
неизменяемых структур — так сборка отчёта остаётся чистой функцией и тестируется без базы.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID

from src.core.inputs import Facts, Plan


@dataclass(frozen=True)
class StatusSnapshot:
    """Статус объекта на момент анализа (`object_status`)."""

    as_of: datetime
    computed_at: datetime
    status: str
    delay_days: int | None
    spi: float | None
    confidence: str
    # Дни наблюдений, доля видимых сессий — числа, на которых стоит уверенность.
    facts: Mapping[str, Any] = field(default_factory=dict)
    blind_areas: int = 0
    # Этапы критического пути с прогнозом позже плана — как их отдал прогон.
    stages_at_risk: Sequence[Mapping[str, Any]] = ()


@dataclass(frozen=True)
class StageSnapshot:
    """Факт и прогноз этапа (`stage_fact`)."""

    stage_id: UUID
    actual_start: date | None
    progress: float
    planned_progress: float
    spi: float | None
    forecast_end: date | None
    delay_days: int | None
    status: str
    confidence: str
    # PLAN — прогресс по плану (участок не видели), OBSERVED — по наблюдениям,
    # OPERATOR — этап закрыт отметкой оператора «выполнен».
    basis: str | None = None


@dataclass(frozen=True)
class EquipmentDay:
    """Загрузка техники за местный день (`daily_equipment`)."""

    day: date
    equipment_class: str
    sessions_seen: int
    max_count: int


@dataclass(frozen=True)
class DeviationSnapshot:
    """Строка ленты отклонений."""

    id: UUID
    code: str
    severity: str
    status: str
    verdict: str | None
    stage_id: UUID | None
    area: str | None
    equipment_class: str | None
    title: str
    message: str
    first_seen_at: datetime
    last_seen_at: datetime
    # [{image_id, detection_ids}] — как в `deviation.evidence`.
    evidence: Sequence[Mapping[str, Any]] = ()


@dataclass(frozen=True)
class Box:
    """Рамка на снимке: `bbox` в долях кадра; выделены рамки из доказательства вывода."""

    bbox: tuple[float, float, float, float]
    label: str
    highlighted: bool


@dataclass(frozen=True)
class EvidenceImage:
    """Снимок-доказательство, готовый к вставке; `problem` — почему его нет в отчёте."""

    deviation_id: UUID
    image_id: UUID
    captured_at: datetime | None = None
    data_uri: str | None = None
    width: int | None = None
    height: int | None = None
    boxes: tuple[Box, ...] = ()
    problem: str | None = None


@dataclass(frozen=True)
class Labels:
    """Русские названия значений перечислений (`data/report_labels.yaml`) и типов зон."""

    names: Mapping[str, Mapping[str, str]]
    zone_types: Mapping[str, str] = field(default_factory=dict)

    def of(self, enum: str, value: str | None) -> str:
        if value is None:
            return "—"
        return self.names.get(enum, {}).get(value, value)


@dataclass(frozen=True)
class ReportInput:
    plan: Plan
    status: StatusSnapshot
    stages: Sequence[StageSnapshot]
    equipment: Sequence[EquipmentDay]
    deviations: Sequence[DeviationSnapshot]
    # Факты периода от site-service; None — site не ответил, раздел «Ограничения» это скажет.
    facts: Facts | None
    period_from: date
    period_to: date
    generated_at: datetime
    labels: Labels
    # Порядок серьёзностей из enums.yaml, от низкой к высокой.
    severity_order: Sequence[str]
    # Снимки без времени съёмки; None — site не ответил.
    images_without_time: int | None = None
    evidence: Sequence[EvidenceImage] = ()
