"""Чтение ленты отклонений: фильтры, сортировка, страница."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dal.models import Deviation


@dataclass(frozen=True)
class DeviationFilter:
    """Фильтры ленты; пустой список или None — фильтра нет."""

    object_id: UUID | None = None
    codes: Sequence[str] = ()
    severities: Sequence[str] = ()
    statuses: Sequence[str] = ()
    # Вердикт оператора — отдельно от статуса: закрытое с вердиктом остаётся RESOLVED.
    verdicts: Sequence[str] = ()
    stage_id: UUID | None = None
    area: str | None = None
    # Эпизод пересекается с [since, until).
    since: datetime | None = None
    until: datetime | None = None


class DeviationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, deviation_id: UUID) -> Deviation | None:
        return await self._session.get(Deviation, deviation_id)

    async def overlapping(
        self, object_id: UUID, since: datetime, until: datetime
    ) -> list[Deviation]:
        """Все эпизоды объекта, пересекающиеся с [since, until), — для отчёта, без страниц."""
        rows = await self._session.scalars(
            select(Deviation)
            .where(
                Deviation.object_id == object_id,
                Deviation.last_seen_at > since,
                Deviation.first_seen_at < until,
            )
            .order_by(Deviation.first_seen_at, Deviation.id)
        )
        return list(rows)

    async def page(
        self,
        flt: DeviationFilter,
        *,
        sort: str,
        severity_order: Sequence[str],
        limit: int,
        offset: int,
    ) -> tuple[list[Deviation], int]:
        """Страница ленты и общее число строк под тем же фильтром.

        `sort` — поле с необязательным минусом (по убыванию). Серьёзность сортируется
        по порядку списка из enums.yaml, а не по алфавиту.
        """
        query = select(Deviation)
        if flt.object_id is not None:
            query = query.where(Deviation.object_id == flt.object_id)
        if flt.codes:
            query = query.where(Deviation.code.in_(flt.codes))
        if flt.severities:
            query = query.where(Deviation.severity.in_(flt.severities))
        if flt.statuses:
            query = query.where(Deviation.status.in_(flt.statuses))
        if flt.verdicts:
            query = query.where(Deviation.verdict.in_(flt.verdicts))
        if flt.stage_id is not None:
            query = query.where(Deviation.stage_id == flt.stage_id)
        if flt.area is not None:
            query = query.where(Deviation.area == flt.area)
        if flt.since is not None:
            query = query.where(Deviation.last_seen_at > flt.since)
        if flt.until is not None:
            query = query.where(Deviation.first_seen_at < flt.until)

        total = await self._session.scalar(select(func.count()).select_from(query.subquery()))
        field = sort.removeprefix("-")
        column = (
            case({s: i for i, s in enumerate(severity_order)}, value=Deviation.severity)
            if field == "severity"
            else getattr(Deviation, field)
        )
        ordered = column.desc() if sort.startswith("-") else column.asc()
        # id вторым ключом: страницы стабильны, даже когда времена совпадают.
        rows = await self._session.scalars(
            query.order_by(ordered, Deviation.id).limit(limit).offset(offset)
        )
        return list(rows), int(total or 0)
