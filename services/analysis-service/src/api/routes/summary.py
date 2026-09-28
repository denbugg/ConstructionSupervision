"""Текстовое резюме по объекту без формирования PDF (F12, README, раздел 5)."""

from fastapi import APIRouter

from src.api.deps import ReportServiceDep
from src.api.schemas.reports import ReportCreate, SummaryRead

router = APIRouter(prefix="/summary", tags=["Отчёты"])


@router.post(
    "",
    response_model=SummaryRead,
    summary="Резюме за период: нейросеть с проверкой чисел или шаблон",
    description="Тот же контекст и период по умолчанию, что у `POST /reports`. Текст нейросети "
    "показывается, только если каждое его число есть в фактах, а каждая ссылка — ID отклонения; "
    "иначе резюме шаблонное, а причина — в `llm_rejected`.",
)
async def create_summary(body: ReportCreate, service: ReportServiceDep):
    result = await service.summary(body.object_id, body.period_from, body.period_to)
    return SummaryRead.of(body.object_id, result)
