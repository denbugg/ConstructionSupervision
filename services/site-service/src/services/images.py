"""Приём снимков (F1): загрузка пакетом и импорт из смонтированной папки.

Частичный успех (api-guidelines.md, раздел 7): каждый файл принимается в своей точке
сохранения транзакции, и плохой кадр не роняет пакет из 200 снимков. Снимок без времени
принимается со статусом NEEDS_TIME. Распознавание — задача воркера: здесь снимок
получает статус PENDING, окно и место в хранилище.
"""

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from lct_common import NotFoundError, get_logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.cameras import CODE_PATTERN
from src.clients.storage import ImageStorage, StorageUnavailable
from src.config import settings
from src.core.image_meta import ImageMeta, UnsupportedImage, read_image_meta
from src.core.sessions import session_window
from src.core.timestamp import resolve_captured_at
from src.dal.models import Camera, Image
from src.dal.repositories.cameras import CameraRepository
from src.dal.repositories.images import ImageRepository

log = get_logger(__name__)
DUPLICATE = "Этот снимок уже загружен"


class ImportDirNotFound(NotFoundError):
    code = "IMPORT_DIR_NOT_FOUND"


class Rejected(Exception):
    """Файл не принят; это строка в `rejected`, а не ошибка запроса."""

    def __init__(self, code: str, message: str, image_id: UUID | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.image_id = code, message, image_id


@dataclass
class IntakeReport:
    accepted: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"accepted": self.accepted, "rejected": self.rejected}


class ImageIntake:
    def __init__(self, session: AsyncSession, storage: ImageStorage) -> None:
        self._session = session
        self._storage = storage
        self._images = ImageRepository(session)
        self._cameras = CameraRepository(session)
        self._tz = ZoneInfo(settings.camera_timezone)

    async def upload(
        self,
        object_id: UUID,
        files: list[tuple[str, bytes]],
        *,
        camera_code: str | None,
        captured_at: str | None,
    ) -> dict[str, Any]:
        """Пакет из формы: камера — поле формы, иначе подпапка в имени файла."""
        report = IntakeReport()
        for name, content in files:
            await self._accept(report, object_id, name, content, camera_code, captured_at, "UPLOAD")
        self._log(object_id, "UPLOAD", report)
        return report.as_dict()

    async def import_folder(self, object_id: UUID, subpath: str) -> dict[str, Any]:
        """Папка IMPORT_DIR/<subpath>: каждая подпапка — камера, файлы в ней — её снимки."""
        root = Path(settings.import_dir).resolve()
        target = (root / subpath).resolve()
        if not target.is_relative_to(root) or not target.is_dir():
            raise ImportDirNotFound(
                f"Папки {subpath or '.'} нет в каталоге импорта", import_dir=str(root)
            )
        report = IntakeReport()
        for path in await asyncio.to_thread(_files, target):
            relative = path.relative_to(target).as_posix()
            content = await asyncio.to_thread(path.read_bytes)
            await self._accept(report, object_id, relative, content, None, None, "FOLDER_IMPORT")
        self._log(object_id, "FOLDER_IMPORT", report)
        return report.as_dict()

    async def _accept(
        self,
        report: IntakeReport,
        object_id: UUID,
        name: str,
        content: bytes,
        camera_code: str | None,
        captured_at: str | None,
        source: str,
    ) -> None:
        try:
            async with self._session.begin_nested():
                item = await self._one(object_id, name, content, camera_code, captured_at, source)
            report.accepted.append(item)
        except Rejected as exc:
            report.rejected.append(
                {"file": name, "code": exc.code, "message": exc.message, "image_id": exc.image_id}
            )
        except IntegrityError:
            # Тот же файл пришёл параллельно в другом запросе: уникальность держит база.
            existing = await self._images.by_checksum(object_id, _sha256(content))
            report.rejected.append(
                {
                    "file": name,
                    "code": "IMAGE_ALREADY_EXISTS",
                    "message": DUPLICATE,
                    "image_id": existing.id if existing else None,
                }
            )

    async def _one(
        self,
        object_id: UUID,
        name: str,
        content: bytes,
        camera_code: str | None,
        captured_at: str | None,
        source: str,
    ) -> dict[str, Any]:
        if len(content) > settings.max_image_mb * 1024 * 1024:
            raise Rejected("IMAGE_TOO_LARGE", f"Файл больше {settings.max_image_mb} МБ")
        meta, checksum = await asyncio.to_thread(_inspect, content)
        existing = await self._images.by_checksum(object_id, checksum)
        if existing is not None:
            raise Rejected("IMAGE_ALREADY_EXISTS", DUPLICATE, existing.id)
        camera = await self._camera(object_id, camera_code or _folder(name))
        when = resolve_captured_at(meta.exif, name, captured_at, self._tz)

        image_id = uuid4()
        day = when.at.date().isoformat() if when.at else "no-time"
        key = f"{object_id}/{camera.id}/{day}/{image_id}.{meta.format.lower()}"
        try:
            await self._storage.put(key, content, meta.content_type)
        except StorageUnavailable as exc:
            raise Rejected("STORAGE_UNAVAILABLE", exc.message) from exc

        session_id = None
        if when.at is not None:
            start, end = session_window(when.at, settings.session_window_minutes)
            session_id = await self._images.session_for_window(object_id, start, end)
        image = await self._images.add(
            Image(
                id=image_id,
                object_id=object_id,
                camera_id=camera.id,
                captured_at=when.at,
                captured_at_source=when.source,
                session_id=session_id,
                storage_key=key,
                width=meta.width,
                height=meta.height,
                checksum=checksum,
                source=source,
                exif=meta.exif,
                status="PENDING" if when.at else "NEEDS_TIME",
            )
        )
        if session_id is not None:
            await self._images.recount_session(session_id)
        if camera.reference_image_id is None:
            # Первый снимок камеры — эталонный кадр: на нём размечают зоны.
            camera.reference_image_id = image.id
        return {
            "image_id": image.id,
            "file": name,
            "camera_code": camera.code,
            "captured_at": when.at,
            "captured_at_source": when.source,
            "time_detail": when.detail,
            "status": image.status,
        }

    async def _camera(self, object_id: UUID, code: str | None) -> Camera:
        """Камера по коду; новая заводится сама — так работает загрузка папки (README, раздел 9)."""
        if not code or not re.fullmatch(CODE_PATTERN, code):
            raise Rejected(
                "CAMERA_REQUIRED",
                "Камера не указана: передайте camera_code или положите снимок в подпапку "
                "с кодом камеры (латиница, цифры, «-», «_», «.»)",
            )
        camera = await self._cameras.by_code(object_id, code)
        if camera is None:
            camera = await self._cameras.add(Camera(object_id=object_id, code=code, name=code))
        return camera

    def _log(self, object_id: UUID, source: str, report: IntakeReport) -> None:
        log.info(
            "images.received",
            object_id=str(object_id),
            source=source,
            accepted=len(report.accepted),
            rejected=len(report.rejected),
        )


def _inspect(content: bytes) -> tuple[ImageMeta, str]:
    try:
        meta = read_image_meta(content)
    except UnsupportedImage as exc:
        raise Rejected("UNSUPPORTED_MEDIA_TYPE", str(exc)) from exc
    return meta, _sha256(content)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _folder(name: str) -> str | None:
    """Первая подпапка в имени файла — код камеры: `cam-north/20261020_090000.jpg`.

    Внутри папки камеры могут быть свои подпапки (по датам): камера — всё равно первая.
    """
    parts = PurePosixPath(name.replace("\\", "/")).parts
    return parts[0] if len(parts) >= 2 else None


def _files(folder: Path) -> list[Path]:
    """Файлы папки по порядку имён; скрытые (.gitkeep, .DS_Store) пропускаются."""
    return sorted(
        p
        for p in folder.rglob("*")
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(folder).parts)
    )
