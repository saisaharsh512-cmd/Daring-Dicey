"""
api/backend.py

The single entry point: analyze_disaster(disaster_type, images) -> structured result.

Pipeline: validate -> [PER IMAGE: general relevance gate -> disaster-type
relevance gate -> ONLY IF BOTH PASS: routed specialized models] -> per-detection
severity -> location clustering -> per-location severity aggregation ->
priority ranking -> infrastructure constraints for the mapping team.

The gates (scoring/relevance_gate.py) are enforced inside inference_engine.py's
analyze_image(), not here -- this module only rolls up already-gated results.
A specialized model NEVER runs on an image that failed either gate (RULE 1/2).
"""
import logging
from typing import List, Dict, Any, Optional

from inference.inference_engine import validate_image, validate_location, analyze_image
from aggregation.location_aggregator import cluster_images, DEFAULT_CLUSTER_TOLERANCE_METERS
from scoring.severity_engine import compute_location_severity
from scoring.disaster_weights import get_route
from scoring.evacuation_planner import build_evacuation_plan
from scoring.rescue_allocation import build_rescue_allocation
from scoring.hazard_recommendations import build_recommendations
from schemas.output_schema import make_infrastructure_constraint
from llm.report_generator import generate_report

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("backend.api")

# Damage types that constitute a mapping-relevant infrastructure constraint,
# and what status they imply. Deliberately conservative/explainable: only
# road and building/debris evidence above these thresholds gets surfaced as
# a hard constraint, everything else stays in detected_damage only.
ROAD_BLOCK_TYPES = {"Pothole", "Alligator Crack"}          # severe enough to imply "blocked", not just "damaged"
ROAD_DAMAGE_TYPES = set()  # populated below to include every other road class as "damaged" (not "blocked")

# Priority order for rolling up multiple images' gate_status into one batch-level status.
_GATE_STATUS_PRIORITY = [
    "DISASTER_DETECTED", "UNCERTAIN_TYPE_RELEVANCE", "NOT_RELEVANT_TO_SELECTED_TYPE",
    "UNCERTAIN_NOT_A_DISASTER", "NOT_A_DISASTER",
]


def _road_damage_types():
    from scoring.disaster_weights import ROAD_BASE_SEVERITY
    return set(ROAD_BASE_SEVERITY.keys()) - ROAD_BLOCK_TYPES


ROAD_DAMAGE_TYPES = _road_damage_types()


def _build_infrastructure_constraints(evidence: List[Dict[str, Any]], location: Dict[str, float]) -> List[Dict[str, Any]]:
    constraints = []
    for d in evidence:
        if d["model"] == "road":
            if d["damage_type"] in ROAD_BLOCK_TYPES:
                constraints.append(make_infrastructure_constraint(
                    "road", "blocked", d["damage_type"], d["confidence"], location))
            elif d["damage_type"] in ROAD_DAMAGE_TYPES:
                constraints.append(make_infrastructure_constraint(
                    "road", "damaged", d["damage_type"], d["confidence"], location))
        elif d["model"] == "building" and d["severity_value"] >= 60:
            constraints.append(make_infrastructure_constraint(
                "building", "unsafe", d["damage_type"], d["confidence"], location))
        elif d["model"] == "debris":
            constraints.append(make_infrastructure_constraint(
                "debris", "obstruction", d["damage_type"], d["confidence"], location))
    return constraints


def _disaster_category_label(disaster_type: str, is_disaster: bool) -> str:
    if not is_disaster:
        return "Not a Disaster"
    if (disaster_type or "").strip().lower() == "other":
        return "Other / Unclassified Disaster"
    return (disaster_type or "").strip().title()


def _build_model_status(disaster_type: str, is_disaster: bool, per_image_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Batch-level model status (one entry per model that could plausibly be
    relevant to this disaster_type, per the router). Never presents a model
    error or gate-block as a detection -- see RULE 3/4.
    """
    r = get_route(disaster_type)
    statuses = []

    for model_name in r["run"]:
        if not is_disaster:
            statuses.append({"model": model_name, "status": "gate_blocked",
                              "reason": "specialized models were not run because no image passed the disaster relevance gate"})
            continue

        succeeded = unavailable = errored = False
        for img_result in per_image_results.values():
            output = img_result["model_outputs"].get(model_name)
            if output is None:
                continue
            if output["success"]:
                succeeded = True
            elif not output["available"]:
                unavailable = True
            else:
                errored = True

        if succeeded:
            statuses.append({"model": model_name, "status": "success", "reason": None})
        elif unavailable:
            statuses.append({"model": model_name, "status": "unavailable", "reason": "dependency/environment issue -- see model_errors"})
        elif errored:
            statuses.append({"model": model_name, "status": "error", "reason": "see model_errors"})
        else:
            statuses.append({"model": model_name, "status": "not_run", "reason": None})

    for model_name in r["skip"]:
        statuses.append({"model": model_name, "status": "not_relevant",
                          "reason": f"not relevant to selected disaster type '{disaster_type}'"})

    return statuses


def analyze_disaster(
    disaster_type: str,
    images: List[Dict[str, Any]],
    cluster_tolerance_meters: float = DEFAULT_CLUSTER_TOLERANCE_METERS,
    total_rescue_members: int = 0,
) -> Dict[str, Any]:
    """
    images: list of {'image_path': str, 'location': {'latitude': float, 'longitude': float}}
            (also accepts flat 'latitude'/'longitude' keys for convenience)

    Returns the full structured result -- see README for the exact schema.
    """
    log.info("[PIPELINE] analyze_disaster(disaster_type=%r, %d image(s))", disaster_type, len(images))

    valid_images = []
    skipped_images = []

    for entry in images:
        image_path = entry.get("image_path")
        img_check = validate_image(image_path) if image_path else {"valid": False, "error": "missing image_path"}
        loc_check = validate_location(entry)

        if not img_check["valid"] or not loc_check["valid"]:
            skipped_images.append({
                "image_path": image_path,
                "image_error": img_check["error"],
                "location_error": loc_check["error"],
            })
            log.warning("[VALIDATION] skipping %s -- image_error=%s location_error=%s",
                        image_path, img_check["error"], loc_check["error"])
            continue

        valid_images.append({
            "image_path": image_path,
            "latitude": loc_check["latitude"],
            "longitude": loc_check["longitude"],
            "metadata": entry.get("metadata"),
        })

    per_image_results = {}
    for img in valid_images:
        result = analyze_image(img["image_path"], disaster_type)
        per_image_results[img["image_path"]] = result

    # Batch-level gate rollup, computed from every valid image's gate result.
    any_gate_passed = any(r["gate_passed"] for r in per_image_results.values())
    disaster_confidence = (
        max((r["general_gate"]["positive_probability"] for r in per_image_results.values()), default=None)
    )
    type_relevance = (
        max((r["type_gate"]["positive_probability"] for r in per_image_results.values() if r["type_gate"] is not None), default=None)
    )
    if per_image_results:
        statuses_seen = {r["gate_status"] for r in per_image_results.values()}
        batch_gate_status = next((s for s in _GATE_STATUS_PRIORITY if s in statuses_seen), "NOT_A_DISASTER")
    else:
        batch_gate_status = "NOT_A_DISASTER"

    clusters = cluster_images(valid_images, tolerance_meters=cluster_tolerance_meters)

    locations = []
    for cluster in clusters:
        location_id = cluster["location_id"]
        centroid = cluster["centroid"]

        all_evidence = []
        detected_damage = []
        location_gate_passed = False
        for img in cluster["images"]:
            img_result = per_image_results[img["image_path"]]
            if img_result["gate_passed"]:
                location_gate_passed = True
            all_evidence.extend(img_result["evidence"])
            for d in img_result["evidence"]:
                detected_damage.append({
                    "model": d["model"],
                    "damage_type": d["damage_type"],
                    "severity": d["severity_value"],
                    "confidence": d["confidence"],
                    "bbox": d["bbox"],
                    "evidence_type": d["evidence_type"],
                    "source_image": d["image_path"],
                })

        severity = compute_location_severity(all_evidence, disaster_type) if location_gate_passed else \
            {"score": 0.0, "level": "LOW", "explanation": "No image at this location passed the disaster relevance gate -- no specialized models were run."}
        infrastructure_constraints = _build_infrastructure_constraints(all_evidence, centroid) if location_gate_passed else []

        model_errors = {}
        for img in cluster["images"]:
            for model_name, output in per_image_results[img["image_path"]]["model_outputs"].items():
                if output.get("error"):
                    model_errors.setdefault(model_name, []).append({
                        "image_path": img["image_path"], "error": output["error"], "available": output["available"],
                    })

        cluster_gate_statuses = [per_image_results[img["image_path"]]["gate_status"] for img in cluster["images"]]
        loc_gate_status = next((s for s in _GATE_STATUS_PRIORITY if s in set(cluster_gate_statuses)), "NOT_A_DISASTER")

        locations.append({
            "location_id": location_id,
            "latitude": centroid["latitude"],
            "longitude": centroid["longitude"],
            "num_images": len(cluster["images"]),
            "is_disaster": location_gate_passed,
            "gate_status": loc_gate_status,
            "severity_score": severity["score"],
            "severity_level": severity["level"] if location_gate_passed else "NONE",
            "severity_explanation": severity["explanation"],
            "detected_damage": detected_damage,
            "infrastructure_constraints": infrastructure_constraints,
            "model_errors": model_errors,
        })

    # Priority ranking: sort by severity_score desc. Deterministic tie-break:
    # (1) presence of any single detection with severity_value >= 90 (near-critical
    #     individual evidence, e.g. collapse) ranks first among ties,
    # (2) then by number of distinct models corroborating (more corroboration first),
    # (3) then by location_id ascending, for full determinism.
    def _has_critical_evidence(loc):
        return any(d["severity"] >= 90 for d in loc["detected_damage"])

    def _num_models(loc):
        return len(set(d["model"] for d in loc["detected_damage"]))

    locations_sorted = sorted(
        locations,
        key=lambda loc: (
            -loc["severity_score"],
            not _has_critical_evidence(loc),
            -_num_models(loc),
            loc["location_id"],
        ),
    )

    for rank, loc in enumerate(locations_sorted, start=1):
        loc["priority_rank"] = rank
        log.info("[PRIORITY] %s ranked #%d (severity=%.1f, is_disaster=%s)",
                  loc["location_id"], rank, loc["severity_score"], loc["is_disaster"])

    priority_order = [
        {"location_id": loc["location_id"], "severity_score": loc["severity_score"], "priority_rank": loc["priority_rank"]}
        for loc in locations_sorted
    ]

    model_status = _build_model_status(disaster_type, any_gate_passed, per_image_results)
    disaster_category_label = _disaster_category_label(disaster_type, any_gate_passed)

    overall_severity_level = "NONE"
    if any_gate_passed and locations_sorted:
        levels_present = [loc["severity_level"] for loc in locations_sorted if loc["is_disaster"]]
        for lvl in ["CRITICAL", "HIGH", "MODERATE", "LOW"]:
            if lvl in levels_present:
                overall_severity_level = lvl
                break

    # Per-image gate detail, explicitly requested (RULE-level transparency):
    # general_gate_status / type_gate_status / gate_confidence / gate_reason.
    images_summary = []
    for img in valid_images:
        r = per_image_results[img["image_path"]]
        images_summary.append({
            "image_path": img["image_path"],
            "latitude": img["latitude"],
            "longitude": img["longitude"],
            "is_disaster": r["gate_passed"],
            "gate_status": r["gate_status"],
            "general_gate_status": r["general_gate"]["state"],
            "type_gate_status": r["type_gate"]["state"] if r["type_gate"] is not None else None,
            "gate_confidence": r["general_gate"]["confidence"],
            "gate_reason": r["general_gate"]["reason"] if not r["gate_passed"] and r["general_gate"]["state"] != "RELEVANT"
                           else (r["type_gate"]["reason"] if r["type_gate"] is not None and r["type_gate"]["state"] != "RELEVANT"
                                 else r["general_gate"]["reason"]),
        })

    # Batch-level representative gate detail -- picks the first image matching
    # the overall batch_gate_status so the top-level summary is internally consistent.
    representative = next((s for s in images_summary if s["gate_status"] == batch_gate_status), None) \
        or (images_summary[0] if images_summary else None)
    general_gate_status = representative["general_gate_status"] if representative else None
    type_gate_status = representative["type_gate_status"] if representative else None
    gate_confidence = representative["gate_confidence"] if representative else None
    gate_reason = representative["gate_reason"] if representative else "No valid images were submitted."

    evacuation_plan = build_evacuation_plan(locations_sorted)
    rescue_allocation = build_rescue_allocation(locations_sorted, total_rescue_members)
    recommendations = build_recommendations(disaster_type, locations_sorted, evacuation_plan)

    report = {
        "overall_status": "DISASTER_DETECTED" if any_gate_passed else "NOT_A_DISASTER",
        "selected_disaster": disaster_type,
        "disaster_category_label": disaster_category_label,
        "disaster_confidence": disaster_confidence,
        "type_relevance": type_relevance,
        "overall_severity_level": overall_severity_level,
        "num_locations": len(locations_sorted),
        "num_images_analyzed": len(valid_images),
        "num_images_skipped": len(skipped_images),
        "model_status": model_status,
    }

    hazards = sorted(set(
        d["damage_type"] for loc in locations_sorted if loc["is_disaster"] for d in loc["detected_damage"]
    ))

    result = {
        "success": True,
        "is_disaster": any_gate_passed,
        "disaster_type": disaster_type,
        "overall_severity": overall_severity_level,
        "disaster_confidence": disaster_confidence,
        "type_relevance": type_relevance,
        "gate_status": batch_gate_status,
        "general_gate_status": general_gate_status,
        "type_gate_status": type_gate_status,
        "gate_confidence": gate_confidence,
        "gate_reason": gate_reason,
        "images": images_summary,
        "locations": locations_sorted,
        "hazards": hazards,
        "priority_order": priority_order,
        "evacuation_plan": evacuation_plan,
        "rescue_allocation": rescue_allocation,
        "recommendations": recommendations,
        "model_status": model_status,
        "report": report,
        "skipped_images": skipped_images,
        "cluster_tolerance_meters": cluster_tolerance_meters,
    }

    llm_result = generate_report(result)
    result["llm_report"] = llm_result

    return result
