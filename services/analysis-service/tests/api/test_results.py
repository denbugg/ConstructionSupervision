"""API выводов по объекту: статус, прогресс этапов, загрузка техники (T16a)."""

from tests.conftest import DEMO_OBJECT_ID

BASE = f"/api/v1/analysis/objects/{DEMO_OBJECT_ID}"
PIT_STAGE_ID = "7c1e9f03-b5a2-4d78-8e46-c3f0a1b7d926"


async def test_статус_объекта_для_дашборда(client, analyzed):
    response = await client.get(f"{BASE}/status")

    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["delay_days"], body["confidence"]) == ("DELAY", 10, "MEDIUM")
    assert body["as_of"] == "2026-10-22T12:00:00Z"
    # Все серьёзности — с нулями: дашборду не нужно гадать, какие ключи бывают.
    assert body["deviations"] == {"INFO": 1, "LOW": 1, "MEDIUM": 0, "HIGH": 0}
    assert body["blind_areas"] == 1
    assert body["stages"]["total"] == 3
    assert [s["name"] for s in body["stages_at_risk"]] == [
        "Разработка котлована",
        "Фундаментная плита",
    ]
    assert body["facts"]["observation_days"] == 4


async def test_без_прогона_статуса_нет(client):
    response = await client.get(f"{BASE}/status")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "OBJECT_NOT_ANALYZED"


async def test_прогресс_этапов_с_активностью_по_дням(client, analyzed):
    body = (await client.get(f"{BASE}/progress")).json()

    assert body["as_of"] == "2026-10-22T12:00:00Z"
    assert len(body["stages"]) == 3
    pit = next(s for s in body["stages"] if s["stage_id"] == PIT_STAGE_ID)
    # Котлован по плану с 15.10, наблюдения — с 19.10: старт снимки не застали, три рабочих
    # дня до наблюдений засчитаны по плану (methodology.md, 10.3a). Эффективных дней
    # 3 + 3 из 31, темп 0.75: (1 − 6/31) × 31 / 0.75 → 34 рабочих дня от 22.10.
    assert pit["actual_start"] is None and pit["status"] == "LATE"
    assert pit["facts"]["credited_days"] == 3 and pit["effective_days"] == 6
    assert pit["forecast_end"] == "2026-12-02" and pit["delay_days"] == 10
    # День 1 (20.10) без самосвалов: комплект неполный, активность ноль.
    assert [(a["date"], a["activity_index"]) for a in pit["activity"]] == [
        ("2026-10-19", 1.0),
        ("2026-10-20", 0.0),
        ("2026-10-21", 1.0),
        ("2026-10-22", 1.0),
    ]


async def test_загрузка_техники_по_дням(client, analyzed):
    body = (await client.get(f"{BASE}/equipment")).json()

    excavator = [i for i in body["items"] if i["equipment_class"] == "excavator"]
    assert [i["date"] for i in excavator] == [
        "2026-10-19",
        "2026-10-20",
        "2026-10-21",
        "2026-10-22",
    ]


async def test_загрузка_техники_за_полуинтервал_дат(client, analyzed):
    body = (
        await client.get(f"{BASE}/equipment", params={"from": "2026-10-22", "to": "2026-10-23"})
    ).json()

    assert {i["date"] for i in body["items"]} == {"2026-10-22"}
    # День 3: экскаватор в котловане и второй — у въезда.
    excavator = next(i for i in body["items"] if i["equipment_class"] == "excavator")
    assert excavator["max_count"] == 2


async def test_без_прогона_загрузки_нет(client):
    response = await client.get(f"{BASE}/equipment")

    assert response.status_code == 404
