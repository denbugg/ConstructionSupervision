"""Сводит датасет Лимы к классам системы и раскладывает его в формат YOLO по train/val/test.

    python ml/prepare/ulima.py --source ml/datasets/ulima --out ml/datasets/external/ulima

`--source` — каталог, где лежат IMG<n>.jpg и IMG<n>.txt из архива, в любой вложенности.
Метки датасета приводятся к кодам через aliases «ulima:<метка>» в equipment_classes.yaml,
номер класса — место в этом файле, серии и разбиение — из ulima.yaml рядом. Кадры
уменьшаются до --max-side по длинной стороне: обучение всё равно идёт на входе такого размера,
а читать 4K с диска каждую эпоху — долго.
Пишутся data.yaml (имена — коды, для обычного YOLO) и data-world.yaml (имена — первый промпт
класса, для YOLO-World: по этим строкам он строит текстовые эмбеддинги).
"""

import argparse
import re
import shutil
from collections import Counter
from pathlib import Path

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
CLASSES_FILE = ROOT / "packages" / "contracts" / "equipment_classes.yaml"
CONFIG_FILE = Path(__file__).with_name("ulima.yaml")
ALIAS_PREFIX = "ulima:"
IMAGE_NAME = re.compile(r"^IMG(\d+)(?:jpg)?$")  # в архиве есть «IMG54jpg.jpg»


def class_map(classes: list[dict], labels: list[str], prefix: str = ALIAS_PREFIX) -> dict[int, int]:
    """Номер метки датасета → номер класса, то есть его место в equipment_classes.yaml.

    В датасет попадают все классы системы, даже без единой рамки. Номера тогда не зависят от
    датасета, а YOLO-World учится на их промптах как на отрицательных: без этого он называл
    мини-погрузчики бульдозером — промпт «bulldozer» в обучении не участвовал.
    """
    by_alias = {
        alias.removeprefix(prefix): c
        for c in classes
        for alias in c["aliases"]
        if alias.startswith(prefix)
    }
    missing = [label for label in labels if label not in by_alias]
    if missing:
        raise SystemExit(f"Нет aliases «{prefix}…» для меток: {', '.join(missing)}")
    index = {c["code"]: i for i, c in enumerate(classes)}
    return {i: index[by_alias[label]["code"]] for i, label in enumerate(labels)}


def split_of(bursts: list[dict]) -> dict[int, str]:
    """Номер кадра → train/val/test по серии, в которую он входит."""
    return {i: b["split"] for b in bursts for i in range(b["ids"][0], b["ids"][1] + 1)}


def convert_labels(text: str, mapping: dict[int, int], skip: set[int]) -> list[str]:
    """Строки YOLO датасета → строки с номерами классов системы; номера из skip выбрасываются."""
    out = []
    for line in text.splitlines():
        parts = line.split()
        if parts and int(parts[0]) not in skip:
            out.append(" ".join([str(mapping[int(parts[0])]), *parts[1:]]))
    return out


def write_yaml(path: Path, names: list[str]) -> None:
    """Описание датасета для Ultralytics.

    Без ключа path: тогда Ultralytics берёт каталог самого yaml, и файл одинаково работает
    на хосте и в контейнере, куда репозиторий смонтирован по другому пути.
    """
    data = {"train": "images/train", "val": "images/val"}
    data |= {"test": "images/test", "names": dict(enumerate(names))}
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=ROOT / "ml" / "datasets" / "ulima")
    parser.add_argument("--out", type=Path, default=ROOT / "ml" / "datasets" / "external" / "ulima")
    parser.add_argument("--max-side", type=int, default=1280)
    args = parser.parse_args()

    config = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    classes = yaml.safe_load(CLASSES_FILE.read_text(encoding="utf-8"))["equipment_classes"]
    mapping = class_map(classes, config["labels"])
    splits = split_of(config["bursts"])
    excluded = {(e["image"], config["labels"].index(e["label"])) for e in config["exclude_boxes"]}

    if args.out.exists():
        shutil.rmtree(args.out)
    stats: dict[str, Counter] = {s: Counter() for s in ("train", "val", "test")}
    for jpg in sorted(args.source.rglob("IMG*.jpg")):
        match = IMAGE_NAME.match(jpg.stem)
        if not match or int(match.group(1)) not in splits:
            continue
        number = int(match.group(1))
        split = splits[number]
        txt = jpg.with_name(f"IMG{number}.txt")
        skip = {label for image, label in excluded if image == number}
        lines = convert_labels(txt.read_text() if txt.exists() else "", mapping, skip)

        image_dir = args.out / "images" / split
        label_dir = args.out / "labels" / split
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(jpg) as im:
            im = im.convert("RGB")
            im.thumbnail((args.max_side, args.max_side))
            im.save(image_dir / f"IMG{number}.jpg", quality=92)
        (label_dir / f"IMG{number}.txt").write_text("\n".join(lines) + "\n" if lines else "")

        stats[split]["кадров"] += 1
        stats[split].update(classes[int(line.split()[0])]["code"] for line in lines)

    write_yaml(args.out / "data.yaml", [c["code"] for c in classes])
    write_yaml(args.out / "data-world.yaml", [c["prompts"][0] for c in classes])
    present = [classes[i]["code"] for i in sorted(set(mapping.values()))]
    for split, counter in stats.items():
        rest = ", ".join(f"{code} {counter[code]}" for code in present)
        print(f"{split:<5} кадров {counter['кадров']:>4}: {rest}")


if __name__ == "__main__":
    main()
