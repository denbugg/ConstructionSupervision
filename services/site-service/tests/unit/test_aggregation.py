"""Факт окна: максимум по камерам, неподвижность, видимость, опасные зоны, стадия (раздел 4)."""

from pathlib import Path
from uuid import UUID

import yaml
from src.core.aggregation import (
    CameraZones,
    Frame,
    FrameDetection,
    aggregate_window,
    camera_states,
    frame_usability,
)
from src.core.reference import parse_enums
from src.core.zones import OUTSIDE, ZoneShape, check_polygon

from tests.conftest import SERVICE_ROOT

ENUMS_FILE = SERVICE_ROOT.parents[1] / "packages/contracts/enums.yaml"
ROLES = parse_enums(yaml.safe_load(Path(ENUMS_FILE).read_text(encoding="utf-8"))).zone_roles

LEFT = [[0, 0], [0.5, 0], [0.5, 1], [0, 1]]
RIGHT = [[0.5, 0], [1, 0], [1, 1], [0.5, 1]]
LEFT_BOTTOM = [[0, 0.6], [0.5, 0.6], [0.5, 1], [0, 1]]

NORTH, GATE = UUID(int=1), UUID(int=2)
_ids = iter(range(1000, 10000))


def zone(camera: UUID, zone_type: str, name: str, polygon) -> ZoneShape:
    return ZoneShape(UUID(int=next(_ids)), zone_type, name, check_polygon(polygon))


# Котлован виден только с северной камеры, въезд — с обеих, склад — только с камеры въезда.
CAMERAS = [
    CameraZones(
        NORTH,
        "cam-north",
        (zone(NORTH, "PIT", "Котлован", LEFT), zone(NORTH, "ENTRY_GATE", "Въезд", RIGHT)),
    ),
    CameraZones(
        GATE,
        "cam-gate",
        (zone(GATE, "ENTRY_GATE", "Въезд", LEFT), zone(GATE, "STORAGE", "Склад", RIGHT)),
    ),
]
IN_LEFT = (0.1, 0.2, 0.3, 0.8)
IN_RIGHT = (0.6, 0.2, 0.8, 0.8)


def det(cls: str, bbox, conf=0.9, moved=None) -> FrameDetection:
    return FrameDetection(UUID(int=next(_ids)), cls, bbox, conf, moved)


def frame(camera, *dets, usable=True, reason=None, stage=None, n=None) -> Frame:
    image = UUID(int=n if n is not None else next(_ids))
    return Frame(image, camera, usable, reason, tuple(dets), stage)


def facts(result):
    return {(f.area, f.equipment_class): f for f in result.equipment}


def visibility(result):
    return {v.area: v for v in result.visibility}


def test_одна_машина_с_двух_камер_считается_один_раз():
    result = aggregate_window(
        [frame(NORTH, det("excavator", IN_RIGHT)), frame(GATE, det("excavator", IN_LEFT))],
        CAMERAS,
        ROLES,
    )

    assert facts(result)[("ENTRY_GATE:Въезд", "excavator")].count == 1


def test_максимум_по_камерам_а_не_сумма():
    north = frame(NORTH, det("dump_truck", IN_RIGHT))
    gate = frame(GATE, det("dump_truck", IN_LEFT), det("dump_truck", (0.2, 0.1, 0.4, 0.5)))

    fact = facts(aggregate_window([north, gate], CAMERAS, ROLES))[
        ("ENTRY_GATE:Въезд", "dump_truck")
    ]

    assert fact.count == 2
    assert {e["camera"] for e in fact.evidence} == {"cam-gate"}
    assert len(fact.evidence) == 2


def test_несколько_кадров_камеры_берётся_наибольший():
    first = frame(NORTH, det("dump_truck", IN_LEFT))
    second = frame(NORTH, det("dump_truck", IN_LEFT), det("dump_truck", (0.0, 0.1, 0.2, 0.5)))

    fact = facts(aggregate_window([first, second], CAMERAS, ROLES))[("PIT:Котлован", "dump_truck")]

    assert fact.count == 2
    assert {e["image_id"] for e in fact.evidence} == {str(second.image_id)}


def test_непригодный_кадр_не_входит_в_факт():
    dark = frame(NORTH, det("excavator", IN_LEFT), usable=False, reason="DARK")

    result = aggregate_window([dark], CAMERAS, ROLES)

    assert result.equipment == ()
    assert visibility(result)["PIT:Котлован"].status == "BLIND"
    assert visibility(result)["PIT:Котлован"].reason == "DARK"


def test_видимость_ok_partial_blind():
    # Камера въезда тёмная: котлован OK (его видит только север), въезд PARTIAL, склад BLIND.
    result = aggregate_window(
        [frame(NORTH), frame(GATE, usable=False, reason="DARK")], CAMERAS, ROLES
    )
    vis = visibility(result)

    assert (vis["PIT:Котлован"].status, vis["PIT:Котлован"].reason) == ("OK", None)
    gate = vis["ENTRY_GATE:Въезд"]
    assert (gate.status, gate.cameras_total, gate.cameras_usable, gate.reason) == (
        "PARTIAL",
        2,
        1,
        "DARK",
    )
    assert (vis["STORAGE:Склад"].status, vis["STORAGE:Склад"].reason) == ("BLIND", "DARK")


def test_камера_без_снимков_причина_no_images():
    vis = visibility(aggregate_window([frame(NORTH)], CAMERAS, ROLES))

    assert (vis["STORAGE:Склад"].status, vis["STORAGE:Склад"].reason) == ("BLIND", "NO_IMAGES")


def test_видимость_есть_у_всех_участков_даже_пустых():
    result = aggregate_window([], CAMERAS, ROLES)

    assert set(visibility(result)) == {"PIT:Котлован", "ENTRY_GATE:Въезд", "STORAGE:Склад"}
    assert all(v.status == "BLIND" for v in result.visibility)


def test_самая_частая_причина_непригодности():
    frames = [
        frame(GATE, usable=False, reason="BLURRED"),
        frame(GATE, usable=False, reason="DARK"),
        frame(GATE, usable=False, reason="DARK"),
    ]

    assert visibility(aggregate_window(frames, CAMERAS, ROLES))["STORAGE:Склад"].reason == "DARK"


def test_вне_зон_outside():
    cameras = [CameraZones(NORTH, "cam-north", (zone(NORTH, "PIT", "Котлован", LEFT_BOTTOM),))]

    result = aggregate_window([frame(NORTH, det("truck", (0.6, 0.1, 0.9, 0.3)))], cameras, ROLES)

    assert facts(result)[(OUTSIDE, "truck")].count == 1


def test_опасная_зона_поверх_основной():
    danger = zone(NORTH, "DANGER", "Зона крана", [[0, 0.5], [0.3, 0.5], [0.3, 1], [0, 1]])
    cameras = [CameraZones(NORTH, "cam-north", (*CAMERAS[0].zones, danger))]

    result = facts(aggregate_window([frame(NORTH, det("person", IN_LEFT))], cameras, ROLES))

    assert result[("PIT:Котлован", "person")].count == 1
    assert result[("DANGER:Зона крана", "person")].count == 1


def test_неподвижность_на_камере_давшей_максимум():
    frames = [
        frame(
            NORTH,
            det("excavator", IN_LEFT, moved=False),
            det("excavator", (0.0, 0.1, 0.2, 0.5), moved=True),
        )
    ]

    assert (
        facts(aggregate_window(frames, CAMERAS, ROLES))[("PIT:Котлован", "excavator")].static == 1
    )


def test_неподвижность_null_если_сравнивать_не_с_чем():
    fact = facts(aggregate_window([frame(NORTH, det("excavator", IN_LEFT))], CAMERAS, ROLES))[
        ("PIT:Котлован", "excavator")
    ]

    assert fact.static is None


def test_единица_без_пары_не_считается_неподвижной():
    frames = [
        frame(
            NORTH,
            det("excavator", IN_LEFT, moved=False),
            det("excavator", (0.0, 0.1, 0.2, 0.5), moved=None),
        )
    ]

    fact = facts(aggregate_window(frames, CAMERAS, ROLES))[("PIT:Котлован", "excavator")]

    assert (fact.count, fact.static) == (2, 1)


def test_кадры_неактивной_камеры_не_учитываются():
    stray = frame(UUID(int=99), det("excavator", IN_LEFT))

    assert aggregate_window([stray], CAMERAS, ROLES).equipment == ()


def test_стадия_окна_по_сумме_уверенности_пригодных_кадров():
    frames = [
        frame(NORTH, stage={"PIT": 0.6, "FOUNDATION": 0.4}),
        frame(GATE, stage={"PIT": 0.3, "FOUNDATION": 0.7}),
        frame(GATE, stage={"PIT": 0.9, "FOUNDATION": 0.1}),
        frame(GATE, usable=False, reason="DARK", stage={"PIT": 0.0, "FOUNDATION": 1.0}),
    ]

    stage = aggregate_window(frames, CAMERAS, ROLES).stage

    assert stage.label == "PIT"
    assert stage.scores == {"FOUNDATION": 1.2, "PIT": 1.8}
    assert stage.conf == 0.6


def test_стадии_нет_без_пригодных_кадров():
    frames = [frame(NORTH, usable=False, reason="DARK", stage={"PIT": 1.0})]

    assert aggregate_window(frames, CAMERAS, ROLES).stage is None


def test_результат_не_зависит_от_порядка_кадров():
    frames = [
        frame(NORTH, det("dump_truck", IN_RIGHT), stage={"PIT": 1.0}),
        frame(GATE, det("dump_truck", IN_LEFT), usable=False, reason="BLURRED"),
        frame(GATE, det("excavator", IN_RIGHT)),
    ]

    assert aggregate_window(frames, CAMERAS, ROLES) == aggregate_window(
        list(reversed(frames)), CAMERAS, ROLES
    )


def test_пригодность_кадра():
    assert frame_usability({"brightness": 0.5, "blur": 0.1}, 0.15, 0.6) == (True, None)
    assert frame_usability({"brightness": 0.1, "blur": 0.9}, 0.15, 0.6) == (False, "DARK")
    assert frame_usability({"brightness": 0.5, "blur": 0.61}, 0.15, 0.6) == (False, "BLURRED")
    # Границы включительно пригодны: порог — это «хуже чем».
    assert frame_usability({"brightness": 0.15, "blur": 0.6}, 0.15, 0.6) == (True, None)


def test_камеры_окна_без_снимков_тёмная_и_пригодная():
    dark = frame(GATE, usable=False, reason="DARK", n=5)
    bright, blurred = frame(NORTH, n=7), frame(NORTH, usable=False, reason="BLURRED", n=6)
    idle = CameraZones(UUID(int=3), "cam-yard", ())

    states = {s.code: s for s in camera_states([bright, dark, blurred], [*CAMERAS, idle])}

    assert [s.code for s in camera_states([], [*CAMERAS, idle])] == [
        "cam-gate",
        "cam-north",
        "cam-yard",
    ]
    north, gate, yard = states["cam-north"], states["cam-gate"], states["cam-yard"]
    assert (north.images, north.usable, north.reason) == (2, True, None)
    assert north.image_ids == (UUID(int=6), UUID(int=7))
    assert (gate.images, gate.usable, gate.reason, gate.image_ids) == (
        1,
        False,
        "DARK",
        (UUID(int=5),),
    )
    assert (yard.images, yard.usable, yard.reason, yard.image_ids) == (0, False, "NO_IMAGES", ())
