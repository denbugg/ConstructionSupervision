"""Тесты сервисов в одноразовых контейнерах из их образов — то же, что `make test`, но на Windows.

    python scripts/test.py              # все сервисы с тестами
    python scripts/test.py plan site    # выбранные

На хосте pytest сервиса не запустить: зависимости и `lct_common` есть только в образе. Поэтому
тесты идут в контейнере образа сервиса, а код сервиса и `packages/contracts` монтируются из
рабочей копии. `py-common` берётся из образа: правка его требует `docker compose build`.

API-тесты пишут в базу и откатывают миграции до нуля, поэтому им нужна отдельная база
`<база>_test` с владельцем — ролью сервиса (README сервисов, «Запуск и тесты»). Если её нет,
скрипт её заводит. Нужен поднятый `postgres` стека: `docker compose up -d postgres`.
"""

import json
import subprocess
import sys

from _common import ROOT, load_env, use_utf8_output

# Версии — как в requirements-dev.txt сервисов: в рабочих образах pytest нет.
PYTEST = "pytest==8.3.4 pytest-asyncio==0.25.0"
# Переменная с DSN рабочей базы сервиса; сервисы без базы здесь не перечислены.
DSN_VARS = {"plan": "PLAN_DB_DSN", "site": "SITE_DB_DSN", "analysis": "ANALYSIS_DB_DSN"}


def compose_config() -> dict:
    out = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    return json.loads(out)


def ensure_test_db(dsn: str, superuser: str) -> str:
    """DSN тестовой базы рядом с рабочей: та же роль, имя `<база>_test`; база заводится один раз."""
    prefix, _, db = dsn.rpartition("/")
    user = prefix.split("://", 1)[1].split(":", 1)[0]
    test_db = f"{db}_test"

    def psql(sql: str, database: str = "postgres") -> str:
        return subprocess.run(
            ["docker", "compose", "exec", "-T", "postgres",
             "psql", "-U", superuser, "-d", database, "-tAc", sql],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()  # fmt: skip

    if psql(f"SELECT 1 FROM pg_database WHERE datname = '{test_db}'") != "1":
        # Как в infra/postgres/init/01-databases.sh для рабочей базы.
        psql(f"CREATE DATABASE {test_db} OWNER {user}")
        psql("CREATE EXTENSION IF NOT EXISTS pgcrypto", test_db)
        psql(f"ALTER SCHEMA public OWNER TO {user}", test_db)
        print(f"  заведена база {test_db}")
    return f"{prefix}/{test_db}"


def run_tests(service: str, image: str, network: str, dsn: str | None) -> int:
    """pytest сервиса в контейнере его образа; код возврата — как у pytest."""
    app = f"/app/services/{service}"
    cmd = [
        "docker", "run", "--rm", "--network", network,
        "-v", f"{ROOT / 'services' / service}:{app}",
        "-v", f"{ROOT / 'packages' / 'contracts'}:/app/packages/contracts:ro",
        "-e", "CONTRACTS_DIR=/app/packages/contracts",
        "-w", app, "--entrypoint", "sh",
    ]  # fmt: skip
    if dsn:
        cmd += ["-e", f"TEST_DB_DSN={dsn}"]
    pip = "pip install -q --disable-pip-version-check --root-user-action=ignore"
    script = f"{pip} {PYTEST} && PYTHONPATH=. pytest -q"
    return subprocess.run([*cmd, image, "-c", script], cwd=ROOT).returncode


def main() -> int:
    use_utf8_output()
    env = load_env()
    config = compose_config()
    # Сеть стека: по ней контейнер с тестами видит postgres под его именем в compose.
    network = next(iter(config["networks"].values()))["name"]
    available = sorted(
        p.parent.name.removesuffix("-service") for p in (ROOT / "services").glob("*/tests")
    )
    wanted = sys.argv[1:] or available
    unknown = [s for s in wanted if s not in available]
    if unknown:
        print(f"Нет сервиса с тестами: {', '.join(unknown)}. Есть: {', '.join(available)}")
        return 2

    failed = []
    for short in wanted:
        service = f"{short}-service"
        # flush: иначе заголовок окажется после вывода pytest из дочернего процесса.
        print(f"\n=== {service}", flush=True)
        dsn = None
        if short in DSN_VARS:
            dsn = ensure_test_db(env[DSN_VARS[short]], env.get("POSTGRES_SUPERUSER", "postgres"))
        if run_tests(service, config["services"][service]["image"], network, dsn) != 0:
            failed.append(service)

    print("\nВсе тесты прошли." if not failed else f"\nУпали: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
