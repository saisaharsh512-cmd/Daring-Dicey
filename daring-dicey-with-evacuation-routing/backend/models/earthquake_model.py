"""
models/earthquake_model.py

Adapter around the existing earthquake_damage/earthquake_detector.py module
(CLIP zero-shot, preserved as-is per project constraint -- not rewritten).

Converts its native output (whole_image_classification + regional_evidence)
into the common schema used by the other five models, WITHOUT relabeling
heuristic grid-tile evidence as real object detection. Every earthquake
detection carries evidence_type="regional_evidence" through the whole
pipeline -- the severity engine and aggregation stage must treat these
differently from real detections (e.g. not summing overlapping tile areas).
"""
import logging
import sys
from pathlib import Path

from schemas.output_schema import make_detection, make_model_output

log = logging.getLogger("backend.earthquake_model")

_EARTHQUAKE_DIR = Path(__file__).resolve().parent / "earthquake"
if str(_EARTHQUAKE_DIR) not in sys.path:
    sys.path.insert(0, str(_EARTHQUAKE_DIR))

_module = None


def _get_module():
    global _module
    if _module is None:
        log.info("[MODEL] Loading earthquake model (CLIP zero-shot)...")
        import earthquake_detector as eq
        eq.load_model()
        _module = eq
        log.info("[MODEL] Earthquake model loaded")
    return _module


def analyze(image_path: str) -> dict:
    try:
        eq = _get_module()
    except Exception as e:
        return make_model_output("earthquake", "heuristic_regional_evidence", [], error=f"model load failed: {e}")

    try:
        result = eq.analyze_earthquake(image_path, save_outputs=False)
    except Exception as e:
        return make_model_output("earthquake", "heuristic_regional_evidence", [], error=f"inference failed: {e}")

    detections = []

    # Whole-image classification, if it indicates damage, is itself one piece
    # of evidence (no bbox -- it describes the whole frame).
    whole = result.get("whole_image_classification", {})
    if whole.get("label") and whole["label"] != "No visible damage":
        detections.append(
            make_detection(
                whole["label"], whole.get("confidence", 0.0), bbox=None,
                evidence_type="whole_image", raw_class=whole["label"],
            )
        )

    # Regional grid-tile evidence -- explicitly NOT real detections.
    for region in result.get("regional_evidence", []):
        detections.append(
            make_detection(
                region["damage_type"], region["confidence"], bbox=region["grid_bbox"],
                evidence_type="regional_evidence", raw_class=region["damage_type"],
            )
        )

    log.info(
        "[DETECTION] earthquake: whole-image=%s, %d regional evidence tiles",
        whole.get("label"), len(result.get("regional_evidence", [])),
    )

    output = make_model_output(
        "earthquake",
        "heuristic_regional_evidence",
        detections,
        notes=(
            f"{result.get('detection_method', 'CLIP zero-shot classification')}. "
            f"Native severity_score={result.get('severity_score')} / "
            f"{result.get('overall_severity')} available under "
            f"'_native_earthquake_output' if preferred over the unified severity engine."
        ),
    )
    output["_native_earthquake_output"] = result
    return output
