"""Общий шаг правки этапов, правил и календаря: plan_version растёт, analysis пересчитывает."""

from collections.abc import Collection
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.analysis_client import AnalysisClient
from src.dal.repositories.objects import ObjectRepository


class PlanVersion:
    def __init__(self, session: AsyncSession, signal: AnalysisClient) -> None:
        self._session = session
        self._objects = ObjectRepository(session)
        self._signal = signal

    async def changed(self, object_ids: Collection[UUID]) -> None:
        """Версия растёт в той же транзакции, что и правка; сигнал уходит после фиксации.

        Если послать сигнал до commit, analysis запросит «весь план» раньше, чем правка
        станет видна, и посчитает старый план под новым номером.
        """
        active = await self._objects.bump_plan_version(object_ids)
        await self._session.commit()
        for object_id in active:
            await self._signal.request_run(object_id)
