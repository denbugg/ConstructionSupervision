"""DTO рабочего календаря. Рабочие часы — местное время часового пояса календаря."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class WorkHours(BaseModel):
    start: str = Field(pattern=HHMM, examples=["07:00"])
    end: str = Field(pattern=HHMM, examples=["23:00"])


class CalendarCreate(BaseModel):
    code: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
        examples=["moscow-5day"],
        description="Не меняется после создания: на код ссылается DEFAULT_CALENDAR",
    )
    name: str = Field(min_length=1, max_length=200)
    timezone: str = Field(default="Europe/Moscow", description="IANA, например Europe/Moscow")
    weekend_days: list[int] = Field(description="Выходные по ISO: понедельник = 1, воскресенье = 7")
    holidays: list[date] = Field(
        default_factory=list, description="Нерабочие праздничные дни; у каждой даты — источник"
    )
    work_hours: WorkHours


class CalendarUpdate(BaseModel):
    """Частичное изменение. Списки заменяются целиком: праздник убирается новым списком."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = None
    weekend_days: list[int] | None = None
    holidays: list[date] | None = None
    work_hours: WorkHours | None = None


class CalendarRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    timezone: str
    weekend_days: list[int]
    holidays: list[date]
    work_hours: WorkHours
    created_at: datetime
    updated_at: datetime
