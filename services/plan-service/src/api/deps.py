"""Зависимости FastAPI: сессия БД, клиент сигнала в analysis, проверка ключа."""

from collections.abc import AsyncIterator
from typing import Annotated
from urllib.parse import unquote

from fastapi import Depends, Header, Request
from lct_common import make_api_key_dependency
from lct_common.db import session_dependency
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.analysis_client import AnalysisClient
from src.config import settings

require_api_key = make_api_key_dependency(settings.api_key)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async for session in session_dependency(request.app.state.session_factory):
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_actor(x_actor: Annotated[str | None, Header(alias="X-Actor")] = None) -> str | None:
    """Имя оператора из `X-Actor` для журнала правок (api-guidelines.md, раздел 6).

    Заголовки HTTP — только ASCII, поэтому имя по-русски приходит в URL-кодировке.
    """
    return unquote(x_actor).strip() or None if x_actor else None


ActorDep = Annotated[str | None, Depends(get_actor)]


def get_analysis_client(request: Request) -> AnalysisClient:
    return request.app.state.analysis_client


AnalysisDep = Annotated[AnalysisClient, Depends(get_analysis_client)]
