"""Резюме нейросетью по фактам отчёта: контекст для модели и проверка её текста (F12).

LLM не считает (ADR-0008): она получает только JSON из уже собранного контекста отчёта и
пишет по нему текст. Проверка — чистая функция: каждое число текста должно встречаться в
контексте, каждая ссылка на отклонение — быть его ID. Не прошло — текст отбрасывается, и
отчёт получает шаблонное резюме. Проверка — эвристика по числовым токенам: число,
записанное словами, она не поймает, а корректное округление — отбросит; второе безопасно.
"""

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

# Число — цифры с точками и запятыми внутри: «0.98», «22.10.2026», «1,5».
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# Ссылка на отклонение — первые восемь знаков его ID, как в таблице отчёта.
DEVIATION_REF = re.compile(r"\b[0-9a-f]{8}\b")
# Сколько отклонений отдавать модели: остальные — в таблице отчёта. Маленькой локальной
# модели длинный контекст только мешает.
MAX_DEVIATIONS = 12


def llm_context(context: Mapping[str, Any]) -> dict[str, Any]:
    """JSON для модели из контекста отчёта: те же строки и числа, что увидит читатель."""
    title, summary, counts = context["title"], context["summary"], context["counts"]
    return {
        "объект": title["object"],
        "период": title["period"],
        "момент_анализа": title["as_of"],
        "статус": title["status"],
        "отклонение_от_графика_раб_дн": title["delay"],
        "spi": title["spi"],
        "уверенность": title["confidence"],
        "прогресс_по_фазам": summary["phases"],
        "этапы_в_зоне_риска": summary["at_risk"],
        "отклонения": {
            "всего": counts["deviations"],
            "открыто": counts["open"],
            "по_кодам": dict(counts["by_code"]),
            "главные": [
                {
                    "id": d["id"],
                    "код": d["code"],
                    "серьёзность": d["severity"],
                    "этап": d["stage"],
                    "участок": d["area"],
                    "что": d["title"],
                    "подробно": d["message"],
                    "когда": d["period"],
                    "статус": d["status"],
                }
                for d in context["deviations"][:MAX_DEVIATIONS]
            ],
        },
        "ограничения": context["limitations"],
    }


def context_json(llm_ctx: Mapping[str, Any]) -> str:
    return json.dumps(llm_ctx, ensure_ascii=False, indent=1)


def clean_text(text: str) -> str:
    """Разметку Markdown модели — в простой текст: в PDF резюме выводится как есть."""
    lines = []
    for line in text.replace("\r\n", "\n").split("\n"):
        line = re.sub(r"^\s*#+\s*", "", line)
        line = re.sub(r"^\s*[*-]\s+", "• ", line)
        lines.append(line.replace("**", "").replace("__", "").rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def check_summary(text: str, llm_ctx: Mapping[str, Any]) -> list[str]:
    """Почему текст модели нельзя показать; пустой список — можно."""
    if not text.strip():
        return ["пустой ответ"]
    source = context_json(llm_ctx)
    ids = {d["id"] for d in llm_ctx["отклонения"]["главные"]}
    problems = []

    refs = set(DEVIATION_REF.findall(text))
    unknown = sorted(r for r in refs if r not in ids and not r.isdigit())
    if unknown:
        problems.append(f"ссылки на неизвестные отклонения: {', '.join(unknown)}")
    if ids and not refs & ids:
        problems.append("нет ни одной ссылки на ID отклонения")

    # ID отклонений содержат цифры: из проверки чисел они убираются целиком. Восемь цифр
    # подряд без букв — это число, а не ID, и проверяется как число.
    bare = DEVIATION_REF.sub(
        lambda m: " " if m.group() in ids or not m.group().isdigit() else m.group(), text
    )
    allowed = _allowed_numbers(NUMBER.findall(source))
    invented = sorted({n for n in NUMBER.findall(bare) if _norm(n) not in allowed})
    if invented:
        problems.append(f"числа не из фактов: {', '.join(invented)}")
    return problems


def _allowed_numbers(tokens: Iterable[str]) -> set[str]:
    """Числа контекста и их части: дата «22.10.2026» разрешает и «22.10», и «2026»."""
    allowed = set()
    for token in tokens:
        parts = _norm(token).split(".")
        for start in range(len(parts)):
            for end in range(start + 1, len(parts) + 1):
                allowed.add(".".join(parts[start:end]))
    return allowed


def _norm(token: str) -> str:
    """«0,98» = «0.98», «09» = «9»: разное написание одного числа — не выдумка."""
    return ".".join(p.lstrip("0") or "0" for p in token.replace(",", ".").split("."))
