import math
from typing import Any, Iterable, List, Mapping, Sequence, Set, Tuple


def normalise_duration(value: Any) -> float:
    if value is None:
        return math.inf
    if isinstance(value, (int, float)):
        result = float(value)
        if math.isnan(result):
            return math.inf
        return result
    try:
        result = float(str(value))
    except (TypeError, ValueError):
        return math.inf
    if math.isnan(result):
        return math.inf
    return result


def normalise_matrix(rows: Sequence[Sequence[Any]]) -> List[List[float]]:
    matrix: List[List[float]] = []
    for row in rows:
        matrix.append([normalise_duration(value) for value in row])
    return matrix


def prepare_duration_matrix(
    durations: Sequence[Sequence[Any]],
    objects: Sequence[Mapping[str, Any]],
) -> Tuple[List[Any], List[List[float]]]:
    objects = list(objects)
    object_ids = [obj["id"] for obj in objects]
    object_id_tokens = [str(object_id) for object_id in object_ids]

    if not durations:
        return object_ids, []

    row_count = len(durations)
    column_count = len(durations[0]) if durations[0] else 0

    expects_headers = False

    if row_count == len(objects) + 1 and column_count == len(objects) + 1:
        expects_headers = True
    elif row_count != len(objects) or column_count != len(objects):
        try:
            float(durations[0][0])
        except (TypeError, ValueError):
            expects_headers = True

    if expects_headers:
        if row_count < 2 or column_count < 2:
            raise ValueError("duration matrix with headers must be at least 2x2")

        header_row = durations[0][1:]
        header_col = [row[0] for row in durations[1:]]

        header_row_tokens = [str(value) for value in header_row]
        header_col_tokens = [str(value) for value in header_col]

        missing_ids = [
            token for token in object_id_tokens if token not in header_row_tokens
        ]
        if missing_ids:
            raise ValueError(
                f"duration matrix is missing columns for ids: {missing_ids}"
            )
        missing_rows = [
            token for token in object_id_tokens if token not in header_col_tokens
        ]
        if missing_rows:
            raise ValueError(f"duration matrix is missing rows for ids: {missing_rows}")

        matrix: List[List[float]] = []
        for object_token in object_id_tokens:
            row_index = header_col_tokens.index(object_token)
            raw_row = durations[row_index + 1][1:]

            row_values: List[float] = []
            for target_token in object_id_tokens:
                column_index = header_row_tokens.index(target_token)
                value = raw_row[column_index]
                row_values.append(normalise_duration(value))
            matrix.append(row_values)

        return object_ids, matrix

    if any(len(row) != len(objects) for row in durations):
        raise ValueError(
            "duration matrix must be square and match the number of objects"
        )

    return object_ids, normalise_matrix(durations)


def parse_visit_time(raw_value) -> float:
    try:
        v = float(str(raw_value).strip().replace(",", "."))
    except Exception:
        return 0.0
    if not math.isfinite(v) or v < 0:
        return 0.0
    return v


def coefficient_of_variation(values: Sequence[float]) -> float:
    filtered = [value for value in values if value > 0]
    if len(filtered) < 2:
        return 0.0

    mean_value = sum(filtered) / len(filtered)
    if mean_value == 0:
        return 0.0

    variance = sum((value - mean_value) ** 2 for value in filtered) / len(filtered)
    return math.sqrt(variance) / mean_value


def select_object_ids_by_tags(
    objects: Sequence[Mapping[str, Any]],
    tags: Iterable[Any],
) -> List[Any]:
    if not tags:
        return []

    normalized_tags: Set[str] = set()
    for tag in tags:
        if tag is None:
            continue
        token = str(tag).strip()
        if token:
            normalized_tags.add(token.upper())

    if not normalized_tags:
        return []

    selected: List[Any] = []
    seen_ids: Set[str] = set()

    for obj in objects:
        tag_value = obj.get("tag")
        if tag_value is None:
            continue

        tag_token = str(tag_value).strip()
        if not tag_token or tag_token.upper() not in normalized_tags:
            continue

        object_id = obj.get("id")
        if object_id is None:
            continue

        identity = str(object_id)
        if identity in seen_ids:
            continue

        seen_ids.add(identity)
        selected.append(object_id)

    return selected


def extract_submatrix_by_ids(
    durations: Sequence[Sequence[Any]],
    objects: Sequence[Mapping[str, Any]],
    object_ids: Sequence[Any],
) -> Tuple[List[Any], List[List[float]]]:
    aligned_ids, matrix = prepare_duration_matrix(durations, objects)

    if not object_ids or not matrix:
        return [], []

    index_by_token = {str(object_id): idx for idx, object_id in enumerate(aligned_ids)}

    selected_indices: List[int] = []
    selected_ids: List[Any] = []
    seen_tokens: Set[str] = set()

    for object_id in object_ids:
        token = str(object_id)
        if token in seen_tokens:
            continue

        if token not in index_by_token:
            raise KeyError(f"id {object_id!r} is not present in the duration matrix")

        idx = index_by_token[token]
        seen_tokens.add(token)
        selected_indices.append(idx)
        selected_ids.append(aligned_ids[idx])

    submatrix: List[List[float]] = []
    for row_idx in selected_indices:
        row = matrix[row_idx]
        submatrix.append([row[col_idx] for col_idx in selected_indices])

    return selected_ids, submatrix
