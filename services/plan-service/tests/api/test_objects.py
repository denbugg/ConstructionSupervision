"""API объектов: коды ответов, форма тела, конверт ошибки."""

BASE = "/api/v1/plan/objects"
SAMPLE = {
    "name": "Строительство монолитного жилого дома 17 этажей, г. Москва",
    "object_type": "RESIDENTIAL_MONOLITH",
    "address": "г. Москва, ул. Примерная, вл. 1",
    "plan_start": "2026-10-01",
}


async def test_создание_объекта_возвращает_201_и_location(client):
    response = await client.post(BASE, json=SAMPLE)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == SAMPLE["name"]
    assert body["status"] == "DRAFT"
    assert body["plan_version"] == 0
    assert response.headers["Location"].endswith(body["id"])


async def test_созданный_объект_читается_по_идентификатору(client):
    created = (await client.post(BASE, json=SAMPLE)).json()

    response = await client.get(f"{BASE}/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_список_отдаётся_в_общем_формате_страницы(client):
    await client.post(BASE, json=SAMPLE)

    body = (await client.get(BASE, params={"limit": 10})).json()

    assert set(body) == {"items", "total", "limit", "offset"}
    assert body["total"] >= 1
    assert body["limit"] == 10


async def test_фильтр_по_типу_объекта_отсекает_чужие(client):
    await client.post(BASE, json=SAMPLE)

    body = (await client.get(BASE, params={"object_type": "ROAD"})).json()

    assert all(item["object_type"] == "ROAD" for item in body["items"])


async def test_несуществующий_объект_отдаёт_конверт_ошибки(client):
    response = await client.get(f"{BASE}/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "OBJECT_NOT_FOUND"
    assert error["message"]
    assert "request_id" in error


async def test_запрос_без_ключа_отклоняется(client):
    response = await client.get(BASE, headers={"X-API-Key": ""})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_слишком_короткое_наименование_не_проходит_схему(client):
    response = await client.post(BASE, json={"name": "дом"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SCHEMA_VALIDATION_FAILED"


async def test_архивация_не_удаляет_объект(client):
    created = (await client.post(BASE, json=SAMPLE)).json()

    assert (await client.delete(f"{BASE}/{created['id']}")).status_code == 204

    body = (await client.get(f"{BASE}/{created['id']}")).json()
    assert body["status"] == "ARCHIVED"
