"""Правка этапа: даты включительно, работы только на рабочем участке, отметка «выполнен»."""

from datetime import date

import pytest
from src.core.stages import (
    StageCompletionError,
    StageDatesError,
    StageZoneError,
    check_stage,
    completion_changes,
    work_zone_types,
)

ROLES = {"PIT": "WORK", "ENTRY_GATE": "SERVICE", "DANGER": "SAFETY", "ROAD": "WORK"}
START = date(2026, 10, 15)


def test_этап_в_один_день_допустим():
    check_stage(START, START, "PIT", ROLES)


def test_конец_раньше_начала_отклоняется():
    with pytest.raises(StageDatesError, match="2026-10-14"):
        check_stage(START, date(2026, 10, 14), "PIT", ROLES)


@pytest.mark.parametrize("zone_type", ["ENTRY_GATE", "DANGER", "SPACEPORT"])
def test_этап_не_бывает_на_служебном_опасном_или_неизвестном_участке(zone_type):
    with pytest.raises(StageZoneError, match="PIT"):
        check_stage(START, START, zone_type, ROLES)


def test_рабочие_типы_в_порядке_справочника():
    assert work_zone_types(ROLES) == ("PIT", "ROAD")


def test_отметка_берёт_автора_из_запроса_и_чистит_комментарий():
    done = date(2026, 11, 18)

    changes = completion_changes(
        {"completed_on": done, "completion_note": "  акт №7  "}, None, "Иван"
    )

    assert changes == {"completed_on": done, "completed_by": "Иван", "completion_note": "акт №7"}


def test_снятая_отметка_уносит_автора_и_комментарий():
    changes = completion_changes({"completed_on": None, "completion_note": "x"}, START, "Иван")

    assert changes == {"completed_on": None, "completed_by": None, "completion_note": None}


def test_комментарий_к_уже_отмеченному_этапу_не_меняет_автора():
    assert completion_changes({"completion_note": "акт"}, START, "Пётр") == {
        "completion_note": "акт"
    }


def test_комментарий_без_отметки_отклоняется():
    with pytest.raises(StageCompletionError):
        completion_changes({"completion_note": "акт"}, None, "Иван")


def test_без_полей_отметки_правка_её_не_трогает():
    assert completion_changes({}, START, "Иван") == {}
