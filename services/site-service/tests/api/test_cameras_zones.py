"""Камеры, зоны и участки через API; импорт разметки в формате data/seed/cameras.json."""

import copy

SITE = "/api/v1/site"
OBJECT_ID = "11111111-1111-4111-8111-111111111111"
# Пример из data/README.md: въезд размечен на обеих камерах, склад — только на камере въезда.
DEMO = {
    "object_id": OBJECT_ID,
    "cameras": [
        {
            "code": "cam-north",
            "name": "Северная обзорная",
            "reference_image": "cam-north/20261020_090000.jpg",
            "zones": [
                {
                    "zone_type": "PIT",
                    "name": "Котлован",
                    "polygon": [[0.09, 0.47], [0.30, 0.43], [0.33, 0.68], [0.08, 0.71]],
                },
                {
                    "zone_type": "ENTRY_GATE",
                    "name": "Въезд",
                    "polygon": [[0.35, 0.48], [0.46, 0.44], [0.46, 0.74], [0.36, 0.74]],
                },
            ],
        },
        {
            "code": "cam-gate",
            "name": "Камера на въезд",
            "reference_image": "cam-gate/20261020_090000.jpg",
            "zones": [
                {
                    "zone_type": "ENTRY_GATE",
                    "name": "Въезд",
                    "polygon": [[0.04, 0.45], [0.62, 0.40], [0.64, 0.95], [0.02, 0.95]],
                },
                {
                    "zone_type": "STORAGE",
                    "name": "Склад",
                    "polygon": [[0.68, 0.35], [0.97, 0.33], [0.98, 0.80], [0.70, 0.82]],
                },
            ],
        },
    ],
}
SQUARE = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]


async def _import(client, body=DEMO):
    return await client.post(f"{SITE}/zones/import", json=body)


def _areas(result) -> dict[str, list[str]]:
    return {a["area"]: sorted(c["camera_code"] for c in a["cameras"]) for a in result["areas"]}


async def _camera(client, code="cam-1") -> dict:
    response = await client.post(f"{SITE}/cameras", json={"object_id": OBJECT_ID, "code": code})
    return response.json()


async def test_импорт_демо_разметки_даёт_участок_въезда_на_двух_камерах(client):
    response = await _import(client)

    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["cameras_created"], result["zones_created"], result["zones_version"]) == (
        2,
        4,
        4,
    )
    assert _areas(result) == {
        "ENTRY_GATE:Въезд": ["cam-gate", "cam-north"],
        "PIT:Котлован": ["cam-north"],
        "STORAGE:Склад": ["cam-gate"],
    }
    roles = {a["area"]: a["role"] for a in result["areas"]}
    assert roles["PIT:Котлован"] == "WORK" and roles["ENTRY_GATE:Въезд"] == "SERVICE"
    areas = (await client.get(f"{SITE}/objects/{OBJECT_ID}/areas")).json()
    assert _areas(areas) == _areas(result)


async def test_повторный_импорт_ничего_не_меняет(client):
    await _import(client)

    again = (await _import(client)).json()

    assert (again["zones_created"], again["zones_unchanged"], again["zones_version"]) == (0, 4, 4)


async def test_импорт_правит_и_деактивирует_зоны_и_растит_версию(client):
    await _import(client)
    changed = copy.deepcopy(DEMO)
    north = changed["cameras"][0]
    north["zones"][0]["polygon"] = SQUARE  # котлован переразмечен
    del north["zones"][1]  # въезд с северной камеры больше не виден

    result = (await _import(client, changed)).json()

    assert (result["zones_updated"], result["zones_deactivated"], result["zones_version"]) == (
        1,
        1,
        6,
    )
    assert _areas(result)["ENTRY_GATE:Въезд"] == ["cam-gate"]


async def test_ошибки_полигонов_собираются_по_всему_файлу(client):
    broken = copy.deepcopy(DEMO)
    broken["cameras"][0]["zones"][0]["polygon"] = [[0, 0], [1920, 0], [1920, 1080]]
    broken["cameras"][1]["zones"][1]["polygon"] = [[0, 0], [1, 1]]

    response = await _import(client, broken)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "INVALID_POLYGON"
    assert [e["path"] for e in error["details"]["errors"]] == [
        "cameras[0].zones[0].polygon",
        "cameras[1].zones[1].polygon",
    ]
    assert (await client.get(f"{SITE}/objects/{OBJECT_ID}/areas")).json()["areas"] == []


async def test_камера_заводится_правится_и_деактивируется_вместе_с_зонами(client):
    camera = await _camera(client)
    zone = (
        await client.post(
            f"{SITE}/zones", json={"camera_id": camera["id"], "zone_type": "PIT", "polygon": SQUARE}
        )
    ).json()

    duplicate = await client.post(f"{SITE}/cameras", json={"object_id": OBJECT_ID, "code": "cam-1"})
    renamed = await client.patch(f"{SITE}/cameras/{camera['id']}", json={"name": "Юг"})
    no_image = await client.patch(
        f"{SITE}/cameras/{camera['id']}",
        json={"reference_image_id": "22222222-2222-4222-8222-222222222222"},
    )
    deleted = await client.delete(f"{SITE}/cameras/{camera['id']}")

    assert camera["name"] == "cam-1"  # название по умолчанию — код
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "CAMERA_ALREADY_EXISTS"
    assert renamed.json()["name"] == "Юг"
    assert no_image.status_code == 404
    assert no_image.json()["error"]["code"] == "IMAGE_NOT_FOUND"
    assert deleted.status_code == 204
    assert (await client.get(f"{SITE}/cameras/{camera['id']}")).json()["is_active"] is False
    zone_after = (await client.get(f"{SITE}/zones/{zone['id']}")).json()
    assert (zone_after["is_active"], zone_after["version"]) == (False, 2)


async def test_зона_с_названием_по_умолчанию_и_версией(client):
    camera = await _camera(client)
    created = await client.post(
        f"{SITE}/zones", json={"camera_id": camera["id"], "zone_type": "PIT", "polygon": SQUARE}
    )
    zone = created.json()
    url = f"{SITE}/zones/{zone['id']}"

    same = (await client.patch(url, json={"polygon": SQUARE})).json()
    moved = (await client.patch(url, json={"polygon": [[0, 0], [0.4, 0], [0.4, 0.4]]})).json()
    await client.delete(url)

    assert created.status_code == 201
    assert (zone["name"], zone["area"], zone["version"]) == ("Котлован", "PIT:Котлован", 1)
    assert same["version"] == 1  # правка без изменений версию не поднимает
    assert moved["version"] == 2
    active = (await client.get(f"{SITE}/zones", params={"camera_id": camera["id"]})).json()
    everything = (
        await client.get(
            f"{SITE}/zones", params={"camera_id": camera["id"], "include_inactive": True}
        )
    ).json()
    assert (active["total"], everything["items"][0]["version"]) == (0, 3)


async def test_ошибки_создания_зоны(client):
    camera = await _camera(client)

    pixels = await client.post(
        f"{SITE}/zones",
        json={
            "camera_id": camera["id"],
            "zone_type": "PIT",
            "polygon": [[0, 0], [800, 0], [0, 600]],
        },
    )
    unknown_type = await client.post(
        f"{SITE}/zones", json={"camera_id": camera["id"], "zone_type": "LAKE", "polygon": SQUARE}
    )
    no_camera = await client.post(
        f"{SITE}/zones", json={"camera_id": OBJECT_ID, "zone_type": "PIT", "polygon": SQUARE}
    )

    assert (pixels.status_code, pixels.json()["error"]["code"]) == (400, "INVALID_POLYGON")
    assert unknown_type.status_code == 422
    assert (no_camera.status_code, no_camera.json()["error"]["code"]) == (404, "CAMERA_NOT_FOUND")
    missing = await client.get(f"{SITE}/zones/{OBJECT_ID}")
    assert missing.json()["error"]["code"] == "ZONE_NOT_FOUND"
