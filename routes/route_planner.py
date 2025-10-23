from typing import Dict, List, Optional

from utils.config import (
    CANDIDATE_EXPANSION_STEP,
    MAX_ROUTE_CANDIDATES_DEFAULT,
)
from utils.logger import get_logger
from gpt_api.get_description import build_route_explanation, GigaChatError
from fastapi import APIRouter, HTTPException

from schemas import RoutePoint, RouteRequest, RouteResponse
from utils.data_provider import (
    get_duration_matrix,
    get_objects,
    get_objects_by_id,
)
from utils.route_optimizer import find_top_routes
from utils.route_support import extract_submatrix_by_ids, select_object_ids_by_tags

log = get_logger("[RoutePlanner]")
router = APIRouter()

DEFAULT_MAX_ROUTE_CANDIDATES = MAX_ROUTE_CANDIDATES_DEFAULT
DEFAULT_CANDIDATE_STEP = CANDIDATE_EXPANSION_STEP


@router.post("", response_model=RouteResponse)
def build_routes(request: RouteRequest) -> RouteResponse:
    log.info(
        "Building routes | interests=%s | walking_time=%.2fh",
        request.interests,
        request.walking_time,
    )
    objects = get_objects()
    objects_by_id = get_objects_by_id()
    full_matrix = get_duration_matrix()

    matched_ids = select_object_ids_by_tags(objects, request.interests)
    if not matched_ids:
        raise HTTPException(
            status_code=404, detail="No objects found for provided interests"
        )

    max_total_time = request.walking_time
    user_location: Optional[Dict[str, float]] = None
    if request.user_location is not None:
        user_location = {
            "latitude": request.user_location.latitude,
            "longitude": request.user_location.longitude,
        }

    candidate_limit = min(len(matched_ids), DEFAULT_MAX_ROUTE_CANDIDATES)
    routes: List = []

    while candidate_limit > 0:
        log.debug("Trying candidate_limit=%d/%d", candidate_limit, len(matched_ids))
        trimmed_ids = matched_ids[:candidate_limit]
        try:
            selected_ids, submatrix = extract_submatrix_by_ids(
                full_matrix, objects, trimmed_ids
            )
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        filtered_objects = [
            objects_by_id[str(object_id)]
            for object_id in selected_ids
            if str(object_id) in objects_by_id
        ]
        if len(filtered_objects) < 3:
            raise HTTPException(
                status_code=404, detail="Not enough objects to build a route"
            )

        routes = find_top_routes(
            submatrix,
            filtered_objects,
            max_total_time=max_total_time,
            user_location=user_location,
            min_stops=3,
            max_stops=5,
            max_results=3,
            max_candidates=min(candidate_limit, len(filtered_objects)),
        )

        if len(routes) >= 3 or candidate_limit >= len(matched_ids):
            break

        candidate_limit = min(
            len(matched_ids), candidate_limit + DEFAULT_CANDIDATE_STEP
        )

    if len(routes) < 1:
        log.warning(
            "No routes found for interests=%s",
            request.interests,
        )
        raise HTTPException(status_code=404, detail="No routes found")

    response_routes: List[List[RoutePoint]] = []
    for route in routes[:1]:
        points: List[RoutePoint] = []
        for stop_id in route.stops:
            obj = objects_by_id.get(str(stop_id))
            if not obj:
                continue
            latitude = obj.get("lat")
            longitude = obj.get("lon")
            if latitude is None or longitude is None:
                continue
            points.append(
                RoutePoint(
                    latitude=float(latitude),
                    longitude=float(longitude),
                    title=str(obj.get("title") or ""),
                    description=str(obj.get("description") or ""),
                    address=str(obj.get("address") or ""),
                )
            )
        if points:
            response_routes.append(points)

    final_routes = response_routes[:1]
    if len(final_routes) < 1:
        log.warning(
            "No routes with valid coordinates after filtering",
        )
        raise HTTPException(status_code=404, detail="No routes with valid coordinates")

    explanation: Optional[str] = None
    best_points: List[RoutePoint] = final_routes[0]
    try:
        explanation = build_route_explanation(
            route_points=[p.model_dump() for p in best_points],
            tags=request.interests,
            time_limit_min=max_total_time,
        )
    except GigaChatError as e:
        log.error("GigaChat explanation error: %s", e)
        explanation = None

    log.info(
        "Built %d candidate routes; returning 1 route with explanation=%s",
        len(routes),
        "yes" if explanation else "no",
    )

    return RouteResponse(routes=best_points, explanation=explanation)
