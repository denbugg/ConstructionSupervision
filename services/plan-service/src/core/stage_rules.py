"""Правило «этап → техника»: форма правила до записи (docs/methodology.md, раздел 5).

Правило — главная настраиваемая сущность методики, и оператор правит его руками. Ошибка
в правиле не видна сразу: оно просто перестаёт срабатывать. Поэтому бессмысленное правило
отклоняется при сохранении, а не молча портит сверку.
"""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any


class StageRuleError(ValueError):
    """Правило в таком виде не имеет смысла и не сохраняется."""


def _repeated(codes: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    repeated: list[str] = []
    for code in codes:
        if code in seen and code not in repeated:
            repeated.append(code)
        seen.add(code)
    return repeated


def check_rule_shape(
    required: Sequence[Mapping[str, Any]],
    allowed: Sequence[str],
    signature_equipment: Sequence[str],
) -> None:
    """Повторы — признак опечатки: «любой из [самосвал, самосвал]» оператор не имел в виду."""
    for number, group in enumerate(required, start=1):
        repeated = _repeated(group["any_of"])
        if repeated:
            raise StageRuleError(f"Группа {number}: класс {repeated} указан дважды")
    for name, codes in (("allowed", allowed), ("signature.equipment", signature_equipment)):
        repeated = _repeated(codes)
        if repeated:
            raise StageRuleError(f"{name}: класс {repeated} указан дважды")


def rule_codes(
    required: Sequence[Mapping[str, Any]],
    allowed: Sequence[str],
    signature_equipment: Sequence[str],
) -> list[str]:
    """Все коды классов правила в порядке упоминания — для сверки с equipment_classes.yaml."""
    codes = [c for group in required for c in group["any_of"]]
    return list(dict.fromkeys([*codes, *allowed, *signature_equipment]))
