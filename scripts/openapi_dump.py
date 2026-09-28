"""Снимает спецификацию OpenAPI из кода сервиса, не поднимая его.

Используется в CI и в `contracts.py`: контракт проверяется без запущенной БД.
Приложение только импортируется — lifespan не выполняется, соединений нет.

    python scripts/openapi_dump.py services/plan-service
"""

import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def dump(service_dir: Path) -> dict:
    # Схемы строят типы перечислений из enums.yaml при импорте: без справочных файлов
    # сервис не импортируется. В контейнере они в /contracts, в рабочей копии и CI — здесь.
    os.environ.setdefault("CONTRACTS_DIR", str(ROOT / "packages" / "contracts"))
    sys.path.insert(0, str(service_dir.resolve()))
    module = importlib.import_module("src.main")
    return module.app.openapi()


def render(spec: dict) -> str:
    """Текст снапшота: один и тот же в CI и в `contracts.py`, иначе сверка шумит."""
    return json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("использование: python scripts/openapi_dump.py <каталог сервиса>", file=sys.stderr)
        raise SystemExit(2)

    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(render(dump(Path(sys.argv[1]))))
