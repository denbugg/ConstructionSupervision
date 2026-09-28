"""Шаблоны этапов по типам объектов (data/wbs_templates.json): разбор и проверка.

Из шаблона импорт и генератор берут фазу, тип участка, визуальную стадию, связи и правило
«этап → техника» (ТЗ, п. 5.2). Испорченный шаблон — ошибка старта, а не правило, которое
молча не сработает на площадке.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from src.core.cpm import CpmError, CpmStage, Link, order_stages
from src.core.stage_rules import StageRuleError, check_rule_shape, rule_codes
from src.core.stages import WORK_ROLE


class TemplateError(ValueError):
    """Шаблон этапов испорчен: сервис с ним не стартует."""


@dataclass(frozen=True)
class TemplateLink:
    code: str
    type: str
    lag_days: int


@dataclass(frozen=True)
class TemplateStage:
    code: str
    name: str
    work_codes: tuple[str, ...]
    phase: str
    zone_type: str
    visual_stage: str | None
    # Длительность этапа в долях его периода таблицы 1 МРР — для генератора; None — не задана.
    share: float | None
    predecessors: tuple[TemplateLink, ...]
    # Правило в форме API: required, allowed, signature (min_sessions — по умолчанию базы).
    rule: dict[str, Any] | None
    # Длительность — время устройства свай по МРР, п. 5.1.6, а не доля периода.
    piles: bool = False


@dataclass(frozen=True)
class Vocabulary:
    """Допустимые значения из enums.yaml и equipment_classes.yaml."""

    object_types: Collection[str]
    phases: Collection[str]
    zone_roles: Mapping[str, str]
    stage_labels: Collection[str]
    equipment: Collection[str]


def parse_templates(raw: Any, vocab: Vocabulary) -> dict[str, tuple[TemplateStage, ...]]:
    """Шаблоны по типу объекта; ключи с `_` — пояснения к файлу."""
    if not isinstance(raw, dict):
        raise TemplateError("wbs_templates.json: ожидался словарь «тип объекта → этапы»")
    templates = {}
    for object_type, items in raw.items():
        if object_type.startswith("_"):
            continue
        if object_type not in vocab.object_types:
            raise TemplateError(f"wbs_templates.json: типа объекта {object_type!r} нет в enums")
        templates[object_type] = _parse_stages(object_type, items or (), vocab)
    return templates


def _parse_stages(object_type: str, items: Any, vocab: Vocabulary) -> tuple[TemplateStage, ...]:
    stages: list[TemplateStage] = []
    for number, item in enumerate(items, start=1):
        where = f"wbs_templates.json, {object_type}, этап {number}"
        try:
            stage = _stage(item)
        except (KeyError, TypeError, ValueError) as exc:
            raise TemplateError(f"{where}: испорчено поле {exc}") from exc
        _check_stage(stage, vocab, where)
        stages.append(stage)
    codes = [s.code for s in stages]
    repeated = {c for c in codes if codes.count(c) > 1}
    if repeated:
        raise TemplateError(
            f"wbs_templates.json, {object_type}: коды {sorted(repeated)} повторяются"
        )
    _check_links(object_type, stages)
    return tuple(stages)


def _stage(item: Mapping[str, Any]) -> TemplateStage:
    links = tuple(
        TemplateLink(str(p["code"]), str(p["type"]), int(p.get("lag_days", 0)))
        for p in item.get("predecessors") or ()
    )
    share = item.get("share")
    return TemplateStage(
        code=str(item["code"]),
        name=str(item["name"]),
        work_codes=tuple(str(c) for c in item.get("work_codes") or ()),
        phase=str(item["phase"]),
        zone_type=str(item["zone_type"]),
        visual_stage=item.get("visual_stage"),
        share=float(share) if share is not None else None,
        predecessors=links,
        rule=item.get("rule"),
        piles=bool(item.get("piles", False)),
    )


def _check_stage(stage: TemplateStage, vocab: Vocabulary, where: str) -> None:
    if stage.phase not in vocab.phases:
        raise TemplateError(f"{where}: фазы {stage.phase!r} нет в construction_phase")
    if vocab.zone_roles.get(stage.zone_type) != WORK_ROLE:
        raise TemplateError(f"{where}: тип участка {stage.zone_type!r} — не рабочий")
    if stage.visual_stage is not None and stage.visual_stage not in vocab.stage_labels:
        raise TemplateError(f"{where}: стадии {stage.visual_stage!r} нет в stage_label")
    if stage.share is not None and not 0 < stage.share <= 1:
        raise TemplateError(f"{where}: доля этапа — число от 0 до 1")
    if stage.piles and stage.share is not None:
        raise TemplateError(f"{where}: у этапа свай длительность из норм на сваи, доля не нужна")
    if stage.rule is not None:
        _check_rule(stage.rule, vocab, where)


def _check_rule(rule: Mapping[str, Any], vocab: Vocabulary, where: str) -> None:
    try:
        required = rule.get("required") or []
        allowed = rule.get("allowed") or []
        signature = rule.get("signature") or {}
        equipment = signature.get("equipment") or []
        if any(not group["any_of"] or int(group["min"]) < 1 for group in required):
            raise TemplateError(f"{where}: группа правила пуста или min < 1")
        check_rule_shape(required, allowed, equipment)
    except (KeyError, TypeError, AttributeError, StageRuleError) as exc:
        raise TemplateError(f"{where}: испорчено правило: {exc}") from exc
    unknown = [c for c in rule_codes(required, allowed, equipment) if c not in vocab.equipment]
    if unknown:
        raise TemplateError(f"{where}: классов {unknown} нет в equipment_classes.yaml")
    label = signature.get("stage_label")
    if label is not None and label not in vocab.stage_labels:
        raise TemplateError(f"{where}: стадии сигнатуры {label!r} нет в stage_label")


def _check_links(object_type: str, stages: list[TemplateStage]) -> None:
    """Связи шаблона — на этапы того же шаблона, без циклов; даты для проверки не нужны."""
    ids = {s.code: uuid5(NAMESPACE_URL, s.code) for s in stages}
    try:
        cpm = []
        for stage in stages:
            links = []
            for link in stage.predecessors:
                if link.code not in ids:
                    raise CpmError(f"связь на этап {link.code!r}, которого нет в шаблоне")
                links.append(Link(ids[link.code], link.type, link.lag_days))
            # Для порядка связей даты не нужны: подставляется любая.
            cpm.append(CpmStage(ids[stage.code], date.min, date.min, tuple(links)))
        order_stages(cpm)
    except CpmError as exc:
        raise TemplateError(f"wbs_templates.json, {object_type}: {exc}") from exc
