"""Импорт графика: столбцы, шаблон этапов, даты, связи, ошибки с номерами строк."""

import io
from datetime import date, datetime

import pytest
from openpyxl import Workbook
from src.core.calendar import WorkCalendar
from src.core.plan_import import PlanImportError, parse_schedule, read_table

from tests.conftest import SERVICE_ROOT
from tests.unit.vocab import MONOLITH, VOCAB

# Шестидневка с праздником 4 ноября — как moscow-6day.
CALENDAR = WorkCalendar(weekend_days=(7,), holidays=frozenset({date(2026, 11, 4)}))
DEMO = (SERVICE_ROOT / "tests/fixtures/demo_schedule.csv").read_bytes()


def _parse(text: str):
    return parse_schedule(read_table("plan.csv", text.encode()), MONOLITH, VOCAB, CALENDAR)


def _issues(text: str):
    with pytest.raises(PlanImportError) as error:
        _parse(text)
    return [(i.row, i.column) for i in error.value.issues]


def test_демо_график_совпадает_с_фикстурой_analysis():
    """Даты и длительности — как в services/analysis-service/tests/fixtures/plan.json."""
    stages = parse_schedule(read_table("demo.csv", DEMO), MONOLITH, VOCAB, CALENDAR)

    assert [s.code for s in stages] == ["10.4-10.8", "12.3.1", "12.3.4"]
    assert [s.norm_duration_days for s in stages] == [21, 31, 24]
    prep, pit, slab = stages
    assert (pit.zone_type, pit.visual_stage, slab.visual_stage) == ("PIT", "PIT", "FOUNDATION")
    assert pit.plan_start == date(2026, 10, 15)  # дата в виде ДД.ММ.ГГГГ
    assert [(p.code, p.type) for p in pit.predecessors] == [("10.4-10.8", "FS")]
    # Пустая ячейка связей — связи шаблона, но только на этапы, которые есть в файле.
    assert prep.predecessors == ()
    assert pit.rule["required"][1] == {"any_of": ["dump_truck"], "min": 2}
    assert pit.work_codes == ("12.3.1", "12.3.7")


def test_столбцы_файла_главнее_шаблона_и_порядок_столбцов_любой():
    stage = _parse(
        "Окончание,Код,Наименование,Начало,Тип участка,Визуальная стадия,Фаза\n"
        "2026-10-24,12.3.1,Котлован,2026-10-19,BUILDING_FOOTPRINT,FOUNDATION,PREPARATORY\n"
    )[0]

    assert (stage.zone_type, stage.visual_stage, stage.phase) == (
        "BUILDING_FOOTPRINT",
        "FOUNDATION",
        "PREPARATORY",
    )
    assert stage.norm_duration_days == 6


def test_этап_без_шаблона_без_правила_но_с_фазой_и_участком():
    stage = _parse(
        "код;наименование;начало;окончание;фаза;тип участка\n"
        "99.1;Свой этап;2026-10-19;2026-10-19;NETWORKS;PERIMETER\n"
    )[0]

    assert stage.rule is None
    assert stage.work_codes == ("99.1",)
    assert stage.basis == "Импорт графика"


def test_связи_с_типом_и_лагом_и_без_связей():
    stages = _parse(
        "код;наименование;начало;окончание;связи\n"
        "10.4-10.8;Подготовка;2026-10-19;2026-10-21;\n"
        "10.11;Площадка;2026-10-19;2026-10-24;-\n"
        # В CSV с «;» связи внутри ячейки разделяются запятой.
        "12.3.2;Сваи;2026-10-26;2026-10-31;10.4-10.8 SS+2, 10.11\n"
    )

    assert stages[1].predecessors == ()
    assert [(p.code, p.type, p.lag_days) for p in stages[2].predecessors] == [
        ("10.4-10.8", "SS", 2),
        ("10.11", "FS", 0),
    ]


def test_ошибки_собираются_по_всем_строкам_с_номерами():
    issues = _issues(
        "код;наименование;начало;окончание\n"
        "12.3.1;Котлован;2026-10-20;2026-10-19\n"
        "\n"
        "12.3.4;Плита;завтра;2026-12-18\n"
        "99.1;Без шаблона;2026-10-19;2026-10-20\n"
    )

    assert issues == [(2, "окончание"), (4, "начало"), (5, "фаза"), (5, "тип участка")]


def test_повтор_кода_и_связь_на_отсутствующий_этап():
    issues = _issues(
        "код;наименование;начало;окончание;связи\n"
        "12.3.1;Котлован;2026-10-19;2026-10-20;12.3.2\n"
        "12.3.1;Котлован ещё раз;2026-10-21;2026-10-22;\n"
    )

    assert (3, "код") in issues and (2, "связи") in issues


def test_цикл_в_связях():
    issues = _issues(
        "код;наименование;начало;окончание;связи\n"
        "12.3.1;Котлован;2026-10-19;2026-10-20;12.3.4\n"
        "12.3.4;Плита;2026-10-21;2026-10-22;12.3.1\n"
    )

    assert issues == [(None, "связи")]


def test_этап_целиком_на_выходных():
    assert _issues(
        "код;наименование;начало;окончание\n12.3.1;Котлован;2026-10-25;2026-10-25\n"
    ) == [(2, "окончание")]


def test_нет_обязательного_столбца():
    with pytest.raises(PlanImportError, match="окончание") as error:
        _parse("код;наименование;начало\n12.3.1;Котлован;2026-10-19\n")
    assert error.value.issues[0].row == 1


@pytest.mark.parametrize("name", ["plan.pdf", "plan"])
def test_неподдерживаемый_формат(name):
    with pytest.raises(PlanImportError, match="csv"):
        read_table(name, b"")


def test_xlsx_с_датами_ячейками_и_кодом_испорченным_excel():
    """Excel хранит даты датами, а код «10.11» превращает в 10 ноября."""
    book = Workbook()
    sheet = book.active
    sheet.append(["Код", "Наименование", "Начало", "Окончание"])
    sheet.append(
        [datetime(2025, 11, 10), "Обустройство площадки", date(2026, 10, 19), date(2026, 10, 24)]
    )
    sheet.append([12.0, "Весь СМР", datetime(2026, 10, 26), datetime(2026, 10, 31)])
    buffer = io.BytesIO()
    book.save(buffer)

    with pytest.raises(PlanImportError) as error:
        parse_schedule(read_table("plan.xlsx", buffer.getvalue()), MONOLITH, VOCAB, CALENDAR)

    # 10.11 восстановлен и нашёл шаблон; у «12» шаблона нет — нужна фаза и участок.
    assert [(i.row, i.column) for i in error.value.issues] == [(3, "фаза"), (3, "тип участка")]


def test_испорченный_xlsx():
    with pytest.raises(PlanImportError, match="XLSX"):
        read_table("plan.xlsx", b"not a zip")
