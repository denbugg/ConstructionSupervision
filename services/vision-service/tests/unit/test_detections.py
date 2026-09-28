"""Постобработка детектора: нормировка, порог, класс по промпту, склейка дублей."""

import pytest
from src.core.detections import Detection, RawBox, iou, postprocess

CODES = ("excavator", "excavator", "dump_truck", "person")


def run(boxes, width=1000, height=500, min_conf=0.35, iou_threshold=0.5):
    return postprocess(boxes, width, height, CODES, min_conf, iou_threshold)


def test_рамка_нормирована_от_левого_верхнего_угла():
    [det] = run([RawBox(100, 50, 300, 250, 0.9, 2)])

    assert det == Detection("dump_truck", (0.1, 0.1, 0.3, 0.5), 0.9)


def test_рамка_за_краем_кадра_обрезается():
    [det] = run([RawBox(-20, -10, 1100, 600, 0.8, 3)])

    assert det.bbox == (0.0, 0.0, 1.0, 1.0)


def test_вырожденная_рамка_отбрасывается():
    assert run([RawBox(100, 100, 100, 200, 0.9, 0)]) == []
    assert run([RawBox(1200, 100, 1300, 200, 0.9, 0)]) == []


def test_порог_уверенности_включительно():
    boxes = [RawBox(0, 0, 10, 10, 0.35, 0), RawBox(20, 20, 30, 30, 0.3499, 2)]

    assert [d.conf for d in run(boxes)] == [0.35]


def test_два_промпта_одного_класса_на_одной_машине_дают_одну_рамку():
    boxes = [RawBox(100, 100, 300, 300, 0.7, 1), RawBox(105, 100, 300, 305, 0.9, 0)]

    [det] = run(boxes)

    assert det.equipment_class == "excavator"
    assert det.conf == 0.9


def test_одна_машина_рамками_разных_классов_остаётся_одной_самой_уверенной():
    boxes = [RawBox(100, 100, 300, 300, 0.6, 0), RawBox(102, 98, 300, 302, 0.8, 2)]

    [det] = run(boxes)

    assert det.equipment_class == "dump_truck"


def test_человек_у_экскаватора_не_склеивается_с_ним():
    # Рамка человека мала: IoU с машиной низкий, иначе пропал бы D6 по опасной зоне.
    boxes = [RawBox(100, 100, 300, 300, 0.9, 0), RawBox(280, 150, 320, 290, 0.8, 3)]

    assert [d.equipment_class for d in run(boxes)] == ["excavator", "person"]


def test_две_машины_одного_класса_рядом_остаются_двумя():
    boxes = [RawBox(0, 0, 100, 100, 0.9, 0), RawBox(80, 0, 180, 100, 0.8, 0)]

    assert len(run(boxes)) == 2


def test_результат_по_убыванию_уверенности():
    boxes = [RawBox(0, 0, 10, 10, 0.5, 2), RawBox(50, 50, 60, 60, 0.95, 3)]

    assert [d.conf for d in run(boxes)] == [0.95, 0.5]


def test_номер_промпта_вне_словаря_ошибка():
    with pytest.raises(ValueError, match="вне словаря"):
        run([RawBox(0, 0, 10, 10, 0.9, 7)])


def test_iou():
    assert iou((0, 0, 2, 2), (1, 1, 3, 3)) == pytest.approx(1 / 7)
    assert iou((0, 0, 1, 1), (1, 1, 2, 2)) == 0.0
    assert iou((0, 0, 1, 1), (0, 0, 1, 1)) == 1.0
