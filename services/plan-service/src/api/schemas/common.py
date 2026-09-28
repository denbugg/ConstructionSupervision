"""Перечисления контракта — из packages/contracts/enums.yaml, без копии в коде.

Списки значений не дублируются в Python (AGENTS.md, раздел 7): типы `Literal` строятся
из enums.yaml при старте. Swagger по-прежнему показывает допустимые значения, а новое
значение — строка в enums.yaml и перезапуск, без правки кода.
"""

from typing import Literal

from src.reference import reference

_ENUMS = reference().enums

ObjectType = Literal[_ENUMS["object_type"]]
ObjectLifecycle = Literal[_ENUMS["object_lifecycle"]]
ConstructionPhase = Literal[_ENUMS["construction_phase"]]
ZoneType = Literal[_ENUMS["zone_type"]]
EquipmentGroup = Literal[_ENUMS["equipment_group"]]
StageLabel = Literal[_ENUMS["stage_label"]]
StageSource = Literal[_ENUMS["stage_source"]]
DependencyType = Literal[_ENUMS["dependency_type"]]
