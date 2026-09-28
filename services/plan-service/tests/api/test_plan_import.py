"""Импорт графика через API: демо-график даёт «весь план» как в фикстуре analysis (T06)."""

from tests.conftest import SERVICE_ROOT

OBJECTS = "/api/v1/plan/objects"
DEMO = (SERVICE_ROOT / "tests/fixtures/demo_schedule.csv").read_bytes()


async def _object(client) -> str:
    created = await client.post(OBJECTS, json={"name": "Монолитный жилой дом, 17 этажей, 2 секции"})
    return created.json()["id"]


async def _import(client, object_id, content=DEMO, name="demo.csv", **params):
    return await client.post(
        f"{OBJECTS}/{object_id}/plan/import",
        files={"file": (name, content, "text/csv")},
        params=params,
    )


async def test_демо_график_даёт_весь_план_как_фикстура_analysis(client, analysis):
    object_id = await _object(client)

    response = await _import(client, object_id)

    assert response.status_code == 200, response.text
    assert response.json() | {"object_id": None} == {
        "object_id": None,
        "plan_version": 1,
        "stages": 3,
        "rules": 3,
        "critical_stages": 3,
    }
    assert [str(s) for s in analysis.signals] == [object_id]
    plan = (await client.get(f"{OBJECTS}/{object_id}/plan")).json()
    assert plan["object"]["plan_start"] == "2026-09-21"  # начало СМР — по первому этапу
    prep, pit, slab = plan["stages"]
    # Значения — как в services/analysis-service/tests/fixtures/plan.json.
    assert [(s["code"], s["plan_start"], s["plan_end"], s["norm_duration_days"]) for s in plan["stages"]] == [
        ("10.4-10.8", "2026-09-21", "2026-10-14", 21),
        ("12.3.1", "2026-10-15", "2026-11-20", 31),
        ("12.3.4", "2026-11-21", "2026-12-18", 24),
    ]  # fmt: skip
    assert (prep["zone_type"], pit["zone_type"], slab["visual_stage"]) == (
        "BUILDING_FOOTPRINT",
        "PIT",
        "FOUNDATION",
    )
    assert pit["predecessors"] == [{"stage_id": prep["id"], "type": "FS", "lag_days": 0}]
    assert all(s["is_critical"] and s["total_float_days"] == 0 for s in plan["stages"])
    assert pit["rule"]["required"] == [
        {"any_of": ["excavator"], "min": 1},
        {"any_of": ["dump_truck"], "min": 2},
    ]
    assert slab["rule"]["signature"] == {
        "equipment": ["concrete_mixer", "concrete_pump"],
        "stage_label": None,
    }
    assert pit["rule"]["min_sessions"] == 2


async def test_повторный_импорт_только_с_force(client):
    object_id = await _object(client)
    await _import(client, object_id)

    refused = await _import(client, object_id)
    forced = await _import(client, object_id, force=True)

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "PLAN_ALREADY_EXISTS"
    assert forced.status_code == 200
    assert forced.json()["plan_version"] == 2
    stages = (await client.get(f"{OBJECTS}/{object_id}/stages")).json()
    assert stages["total"] == 3  # старый график заменён, а не дополнен


async def test_ошибка_импорта_называет_строку_и_ничего_не_меняет(client, analysis):
    object_id = await _object(client)
    bad = "код;наименование;начало;окончание\n12.3.1;Котлован;2026-10-20;2026-10-19\n"

    response = await _import(client, object_id, bad.encode())

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "PLAN_IMPORT_INVALID"
    assert error["message"].startswith("строка 2")
    assert error["details"]["errors"] == [
        {"row": 2, "column": "окончание", "message": error["details"]["errors"][0]["message"]}
    ]
    assert (await client.get(f"{OBJECTS}/{object_id}/plan")).json()["stages"] == []
    assert analysis.signals == []


async def test_неподдерживаемый_формат_файла(client):
    object_id = await _object(client)

    response = await _import(client, object_id, b"%PDF", name="plan.pdf")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PLAN_IMPORT_INVALID"


async def test_импорт_в_несуществующий_объект(client):
    response = await _import(client, "00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
