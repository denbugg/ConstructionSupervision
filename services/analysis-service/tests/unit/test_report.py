"""Отчёт как чистая функция (T34b): выводы прогона по демо-дням → контекст → HTML."""

import re
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from src.core.forecast import ForecastParams
from src.core.predicates import load_rules
from src.core.rules import RuleParams
from src.core.run import analyze
from src.report.context import build_context, deviations_in_period, pick_evidence
from src.report.html import link_refs, render_html, template_summary
from src.report.labels import load_labels
from src.report.model import (
    Box,
    DeviationSnapshot,
    EquipmentDay,
    EvidenceImage,
    ReportInput,
    StageSnapshot,
    StatusSnapshot,
)

from tests.conftest import CONTRACTS_DIR
from tests.factories import load_facts, load_plan, make_facts, stable_id

SERVICE = Path(__file__).resolve().parents[2]
RULES = load_rules(SERVICE / "data" / "deviation_rules.yaml")
LABELS = load_labels(SERVICE / "data" / "report_labels.yaml", CONTRACTS_DIR)
PLAN = load_plan()
DAYS = ["facts_normal_day.json", "facts_day1.json", "facts_day2.json", "facts_day3.json"]
# Разделы в порядке отчёта: резюме читают первым — оно сразу за титулом.
SECTIONS = (
    "Резюме",
    "Сводка",
    "Диаграмма Ганта план-факт",
    "Загрузка техники по дням",
    "Отклонения за период",
    "Снимки-доказательства",
    "Ограничения",
)


def _facts():
    return make_facts(*(s for name in DAYS for s in load_facts(name).sessions))


@pytest.fixture(scope="module")
def report_input():
    """Вход отчёта так, как его собирает сценарий из строк базы после прогона."""
    from src.core.enums import load_enums

    enums = load_enums(CONTRACTS_DIR)
    facts = _facts()
    result = analyze(
        PLAN,
        facts,
        rules=RULES,
        enums=enums,
        params=RuleParams(transient_window_sessions=4, min_stage_conf=0.5),
        forecast_params=ForecastParams(
            min_activity=0.1,
            forecast_window_days=5,
            min_days_for_forecast=3,
            on_track_tolerance_days=2,
            confidence_high_days=5,
            confidence_high_visible=0.8,
            confidence_medium_visible=0.5,
            unknown_blind_share=0.5,
        ),
    )
    status = result.object_status
    return ReportInput(
        plan=PLAN,
        status=StatusSnapshot(
            as_of=result.as_of,
            computed_at=result.as_of,
            status=status.status,
            delay_days=status.delay_days,
            spi=status.spi,
            confidence=status.confidence,
            facts=status.facts,
            stages_at_risk=list(status.stages_at_risk),
        ),
        stages=[
            StageSnapshot(
                stage_id=s.stage_id,
                actual_start=s.actual_start,
                progress=s.progress,
                planned_progress=s.planned_progress or 0.0,
                spi=s.spi,
                forecast_end=s.forecast_end,
                delay_days=s.delay_days,
                status=s.status,
                confidence=s.confidence,
                basis=s.facts.get("basis"),
            )
            for s in result.stage_facts
        ],
        equipment=[
            EquipmentDay(e.day, e.equipment_class, e.sessions_seen, e.max_count)
            for e in result.daily_equipment
        ],
        deviations=[
            DeviationSnapshot(
                id=stable_id("deviation", i),
                code=d.finding.code,
                severity=d.finding.severity,
                status="NEW" if d.finding.active else "RESOLVED",
                verdict=None,
                stage_id=d.finding.stage_id,
                area=d.finding.area,
                equipment_class=d.finding.equipment_class,
                title=d.title,
                message=d.message,
                first_seen_at=d.finding.first_seen_at,
                last_seen_at=d.finding.last_seen_at,
                evidence=list(d.finding.evidence),
            )
            for i, d in enumerate(result.deviations)
        ],
        facts=facts,
        period_from=date(2026, 10, 19),
        period_to=date(2026, 10, 22),
        generated_at=datetime(2026, 10, 23, 9, tzinfo=UTC),
        labels=LABELS,
        severity_order=enums.values["severity"],
        images_without_time=3,
    )


def _html(inp):
    context = build_context(inp)
    return render_html(context, template_summary(context))


def test_в_отчёте_все_разделы_и_ни_одного_пустого_значения(report_input):
    html = _html(report_input)

    for section in SECTIONS:
        assert f"<h2>{section}</h2>" in html
    assert "None" not in html and ">nan" not in html
    assert html.count("<svg") == 2  # Гант и загрузка техники; снимков на входе нет


def test_ограничения_называют_слепой_склад_и_снимки_без_времени(report_input):
    lines = build_context(report_input)["limitations"]
    text = "\n".join(lines)

    assert lines[0].startswith("Уверенность выводов — ")
    assert "«Склад» не виден" in text and "проверить вручную" in text
    assert "Снимков без времени съёмки: 3" in text
    assert "Вне контроля ИИ" in text


def test_ограничения_честно_говорят_когда_site_не_ответил(report_input):
    inp = replace(report_input, facts=None, images_without_time=None)

    text = "\n".join(build_context(inp)["limitations"])

    assert "слепые участки не оценены" in text
    assert "Число снимков без времени съёмки неизвестно" in text


def test_ограничения_называют_этапы_закрытые_отметкой_кем_и_когда(report_input):
    """ADR-0015: отметка сильнее снимков, поэтому в отчёте видно, кто и когда её поставил."""
    pit = PLAN.stages[1].model_copy(
        update={"completed_on": date(2026, 10, 21), "completed_by": "Петров П. П."}
    )
    plan = PLAN.model_copy(update={"stages": (PLAN.stages[0], pit, PLAN.stages[2])})
    stages = [
        replace(s, basis="OPERATOR") if s.stage_id == pit.id else s for s in report_input.stages
    ]

    text = "\n".join(build_context(replace(report_input, plan=plan, stages=stages))["limitations"])

    assert "закрытых отметкой оператора «выполнен»: 1" in text
    assert "«Разработка котлована» — 21.10.2026, Петров П. П." in text


def test_период_отбирает_пересекающиеся_эпизоды(report_input):
    only_day1 = replace(report_input, period_from=date(2026, 10, 20), period_to=date(2026, 10, 20))

    assert {d.code for d in deviations_in_period(report_input)} == {"D2", "D3", "D4", "D10"}
    assert [d.code for d in deviations_in_period(only_day1)] == ["D2"]


def test_доказательства_от_серьёзных_без_ложных_и_не_больше_предела(report_input):
    deviations = list(report_input.deviations)
    rejected = replace(deviations[0], verdict="REJECTED")

    picks = pick_evidence([rejected, *deviations[1:]], report_input.severity_order, limit=2)

    assert len(picks) == 2
    assert rejected.id not in {p.deviation.id for p in picks}
    ranks = [report_input.severity_order.index(p.deviation.severity) for p in picks]
    assert ranks == sorted(ranks, reverse=True)


def test_снимок_с_рамками_и_пропавший_снимок_с_причиной(report_input):
    d = report_input.deviations[0]
    shown = EvidenceImage(
        deviation_id=d.id,
        image_id=stable_id("img", 1),
        captured_at=datetime(2026, 10, 20, 9, tzinfo=UTC),
        data_uri="data:image/jpeg;base64,AAAA",
        width=400,
        height=300,
        boxes=(Box((0.1, 0.2, 0.3, 0.4), "Экскаватор", True), Box((0.5, 0.5, 0.6, 0.6), "", False)),
    )
    lost = EvidenceImage(deviation_id=d.id, image_id=stable_id("img", 2), problem="снимок удалён")

    html = _html(replace(report_input, evidence=[shown, lost]))

    figures = html.split("<h2>Снимки-доказательства</h2>")[1].split("<h2>")[0]
    assert 'xlink:href="data:image/jpeg;base64,AAAA"' in figures
    assert figures.count('stroke="#dc2626"') == 1 and "Экскаватор" in figures
    assert "не вставлен: снимок удалён" in html
    assert "Снимков-доказательств не удалось вставить: 1 (снимок удалён)" in html


def test_резюме_шаблонное_ссылается_на_id_и_берёт_числа_из_отчёта(report_input):
    context = build_context(report_input)

    summary = template_summary(context)

    assert summary.generated_by == "TEMPLATE"
    assert all(f"[{row['id']}]" in summary.text for row in context["deviations"][:5])
    numbers = set(re.findall(r"\d+(?:[.,]\d+)?", summary.text))
    # Каждое число резюме есть в остальном отчёте — резюме ничего не считает само. Блок
    # резюме вырезается целиком: ссылки на отклонения меняют его текст внутри HTML.
    html = render_html(context, summary)
    rest = re.sub(r'<div class="summary">.*?</div>', "", html, flags=re.S)
    assert rest != html
    assert numbers <= set(re.findall(r"\d+(?:[.,]\d+)?", rest))


def test_резюме_сразу_за_титулом_и_ссылается_на_строки_таблицы(report_input):
    context = build_context(report_input)
    html = render_html(context, template_summary(context))

    order = [html.index(f"<h2>{section}</h2>") for section in SECTIONS]
    assert order == sorted(order)
    block = re.search(r'<div class="summary">(.*?)</div>', html, flags=re.S).group(1)
    for row in context["deviations"][:5]:
        assert f'<a href="#dev-{row["id"]}">{row["id"]}</a>' in block
        assert f'<tr id="dev-{row["id"]}">' in html


def test_ссылки_резюме_только_на_известные_id_и_текст_экранирован():
    text = "См. [bac02fc0] и [deadbeef] <script>alert(1)</script>"

    html = str(link_refs(text, ["bac02fc0"]))

    assert '<a href="#dev-bac02fc0">bac02fc0</a>' in html
    assert "[deadbeef]" in html and "#dev-deadbeef" not in html
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_гант_по_полосе_на_этап_загрузка_по_клетке_на_класс_и_день(report_input):
    context = build_context(report_input)
    classes = {e.equipment_class for e in report_input.equipment}

    assert context["gantt"].count('rx="2"') == len(PLAN.stages)
    assert context["equipment"].count("<rect") == 1 + len(classes) * 4
