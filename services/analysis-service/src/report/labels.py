"""Русские названия для отчёта: `data/report_labels.yaml` и типы зон из enums.yaml."""

from pathlib import Path

import yaml

from src.core.enums import ENUMS_FILE
from src.report.model import Labels


def load_labels(labels_file: str | Path, contracts_dir: str | Path) -> Labels:
    with Path(labels_file).open(encoding="utf-8") as file:
        names = yaml.safe_load(file) or {}
    with (Path(contracts_dir) / ENUMS_FILE).open(encoding="utf-8") as file:
        zone_types = (yaml.safe_load(file) or {}).get("zone_type_name", {})
    return Labels(
        names={str(k): {str(a): str(b) for a, b in v.items()} for k, v in names.items()},
        zone_types={str(k): str(v) for k, v in zone_types.items()},
    )
