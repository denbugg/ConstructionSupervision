"""Этапы графика: список объекта и ручная правка дат, участка, длительности, стадии по фото
и отметки «этап выполнен» (ADR-0015)."""

from uuid import UUID

from lct_common import NotFoundError, ValidationError, get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.stages import StageUpdate
from src.clients.analysis_client import AnalysisClient
from src.core.stages import (
    COMPLETION_FIELDS,
    StageCompletionError,
    StageDatesError,
    StageError,
    check_stage,
    completion_changes,
)
from src.dal.models import Stage, StageRule
from src.dal.repositories.rules import RuleRepository
from src.dal.repositories.stages import StageRepository
from src.reference import reference
from src.services.critical_path import refresh_critical_path
from src.services.objects import ObjectService
from src.services.plan_version import PlanVersion

log = get_logger(__name__)

# Поля, которые можно явно обнулить; остальные null в правке означает «не менять».
NULLABLE = frozenset({"visual_stage"})


class StageNotFound(NotFoundError):
    code = "STAGE_NOT_FOUND"

    def __init__(self, stage_id: UUID) -> None:
        super().__init__("Этап не найден", stage_id=str(stage_id))


class InvalidDateRange(ValidationError):
    code = "INVALID_DATE_RANGE"


class InvalidZoneType(ValidationError):
    code = "INVALID_ZONE_TYPE"


class InvalidCompletion(ValidationError):
    code = "INVALID_COMPLETION"


class StageService:
    def __init__(self, session: AsyncSession, signal: AnalysisClient) -> None:
        self._session = session
        self._repo = StageRepository(session)
        self._rules = RuleRepository(session)
        self._plan_version = PlanVersion(session, signal)

    async def get(self, stage_id: UUID) -> Stage:
        stage = await self._repo.get(stage_id)
        if stage is None:
            raise StageNotFound(stage_id)
        return stage

    async def rule_of(self, stage: Stage) -> StageRule | None:
        return await self._rules.by_stage(stage.id)

    async def list_for_object(
        self, object_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[Stage], int, dict[UUID, StageRule]]:
        """Страница этапов, общее число и правила этих этапов по id этапа."""
        await ObjectService(self._session).get(object_id)
        stages, total = await self._repo.list_for_object(object_id, limit=limit, offset=offset)
        return stages, total, await self._rules.by_stages([s.id for s in stages])

    async def update(self, stage_id: UUID, payload: StageUpdate, actor: str | None) -> Stage:
        """Правка этапа; после смены дат пересчитывается критический путь всего объекта."""
        stage = await self.get(stage_id)
        requested = payload.model_dump(exclude_unset=True)
        changes = {
            k: v
            for k, v in requested.items()
            if k not in COMPLETION_FIELDS and (v is not None or k in NULLABLE)
        }
        try:
            check_stage(
                changes.get("plan_start", stage.plan_start),
                changes.get("plan_end", stage.plan_end),
                changes.get("zone_type", stage.zone_type),
                reference().zone_roles,
            )
            completion = completion_changes(
                {k: v for k, v in requested.items() if k in COMPLETION_FIELDS},
                stage.completed_on,
                actor,
            )
        except StageDatesError as exc:
            raise InvalidDateRange(str(exc), stage_id=str(stage_id)) from exc
        except StageCompletionError as exc:
            raise InvalidCompletion(str(exc), stage_id=str(stage_id)) from exc
        except StageError as exc:
            raise InvalidZoneType(str(exc), stage_id=str(stage_id)) from exc

        changes |= completion
        for field, value in changes.items():
            setattr(stage, field, value)
        stage = await self._repo.save(stage)
        if changes.keys() & {"plan_start", "plan_end"}:
            await refresh_critical_path(self._session, [stage.object_id])
            await self._session.refresh(stage)
        if "completed_on" in completion:
            event = "stage.completed" if stage.completed_on else "stage.reopened"
            log.info(
                event, stage_id=str(stage_id), completed_on=str(stage.completed_on), actor=actor
            )
        if changes:
            await self._plan_version.changed([stage.object_id])
        return stage
