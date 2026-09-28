"""API этапов: список объекта, правка, рост plan_version и сигнал «пересчитай»."""

OBJECTS = "/api/v1/plan/objects"
STAGES = "/api/v1/plan/stages"


async def test_этапы_объекта_в_формате_страницы(client, demo_stage):
    object_id = demo_stage["object"]["id"]

    body = (await client.get(f"{OBJECTS}/{object_id}/stages")).json()

    assert body["total"] == 1
    stage = body["items"][0]
    assert stage["id"] == demo_stage["stage_id"]
    assert (stage["zone_type"], stage["visual_stage"]) == ("PIT", "PIT")
    assert stage["predecessors"] == []


async def test_этапы_несуществующего_объекта(client):
    response = await client.get(f"{OBJECTS}/00000000-0000-0000-0000-000000000000/stages")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "OBJECT_NOT_FOUND"


async def test_правка_дат_поднимает_версию_и_шлёт_сигнал(client, demo_stage, analysis):
    object_id = demo_stage["object"]["id"]

    response = await client.patch(
        f"{STAGES}/{demo_stage['stage_id']}",
        json={"plan_end": "2026-11-27", "visual_stage": None},
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["plan_end"], body["visual_stage"]) == ("2026-11-27", None)
    assert (await client.get(f"{OBJECTS}/{object_id}")).json()["plan_version"] == 1
    assert [str(s) for s in analysis.signals] == [object_id]


async def test_конец_раньше_начала_отклоняется(client, demo_stage, analysis):
    response = await client.patch(
        f"{STAGES}/{demo_stage['stage_id']}", json={"plan_end": "2026-10-01"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_DATE_RANGE"
    assert analysis.signals == []


async def test_этап_не_переносится_на_въезд(client, demo_stage):
    response = await client.patch(
        f"{STAGES}/{demo_stage['stage_id']}", json={"zone_type": "ENTRY_GATE"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ZONE_TYPE"


async def test_нулевая_длительность_не_проходит_схему(client, demo_stage):
    response = await client.patch(
        f"{STAGES}/{demo_stage['stage_id']}", json={"norm_duration_days": 0}
    )

    assert response.status_code == 422


async def test_отметка_выполнения_с_автором_попадает_в_весь_план(client, demo_stage, analysis):
    object_id = demo_stage["object"]["id"]

    response = await client.patch(
        f"{STAGES}/{demo_stage['stage_id']}",
        json={"completed_on": "2026-11-18", "completion_note": "акт приёмки №7"},
        headers={"X-Actor": "%D0%98%D0%B2%D0%B0%D0%BD"},
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["completed_on"], body["completed_by"], body["completion_note"]) == (
        "2026-11-18",
        "Иван",
        "акт приёмки №7",
    )
    stage = (await client.get(f"{OBJECTS}/{object_id}/plan")).json()["stages"][0]
    assert (stage["completed_on"], stage["completed_by"]) == ("2026-11-18", "Иван")
    assert [str(s) for s in analysis.signals] == [object_id]


async def test_снятие_отметки_уносит_автора_и_комментарий(client, demo_stage):
    url = f"{STAGES}/{demo_stage['stage_id']}"
    await client.patch(url, json={"completed_on": "2026-11-18", "completion_note": "акт"})

    body = (await client.patch(url, json={"completed_on": None})).json()

    assert (body["completed_on"], body["completed_by"], body["completion_note"]) == (None,) * 3


async def test_комментарий_без_отметки_отклоняется(client, demo_stage, analysis):
    response = await client.patch(
        f"{STAGES}/{demo_stage['stage_id']}", json={"completion_note": "акт"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_COMPLETION"
    assert analysis.signals == []


async def test_несуществующий_этап(client):
    response = await client.patch(
        f"{STAGES}/00000000-0000-0000-0000-000000000000", json={"plan_end": "2026-11-27"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "STAGE_NOT_FOUND"
