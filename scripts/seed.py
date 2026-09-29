"""Демо-данные в поднятый стек и прогон анализа.

    python scripts/seed.py [--force-plan] [--timeout 900]

Шаги: объект из data/seed/object.json (ищется по имени, иначе создаётся) → график из
data/seed/schedule.xlsx (если у объекта его ещё нет; --force-plan заменяет) → правила этапов без
шаблона из data/seed/rules.json (если у этапа правила нет) → снимки из
data/seed/images через POST /images/import → камеры и зоны из data/seed/cameras.json →
ожидание распознавания → если разметка изменилась, ожидание пересчёта фактов окон по ней →
POST /analysis/runs?wait=true → сводка отклонений.

Снимки грузятся раньше зон: эталонным кадром камеры становится её первый снимок
(services/site-service/README.md, раздел 9). Всё повторяемо: объект находится по имени, дубли
снимков отклоняются по sha256, повторный импорт зон ничего не меняет. Адрес gateway и ключ —
из .env (GATEWAY_PORT, API_KEY); в контейнере tools — GATEWAY_URL.
"""

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx
from _common import ROOT, gateway_url, load_env, use_utf8_output

SEED = ROOT / "data" / "seed"
# Сколько снимков ещё не распознано: пока не ноль, прогон увидел бы неполные окна.
WAITING_STATUSES = ("PENDING", "PROCESSING")
POLL_S = 3.0
PAGE = 200


class SeedError(Exception):
    """Шаг не удался; сообщение — для человека."""


def check(resp: httpx.Response, step: str) -> dict:
    """Тело успешного ответа или понятная ошибка с кодом и сообщением сервиса."""
    if resp.is_success:
        return resp.json() if resp.content else {}
    try:
        error = resp.json()["error"]
        detail = f"{error['code']}: {error['message']}"
    except (ValueError, KeyError, TypeError):
        detail = resp.text[:300]
    raise SeedError(f"{step}: HTTP {resp.status_code} — {detail}")


def connect(env: dict[str, str], actor: str) -> httpx.Client:
    """Клиент gateway: адрес и ключ из .env, `actor` — кто правит, для журналов сервисов."""
    base = f"{gateway_url(env)}/api/v1"
    headers = {"X-API-Key": env.get("API_KEY", ""), "X-Actor": actor}
    # Прогон с ожиданием держит соединение, пока analysis не закончит (RUN_WAIT_TIMEOUT_S).
    return httpx.Client(base_url=base, headers=headers, timeout=180)


def object_spec() -> dict:
    """Карточка демо-объекта из object.json."""
    return json.loads((SEED / "object.json").read_text(encoding="utf-8"))


def ensure_object(client: httpx.Client, spec: dict) -> dict:
    """Объект с именем из `spec`: найденный или только что созданный."""
    page = check(client.get("/plan/objects", params={"limit": 200}), "список объектов")
    for item in page["items"]:
        if item["name"] == spec["name"] and item["status"] != "ARCHIVED":
            print(f"объект     найден {item['id']}")
            return item
    created = check(client.post("/plan/objects", json=spec), "создание объекта")
    print(f"объект     создан {created['id']}")
    return created


def import_plan(client: httpx.Client, obj: dict, force: bool) -> None:
    """График из XLSX; существующий не трогается без --force-plan."""
    if obj["plan_version"] > 0 and not force:
        print(f"график     уже есть (plan_version {obj['plan_version']}), --force-plan заменит")
        return
    path = SEED / "schedule.xlsx"
    with path.open("rb") as file:
        files = {"file": (path.name, file, "application/octet-stream")}
        params = {"force": "true"} if force else {}
        body = check(
            client.post(f"/plan/objects/{obj['id']}/plan/import", files=files, params=params),
            "импорт графика",
        )
    print(f"график     {body['stages']} этапов, plan_version {body['plan_version']}")


def ensure_rules(client: httpx.Client, object_id: str) -> None:
    """Правила из rules.json этапам без правила: у них нет шаблона, импорт правило не ставит.

    Существующее правило не трогается: его могли поправить в интерфейсе.
    """
    rules = json.loads((SEED / "rules.json").read_text(encoding="utf-8"))["rules"]
    stages = check(
        client.get(f"/plan/objects/{object_id}/stages", params={"limit": 200}), "этапы объекта"
    )["items"]
    by_code = {stage["code"]: stage for stage in stages}
    for code, rule in rules.items():
        stage = by_code.get(code)
        if stage is None:
            raise SeedError(f"правило для этапа {code}, а его нет в schedule.xlsx")
        if stage["rule"] is not None:
            print(f"правило    {code} уже есть (версия {stage['rule']['version']})")
            continue
        check(client.post("/plan/rules", json={"stage_id": stage["id"], **rule}), f"правило {code}")
        print(f"правило    {code} поставлено")


def import_images(client: httpx.Client, object_id: str) -> None:
    """Все подпапки data/seed/images: первая подпапка — код камеры."""
    # Без кадров импорт честно примет ноль файлов, и объект выйдет пустым — это не демо.
    if not any(p.is_file() for p in (SEED / "images").glob("*/*")):
        raise SeedError(
            "в data/seed/images нет демо-кадров: скачайте их командой "
            "`docker compose run --rm tools python scripts/fetch_models.py` (README, раздел 3)"
        )
    body = check(
        client.post("/site/images/import", json={"object_id": object_id, "path": ""}),
        "загрузка снимков",
    )
    reasons = Counter(item["code"] for item in body["rejected"])
    skipped = ", ".join(f"{code} {n}" for code, n in reasons.items()) or "нет"
    print(f"снимки     принято {len(body['accepted'])}, отклонено: {skipped}")
    no_time = [item["file"] for item in body["accepted"] if item["status"] == "NEEDS_TIME"]
    if no_time:
        raise SeedError(f"снимки без времени (имя файла не ГГГГММДД_ЧЧММСС): {no_time[:5]}")


def import_zones(client: httpx.Client, object_id: str) -> datetime | None:
    """Камеры и зоны из cameras.json; камеры сверяются по коду, зоны — по участку.

    Возвращает время сервера на момент импорта, если разметка изменилась: site пересчитает
    факты окон в фоне (`reapply_zones`), и прогон нужно запускать после этого.
    """
    spec = json.loads((SEED / "cameras.json").read_text(encoding="utf-8"))
    resp = client.post("/site/zones/import", json={"object_id": object_id, **spec})
    body = check(resp, "импорт зон")
    print(
        f"зоны       камер новых {body['cameras_created']}, обновлено {body['cameras_updated']};"
        f" зон новых {body['zones_created']}, обновлено {body['zones_updated']};"
        f" участков {len(body['areas'])}"
    )
    if not body["areas"]:
        print("           зон нет: вся техника окажется вне участков, а этапы — без участков (D10)")
    changed = body["zones_created"] + body["zones_updated"] + body["cameras_updated"]
    return parsedate_to_datetime(resp.headers["date"]) if changed else None


def wait_zones_applied(
    client: httpx.Client, object_id: str, since: datetime, timeout_s: float
) -> None:
    """Ждать, пока факты всех окон объекта пересчитаны по новой разметке.

    `reapply_zones` пишет окна одной транзакцией и ставит им `updated_at` — время её
    начала, а оно позже импорта зон. Заголовок Date округлён до секунды, отсюда запас.
    """
    threshold = since - timedelta(seconds=1)
    deadline = time.monotonic() + timeout_s
    while True:
        stale = sum(u < threshold for u in session_updates(client, object_id))
        if stale == 0:
            print(f"разметка   факты окон пересчитаны{' ' * 20}")
            return
        if time.monotonic() > deadline:
            raise SeedError(f"за {timeout_s:.0f} с не пересчитано {stale} окон: site-worker жив?")
        print(f"пересчёт по зонам: осталось окон {stale}", end="\r", flush=True)
        time.sleep(POLL_S)


def session_updates(client: httpx.Client, object_id: str) -> list[datetime]:
    """Когда факт каждого окна объекта пересчитан последний раз."""
    updates: list[datetime] = []
    offset = 0
    while True:
        page = check(
            client.get(
                "/site/sessions",
                params={"object_id": object_id, "limit": PAGE, "offset": offset},
            ),
            "окна наблюдения",
        )
        updates += [datetime.fromisoformat(s["updated_at"]) for s in page["items"]]
        offset += PAGE
        if offset >= page["total"]:
            return updates


def wait_recognition(client: httpx.Client, object_id: str, timeout_s: float) -> None:
    """Ждать, пока воркер распознает все снимки объекта."""
    deadline = time.monotonic() + timeout_s
    while True:
        left = 0
        for status in WAITING_STATUSES:
            page = check(
                client.get(
                    "/site/images", params={"object_id": object_id, "status": status, "limit": 1}
                ),
                "статус снимков",
            )
            left += page["total"]
        if left == 0:
            break
        if time.monotonic() > deadline:
            raise SeedError(f"за {timeout_s:.0f} с не распознано {left} снимков: site-worker жив?")
        print(f"распознавание: осталось {left}", end="\r", flush=True)
        time.sleep(POLL_S)
    failed = check(
        client.get("/site/images", params={"object_id": object_id, "status": "FAILED", "limit": 1}),
        "статус снимков",
    )["total"]
    print(f"распознавание готово{' ' * 20}" + (f"; с ошибкой {failed}" if failed else ""))


def run_analysis(client: httpx.Client, object_id: str) -> dict:
    """Прогон анализа с ожиданием и сводка отклонений по кодам."""
    run = check(
        client.post(
            "/analysis/runs",
            params={"wait": "true"},
            json={"object_id": object_id, "triggered_by": "MANUAL"},
        ),
        "прогон анализа",
    )
    print(f"прогон     {run.get('status')}, as_of {run.get('as_of')}")
    items = deviations(client, object_id)
    codes = Counter(item["code"] for item in items)
    summary = ", ".join(f"{code} {n}" for code, n in sorted(codes.items())) or "нет"
    print(f"отклонения {len(items)}: {summary}")
    return run


def deviations(client: httpx.Client, object_id: str) -> list[dict]:
    """Вся лента объекта: открытые и закрытые строки."""
    items: list[dict] = []
    offset = 0
    while True:
        page = check(
            client.get(
                "/analysis/deviations",
                params={"object_id": object_id, "limit": PAGE, "offset": offset},
            ),
            "отклонения",
        )
        items += page["items"]
        offset += PAGE
        if offset >= page["total"]:
            return items


def prepare(client: httpx.Client, spec: dict, *, force_plan: bool, timeout_s: float) -> dict:
    """Объект со всеми данными из data/seed, распознанный и с фактами по текущей разметке."""
    obj = ensure_object(client, spec)
    import_plan(client, obj, force_plan)
    ensure_rules(client, obj["id"])
    import_images(client, obj["id"])
    zones_changed_at = import_zones(client, obj["id"])
    wait_recognition(client, obj["id"], timeout_s)
    if zones_changed_at is not None:
        wait_zones_applied(client, obj["id"], zones_changed_at, timeout_s)
    return obj


def main() -> int:
    use_utf8_output()
    parser = argparse.ArgumentParser(description="Демо-данные и прогон анализа")
    parser.add_argument("--force-plan", action="store_true", help="заменить график объекта")
    parser.add_argument("--timeout", type=float, default=900, help="ожидание распознавания, с")
    args = parser.parse_args()

    with connect(load_env(), "seed.py") as client:
        try:
            obj = prepare(client, object_spec(), force_plan=args.force_plan, timeout_s=args.timeout)
            run_analysis(client, obj["id"])
        except SeedError as exc:
            print(f"\nОшибка: {exc}")
            return 1
        except httpx.TransportError as exc:
            print(f"\nСтек недоступен по {client.base_url}: {exc}. Поднят ли docker compose?")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
