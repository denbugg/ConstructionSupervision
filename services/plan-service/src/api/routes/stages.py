"""Этапы календарного графика: список объекта и ручная правка."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from lct_common import Page, PageParams

from src.api.deps import ActorDep, AnalysisDep, SessionDep
from src.api.schemas.stages import StageRead, StageUpdate
from src.services.stages import StageService

router = APIRouter(tags=["График"])


@router.get(
    "/objects/{object_id}/stages",
    response_model=Page[StageRead],
    summary="Этапы объекта",
    description="Этапы по `seq` вместе с правилом «этап → техника» (`rule`, `null` — правила нет).",
)
async def list_stages(
    object_id: UUID,
    session: SessionDep,
    signal: AnalysisDep,
    params: Annotated[PageParams, Depends()],
):
    stages, total, rules = await StageService(session, signal).list_for_object(
        object_id, limit=params.limit, offset=params.offset
    )
    return Page[StageRead].of([StageRead.of(s, rules.get(s.id)) for s in stages], total, params)


@router.patch(
    "/stages/{stage_id}",
    response_model=StageRead,
    summary="Изменить этап",
    description="Даты (включительно), тип участка, нормативная длительность, стадия по фото, "
    "отметка «этап выполнен» (`completed_on`, `completion_note`; автор — из `X-Actor`, "
    "`completed_on: null` снимает отметку). `plan_version` объекта растёт, в analysis уходит "
    "сигнал «пересчитай».",
)
async def update_stage(
    stage_id: UUID, payload: StageUpdate, session: SessionDep, signal: AnalysisDep, actor: ActorDep
):
    service = StageService(session, signal)
    stage = await service.update(stage_id, payload, actor)
    return StageRead.of(stage, await service.rule_of(stage))
