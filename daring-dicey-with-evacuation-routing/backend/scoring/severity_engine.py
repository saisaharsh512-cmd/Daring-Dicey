"""
scoring/severity_engine.py

Deterministic, explainable severity scoring. No ML, no opaque logic --
every step below can be read aloud to a judge.

PER-DETECTION SEVERITY:
    severity_value = base_severity(model, damage_type) * (0.5 + 0.5 * confidence)

    Confidence only SOFTENS a detection's contribution (0.5x-1.0x range) --
    it never determines severity by itself. A low-confidence "collapse"
    still scores far higher than a high-confidence "hairline crack", exactly
    per the project's "severity != confidence" requirement.

PER-LOCATION SEVERITY (combining evidence from possibly many models/images):
    location_score = min(100,
        weighted_max_evidence          # the single worst piece of weighted evidence
        + corroboration_bonus          # capped bonus: multiple independent models agree
        + count_bonus                  # capped bonus: more total detections
    )

    weighted_max_evidence = max(severity_value(d) * model_weight(disaster, d.model) for d in evidence)

    corroboration_bonus = min(15, 5 * (distinct_models_with_evidence - 1))
    count_bonus          = min(10, 1 * total_detection_count)

    Rationale: a single confirmed "building collapse" already signals a
    critical location on its own (that's why MAX drives the base score, not
    an average that would get diluted by many minor detections). Additional
    independent models corroborating the same location, or more detections
    overall, nudge the score up further but are capped so they can't let
    many small pieces of weak evidence outscore one severe confirmed one.
"""
import logging
from typing import List, Dict, Any

from scoring.disaster_weights import get_base_severity, get_weights

log = logging.getLogger("backend.severity_engine")

SEVERITY_THRESHOLDS = [(25, "LOW"), (50, "MODERATE"), (75, "HIGH"), (101, "CRITICAL")]

CORROBORATION_BONUS_CAP = 15
CORROBORATION_BONUS_PER_MODEL = 5
COUNT_BONUS_CAP = 10
COUNT_BONUS_PER_DETECTION = 1


def severity_level(score: float) -> str:
    for threshold, level in SEVERITY_THRESHOLDS:
        if score < threshold:
            return level
    return "CRITICAL"


def compute_detection_severity_value(model: str, damage_type: str, confidence: float) -> float:
    """The per-detection severity_value: base type-severity, softened (never driven) by confidence."""
    base = get_base_severity(model, damage_type)
    return round(base * (0.5 + 0.5 * confidence), 2)


def compute_location_severity(
    evidence: List[Dict[str, Any]],
    disaster_type: str,
) -> Dict[str, Any]:
    """
    evidence: list of standardized detections, each with 'model', 'damage_type',
    'confidence', 'severity_value' (already computed via compute_detection_severity_value).

    Returns {'score': float, 'level': str, 'explanation': str}.
    """
    if not evidence:
        return {"score": 0.0, "level": "LOW", "explanation": "No damage evidence detected at this location."}

    weights = get_weights(disaster_type)

    weighted = []
    for d in evidence:
        w = weights.get(d["model"], 0.5)
        weighted.append(d["severity_value"] * w)

    weighted_max = max(weighted)
    distinct_models = len(set(d["model"] for d in evidence))
    corroboration_bonus = min(CORROBORATION_BONUS_CAP, CORROBORATION_BONUS_PER_MODEL * (distinct_models - 1))
    count_bonus = min(COUNT_BONUS_CAP, COUNT_BONUS_PER_DETECTION * len(evidence))

    score = round(min(100.0, weighted_max + corroboration_bonus + count_bonus), 2)
    level = severity_level(score)

    explanation = (
        f"Worst weighted evidence contributed {weighted_max:.1f} pts "
        f"(disaster-relevance-weighted severity of the single most severe detection); "
        f"+{corroboration_bonus:.0f} pts for {distinct_models} independent model(s) agreeing; "
        f"+{count_bonus:.0f} pts for {len(evidence)} total detection(s). "
        f"Final score capped at 100."
    )

    log.info("[SCORING] location severity = %.1f (%s)", score, level)
    return {"score": score, "level": level, "explanation": explanation}
