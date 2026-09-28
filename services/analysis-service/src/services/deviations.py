"""Лента отклонений: список, карточка, объяснение, вердикт оператора (методика, разделы 9, 12).

Отклонение объясняется тем, что уже сохранено: текст, `facts`, доказательства и
действующая настройка правила. Сессии эпизода запрашиваются у site-service — своих
первичных данных у analysis нет. Если site недоступен, объяснение всё равно отдаётся,
но без сессий и с причиной: «не знаем», а не «сессий не было».
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from lct_common import ConflictError, NotFoundError, UpstreamError, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.site_client import SiteClient
from src.config import settings
from src.core.ledger import CONFIRMED, REJECTED, RESOLVED
from src.dal.models import Deviation
from src.dal.models import DeviationRule as DeviationRuleRow
from src.dal.repositories.deviations import DeviationFilter, DeviationRepository
from src.dal.repositories.rules import RuleRepository
from src.services.runs import enums

SORTABLE = ("last_seen_at", "first_seen_at", "severity")
VERDICTS = (CONFIRMED, REJECTED)
OUTSIDE = "OUTSIDE"
# Составной участок D1/D2 (несколько участков одного типа) хранится через этот разделитель.
AREA_SEPARATOR = " + "


class DeviationNotFound(NotFoundError):
    code = "DEVIATION_NOT_FOUND"

    def __init__(self, deviation_id: UUID) -> None:
        super().__init__("Отклонение не найдено", deviation_id=str(deviation_id))


class InvalidVerdict(ValidationError):
    code = "INVALID_VERDICT"


class VerdictConflict(ConflictError):
    code = "VERDICT_CONFLICT"


@dataclass(frozen=True)
class Explanation:
    deviation: Deviation
    rule: DeviationRuleRow | None
    sessions: list[dict[str, Any]] | None
    sessions_truncated: bool
    sessions_unavailable_reason: str | None


def _check_values(name: str, values: list[str], enum: str) -> None:
    allowed = enums().values.get(enum, ())
    unknown = sorted(set(values) - set(allowed))
    if unknown:
        raise ValidationError(
            f"Неизвестное значение фильтра {name}", unknown=unknown, allowed=list(allowed)
        )


class DeviationService:
    def __init__(self, session: AsyncSession, site_client: SiteClient | None = None) -> None:
        self._session = session
        self._repo = DeviationRepository(session)
        self._site = site_client

    async def feed(
        self, flt: DeviationFilter, *, sort: str, limit: int, offset: int
    ) -> tuple[list[Deviation], int]:
        _check_values("code", list(flt.codes), "deviation_code")
        _check_values("severity", list(flt.severities), "severity")
        _check_values("status", list(flt.statuses), "deviation_status")
        unknown = sorted(set(flt.verdicts) - set(VERDICTS))
        if unknown:
            raise ValidationError(
                "Неизвестное значение фильтра verdict", unknown=unknown, allowed=list(VERDICTS)
            )
        if sort.removeprefix("-") not in SORTABLE:
            raise ValidationError(
                "Сортировка по этому полю не поддерживается", sort=sort, allowed=list(SORTABLE)
            )
        return await self._repo.page(
            flt,
            sort=sort,
            severity_order=enums().values.get("severity", ()),
            limit=limit,
            offset=offset,
        )

    async def get(self, deviation_id: UUID) -> Deviation:
        row = await self._repo.get(deviation_id)
        if row is None:
            raise DeviationNotFound(deviation_id)
        return row

    async def verdict(
        self, deviation_id: UUID, status: str, comment: str | None, actor: str | None
    ) -> Deviation:
        """Подтвердить или пометить ложным — открытое или закрытое (методика, раздел 9, п. 3).

        Открытое получает вердикт и в статус; закрытое остаётся `RESOLVED`, вердикт — в поле
        `verdict`. `REJECTED` прогон не открывает заново, пока условие держится (core/ledger.py).
        """
        if status not in VERDICTS:
            raise InvalidVerdict(
                "Вердикт — CONFIRMED или REJECTED", status=status, allowed=list(VERDICTS)
            )
        row = await self.get(deviation_id)
        if row.status != RESOLVED:
            row.status = status
        row.verdict = status
        row.verdict_comment = comment
        row.verdict_by = actor
        row.verdict_at = datetime.now(UTC)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            # Отклонённый эпизод закончился, по тому же ключу уже открыт новый: подтверждать
            # нужно новый, а не старый — открытая строка по ключу одна.
            raise VerdictConflict(
                "По этому ключу уже открыто более новое отклонение", deviation_id=str(row.id)
            ) from exc
        await self._session.refresh(row)
        return row

    async def explain(self, deviation_id: UUID) -> Explanation:
        row = await self.get(deviation_id)
        rule = await RuleRepository(self._session).get(row.code)
        sessions, truncated, reason = None, False, None
        try:
            sessions, truncated = await self._episode_sessions(row)
        except UpstreamError as exc:
            reason = exc.message
        return Explanation(row, rule, sessions, truncated, reason)

    async def _episode_sessions(self, row: Deviation) -> tuple[list[dict[str, Any]], bool]:
        """Сессии эпизода с фактами участка отклонения — как их прислал site-service."""
        facts = await self._site.get_facts(row.object_id, row.first_seen_at, row.last_seen_at)
        sessions = sorted(
            (s for s in facts.sessions if row.first_seen_at <= s.window_start < row.last_seen_at),
            key=lambda s: s.window_start,
        )
        limit = settings.explain_max_sessions
        truncated = len(sessions) > limit
        areas = set(row.area.split(AREA_SEPARATOR)) if row.area else None
        result = []
        for session in sessions[-limit:]:
            item = session.model_dump(
                mode="json",
                include={
                    "session_id",
                    "window_start",
                    "window_end",
                    "cameras",
                    "stage_observation",
                },
            )
            item["areas"] = [
                a.model_dump(mode="json") for a in session.areas if areas is None or a.area in areas
            ]
            if areas is None or OUTSIDE in areas:
                item["outside_zones"] = [e.model_dump(mode="json") for e in session.outside_zones]
            result.append(item)
        return result, truncated
