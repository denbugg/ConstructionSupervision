"""Резюме нейросетью (T35): проверка чисел и ссылок, запасной шаблон (ADR-0008)."""

import pytest
from src.report.context import build_context
from src.report.summary import check_summary, clean_text, llm_context
from src.services.summary import Summarizer

from tests.conftest import StubLlm
from tests.unit.test_report import report_input  # noqa: F401 — фикстура входа отчёта


@pytest.fixture
def context(report_input):  # noqa: F811
    return build_context(report_input)


@pytest.fixture
def facts(context):
    return llm_context(context)


def _honest(facts) -> str:
    """Текст, как его должна писать модель: числа и ID — только из контекста."""
    first, second = facts["отклонения"]["главные"][:2]
    return (
        f"На {facts['момент_анализа']} объект «{facts['объект']}»: {facts['статус'].lower()}, "
        f"отставание {facts['отклонение_от_графика_раб_дн']} раб. дн., SPI {facts['spi']}.\n\n"
        f"Главное: [{first['id']}] {first['что']}; [{second['id']}] {second['что']}.\n\n"
        f"{facts['ограничения'][1]}"
    )


def test_честный_текст_проходит(facts):
    assert check_summary(_honest(facts), facts) == []


def test_то_же_число_в_другой_записи_не_выдумка(facts):
    spi = facts["spi"]
    text = _honest(facts).replace(f"SPI {spi}", f"SPI {spi.replace('.', ',')}")
    # Дата по частям и время с ведущим нулём — то же, что в контексте.
    day, month, year = facts["момент_анализа"].split()[0].split(".")
    text += f" Данные на {day}.{month}, год {year}."

    assert check_summary(text, facts) == []


def test_выдуманное_число_отбрасывает_текст(facts):
    text = _honest(facts) + " Завершение ожидается через 987 дней."

    assert check_summary(text, facts) == ["числа не из фактов: 987"]


def test_чужой_id_и_текст_без_ссылок_отбрасываются(facts):
    no_refs = f"Объект «{facts['объект']}», SPI {facts['spi']}."
    alien = _honest(facts) + " См. также [abcdef12]."

    assert check_summary(no_refs, facts) == ["нет ни одной ссылки на ID отклонения"]
    assert check_summary(alien, facts) == ["ссылки на неизвестные отклонения: abcdef12"]
    assert check_summary("  ", facts) == ["пустой ответ"]


def test_разметка_модели_становится_простым_текстом():
    raw = "## Итог\n**Статус:** в графике\n* пункт один\n- пункт два\n\n\n\nконец"

    assert clean_text(raw) == "Итог\nСтатус: в графике\n• пункт один\n• пункт два\n\nконец"


async def test_без_нейросети_шаблон(context):
    summary, rejected = await Summarizer(None).summarize(context)

    assert summary.generated_by == "TEMPLATE" and rejected == []


async def test_проверенный_текст_нейросети_идёт_в_резюме(context, facts):
    llm = StubLlm()
    llm.reply = "**" + _honest(facts) + "**"

    summary, rejected = await Summarizer(llm).summarize(context)

    assert (summary.generated_by, rejected) == ("LLM", [])
    assert summary.text == _honest(facts) and "stub-llm" in summary.source
    system, user = llm.prompts[0]
    # В модель уходят инструкция из prompts/ и JSON фактов — больше ничего (ADR-0008).
    assert "Не считай" in system and user.startswith("Факты отчёта (JSON):")


async def test_выдумка_нейросети_заменяется_шаблоном_без_выдуманного_числа(context, facts):
    llm = StubLlm()
    llm.reply = _honest(facts) + " Потери составят 987 дней."

    summary, rejected = await Summarizer(llm).summarize(context)

    assert summary.generated_by == "TEMPLATE"
    assert rejected == ["числа не из фактов: 987"]
    assert "987" not in summary.source and "не прошёл проверку" in summary.source


async def test_недоступная_нейросеть_не_ошибка(context):
    llm = StubLlm()
    llm.unavailable = True

    summary, rejected = await Summarizer(llm).summarize(context)

    assert summary.generated_by == "TEMPLATE" and "недоступна" in summary.source
    assert rejected == ["нейросеть недоступна: ReadTimeout"]
