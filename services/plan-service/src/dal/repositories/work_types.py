"""Запросы к таблице work_type."""

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dal.models import WorkType


class WorkTypeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def filtered(self, *, level: int | None, parent_code: str | None) -> Sequence[WorkType]:
        """Все подходящие строки без порядка: порядок кодов задаёт core (code_sort_key)."""
        query = select(WorkType)
        if level is not None:
            query = query.where(WorkType.level == level)
        if parent_code is not None:
            query = query.where(WorkType.parent_code == parent_code)
        return (await self._session.scalars(query)).all()

    async def replace_all(self, work_types: Sequence[WorkType]) -> None:
        """Справочник заменяется целиком: он один на систему и приходит одним файлом."""
        await self._session.execute(delete(WorkType))
        self._session.add_all(work_types)
        await self._session.flush()
