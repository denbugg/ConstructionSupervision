"""Запись выводов прогона: лента отклонений и срезы по этапам, дням и объекту.

Срезы (stage_fact, daily_activity, daily_equipment, object_status) целиком
пересчитываются каждым прогоном, поэтому заменяются полностью. Лента — нет: у
отклонения есть вердикт оператора и история, её строки обновляются по плану
сверки из core/ledger.py.
"""

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.explain import Deviation as DeviationText
from src.core.ledger import OPEN, RESOLVED
from src.core.run import AnalysisResult
from src.dal.models import DailyActivity, DailyEquipment, Deviation, ObjectStatus, StageFact


def _fill(row: Deviation, text: DeviationText, status: str) -> Deviation:
    """Поля строки ленты из найденного эпизода: всё, кроме вердикта оператора."""
    finding = text.finding
    row.stage_id = finding.stage_id
    row.area = finding.area
    row.equipment_class = finding.equipment_class
    row.session_id = finding.session_id
    row.code = finding.code
    row.severity = finding.severity
    row.title = text.title
    row.message = text.message
    row.facts = finding.facts
    row.rule_ref = finding.rule_ref
    row.evidence = list(finding.evidence)
    row.status = status
    row.first_seen_at = finding.first_seen_at
    row.last_seen_at = finding.last_seen_at
    row.occurrences = finding.occurrences
    return row


class ResultsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def deviations(self, object_id: UUID) -> list[Deviation]:
        rows = await self._session.scalars(
            select(Deviation).where(Deviation.object_id == object_id)
        )
        return list(rows)

    async def count_open(self, object_id: UUID) -> int:
        total = await self._session.scalar(
            select(func.count())
            .select_from(Deviation)
            .where(Deviation.object_id == object_id, Deviation.status.in_(OPEN))
        )
        return int(total or 0)

    async def delete(self, ids: Iterable[UUID]) -> None:
        """Строки пересмотренных эпизодов: их по нынешним фактам не было."""
        ids = list(ids)
        if ids:
            await self._session.execute(delete(Deviation).where(Deviation.id.in_(ids)))
            await self._session.flush()

    async def resolve(self, ids: Iterable[UUID]) -> None:
        ids = list(ids)
        if ids:
            await self._session.execute(
                update(Deviation).where(Deviation.id.in_(ids)).values(status=RESOLVED)
            )
            # Открытая строка по ключу единственна: закрытие должно дойти до базы раньше,
            # чем по тому же ключу откроется новая.
            await self._session.flush()

    async def update(self, row: Deviation, text: DeviationText, status: str) -> None:
        _fill(row, text, status)
        await self._session.flush()

    async def insert(self, object_id: UUID, text: DeviationText, status: str) -> None:
        self._session.add(_fill(Deviation(object_id=object_id), text, status))
        await self._session.flush()

    async def replace_snapshots(self, result: AnalysisResult, computed_at: datetime) -> None:
        """Срезы объекта целиком из результата прогона."""
        object_id = result.object_id
        for model in (StageFact, DailyActivity, DailyEquipment, ObjectStatus):
            await self._session.execute(delete(model).where(model.object_id == object_id))
        self._session.add_all(
            StageFact(
                object_id=object_id,
                stage_id=s.stage_id,
                actual_start=s.actual_start,
                last_activity_at=s.last_activity_at,
                effective_days=s.effective_days,
                progress=s.progress,
                planned_progress=s.planned_progress or 0.0,
                spi=s.spi,
                forecast_end=s.forecast_end,
                delay_days=s.delay_days,
                status=s.status,
                confidence=s.confidence,
                facts=s.facts
                | {
                    "expected_start": s.expected_start.isoformat(),
                    "expected_end": s.expected_end.isoformat(),
                },
            )
            for s in result.stage_facts
        )
        self._session.add_all(
            DailyActivity(
                object_id=object_id,
                stage_id=a.stage_id,
                day=a.day,
                sessions_total=a.sessions_total,
                sessions_working=a.sessions_working,
                activity_index=a.activity_index,
                blind_sessions=a.blind_sessions,
            )
            for a in result.daily_activity
        )
        self._session.add_all(
            DailyEquipment(
                object_id=object_id,
                day=e.day,
                equipment_class=e.equipment_class,
                sessions_seen=e.sessions_seen,
                max_count=e.max_count,
            )
            for e in result.daily_equipment
        )
        status = result.object_status
        self._session.add(
            ObjectStatus(
                object_id=object_id,
                computed_at=computed_at,
                as_of=result.as_of,
                status=status.status,
                delay_days=status.delay_days,
                spi=status.spi,
                confidence=status.confidence,
                counters=result.counters | {"facts": status.facts},
                stages_at_risk=list(status.stages_at_risk),
            )
        )
        await self._session.flush()
