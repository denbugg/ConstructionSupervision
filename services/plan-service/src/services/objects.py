"""Сценарии работы с объектами: оркестрация репозитория и доменных правил.

Формул и правил здесь нет — они живут в core/. Здесь только «получить,
проверить, сохранить».
"""

from uuid import UUID

from lct_common import NotFoundError, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.objects import ObjectCreate, ObjectUpdate
from src.config import settings
from src.dal.models import ConstructionObject
from src.dal.repositories.calendars import CalendarRepository
from src.dal.repositories.objects import ObjectRepository


class ObjectService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = ObjectRepository(session)
        self._calendars = CalendarRepository(session)

    async def create(self, payload: ObjectCreate) -> ConstructionObject:
        # Календарь по умолчанию (DEFAULT_CALENDAR); кода нет в базе — объект без календаря.
        calendar = await self._calendars.by_code(settings.default_calendar)
        obj = ConstructionObject(
            calendar_id=calendar.id if calendar else None,
            name=payload.name.strip(),
            # Тип не указан — считаем объект монолитным жильём: это самый частый
            # случай АИП Москвы и тип демо-объекта. Разбора наименования нет (ADR-0011).
            object_type=payload.object_type or "RESIDENTIAL_MONOLITH",
            address=payload.address,
            plan_start=payload.plan_start,
            tep=payload.tep,
            status="DRAFT",
        )
        return await self._repo.add(obj)

    async def get(self, object_id: UUID) -> ConstructionObject:
        obj = await self._repo.get(object_id)
        if obj is None:
            raise ObjectNotFound(object_id)
        return obj

    async def list(
        self, *, limit: int, offset: int, status: str | None, object_type: str | None
    ) -> tuple[list[ConstructionObject], int]:
        return await self._repo.list(
            limit=limit, offset=offset, status=status, object_type=object_type
        )

    async def update(self, object_id: UUID, payload: ObjectUpdate) -> ConstructionObject:
        obj = await self.get(object_id)
        changes = payload.model_dump(exclude_unset=True)

        if "plan_start" in changes and obj.plan_version > 0:
            # Сдвиг даты начала после построения графика меняет все этапы,
            # поэтому выполняется перегенерацией плана, а не правкой поля.
            raise ValidationError(
                "Дата начала меняется через перегенерацию плана, а не напрямую",
                object_id=str(object_id),
                plan_version=obj.plan_version,
            )

        for field, value in changes.items():
            setattr(obj, field, value)
        return obj

    async def archive(self, object_id: UUID) -> None:
        """Объект не удаляется физически: на него ссылаются снимки и выводы."""
        obj = await self.get(object_id)
        obj.status = "ARCHIVED"


class ObjectNotFound(NotFoundError):
    code = "OBJECT_NOT_FOUND"

    def __init__(self, object_id: UUID) -> None:
        super().__init__("Объект не найден", object_id=str(object_id))
