import csv
from functools import lru_cache
from typing import Any, Dict, List, Optional

from utils.config import DATA_DIR
from utils.logger import get_logger

log = get_logger("[DataProvider]")

OBJECTS_PATH = (DATA_DIR / "objects.csv").resolve()
DURATIONS_PATH = (DATA_DIR / "durations.csv").resolve()


def _safe_float(raw: Any) -> Optional[float]:
    if raw in (None, "", "nan"):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


@lru_cache()
def get_objects() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with OBJECTS_PATH.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            normalized: Dict[str, Any] = {}
            for key, value in row.items():
                if key is None:
                    continue
                clean_key = key.strip()
                if isinstance(value, str):
                    clean_value = value.strip()
                    if clean_value == "":
                        clean_value = None
                else:
                    clean_value = value
                normalized[clean_key] = clean_value

            normalized["lon"] = _safe_float(normalized.get("lon"))
            normalized["lat"] = _safe_float(normalized.get("lat"))
            records.append(normalized)
    log.info("Loaded %d objects from %s", len(records), OBJECTS_PATH)
    return records


@lru_cache()
def get_objects_by_id() -> Dict[str, Dict[str, Any]]:
    return {
        str(obj["id"]): obj
        for obj in get_objects()
        if obj.get("id") is not None
    }


@lru_cache()
def get_duration_matrix() -> List[List[Any]]:
    matrix: List[List[Any]] = []
    with DURATIONS_PATH.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for row_index, row in enumerate(reader):
            processed_row: List[Any] = []
            for col_index, value in enumerate(row):
                value = value.strip() if isinstance(value, str) else value
                if row_index == 0 or col_index == 0:
                    processed_row.append(value)
                    continue
                if value in (None, "", "nan"):
                    processed_row.append(None)
                    continue
                try:
                    processed_row.append(float(value) / 60.0)
                except ValueError:
                    processed_row.append(None)
            matrix.append(processed_row)
    log.info("Loaded duration matrix %s (%d rows)", DURATIONS_PATH, len(matrix))
    return matrix

