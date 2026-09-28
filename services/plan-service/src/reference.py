"""Справочные файлы контрактов, прочитанные один раз при старте (ADR-0014).

Файлы смонтированы в контейнер только для чтения (`CONTRACTS_DIR`), поэтому читаются
один раз: новый класс техники — правка файла и перезапуск сервиса.
"""

from dataclasses import dataclass
from functools import cached_property, lru_cache
from pathlib import Path

import yaml

from src.config import settings
from src.core.reference import (
    EquipmentClass,
    parse_enums,
    parse_equipment_classes,
    parse_zone_roles,
)

ENUMS_FILE = "enums.yaml"
CLASSES_FILE = "equipment_classes.yaml"


@dataclass(frozen=True)
class Reference:
    enums: dict[str, tuple[str, ...]]
    # Роль типа зоны: на участках с ролью WORK идут работы этапов.
    zone_roles: dict[str, str]
    equipment_classes: tuple[EquipmentClass, ...]

    @cached_property
    def by_code(self) -> dict[str, EquipmentClass]:
        return {c.code: c for c in self.equipment_classes}


def _read(name: str) -> object:
    with (Path(settings.contracts_dir) / name).open(encoding="utf-8") as file:
        return yaml.safe_load(file)


@lru_cache
def reference() -> Reference:
    raw_enums = _read(ENUMS_FILE)
    enums = parse_enums(raw_enums)
    classes = parse_equipment_classes(_read(CLASSES_FILE), enums["equipment_group"])
    return Reference(
        enums=enums,
        zone_roles=parse_zone_roles(raw_enums, enums["zone_type"]),
        equipment_classes=classes,
    )
