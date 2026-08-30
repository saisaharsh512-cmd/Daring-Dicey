"""
inference/disaster_router.py

Decides which models RUN for a given disaster_type. See
scoring/disaster_weights.py's DISASTER_MODEL_ROUTES for the actual
run/skip lists and the reasoning behind each.
"""
import logging

from scoring.disaster_weights import get_route, ALL_MODELS

log = logging.getLogger("backend.disaster_router")

VALID_DISASTER_TYPES = {"earthquake", "flood", "wildfire", "fire", "cyclone", "landslide", "other"}


def route(disaster_type: str) -> dict:
    """Returns {'run': [...], 'skip': [...], 'recognized': bool}."""
    key = (disaster_type or "").strip().lower()
    recognized = key in VALID_DISASTER_TYPES
    if not recognized:
        log.warning(
            "[ROUTER] disaster_type '%s' not recognized (expected one of %s) -- "
            "running all models with equal default weighting as a safe fallback",
            disaster_type, sorted(VALID_DISASTER_TYPES),
        )
    r = get_route(key)
    log.info("[ROUTER] disaster_type='%s' -> running: %s, skipping: %s", key, r["run"], r["skip"])
    return {"run": r["run"], "skip": r["skip"], "recognized": recognized}
