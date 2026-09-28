"""API PDF-отчётов: формирование, список, ссылка, деградация без site (T34c)."""

from datetime import UTC, datetime

from lct_common import UpstreamError

from tests.conftest import DEMO_OBJECT_ID, StubLlm

BASE = "/api/v1/analysis/reports"
SUMMARY = "/api/v1/analysis/summary"


async def _deviation_ref(client) -> str:
    page = await client.get("/api/v1/analysis/deviations", params={"object_id": DEMO_OBJECT_ID})
    return page.json()["items"][0]["id"][:8]


async def test_отчёт_по_умолчанию_за_неделю_до_дня_анализа(client, analyzed, upstream):
    response = await client.post(BASE, json={"object_id": DEMO_OBJECT_ID})

    assert response.status_code == 201, response.text
    body = response.json()
    # as_of 22.10 12:00 UTC — 22.10 по Москве; неделя — с 16.10 по 22.10 включительно.
    assert (body["period_from"], body["period_to"]) == ("2026-10-16", "2026-10-22")
    assert body["key"].startswith(f"{DEMO_OBJECT_ID}/{body['generated_on']}T")
    assert body["key"].endswith("-2026-10-16_2026-10-22.pdf")
    assert body["as_of"] == "2026-10-22T12:00:00Z"
    assert body["summary_generated_by"] == "TEMPLATE"
    assert body["evidence_images"] >= 1 and body["evidence_missing"] == 0
    assert body["url"].startswith("http://localhost:8333/reports/")
    # Факты — за местные сутки периода, в UTC.
    _, since, until = upstream.site.calls[-1]
    assert (since, until) == (
        datetime(2026, 10, 15, 21, tzinfo=UTC),
        datetime(2026, 10, 22, 21, tzinfo=UTC),
    )
    content, _ = upstream.storage.files[body["key"]]
    assert content.startswith(b"%PDF") and body["size_bytes"] == len(content)


async def test_список_и_ссылка_на_отчёт(client, analyzed):
    created = (
        await client.post(
            BASE,
            json={
                "object_id": DEMO_OBJECT_ID,
                "period_from": "2026-10-20",
                "period_to": "2026-10-20",
            },
        )
    ).json()

    page = (await client.get(BASE, params={"object_id": DEMO_OBJECT_ID})).json()
    link = await client.get(f"{BASE}/{created['key']}")

    assert page["total"] == 1 and page["items"][0]["key"] == created["key"]
    assert link.status_code == 200 and link.json()["url"] == created["url"]
    missing = await client.get(f"{BASE}/{DEMO_OBJECT_ID}/2026-01-01-2026-01-01_2026-01-02.pdf")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "REPORT_NOT_FOUND"


async def test_повтор_того_же_периода_не_затирает_прежний_отчёт(client, analyzed, upstream):
    # 27.09 20:15:00 и 20:15:07 по Москве: тот же день, тот же период по умолчанию.
    moments = iter(
        [datetime(2026, 9, 27, 17, 15, 0, tzinfo=UTC), datetime(2026, 9, 27, 17, 15, 7, tzinfo=UTC)]
    )
    upstream.clock = lambda: next(moments)

    first = (await client.post(BASE, json={"object_id": DEMO_OBJECT_ID})).json()
    second = (await client.post(BASE, json={"object_id": DEMO_OBJECT_ID})).json()
    page = (await client.get(BASE, params={"object_id": DEMO_OBJECT_ID})).json()

    assert first["key"] == f"{DEMO_OBJECT_ID}/2026-09-27T201500-2026-10-16_2026-10-22.pdf"
    assert second["key"] == f"{DEMO_OBJECT_ID}/2026-09-27T201507-2026-10-16_2026-10-22.pdf"
    assert page["total"] == 2
    assert {item["key"] for item in page["items"]} == {first["key"], second["key"]}


async def test_без_site_отчёт_выходит_и_говорит_о_пробелах(client, analyzed, upstream):
    upstream.site.error = UpstreamError("site-service недоступен")

    response = await client.post(BASE, json={"object_id": DEMO_OBJECT_ID})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["evidence_images"] == 0 and body["evidence_missing"] >= 1


async def test_период_без_наблюдений(client, analyzed):
    response = await client.post(
        BASE,
        json={"object_id": DEMO_OBJECT_ID, "period_from": "2026-10-01", "period_to": "2026-10-05"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_DATA_FOR_PERIOD"


async def test_резюме_без_нейросети_шаблонное(client, analyzed):
    response = await client.post(SUMMARY, json={"object_id": DEMO_OBJECT_ID})

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["period_from"], body["period_to"]) == ("2026-10-16", "2026-10-22")
    assert body["generated_by"] == "TEMPLATE" and body["llm_rejected"] == []
    assert body["text"].startswith("На 22.10.2026")


async def test_резюме_нейросети_с_проверкой(client, analyzed, upstream):
    upstream.llm = StubLlm()
    ref = await _deviation_ref(client)

    honest_text = f"Главное отклонение периода — [{ref}]."
    upstream.llm.reply = honest_text
    honest = (await client.post(SUMMARY, json={"object_id": DEMO_OBJECT_ID})).json()
    upstream.llm.reply = f"Главное отклонение — [{ref}], потери 987 дней."
    invented = (await client.post(SUMMARY, json={"object_id": DEMO_OBJECT_ID})).json()

    assert (honest["generated_by"], honest["text"]) == ("LLM", honest_text)
    assert invented["generated_by"] == "TEMPLATE"
    assert invented["llm_rejected"] == ["числа не из фактов: 987"]


async def test_pdf_с_резюме_нейросети(client, analyzed, upstream):
    upstream.llm = StubLlm()
    upstream.llm.reply = f"Главное отклонение периода — [{await _deviation_ref(client)}]."

    response = await client.post(BASE, json={"object_id": DEMO_OBJECT_ID})

    assert response.status_code == 201, response.text
    assert response.json()["summary_generated_by"] == "LLM"


async def test_перевёрнутый_период_и_объект_без_анализа(client, analyzed):
    reversed_period = await client.post(
        BASE,
        json={"object_id": DEMO_OBJECT_ID, "period_from": "2026-10-22", "period_to": "2026-10-19"},
    )
    not_analyzed = await client.post(
        BASE, json={"object_id": "00000000-0000-4000-8000-000000000000"}
    )

    assert reversed_period.status_code == 400
    assert not_analyzed.status_code == 404
    assert not_analyzed.json()["error"]["code"] == "OBJECT_NOT_ANALYZED"
