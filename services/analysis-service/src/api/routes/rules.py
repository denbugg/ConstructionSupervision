"""Настройки правил отклонений D1–D10: пороги и тексты правятся без правки кода."""

from typing import Annotated

from fastapi import APIRouter, Depends
from lct_common import Page, PageParams

from src.api.deps import ActorDep, SessionDep
from src.api.schemas.rules import DeviationRuleRead, DeviationRuleUpdate
from src.services.rules import RuleService

router = APIRouter(prefix="/deviation-rules", tags=["Правила отклонений"])


@router.get("", response_model=Page[DeviationRuleRead], summary="Настройки D1–D10")
async def list_rules(session: SessionDep, params: Annotated[PageParams, Depends()]):
    rows = await RuleService(session).all()
    page = rows[params.offset : params.offset + params.limit]
    return Page[DeviationRuleRead].of(
        [DeviationRuleRead.model_validate(r) for r in page], len(rows), params
    )


@router.get("/{code}", response_model=DeviationRuleRead, summary="Настройка одного кода")
async def get_rule(code: str, session: SessionDep):
    return await RuleService(session).get(code)


@router.patch(
    "/{code}",
    response_model=DeviationRuleRead,
    summary="Изменить пороги, серьёзность или тексты правила",
    description="Действует со следующего прогона. `X-Actor` — кто правит, попадает в журнал.",
)
async def update_rule(
    code: str, payload: DeviationRuleUpdate, session: SessionDep, actor: ActorDep
):
    changes = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    return await RuleService(session).update(code, changes, actor)
