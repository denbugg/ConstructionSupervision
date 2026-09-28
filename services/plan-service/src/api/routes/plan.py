"""«Весь план» объекта (межсервисный контракт 1), импорт графика из файла и генерация по МРР."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, UploadFile

from src.api.deps import ActorDep, AnalysisDep, SessionDep
from src.api.schemas.plan import (
    Plan,
    PlanGenerateRequest,
    PlanGenerateResult,
    PlanImportResult,
)
from src.services.plan import PlanService
from src.services.plan_generate import PlanGenerateService
from src.services.plan_import import PlanImportService

router = APIRouter(prefix="/objects/{object_id}/plan", tags=["График"])


@router.get(
    "",
    response_model=Plan,
    summary="Весь план объекта",
    description="Этапы по `seq`, связи, правила, календарь и классы техники одним ответом. "
    "Объект без этапов — не ошибка: `stages: []`. Выключенное правило приходит как `rule: null`.",
)
async def get_plan(object_id: UUID, session: SessionDep):
    return await PlanService(session).get_plan(object_id)


@router.post(
    "/import",
    response_model=PlanImportResult,
    summary="Импорт графика из CSV или XLSX",
    description="Столбцы: код, наименование, начало, окончание (обязательно); тип участка, "
    "визуальная стадия, связи (`12.3.1 FS+2`, несколько — через запятую), фаза. Недостающее "
    "берётся из шаблона этапа с тем же кодом, вместе с правилом «этап → техника». График "
    "заменяется целиком; поверх существующего — только с `force=true`. Ошибки — "
    "`PLAN_IMPORT_INVALID` со списком `details.errors` (строка, столбец, текст).",
)
async def import_plan(
    object_id: UUID,
    session: SessionDep,
    signal: AnalysisDep,
    actor: ActorDep,
    file: Annotated[UploadFile, File(description="График: .csv (UTF-8 или cp1251) или .xlsx")],
    force: bool = False,
):
    content = await file.read()
    return await PlanImportService(session, signal).import_file(
        object_id, file.filename or "", content, force=force, actor=actor
    )


@router.post(
    "/generate",
    response_model=PlanGenerateResult,
    summary="Сгенерировать график по МРР-3.2.81-12",
    description="Сроки периодов — табл. 1 п. 5.1.21 с интерполяцией и коэффициентами, этапы и "
    "правила — из шаблона типа объекта, даты — по календарю объекта. У каждого этапа в `basis` — "
    "откуда его срок. Поверх существующего графика — только с `force=true` (ручные правки "
    "затираются). Нет норм для типа или параметры вне таблицы — `NORMS_NOT_AVAILABLE`, "
    "график тогда импортируется из файла.",
)
async def generate_plan(
    object_id: UUID,
    session: SessionDep,
    signal: AnalysisDep,
    actor: ActorDep,
    payload: PlanGenerateRequest | None = None,
    force: bool = False,
):
    payload = payload or PlanGenerateRequest()
    return await PlanGenerateService(session, signal).generate(
        object_id, tep=payload.tep, start_date=payload.start_date, force=force, actor=actor
    )
