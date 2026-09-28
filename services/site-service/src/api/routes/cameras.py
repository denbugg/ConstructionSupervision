"""Камеры объекта — точки съёмки. Подпапка при загрузке снимков совпадает с кодом камеры."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status
from lct_common import Page, PageParams

from src.api.deps import QueueDep, SessionDep
from src.api.routes.zones import schedule_reapply
from src.api.schemas.cameras import CameraCreate, CameraRead, CameraUpdate
from src.services.cameras import CameraService

router = APIRouter(prefix="/cameras", tags=["Камеры и зоны"])


@router.get("", response_model=Page[CameraRead], summary="Камеры")
async def list_cameras(
    session: SessionDep,
    params: Annotated[PageParams, Depends()],
    object_id: UUID | None = None,
    is_active: bool | None = None,
):
    items, total = await CameraService(session).list(
        object_id=object_id, is_active=is_active, limit=params.limit, offset=params.offset
    )
    return Page[CameraRead].of([CameraRead.model_validate(c) for c in items], total, params)


@router.post(
    "",
    response_model=CameraRead,
    status_code=status.HTTP_201_CREATED,
    summary="Завести камеру",
    description="Код в объекте не повторяется (`CAMERA_ALREADY_EXISTS`). При загрузке папки "
    "снимков камеры заводятся сами по именам подпапок.",
)
async def create_camera(payload: CameraCreate, session: SessionDep, response: Response):
    camera = await CameraService(session).create(payload)
    response.headers["Location"] = f"/api/v1/site/cameras/{camera.id}"
    return camera


@router.get("/{camera_id}", response_model=CameraRead, summary="Камера")
async def get_camera(camera_id: UUID, session: SessionDep):
    return await CameraService(session).get(camera_id)


@router.patch(
    "/{camera_id}",
    response_model=CameraRead,
    summary="Изменить камеру",
    description="Название, эталонный кадр (снимок этой камеры), параметры установки, "
    "активность. `is_active: false` деактивирует и зоны камеры; смена активности "
    "пересчитывает факты окон объекта в фоне.",
)
async def update_camera(
    camera_id: UUID,
    payload: CameraUpdate,
    session: SessionDep,
    queue: QueueDep,
    background: BackgroundTasks,
):
    service = CameraService(session)
    camera = await service.update(camera_id, payload)
    schedule_reapply(background, queue, service.touched)
    return camera


@router.delete(
    "/{camera_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Деактивировать камеру",
    description="Камера и её зоны не удаляются: на них ссылаются снимки и детекции.",
)
async def delete_camera(
    camera_id: UUID, session: SessionDep, queue: QueueDep, background: BackgroundTasks
):
    service = CameraService(session)
    await service.deactivate(camera_id)
    schedule_reapply(background, queue, service.touched)
