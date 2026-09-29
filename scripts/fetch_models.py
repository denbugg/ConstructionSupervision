"""Скачивает всё, чего нет в git: веса моделей, демо-кадры и локальную LLM.

    python scripts/fetch_models.py [--skip llm] [--skip demo] [--force]
    docker compose run --rm tools python scripts/fetch_models.py     # без Python на хосте

Что и куда:
- `models` — базовые веса vision-service в `data/models/` (монтируется как /models): YOLO-World,
  OpenCLIP для стадии, текстовый CLIP для промптов YOLO-World;
- `demo` — дообученный детектор `yolov8s-worldv2-ce-ulima-v1.pt` (стоит в VISION_DET_WEIGHTS)
  и 56 демо-кадров датасета Лимы в `data/seed/images/` — ассеты релиза `demo-data-v1` на GitHub;
- `llm` — Gemma 4 E4B Q4_K_M для сервиса `llm` (llama.cpp) в `data/models/llm/`, около 5 ГБ.

Идемпотентен: файл с верной контрольной суммой повторно не качается. Скачивание идёт во
временный `.part`, поэтому оборванная загрузка не оставляет «готовый» битый файл. ASSETS_URL
в окружении подменяет адрес релиза — для зеркала или проверки скрипта.
"""

import argparse
import hashlib
import os
import sys
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from _common import ROOT, use_utf8_output

CHUNK = 1024 * 1024
MODELS = ROOT / "data" / "models"
# Ассеты релиза на GitHub (scripts/pack_assets.py их собирает): тег не начинается с «v»,
# поэтому workflow Release на нём не запускается.
ASSETS_URL = os.environ.get(
    "ASSETS_URL",
    "https://github.com/cerXXXX/ConstructionSupervision/releases/download/demo-data-v1",
)
# Коммит репозитория на Hugging Face, а не main: файл там перезаливали, а нужен ровно тот,
# на котором проверены резюме отчётов на демо-стенде.
GEMMA_REVISION = "e2999f09c6f69ed494a207046f7b784a7fa0b5f8"


@dataclass(frozen=True)
class Asset:
    """Один файл: откуда, куда, какой должна быть его sha256; архив ещё и распаковывается."""

    group: str
    name: str
    url: str
    path: Path
    sha256: str
    unpack_to: Path | None = None


# Пути совпадают с настройками по умолчанию: VISION_DET_WEIGHTS и VISION_STAGE_MODEL
# (services/vision-service/README.md, раздел 5), команда сервиса llm в docker-compose.yml.
# Контрольная сумма OpenCLIP и Gemma — из заголовка X-Linked-ETag Hugging Face, YOLO-World —
# из первого скачивания: в релизе Ultralytics её нет.
ASSETS = [
    Asset(
        group="models",
        name="YOLO-World v2, размер s (детектор техники, zero-shot)",
        url="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s-worldv2.pt",
        path=MODELS / "yolov8s-worldv2.pt",
        sha256="9b2c17ab6124a913e9b3a5c170617920d91b0f01111a8479da69f00e2cf27792",
    ),
    Asset(
        group="models",
        name="OpenCLIP ViT-B-32, laion2b_s34b_b79k (стадия объекта)",
        url=(
            "https://huggingface.co/laion/CLIP-ViT-B-32-laion2B-s34B-b79K"
            "/resolve/main/open_clip_model.safetensors"
        ),
        path=MODELS / "openclip-vit-b32" / "open_clip_model.safetensors",
        sha256="ac4f8c4b88af6d963118cbf40ad93176d092abbedfcb752601ae1866352656e6",
    ),
    # YOLO-World кодирует промпты классов текстовым энкодером OpenAI CLIP ViT-B/32 и без этого
    # файла качает его при старте. Адрес и sha256 (она же — каталог в адресе) — из пакета clip.
    Asset(
        group="models",
        name="OpenAI CLIP ViT-B/32 (текстовый энкодер промптов YOLO-World)",
        url=(
            "https://openaipublic.azureedge.net/clip/models/"
            "40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af/ViT-B-32.pt"
        ),
        path=MODELS / "clip" / "ViT-B-32.pt",
        sha256="40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af",
    ),
    # Детектор стенда (VISION_DET_WEIGHTS): дообучен на Лиме и Construction Equipment (ml/README).
    Asset(
        group="demo",
        name="YOLO-World v2 s, дообученный на Лиме и ConstructionEquipment (ce-ulima-v1)",
        url=f"{ASSETS_URL}/yolov8s-worldv2-ce-ulima-v1.pt",
        path=MODELS / "yolov8s-worldv2-ce-ulima-v1.pt",
        sha256="14036da9d4eb751f5f2e00814e2b67fbe2917a5f763dd170d8db8dfc13f2a4d4",
    ),
    # Кадры Universidad de Lima, CC BY 4.0 (data/README.md): архив из scripts/pack_assets.py.
    Asset(
        group="demo",
        name="Демо-кадры: 56 снимков двух камер Лимы, разложенные по дням демо",
        url=f"{ASSETS_URL}/demo-images.zip",
        path=ROOT / "data" / "seed" / "demo-images.zip",
        sha256="146633095be2132fa1bbf9ef6949451dc881e2f7fcae02973269100c984236ec",
        unpack_to=ROOT / "data" / "seed" / "images",
    ),
    Asset(
        group="llm",
        name="Gemma 4 E4B instruct, GGUF Q4_K_M (резюме отчётов, Apache 2.0)",
        url=(
            "https://huggingface.co/lmstudio-community/gemma-4-E4B-it-GGUF/resolve/"
            f"{GEMMA_REVISION}/gemma-4-E4B-it-Q4_K_M.gguf"
        ),
        path=MODELS / "llm" / "gemma-4-E4B-it-Q4_K_M.gguf",
        sha256="d264fb541e1fd4cb67ff710664cef60a50aaa8ab6f7acdf2bf5c76911dbd5b76",
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
            if time.monotonic() - last_print > 5:
                shown = (
                    f"{done / total:.0%} из {total // CHUNK} МБ" if total else f"{done // CHUNK} МБ"
                )
                print(f"    {shown}", flush=True)
                last_print = time.monotonic()
    part.replace(target)


def unpack(archive: Path, dest: Path) -> None:
    """Распаковать архив поверх каталога: файлы с теми же именами заменяются, чужие остаются."""
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dest)
        files = [n for n in zf.namelist() if not n.endswith("/")]
    print(f"  распакован в {dest.relative_to(ROOT)}: {len(files)} файлов")


def fetch(asset: Asset, force: bool) -> bool:
    """Скачать один файл, если его нет или он не тот. True — файл на месте и проверен."""
    target = asset.path
    print(f"- {asset.name}\n  {target.relative_to(ROOT)}")

    if target.exists() and not force and sha256_of(target) == asset.sha256:
        print("  уже есть, контрольная сумма верна")
    else:
        try:
            download(asset.url, target)
        except OSError as exc:
            print(f"  ОШИБКА скачивания {asset.url}: {exc}")
            return False
        actual = sha256_of(target)
        if actual != asset.sha256:
            target.unlink()
            print(f"  ОШИБКА: sha256 {actual}, ожидалась {asset.sha256}; файл удалён")
            return False
        print(f"  скачан, {target.stat().st_size // CHUNK} МБ")

    if asset.unpack_to is not None:
        unpack(target, asset.unpack_to)
    return True


def main() -> int:
    use_utf8_output()
    parser = argparse.ArgumentParser(description="Скачать веса моделей, демо-кадры и LLM")
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        choices=["demo", "llm"],
        help="не качать группу: demo — дообученные веса и кадры, llm — Gemma (5 ГБ)",
    )
    parser.add_argument("--force", action="store_true", help="скачать заново, даже если файл есть")
    args = parser.parse_args()

    chosen = [a for a in ASSETS if a.group not in args.skip]
    results = [fetch(asset, args.force) for asset in chosen]
    print(f"\nГотово {sum(results)} из {len(results)}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
