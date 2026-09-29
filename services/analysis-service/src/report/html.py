"""HTML отчёта и шаблонное резюме из контекста (Jinja2, шаблоны — в `templates/`).

Тексты для человека живут в шаблонах, а не в коде (CONTRIBUTING.md, раздел 3). Резюме по
шаблону — не заглушка на случай без LLM, а полноценный текст по тем же фактам; LLM-вариант
заменяет только его, остальной отчёт не меняется. Резюме стоит сразу за титулом, а его
ссылки на отклонения ведут к строкам таблицы отклонений.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup, escape

from src.report.summary import DEVIATION_REF

TEMPLATES = Path(__file__).parent / "templates"
TEMPLATE = "TEMPLATE"


@dataclass(frozen=True)
class Summary:
    text: str
    # TEMPLATE или LLM — показывается в отчёте и интерфейсе (ADR-0008).
    generated_by: str
    source: str


def link_refs(text: str, ids: Iterable[str]) -> Markup:
    """Ссылки резюме на отклонения (`bac02fc0`) — внутренние ссылки PDF на строку таблицы.

    Текст сначала экранируется целиком, потом ID из таблицы отчёта оборачиваются ссылкой:
    разметку из текста модели так не протащить. ID, которого в таблице нет, остаётся текстом —
    ссылка в никуда хуже её отсутствия.
    """
    known = set(ids)

    def link(match: re.Match[str]) -> str:
        ref = match.group()
        return f'<a href="#dev-{ref}">{ref}</a>' if ref in known else ref

    return Markup(DEVIATION_REF.sub(link, str(escape(text))))


@cache
def _env() -> Environment:
    # StrictUndefined: опечатка в шаблоне — ошибка сборки, а не пустое место в отчёте заказчику.
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(enabled_extensions=("html.j2",), default=False),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["link_refs"] = link_refs
    return env


def template_summary(context: dict[str, Any]) -> Summary:
    text = _env().get_template("summary.ru.txt.j2").render(**context).strip()
    return Summary(text=text, generated_by=TEMPLATE, source="шаблон по фактам отчёта, без LLM")


def render_html(context: dict[str, Any], summary: Summary) -> str:
    return _env().get_template("report.html.j2").render(**context, summary_text=summary)
