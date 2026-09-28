"""Классы техники. Правятся в файле equipment_classes.yaml, через API — только чтение."""

from typing import Annotated

from fastapi import APIRouter, Depends
from lct_common import Page, PageParams

from src.api.schemas.common import EquipmentGroup
from src.api.schemas.equipment_classes import EquipmentClassRead
from src.services.equipment_classes import list_classes

router = APIRouter(prefix="/equipment-classes", tags=["Справочники"])


@router.get(
    "",
    response_model=Page[EquipmentClassRead],
    summary="Классы техники",
    description="Новый класс — запись в `packages/contracts/equipment_classes.yaml` и "
    "перезапуск plan-service и vision-service, без правки кода.",
)
async def get_equipment_classes(
    params: Annotated[PageParams, Depends()],
    group: EquipmentGroup | None = None,
    transient: bool | None = None,
):
    classes = list_classes(group, transient)
    page = classes[params.offset : params.offset + params.limit]
    return Page[EquipmentClassRead].of(
        [EquipmentClassRead.model_validate(c) for c in page], len(classes), params
    )
