import logging
import os
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence

import requests

from utils.config import ORS_KEY
from utils.logger import get_logger

DEFAULT_MATRIX_URL = "https://api.openrouteservice.org/v2/matrix/foot-walking"
log = get_logger("[RouteOptimizer]")


class ORSError(RuntimeError):
    """Raised when OpenRouteService responds with an error."""


def build_matrix_request(
    locations: Sequence[Sequence[float]],
    sources: Sequence[int],
    destinations: Sequence[int],
    profile: str = "foot-walking",
) -> Dict[str, Any]:
    return {
        "locations": locations,
        "profile": profile,
        "metrics": ["duration"],
        "sources": list(sources),
        "destinations": list(destinations),
    }


def post_matrix_request(
    payload: Mapping[str, Any],
    *,
    api_key: Optional[str] = None,
    url: str = DEFAULT_MATRIX_URL,
    timeout: float = 30.0,
) -> Mapping[str, Any]:

    key = api_key or ORS_KEY
    if not key:
        raise EnvironmentError("ORS_KEY is not configured")

    headers = {
        "Authorization": key,
        "Content-Type": "application/json",
    }

    response = requests.post(url, headers=headers, json=dict(payload), timeout=timeout)
    if response.status_code != 200:
        log.error("ORS matrix error %s: %s", response.status_code, response.text)
        raise ORSError(f"ORS error {response.status_code}: {response.text}")

    try:
        return response.json()
    except ValueError as exc:
        raise ORSError("ORS response is not valid JSON") from exc


def fetch_point_to_points_durations(
    origin: Mapping[str, float],
    targets: Iterable[Mapping[str, Any]],
    *,
    api_key: Optional[str] = None,
    profile: str = "foot-walking",
    url: str = DEFAULT_MATRIX_URL,
    timeout: float = 30.0,
) -> Dict[Any, float]:
    longitude = float(origin["longitude"])
    latitude = float(origin["latitude"])
    locations = [[longitude, latitude]]

    ids: list[Any] = []
    for target in targets:
        try:
            lon = float(target["lon"])
            lat = float(target["lat"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "each target must provide numeric 'lon' and 'lat'"
            ) from exc
        ids.append(target["id"])
        locations.append([lon, lat])

    if len(locations) == 1:
        return {}

    payload = build_matrix_request(
        locations,
        sources=[0],
        destinations=list(range(1, len(locations))),
        profile=profile,
    )

    result = post_matrix_request(payload, api_key=api_key, url=url, timeout=timeout)
    durations = result.get("durations")
    if not durations:
        return {}

    first_row = durations[0]
    if len(first_row) != len(ids):
        log.warning(
            "ORS returned unexpected duration count: expected %s got %s",
            len(ids),
            len(first_row),
        )

    mapping: MutableMapping[Any, float] = {}
    for idx, value in enumerate(first_row):
        try:
            target_id = ids[idx]
        except IndexError:
            break
        if value is None:
            continue
        mapping[target_id] = float(value)
    return dict(mapping)
