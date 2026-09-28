"""Чтение enums.yaml: роли типов зон и порядок стадий берутся из контракта."""

import pytest
from src.core.enums import EnumsError, parse_enums


def test_роли_типов_зон_прочитаны_из_контракта(enums):
    assert enums.role("PIT") == "WORK"
    assert enums.role("ENTRY_GATE") == "SERVICE"
    assert enums.role("DANGER") == "SAFETY"


def test_у_каждого_типа_зоны_есть_роль(enums):
    assert set(enums.values["zone_type"]) == set(enums.zone_type_role)


def test_стадии_сравниваются_по_порядку_строительства(enums):
    assert enums.stage_index("PIT") < enums.stage_index("FOUNDATION") < enums.stage_index("FRAME")


def test_неизвестный_тип_зоны_это_ошибка_данных(enums):
    with pytest.raises(EnumsError):
        enums.role("ROOF")


def test_тип_зоны_без_роли_не_проходит_разбор():
    raw = {"zone_type": ["PIT", "ROOF"], "zone_type_role": {"PIT": "WORK"}, "stage_label": ["PIT"]}

    with pytest.raises(EnumsError, match="ROOF"):
        parse_enums(raw)


def test_без_ролей_зон_разбор_не_проходит():
    with pytest.raises(EnumsError):
        parse_enums({"stage_label": ["PIT"]})
