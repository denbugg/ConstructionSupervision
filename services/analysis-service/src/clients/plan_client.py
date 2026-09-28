"""Клиент plan-service: весь план объекта одним запросом (interservice.md, контракт 1)."""

from uuid import UUID

from lct_common import NotFoundError, ServiceClient, UpstreamError

from src.core.inputs import Plan


class ObjectNotFound(NotFoundError):
    code = "OBJECT_NOT_FOUND"

    def __init__(self, object_id: UUID) -> None:
        super().__init__("Объект не найден", object_id=str(object_id))


class PlanServiceUnavailable(UpstreamError):
    code = "PLAN_SERVICE_UNAVAILABLE"


class PlanClient(ServiceClient):
    async def get_plan(self, object_id: UUID) -> Plan:
        """Весь план: этапы, правила, календарь, классы техники."""
        try:
            payload = await self.get(f"/api/v1/plan/objects/{object_id}/plan")
        except UpstreamError as exc:
            if exc.http_status == 404:
                raise ObjectNotFound(object_id) from exc
            raise PlanServiceUnavailable(
                "plan-service недоступен: план объекта не получен", **exc.details
            ) from exc
        return Plan.model_validate(payload)
