"""Собирает ассеты релиза demo-data-v1: то, что fetch_models.py раздаёт вместо git.

    python scripts/pack_assets.py [--out dist/demo-data-v1]

Кладёт в каталог дообученные веса детектора и архив демо-кадров из data/seed/images и печатает
их sha256 — они же должны стоять в fetch_models.py. Архив воспроизводим: порядок файлов и дата
в заголовках фиксированы, сжатия нет (JPEG не сжимается), поэтому те же кадры дают тот же
sha256. Загружает ассеты в релиз человек (runbook, раздел 10).
"""

import argparse
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

from _common import ROOT, use_utf8_output

# Одна модель на весь проект — та, что стоит в VISION_DET_WEIGHTS стенда.
WEIGHTS = [ROOT / "data" / "models" / "yolov8s-worldv2-ce-ulima-v1.pt"]
IMAGES = ROOT / "data" / "seed" / "images"
# Дата в заголовках zip: от mtime файлов sha256 архива зависеть не должен.
FIXED_TIME = (2026, 10, 19, 0, 0, 0)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pack_images(target: Path) -> int:
    """Архив кадров: пути внутри — `cam-<код>/<файл>`, как в data/seed/images."""
    files = sorted(p for p in IMAGES.rglob("*") if p.is_file())
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as zf:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(IMAGES).as_posix(), FIXED_TIME)
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())
    return len(files)


def main() -> int:
    use_utf8_output()
    parser = argparse.ArgumentParser(description="Ассеты релиза demo-data-v1")
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "demo-data-v1")
    args = parser.parse_args()

    missing = [p for p in (*WEIGHTS, IMAGES) if not p.exists()]
    if missing:
        print(f"Нет исходных файлов: {', '.join(str(p) for p in missing)}")
        return 1
    args.out.mkdir(parents=True, exist_ok=True)

    packed = []
    for source in WEIGHTS:
        shutil.copyfile(source, args.out / source.name)
        packed.append((args.out / source.name, "веса"))
    archive = args.out / "demo-images.zip"
    packed.append((archive, f"{pack_images(archive)} кадров"))

    print(f"Каталог: {args.out}")
    for path, note in packed:
        size = path.stat().st_size / 2**20
        print(f"  {path.name:40} {size:6.1f} МБ  {note}\n    sha256 {sha256_of(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
