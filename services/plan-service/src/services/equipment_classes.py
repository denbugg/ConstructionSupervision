"""Классы техники: список для интерфейса и проверка кодов в правилах этапов (ADR-0014)."""

from collections.abc import Iterable

from lct_common import ValidationError

from src.core.reference import EquipmentClass, unknown_codes
from src.reference import reference


class UnknownEquipmentClass(ValidationError):
    code = "UNKNOWN_EQUIPMENT_CLASS"


def list_classes(group: str | None = None, transient: bool | None = None) -> list[EquipmentClass]:
    """Классы в порядке файла: так их видит и оператор, и детектор."""
    return [
        c
        for c in reference().equipment_classes
        if (group is None or c.group == group) and (transient is None or c.transient is transient)
    ]


def check_equipment_codes(codes: Iterable[str]) -> None:
    """Каждый код в правиле этапа должен быть в equipment_classes.yaml.

    Опечатка в коде класса — не «техники нет», а правило, которое никогда не сработает:
    такое правило отклоняется при сохранении, а не молча портит сверку.
    """
    unknown = unknown_codes(codes, reference().equipment_classes)
    if unknown:
        raise UnknownEquipmentClass(
            "Класса техники нет в справочнике equipment_classes.yaml",
            unknown=unknown,
            known=[c.code for c in reference().equipment_classes],
        )
