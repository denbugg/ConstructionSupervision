"""API календарей: moscow-6day с праздниками по ТК РФ, проверка настроек, рост plan_version."""

BASE = "/api/v1/plan/calendars"
OBJECTS = "/api/v1/plan/objects"
FIVE_DAY = {
    "code": "test-5day",
    "name": "Пятидневка для теста",
    "weekend_days": [7, 6],
    "holidays": ["2026-11-04", "2026-11-04"],
    "work_hours": {"start": "08:00", "end": "20:00"},
}


async def _moscow(client) -> dict:
    items = (await client.get(BASE, params={"limit": 200})).json()["items"]
    return next(c for c in items if c["code"] == "moscow-6day")


async def test_шестидневка_москвы_заведена_с_праздником_4_ноября(client):
    calendar = await _moscow(client)

    assert calendar["timezone"] == "Europe/Moscow"
    assert calendar["weekend_days"] == [7]
    assert calendar["work_hours"] == {"start": "07:00", "end": "23:00"}
    assert "2026-11-04" in calendar["holidays"]
    assert "2026-12-31" not in calendar["holidays"]


async def test_новый_объект_получает_календарь_по_умолчанию(client):
    moscow = await _moscow(client)

    created = (await client.post(OBJECTS, json={"name": "Жилой дом, корпус 2"})).json()

    assert created["calendar_id"] == moscow["id"]


async def test_создание_календаря_убирает_повторы_праздников(client):
    response = await client.post(BASE, json=FIVE_DAY)

    assert response.status_code == 201
    body = response.json()
    assert body["holidays"] == ["2026-11-04"]
    assert response.headers["Location"].endswith(body["id"])
    assert (await client.get(f"{BASE}/{body['id']}")).json()["code"] == "test-5day"


async def test_повтор_кода_календаря_это_конфликт(client):
    await client.post(BASE, json=FIVE_DAY)

    response = await client.post(BASE, json=FIVE_DAY)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CALENDAR_ALREADY_EXISTS"


async def test_бессмысленные_рабочие_часы_отклоняются(client):
    response = await client.post(
        BASE, json=FIVE_DAY | {"work_hours": {"start": "20:00", "end": "08:00"}}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CALENDAR_INVALID"


async def test_правка_календаря_поднимает_версию_плана_и_шлёт_сигнал(client, analysis):
    moscow = await _moscow(client)
    created = (await client.post(OBJECTS, json={"name": "Жилой дом, корпус 3"})).json()

    response = await client.patch(
        f"{BASE}/{moscow['id']}", json={"holidays": [*moscow["holidays"], "2026-12-31"]}
    )

    assert response.status_code == 200
    assert "2026-12-31" in response.json()["holidays"]
    obj = (await client.get(f"{OBJECTS}/{created['id']}")).json()
    assert obj["plan_version"] == created["plan_version"] + 1
    assert created["id"] in {str(s) for s in analysis.signals}


async def test_переименование_календаря_план_не_меняет(client, analysis):
    moscow = await _moscow(client)

    response = await client.patch(f"{BASE}/{moscow['id']}", json={"name": "Москва, 6 дней"})

    assert response.status_code == 200
    assert analysis.signals == []


async def test_неизвестный_календарь(client):
    response = await client.patch(
        f"{BASE}/00000000-0000-0000-0000-000000000000", json={"name": "нет"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CALENDAR_NOT_FOUND"
