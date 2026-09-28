"""Нормы МРР: таблица 1, интерполяция, экстраполяция и её пределы, сменность, сваи."""

import copy
import html
import json
import math
import re

import pytest
from src.core.mrr_norms import (
    GeneratorParamsError,
    NormsError,
    NormsNotAvailable,
    params_from_tep,
    parse_norms,
    period_months,
    piles_working_days,
)

from tests.conftest import SERVICE_ROOT
from tests.unit.vocab import ENUMS

RAW = json.loads((SERVICE_ROOT / "data/mrr_norms.json").read_text(encoding="utf-8"))
NORMS = parse_norms(RAW, ENUMS["construction_phase"])["RESIDENTIAL_MONOLITH"]
MRR = SERVICE_ROOT.parents[1] / "data/reference/МРР-3.2.81-12.htm"


def _months(floors: int, area: float) -> dict[str, float]:
    return {k: round(v, 3) for k, v in period_months(NORMS, floors, area).months.items()}


def test_пример_из_тз_17_этажей_10000_м2():
    """ТЗ, п. 8: 8,7 мес. = 1,0 + 1,5 + 4,7 + 1,5."""
    result = period_months(NORMS, 17, 10000)

    assert _months(17, 10000) == {
        "total": 8.7,
        "preparatory": 1.0,
        "underground": 1.5,
        "aboveground": 4.7,
        "finishing": 1.5,
    }
    assert "стр. 1.18" in result.basis


def test_площадь_между_строками_группы_интерполируется():
    months = _months(17, 8500)  # посередине между стр. 1.17 (7000 м²) и 1.18 (10000 м²)

    assert (months["total"], months["aboveground"]) == (8.35, 4.35)
    assert "стр. 1.17–1.18" in period_months(NORMS, 17, 8500).basis


def test_этажность_между_группами_интерполируется():
    # 7–10 эт. при 7000 м² — стр. 1.2: 6,0; 12 эт. — между стр. 1.7 и 1.8: 6,9; 11 эт. — середина.
    assert _months(11, 7000)["total"] == 6.45


def test_экстраполяция_0_3_процента_на_процент_площади():
    above = _months(17, 30000)["total"]  # стр. 1.23: 26000 м², 11,1 мес.
    below = _months(17, 2000)["total"]  # стр. 1.16: 4000 м², 7,0 мес.; ровно половина

    assert math.isclose(above, round(11.1 * (1 + 0.3 * (30000 / 26000 - 1)), 3))
    assert below == round(7.0 * 0.85, 3)


@pytest.mark.parametrize(
    ("floors", "area"),
    [(17, 1999), (17, 52001), (6, 5000), (26, 9000)],
    ids=["меньше половины", "больше двойной", "ниже таблицы", "выше таблицы"],
)
def test_вне_пределов_норм_нет(floors, area):
    with pytest.raises(NormsNotAvailable):
        period_months(NORMS, floors, area)


def test_параметры_по_умолчанию_и_сменность():
    params = params_from_tep({"floors": 17, "total_area": 10000, "shifts": 2}, NORMS)

    assert (params.sections, params.piles, params.shifts) == (1, 0, "2")
    assert params_from_tep({"floors": 17, "total_area": 10000}, NORMS).shifts == "1.5"


def test_ошибки_параметров_собираются_вместе():
    with pytest.raises(GeneratorParamsError) as error:
        params_from_tep({"sections": 0, "shifts": 2.5, "piles": True}, NORMS)

    message = str(error.value)
    for key in ("floors", "total_area", "sections", "piles", "shifts"):
        assert key in message


@pytest.mark.parametrize(
    ("piles", "sections", "days"),
    [(200, 2, 10), (200, 5, 6), (150, 4, 8), (0, 2, 0)],
)
def test_сваи_10_рабочих_дней_на_100_с_коэффициентом_совмещения(piles, sections, days):
    assert piles_working_days(NORMS, piles, sections)[0] == days


def test_опечатка_в_таблице_и_число_без_источника_не_дают_стартовать():
    typo = copy.deepcopy(RAW)
    typo["RESIDENTIAL_MONOLITH"]["table"]["rows"][0]["months"][0] = 6.1
    unsourced = copy.deepcopy(RAW)
    unsourced["RESIDENTIAL_MONOLITH"]["piles"]["source"] = ""

    with pytest.raises(NormsError, match=r"строка 1\.1:"):
        parse_norms(typo, ENUMS["construction_phase"])
    with pytest.raises(NormsError, match="source"):
        parse_norms(unsourced, ENUMS["construction_phase"])


@pytest.mark.skipif(not MRR.exists(), reason="нет data/reference: тест из рабочей копии")
def test_таблица_совпадает_с_первоисточником():
    """Каждое число mrr_norms.json сверяется с таблицей 1 в полном тексте МРР."""
    text = MRR.read_text(encoding="utf-8")
    table = re.search(r"(?is)<table.*?</table>", text[text.find("5.1.21") :]).group(0)
    source, floors = {}, None
    for tr in re.findall(r"(?is)<tr.*?</tr>", table):
        cells = [
            re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
            for c in re.findall(r"(?is)<td[^>]*>(.*?)</td>", tr)
        ]
        if not cells or not re.fullmatch(r"1\.\d+", cells[0]):
            continue
        floors = cells[2] or floors
        numbers = [float(c.replace(",", ".")) for c in cells[3:9]]
        source[cells[0]] = (floors.replace(" ", ""), numbers[0], numbers[1:])

    ours = {
        r["row"]: (
            "-".join(str(f) for f in dict.fromkeys(r["floors"])),
            r["area"],
            r["months"],
        )
        for r in RAW["RESIDENTIAL_MONOLITH"]["table"]["rows"]
    }
    assert ours == source
