"""«Весь план»: форма строго по контракту 1, выключенное правило, критический путь."""

from datetime import date
from uuid import UUID

import pytest

OBJECTS = "/api/v1/plan/objects"

# Ключи из примера interservice.md, раздел 1 (и фикстуры analysis-service tests/fixtures/plan.json).
PLAN_KEYS = {"object", "plan_version", "calendar", "equipment_classes", "stages"}
OBJECT_KEYS = {"id", "name", "object_type", "plan_start"}
CALENDAR_KEYS = {"code", "timezone", "weekend_days", "holidays", "work_hours"}
CLASS_KEYS = {"code", "name_ru", "group", "transient", "works_in_place"}
STAGE_KEYS = {
    "id", "code", "name", "phase", "seq", "work_codes", "zone_type", "visual_stage",
    "plan_start", "plan_end", "norm_duration_days", "predecessors", "is_critical",
    "total_float_days", "basis", "rule", "completed_on", "completed_by", "completion_note",
}  # fmt: skip
RULE_KEYS = {"id", "version", "required", "allowed", "signature", "min_sessions"}


@pytest.fixture
async def two_stages(client, session, demo_stage) -> dict:
    """К котловану из demo_stage — плита FS после него и параллельный короткий этап."""
    from src.dal.models import Stage

    pit = UUID(demo_stage["stage_id"])
    object_id = UUID(demo_stage["object"]["id"])
    common = {
        "object_id": object_id,
        "phase": "SUBSTRUCTURE",
        "zone_type": "PIT",
        "source": "IMPORT",
    }
    slab = Stage(
        **common, code="12.3.4", name="Фундаментная плита", seq=2, visual_stage="FOUNDATION",
        plan_start=date(2026, 11, 21), plan_end=date(2026, 12, 18), norm_duration_days=24,
        predecessors=[{"stage_id": str(pit), "type": "FS", "lag_days": 0}],
    )  # fmt: skip
    side = Stage(
        **common, code="12.3.2", name="Сваи", seq=3, plan_start=date(2026, 11, 21),
        plan_end=date(2026, 11, 23), norm_duration_days=3,
        predecessors=[{"stage_id": str(pit), "type": "FS", "lag_days": 0}],
    )  # fmt: skip
    session.add_all([slab, side])
    await session.flush()
    rule = {
        "required": [{"any_of": ["excavator"], "min": 1}, {"any_of": ["dump_truck"], "min": 2}],
        "allowed": ["bulldozer"],
        "signature": {"equipment": ["excavator", "dump_truck"]},
    }
    await client.post("/api/v1/plan/rules", json=rule | {"stage_id": demo_stage["stage_id"]})
    await client.post(
        "/api/v1/plan/rules", json=rule | {"stage_id": str(slab.id), "is_active": False}
    )
    return demo_stage | {"slab_id": str(slab.id), "side_id": str(side.id)}


async def test_весь_план_по_форме_контракта(client, two_stages):
    plan = (await client.get(f"{OBJECTS}/{two_stages['object']['id']}/plan")).json()

    assert set(plan) == PLAN_KEYS
    assert set(plan["object"]) == OBJECT_KEYS
    assert set(plan["calendar"]) == CALENDAR_KEYS
    assert plan["calendar"]["code"] == "moscow-6day"
    assert "2026-11-04" in plan["calendar"]["holidays"]
    assert all(set(c) == CLASS_KEYS for c in plan["equipment_classes"])
    assert [s["seq"] for s in plan["stages"]] == [1, 2, 3]
    assert all(set(s) == STAGE_KEYS for s in plan["stages"])
    pit = plan["stages"][0]
    assert set(pit["rule"]) == RULE_KEYS
    assert pit["rule"]["signature"] == {
        "equipment": ["excavator", "dump_truck"],
        "stage_label": None,
    }
    assert plan["plan_version"] == 2  # два правила — две правки плана


async def test_выключенное_правило_приходит_как_null(client, two_stages):
    plan = (await client.get(f"{OBJECTS}/{two_stages['object']['id']}/plan")).json()

    assert plan["stages"][1]["rule"] is None


async def test_объект_без_этапов_не_ошибка(client):
    created = (await client.post(OBJECTS, json={"name": "Жилой дом без графика"})).json()

    plan = (await client.get(f"{OBJECTS}/{created['id']}/plan")).json()

    assert plan["stages"] == []
    assert plan["plan_version"] == 0


async def test_весь_план_несуществующего_объекта(client):
    response = await client.get(f"{OBJECTS}/00000000-0000-0000-0000-000000000000/plan")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "OBJECT_NOT_FOUND"


async def test_правка_даты_пересчитывает_критический_путь(client, two_stages):
    """Котлован кончается 20.11 (пятница), следующий этап — 21.11: шестидневка, резерва нет.

    Сдвиг конца котлована на 19.11 даёт ему день резерва; короткие сваи с резервом всегда.
    """
    response = await client.patch(
        f"/api/v1/plan/stages/{two_stages['stage_id']}", json={"plan_end": "2026-11-19"}
    )

    assert response.status_code == 200
    assert (response.json()["total_float_days"], response.json()["is_critical"]) == (1, False)
    stages = (await client.get(f"{OBJECTS}/{two_stages['object']['id']}/plan")).json()["stages"]
    slab, side = stages[1], stages[2]
    assert (slab["is_critical"], slab["total_float_days"]) == (True, 0)
    assert side["is_critical"] is False and side["total_float_days"] > 0
