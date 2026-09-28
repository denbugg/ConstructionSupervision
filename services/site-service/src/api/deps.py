"""Зависимости FastAPI: сессия БД, хранилище снимков, проверка ключа."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from lct_common import make_api_key_dependency
from lct_common.db import session_dependency
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.queue import RecognitionQueue
from src.clients.storage import ImageStorage
from src.config import settings

require_api_key = make_api_key_dependency(settings.api_key)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async for session in session_dependency(request.app.state.session_factory):
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_storage(request: Request) -> ImageStorage:
    return request.app.state.storage


StorageDep = Annotated[ImageStorage, Depends(get_storage)]


def get_queue(request: Request) -> RecognitionQueue:
    return request.app.state.queue


QueueDep = Annotated[RecognitionQueue, Depends(get_queue)]
