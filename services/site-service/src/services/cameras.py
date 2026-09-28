"""Камеры объекта: заведение, правка, эталонный кадр, деактивация."""

from uuid import UUID

from lct_common import ConflictError, NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.cameras import CameraCreate, CameraUpdate
from src.dal.models import Camera, Zone
from src.dal.repositories.cameras import CameraRepository
from src.dal.repositories.zones import ZoneRepository


class CameraNotFound(NotFoundError):
    code = "CAMERA_NOT_FOUND"

    def __init__(self, camera_id: UUID) -> None:
        super().__init__("Камера не найдена", camera_id=str(camera_id))


class CameraAlreadyExists(ConflictError):
    code = "CAMERA_ALREADY_EXISTS"


class ImageNotFound(NotFoundError):
    code = "IMAGE_NOT_FOUND"


class CameraService:
    def __init__(self, session: AsyncSession) -> None:
        self._cameras = CameraRepository(session)
        self._zones = ZoneRepository(session)
        # Объекты, где камера включена или выключена: её кадры входят в факты окон или выходят
        # из них, поэтому факты пересчитываются заново.
        self.touched: set[UUID] = set()

    async def get(self, camera_id: UUID) -> Camera:
        camera = await self._cameras.get(camera_id)
        if camera is None:
            raise CameraNotFound(camera_id)
        return camera

    async def list(
        self, *, object_id: UUID | None, is_active: bool | None, limit: int, offset: int
    ) -> tuple[list[Camera], int]:
        return await self._cameras.list(
            object_id=object_id, is_active=is_active, limit=limit, offset=offset
        )

    async def create(self, payload: CameraCreate) -> Camera:
        existing = await self._cameras.by_code(payload.object_id, payload.code)
        if existing is not None:
            raise CameraAlreadyExists(
                f"Камера с кодом {payload.code} у объекта уже есть",
                camera_id=str(existing.id),
            )
        camera = Camera(
            object_id=payload.object_id,
            code=payload.code,
            name=(payload.name or "").strip() or payload.code,
            install_meta=payload.install_meta,
        )
        return await self._cameras.add(camera)

    async def update(self, camera_id: UUID, payload: CameraUpdate) -> Camera:
        camera = await self.get(camera_id)
        changes = payload.model_dump(exclude_unset=True)
        image_id = changes.get("reference_image_id")
        if (
            image_id is not None
            and await self._cameras.image_of_camera(image_id, camera.id) is None
        ):
            raise ImageNotFound(
                "Эталонный кадр — снимок этой камеры, а такого снимка у неё нет",
                image_id=str(image_id),
            )
        if changes.get("is_active") is False:
            await self._deactivate_zones(camera)
        if "is_active" in changes and changes["is_active"] != camera.is_active:
            self.touched.add(camera.object_id)
        for field, value in changes.items():
            setattr(camera, field, value.strip() if isinstance(value, str) else value)
        return await self._cameras.save(camera)

    async def deactivate(self, camera_id: UUID) -> None:
        """Камера не удаляется: на неё ссылаются снимки. Её зоны уходят вместе с ней."""
        camera = await self.get(camera_id)
        await self._deactivate_zones(camera)
        if camera.is_active:
            self.touched.add(camera.object_id)
        camera.is_active = False
        await self._cameras.save(camera)

    async def _deactivate_zones(self, camera: Camera) -> None:
        # Версия растёт, чтобы zones_version объекта заметила, что участки поменялись.
        for zone in await self._zones.active_for_camera(camera.id):
            zone.is_active = False
            zone.version = Zone.version + 1
