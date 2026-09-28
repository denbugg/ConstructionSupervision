"""Распознавание снимка (F2, F6) и описание загруженных моделей."""

import json

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError as PydanticValidationError
from starlette.datastructures import UploadFile

from src.api.deps import AnalyzerDep
from src.api.schemas.analyze import AnalyzeRequest, AnalyzeResult, ModelRead
from src.services.analyze import UnsupportedMediaType

router = APIRouter(tags=["Распознавание"])

# Один эндпоинт принимает два вида тела, а FastAPI из сигнатуры описывает только один:
# тело разбирается вручную, а в OpenAPI оба варианта перечислены явно.
REQUEST_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {"schema": AnalyzeRequest.model_json_schema()},
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {"file": {"type": "string", "format": "binary"}},
                }
            },
        },
    }
}


@router.post(
    "/analyze",
    response_model=AnalyzeResult,
    summary="Распознать снимок",
    description="Детекция техники, стадия объекта и качество кадра за один вызов. Тело — JSON "
    '`{"image_url": ...}` (так вызывает site-worker) или `multipart/form-data` с полем `file` '
    "для ручной проверки. Рамки нормированы 0…1. Недоступная ссылка — `UPSTREAM_UNAVAILABLE`.",
    openapi_extra=REQUEST_BODY,
)
async def analyze(request: Request, analyzer: AnalyzerDep) -> AnalyzeResult:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        return await analyzer.analyze_url(await _json_body(request))
    if content_type.startswith("multipart/form-data"):
        return await analyzer.analyze_bytes(await _form_file(request))
    raise UnsupportedMediaType(
        "Тело запроса — application/json или multipart/form-data", content_type=content_type
    )


@router.get(
    "/model",
    response_model=ModelRead,
    summary="Загруженные модели",
    description="Детектор, классификатор стадии, фактическое устройство, версия и словарь "
    "классов, пороги детектора. До окончания загрузки — `MODEL_NOT_LOADED`.",
)
async def model(analyzer: AnalyzerDep) -> ModelRead:
    return analyzer.describe()


async def _json_body(request: Request) -> str:
    try:
        payload = AnalyzeRequest.model_validate(await request.json())
    except json.JSONDecodeError as exc:
        raise RequestValidationError(
            [{"loc": ("body",), "msg": "Тело не разбирается как JSON", "type": "json_invalid"}]
        ) from exc
    except PydanticValidationError as exc:
        raise RequestValidationError(
            [{**e, "loc": ("body", *e["loc"])} for e in exc.errors()]
        ) from exc
    return payload.image_url


async def _form_file(request: Request) -> bytes:
    form = await request.form()
    file = form.get("file")
    if not isinstance(file, UploadFile):
        raise RequestValidationError(
            [{"loc": ("body", "file"), "msg": "Нужен файл в поле file", "type": "missing"}]
        )
    return await file.read()
