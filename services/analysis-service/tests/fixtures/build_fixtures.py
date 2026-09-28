"""Сборка фикстур «фактов за период» для демо-дней (docs/runbook.md, раздел 6).

JSON-файлы рядом — результат этого скрипта. Сценарий читается здесь, в коде, а не
в тысяче строк JSON; поменяли сценарий — пересоберите фикстуры:

    PYTHONPATH=. python -m tests.fixtures.build_fixtures

Площадка — как в примере data/README.md: обзорная камера `cam-north` видит котлован
и въезд, камера `cam-gate` — въезд и склад. Окна — 06:00–12:00 UTC (09:00–15:00 МСК),
внутри рабочих часов календаря; все дни — будни.
"""

import json
from datetime import date, datetime, time, timedelta

from src.core.inputs import AreaFact, CameraState, Facts
from tests.factories import (
    FIXTURES,
    make_area,
    make_camera,
    make_equipment,
    make_facts,
    make_session,
    windows,
)

PIT = "PIT:Котлован"
GATE = "ENTRY_GATE:Въезд"
STORAGE = "STORAGE:Склад"
FIRST_WINDOW = time(6, 0)
SESSIONS_PER_DAY = 12
# Самосвалы приезжают раз в 2 часа — каждое четвёртое окно, по два за раз.
TRUCK_EVERY = 4


def _cameras(at: datetime, gate_dark: bool) -> tuple[CameraState, ...]:
    return (
        make_camera("cam-north", at),
        make_camera("cam-gate", at, reason="DARK" if gate_dark else None),
    )


def _pit(at: datetime, i: int, *, trucks: bool, pump: bool = False) -> AreaFact:
    """Котлован: экскаватор копает; самосвалы — по расписанию; бетононасос — по сценарию."""
    equipment = [make_equipment("excavator", static=0, at=at)]
    if trucks and i % TRUCK_EVERY == 0:
        equipment.append(make_equipment("dump_truck", 2, static=0, at=at))
    if pump:
        equipment.append(make_equipment("concrete_pump", static=0, at=at))
    return make_area(PIT, *equipment)


def _gate(at: datetime, i: int, *, idle_excavator: bool, gate_dark: bool) -> AreaFact:
    """Въезд размечен на обеих камерах: тёмная cam-gate делает его PARTIAL, а не BLIND."""
    equipment = []
    if idle_excavator:
        # В первом окне дня экскаватор только что приехал с котлована: сдвинулся.
        equipment.append(make_equipment("excavator", static=0 if i == 0 else 1, at=at))
    if gate_dark:
        return make_area(GATE, *equipment, cameras_total=2, cameras_usable=1, reason="DARK")
    return make_area(GATE, *equipment, cameras_total=2)


def _storage(gate_dark: bool) -> AreaFact:
    """Склад виден только с cam-gate."""
    if gate_dark:
        return make_area(STORAGE, cameras_usable=0, reason="DARK")
    return make_area(STORAGE)


def build_day(day: date, *, trucks: bool, pump_from: int | None, gate_problem: bool) -> Facts:
    sessions = []
    for i, at in enumerate(windows(day, FIRST_WINDOW, SESSIONS_PER_DAY)):
        pump = pump_from is not None and i >= pump_from
        sessions.append(
            make_session(
                at,
                _pit(at, i, trucks=trucks, pump=pump),
                _gate(at, i, idle_excavator=gate_problem, gate_dark=gate_problem),
                _storage(gate_problem),
                cameras=_cameras(at, gate_problem),
            )
        )
    start = datetime.combine(day, time(0), tzinfo=sessions[0].window_start.tzinfo)
    return make_facts(*sessions, period_from=start, period_to=start + timedelta(days=1))


DAYS = {
    # Нормальный день: комплект котлована полный, самосвалы в окне 2 часа есть → без D2.
    "facts_normal_day.json": build_day(
        date(2026, 10, 19), trucks=True, pump_from=None, gate_problem=False
    ),
    # День 1: экскаватор есть, самосвалов нет весь день → D2.
    "facts_day1.json": build_day(
        date(2026, 10, 20), trucks=False, pump_from=None, gate_problem=False
    ),
    # День 2: с 10:00 UTC в котловане бетононасос — техника будущего этапа → D3.
    "facts_day2.json": build_day(date(2026, 10, 21), trucks=True, pump_from=8, gate_problem=False),
    # День 3: второй экскаватор неподвижно на въезде (его видит cam-north) → D4;
    # cam-gate тёмная весь день → склад BLIND → D10, въезд PARTIAL.
    "facts_day3.json": build_day(
        date(2026, 10, 22), trucks=True, pump_from=None, gate_problem=True
    ),
}


def main() -> None:
    for name, facts in DAYS.items():
        payload = facts.model_dump(mode="json", by_alias=True)
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        (FIXTURES / name).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
