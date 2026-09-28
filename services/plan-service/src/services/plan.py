"""«Весь план» объекта (interservice.md, раздел 1).

Весь план отдаётся одним ответом: этапы, связи, правила, календарь и классы техники —
analysis-service больше ничего у plan не спрашивает.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.plan import Plan, PlanRule, PlanStage
from src.dal.models import Stage, StageRule
from src.dal.repositories.rules import RuleRepository
from src.dal.repositories.stages import StageRepository
from src.reference import reference
from src.services.critical_path import calendar_of
from src.services.objects import ObjectService


class PlanService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._objects = ObjectService(session)
        self._stages = StageRepository(session)
        self._rules = RuleRepository(session)

    async def get_plan(self, object_id: UUID) -> Plan:
        obj = await self._objects.get(object_id)
        calendar = await calendar_of(self._session, obj)
        stages = await self._stages.all_for_object(object_id)
        rules = await self._rules.by_stages([s.id for s in stages])
        return Plan.model_validate(
            {
                "object": obj,
                "plan_version": obj.plan_version,
                "calendar": calendar,
                "equipment_classes": reference().equipment_classes,
                "stages": [_stage(s, rules.get(s.id)) for s in stages],
            },
            from_attributes=True,
        )


def _stage(stage: Stage, rule: StageRule | None) -> PlanStage:
    """Выключенное правило уходит как null: для анализа его нет."""
    read = PlanStage.model_validate(stage, from_attributes=True)
    active = rule is not None and rule.is_active
    read.rule = PlanRule.model_validate(rule, from_attributes=True) if active else None
    return read
