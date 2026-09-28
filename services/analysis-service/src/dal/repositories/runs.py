"""Запросы к analysis_run. Единственное место, где есть SQL по прогонам."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.dal.models import AnalysisRun

RUNNING = "RUNNING"


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, run: AnalysisRun) -> AnalysisRun:
        self._session.add(run)
        await self._session.flush()
        # id, статус и время задаёт база: перечитываем, чтобы отдать их в ответе.
        await self._session.refresh(run)
        return run

    async def get(self, run_id: UUID) -> AnalysisRun | None:
        return await self._session.get(AnalysisRun, run_id)

    async def lock_object(self, object_id: UUID) -> None:
        """Блокировка объекта до конца транзакции: два сигнала не заведут два прогона."""
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"analysis_run:{object_id}"},
        )

    async def running(self, object_id: UUID) -> list[AnalysisRun]:
        rows = await self._session.scalars(
            select(AnalysisRun)
            .where(AnalysisRun.object_id == object_id, AnalysisRun.status == RUNNING)
            .order_by(AnalysisRun.created_at)
        )
        return list(rows)

    async def consume_rerun(self, run_id: UUID) -> bool:
        """Снимает отметку «нужен ещё прогон»; True — отметка была и снята именно сейчас.

        Снятие атомарно, поэтому повторный прогон запускается ровно один раз, даже если
        проверку по ошибке вызвали дважды.
        """
        consumed = await self._session.scalar(
            update(AnalysisRun)
            .where(AnalysisRun.id == run_id, AnalysisRun.rerun_requested.is_(True))
            .values(rerun_requested=False)
            .returning(AnalysisRun.id)
        )
        return consumed is not None

    async def latest(self, object_id: UUID) -> AnalysisRun | None:
        return await self._session.scalar(
            select(AnalysisRun)
            .where(AnalysisRun.object_id == object_id)
            .order_by(AnalysisRun.created_at.desc())
            .limit(1)
        )

    async def rerun_pending(self, object_id: UUID) -> bool:
        """Есть прогон с отметкой «нужен ещё»: закончился, а его повтор ещё не заведён."""
        found = await self._session.scalar(
            select(AnalysisRun.id)
            .where(AnalysisRun.object_id == object_id, AnalysisRun.rerun_requested.is_(True))
            .limit(1)
        )
        return found is not None

    async def count_running(self, object_id: UUID) -> int:
        total = await self._session.scalar(
            select(func.count())
            .select_from(AnalysisRun)
            .where(AnalysisRun.object_id == object_id, AnalysisRun.status == RUNNING)
        )
        return int(total or 0)

    @staticmethod
    def is_stale(run: AnalysisRun, now: datetime, stale_after_s: float) -> bool:
        return (now - run.created_at).total_seconds() > stale_after_s
