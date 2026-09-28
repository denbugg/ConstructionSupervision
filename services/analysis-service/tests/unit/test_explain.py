"""Тексты отклонений из шаблонов и facts."""

from dataclasses import replace
from pathlib import Path

import pytest
from src.core.context import build_context
from src.core.explain import (
    KNOWN_SPECS,
    ExplainError,
    describe,
    render,
    template_fields,
    templates,
    validate_rule,
)
from src.core.predicates import evaluate, load_rules
from src.core.rules import RuleParams

from tests.factories import load_facts, load_plan

RULES = {
    r.code: r for r in load_rules(Path(__file__).resolve().parents[2] / "data/deviation_rules.yaml")
}
PLAN = load_plan()
NAMES = {c.code: c.name_ru for c in PLAN.equipment_classes}


def test_d2_дня_1_читается_как_карточка(enums):
    ctx = build_context(
        PLAN,
        load_facts("facts_day1.json"),
        enums=enums,
        params=RuleParams(transient_window_sessions=4, min_stage_conf=0.5),
    )
    (finding,) = evaluate(ctx, [RULES["D2"]])

    deviation = describe(finding, RULES["D2"], NAMES)

    assert deviation.title == "Неполный комплект техники: «Разработка котлована»"
    assert "с 15.10.2026 по 20.11.2026" in deviation.message
    assert "экскаватор — 1, самосвал — 0" in deviation.message
    assert "самосвал — 0 при норме не меньше 2" in deviation.message
    assert "версия 2" in deviation.message


@pytest.mark.parametrize("code", list(RULES))
def test_шаблоны_используют_только_известные_форматы(code):
    rule = RULES[code]
    variants = [None, *rule.params.get("variants", {})]

    for variant in variants:
        for template in templates(rule, variant):
            assert {spec for _, spec in template_fields(template)} <= KNOWN_SPECS


SEVERITIES = ("INFO", "LOW", "MEDIUM", "HIGH")


@pytest.mark.parametrize("code", list(RULES))
def test_начальные_настройки_проходят_проверку(code):
    validate_rule(RULES[code], SEVERITIES)


@pytest.mark.parametrize(
    "change",
    [
        {"severity": "CRITICAL"},
        {"params": {"escalate_after_days": 1, "escalate_to": "URGENT"}},
        {"params": {"min_sessions": 0}},
        {"params": {"min_sessions": "2"}},
        {"params": {"min_sessions": True}},
        {"params": {"k_days": -1}},
        {"params": {"min_visible_share": 1.5}},
        {"params": {"variants": ["ahead"]}},
        {"title_template": "Этап «{stage_name»"},
        {"message_template": "{plan_start:weekday}"},
        {"params": {"variants": {"ahead": {"title_template": "{x:bad}", "message_template": ""}}}},
    ],
)
def test_испорченная_настройка_не_проходит_проверку(change):
    with pytest.raises(ExplainError):
        validate_rule(replace(RULES["D2"], **change), SEVERITIES)


def test_неизвестный_вариант_текста_это_ошибка_настройки():
    with pytest.raises(ExplainError):
        templates(RULES["D3"], "no_such_variant")


def test_группа_любой_из_перечисляет_классы_через_или():
    groups = [{"any_of": ["roller", "bulldozer"], "min": 1, "observed": 0}]

    text = render("{g:groups}", {"g": groups}, {"roller": "Каток", "bulldozer": "Бульдозер"})

    assert text == "каток или бульдозер — 0 при норме не меньше 1"


def test_поле_которого_нет_в_facts_это_ошибка_шаблона():
    with pytest.raises(ExplainError):
        render("Этап «{stage_name}»", {}, {})


def test_неизвестный_формат_это_ошибка_шаблона():
    with pytest.raises(ExplainError):
        render("{plan_start:weekday}", {"plan_start": "2026-10-20"}, {})
