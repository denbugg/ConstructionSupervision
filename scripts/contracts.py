"""Снапшоты OpenAPI всех сервисов и TS-типы для интерфейса.

    python scripts/contracts.py

1. Снапшот каждого сервиса (`packages/contracts/openapi/<сервис>.json`) снимается тем же
   `openapi_dump.py`, что и в CI, но в одноразовом контейнере из образа сервиса: зависимости
   сервиса есть только там, а код берётся из рабочей копии, смонтированной только для чтения.
   Окружение контейнера — значения по умолчанию, без `.env`, как в CI: иначе снапшот зависел
   бы от настроек стенда и сверка в CI падала бы.
2. Типы (`packages/ts-api-client/src/<сервис>.gen.ts`) генерирует `openapi-typescript`
   из снапшотов; `index.ts` собирает их в пространства имён.

Нужны Docker и собранные образы сервисов (`docker compose build`), Node.js с npm.
Повторный запуск без изменений в коде ничего не меняет.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from _common import ROOT, use_utf8_output

SNAPSHOTS = ROOT / "packages" / "contracts" / "openapi"
CLIENT = ROOT / "packages" / "ts-api-client"
INDEX_HEADER = "// Сгенерировано scripts/contracts.py — руками не править (README пакета).\n"


def services() -> list[str]:
    """Сервисы с приложением FastAPI: у gateway его нет, и искать его не нужно."""
    return sorted(p.parent.parent.name for p in (ROOT / "services").glob("*/src/main.py"))


def images() -> dict[str, str]:
    """Образ каждого сервиса — из docker compose, а не из головы: имена задаёт compose."""
    out = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    return {name: spec.get("image", "") for name, spec in json.loads(out)["services"].items()}


def snapshot(service: str, image: str) -> str:
    """OpenAPI сервиса текстом снапшота; код — из рабочей копии, зависимости — из образа."""
    result = subprocess.run(
        [
            "docker", "run", "--rm", "--network", "none",
            "-v", f"{ROOT}:/repo:ro", "-w", "/repo",
            "--entrypoint", "python", image,
            "scripts/openapi_dump.py", f"services/{service}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )  # fmt: skip
    if result.returncode != 0:
        raise RuntimeError(f"{service}: снапшот не снят\n{result.stderr.strip()}")
    return result.stdout


def write_if_changed(path: Path, text: str) -> bool:
    """LF и UTF-8 без BOM — как у openapi_dump.py в CI; неизменный файл не трогается."""
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return True


def generate_types(names: list[str]) -> list[str]:
    """TS-типы из снапшотов: по файлу на сервис, одинаковые имена схем не сталкиваются."""
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm не найден: нужен Node.js для генерации TS-типов")
    if not (CLIENT / "node_modules").exists():
        subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=CLIENT, check=True)
    changed = []
    for name in names:
        target = CLIENT / "src" / f"{short(name)}.gen.ts"
        before = target.read_text(encoding="utf-8") if target.exists() else None
        subprocess.run(
            [npm, "exec", "--", "openapi-typescript", str(SNAPSHOTS / f"{name}.json"),
             "--output", str(target)],
            cwd=CLIENT,
            check=True,
            capture_output=True,
        )  # fmt: skip
        if target.read_text(encoding="utf-8") != before:
            changed.append(str(target.relative_to(ROOT)))
    index = INDEX_HEADER + "".join(
        f'export type * as {short(n)} from "./{short(n)}.gen";\n' for n in names
    )
    if write_if_changed(CLIENT / "src" / "index.ts", index):
        changed.append("packages/ts-api-client/src/index.ts")
    return changed


def short(service: str) -> str:
    """`plan-service` → `plan`: так же называется префикс пути API сервиса."""
    return service.removesuffix("-service")


def main() -> int:
    use_utf8_output()
    names, known = services(), images()
    missing = [n for n in names if not known.get(n)]
    if missing:
        print(f"В docker-compose.yml нет образа для: {', '.join(missing)}")
        return 1

    changed = []
    for name in names:
        try:
            text = snapshot(name, known[name])
        except RuntimeError as exc:
            print(exc)
            print(f"Образ не собран или устарел? docker compose build {name}")
            return 1
        path = SNAPSHOTS / f"{name}.json"
        if write_if_changed(path, text):
            changed.append(str(path.relative_to(ROOT)))
        print(f"{name:<18} снапшот готов: {len(json.loads(text)['paths'])} путей")

    changed += generate_types(names)
    print("\nИзменены:" if changed else "\nНичего не изменилось.")
    for path in changed:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
