"""Схемы PDF-отчётов: запрос на формирование, файл отчёта со ссылкой."""

import datetime as dt
from uuid import UUID

from pydantic import BaseModel, Field

from src.services.reports import CreatedReport, ReportFile, ReportSummary


class ReportCreate(BaseModel):
    object_id: UUID
    period_from: dt.date | None = Field(
        default=None, description="Первый местный день периода; по умолчанию — неделя до конца"
    )
    period_to: dt.date | None = Field(
        default=None, description="Последний местный день включительно; по умолчанию — день as_of"
    )


class SummaryRead(BaseModel):
    object_id: UUID
    period_from: dt.date
    period_to: dt.date
    as_of: dt.datetime = Field(description="Момент анализа, чьи выводы пересказаны")
    text: str
    generated_by: str = Field(description="`LLM` или `TEMPLATE` — показывать всегда (ADR-0008)")
    source: str = Field(description="Откуда текст и почему шаблон, если нейросеть не подошла")
    llm_rejected: list[str] = Field(
        description="Почему текст нейросети отброшен: числа не из фактов, чужие ID, недоступность"
    )

    @classmethod
    def of(cls, object_id: UUID, result: ReportSummary) -> "SummaryRead":
        return cls(
            object_id=object_id,
            period_from=result.period_from,
            period_to=result.period_to,
            as_of=result.as_of,
            text=result.summary.text,
            generated_by=result.summary.generated_by,
            source=result.summary.source,
            llm_rejected=result.rejected,
        )


class ReportRead(BaseModel):
    key: str = Field(description="Ключ файла в бакете `reports`; им же читается ссылка")
    object_id: UUID
    period_from: dt.date
    period_to: dt.date
    generated_on: dt.date = Field(description="Местный день формирования — часть ключа")
    created_at: dt.datetime
    size_bytes: int
    url: str = Field(description="Presigned-ссылка на S3_PUBLIC_ENDPOINT; живёт S3_PRESIGN_TTL_S")

    @classmethod
    def of(cls, report: ReportFile) -> "ReportRead":
        return cls(
            key=str(report.key),
            object_id=report.key.object_id,
            period_from=report.key.period_from,
            period_to=report.key.period_to,
            generated_on=report.key.generated_on,
            created_at=report.modified_at,
            size_bytes=report.size,
            url=report.url,
        )


class ReportCreated(ReportRead):
    as_of: dt.datetime = Field(description="Момент анализа, чьи выводы вошли в отчёт")
    summary_generated_by: str = Field(description="`TEMPLATE` или `LLM` — источник резюме")
    evidence_images: int = Field(description="Снимков-доказательств вставлено")
    evidence_missing: int = Field(
        description="Снимков не вставлено; причины — в разделе «Ограничения»"
    )

    @classmethod
    def of_created(cls, report: CreatedReport) -> "ReportCreated":
        return cls(
            **ReportRead.of(report.file).model_dump(),
            as_of=report.as_of,
            summary_generated_by=report.summary_generated_by,
            evidence_images=report.evidence_shown,
            evidence_missing=report.evidence_missing,
        )
