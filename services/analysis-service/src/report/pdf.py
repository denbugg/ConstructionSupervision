"""HTML → PDF (WeasyPrint) и ключ файла отчёта в бакете `reports`.

Ключ: `{object_id}/{местные дата и время формирования}-{period_from}_{period_to}.pdf`
(architecture.md, 7.2). Каждое формирование — отдельный файл: отчёт — документ на свой момент,
и повтор того же периода не должен затирать уже отданный. Список отчётов читается из самого
бакета, без таблицы в базе.
"""

import re
from dataclasses import dataclass
from datetime import date, time
from uuid import UUID

from weasyprint import HTML

# Время необязательно: ключи до 27.09 были без него и остаются в бакете.
KEY_PATTERN = re.compile(
    r"^(?P<object_id>[0-9a-f-]{36})/(?P<generated_on>\d{4}-\d{2}-\d{2})"
    r"(?:T(?P<generated_time>\d{6}))?-"
    r"(?P<period_from>\d{4}-\d{2}-\d{2})_(?P<period_to>\d{4}-\d{2}-\d{2})\.pdf$"
)


@dataclass(frozen=True)
class ReportKey:
    object_id: UUID
    generated_on: date
    period_from: date
    period_to: date
    # Местное время формирования с точностью до секунды; None — старый ключ без времени.
    generated_time: time | None = None

    def __str__(self) -> str:
        moment = self.generated_on.isoformat()
        if self.generated_time is not None:
            moment += f"T{self.generated_time:%H%M%S}"
        return f"{self.object_id}/{moment}-{self.period_from}_{self.period_to}.pdf"


def parse_report_key(key: str) -> ReportKey | None:
    """Ключ из бакета → его части; чужой файл в бакете — None, а не ошибка."""
    match = KEY_PATTERN.match(key)
    if match is None:
        return None
    try:
        raw_time = match["generated_time"]
        return ReportKey(
            object_id=UUID(match["object_id"]),
            generated_on=date.fromisoformat(match["generated_on"]),
            period_from=date.fromisoformat(match["period_from"]),
            period_to=date.fromisoformat(match["period_to"]),
            generated_time=(
                time(int(raw_time[:2]), int(raw_time[2:4]), int(raw_time[4:])) if raw_time else None
            ),
        )
    except ValueError:
        return None


def render_pdf(html: str) -> bytes:
    """PDF из готового HTML. Блокирующий вызов: сценарий уводит его в пул потоков.

    Внешних ресурсов у отчёта нет — графики SVG, снимки data URI, шрифт системный, — поэтому
    `base_url` не нужен и WeasyPrint никуда не ходит по сети.
    """
    return HTML(string=html).write_pdf()
