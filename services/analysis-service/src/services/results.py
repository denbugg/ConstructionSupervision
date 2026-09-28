"""Чтение выводов по объекту: статус, прогресс этапов, загрузка техники (README, раздел 3).

Всё здесь — срезы последнего прогона; ничего не пересчитывается на лету.
"""

from datetime import date
from uuid import UUID

from lct_common import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from src.dal.models import DailyActivity, DailyEquipment, ObjectStatus, StageFact
from src.dal.repositories.snapshots import SnapshotRepository
from src.services.runs import enums


class ObjectNotAnalyzed(NotFoundError):
    code = "OBJECT_NOT_ANALYZED"

    def __init__(self, object_id: UUID) -> None:
        super().__init__(
            "По объекту ещё не было успешного прогона анализа: запустите POST /runs",
            object_id=str(object_id),
        )


class ResultsService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = SnapshotRepository(session)

    async def status(self, object_id: UUID) -> ObjectStatus:
        row = await self._repo.object_status(object_id)
        if row is None:
            raise ObjectNotAnalyzed(object_id)
        return row

    async def status_counters(self, object_id: UUID) -> tuple[ObjectStatus, dict[str, int]]:
        """Статус и отклонения по каждой серьёзности — с нулями, чтобы дашборд не гадал."""
        row = await self.status(object_id)
        found = row.counters.get("deviations", {})
        by_severity = {s: found.get(s, 0) for s in enums().values.get("severity", ())}
        return row, by_severity

    async def progress(
        self, object_id: UUID
    ) -> tuple[ObjectStatus, list[StageFact], dict[UUID, list[DailyActivity]]]:
        row = await self.status(object_id)
        activity: dict[UUID, list[DailyActivity]] = {}
        for day in await self._repo.daily_activity(object_id):
            activity.setdefault(day.stage_id, []).append(day)
        return row, await self._repo.stage_facts(object_id), activity

    async def equipment(
        self, object_id: UUID, day_from: date | None, day_to: date | None
    ) -> tuple[ObjectStatus, list[DailyEquipment]]:
        row = await self.status(object_id)
        return row, await self._repo.daily_equipment(object_id, day_from, day_to)
