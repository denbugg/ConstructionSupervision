"""Генерация графика по МРР-3.2.81-12 (ТЗ, п. 8; ADR-0011).

Параметры и дата начала берутся из запроса или из карточки объекта. Переданные в запросе
сохраняются в объект: по карточке видно, из чего построен график. График заменяется целиком
(services/plan_writer.py), поверх существующего — только с `force`.
"""

from datetime import date
from typing import Any
from uuid import UUID

from lct_common import ValidationError, get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.analysis_client import AnalysisClient
from src.core.mrr_norms import GeneratorParamsError, NormsNotAvailable, params_from_tep
from src.core.schedule_generator import generate_schedule
from src.services.critical_path import calendar_of, to_work_calendar
from src.services.objects import ObjectService
from src.services.plan_writer import PlanWriter
from src.templates import norms, templates

log = get_logger(__name__)


class NormsNotAvailableError(ValidationError):
    code = "NORMS_NOT_AVAILABLE"


class GeneratorParamsInvalid(ValidationError):
    code = "GENERATOR_PARAMS_INVALID"


class PlanGenerateService:
    def __init__(self, session: AsyncSession, signal: AnalysisClient) -> None:
        self._session = session
        self._objects = ObjectService(session)
        self._writer = PlanWriter(session, signal)

    async def generate(
        self,
        object_id: UUID,
        *,
        tep: dict[str, Any] | None,
        start_date: date | None,
        force: bool,
        actor: str | None,
    ) -> dict[str, Any]:
        obj = await self._objects.get(object_id)
        object_norms = norms().get(obj.object_type)
        if object_norms is None:
            raise NormsNotAvailableError(
                f"Для типа объекта {obj.object_type} норм МРР нет: график — импортом из файла",
                object_type=obj.object_type,
            )
        await self._writer.ensure_replaceable(obj, force=force, action="генерация")
        merged = {**obj.tep, **(tep or {})}
        start = start_date or obj.plan_start
        if start is None:
            raise GeneratorParamsInvalid(
                "Нет даты начала: передайте start_date или задайте plan_start объекта"
            )
        calendar = to_work_calendar(await calendar_of(self._session, obj))
        try:
            params = params_from_tep(merged, object_norms)
            schedule = generate_schedule(
                templates()[obj.object_type], object_norms, params, start, calendar
            )
        except GeneratorParamsError as exc:
            raise GeneratorParamsInvalid(str(exc), tep=merged) from exc
        except NormsNotAvailable as exc:
            raise NormsNotAvailableError(str(exc), tep=merged) from exc

        obj.tep, obj.plan_start = merged, start
        result = await self._writer.replace(obj, schedule.stages, source="GENERATED")
        log.info(
            "plan.generated",
            object_id=str(object_id),
            stages=result["stages"],
            total_months=round(schedule.total_months, 2),
            actor=actor,
        )
        return result | {
            "plan_start": schedule.stages[0].plan_start,
            "plan_end": max(s.plan_end for s in schedule.stages),
            "total_months": round(schedule.total_months, 2),
            "basis": schedule.basis,
        }
