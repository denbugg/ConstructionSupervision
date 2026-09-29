"""API классов техники: список совпадает с equipment_classes.yaml."""

import yaml

from tests.conftest import CONTRACTS_DIR

BASE = "/api/v1/plan/equipment-classes"
FILE = yaml.safe_load((CONTRACTS_DIR / "equipment_classes.yaml").read_text(encoding="utf-8"))


async def test_список_классов_совпадает_с_файлом(client):
    body = (await client.get(BASE, params={"limit": 200})).json()

    assert body["total"] == len(FILE["equipment_classes"])
    assert [c["code"] for c in body["items"]] == [c["code"] for c in FILE["equipment_classes"]]
    first = body["items"][0]
    assert set(first) == {
        "code",
        "name_ru",
        "group",
        "transient",
        "works_in_place",
        "prompts",
        "aliases",
    }


async def test_фильтр_по_группе_и_транзиту(client):
    lifting = (await client.get(BASE, params={"group": "LIFTING"})).json()["items"]
    transient = (await client.get(BASE, params={"transient": True})).json()["items"]

    assert {c["group"] for c in lifting} == {"LIFTING"}
    assert {c["code"] for c in transient} == {
        c["code"] for c in FILE["equipment_classes"] if c["transient"]
    }


async def test_неизвестная_группа_не_проходит_схему(client):
    response = await client.get(BASE, params={"group": "SPACESHIPS"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SCHEMA_VALIDATION_FAILED"


async def test_тип_объекта_проверяется_по_enums(client):
    response = await client.post(
        "/api/v1/plan/objects", json={"name": "Жилой дом, корпус 1", "object_type": "SPACEPORT"}
    )

    assert response.status_code == 422
