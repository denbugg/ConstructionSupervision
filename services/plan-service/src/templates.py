"""Шаблоны этапов (data/wbs_templates.json) и нормы МРР (data/mrr_norms.json), прочитанные один
раз при старте.

Испорченный шаблон не даёт сервису стартовать: лучше упасть при запуске, чем создавать
при импорте этапа с правилами, которые никогда не сработают.
"""

import json
from functools import lru_cache
from pathlib import Path

from src.config import settings
from src.core.mrr_norms import Norms, parse_norms
from src.core.schedule_generator import check_generator_template
from src.core.templates import TemplateStage, Vocabulary, parse_templates
from src.reference import reference

SERVICE_ROOT = Path(__file__).resolve().parents[1]


def vocabulary() -> Vocabulary:
    ref = reference()
    return Vocabulary(
        object_types=ref.enums["object_type"],
        phases=ref.enums["construction_phase"],
        zone_roles=ref.zone_roles,
        stage_labels=ref.enums["stage_label"],
        equipment=[c.code for c in ref.equipment_classes],
    )


@lru_cache
def templates() -> dict[str, tuple[TemplateStage, ...]]:
    path = SERVICE_ROOT / settings.wbs_templates_file
    raw = json.loads(path.read_text(encoding="utf-8"))
    return parse_templates(raw, vocabulary())


def template_for(object_type: str) -> dict[str, TemplateStage]:
    """Этапы шаблона типа объекта по коду; для типа без шаблона — пусто."""
    return {s.code: s for s in templates().get(object_type, ())}


@lru_cache
def norms() -> dict[str, Norms]:
    """Нормы МРР по типам объектов; сверены с шаблоном этапов, иначе сервис не стартует."""
    path = SERVICE_ROOT / settings.mrr_norms_file
    raw = json.loads(path.read_text(encoding="utf-8"))
    parsed = parse_norms(raw, vocabulary().phases)
    for object_type, item in parsed.items():
        check_generator_template(object_type, templates().get(object_type, ()), item)
    return parsed
