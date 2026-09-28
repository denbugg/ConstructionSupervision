"""Схемы настроек правил отклонений D1–D10."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DeviationRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    predicate: str = Field(description="Имя предиката из реестра; правится только в коде")
    enabled: bool
    severity: str
    params: dict[str, Any]
    title_template: str
    message_template: str
    updated_at: datetime


class DeviationRuleUpdate(BaseModel):
    """Частичная правка: передаются только меняемые поля."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    severity: str | None = Field(None, examples=["HIGH"])
    params: dict[str, Any] | None = Field(
        None,
        description="Сливается с текущими параметрами по ключам; ключ со значением null удаляется",
        examples=[{"min_sessions": 3}],
    )
    title_template: str | None = Field(None, min_length=1)
    message_template: str | None = Field(None, min_length=1)
