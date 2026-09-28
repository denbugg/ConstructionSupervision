"""Клиент site-service: факты за период (контракт 2) и снимки для отчёта (контракт 6)."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from lct_common import ServiceClient, UpstreamError

from src.core.inputs import Facts


class SiteServiceUnavailable(UpstreamError):
    code = "SITE_SERVICE_UNAVAILABLE"


def _iso(moment: datetime) -> str:
    """ISO-8601 в UTC с `Z`, как требуют общие правила контрактов."""
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


class SiteClient(ServiceClient):
    async def get_facts(self, object_id: UUID, period_from: datetime, period_to: datetime) -> Facts:
        """Факты по сессиям с началом окна в [period_from, period_to)."""
        try:
            payload = await self.get(
                f"/api/v1/site/objects/{object_id}/facts",
                params={"from": _iso(period_from), "to": _iso(period_to)},
            )
        except UpstreamError as exc:
            raise SiteServiceUnavailable(
                "site-service недоступен: факты объекта не получены", **exc.details
            ) from exc
        return Facts.model_validate(payload)

    async def get_image(self, image_id: UUID) -> dict[str, Any]:
        """Карточка снимка с рамками и ссылкой во внутреннюю сеть (контракт 6)."""
        return await self.get(f"/api/v1/site/images/{image_id}", params={"link": "internal"})

    async def count_images_without_time(self, object_id: UUID) -> int:
        """Снимки объекта со статусом NEEDS_TIME: в факты они не попали."""
        page = await self.get(
            "/api/v1/site/images",
            params={"object_id": str(object_id), "status": "NEEDS_TIME", "limit": 1},
        )
        return int(page["total"])

    async def download(self, url: str) -> bytes:
        """Файл снимка по presigned-ссылке хранилища — без ключа API: это не запрос к site."""
        try:
            async with httpx.AsyncClient(timeout=self._client.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamError("Файл снимка не скачан", cause=type(exc).__name__) from exc
        return response.content
