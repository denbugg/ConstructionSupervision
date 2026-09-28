"""Форма правила «этап → техника»: повторы классов и сбор кодов для проверки."""

import pytest
from src.core.stage_rules import StageRuleError, check_rule_shape, rule_codes

PIT = [{"any_of": ["excavator"], "min": 1}, {"any_of": ["dump_truck"], "min": 2}]


def test_правило_котлована_из_контракта_проходит():
    check_rule_shape(PIT, ["bulldozer", "loader"], ["excavator", "dump_truck"])


@pytest.mark.parametrize(
    ("required", "allowed", "signature", "where"),
    [
        ([{"any_of": ["dump_truck", "dump_truck"], "min": 1}], [], [], "Группа 1"),
        (PIT, ["loader", "loader"], [], "allowed"),
        (PIT, [], ["excavator", "excavator"], "signature"),
    ],
)
def test_повтор_класса_это_опечатка(required, allowed, signature, where):
    with pytest.raises(StageRuleError, match=where):
        check_rule_shape(required, allowed, signature)


def test_коды_правила_без_повторов_в_порядке_упоминания():
    codes = rule_codes(PIT, ["bulldozer", "excavator"], ["excavator", "dump_truck"])

    assert codes == ["excavator", "dump_truck", "bulldozer"]
