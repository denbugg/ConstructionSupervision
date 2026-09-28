"""Шаблон этапов жилого монолита: разбирается, повторяет таблицу ТЗ п. 5.2, ломается громко."""

import copy

import pytest
from src.core.templates import TemplateError, parse_templates

from tests.unit.vocab import MONOLITH, RAW_TEMPLATES, VOCAB


def _broken(**change):
    raw = copy.deepcopy(RAW_TEMPLATES)
    raw["RESIDENTIAL_MONOLITH"][3].update(change)
    return raw


def test_шаблон_монолита_повторяет_таблицу_тз():
    assert len(MONOLITH) == 12
    pit = MONOLITH["12.3.1"]
    assert (pit.zone_type, pit.visual_stage, pit.phase) == ("PIT", "PIT", "SUBSTRUCTURE")
    assert pit.rule["required"] == [
        {"any_of": ["excavator"], "min": 1},
        {"any_of": ["dump_truck"], "min": 2},
    ]
    # Группа «любой из»: стены и фасад — башенный кран, автокран или кран-манипулятор.
    envelope = MONOLITH["12.4.8"].rule["required"][0]
    assert envelope["any_of"] == ["tower_crane", "truck_crane", "manipulator_crane"]
    # У каждого этапа длительность для генератора: доля периода МРР или время на сваи.
    assert all((s.share is None) == s.piles for s in MONOLITH.values())
    assert [s.code for s in MONOLITH.values() if s.piles] == ["12.3.2"]


def test_каждая_связь_шаблона_ведёт_на_его_этап():
    for stage in MONOLITH.values():
        assert all(link.code in MONOLITH for link in stage.predecessors)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"phase": "DIGGING"}, "фазы"),
        ({"zone_type": "ENTRY_GATE"}, "не рабочий"),
        ({"visual_stage": "ROOF"}, "stage_label"),
        ({"predecessors": [{"code": "99.9", "type": "FS"}]}, "нет в шаблоне"),
        ({"predecessors": [{"code": "12.3.3", "type": "FS"}]}, "Цикл"),
        ({"rule": {"required": [{"any_of": ["ekskavator"], "min": 1}]}}, "ekskavator"),
        ({"rule": {"required": [{"any_of": [], "min": 1}]}}, "пуста"),
        ({"code": "12.3.2"}, "повторяются"),
        ({"share": 1.5}, "доля"),
        ({"piles": True}, "сваи"),
    ],
)
def test_испорченный_шаблон_не_даёт_стартовать(change, message):
    with pytest.raises(TemplateError, match=message):
        parse_templates(_broken(**change), VOCAB)


def test_неизвестный_тип_объекта_в_шаблоне():
    with pytest.raises(TemplateError, match="SPACEPORT"):
        parse_templates({"SPACEPORT": []}, VOCAB)
