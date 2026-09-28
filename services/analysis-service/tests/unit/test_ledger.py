"""Сверка эпизодов прогона с лентой отклонений (docs/methodology.md, раздел 9)."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from src.core.ledger import LedgerRow, reconcile
from src.core.predicates import Finding

T0 = datetime(2026, 10, 20, 6, tzinfo=UTC)
KEY = (None, "PIT:Котлован", "D2", None)
# Пересчитанный отрезок: от начала фактов до as_of; все строки ниже лежат внутри.
PERIOD = (T0 - timedelta(days=1), T0 + timedelta(days=1))


def _reconcile(rows, findings, period=PERIOD):
    return reconcile(rows, findings, period)


def _finding(start_h=0, end_h=2, *, active=True, key=KEY):
    stage_id, area, code, cls = key
    return Finding(
        code=code,
        severity="MEDIUM",
        stage_id=stage_id,
        area=area,
        equipment_class=cls,
        session_id=uuid4(),
        first_seen_at=T0 + timedelta(hours=start_h),
        last_seen_at=T0 + timedelta(hours=end_h),
        occurrences=4,
        active=active,
        facts={"n": 1},
        evidence=({"image_id": "x", "detection_ids": []},),
    )


def _row(status="NEW", start_h=0, end_h=1, key=KEY, verdict=None):
    return LedgerRow(
        id=uuid4(),
        key=key,
        status=status,
        first_seen_at=T0 + timedelta(hours=start_h),
        last_seen_at=T0 + timedelta(hours=end_h),
        # Вердикт ставит оператор: CONFIRMED и REJECTED без него не бывают.
        has_verdict=status in ("CONFIRMED", "REJECTED") if verdict is None else verdict,
    )


def test_новый_эпизод_открывается():
    plan = _reconcile([], [_finding()])

    assert [status for _, status in plan.insert] == ["NEW"] and plan.opened == 1


def test_закончившийся_эпизод_без_строки_попадает_в_историю_закрытым():
    plan = _reconcile([], [_finding(active=False)])

    assert [status for _, status in plan.insert] == ["RESOLVED"] and plan.opened == 0


def test_повтор_обновляет_строку_а_не_плодит_дубль():
    row = _row()

    plan = _reconcile([row], [_finding()])

    assert plan.insert == () and plan.resolve == ()
    assert [(i, s) for i, _, s in plan.update] == [(row.id, "NEW")]


def test_вердикт_оператора_сохраняется_пока_условие_держится():
    confirmed, rejected = _row("CONFIRMED"), _row("REJECTED", key=(None, "B", "D2", None))

    plan = _reconcile([confirmed, rejected], [_finding(), _finding(key=(None, "B", "D2", None))])

    assert {(i, s) for i, _, s in plan.update} == {
        (confirmed.id, "CONFIRMED"),
        (rejected.id, "REJECTED"),
    }


def test_условие_пропало_строка_закрывается():
    row = _row()

    plan = _reconcile([row], [_finding(active=False)])

    assert [(i, s) for i, _, s in plan.update] == [(row.id, "RESOLVED")]


def test_строка_без_эпизода_в_пересчитанном_периоде_удаляется():
    new, resolved = _row("NEW"), _row("RESOLVED", key=(None, "B", "D2", None))

    plan = _reconcile([new, resolved], [])

    assert set(plan.delete) == {new.id, resolved.id} and plan.resolve == ()


def test_строка_с_вердиктом_без_эпизода_не_удаляется():
    confirmed = _row("CONFIRMED")
    rejected = _row("REJECTED", key=(None, "B", "D2", None))
    resolved = _row("RESOLVED", key=(None, "C", "D2", None), verdict=True)

    plan = _reconcile([confirmed, rejected, resolved], [])

    assert plan.delete == () and plan.resolve == (confirmed.id,)


@pytest.mark.parametrize("verdict", ["CONFIRMED", "REJECTED"])
def test_закрытый_с_вердиктом_снова_держится_открывается_со_своим_вердиктом(verdict):
    resolved = replace(_row("RESOLVED", start_h=0, end_h=1, verdict=True), verdict=verdict)

    plan = _reconcile([resolved], [_finding(0, 3)])

    assert [(i, s) for i, _, s in plan.update] == [(resolved.id, verdict)]


def test_открытая_строка_вне_пересчитанного_периода_закрывается_а_не_удаляется():
    row = _row(start_h=0, end_h=30)  # продолжается после as_of: прогон её конца не видел

    plan = _reconcile([row], [])

    assert plan.delete == () and plan.resolve == (row.id,)


def test_эпизод_не_пересекающий_строку_не_спасает_её():
    phantom = _row("RESOLVED", start_h=0, end_h=1)

    plan = _reconcile([phantom], [_finding(3, 5, active=False)])

    assert plan.delete == (phantom.id,)
    assert [s for _, s in plan.insert] == ["RESOLVED"]


def test_отклонённое_после_перерыва_открывается_заново():
    rejected = _row("REJECTED", start_h=0, end_h=1)

    plan = _reconcile([rejected], [_finding(0, 1, active=False), _finding(3, 5)])

    assert [(i, s) for i, _, s in plan.update] == [(rejected.id, "REJECTED")]
    assert [s for _, s in plan.insert] == ["NEW"]


def test_устаревшая_открытая_строка_уходит_раньше_новой_по_тому_же_ключу():
    stale = _row("NEW", start_h=0, end_h=1)
    confirmed = _row("CONFIRMED", start_h=0, end_h=1, key=(None, "B", "D2", None))

    plan = _reconcile(
        [stale, confirmed], [_finding(3, 5), _finding(3, 5, key=(None, "B", "D2", None))]
    )

    # Без вердикта эпизода 0–1 ч не было: удаляется; с вердиктом — закрывается.
    assert plan.delete == (stale.id,) and plan.resolve == (confirmed.id,)
    assert [s for _, s in plan.insert] == ["NEW", "NEW"]


def test_закрытый_эпизод_снова_держится_открывается():
    resolved = _row("RESOLVED", start_h=0, end_h=1)

    plan = _reconcile([resolved], [_finding(0, 3)])

    assert [(i, s) for i, _, s in plan.update] == [(resolved.id, "NEW")]
