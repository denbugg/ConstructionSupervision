"""Текст отклонения из шаблона правила и его `facts` (docs/methodology.md, раздел 12).

Шаблоны живут в данных (deviation_rule), здесь только подстановка. Все числа текста
берутся из `facts`, поэтому текст нельзя разойтись с числами, которые видит оператор.
"""

import string
from dataclasses import dataclass
from datetime import date
from typing import Any

from src.core.predicates import DeviationRule, Finding

# Форматы подстановки после двоеточия: {plan_start:date}, {observed:counts}, …
KNOWN_SPECS = frozenset({"", "date", "counts", "groups", "list"})


class ExplainError(ValueError):
    """Шаблон ссылается на поле, которого нет в facts, или на неизвестный формат."""


class _Formatter(string.Formatter):
    def __init__(self, class_names: dict[str, str]) -> None:
        self._names = class_names

    def _name(self, code: str) -> str:
        return self._names.get(code, code).lower()

    def _group(self, group: dict[str, Any]) -> str:
        names = " или ".join(self._name(c) for c in group["any_of"])
        if "observed" in group:
            return f"{names} — {group['observed']} при норме не меньше {group['min']}"
        return f"{names} — не меньше {group['min']}"

    def format_field(self, value: Any, format_spec: str) -> str:
        if format_spec == "date":
            return date.fromisoformat(value).strftime("%d.%m.%Y")
        if format_spec == "counts":
            return ", ".join(f"{self._name(c)} — {n}" for c, n in value.items())
        if format_spec == "groups":
            return "; ".join(self._group(g) for g in value)
        if format_spec == "list":
            return ", ".join(str(v) for v in value)
        return super().format_field(value, format_spec)


def template_fields(template: str) -> set[tuple[str, str]]:
    """Поля и форматы шаблона — для проверки настроек без подстановки."""
    return {(name, spec or "") for _, name, spec, _ in string.Formatter().parse(template) if name}


def render(template: str, facts: dict[str, Any], class_names: dict[str, str]) -> str:
    unknown = {spec for _, spec in template_fields(template)} - KNOWN_SPECS
    if unknown:
        raise ExplainError(f"Неизвестный формат подстановки: {sorted(unknown)}")
    try:
        return _Formatter(class_names).format(template, **facts)
    except (KeyError, IndexError) as exc:
        raise ExplainError(f"В facts нет поля для шаблона: {exc}") from exc


@dataclass(frozen=True)
class Deviation:
    """Находка, оформленная для ленты: заголовок и текст карточки."""

    finding: Finding
    title: str
    message: str


def templates(rule: DeviationRule, variant: str | None = None) -> tuple[str, str]:
    """Шаблоны заголовка и текста; вариант — другая формулировка того же кода.

    Варианты лежат в `params.variants` правила (например, D3 «возможное опережение»):
    так формулировка остаётся в данных, а не в ветке кода.
    """
    if variant is None:
        return rule.title_template, rule.message_template
    try:
        body = rule.params["variants"][variant]
        return body["title_template"], body["message_template"]
    except (KeyError, TypeError) as exc:
        raise ExplainError(f"{rule.code}: нет варианта текста {variant!r}") from exc


def _check_template(template: str) -> None:
    try:
        specs = {spec for _, spec in template_fields(template)}
    except ValueError as exc:
        raise ExplainError(f"Шаблон не разбирается: {exc}") from exc
    unknown = specs - KNOWN_SPECS
    if unknown:
        raise ExplainError(f"Неизвестный формат подстановки: {sorted(unknown)}")


def validate_rule(rule: DeviationRule, severities: tuple[str, ...]) -> None:
    """Правка настройки правила не должна ломать прогон: пороги и шаблоны проверяются заранее.

    Поля шаблона с `facts` здесь не сверяются — набор `facts` знает только предикат; такой
    промах всплывёт ошибкой прогона `ANALYSIS_INPUT_INVALID`, а не молчаливым текстом.
    """
    for level in (rule.severity, rule.params.get("escalate_to", rule.severity)):
        if level not in severities:
            raise ExplainError(f"Неизвестная серьёзность {level!r}; допустимо: {list(severities)}")
    for name in ("min_sessions", "escalate_after_days", "k_days"):
        value = rule.params.get(name)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise ExplainError(f"Параметр {name} должен быть целым неотрицательным числом")
    if rule.params.get("min_sessions") == 0:
        raise ExplainError("Параметр min_sessions должен быть не меньше 1")
    share = rule.params.get("min_visible_share")
    if share is not None and not (isinstance(share, int | float) and 0 <= share <= 1):
        raise ExplainError("Параметр min_visible_share — доля от 0 до 1")
    variants = rule.params.get("variants") or {}
    if not isinstance(variants, dict):
        raise ExplainError("Параметр variants должен быть словарём вариантов текста")
    for variant in (None, *variants):
        for template in templates(rule, variant):
            _check_template(template)


def describe(finding: Finding, rule: DeviationRule, class_names: dict[str, str]) -> Deviation:
    title, message = templates(rule, finding.facts.get("template_variant"))
    return Deviation(
        finding=finding,
        title=render(title, finding.facts, class_names),
        message=render(message, finding.facts, class_names),
    )
