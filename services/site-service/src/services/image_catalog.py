"""Снимки после приёма: список, карточка с доказательствами, ручное время для NEEDS_TIME."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from lct_common import ConflictError, NotFoundError, ValidationError, get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.storage import ImageStorage
from src.config import settings
from src.core.sessions import session_window
from src.core.timestamp import EARLIEST, parse_form_value
from src.dal.models import Image
from src.dal.repositories.images import ImageRepository

log = get_logger(__name__)


class ImageNotFound(NotFoundError):
    code = "IMAGE_NOT_FOUND"

    def __init__(self, image_id: UUID) -> None:
        super().__init__("Снимок не найден", image_id=str(image_id))


class InvalidPeriod(ValidationError):
    code = "INVALID_PERIOD"


class InvalidCapturedAt(ValidationError):
    code = "INVALID_CAPTURED_AT"


class ImageTimeAlreadySet(ConflictError):
    code = "IMAGE_TIME_ALREADY_SET"


class ImageCatalog:
    def __init__(self, session: AsyncSession, storage: ImageStorage) -> None:
        self._images = ImageRepository(session)
        self._storage = storage

    async def get(self, image_id: UUID) -> Image:
        image = await self._images.get(image_id)
        if image is None:
            raise ImageNotFound(image_id)
        return image

    async def list(
        self, *, start: datetime | None, end: datetime | None, **filters: Any
    ) -> tuple[list[Image], int]:
        if start is not None and end is not None and end <= start:
            raise InvalidPeriod("Конец периода должен быть позже начала")
        return await self._images.list(start=start, end=end, **filters)

    async def detail(self, image_id: UUID, *, internal: bool = False) -> dict[str, Any]:
        """Карточка: снимок, ссылка, рамки техники и стадия — доказательства вывода.

        Ссылка для браузера подписана на публичный адрес хранилища, для сервиса (отчёт analysis,
        interservice.md, контракт 6) — на внутренний: подпись привязана к адресу.
        """
        image = await self.get(image_id)
        sign = self._storage.internal_url if internal else self._storage.presigned_url
        return {
            **{column: getattr(image, column) for column in _COLUMNS},
            "url": await sign(image.storage_key),
            "detections": await self._images.detections(image_id),
            "stage": await self._images.stage(image_id),
        }

    async def set_time(self, image_id: UUID, value: str) -> Image:
        """Ручное время для NEEDS_TIME: снимок попадает в своё окно и встаёт в очередь."""
        image = await self.get(image_id)
        if image.status != "NEEDS_TIME":
            raise ImageTimeAlreadySet(
                "Время снимка уже известно; ручной ввод — только для статуса NEEDS_TIME",
                image_id=str(image_id),
                captured_at_source=image.captured_at_source,
            )
        at = parse_form_value(value, ZoneInfo(settings.camera_timezone))
        if at is None or at < EARLIEST:
            raise InvalidCapturedAt(
                f"Время {value!r} не разобрано; ожидается ISO-8601, например 2026-10-20T12:03:00",
                captured_at=value,
            )
        start, end = session_window(at, settings.session_window_minutes)
        session_id = await self._images.session_for_window(image.object_id, start, end)
        image.captured_at, image.captured_at_source = at, "MANUAL"
        image.session_id, image.status = session_id, "PENDING"
        await self._images.save(image)
        await self._images.recount_session(session_id)
        log.info("image.time_set", image_id=str(image_id), captured_at=at.isoformat())
        return image

    async def reanalyze(self, object_id: UUID, camera_id: UUID | None) -> Sequence[UUID]:
        """Повторное распознавание после смены модели или порогов: снимки снова в PENDING.

        Статус в базе, а не задача в очереди: если очередь потеряет задачи, проход воркера
        по базе подберёт эти снимки сам (architecture.md, 7.3).
        """
        ids = await self._images.reset_for_reanalysis(object_id, camera_id)
        log.info("images.reanalyze", object_id=str(object_id), images=len(ids))
        return ids


_COLUMNS = (
    "id",
    "object_id",
    "camera_id",
    "captured_at",
    "captured_at_source",
    "session_id",
    "width",
    "height",
    "status",
    "usable",
    "usable_reason",
    "source",
    "received_at",
    "exif",
    "quality",
    "error",
)
