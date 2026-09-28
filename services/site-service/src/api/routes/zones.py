"""Зоны камер (F3) и участки объекта (ADR-0013); импорт разметки; пересчёт фактов (F11)."""

from collections.abc import Iterable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status
from lct_common import Page, PageParams, UpstreamError

from src.api.deps import QueueDep, SessionDep
from src.api.schemas.zones import (
    ObjectAreas,
    ReapplyQueued,
    ZoneCreate,
    ZoneRead,
    ZonesImport,
    ZonesImportResult,
    ZonesReapply,
    ZoneUpdate,
)
from src.clients.queue import RecognitionQueue
from src.services.zones import ZoneService

router = APIRouter(tags=["Камеры и зоны"])

VERSION_NOTE = (
    "Версия зоны растёт, вместе с ней — `zones_version` объекта; факты окон объекта "
    "пересчитываются в фоне без повторного распознавания."
)


class QueueUnavailable(UpstreamError):
    code = "QUEUE_UNAVAILABLE"


def schedule_reapply(
    background: BackgroundTasks, queue: RecognitionQueue, object_ids: Iterable[UUID]
) -> None:
    """Пересчёт фактов после правки разметки — после ответа, то есть после commit.

    Задача, поставленная до commit, могла бы прочитать старые зоны. Если очередь недоступна,
    правка всё равно сохранена, а пересчёт запускается вручную: `POST /zones/reapply`.
    """
    for object_id in sorted(object_ids):
        background.add_task(queue.enqueue_reapply, object_id)


@router.get("/zones", response_model=Page[ZoneRead], summary="Зоны")
async def list_zones(
    session: SessionDep,
    params: Annotated[PageParams, Depends()],
    object_id: UUID | None = None,
    camera_id: UUID | None = None,
    include_inactive: bool = False,
):
    items, total = await ZoneService(session).list(
        object_id=object_id,
        camera_id=camera_id,
        include_inactive=include_inactive,
        limit=params.limit,
        offset=params.offset,
    )
    return Page[ZoneRead].of([ZoneRead.model_validate(z) for z in items], total, params)


@router.post(
    "/zones",
    response_model=ZoneRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать зону",
    description="Полигон в долях 0…1 от размера кадра, без самопересечений "
    "(`INVALID_POLYGON`). Название по умолчанию — название типа из enums.yaml.",
)
async def create_zone(
    payload: ZoneCreate,
    session: SessionDep,
    queue: QueueDep,
    background: BackgroundTasks,
    response: Response,
):
    service = ZoneService(session)
    zone = await service.create(payload)
    schedule_reapply(background, queue, service.touched)
    response.headers["Location"] = f"/api/v1/site/zones/{zone.id}"
    return zone


@router.post(
    "/zones/import",
    response_model=ZonesImportResult,
    summary="Загрузить камеры и зоны из cameras.json",
    description="Формат `data/seed/cameras.json` плюс `object_id`. Камеры сверяются по коду, "
    "зоны камеры — по подписи участка: новые создаются, изменённые получают новый полигон, "
    "отсутствующие в файле деактивируются. Повторный импорт того же файла ничего не меняет. "
    "Ошибки полигонов — по всему файлу, с путём (`INVALID_POLYGON`, `details.errors`). "
    "Если разметка поменялась, факты окон объекта пересчитываются в фоне.",
)
async def import_zones(
    payload: ZonesImport, session: SessionDep, queue: QueueDep, background: BackgroundTasks
):
    service = ZoneService(session)
    result = await service.import_markup(payload)
    schedule_reapply(background, queue, service.touched)
    return result


@router.post(
    "/zones/reapply",
    response_model=ReapplyQueued,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Пересчитать факты по текущим зонам",
    description="Заново отнести детекции объекта к активным зонам и пересчитать факты всех его "
    "окон — без повторного распознавания; затем сигнал в analysis. Правки зон и камер ставят "
    "этот пересчёт сами; вручную он нужен, если очередь была недоступна "
    "(`QUEUE_UNAVAILABLE`).",
)
async def reapply_zones(payload: ZonesReapply, queue: QueueDep):
    if not await queue.enqueue_reapply(payload.object_id):
        raise QueueUnavailable(
            "Очередь задач недоступна: пересчёт не поставлен", object_id=str(payload.object_id)
        )
    return {"object_id": payload.object_id, "queued": True}


@router.get("/zones/{zone_id}", response_model=ZoneRead, summary="Зона")
async def get_zone(zone_id: UUID, session: SessionDep):
    return await ZoneService(session).get(zone_id)


@router.patch(
    "/zones/{zone_id}", response_model=ZoneRead, summary="Изменить зону", description=VERSION_NOTE
)
async def update_zone(
    zone_id: UUID,
    payload: ZoneUpdate,
    session: SessionDep,
    queue: QueueDep,
    background: BackgroundTasks,
):
    service = ZoneService(session)
    zone = await service.update(zone_id, payload)
    schedule_reapply(background, queue, service.touched)
    return zone


@router.delete(
    "/zones/{zone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Деактивировать зону",
    description=f"Зона не удаляется: на неё ссылаются детекции. {VERSION_NOTE}",
)
async def delete_zone(
    zone_id: UUID, session: SessionDep, queue: QueueDep, background: BackgroundTasks
):
    service = ZoneService(session)
    await service.deactivate(zone_id)
    schedule_reapply(background, queue, service.touched)


@router.get(
    "/objects/{object_id}/areas",
    response_model=ObjectAreas,
    summary="Участки объекта",
    description="Участок — активные зоны активных камер с одинаковыми типом и названием, "
    "ключ `ТИП:Название` (ADR-0013). Плюс `zones_version` объекта.",
)
async def get_areas(object_id: UUID, session: SessionDep):
    return await ZoneService(session).areas(object_id)
