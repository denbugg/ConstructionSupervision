"""Правила «этап → техника»: создание, правка, удаление с ростом версий и сигналом (F11).

Каждая правка правила меняет план объекта: версия правила растёт (она попадает в
отклонение), растёт plan_version объекта, и в analysis уходит сигнал «пересчитай».
"""

from typing import Any
from uuid import UUID

from lct_common import ConflictError, NotFoundError, ValidationError, get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.rules import RuleCreate, RuleUpdate
from src.clients.analysis_client import AnalysisClient
from src.core.stage_rules import StageRuleError, check_rule_shape, rule_codes
from src.dal.models import StageRule
from src.dal.repositories.rules import RuleRepository
from src.services.equipment_classes import check_equipment_codes
from src.services.plan_version import PlanVersion
from src.services.stages import StageService

log = get_logger(__name__)


class StageRuleNotFound(NotFoundError):
    code = "STAGE_RULE_NOT_FOUND"

    def __init__(self, rule_id: UUID) -> None:
        super().__init__("Правило для этапа не найдено", rule_id=str(rule_id))


class StageRuleAlreadyExists(ConflictError):
    code = "STAGE_RULE_ALREADY_EXISTS"


class StageRuleInvalid(ValidationError):
    code = "STAGE_RULE_INVALID"


def _check(fields: dict[str, Any]) -> None:
    """Форма правила, затем коды классов по equipment_classes.yaml."""
    equipment = fields["signature"]["equipment"]
    try:
        check_rule_shape(fields["required"], fields["allowed"], equipment)
    except StageRuleError as exc:
        raise StageRuleInvalid(str(exc)) from exc
    check_equipment_codes(rule_codes(fields["required"], fields["allowed"], equipment))


class RuleService:
    def __init__(self, session: AsyncSession, signal: AnalysisClient) -> None:
        self._repo = RuleRepository(session)
        self._stages = StageService(session, signal)
        self._plan_version = PlanVersion(session, signal)

    async def get(self, rule_id: UUID) -> StageRule:
        rule = await self._repo.get(rule_id)
        if rule is None:
            raise StageRuleNotFound(rule_id)
        return rule

    async def list(
        self, *, limit: int, offset: int, stage_id: UUID | None, object_id: UUID | None
    ) -> tuple[list[StageRule], int]:
        return await self._repo.list(
            limit=limit, offset=offset, stage_id=stage_id, object_id=object_id
        )

    async def create(self, payload: RuleCreate, actor: str | None) -> StageRule:
        stage = await self._stages.get(payload.stage_id)
        fields = payload.model_dump(mode="json", exclude_none=True)
        fields["signature"] = payload.signature.model_dump(mode="json")
        _check(fields)
        if await self._repo.by_stage(stage.id) is not None:
            raise StageRuleAlreadyExists(
                "У этапа уже есть правило: правьте его, а не создавайте второе",
                stage_id=str(stage.id),
            )
        fields["stage_id"] = stage.id
        rule = await self._repo.add(StageRule(**fields))
        await self._plan_version.changed([stage.object_id])
        log.info("stage_rule.created", rule_id=str(rule.id), stage_id=str(stage.id), actor=actor)
        return rule

    async def update(self, rule_id: UUID, payload: RuleUpdate, actor: str | None) -> StageRule:
        rule = await self.get(rule_id)
        # null в частичной правке означает «не менять»: у правила нет пустых полей.
        changes = {k: v for k, v in payload.model_dump(mode="json").items() if v is not None}
        if not changes:
            return rule
        current = {"required": rule.required, "allowed": rule.allowed, "signature": rule.signature}
        _check(current | changes)
        for field, value in changes.items():
            setattr(rule, field, value)
        # Приращение в SQL, а не в Python: две правки подряд дают две версии, а не одну.
        rule.version = StageRule.version + 1
        rule = await self._repo.save(rule)
        stage = await self._stages.get(rule.stage_id)
        await self._plan_version.changed([stage.object_id])
        log.info("stage_rule.updated", rule_id=str(rule_id), fields=sorted(changes), actor=actor)
        return rule

    async def delete(self, rule_id: UUID, actor: str | None) -> None:
        """Этап без правила: по нему не проверяются D1, D2, D8, D9 (interservice.md, раздел 1)."""
        rule = await self.get(rule_id)
        stage = await self._stages.get(rule.stage_id)
        await self._repo.delete(rule)
        await self._plan_version.changed([stage.object_id])
        log.info("stage_rule.deleted", rule_id=str(rule_id), stage_id=str(stage.id), actor=actor)
