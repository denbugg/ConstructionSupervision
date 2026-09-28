"""Клиент analysis-service: сигнал «пересчитай» после правки плана (interservice.md, раздел 4)."""

from uuid import UUID

from lct_common import DomainError, ServiceClient, get_logger

log = get_logger(__name__)


class AnalysisClient(ServiceClient):
    async def request_run(self, object_id: UUID) -> None:
        """Сигнал без ожидания результата: ошибка только пишется в лог.

        Правка плана уже сохранена, и недоступный analysis не должен её откатывать:
        следующий прогон или кнопка «пересчитать» всё равно считают план с нуля.
        """
        try:
            await self.post(
                "/api/v1/analysis/runs",
                json={"object_id": str(object_id), "triggered_by": "PLAN_CHANGED"},
            )
        except DomainError as exc:
            log.warning(
                "analysis.signal_failed", object_id=str(object_id), code=exc.code, **exc.details
            )
