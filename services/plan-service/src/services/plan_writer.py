"""Запись нового графика объекта целиком: общий шаг импорта из файла и генератора по МРР.

График заменяется вместе с правилами, затем пересчитываются резервы, растёт `plan_version`
и уходит сигнал «пересчитай». Поверх существующего графика — только с `force`: иначе одна
загрузка или генерация молча стёрла бы ручные правки дат и правил.
"""

from collections.abc import Sequence
from datetime import date
from typing import Any, Protocol
from uuid import uuid4

from lct_common import ConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.analysis_client import AnalysisClient
from src.dal.models import ConstructionObject, Stage, StageRule
from src.dal.repositories.stages import StageRepository
from src.services.critical_path import refresh_critical_path
from src.services.plan_version import PlanVersion


class PlanAlreadyExists(ConflictError):
    code = "PLAN_ALREADY_EXISTS"


class Link(Protocol):
    code: str
    type: str
    lag_days: int


class StageDraft(Protocol):
    """Этап до записи в базу: его дают и импорт (ImportedStage), и генератор (GeneratedStage)."""

    seq: int
    code: str
    name: str
    phase: str
    zone_type: str
    visual_stage: str | None
    plan_start: date
    plan_end: date
    norm_duration_days: int
    work_codes: tuple[str, ...]
    predecessors: tuple[Link, ...]
    rule: dict[str, Any] | None
    basis: str


class PlanWriter:
    def __init__(self, session: AsyncSession, signal: AnalysisClient) -> None:
        self._session = session
        self._stages = StageRepository(session)
        self._plan_version = PlanVersion(session, signal)

    async def ensure_replaceable(
        self, obj: ConstructionObject, *, force: bool, action: str
    ) -> None:
        if await self._stages.all_for_object(obj.id) and not force:
            raise PlanAlreadyExists(
                f"У объекта уже есть график: {action} заменит его целиком, передайте force=true",
                object_id=str(obj.id),
            )

    async def replace(
        self, obj: ConstructionObject, drafts: Sequence[StageDraft], *, source: str
    ) -> dict[str, Any]:
        """Новый график объекта; ответ — сводка для клиента."""
        stages, rules = _rows(obj, drafts, source)
        await self._stages.replace_for_object(obj.id, stages)
        self._session.add_all(rules)
        await self._session.flush()
        await refresh_critical_path(self._session, [obj.id])
        critical = sum(1 for s in stages if s.is_critical)
        await self._plan_version.changed([obj.id])
        await self._session.refresh(obj)
        return {
            "object_id": obj.id,
            "plan_version": obj.plan_version,
            "stages": len(stages),
            "rules": len(rules),
            "critical_stages": critical,
        }


def _rows(
    obj: ConstructionObject, drafts: Sequence[StageDraft], source: str
) -> tuple[list[Stage], list[StageRule]]:
    """Строки базы: id этапов задаются заранее, чтобы связи ссылались на них по UUID."""
    ids = {d.code: uuid4() for d in drafts}
    stages, rules = [], []
    for item in drafts:
        stages.append(
            Stage(
                id=ids[item.code],
                object_id=obj.id,
                code=item.code,
                work_codes=list(item.work_codes),
                name=item.name,
                phase=item.phase,
                seq=item.seq,
                zone_type=item.zone_type,
                visual_stage=item.visual_stage,
                plan_start=item.plan_start,
                plan_end=item.plan_end,
                norm_duration_days=item.norm_duration_days,
                predecessors=[
                    {"stage_id": str(ids[p.code]), "type": p.type, "lag_days": p.lag_days}
                    for p in item.predecessors
                ],
                source=source,
                basis=item.basis,
            )
        )
        if item.rule is not None:
            signature = item.rule.get("signature") or {}
            rules.append(
                StageRule(
                    stage_id=ids[item.code],
                    required=item.rule.get("required") or [],
                    allowed=item.rule.get("allowed") or [],
                    signature={
                        "equipment": signature.get("equipment") or [],
                        "stage_label": signature.get("stage_label"),
                    },
                )
            )
    return stages, rules
