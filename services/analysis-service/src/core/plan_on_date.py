"""План на дату: какие этапы активны и как объект должен выглядеть на фото.

Активный этап — «по плану»: местная дата сессии лежит в [plan_start, plan_end], обе
даты включительно (docs/methodology.md, раздел 2). Отдельного запроса «план на дату»
к plan-service нет: analysis решает это сам по всему плану. Этап, закрытый отметкой
оператора «выполнен», со следующего дня после отметки не активен (раздел 10.3b).
"""

from datetime import date

from src.core.inputs import Plan, Stage


def closed(stage: Stage, day: date) -> bool:
    """Этап закрыт отметкой оператора: день позже даты выполнения (раздел 10.3b).

    В сам день отметки этап ещё открыт — работы в этот день идут.
    """
    return stage.completed_on is not None and day > stage.completed_on


def completion(stage: Stage, today: date) -> date | None:
    """Дата отметки «выполнен», если она действует на `today`.

    Отметка с датой позже момента анализа в прогоне не действует: анализ считается на
    свой момент (раздел 10.3b).
    """
    if stage.completed_on is not None and stage.completed_on <= today:
        return stage.completed_on
    return None


def active_stages(plan: Plan, day: date) -> tuple[Stage, ...]:
    """Этапы, активные на местную дату, по порядку графика."""
    active = [s for s in plan.stages if s.plan_start <= day <= s.plan_end and not closed(s, day)]
    return tuple(sorted(active, key=lambda s: s.seq))


def visual_milestone(plan: Plan, day: date) -> Stage | None:
    """Этап, задающий плановую визуальную стадию на дату (docs/methodology.md, раздел 8).

    Это активный этап с заданным `visual_stage` и наибольшим `seq`: если параллельно
    идут котлован и сваи, объект на фото должен выглядеть по более поздней.
    """
    with_stage = [s for s in active_stages(plan, day) if s.visual_stage is not None]
    return with_stage[-1] if with_stage else None


def planned_visual_stage(plan: Plan, day: date) -> str | None:
    """Плановая визуальная стадия на дату; None — на дату нет этапа со стадией, D7 не с чем."""
    stage = visual_milestone(plan, day)
    return stage.visual_stage if stage else None
