"""Демо-сценарий: ожидания из data/seed/expected.json и сверка с лентой отклонений.

Общее для e2e.py (проверка) и demo.py (показ по дням).
"""

import json
from dataclasses import dataclass

import httpx
from _common import ROOT
from seed import check

EXPECTED = ROOT / "data" / "seed" / "expected.json"


def load_expected() -> dict:
    return json.loads(EXPECTED.read_text(encoding="utf-8"))


def day_of(item: dict) -> str:
    """День отклонения — дата начала эпизода в UTC (почему так — expected.json, _about)."""
    return item["first_seen_at"][:10]


def describe(item: dict) -> str:
    """Строка ленты для человека: код, участок, класс или этап."""
    what = item.get("equipment_class") or (item.get("facts") or {}).get("stage_code") or ""
    return f"{item['code']} {item.get('area') or '—'} {what}".rstrip()


def _matches(want: dict, day: str, item: dict) -> bool:
    return (
        want["code"] == item["code"]
        and day == day_of(item)
        and want.get("area") == item.get("area")
        and want.get("equipment_class") == item.get("equipment_class")
        and ("stage" not in want or want["stage"] == (item.get("facts") or {}).get("stage_code"))
    )


@dataclass
class Comparison:
    """Итог сверки: чего не нашли и что нашли сверх сценария."""

    missing: list[tuple[str, dict]]
    extra: list[dict]

    @property
    def ok(self) -> bool:
        return not self.missing and not self.extra


def compare(expected: dict, items: list[dict]) -> Comparison:
    """Лента против сценария: каждое ожидание — ровно одной строке ленты, и наоборот."""
    left = list(items)
    missing: list[tuple[str, dict]] = []
    for day in expected["days"]:
        for want in day["deviations"]:
            found = next((item for item in left if _matches(want, day["date"], item)), None)
            if found is None:
                missing.append((day["date"], want))
            else:
                left.remove(found)
    return Comparison(missing=missing, extra=left)


def stage_rule(client: httpx.Client, object_id: str, stage_code: str) -> dict:
    """Действующее правило этапа по его коду."""
    stages = check(
        client.get(f"/plan/objects/{object_id}/stages", params={"limit": 200}), "этапы объекта"
    )["items"]
    stage = next((s for s in stages if s["code"] == stage_code), None)
    if stage is None or stage["rule"] is None:
        raise LookupError(f"у этапа {stage_code} нет правила")
    return stage["rule"]


def set_required(client: httpx.Client, rule_id: str, required: list[dict]) -> None:
    """Правка обязательной техники: plan поднимет версию правила и пошлёт сигнал анализу."""
    check(client.patch(f"/plan/rules/{rule_id}", json={"required": required}), "правка правила")
