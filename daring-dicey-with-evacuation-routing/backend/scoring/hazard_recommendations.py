"""
scoring/hazard_recommendations.py

Deterministic, rule-based recommendations from already-computed evidence.
NOT an LLM -- every recommendation here traces to a specific rule keyed off
real detected damage types, so it can be read and defended line by line.
The LLM (llm/report_generator.py) consumes this module's OUTPUT as
structured input; it never generates recommendations on its own.

Only locations with is_disaster=True are considered. A hazard rule only
fires if that hazard's damage_type was actually detected -- this module
NEVER invents a hazard that wasn't in the evidence.
"""
from typing import List, Dict, Any

DISCLAIMER = (
    "These are AI-generated decision-support recommendations based on detected "
    "visual evidence only. They are NOT an authoritative emergency evacuation "
    "order or verified safety assessment -- confirm with ground-truth "
    "information and qualified responders before acting."
)

# Damage-type substrings (case-insensitive) that trigger each hazard rule.
# Kept as substring matches so e.g. "Pothole", "Alligator Crack", etc. all
# trigger the generic "road damage" rule without listing every road class.
BUILDING_TYPES = {"damaged building"}
ROAD_TYPES = {"pothole", "alligator crack", "block crack", "unspecified crack",
              "edge crack", "longitudinal crack", "transverse crack"}
DEBRIS_TYPES = {"debris"}
FIRE_TYPES = {"fire"}
SMOKE_TYPES = {"smoke"}
FLOOD_TYPES = {"flooding"}
EARTHQUAKE_TYPES = {  # from the earthquake CLIP module's own vocabulary
    "building collapse", "partial wall collapse", "fallen structural elements",
    "structural fractures", "major wall cracks", "severe deformation",
    "roof damage", "cracks in walls", "critical / collapse-level damage",
    "severe damage", "moderate damage", "minor damage",
}

# Disaster-specific "immediate action" framing shown once per critical/high
# location when that disaster type is selected -- these are the only lines
# that vary by disaster_type; every hazard-specific rule below is disaster-agnostic.
DISASTER_IMMEDIATE_FRAMING = {
    "earthquake": "Move people to open/safe areas away from structures; check for secondary structural hazards before re-entry.",
    "flood": "Move to higher ground immediately.",
    "fire": "Evacuate the affected zone immediately.",
    "wildfire": "Evacuate the affected zone immediately.",
    "cyclone": "Move away from exposed/open areas; seek appropriate shelter.",
    "landslide": "Avoid slope/failure zones; move away from unstable terrain.",
    "other": "Exercise caution based on the detected evidence below; the specific disaster type is unclassified.",
}


def _matches(damage_type: str, type_set: set) -> bool:
    return damage_type.strip().lower() in type_set


def _rec(priority, action, reason, hazard, location_id, confidence, category):
    return {
        "priority": priority, "action": action, "reason": reason, "hazard": hazard,
        "location": location_id, "confidence": round(confidence, 4) if confidence is not None else None,
        "category": category,
    }


def _hazard_rules_for_location(loc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Evidence-driven rules -- fire regardless of selected disaster_type,
    purely based on what was actually detected at this location."""
    location_id = loc["location_id"]
    severity_level = loc["severity_level"]
    recs = []

    detections_by_hazard = {
        "Building damage": (BUILDING_TYPES, []),
        "Earthquake structural damage": (EARTHQUAKE_TYPES, []),
        "Road damage": (ROAD_TYPES, []),
        "Debris": (DEBRIS_TYPES, []),
        "Fire": (FIRE_TYPES, []),
        "Smoke": (SMOKE_TYPES, []),
        "Flooding": (FLOOD_TYPES, []),
    }
    for d in loc["detected_damage"]:
        for hazard_name, (type_set, bucket) in detections_by_hazard.items():
            if _matches(d["damage_type"], type_set):
                bucket.append(d)

    for hazard_name, (_, dets) in detections_by_hazard.items():
        if not dets:
            continue
        best_confidence = max(d["confidence"] for d in dets)
        count = len(dets)
        reason = f"{count} '{hazard_name}' detection(s) at this location, highest confidence {best_confidence:.0%}."

        if hazard_name in ("Building damage", "Earthquake structural damage"):
            recs.append(_rec(severity_level, "Avoid entering or approaching damaged structures.",
                              reason, hazard_name, location_id, best_confidence, "hazard_specific"))
            recs.append(_rec(severity_level, "Check for secondary structural hazards before any re-entry.",
                              reason, hazard_name, location_id, best_confidence, "hazard_specific"))
        elif hazard_name == "Road damage":
            recs.append(_rec(severity_level, "Avoid the damaged road segment(s); use alternate access routes.",
                              reason, hazard_name, location_id, best_confidence, "hazard_specific"))
        elif hazard_name == "Debris":
            recs.append(_rec(severity_level, "Keep emergency access corridors clear of debris.",
                              reason, hazard_name, location_id, best_confidence, "hazard_specific"))
        elif hazard_name == "Fire":
            recs.append(_rec("CRITICAL", "Evacuate the affected zone immediately.",
                              reason, hazard_name, location_id, best_confidence, "immediate"))
            recs.append(_rec(severity_level, "Avoid smoke-affected areas.",
                              reason, hazard_name, location_id, best_confidence, "avoid"))
            recs.append(_rec(severity_level, "Prioritize emergency/fire-response access to this location.",
                              reason, hazard_name, location_id, best_confidence, "resource_priority"))
        elif hazard_name == "Smoke":
            recs.append(_rec(severity_level, "Move away from the smoke plume; consider respiratory protection where appropriate.",
                              reason, hazard_name, location_id, best_confidence, "hazard_specific"))
        elif hazard_name == "Flooding":
            recs.append(_rec(severity_level, "Avoid submerged/flooded roads.",
                              reason, hazard_name, location_id, best_confidence, "avoid"))
            recs.append(_rec(severity_level, "Avoid contact with potentially contaminated floodwater.",
                              reason, hazard_name, location_id, best_confidence, "avoid"))

    return recs


def _immediate_framing_for_location(disaster_type: str, loc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The one disaster-type-specific line per high/critical location."""
    if loc["severity_level"] not in ("CRITICAL", "HIGH"):
        return []
    key = (disaster_type or "").strip().lower()
    framing = DISASTER_IMMEDIATE_FRAMING.get(key, DISASTER_IMMEDIATE_FRAMING["other"])
    return [_rec(loc["severity_level"], framing,
                  f"Severity classified as {loc['severity_level']} at this location.",
                  "Overall severity", loc["location_id"], None, "immediate")]


def build_recommendations(disaster_type: str, locations: List[Dict[str, Any]],
                            evacuation_plan: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    locations: locations_sorted from api/backend.py (already gated + scored).
    evacuation_plan: output of evacuation_planner.build_evacuation_plan(), used
    only to attach a resource_priority recommendation for the #1 priority
    location -- no new logic duplicated here.

    Returns {'items': [...], 'immediate_actions': [...], 'hazard_specific_actions': [...],
    'avoid': [...], 'resource_priorities': [...], 'disclaimer': str}
    """
    disaster_locs = [loc for loc in locations if loc.get("is_disaster")]

    items: List[Dict[str, Any]] = []
    for loc in disaster_locs:
        items.extend(_immediate_framing_for_location(disaster_type, loc))
        items.extend(_hazard_rules_for_location(loc))

    if evacuation_plan and evacuation_plan.get("priorities"):
        top = evacuation_plan["priorities"][0]
        items.append(_rec(top["severity_level"],
                           f"Send emergency resources to {top['location_id'].replace('_', ' ')} first (priority #1).",
                           top["reason"], "Resource allocation", top["location_id"], None, "resource_priority"))

    by_category = {cat: [r for r in items if r["category"] == cat]
                   for cat in ("immediate", "hazard_specific", "avoid", "resource_priority")}

    return {
        "items": items,
        "immediate_actions": by_category["immediate"],
        "hazard_specific_actions": by_category["hazard_specific"],
        "avoid": by_category["avoid"],
        "resource_priorities": by_category["resource_priority"],
        "disclaimer": DISCLAIMER,
    }
