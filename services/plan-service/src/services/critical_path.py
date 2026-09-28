"""Календарь объекта и пересчёт критического пути после правки дат или календаря.

Отдельный модуль без зависимостей от других сценариев: его зовут и правка этапа, и правка
календаря, и импорт графика.
"""

from datetime import date
from uuid import UUID

from lct_common import NotFoundError, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.calendar import WorkCalendar
from src.core.cpm import CpmError, CpmStage, Link, total_floats
from src.dal.models import ConstructionObject, Stage
from src.dal.models import WorkCalendar as WorkCalendarRow
from src.dal.repositories.calendars import CalendarRepository
from src.dal.repositories.objects import ObjectRepository
from src.dal.repositories.stages import StageRepository


class CalendarNotFound(NotFoundError):
    code = "CALENDAR_NOT_FOUND"

    def __init__(self, calendar_id: UUID | None, code: str | None = None) -> None:
        # Без id — не нашёлся календарь по умолчанию: тогда в деталях его код.
        details = {"calendar_id": str(calendar_id)} if calendar_id else {"code": code}
        super().__init__("Календарь не найден", **details)


class PlanCycle(ValidationError):
    """Связи этапов противоречивы: цикл, ссылка на отсутствующий этап, неизвестный тип."""

    code = "PLAN_CYCLE"


async def calendar_of(session: AsyncSession, obj: ConstructionObject) -> WorkCalendarRow:
    """Календарь объекта; объект без календаря работает по DEFAULT_CALENDAR."""
    calendars = CalendarRepository(session)
    if obj.calendar_id is not None:
        calendar = await calendars.get(obj.calendar_id)
    else:
        calendar = await calendars.by_code(settings.default_calendar)
    if calendar is None:
        raise CalendarNotFound(obj.calendar_id, code=settings.default_calendar)
    return calendar


def to_work_calendar(row: WorkCalendarRow) -> WorkCalendar:
    return WorkCalendar(
        weekend_days=tuple(row.weekend_days),
        holidays=frozenset(date.fromisoformat(d) for d in row.holidays),
    )


def to_cpm_stage(stage: Stage) -> CpmStage:
    links = tuple(
        Link(UUID(p["stage_id"]), p["type"], p.get("lag_days", 0)) for p in stage.predecessors
    )
    return CpmStage(stage.id, stage.plan_start, stage.plan_end, links)


async def refresh_critical_path(session: AsyncSession, object_ids: list[UUID]) -> None:
    """Резервы и признак критичности этапов — заново по текущим датам, связям и календарю."""
    objects = ObjectRepository(session)
    stages_repo = StageRepository(session)
    for object_id in object_ids:
        obj = await objects.get(object_id)
        if obj is None:
            continue
        calendar = to_work_calendar(await calendar_of(session, obj))
        stages = await stages_repo.all_for_object(object_id)
        try:
            floats = total_floats([to_cpm_stage(s) for s in stages], calendar)
        except CpmError as exc:
            raise PlanCycle(str(exc), object_id=str(object_id)) from exc
        for stage in stages:
            stage.total_float_days = floats[stage.id].total_float_days
            stage.is_critical = floats[stage.id].is_critical
    await session.flush()
