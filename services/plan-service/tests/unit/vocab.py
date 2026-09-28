"""Словарь допустимых значений из настоящих справочных файлов — для unit-тестов без сервиса."""

import json

import yaml
from src.core.reference import parse_enums, parse_equipment_classes, parse_zone_roles
from src.core.templates import Vocabulary, parse_templates

from tests.conftest import CONTRACTS_DIR, SERVICE_ROOT

RAW_ENUMS = yaml.safe_load((CONTRACTS_DIR / "enums.yaml").read_text(encoding="utf-8"))
RAW_CLASSES = yaml.safe_load((CONTRACTS_DIR / "equipment_classes.yaml").read_text(encoding="utf-8"))
RAW_TEMPLATES = json.loads((SERVICE_ROOT / "data/wbs_templates.json").read_text(encoding="utf-8"))
ENUMS = parse_enums(RAW_ENUMS)
VOCAB = Vocabulary(
    object_types=ENUMS["object_type"],
    phases=ENUMS["construction_phase"],
    zone_roles=parse_zone_roles(RAW_ENUMS, ENUMS["zone_type"]),
    stage_labels=ENUMS["stage_label"],
    equipment=[c.code for c in parse_equipment_classes(RAW_CLASSES, ENUMS["equipment_group"])],
)
MONOLITH = {s.code: s for s in parse_templates(RAW_TEMPLATES, VOCAB)["RESIDENTIAL_MONOLITH"]}
