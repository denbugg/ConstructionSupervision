"""Дообучение детектора техники: YOLO-World (классы остаются промптами) или обычный YOLO.

    python ml/training/train.py --name world-s-ulima-v3 --model yolov8s-worldv2.pt \
        --data ml/datasets/external/ulima/data-world.yaml

Запускается там, где есть torch и Ultralytics, — в образе vision-service (ml/README.md,
«Обучение»). Режим выбирается по имени весов: у YOLO-World имена классов датасета — это
текстовые промпты, и после обучения словарь по-прежнему задаётся из equipment_classes.yaml.
Результат — ml/runs/<name>/weights/last.pt (почему не best.pt — у --patience).

Прерванный прогон продолжается с его last.pt — эпоха, оптимизатор и расписание LR
восстанавливаются из чекпойнта, остальные аргументы берутся оттуда же:

    python ml/training/train.py --name world-s-ce-ulima-kict-v1 --resume
"""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", help="исходные веса, например yolov8s-worldv2.pt")
    parser.add_argument("--data", type=Path)
    parser.add_argument("--name", required=True, help="имя прогона в ml/runs/")
    parser.add_argument("--resume", action="store_true", help="продолжить прерванный прогон --name")
    parser.add_argument("--epochs", type=int, default=40)
    # Вход 1280, как у vision-service: техника с обзорной камеры мелкая, на 640 она пропадает.
    parser.add_argument("--imgsz", type=int, default=1280)
    # 4 кадра 1280 — предел 6 ГБ видеопамяти демо-стенда для размера s.
    parser.add_argument("--batch", type=int, default=4)
    # Ранняя остановка выключена: валидация Лимы — две серии, 62 кадра, и её метрика шумит
    # с первой эпохи (прогон world-s-ulima-v1 остановился на 16-й с «лучшей» 1-й). Учим
    # фиксированное число эпох и берём last.pt, а не best.pt, выбранный по этому шуму.
    parser.add_argument("--patience", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not args.resume and (args.model is None or args.data is None):
        parser.error("без --resume нужны --model и --data")

    import yaml
    from ultralytics import YOLO, YOLOWorld

    if args.resume:
        run = ROOT / "ml" / "runs" / args.name
        # Режим — по исходным весам прогона, как при запуске: у last.pt в имени его нет.
        world = "world" in yaml.safe_load((run / "args.yaml").read_text(encoding="utf-8"))["model"]
        last = run / "weights" / "last.pt"
        (YOLOWorld(last) if world else YOLO(last)).train(resume=True)
        return

    model = YOLOWorld(args.model) if "world" in args.model else YOLO(args.model)
    model.train(
        data=str(args.data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        patience=args.patience,
        workers=args.workers,
        project=str(ROOT / "ml" / "runs"),
        name=args.name,
        exist_ok=True,
        seed=0,
        deterministic=True,
        plots=True,
    )


if __name__ == "__main__":
    main()
