import math
from dataclasses import dataclass, field
from itertools import combinations, permutations
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from utils.config import (
    MAX_COMBINATIONS_PER_LENGTH,
    MAX_ROUTE_CANDIDATES_DEFAULT,
    MAX_ROUTE_EVALUATIONS,
    ROUTE_DIFFERENCE_RATIO,
)
from utils.logger import get_logger

from utils.ors_client import fetch_point_to_points_durations
from utils.route_support import (
    coefficient_of_variation,
    normalise_duration,
    parse_visit_time,
    prepare_duration_matrix,
)

log = get_logger("[RouteOptimizer]")


@dataclass(frozen=True)
class RouteLeg:
    origin_id: Optional[Any]
    destination_id: Any
    travel_time: float


@dataclass
class RouteResult:
    start_id: Optional[Any]
    stops: List[Any]
    path: List[Any]
    legs: List[RouteLeg]
    total_travel_time: float
    total_visit_time: float
    total_time: float
    leg_variation: float
    unused_time: float
    start_location: Optional[Mapping[str, float]] = field(default=None)
    stop_set: Set[Any] = field(default_factory=set, init=False, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_id": self.start_id,
            "start_location": (
                dict(self.start_location) if self.start_location else None
            ),
            "stops": list(self.stops),
            "path": list(self.path),
            "legs": [
                {
                    "origin_id": leg.origin_id,
                    "destination_id": leg.destination_id,
                    "travel_time": leg.travel_time,
                }
                for leg in self.legs
            ],
            "total_travel_time": self.total_travel_time,
            "total_visit_time": self.total_visit_time,
            "total_time": self.total_time,
            "leg_variation": self.leg_variation,
            "unused_time": self.unused_time,
        }

    def __post_init__(self) -> None:
        self.stop_set = set(self.stops)


def find_top_routes(
    durations: Sequence[Sequence[Any]],
    objects: Sequence[Mapping[str, Any]],
    max_total_time: float,
    start_object_id: Optional[Any] = None,
    start_durations: Optional[Mapping[Any, float]] = None,
    user_location: Optional[Mapping[str, float]] = None,
    ors_profile: str = "foot-walking",
    ors_api_key: Optional[str] = None,
    min_stops: int = 3,
    max_stops: int = 5,
    max_results: int = 3,
    max_candidates: Optional[int] = None,
) -> List[RouteResult]:
    if max_candidates is None:
        max_candidates = MAX_ROUTE_CANDIDATES_DEFAULT
    log.debug(
        "find_top_routes start | objs=%d | max_time=%.1f | max_candidates=%s",
        len(objects),
        max_total_time,
        max_candidates,
    )
    if max_results < 1:
        raise ValueError("max_results must be at least 1")

    if max_total_time <= 0:
        return []

    if min_stops < 1:
        raise ValueError("min_stops must be at least 1")
    if max_stops < min_stops:
        raise ValueError("max_stops cannot be lower than min_stops")

    objects_list = list(objects)
    id_by_index, matrix = prepare_duration_matrix(durations, objects_list)
    if not matrix:
        log.warning("No routes: empty duration matrix")
        return []
    log.debug(
        "Prepared matrix | objects=%d | max_candidates=%s",
        len(objects_list),
        max_candidates,
    )
    objects_by_id: Dict[Any, Mapping[str, Any]] = {
        obj["id"]: obj for obj in objects_list
    }
    objects_list = [objects_by_id[object_id] for object_id in id_by_index]
    index_by_id: Dict[Any, int] = {
        object_id: idx for idx, object_id in enumerate(id_by_index)
    }
    visit_times_all = [parse_visit_time(obj.get("time")) for obj in objects_list]

    if start_object_id is not None and user_location is not None:
        raise ValueError("Provide either start_object_id or user_location, not both")

    start_index: Optional[int] = None
    start_location: Optional[Dict[str, float]] = None

    if user_location is not None:
        try:
            start_location = {
                "latitude": float(user_location["latitude"]),
                "longitude": float(user_location["longitude"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "user_location must expose numeric 'latitude' and 'longitude'"
            ) from exc

    if start_object_id is not None:
        if start_object_id in index_by_id:
            start_index = index_by_id[start_object_id]
        elif not start_durations:
            raise ValueError(
                "start_object_id is not present in objects list; provide start_durations instead"
            )

    computed_start_durations: Optional[Mapping[Any, float]] = start_durations
    start_durations_in_seconds = False

    if start_location is not None and computed_start_durations is None:
        target_payload: List[Dict[str, Any]] = []
        for obj in objects_list:
            lon = obj.get("lon", obj.get("longitude"))
            lat = obj.get("lat", obj.get("latitude"))
            if lon is None or lat is None:
                raise ValueError(
                    "Each object must provide 'lon' and 'lat' when using user_location"
                )
            target_payload.append({"id": obj["id"], "lon": lon, "lat": lat})

        computed_start_durations = fetch_point_to_points_durations(
            start_location,
            target_payload,
            api_key=ors_api_key,
            profile=ors_profile,
        )
        start_durations_in_seconds = True

    parsed_start_durations: Optional[Dict[Any, float]] = None
    if computed_start_durations:
        parsed_start_durations = {}
        for object_id, value in computed_start_durations.items():
            travel_time = normalise_duration(value)
            if math.isinf(travel_time):
                continue
            if start_durations_in_seconds:
                travel_time /= 60.0
            parsed_start_durations[object_id] = travel_time

    candidate_indices = [
        idx for idx, object_id in enumerate(id_by_index) if object_id != start_object_id
    ]
    total_candidates = len(candidate_indices)
    if total_candidates < min_stops:
        return []

    if (
        max_candidates is not None
        and max_candidates > 0
        and total_candidates > max_candidates
    ):

        def centrality(index: int) -> float:
            row = matrix[index]
            values: List[float] = []
            for other in candidate_indices:
                if other == index:
                    continue
                value = row[other]
                if value is None or not _is_finite(value):
                    continue
                values.append(float(value))
            if not values:
                return math.inf
            return sum(values) / len(values)

        scored = sorted((centrality(idx), idx) for idx in candidate_indices)
        selected: List[int] = []
        seen_idx: Set[int] = set()

        half = max(1, max_candidates // 2)
        for _, idx in scored[:half]:
            selected.append(idx)
            seen_idx.add(idx)

        remaining = max_candidates - len(selected)
        if remaining > 0:
            for _, idx in reversed(scored):
                if idx in seen_idx:
                    continue
                selected.append(idx)
                seen_idx.add(idx)
                remaining -= 1
                if remaining <= 0:
                    break

        candidate_indices = selected

    top_candidates: List[Tuple[Tuple[int, float, float], RouteResult]] = []
    seen_paths: Set[Tuple[Any, ...]] = set()
    buffer_limit = max(30, max_results * 40)

    def register_candidate(score: Tuple[int, float, float], route: RouteResult) -> None:
        for _, existing_route in top_candidates:
            if _too_similar(route, existing_route, overlap_ratio):
                return
        top_candidates.append((score, route))
        top_candidates.sort(key=lambda item: item[0])
        if len(top_candidates) > buffer_limit:
            del top_candidates[buffer_limit:]

    overlap_ratio = ROUTE_DIFFERENCE_RATIO

    current_limit = len(candidate_indices)

    max_route_evaluations = MAX_ROUTE_EVALUATIONS
    evaluations = 0
    stop_search = False
    distinct_cache: Optional[List[RouteResult]] = None

    for length in range(min(max_stops, current_limit), min_stops - 1, -1):
        if stop_search:
            break
        combo_counter = 0
        max_combos_this_length = MAX_COMBINATIONS_PER_LENGTH
        for combo in combinations(candidate_indices, length):
            if stop_search:
                break
            combo_counter += 1
            if combo_counter > max_combos_this_length:
                break
            for order in permutations(combo):
                path_ids = tuple(id_by_index[idx] for idx in order)
                if (
                    start_index is None
                    and start_object_id is None
                    and start_location is None
                    and not parsed_start_durations
                ):
                    normalized = min(path_ids, tuple(reversed(path_ids)))
                    if normalized in seen_paths:
                        continue
                    seen_paths.add(normalized)

                legs, leg_times = _build_legs(
                    order,
                    matrix,
                    id_by_index,
                    start_index=start_index,
                    start_id=start_object_id,
                    start_durations=parsed_start_durations,
                )
                if legs is None:
                    continue

                visit_time = sum(visit_times_all[idx] for idx in order)
                total_travel = sum(leg_times)
                total_time = total_travel + visit_time

                if total_time > max_total_time:
                    continue

                variation = coefficient_of_variation(leg_times)
                unused_time = max_total_time - total_time

                score = (unused_time, -length, variation)

                route = RouteResult(
                    start_id=start_object_id,
                    stops=[id_by_index[idx] for idx in order],
                    path=_build_path(
                        start_object_id, order, id_by_index, start_location
                    ),
                    legs=legs,
                    total_travel_time=total_travel,
                    total_visit_time=visit_time,
                    total_time=total_time,
                    leg_variation=variation,
                    unused_time=unused_time,
                    start_location=start_location,
                )
                register_candidate(score, route)
                evaluations += 1
                if (
                    evaluations >= max_route_evaluations
                    and len(top_candidates) >= max_results
                ):
                    maybe_distinct = _choose_distinct_routes(
                        top_candidates, overlap_ratio, max_results
                    )
                    if len(maybe_distinct) >= max_results:
                        distinct_cache = maybe_distinct
                        stop_search = True
                        break

        if top_candidates and len(top_candidates) >= max_results:
            best_unused = top_candidates[0][0][0]
            if best_unused <= 1.0:
                break

    if distinct_cache is not None:
        return distinct_cache
    top_candidates.sort(key=lambda item: item[0])
    distinct = _choose_distinct_routes(top_candidates, overlap_ratio, max_results)

    if (
        len(distinct) < max_results
        and max_candidates is not None
        and max_candidates > 0
        and current_limit < total_candidates
    ):
        next_limit = min(total_candidates, max(current_limit * 2, max_candidates * 2))
        if next_limit > current_limit:
            log.info(
                "Expanding candidate limit from %d to %d", current_limit, next_limit
            )
            return find_top_routes(
                durations,
                objects,
                max_total_time,
                start_object_id=start_object_id,
                start_durations=parsed_start_durations or start_durations,
                user_location=None if parsed_start_durations else user_location,
                ors_profile=ors_profile,
                ors_api_key=ors_api_key,
                min_stops=min_stops,
                max_stops=max_stops,
                max_results=max_results,
                max_candidates=next_limit,
            )

    return distinct


def _choose_distinct_routes(
    candidates: List[Tuple[Tuple[int, float, float], RouteResult]],
    overlap_ratio: float,
    max_results: int,
) -> List[RouteResult]:
    if not candidates:
        return []

    thresholds = [overlap_ratio, min(0.6, overlap_ratio + 0.2), 1.0]
    for threshold in thresholds:
        selection: List[RouteResult] = []
        for _, route in candidates:
            if all(
                not _too_similar(route, existing, threshold) for existing in selection
            ):
                selection.append(route)
            if len(selection) == max_results:
                return selection

    return [route for _score, route in candidates[:max_results]]


def _too_similar(route_a: RouteResult, route_b: RouteResult, ratio: float) -> bool:
    shared = len(route_a.stop_set & route_b.stop_set)
    union_size = len(route_a.stop_set | route_b.stop_set) or 1
    shared_ratio = shared / union_size
    return shared_ratio > ratio


def _build_path(
    start_id: Optional[Any],
    order: Iterable[int],
    ids: Sequence[Any],
    start_location: Optional[Mapping[str, float]],
) -> List[Any]:
    if start_location is not None and start_id is None:
        return [ids[idx] for idx in order]
    if start_id is not None:
        return [start_id] + [ids[idx] for idx in order]
    return [ids[idx] for idx in order]


def _build_legs(
    order: Tuple[int, ...],
    matrix: Sequence[Sequence[float]],
    ids: Sequence[Any],
    start_index: Optional[int],
    start_id: Optional[Any],
    start_durations: Optional[Mapping[Any, float]],
) -> Tuple[Optional[List[RouteLeg]], List[float]]:
    legs: List[RouteLeg] = []
    leg_times: List[float] = []

    previous_index = start_index
    previous_id = start_id

    for position, idx in enumerate(order):
        current_id = ids[idx]
        if previous_index is not None:
            travel_time = matrix[previous_index][idx]
        elif start_durations is not None and position == 0:
            travel_time = start_durations.get(current_id, math.inf)
        elif previous_id is None:
            travel_time = 0.0 if position == 0 else matrix[order[position - 1]][idx]
        else:
            travel_time = math.inf

        if travel_time is None or math.isinf(travel_time):
            return None, []

        legs.append(
            RouteLeg(
                origin_id=previous_id,
                destination_id=current_id,
                travel_time=float(travel_time),
            )
        )
        leg_times.append(float(travel_time))

        previous_index = idx
        previous_id = current_id

    return legs, leg_times


def _is_finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False
