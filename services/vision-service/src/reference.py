"""Справочные файлы, прочитанные один раз при старте.

equipment_classes.yaml и enums.yaml смонтированы в `CONTRACTS_DIR` только для чтения,
stage_prompts.yaml — справочник самого сервиса. Испорченный файл не даёт сервису стартовать.
"""

from functools import lru_cache
from pathlib import Path

import yaml

from src.config import settings
from src.core.stages import StagePrompts, parse_stage_labels, parse_stage_prompts
from src.core.vocabulary import Vocabulary, parse_vocabulary

CLASSES_FILE = "equipment_classes.yaml"
ENUMS_FILE = "enums.yaml"


@lru_cache
def vocabulary() -> Vocabulary:
    return parse_vocabulary((Path(settings.contracts_dir) / CLASSES_FILE).read_bytes())


@lru_cache
def stage_prompts() -> StagePrompts:
    with (Path(settings.contracts_dir) / ENUMS_FILE).open(encoding="utf-8") as file:
        labels = parse_stage_labels(yaml.safe_load(file))
    with Path(settings.stage_prompts_file).open(encoding="utf-8") as file:
        return parse_stage_prompts(yaml.safe_load(file), labels)
