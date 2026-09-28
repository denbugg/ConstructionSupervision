"""API ленты отклонений: фильтры, карточка, объяснение, вердикт (T16b).

Лента — после прогона по четырём демо-дням: D2 (день 1) и D3 (день 2) закрыты,
D4 и D10 (день 3) открыты.
"""

from urllib.parse import quote

from src.clients.site_client import SiteServiceUnavailable
from src.config import settings

from tests.conftest import DEMO_OBJECT_ID

BASE = "/api/v1/analysis/deviations"


async def _list(client, **params):
    response = await client.get(BASE, params={"object_id": DEMO_OBJECT_ID, **params})
    assert response.status_code == 200, response.text
    return response.json()


async def _one(client, code):
    (item,) = (await _list(client, code=code))["items"]
    return item


async def _rerun(client):
    await client.post(
        "/api/v1/analysis/runs", json={"object_id": DEMO_OBJECT_ID}, params={"wait": True}
    )


async def test_лента_объекта_страницей_свежие_сверху(client, analyzed):
    body = await _list(client)

    assert (body["total"], body["limit"], body["offset"]) == (4, 50, 0)
    assert [i["code"] for i in body["items"]][-2:] == ["D3", "D2"]
    assert all(i["facts"] and i["title"] and i["message"] for i in body["items"])


async def test_фильтр_по_статусу_и_нескольким_серьёзностям(client, analyzed):
    open_items = (await _list(client, status="NEW"))["items"]
    minor = await client.get(BASE, params=[("severity", "LOW"), ("severity", "INFO")])

    assert {i["code"] for i in open_items} == {"D4", "D10"}
    assert {i["code"] for i in minor.json()["items"]} == {"D4", "D10"}


async def test_фильтр_по_периоду_берёт_пересекающиеся_эпизоды(client, analyzed):
    body = await _list(client, **{"from": "2026-10-21", "to": "2026-10-22"})

    assert [i["code"] for i in body["items"]] == ["D3"]


async def test_фильтр_по_участку(client, analyzed):
    body = await _list(client, area="STORAGE:Склад")

    assert [i["code"] for i in body["items"]] == ["D10"]


async def test_сортировка_по_серьёзности_в_порядке_enums(client, analyzed):
    ascending = [i["severity"] for i in (await _list(client, sort="severity"))["items"]]
    descending = [i["severity"] for i in (await _list(client, sort="-severity"))["items"]]

    assert ascending == ["INFO", "LOW", "MEDIUM", "MEDIUM"]
    assert descending[:2] == ["MEDIUM", "MEDIUM"]


async def test_неизвестный_фильтр_и_сортировка_отклоняются(client, analyzed):
    for params in ({"severity": "CRITICAL"}, {"status": "OPEN"}, {"sort": "title"}):
        response = await client.get(BASE, params=params)

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_карточка_отклонения(client, analyzed):
    d4 = await _one(client, "D4")

    body = (await client.get(f"{BASE}/{d4['id']}")).json()

    assert body == d4
    assert body["equipment_class"] == "excavator" and body["evidence"]


async def test_неизвестное_отклонение_это_404(client):
    response = await client.get(f"{BASE}/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DEVIATION_NOT_FOUND"


async def test_объяснение_правило_сессии_эпизода_и_снимки(client, analyzed):
    d4 = await _one(client, "D4")

    body = (await client.get(f"{BASE}/{d4['id']}/explain")).json()

    assert body["deviation"]["id"] == d4["id"]
    assert body["rule"]["code"] == "D4" and body["rule"]["params"]["min_sessions"] == 3
    # День 3: 12 сессий, в каждой — только участок отклонения.
    assert len(body["sessions"]) == 12 and body["sessions_truncated"] is False
    assert {a["area"] for s in body["sessions"] for a in s["areas"]} == {"ENTRY_GATE:Въезд"}
    evidence = body["evidence"][0]
    assert evidence["image_path"] == f"/api/v1/site/images/{evidence['image_id']}"


async def test_объяснение_показывает_последние_сессии_длинного_эпизода(
    client, analyzed, monkeypatch
):
    monkeypatch.setattr(settings, "explain_max_sessions", 5)
    d4 = await _one(client, "D4")

    body = (await client.get(f"{BASE}/{d4['id']}/explain")).json()

    assert len(body["sessions"]) == 5 and body["sessions_truncated"] is True
    assert body["sessions"][-1]["window_start"] == "2026-10-22T11:30:00Z"


async def test_объяснение_без_site_service_честно_говорит_не_знаю(client, upstream, analyzed):
    d10 = await _one(client, "D10")
    upstream.site.error = SiteServiceUnavailable("site-service недоступен")

    response = await client.get(f"{BASE}/{d10['id']}/explain")

    assert response.status_code == 200
    body = response.json()
    assert body["sessions"] is None and body["sessions_unavailable_reason"]
    assert body["deviation"]["facts"]["reason"] == "DARK"


async def test_отклонённое_оператором_остаётся_отклонённым(client, analyzed):
    d4 = await _one(client, "D4")

    response = await client.patch(
        f"{BASE}/{d4['id']}",
        json={"status": "REJECTED", "comment": "Экскаватор ждёт трал, простой согласован"},
        headers={"X-Actor": quote("Иванова А. П.")},
    )
    await _rerun(client)

    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["verdict_by"]) == ("REJECTED", "Иванова А. П.")
    assert body["verdict_comment"] and body["verdict_at"]
    after = await _one(client, "D4")
    assert after["id"] == d4["id"] and after["status"] == "REJECTED"


async def test_подтверждённое_остаётся_подтверждённым(client, analyzed):
    d10 = await _one(client, "D10")

    await client.patch(f"{BASE}/{d10['id']}", json={"status": "CONFIRMED"})
    await _rerun(client)

    assert (await _one(client, "D10"))["status"] == "CONFIRMED"


async def test_закрытому_отклонению_вердикт_ставится_статус_остаётся(client, analyzed):
    """Методика, раздел 9, правило 3: «да, это было» — вердикт, а не новое открытое."""
    d2 = await _one(client, "D2")
    assert d2["status"] == "RESOLVED"

    response = await client.patch(
        f"{BASE}/{d2['id']}", json={"status": "CONFIRMED", "comment": "было"}
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["verdict"], body["verdict_comment"]) == (
        "RESOLVED",
        "CONFIRMED",
        "было",
    )
    await _rerun(client)
    after = await _one(client, "D2")
    assert (after["status"], after["verdict"]) == ("RESOLVED", "CONFIRMED")


async def test_фильтр_по_вердикту_находит_и_открытые_и_закрытые(client, analyzed):
    d2, d10 = await _one(client, "D2"), await _one(client, "D10")
    await client.patch(f"{BASE}/{d2['id']}", json={"status": "REJECTED"})
    await client.patch(f"{BASE}/{d10['id']}", json={"status": "REJECTED"})

    rejected = (await _list(client, verdict="REJECTED"))["items"]
    by_status = (await _list(client, status="REJECTED"))["items"]
    bad = await client.get(BASE, params={"verdict": "RESOLVED"})

    assert {(i["code"], i["status"]) for i in rejected} == {("D2", "RESOLVED"), ("D10", "REJECTED")}
    assert [i["code"] for i in by_status] == ["D10"]
    assert (await _list(client, verdict="CONFIRMED"))["total"] == 0
    assert bad.status_code == 400


async def test_вердикт_открытого_пишется_и_в_статус_и_в_поле(client, analyzed):
    d10 = await _one(client, "D10")

    body = (await client.patch(f"{BASE}/{d10['id']}", json={"status": "REJECTED"})).json()

    assert (body["status"], body["verdict"]) == ("REJECTED", "REJECTED")


async def test_вердикт_только_подтвердить_или_отклонить(client, analyzed):
    d4 = await _one(client, "D4")

    response = await client.patch(f"{BASE}/{d4['id']}", json={"status": "RESOLVED"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_VERDICT"
    assert (await _one(client, "D4"))["status"] == "NEW"
