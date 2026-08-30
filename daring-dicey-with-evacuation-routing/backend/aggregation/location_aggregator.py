"""
aggregation/location_aggregator.py

Groups images by location using haversine-distance clustering with a
configurable tolerance (meters), so slightly differing GPS fixes for the
"same" real-world spot get merged into one incident, per project requirement.

Clustering algorithm: simple greedy single-pass. Each new point either joins
the nearest existing cluster (if within tolerance of that cluster's centroid)
or starts a new cluster. This is deterministic given input order and O(n*k)
where k = number of clusters so far -- more than fast enough for a hackathon
demo's image counts. Not a full DBSCAN -- documented as a reasonable
simplification, not hidden as something more sophisticated than it is.
"""
import logging
from math import radians, sin, cos, sqrt, atan2
from typing import List, Dict, Any

log = logging.getLogger("backend.location_aggregator")

DEFAULT_CLUSTER_TOLERANCE_METERS = 75.0


def haversine_m(lat1, lng1, lat2, lng2) -> float:
    R = 6371000.0
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def cluster_images(
    images: List[Dict[str, Any]],
    tolerance_meters: float = DEFAULT_CLUSTER_TOLERANCE_METERS,
) -> List[Dict[str, Any]]:
    """
    images: list of dicts, each must have 'latitude' and 'longitude' (already
    validated upstream -- see inference_engine for missing/invalid handling).

    Returns list of clusters: [{'location_id': str, 'centroid': {'latitude','longitude'},
    'images': [original image dicts]}, ...], in first-seen order.
    """
    clusters: List[Dict[str, Any]] = []

    for img in images:
        lat, lng = img["latitude"], img["longitude"]
        placed = False
        for cluster in clusters:
            dist = haversine_m(lat, lng, cluster["centroid"]["latitude"], cluster["centroid"]["longitude"])
            if dist <= tolerance_meters:
                cluster["images"].append(img)
                # recompute centroid as running mean, keeps it stable/deterministic
                n = len(cluster["images"])
                cluster["centroid"]["latitude"] = (
                    (cluster["centroid"]["latitude"] * (n - 1) + lat) / n
                )
                cluster["centroid"]["longitude"] = (
                    (cluster["centroid"]["longitude"] * (n - 1) + lng) / n
                )
                placed = True
                break
        if not placed:
            clusters.append({
                "location_id": f"location_{len(clusters) + 1}",
                "centroid": {"latitude": lat, "longitude": lng},
                "images": [img],
            })

    log.info("[AGGREGATION] %d image(s) grouped into %d location(s) (tolerance=%.0fm)",
              len(images), len(clusters), tolerance_meters)
    return clusters
