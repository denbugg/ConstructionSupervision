"""Сценарий PDF-отчёта: выводы из своей базы, план и факты периода, снимки → PDF в S3.

Отчёт оформляет выводы последнего прогона и ничего не пересчитывает (README, раздел 5).
Без плана отчёт не собрать — в нём названия и даты этапов, поэтому недоступный plan-service —
ошибка. Недоступность site-service и снимков ошибкой не считается: отчёт выходит, а раздел
«Ограничения» прямо говорит, чего в нём нет (interservice.md, контракт 6). Резюме — от
нейросети после проверки чисел или по шаблону (`services/summary.py`); `POST /summary` отдаёт
его без PDF по тому же контексту.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta, tzinfo
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

from lct_common import DomainError, NotFoundError, UpstreamError, ValidationError, get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from src.clients.plan_client import PlanClient
from src.clients.site_client import SiteClient
from src.clients.storage import ReportStorage, StoredFile
from src.config import settings
from src.core.calendar import calendar_from_plan, local_date
from src.core.inputs import Facts, Plan
from src.dal.models import Deviation, ObjectStatus, StageFact
from src.dal.repositories.deviations import DeviationRepository
from src.dal.repositories.snapshots import SnapshotRepository
from src.report.context import (
    EvidencePick,
    build_context,
    deviations_in_period,
    period_bounds,
    pick_evidence,
)
from src.report.html import Summary, render_html
from src.report.images import ImageUnreadable, evidence_image, missing_image
from src.report.labels import load_labels
from src.report.model import (
    DeviationSnapshot,
    EquipmentDay,
    EvidenceImage,
    Labels,
    ReportInput,
    StageSnapshot,
    StatusSnapshot,
)
from src.report.pdf import ReportKey, parse_report_key, render_pdf
from src.services.results import ObjectNotAnalyzed
from src.services.runs import SERVICE_ROOT, enums
from src.services.summary import Summarizer

log = get_logger(__name__)
PDF = "application/pdf"


class NoDataForPeriod(DomainError):
    code = "NO_DATA_FOR_PERIOD"
    http_status = 422


class RenderFailed(DomainError):
    code = "RENDER_FAILED"
    http_status = 500


class ReportNotFound(NotFoundError):
    code = "REPORT_NOT_FOUND"

    def __init__(self, key: str) -> None:
        super().__init__("Отчёт не найден", key=key)


@dataclass(frozen=True)
class ReportFile:
    key: ReportKey
    size: int
    modified_at: datetime
    url: str


@dataclass(frozen=True)
class CreatedReport:
    file: ReportFile
    as_of: datetime
    summary_generated_by: str
    evidence_shown: int
    evidence_missing: int


@dataclass(frozen=True)
class ReportSummary:
    period_from: date
    period_to: date
    as_of: datetime
    summary: Summary
    # Почему текст нейросети отброшен; пусто — не отбрасывали или нейросеть выключена.
    rejected: list[str]


@lru_cache
def labels() -> Labels:
    path = Path(settings.report_labels_file)
    return load_labels(path if path.is_absolute() else SERVICE_ROOT / path, settings.contracts_dir)


class ReportService:
    def __init__(
        self,
        session: AsyncSession,
        plan_client: PlanClient,
        site_client: SiteClient,
        storage: ReportStorage,
        summarizer: Summarizer,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._session = session
        self._plan = plan_client
        self._site = site_client
        self._storage = storage
        self._summarizer = summarizer
        self._now = now

    async def create(
        self, object_id: UUID, period_from: date | None, period_to: date | None
    ) -> CreatedReport:
        """Собирает PDF за местные дни [period_from, period_to] и кладёт его в бакет."""
        inp, as_of, tz = await self._prepare(object_id, period_from, period_to)
        inp = replace(inp, evidence=await self._evidence(inp))

        context = await run_in_threadpool(build_context, inp)
        summary, _ = await self._summarizer.summarize(context)
        pdf = await self._render(context, summary)
        local = inp.generated_at.astimezone(tz)
        key = ReportKey(object_id, local.date(), *_period(inp), local.time().replace(microsecond=0))
        await self._storage.put(str(key), pdf, PDF)
        log.info("report.created", key=str(key), size=len(pdf), evidence=len(inp.evidence))
        return CreatedReport(
            file=ReportFile(
                key, len(pdf), inp.generated_at, await self._storage.presigned_url(str(key))
            ),
            as_of=as_of,
            summary_generated_by=summary.generated_by,
            evidence_shown=sum(e.problem is None for e in inp.evidence),
            evidence_missing=sum(e.problem is not None for e in inp.evidence),
        )

    async def summary(
        self, object_id: UUID, period_from: date | None, period_to: date | None
    ) -> ReportSummary:
        """Резюме за период без PDF и без снимков: тот же контекст, что у отчёта."""
        inp, as_of, _ = await self._prepare(object_id, period_from, period_to)
        context = await run_in_threadpool(build_context, inp)
        summary, rejected = await self._summarizer.summarize(context)
        period_from, period_to = _period(inp)
        return ReportSummary(period_from, period_to, as_of, summary, rejected)

    async def _prepare(
        self, object_id: UUID, period_from: date | None, period_to: date | None
    ) -> tuple[ReportInput, datetime, tzinfo]:
        """Вход отчёта без снимков, момент анализа и пояс объекта.

        По умолчанию период — `REPORT_DEFAULT_DAYS` дней, заканчивая днём момента анализа:
        отчёт о том, что уже посчитано, а не о сегодняшнем дне без выводов.
        """
        status = await SnapshotRepository(self._session).object_status(object_id)
        if status is None:
            raise ObjectNotAnalyzed(object_id)
        plan = await self._plan.get_plan(object_id)
        cal = calendar_from_plan(plan.calendar)
        period_to = period_to or local_date(cal, status.as_of)
        period_from = period_from or period_to - timedelta(days=settings.report_default_days - 1)
        if period_from > period_to:
            raise ValidationError(
                "Начало периода позже конца",
                period_from=period_from.isoformat(),
                period_to=period_to.isoformat(),
            )

        generated_at = self._now()
        inp = await self._input(object_id, plan, status, period_from, period_to, generated_at)
        start, end = period_bounds(inp)
        facts = await self._facts(object_id, start, end)
        if facts is not None and not facts.sessions:
            raise NoDataForPeriod(
                "За период нет ни одной сессии наблюдения: отчёту не на чем стоять",
                period_from=period_from.isoformat(),
                period_to=period_to.isoformat(),
            )
        inp = replace(
            inp, facts=facts, images_without_time=await self._images_without_time(object_id)
        )
        return inp, status.as_of, cal.tz

    async def list_reports(self, object_id: UUID) -> list[ReportFile]:
        """Отчёты объекта, новые сверху: список — это содержимое бакета, базы у отчётов нет."""
        files = await self._storage.list_files(f"{object_id}/")
        found = [(parse_report_key(f.key), f) for f in files]
        reports = [await self._file(key, f) for key, f in found if key is not None]
        return sorted(reports, key=lambda r: r.modified_at, reverse=True)

    async def get(self, key: str) -> ReportFile:
        parsed = parse_report_key(key)
        stored = await self._storage.stat(key) if parsed is not None else None
        if parsed is None or stored is None:
            raise ReportNotFound(key)
        return await self._file(parsed, stored)

    async def _file(self, key: ReportKey, stored: StoredFile) -> ReportFile:
        url = await self._storage.presigned_url(stored.key)
        return ReportFile(key=key, size=stored.size, modified_at=stored.modified_at, url=url)

    async def _input(
        self,
        object_id: UUID,
        plan: Plan,
        status: ObjectStatus,
        period_from: date,
        period_to: date,
        generated_at: datetime,
    ) -> ReportInput:
        """Вход отчёта из срезов последнего прогона; факты и снимки добавляются следом."""
        snapshots = SnapshotRepository(self._session)
        inp = ReportInput(
            plan=plan,
            status=_status(status),
            stages=[_stage(s) for s in await snapshots.stage_facts(object_id)],
            equipment=[
                EquipmentDay(e.day, e.equipment_class, e.sessions_seen, e.max_count)
                for e in await snapshots.daily_equipment(
                    object_id, period_from, period_to + timedelta(days=1)
                )
            ],
            deviations=(),
            facts=None,
            period_from=period_from,
            period_to=period_to,
            generated_at=generated_at,
            labels=labels(),
            severity_order=enums().values.get("severity", ()),
        )
        start, end = period_bounds(inp)
        rows = await DeviationRepository(self._session).overlapping(object_id, start, end)
        return replace(inp, deviations=[_deviation(d) for d in rows])

    async def _facts(self, object_id: UUID, start: datetime, end: datetime) -> Facts | None:
        try:
            return await self._site.get_facts(object_id, start, end)
        except UpstreamError as exc:
            log.warning("report.facts_unavailable", error=exc.code)
            return None

    async def _images_without_time(self, object_id: UUID) -> int | None:
        try:
            return await self._site.count_images_without_time(object_id)
        except UpstreamError as exc:
            log.warning("report.images_count_unavailable", error=exc.code)
            return None

    async def _evidence(self, inp: ReportInput) -> list[EvidenceImage]:
        picks = pick_evidence(
            deviations_in_period(inp), inp.severity_order, settings.report_max_evidence_images
        )
        names = {c.code: c.name_ru for c in inp.plan.equipment_classes}
        return list(await asyncio.gather(*(self._image(p, names) for p in picks)))

    async def _image(self, pick: EvidencePick, names: dict[str, str]) -> EvidenceImage:
        """Один снимок; любая неудача — пометка с причиной, а не отказ всего отчёта."""
        try:
            detail = await self._site.get_image(pick.image_id)
        except UpstreamError as exc:
            if exc.http_status == 404:
                return missing_image(pick, "снимок удалён в site-service")
            return missing_image(pick, "site-service недоступен")
        url = detail.get("url")
        if not url:
            return missing_image(pick, "у снимка нет файла")
        try:
            content = await self._site.download(url)
        except UpstreamError:
            return missing_image(pick, "файл снимка недоступен в хранилище")
        try:
            return await run_in_threadpool(
                evidence_image, pick, detail, content, names, settings.report_image_max_px
            )
        except ImageUnreadable:
            return missing_image(pick, "файл снимка не читается")

    async def _render(self, context: dict[str, Any], summary: Summary) -> bytes:
        """HTML → PDF в пуле потоков: WeasyPrint блокирующий и небыстрый."""
        try:
            return await run_in_threadpool(lambda: render_pdf(render_html(context, summary)))
        # Jinja2 и WeasyPrint бросают разнородные ошибки: любая из них — отказ вёрстки.
        except Exception as exc:
            log.exception("report.render_failed", error=type(exc).__name__)
            raise RenderFailed("PDF-отчёт не сформирован", cause=type(exc).__name__) from exc


def _period(inp: ReportInput) -> tuple[date, date]:
    return inp.period_from, inp.period_to


def _status(row: ObjectStatus) -> StatusSnapshot:
    return StatusSnapshot(
        as_of=row.as_of,
        computed_at=row.computed_at,
        status=row.status,
        delay_days=row.delay_days,
        spi=row.spi,
        confidence=row.confidence,
        facts=row.counters.get("facts", {}),
        blind_areas=row.counters.get("blind_areas", 0),
        stages_at_risk=row.stages_at_risk,
    )


def _stage(row: StageFact) -> StageSnapshot:
    return StageSnapshot(
        stage_id=row.stage_id,
        actual_start=row.actual_start,
        progress=row.progress,
        planned_progress=row.planned_progress,
        spi=row.spi,
        forecast_end=row.forecast_end,
        delay_days=row.delay_days,
        status=row.status,
        confidence=row.confidence,
        basis=row.facts.get("basis"),
    )


def _deviation(row: Deviation) -> DeviationSnapshot:
    return DeviationSnapshot(
        id=row.id,
        code=row.code,
        severity=row.severity,
        status=row.status,
        verdict=row.verdict,
        stage_id=row.stage_id,
        area=row.area,
        equipment_class=row.equipment_class,
        title=row.title,
        message=row.message,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        evidence=row.evidence or (),
    )
