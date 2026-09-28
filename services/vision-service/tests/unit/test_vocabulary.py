"""Словарь детектора: классы и промпты из equipment_classes.yaml, версия по содержимому."""

import hashlib

import pytest
import yaml
from src.core.vocabulary import ReferenceDataError, parse_vocabulary

from tests.conftest import CONTRACTS_DIR

CLASSES_FILE = CONTRACTS_DIR / "equipment_classes.yaml"


def test_настоящий_файл_классы_и_промпты_как_в_файле():
    content = CLASSES_FILE.read_bytes()
    raw = yaml.safe_load(content)["equipment_classes"]

    vocab = parse_vocabulary(content)

    assert vocab.codes == tuple(item["code"] for item in raw)
    assert "person" in vocab.codes
    assert vocab.prompts == tuple(p for item in raw for p in item["prompts"])
    for item in raw:
        assert vocab.prompts_of(item["code"]) == tuple(item["prompts"])
    assert vocab.version == hashlib.sha256(content).hexdigest()[:8]


def test_номер_промпта_указывает_на_его_класс():
    vocab = parse_vocabulary(
        b"equipment_classes:\n"
        b"  - {code: excavator, prompts: [excavator, digger]}\n"
        b"  - {code: dump_truck, prompts: [dump truck]}\n"
    )

    assert vocab.prompts == ("excavator", "digger", "dump truck")
    assert vocab.prompt_codes == ("excavator", "excavator", "dump_truck")


def test_новый_класс_в_файле_меняет_словарь_и_версию_без_кода():
    base = b"equipment_classes:\n  - {code: excavator, prompts: [excavator]}\n"
    extended = base + b"  - {code: forklift, prompts: [forklift]}\n"

    before, after = parse_vocabulary(base), parse_vocabulary(extended)

    assert after.codes == ("excavator", "forklift")
    assert after.version != before.version


@pytest.mark.parametrize(
    ("content", "fragment"),
    [
        (b"[1, 2", "YAML"),
        (b"other: []\n", "нет списка"),
        (b"equipment_classes:\n  - {code: Excavator, prompts: [x]}\n", "неверный код"),
        (b"equipment_classes:\n  - {code: excavator, prompts: []}\n", "пустой список"),
        (b"equipment_classes:\n  - {code: excavator}\n", "нет списка prompts"),
        (
            b"equipment_classes:\n  - {code: a, prompts: [x]}\n  - {code: a, prompts: [y]}\n",
            "дважды",
        ),
        (
            b"equipment_classes:\n  - {code: a, prompts: [truck]}\n  - {code: b, prompts: [truck]}\n",
            "есть у a и у b",
        ),
    ],
)
def test_испорченный_файл_не_даёт_стартовать(content, fragment):
    with pytest.raises(ReferenceDataError, match=fragment):
        parse_vocabulary(content)
