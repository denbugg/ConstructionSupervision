"""Объекты строительства.

Роутер только принимает, валидирует и зовёт сценарий. Расчётов, SQL и вызовов
других сервисов здесь нет — см. docs/code-style.md, раздел 2.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from lct_common import Page, PageParams

from src.api.deps import SessionDep
from src.api.schemas.common import ObjectLifecycle, ObjectType
from src.api.schemas.objects import ObjectCreate, ObjectRead, ObjectUpdate
from src.services.objects import ObjectService

router = APIRouter(prefix="/objects", tags=["Объекты"])


@router.post(
    "",
    response_model=ObjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать объект",
)
async def create_object(payload: ObjectCreate, session: SessionDep, response: Response):
    obj = await ObjectService(session).create(payload)
    response.headers["Location"] = f"/api/v1/plan/objects/{obj.id}"
    return obj


@router.get("", response_model=Page[ObjectRead], summary="Список объектов")
async def list_objects(
    session: SessionDep,
    params: Annotated[PageParams, Depends()],
    status_filter: Annotated[ObjectLifecycle | None, Query(alias="status")] = None,
    object_type: ObjectType | None = None,
):
    items, total = await ObjectService(session).list(
        limit=params.limit,
        offset=params.offset,
        status=status_filter,
        object_type=object_type,
    )
    return Page[ObjectRead].of([ObjectRead.model_validate(o) for o in items], total, params)


@router.get("/{object_id}", response_model=ObjectRead, summary="Карточка объекта")
async def get_object(object_id: UUID, session: SessionDep):
    return await ObjectService(session).get(object_id)


@router.patch("/{object_id}", response_model=ObjectRead, summary="Изменить реквизиты объекта")
async def update_object(object_id: UUID, payload: ObjectUpdate, session: SessionDep):
    return await ObjectService(session).update(object_id, payload)


@router.delete(
    "/{object_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Перевести объект в архив",
)
async def archive_object(object_id: UUID, session: SessionDep) -> None:
    await ObjectService(session).archive(object_id)
