"""Настройки правил отклонений D1–D10: чтение и правка без правки кода (AGENTS.md, раздел 12)."""

from dataclasses import replace
from typing import Any

from lct_common import NotFoundError, ValidationError, get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.explain import ExplainError, validate_rule
from src.dal.models import DeviationRule as DeviationRuleRow
from src.dal.repositories.rules import RuleRepository, to_rule
from src.services.runs import enums

log = get_logger(__name__)


class DeviationRuleNotFound(NotFoundError):
    code = "DEVIATION_RULE_NOT_FOUND"

    def __init__(self, code: str) -> None:
        super().__init__("Правило отклонения не найдено", code=code)


class DeviationRuleInvalid(ValidationError):
    code = "DEVIATION_RULE_INVALID"


class RuleService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = RuleRepository(session)

    async def all(self) -> list[DeviationRuleRow]:
        return await self._repo.rows()

    async def get(self, code: str) -> DeviationRuleRow:
        row = await self._repo.get(code)
        if row is None:
            raise DeviationRuleNotFound(code)
        return row

    async def update(
        self, code: str, changes: dict[str, Any], actor: str | None
    ) -> DeviationRuleRow:
        """Частичная правка. `params` сливаются по ключам: ключ со значением null удаляется.

        Предикат не правится: это имя функции в коде, а не настройка. Новая настройка
        проверяется целиком до записи — сломанный шаблон не должен уронить следующий прогон.
        """
        row = await self.get(code)
        params_patch = changes.pop("params", None) or {}
        params = dict(row.params)
        for key, value in params_patch.items():
            if value is None:
                params.pop(key, None)
            else:
                params[key] = value
        candidate = replace(to_rule(row), params=params, **changes)
        try:
            validate_rule(candidate, enums().values.get("severity", ()))
        except ExplainError as exc:
            raise DeviationRuleInvalid(str(exc), code=code) from exc

        row.enabled = candidate.enabled
        row.severity = candidate.severity
        row.params = candidate.params
        row.title_template = candidate.title_template
        row.message_template = candidate.message_template
        await self._repo.save(row)
        # Журнала правок в базе нет: кто и что поменял, остаётся в структурном логе.
        log.info(
            "deviation_rule.updated",
            code=code,
            actor=actor,
            fields=sorted(changes),
            params=sorted(params_patch),
        )
        return row
