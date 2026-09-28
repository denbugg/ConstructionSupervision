"""Сценарий прогона: получить план и факты, посчитать, записать выводы.

Вся методика — в core/run.py; здесь только «откуда взять» и «куда положить». Прогон
пишет в базу своими транзакциями, а не транзакцией запроса: отметка FAILED должна
сохраниться, даже когда запрос завершается ошибкой, а фоновый прогон живёт дольше
запроса.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, time
from functools import lru_cache, partial
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from lct_common import ConflictError, DomainError, NotFoundError, ValidationError, get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.concurrency import run_in_threadpool

from src.clients.plan_client import PlanClient
from src.clients.site_client import SiteClient
from src.config import settings
from src.core.enums import Enums, load_enums
from src.core.forecast import ForecastParams
from src.core.inputs import Plan
from src.core.ledger import OPEN, LedgerRow, reconcile
from src.core.predicates import DeviationRule, load_rules
from src.core.rules import RuleParams
from src.core.run import analyze
from src.dal.models import AnalysisRun
from src.dal.repositories.results import ResultsRepository
from src.dal.repositories.rules import RuleRepository
from src.dal.repositories.runs import RunRepository

log = get_logger(__name__)
SERVICE_ROOT = Path(__file__).resolve().parents[2]
# Конец периода фактов, когда as_of не задан: «без верхней границы», а не порог.
OPEN_END = datetime(9999, 12, 31, tzinfo=UTC)


class RunNotFound(NotFoundError):
    code = "RUN_NOT_FOUND"

    def __init__(self, run_id: UUID) -> None:
        super().__init__("Прогон не найден", run_id=str(run_id))


class PlanNotReady(ConflictError):
    code = "PLAN_NOT_READY"


class AnalysisInputInvalid(DomainError):
    """План, факты или настройки правил нельзя посчитать: цикл связей, чужой объект и т. п."""

    code = "ANALYSIS_INPUT_INVALID"
    http_status = 422


@lru_cache
def enums() -> Enums:
    return load_enums(settings.contracts_dir)


def default_rules() -> tuple[DeviationRule, ...]:
    """Начальные настройки D1–D10 из YAML; относительный путь — от корня сервиса."""
    path = Path(settings.deviation_rules_file)
    return load_rules(path if path.is_absolute() else SERVICE_ROOT / path)


def rule_params() -> RuleParams:
    return RuleParams(
        transient_window_sessions=settings.transient_window_sessions,
        min_stage_conf=settings.min_stage_conf,
    )


def forecast_params() -> ForecastParams:
    return ForecastParams(
        min_activity=settings.min_activity,
        forecast_window_days=settings.forecast_window_days,
        min_days_for_forecast=settings.min_days_for_forecast,
        on_track_tolerance_days=settings.on_track_tolerance_days,
        confidence_high_days=settings.confidence_high_days,
        confidence_high_visible=settings.confidence_high_visible,
        confidence_medium_visible=settings.confidence_medium_visible,
        unknown_blind_share=settings.unknown_blind_share,
    )


def period_start(plan: Plan) -> datetime:
    """Начало периода фактов: местная полночь даты начала СМР (или первого этапа)."""
    first = plan.object.plan_start or min((s.plan_start for s in plan.stages), default=None)
    if first is None:
        raise PlanNotReady(
            "У объекта нет ни даты начала СМР, ни этапов: анализировать нечего",
            object_id=str(plan.object.id),
        )
    local = datetime.combine(first, time(0), tzinfo=ZoneInfo(plan.calendar.timezone))
    return local.astimezone(UTC)


class RunService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        plan_client: PlanClient,
        site_client: SiteClient,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._factory = session_factory
        self._plan = plan_client
        self._site = site_client
        self._now = now

    async def start(
        self, object_id: UUID, triggered_by: str, as_of: datetime | None
    ) -> tuple[AnalysisRun, bool]:
        """Заводит прогон RUNNING или схлопывает сигнал с идущим: (прогон, схлопнут ли).

        На объект одновременно идёт не больше одного прогона. Сигнал во время прогона
        только отмечает, что по его окончании нужен ещё один (interservice.md, раздел 4).
        """
        allowed = enums().values.get("analysis_trigger", ())
        if triggered_by not in allowed:
            raise ValidationError(
                "Неизвестный источник прогона", triggered_by=triggered_by, allowed=list(allowed)
            )
        async with self._factory() as session, session.begin():
            runs = RunRepository(session)
            await runs.lock_object(object_id)
            return await self._start_locked(runs, object_id, triggered_by, as_of)

    async def _start_locked(
        self, runs: RunRepository, object_id: UUID, triggered_by: str, as_of: datetime | None
    ) -> tuple[AnalysisRun, bool]:
        """Тело `start` под уже взятой блокировкой объекта."""
        for current in await runs.running(object_id):
            if runs.is_stale(current, self._now(), settings.run_stale_after_s):
                # Процесс упал посреди прогона: строка RUNNING не должна держать объект.
                # Его отметку «нужен ещё» закрывает прогон, который заводится сейчас.
                current.status = "FAILED"
                current.rerun_requested = False
                current.error = {
                    "code": "RUN_ABANDONED",
                    "message": "Прогон не завершился вовремя и считается брошенным",
                }
                continue
            current.rerun_requested = True
            return current, True
        run = AnalysisRun(object_id=object_id, triggered_by=triggered_by, as_of=as_of)
        return await runs.add(run), False

    async def get(self, run_id: UUID) -> AnalysisRun:
        async with self._factory() as session:
            run = await RunRepository(session).get(run_id)
        if run is None:
            raise RunNotFound(run_id)
        return run

    async def execute(self, run_id: UUID) -> AnalysisRun:
        """Прогон целиком, затем повтор, если во время него пришёл сигнал.

        Ошибка отмечается в строке прогона и пробрасывается дальше — но только после
        повтора: сигнал, пришедший во время неудачного прогона, тоже не теряется.
        """
        run = await self.get(run_id)
        try:
            await self._compute_and_save(run)
        except DomainError as exc:
            await self._fail(run_id, exc)
            raise
        except ValueError as exc:
            # Ошибки ядра (цикл связей, неизвестный тип зоны, испорченный шаблон) — это
            # данные, которые нельзя посчитать, а не сбой сервиса.
            error = AnalysisInputInvalid(str(exc), object_id=str(run.object_id))
            await self._fail(run_id, error)
            raise error from exc
        finally:
            await self._follow_up(run)
        return await self.get(run_id)

    async def execute_in_background(self, run_id: UUID) -> None:
        """Фоновый прогон: исход уже записан в строке прогона, здесь только лог."""
        try:
            await self.execute(run_id)
        except DomainError as exc:
            log.warning("run.failed", run_id=str(run_id), code=exc.code)

    async def wait_idle(self, object_id: UUID) -> AnalysisRun | None:
        """Ждёт, пока по объекту не останется идущих прогонов; None — не дождались.

        Нужен `?wait=true`, когда сигнал схлопнулся с чужим прогоном: вызывающему важен
        не номер прогона, а то, что выводы посчитаны с учётом его сигнала.
        """
        deadline = self._now().timestamp() + settings.run_wait_timeout_s
        while True:
            async with self._factory() as session:
                runs = RunRepository(session)
                # Закончившийся прогон с отметкой «нужен ещё» — ещё не конец: повтор, который
                # учтёт сигнал вызывающего, вот-вот заведётся.
                idle = await runs.count_running(object_id) == 0
                if idle and not await runs.rerun_pending(object_id):
                    return await runs.latest(object_id)
            if self._now().timestamp() >= deadline:
                return None
            await asyncio.sleep(settings.run_wait_poll_s)

    async def _follow_up(self, run: AnalysisRun) -> None:
        """Ровно один повторный прогон, если во время `run` пришёл сигнал."""
        # Снятие отметки и заведение повтора — одна транзакция под блокировкой объекта:
        # иначе между ними `wait_idle` увидел бы «прогонов нет» и отдал устаревший результат.
        async with self._factory() as session, session.begin():
            runs = RunRepository(session)
            await runs.lock_object(run.object_id)
            if not await runs.consume_rerun(run.id):
                return
            # as_of схлопнутого сигнала не хранится; сигналы site и plan приходят без него,
            # поэтому повтор считает на момент по умолчанию — конец последней сессии.
            follow, coalesced = await self._start_locked(
                runs, run.object_id, run.triggered_by, None
            )
        if coalesced:
            # Кто-то уже начал новый прогон — повтор сделает он.
            return
        log.info("run.rerun", run_id=str(follow.id), after=str(run.id))
        try:
            await self.execute(follow.id)
        except DomainError as exc:
            log.warning("run.failed", run_id=str(follow.id), code=exc.code)

    async def _compute_and_save(self, run: AnalysisRun) -> None:
        plan = await self._plan.get_plan(run.object_id)
        # Без as_of верхней границы у фактов нет: момент по умолчанию — конец последней сессии
        # с фактами (interservice.md, раздел 4), и он бывает позже «сейчас» — демо-хронология
        # живёт в датах графика. Граница «сейчас» отрезала бы такие факты, и прогон по
        # сигналу от site или plan закрыл бы все отклонения объекта.
        period_to = run.as_of or OPEN_END
        period_from = period_start(plan)
        facts = await self._site.get_facts(run.object_id, period_from, period_to)

        async with self._factory() as session, session.begin():
            rules_repo = RuleRepository(session)
            await rules_repo.seed_missing(default_rules())
            rules = tuple(await rules_repo.all())

        # Без фактов «сегодня» — момент запуска (interservice.md, раздел 4).
        as_of = run.as_of or (None if facts.sessions else self._now())
        result = await run_in_threadpool(
            partial(
                analyze,
                plan,
                facts,
                rules=rules,
                enums=enums(),
                params=rule_params(),
                forecast_params=forecast_params(),
                as_of=as_of,
            )
        )

        async with self._factory() as session, session.begin():
            results = ResultsRepository(session)
            rows = await results.deviations(run.object_id)
            by_id = {row.id: row for row in rows}
            plan_of_changes = reconcile(
                [
                    LedgerRow(
                        id=r.id,
                        key=(r.stage_id, r.area, r.code, r.equipment_class),
                        status=r.status,
                        first_seen_at=r.first_seen_at,
                        last_seen_at=r.last_seen_at,
                        has_verdict=r.verdict_at is not None,
                        verdict=r.verdict,
                    )
                    for r in rows
                ],
                [d.finding for d in result.deviations],
                (period_from, result.as_of),
            )
            texts = {id(d.finding): d for d in result.deviations}
            resolved = set(plan_of_changes.resolve)
            await results.delete(plan_of_changes.delete)
            await results.resolve(plan_of_changes.resolve)
            for row_id, finding, status in plan_of_changes.update:
                if by_id[row_id].status in OPEN and status not in OPEN:
                    resolved.add(row_id)
                await results.update(by_id[row_id], texts[id(finding)], status)
            for finding, status in plan_of_changes.insert:
                await results.insert(run.object_id, texts[id(finding)], status)
            await results.replace_snapshots(result, self._now())

            stored = await RunRepository(session).get(run.id)
            stored.as_of = result.as_of
            stored.plan_version = result.plan_version
            stored.zones_version = result.zones_version
            stored.status = "DONE"
            stored.stats = result.stats | {
                "deviations_open": await results.count_open(run.object_id),
                "deviations_opened": plan_of_changes.opened,
                "deviations_resolved": len(resolved),
                "deviations_withdrawn": len(plan_of_changes.delete),
            }

    async def _fail(self, run_id: UUID, error: DomainError) -> None:
        async with self._factory() as session, session.begin():
            stored = await RunRepository(session).get(run_id)
            stored.status = "FAILED"
            stored.error = {"code": error.code, "message": error.message}
