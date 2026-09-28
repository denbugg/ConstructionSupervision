"""Прогон анализа: сигнал «пересчитай» и ручной запуск (interservice.md, раздел 4)."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Response, status

from src.api.deps import RunServiceDep
from src.api.schemas.runs import RunAccepted, RunCreate, RunRead

router = APIRouter(prefix="/runs", tags=["Прогон анализа"])


@router.post(
    "",
    response_model=RunAccepted | RunRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запустить прогон или подать сигнал «пересчитай»",
    description="Без `wait` прогон идёт в фоне, ответ 202. С `wait=true` — 200 и результат "
    "прогона, как у `GET /runs/{id}`; ошибка прогона приходит конвертом ошибки. Если по "
    "объекту прогон уже идёт, сигнал схлопывается с ним (`coalesced: true`, номер идущего), "
    "а по его окончании запускается ровно один новый. `wait=true` в этом случае ждёт, пока "
    "прогоны по объекту закончатся, и отдаёт последний; не дождался — 202.",
)
async def create_run(
    payload: RunCreate,
    service: RunServiceDep,
    background: BackgroundTasks,
    response: Response,
    wait: bool = False,
):
    run, coalesced = await service.start(payload.object_id, payload.triggered_by, payload.as_of)
    if coalesced:
        finished = await service.wait_idle(payload.object_id) if wait else None
        if finished is not None:
            response.status_code = status.HTTP_200_OK
            return RunRead.of(finished)
        return RunAccepted(run_id=run.id, status=run.status, coalesced=True)
    if wait:
        response.status_code = status.HTTP_200_OK
        return RunRead.of(await service.execute(run.id))
    background.add_task(service.execute_in_background, run.id)
    return RunAccepted(run_id=run.id, status=run.status, coalesced=False)


@router.get("/{run_id}", response_model=RunRead, summary="Результат прогона")
async def get_run(run_id: UUID, service: RunServiceDep):
    return RunRead.of(await service.get(run_id))
