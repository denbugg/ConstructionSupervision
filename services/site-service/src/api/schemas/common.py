"""Перечисления контракта — из packages/contracts/enums.yaml, без копии в коде.

Типы `Literal` строятся из enums.yaml при старте (AGENTS.md, раздел 7): Swagger показывает
допустимые значения, а новое значение — строка в файле и перезапуск.
"""

from typing import Literal

from src.reference import enums

ZoneType = Literal[enums().zone_types]
ImageStatus = Literal[enums().values["image_status"]]
