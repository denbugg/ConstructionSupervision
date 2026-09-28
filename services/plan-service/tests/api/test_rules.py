"""API правил «этап → техника»: форма из контракта, проверка классов, версии и сигнал."""

RULES = "/api/v1/plan/rules"
OBJECTS = "/api/v1/plan/objects"
PIT_RULE = {
    "required": [{"any_of": ["excavator"], "min": 1}, {"any_of": ["dump_truck"], "min": 2}],
    "allowed": ["bulldozer", "loader"],
    "signature": {"equipment": ["excavator", "dump_truck"], "stage_label": None},
    "min_sessions": 2,
}


async def _create(client, demo_stage, **change):
    return await client.post(RULES, json=PIT_RULE | {"stage_id": demo_stage["stage_id"]} | change)


async def _plan_version(client, demo_stage) -> int:
    obj = (await client.get(f"{OBJECTS}/{demo_stage['object']['id']}")).json()
    return obj["plan_version"]


async def test_правило_создаётся_в_форме_контракта_и_видно_у_этапа(client, demo_stage, analysis):
    response = await _create(client, demo_stage)

    assert response.status_code == 201
    rule = response.json()
    assert rule["version"] == 1 and rule["is_active"] is True
    assert rule["required"] == PIT_RULE["required"]
    assert response.headers["Location"].endswith(rule["id"])
    stages = (await client.get(f"{OBJECTS}/{demo_stage['object']['id']}/stages")).json()
    assert stages["items"][0]["rule"]["id"] == rule["id"]
    assert await _plan_version(client, demo_stage) == 1
    assert len(analysis.signals) == 1


async def test_минимум_сессий_по_умолчанию_из_базы(client, demo_stage):
    body = {k: v for k, v in PIT_RULE.items() if k != "min_sessions"}

    rule = (await client.post(RULES, json=body | {"stage_id": demo_stage["stage_id"]})).json()

    assert rule["min_sessions"] == 2


async def test_второе_правило_у_этапа_это_конфликт(client, demo_stage):
    await _create(client, demo_stage)

    response = await _create(client, demo_stage)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STAGE_RULE_ALREADY_EXISTS"


async def test_неизвестный_класс_техники_отклоняется(client, demo_stage, analysis):
    response = await _create(client, demo_stage, allowed=["ekskavator"])

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "UNKNOWN_EQUIPMENT_CLASS"
    assert error["details"]["unknown"] == ["ekskavator"]
    assert analysis.signals == []


async def test_повтор_класса_в_группе_отклоняется(client, demo_stage):
    response = await _create(
        client, demo_stage, required=[{"any_of": ["loader", "loader"], "min": 1}]
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "STAGE_RULE_INVALID"


async def test_пустая_группа_и_неизвестная_стадия_не_проходят_схему(client, demo_stage):
    empty = await _create(client, demo_stage, required=[{"any_of": [], "min": 1}])
    label = await _create(
        client, demo_stage, signature={"equipment": [], "stage_label": "SPACEPORT"}
    )

    assert (empty.status_code, label.status_code) == (422, 422)


async def test_правило_для_несуществующего_этапа(client):
    response = await client.post(
        RULES, json=PIT_RULE | {"stage_id": "00000000-0000-0000-0000-000000000000"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "STAGE_NOT_FOUND"


async def test_правка_правила_поднимает_версии_и_шлёт_сигнал(client, demo_stage, analysis):
    rule = (await _create(client, demo_stage)).json()

    response = await client.patch(
        f"{RULES}/{rule['id']}",
        json={
            "required": [{"any_of": ["excavator"], "min": 1}, {"any_of": ["dump_truck"], "min": 1}]
        },
        headers={"X-Actor": "%D0%98%D0%B2%D0%B0%D0%BD"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 2
    assert body["required"][1]["min"] == 1
    assert body["allowed"] == PIT_RULE["allowed"]
    assert await _plan_version(client, demo_stage) == 2
    assert [str(s) for s in analysis.signals] == [demo_stage["object"]["id"]] * 2


async def test_правка_с_опечаткой_не_меняет_правило(client, demo_stage):
    rule = (await _create(client, demo_stage)).json()

    response = await client.patch(
        f"{RULES}/{rule['id']}", json={"signature": {"equipment": ["crane"]}}
    )

    assert response.status_code == 400
    assert (await client.get(f"{RULES}/{rule['id']}")).json()["version"] == 1


async def test_фильтр_по_объекту_и_этапу(client, demo_stage):
    rule = (await _create(client, demo_stage)).json()

    by_object = (await client.get(RULES, params={"object_id": demo_stage["object"]["id"]})).json()
    by_stage = (await client.get(RULES, params={"stage_id": demo_stage["stage_id"]})).json()

    assert [r["id"] for r in by_object["items"]] == [rule["id"]]
    assert by_stage["total"] == 1


async def test_удаление_правила_оставляет_этап_без_правила(client, demo_stage, analysis):
    rule = (await _create(client, demo_stage)).json()

    assert (await client.delete(f"{RULES}/{rule['id']}")).status_code == 204

    missing = await client.get(f"{RULES}/{rule['id']}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "STAGE_RULE_NOT_FOUND"
    stages = (await client.get(f"{OBJECTS}/{demo_stage['object']['id']}/stages")).json()
    assert stages["items"][0]["rule"] is None
    assert await _plan_version(client, demo_stage) == 2
