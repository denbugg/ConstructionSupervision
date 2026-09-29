"""Критический путь: резерв в рабочих днях, связи FS/SS/FF/SF, выходные, праздники, циклы.

Шестидневка (выходной — воскресенье): 19.10.2026 — понедельник, 25.10 — воскресенье.
"""

from datetime import date
from uuid import UUID

import pytest
from src.core.calendar import WorkCalendar
from src.core.cpm import CpmError, CpmStage, Link, order_stages, total_floats

SIX_DAY = WorkCalendar(weekend_days=(7,), holidays=frozenset({date(2026, 11, 4)}))
A, B, C = UUID(int=1), UUID(int=2), UUID(int=3)


def _stage(stage_id, start, end, *links):
    return CpmStage(stage_id, date.fromisoformat(start), date.fromisoformat(end), tuple(links))


def _floats(*stages):
    return {
        k: (v.total_float_days, v.is_critical) for k, v in total_floats(stages, SIX_DAY).items()
    }


def test_цепочка_fs_критическая_а_параллельный_короткий_этап_с_резервом():
    floats = _floats(
        _stage(A, "2026-10-19", "2026-10-21"),
        _stage(B, "2026-10-22", "2026-10-24", Link(A, "FS")),
        _stage(C, "2026-10-22", "2026-10-22", Link(A, "FS")),
    )

    assert floats == {A: (0, True), B: (0, True), C: (2, False)}


def test_воскресенье_между_этапами_не_даёт_резерва():
    floats = _floats(
        _stage(A, "2026-10-22", "2026-10-24"),
        _stage(B, "2026-10-26", "2026-10-26", Link(A, "FS")),
    )

    assert floats[A] == (0, True)


def test_праздник_4_ноября_не_даёт_резерва():
    floats = _floats(
        _stage(A, "2026-11-02", "2026-11-03"),
        _stage(B, "2026-11-05", "2026-11-05", Link(A, "FS")),
    )

    assert floats[A] == (0, True)


def test_лаг_fs_в_рабочих_днях():
    floats = _floats(
        _stage(A, "2026-10-19", "2026-10-20"),
        _stage(B, "2026-10-23", "2026-10-23", Link(A, "FS", 2)),
    )

    assert floats[A] == (0, True)


def test_даты_нарушают_связь_резерв_отрицательный():
    floats = _floats(
        _stage(A, "2026-10-19", "2026-10-21"),
        _stage(B, "2026-10-21", "2026-10-23", Link(A, "FS")),
    )

    assert floats[A] == (-1, True)


def test_ss_с_лагом():
    floats = _floats(
        _stage(A, "2026-10-19", "2026-10-23"),
        _stage(B, "2026-10-20", "2026-10-24", Link(A, "SS", 1)),
    )

    assert floats == {A: (0, True), B: (0, True)}


def test_ff_оставляет_резерв_короткому_предшественнику():
    floats = _floats(
        _stage(A, "2026-10-19", "2026-10-21"),
        _stage(B, "2026-10-19", "2026-10-24", Link(A, "FF")),
    )

    assert floats[A] == (3, False)


def test_sf_конец_последователя_от_начала_предшественника():
    floats = _floats(
        _stage(A, "2026-10-22", "2026-10-22"),
        _stage(B, "2026-10-19", "2026-10-22", Link(A, "SF")),
    )

    assert floats == {A: (0, True), B: (0, True)}


def test_цикл_в_связях_отклоняется():
    with pytest.raises(CpmError, match="Цикл"):
        order_stages(
            [
                _stage(A, "2026-10-19", "2026-10-21", Link(B, "FS")),
                _stage(B, "2026-10-22", "2026-10-24", Link(A, "FS")),
            ]
        )


@pytest.mark.parametrize(
    ("link", "message"),
    [
        (Link(C, "FS"), "нет в графике"),
        (Link(A, "XX"), "тип связи"),
        (Link(B, "FS"), "сам от себя"),
    ],
)
def test_испорченная_связь_отклоняется(link, message):
    with pytest.raises(CpmError, match=message):
        order_stages(
            [_stage(A, "2026-10-19", "2026-10-21"), _stage(B, "2026-10-22", "2026-10-24", link)]
        )


def test_пустой_график():
    assert total_floats([], SIX_DAY) == {}
