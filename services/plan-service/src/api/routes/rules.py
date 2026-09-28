"""Правила «этап → техника»: главная настройка методики, правится оператором (F11)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from lct_common import Page, PageParams

from src.api.deps import ActorDep, AnalysisDep, SessionDep
from src.api.schemas.rules import RuleCreate, RuleRead, RuleUpdate
from src.services.rules import RuleService

router = APIRouter(prefix="/rules", tags=["Правила этапов"])

CHANGE_NOTE = (
    "Коды классов проверяются по `equipment_classes.yaml`. Версия правила и `plan_version` "
    "объекта растут, в analysis уходит сигнал «пересчитай». `X-Actor` — кто правит, в журнал."
)


@router.get("", response_model=Page[RuleRead], summary="Правила этапов")
async def list_rules(
    session: SessionDep,
    signal: AnalysisDep,
    params: Annotated[PageParams, Depends()],
    stage_id: UUID | None = None,
    object_id: UUID | None = None,
):
    items, total = await RuleService(session, signal).list(
        limit=params.limit, offset=params.offset, stage_id=stage_id, object_id=object_id
    )
    return Page[RuleRead].of([RuleRead.model_validate(r) for r in items], total, params)


@router.post(
    "",
    response_model=RuleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать правило этапа",
    description=CHANGE_NOTE,
)
async def create_rule(
    payload: RuleCreate,
    session: SessionDep,
    signal: AnalysisDep,
    actor: ActorDep,
    response: Response,
):
    rule = await RuleService(session, signal).create(payload, actor)
    response.headers["Location"] = f"/api/v1/plan/rules/{rule.id}"
    return rule


@router.get("/{rule_id}", response_model=RuleRead, summary="Правило этапа")
async def get_rule(rule_id: UUID, session: SessionDep, signal: AnalysisDep):
    return await RuleService(session, signal).get(rule_id)


@router.patch(
    "/{rule_id}", response_model=RuleRead, summary="Изменить правило этапа", description=CHANGE_NOTE
)
async def update_rule(
    rule_id: UUID, payload: RuleUpdate, session: SessionDep, signal: AnalysisDep, actor: ActorDep
):
    return await RuleService(session, signal).update(rule_id, payload, actor)


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить правило этапа",
    description="По этапу без правила не проверяются D1, D2, D8, D9. `plan_version` растёт.",
)
async def delete_rule(
    rule_id: UUID, session: SessionDep, signal: AnalysisDep, actor: ActorDep
) -> None:
    await RuleService(session, signal).delete(rule_id, actor)
