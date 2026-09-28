"""Фикстуры двух контрактов разбираются моделями и описывают сценарий демо-дней.

Если эти тесты упали, методика будет проверяться не на том входе: сначала чинятся
фикстуры (tests/fixtures/build_fixtures.py), потом всё остальное.
"""

from datetime import date

import pytest
from pydantic import ValidationError
from src.core.inputs import Facts, Plan

from tests.factories import load_facts, load_plan

FACTS_FILES = [
    "facts_normal_day.json",
    "facts_day1.json",
    "facts_day2.json",
    "facts_day3.json",
]
PIT, GATE, STORAGE = "PIT:Котлован", "ENTRY_GATE:Въезд", "STORAGE:Склад"


def _counts(facts: Facts, area: str, equipment_class: str) -> list[int]:
    """Число единиц класса на участке по окнам дня; 0 — класса в окне нет."""
    result = []
    for session in facts.sessions:
        (fact,) = [a for a in session.areas if a.area == area]
        result.append(sum(e.count for e in fact.equipment if e.equipment_class == equipment_class))
    return result


def _visibility(facts: Facts, area: str) -> set[str]:
    return {a.visibility.status for s in facts.sessions for a in s.areas if a.area == area}


def test_план_разбирается_и_этапы_идут_по_порядку():
    plan = load_plan()

    assert [s.seq for s in plan.stages] == [1, 2, 3]
    assert plan.calendar.weekend_days == (7,)
    assert plan.stages[1].rule.required[1].min == 2


def test_классы_в_правилах_есть_в_плане():
    plan = load_plan()
    known = {c.code for c in plan.equipment_classes}

    for stage in plan.stages:
        rule = stage.rule
        used = {c for g in rule.required for c in g.any_of} | set(rule.allowed)
        used |= set(rule.signature.equipment)
        assert used <= known, stage.name


def test_этапы_идут_на_рабочих_участках(enums):
    plan = load_plan()

    assert plan.object.object_type in enums.values["object_type"]
    for stage in plan.stages:
        assert enums.role(stage.zone_type) == "WORK", stage.name
        assert stage.phase in enums.values["construction_phase"]
        if stage.visual_stage is not None:
            enums.stage_index(stage.visual_stage)


@pytest.mark.parametrize("name", FACTS_FILES)
def test_факты_разбираются_и_принадлежат_объекту_плана(name):
    facts = load_facts(name)

    assert facts.object_id == load_plan().object.id
    assert facts.sessions
    for session in facts.sessions:
        assert facts.period_from <= session.window_start < facts.period_to
        assert {a.area for a in session.areas} == {PIT, GATE, STORAGE}


@pytest.mark.parametrize("name", FACTS_FILES)
def test_значения_фактов_есть_в_enums(name, enums):
    facts = load_facts(name)
    classes = {c.code for c in load_plan().equipment_classes}

    for session in facts.sessions:
        enums.stage_index(session.stage_observation.stage_label)
        for area in session.areas:
            enums.role(area.zone_type)
            assert area.area == f"{area.zone_type}:{area.name}"
            assert area.visibility.status in enums.values["visibility_status"]
            if area.visibility.reason is not None:
                assert area.visibility.reason in enums.values["visibility_reason"]
            for item in area.equipment:
                assert item.equipment_class in classes
                assert len(item.evidence) == item.count


@pytest.mark.parametrize("name", FACTS_FILES)
def test_у_каждой_рамки_свой_идентификатор(name):
    facts = load_facts(name)

    for session in facts.sessions:
        ids = [
            ev.detection_id for a in session.areas for item in a.equipment for ev in item.evidence
        ]
        assert len(ids) == len(set(ids))


def test_неизвестные_поля_поставщика_игнорируются():
    raw = load_plan().model_dump(mode="json")
    raw["new_field"] = 1
    raw["stages"][0]["another"] = {"x": 1}

    assert Plan.model_validate(raw).stages[0].name == "Подготовка территории"


def test_отметка_выполнен_разбирается_и_необязательна():
    """Контракт 1: поля отметки новые и необязательные — старый ответ плана тоже разбирается."""
    raw = load_plan().model_dump(mode="json")
    raw["stages"][1] |= {
        "completed_on": "2026-11-18",
        "completed_by": "Петров П. П.",
        "completion_note": "акт приёмки",
    }

    pit = Plan.model_validate(raw).stages[1]

    assert (pit.completed_on, pit.completed_by) == (date(2026, 11, 18), "Петров П. П.")
    assert load_plan().stages[1].completed_on is None


def test_техника_без_доказательств_не_проходит_разбор():
    raw = load_facts("facts_day1.json").model_dump(mode="json", by_alias=True)
    raw["sessions"][0]["areas"][0]["equipment"][0]["evidence"] = []

    with pytest.raises(ValidationError):
        Facts.model_validate(raw)


def test_нормальный_день_самосвалы_по_два_раз_в_два_часа():
    trucks = _counts(load_facts("facts_normal_day.json"), PIT, "dump_truck")

    assert trucks[::4] == [2, 2, 2]
    assert sum(trucks) == 6


def test_день_1_экскаватор_без_самосвалов():
    facts = load_facts("facts_day1.json")

    assert all(n == 1 for n in _counts(facts, PIT, "excavator"))
    assert sum(_counts(facts, PIT, "dump_truck")) == 0


def test_день_2_в_котловане_появляется_бетононасос():
    pump = _counts(load_facts("facts_day2.json"), PIT, "concrete_pump")

    assert pump[:8] == [0] * 8
    assert all(pump[8:])


def test_день_3_экскаватор_стоит_на_въезде_а_склад_не_виден():
    facts = load_facts("facts_day3.json")

    gate = [a for s in facts.sessions for a in s.areas if a.area == GATE]
    statics = [e.static for a in gate for e in a.equipment if e.equipment_class == "excavator"]
    assert statics[0] == 0 and all(n == 1 for n in statics[1:])
    assert _visibility(facts, STORAGE) == {"BLIND"}
    assert _visibility(facts, GATE) == {"PARTIAL"}
    assert _visibility(facts, PIT) == {"OK"}
