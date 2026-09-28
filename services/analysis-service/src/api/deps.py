"""Зависимости FastAPI: сессия БД, сценарий прогона, проверка ключа."""

from collections.abc import AsyncIterator
from typing import Annotated
from urllib.parse import unquote

from fastapi import Depends, Header, Request
from lct_common import make_api_key_dependency
from lct_common.db import session_dependency
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.site_client import SiteClient
from src.config import settings
from src.services.deviations import DeviationService
from src.services.reports import ReportService
from src.services.runs import RunService
from src.services.summary import Summarizer

require_api_key = make_api_key_dependency(settings.api_key)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async for session in session_dependency(request.app.state.session_factory):
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_actor(x_actor: Annotated[str | None, Header(alias="X-Actor")] = None) -> str | None:
    """Имя оператора из `X-Actor`.

    Заголовки HTTP — только ASCII, поэтому имя по-русски приходит в URL-кодировке
    (`%D0%98…`); ASCII-имя без процентов раскодирование не меняет.
    """
    return unquote(x_actor).strip() or None if x_actor else None


ActorDep = Annotated[str | None, Depends(get_actor)]


def get_site_client(request: Request) -> SiteClient:
    return request.app.state.site_client


def get_deviation_service(
    session: SessionDep, site: Annotated[SiteClient, Depends(get_site_client)]
) -> DeviationService:
    return DeviationService(session, site)


DeviationServiceDep = Annotated[DeviationService, Depends(get_deviation_service)]


def get_run_service(request: Request) -> RunService:
    """Прогон пишет своими транзакциями, поэтому берёт фабрику сессий, а не сессию запроса."""
    state = request.app.state
    return RunService(state.session_factory, state.plan_client, state.site_client)


RunServiceDep = Annotated[RunService, Depends(get_run_service)]


def get_report_service(request: Request, session: SessionDep) -> ReportService:
    state = request.app.state
    return ReportService(
        session,
        state.plan_client,
        state.site_client,
        state.report_storage,
        Summarizer(state.llm_client),
    )


ReportServiceDep = Annotated[ReportService, Depends(get_report_service)]
