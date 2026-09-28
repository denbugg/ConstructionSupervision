"""Сквозной сценарий на поднятом стеке: заложенные отклонения найдены, лишних нет.

    python scripts/e2e.py [--timeout 900]

Объект «E2E: <имя демо-объекта>» собирается из тех же data/seed, что и демо (seed.py), но
отдельно от него: правки демо-объекта в интерфейсе на проверку не влияют. График каждый раз
импортируется заново (правило 12.4.10 — тоже), поэтому незавершённый прошлый запуск не мешает.

Проверки:
1. лента совпадает со сценарием data/seed/expected.json по дням: каждое ожидаемое отклонение
   найдено ровно в свой день, ничего лишнего (в том числе ни одного D2 в нормальный день);
2. у каждого отклонения, кроме D10, есть факты и доказательства — снимки;
3. итог объекта на дашборде — `object_status` сценария;
4. правка правила (runbook §6, шаг «Правка правила»): после неё отклонения `gone` исчезают,
   `kept` остаются; после отката правила лента снова совпадает со сценарием.

Код выхода 0 — всё сошлось, 1 — нет (что именно — в выводе).
"""

import argparse
import sys

import httpx
from _common import load_env, use_utf8_output
from _scenario import compare, day_of, describe, load_expected, set_required, stage_rule
from seed import SeedError, check, connect, deviations, object_spec, prepare, run_analysis

PREFIX = "E2E: "


def report(title: str, expected: dict, items: list[dict]) -> bool:
    """Сверка ленты со сценарием с разбором по дням; True — совпала."""
    result = compare(expected, items)
    print(f"\n{title}: {'совпадает' if result.ok else 'НЕ совпадает'} со сценарием")
    for day in expected["days"]:
        found = sorted(describe(i) for i in items if day_of(i) == day["date"])
        print(f"  {day['date']} {day['title']}: {', '.join(found) or 'без отклонений'}")
    for date, want in result.missing:
        print(f"  не найдено {date}: {want}")
    for item in result.extra:
        print(f"  лишнее     {day_of(item)}: {describe(item)} — {item['title']}")
    return result.ok


def check_evidence(items: list[dict]) -> bool:
    """Ни одного вывода без фактов и снимков (кроме D10: слепой участок снимков не даёт)."""
    bare = [i for i in items if i["code"] != "D10" and not (i["facts"] and i["evidence"])]
    for item in bare:
        print(f"  без доказательств: {day_of(item)} {describe(item)}")
    print(f"\nдоказательства: {'у всех есть' if not bare else f'нет у {len(bare)}'}")
    return not bare


def check_status(client: httpx.Client, object_id: str, expected: dict) -> bool:
    """Итог объекта на дашборде совпадает со сценарием."""
    status = check(client.get(f"/analysis/objects/{object_id}/status"), "статус объекта")
    ok = status["status"] == expected["object_status"]
    print(
        f"\nстатус объекта: {status['status']}, задержка {status['delay_days']}, "
        f"SPI {status['spi']}, уверенность {status['confidence']}"
        + ("" if ok else f" — ожидался {expected['object_status']}")
    )
    return ok


def check_rule_edit(client: httpx.Client, object_id: str, expected: dict) -> bool:
    """Правка правила меняет ленту без перезапуска стека; откат возвращает сценарий."""
    edit = expected["rule_edit"]
    rule = stage_rule(client, object_id, edit["stage"])
    print(f"\nправка правила {edit['stage']}: {edit['what']}")
    try:
        set_required(client, rule["id"], edit["required"])
        run_analysis(client, object_id)
        codes = {i["code"] for i in deviations(client, object_id)}
        gone = [c for c in edit["gone"] if c in codes]
        kept = [c for c in edit["kept"] if c not in codes]
        if gone:
            print(f"  не исчезли: {gone}")
        if kept:
            print(f"  пропали лишние: {kept}")
        edited_ok = not gone and not kept
        print(f"  после правки: {'как задумано' if edited_ok else 'НЕ как задумано'}")
    finally:
        set_required(client, rule["id"], rule["required"])
        print("  правило возвращено")
    run_analysis(client, object_id)
    return report("после отката правила", expected, deviations(client, object_id)) and edited_ok


def main() -> int:
    use_utf8_output()
    parser = argparse.ArgumentParser(description="Сквозной сценарий на поднятом стеке")
    parser.add_argument("--timeout", type=float, default=900, help="ожидание распознавания, с")
    args = parser.parse_args()

    expected = load_expected()
    spec = object_spec()
    spec["name"] = PREFIX + spec["name"]
    with connect(load_env(), "e2e.py") as client:
        try:
            obj = prepare(client, spec, force_plan=True, timeout_s=args.timeout)
            run_analysis(client, obj["id"])
            items = deviations(client, obj["id"])
            checks = [
                report("лента", expected, items),
                check_evidence(items),
                check_status(client, obj["id"], expected),
                check_rule_edit(client, obj["id"], expected),
            ]
        except (SeedError, LookupError) as exc:
            print(f"\nОшибка: {exc}")
            return 1
        except httpx.TransportError as exc:
            print(f"\nСтек недоступен по {client.base_url}: {exc}. Поднят ли docker compose?")
            return 1
    passed = all(checks)
    print(f"\nE2E {'пройден' if passed else 'НЕ пройден'}: объект {obj['id']}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
