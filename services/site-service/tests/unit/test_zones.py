"""Привязка к зоне: точка контакта, граница, перекрытие, опасная зона поверх, вне зон."""

from pathlib import Path
from uuid import UUID

import pytest
import yaml
from src.core.reference import ReferenceDataError, parse_enums
from src.core.zones import (
    OUTSIDE,
    PolygonError,
    ZoneDraft,
    ZoneImportError,
    ZoneShape,
    anchor_point,
    area_key,
    check_polygon,
    place,
    sync_zones,
)

from tests.conftest import SERVICE_ROOT

ENUMS_FILE = SERVICE_ROOT.parents[1] / "packages/contracts/enums.yaml"
RAW_ENUMS = yaml.safe_load(Path(ENUMS_FILE).read_text(encoding="utf-8"))
ROLES = parse_enums(RAW_ENUMS).zone_roles


def _zone(n: int, zone_type: str, name: str, polygon) -> ZoneShape:
    return ZoneShape(UUID(int=n), zone_type, name, check_polygon(polygon))


# Пятно застройки на половину кадра, котлован внутри него, опасная зона крана поверх котлована.
FOOTPRINT = _zone(
    1, "BUILDING_FOOTPRINT", "Пятно застройки", [[0, 0.4], [0.6, 0.4], [0.6, 1], [0, 1]]
)
PIT = _zone(2, "PIT", "Котлован", [[0.1, 0.5], [0.4, 0.5], [0.4, 0.9], [0.1, 0.9]])
DANGER = _zone(3, "DANGER", "Зона крана", [[0.3, 0.6], [0.5, 0.6], [0.5, 0.8], [0.3, 0.8]])
GATE = _zone(4, "ENTRY_GATE", "Въезд", [[0.7, 0.5], [1, 0.5], [1, 1], [0.7, 1]])
ZONES = [FOOTPRINT, PIT, DANGER, GATE]


def _bbox_at(x: float, y: float) -> list[float]:
    """Рамка шириной 0,1 и высотой 0,2 с серединой нижней стороны в (x, y)."""
    return [x - 0.05, y - 0.2, x + 0.05, y]


def test_точка_контакта_середина_нижней_стороны():
    assert anchor_point([0.2, 0.1, 0.4, 0.7]) == (pytest.approx(0.3), 0.7)


def test_высокая_техника_привязывается_по_низу_а_не_по_центру():
    # Центр рамки крана (0,25; 0,3) — выше котлована, а опора — в котловане.
    crane = [0.2, 0.0, 0.3, 0.6]

    assert place(crane, ZONES, ROLES).zone == PIT


def test_меньшая_зона_главнее_при_перекрытии():
    in_pit = place(_bbox_at(0.2, 0.7), ZONES, ROLES)
    in_footprint_only = place(_bbox_at(0.5, 0.45), ZONES, ROLES)

    assert (in_pit.zone, in_pit.area) == (PIT, "PIT:Котлован")
    assert in_footprint_only.zone == FOOTPRINT


def test_опасная_зона_накладывается_поверх_рабочей():
    placement = place(_bbox_at(0.35, 0.7), ZONES, ROLES)

    assert placement.zone == PIT  # опасная зона не отнимает детекцию у котлована
    assert placement.danger == (DANGER,)


def test_только_опасная_зона_это_вне_участков():
    only_danger = [DANGER]

    placement = place(_bbox_at(0.4, 0.7), only_danger, ROLES)

    assert (placement.zone, placement.area, placement.danger) == (None, OUTSIDE, (DANGER,))


def test_вне_всех_зон():
    placement = place(_bbox_at(0.65, 0.2), ZONES, ROLES)

    assert (placement.area, placement.danger) == (OUTSIDE, ())


def test_точка_на_границе_считается_внутри():
    on_edge = place(_bbox_at(0.85, 0.5), ZONES, ROLES)  # верхняя сторона въезда
    on_vertex = place(_bbox_at(1.0, 1.0), ZONES, ROLES)  # угол кадра — вершина въезда

    assert on_edge.zone == on_vertex.zone == GATE


def test_равные_зоны_выбираются_детерминированно():
    twin = _zone(9, "PIT", "Котлован-2", PIT.polygon)

    first = place(_bbox_at(0.2, 0.7), [twin, PIT], ROLES).zone
    second = place(_bbox_at(0.2, 0.7), [PIT, twin], ROLES).zone

    assert first == second == PIT


def test_ключ_участка_из_типа_и_названия():
    assert area_key("ENTRY_GATE", " Въезд ") == "ENTRY_GATE:Въезд"


def test_замыкающая_вершина_убирается():
    assert len(check_polygon([[0, 0], [1, 0], [1, 1], [0, 0]])) == 3


@pytest.mark.parametrize(
    ("polygon", "message"),
    [
        ([[0, 0], [1, 1]], "меньше 3"),
        ([[0, 0], [1920, 0], [1920, 1080]], "пиксели"),
        ([[0, 0], [0.5, 0.5], [1, 1]], "вырожден"),
        ([[0, 0], [1, 1], [1, 0], [0, 1]], "пересекает"),  # «бабочка»
        ([[0, "a"], [1, 0], [1, 1]], "числами"),
        (None, "числами"),
    ],
)
def test_бессмысленный_полигон_отклоняется(polygon, message):
    with pytest.raises(PolygonError, match=message):
        check_polygon(polygon)


def test_сверка_разметки_по_подписи_участка():
    moved_pit = ZoneDraft("PIT", "Котлован", check_polygon([[0.1, 0.5], [0.45, 0.5], [0.4, 0.9]]))
    same_gate = ZoneDraft("ENTRY_GATE", "Въезд", GATE.polygon)
    storage = ZoneDraft("STORAGE", "Склад", check_polygon([[0.7, 0.1], [0.9, 0.1], [0.9, 0.3]]))

    sync = sync_zones([PIT, GATE, DANGER], [moved_pit, same_gate, storage])

    assert sync.create == (storage,)
    assert sync.update == ((PIT.id, moved_pit.polygon),)
    assert sync.deactivate == (DANGER.id,)  # в файле её нет — деактивируется, а не удаляется
    assert sync.unchanged == 1


def test_повторная_сверка_того_же_файла_ничего_не_меняет():
    drafts = [ZoneDraft(z.zone_type, z.name, z.polygon) for z in ZONES]

    sync = sync_zones(ZONES, drafts)

    assert (sync.create, sync.update, sync.deactivate, sync.unchanged) == ((), (), (), 4)


def test_участок_дважды_на_одной_камере_ошибка():
    twice = [ZoneDraft("PIT", "Котлован", PIT.polygon)] * 2

    with pytest.raises(ZoneImportError, match="PIT:Котлован"):
        sync_zones([], twice)


def test_названия_типов_зон_из_enums():
    assert parse_enums(RAW_ENUMS).zone_names["PIT"] == "Котлован"


def test_роли_типов_зон_из_enums():
    enums = parse_enums(RAW_ENUMS)

    assert "DANGER" in enums.zone_types
    assert (ROLES["DANGER"], ROLES["PIT"], ROLES["ENTRY_GATE"]) == ("SAFETY", "WORK", "SERVICE")


def test_тип_зоны_без_роли_не_даёт_стартовать():
    broken = dict(RAW_ENUMS) | {"zone_type_role": {"PIT": "WORK"}}

    with pytest.raises(ReferenceDataError, match="нет роли"):
        parse_enums(broken)
