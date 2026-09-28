"""Запись факта окна: session_fact, area_visibility и стадия окна."""

from uuid import UUID

from sqlalchemy import delete, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.aggregation import WindowFact
from src.dal.models import AreaVisibility, ObservationSession, SessionFact


class FactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_window_fact(self, session_id: UUID, fact: WindowFact) -> None:
        """Факт окна пересчитывается целиком: старые строки уходят, новые пишутся заново."""
        await self._session.execute(delete(SessionFact).where(SessionFact.session_id == session_id))
        await self._session.execute(
            delete(AreaVisibility).where(AreaVisibility.session_id == session_id)
        )
        self._session.add_all(
            SessionFact(
                session_id=session_id,
                area=f.area,
                equipment_class=f.equipment_class,
                count=f.count,
                static=f.static,
                evidence=list(f.evidence),
            )
            for f in fact.equipment
        )
        self._session.add_all(
            AreaVisibility(
                session_id=session_id,
                area=v.area,
                zone_type=v.zone_type,
                name=v.name,
                cameras_total=v.cameras_total,
                cameras_usable=v.cameras_usable,
                status=v.status,
                reason=v.reason,
            )
            for v in fact.visibility
        )
        stage = fact.stage
        # updated_at ставится явно: это «когда факт окна пересчитан», его отдаёт контракт.
        await self._session.execute(
            update(ObservationSession)
            .where(ObservationSession.id == session_id)
            .values(
                stage_label=stage.label if stage else None,
                stage_conf=stage.conf if stage else None,
                stage_scores=stage.scores if stage else {},
                updated_at=func.now(),
            )
        )
        await self._session.flush()
