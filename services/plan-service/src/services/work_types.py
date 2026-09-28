"""Справочник строительных работ: импорт XLSX заказчика и чтение (ТЗ, п. 1).

Справочник один на систему и заменяется целиком. Этапы ссылаются на него кодами без внешних
ключей (`stage.work_codes`), поэтому перезагрузка справочника график не трогает.
"""

from dataclasses import asdict
from typing import Any

from lct_common import ValidationError, get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.reference_import import (
    ReferenceImportError,
    code_sort_key,
    parse_work_types,
    read_sheet,
)
from src.dal.models import WorkType
from src.dal.repositories.work_types import WorkTypeRepository

log = get_logger(__name__)


class WorkTypesImportInvalid(ValidationError):
    code = "WORK_TYPES_IMPORT_INVALID"


class WorkTypeService:
    def __init__(self, session: AsyncSession) -> None:
        self._work_types = WorkTypeRepository(session)

    async def list(
        self, *, level: int | None, parent_code: str | None, limit: int, offset: int
    ) -> tuple[list[WorkType], int]:
        """Строки в порядке файла заказчика: «10.2» раньше «10.10»."""
        rows = sorted(
            await self._work_types.filtered(level=level, parent_code=parent_code),
            key=lambda w: code_sort_key(w.code),
        )
        return rows[offset : offset + limit], len(rows)

    async def import_file(self, filename: str, content: bytes, actor: str | None) -> dict[str, Any]:
        if len(content) > settings.plan_import_max_mb * 1024 * 1024:
            raise WorkTypesImportInvalid(
                f"Файл больше {settings.plan_import_max_mb} МБ",
                limit_mb=settings.plan_import_max_mb,
            )
        try:
            sheet, table = read_sheet(content)
            parsed = parse_work_types(table, filename=filename, sheet=sheet)
        except ReferenceImportError as exc:
            raise WorkTypesImportInvalid(
                str(exc), errors=[asdict(issue) for issue in exc.issues]
            ) from exc

        await self._work_types.replace_all(
            [
                WorkType(
                    code=item.code,
                    name=item.name,
                    level=item.level,
                    parent_code=item.parent_code,
                    applicable=item.applicable,
                    source=item.source,
                )
                for item in parsed
            ]
        )
        restored = [
            {"row": i.row, "cell": i.restored_from, "code": i.code}
            for i in parsed
            if i.restored_from
        ]
        without_code = sum(1 for i in parsed if not i.code_in_file)
        log.info(
            "work_types.imported",
            filename=filename,
            work_types=len(parsed),
            restored_codes=len(restored),
            actor=actor,
        )
        return {
            "work_types": len(parsed),
            "rows_without_code": without_code,
            "restored_codes": restored,
        }
