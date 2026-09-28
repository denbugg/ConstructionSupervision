"""Набор KICT (Корея, Mendeley rz8723t6d7) → классы системы в формате YOLO по train/val.

    python ml/prepare/kict.py --extract    # том архива → ml/datasets/kict/raw (один раз)
    python ml/prepare/kict.py              # raw → ml/datasets/external/kict

На Mendeley лежит только последний том трёхтомного zip64 — Bbox_dataset_classified.zip
(sha256 66f69e1c…, в обеих версиях набора). Оглавление архива — в этом томе, и файлы,
которые начинаются в нём, читаются целиком; их около трети набора. zipfile многотомные
архивы не открывает, поэтому оглавление разбирается здесь.
"""

import argparse
import json
import re
import shutil
import struct
import zlib
from collections import Counter
from pathlib import Path

import yaml
from PIL import Image
from ulima import CLASSES_FILE, ROOT, class_map, write_yaml

DATASETS = ROOT / "ml" / "datasets"
VOLUME = DATASETS / "kict" / "Bbox_dataset_classified.zip"
RAW = DATASETS / "kict" / "raw"
ALIAS_PREFIX = "kict:"
# Категории, проверенные по вырезкам (ml/README.md): «crane» здесь — кран-манипулятор на
# грузовике, «crawler_drill» — буровая на гусеницах. В последнем томе других категорий
# техники нет. Машины без нашего класса остаются на кадре фоном.
LABELS = ["excavator", "dumptruck", "bull_dozer", "crawler_drill", "crane"]
DROP_BOXES = {"car", "fork_lift_truck", "unknown"}
# Среди «crane» есть ошибочные крошечные рамки (красные пятна у края кадра); манипуляторы
# на кадрах — от 150 px в ширину.
MIN_CRANE_WIDTH = 100
# Пары «точка съёмки + день» в val: в них есть все пять классов, включая буровую (только p04).
VAL = {("p04", "20210910"), ("p08", "20210830"), ("p03", "20210903")}
# IPC522_20210826092701_244_p03_foggy_00024: камера, начало ролика, ролик, точка, погода, кадр.
NAME = re.compile(r"^IPC\d+_(\d{8})\d{6}(?:-\d+)?_\d+_(p\d+)_[a-z]+_(\d+)$")


def central_directory(fp) -> tuple[int, list[tuple[str, int, int, int, int]]]:
    """Номер этого тома и записи оглавления: (имя, том, смещение, сжатый размер, метод)."""
    fp.seek(-200, 2)
    tail = fp.read()
    _, _, off_z64, _ = struct.unpack("<4sLQL", tail[tail.rfind(b"PK\x06\x07") :][:20])
    fp.seek(off_z64)
    rec = struct.unpack("<4sQHHLLQQQQ", fp.read(56))
    this_disk, cd_size, cd_off = rec[4], rec[8], rec[9]
    fp.seek(cd_off)
    cd = fp.read(cd_size)
    rows, p = [], 0
    while cd[p : p + 4] == b"PK\x01\x02":
        f = struct.unpack("<4s6H3L5H2L", cd[p : p + 46])
        method, crc, csize, usize = f[4], f[7], f[8], f[9]
        nlen, xlen, clen, disk, off = f[10], f[11], f[12], f[13], f[16]
        name = cd[p + 46 : p + 46 + nlen].decode("utf-8")
        extra = cd[p + 46 + nlen : p + 46 + nlen + xlen]
        q = 0
        while q < len(extra):  # zip64: поля, у которых в основной записи 0xFFFF…
            hid, hlen = struct.unpack("<HH", extra[q : q + 4])
            if hid == 1:
                vals, k = extra[q + 4 : q + 4 + hlen], 0
                for field in ("usize", "csize", "off"):
                    if {"usize": usize, "csize": csize, "off": off}[field] == 0xFFFFFFFF:
                        value = struct.unpack("<Q", vals[k : k + 8])[0]
                        k += 8
                        usize, csize, off = (
                            value if field == "usize" else usize,
                            value if field == "csize" else csize,
                            value if field == "off" else off,
                        )
                if disk == 0xFFFF:
                    disk = struct.unpack("<L", vals[k : k + 4])[0]
            q += 4 + hlen
        rows.append((name, disk, off, csize, method, crc))
        p += 46 + nlen + xlen + clen
    return this_disk, rows


def extract() -> None:
    """Файлы, которые начинаются в этом томе, — в RAW с той же структурой каталогов."""
    with VOLUME.open("rb") as fp:
        disk, rows = central_directory(fp)
        mine = [r for r in rows if r[1] == disk and not r[0].endswith("/")]
        print(f"записей в оглавлении {len(rows)}, в этом томе {len(mine)}")
        bad = 0
        for name, _, off, csize, method, crc in mine:
            fp.seek(off)
            head = fp.read(30)
            nlen, xlen = struct.unpack("<HH", head[26:30])
            fp.seek(off + 30 + nlen + xlen)
            data = fp.read(csize)
            data = zlib.decompress(data, -15) if method == 8 else data
            if zlib.crc32(data) != crc:
                bad += 1
                continue
            out = RAW / name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
        print(f"распаковано {len(mine) - bad}, не сошлась CRC у {bad}")


def convert(out: Path, every: int, max_side: int) -> None:
    """raw → YOLO: каждый every-й кадр ролика (соседние кадры ролика почти одинаковы)."""
    classes = yaml.safe_load(CLASSES_FILE.read_text(encoding="utf-8"))["equipment_classes"]
    if out.exists():
        shutil.rmtree(out)
    stats: dict[str, Counter] = {s: Counter() for s in ("train", "val")}
    mapping = dict(zip(LABELS, class_map(classes, LABELS, ALIAS_PREFIX).values(), strict=True))
    for js in sorted(RAW.glob("Bbox_dataset_classified/*/*/Annotations/*.json")):
        day, point, frame = NAME.match(js.stem).groups()
        if int(frame) % every:
            continue
        doc = json.loads(js.read_text(encoding="utf-8"))
        names = {c["id"]: c["name"] for c in doc["categories"]}
        width, height = doc["images"][0]["width"], doc["images"][0]["height"]
        lines = []
        for a in doc["annotations"]:
            label = names[a["category_id"]]
            x, y, w, h = a["bbox"]
            if label in DROP_BOXES or (label == "crane" and w < MIN_CRANE_WIDTH):
                continue
            if label not in mapping:
                raise SystemExit(f"{js.name}: категория {label} не проверена по вырезкам")
            cx, cy = (x + w / 2) / width, (y + h / 2) / height
            lines.append(f"{mapping[label]} {cx:.6f} {cy:.6f} {w / width:.6f} {h / height:.6f}")
        split = "val" if (point, day) in VAL else "train"
        image_dir, label_dir = out / "images" / split, out / "labels" / split
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(js.parent.parent / "JPEGImages" / f"{js.stem}.jpg") as im:
            im = im.convert("RGB")
            im.thumbnail((max_side, max_side))
            im.save(image_dir / f"{js.stem}.jpg", quality=92)
        (label_dir / f"{js.stem}.txt").write_text("\n".join(lines) + "\n" if lines else "")
        stats[split]["кадров"] += 1
        stats[split].update(classes[int(line.split()[0])]["code"] for line in lines)

    write_yaml(out / "data.yaml", [c["code"] for c in classes])
    write_yaml(out / "data-world.yaml", [c["prompts"][0] for c in classes])
    present = [classes[i]["code"] for i in sorted(set(mapping.values()))]
    for split, counter in stats.items():
        rest = ", ".join(f"{code} {counter[code]}" for code in present)
        print(f"{split:<5} кадров {counter['кадров']:>5}: {rest}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--extract", action="store_true", help="распаковать том в raw")
    parser.add_argument("--out", type=Path, default=DATASETS / "external" / "kict")
    parser.add_argument("--every", type=int, default=8, help="брать каждый N-й кадр ролика")
    parser.add_argument("--max-side", type=int, default=1280)
    args = parser.parse_args()
    if args.extract:
        extract()
    else:
        convert(args.out, args.every, args.max_side)


if __name__ == "__main__":
    main()
