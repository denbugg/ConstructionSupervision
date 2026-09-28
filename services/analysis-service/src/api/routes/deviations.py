"""Лента отклонений: фильтры, карточка, объяснение, вердикт оператора."""

from datetime import UTC, date, datetime, time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from lct_common import Page, PageParams
from pydantic import AwareDatetime

from src.api.deps import ActorDep, DeviationServiceDep
from src.api.schemas.deviations import (
    DeviationRead,
    DeviationVerdict,
    EvidenceRead,
    ExplainRead,
)
from src.api.schemas.rules import DeviationRuleRead
from src.dal.repositories.deviations import DeviationFilter

router = APIRouter(prefix="/deviations", tags=["Отклонения"])

Moment = AwareDatetime | date


def _moment(value: Moment | None) -> datetime | None:
    """Дата без времени — полночь UTC: у analysis нет календаря объекта для фильтра ленты."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.combine(value, time(0), tzinfo=UTC)


@router.get(
    "",
    response_model=Page[DeviationRead],
    summary="Лента отклонений",
    description="Повторяющийся параметр — несколько значений: `?severity=HIGH&severity=MEDIUM`. "
    "`verdict` — `CONFIRMED` / `REJECTED`, вердикт оператора независимо от статуса: закрытое "
    "с вердиктом остаётся `RESOLVED`. "
    "`from`/`to` — эпизоды, пересекающиеся с `[from, to)`. `sort` — `last_seen_at`, "
    "`first_seen_at` или `severity`, минус — по убыванию; по умолчанию `-last_seen_at`.",
)
async def list_deviations(
    service: DeviationServiceDep,
    params: Annotated[PageParams, Depends()],
    object_id: UUID | None = None,
    code: Annotated[list[str], Query()] = [],  # noqa: B006 — FastAPI копирует значение
    severity: Annotated[list[str], Query()] = [],  # noqa: B006
    status: Annotated[list[str], Query()] = [],  # noqa: B006
    verdict: Annotated[list[str], Query()] = [],  # noqa: B006
    stage_id: UUID | None = None,
    area: str | None = None,
    since: Annotated[Moment | None, Query(alias="from")] = None,
    until: Annotated[Moment | None, Query(alias="to")] = None,
    sort: str = "-last_seen_at",
):
    flt = DeviationFilter(
        object_id=object_id,
        codes=code,
        severities=severity,
        statuses=status,
        verdicts=verdict,
        stage_id=stage_id,
        area=area,
        since=_moment(since),
        until=_moment(until),
    )
    rows, total = await service.feed(flt, sort=sort, limit=params.limit, offset=params.offset)
    return Page[DeviationRead].of([DeviationRead.model_validate(r) for r in rows], total, params)


@router.get("/{deviation_id}", response_model=DeviationRead, summary="Карточка отклонения")
async def get_deviation(deviation_id: UUID, service: DeviationServiceDep):
    return await service.get(deviation_id)


@router.get(
    "/{deviation_id}/explain",
    response_model=ExplainRead,
    summary="Полное объяснение: правило, сессии эпизода, снимки",
)
async def explain_deviation(deviation_id: UUID, service: DeviationServiceDep):
    explanation = await service.explain(deviation_id)
    row = explanation.deviation
    return ExplainRead(
        deviation=DeviationRead.model_validate(row),
        rule=DeviationRuleRead.model_validate(explanation.rule) if explanation.rule else None,
        sessions=explanation.sessions,
        sessions_truncated=explanation.sessions_truncated,
        sessions_unavailable_reason=explanation.sessions_unavailable_reason,
        evidence=[
            EvidenceRead(
                image_id=e["image_id"],
                detection_ids=e["detection_ids"],
                image_path=f"/api/v1/site/images/{e['image_id']}",
            )
            for e in row.evidence
        ],
    )


@router.patch(
    "/{deviation_id}",
    response_model=DeviationRead,
    summary="Вердикт оператора: подтвердить или пометить ложным",
    description="`X-Actor` — кто вынес вердикт (по-русски — в URL-кодировке). `REJECTED` не "
    "открывается заново, пока условие держится непрерывно.",
)
async def set_verdict(
    deviation_id: UUID, payload: DeviationVerdict, service: DeviationServiceDep, actor: ActorDep
):
    return await service.verdict(deviation_id, payload.status, payload.comment, actor)
