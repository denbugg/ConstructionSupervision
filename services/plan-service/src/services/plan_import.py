"""Импорт календарного графика из файла (ТЗ, п. 3; F11).

Импорт заменяет график объекта целиком (services/plan_writer.py). Поверх существующего
графика — только с `force`.
"""

from dataclasses import asdict
from typing import Any
from uuid import UUID

from lct_common import ValidationError, get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.analysis_client import AnalysisClient
from src.config import settings
from src.core.plan_import import PlanImportError, parse_schedule, read_table
from src.services.critical_path import calendar_of, to_work_calendar
from src.services.objects import ObjectService
from src.services.plan_writer import PlanWriter
from src.templates import template_for, vocabulary

log = get_logger(__name__)


class PlanImportInvalid(ValidationError):
    code = "PLAN_IMPORT_INVALID"


class PlanImportService:
    def __init__(self, session: AsyncSession, signal: AnalysisClient) -> None:
        self._session = session
        self._objects = ObjectService(session)
        self._writer = PlanWriter(session, signal)

    async def import_file(
        self, object_id: UUID, filename: str, content: bytes, *, force: bool, actor: str | None
    ) -> dict[str, Any]:
        obj = await self._objects.get(object_id)
        if len(content) > settings.plan_import_max_mb * 1024 * 1024:
            raise PlanImportInvalid(
                f"Файл больше {settings.plan_import_max_mb} МБ",
                limit_mb=settings.plan_import_max_mb,
            )
        await self._writer.ensure_replaceable(obj, force=force, action="импорт")
        calendar = to_work_calendar(await calendar_of(self._session, obj))
        try:
            parsed = parse_schedule(
                read_table(filename, content), template_for(obj.object_type), vocabulary(), calendar
            )
        except PlanImportError as exc:
            raise PlanImportInvalid(
                str(exc), errors=[asdict(issue) for issue in exc.issues]
            ) from exc

        if obj.plan_start is None:
            # Начало СМР — от него analysis запрашивает факты (interservice.md, раздел 1).
            obj.plan_start = min(s.plan_start for s in parsed)
        result = await self._writer.replace(obj, parsed, source="IMPORT")
        log.info("plan.imported", object_id=str(object_id), stages=result["stages"], actor=actor)
        return result
