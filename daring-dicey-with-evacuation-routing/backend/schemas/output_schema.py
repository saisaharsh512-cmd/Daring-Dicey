"""
schemas/output_schema.py

The common contract every model wrapper must produce, and every downstream
stage (severity engine, aggregation, API) consumes. Defined as plain dicts
via helper constructors (not pydantic) to keep this dependency-free and easy
to import from a Colab-style environment too.

Design rule (per project requirement): never invent fields a model can't
actually support. `bbox` is None for whole-image classifiers. `evidence_type`
distinguishes real learned detections from heuristic regional evidence.
"""
from typing import Optional, List, Dict, Any


def make_detection(
    damage_type: str,
    confidence: float,
    bbox: Optional[List[float]] = None,
    evidence_type: str = "detection",
    raw_class: Optional[str] = None,
) -> Dict[str, Any]:
    """
    One piece of evidence from one model.

    evidence_type:
      "detection"         -- a real learned object detector's output (road, building, fire, debris)
      "whole_image"        -- a whole-image classifier's single label (flood)
      "regional_evidence"  -- heuristic grid-tile evidence, NOT a trained detector (earthquake)
    """
    return {
        "damage_type": damage_type,
        "confidence": round(float(confidence), 4),
        "bbox": [round(float(v), 1) for v in bbox] if bbox is not None else None,
        "evidence_type": evidence_type,
        "raw_class": raw_class if raw_class is not None else damage_type,
    }


def make_model_output(
    model: str,
    detection_type: str,
    detections: List[Dict[str, Any]],
    error: Optional[str] = None,
    notes: Optional[str] = None,
    available: bool = True,
) -> Dict[str, Any]:
    """
    Standardized output of one model wrapper for one image.

    detection_type:
      "object_detection"          -- real bounding-box detector
      "classification"             -- whole-image classifier, no localization
      "heuristic_regional_evidence" -- grid-tile CLIP-style evidence

    error: set (non-null) if this model failed to run on this image. When set,
    `detections` must be []. The rest of the pipeline must not crash because
    one optional model failed -- it just carries this error through.

    available: False specifically means "this model's dependency/environment
    is missing" (e.g. inference-sdk not installed for debris) -- distinct
    from a transient per-call failure (available=True, error=str). Callers
    must never treat available=False as a detection of any kind.
    success is derived automatically (error is None) rather than passed
    separately, so it can never be set inconsistently with error.
    confidence is the max detection confidence in this call, or None if
    there are no detections -- a single-number summary for the top-level
    model_status report, not used anywhere in severity scoring.
    """
    confidence = round(max((d["confidence"] for d in detections), default=0.0), 4) if detections else None
    return {
        "model": model,
        "detection_type": detection_type,
        "detections": detections,
        "confidence": confidence,
        "available": available,
        "success": error is None,
        "error": error,
        "notes": notes,
    }


def make_infrastructure_constraint(
    infrastructure_type: str,
    status: str,
    damage_type: str,
    confidence: float,
    location: Dict[str, float],
) -> Dict[str, Any]:
    """Structured, machine-readable info for the mapping/routing teammate."""
    return {
        "type": infrastructure_type,
        "status": status,
        "damage_type": damage_type,
        "confidence": round(float(confidence), 4),
        "location": location,
    }
