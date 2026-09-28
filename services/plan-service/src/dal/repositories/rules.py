"""Запросы к таблице stage_rule."""

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dal.models import Stage, StageRule


class RuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, rule_id: UUID) -> StageRule | None:
        return await self._session.get(StageRule, rule_id)

    async def by_stage(self, stage_id: UUID) -> StageRule | None:
        return await self._session.scalar(select(StageRule).where(StageRule.stage_id == stage_id))

    async def by_stages(self, stage_ids: Collection[UUID]) -> dict[UUID, StageRule]:
        if not stage_ids:
            return {}
        rows = await self._session.scalars(
            select(StageRule).where(StageRule.stage_id.in_(stage_ids))
        )
        return {rule.stage_id: rule for rule in rows}

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        stage_id: UUID | None = None,
        object_id: UUID | None = None,
    ) -> tuple[list[StageRule], int]:
        """Правила в порядке этапов графика."""
        query = select(StageRule).join(Stage, Stage.id == StageRule.stage_id)
        if stage_id:
            query = query.where(StageRule.stage_id == stage_id)
        if object_id:
            query = query.where(Stage.object_id == object_id)
        total = await self._session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self._session.scalars(
            query.order_by(Stage.object_id, Stage.seq).limit(limit).offset(offset)
        )
        return list(rows), int(total or 0)

    async def add(self, rule: StageRule) -> StageRule:
        self._session.add(rule)
        await self._session.flush()
        await self._session.refresh(rule)
        return rule

    async def save(self, rule: StageRule) -> StageRule:
        await self._session.flush()
        await self._session.refresh(rule)
        return rule

    async def delete(self, rule: StageRule) -> None:
        await self._session.delete(rule)
        await self._session.flush()
