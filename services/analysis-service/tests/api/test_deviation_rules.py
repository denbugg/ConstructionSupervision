"""API настроек правил отклонений: чтение, правка, проверка (T16a)."""

from urllib.parse import quote

from src.api.deps import get_actor

from tests.factories import load_facts

BASE = "/api/v1/analysis/deviation-rules"
OBJECT_ID = "0f3a6c1e-8d4b-4c2a-9e71-5b0d2f6a8c31"


async def test_список_правил_d1_d10_по_порядку(client, seeded_rules):
    body = (await client.get(BASE)).json()

    assert body["total"] == 10
    assert [r["code"] for r in body["items"]] == [f"D{i}" for i in range(1, 11)]


async def test_список_правил_постранично(client, seeded_rules):
    body = (await client.get(BASE, params={"limit": 3, "offset": 9})).json()

    assert [r["code"] for r in body["items"]] == ["D10"]
    assert (body["total"], body["limit"], body["offset"]) == (10, 3, 9)


async def test_одно_правило(client, seeded_rules):
    body = (await client.get(f"{BASE}/D4")).json()

    assert body["predicate"] == "idle_equipment"
    assert body["params"]["min_sessions"] == 3


async def test_правка_сливает_параметры_и_не_трогает_остальное(client, seeded_rules):
    response = await client.patch(
        f"{BASE}/D4",
        json={"severity": "MEDIUM", "params": {"min_sessions": 5, "escalate_to": None}},
        # Заголовки HTTP — ASCII: имя по-русски приходит в URL-кодировке.
        headers={"X-Actor": quote("Иванова А. П.")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["severity"] == "MEDIUM"
    assert body["params"] == {"min_sessions": 5, "escalate_after_days": 1}
    assert body["message_template"] == (await client.get(f"{BASE}/D4")).json()["message_template"]


async def test_выключенное_правило_не_срабатывает_в_следующем_прогоне(
    client, upstream, seeded_rules
):
    await client.patch(f"{BASE}/D2", json={"enabled": False})
    upstream.site.facts = load_facts("facts_day1.json")

    run = (
        await client.post(
            "/api/v1/analysis/runs", json={"object_id": OBJECT_ID}, params={"wait": True}
        )
    ).json()

    assert run["stats"]["deviations_found"] == 0


async def test_испорченная_настройка_отклоняется(client, seeded_rules):
    for payload in (
        {"severity": "CRITICAL"},
        {"params": {"min_sessions": 0}},
        {"message_template": "Этап «{stage_name»"},
    ):
        response = await client.patch(f"{BASE}/D4", json=payload)

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "DEVIATION_RULE_INVALID"
    assert (await client.get(f"{BASE}/D4")).json()["severity"] == "LOW"


async def test_предикат_через_api_не_правится(client, seeded_rules):
    response = await client.patch(f"{BASE}/D4", json={"predicate": "wrong_zone"})

    assert response.status_code == 422


def test_имя_оператора_раскодируется_из_заголовка():
    assert get_actor(quote("Иванова А. П.")) == "Иванова А. П."
    assert get_actor("ivanova") == "ivanova"
    assert get_actor("  ") is None
    assert get_actor(None) is None


async def test_неизвестный_код_это_404(client, seeded_rules):
    response = await client.patch(f"{BASE}/D42", json={"enabled": False})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DEVIATION_RULE_NOT_FOUND"
