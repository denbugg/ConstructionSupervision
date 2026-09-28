"""Схемы ленты отклонений (docs/methodology.md, раздел 12; docs/data-model.md, п. 3.2)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.api.schemas.rules import DeviationRuleRead


class DeviationRead(BaseModel):
    """Карточка: текст для человека, числа для проверки, снимки-доказательства."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    object_id: UUID
    stage_id: UUID | None
    area: str | None
    equipment_class: str | None
    session_id: UUID | None
    code: str
    severity: str
    status: str
    title: str
    message: str
    facts: dict[str, Any]
    rule_ref: dict[str, Any]
    evidence: list[dict[str, Any]]
    first_seen_at: datetime
    last_seen_at: datetime
    occurrences: int
    verdict: str | None = Field(
        description="CONFIRMED / REJECTED — вердикт оператора; у закрытого статус остаётся RESOLVED"
    )
    verdict_comment: str | None
    verdict_by: str | None
    verdict_at: datetime | None


class DeviationVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(examples=["REJECTED"], description="CONFIRMED или REJECTED")
    comment: str | None = Field(None, max_length=2000)


class EvidenceRead(BaseModel):
    image_id: UUID
    detection_ids: list[UUID]
    # Снимок и рамки отдаёт site-service; путь — через gateway.
    image_path: str


class ExplainRead(BaseModel):
    deviation: DeviationRead
    rule: DeviationRuleRead | None = Field(description="Действующая настройка правила")
    sessions: list[dict[str, Any]] | None = Field(
        description="Сессии эпизода с фактами участка; null — site-service не ответил"
    )
    sessions_truncated: bool = Field(description="Показаны только последние сессии эпизода")
    sessions_unavailable_reason: str | None
    evidence: list[EvidenceRead]
