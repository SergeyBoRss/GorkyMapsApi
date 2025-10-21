import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from utils.route_optimizer import find_top_routes
from utils.route_support import (
    extract_submatrix_by_ids,
    select_object_ids_by_tags,
)


DEFAULT_OBJECTS_PATH = Path("data/objects.csv")
DEFAULT_DURATIONS_PATH = Path("data/durations.csv")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a sample route for selected tags.")
    parser.add_argument(
        "--tags",
        required=True,
        help="Comma-separated list of tags (e.g. ARCHITECTURE,URBAN_ART).",
    )
    parser.add_argument(
        "--max-time",
        type=float,
        required=True,
        help="Maximum total time budget (minutes).",
    )
    parser.add_argument(
        "--objects-path",
        default=str(DEFAULT_OBJECTS_PATH),
        help="Path to objects.csv (default: data/objects.csv).",
    )
    parser.add_argument(
        "--durations-path",
        default=str(DEFAULT_DURATIONS_PATH),
        help="Path to durations.csv (default: data/durations.csv).",
    )
    parser.add_argument(
        "--start-id",
        type=str,
        help="Optional starting object id.",
    )
    parser.add_argument(
        "--user-lat",
        type=float,
        help="Latitude for user starting location (requires --user-lon).",
    )
    parser.add_argument(
        "--user-lon",
        type=float,
        help="Longitude for user starting location (requires --user-lat).",
    )
    parser.add_argument(
        "--min-stops",
        type=int,
        default=3,
        help="Minimum number of stops in the route (default: 3).",
    )
    parser.add_argument(
        "--max-stops",
        type=int,
        default=5,
        help="Maximum number of stops in the route (default: 5).",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=12,
        help="Maximum number of objects considered during optimisation (default: 12).",
    )
    return parser.parse_args(argv)


def read_objects(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            normalized: Dict[str, Any] = {}
            for key, value in raw.items():
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
            records.append(normalized)
    return records


def read_duration_matrix(path: Path) -> List[List[Any]]:
    matrix: List[List[Any]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for row_idx, row in enumerate(reader):
            processed: List[Any] = []
            for col_idx, value in enumerate(row):
                if row_idx == 0 or col_idx == 0:
                    processed.append(value)
                    continue
                if value == "":
                    processed.append(None)
                    continue
                try:
                    processed.append(float(value) / 60.0)
                except ValueError:
                    processed.append(value)
            matrix.append(processed)
    return matrix


def build_objects_map(objects: Iterable[Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    result: Dict[str, Mapping[str, Any]] = {}
    for obj in objects:
        object_id = obj.get("id")
        if object_id is None:
            continue
        result[str(object_id)] = obj
    return result


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)

    tags = [token.strip() for token in args.tags.split(",") if token.strip()]
    if not tags:
        print("No valid tags provided.", file=sys.stderr)
        return 1

    print(f"[1/5] Loading objects from {args.objects_path}...")
    objects_path = Path(args.objects_path)
    if not objects_path.exists():
        print(f"Objects file not found: {objects_path}", file=sys.stderr)
        return 1
    objects = read_objects(objects_path)
    print(f"Loaded {len(objects)} objects.")

    print(f"[2/5] Selecting objects by tags {tags}...")
    matched_ids = select_object_ids_by_tags(objects, tags)
    print(f"Found {len(matched_ids)} objects matching tags.")
    if len(matched_ids) < args.min_stops:
        print(f"Need at least {args.min_stops} objects, but only {len(matched_ids)} matched.", file=sys.stderr)
        return 1

    print(f"[3/5] Loading duration matrix from {args.durations_path}...")
    durations_path = Path(args.durations_path)
    if not durations_path.exists():
        print(f"Durations file not found: {durations_path}", file=sys.stderr)
        return 1
    duration_matrix = read_duration_matrix(durations_path)
    print(f"Duration matrix loaded ({len(duration_matrix)} rows).")

    print("[4/5] Extracting submatrix for selected objects...")
    try:
        selected_ids, submatrix = extract_submatrix_by_ids(duration_matrix, objects, matched_ids)
    except KeyError as exc:
        print(f"Failed to build submatrix: {exc}", file=sys.stderr)
        return 1

    print(f"Submatrix size: {len(selected_ids)} x {len(selected_ids)}.")
    print_submatrix(selected_ids, submatrix)

    candidate_limit = (
        args.max_candidates if args.max_candidates and args.max_candidates > 0 else None
    )
    if candidate_limit is not None and len(selected_ids) > candidate_limit:
        print(
            f"Limiting optimisation to {candidate_limit} most central objects "
            f"(from {len(selected_ids)})."
        )

    objects_map = build_objects_map(objects)
    filtered_objects = [objects_map[str(object_id)] for object_id in selected_ids]

    start_id = args.start_id
    if start_id:
        start_id = str(start_id)
        if start_id not in objects_map:
            print(f"Start id {start_id} not found among objects.", file=sys.stderr)
            return 1

    user_location = None
    if args.user_lat is not None or args.user_lon is not None:
        if args.user_lat is None or args.user_lon is None:
            print("Both --user-lat and --user-lon must be provided together.", file=sys.stderr)
            return 1
        user_location = {"latitude": args.user_lat, "longitude": args.user_lon}

    print("[5/5] Running route optimiser...")
    routes = find_top_routes(
        submatrix,
        filtered_objects,
        max_total_time=args.max_time,
        start_object_id=start_id,
        user_location=user_location,
        min_stops=args.min_stops,
        max_stops=min(args.max_stops, len(filtered_objects)),
        max_results=3,
        max_candidates=candidate_limit,
    )

    if not routes:
        print("No feasible route found within the specified constraints.")
        return 1

    for idx, result in enumerate(routes, start=1):
        print(f"\n=== Route #{idx} ===")
        print(f"Stops count: {len(result.stops)}")
        print(f"Path: {result.path}")
        print(f"Total travel time: {_format_duration(result.total_travel_time)}")
        print(f"Total visit time: {_format_duration(result.total_visit_time)}")
        print(
            f"Total time: {_format_duration(result.total_time)} "
            f"(unused: {_format_duration(result.unused_time)})"
        )
        print(f"Leg variation (CV): {result.leg_variation:.3f}")

        if result.start_location:
            print(f"Start location: {result.start_location}")
        elif result.start_id:
            print("Start object:")
            print_object_details(result.start_id, objects_map)

        print("\nStops:")
        for stop_id in result.stops:
            print_object_details(stop_id, objects_map)

        print("\nLeg details:")
        for leg_index, leg in enumerate(result.legs, start=1):
            print(
                f"  Leg {leg_index}: {leg.origin_id} -> {leg.destination_id} "
                f"({_format_duration(leg.travel_time)})"
            )

    return 0


def print_submatrix(ids: Sequence[Any], matrix: Sequence[Sequence[float]]) -> None:
    if not ids or not matrix:
        print("Submatrix is empty.")
        return

    header = ["     "] + [f"{str(id_):>10}" for id_ in ids]
    # print("Submatrix (minutes):")
    # print("".join(header))
    # for object_id, row in zip(ids, matrix):
    #     cells = [f"{str(object_id):>5}"]
    #     for value in row:
    #         if value is None:
    #             cells.append(f"{'∞':>10}")
    #         else:
    #             cells.append(f"{value:10.1f}")
    #     print("".join(cells))


def print_object_details(object_id: Any, objects_map: Mapping[str, Mapping[str, Any]]) -> None:
    obj = objects_map.get(str(object_id))
    if not obj:
        print(f"  {object_id}: (details unavailable)")
        return

    title = obj.get("title") or "(no title)"
    address = obj.get("address") or ""
    lon = _format_float(obj.get("lon") or obj.get("longitude"))
    lat = _format_float(obj.get("lat") or obj.get("latitude"))
    visit_time = obj.get("time")

    parts = [f"  {object_id}: {title}"]
    if address:
        parts.append(f" — {address}")
    parts.append(f" [lat={lat}, lon={lon}]")
    if visit_time not in (None, "", "nan"):
        parts.append(f" visit={visit_time}")
    print("".join(parts))


def _format_duration(minutes: float) -> str:
    seconds = minutes * 60.0
    return f"{minutes:.1f} min ({seconds:.0f} s)"


def _format_float(value: Optional[Any]) -> str:
    if value is None or value == "":
        return "?"
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return str(value)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
