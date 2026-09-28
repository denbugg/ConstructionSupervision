"""Скачивает веса моделей распознавания в data/models/ (монтируется в vision-service как /models).

    python scripts/fetch_models.py [--force] [--dest data/models]

Идемпотентен: файл с верной контрольной суммой повторно не качается. Скачивание идёт во
временный `.part`, поэтому оборванная загрузка не оставляет «готовый» битый файл.
"""

import argparse
import hashlib
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from _common import ROOT, use_utf8_output

CHUNK = 1024 * 1024


@dataclass(frozen=True)
class Weights:
    """Один файл весов: откуда, куда и какой должна быть его sha256."""

    name: str
    url: str
    path: str
    sha256: str


# Пути совпадают с настройками vision-service по умолчанию: VISION_DET_WEIGHTS и
# VISION_STAGE_MODEL (services/vision-service/README.md, раздел 5). Контрольная сумма
# OpenCLIP — из заголовка X-Linked-ETag Hugging Face, YOLO-World — из первого скачивания:
# в релизе GitHub её нет.
MODELS = [
    Weights(
        name="YOLO-World v2, размер s (детектор техники)",
        url="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s-worldv2.pt",
        path="yolov8s-worldv2.pt",
        sha256="9b2c17ab6124a913e9b3a5c170617920d91b0f01111a8479da69f00e2cf27792",
    ),
    Weights(
        name="OpenCLIP ViT-B-32, laion2b_s34b_b79k (стадия объекта)",
        url=(
            "https://huggingface.co/laion/CLIP-ViT-B-32-laion2B-s34B-b79K"
            "/resolve/main/open_clip_model.safetensors"
        ),
        path="openclip-vit-b32/open_clip_model.safetensors",
        sha256="ac4f8c4b88af6d963118cbf40ad93176d092abbedfcb752601ae1866352656e6",
    ),
    # YOLO-World кодирует промпты классов текстовым энкодером OpenAI CLIP ViT-B/32 и без этого
    # файла качает его при старте. Адрес и sha256 (она же — каталог в адресе) — из пакета clip.
    Weights(
        name="OpenAI CLIP ViT-B/32 (текстовый энкодер промптов YOLO-World)",
        url=(
            "https://openaipublic.azureedge.net/clip/models/"
            "40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af/ViT-B-32.pt"
        ),
        path="clip/ViT-B-32.pt",
        sha256="40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af",
    ),
]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path) -> None:
    """Потоковое скачивание с прогрессом; файл появляется под своим именем только целиком."""
    part = target.with_name(target.name + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "lct-fetch-models"})
    with urllib.request.urlopen(request, timeout=60) as resp, part.open("wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done, last_print = 0, 0.0
        while chunk := resp.read(CHUNK):
            out.write(chunk)
            done += len(chunk)
            if time.monotonic() - last_print > 2:
                shown = f"{done / total:.0%}" if total else f"{done // CHUNK} МБ"
                print(f"    {shown}", flush=True)
                last_print = time.monotonic()
    part.replace(target)


def fetch(model: Weights, dest: Path, force: bool) -> bool:
    """Скачать один файл, если его нет или он не тот. True — файл на месте и проверен."""
    target = dest / model.path
    print(f"- {model.name}\n  {target}")

    if target.exists() and not force:
        actual = sha256_of(target)
        if not model.sha256 or actual == model.sha256:
            print(f"  уже есть, sha256 {actual}")
            return True
        print("  контрольная сумма не совпала, качаю заново")

    try:
        download(model.url, target)
    except OSError as exc:
        print(f"  ОШИБКА скачивания: {exc}")
        return False

    actual = sha256_of(target)
    if model.sha256 and actual != model.sha256:
        target.unlink()
        print(f"  ОШИБКА: sha256 {actual}, ожидалась {model.sha256}; файл удалён")
        return False
    print(f"  скачан, {target.stat().st_size // CHUNK} МБ, sha256 {actual}")
    return True


def main() -> int:
    use_utf8_output()
    parser = argparse.ArgumentParser(description="Скачать веса моделей распознавания")
    parser.add_argument("--dest", type=Path, default=ROOT / "data" / "models")
    parser.add_argument("--force", action="store_true", help="скачать заново, даже если файл есть")
    args = parser.parse_args()

    results = [fetch(model, args.dest, args.force) for model in MODELS]
    print(f"\nГотово {sum(results)} из {len(results)}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
