"""enums.yaml, прочитанный один раз при старте.

Файл смонтирован в контейнер только для чтения (`CONTRACTS_DIR`): новый тип зоны — строка в
enums.yaml и перезапуск сервиса, без правки кода.
"""

from functools import lru_cache
from pathlib import Path

import yaml

from src.config import settings
from src.core.reference import Enums, parse_enums

ENUMS_FILE = "enums.yaml"


@lru_cache
def enums() -> Enums:
    with (Path(settings.contracts_dir) / ENUMS_FILE).open(encoding="utf-8") as file:
        return parse_enums(yaml.safe_load(file))
