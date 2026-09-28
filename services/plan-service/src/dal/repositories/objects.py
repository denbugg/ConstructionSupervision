"""Запросы к таблице object. Единственное место, где есть SQL по объектам."""

from collections.abc import Collection, Sequence
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.dal.models import ConstructionObject


class ObjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, object_id: UUID) -> ConstructionObject | None:
        return await self._session.get(ConstructionObject, object_id)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        object_type: str | None = None,
    ) -> tuple[list[ConstructionObject], int]:
        """Страница объектов и общее число записей под тем же фильтром."""
        query = select(ConstructionObject)
        if status:
            query = query.where(ConstructionObject.status == status)
        if object_type:
            query = query.where(ConstructionObject.object_type == object_type)

        total = await self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self._session.scalars(
            query.order_by(ConstructionObject.created_at.desc()).limit(limit).offset(offset)
        )
        return list(rows), int(total or 0)

    async def add(self, obj: ConstructionObject) -> ConstructionObject:
        self._session.add(obj)
        await self._session.flush()
        return obj

    # Возвращаемые типы — Sequence: имя list в теле класса занято методом list.
    async def ids_with_calendar(self, calendar_id: UUID) -> Sequence[UUID]:
        rows = await self._session.scalars(
            select(ConstructionObject.id).where(ConstructionObject.calendar_id == calendar_id)
        )
        return list(rows)

    async def bump_plan_version(self, object_ids: Collection[UUID]) -> Sequence[UUID]:
        """plan_version + 1 одним UPDATE: две правки подряд не теряют ни одного шага.

        Возвращает объекты не в архиве — только их анализ стоит пересчитывать.
        """
        if not object_ids:
            return []
        rows = await self._session.execute(
            update(ConstructionObject)
            .where(ConstructionObject.id.in_(object_ids))
            .values(plan_version=ConstructionObject.plan_version + 1)
            .returning(ConstructionObject.id, ConstructionObject.status)
            .execution_options(synchronize_session="fetch")
        )
        return [object_id for object_id, status in rows if status != "ARCHIVED"]
