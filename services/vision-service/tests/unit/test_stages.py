"""Стадия по фото: промпты сверены с enums.yaml, метка — по softmax логитов."""

import pytest
import yaml
from src.core.stages import parse_stage_labels, parse_stage_prompts, stage_from_logits
from src.core.vocabulary import ReferenceDataError

from tests.conftest import CONTRACTS_DIR, SERVICE_ROOT

ENUMS = yaml.safe_load((CONTRACTS_DIR / "enums.yaml").read_text(encoding="utf-8"))
PROMPTS = yaml.safe_load((SERVICE_ROOT / "data/stage_prompts.yaml").read_text(encoding="utf-8"))


def test_файл_промптов_покрывает_все_метки_стадий_из_enums():
    labels = parse_stage_labels(ENUMS)

    prompts = parse_stage_prompts(PROMPTS, labels)

    assert prompts.labels == tuple(ENUMS["stage_label"])
    assert all(prompts.prompts[label] for label in labels)


def test_метка_без_промптов_ошибка_старта():
    raw = {"stage_prompts": {"PIT": ["pit"]}}

    with pytest.raises(ReferenceDataError, match=r"нет промптов для \['FRAME'\]"):
        parse_stage_prompts(raw, ("PIT", "FRAME"))


def test_лишняя_метка_ошибка_старта():
    raw = {"stage_prompts": {"PIT": ["pit"], "ROOF": ["roof"]}}

    with pytest.raises(ReferenceDataError, match=r"лишние \['ROOF'\]"):
        parse_stage_prompts(raw, ("PIT",))


def test_пустые_промпты_ошибка_старта():
    with pytest.raises(ReferenceDataError, match="пустой"):
        parse_stage_prompts({"stage_prompts": {"PIT": ["  "]}}, ("PIT",))


def test_стадия_по_наибольшему_логиту_и_вероятности_в_сумме_единица():
    stage = stage_from_logits(("PIT", "FOUNDATION", "FRAME"), [25.0, 22.0, 20.0])

    assert stage.label == "PIT"
    assert stage.scores["PIT"] > stage.scores["FOUNDATION"] > stage.scores["FRAME"]
    assert sum(stage.scores.values()) == pytest.approx(1.0, abs=1e-3)
    assert stage.conf == stage.scores["PIT"]


def test_большие_логиты_не_переполняются():
    stage = stage_from_logits(("PIT", "FRAME"), [1000.0, 999.0])

    assert stage.scores == {"PIT": 0.7311, "FRAME": 0.2689}


def test_равные_логиты_равные_вероятности():
    stage = stage_from_logits(("PIT", "FRAME"), [5.0, 5.0])

    assert stage.scores == {"PIT": 0.5, "FRAME": 0.5}


def test_число_логитов_не_совпадает_с_метками():
    with pytest.raises(ValueError):
        stage_from_logits(("PIT", "FRAME"), [1.0])
