"""Схлопывание сигналов прогона: на объект один прогон, повтор — ровно один (T15b)."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from src.clients.plan_client import PlanServiceUnavailable
from src.config import settings
from src.dal.models import AnalysisRun
from src.services.runs import RunService

from tests.factories import load_facts

BASE = "/api/v1/analysis/runs"
OBJECT_ID = UUID("0f3a6c1e-8d4b-4c2a-9e71-5b0d2f6a8c31")
SIGNAL = {"object_id": str(OBJECT_ID), "triggered_by": "FACTS_UPDATED"}


async def _running(session_factory, *, age: timedelta = timedelta(0)) -> AnalysisRun:
    """Строка прогона, который «идёт» прямо сейчас (или брошен `age` назад)."""
    async with session_factory() as session, session.begin():
        run = AnalysisRun(object_id=OBJECT_ID, triggered_by="MANUAL", status="RUNNING")
        if age:
            run.created_at = datetime.now(UTC) - age
        session.add(run)
    return run


async def _runs(session_factory) -> list[AnalysisRun]:
    async with session_factory() as session:
        return list(await session.scalars(select(AnalysisRun).order_by(AnalysisRun.created_at)))


def _service(session_factory, upstream) -> RunService:
    return RunService(session_factory, upstream.plan, upstream.site)


async def test_сигналы_во_время_прогона_схлопываются_в_один_повтор(
    client, upstream, session_factory
):
    upstream.site.facts = load_facts("facts_day1.json")
    current = await _running(session_factory)

    first = await client.post(BASE, json=SIGNAL)
    second = await client.post(BASE, json=SIGNAL)

    for response in (first, second):
        assert response.status_code == 202
        assert response.json() == {
            "run_id": str(current.id),
            "status": "RUNNING",
            "coalesced": True,
        }
    await _service(session_factory, upstream).execute(current.id)

    runs = await _runs(session_factory)
    assert [(r.status, r.rerun_requested) for r in runs] == [("DONE", False), ("DONE", False)]
    assert len(upstream.site.calls) == 2


async def test_без_сигналов_повтора_нет(client, upstream, session_factory):
    upstream.site.facts = load_facts("facts_day1.json")

    await client.post(BASE, json=SIGNAL, params={"wait": True})

    assert len(await _runs(session_factory)) == 1


async def test_повтор_после_неудачного_прогона_не_теряется(client, upstream, session_factory):
    upstream.site.facts = load_facts("facts_day1.json")
    current = await _running(session_factory)
    await client.post(BASE, json=SIGNAL)
    plan = upstream.plan.plan

    class FailOnce:
        calls = 0

        async def get_plan(self, object_id):
            FailOnce.calls += 1
            if FailOnce.calls == 1:
                raise PlanServiceUnavailable("plan-service недоступен")
            return plan

    service = RunService(session_factory, FailOnce(), upstream.site)
    # Ошибка прогона доходит до вызывающего — но уже после повтора.
    with pytest.raises(PlanServiceUnavailable):
        await service.execute(current.id)

    assert [r.status for r in await _runs(session_factory)] == ["FAILED", "DONE"]


async def test_брошенный_прогон_не_держит_объект(client, upstream, session_factory):
    upstream.site.facts = load_facts("facts_day1.json")
    abandoned = await _running(
        session_factory, age=timedelta(seconds=settings.run_stale_after_s + 60)
    )

    response = await client.post(BASE, json=SIGNAL, params={"wait": True})

    assert response.status_code == 200 and response.json()["status"] == "DONE"
    runs = {r.id: r for r in await _runs(session_factory)}
    assert runs[abandoned.id].status == "FAILED"
    assert runs[abandoned.id].error["code"] == "RUN_ABANDONED"


async def test_ожидание_чужого_прогона_ограничено_по_времени(
    client, upstream, session_factory, monkeypatch
):
    monkeypatch.setattr(settings, "run_wait_timeout_s", 0.2)
    monkeypatch.setattr(settings, "run_wait_poll_s", 0.05)
    current = await _running(session_factory)

    response = await client.post(BASE, json=SIGNAL, params={"wait": True})

    assert response.status_code == 202
    assert response.json()["coalesced"] is True and response.json()["run_id"] == str(current.id)


async def test_ожидание_не_кончается_в_зазоре_перед_повтором(
    upstream, session_factory, monkeypatch
):
    """Прогон уже DONE, повтор по схлопнутому сигналу ещё не заведён: результат не готов."""
    monkeypatch.setattr(settings, "run_wait_timeout_s", 0.2)
    monkeypatch.setattr(settings, "run_wait_poll_s", 0.05)
    upstream.site.facts = load_facts("facts_day1.json")
    async with session_factory() as session, session.begin():
        finished = AnalysisRun(
            object_id=OBJECT_ID, triggered_by="MANUAL", status="DONE", rerun_requested=True
        )
        session.add(finished)
    service = _service(session_factory, upstream)

    assert await service.wait_idle(OBJECT_ID) is None

    await service._follow_up(finished)
    latest = await service.wait_idle(OBJECT_ID)

    assert latest.status == "DONE" and latest.id != finished.id


async def test_ожидание_чужого_прогона_отдаёт_последний_с_учётом_сигнала(
    client, upstream, session_factory, monkeypatch
):
    monkeypatch.setattr(settings, "run_wait_poll_s", 0.05)
    upstream.site.facts = load_facts("facts_day1.json")
    current = await _running(session_factory)

    async def finish_current():
        await asyncio.sleep(0.2)
        await _service(session_factory, upstream).execute(current.id)

    response, _ = await asyncio.gather(
        client.post(BASE, json=SIGNAL, params={"wait": True}), finish_current()
    )

    assert response.status_code == 200
    body = response.json()
    # Последний — повтор, запущенный из-за нашего сигнала, а не тот, с которым он схлопнулся.
    assert body["status"] == "DONE" and body["run_id"] != str(current.id)
