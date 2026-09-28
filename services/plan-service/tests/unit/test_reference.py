"""Справочные файлы контрактов: разбор, проверка, коды классов в правилах (ADR-0014)."""

import copy

import pytest
import yaml
from src.core.reference import (
    ReferenceDataError,
    parse_enums,
    parse_equipment_classes,
    parse_zone_roles,
    unknown_codes,
)

from tests.conftest import CONTRACTS_DIR

RAW_ENUMS = yaml.safe_load((CONTRACTS_DIR / "enums.yaml").read_text(encoding="utf-8"))
RAW_CLASSES = yaml.safe_load((CONTRACTS_DIR / "equipment_classes.yaml").read_text(encoding="utf-8"))
GROUPS = parse_enums(RAW_ENUMS)["equipment_group"]


def _classes_with(**change):
    raw = copy.deepcopy(RAW_CLASSES)
    raw["equipment_classes"][0].update(change)
    return raw


def test_настоящие_файлы_разбираются():
    classes = parse_equipment_classes(RAW_CLASSES, GROUPS)

    assert [c.code for c in classes] == [c["code"] for c in RAW_CLASSES["equipment_classes"]]
    excavator, dump_truck = classes[0], classes[1]
    assert (excavator.name_ru, excavator.transient) == ("Экскаватор", False)
    assert dump_truck.transient is True and "dump truck" in dump_truck.prompts
    in_place = {c.code for c in classes if c.works_in_place}
    assert in_place == {"tower_crane", "truck_crane", "concrete_pump"}


def test_списки_enums_без_словарей():
    values = parse_enums(RAW_ENUMS)

    assert "PIT" in values["zone_type"]
    assert "zone_type_role" not in values


@pytest.mark.parametrize(
    "change",
    [
        {"code": "Excavator"},
        {"code": "dump_truck"},  # повтор кода второй записи
        {"group": "SPACESHIPS"},
        {"transient": "yes"},
        {"works_in_place": "yes"},
        {"name_ru": "  "},
    ],
)
def test_испорченная_запись_класса_это_ошибка_старта(change):
    with pytest.raises(ReferenceDataError):
        parse_equipment_classes(_classes_with(**change), GROUPS)


def test_запись_без_обязательного_поля_это_ошибка():
    raw = copy.deepcopy(RAW_CLASSES)
    del raw["equipment_classes"][0]["transient"]

    with pytest.raises(ReferenceDataError, match="запись 1"):
        parse_equipment_classes(raw, GROUPS)


@pytest.mark.parametrize("raw", [{}, {"equipment_classes": []}, None])
def test_пустой_справочник_классов_это_ошибка(raw):
    with pytest.raises(ReferenceDataError):
        parse_equipment_classes(raw, GROUPS)


def test_без_нужного_перечисления_enums_не_принимается():
    raw = {k: v for k, v in RAW_ENUMS.items() if k != "zone_type"}

    with pytest.raises(ReferenceDataError, match="zone_type"):
        parse_enums(raw)


def test_роли_типов_зон_читаются_для_каждого_типа():
    zone_types = parse_enums(RAW_ENUMS)["zone_type"]

    roles = parse_zone_roles(RAW_ENUMS, zone_types)

    assert set(roles) == set(zone_types)
    assert roles["PIT"] == "WORK" and roles["ENTRY_GATE"] == "SERVICE"


def test_тип_зоны_без_роли_это_ошибка_старта():
    raw = copy.deepcopy(RAW_ENUMS)
    del raw["zone_type_role"]["STORAGE"]

    with pytest.raises(ReferenceDataError, match="STORAGE"):
        parse_zone_roles(raw, parse_enums(raw)["zone_type"])


def test_неизвестные_коды_по_порядку_и_без_повторов():
    classes = parse_equipment_classes(RAW_CLASSES, GROUPS)

    assert unknown_codes(
        ["excavator", "ekskavator", "dump_truck", "ekskavator", "crane"], classes
    ) == [
        "ekskavator",
        "crane",
    ]
    assert unknown_codes(["excavator", "person"], classes) == []


def test_проверка_кодов_в_правиле_называет_неизвестные():
    from src.services.equipment_classes import UnknownEquipmentClass, check_equipment_codes

    check_equipment_codes(["excavator", "dump_truck"])
    with pytest.raises(UnknownEquipmentClass) as error:
        check_equipment_codes(["excavator", "ekskavator"])

    assert error.value.code == "UNKNOWN_EQUIPMENT_CLASS"
    assert error.value.details["unknown"] == ["ekskavator"]
