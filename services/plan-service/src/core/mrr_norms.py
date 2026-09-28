"""Нормы продолжительности строительства по МРР-3.2.81-12 (data/mrr_norms.json; ТЗ, п. 8).

Разбор и проверка файла норм и расчёт сроков периодов по таблице: интерполяция, экстраполяция,
коэффициент сменности, время на сваи. Каждое число берётся из файла, где у него есть ссылка
на пункт и таблицу; текст `basis` называет строки таблицы и коэффициенты — срок любого этапа
проверяется по документу.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

TOTAL = "total"


class NormsError(ValueError):
    """Файл норм испорчен: сервис с ним не стартует."""


class NormsNotAvailable(ValueError):
    """Для объекта нет норм: тип или параметры вне таблицы. График — импортом из файла."""


class GeneratorParamsError(ValueError):
    """Параметры объекта (tep) для генератора не заданы или не имеют смысла."""


@dataclass(frozen=True)
class NormRow:
    row: str
    floors: tuple[int, int]
    area: float
    # Столбец таблицы → месяцы.
    months: Mapping[str, float]


@dataclass(frozen=True)
class Norms:
    table_source: str
    columns: tuple[str, ...]
    titles: Mapping[str, str]
    rows: tuple[NormRow, ...]
    # Фаза этапа (construction_phase) → столбец таблицы.
    phase_columns: Mapping[str, str]
    extrapolation_source: str
    percent_per_percent: float
    max_ratio: float
    min_ratio: float
    shifts_source: str
    shifts_default: str
    shift_coefficients: Mapping[str, float]
    piles_source: str
    piles_days_per_100: float
    # (наибольшее число секций или None — «больше любого», коэффициент совмещения)
    piles_combining: tuple[tuple[int | None, float], ...]

    @property
    def periods(self) -> tuple[str, ...]:
        """Периоды таблицы по порядку, без столбца «общая»."""
        return tuple(c for c in self.columns if c != TOTAL)


@dataclass(frozen=True)
class Params:
    """Параметры объекта для генератора: tep карточки объекта."""

    floors: int
    area: float
    sections: int
    piles: int
    shifts: str


@dataclass(frozen=True)
class PeriodMonths:
    """Сроки периодов по таблице для параметров объекта, с объяснением, откуда они."""

    months: Mapping[str, float]
    basis: str


def parse_norms(raw: Any, phases: Sequence[str]) -> dict[str, Norms]:
    """Нормы по типам объектов; ключи с `_` — пояснения к файлу."""
    if not isinstance(raw, dict):
        raise NormsError("mrr_norms.json: ожидался словарь «тип объекта → нормы»")
    result = {}
    for object_type, item in raw.items():
        if object_type.startswith("_"):
            continue
        where = f"mrr_norms.json, {object_type}"
        try:
            norms = _norms(item)
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise NormsError(f"{where}: испорчено поле {exc}") from exc
        _check(norms, phases, where)
        result[object_type] = norms
    return result


def _norms(item: Mapping[str, Any]) -> Norms:
    table, extra, shifts, piles = (
        item["table"],
        item["extrapolation"],
        item["shifts"],
        item["piles"],
    )
    columns = tuple(str(c) for c in table["columns"])
    rows = tuple(
        NormRow(
            row=str(r["row"]),
            floors=(int(r["floors"][0]), int(r["floors"][1])),
            area=float(r["area"]),
            months=dict(zip(columns, (float(m) for m in r["months"]), strict=True)),
        )
        for r in table["rows"]
    )
    return Norms(
        table_source=_source(table),
        columns=columns,
        titles={str(k): str(v) for k, v in table["titles"].items()},
        rows=rows,
        phase_columns={str(k): str(v) for k, v in item["phase_columns"].items()},
        extrapolation_source=_source(extra),
        percent_per_percent=float(extra["percent_per_percent"]),
        max_ratio=float(extra["max_ratio"]),
        min_ratio=float(extra["min_ratio"]),
        shifts_source=_source(shifts),
        shifts_default=str(shifts["default"]),
        shift_coefficients={str(k): float(v) for k, v in shifts["coefficients"].items()},
        piles_source=_source(piles),
        piles_days_per_100=float(piles["working_days_per_100"]),
        piles_combining=tuple(
            (None if c["max_sections"] is None else int(c["max_sections"]), float(c["coefficient"]))
            for c in piles["combining"]
        ),
    )


def _source(block: Mapping[str, Any]) -> str:
    """Число без ссылки на пункт документа не используется (AGENTS.md, правило 7)."""
    source = str(block.get("source") or "").strip()
    if not source:
        raise ValueError("source: у чисел нет ссылки на пункт и таблицу МРР")
    return source


def _check(norms: Norms, phases: Sequence[str], where: str) -> None:
    if TOTAL not in norms.columns or not norms.periods:
        raise NormsError(f"{where}: в таблице нет столбца «{TOTAL}» или периодов")
    missing_titles = [c for c in norms.columns if c not in norms.titles]
    if missing_titles:
        raise NormsError(f"{where}: нет названий столбцов {missing_titles}")
    for row in norms.rows:
        if row.floors[0] > row.floors[1] or row.area <= 0:
            raise NormsError(f"{where}, строка {row.row}: этажность или площадь не имеют смысла")
        if any(m <= 0 for m in row.months.values()):
            raise NormsError(f"{where}, строка {row.row}: срок должен быть больше нуля")
        # Сумма периодов равна общему сроку: так ловится опечатка при переносе таблицы.
        periods = sum(row.months[c] for c in norms.periods)
        if not math.isclose(periods, row.months[TOTAL], abs_tol=0.051):
            raise NormsError(f"{where}, строка {row.row}: периоды не дают общий срок")
    wrong = {p: c for p, c in norms.phase_columns.items() if p not in phases}
    wrong |= {p: c for p, c in norms.phase_columns.items() if c not in norms.periods}
    if wrong:
        raise NormsError(f"{where}: phase_columns с неизвестной фазой или периодом: {wrong}")
    if norms.shifts_default not in norms.shift_coefficients:
        raise NormsError(f"{where}: сменности по умолчанию нет среди коэффициентов")
    if not norms.piles_combining or norms.piles_combining[-1][0] is not None:
        raise NormsError(f"{where}: последний коэффициент свай — для любого числа секций")


def params_from_tep(tep: Mapping[str, Any], norms: Norms) -> Params:
    """Параметры из `tep`: этажность и площадь обязательны, остальное — по умолчанию МРР."""
    problems = []
    floors = _number(tep, "floors", problems, integer=True, minimum=1)
    area = _number(tep, "total_area", problems, minimum=1)
    sections = _number(tep, "sections", problems, integer=True, minimum=1, default=1)
    piles = _number(tep, "piles", problems, integer=True, minimum=0, default=0)
    shifts = _shifts(tep.get("shifts"), norms)
    if shifts is None:
        allowed = ", ".join(norms.shift_coefficients)
        problems.append(f"shifts — сменность работ, одно из: {allowed}")
    if problems:
        raise GeneratorParamsError("Параметры объекта (tep): " + "; ".join(problems))
    return Params(int(floors), float(area), int(sections), int(piles), shifts)


def _number(
    tep: Mapping[str, Any],
    key: str,
    problems: list[str],
    *,
    integer: bool = False,
    minimum: float,
    default: float | None = None,
) -> float | None:
    value = tep.get(key, default)
    if value is None:
        problems.append(f"{key} не задан")
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        problems.append(f"{key} — число, а не {value!r}")
        return None
    if value < minimum or (integer and not float(value).is_integer()):
        kind = "целое " if integer else ""
        problems.append(f"{key} — {kind}число не меньше {minimum:g}")
        return None
    return value


def _shifts(value: Any, norms: Norms) -> str | None:
    """Сменность как ключ коэффициентов: 2, 2.0 и «2» — одно и то же."""
    if value is None:
        return norms.shifts_default
    if isinstance(value, bool):
        return None
    try:
        key = f"{float(value):g}"
    except (TypeError, ValueError):
        return None
    return key if key in norms.shift_coefficients else None


def period_months(norms: Norms, floors: int, area: float) -> PeriodMonths:
    """Сроки периодов таблицы для этажности и площади (п. 4.9, п. 5.1.3–5.1.4).

    Площадь между строками одной группы этажности — линейная интерполяция, за краями —
    экстраполяция: 0,3 % срока на 1 % площади, не дальше пределов п. 5.1.4. Этажность между
    группами — интерполяция между ними. Этажность вне таблицы — нормы нет: п. 4.9 задаёт
    экстраполяцию только для показателя мощности, а не для этажности.
    """
    groups: dict[tuple[int, int], list[NormRow]] = {}
    for row in norms.rows:
        groups.setdefault(row.floors, []).append(row)
    ranges = sorted(groups)
    inside = [r for r in ranges if r[0] <= floors <= r[1]]
    if inside:
        return _in_group(norms, groups[inside[0]], area)
    lower = [r for r in ranges if r[1] < floors]
    upper = [r for r in ranges if r[0] > floors]
    if not lower or not upper:
        first, last = ranges[0][0], ranges[-1][1]
        raise NormsNotAvailable(
            f"Этажность {floors} вне таблицы МРР ({first}–{last} этажей): "
            "срок определяется ПОС, график — импортом"
        )
    lo, hi = lower[-1], upper[0]
    below, above = _in_group(norms, groups[lo], area), _in_group(norms, groups[hi], area)
    t = (floors - lo[1]) / (hi[0] - lo[1])
    months = {c: below.months[c] + t * (above.months[c] - below.months[c]) for c in norms.columns}
    basis = (
        f"этажность {floors} между группами {_floors(lo)} и {_floors(hi)} эт. — интерполяция "
        f"({below.basis}; {above.basis})"
    )
    return PeriodMonths(months, basis)


def _in_group(norms: Norms, rows: list[NormRow], area: float) -> PeriodMonths:
    rows = sorted(rows, key=lambda r: r.area)
    group = f"{_floors(rows[0].floors)} эт."
    for row in rows:
        if math.isclose(row.area, area):
            return PeriodMonths(row.months, f"стр. {row.row} ({group}, {row.area:g} м²)")
    first, last = rows[0], rows[-1]
    if first.area < area < last.area:
        lo = max((r for r in rows if r.area < area), key=lambda r: r.area)
        hi = min((r for r in rows if r.area > area), key=lambda r: r.area)
        t = (area - lo.area) / (hi.area - lo.area)
        months = {c: lo.months[c] + t * (hi.months[c] - lo.months[c]) for c in norms.columns}
        return PeriodMonths(
            months, f"стр. {lo.row}–{hi.row} ({group}), интерполяция на {area:g} м²"
        )
    edge = last if area > last.area else first
    ratio = area / edge.area
    if not norms.min_ratio <= ratio <= norms.max_ratio:
        raise NormsNotAvailable(
            f"Площадь {area:g} м² дальше пределов экстраполяции от стр. {edge.row} "
            f"({edge.area:g} м², ×{norms.min_ratio:g}…×{norms.max_ratio:g}): срок определяется ТЭО"
        )
    factor = 1 + norms.percent_per_percent * (ratio - 1)
    months = {c: m * factor for c, m in edge.months.items()}
    change = f"{(ratio - 1) * 100:+.1f} % площади → {(factor - 1) * 100:+.1f} % срока"
    return PeriodMonths(months, f"стр. {edge.row} ({group}), экстраполяция: {change}")


def _floors(floors: tuple[int, int]) -> str:
    return str(floors[0]) if floors[0] == floors[1] else f"{floors[0]}–{floors[1]}"


def piles_working_days(norms: Norms, piles: int, sections: int) -> tuple[int, str]:
    """Время на сваи в рабочих днях (п. 5.1.6), с округлением вверх до целого дня."""
    coefficient = next(
        k for limit, k in norms.piles_combining if limit is None or sections <= limit
    )
    days = math.ceil(norms.piles_days_per_100 * piles / 100 * coefficient - 1e-9)
    rate, share = (f"{v:g}".replace(".", ",") for v in (norms.piles_days_per_100, coefficient))
    basis = (
        f"{piles} свай × {rate} раб. дн. на 100 свай × {share} (секций: {sections}) "
        f"= {days} раб. дн."
    )
    return days, basis
