"""Инфраструктура, общая для всех Python-сервисов.

Здесь нет и не может быть доменной логики: ни этапов, ни отклонений, ни техники.
Общая библиотека с бизнес-правилами превратила бы систему в распределённый
монолит — см. AGENTS.md, раздел 6.
"""

from lct_common.auth import API_KEY_HEADER, make_api_key_dependency
from lct_common.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    UnauthorizedError,
    UpstreamError,
    ValidationError,
    install_error_handlers,
)
from lct_common.health import HealthCheck, make_health_router
from lct_common.http import ServiceClient
from lct_common.logging import get_logger, setup_logging
from lct_common.pagination import Page, PageParams
from lct_common.request_id import RequestIdMiddleware, current_request_id
from lct_common.settings import BaseServiceSettings

__all__ = [
    "API_KEY_HEADER",
    "BaseServiceSettings",
    "ConflictError",
    "DomainError",
    "HealthCheck",
    "NotFoundError",
    "Page",
    "PageParams",
    "RequestIdMiddleware",
    "ServiceClient",
    "UnauthorizedError",
    "UpstreamError",
    "ValidationError",
    "current_request_id",
    "get_logger",
    "install_error_handlers",
    "make_api_key_dependency",
    "make_health_router",
    "setup_logging",
]
