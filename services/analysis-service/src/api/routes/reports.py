"""PDF-отчёты по объекту: формирование, список, ссылка на файл (README, раздел 5)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from lct_common import Page, PageParams

from src.api.deps import ReportServiceDep
from src.api.schemas.reports import ReportCreate, ReportCreated, ReportRead

router = APIRouter(prefix="/reports", tags=["Отчёты"])


@router.post(
    "",
    response_model=ReportCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Сформировать PDF-отчёт за период",
    description="Период — местные дни календаря объекта включительно. Формирование синхронное: "
    "ответ приходит с готовой ссылкой. Отчёт того же периода, сформированный в тот же день, "
    "заменяется.",
)
async def create_report(body: ReportCreate, service: ReportServiceDep):
    created = await service.create(body.object_id, body.period_from, body.period_to)
    return ReportCreated.of_created(created)


@router.get("", response_model=Page[ReportRead], summary="Отчёты объекта, новые сверху")
async def list_reports(
    object_id: UUID, service: ReportServiceDep, params: Annotated[PageParams, Depends()]
):
    reports = await service.list_reports(object_id)
    page = reports[params.offset : params.offset + params.limit]
    return Page.of([ReportRead.of(r) for r in page], len(reports), params)


@router.get(
    "/{key:path}",
    response_model=ReportRead,
    summary="Ссылка на готовый отчёт",
    description="`key` — ключ из списка, вида `{object_id}/{дата}T{ЧЧММСС}-{начало}_{конец}.pdf`.",
)
async def get_report(key: str, service: ReportServiceDep):
    return ReportRead.of(await service.get(key))
