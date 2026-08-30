"""
scoring/evacuation_planner.py

Turns already-scored locations into an evacuation PRIORITY list with a
deterministic, explainable reason per location. This is explicitly
"priority based on detected visual damage" -- it does NOT know real
population density, road closures, hospital capacity, or safe routes, and
says so in every response so it's never mistaken for real-world emergency
routing.

Only locations with is_disaster=True are considered -- a location the gates
rejected never appears in the evacuation plan, regardless of what a
specialized model might otherwise have reported.
"""
from typing import List, Dict, Any

DISCLAIMER = (
    "This ordering reflects PRIORITY BASED ON DETECTED VISUAL DAMAGE ONLY. "
    "It does not use or know real-world population density, road closures, "
    "hospital capacity, or actual safe evacuation routes. Treat this as a "
    "triage starting point for human responders, not a routing decision."
)


def _summarize_evidence(location: Dict[str, Any]) -> str:
    """Deterministic one-line summary of why this location scored the way it did,
    built entirely from already-computed structured fields -- no LLM, no invention."""
    by_model: Dict[str, List[str]] = {}
    for d in location["detected_damage"]:
        by_model.setdefault(d["model"], []).append(d["damage_type"])

    if not by_model:
        return "No damage evidence."

    parts = []
    for model, types in by_model.items():
        distinct = sorted(set(types))
        parts.append(f"{model}: {', '.join(distinct)}")

    blocked_roads = [c for c in location.get("infrastructure_constraints", []) if c["type"] == "road" and c["status"] == "blocked"]
    if blocked_roads:
        parts.append(f"{len(blocked_roads)} blocked road segment(s) detected")

    return "; ".join(parts)


def build_evacuation_plan(locations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    locations: the full locations_sorted list from api/backend.py (already
    ranked by severity). Only is_disaster=True entries are included here.

    Returns {'priorities': [...], 'disclaimer': str, 'num_locations_considered': int}.
    """
    disaster_locations = [loc for loc in locations if loc.get("is_disaster")]

    priorities = []
    for loc in disaster_locations:
        priorities.append({
            "location_id": loc["location_id"],
            "priority_rank": loc["priority_rank"],
            "latitude": loc["latitude"],
            "longitude": loc["longitude"],
            "severity_score": loc["severity_score"],
            "severity_level": loc["severity_level"],
            "reason": _summarize_evidence(loc),
        })

    # Already sorted upstream by priority_rank (severity descending) -- re-sort
    # defensively so this function's output is correct even if called standalone.
    priorities.sort(key=lambda p: p["priority_rank"])

    return {
        "priorities": priorities,
        "disclaimer": DISCLAIMER,
        "num_locations_considered": len(disaster_locations),
    }
