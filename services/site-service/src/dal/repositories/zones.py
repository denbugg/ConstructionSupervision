"""Запросы к таблице zone."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dal.models import Camera, Zone


class ZoneRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, zone_id: UUID) -> Zone | None:
        return await self._session.get(Zone, zone_id)

    async def list(
        self,
        *,
        object_id: UUID | None,
        camera_id: UUID | None,
        include_inactive: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Zone], int]:
        query = select(Zone)
        if object_id is not None:
            query = query.where(Zone.object_id == object_id)
        if camera_id is not None:
            query = query.where(Zone.camera_id == camera_id)
        if not include_inactive:
            query = query.where(Zone.is_active)
        total = await self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self._session.scalars(
            query.order_by(Zone.camera_id, Zone.zone_type, Zone.name, Zone.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)

    async def active_for_camera(self, camera_id: UUID) -> Sequence[Zone]:
        rows = await self._session.scalars(
            select(Zone).where(Zone.camera_id == camera_id, Zone.is_active)
        )
        return rows.all()

    async def active_on_active_cameras(self, object_id: UUID) -> Sequence[tuple[Zone, Camera]]:
        """Зоны, по которым строятся участки: и зона, и её камера активны."""
        rows = await self._session.execute(
            select(Zone, Camera)
            .join(Camera, Camera.id == Zone.camera_id)
            .where(Zone.object_id == object_id, Zone.is_active, Camera.is_active)
            .order_by(Zone.zone_type, Zone.name, Camera.code)
        )
        return [(zone, camera) for zone, camera in rows]

    async def zones_version(self, object_id: UUID) -> int:
        """Сумма версий всех зон объекта, включая неактивные: зоны не удаляются, сумма растёт."""
        total = await self._session.scalar(
            select(func.coalesce(func.sum(Zone.version), 0)).where(Zone.object_id == object_id)
        )
        return int(total or 0)

    async def add(self, zone: Zone) -> Zone:
        self._session.add(zone)
        await self._session.flush()
        await self._session.refresh(zone)
        return zone

    async def flush(self) -> None:
        """Отправить отложенные правки: следующий запрос должен их видеть."""
        await self._session.flush()

    async def save(self, zone: Zone) -> Zone:
        await self._session.flush()
        await self._session.refresh(zone)
        return zone
