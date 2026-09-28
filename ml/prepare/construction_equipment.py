"""Сводит набор Construction Equipment (Kaggle) к классам системы в формате YOLO по train/val.

    python ml/prepare/construction_equipment.py
    python ml/prepare/construction_equipment.py --dry-run --min-gap 30   # только посчитать

`--source` — распакованный архив как есть (train/ и valid/, в каждом images/ и labels/).
Метки набора приводятся к кодам через aliases «ce:<метка>» в equipment_classes.yaml. Названия
меток — со страницы Kaggle, но у пяти из них размечено другое; что на самом деле под каждым
номером и почему он сведён так — таблица в ml/README.md.

Разбиение Kaggle на train/valid не используется: оно по кадрам, а соседние кадры неподвижной
камеры почти одинаковы. Здесь val — целые пары «камера + день», остальное — train. По той же
причине кадры прореживаются: с одной камеры за день берётся кадр не чаще раза в --min-gap секунд.

Пишутся data.yaml и data-world.yaml, как у ulima.py, и data-world.yaml в --combined-out: этот
набор вместе с Лимой, для обучения на обоих.
"""

import argparse
import re
import shutil
import zlib
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import yaml
from PIL import Image
from ulima import CLASSES_FILE, ROOT, class_map, convert_labels, write_yaml

ALIAS_PREFIX = "ce:"
# Номер метки в файлах разметки → название на странице Kaggle.
LABELS = [
    "Dump truck", "Excavator", "Motor grader", "Roller", "Crane manipulator", "Gazelle",
    "Forklift Standart", "Bucket loader Big", "Mixer", "Tanker", "Bulldozer",
    "Cleaning equipment", "Truck", "Trailer", "Forklift Giraffe", "Bucket loader Standart",
    "Autocran",
]
# Под «Roller» катки вперемешку с мини-погрузчиками, под «Bulldozer» одна рамка мини-погрузчика.
# Кадр исключается целиком: машина без рамки научила бы модель, что это фон.
DROP_FRAMES = {"Roller", "Bulldozer"}
# Классов для этих машин нет; рамки выбрасываются, машины остаются на кадре фоном.
DROP_BOXES = {"Forklift Standart", "Forklift Giraffe", "Tanker"}

# 1231_07_14_53_440636-2023-11-10 и camera_6.702_2024-01-03T20_56_25_516+03_00
NAME_A = re.compile(r"^(\d+)_(\d\d)_(\d\d)_(\d\d)_\d+-(\d{4}-\d\d-\d\d)$")
NAME_B = re.compile(r"^camera_([\d.]+)_(\d{4}-\d\d-\d\d)T(\d\d)_(\d\d)_(\d\d)_\d+\+03_00$")


def parse_name(stem: str) -> tuple[str, str, datetime]:
    """Камера, день и время съёмки из имени кадра."""
    if m := NAME_A.match(stem):
        camera, hh, mm, ss, day = m.groups()
    elif m := NAME_B.match(stem):
        camera, day, hh, mm, ss = m.groups()
        camera = f"camera_{camera}"
    else:
        raise SystemExit(f"Непонятное имя кадра: {stem}")
    return camera, day, datetime.fromisoformat(f"{day}T{hh}:{mm}:{ss}")


def is_val(camera: str, day: str, share: int) -> bool:
    """Пара «камера + день» в val — по устойчивому хешу, одинаково при каждом запуске."""
    return zlib.crc32(f"{camera}|{day}".encode()) % 100 < share


def thin(frames: list[tuple[datetime, Path]], min_gap: float) -> list[Path]:
    """Кадры одной камеры за день по времени, не чаще раза в min_gap секунд."""
    kept, last = [], None
    for moment, path in sorted(frames):
        if last is None or (moment - last).total_seconds() >= min_gap:
            kept.append(path)
            last = moment
    return kept


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    datasets = ROOT / "ml" / "datasets"
    parser.add_argument("--source", type=Path, default=datasets / "construction-equipment")
    parser.add_argument("--out", type=Path, default=datasets / "external" / "construction-equipment")
    parser.add_argument("--ulima", type=Path, default=datasets / "external" / "ulima")
    parser.add_argument("--combined-out", type=Path, default=datasets / "external" / "ce-ulima")
    # 10 с, а не больше: прореживание бьёт по редким классам сильнее, чем по частым
    # (при 30 с от 741 рамки манипуляторов в train остаётся 180, при 10 с — 300).
    parser.add_argument("--min-gap", type=float, default=10.0, help="секунд между кадрами камеры")
    parser.add_argument("--val-share", type=int, default=12, help="доля пар «камера + день» в val, %%")
    parser.add_argument("--max-side", type=int, default=1280)
    parser.add_argument("--dry-run", action="store_true", help="только посчитать, ничего не писать")
    args = parser.parse_args()

    classes = yaml.safe_load(CLASSES_FILE.read_text(encoding="utf-8"))["equipment_classes"]
    kept_labels = [label for label in LABELS if label not in DROP_FRAMES | DROP_BOXES]
    mapping = {LABELS.index(label): target for label, target in zip(
        kept_labels, class_map(classes, kept_labels, ALIAS_PREFIX).values(), strict=True)}
    drop_frames = {LABELS.index(label) for label in DROP_FRAMES}
    skip = {LABELS.index(label) for label in DROP_BOXES}

    groups: dict[tuple[str, str], list[tuple[datetime, Path]]] = defaultdict(list)
    dropped = 0
    for jpg in args.source.glob("*/images/*.jpg"):
        text = (jpg.parent.parent / "labels" / f"{jpg.stem}.txt").read_text()
        if {int(line.split()[0]) for line in text.splitlines() if line.strip()} & drop_frames:
            dropped += 1
            continue
        camera, day, moment = parse_name(jpg.stem)
        groups[(camera, day)].append((moment, jpg))

    if not args.dry_run and args.out.exists():
        shutil.rmtree(args.out)
    stats: dict[str, Counter] = {s: Counter() for s in ("train", "val")}
    for (camera, day), frames in sorted(groups.items()):
        split = "val" if is_val(camera, day, args.val_share) else "train"
        stats[split]["пар камера+день"] += 1
        for jpg in thin(frames, args.min_gap):
            text = (jpg.parent.parent / "labels" / f"{jpg.stem}.txt").read_text()
            lines = convert_labels(text, mapping, skip)
            stats[split]["кадров"] += 1
            stats[split].update(classes[int(line.split()[0])]["code"] for line in lines)
            if args.dry_run:
                continue
            image_dir = args.out / "images" / split
            label_dir = args.out / "labels" / split
            image_dir.mkdir(parents=True, exist_ok=True)
            label_dir.mkdir(parents=True, exist_ok=True)
            with Image.open(jpg) as im:
                im = im.convert("RGB")
                im.thumbnail((args.max_side, args.max_side))
                im.save(image_dir / jpg.name, quality=92)
            (label_dir / f"{jpg.stem}.txt").write_text("\n".join(lines) + "\n" if lines else "")

    print(f"исключено кадров с Roller/Bulldozer: {dropped}")
    present = [classes[i]["code"] for i in sorted(set(mapping.values()))]
    for split, counter in stats.items():
        rest = ", ".join(f"{code} {counter[code]}" for code in present)
        print(f"{split:<5} пар {counter['пар камера+день']:>3}, кадров {counter['кадров']:>5}: {rest}")
    if args.dry_run:
        return

    write_yaml(args.out / "data.yaml", [c["code"] for c in classes])
    write_yaml(args.out / "data-world.yaml", [c["prompts"][0] for c in classes])
    write_combined(args.combined_out, [args.ulima, args.out], classes)


def write_combined(out: Path, sources: list[Path], classes: list[dict]) -> None:
    """data-world.yaml для обучения на нескольких наборах сразу.

    Кадры перечисляются в train.txt и val.txt, а не списком каталогов в yaml: тренер
    YOLO-World кладёт кэш текстовых эмбеддингов рядом с путём train и списка не принимает.
    Строки «./../<набор>/…» Ultralytics читает относительно каталога txt — файлы работают
    и на хосте, и в контейнере.
    """
    out.mkdir(parents=True, exist_ok=True)
    for split in ("train", "val"):
        lines = [
            f"./../{source.name}/images/{split}/{jpg.name}"
            for source in sources
            for jpg in sorted((source / "images" / split).glob("*.jpg"))
        ]
        (out / f"{split}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    data = {"train": "train.txt", "val": "val.txt", "names": dict(enumerate(c["prompts"][0] for c in classes))}
    (out / "data-world.yaml").write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    main()
