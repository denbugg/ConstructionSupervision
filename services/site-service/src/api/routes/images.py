"""Снимки (F1): пакет из формы, импорт из папки, список, карточка, ручное время, повтор."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile, status
from lct_common import Page, PageParams, ValidationError

from src.api.deps import QueueDep, SessionDep, StorageDep
from src.api.schemas.common import ImageStatus
from src.api.schemas.images import (
    FolderImport,
    ImageDetail,
    ImageRead,
    ImageTimeUpdate,
    IntakeResult,
    ReanalyzeRequest,
    ReanalyzeResult,
)
from src.clients.queue import RecognitionQueue
from src.config import settings
from src.services.image_catalog import ImageCatalog
from src.services.images import ImageIntake

router = APIRouter(prefix="/images", tags=["Снимки"])

TIME_NOTE = (
    "Время: EXIF → дата и время в имени файла → поле `captured_at` (ISO-8601; без смещения — "
    "местное время камеры, `CAMERA_TIMEZONE`). Без времени снимок принимается со статусом "
    "`NEEDS_TIME`. Первый снимок камеры становится её эталонным кадром."
)


class BatchTooLarge(ValidationError):
    code = "IMAGE_BATCH_TOO_LARGE"


@router.post(
    "",
    response_model=IntakeResult,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Загрузить снимки пакетом",
    description=f"До {settings.max_files_per_request} файлов (поле `files`), каждый до "
    f"`MAX_IMAGE_MB`. Камера — поле `camera_code`, иначе подпапка в имени файла "
    f"(`cam-north/20261020_090000.jpg`); новая камера заводится сама. {TIME_NOTE} Ответ — "
    "частичный успех: `accepted` и `rejected`.",
)
async def upload_images(
    session: SessionDep,
    storage: StorageDep,
    queue: QueueDep,
    background: BackgroundTasks,
    object_id: Annotated[UUID, Form()],
    files: Annotated[list[UploadFile], File(description="Снимки: JPEG, PNG, WebP")],
    camera_code: Annotated[str | None, Form()] = None,
    captured_at: Annotated[
        str | None, Form(description="Время съёмки, если его нет в файле")
    ] = None,
):
    if len(files) > settings.max_files_per_request:
        raise BatchTooLarge(
            f"За запрос — не больше {settings.max_files_per_request} файлов",
            limit=settings.max_files_per_request,
            received=len(files),
        )
    batch = [(f.filename or "", await f.read()) for f in files]
    result = await ImageIntake(session, storage).upload(
        object_id, batch, camera_code=camera_code, captured_at=captured_at
    )
    _enqueue(background, queue, result["accepted"])
    return result


@router.get(
    "",
    response_model=Page[ImageRead],
    summary="Снимки",
    description="По времени съёмки; снимки без времени — в конце. `from` и `to` — "
    "полуинтервал по `captured_at` (ISO-8601).",
)
async def list_images(
    session: SessionDep,
    storage: StorageDep,
    params: Annotated[PageParams, Depends()],
    object_id: UUID | None = None,
    camera_id: UUID | None = None,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    image_status: Annotated[ImageStatus | None, Query(alias="status")] = None,
):
    items, total = await ImageCatalog(session, storage).list(
        object_id=object_id,
        camera_id=camera_id,
        start=start,
        end=end,
        status=image_status,
        limit=params.limit,
        offset=params.offset,
    )
    return Page[ImageRead].of([ImageRead.model_validate(i) for i in items], total, params)


@router.get(
    "/{image_id}",
    response_model=ImageDetail,
    summary="Снимок",
    description="Метаданные, ссылка для браузера (путь на gateway), рамки техники с "
    "точкой контакта и зоной, стадия по снимку. `link=internal` — ссылка на внутренний адрес "
    "хранилища (`S3_ENDPOINT`) для других сервисов: так снимки берёт отчёт analysis "
    "(interservice.md, контракт 6).",
)
async def get_image(
    image_id: UUID,
    session: SessionDep,
    storage: StorageDep,
    link: Literal["public", "internal"] = "public",
):
    return await ImageCatalog(session, storage).detail(image_id, internal=link == "internal")


@router.patch(
    "/{image_id}",
    response_model=ImageRead,
    summary="Указать время съёмки вручную",
    description="Только для статуса `NEEDS_TIME` (`IMAGE_TIME_ALREADY_SET` иначе). Снимок "
    "получает окно наблюдения и статус `PENDING`, источник времени — `MANUAL`.",
)
async def set_image_time(
    image_id: UUID,
    payload: ImageTimeUpdate,
    session: SessionDep,
    storage: StorageDep,
    queue: QueueDep,
    background: BackgroundTasks,
):
    image = await ImageCatalog(session, storage).set_time(image_id, payload.captured_at)
    _enqueue(background, queue, [{"image_id": image.id, "status": image.status}])
    return image


@router.post(
    "/import",
    response_model=IntakeResult,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Импорт снимков из смонтированной папки",
    description="Папка `IMPORT_DIR/<path>`: подпапка — код камеры (`cam-north/...`), камеры "
    f"заводятся сами, скрытые файлы пропускаются. {TIME_NOTE} Повторный импорт той же папки "
    "отклоняет уже загруженные снимки как `IMAGE_ALREADY_EXISTS`.",
)
async def import_images(
    payload: FolderImport,
    session: SessionDep,
    storage: StorageDep,
    queue: QueueDep,
    background: BackgroundTasks,
):
    result = await ImageIntake(session, storage).import_folder(payload.object_id, payload.path)
    _enqueue(background, queue, result["accepted"])
    return result


@router.post(
    "/reanalyze",
    response_model=ReanalyzeResult,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Распознать снимки объекта заново",
    description="После смены модели или её порога: распознанные (`ANALYZED`) и отказные "
    "(`FAILED`) снимки объекта — или одной камеры — снова получают `PENDING` и распознаются "
    "воркером; факты окон пересчитываются по мере распознавания. Пока идёт повтор, "
    "`pending_images` в фактах больше нуля.",
)
async def reanalyze_images(
    payload: ReanalyzeRequest,
    session: SessionDep,
    storage: StorageDep,
    queue: QueueDep,
    background: BackgroundTasks,
):
    ids = await ImageCatalog(session, storage).reanalyze(payload.object_id, payload.camera_id)
    _enqueue(background, queue, [{"image_id": i, "status": "PENDING"} for i in ids])
    return {"object_id": payload.object_id, "images": len(ids)}


def _enqueue(background: BackgroundTasks, queue: RecognitionQueue, accepted: list[dict]) -> None:
    """Поставить принятые снимки в очередь распознавания — после ответа, то есть после commit.

    Задача, поставленная раньше commit, не нашла бы снимок в базе. Если постановка не удалась,
    снимок всё равно в PENDING, и воркер подберёт его проходом по базе.
    """
    ids = [item["image_id"] for item in accepted if item["status"] == "PENDING"]
    if ids:
        background.add_task(queue.enqueue, ids)
