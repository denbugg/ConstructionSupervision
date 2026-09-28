"""SVG-графики отчёта: Гант план-факт и загрузка техники по дням (F10).

Строки SVG встраиваются в HTML, WeasyPrint рисует их векторно. Обозначения те же, что на
экране Ганта интерфейса: полоса — плановое окно, заливка — прогресс цветом статуса,
треугольник — фактический старт, пунктирный хвост — прогноз позже плана.
"""

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from html import escape
from uuid import UUID

from src.core.inputs import Stage
from src.report.model import EquipmentDay, StageSnapshot

WIDTH = 1000
LABEL_WIDTH = 300
ROW = 22
HEADER = 30
BAR = 12

# Цвета совпадают с интерфейсом (apps/web/src/entities/status.ts).
STATUS_FILL = {
    "NOT_STARTED": "#a8a29e",
    "IN_PROGRESS": "#f59e0b",
    "DONE": "#059669",
    "LATE": "#dc2626",
    "AHEAD": "#0284c7",
}
ACCENT = "#c2451a"
MONTHS = ("янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")


def _text(x: float, y: float, value: str, **attrs: str) -> str:
    extra = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f'<text x="{x:.1f}" y="{y:.1f}"{extra}>{escape(value)}</text>'


def _rect(x: float, y: float, w: float, h: float, **attrs: str) -> str:
    extra = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 1):.1f}" height="{h:.1f}"{extra}/>'


def _svg(height: float, body: list[str]) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height:.0f}" '
        f'width="100%" font-family="DejaVu Sans, sans-serif" font-size="10">'
        + "".join(body)
        + "</svg>"
    )


def gantt_svg(stages: Sequence[Stage], facts: Mapping[UUID, StageSnapshot], as_of: date) -> str:
    """Гант: этапы по `seq`, шкала — от начала месяца первой даты до конца месяца последней."""
    days = [d for s in stages for d in (s.plan_start, s.plan_end)] + [as_of]
    days += [f.forecast_end for f in facts.values() if f.forecast_end]
    days += [f.actual_start for f in facts.values() if f.actual_start]
    start = min(days).replace(day=1)
    last = max(days)
    end = (last.replace(day=28) + timedelta(days=4)).replace(day=1)
    scale = (WIDTH - LABEL_WIDTH) / (end - start).days

    def x(day: date) -> float:
        return LABEL_WIDTH + (day - start).days * scale

    height = HEADER + ROW * len(stages) + 16
    body = [_rect(0, 0, WIDTH, height, fill="#ffffff")]
    month = start
    while month < end:
        body.append(
            f'<line x1="{x(month):.1f}" x2="{x(month):.1f}" y1="{HEADER - 12}" '
            f'y2="{height - 16}" stroke="#e7e5e4"/>'
        )
        label = MONTHS[month.month - 1] + (
            f" {month.year}" if month.month == 1 or month == start else ""
        )
        body.append(_text(x(month) + 2, HEADER - 4, label, fill="#5e6763", font_size="8"))
        month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)

    for row, stage in enumerate(stages):
        y = HEADER + row * ROW
        fact = facts.get(stage.id)
        name = f"{stage.code} {stage.name}"
        body.append(
            _text(4, y + 15, name if len(name) <= 48 else name[:47] + "…",
                  fill=ACCENT if stage.is_critical else "#15181a")
        )  # fmt: skip
        left, right = x(stage.plan_start), x(stage.plan_end + timedelta(days=1))
        top = y + (ROW - BAR) / 2
        body.append(
            _rect(left, top, right - left, BAR, rx="2",
                  fill="#f3d3c7" if stage.is_critical else "#e7e5e4",
                  stroke=ACCENT if stage.is_critical else "#a8a29e")
        )  # fmt: skip
        if fact is None:
            continue
        done = min(max(fact.progress, 0.0), 1.0)
        if done > 0:
            body.append(
                _rect(left, top + 3, (right - left) * done, BAR - 6,
                      fill=STATUS_FILL.get(fact.status, "#a8a29e"))
            )  # fmt: skip
        if fact.forecast_end and fact.forecast_end > stage.plan_end:
            tail = x(fact.forecast_end + timedelta(days=1))
            body.append(
                _rect(right, top + 2, tail - right, BAR - 4,
                      fill="#fee2e2", stroke="#dc2626", stroke_dasharray="3 2")
            )  # fmt: skip
            right = tail
        if fact.actual_start:
            ax = x(fact.actual_start)
            body.append(f'<path d="M {ax - 4:.1f} {top - 5:.1f} h 8 l -4 5 z" fill="#15181a"/>')
        if fact.delay_days:
            sign = "+" if fact.delay_days > 0 else "−"
            body.append(
                _text(right + 3, top + BAR - 2, f"{sign}{abs(fact.delay_days)}",
                      fill="#b91c1c" if fact.delay_days > 0 else "#0369a1", font_size="9")
            )  # fmt: skip

    line = x(as_of + timedelta(days=1))
    body.append(
        f'<line x1="{line:.1f}" x2="{line:.1f}" y1="{HEADER - 12}" y2="{height - 14}" '
        'stroke="#15181a" stroke-dasharray="4 3"/>'
    )
    body.append(_text(line, height - 3, f"на момент анализа {as_of:%d.%m.%Y}",
                      text_anchor="middle", font_size="8"))  # fmt: skip
    return _svg(height, body)


def equipment_svg(
    rows: Sequence[EquipmentDay], days: Sequence[date], names: Mapping[str, str]
) -> str:
    """Загрузка техники: строки — классы, столбцы — дни периода, в клетке — максимум единиц
    за сессию; насыщенность — доля сессий дня, когда класс был виден."""
    classes = sorted({r.equipment_class for r in rows}, key=lambda c: names.get(c, c))
    cells = {(r.equipment_class, r.day): r for r in rows}
    busiest = max((r.sessions_seen for r in rows), default=1) or 1
    column = (WIDTH - LABEL_WIDTH) / max(len(days), 1)
    height = HEADER + ROW * len(classes) + 4
    body = [_rect(0, 0, WIDTH, height, fill="#ffffff")]
    for i, day in enumerate(days):
        body.append(
            _text(LABEL_WIDTH + (i + 0.5) * column, HEADER - 8, f"{day:%d.%m}",
                  text_anchor="middle", fill="#5e6763", font_size="8")
        )  # fmt: skip
    for row, code in enumerate(classes):
        y = HEADER + row * ROW
        body.append(_text(4, y + 15, names.get(code, code)))
        for i, day in enumerate(days):
            cell = cells.get((code, day))
            cx = LABEL_WIDTH + i * column
            if cell is None:
                body.append(_rect(cx + 1, y + 1, column - 2, ROW - 2, fill="#f5f5f4"))
                continue
            share = cell.sessions_seen / busiest
            body.append(
                _rect(cx + 1, y + 1, column - 2, ROW - 2,
                      fill=ACCENT, fill_opacity=f"{0.15 + 0.6 * share:.2f}")
            )  # fmt: skip
            body.append(
                _text(cx + column / 2, y + 15, f"{cell.max_count} ({cell.sessions_seen})",
                      text_anchor="middle", font_size="9")
            )  # fmt: skip
    return _svg(height, body)
