"""YOLO-World: open-vocabulary детектор техники, классы — текстовые промпты из файла (F2)."""

from collections.abc import Sequence
from pathlib import Path

from PIL import Image

from src.core.detections import RawBox


class YoloWorldDetector:
    """Детектор со словарём, заданным при загрузке; номер класса на выходе — номер промпта."""

    def __init__(
        self,
        weights: str,
        prompts: Sequence[str],
        device: str,
        imgsz: int,
        conf: float,
        iou: float,
    ) -> None:
        from ultralytics import YOLOWorld

        self.name = Path(weights).stem
        self._device = device
        self._imgsz = imgsz
        self._conf = conf
        self._iou = iou
        self._model = YOLOWorld(weights)
        # Промпты кодируются текстовым энкодером CLIP на том же устройстве, что и модель,
        # поэтому модель переносится до set_classes.
        self._model.to(device)
        self._model.set_classes(list(prompts))
        # Текстовый CLIP нужен только чтобы закодировать промпты, а словарь меняется лишь
        # перезапуском. Ultralytics держит его в модели до конца процесса: это сотни мегабайт
        # памяти, а на 6 ГБ видеокарты демо-стенда — заметная доля.
        self._model.model.clip_model = None

    def detect(self, image: Image.Image) -> list[RawBox]:
        result = self._model.predict(
            image,
            imgsz=self._imgsz,
            conf=self._conf,
            iou=self._iou,
            device=self._device,
            verbose=False,
        )[0]
        boxes = result.boxes
        xyxy = boxes.xyxy.cpu().tolist()
        confs = boxes.conf.cpu().tolist()
        classes = boxes.cls.cpu().tolist()
        return [
            RawBox(x1, y1, x2, y2, conf, int(cls))
            for (x1, y1, x2, y2), conf, cls in zip(xyxy, confs, classes, strict=True)
        ]
