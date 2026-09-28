"""Запросы к таблицам camera и image (эталонный кадр)."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dal.models import Camera, Image


class CameraRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, camera_id: UUID) -> Camera | None:
        return await self._session.get(Camera, camera_id)

    async def by_code(self, object_id: UUID, code: str) -> Camera | None:
        return await self._session.scalar(
            select(Camera).where(Camera.object_id == object_id, Camera.code == code)
        )

    async def for_object(self, object_id: UUID) -> Sequence[Camera]:
        rows = await self._session.scalars(
            select(Camera).where(Camera.object_id == object_id).order_by(Camera.code)
        )
        return rows.all()

    async def list(
        self, *, object_id: UUID | None, is_active: bool | None, limit: int, offset: int
    ) -> tuple[list[Camera], int]:
        query = select(Camera)
        if object_id is not None:
            query = query.where(Camera.object_id == object_id)
        if is_active is not None:
            query = query.where(Camera.is_active == is_active)
        total = await self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self._session.scalars(
            query.order_by(Camera.object_id, Camera.code).limit(limit).offset(offset)
        )
        return list(rows), int(total or 0)

    async def add(self, camera: Camera) -> Camera:
        self._session.add(camera)
        await self._session.flush()
        await self._session.refresh(camera)
        return camera

    async def save(self, camera: Camera) -> Camera:
        await self._session.flush()
        await self._session.refresh(camera)
        return camera

    async def image_of_camera(self, image_id: UUID, camera_id: UUID) -> Image | None:
        return await self._session.scalar(
            select(Image).where(Image.id == image_id, Image.camera_id == camera_id)
        )
