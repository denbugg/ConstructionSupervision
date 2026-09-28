"""Справочник строительных работ: загрузка XLSX заказчика и чтение."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from lct_common import Page, PageParams

from src.api.deps import ActorDep, SessionDep
from src.api.schemas.work_types import WorkTypeImportResult, WorkTypeRead
from src.services.work_types import WorkTypeService

router = APIRouter(prefix="/work-types", tags=["Справочники"])


@router.get(
    "",
    response_model=Page[WorkTypeRead],
    summary="Справочник работ",
    description="В порядке файла заказчика: «10.2» раньше «10.10», строки без кода — сразу "
    "за своим кодом.",
)
async def list_work_types(
    session: SessionDep,
    params: Annotated[PageParams, Depends()],
    level: Annotated[int | None, Query(ge=1, le=4)] = None,
    parent_code: str | None = None,
):
    items, total = await WorkTypeService(session).list(
        level=level, parent_code=parent_code, limit=params.limit, offset=params.offset
    )
    return Page[WorkTypeRead].of([WorkTypeRead.model_validate(w) for w in items], total, params)


@router.post(
    "/import",
    response_model=WorkTypeImportResult,
    summary="Загрузить справочник работ из XLSX",
    description="«Сводный перечень строительных работ ЛТЦ» (data/README.md). Коды, которые "
    "Excel превратил в даты, восстанавливаются (`d.m.2025` → `d.m`), строки без кода "
    "относятся к 4-му уровню ближайшего кода сверху. Справочник заменяется целиком. Ошибки — "
    "`WORK_TYPES_IMPORT_INVALID` со списком `details.errors` (строка, столбец, текст).",
)
async def import_work_types(
    session: SessionDep,
    actor: ActorDep,
    file: Annotated[UploadFile, File(description="Справочник работ, .xlsx, первый лист")],
):
    content = await file.read()
    return await WorkTypeService(session).import_file(file.filename or "", content, actor)
