"""Демо-сценарий по дням (docs/runbook.md, раздел 6) с паузами для показа.

    python scripts/demo.py [--no-pause] [--rule-edit] [--force-plan] [--timeout 900]

Готовит демо-объект так же, как seed.py, и прогоняет анализ. Потом ведёт по сценарию
data/seed/expected.json: для каждого дня — что показать, найденные отклонения со ссылками на
снимок-доказательство в интерфейсе и пометка, если лента разошлась со сценарием. Между
шагами — пауза до Enter (`--no-pause` — без пауз).

Шаг «Правка правила» меняет правило этапа через API и после показа возвращает его. В
интерактивном режиме скрипт спрашивает разрешения, `--rule-edit` делает это без вопроса;
с `--no-pause` без `--rule-edit` шаг только описывается.
"""

import argparse
import sys

import httpx
from _common import load_env, use_utf8_output
from _scenario import compare, day_of, describe, load_expected, set_required, stage_rule
from seed import SeedError, check, connect, deviations, object_spec, prepare, run_analysis


class Show:
    """Вывод сценария: заголовки шагов, паузы, ссылки в интерфейс."""

    def __init__(self, client: httpx.Client, web: str, object_id: str, pause: bool) -> None:
        self.client = client
        self.web = web
        self.object_id = object_id
        self.pause = pause
        self._cameras: dict[str, str] | None = None

    def step(self, title: str) -> None:
        print(f"\n{'─' * 72}\n{title}")

    def wait(self) -> None:
        if self.pause:
            input("\nEnter — дальше ")

    def ask(self, question: str) -> bool:
        return self.pause and input(f"\n{question} [y/N] ").strip().lower() in ("y", "д", "да")

    def evidence_link(self, item: dict) -> str | None:
        """Первый снимок-доказательство на экране камер: камера и снимок в адресе."""
        if not item["evidence"]:
            return None
        image_id = item["evidence"][0]["image_id"]
        image = check(self.client.get(f"/site/images/{image_id}"), "снимок")
        code = self.camera_codes().get(image["camera_id"], "")
        return f"{self.web}/objects/{self.object_id}/cameras?camera={code}&image={image_id}"

    def camera_codes(self) -> dict[str, str]:
        if self._cameras is None:
            page = check(
                self.client.get("/site/cameras", params={"object_id": self.object_id}), "камеры"
            )
            self._cameras = {c["id"]: c["code"] for c in page["items"]}
        return self._cameras


def show_days(show: Show, expected: dict, items: list[dict]) -> None:
    """Дни сценария: что рассказать и что нашла система."""
    result = compare(expected, items)
    extra = {id(i) for i in result.extra}
    for number, day in enumerate(expected["days"], start=1):
        show.step(f"День {number} — {day['date']}: {day['title']}")
        print(day["show"])
        found = sorted(
            (i for i in items if day_of(i) == day["date"]), key=lambda i: i["first_seen_at"]
        )
        for item in found:
            mark = "  ← не по сценарию" if id(item) in extra else ""
            print(f"\n  {describe(item)}{mark}\n  {item['title']}")
            link = show.evidence_link(item)
            if link:
                print(f"  снимок: {link}")
        if not found:
            print("\n  отклонений нет")
        for date, want in result.missing:
            if date == day["date"]:
                print(f"\n  НЕ НАЙДЕНО по сценарию: {want}")
        show.wait()


def show_rule_edit(show: Show, expected: dict, force: bool) -> None:
    """Правка правила: логика — данные, а не код. Правило возвращается после показа."""
    edit = expected["rule_edit"]
    show.step(f"Правка правила этапа {edit['stage']}")
    print(f"В правиле {edit['what']}. После пересчёта {', '.join(edit['gone'])} исчезает из ленты,")
    print(f"{', '.join(edit['kept'])} остаётся. Код не меняется: правило — данные.")
    if not (force or show.ask("Сделать правку сейчас через API и потом вернуть?")):
        return
    rule = stage_rule(show.client, show.object_id, edit["stage"])
    try:
        set_required(show.client, rule["id"], edit["required"])
        run_analysis(show.client, show.object_id)
        codes = sorted({i["code"] for i in deviations(show.client, show.object_id)})
        print(f"\n  коды в ленте после правки: {', '.join(codes)}")
        show.wait()
    finally:
        set_required(show.client, rule["id"], rule["required"])
        run_analysis(show.client, show.object_id)
        print("  правило возвращено")


def main() -> int:
    use_utf8_output()
    parser = argparse.ArgumentParser(description="Демо-сценарий по дням")
    parser.add_argument("--no-pause", action="store_true", help="без пауз между шагами")
    parser.add_argument("--rule-edit", action="store_true", help="править правило без вопроса")
    parser.add_argument("--force-plan", action="store_true", help="заменить график объекта")
    parser.add_argument("--timeout", type=float, default=900, help="ожидание распознавания, с")
    args = parser.parse_args()

    env = load_env()
    web = f"http://localhost:{env.get('GATEWAY_PORT', '8080')}"
    expected = load_expected()
    with connect(env, "demo.py") as client:
        try:
            obj = prepare(client, object_spec(), force_plan=args.force_plan, timeout_s=args.timeout)
            run_analysis(client, obj["id"])
            show = Show(client, web, obj["id"], pause=not args.no_pause)
            show.step("График и объект")
            print(f"Дашборд: {web}/objects/{obj['id']}")
            print(f"Камеры:  {web}/objects/{obj['id']}/cameras")
            print(f"Зоны:    {web}/objects/{obj['id']}/settings/zones")
            show.wait()
            show_days(show, expected, deviations(client, obj["id"]))
            show.step("Гант и отчёт")
            print("Фактический старт, прогноз окончания, критический путь, перенос на зависимые")
            print("этапы. Отчёт: «Сформировать PDF» — план-факт, загрузка техники, LLM-резюме.")
            print(f"Гант:    {web}/objects/{obj['id']}/gantt")
            print(f"Отчёты:  {web}/objects/{obj['id']}/reports")
            show.wait()
            show_rule_edit(show, expected, args.rule_edit)
        except (SeedError, LookupError) as exc:
            print(f"\nОшибка: {exc}")
            return 1
        except httpx.TransportError as exc:
            print(f"\nСтек недоступен по {client.base_url}: {exc}. Поднят ли docker compose?")
            return 1
    print("\nСценарий показан.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
