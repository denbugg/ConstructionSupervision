"""Критический путь графика: полный резерв каждого этапа в рабочих днях (ТЗ, п. 8).

Даты этапов не пересчитываются: график приходит из импорта или генератора, и его даты — это
план, а не результат расчёта. По ним считается только обратный проход: насколько поздно
этап может закончиться, не сдвигая конец объекта. Резерв 0 — этап на критическом пути,
отрицательный резерв — даты уже нарушают связи графика.

Семантика связей совпадает с переносом сдвига в analysis-service (methodology.md, 10.6):
обе даты этапа включительно, лаг — в рабочих днях, FS с лагом 0 — следующий рабочий день.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from graphlib import CycleError, TopologicalSorter
from uuid import UUID

from src.core.calendar import WorkCalendar, count_working_days

LINK_TYPES = ("FS", "SS", "FF", "SF")


class CpmError(ValueError):
    """Связи графика противоречивы: цикл, ссылка на чужой этап, неизвестный тип связи."""


@dataclass(frozen=True)
class Link:
    stage_id: UUID
    type: str
    lag_days: int = 0


@dataclass(frozen=True)
class CpmStage:
    id: UUID
    start: date
    end: date
    predecessors: tuple[Link, ...] = ()


@dataclass(frozen=True)
class Float:
    total_float_days: int
    is_critical: bool


def order_stages(stages: Sequence[CpmStage]) -> list[CpmStage]:
    """Этапы в порядке связей: предшественник раньше последователя."""
    by_id = {s.id: s for s in stages}
    for stage in stages:
        for link in stage.predecessors:
            if link.stage_id not in by_id:
                raise CpmError(f"Связь ссылается на этап {link.stage_id}, которого нет в графике")
            if link.type not in LINK_TYPES:
                raise CpmError(f"Неизвестный тип связи {link.type!r}; допустимо: {LINK_TYPES}")
            if link.stage_id == stage.id:
                raise CpmError("Этап не может зависеть сам от себя")
    graph = {s.id: {link.stage_id for link in s.predecessors} for s in stages}
    try:
        order = list(TopologicalSorter(graph).static_order())
    except CycleError as exc:
        raise CpmError(f"Цикл в связях этапов: {exc.args[1]}") from exc
    return [by_id[i] for i in order]


def total_floats(stages: Sequence[CpmStage], calendar: WorkCalendar) -> dict[UUID, Float]:
    """Полный резерв этапов обратным проходом от самой поздней даты окончания графика.

    Даты переводятся в номера рабочих дней, и дальше вся арифметика целочисленная:
    выходные и праздники не участвуют в расчёте резерва.
    """
    if not stages:
        return {}
    ordered = order_stages(stages)
    base = min(s.start for s in stages)

    def index(day: date) -> int:
        # Номер рабочего дня: сколько рабочих дней прошло до `day`, не считая его.
        return count_working_days(calendar, base, day)

    early_start = {s.id: index(s.start) for s in stages}
    early_finish = {s.id: index(s.end + timedelta(days=1)) - 1 for s in stages}
    duration = {i: early_finish[i] - early_start[i] + 1 for i in early_start}
    project_finish = max(early_finish.values())

    late_finish: dict[UUID, int] = {}
    successors = _successors(stages)
    for stage in reversed(ordered):
        limits = [project_finish]
        for succ_id, link in successors.get(stage.id, ()):
            limits.append(
                _latest_finish(link, duration[stage.id], late_finish[succ_id], duration[succ_id])
            )
        late_finish[stage.id] = min(limits)

    result = {}
    for stage in stages:
        slack = late_finish[stage.id] - early_finish[stage.id]
        result[stage.id] = Float(total_float_days=slack, is_critical=slack <= 0)
    return result


def _successors(stages: Iterable[CpmStage]) -> dict[UUID, list[tuple[UUID, Link]]]:
    successors: dict[UUID, list[tuple[UUID, Link]]] = {}
    for stage in stages:
        for link in stage.predecessors:
            successors.setdefault(link.stage_id, []).append((stage.id, link))
    return successors


def _latest_finish(link: Link, pred_duration: int, succ_finish: int, succ_duration: int) -> int:
    """Самый поздний конец предшественника, при котором последователь не сдвигается."""
    succ_start = succ_finish - succ_duration + 1
    if link.type == "FS":  # последователь начинается на следующий рабочий день после конца
        return succ_start - 1 - link.lag_days
    if link.type == "SS":  # начало не раньше начала предшественника + лаг
        return succ_start - link.lag_days + pred_duration - 1
    if link.type == "FF":  # конец не раньше конца предшественника + лаг
        return succ_finish - link.lag_days
    return succ_finish - link.lag_days + pred_duration - 1  # SF: конец не раньше начала + лаг
