"""Демо-хронология снимков: кадры датасета → data/seed/images/<камера>/ГГГГММДД_ЧЧММСС.jpg.

    python scripts/seed_images.py          # собрать по data/seed/chronology.json
    python scripts/seed_images.py --yes    # и удалить папки камер, которых нет в хронологии

Какие серии идут в какой день — data/seed/chronology.json: серия — диапазон номеров кадров
IMG<n>.jpg, кадры ищутся в `source` в любой вложенности (архив распаковывается как есть).
Кадры серии берутся равномерно по её длине, по одному на слот. Файлы копируются как есть:
время снимка задаёт имя файла, EXIF у кадров Лимы нет. Повторный запуск кладёт те же кадры под
те же имена.
"""

import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

from _common import ROOT, use_utf8_output

CHRONOLOGY = ROOT / "data" / "seed" / "chronology.json"
IMAGES = ROOT / "data" / "seed" / "images"
# В архиве Лимы встречается «IMG54jpg.jpg»: номер — первые цифры имени.
FRAME_NUMBER = re.compile(r"^IMG(\d+)")


def index(source: Path) -> dict[int, Path]:
    """Номер кадра → файл, в любой вложенности каталога датасета."""
    found = {}
    for path in source.rglob("IMG*.jpg"):
        match = FRAME_NUMBER.match(path.name)
        if match:
            found[int(match.group(1))] = path
    if not found:
        raise SystemExit(f"В {source} нет кадров IMG<n>.jpg: распакуйте датасет (ml/README.md)")
    return found


def frames(by_number: dict[int, Path], bursts: list[list[int]]) -> list[Path]:
    """Кадры серий подряд; внутри серии — по номеру, то есть по времени съёмки.

    Пропуски номеров внутри серии есть в самом датасете (696, 888, 889) и не ошибка.
    """
    return [
        by_number[n] for first, last in bursts for n in range(first, last + 1) if n in by_number
    ]


def spread(items: list[Path], count: int) -> list[Path]:
    """count элементов, равномерно по всей длине: слоты дня покрывают всю серию, а не её начало."""
    if len(items) < count:
        raise SystemExit(f"В сериях {len(items)} кадров, а слотов {count}")
    if count == 1:
        return [items[len(items) // 2]]
    return [items[round(i * (len(items) - 1) / (count - 1))] for i in range(count)]


def plan(chronology: dict) -> dict[Path, Path]:
    """Куда какой кадр: путь в data/seed/images → исходный кадр."""
    by_number = index(ROOT / chronology["source"])
    slots = chronology["slots"]
    placed: dict[Path, Path] = {}
    for day in chronology["days"]:
        stamp = date.fromisoformat(day["date"]).strftime("%Y%m%d")
        for camera, bursts in day["cameras"].items():
            chosen = spread(frames(by_number, bursts), len(slots))
            for slot, frame in zip(slots, chosen, strict=True):
                hhmm = slot.replace(":", "")
                placed[IMAGES / camera / f"{stamp}_{hhmm}00.jpg"] = frame
    return placed


def main() -> int:
    use_utf8_output()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="удалить папки камер не из хронологии")
    args = parser.parse_args()

    placed = plan(json.loads(CHRONOLOGY.read_text(encoding="utf-8")))
    cameras = {path.parent.name for path in placed}
    stale = sorted(p for p in IMAGES.glob("*") if p.is_dir() and p.name not in cameras)
    if stale and not args.yes:
        print(
            "В data/seed/images есть камеры не из хронологии: " + ", ".join(p.name for p in stale)
        )
        print("Они попадут в загрузку seed.py. Удалить их — запуск с --yes.")
        return 1
    for folder in stale:
        shutil.rmtree(folder)
        print(f"удалена {folder.relative_to(ROOT)}")

    for camera in sorted(cameras):
        folder = IMAGES / camera
        if folder.exists():
            # Старые кадры камеры убираем: иначе снимок прошлой хронологии остался бы в загрузке.
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
    for target, frame in sorted(placed.items()):
        shutil.copyfile(frame, target)
    for camera in sorted(cameras):
        count = sum(1 for path in placed if path.parent.name == camera)
        print(f"{camera:<14} {count} снимков")
    return 0


if __name__ == "__main__":
    sys.exit(main())
