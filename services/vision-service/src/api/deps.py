"""Зависимости FastAPI: проверка ключа и сценарий распознавания.

Сессии БД здесь нет и не будет: сервис не хранит состояние. Модели живут в `app.state.models`
и появляются там после фоновой загрузки при старте.
"""

from typing import Annotated

from fastapi import Depends, Request
from lct_common import make_api_key_dependency

from src.config import settings
from src.services.analyze import Analyzer

require_api_key = make_api_key_dependency(settings.api_key)


def get_analyzer(request: Request) -> Analyzer:
    return Analyzer(getattr(request.app.state, "models", None), settings)


AnalyzerDep = Annotated[Analyzer, Depends(get_analyzer)]
