"""Генератор графика: сроки по МРР раскладываются на этапы шаблона, даты — по календарю."""

from dataclasses import replace
from datetime import date

import pytest
from src.core.calendar import WorkCalendar, count_working_days
from src.core.mrr_norms import NormsError, NormsNotAvailable, params_from_tep
from src.core.schedule_generator import check_generator_template, generate_schedule

from tests.unit.test_mrr_norms import NORMS
from tests.unit.vocab import MONOLITH

# Шестидневка с праздником 4 ноября — как moscow-6day.
CALENDAR = WorkCalendar(weekend_days=(7,), holidays=frozenset({date(2026, 11, 4)}))
START = date(2026, 9, 21)  # понедельник
DEMO = {"floors": 17, "total_area": 10000, "sections": 2, "piles": 200}
TEMPLATES = list(MONOLITH.values())


def _generate(templates=TEMPLATES, start=START, **tep):
    params = params_from_tep(DEMO | tep, NORMS)
    return generate_schedule(templates, NORMS, params, start, CALENDAR)


def _stages(**tep):
    return {s.code: s for s in _generate(**tep).stages}


def _working_days(first: date, last: date) -> int:
    return count_working_days(CALENDAR, first, last) + 1


def test_демо_объект_все_этапы_шаблона_по_порядку_от_даты_начала():
    schedule = _generate()

    assert [s.code for s in schedule.stages] == [s.code for s in TEMPLATES]
    assert [s.seq for s in schedule.stages] == list(range(1, 13))
    assert schedule.stages[0].plan_start == START
    assert schedule.total_months == pytest.approx(8.7)  # ТЗ, п. 8: 17 эт., 10 000 м²
    assert [p.months for p in schedule.periods] == pytest.approx([1.0, 1.5, 4.7, 1.5])


def test_длительность_этапа_это_рабочие_дни_между_его_датами():
    for stage in _generate().stages:
        assert stage.norm_duration_days == _working_days(stage.plan_start, stage.plan_end)
        assert CALENDAR.is_working_day(stage.plan_start) and CALENDAR.is_working_day(stage.plan_end)


def test_доли_раскладывают_период_на_этапы():
    schedule = _generate()
    stages = {s.code: s for s in schedule.stages}
    underground = schedule.periods[1].working_days

    assert stages["10.11"].norm_duration_days == schedule.periods[0].working_days  # доля 1,0
    assert stages["12.3.1"].norm_duration_days == round(0.35 * underground)
    assert stages["12.3.2"].norm_duration_days == 10  # 200 свай × 10 / 100 × 0,5 (2 секции)


def test_связи_шаблона_соблюдены():
    stages = _stages()

    for stage in stages.values():
        for link in stage.predecessors:
            before = stages[link.code]
            if link.type == "FS":
                assert stage.plan_start > before.plan_end, (stage.code, link.code)
            elif link.type == "SS":
                assert stage.plan_start >= before.plan_start


def test_цепочка_этапов_занимает_срок_по_нормам_плюс_сваи():
    """Конец графика — сумма периодов МРР в рабочих днях и время на сваи, с точностью до
    округления долей этапов."""
    schedule = _generate()
    planned = sum(p.working_days for p in schedule.periods) + 10
    actual = _working_days(START, max(s.plan_end for s in schedule.stages))

    assert abs(actual - planned) <= 3


def test_без_свай_этап_свай_выпадает_а_связи_переходят_на_его_предшественников():
    stages = _stages(piles=0)

    assert "12.3.2" not in stages
    assert [(p.code, p.type) for p in stages["12.3.1"].predecessors] == [
        ("10.4-10.8", "FS"),
        ("10.11", "FS"),
    ]
    assert [s.seq for s in stages.values()] == list(range(1, 12))


def test_работа_в_две_смены_сокращает_срок():
    two_shifts = _generate(shifts=2)

    assert two_shifts.total_months == pytest.approx(8.7 * 0.9)
    assert max(s.plan_end for s in two_shifts.stages) < max(s.plan_end for s in _generate().stages)


def test_у_каждого_этапа_основание_со_ссылкой_на_мрр():
    stages = _stages()

    assert all(s.basis.startswith("МРР-3.2.81-12") for s in stages.values())
    assert "стр. 1.18" in stages["12.3.1"].basis
    assert "доля этапа 0,35" in stages["12.3.1"].basis
    assert "п. 5.1.6" in stages["12.3.2"].basis


def test_правила_и_участки_из_шаблона():
    pit = _stages()["12.3.1"]

    assert (pit.zone_type, pit.visual_stage, pit.phase) == ("PIT", "PIT", "SUBSTRUCTURE")
    assert pit.rule == MONOLITH["12.3.1"].rule
    assert pit.work_codes == ("12.3.1", "12.3.7")


def test_старт_в_выходной_переносится_на_рабочий_день():
    assert _generate(start=date(2026, 9, 20)).stages[0].plan_start == START  # воскресенье


def test_этап_без_доли_в_шаблоне_не_генерируется():
    broken = [replace(s, share=None) if s.code == "12.7" else s for s in TEMPLATES]

    with pytest.raises(NormsNotAvailable, match=r"12\.7"):
        _generate(templates=broken)


def test_повторный_вызов_даёт_тот_же_график():
    assert _generate() == _generate()


def test_шаблон_без_доли_или_без_этапов_не_даёт_стартовать():
    check_generator_template("RESIDENTIAL_MONOLITH", TEMPLATES, NORMS)
    broken = [replace(s, share=None) if s.code == "12.7" else s for s in TEMPLATES]

    with pytest.raises(NormsError, match="share"):
        check_generator_template("RESIDENTIAL_MONOLITH", broken, NORMS)
    with pytest.raises(NormsError, match="шаблона этапов нет"):
        check_generator_template("ROAD", (), NORMS)
