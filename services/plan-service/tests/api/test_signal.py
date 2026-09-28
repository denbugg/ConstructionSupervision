"""Клиент сигнала «пересчитай»: одна попытка, ошибка только в лог (interservice.md, раздел 4).

Базы не нужно: analysis подменяется транспортом httpx.
"""

import httpx
from src.clients.analysis_client import AnalysisClient

OBJECT_ID = "0f3a6c1e-8d4b-4c2a-9e71-5b0d2f6a8c31"


def _client(handler) -> AnalysisClient:
    client = AnalysisClient(
        "http://analysis", service="analysis-service", api_key="k", timeout_s=2.0, retries=0
    )
    client._client = httpx.AsyncClient(
        base_url="http://analysis", transport=httpx.MockTransport(handler)
    )
    return client


async def test_сигнал_уходит_с_причиной_plan_changed():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={"run_id": OBJECT_ID, "status": "RUNNING"})

    await _client(handler).request_run(OBJECT_ID)

    assert requests[0].url.path == "/api/v1/analysis/runs"
    assert b'"triggered_by":"PLAN_CHANGED"' in requests[0].content.replace(b" ", b"")


async def test_недоступный_analysis_не_роняет_правку_и_не_повторяется():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ConnectError("нет соединения")

    await _client(handler).request_run(OBJECT_ID)

    assert len(calls) == 1


async def test_ответ_ошибкой_только_в_лог():
    await _client(lambda request: httpx.Response(503)).request_run(OBJECT_ID)
    await _client(
        lambda request: httpx.Response(404, json={"error": {"code": "OBJECT_NOT_FOUND"}})
    ).request_run(OBJECT_ID)
