"""Справочник строительных работ (docs/data-model.md, 1.2)."""

from pydantic import BaseModel, ConfigDict, Field


class WorkTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str = Field(
        examples=["12.3.1"],
        description="Код из файла заказчика. У строки без кода — `<код родителя>/<n>`: "
        "n-я такая строка под ближайшим кодом сверху",
    )
    name: str
    level: int = Field(ge=1, le=4)
    parent_code: str | None
    applicable: dict[str, bool] = Field(
        description="Отметки обязательности по столбцам типов объектов файла. `false` не "
        "запрещает работу для этого типа (ТЗ, п. 1)"
    )
    source: str | None = Field(description="Файл, лист и номер строки первоисточника")


class RestoredCode(BaseModel):
    row: int = Field(description="Строка файла, как в Excel")
    cell: str = Field(description="Дата, которую Excel записал вместо кода")
    code: str


class WorkTypeImportResult(BaseModel):
    work_types: int = Field(description="Сколько строк справочника загружено")
    rows_without_code: int = Field(description="Сколько строк получили код от парсера")
    restored_codes: list[RestoredCode] = Field(
        description="Коды, которые Excel превратил в даты, и во что они восстановлены"
    )
