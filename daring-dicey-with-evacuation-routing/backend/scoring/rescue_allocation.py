"""
scoring/rescue_allocation.py

Deterministic rescue-team allocation based only on already-computed visual
severity/priority. `total_rescue_members` is the AVAILABLE POOL, not a number
to deploy. Each affected location has a severity-based operational cap, so a
large pool is never dumped into a single location.

This is a triage planning aid, not a real-world staffing/routing decision.
"""
from typing import Any, Dict, List

SEVERITY_CAPS = {
    "CRITICAL": 50,
    "HIGH": 35,
    "MODERATE": 20,
    "LOW": 10,
}

SPECIALIZATIONS = {
    "CRITICAL": "Urban Search & Rescue",
    "HIGH": "Rapid Response & Rescue",
    "MODERATE": "General Rescue",
    "LOW": "Rapid Response",
}


def _specialization(location: Dict[str, Any]) -> str:
    hazards = {str(d.get("damage_type", "")).lower() for d in location.get("detected_damage", [])}
    if any("fire" in h or "flame" in h for h in hazards):
        return "Fire & Rescue"
    if any("flood" in h or "water" in h for h in hazards):
        return "Flood Rescue"
    return SPECIALIZATIONS.get(location.get("severity_level", "LOW"), "General Rescue")


def _minimum_one_per_location(total: int, count: int) -> List[int]:
    """Give each location one member first when the pool is smaller than caps."""
    return [1 if i < total else 0 for i in range(count)]


def build_rescue_allocation(
    locations: List[Dict[str, Any]],
    total_rescue_members: int,
) -> Dict[str, Any]:
    """
    Allocate a bounded team to each disaster-confirmed location.

    `total_rescue_members` is the total available personnel. Unused personnel
    remain in reserve; they are never automatically assigned just because the
    pool is large.
    """
    total = max(0, int(total_rescue_members or 0))
    disaster_locations = [
        loc for loc in locations
        if loc.get("is_disaster") and loc.get("severity_level") in SEVERITY_CAPS
    ]
    disaster_locations = sorted(
        disaster_locations,
        key=lambda loc: (
            loc.get("priority_rank", 10**9),
            -float(loc.get("severity_score", 0)),
            loc.get("location_id", ""),
        ),
    )

    if not disaster_locations or total == 0:
        return {
            "total_available_members": total,
            "total_allocated_members": 0,
            "reserve_members": total,
            "num_teams": 0,
            "teams": [],
            "disclaimer": (
                "Allocation is a bounded triage plan based on detected visual "
                "damage only. It does not account for real staffing skills, "
                "fatigue, travel time, equipment, or live field conditions."
            ),
        }

    caps = [
        min(SEVERITY_CAPS[loc["severity_level"]], total)
        for loc in disaster_locations
    ]

    # If the pool is very small, spread at least one member to as many
    # prioritized locations as possible before adding extra members.
    allocations = _minimum_one_per_location(total, len(disaster_locations))
    remaining = total - sum(allocations)

    # Add personnel in priority order, never exceeding the per-location cap.
    # This deliberately leaves a reserve when every location reaches its cap.
    while remaining > 0:
        changed = False
        for i, cap in enumerate(caps):
            if allocations[i] < cap and remaining > 0:
                allocations[i] += 1
                remaining -= 1
                changed = True
        if not changed:
            break

    teams = []
    for idx, (loc, members, cap) in enumerate(zip(disaster_locations, allocations, caps), start=1):
        if members <= 0:
            continue
        level = loc["severity_level"]
        teams.append({
            "team_id": f"TEAM_{idx}",
            "team_name": f"Team {idx}",
            "members": members,
            "destination": loc["location_id"],
            "latitude": loc["latitude"],
            "longitude": loc["longitude"],
            "priority_rank": loc.get("priority_rank"),
            "severity_score": loc.get("severity_score", 0),
            "severity_level": level,
            "specialization": _specialization(loc),
            "maximum_team_size": cap,
            "hazards": sorted({d.get("damage_type") for d in loc.get("detected_damage", []) if d.get("damage_type")}),
            "reason": (
                f"{level} priority location ranked #{loc.get('priority_rank')}; "
                f"team capped at {cap} members to avoid over-deployment. "
                f"Remaining available personnel stay in reserve."
            ),
        })

    allocated = sum(t["members"] for t in teams)
    return {
        "total_available_members": total,
        "total_allocated_members": allocated,
        "reserve_members": total - allocated,
        "num_teams": len(teams),
        "teams": teams,
        "severity_caps": SEVERITY_CAPS,
        "disclaimer": (
            "Allocation is a bounded triage plan based on detected visual "
            "damage only. It does not account for real staffing skills, "
            "fatigue, travel time, equipment, or live field conditions."
        ),
    }
