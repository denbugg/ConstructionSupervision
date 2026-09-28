"""Словарь детектора из packages/contracts/equipment_classes.yaml (ADR-0014).

YOLO-World получает классы текстовыми промптами, поэтому новый класс техники — запись в файле и
перезапуск сервиса, без переобучения и без правки кода. Здесь только разбор и проверка уже
прочитанного файла; испорченный файл — ошибка старта, а не тихий пустой словарь.
"""

import hashlib
import re
from dataclasses import dataclass

import yaml

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class ReferenceDataError(ValueError):
    """Справочный файл испорчен: сервис с ним не стартует."""


@dataclass(frozen=True)
class Vocabulary:
    """Промпты детектора и класс техники, которому принадлежит каждый из них."""

    # Промпты в порядке файла: индекс промпта — это номер класса на выходе детектора.
    prompts: tuple[str, ...]
    prompt_codes: tuple[str, ...]
    codes: tuple[str, ...]
    # Первые 8 символов sha256 файла: по нему видно, на каком словаре получен вывод
    # (interservice.md, раздел 3).
    version: str

    def prompts_of(self, code: str) -> tuple[str, ...]:
        return tuple(p for p, c in zip(self.prompts, self.prompt_codes, strict=True) if c == code)


def parse_vocabulary(content: bytes) -> Vocabulary:
    """Коды и промпты классов; промпт не может принадлежать двум классам сразу."""
    try:
        raw = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ReferenceDataError(f"equipment_classes.yaml: не разбирается как YAML: {exc}") from exc
    items = raw.get("equipment_classes") if isinstance(raw, dict) else None
    if not isinstance(items, list) or not items:
        raise ReferenceDataError("equipment_classes.yaml: нет списка equipment_classes")

    codes: list[str] = []
    prompts: list[str] = []
    prompt_codes: list[str] = []
    for index, item in enumerate(items):
        code, item_prompts = _parse_class(item, index)
        if code in codes:
            raise ReferenceDataError(f"equipment_classes.yaml: класс {code} описан дважды")
        codes.append(code)
        for prompt in item_prompts:
            if prompt in prompts:
                # Один промпт на два класса — детектор не сможет сказать, чья это рамка.
                owner = prompt_codes[prompts.index(prompt)]
                raise ReferenceDataError(
                    f"equipment_classes.yaml: промпт «{prompt}» есть у {owner} и у {code}"
                )
            prompts.append(prompt)
            prompt_codes.append(code)

    version = hashlib.sha256(content).hexdigest()[:8]
    return Vocabulary(tuple(prompts), tuple(prompt_codes), tuple(codes), version)


def _parse_class(item: object, index: int) -> tuple[str, list[str]]:
    if not isinstance(item, dict):
        raise ReferenceDataError(f"equipment_classes.yaml: запись {index} — не словарь")
    code = str(item.get("code") or "")
    if not CODE_PATTERN.match(code):
        raise ReferenceDataError(f"equipment_classes.yaml: запись {index}: неверный код «{code}»")
    raw_prompts = item.get("prompts")
    if not isinstance(raw_prompts, list):
        raise ReferenceDataError(f"equipment_classes.yaml: у {code} нет списка prompts")
    prompts = [str(p).strip() for p in raw_prompts if str(p).strip()]
    if not prompts:
        raise ReferenceDataError(f"equipment_classes.yaml: у {code} пустой список prompts")
    return code, prompts
