"""Road-network evacuation routing helper.

This module asks a routing engine for a road route between a disaster location
and a responder-selected safe zone. It deliberately does not claim that a
route is operationally safe: the public routing graph does not know live road
closures, flooding, fire lines, traffic, or emergency access restrictions.
"""
import os
from typing import Any, Dict

import requests

DEFAULT_OSRM_BASE_URL = "https://router.project-osrm.org"
ROUTE_DISCLAIMER = (
    "Road-network route only. This route does not know live road closures, "
    "flooding, fire lines, traffic, or emergency access restrictions. "
    "Verify the route with local authorities before evacuation."
)


def _valid_coord(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("coordinates must be numeric")
    if not low <= number <= high:
        raise ValueError("coordinates are outside valid geographic bounds")
    return number


def calculate_road_route(
    origin_latitude: Any,
    origin_longitude: Any,
    destination_latitude: Any,
    destination_longitude: Any,
) -> Dict[str, Any]:
    """Return a GeoJSON route plus distance/time from the configured OSRM service."""
    o_lat = _valid_coord(origin_latitude, -90, 90)
    o_lon = _valid_coord(origin_longitude, -180, 180)
    d_lat = _valid_coord(destination_latitude, -90, 90)
    d_lon = _valid_coord(destination_longitude, -180, 180)

    base_url = os.getenv("OSRM_BASE_URL", DEFAULT_OSRM_BASE_URL).rstrip("/")
    url = f"{base_url}/route/v1/driving/{o_lon},{o_lat};{d_lon},{d_lat}"
    response = requests.get(
        url,
        params={"overview": "full", "geometries": "geojson", "steps": "false"},
        timeout=15,
        headers={"User-Agent": "Daring-Dicey-Disaster-Response-Demo/1.0"},
    )
    response.raise_for_status()
    payload = response.json()

    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise RuntimeError(payload.get("message") or "No drivable route was found")

    route = payload["routes"][0]
    geometry = route.get("geometry", {}).get("coordinates", [])
    if len(geometry) < 2:
        raise RuntimeError("Routing service returned an incomplete route")

    return {
        "distance_km": round(float(route["distance"]) / 1000, 2),
        "duration_minutes": round(float(route["duration"]) / 60, 1),
        "geometry": geometry,
        "profile": "driving",
        "disclaimer": ROUTE_DISCLAIMER,
        "provider": "OSRM",
    }
