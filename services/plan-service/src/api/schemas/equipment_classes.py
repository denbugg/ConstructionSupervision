"""Класс техники из equipment_classes.yaml — только чтение (ADR-0014)."""

from pydantic import BaseModel, ConfigDict, Field


class EquipmentClassRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str = Field(examples=["excavator"])
    name_ru: str
    group: str
    transient: bool = Field(
        description="Приезжает рейсами: присутствие считается за окно нескольких сессий"
    )
    works_in_place: bool = Field(
        description="Работает, не сдвигаясь с места: неподвижность на рабочем участке не простой"
    )
    prompts: list[str] = Field(description="Текстовые запросы детектору")
    aliases: list[str] = Field(description="Метки класса во внешних датасетах")
