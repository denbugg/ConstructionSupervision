"""Чтение срезов последнего прогона: статус объекта, этапы, активность, загрузка техники."""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dal.models import DailyActivity, DailyEquipment, ObjectStatus, StageFact


class SnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def object_status(self, object_id: UUID) -> ObjectStatus | None:
        return await self._session.get(ObjectStatus, object_id)

    async def stage_facts(self, object_id: UUID) -> list[StageFact]:
        rows = await self._session.scalars(
            select(StageFact).where(StageFact.object_id == object_id)
        )
        return list(rows)

    async def daily_activity(self, object_id: UUID) -> list[DailyActivity]:
        rows = await self._session.scalars(
            select(DailyActivity)
            .where(DailyActivity.object_id == object_id)
            .order_by(DailyActivity.stage_id, DailyActivity.day)
        )
        return list(rows)

    async def daily_equipment(
        self, object_id: UUID, day_from: date | None, day_to: date | None
    ) -> list[DailyEquipment]:
        """Загрузка техники за дни [day_from, day_to): полуинтервал, как у всех фильтров."""
        query = select(DailyEquipment).where(DailyEquipment.object_id == object_id)
        if day_from is not None:
            query = query.where(DailyEquipment.day >= day_from)
        if day_to is not None:
            query = query.where(DailyEquipment.day < day_to)
        rows = await self._session.scalars(
            query.order_by(DailyEquipment.day, DailyEquipment.equipment_class)
        )
        return list(rows)
