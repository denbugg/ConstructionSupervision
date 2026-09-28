"""Генерация графика по МРР через API: демо-объект, параметры, force, нет норм."""

OBJECTS = "/api/v1/plan/objects"
DEMO_TEP = {"floors": 17, "total_area": 10000, "sections": 2, "piles": 200}


async def _object(client, **fields) -> str:
    body = {"name": "Монолитный жилой дом, 17 этажей, 2 секции"} | fields
    return (await client.post(OBJECTS, json=body)).json()["id"]


async def _generate(client, object_id, body=None, **params):
    return await client.post(f"{OBJECTS}/{object_id}/plan/generate", json=body, params=params)


async def test_демо_объект_получает_график_по_мрр(client, analysis):
    object_id = await _object(client)

    response = await _generate(client, object_id, {"tep": DEMO_TEP, "start_date": "2026-09-21"})

    assert response.status_code == 200, response.text
    result = response.json()
    assert {k: result[k] for k in ("plan_version", "stages", "rules", "total_months")} == {
        "plan_version": 1,
        "stages": 12,
        "rules": 12,
        "total_months": 8.7,
    }
    # Календарь moscow-6day со всеми праздниками ТК РФ, ст. 112 — не только 4 ноября.
    assert (result["plan_start"], result["plan_end"]) == ("2026-09-21", "2027-06-21")
    assert "стр. 1.18" in result["basis"]
    assert [str(s) for s in analysis.signals] == [object_id]
    obj = (await client.get(f"{OBJECTS}/{object_id}")).json()
    assert (obj["tep"], obj["plan_start"]) == (DEMO_TEP, "2026-09-21")
    plan = (await client.get(f"{OBJECTS}/{object_id}/plan")).json()
    pit = next(s for s in plan["stages"] if s["code"] == "12.3.1")
    assert pit["basis"].startswith("МРР-3.2.81-12")
    assert pit["rule"]["required"][1] == {"any_of": ["dump_truck"], "min": 2}
    assert any(s["is_critical"] for s in plan["stages"])


async def test_без_тела_берёт_параметры_и_дату_из_объекта(client):
    object_id = await _object(client, tep=DEMO_TEP | {"piles": 0}, plan_start="2026-09-21")

    response = await _generate(client, object_id)

    assert response.status_code == 200, response.text
    assert response.json()["stages"] == 11  # без свай этап свай выпадает


async def test_повторная_генерация_только_с_force(client):
    object_id = await _object(client, tep=DEMO_TEP, plan_start="2026-09-21")
    await _generate(client, object_id)

    refused = await _generate(client, object_id)
    forced = await _generate(client, object_id, {"tep": {"shifts": 2}}, force=True)

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "PLAN_ALREADY_EXISTS"
    assert forced.status_code == 200
    assert (forced.json()["plan_version"], forced.json()["total_months"]) == (2, 7.83)


async def test_нет_параметров_или_даты_начала(client, analysis):
    no_tep = await _object(client, plan_start="2026-09-21")
    no_start = await _object(client, tep=DEMO_TEP)

    params = await _generate(client, no_tep)
    start = await _generate(client, no_start)

    assert params.status_code == start.status_code == 400
    assert params.json()["error"]["code"] == "GENERATOR_PARAMS_INVALID"
    assert "floors" in params.json()["error"]["message"]
    assert start.json()["error"]["code"] == "GENERATOR_PARAMS_INVALID"
    assert analysis.signals == []


async def test_нет_норм_для_типа_или_параметров(client):
    road = await _object(client, object_type="ROAD", tep=DEMO_TEP, plan_start="2026-09-21")
    tall = await _object(client, tep=DEMO_TEP | {"floors": 30}, plan_start="2026-09-21")

    for object_id in (road, tall):
        response = await _generate(client, object_id)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "NORMS_NOT_AVAILABLE"
    assert (await client.get(f"{OBJECTS}/{tall}/plan")).json()["stages"] == []
